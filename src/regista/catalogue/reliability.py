"""Split-half reliability per level: which metrics a season of a level's football can separate within a role, and which
are mostly luck.

    python -m regista.catalogue reliability [--repeats 6] [--out data/catalogue/reliability.json]

**Method.** The Regista League's method (``regista.season.reliability``), applied per level on measurement seasons
(``regista.catalogue.measure``: every competition's full double round robin, regenerated in memory with measurement
seeds). Each season is cut in two halves of rounds, each half computed with the catalogue engine's rule for its
competition; for a metric, every player who qualifies in both halves gives one row, centred on his role's mean in that
competition-season, and rows are pooled over every competition of the level and every measurement season. ``r`` is the
split-half correlation, ``season_r`` its Spearman-Brown estimate for a whole season (2r / (1 + r)); ``noisy``: ``r``
below 0.3, so a ranking within a role over half a season of that level is mostly luck.

**What it can and cannot say.** It measures a full season of the level, cut in halves. Every sparse competition's
uploaded sample is smaller than half its full season (3-8 matches against 12-30), so a metric marked noisy here is
noisier still on the uploads, and one that is not marked may still be noisy there. A per-competition reliability on the
uploads themselves is not computed: 3-8 matches cannot be split meaningfully. England's own table
(``data/season/reliability.json``) stays what the existing endpoints read; this file adds the levels.

The file is committed beside the catalogue index and stamped with the generator's league version and a fingerprint of
everything that shapes the measurement (each competition's clubs, squads, ratings, seed, generator settings and level;
England's league fingerprint, which covers the generator's source); a test checks the stamp and a slow test recomputes
one level.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from regista.season.reliability import MIN_ROWS, NOISE_R, _centred_r

Record = dict[str, Any]

FILE_NAME = "reliability.json"
METHOD_VERSION = 1
NOTE = ("measured per level on full regenerated seasons of its competitions (split in halves of rounds); the uploaded "
        "sample of every sparse competition is smaller than half a season, so its numbers are noisier still")


def catalogue_fingerprint(league: Record, comps: list[Record], repeats: int) -> str:
    """Changes when anything that shapes the measurement changes: England's league fingerprint (its file and the
    generator's source), every competition's clubs (squads, hidden ratings), seed, generator settings, labels and level
    scale, the measurement offset, the number of seasons and this method's version."""
    from regista.catalogue.measure import MEASURE_OFFSET
    from regista.season.reliability import league_fingerprint

    data = {"england": league_fingerprint(league), "offset": MEASURE_OFFSET, "repeats": repeats, "method": METHOD_VERSION,
            "competitions": {c["competition"]["competition_id"]: {k: c.get(k) for k in
                                                                   ("clubs", "seed", "generator", "competition", "level")}
                             for c in comps}}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def table(results: list[Record]) -> dict[str, Record]:
    """{level: {competitions, seasons, median_half_minutes, metrics: {key: {r, season_r, n, noisy}}}} from
    ``measure.measure``'s results."""
    import statistics

    from regista.season.metrics import CATALOGUE

    by_level: dict[str, list[Record]] = {}
    for r in results:
        by_level.setdefault(r["level"], []).append(r)
    out: dict[str, Record] = {}
    for level, rs in sorted(by_level.items()):
        rows: dict[str, list[tuple[str, float, float]]] = {}
        for r in rs:
            for key, rr in r["rows"].items():
                rows.setdefault(key, []).extend(tuple(x) for x in rr)
        metrics: dict[str, Record] = {}
        for key in CATALOGUE:
            corr, n = _centred_r(rows.get(key, []))
            if corr is None:
                metrics[key] = {"r": None, "season_r": None, "n": n, "noisy": None}
            else:
                metrics[key] = {"r": round(corr, 3), "season_r": round(2 * corr / (1 + corr), 3) if corr > 0 else 0.0,
                                "n": n, "noisy": round(corr, 3) < NOISE_R}
        half = [m for r in rs for m in r["half_minutes"]]
        out[level] = {"competitions": sorted({r["competition_id"] for r in rs}),
                      "seasons": len({r["repeat"] for r in rs}),
                      "matches": sum(r["matches"] for r in rs),
                      "median_half_minutes": round(statistics.median(half), 1) if half else None,
                      "metrics": metrics}
    return out


def compute(league: Record, comps: list[Record], repeats: int, xt: Any, workers: int | None = None,
            results: list[Record] | None = None) -> Record:
    """The whole file: every level of ``comps`` (England included when ``league`` is among them), measured now unless
    ``results`` (``measure.measure``'s) are given."""
    from regista.catalogue.measure import measure
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    if results is None:
        results = measure([league, *comps], repeats, xt, workers)
    return {"generator_version": LEAGUE_GENERATOR_VERSION, "catalogue_fingerprint": catalogue_fingerprint(league, comps, repeats),
            "seasons": repeats, "noise_r": NOISE_R, "min_rows": MIN_ROWS, "synthetic": True, "note": NOTE,
            "method": "split-half reliability within role, per level: each competition's full double round robin "
                      f"regenerated {repeats} times with measurement seeds (regista.catalogue.measure), each season cut "
                      "into its first and second half of rounds, each half computed with the catalogue engine's rule "
                      "for its competition; values centred on the role's mean in that competition-season; rows pooled "
                      "over the level's competitions and seasons. r is the split-half correlation, season_r its "
                      f"Spearman-Brown estimate for a whole season, 2r/(1+r). noisy: r below {NOISE_R}",
            "levels": table(results)}


def default_path() -> Path:
    from regista.catalogue.store import index_path

    return index_path().with_name(FILE_NAME)


def load(league: Record, comps: list[Record], path: Path | str | None = None) -> Record:
    """The committed per-level table, or an empty one (``levels`` {} and ``stale`` saying why) when it is missing or was
    measured for another catalogue, league or generator. Then nothing outside England's own table is marked noisy."""
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    path = Path(path) if path else default_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"levels": {}, "stale": f"no {FILE_NAME} beside the catalogue index"}
    if data.get("generator_version") != LEAGUE_GENERATOR_VERSION:
        return {"levels": {}, "stale": f"{FILE_NAME} was measured for generator {data.get('generator_version')}"}
    if data.get("catalogue_fingerprint") != catalogue_fingerprint(league, comps, data.get("seasons", 0)):
        return {"levels": {}, "stale": f"{FILE_NAME} was measured for another catalogue"}
    return data


def level_table(data: Record, level: str) -> Record:
    """One level's table in the shape ``SeasonMetrics.reliability`` holds (``metrics``), labelled."""
    lv = (data.get("levels") or {}).get(level)
    if not lv:
        return {"metrics": {}, "stale": data.get("stale") or f"no reliability measured for {level}", "level": level}
    return {"metrics": lv["metrics"], "level": level, "seasons": lv["seasons"], "competitions": lv["competitions"],
            "median_half_minutes": lv["median_half_minutes"], "note": NOTE}
