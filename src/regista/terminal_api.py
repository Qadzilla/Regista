"""The Scout terminal's API: the industry's scouting metrics on the Regista League (``regista.season.metrics``). All reads,
all public; every response says the data is synthetic and every metric carries its definition and source.

GET /api/metrics                        the catalogue: every metric's definition, rule, sources, unit, kind, direction and
                                        positions; groups; the season's thresholds (qualifying minutes, ratio minimums);
                                        the fitted xT grid
GET /api/terminal/screen                players with chosen metric columns; filters position, role, club, min_minutes, age,
                                        foot, q; sort by any metric
GET /api/terminal/rank                  one metric's leaderboard (rank, value, percentile, how many events back it)
GET /api/terminal/scatter               two metrics per player, plus the pool's medians
GET /api/players/{global_id}/metrics    every metric for one player with percentiles and evidence (the events behind each
                                        number, with the clip each sits in; 10 per metric by default); evidence=KEY
                                        returns one metric's list (up to 500); evidence_limit=N caps either, 0 gives none
GET /api/players/{global_id}/form       per-match values of chosen metrics, and consistency
GET /api/players/{global_id}/similar    the most similar players in the same position (cosine on standardised per-90s)
GET /api/teams                          every club's style metrics
GET /api/teams/{club_id}/style          one club's style: possession, field tilt, PPDA, directness, set-piece xG, with ranks

The season is built once per process (``load_metrics``) from the league's event streams, regenerated on demand like the
rest of the Scout view.
"""

from __future__ import annotations

import re
import statistics
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from regista.season.metrics import (CATALOGUE, DEFAULT_COLUMNS, SYNTHETIC_NOTE, TEAM_CATALOGUE, SeasonMetrics, catalogue,
                                    load_metrics)

router = APIRouter()
GID_PATTERN = r"^pl_[a-z0-9_]{1,40}$"
CLUB_PATTERN = r"^cl_[a-z0-9_]{1,40}$"
KEY_PATTERN = r"^[a-z0-9_]{1,40}$"
KEYS_PATTERN = r"^[a-z0-9_]{1,40}(,[a-z0-9_]{1,40}){0,15}$"
MAX_EVIDENCE = 500   # evidence=KEY: at most this many items
TABLE_EVIDENCE = 10  # the whole table: this many items per metric unless evidence_limit says otherwise
POSITION = Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)$")]
ROLE = Annotated[str | None, Query(pattern="^(GK|FB|CB|DM|CM|AM|W|ST)$")]
CLUB = Annotated[str | None, Query(max_length=40, pattern=r"^[A-Za-z0-9_ ]{1,40}$")]
FOOT = Annotated[str | None, Query(pattern="^(right|left|both)$")]
NAME_Q = Annotated[str | None, Query(max_length=80)]
MIN_MINUTES = Annotated[float | None, Query(ge=0.0, le=10000.0)]
AGE = Annotated[int | None, Query(ge=14, le=50)]


def metrics() -> SeasonMetrics:
    from regista.api import SEASON_LEAGUE, SEASON_ROOT

    if not SEASON_LEAGUE.exists():
        raise HTTPException(404, "no league on this server (data/season/league.json)")
    return load_metrics(SEASON_LEAGUE, SEASON_ROOT)


def warm_metrics() -> None:
    """Build the season's metrics after the profiles (``season_api.warm_season``), so the first terminal query is quick."""
    try:
        metrics()
    except Exception:  # noqa: BLE001 - a later request builds it and reports the error
        pass


def _keys(raw: str | None, *, default: tuple[str, ...]) -> list[str]:
    if not raw:
        return list(default)
    keys = list(dict.fromkeys(raw.split(",")))
    unknown = [k for k in keys if k not in CATALOGUE]
    if unknown:
        raise HTTPException(422, f"unknown metric(s): {', '.join(unknown)} (GET /api/metrics lists them)")
    return keys


def _key(k: str) -> str:
    if k not in CATALOGUE:
        raise HTTPException(422, f"unknown metric {k!r} (GET /api/metrics lists them)")
    return k


def _player(sm: SeasonMetrics, gid: str):
    if not re.match(GID_PATTERN, gid):
        raise HTTPException(400, "bad player id")
    ps = sm.player(gid)
    if ps is None:
        raise HTTPException(404, f"no player {gid!r} has played in the league")
    return ps


def _season_meta(sm: SeasonMetrics) -> dict[str, Any]:
    return {"min_minutes": sm.min_minutes, "matches_per_club": sm.matches_per_club, "thresholds": sm.thresholds,
            "peer_groups": "the league's positions GK, DF, MF, FW (FBref uses six sets; these squads are too small)",
            "percentile_rule": "FBref: the mean of the share of peers strictly below and the share at or below; inverted "
                               "where lower is better; only players with the qualifying minutes (and, for a ratio, the "
                               "minimum attempts) are in the pool or get a percentile",
            "scope": "Regista League fixtures (synthetic); claimed and uploaded matches count on profiles only",
            "sample": sm.sample(),
            "reliability": {"noise_r": sm.reliability.get("noise_r"), "seasons": sm.reliability.get("seasons"),
                            "method": sm.reliability.get("method"), "stale": sm.reliability.get("stale"),
                            "noisy": sorted(k for k in CATALOGUE if sm.noisy(k))},
            "synthetic": True, "note": SYNTHETIC_NOTE}


def _filters(sm: SeasonMetrics, position, role, club, min_minutes, age_min, age_max, foot, q):
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(422, "age_min is above age_max")
    return sm.rows(position=position, role=role, club=club, min_minutes=min_minutes, age_min=age_min, age_max=age_max,
                   foot=foot, q=q)


@router.get("/api/metrics")
async def get_metrics() -> dict[str, Any]:
    sm = await run_in_threadpool(metrics)
    return {**catalogue(), "metrics": [sm.describe(k) for k in CATALOGUE], "season": _season_meta(sm),
            "xt": sm.xt.public() if sm.xt else None}


@router.get("/api/terminal/screen")
async def screen(metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                 position: POSITION = None, role: ROLE = None, club: CLUB = None, min_minutes: MIN_MINUTES = None,
                 age_min: AGE = None, age_max: AGE = None, foot: FOOT = None, q: NAME_Q = None,
                 sort: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None, order: Literal["asc", "desc"] | None = None,
                 limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Players with the chosen metric columns (default: the position's core set). Each cell: value (per 90, ratio, ...),
    the count behind it, the percentile among position peers, and whether the player qualifies. Sorted by ``sort`` (default
    the first column), best first unless ``order`` says otherwise; ``min_minutes`` defaults to the qualifying minimum."""
    keys = _keys(metrics_, default=DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None]))
    sort_key = _key(sort) if sort else keys[0]

    def run() -> dict[str, Any]:
        sm = metrics()
        rows = sm.sort(_filters(sm, position, role, club, min_minutes, age_min, age_max, foot, q), sort_key, order)
        return {"columns": [sm.describe(k) for k in keys], "sort": sort_key, "total": len(rows),
                "players": [{**sm.card(ps), "values": {k: sm.cell(ps, k) for k in keys}} for ps in rows[:limit]],
                "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/terminal/rank")
async def rank(metric: Annotated[str, Query(pattern=KEY_PATTERN)], position: POSITION = None, role: ROLE = None,
               club: CLUB = None, min_minutes: MIN_MINUTES = None, age_min: AGE = None, age_max: AGE = None,
               foot: FOOT = None, order: Literal["asc", "desc"] | None = None,
               limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    """One metric's leaderboard. Ratios rank only players with the minimum attempts (the rest are listed after, unranked)."""
    key = _key(metric)

    def run() -> dict[str, Any]:
        sm = metrics()
        m = CATALOGUE[key]
        rows = sm.sort(_filters(sm, position, role, club, min_minutes, age_min, age_max, foot, None), key, order)
        ranked = [ps for ps in rows if sm.qualified(ps, m) or (m.kind == "total" and ps.values.get(key) is not None)]
        rest = [ps for ps in rows if ps not in ranked]
        out, prev, place = [], None, 0
        for i, ps in enumerate(ranked, start=1):
            v = round(ps.values[key], m.digits)
            if v != prev:
                place, prev = i, v
            out.append({"rank": place, **sm.card(ps), **sm.cell(ps, key),
                        "evidence_count": sum(len(ps.evidence.get(k, [])) for k in m.evidence_keys())})
        return {"metric": sm.describe(key), "players": out[:limit], "ranked": len(ranked),
                "unranked": [{**sm.card(ps), **sm.cell(ps, key)} for ps in rest[:limit]],
                "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/terminal/scatter")
async def scatter(x: Annotated[str, Query(pattern=KEY_PATTERN)], y: Annotated[str, Query(pattern=KEY_PATTERN)],
                  position: POSITION = None, role: ROLE = None, club: CLUB = None, min_minutes: MIN_MINUTES = None,
                  age_min: AGE = None, age_max: AGE = None, foot: FOOT = None) -> dict[str, Any]:
    """Two metrics for every player who passes the filters and has both values; the pool's medians draw the quadrants."""
    kx, ky = _key(x), _key(y)

    def run() -> dict[str, Any]:
        sm = metrics()
        rows = _filters(sm, position, role, club, min_minutes, age_min, age_max, foot, None)
        pts = []
        for ps in rows:
            vx, vy = ps.values.get(kx), ps.values.get(ky)
            if vx is None or vy is None:
                continue
            pts.append({**sm.card(ps), "x": round(vx, CATALOGUE[kx].digits), "y": round(vy, CATALOGUE[ky].digits),
                        "x_percentile": ps.percentiles.get(kx), "y_percentile": ps.percentiles.get(ky)})
        def med(vals: list[float]) -> float | None:
            return round(statistics.median(vals), 4) if vals else None

        return {"x": sm.describe(kx), "y": sm.describe(ky), "points": pts,
                "median": {"x": med([p["x"] for p in pts]), "y": med([p["y"] for p in pts])}, "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/metrics")
async def player_metrics(gid: str, evidence: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                         evidence_limit: int | None = Query(None, ge=0, le=MAX_EVIDENCE),
                         group: Annotated[str | None, Query(pattern=r"^[a-z]{1,20}$")] = None) -> dict[str, Any]:
    """Every metric (or one ``group``) for one player: value, count, percentile, peers, and evidence (the first
    ``evidence_limit`` items behind each number, default 10, in match order, with the total). ``evidence=KEY`` returns that
    metric's evidence instead of the whole table: all of it up to 500 by default, or the first ``evidence_limit``.
    ``evidence_limit=0`` returns no items (the totals only), for event and physical metrics alike."""
    if evidence:
        _key(evidence)

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        if evidence:
            return {"global_id": gid, "name": ps.info["name"], "metric": sm.describe(evidence), **sm.cell(ps, evidence),
                    "evidence": sm.evidence(ps, evidence, limit=MAX_EVIDENCE if evidence_limit is None else evidence_limit),
                    "synthetic": True}
        keys = [k for k, m in CATALOGUE.items() if not group or m.group == group]
        if group and not keys:
            raise HTTPException(422, f"unknown group {group!r}")
        limit = TABLE_EVIDENCE if evidence_limit is None else evidence_limit
        return {**sm.card(ps), "metrics": {k: {**sm.cell(ps, k), "evidence": sm.evidence(ps, k, limit=limit)}
                                           for k in keys},
                "catalogue": {k: sm.describe(k) for k in keys}, "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/form")
async def player_form(gid: str, metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None) -> dict[str, Any]:
    """Per-match values (per 90 of that match, the match ratio, or the match's top speed) and consistency: the mean, standard
    deviation and coefficient of variation over matches with 15+ minutes (Regista's measure; no provider publishes one),
    and the last three matches against the season value."""

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        keys = _keys(metrics_, default=DEFAULT_COLUMNS.get(ps.info["position"], DEFAULT_COLUMNS[None]))
        return {**sm.card(ps), **sm.form(ps, keys), "catalogue": {k: sm.describe(k) for k in keys},
                "consistency_rule": "Regista: coefficient of variation (sd / mean) of per-match values over matches with "
                                    "at least 15 minutes; lower is steadier. Thirty-minute matches make it noisy.",
                "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/similar")
async def player_similar(gid: str, n: int = Query(5, ge=1, le=20)) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        return {**sm.card(ps), **sm.similar(gid, n),
                "rule": "Cosine similarity of z-scored per-90 values (FBref's summary template for outfielders, a keeper "
                        "template for keepers) among qualified players in the same position; FBref ranks by smallest "
                        "percentile differences, Regista by cosine on z-scores",
                "sources": ["FB-SR"], "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/teams")
async def teams() -> dict[str, Any]:
    def run() -> dict[str, Any]:
        sm = metrics()
        return {"metrics": [m.public() for m in TEAM_CATALOGUE.values()],
                "teams": [sm.team_style(cid) | {"per_match": None, "evidence": None} for cid in sm.teams],
                "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/teams/{club_id}/style")
async def team_style(club_id: str) -> dict[str, Any]:
    if not re.match(CLUB_PATTERN, club_id):
        raise HTTPException(400, "bad club id")

    def run() -> dict[str, Any]:
        sm = metrics()
        if club_id not in sm.teams:
            raise HTTPException(404, f"no club {club_id!r} in the league")
        return {**sm.team_style(club_id), "metrics": [m.public() for m in TEAM_CATALOGUE.values()], "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)
