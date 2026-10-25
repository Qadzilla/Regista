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
                                        returns one metric's list (up to 500 a page; evidence_offset pages through the
                                        rest, so every moment can be read); evidence_limit=N caps either, 0 gives none
GET /api/players/{global_id}/shots      every shot the player took (penalties too): where, xG, outcome, body part, minute,
                                        clip (the shot map)
GET /api/players/{global_id}/heatmap    the player's on-ball actions per pitch cell in league fixtures only (claimed and
                                        uploaded matches stay on the profile's own grid), attacking left to right
GET /api/players/{global_id}/form       per-match values of chosen metrics, and consistency
GET /api/players/{global_id}/similar    the most similar players in the same position (cosine on standardised per-90s)
GET /api/teams                          every club's style metrics
GET /api/teams/{club_id}/style          one club's style: possession, field tilt, PPDA, directness, set-piece xG, with ranks
GET /api/teams/{club_id}/shots          every shot by the club (side=for) or against it (side=against), with who took it
                                        and its clip (the team's shot reels)

The season is built once per process (``load_metrics``) from the league's event streams, regenerated on demand like the
rest of the Scout view.
"""

from __future__ import annotations

import re
import statistics
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from regista.catalogue_api import COMPETITION, RANK_BY, ScopeDep, WhereDep, catalogue_mode
from regista.season.metrics import (CATALOGUE, DEFAULT_COLUMNS, PITCH_L, PITCH_W, SYNTHETIC_NOTE, TEAM_CATALOGUE,
                                    SeasonMetrics, catalogue, load_metrics)
from regista.season.profiles import GRID_X, GRID_Y, TOUCH_MAP_EVENTS

router = APIRouter()
GID_PATTERN = r"^pl_[a-z0-9_]{1,40}$"
CLUB_PATTERN = r"^cl_[a-z0-9_]{1,40}$"
KEY_PATTERN = r"^[a-z0-9_]{1,40}$"
KEYS_PATTERN = r"^[a-z0-9_]{1,40}(,[a-z0-9_]{1,40}){0,15}$"
MAX_EVIDENCE = 500   # evidence=KEY: at most this many items a page (evidence_offset reads the next page)
MAX_OFFSET = 100000
TABLE_EVIDENCE = 10  # the whole table: this many items per metric unless evidence_limit says otherwise
POSITION = Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)$")]
ROLE = Annotated[str | None, Query(pattern="^(GK|FB|CB|DM|CM|AM|W|ST)$")]
CLUB = Annotated[str | None, Query(max_length=40, pattern=r"^[A-Za-z0-9_ ]{1,40}$")]
FOOT = Annotated[str | None, Query(pattern="^(right|left|both)$")]
NAME_Q = Annotated[str | None, Query(max_length=80)]
MIN_MINUTES = Annotated[float | None, Query(ge=0.0, le=10000.0)]
AGE = Annotated[int | None, Query(ge=14, le=50)]
FORM_RULE = ("Regista: coefficient of variation (sd / mean) of per-match values over matches with at least 15 minutes; "
             "lower is steadier. Thirty-minute matches make it noisy.")
SIMILAR_RULE = ("Cosine similarity of z-scored per-90 values (FBref's summary template for outfielders, a keeper template "
                "for keepers) among qualified players in the same position; FBref ranks by smallest percentile "
                "differences, Regista by cosine on z-scores")


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
        from regista.catalogue_api import player_hint

        raise HTTPException(404, f"no player {gid!r} has played in the league{player_hint(gid)}")
    return ps


def _row_mode(competition: str | None, scope: str | None) -> bool:
    """A player endpoint answers from the catalogue when ``competition`` or ``scope`` is given."""
    return bool(competition) or scope is not None


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


PITCH = {"length": PITCH_L, "width": PITCH_W,
         "frame": "attacking left to right: x runs along the length toward the opponent's goal at x = length",
         "heatmap_grid": [GRID_X, GRID_Y], "heatmap_events": list(TOUCH_MAP_EVENTS),
         "heatmap_rule": "on-ball actions per cell (the touch-map events) in Regista League fixtures only, like every "
                         "terminal number; rows y (0 to width), columns x (0 to length), attacking left to right "
                         "(GET /api/players/{id}/heatmap; the profile page's grid also counts claimed and uploaded matches)"}


@router.get("/api/metrics")
async def get_metrics(competition: COMPETITION = None, *, scope: ScopeDep) -> dict[str, Any]:
    """The metrics catalogue and the Regista League's season. ``competition=`` (and ``scope``) describe each metric in that
    catalogue competition (its ratio minimums, the reliability table its numbers read, its realism check) with the
    catalogue's ``season`` block; outside England the xT grid is England's (a fixed reference grid)."""
    if _row_mode(competition, scope):
        from regista.catalogue.taxonomy import ENGLAND_ID
        from regista.catalogue_api import _known_competition, _meta, catalogue_metrics

        cid = competition or ENGLAND_ID
        _known_competition(cid, status=422)
        sc = scope or "level"

        def run() -> dict[str, Any]:
            cm = catalogue_metrics()
            sm = cm.metrics[cid]
            return {**catalogue(), "metrics": [cm.describe(k, cid, sc) for k in CATALOGUE], "season": _meta(cm, [cid], sc),
                    "xt": sm.xt.public() if sm.xt else None, "pitch": PITCH}

        return await run_in_threadpool(run)
    sm = await run_in_threadpool(metrics)
    return {**catalogue(), "metrics": [sm.describe(k) for k in CATALOGUE], "season": _season_meta(sm),
            "xt": sm.xt.public() if sm.xt else None, "pitch": PITCH}


@router.get("/api/terminal/screen")
async def screen(metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                 position: POSITION = None, role: ROLE = None, club: CLUB = None, min_minutes: MIN_MINUTES = None,
                 age_min: AGE = None, age_max: AGE = None, foot: FOOT = None, q: NAME_Q = None,
                 sort: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None, order: Literal["asc", "desc"] | None = None,
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=MAX_OFFSET),
                 rank_by: RANK_BY = None, *, w: WhereDep, scope: ScopeDep) -> dict[str, Any]:
    """Players with the chosen metric columns (default: the position's core set). Each cell: value (per 90, ratio, ...),
    the count behind it, the percentile among position peers, whether the player qualifies, and ``evidence_total`` (how
    many moments, or for a physical number matches, are behind it: the evidence's ``moments``, each event once, where a
    ratio's ``total`` counts a pass and its completion twice). Sorted by ``sort`` (default
    the first column), best first unless ``order`` says otherwise; ``min_minutes`` defaults to the qualifying minimum.
    ``offset`` skips that many rows, so a reader can page past ``limit`` (``total`` counts every row).

    Catalogue parameters (``competition``, ``country``, ``tier`` or ``level``, ``age_group``, ``gender``, ``scope`` or
    ``pool``, ``rank_by``) answer from the catalogue in the same shape plus three keys: England semi-pro men unless a
    filter picks others, each cell with its ``pool`` and ``sample``, percentiles in ``scope`` (level by default), the
    catalogue's ``season`` block, and how the rows were ranked (``rank_by``, ``rank_rule``, ``boards``). There,
    percentiles are compared only within one position and raw numbers only within one level (``RANK_RULE``): rows from
    more than one level that hold one position are ranked by each row's percentile within its own pool, one board per
    gender; rows from more than one level and more than one position by value within each level, one board per level;
    ``rank_by`` forces a mode (each row's ``board``). ``order`` "desc" lists the largest numbers first in value mode, and
    in pool mode the rows highest in their own pool in the raw direction (largest relative to the pool, not the largest
    numbers)."""
    if catalogue_mode(w, scope) or rank_by is not None:
        from regista.catalogue_api import screen_payload

        return await run_in_threadpool(lambda: screen_payload(
            w, scope or "level", metrics_raw=metrics_, position=position, role=role, club=club, q=q,
            min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot, sort=sort, order=order, limit=limit,
            offset=offset, rank_by=rank_by))
    keys = _keys(metrics_, default=DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None]))
    sort_key = _key(sort) if sort else keys[0]

    def run() -> dict[str, Any]:
        sm = metrics()
        rows = sm.sort(_filters(sm, position, role, club, min_minutes, age_min, age_max, foot, q), sort_key, order)
        return {"columns": [sm.describe(k) for k in keys], "sort": sort_key, "total": len(rows), "offset": offset,
                "players": [{**sm.card(ps), "values": {k: {**sm.cell(ps, k), "evidence_total": sm.evidence_total(ps, k)}
                                                       for k in keys}} for ps in rows[offset:offset + limit]],
                "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/terminal/rank")
async def rank(metric: Annotated[str, Query(pattern=KEY_PATTERN)], position: POSITION = None, role: ROLE = None,
               club: CLUB = None, min_minutes: MIN_MINUTES = None, age_min: AGE = None, age_max: AGE = None,
               foot: FOOT = None, order: Literal["asc", "desc"] | None = None,
               limit: int = Query(25, ge=1, le=200), rank_by: RANK_BY = None,
               *, w: WhereDep, scope: ScopeDep) -> dict[str, Any]:
    """One metric's leaderboard, best first unless ``order``. Ratios rank only players with the minimum attempts (the rest
    are listed after, unranked). Catalogue parameters (and ``rank_by``) answer from the catalogue as
    ``/api/terminal/screen`` does: every row with its own pool, ranked as ``RANK_RULE`` says (across levels within one
    position by percentile, one board per gender; across levels and positions by value within each level, one board per
    level), ranks restarting on each board; the response adds ``rank_by``, ``rank_rule`` and ``boards`` (each board's
    key, label, size, offset among the ranked rows and top rows)."""
    if catalogue_mode(w, scope) or rank_by is not None:
        from regista.catalogue_api import rank_payload

        return await run_in_threadpool(lambda: rank_payload(
            w, scope or "level", metric=metric, position=position, role=role, club=club, min_minutes=min_minutes,
            age_min=age_min, age_max=age_max, foot=foot, order=order, limit=limit, rank_by=rank_by))
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
                  age_min: AGE = None, age_max: AGE = None, foot: FOOT = None, *, w: WhereDep,
                  scope: ScopeDep) -> dict[str, Any]:
    """Two metrics for every player who passes the filters and has both values (with how many moments are behind each,
    ``x_evidence_total`` and ``y_evidence_total``); the pool's medians draw the quadrants. Catalogue parameters answer
    from the catalogue (as ``/api/terminal/screen``), each point with ``x_pool`` and ``y_pool``."""
    if catalogue_mode(w, scope):
        from regista.catalogue_api import scatter_payload

        return await run_in_threadpool(lambda: scatter_payload(
            w, scope or "level", x, y, position=position, role=role, club=club, min_minutes=min_minutes,
            age_min=age_min, age_max=age_max, foot=foot))
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
                        "x_percentile": ps.percentiles.get(kx), "y_percentile": ps.percentiles.get(ky),
                        "x_evidence_total": sm.evidence_total(ps, kx), "y_evidence_total": sm.evidence_total(ps, ky)})
        def med(vals: list[float]) -> float | None:
            return round(statistics.median(vals), 4) if vals else None

        return {"x": sm.describe(kx), "y": sm.describe(ky), "points": pts,
                "median": {"x": med([p["x"] for p in pts]), "y": med([p["y"] for p in pts])}, "season": _season_meta(sm)}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/metrics")
async def player_metrics(gid: str, evidence: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                         evidence_limit: int | None = Query(None, ge=0, le=MAX_EVIDENCE),
                         evidence_offset: int = Query(0, ge=0, le=MAX_OFFSET),
                         group: Annotated[str | None, Query(pattern=r"^[a-z]{1,20}$")] = None,
                         competition: COMPETITION = None, *, scope: ScopeDep) -> dict[str, Any]:
    """Every metric (or one ``group``) for one player: value, count, percentile, peers, and evidence (the first
    ``evidence_limit`` items behind each number, default 10, in match order, with ``total`` and ``moments``: ``total``
    counts the rows, one per key, so a ratio's pass and its completion are two; ``moments`` counts each event once).
    ``evidence=KEY`` returns that metric's evidence instead of the whole table: a page of up to 500 items from ``evidence_offset`` (default 0), or
    ``evidence_limit`` of them; page on while ``offset + len(items) < total`` to read every moment.
    ``evidence_limit=0`` returns no items (the totals only), for event and physical metrics alike.

    ``competition=`` (any catalogue competition the player played in) or ``scope`` answer from the catalogue: that row
    (default: the player's row with the most minutes), each cell with its ``pool`` and ``sample``, percentiles in
    ``scope`` (level by default)."""
    if evidence:
        _key(evidence)
    elif evidence_offset:
        raise HTTPException(422, "evidence_offset pages one metric's evidence: give evidence=KEY too")
    if _row_mode(competition, scope):
        from regista.catalogue_api import player_metrics_payload

        return await run_in_threadpool(lambda: player_metrics_payload(
            gid, competition, scope or "level", evidence=evidence, evidence_limit=evidence_limit,
            evidence_offset=evidence_offset, group=group, table_evidence=TABLE_EVIDENCE))

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        if evidence:
            return {"global_id": gid, "name": ps.info["name"], "metric": sm.describe(evidence), **sm.cell(ps, evidence),
                    "evidence": sm.evidence(ps, evidence, limit=MAX_EVIDENCE if evidence_limit is None else evidence_limit,
                                            offset=evidence_offset),
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
async def player_form(gid: str, metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                      competition: COMPETITION = None, *, scope: ScopeDep) -> dict[str, Any]:
    """Per-match values (per 90 of that match, the match ratio, or the match's top speed) and consistency: the mean, standard
    deviation and coefficient of variation over matches with 15+ minutes (Regista's measure; no provider publishes one),
    and the last three matches against the season value. ``competition=`` reads that catalogue row instead."""
    if _row_mode(competition, scope):
        from regista.catalogue_api import player_form_payload

        return await run_in_threadpool(lambda: player_form_payload(gid, competition, scope or "level", metrics_, FORM_RULE))

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        keys = _keys(metrics_, default=DEFAULT_COLUMNS.get(ps.info["position"], DEFAULT_COLUMNS[None]))
        return {**sm.card(ps), **sm.form(ps, keys), "catalogue": {k: sm.describe(k) for k in keys},
                "consistency_rule": FORM_RULE,
                "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/heatmap")
async def player_heatmap(gid: str, competition: COMPETITION = None, *, scope: ScopeDep) -> dict[str, Any]:
    """The player's touch grid from league fixtures only: the same events and cells as the profile page's grid, without
    the confirmed claims and Player-view uploads that the profile adds, so it sits beside the league-only metrics.
    ``competition=`` gives that catalogue competition's uploaded matches instead."""
    if _row_mode(competition, scope):
        from regista.catalogue_api import player_heatmap_payload

        return await run_in_threadpool(lambda: player_heatmap_payload(gid, competition, PITCH))

    def run() -> dict[str, Any]:
        from regista.season_api import season

        sm = metrics()
        ps = _player(sm, gid)
        grid = season().league_grids.get(gid)
        if grid is None:
            raise HTTPException(404, f"no player {gid!r} has played in the league")
        return {**sm.card(ps), "grid": grid, "total": sum(map(sum, grid)), "scope": "Regista League fixtures (synthetic)",
                "pitch": PITCH, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/shots")
async def player_shots(gid: str, competition: COMPETITION = None, *, scope: ScopeDep) -> dict[str, Any]:
    """Every shot the player took in the league, penalties included (the Shots metric follows FBref and leaves penalty
    kicks out; the map shows them, marked): attacking-frame location (x toward the opponent's goal), end point, xG,
    outcome, body part, penalty, football minute, round, opponent and the clip it sits in. ``competition=`` gives that
    catalogue competition's shots instead."""
    if _row_mode(competition, scope):
        from regista.catalogue_api import player_shots_payload

        return await run_in_threadpool(lambda: player_shots_payload(gid, competition, PITCH))

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        shots = sm.player_shots(gid)
        return {**sm.card(ps), "shots": shots, "total": len(shots), "penalties": sum(1 for s in shots if s["penalty"]),
                "goals": sum(1 for s in shots if s["outcome"] == "goal"), "pitch": PITCH, "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/similar")
async def player_similar(gid: str, n: int = Query(5, ge=1, le=20), competition: COMPETITION = None,
                         *, scope: ScopeDep) -> dict[str, Any]:
    """The most similar players in the same position. ``competition=`` or ``scope`` answer from the catalogue: candidates
    in the competition, the level (default) or every level of the gender (each standardised on its own level)."""
    if _row_mode(competition, scope):
        from regista.catalogue_api import player_similar_payload

        rule = SIMILAR_RULE + ("; scope level standardises on the level's pool, scope all on each row's own level's pool"
                               if (scope or "level") != "competition" else "")
        return await run_in_threadpool(lambda: player_similar_payload(gid, competition, scope or "level", n, rule))

    def run() -> dict[str, Any]:
        sm = metrics()
        ps = _player(sm, gid)
        return {**sm.card(ps), **sm.similar(gid, n),
                "rule": SIMILAR_RULE,
                "sources": ["FB-SR"], "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/teams")
async def teams(w: WhereDep) -> dict[str, Any]:
    """Every club's style metrics. Catalogue filters list the selected competitions' clubs instead, each with its rank in
    its competition and among every club of its level."""
    if w.given():
        from regista.catalogue_api import teams_payload

        return await run_in_threadpool(teams_payload, w)

    def run() -> dict[str, Any]:
        sm = metrics()
        return {"metrics": [m.public() for m in TEAM_CATALOGUE.values()],
                "teams": [sm.team_style(cid) | {"per_match": None, "evidence": None} for cid in sm.teams],
                "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/teams/{club_id}/shots")
async def team_shots(club_id: str, side: Literal["for", "against"] = "for", competition: COMPETITION = None) -> dict[str, Any]:
    """Every shot by the club (``side=for``) or by its opponents in its matches (``side=against``), penalties included,
    each with who took it, its xG, outcome, minute and clip: the shots behind the team's xG, goals and shots numbers.
    ``competition=`` reads a catalogue club in that competition."""
    if competition:
        from regista.catalogue_api import team_shots_payload

        return await run_in_threadpool(team_shots_payload, club_id, competition, side, PITCH)
    if not re.match(CLUB_PATTERN, club_id):
        raise HTTPException(400, "bad club id")

    def run() -> dict[str, Any]:
        sm = metrics()
        if club_id not in sm.teams:
            from regista.catalogue_api import club_hint

            raise HTTPException(404, f"no club {club_id!r} in the league{club_hint(club_id)}")
        shots = sm.team_shots(club_id, side)
        return {"club_id": club_id, "club": sm.clubs[club_id]["name"], "side": side, "shots": shots, "total": len(shots),
                "xg": round(sum(s["xg"] or 0.0 for s in shots), 3), "goals": sum(1 for s in shots if s["outcome"] == "goal"),
                "pitch": PITCH, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/teams/{club_id}/style")
async def team_style(club_id: str, competition: COMPETITION = None) -> dict[str, Any]:
    """One club's style with its ranks. ``competition=`` reads a catalogue club in that competition, ranked in its
    competition and among every club of its level (``level_rank``)."""
    if competition:
        from regista.catalogue_api import team_style_payload

        return await run_in_threadpool(team_style_payload, club_id, competition)
    if not re.match(CLUB_PATTERN, club_id):
        raise HTTPException(400, "bad club id")

    def run() -> dict[str, Any]:
        sm = metrics()
        if club_id not in sm.teams:
            from regista.catalogue_api import club_hint

            raise HTTPException(404, f"no club {club_id!r} in the league{club_hint(club_id)}")
        return {**sm.team_style(club_id), "metrics": [m.public() for m in TEAM_CATALOGUE.values()], "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)
