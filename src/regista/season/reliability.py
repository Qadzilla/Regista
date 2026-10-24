"""How much of one season's number is the player and how much is luck: split-half reliability for every Scout terminal
metric, so the terminal and the profiles can say which numbers a season of 30-minute matches cannot yet separate.

    python -m regista.season.reliability [data/season/league.json] [--seasons 6] [--out data/season/reliability.json]

**Method.** Each season is cut in two: rounds 1-5 and rounds 6-10 (about 150 minutes for a regular in each half). Each
half is computed with the terminal's own engine (``SeasonMetrics.from_streams``: the same definitions, the same
qualifying rule scaled to the half's minutes). For a metric, every player who qualifies in both halves gives one row
(his value in half A, his value in half B); rows are centred on the mean of his role (kit slot role: FB, CB, DM, ...)
in that season, so what is left is how he differs from others in the same role, then correlated across all rows of all
seasons (``seasons``: the league regenerated with every seed shifted by 1000 per extra season, as the audit does; more
seasons give a steadier estimate of one season's reliability, not a longer season). ``r`` is that split-half
correlation; ``season_r`` is the Spearman-Brown estimate for a whole season (two halves): 2r / (1 + r), and 0 when r is
not above 0.

A metric whose split-half ``r`` is below ``NOISE_R`` (0.3) is marked ``noisy``: within a role, one season's ranking on it
is mostly luck. The synthetic league is the reason: ten 30-minute matches a club, so a regular plays about 300 minutes.

The file is committed beside the league (like ``summaries.json``) and stamped with the generator's league version and
the league file's fingerprint; a test checks both, and a slow test recomputes it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

Record = dict[str, Any]

NOISE_R = 0.3          # split-half r below this: mostly noise in one season
MIN_ROWS = 8           # fewer rows than this: no estimate (keepers' save % over three seasons has about 18)
DEFAULT_SEASONS = 6   # as the report pools leaders and rare events (regista.synth.report.LEADER_SEASONS)
FILE_NAME = "reliability.json"


def league_fingerprint(league: Record) -> str:
    """Changes when anything that shapes the league's matches changes (clubs, squads, ratings, fixtures, seeds)."""
    data = {k: league[k] for k in ("clubs", "fixtures", "generator") if k in league}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def compute(league: Record, seasons: int = DEFAULT_SEASONS) -> Record:
    from regista.season.audit import season_matches
    from regista.season.metrics import CATALOGUE, SeasonMetrics
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    matches = season_matches(league, seasons=seasons)
    n_fx = len(league["fixtures"])
    rows: dict[str, list[tuple[str, float, float]]] = defaultdict(list)   # metric -> (season:role, a, b)
    for k in range(seasons):
        chunk = matches[k * n_fx:(k + 1) * n_fx]
        halves = []
        for rounds in (range(1, 6), range(6, 11)):
            streams = [(fx, stream, None) for fx, (rnd, _h, stream) in zip(league["fixtures"], chunk) if rnd in rounds]
            halves.append(SeasonMetrics.from_streams(league, streams))
        a, b = halves
        for gid, pa in a.players.items():
            pb = b.players.get(gid)
            if pb is None:
                continue
            role = pa.info.get("role") or pa.info["position"]
            for key, m in CATALOGUE.items():
                if m.kind == "total" or pa.info["position"] not in m.positions:
                    continue
                if not (a.qualified(pa, m) and b.qualified(pb, m)):
                    continue
                rows[key].append((f"{k}:{role}", pa.values[key], pb.values[key]))
    out: dict[str, Record] = {}
    for key in CATALOGUE:
        r, n = _centred_r(rows.get(key, []))
        if r is None:
            out[key] = {"r": None, "season_r": None, "n": n, "noisy": None}
            continue
        out[key] = {"r": round(r, 3), "season_r": round(2 * r / (1 + r), 3) if r > 0 else 0.0, "n": n,
                    "noisy": r < NOISE_R}
    return {"generator_version": LEAGUE_GENERATOR_VERSION, "league_fingerprint": league_fingerprint(league),
            "seasons": seasons, "noise_r": NOISE_R, "synthetic": True,
            "method": "split-half reliability within role: rounds 1-5 against rounds 6-10 of each season, each half computed "
                      "with the terminal's engine and qualifying rule; values centred on the role's mean in that season; "
                      f"rows pooled over {seasons} regenerated seasons (seeds shifted by 1000). r is the split-half "
                      "correlation, season_r its Spearman-Brown estimate for a whole season, 2r/(1+r). noisy: r below "
                      f"{NOISE_R}, so one season's ranking within a role is mostly luck",
            "metrics": out}


def _centred_r(rows: list[tuple[str, float, float]]) -> tuple[float | None, int]:
    if len(rows) < MIN_ROWS:
        return None, len(rows)
    by: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for g, x, y in rows:
        by[g].append((x, y))
    means = {g: (statistics.fmean(x for x, _ in v), statistics.fmean(y for _, y in v)) for g, v in by.items()}
    xs = [x - means[g][0] for g, x, _ in rows]
    ys = [y - means[g][1] for g, _, y in rows]
    if statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return None, len(rows)
    return statistics.correlation(xs, ys), len(rows)


def load(league_path: Path | str, league: Record | None = None) -> Record:
    """The committed reliability beside the league file, or an empty table when it is missing or was computed for another
    league or generator (then nothing is marked, and ``stale`` says why)."""
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    path = Path(league_path).with_name(FILE_NAME)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"metrics": {}, "stale": f"no {FILE_NAME} beside the league file"}
    if data.get("generator_version") != LEAGUE_GENERATOR_VERSION:
        return {"metrics": {}, "stale": f"{FILE_NAME} was computed for generator {data.get('generator_version')}"}
    if league is not None and data.get("league_fingerprint") != league_fingerprint(league):
        return {"metrics": {}, "stale": f"{FILE_NAME} was computed for another league file"}
    return data


def main(argv: list[str] | None = None) -> int:
    from regista.season.league import load_league

    ap = argparse.ArgumentParser(prog="python -m regista.season.reliability", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("league", nargs="?", default="data/season/league.json", type=Path)
    ap.add_argument("--seasons", type=int, default=DEFAULT_SEASONS)
    ap.add_argument("--out", type=Path, default=None, help=f"default: {FILE_NAME} beside the league file")
    args = ap.parse_args(argv)
    data = compute(load_league(args.league), args.seasons)
    out = args.out or args.league.with_name(FILE_NAME)
    out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    noisy = sorted(k for k, v in data["metrics"].items() if v["noisy"])
    print(f"wrote {out}: {len(data['metrics'])} metrics, {len(noisy)} mostly noise in one season (split-half r < {NOISE_R})")
    for k, v in sorted(data["metrics"].items(), key=lambda kv: (kv[1]["r"] is None, kv[1]["r"] or 0.0)):
        print(f"  {k:32s} r {v['r']!s:>7}  season {v['season_r']!s:>7}  n {v['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
