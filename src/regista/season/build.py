"""Regenerate the league's matches from ``league.json`` into match folders the rest of Regista reads.

Each match folder looks like a committed sample: ``events.jsonl``, ``clips.jsonl`` (every starter's clips, labelled by
the rules labeller) and ``manifest.json`` (title, round, ``collection: season``). ``tracks.jsonl`` (about 17 MB for a
30-minute match) is written only when something needs positions, such as video (``ensure_tracks``); profiles need only
the events. A folder is written
into a temporary name and renamed into place, so a reader never sees half a match, and it is rebuilt when the league
definition changes (``manifest.json`` records a fingerprint of the fixture and generator settings).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from regista.clips import derive_clips
from regista.schema import write_jsonl
from regista.season.league import club_by_id, generate_kwargs
from regista.synth.generator import generate

Record = dict[str, Any]
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def fingerprint(league: Record, fixture: Record) -> str:
    """Changes whenever anything that shapes this match changes: the fixture, both squads, the generator settings."""
    kw = generate_kwargs(league, fixture)
    return hashlib.sha256(json.dumps({"kw": kw, "gen": league["generator"]}, sort_keys=True).encode()).hexdigest()[:16]


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
        starters = [p for p in result.match["players"] if p["starter"]]
        clips: list[Record] = []
        labels: list[Record] = []
        for p in starters:
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
                            "every starter's moments cut and labelled.",
                "score": result.score, "fingerprint": fingerprint(league, fixture),
                "generator": {**league["generator"], "seed": fixture["seed"]},
                "video_duration_s": result.match["video"]["duration_s"], "clip_count": len(clips),
            }
            (tmp / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
            if dest.exists():
                shutil.rmtree(dest)
            tmp.rename(dest)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    return dest


def build_all(league: Record, root: Path | str) -> list[Path]:
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
