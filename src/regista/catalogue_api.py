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
GET /api/catalogue/directory               every player-competition row once, by name: the cards without metric cells (a
                                           name search's one read), and each competition's qualifying minutes
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
from regista.catalogue.metrics import (ALL_WARNING, NONE_YET_RULE, NOISY_WORDS, POOL_RULE, RANK_RULE, RELIABILITY_NOTE,
                                       SYNTHETIC_NOTE, CatalogueMetrics, load_catalogue_metrics)
from regista.catalogue.profiles import ENGLAND_BASIS, FIXTURES_BASIS
from regista.catalogue.taxonomy import AS_OF, ENGLAND_ID, levels_public
from regista.catalogue.tools import comp_labels, competition_summary, entries_matching
from regista.season.metrics import CATALOGUE, COUNT_METRICS, DEFAULT_COLUMNS, TEAM_CATALOGUE

Record = dict[str, Any]
router = APIRouter()

COMP_PATTERN = r"^co_[a-z0-9_]{1,40}$"
GID_PATTERN = r"^pl_[a-z0-9_]{1,40}$"
CLUB_PATTERN = r"^cl_[a-z0-9_]{1,40}$"
KEY_PATTERN = r"^[a-z0-9_]{1,40}$"
KEYS_PATTERN = r"^[a-z0-9_]{1,40}(,[a-z0-9_]{1,40}){0,15}$"
TIER_PATTERN = "^(semi_pro|amateur|college|academy)(,(semi_pro|amateur|college|academy)){0,3}$"   # one tier or a list
MAX_OFFSET = 100000
MAX_EVIDENCE = 500
COMPETITION = Annotated[str | None, Query(pattern=COMP_PATTERN)]
TIER = Annotated[str | None, Query(pattern=TIER_PATTERN)]
AGE_GROUP = Annotated[str | None, Query(pattern="^(senior|college|U20|U19|U18|U17)$")]
GENDER = Annotated[str | None, Query(pattern="^(men|women)$")]
COUNTRY = Annotated[str | None, Query(min_length=2, max_length=40, pattern=r"^[A-Za-z][A-Za-z .'\-]{1,39}$")]
SCOPE = Annotated[Literal["level", "competition", "all"] | None, Query()]
POSITION = Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)$")]
# /api/catalogue/players and /rank: one position or a comma list ("DF,MF,FW": the positions a metric is scored for, so a
# goals list with no position picked leaves goalkeepers out, as the metrics engine decides)
POSITIONS = Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)(,(GK|DF|MF|FW)){0,3}$",
                                        description="one position or a comma list of them")]
ROLE = Annotated[str | None, Query(pattern="^(GK|FB|CB|DM|CM|AM|W|ST)$")]
CLUB = Annotated[str | None, Query(max_length=40, pattern=r"^[A-Za-z0-9_ ]{1,40}$")]
FOOT = Annotated[str | None, Query(pattern="^(right|left|both)$")]
NAME_Q = Annotated[str | None, Query(max_length=80)]
MIN_MINUTES = Annotated[float | None, Query(ge=0.0, le=10000.0)]
AGE = Annotated[int | None, Query(ge=14, le=50)]
CAMERA = Annotated[str | None, Query(pattern="^(tripod|phone|drone|broadcast)$")]
UPLOADER_TYPE = Annotated[str | None, Query(pattern="^(team|player)$")]
MIN_PERCENTILE = Annotated[float | None, Query(ge=0.0, le=100.0, description="keep rows whose percentile in their own "
                                                                            "pool (scope) is at least this; none yet never")]
LIST_SORTS = ("minutes", "name")   # /api/catalogue/players sorts that are not metrics

PLAYER_UPLOADS_NOTE = ("Uploaded through the Player view; not counted in this competition's numbers, which count the "
                       "competition's own uploaded matches only.")
AS_OF_NOTE = ("The catalogue holds footage of matches already played: every uploaded match is dated on or before as_of. "
              "Each competition's season continues after it; its later rounds have no footage yet.")
CAMERA_NOTE = ("Camera type is a label of the upload: Regista renders every match with the same broadcast-style view, and "
               "the vision layer is measured only on that render. Nothing here processes phone or drone footage differently.")
MIXED_WARNING = ALL_WARNING   # rows from different levels: the same caution as scope all
RANK_BY = Annotated[Literal["pool", "value"] | None, Query(description="pool: percentile within each row's own pool "
                                                                       "(default across levels within one position); "
                                                                       "value: the raw value within each level")]
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
    """The catalogue's competition filters. ``level`` is an alias of ``tier`` (semi_pro, amateur, college, academy, or a
    comma list of them: ``amateur,college,academy``)."""
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


def catalogue_profiles(basis: Literal["app", "fixtures"] = "app"):
    """Every competition's ``Season`` (moments, touch maps, matches, results), with the metrics engine's unrounded
    minutes so a profile stat's pooled percentile ranks rates as ``Season`` does. ``basis="app"`` (the default): England's
    is the app's own season (``season_api.season()``: fixtures, confirmed claims and finished Player-view uploads), so
    England's catalogue-mode cards on ``/api/players`` are today's cards (``ENGLAND_BASIS``). ``basis="fixtures"``: the
    catalogue's own pages, where England counts the Regista League's fixtures only (``FIXTURES_BASIS``), as every other
    competition counts its own uploaded matches."""
    from regista.api import CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT
    from regista.catalogue.profiles import load_catalogue_profiles

    from regista.season_api import season as league_season

    cm = catalogue_metrics()
    cp = load_catalogue_profiles(_index_path(), CATALOGUE_ROOT, SEASON_LEAGUE, SEASON_ROOT)
    cp.use_england(league_season())   # the app's own: fixtures plus confirmed claims and Player-view uploads
    if not cp.exact_minutes:
        cp.use_minutes({(cid, gid): ps.minutes for cid in cm.order for gid, ps in cm.metrics[cid].players.items()})
    if not cp.thresholds:
        cp.use_thresholds({cid: cm.metrics[cid].thresholds for cid in cm.order})
    return cp.fixtures_only() if basis == "fixtures" else cp


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
            catalogue_profiles("fixtures")
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


def sample_words(cm: CatalogueMetrics, cid: str) -> str:
    return cm.sample_words(cid)


def _sample(cm: CatalogueMetrics, cid: str) -> Record:
    """A competition's sample with its plain ``words``."""
    return {**cm.metrics[cid].sample(), "words": cm.sample_words(cid)}


def _meta(cm: CatalogueMetrics, cids: list[str], scope: str) -> Record:
    """The ``season`` block of an existing terminal response answered from the catalogue."""
    comps = []
    for cid in cids:
        sm = cm.metrics[cid]
        comps.append({**cm.labels_of(cid), "region": cm.labels[cid]["region"], "coverage": cm.labels[cid]["coverage"],
                      "level": cm.level[cid], "min_minutes": round(sm.min_minutes, 1),
                      "matches_per_club": sm.matches_per_club, "sample": _sample(cm, cid)})
    out: Record = {"scope": scope, "competitions": comps, "percentile_rule": POOL_RULE,
                   "peer_groups": "the league's positions GK, DF, MF, FW, within the scope's pool",
                   "reliability_note": RELIABILITY_NOTE, "warning": _warning(cm, cids, scope),
                   "synthetic": True, "note": SYNTHETIC_NOTE}
    if len(cids) == 1:
        sm = cm.metrics[cids[0]]
        out.update({"competition_id": cids[0], "min_minutes": sm.min_minutes, "matches_per_club": sm.matches_per_club,
                    "thresholds": sm.thresholds, "sample": _sample(cm, cids[0]),
                    "noisy": sorted(k for k in CATALOGUE if cm.noisy(cids[0], k, scope))})
    return out


def _rows(cm: CatalogueMetrics, w: Where, *, default_all: bool, position=None, role=None, club=None, q=None,
          min_minutes=None, age_min=None, age_max=None, foot=None, camera=None, career=None) -> tuple[list[str], list]:
    cids = _selected(cm, w, default_all)
    several = sorted(set(position.split(","))) if position and "," in position else None
    rows = []
    for cid in cids:
        rows += cm.select(competition=cid, position=None if several else position, role=role, q=q,
                          min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot, camera=camera,
                          career=career)
    if several:
        rows = [(cid, ps) for cid, ps in rows if ps.info["position"] in several]
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
    """The catalogue: every competition with its labels and upload counts, the levels and which competitions share a pool
    (with their plain ``words`` and ``label``), every club (``clubs``: id, name, short name, competition, kit), the
    careers, totals, the counts that read "none yet" at 0 (``count_metrics``, ``none_yet_rule``) and what ≈ means
    (``noisy_words``). Reads the committed files only (no match is built), so it answers at once."""

    def run() -> Record:
        index = _index_path()
        idx = store.load_index(index)
        comps = [(e, store.competition(e["competition_id"], index)) for e in store.entries(index)]
        gids = {p["global_id"] for _e, c in comps for club in c["clubs"] for p in club.get("squad", [])}
        clubs = [{"club_id": club["club_id"], "name": club["name"], "short_name": club["short_name"],
                  "competition_id": e["competition_id"], "kit": club.get("kit")} for e, c in comps for club in c["clubs"]]
        return {"catalogue": idx["catalogue"], "season": idx["season"], "as_of": AS_OF, "as_of_note": AS_OF_NOTE,
                "competitions": [_summary(e, c) for e, c in comps], "levels": levels_public(words=True),
                "clubs": clubs, "count_metrics": sorted(COUNT_METRICS), "none_yet_rule": NONE_YET_RULE,
                "noisy_words": NOISY_WORDS,
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
        return {"competitions": rows, "total": len(rows), "filters": w.public(), "levels": levels_public(words=True),
                "camera_note": CAMERA_NOTE, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


@router.get("/api/competitions/{competition_id}")
async def get_competition(competition_id: str) -> Record:
    """One competition: its labels, its clubs and squads (public bio only, plus each player's appearances, minutes,
    ``played`` and ``qualified`` in this competition's matches; each club's ``uploaded_matches``), its uploaded matches
    with uploader and camera (each opens in the Clip view), its results and the sample (with ``words``). England semi-pro
    men's ``table`` is the Regista League's table; every other competition has ``table: null`` and ``results`` of its
    uploaded matches only (``results_note``). ``player_uploads``: finished Player-view uploads of this competition's
    clubs, named here and never counted in its numbers (``player_uploads_note``)."""
    e = _known_competition(competition_id)

    def run() -> Record:
        from regista.season.league import bio, club_by_id

        cm = catalogue_metrics()
        cp = catalogue_profiles("fixtures")
        comp = store.competition(competition_id, _index_path())
        clubs = club_by_id(comp)
        careers = {gid: [c for c, _p in cm.people.get(gid, []) if c != competition_id] for gid in cm.careers}
        squad_bio = ("age", "date_of_birth", "height_cm", "preferred_foot", "nationality")
        sm = cm.metrics[competition_id]
        matches = []
        for m in cp.matches(competition_id):
            matches.append({**m, "home_name": clubs[m["home"]]["name"], "away_name": clubs[m["away"]]["name"],
                            "uploader": _uploader_public(m.get("uploader"), comp)})
        club_matches = Counter(x for m in matches for x in (m["home"], m["away"]))

        def played(gid: str) -> Record:   # the league fixtures / uploaded matches only, as every catalogue number
            ps = sm.players.get(gid)
            mins = round(ps.minutes, 1) if ps else 0.0
            return {"appearances": ps.appearances if ps else 0, "minutes": mins, "played": bool(ps and ps.appearances),
                    "qualified": bool(ps) and ps.minutes >= sm.min_minutes}

        out_clubs = []
        for c in comp["clubs"]:
            squad = [{**{k: p.get(k) for k in ("global_id", "name", "kit_number", "position", "role", "starter")},
                      **{k: v for k, v in bio(p).items() if k in squad_bio},
                      "career": careers.get(p["global_id"]) or None, **played(p["global_id"])} for p in c.get("squad", [])]
            out_clubs.append({**{k: c.get(k) for k in ("club_id", "name", "short_name", "city", "ground", "kit")},
                              "uploaded_matches": club_matches.get(c["club_id"], 0), "squad": squad})
        results, note = cp.results(competition_id)
        s = cp.seasons[competition_id]
        level_pool = next((p for p in cm.pool_sizes("level") if competition_id in p["competitions"]), None)
        from regista.player_api import player_uploads

        return {**_comp_labels(e), "clubs": out_clubs, "matches": matches, "results": results, "results_note": note,
                "table": s.table if e.get("coverage") == "full" else None,
                "sample": {"matches_uploaded": len(matches), "club_matches": dict(sorted(club_matches.items())),
                           "qualifying_minutes": round(s.min_minutes, 1),
                           "note": "Per-90s and percentiles rest on the uploaded matches only." if note else s.sample()["note"],
                           "words": sample_words(cm, competition_id)},
                "level_pool": level_pool, "player_uploads": player_uploads(competition_id),
                "player_uploads_note": PLAYER_UPLOADS_NOTE, "noisy_words": NOISY_WORDS,
                "camera_note": CAMERA_NOTE, "warm": dict(WARM), "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


def _fits(cm: CatalogueMetrics, rows: list, key: str, scope: str, min_percentile: float | None) -> list:
    """``min_percentile``: the rows whose percentile in their own pool is at least it (none yet never has one)."""
    if min_percentile is None:
        return rows
    out = []
    for cid, ps in rows:
        pct = cm.percentile(cid, ps, key, scope)
        if pct is not None and pct >= min_percentile:
            out.append((cid, ps))
    return out


def _list_sort(cm: CatalogueMetrics, rows: list, sort: str, order: str | None) -> tuple[list, str, str | None]:
    """``sort=minutes``: by minutes played (most first; ``order=asc`` fewest), one board per level, as a total ranks;
    ``sort=name``: alphabetical (``order=desc`` reverses), one list with no places."""
    if sort == "name":
        rows = sorted(rows, key=lambda r: (r[1].info["name"], r[0]), reverse=order == "desc")
        return rows, "name", None
    sign = 1 if order == "asc" else -1
    rows = sorted(rows, key=lambda r: (sign * r[1].minutes, r[1].info["name"], r[0]))
    by = cm.board_by([cm.where_of(r) for r in rows], "value")
    return cm.group_boards(rows, by, cm.where_of), "value", by


def _tally(cm: CatalogueMetrics, boards: list[Record] | None, by: str | None, rows: list, key: str) -> None:
    """Each board's ``with_any`` / ``none_yet`` over every row of the list (ranked or not)."""
    if not boards or key not in COUNT_METRICS:
        return
    has = cm.any_of(key)
    tally: dict[str, list[int]] = {}
    for r in rows:
        t = tally.setdefault(cm.board_key(by, r[0], r[1].info["position"]), [0, 0])
        f = has(r)
        if f is True:
            t[0] += 1
        elif f is False:
            t[1] += 1
    for b in boards:
        b["with_any"], b["none_yet"] = tally.get(b["board"], [0, 0])


def _screen(cm: CatalogueMetrics, w: Where, scope: str, *, default_all: bool, metrics_raw, position, role, club, q,
            min_minutes, age_min, age_max, foot, camera, career, sort, order, limit, offset, rank_by=None,
            min_percentile=None, list_sorts: bool = False) -> Record:
    _check_ages(age_min, age_max)
    keys = _keys(metrics_raw, default=DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None]))
    by_list = list_sorts and sort in LIST_SORTS
    if by_list and (rank_by or min_percentile is not None):
        raise HTTPException(422, f"sort={sort} is not a metric: rank_by and min_percentile need a metric sort")
    sort_key = sort if by_list else (_key(sort) if sort else keys[0])
    cids, rows = _rows(cm, w, default_all=default_all, position=position, role=role, club=club, q=q,
                       min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot, camera=camera, career=career)
    if by_list:
        rows, mode, by = _list_sort(cm, rows, sort_key, order)
        # minutes: a place for every row with its competition's qualifying minutes, shared by the same whole minutes;
        # a name list has no places
        placed = [] if sort_key == "name" else [(cid, ps) for cid, ps in rows
                                                if ps.minutes >= cm.metrics[cid].min_minutes]
        places = _places(cm, placed, by, lambda cid, ps: round(ps.minutes))
    else:
        rows = _fits(cm, rows, sort_key, scope, min_percentile)
        rows, mode, by, by_pct = cm.order_rows(rows, sort_key, scope, order, rank_by)
        placed = _ranked_rows(cm, rows, sort_key, mode, by_pct)
        digits = CATALOGUE[sort_key].digits
        places = _places(cm, placed, by, lambda cid, ps: (cm.percentile(cid, ps, sort_key, scope),
                                                          round(ps.values[sort_key], digits))
                         if mode == "pool" else round(ps.values[sort_key], digits))
    place_of = {(cid, ps.info["global_id"]): n for (cid, ps), n in zip(placed, places)}

    def row_of(cid: str, ps) -> Record:
        return {**_card(cm, cid, ps), "board": cm.board_key(by, cid, ps.info["position"]),
                "rank": place_of.get((cid, ps.info["global_id"])),
                "values": {k: cm.cell(cid, ps.info["global_id"], k, scope) for k in keys}}

    boards = cm.boards(by, rows, cm.where_of, lambda i: row_of(*rows[i]), limit,
                       any_of=None if by_list else cm.any_of(sort_key))
    split = cm.count_split(rows, sort_key) if not by_list else {"with_any": None, "none_yet": None}
    return {"columns": [_describe(cm, k, cids, scope) for k in keys], "scope": scope, "sort": sort_key, "order": order,
            "rank_by": mode, "rank_rule": RANK_RULE, "boards": boards, **split,
            "total": len(rows), "offset": offset, "limit": limit,
            "players": [row_of(cid, ps) for cid, ps in rows[offset:offset + limit]],
            "competitions": cids, "pools": _pools_of(cm, cids, scope), "pool_rule": POOL_RULE,
            "samples": {cid: _sample(cm, cid) for cid in cids},
            "reliability_note": RELIABILITY_NOTE, "warning": _warning(cm, cids, scope), "filters": w.public(),
            "min_percentile": min_percentile, "none_yet_rule": NONE_YET_RULE, "noisy_words": NOISY_WORDS,
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
                            position: POSITIONS = None, role: ROLE = None, club: CLUB = None, q: NAME_Q = None,
                            min_minutes: MIN_MINUTES = None, age_min: AGE = None, age_max: AGE = None, foot: FOOT = None,
                            camera: CAMERA = None, career: bool | None = None,
                            sort: Annotated[str | None, Query(pattern=KEY_PATTERN)] = None,
                            order: Literal["asc", "desc"] | None = None, rank_by: RANK_BY = None,
                            min_percentile: MIN_PERCENTILE = None,
                            limit: int = Query(50, ge=1, le=200),
                            offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """The cross-country screen: one row per player and competition (a career player has two), each cell with its pool
    and sample. Percentiles in ``scope`` (level by default). ``min_minutes`` defaults to each row's own competition's
    qualifying minutes; ``camera`` keeps players with an appearance in a match filmed on that camera type; ``career=true``
    only players in two competitions. Ranked as ``RANK_RULE`` says: percentiles are compared only within one position and
    raw numbers only within one level, so rows from more than one level that hold one position are sorted by each row's
    percentile within its own pool (one board per gender), and rows from more than one level and more than one position
    by value within each level (one board per level); ``rank_by`` forces a mode; ``boards`` gives each board's key,
    label, size, offset and top rows. ``order`` "desc" lists the largest numbers first in value mode and, in pool mode,
    the rows highest in their own pool in the raw direction (largest relative to the pool, not the largest numbers).
    Paged by ``offset`` and ``limit`` (``total`` counts every row).

    A count at 0 is none yet (``none_yet_rule``): no percentile, listed after the ranked rows; ``with_any`` and
    ``none_yet`` (top level and per board) count the rows with any and with none. ``min_percentile`` keeps the rows whose
    percentile in their own pool (``scope``) is at least it. ``sort=minutes`` ranks minutes played by value, one board
    per level; ``sort=name`` is alphabetical with no places (``rank_by: name``)."""

    def run() -> Record:
        return _screen(catalogue_metrics(), w, scope or "level", default_all=True, metrics_raw=metrics_, position=position,
                       role=role, club=club, q=q, min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot,
                       camera=camera, career=career, sort=sort, order=order, limit=limit, offset=offset, rank_by=rank_by,
                       min_percentile=min_percentile, list_sorts=True)

    return await run_in_threadpool(run)


@router.get("/api/catalogue/directory")
async def catalogue_directory() -> Record:
    """Every player-competition row of the catalogue once, by name: who they are and where they play (the cards of
    ``/api/catalogue/players`` without any metric cell, pool or sample), for a name search. ``total`` counts them;
    ``qualifying_minutes`` gives each competition's minutes for a percentile. One read instead of paging the screen;
    nothing here is ranked."""

    def run() -> Record:
        cm = catalogue_metrics()
        _cids, rows = _rows(cm, Where(), default_all=True, min_minutes=0)
        rows, _mode, _by = _list_sort(cm, rows, "name", None)
        return {"players": [_card(cm, cid, ps) for cid, ps in rows], "total": len(rows),
                "qualifying_minutes": {cid: round(cm.metrics[cid].min_minutes, 1) for cid in cm.order},
                "synthetic": True, "note": SYNTHETIC_NOTE}

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
                           moments: int = Query(20, ge=0, le=40),
                           include: Annotated[str | None, Query(pattern="^profile$")] = None) -> Record:
    """The player across the catalogue: bio, the career (every competition, even with 0 minutes), what adds up (no merged
    per-90), and per competition the metrics (default: the position's core set) with their pools, the touch map, the
    competition's summary; the best moments across competitions. ``evidence=KEY`` returns one number's evidence
    instead (``competition=`` picks the row, default the one with the most minutes; paged by ``evidence_offset``).

    Every number counts each competition's own uploaded matches; England's the Regista League's fixtures only
    (``FIXTURES_BASIS``). Matches the player uploaded through the Player view, or that a confirmed claim adds to the
    league profile, are named in each row's ``not_counted`` and never counted; ``basis`` says so in one sentence.
    ``include=profile`` adds each row's ``profile`` in the profile page's shape (``regista.catalogue.page``), in
    ``scope``: counts, per-90s, percentiles with their pools in plain words, none yet, ratios from the metrics engine,
    evidence, matches with uploader and camera, touch map, ``moments`` moments and the summary."""
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
        from regista.catalogue.page import profile_row, summary_row, with_clock

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
        cp = catalogue_profiles("fixtures")
        uncounted = not_counted(gid)
        for row in out["rows"]:
            cid = row["competition_id"]
            row["touch_map"] = cp.touch_map(cid, gid)
            row["summary"] = summary_row(cm, cp, cid, gid)
            row["also_in"] = [c for c, _p in cm.people[gid] if c != cid]
            row["not_counted"] = [u for u in uncounted if u["competition_id"] == cid]
            row["basis"] = basis_sentence(cm, cid, gid, row["not_counted"])
            row["sample"]["words"] = cm.sample_words(cid)
            if include == "profile":
                comp = store.competition(cid, _index_path())
                row["profile"] = profile_row(cm, cp, cid, gid, sc, moments=40, matches=cp.matches(cid),
                                             uploader=lambda up, comp=comp: _uploader_public(up, comp))
        out["moments"] = with_clock(cm, cp.moments(gid, limit=moments)) if moments else []
        out["profile_url"] = f"/players/{gid}"
        out["not_counted"] = uncounted
        out["summary_note"] = ("Each row's summary is written from that competition's own matches (England: the Regista "
                               "League's fixtures only), ranks among the competition's players with enough minutes; "
                               "engine says whether Regista's rules or a Foundry model wrote it (a stored Foundry summary "
                               "is shown only while its numbers still hold).")
        out["basis"] = FIXTURES_BASIS
        return out

    return await run_in_threadpool(run)


def not_counted(gid: str) -> list[Record]:
    """The player's matches the catalogue names but never counts: finished Player-view uploads (any competition) and,
    for England, confirmed claims and uploads the league profile counts. Each: match_id, competition_id, date, opponent,
    source (upload or claim), title, and the Clip view link."""
    from regista.player_api import player_uploads
    from regista.season_api import season as league_season

    out: list[Record] = []
    seen: set[str] = set()
    for u in player_uploads(global_id=gid):
        seen.add(u["match_id"])
        out.append({"match_id": u["match_id"], "competition_id": u["competition_id"], "date": u["date"],
                    "opponent": u["opponent"], "source": "upload", "kind": u["kind"], "title": u["title"],
                    "camera": u["camera"], "clip_view": u["clip_view"]})
    try:
        s = league_season()
    except HTTPException:
        return out
    p = s.player(gid)
    if p:
        titles = {m["match_id"]: m.get("title") for m in [*s.uploaded, *s.claimed]}
        for m in p["matches"]:
            if m.get("source") in ("claim", "upload") and m["match_id"] not in seen:
                seen.add(m["match_id"])
                out.append({"match_id": m["match_id"], "competition_id": ENGLAND_ID, "date": m.get("date"),
                            "opponent": m.get("opponent"), "source": m["source"], "kind": "friendly",
                            "title": titles.get(m["match_id"]), "camera": None,
                            "clip_view": f"/?match={m['match_id']}&player={m['player_id']}"})
    return out


def basis_sentence(cm: CatalogueMetrics, cid: str, gid: str, uncounted: list[Record]) -> str:
    """One plain sentence: what this row's numbers count, and which of the player's matches they leave out."""
    ps = cm.metrics[cid].players.get(gid)
    n = ps.appearances if ps else 0
    what = (f"the {cm.labels[cid]['name']} fixtures only" if cm.labels[cid]["coverage"] == "full"
            else f"{cm.labels[cid]['name']}'s uploaded matches only")
    out = f"These numbers count {what} ({n} match{'es' if n != 1 else ''})."
    if uncounted:
        name = cm.people[gid][0][1]["name"]
        parts = []
        for u in uncounted:
            kind = "friendly" if u.get("kind") == "friendly" else "match"
            via = "uploaded through the Player view" if u["source"] == "upload" else "added by a confirmed claim"
            parts.append(f"{kind} v {u['opponent']}, {via}" if u.get("opponent") else f"{kind}, {via}")
        out += f" {name}'s {'; '.join(parts)}, {'is' if len(parts) == 1 else 'are'} not counted here."
    return out


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


def _places(cm: CatalogueMetrics, ranked: list, by: str | None, shown: Any) -> list[int]:
    """The place of each ranked row, in order: each board ranks from 1, and rows showing the same number
    (``shown(cid, ps)``: the rounded value, or in pool mode the percentile and the value) share a place (1, 2, 2, 4)."""
    places, prev, place, board, n_in_board = [], None, 0, None, 0
    for cid, ps in ranked:
        g = cm.board_key(by, cid, ps.info["position"])
        if g != board:   # each board ranks from 1
            board, n_in_board, prev = g, 0, None
        n_in_board += 1
        tie = shown(cid, ps)
        if tie != prev:
            place, prev = n_in_board, tie
        places.append(place)
    return places


def _ranked_rows(cm: CatalogueMetrics, rows: list, key: str, mode: str, by_pct: set) -> list:
    """The rows that get a place, in order (``RANK_RULE``): pool mode, the rows ranked by percentile; value mode, the rows
    with their competition's minimum minutes (and attempts), never none yet (a count at 0)."""
    m = CATALOGUE[key]
    if mode == "pool":
        return [(cid, ps) for cid, ps in rows if (cid, ps.info["global_id"]) in by_pct]
    return [(cid, ps) for cid, ps in rows
            if (cm.metrics[cid].qualified(ps, m) or (m.kind == "total" and ps.values.get(key) is not None))
            and not cm.none_yet(ps, key)]


def _rank(cm: CatalogueMetrics, w: Where, scope: str, *, default_all: bool, metric: str, position, role, club,
          min_minutes, age_min, age_max, foot, camera, career, order, limit, offset, rank_by=None,
          min_percentile=None) -> Record:
    _check_ages(age_min, age_max)
    key = _key(metric)
    m = CATALOGUE[key]
    cids, rows = _rows(cm, w, default_all=default_all, position=position, role=role, club=club, min_minutes=min_minutes,
                       age_min=age_min, age_max=age_max, foot=foot, camera=camera, career=career)
    rows = _fits(cm, rows, key, scope, min_percentile)
    rows, mode, by, by_pct = cm.order_rows(rows, key, scope, order, rank_by)
    ranked = _ranked_rows(cm, rows, key, mode, by_pct)   # none yet (a count at 0) gets no place
    ranked_ids = {(cid, ps.info["global_id"]) for cid, ps in ranked}
    rest = [(cid, ps) for cid, ps in rows if (cid, ps.info["global_id"]) not in ranked_ids]
    places = _places(cm, ranked, by, lambda cid, ps: (cm.percentile(cid, ps, key, scope), round(ps.values[key], m.digits))
                     if mode == "pool" else round(ps.values[key], m.digits))

    def row_of(i: int) -> Record:
        cid, ps = ranked[i]
        return {"rank": places[i], "board": cm.board_key(by, cid, ps.info["position"]), **_card(cm, cid, ps),
                **cm.cell(cid, ps.info["global_id"], key, scope),
                "evidence_count": sum(len(ps.evidence.get(k, [])) for k in m.evidence_keys())}

    out = [row_of(i) for i in range(offset, min(offset + limit, len(ranked)))]
    # each board's size, where it starts among the ranked rows (page there with offset), and its top rows; with_any
    # and none_yet count every row of the board, ranked or not
    boards = cm.boards(by, ranked, cm.where_of, row_of, limit, any_of=cm.any_of(key))
    _tally(cm, boards, by, rows, key)
    return {"metric": _describe(cm, key, cids, scope), "scope": scope, "rank_by": mode, "rank_rule": RANK_RULE,
            "boards": boards, "players": out, "ranked": len(ranked), "offset": offset, "limit": limit,
            **cm.count_split(rows, key), "min_percentile": min_percentile, "none_yet_rule": NONE_YET_RULE,
            "unranked": [{**_card(cm, cid, ps), "board": cm.board_key(by, cid, ps.info["position"]),
                          **cm.cell(cid, ps.info["global_id"], key, scope)}
                         for cid, ps in rest[:limit]],
            "competitions": cids, "pool_rule": POOL_RULE, "warning": _warning(cm, cids, scope), "filters": w.public(),
            "synthetic": True, "note": SYNTHETIC_NOTE}


@router.get("/api/catalogue/rank")
async def catalogue_rank(metric: Annotated[str, Query(pattern=KEY_PATTERN)], w: WhereDep, scope: ScopeDep,
                         position: POSITIONS = None, role: ROLE = None, club: CLUB = None, min_minutes: MIN_MINUTES = None,
                         age_min: AGE = None, age_max: AGE = None, foot: FOOT = None, camera: CAMERA = None,
                         career: bool | None = None, order: Literal["asc", "desc"] | None = None,
                         rank_by: RANK_BY = None, min_percentile: MIN_PERCENTILE = None,
                         limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """One metric's leaderboard across the filtered catalogue, ranked as ``RANK_RULE`` says. Percentiles are compared only
    within one position and raw numbers only within one level: rows from more than one level that hold one position are
    ranked by each row's percentile within its own pool (best first; ties by pool size, minutes, then value), one board
    per gender; rows from more than one level and more than one position by value within each level, one board per
    level ("most goals in England" puts the semi-pro men's top scorer first, not a defender high among defenders); one
    level by value. ``rank_by`` forces a mode. ``order`` "desc" lists the largest numbers first in value mode (even where
    lower is better) and, in pool mode, the rows highest in their own pool in the raw direction: the largest numbers
    relative to each row's pool, not the largest numbers. Each row's ``board``; ranks restart at 1 on each board;
    ``boards`` gives each board's key, label, size, its ``offset`` among the ranked rows and its ``top`` rows, so every
    board is on every page. Rows without a percentile (pool rank) or without their competition's minimum attempts (value
    rank) are listed after, unranked, and so is none yet (a count at 0, ``none_yet_rule``); ``with_any`` and
    ``none_yet`` (top level and per board) count every row. ``min_percentile`` keeps the rows whose percentile in their
    own pool is at least it: "fits" for a team need, the engine's answer."""

    def run() -> Record:
        return _rank(catalogue_metrics(), w, scope or "level", default_all=True, metric=metric, position=position,
                     role=role, club=club, min_minutes=min_minutes, age_min=age_min, age_max=age_max, foot=foot,
                     camera=camera, career=career, order=order, limit=limit, offset=offset, rank_by=rank_by,
                     min_percentile=min_percentile)

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
        players = [{**_card(cm, cid, ps), "values": {k: cm.cell(cid, ps.info["global_id"], k, sc) for k in keys}}
                   for cid, ps in chosen]
        best, rules = {}, {}
        for k in keys:
            best[k], rules[k] = compare_best(cm, chosen, players, k)
        return {"players": players,
                "columns": [_describe(cm, k, cids, sc) for k in keys],
                "scope": sc, "same_pool": same,
                "warning": None if same else "different pools (level or position): read each percentile against its own pool",
                "best": best, "best_rule": rules, "best_rules": BEST_RULES,
                "pool_rule": POOL_RULE, "synthetic": True, "note": SYNTHETIC_NOTE}

    return await run_in_threadpool(run)


BEST_RULES = ("best marks the strongest number of each metric, one rule for every page: players from one level, the best "
              "value as shown (ties share the mark; lower is better where the metric says so); from more than one level "
              "but one position, the best percentile, each in its own pool; from more than one level and more than one "
              "position, no mark (neither raw numbers nor percentiles compare). Never a style marker, a row without a "
              "value or percentile, or none yet.")


def compare_best(cm: CatalogueMetrics, chosen: list, players: list[Record], key: str) -> tuple[list[str], Record]:
    """(the global ids marked best on ``key``, the rule used and why) for compare (``BEST_RULES``)."""
    m = CATALOGUE[key]
    if m.higher_is_better is None:
        return [], {"by": None, "reason": "a style marker: described, never judged"}
    levels = {cm.level[cid] for cid, _ps in chosen}
    positions = {ps.info["position"] for _cid, ps in chosen}
    cells = [(p["global_id"], p["values"][key]) for p in players]
    cells = [(g, c) for g, c in cells if not c.get("none_yet")]
    if len(levels) == 1:
        have = [(g, c["value"]) for g, c in cells if c["value"] is not None]
        if not have:
            return [], {"by": "value", "reason": "no value to compare"}
        top = (min if m.higher_is_better is False else max)(v for _g, v in have)
        return [g for g, v in have if v == top], {"by": "value", "reason": "one level: the best value as shown"}
    if len(positions) == 1:
        have = [(g, c["percentile"]) for g, c in cells if c["percentile"] is not None]
        if not have:
            return [], {"by": "percentile", "reason": "no percentile to compare"}
        top = max(v for _g, v in have)
        return [g for g, v in have if v == top], {"by": "percentile",
                                                  "reason": "more than one level, one position: the best percentile, "
                                                            "each in its own pool"}
    return [], {"by": None, "reason": "more than one level and more than one position: no mark"}


@router.get("/api/catalogue/matches")
async def catalogue_matches(w: WhereDep, club: Annotated[str | None, Query(pattern=CLUB_PATTERN)] = None,
                            camera: CAMERA = None, uploader_type: UPLOADER_TYPE = None,
                            limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=MAX_OFFSET)) -> Record:
    """Uploaded matches across the catalogue, in the index's competition order then date: each with its competition,
    score, uploader (team or player, named) and camera, and its Clip view link. Paged by ``offset`` and ``limit``."""

    def run() -> Record:
        from regista.season.league import club_by_id

        catalogue_metrics()
        cp = catalogue_profiles("fixtures")
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
    ``table`` is its uploaded matches' results (``table_note``); ``rounds`` lists the rounds with uploads."""
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

    Ranked as ``RANK_RULE`` says, like ``/api/catalogue/players``. Cards from more than one level that hold one position,
    sorted by a per-90 stat or a ratio, are ranked by each card's percentile in ``scope`` (highest first, then pools that
    are not small, then more minutes, then the value; cards without a percentile follow, by value), one board per gender;
    a ratio's percentile needs its competition's minimum attempts (``CatalogueProfiles.min_attempts``). Cards from more
    than one level and more than one position, and every ``minutes`` or ``name`` sort, are ranked by value within each
    level, one board per level; one level by value. By value, a per-90 or ratio sort lists the cards with their
    competition's qualifying minutes first (a substitute's goal in ten minutes does not top "most goals"). ``rank_by`` forces a mode. ``boards`` (one shape on every surface:
    ``CatalogueMetrics.boards``) gives each board's key, label, size, offset and top cards."""
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
    items = [(cid, p["position"]) for cid, p in found]
    mode = cm.choose_mode(items, rateable, rank_by)
    if mode == "pool":
        pct = {(cid, p["global_id"]): cp.sort_percentile(cid, p["global_id"], sort, scope) for cid, p in found}
        have = [r for r in found if pct[(r[0], r[1]["global_id"])][0] is not None]
        none = [r for r in found if pct[(r[0], r[1]["global_id"])][0] is None]
        have.sort(key=lambda r: (-pct[(r[0], r[1]["global_id"])][0], pct[(r[0], r[1]["global_id"])][1], -r[1]["minutes"],
                                 _sort_key(r[1], sort), r[0]))
        found = have + none
    elif rateable:   # by value: cards with their competition's qualifying minutes first, as the terminal ranks
        found = [r for r in found if cp._qualified(*r)] + [r for r in found if not cp._qualified(*r)]

    def where(r: tuple[str, Record]) -> tuple[str, str]:
        return r[0], r[1]["position"]

    by = cm.board_by(items, mode)
    found = cm.group_boards(found, by, where)

    def card_of(cid: str, p: Record) -> Record:
        c = card(p)
        for stat, h in c["headline"].items():
            sc = cp.stat_cell(cid, p["global_id"], stat, scope)
            h["percentile"], h["pool"] = sc["percentile"], sc["pool"]
        return {**c, **cm.labels_of(cid), "board": cm.board_key(by, cid, p["position"]),
                "career": len(cm.people.get(p["global_id"], [])) > 1,
                "profile_url": f"/players/{p['global_id']}",
                "api_url": f"/api/catalogue/players/{p['global_id']}"}

    rows = [card_of(cid, p) for cid, p in found[offset:offset + limit]]
    boards = cm.boards(by, found, where, lambda i: card_of(*found[i]), limit)
    return {"players": rows, "total": len(found), "offset": offset, "sort": sort, "stats": stats, "scope": scope,
            "rank_by": mode, "rank_rule": RANK_RULE, "boards": boards, "competitions": cids, "filters": w.public(),
            "pool_rule": POOL_RULE, "warning": _warning(cm, cids, scope),
            "basis": ENGLAND_BASIS if ENGLAND_ID in cids else None, "synthetic": True, "note": SYNTHETIC_NOTE}


TERMINAL_RANK_KEYS = ("rank_by", "rank_rule", "boards")   # added in catalogue mode only: how the rows were ranked


def screen_payload(w: Where, scope: str, **kw: Any) -> Record:
    """``/api/terminal/screen`` with catalogue parameters: today's keys (``columns``, ``sort``, ``total``, ``offset``,
    ``players``, ``season``), every cell with its pool and sample, plus how the rows were ranked (``rank_by``,
    ``rank_rule``, ``boards``: ``RANK_RULE``)."""
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
    from regista.catalogue.metrics import strength_words

    cm, cid, ps = player_row(gid, competition)
    sim = cm.similar(cid, gid, scope, n)
    for row in sim["similar"]:
        row["api_url"] = f"/api/catalogue/players/{row['global_id']}"
        row["profile_url"] = f"/players/{row['global_id']}"
        row["shared_strengths_words"] = [strength_words(k) for k in row.get("shared_strengths", [])]
    return {**_card(cm, cid, ps), **sim, "rule": rule, "sources": ["FB-SR"], "synthetic": True, "note": SYNTHETIC_NOTE}


def player_shots_payload(gid: str, competition: str | None, pitch: Record) -> Record:
    cm, cid, ps = player_row(gid, competition)
    shots = cm.metrics[cid].player_shots(gid)
    return {**_card(cm, cid, ps), "shots": shots, "total": len(shots), "penalties": sum(1 for s in shots if s["penalty"]),
            "goals": sum(1 for s in shots if s["outcome"] == "goal"), "pitch": pitch, "synthetic": True, "note": SYNTHETIC_NOTE}


def player_heatmap_payload(gid: str, competition: str | None, pitch: Record) -> Record:
    cm, cid, ps = player_row(gid, competition)
    grid = catalogue_profiles("fixtures").touch_map(cid, gid)
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
