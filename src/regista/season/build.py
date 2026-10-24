"""Regenerate the league's matches from ``league.json`` into match folders the rest of Regista reads.

Each match folder looks like a committed sample: ``events.jsonl``, ``clips.jsonl`` (the clips of every player who played,
labelled by the rules labeller) and ``manifest.json`` (title, round, ``collection: season``). ``tracks.jsonl`` (about 17 MB for a
30-minute match) is written only when something needs positions, such as video (``ensure_tracks``); profiles need only
the events. A folder is written
into a temporary name and renamed into place, so a reader never sees half a match, and it is rebuilt when the league
definition changes (``manifest.json`` records a fingerprint of the fixture and generator settings).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from regista.clips import derive_clips
from regista.schema import write_jsonl
from regista.season.league import club_by_id, generate_kwargs
from regista.season.playing_time import played_seconds
from regista.synth.generator import LEAGUE_GENERATOR_VERSION, generate

Record = dict[str, Any]
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_build_all_lock = threading.Lock()   # one build_all at a time in this process: two would start two pools on one fixture


def fingerprint(league: Record, fixture: Record) -> str:
    """Changes whenever anything that shapes this match changes: the fixture, both squads, the generator settings in the
    league file, and the generator code's own league version (so a folder built by older code is rebuilt even when the
    league file was not regenerated)."""
    kw = generate_kwargs(league, fixture)
    data = {"kw": kw, "gen": league["generator"], "code": LEAGUE_GENERATOR_VERSION}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def title(league: Record, fixture: Record, score: dict[str, int]) -> str:
    clubs = club_by_id(league)
    h, a = clubs[fixture["home"]], clubs[fixture["away"]]
    return f"Round {fixture['round']}: {h['name']} {score.get('t_home', 0)}–{score.get('t_away', 0)} {a['name']}"


def is_current(league: Record, fixture: Record, root: Path) -> bool:
    m = root / fixture["match_id"] / "manifest.json"
    if not (m.exists() and (root / fixture["match_id"] / "events.jsonl").exists()):
        return False
    try:
        return json.loads(m.read_text()).get("fingerprint") == fingerprint(league, fixture)
    except (OSError, ValueError):
        return False


def materialise(league: Record, fixture: Record, root: Path | str) -> Path:
    """The fixture's match folder under ``root``, generated now if it is missing or stale. Safe to call from many
    threads: one builds, the others wait for it."""
    root = Path(root)
    dest = root / fixture["match_id"]
    if is_current(league, fixture, root):
        return dest
    with _locks_guard:
        lock = _locks.setdefault(fixture["match_id"], threading.Lock())
    with lock:
        if is_current(league, fixture, root):
            return dest
        root.mkdir(parents=True, exist_ok=True)
        result = generate(**generate_kwargs(league, fixture))
        stream = result.stream
        played = played_seconds(stream)  # starters, and substitutes who came on (league mode)
        clips: list[Record] = []
        labels: list[Record] = []
        for p in (p for p in result.match["players"] if p["player_id"] in played):
            c, lb = derive_clips(stream, p["player_id"])
            clips += c
            labels += lb
        tmp = Path(tempfile.mkdtemp(prefix=f".{fixture['match_id']}.", dir=root))
        try:
            write_jsonl(tmp / "events.jsonl", stream)
            write_jsonl(tmp / "clips.jsonl", clips + labels)
            manifest = {
                "match_id": fixture["match_id"], "collection": "season", "league": league["league"], "season": league["season"],
                "round": fixture["round"], "date": fixture["date"], "home": fixture["home"], "away": fixture["away"],
                "title": title(league, fixture, result.score),
                "subtitle": f"{league['league']} {league['season']}, round {fixture['round']}: thirty generated minutes, "
                            "every player's moments cut and labelled.",
                "score": result.score, "fingerprint": fingerprint(league, fixture),
                "generator": {**league["generator"], "seed": fixture["seed"]},
                "video_duration_s": result.match["video"]["duration_s"], "clip_count": len(clips),
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
            if is_current(league, fixture, root):
                # another process got there first (build_all's worker processes do not share this thread lock): keep its
                # folder rather than delete it under a reader, and drop ours (identical: same fixture, same seed)
                shutil.rmtree(tmp, ignore_errors=True)
                return dest
            if dest.exists():
                shutil.rmtree(dest)
            tmp.rename(dest)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    return dest


def _materialise_one(args: tuple[Record, Record, str]) -> str:
    league, fixture, root = args
    return str(materialise(league, fixture, root))


def build_all(league: Record, root: Path | str, workers: int | None = None) -> list[Path]:
    """Every fixture's folder. Missing or stale ones are generated in parallel processes (a league match takes about a
    second to generate, so a cold season of 30 takes about 35 s on one core and a few seconds on several); ``workers`` 1
    builds them here, one by one. One call runs at a time per process (the warm-up and a request arriving during it would
    otherwise both spawn pools that generate the same fixtures); the second waits and then finds every folder current.
    Worker processes are spawned, so a script that calls this must guard its entry point with
    ``if __name__ == "__main__":`` (each worker imports the script again)."""
    with _build_all_lock:
        return _build_all(league, Path(root), workers)


def _build_all(league: Record, root: Path, workers: int | None) -> list[Path]:
    stale = [f for f in league["fixtures"] if not is_current(league, f, root)]
    workers = min(len(stale), workers or os.cpu_count() or 1)
    if workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing

        root.mkdir(parents=True, exist_ok=True)
        try:
            with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
                list(pool.map(_materialise_one, [(league, f, str(root)) for f in stale]))
        except Exception:  # noqa: BLE001 - no worker processes here (an interactive or piped __main__): the loop below builds
            pass
    return [materialise(league, f, root) for f in league["fixtures"]]


def ensure_tracks(league: Record, fixture: Record, root: Path | str) -> Path:
    """The match folder with ``tracks.jsonl`` present (regenerated from the fixture, identical to the first build)."""
    dest = materialise(league, fixture, root)
    if (dest / "tracks.jsonl").exists():
        return dest
    with _locks_guard:
        lock = _locks.setdefault(fixture["match_id"], threading.Lock())
    with lock:
        if not (dest / "tracks.jsonl").exists():
            result = generate(**generate_kwargs(league, fixture))
            tmp = dest / ".tracks.jsonl.tmp"
            write_jsonl(tmp, result.tracks)
            tmp.rename(dest / "tracks.jsonl")
    return dest


def fixture_of(league: Record, match_id: str) -> Record | None:
    return next((f for f in league["fixtures"] if f["match_id"] == match_id), None)
