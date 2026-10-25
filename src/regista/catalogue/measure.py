"""Measurement seasons: each competition's full double round robin, regenerated in memory (nothing is written), so a level
can be measured on whole seasons rather than on its 3-8 uploaded matches.

The uploaded sample is what scouts see; it is far too small to say how reliable a level's numbers are or whether its
volumes are football-like. A measurement season is the competition as it would be if every fixture had been filmed: the
same clubs, squads and hidden ratings, every fixture of the double round robin (``define.round_robin``), each with a
measurement seed. The catalogue's per-level reliability (``regista.catalogue.reliability``) and the realism checks per
level (``regista.catalogue.realism``) both read these seasons.

Seeds (design.md §4.1): fixture n of a competition's full round robin (1-based, in round order) has base seed
``comp_seed * 100 + n``, and measurement season ``repeat`` (0-based) adds ``MEASURE_OFFSET * (repeat + 1)``. England's
fixtures are already its full round robin: each keeps its own seed plus the same offset. The offset puts every
measurement seed above 50,000,000, far from every committed seed (league 20,270-20,362; catalogue 20,270,101-20,271,303),
the samples and the vision sets, so a measurement match is never a committed one.

Each season is computed with the engine's own rules for its competition (``regista.catalogue.metrics``): England's
league rules (its own fitted xT, a third of a club's minutes); every other competition with England's committed xT grid,
a 45-minute floor on the qualifying minutes and percentile pools of at least 5. A season is cut in two halves of rounds
(first half of the rounds against the second), as ``regista.season.reliability`` cuts the league.

``measure`` runs one spawn-context process pool, so a script that calls it must guard its entry point with
``if __name__ == "__main__":``. A whole run (14 competitions, 6 seasons each, about 1,500 matches) takes a few minutes on
ten cores.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from regista.catalogue.taxonomy import BY_ID, ENGLAND_ID

Record = dict[str, Any]

MEASURE_OFFSET = 50_000_000
DEFAULT_REPEATS = 6
CATALOGUE_FLOOR = 45.0       # the catalogue's qualifying-minutes floor for every competition but England
CATALOGUE_MIN_POOL = 5       # the catalogue's smallest percentile pool
PEAK_MIN_PLAYED_S = 600.0    # a match top speed counts from 10 minutes on the pitch (regista.season.metrics)
AGG_KEYS = ("passes", "passes_completed", "ball_losses", "goals", "shots", "take_ons", "carries", "tackles_won", "fouls",
            "distance", "hi_distance", "sprint_distance")


def competition_id(comp: Record) -> str:
    return (comp.get("competition") or {}).get("competition_id", ENGLAND_ID)


def level_of(comp: Record) -> str:
    c = BY_ID[competition_id(comp)]
    return c.level_key


def full_fixtures(comp: Record) -> list[Record]:
    """Every fixture of the competition's double round robin with its base seed (England: its 30 fixtures as they are)."""
    from regista.catalogue.define import round_dates, round_robin

    cid = competition_id(comp)
    if cid == ENGLAND_ID:
        return [dict(fx) for fx in comp["fixtures"]]
    clubs = comp["clubs"]
    rounds = round_robin(len(clubs))
    dates = round_dates(BY_ID[cid], len(rounds))
    code = comp["competition"]["code"]
    out, n = [], 0
    for r, pairs in enumerate(rounds, start=1):
        for h, a in pairs:
            n += 1
            home, away = clubs[h], clubs[a]
            out.append({"match_id": f"mx_{code}_{r:02d}_{home['short_name'].lower()}_{away['short_name'].lower()}",
                        "round": r, "date": dates[r - 1].isoformat(), "home": home["club_id"], "away": away["club_id"],
                        "seed": comp["seed"] * 100 + n})
    return out


def measurement_league(comp: Record, repeat: int) -> Record:
    """The competition with its full round robin as fixtures, every seed moved to measurement season ``repeat``."""
    fixtures = [{**fx, "seed": fx["seed"] + MEASURE_OFFSET * (repeat + 1), "match_id": f"{fx['match_id']}_m{repeat + 1}"}
                for fx in full_fixtures(comp)]
    return {**comp, "fixtures": fixtures}


def halves(fixtures: list[Record]) -> tuple[set[int], set[int]]:
    """The rounds of each half: the first half of the rounds and the rest (a double round robin: each pair once in each)."""
    rounds = sorted({fx["round"] for fx in fixtures})
    k = len(rounds) // 2
    return set(rounds[:k]), set(rounds[k:])


def season_metrics(league: Record, streams: list, xt: Any = None, england: bool = False):
    """``SeasonMetrics`` for these streams under the engine's rule for this competition."""
    from regista.season.metrics import SeasonMetrics

    if england:
        return SeasonMetrics.from_streams(league, streams)
    return SeasonMetrics.from_streams(league, streams, xt=xt, min_minutes_floor=CATALOGUE_FLOOR, min_pool=CATALOGUE_MIN_POOL)


def measure_season(args: tuple[Record, int, Any]) -> Record:
    """One measurement season of one competition: its split-half rows for every metric (``regista.catalogue.reliability``)
    and level aggregates (``regista.catalogue.realism``). Runs in a worker process; returns only small numbers."""
    from regista.season.metrics import CATALOGUE
    from regista.synth.generator import generate
    from regista.season.league import generate_kwargs

    comp, repeat, xt = args
    cid = competition_id(comp)
    england = cid == ENGLAND_ID
    league = measurement_league(comp, repeat)
    played = [(fx, generate(**generate_kwargs(league, fx)).stream) for fx in league["fixtures"]]
    first, second = halves(league["fixtures"])
    parts = []
    for rounds in (first, second):
        streams = [(fx, stream, None) for fx, stream in played if fx["round"] in rounds]
        parts.append(season_metrics(league, streams, xt, england))
    a, b = parts
    rows: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for gid, pa in a.players.items():
        pb = b.players.get(gid)
        if pb is None:
            continue
        role = pa.info.get("role") or pa.info["position"]
        for key, m in CATALOGUE.items():
            if m.kind == "total" or pa.info["position"] not in m.positions:
                continue
            if a.qualified(pa, m) and b.qualified(pb, m):
                rows[key].append((f"{cid}:{repeat}:{role}", pa.values[key], pb.values[key]))
    half_minutes = sorted(ps.minutes for sm in parts for ps in sm.players.values() if ps.minutes >= sm.min_minutes)
    agg: dict[str, float] = defaultdict(float)
    peaks: list[float] = []
    for sm in parts:
        agg["team_minutes"] += sum(t["totals"].get("minutes", 0.0) for t in sm.teams.values())
        for ps in sm.players.values():
            if ps.info["position"] == "GK":
                continue
            agg["outfield_minutes"] += ps.minutes
            for k in AGG_KEYS:
                agg[k] += ps.totals.get(k, 0.0)
            peaks += [pk for _mi, pk, s in ps.peaks if s >= PEAK_MIN_PLAYED_S]
        for ps in sm.players.values():
            agg["all_goals"] += ps.totals.get("goals", 0.0)
            agg["all_shots"] += ps.totals.get("shots", 0.0) + ps.totals.get("penalties_taken", 0.0)
    agg["peak_sum"] = sum(peaks)
    agg["peak_n"] = float(len(peaks))
    return {"competition_id": cid, "level": level_of(comp), "repeat": repeat, "matches": len(played),
            "rounds": [sorted(first), sorted(second)], "rows": dict(rows), "half_minutes": half_minutes, "agg": dict(agg)}


def measure(comps: list[Record], repeats: int = DEFAULT_REPEATS, xt: Any = None, workers: int | None = None) -> list[Record]:
    """Every (competition, measurement season) in ``comps`` x ``range(repeats)``, in one pool of spawned processes
    (``workers`` 1: here, one by one). ``xt``: the grid non-England competitions value moves with (England's committed
    season's; the engine's rule)."""
    jobs = [(comp, k, xt) for comp in comps for k in range(repeats)]
    workers = min(len(jobs), workers or os.cpu_count() or 1)
    results = None
    if workers > 1:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor

        try:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                # the biggest seasons first, so the pool's last jobs are short
                order = sorted(range(len(jobs)), key=lambda i: -len(full_fixtures(jobs[i][0])))
                done = dict(zip(order, pool.map(measure_season, [jobs[i] for i in order])))
                results = [done[i] for i in range(len(jobs))]
        except Exception:  # noqa: BLE001 - no worker processes here (an interactive or piped __main__): one by one
            results = None
    if results is None:
        results = [measure_season(j) for j in jobs]
    return results


def level_aggregates(results: list[Record]) -> dict[str, Record]:
    """Per level, pooled over its competitions and measurement seasons: rates the realism checks read. Per 90 rates are
    per outfield player (outfield totals over outfield minutes); team rates per team per 90 (all players' totals over the
    teams' minutes); the peak is the mean of outfielders' match top speeds (matches with 10+ minutes)."""
    acc: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    comps: dict[str, set[str]] = defaultdict(set)
    seasons: dict[str, int] = defaultdict(int)
    for r in results:
        for k, v in r["agg"].items():
            acc[r["level"]][k] += v
        comps[r["level"]].add(r["competition_id"])
        seasons[r["level"]] += 1
    out: dict[str, Record] = {}
    for level, a in acc.items():
        om, tm = a["outfield_minutes"], a["team_minutes"]
        per90 = {k: round(a[k] * 90.0 / om, 3) if om else None
                 for k in ("ball_losses", "take_ons", "carries", "tackles_won", "fouls", "distance", "hi_distance",
                           "sprint_distance", "passes")}
        out[level] = {"competitions": sorted(comps[level]), "seasons": seasons[level],
                      "pass_pct": round(a["passes_completed"] / a["passes"] * 100.0, 2) if a["passes"] else None,
                      "outfield_per90": per90,
                      "team_goals_per90": round(a["all_goals"] * 90.0 / tm, 3) if tm else None,
                      "team_shots_per90": round(a["all_shots"] * 90.0 / tm, 3) if tm else None,
                      "peak_speed_mean": round(a["peak_sum"] / a["peak_n"], 2) if a["peak_n"] else None,
                      "outfield_minutes": round(om, 1)}
    return out
