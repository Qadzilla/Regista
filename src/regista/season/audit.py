"""Can a scout trust the league's numbers? Two checks on a whole season, regenerated in memory (no files, no Azure).

    python -m regista.season.audit [data/season/league.json] [--seasons 1]

**Split-half reliability within a role.** For each player, a stat's per-90 rate in rounds 1-5 and in rounds 6-10; within
each kit slot (the same role at every club) the rates are centred on the slot's mean, then correlated across all
starters. Near 0 means a ranking between two players in the same role is luck; clearly above 0 means it repeats, which is
what scouting needs. docs/scout-terminal/regista-data.md measured this before player ratings existed (about 0 for every
stat); this module repeats that test.

**Top scorers.** Goals per player over the season (penalties included, as a league's scoring chart counts them), with
non-penalty goals and non-penalty xG beside them.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from regista.season.league import generate_kwargs, load_league
from regista.season.playing_time import played_seconds

Record = dict[str, Any]

# stat -> test on an event credited to its player_id
SPLIT_STATS: dict[str, Any] = {
    "passes": lambda e: e["event_type"] in ("pass", "cross"),
    "shots": lambda e: e["event_type"] == "shot" and "penalty" not in e.get("qualifiers", []),
    "goals": lambda e: e["event_type"] == "goal",
    "take_ons": lambda e: e["event_type"] == "take_on",
    "take_ons_won": lambda e: e["event_type"] == "take_on" and e["outcome"] == "success",
    "tackles": lambda e: e["event_type"] == "tackle",
    "interceptions": lambda e: e["event_type"] == "interception",
    "recoveries": lambda e: e["event_type"] == "recovery",
    "pressures": lambda e: e["event_type"] == "pressure",
    "carries": lambda e: e["event_type"] == "carry",
    "crosses": lambda e: e["event_type"] == "cross",
    "key_passes": lambda e: e["event_type"] in ("pass", "cross") and "key_pass" in e.get("qualifiers", []),
    "aerial_duels_won": lambda e: e["event_type"] == "aerial_duel",
    "passes_completed": lambda e: e["event_type"] in ("pass", "cross") and e["outcome"] == "success",
    "xg": lambda e: e["event_type"] == "shot" and "penalty" not in e.get("qualifiers", []),
}
# Physical (league mode, from ``physical`` records): per-90 rates, plus the mean of a player's match top speeds.
PHYSICAL_SPLIT = ("distance_m", "hi_distance_m", "sprint_distance_m", "sprints")
# Ratios a skill decides more than the share of the ball: (numerator, denominator, minimum attempts in each half).
SPLIT_RATIOS = {"pass_completion": ("passes_completed", "passes", 30), "take_on_success": ("take_ons_won", "take_ons", 4),
                "goals_minus_xg_per_shot": ("goals", "shots", 4)}
SLOTS = (1, 2, 3, 4, 5, 6, 8, 10, 7, 9, 11)


def season_matches(league: Record, seasons: int = 1) -> list[tuple[int, Record, list[Record]]]:
    """(round, match header, stream) for every fixture, regenerated with ratings; ``seasons`` > 1 shifts every seed by
    1000 per extra season (rounds keep their numbers)."""
    import multiprocessing
    import os
    from concurrent.futures import ProcessPoolExecutor

    jobs = []
    for k in range(seasons):
        for fx in league["fixtures"]:
            kw = generate_kwargs(league, fx)
            kw["seed"] += 1000 * k
            jobs.append(kw)
    workers = min(len(jobs), os.cpu_count() or 1)
    streams = None
    if workers > 1:   # one process per core: a league match takes about a second to generate
        try:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                streams = list(pool.map(_stream, jobs, chunksize=2))
        except Exception:  # noqa: BLE001 - no worker processes here (an interactive or piped __main__): one by one
            streams = None
    if streams is None:
        streams = [_stream(kw) for kw in jobs]
    return [(fx["round"], stream[0], stream) for fx, stream in zip([f for _k in range(seasons) for f in league["fixtures"]],
                                                                       streams)]


def _stream(kw: Record) -> list[Record]:
    from regista.synth.generator import generate

    return generate(**kw).stream


def _tallies(matches: list[tuple[int, Record, list[Record]]], rounds: set[int]) -> tuple[dict, dict]:
    counts: dict[str, Counter] = defaultdict(Counter)
    minutes: Counter = Counter()
    for rnd, header, stream in matches:
        if rnd not in rounds:
            continue
        gid = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
        for pid, s in played_seconds(stream).items():
            minutes[gid[pid]] += s / 60.0
        for e in stream:
            if e.get("type") == "physical":
                g = gid[e["player_id"]]
                for key in PHYSICAL_SPLIT:
                    counts[g][key] += e["metrics"][key]
                if e["played_s"] >= 600:   # a top speed from at least 10 minutes on the pitch
                    counts[g]["peak_sum"] += e["metrics"]["peak_speed_kmh"]
                    counts[g]["peak_n"] += 1
                continue
            if e.get("type") != "event" or not e.get("player_id"):
                continue
            g = gid[e["player_id"]]
            for key, test in SPLIT_STATS.items():
                if test(e):
                    counts[g][key] += e.get("metrics", {}).get("xg", 0.0) if key == "xg" else 1
    return counts, minutes


def split_half(league: Record, matches: list[tuple[int, Record, list[Record]]] | None = None) -> dict[str, Record]:
    """stat -> {"r_all": r across all starters, "r_slot": r with each kit slot's mean removed, "n": players}."""
    matches = matches if matches is not None else season_matches(league)
    a_counts, a_min = _tallies(matches, set(range(1, 6)))
    b_counts, b_min = _tallies(matches, set(range(6, 11)))
    starters = [(p["global_id"], p["kit_number"]) for c in league["clubs"] for p in c["squad"] if p["kit_number"] in SLOTS]
    out = {}
    physical = any(r.get("type") == "physical" for _rnd, _h, st in matches[:1] for r in st)
    for key in list(SPLIT_STATS) + (list(PHYSICAL_SPLIT) + ["peak_speed_kmh"] if physical else []):
        rows = []
        for gid, kit in starters:
            if a_min[gid] < 30 or b_min[gid] < 30:
                continue
            a, b = a_counts[gid], b_counts[gid]
            if key == "peak_speed_kmh":
                if a["peak_n"] and b["peak_n"]:
                    rows.append((kit, a["peak_sum"] / a["peak_n"], b["peak_sum"] / b["peak_n"]))
                continue
            rows.append((kit, a[key] * 90 / a_min[gid], b[key] * 90 / b_min[gid]))
        xs, ys = [r[1] for r in rows], [r[2] for r in rows]
        by: dict[int, list] = defaultdict(list)
        for kit, x, y in rows:
            by[kit].append((x, y))
        means = {k: (statistics.fmean(x for x, _ in v), statistics.fmean(y for _, y in v)) for k, v in by.items()}
        cx = [x - means[k][0] for k, x, _ in rows]
        cy = [y - means[k][1] for k, _, y in rows]
        out[key] = {"r_all": _r(xs, ys), "r_slot": _r(cx, cy), "n": len(rows)}
    for key, (num, den, least) in SPLIT_RATIOS.items():
        rows = []
        for gid, kit in starters:
            a, b = a_counts[gid], b_counts[gid]
            if a[den] < least or b[den] < least:
                continue
            if key == "goals_minus_xg_per_shot":
                rows.append((kit, (a["goals"] - a["xg"]) / a[den], (b["goals"] - b["xg"]) / b[den]))
            else:
                rows.append((kit, a[num] / a[den], b[num] / b[den]))
        by = defaultdict(list)
        for kit, x, y in rows:
            by[kit].append((x, y))
        means = {k: (statistics.fmean(x for x, _ in v), statistics.fmean(y for _, y in v)) for k, v in by.items()}
        out[key] = {"r_all": _r([r[1] for r in rows], [r[2] for r in rows]),
                    "r_slot": _r([x - means[k][0] for k, x, _ in rows], [y - means[k][1] for k, _, y in rows]), "n": len(rows)}
    return out


def _r(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or statistics.pstdev(xs) == 0 or statistics.pstdev(ys) == 0:
        return None
    return round(statistics.correlation(xs, ys), 3)


def top_scorers(league: Record, matches: list[tuple[int, Record, list[Record]]] | None = None, n: int = 10) -> list[Record]:
    """The season's scoring chart: goals (penalties included), non-penalty goals, non-penalty xG, shots."""
    matches = matches if matches is not None else season_matches(league)
    names = {p["global_id"]: p["name"] for c in league["clubs"] for p in c["squad"]}
    tally: dict[str, Counter] = defaultdict(Counter)
    for _rnd, header, stream in matches:
        gid = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
        for e in stream:
            if e.get("type") != "event" or e["event_type"] not in ("goal", "shot"):
                continue
            g, pen = gid[e["player_id"]], "penalty" in e.get("qualifiers", [])
            if e["event_type"] == "goal":
                tally[g]["goals"] += 1
                tally[g]["np_goals"] += 0 if pen else 1
            elif not pen:
                tally[g]["shots"] += 1
                tally[g]["np_xg"] += e.get("metrics", {}).get("xg", 0.0)
    rows = [{"global_id": g, "name": names.get(g, g), "goals": t["goals"], "np_goals": t["np_goals"],
             "np_xg": round(t["np_xg"], 2), "shots": t["shots"]} for g, t in tally.items()]
    rows.sort(key=lambda r: (-r["goals"], -r["np_goals"], r["global_id"]))
    return rows[:n]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.season.audit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("league", nargs="?", default="data/season/league.json", type=Path)
    ap.add_argument("--seasons", type=int, default=1, help="seasons to pool (seeds shifted by 1000 each)")
    args = ap.parse_args(argv)
    league = load_league(args.league)
    matches = season_matches(league, args.seasons)
    print(f"Split-half reliability (rounds 1-5 vs 6-10), {args.seasons} season(s): r across starters, r within kit slot")
    for key, v in split_half(league, matches).items():
        print(f"  {key:18s} all {v['r_all']!s:>7}  within slot {v['r_slot']!s:>7}  (n={v['n']})")
    print("Top scorers:")
    for r in top_scorers(league, matches):
        print(f"  {r['name']:22s} {r['global_id']:10s} goals {r['goals']:2d} (non-penalty {r['np_goals']}, npxG {r['np_xg']}, "
              f"{r['shots']} shots)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
