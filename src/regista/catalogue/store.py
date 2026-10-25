"""Read the committed catalogue: the index, each competition as a league-shaped dict, and a match by id.

A competition file has ``league.json``'s shape (``league``, ``season``, ``generator``, ``clubs`` with ``squad``,
``fixtures``), so ``regista.season.league.generate_kwargs``, ``regista.season.build.materialise``, ``Season.build`` and
``SeasonMetrics.from_streams`` take it as it is. The England semi-pro men competition is ``league.json`` itself, found
through ``REGISTA_SEASON`` when that is set (tests, the Docker image), so the catalogue never holds a second copy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from regista.catalogue.taxonomy import ENGLAND_ID

Record = dict[str, Any]

DEFAULT_INDEX = Path("data/catalogue/catalogue.json")
DEFAULT_ROOT = Path("data/catalogue/matches")


def index_path() -> Path:
    return Path(os.environ.get("REGISTA_CATALOGUE", str(DEFAULT_INDEX)))


def matches_root() -> Path:
    return Path(os.environ.get("REGISTA_CATALOGUE_ROOT", str(DEFAULT_ROOT)))


def repo_root(index: Path | str) -> Path:
    """Paths in the index are relative to the repository root: the index file's parent's parent's parent."""
    return Path(index).resolve().parent.parent.parent


_cache: dict[str, tuple[int, Any]] = {}


def _read(path: Path) -> Any:
    mtime = path.stat().st_mtime_ns
    hit = _cache.get(str(path))
    if hit is None or hit[0] != mtime:
        hit = (mtime, json.loads(path.read_text()))
        _cache[str(path)] = hit
    return hit[1]


def load_index(path: Path | str | None = None) -> Record:
    return _read(Path(path) if path else index_path())


def competition_path(entry: Record, index: Path | str | None = None) -> Path:
    if entry["source"] == "league" and os.environ.get("REGISTA_SEASON"):
        return Path(os.environ["REGISTA_SEASON"])
    return repo_root(index or index_path()) / entry["path"]


def entries(index: Path | str | None = None) -> list[Record]:
    return load_index(index)["competitions"]


def entry(competition_id: str, index: Path | str | None = None) -> Record | None:
    return next((e for e in entries(index) if e["competition_id"] == competition_id), None)


def competition(competition_id: str, index: Path | str | None = None) -> Record | None:
    """The league-shaped dict of one competition (England: league.json as it is), or None."""
    e = entry(competition_id, index)
    return _read(competition_path(e, index)) if e else None


def new_competitions(index: Path | str | None = None) -> list[Record]:
    """The 13 catalogue competitions (league-shaped), in the index's order; England is not among them."""
    return [_read(competition_path(e, index)) for e in entries(index) if e["source"] == "catalogue"]


def resolve_match(match_id: str, index: Path | str | None = None) -> tuple[Record, Record] | None:
    """(competition, fixture) of a catalogue match (``cm_…``), or None."""
    if not match_id.startswith("cm_"):
        return None
    try:
        comps = new_competitions(index)
    except (OSError, ValueError):
        return None
    for comp in comps:
        for fx in comp["fixtures"]:
            if fx["match_id"] == match_id:
                return comp, fx
    return None


def england_upload(match_id: str, index: Path | str | None = None) -> Record | None:
    """Uploader and camera of a Regista League fixture (the overlay in the index)."""
    e = entry(ENGLAND_ID, index)
    return (e or {}).get("uploads", {}).get(match_id)
