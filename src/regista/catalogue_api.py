"""The catalogue's API: 14 synthetic competitions across countries and levels below the professional line
(``regista.catalogue``; docs/catalogue/build/design.md §8). All reads, all public, never a hidden rating or a level scale.

New endpoints
-------------
GET /api/catalogue                         the catalogue as of its date (as_of: every uploaded match is dated on or before
                                           it): competitions with their labels and upload counts, the levels and their
                                           pools, the careers, totals (reads the committed files; builds nothing)
GET /api/competitions                      competitions; filters country, tier (alias level), age_group, gender
GET /api/competitions/{competition_id}     one competition: clubs with squads (public bio), uploaded matches with uploader
                                           and camera, results (England: the league table; elsewhere uploaded matches
                                           only), the sample, the level's pool sizes
GET /api/competitions/{competition_id}/players   that competition's players with metric columns (scope level by default)
GET /api/catalogue/players                 the cross-country screen: filters tier, age_group, gender, country, competition,
                                           position, role, club, q, min_minutes, age_min, age_max, foot, camera, career;
                                           metrics, sort, order, scope (level by default), limit, offset
GET /api/catalogue/players/{global_id}     one player across the catalogue: bio, career, what adds up, one row per
                                           competition with its pools, touch maps, moments, a rules summary;
                                           evidence=KEY (with competition=) pages one number's evidence
GET /api/catalogue/rank                    one metric's leaderboard within the filters, every row with its own pool
GET /api/catalogue/compare                 two or three players, one row each, and whether they share a pool
GET /api/catalogue/matches                 uploaded matches across the catalogue; filters competition, country, tier,
                                           age_group, gender, club, camera, uploader_type; limit, offset
GET /api/catalogue/pools                   pool sizes per scope and position (small and under-minimum flags)
GET /api/players/{global_id}/career        every competition the player is in, with what they played there

Optional parameters on existing endpoints (season_api, terminal_api) use the helpers here. Without them every existing
response is what it was (tests/test_catalogue_backcompat.py). With any of ``competition``, ``country``, ``tier``
(``level``), ``age_group``, ``gender``, ``scope`` (``pool``) they answer from the catalogue: the selection defaults to
England semi-pro men (the Regista League) unless a filter picks others, and percentiles default to scope ``level``.

Scopes: ``level`` pools the same tier, age group and gender (and position); ``competition`` one competition (for England
today's numbers exactly); ``all`` every tier and age group of one gender, with a warning. Every number carries its pool
(scope, level, position, size, small, min_size, competitions, reason) and its sample.
"""

from __future__ import annotations

import os
import re
import threading
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from regista.catalogue import store
from regista.catalogue.metrics import (ALL_WARNING, BOARD_TOP, GENDER_ORDER, POOL_RULE, RANK_RULE, RELIABILITY_NOTE,
                                       SYNTHETIC_NOTE, CatalogueMetrics, load_catalogue_metrics)
from regista.catalogue.profiles import ENGLAND_BASIS
from regista.catalogue.taxonomy import AS_OF, ENGLAND_ID, levels_public
from regista.catalogue.tools import comp_labels, competition_summary, entries_matching
from regista.season.metrics import CATALOGUE, DEFAULT_COLUMNS, TEAM_CATALOGUE

Record = dict[str, Any]
router = APIRouter()

COMP_PATTERN = r"^co_[a-z0-9_]{1,40}$"
GID_PATTERN = r"^pl_[a-z0-9_]{1,40}$"
CLUB_PATTERN = r"^cl_[a-z0-9_]{1,40}$"
KEY_PATTERN = r"^[a-z0-9_]{1,40}$"
KEYS_PATTERN = r"^[a-z0-9_]{1,40}(,[a-z0-9_]{1,40}){0,15}$"
TIER_PATTERN = "^(semi_pro|amateur|college|academy)$"
MAX_OFFSET = 100000
MAX_EVIDENCE = 500
COMPETITION = Annotated[str | None, Query(pattern=COMP_PATTERN)]
TIER = Annotated[str | None, Query(pattern=TIER_PATTERN)]
AGE_GROUP = Annotated[str | None, Query(pattern="^(senior|college|U20|U19|U18|U17)$")]
GENDER = Annotated[str | None, Query(pattern="^(men|women)$")]
COUNTRY = Annotated[str | None, Query(min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z .'\-]{1,39}$")]
SCOPE = Annotated[Literal["level", "competition", "all"] | None, Query()]
POSITION = Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)$")]
ROLE = Annotated[str | None, Query(pattern="^(GK|FB|CB|DM|CM|AM|W|ST)$")]
CLUB = Annotated[str | None, Query(max_length=40, pattern=r"^[A-Za-z0-9_ ]{1,40}$")]
FOOT = Annotated[str | None, Query(pattern="^(right|left|both)$")]
NAME_Q = Annotated[str | None, Query(max_length=80)]
MIN_MINUTES = Annotated[float | None, Query(ge=0.0, le=10000.0)]
AGE = Annotated[int | None, Query(ge=14, le=50)]
CAMERA = Annotated[str | None, Query(pattern="^(tripod|phone|drone|broadcast)$")]
UPLOADER_TYPE = Annotated[str | None, Query(pattern="^(team|player)$")]

AS_OF_NOTE = ("The catalogue holds footage of matches already played: every uploaded match is dated on or before as_of. "
              "Each competition's season continues after it; its later rounds have no footage yet.")
CAMERA_NOTE = ("Camera type is a label of the upload: Regista renders every match with the same broadcast-style view, and "
               "the vision layer is measured only on that render. Nothing here processes phone or drone footage differently.")
MIXED_WARNING = ALL_WARNING   # rows from different levels: the same caution as scope all
RANK_BY = Annotated[Literal["pool", "value"] | None, Query(description="pool: percentile within each row's own pool "
                                                                       "(default across levels); value: the raw value")]
WARM = {"state": "idle", "error": None}
_warm_lock = threading.Lock()


# ============================================================================ inputs

@dataclass(frozen=True)
class Where:
    """Which competitions a request is about (every field optional)."""

    competition: str | None = None
    country: str | None = None
    tier: str | None = None
    age_group: str | None = None
    gender: str | None = None

    def given(self) -> bool:
        return any(asdict(self).values())

    def public(self) -> Record:
        return {k: v for k, v in asdict(self).items() if v is not None}


def where(competition: COMPETITION = None, country: COUNTRY = None, tier: TIER = None,
          level: Annotated[str | None, Query(pattern=TIER_PATTERN, description="alias of tier")] = None,
          age_group: AGE_GROUP = None, gender: GENDER = None) -> Where:
    """The catalogue's competition filters. ``level`` is an alias of ``tier`` (semi_pro, amateur, college, academy)."""
    if tier and level and tier != level:
        raise HTTPException(422, "tier and level are the same filter: give one, or the same value")
    if competition:
        _known_competition(competition, status=422)
    return Where(competition, country, tier or level, age_group, gender)


def scope_param(scope: SCOPE = None, pool: SCOPE = None) -> str | None:
    """Where percentiles are drawn from: level (default once the catalogue answers), competition or all. ``pool`` is an
    alias of ``scope``."""
    if scope and pool and scope != pool:
        raise HTTPException(422, "scope and pool are the same parameter: give one, or the same value")
    return scope or pool


WhereDep = Annotated[Where, Depends(where)]
ScopeDep = Annotated[str | None, Depends(scope_param)]


def catalogue_mode(w: Where, scope: str | None) -> bool:
    """An existing endpoint answers from the catalogue only when the caller asks for it."""
    return w.given() or scope is not None


def _index_path() -> Path:
    from regista.api import CATALOGUE

    if not CATALOGUE.exists():
        raise HTTPException(404, "no catalogue on this server (data/catalogue/catalogue.json)")
    return CATALOGUE


def _known_competition(cid: str, status: int = 404) -> Record:
    if not re.match(COMP_PATTERN, cid):
        raise HTTPException(400, "bad competition id")
    e = store.entry(cid, _index_path())
    if e is None:
        raise HTTPException(status, f"no competition {cid!r} in the catalogue (GET /api/competitions lists them)")
    return e


def _keys(raw: str | None, *, default: tuple[str, ...] | list[str]) -> list[str]:
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


def _check_ages(age_min: int | None, age_max: int | None) -> None:
    if age_min is not None and age_max is not None and age_min > age_max:
        raise HTTPException(422, "age_min is above age_max")


def _check_gid(gid: str) -> None:
    if not re.match(GID_PATTERN, gid):
        raise HTTPException(400, "bad player id")


# ============================================================================ the engines, built once per process

def catalogue_metrics() -> CatalogueMetrics:
    from regista.api import CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT

    index = _index_path()
    if not SEASON_LEAGUE.exists():
        raise HTTPException(404, "no league on this server (data/season/league.json)")
    return load_catalogue_metrics(index, CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT)


def catalogue_profiles():
    """Every competition's ``Season`` (moments, touch maps, matches, results), with the metrics engine's unrounded
    minutes so a profile stat's pooled percentile ranks rates as ``Season`` does. England's is the app's own season
    (``season_api.season()``: fixtures, confirmed claims and finished Player-view uploads), so England's catalogue-mode
    cards are today's cards (``ENGLAND_BASIS``)."""
    from regista.api import CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT
    from regista.catalogue.profiles import load_catalogue_profiles

    from regista.season_api import season as league_season

    cm = catalogue_metrics()
    cp = load_catalogue_profiles(_index_path(), CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT)
    cp.use_england(league_season())   # the app's own: fixtures plus confirmed claims and Player-view uploads
    if not cp.exact_minutes:
        cp.use_minutes({(cid, gid): ps.minutes for cid in cm.order for gid, ps in cm.metrics[cid].players.items()})
    return cp


def warm_catalogue() -> None:
    """Build the catalogue's matches, metrics and profiles in the background after the league's (``REGISTA_CATALOGUE_WARM``,
    default 1), so the first catalogue request does not wait."""
    from regista.api import CATALOGUE

    if os.environ.get("REGISTA_CATALOGUE_WARM", "1") != "1" or not CATALOGUE.exists():
        return
    with _warm_lock:
        WARM.update(state="building", error=None)
        try:
            catalogue_metrics()
            catalogue_profiles()
            WARM["state"] = "ready"
        except Exception as exc:  # noqa: BLE001 - reported by the catalogue endpoints, never fatal to the app
            WARM.update(state="failed", error=f"{type(exc).__name__}: {exc}")


def is_catalogue_player(gid: str) -> bool:
    """Is this id in a catalogue competition's squad other than England's? (Reads the committed files; builds nothing.)"""
    from regista.api import CATALOGUE

    if not CATALOGUE.exists():
        return False
    try:
        return any(p["global_id"] == gid for comp in store.new_competitions(CATALOGUE) for c in comp["clubs"]
                   for p in c.get("squad", []))
    except (OSError, ValueError, KeyError):
        return False


def player_hint(gid: str) -> str:
    """Added to a 404 for a player who is in the catalogue but not in the Regista League."""
    return f"; a catalogue player: GET /api/catalogue/players/{gid}" if is_catalogue_player(gid) else ""


def club_hint(club_id: str) -> str:
    from regista.api import CATALOGUE

    if not CATALOGUE.exists():
        return ""
    for comp in store.new_competitions(CATALOGUE):
        if any(c["club_id"] == club_id for c in comp["clubs"]):
            return f"; a catalogue club: add competition={comp['competition']['competition_id']}"
    return ""


# ============================================================================ shared pieces

_comp_labels = comp_labels
_summary = competition_summary


def _entries_matching(w: Where) -> list[tuple[Record, Record]]:
    """(index entry, league-shaped competition) for every competition the filters keep, in the index's order."""
    return entries_matching(_index_path(), **asdict(w))


def _selected(cm: CatalogueMetrics, w: Where, default_all: bool) -> list[str]:
    """The competitions a request reads: the filters' competitions, else every competition (new endpoints) or England
    (existing endpoints, so the league's tables keep describing the Regista League unless a caller asks for another)."""
    if not w.given():
        return list(cm.order) if default_all else [ENGLAND_ID]
    return [e["competition_id"] for e, _c in _entries_matching(w) if e["competition_id"] in cm.metrics]


def _warning(cm: CatalogueMetrics, cids: list[str], scope: str) -> str | None:
    if scope == "all":
        return ALL_WARNING
    return MIXED_WARNING if len({cm.level[c] for c in cids}) > 1 else None


def _card(cm: CatalogueMetrics, cid: str, ps) -> Record:
    gid = ps.info["global_id"]
    return {**cm.card(cid, ps), "api_url": f"/api/catalogue/players/{gid}"}


def _describe(cm: CatalogueMetrics, key: str, cids: list[str], scope: str) -> Record:
    """A metric's description: its competition's (ratio minimum, reliability, realism) when one competition is read;
    otherwise the definition with a note that those differ per competition."""
    if len(cids) == 1:
        return cm.describe(key, cids[0], scope)
    m = CATALOGUE[key]
    return {**m.public(), "reliability": None, "reliability_source": "each row's level table (see the row's cells: noisy)",
            "min_attempts": None, "min_attempts_rule": "per competition (a ratio's minimum attempts scale to its minutes)"
            if m.kind == "ratio" else None, "realism": None}


def _meta(cm: CatalogueMetrics, cids: list[str], scope: str) -> Record:
    """The ``season`` block of an existing terminal response answered from the catalogue."""
    comps = []
    for cid in cids:
        sm = cm.metrics[cid]
        comps.append({**cm.labels_of(cid), "region": cm.labels[cid]["region"], "coverage": cm.labels[cid]["coverage"],
                      "level": cm.level[cid], "min_minutes": round(sm.min_minutes, 1),
                      "matches_per_club": sm.matches_per_club, "sample": sm.sample()})
    out: Record = {"scope": scope, "competitions": comps, "percentile_rule": POOL_RULE,
                   "peer_groups": "the league's positions GK, DF, MF, FW, within the scope's pool",
                   "reliability_note": RELIABILITY_NOTE, "warning": _warning(cm, cids, scope),
                   "synthetic": True, "note": SYNTHETIC_NOTE}
    if len(cids) == 1:
        sm = cm.metrics[cids[0]]
        out.update({"competition_id": cids[0], "min_minutes": sm.min_minutes, "matches_per_club": sm.matches_per_club,
                    "thresholds": sm.thresholds, "sample": sm.sample(),
                    "noisy": sorted(k for k in CATALOGUE if cm.noisy(cids[0], k, scope))})
    return out


def _rows(cm: CatalogueMetrics, w: Where, *, default_all: bool, position=None, role=None, club=None, q=None,
          min_minutes=None, age_min=None, age_max=None, foot=None, camera=None, career=None) -> tuple[list[str], list]:
    cids = _selected(cm, w, default_all)
    rows = []
    for cid in cids:
        rows += cm.select(competition=cid, position=position, role=role, q=q, min_minutes=min_minutes, age_min=age_min,
                          age_max=age_max, foot=foot, camera=camera, career=career)
    if club:
        c = club.lower()
        rows = [(cid, ps) for cid, ps in rows
                if c in (ps.info["club_id"].lower(), ps.info["club"].lower(), ps.info["short_name"].lower())]
    return cids, rows


def _pools_of(cm: CatalogueMetrics, cids: list[str], scope: str) -> list[Record]:
    want = set(cids)
    return [p for p in cm.pool_sizes(scope) if want & set(p["competitions"])]


def _people(comp: Record) -> dict[str, Record]:
    from regista.season.league import people

    return people(comp)


def _uploader_public(up: Record | None, comp: Record) -> Record | None:
    """The uploader with a name: the team's, or the player's (a squad member of either side)."""
    if not up:
        return None
    from regista.season.league import club_by_id

    out = dict(up)
    club = club_by_id(comp).get(up.get("club_id") or "")
    out["club"] = club["name"] if club else None
    if up.get("type") == "player":
        p = _people(comp).get(up.get("global_id") or "")
        out["name"] = p["name"] if p else None
    return out


# ============================================================================ new endpoints: the catalogue and its competitions

@router.get("/api/catalogue")
async def get_catalogue() -> Record:
    """The catalogue: every competition with its labels and upload counts, the levels and which competitions share a pool,
    the careers, totals. Reads the committed files only (no match is built), so it answers at once."""

    def run() -> Record:
        index = _index_path()
        idx = store.load_index(index)
        comps = [(e, store.competition(e["competition_id"], index)) for e in store.entries(index)]
        gids = {p["global_id"] for _e, c in comps for club in c["clubs"] for p in club.get("squad", [])}
        return {"catalogue": idx["catalogue"], "season": idx["season"], "as_of": AS_OF, "as_of_note": AS_OF_NOTE,
                "competitions": [_summary(e, c) for e, c in comps], "levels": levels_public(),
                "careers": [{k: car.get(k) for k in ("global_id", "name", "competitions", "clubs", "story")}
                            | {"api_url": f"/api/catalogue/players/{car['global_id']}"} for car in idx.get("careers", [])],
                "totals": {"competitions": len(comps), "countries": len({e["country"] for e, _c in comps}),
                           "clubs": sum(len(c["clubs"]) for _e, c in comps), "players": len(gids),
                           "matches": sum(len(c["fixtures"]) for _e, c in comps)},
                "camera_note": CAMERA_NOTE, "warm": dict(WARM), "synthetic": True, "note": idx.get("note") or SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/competitions")
async def list_competitions(w: WhereDep) -> Record:
    """Competitions, filtered by country, tier (``level``), age_group, gender (and competition)."""

    def run() -> Record:
        rows = [_summary(e, c) for e, c in _entries_matching(w)]
        return {"competitions": rows, "total": len(rows), "filters": w.public(), "levels": levels_public(),
                "camera_note": CAMERA_NOTE, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/competitions/{competition_id}")
async def get_competition(competition_id: str) -> Record:
    """One competition: its labels, its clubs and squads (public bio only), its uploaded matches with uploader and camera
    (each opens in the Clip view), its results and the sample. England semi-pro men's ``table`` is the Regista League's
    table; every other competition has ``table: null`` and ``results`` of its uploaded matches only (``results_note``)."""
    e = _known_competition(competition_id)

    def run() -> Record:
        from regista.season.league import bio, club_by_id

        cm = catalogue_metrics()
        cp = catalogue_profiles()
        comp = store.competition(competition_id, _index_path())
        clubs = club_by_id(comp)
        careers = {gid: [c for c, _p in cm.people.get(gid, []) if c != competition_id] for gid in cm.careers}
        squad_bio = ("age", "date_of_birth", "height_cm", "preferred_foot", "nationality")
        out_clubs = []
        for c in comp["clubs"]:
            squad = [{**{k: p.get(k) for k in ("global_id", "name", "kit_number", "position", "role", "starter")},
                      **{k: v for k, v in bio(p).items() if k in squad_bio},
                      "career": careers.get(p["global_id"]) or None} for p in c.get("squad", [])]
            out_clubs.append({**{k: c.get(k) for k in ("club_id", "name", "short_name", "city", "ground", "kit")},
                              "squad": squad})
        matches = []
        for m in cp.matches(competition_id):
            matches.append({**m, "home_name": clubs[m["home"]]["name"], "away_name": clubs[m["away"]]["name"],
                            "uploader": _uploader_public(m.get("uploader"), comp)})
        results, note = cp.results(competition_id)
        s = cp.seasons[competition_id]
        club_matches = Counter(x for m in matches for x in (m["home"], m["away"]))
        level_pool = next((p for p in cm.pool_sizes("level") if competition_id in p["competitions"]), None)
        return {**_comp_labels(e), "clubs": out_clubs, "matches": matches, "results": results, "results_note": note,
                "table": s.table if e.get("coverage") == "full" else None,
                "sample": {"matches_uploaded": len(matches), "club_matches": dict(sorted(club_matches.items())),
                           "qualifying_minutes": round(s.min_minutes, 1),
                           "note": "Per-90s and percentiles rest on the uploaded matches only." if note else s.sample()["note"]},
                "level_pool": level_pool, "camera_note": CAMERA_NOTE, "warm": dict(WARM), "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


def _boards(cm: CatalogueMetrics, rows: list, genders: list[str] | None) -> list[Record] | None:
    """Each gender board's size and ``offset``: where it starts in the list (rows are grouped by board), so a reader can
    page straight to it."""
    if not genders:
        return None
    out = []
    for g in genders:
        idx = [i for i, (c, _x) in enumerate(rows) if cm.labels[c]["gender"] == g]
        out.append({"gender": g, "rows": len(idx), "offset": idx[0] if idx else None})
    return out


def _screen(cm: CatalogueMetrics, w: Where, scope: str, *, default_all: bool, metrics_raw, position, role, club, q,
            min_minutes, age_min, age_max, foot, camera, career, sort, order, limit, offset, rank_by=None) -> Record:
    _check_ages(age_min, age_max)
    keys = _keys(metrics_raw, default=DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None]))
    sort_key = _key(sort) if sort else keys[0]
    cids, rows = _rows(cm, w, default_all=default_all, position=position, role=role, club=club, q=q,
                       min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot, camera=camera, career=career)
    rows, mode, genders, _ranked = cm.order_rows(rows, sort_key, scope, order, rank_by)

    def row_of(cid: str, ps) -> Record:
        return {**_card(cm, cid, ps), "board": cm.labels[cid]["gender"],
                "values": {k: cm.cell(cid, ps.info["global_id"], k, scope) for k in keys}}

    boards = _boards(cm, rows, genders)
    for b in boards or []:
        b["top"] = [row_of(*r) for r in rows[b["offset"]:b["offset"] + min(BOARD_TOP, b["rows"], limit)]]
    return {"columns": [_describe(cm, k, cids, scope) for k in keys], "scope": scope, "sort": sort_key, "order": order,
            "rank_by": mode, "rank_rule": RANK_RULE, "boards": boards,
            "total": len(rows), "offset": offset, "limit": limit,
            "players": [row_of(cid, ps) for cid, ps in rows[offset:offset + limit]],
            "competitions": cids, "pools": _pools_of(cm, cids, scope), "pool_rule": POOL_RULE,
            "reliability_note": RELIABILITY_NOTE, "warning": _warning(cm, cids, scope), "filters": w.public(),
            "camera_note": CAMERA_NOTE if camera else None, "synthetic": True, "note": SYNTHETIC_NOTE}


@router.get("/api/competitions/{competition_id}/players")
async def competition_players(competition_id: str, scope: ScopeDep,
                              metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                              position: POSITION = None, role: ROLE = None, club: CLUB = None, q: NAME_Q = None,
                              min_minutes: MIN_MINUTES = None, age_min: AGE = None, age_max: AGE = None, foot: FOOT = None,
                              sort: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                              order: Literal["asc", "desc"] | None = None, rank_by: RANK_BY = None,
                              limit: int = Query(50, ge=1, le=200),
                              offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """One competition's players with metric columns (default: the position's core set), percentiles in ``scope``
    (level by default). ``min_minutes`` defaults to the competition's qualifying minutes. Sorted by value (one level);
    ``rank_by=pool`` sorts by percentile."""
    _known_competition(competition_id)

    def run() -> Record:
        return _screen(catalogue_metrics(), Where(competition=competition_id), scope or "level", default_all=False,
                       metrics_raw=metrics_, position=position, role=role, club=club, q=q, min_minutes=min_minutes,
                       age_min=age_min, age_max=age_max, foot=foot, camera=None, career=None, sort=sort, order=order,
                       limit=limit, offset=offset, rank_by=rank_by)

    return await run_in_threadpool(run)


# ============================================================================ new endpoints: players across the catalogue

@router.get("/api/catalogue/players")
async def catalogue_players(w: WhereDep, scope: ScopeDep,
                            metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                            position: POSITION = None, role: ROLE = None, club: CLUB = None, q: NAME_Q = None,
                            min_minutes: MIN_MINUTES = None, age_min: AGE = None, age_max: AGE = None, foot: FOOT = None,
                            camera: CAMERA = None, career: bool | None = None,
                            sort: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                            order: Literal["asc", "desc"] | None = None, rank_by: RANK_BY = None,
                            limit: int = Query(50, ge=1, le=200),
                            offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """The cross-country screen: one row per player and competition (a career player has two), each cell with its pool
    and sample. Percentiles in ``scope`` (level by default). ``min_minutes`` defaults to each row's own competition's
    qualifying minutes; ``camera`` keeps players with an appearance in a match filmed on that camera type; ``career=true``
    only players in two competitions. Rows from more than one level are sorted by each row's percentile within its own
    pool (``rank_by=value`` sorts by the raw value), and men and women are on separate boards (``RANK_RULE``; ``boards``
    gives each board's size, offset and top rows). ``order`` is the raw direction in both modes. Paged by ``offset`` and
    ``limit`` (``total`` counts every row)."""

    def run() -> Record:
        return _screen(catalogue_metrics(), w, scope or "level", default_all=True, metrics_raw=metrics_, position=position,
                       role=role, club=club, q=q, min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot,
                       camera=camera, career=career, sort=sort, order=order, limit=limit, offset=offset, rank_by=rank_by)

    return await run_in_threadpool(run)


def _main_row(cm: CatalogueMetrics, gid: str, competition: str | None) -> tuple[str, Any]:
    rows = cm.player_rows(gid)
    if competition:
        hit = next(((c, ps) for c, ps in rows if c == competition), None)
        if hit is None:
            raise HTTPException(404, f"{gid!r} has not played in {competition!r}")
        return hit
    if not rows:
        raise HTTPException(404, f"{gid!r} has not played in any uploaded match")
    return max(rows, key=lambda r: (r[1].minutes, r[0] == ENGLAND_ID))


@router.get("/api/catalogue/players/{gid}")
async def catalogue_player(gid: str, scope: ScopeDep, competition: COMPETITION = None,
                           metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None,
                           evidence: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                           evidence_limit: int | None = Query(None, ge=0, le=MAX_EVIDENCE),
                           evidence_offset: int = Query(0, ge=0, le=MAX_OFFSET),
                           moments: int = Query(20, ge=0, le=40)) -> Record:
    """The player across the catalogue: bio, the career (every competition, even with 0 minutes), what adds up (no merged
    per-90), and per competition the metrics (default: the position's core set) with their pools, the touch map, the
    competition's rules summary; the best moments across competitions. ``evidence=KEY`` returns one number's evidence
    instead (``competition=`` picks the row, default the one with the most minutes; paged by ``evidence_offset``)."""
    _check_gid(gid)
    keys_in = _keys(metrics_, default=()) if metrics_ else None
    if evidence:
        _key(evidence)
    elif evidence_offset:
        raise HTTPException(422, "evidence_offset pages one metric's evidence: give evidence=KEY too")
    if competition:
        _known_competition(competition, status=422)
    sc = scope or "level"

    def run() -> Record:
        from regista.season.summaries import summary_for

        cm = catalogue_metrics()
        if gid not in cm.people:
            raise HTTPException(404, f"no player {gid!r} in the catalogue")
        if evidence:
            cid, ps = _main_row(cm, gid, competition)
            return {"global_id": gid, "name": ps.info["name"], **cm.labels_of(cid), "metric": cm.describe(evidence, cid, sc),
                    **cm.cell(cid, gid, evidence, sc),
                    "evidence": cm.evidence(cid, gid, evidence, MAX_EVIDENCE if evidence_limit is None else evidence_limit,
                                            evidence_offset), "synthetic": True}
        out = cm.player(gid, sc, keys_in)
        cp = catalogue_profiles()
        for row in out["rows"]:
            cid = row["competition_id"]
            row["touch_map"] = cp.touch_map(cid, gid)
            p = cp.seasons[cid].profiles.get(gid)
            row["summary"] = summary_for(cp.seasons[cid], p) if p else None
        out["moments"] = cp.moments(gid, limit=moments) if moments else []
        out["profile_url"] = f"/players/{gid}" if any(c == ENGLAND_ID for c, _p in cm.people[gid]) else None
        out["summary_note"] = ("Each row's summary is the rules summary of that competition's uploaded matches (ranks among "
                               "the competition's players); no Foundry summary is written for catalogue players yet.")
        out["basis"] = ENGLAND_BASIS if out["profile_url"] else None
        return out

    return await run_in_threadpool(run)


@router.get("/api/players/{gid}/career")
async def player_career(gid: str) -> Record:
    """Every competition the player is in a squad of (season 2026/27): club, shirt, position, appearances, minutes, first
    and last match, the matches; and what adds up across them (no merged per-90). Works for every catalogue player,
    England's included."""
    _check_gid(gid)

    def run() -> Record:
        cm = catalogue_metrics()
        if gid not in cm.people:
            raise HTTPException(404, f"no player {gid!r} in the catalogue")
        return {"global_id": gid, "name": cm.people[gid][0][1]["name"], **career_block(cm, gid), "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


def career_block(cm: CatalogueMetrics, gid: str) -> Record:
    """What ``include=career`` adds to ``/api/players/{id}`` and ``/api/players/{id}/career`` returns."""
    england = any(c == ENGLAND_ID for c, _p in cm.people.get(gid, []))
    return {"career": cm.career(gid), "overall": cm.overall(gid), "story": (cm.careers.get(gid) or {}).get("story"),
            "basis": ENGLAND_BASIS if england else None, "api_url": f"/api/catalogue/players/{gid}"}


def _rank(cm: CatalogueMetrics, w: Where, scope: str, *, default_all: bool, metric: str, position, role, club,
          min_minutes, age_min, age_max, foot, camera, career, order, limit, offset, rank_by=None) -> Record:
    _check_ages(age_min, age_max)
    key = _key(metric)
    m = CATALOGUE[key]
    cids, rows = _rows(cm, w, default_all=default_all, position=position, role=role, club=club, min_minutes=min_minutes,
                       age_min=age_min, age_max=age_max, foot=foot, camera=camera, career=career)
    rows, mode, genders, by_pct = cm.order_rows(rows, key, scope, order, rank_by)
    if mode == "pool":
        ranked = [(cid, ps) for cid, ps in rows if (cid, ps.info["global_id"]) in by_pct]
    else:
        ranked = [(cid, ps) for cid, ps in rows
                  if cm.metrics[cid].qualified(ps, m) or (m.kind == "total" and ps.values.get(key) is not None)]
    ranked_ids = {(cid, ps.info["global_id"]) for cid, ps in ranked}
    rest = [(cid, ps) for cid, ps in rows if (cid, ps.info["global_id"]) not in ranked_ids]
    places, prev, place, board, n_in_board = [], None, 0, None, 0
    for cid, ps in ranked:
        g = cm.labels[cid]["gender"]
        if g != board:   # each gender's board ranks from 1
            board, n_in_board, prev = g, 0, None
        n_in_board += 1
        v = round(ps.values[key], m.digits)
        tie = (cm.percentile(cid, ps, key, scope), v) if mode == "pool" else v
        if tie != prev:
            place, prev = n_in_board, tie
        places.append(place)

    def row_of(i: int) -> Record:
        cid, ps = ranked[i]
        return {"rank": places[i], "board": cm.labels[cid]["gender"], **_card(cm, cid, ps),
                **cm.cell(cid, ps.info["global_id"], key, scope),
                "evidence_count": sum(len(ps.evidence.get(k, [])) for k in m.evidence_keys())}

    out = [row_of(i) for i in range(offset, min(offset + limit, len(ranked)))]
    boards = None
    if genders:   # each board's size, where it starts among the ranked rows (page there with offset), and its top rows
        boards = []
        for g in genders:
            idx = [i for i, (c, _ps) in enumerate(ranked) if cm.labels[c]["gender"] == g]
            boards.append({"gender": g, "ranked": len(idx), "offset": idx[0] if idx else None,
                           "top": [row_of(i) for i in idx[:min(BOARD_TOP, limit)]]})
    return {"metric": _describe(cm, key, cids, scope), "scope": scope, "rank_by": mode, "rank_rule": RANK_RULE,
            "boards": boards, "players": out, "ranked": len(ranked), "offset": offset, "limit": limit,
            "unranked": [{**_card(cm, cid, ps), "board": cm.labels[cid]["gender"], **cm.cell(cid, ps.info["global_id"], key, scope)}
                         for cid, ps in rest[:limit]],
            "competitions": cids, "pool_rule": POOL_RULE, "warning": _warning(cm, cids, scope), "filters": w.public(),
            "synthetic": True, "note": SYNTHETIC_NOTE}


@router.get("/api/catalogue/rank")
async def catalogue_rank(metric: Annotated[str, Query(pattern=KEY_PATTERN)], w: WhereDep, scope: ScopeDep,
                         position: POSITION = None, role: ROLE = None, club: CLUB = None, min_minutes: MIN_MINUTES = None,
                         age_min: AGE = None, age_max: AGE = None, foot: FOOT = None, camera: CAMERA = None,
                         career: bool | None = None, order: Literal["asc", "desc"] | None = None,
                         rank_by: RANK_BY = None,
                         limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """One metric's leaderboard across the filtered catalogue. Rows from more than one level are ranked by each row's
    percentile within its own pool (best first; ties by pool size, minutes, then value), never by raw values from
    different levels; within one level by value. ``rank_by`` forces either. ``order`` is the raw direction in both modes
    ("desc": the largest numbers first, even where lower is better). Men and women are never ranked together: a
    selection holding both gives one board per gender (each row's ``board``; ranks restart at 1; ``boards`` gives each
    board's size, its ``offset`` among the ranked rows and its ``top`` rows, so the second board is on every page). Rows
    without a percentile (pool rank) or without their competition's minimum attempts (value rank) are listed after,
    unranked."""

    def run() -> Record:
        return _rank(catalogue_metrics(), w, scope or "level", default_all=True, metric=metric, position=position,
                     role=role, club=club, min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot,
                     camera=camera, career=career, order=order, limit=limit, offset=offset, rank_by=rank_by)

    return await run_in_threadpool(run)


@router.get("/api/catalogue/compare")
async def catalogue_compare(ids: Annotated[str, Query(pattern=r"^pl_[a-z0-9_]{1,40}(,pl_[a-z0-9_]{1,40}){1,2}$")],
                            scope: ScopeDep,
                            competitions: Annotated[str | None, Query(pattern=r"^co_[a-z0-9_]{1,40}(,co_[a-z0-9_]{1,40}){1,2}$")] = None,
                            metrics_: Annotated[str | None, Query(alias="metrics", pattern=KEYS_PATTERN)] = None) -> Record:
    """Two or three players, one row each (by default the row with the most minutes; ``competitions`` picks the rows, in
    the order of ``ids``), every chosen metric (default: the first player's position's core set) with its pool.
    ``same_pool`` says whether every percentile comes from the same pool; otherwise a ``warning``."""
    gids = list(dict.fromkeys(ids.split(",")))
    if len(gids) < 2:
        raise HTTPException(422, "compare needs two or three different players")
    comps = competitions.split(",") if competitions else [None] * len(gids)
    if len(comps) != len(gids):
        raise HTTPException(422, "competitions needs one competition per player, in the order of ids")
    for c in comps:
        if c:
            _known_competition(c, status=422)
    keys_in = _keys(metrics_, default=()) if metrics_ else None
    sc = scope or "level"

    def run() -> Record:
        cm = catalogue_metrics()
        chosen = []
        for gid, c in zip(gids, comps):
            if gid not in cm.people:
                raise HTTPException(404, f"no player {gid!r} in the catalogue")
            chosen.append(_main_row(cm, gid, c))
        keys = keys_in or list(DEFAULT_COLUMNS.get(chosen[0][1].info["position"], DEFAULT_COLUMNS[None]))
        pools = {(cm._pool_id(cid, sc), ps.info["position"]) for cid, ps in chosen}
        same = len(pools) == 1
        cids = list(dict.fromkeys(c for c, _p in chosen))
        return {"players": [{**_card(cm, cid, ps), "values": {k: cm.cell(cid, ps.info["global_id"], k, sc) for k in keys}}
                            for cid, ps in chosen],
                "columns": [_describe(cm, k, cids, sc) for k in keys],
                "scope": sc, "same_pool": same,
                "warning": None if same else "different pools (level or position): read each percentile against its own pool",
                "pool_rule": POOL_RULE, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/catalogue/matches")
async def catalogue_matches(w: WhereDep, club: Annotated[str | None, Query(pattern=CLUB_PATTERN)] = None,
                            camera: CAMERA = None, uploader_type: UPLOADER_TYPE = None,
                            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """Uploaded matches across the catalogue, in the index's competition order then date: each with its competition,
    score, uploader (team or player, named) and camera, and its Clip view link. Paged by ``offset`` and ``limit``."""

    def run() -> Record:
        from regista.season.league import club_by_id

        catalogue_metrics()
        cp = catalogue_profiles()
        rows = []
        for e, comp in _entries_matching(w):
            cid = e["competition_id"]
            if cid not in cp.seasons:
                continue
            clubs = club_by_id(comp)
            for m in sorted(cp.matches(cid), key=lambda m: (m["date"], m["match_id"])):
                up = m.get("uploader") or {}
                if (camera and m.get("camera") != camera) or (uploader_type and up.get("type") != uploader_type) or \
                        (club and club not in (m["home"], m["away"])):
                    continue
                rows.append({**m, "competition_id": cid, "competition": e["name"], "country": e["country"],
                             "tier": e["tier"], "age_group": e["age_group"], "gender": e["gender"],
                             "home_name": clubs[m["home"]]["name"], "away_name": clubs[m["away"]]["name"],
                             "uploader": _uploader_public(m.get("uploader"), comp)})
        return {"matches": rows[offset:offset + limit], "total": len(rows), "offset": offset, "limit": limit,
                "filters": {**w.public(), **{k: v for k, v in (("club", club), ("camera", camera),
                                                                ("uploader_type", uploader_type)) if v}},
                "camera_note": CAMERA_NOTE, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/catalogue/pools")
async def catalogue_pools(scope: ScopeDep) -> Record:
    """Per pool and position, how many rows qualify on minutes (each under its own competition's rule), with ``small``
    (under 15) and ``under_min`` (no percentile) flags. A metric's own pool can be smaller (ratio attempts)."""

    def run() -> Record:
        cm = catalogue_metrics()
        sc = scope or "level"
        return {"scope": sc, "pools": cm.pool_sizes(sc), "min_pool": cm.MIN_POOL, "small_pool": cm.SMALL_POOL,
                "pool_rule": POOL_RULE, "warning": ALL_WARNING if sc == "all" else None, "synthetic": True,
                "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


# ============================================================================ existing endpoints answered from the catalogue

def season_payload(competition_id: str, stats: list[Record]) -> Record:
    """``/api/season?competition=``: the same keys for that competition (``league`` is its name). A sparse competition's
    ``table`` is its uploaded matches' results (``table_note``); ``rounds`` lists the matchdays with uploads."""
    from regista.season.league import bio, club_by_id
    from regista.season.profiles import METRIC_OF, PERCENTILE_RULE, RATIOS, STATS

    e = _known_competition(competition_id, status=422)
    cm = catalogue_metrics()
    cp = catalogue_profiles()
    s = cp.seasons[competition_id]
    comp = s.league
    clubs = club_by_id(comp)
    rounds: dict[int, list[Record]] = {}
    for m in cp.matches(competition_id):
        rounds.setdefault(m["round"], []).append({**m, "home_name": clubs[m["home"]]["name"],
                                                  "away_name": clubs[m["away"]]["name"],
                                                  "uploader": _uploader_public(m.get("uploader"), comp)})
    results, note = cp.results(competition_id)
    squad_fields = ("global_id", "name", "kit_number", "position", "starter")
    squad_bio = ("age", "date_of_birth", "height_cm", "preferred_foot", "nationality")
    noisy = [k for k in [*STATS, "aerial_duels", *RATIOS] if METRIC_OF.get(k, k) in CATALOGUE
             and cm.noisy(competition_id, METRIC_OF.get(k, k), "competition")]
    return {"league": comp["league"], "season": comp["season"],
            "clubs": [{**{k: c.get(k) for k in ("club_id", "name", "short_name", "kit", "ground")},
                       "squad": [{**{k: p.get(k) for k in squad_fields}, **{k: v for k, v in bio(p).items() if k in squad_bio}}
                                 for p in c.get("squad", [])]} for c in comp["clubs"]],
            "table": results, "table_note": note,
            "rounds": [{"round": r, "date": ms[0]["date"], "matches": ms} for r, ms in sorted(rounds.items())],
            "generator": comp["generator"], "stats": stats, "warm": dict(WARM),
            "percentiles": {"rule": PERCENTILE_RULE, "min_minutes": s.min_minutes, "scope": "competition",
                            "min_pool": s._min_pool},
            "sample": s.sample(), "noisy": noisy, "competition": _comp_labels(e), "camera_note": CAMERA_NOTE,
            "note": SYNTHETIC_NOTE + " Bios (age at 1 August 2026, height, foot, nationality) are synthetic too."}


def players_payload(w: Where, scope: str, *, position, club, q, min_minutes, sort, limit, offset,
                    stats: list[Record], rank_by: str | None = None) -> Record:
    """``/api/players`` with catalogue filters: profile cards from each selected competition's ``Season``, each headline
    percentile replaced by the scope's (with its pool); paged by ``offset``. England's cards come from the app's own
    season (fixtures, confirmed claims, Player-view uploads), so they are today's cards (``basis``).

    Ranked as ``RANK_RULE`` says, like ``/api/catalogue/players``: cards from more than one level sorted by a per-90 stat
    or a ratio are ranked by each card's percentile in ``scope`` (highest first, then pools that are not small, then more
    minutes, then the value; cards without a percentile follow, by value), never by raw rates from different levels;
    within one level, and for ``minutes`` or ``name``, by value; ``rank_by`` forces either. Men and women are never
    ranked together: a selection holding both has one board per gender (``boards``: each board's size and offset)."""
    from regista.season.profiles import _sort_key, card

    cm = catalogue_metrics()
    cp = catalogue_profiles()
    cids = _selected(cm, w, default_all=False)
    found = []
    for cid in cids:
        s = cp.seasons[cid]
        for p in s.profiles.values():
            if not p["appearances"]:
                continue
            if position and p["position"] != position:
                continue
            if club and club.lower() not in (p["club_id"].lower(), p["club"].lower(), p["short_name"].lower()):
                continue
            if min_minutes and p["minutes"] < min_minutes:
                continue
            if q and not all(x in p["name"].lower() or x in p["club"].lower() for x in q.lower().split()):
                continue
            found.append((cid, p))
    try:
        found.sort(key=lambda r: (_sort_key(r[1], sort), r[0]))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    rateable = sort not in ("name", "minutes")
    if rank_by:
        mode = rank_by if rateable else "value"
    else:
        mode = "pool" if rateable and len({cm.level[cid] for cid, _p in found}) > 1 else "value"
    if mode == "pool":
        pct = {(cid, p["global_id"]): cp.sort_percentile(cid, p["global_id"], sort, scope) for cid, p in found}
        have = [r for r in found if pct[(r[0], r[1]["global_id"])][0] is not None]
        none = [r for r in found if pct[(r[0], r[1]["global_id"])][0] is None]
        have.sort(key=lambda r: (-pct[(r[0], r[1]["global_id"])][0], pct[(r[0], r[1]["global_id"])][1], -r[1]["minutes"],
                                 _sort_key(r[1], sort), r[0]))
        found = have + none
    genders = [g for g in GENDER_ORDER if any(cm.labels[cid]["gender"] == g for cid, _p in found)]
    boards = None
    if len(genders) > 1:
        found.sort(key=lambda r: GENDER_ORDER.index(cm.labels[r[0]]["gender"]))   # stable: each board keeps its order
        boards = _boards(cm, found, genders)
    rows = []
    for cid, p in found[offset:offset + limit]:
        c = card(p)
        for stat, h in c["headline"].items():
            sc = cp.stat_cell(cid, p["global_id"], stat, scope)
            h["percentile"], h["pool"] = sc["percentile"], sc["pool"]
        rows.append({**c, **cm.labels_of(cid), "board": cm.labels[cid]["gender"],
                     "career": len(cm.people.get(p["global_id"], [])) > 1,
                     "profile_url": f"/players/{p['global_id']}" if cid == ENGLAND_ID else None,
                     "api_url": f"/api/catalogue/players/{p['global_id']}"})
    return {"players": rows, "total": len(found), "offset": offset, "sort": sort, "stats": stats, "scope": scope,
            "rank_by": mode, "rank_rule": RANK_RULE, "boards": boards, "competitions": cids, "filters": w.public(), "pool_rule": POOL_RULE, "warning": _warning(cm, cids, scope),
            "basis": ENGLAND_BASIS if ENGLAND_ID in cids else None, "synthetic": True, "note": SYNTHETIC_NOTE}


TERMINAL_RANK_KEYS = ("rank_by", "rank_rule", "boards")   # added in catalogue mode only: how the rows were ranked


def screen_payload(w: Where, scope: str, **kw: Any) -> Record:
    """``/api/terminal/screen`` with catalogue parameters: today's keys (``columns``, ``sort``, ``total``, ``offset``,
    ``players``, ``season``), every cell with its pool and sample, plus how the rows were ranked (``rank_by``,
    ``rank_rule``, ``boards``: ``RANK_RULE``; across levels by percentile, genders on separate boards)."""
    cm = catalogue_metrics()
    out = _screen(cm, w, scope, default_all=False, camera=None, career=None, **kw)
    return ({k: out[k] for k in ("columns", "sort", "total", "offset", "players", *TERMINAL_RANK_KEYS)}
            | {"season": _meta(cm, out["competitions"], scope)})


def rank_payload(w: Where, scope: str, **kw: Any) -> Record:
    """``/api/terminal/rank`` with catalogue parameters: today's keys plus ``rank_by``, ``rank_rule`` and ``boards``."""
    cm = catalogue_metrics()
    out = _rank(cm, w, scope, default_all=False, camera=None, career=None, offset=0, **kw)
    return ({k: out[k] for k in ("metric", "players", "ranked", "unranked", *TERMINAL_RANK_KEYS)}
            | {"season": _meta(cm, out["competitions"], scope)})


def scatter_payload(w: Where, scope: str, x: str, y: str, **kw: Any) -> Record:
    import statistics

    _check_ages(kw.get("age_min"), kw.get("age_max"))
    cm = catalogue_metrics()
    kx, ky = _key(x), _key(y)
    cids, rows = _rows(cm, w, default_all=False, **kw)
    pts = []
    for cid, ps in rows:
        vx, vy = ps.values.get(kx), ps.values.get(ky)
        if vx is None or vy is None:
            continue
        gid = ps.info["global_id"]
        cx, cy = cm.cell(cid, gid, kx, scope), cm.cell(cid, gid, ky, scope)
        pts.append({**_card(cm, cid, ps), "x": round(vx, CATALOGUE[kx].digits), "y": round(vy, CATALOGUE[ky].digits),
                    "x_percentile": cx["percentile"], "y_percentile": cy["percentile"],
                    "x_evidence_total": cx["evidence_total"], "y_evidence_total": cy["evidence_total"],
                    "x_pool": cx["pool"], "y_pool": cy["pool"]})

    def med(vals: list[float]) -> float | None:
        return round(statistics.median(vals), 4) if vals else None

    return {"x": _describe(cm, kx, cids, scope), "y": _describe(cm, ky, cids, scope), "points": pts,
            "median": {"x": med([p["x"] for p in pts]), "y": med([p["y"] for p in pts])}, "season": _meta(cm, cids, scope)}


def player_row(gid: str, competition: str | None) -> tuple[CatalogueMetrics, str, Any]:
    """The catalogue row a player endpoint answers with: ``competition``'s, else the one with the most minutes."""
    _check_gid(gid)
    if competition:
        _known_competition(competition, status=422)
    cm = catalogue_metrics()
    if gid not in cm.people:
        raise HTTPException(404, f"no player {gid!r} in the catalogue")
    cid, ps = _main_row(cm, gid, competition)
    return cm, cid, ps


def player_metrics_payload(gid: str, competition: str | None, scope: str, *, evidence, evidence_limit, evidence_offset,
                           group, table_evidence: int) -> Record:
    cm, cid, ps = player_row(gid, competition)
    if evidence:
        return {"global_id": gid, "name": ps.info["name"], **cm.labels_of(cid), "metric": cm.describe(evidence, cid, scope),
                **cm.cell(cid, gid, evidence, scope),
                "evidence": cm.evidence(cid, gid, evidence, MAX_EVIDENCE if evidence_limit is None else evidence_limit,
                                        evidence_offset), "synthetic": True}
    keys = [k for k, m in CATALOGUE.items() if not group or m.group == group]
    if group and not keys:
        raise HTTPException(422, f"unknown group {group!r}")
    limit = table_evidence if evidence_limit is None else evidence_limit
    return {**_card(cm, cid, ps), "metrics": {k: {**cm.cell(cid, gid, k, scope), "evidence": cm.evidence(cid, gid, k, limit)}
                                              for k in keys},
            "catalogue": {k: cm.describe(k, cid, scope) for k in keys}, "season": _meta(cm, [cid], scope)}


def player_form_payload(gid: str, competition: str | None, scope: str, metrics_raw: str | None, rule: str) -> Record:
    cm, cid, ps = player_row(gid, competition)
    keys = _keys(metrics_raw, default=DEFAULT_COLUMNS.get(ps.info["position"], DEFAULT_COLUMNS[None]))
    return {**_card(cm, cid, ps), **cm.metrics[cid].form(ps, keys), "catalogue": {k: cm.describe(k, cid, scope) for k in keys},
            "consistency_rule": rule, "synthetic": True, "note": SYNTHETIC_NOTE}


def player_similar_payload(gid: str, competition: str | None, scope: str, n: int, rule: str) -> Record:
    cm, cid, ps = player_row(gid, competition)
    sim = cm.similar(cid, gid, scope, n)
    for row in sim["similar"]:
        row["api_url"] = f"/api/catalogue/players/{row['global_id']}"
    return {**_card(cm, cid, ps), **sim, "rule": rule, "sources": ["FB-SR"], "synthetic": True, "note": SYNTHETIC_NOTE}


def player_shots_payload(gid: str, competition: str | None, pitch: Record) -> Record:
    cm, cid, ps = player_row(gid, competition)
    shots = cm.metrics[cid].player_shots(gid)
    return {**_card(cm, cid, ps), "shots": shots, "total": len(shots), "penalties": sum(1 for s in shots if s["penalty"]),
            "goals": sum(1 for s in shots if s["outcome"] == "goal"), "pitch": pitch, "synthetic": True, "note": SYNTHETIC_NOTE}


def player_heatmap_payload(gid: str, competition: str | None, pitch: Record) -> Record:
    cm, cid, ps = player_row(gid, competition)
    grid = catalogue_profiles().touch_map(cid, gid)
    if grid is None:
        raise HTTPException(404, f"no player {gid!r} has played in {cid!r}")
    return {**_card(cm, cid, ps), "grid": grid, "total": sum(map(sum, grid)),
            "scope": f"{cm.labels[cid]['name']} uploaded matches (synthetic)", "pitch": pitch, "synthetic": True,
            "note": SYNTHETIC_NOTE}


def teams_payload(w: Where) -> Record:
    cm = catalogue_metrics()
    cids = _selected(cm, w, default_all=False)
    return {"metrics": [m.public() for m in TEAM_CATALOGUE.values()],
            "teams": [cm.team_style(cid, club) | {"per_match": None, "evidence": None}
                      for cid in cids for club in cm.metrics[cid].teams],
            "competitions": cids, "synthetic": True, "note": SYNTHETIC_NOTE}


def team_competition(club_id: str, competition: str) -> CatalogueMetrics:
    if not re.match(CLUB_PATTERN, club_id):
        raise HTTPException(400, "bad club id")
    _known_competition(competition, status=422)
    cm = catalogue_metrics()
    if club_id not in cm.metrics[competition].teams:
        raise HTTPException(404, f"no club {club_id!r} with an uploaded match in {competition!r}")
    return cm


def team_style_payload(club_id: str, competition: str) -> Record:
    cm = team_competition(club_id, competition)
    return {**cm.team_style(competition, club_id), "metrics": [m.public() for m in TEAM_CATALOGUE.values()],
            "synthetic": True, "note": SYNTHETIC_NOTE}


def team_shots_payload(club_id: str, competition: str, side: str, pitch: Record) -> Record:
    cm = team_competition(club_id, competition)
    sm = cm.metrics[competition]
    shots = sm.team_shots(club_id, side)
    return {"club_id": club_id, "club": sm.clubs[club_id]["name"], "side": side, **cm.labels_of(competition),
            "shots": shots, "total": len(shots), "xg": round(sum(s["xg"] or 0.0 for s in shots), 3),
            "goals": sum(1 for s in shots if s["outcome"] == "goal"), "pitch": pitch, "synthetic": True,
            "note": SYNTHETIC_NOTE}
