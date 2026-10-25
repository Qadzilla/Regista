"""The catalogue's profiles side: per competition, the ``Season`` (``regista.season.profiles``) that gives each player's
labelled moments, touch map and match list, and each competition's uploaded matches and results.

The metrics side (``regista.catalogue.metrics``) holds the numbers and their pools; this holds what a profile shows beside
them. England semi-pro men is the Regista League's fixtures (``Season.build`` on ``league.json``: no claims or Player-view
uploads in the catalogue view, so its moments sit beside its fixture-only metrics); every other competition is
``Season.build(comp, root, min_minutes_floor=45, min_pool=5)``, the same rules as its metrics.

A sparse competition's results are its uploaded matches only, never a league table (``results_note``).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from regista.catalogue import store
from regista.catalogue.metrics import FLOOR, MIN_POOL
from regista.catalogue.taxonomy import ENGLAND_ID
from regista.season.profiles import Season

Record = dict[str, Any]

RESULTS_NOTE = "uploaded matches only, not a league table"
MOMENTS_KEPT = 40


class CatalogueProfiles:
    def __init__(self, index: Record, seasons: dict[str, Season]):
        self.index = index
        self.seasons = seasons
        self.order = [e["competition_id"] for e in index["competitions"] if e["competition_id"] in seasons]
        self.coverage = {e["competition_id"]: e.get("coverage") for e in index["competitions"]}
        self.england_uploads = next((e.get("uploads", {}) for e in index["competitions"]
                                     if e["competition_id"] == ENGLAND_ID), {})

    def competitions_of(self, gid: str) -> list[str]:
        return [cid for cid in self.order if gid in self.seasons[cid].profiles]

    def moments(self, gid: str, limit: int = MOMENTS_KEPT) -> list[Record]:
        """The player's best labelled moments across every competition, most watchable first, each with its competition."""
        out = []
        for cid in self.competitions_of(gid):
            for m in self.seasons[cid].profiles[gid]["moments"]:
                out.append({**m, "competition_id": cid})
        out.sort(key=lambda r: (-r["watchability"], r["competition_id"], r["round"] or 0, r["t"]))
        return out[:limit]

    def touch_map(self, cid: str, gid: str) -> list[list[int]] | None:
        """The player's touches in that competition's matches (12 x 8, attacking left to right)."""
        s = self.seasons.get(cid)
        return s.league_grids.get(gid) if s else None

    def matches(self, cid: str) -> list[Record]:
        """The competition's uploaded matches with their uploader and camera (England: all 30 fixtures, from the overlay)."""
        s = self.seasons[cid]
        comp = s.league
        fx = {f["match_id"]: f for f in comp["fixtures"]}
        out = []
        for m in s.matches:
            up = fx[m["match_id"]] if "camera" in fx[m["match_id"]] else self.england_uploads.get(m["match_id"], {})
            out.append({**m, "uploader": up.get("uploader"), "camera": up.get("camera"),
                        "clip_view": f"/?match={m['match_id']}"})
        return out

    def results(self, cid: str) -> tuple[list[Record], str | None]:
        """(rows, note): England's league table as today, or a sparse competition's results of uploaded matches."""
        s = self.seasons[cid]
        if self.coverage.get(cid) == "full":
            return s.table, None
        rows = [{k: r[k] for k in ("club_id", "club", "short_name", "played", "won", "drawn", "lost", "goals_for",
                                   "goals_against")} for r in s.table]
        rows.sort(key=lambda r: (-r["played"], r["club"]))
        return rows, RESULTS_NOTE


def build_catalogue_profiles(index_path: Path | str | None = None, root: Path | str | None = None,
                             league_path: Path | str | None = None, season_root: Path | str | None = None) -> CatalogueProfiles:
    """Every competition's ``Season``. The catalogue's matches are built first with their own manifests
    (``regista.catalogue.build``), so ``Season.build`` finds every folder current and only reads."""
    from regista.catalogue.build import build_catalogue
    from regista.season.league import load_league

    index_path = Path(index_path) if index_path else store.index_path()
    root = Path(root) if root else store.matches_root()
    league_path = Path(league_path) if league_path else store.competition_path(store.entry(ENGLAND_ID, index_path), index_path)
    season_root = Path(season_root or os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    comps = store.new_competitions(index_path)
    build_catalogue(comps, root)
    seasons = {ENGLAND_ID: Season.build(load_league(league_path), season_root)}
    for comp in comps:
        seasons[comp["competition"]["competition_id"]] = Season.build(comp, root, min_minutes_floor=FLOOR, min_pool=MIN_POOL)
    return CatalogueProfiles(store.load_index(index_path), seasons)


_cache: dict[tuple, CatalogueProfiles] = {}
_lock = threading.Lock()


def load_catalogue_profiles(index_path: Path | str | None = None, root: Path | str | None = None,
                            league_path: Path | str | None = None, season_root: Path | str | None = None) -> CatalogueProfiles:
    index_path = Path(index_path) if index_path else store.index_path()
    root = Path(root) if root else store.matches_root()
    league_path = Path(league_path) if league_path else store.competition_path(store.entry(ENGLAND_ID, index_path), index_path)
    season_root = Path(season_root or os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    files = [index_path, league_path] + [store.competition_path(e, index_path) for e in store.entries(index_path)
                                         if e["source"] == "catalogue"]
    key = (str(root.resolve()), str(season_root.resolve()), tuple(str(f.resolve()) for f in files),
           tuple(f.stat().st_mtime_ns for f in files))
    with _lock:
        hit = _cache.get(key)
        if hit is None:
            hit = build_catalogue_profiles(index_path, root, league_path, season_root)
            _cache.clear()
            _cache[key] = hit
        return hit


def invalidate() -> None:
    with _lock:
        _cache.clear()
