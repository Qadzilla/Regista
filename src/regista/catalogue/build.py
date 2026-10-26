"""Regenerate every catalogue match from its competition file into ``data/catalogue/matches/<match_id>/``.

The same folders as the Regista League's (``regista.season.build``): ``events.jsonl``, ``clips.jsonl``, ``manifest.json``,
and ``tracks.jsonl`` only when video needs it (``ensure_tracks``). The manifest adds the catalogue's labels
(``collection: catalogue``, competition, country, level, uploader, camera). Matches are deterministic (league mode takes
its transcendental functions from ``regista.detmath``) and pinned (``regista.catalogue.pins``).

``build_catalogue`` runs one spawn-context process pool over every stale match of every competition, so a script that
calls it must guard its entry point with ``if __name__ == "__main__":``. England stays ``regista.season.build.build_all``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from regista.catalogue import store
from regista.season import build as season_build
from regista.season.league import club_by_id

Record = dict[str, Any]
_lock = threading.Lock()
log = logging.getLogger(__name__)
LABEL_KEYS = ("competition_id", "country", "region", "tier", "age_group", "gender")


def manifest_extra(comp: Record, fixture: Record) -> Record:
    """The catalogue's keys in a match manifest."""
    labels = comp["competition"]
    return {"collection": "catalogue", "competition": comp["league"], **{k: labels[k] for k in LABEL_KEYS},
            "uploader": fixture["uploader"], "camera": fixture["camera"],
            "subtitle": f"{comp['league']} ({labels['country']}) {comp['season']}, round {fixture['round']}: a synthetic "
                        "uploaded match, thirty generated minutes, every player's moments cut and labelled. The camera "
                        "type is a label: every match is rendered the same way."}


def title(comp: Record, fixture: Record, score: dict[str, int]) -> str:
    """The league's form, "Round N: Home h–a Away": a competition's own round number, never "matchday" (the competition's
    name is in the manifest's ``competition``)."""
    clubs = club_by_id(comp)
    h, a = clubs[fixture["home"]], clubs[fixture["away"]]
    return f"Round {fixture['round']}: {h['name']} {score.get('t_home', 0)}–{score.get('t_away', 0)} {a['name']}"


def _labels_current(comp: Record, fixture: Record, root: Path) -> bool:
    """The folder's manifest carries this fixture's catalogue labels (uploader and camera are not in the fingerprint)."""
    try:
        m = json.loads((root / fixture["match_id"] / "manifest.json").read_text())
    except (OSError, ValueError):
        return True   # nothing built yet: materialise decides
    want = manifest_extra(comp, fixture)
    return all(m.get(k) == v for k, v in want.items()) and m.get("title", "").startswith(f"Round {fixture['round']}: ")


def materialise_match(comp: Record, fixture: Record, root: Path | str) -> Path:
    """One catalogue match's folder, generated now if missing or stale."""
    root = Path(root)
    if not _labels_current(comp, fixture, root):
        with season_build.match_lock(fixture["match_id"]):   # never under a thread that is building this folder
            if not _labels_current(comp, fixture, root):
                shutil.rmtree(root / fixture["match_id"], ignore_errors=True)
    return season_build.materialise(comp, fixture, root, manifest_extra=manifest_extra(comp, fixture), title_fn=title)


def ensure_tracks(comp: Record, fixture: Record, root: Path | str) -> Path:
    materialise_match(comp, fixture, root)
    return season_build.ensure_tracks(comp, fixture, root, manifest_extra=manifest_extra(comp, fixture), title_fn=title)


def is_current(comp: Record, fixture: Record, root: Path) -> bool:
    return season_build.is_current(comp, fixture, root) and _labels_current(comp, fixture, root)


def _one(args: tuple[Record, Record, str]) -> str:
    comp, fixture, root = args
    return str(materialise_match(comp, fixture, root))


def build_catalogue(comps: list[Record] | None = None, root: Path | str | None = None, workers: int | None = None) -> list[Path]:
    """Every catalogue match's folder (default: the committed competitions into ``REGISTA_CATALOGUE_ROOT``). Stale ones
    are generated in one pool of spawned processes; ``workers`` 1 builds them here, one by one."""
    comps = store.new_competitions() if comps is None else comps
    root = Path(root) if root is not None else store.matches_root()
    with _lock:
        jobs = [(c, f) for c in comps for f in c["fixtures"] if not is_current(c, f, root)]
        n = min(len(jobs), workers or os.cpu_count() or 1)
        if n > 1:
            from concurrent.futures import ProcessPoolExecutor
            import multiprocessing

            root.mkdir(parents=True, exist_ok=True)
            try:
                with ProcessPoolExecutor(max_workers=n, mp_context=multiprocessing.get_context("spawn")) as pool:
                    list(pool.map(_one, [(c, f, str(root)) for c, f in jobs]))
            except Exception:  # noqa: BLE001 - no worker processes here (an interactive or piped __main__): built below
                log.warning("catalogue build: the process pool failed, building %d matches here, one by one", len(jobs),
                            exc_info=True)
        return [materialise_match(c, f, root) for c in comps for f in c["fixtures"]]
