"""Packaging a vision match directory for the public library (the live app's demo vision match).

A vision run writes more than the app serves: ``.vision_work/`` (the identity result, pickled), ``agents/`` (the
workflow's trace and checkpoints), and a manifest whose ``video.path`` points at a file on the machine that ran it.
``package_match`` copies only what the app reads (``events.jsonl``, ``clips.jsonl``, ``tracks.jsonl``, the Who's who
queue and its crops, and the answers given so far), adds the score (goals the vision layer spotted) to the match header, writes a manifest without
machine paths, and refuses to finish if any copied text still holds one.

``tracks.jsonl`` is made smaller in two steps. ``downsample_tracks`` keeps one sampled frame per ``1 / track_hz``
seconds in each main-camera segment. The vision layer asks for 2 Hz and gets a frame every 0.6 s (its identity frames
are 5 fps); ``track_hz=1`` keeps every other one, 1.2 s apart. The renderer scales its interpolation to the median ball
sampling gap, so it plays the sparser tracks the same way, like the committed generator sample at 1 Hz. On vis_0201,
compared over every main-camera frame at 10 fps: players move 0.38 m on average from where the full tracks put them
(95th percentile 1.37 m), the ball 0.77 m (3.1 m). Then ``trim_tracks`` keeps exactly what the renderer
(``regista.render.scene``) reads:

- main-camera segments: every ball record and every record of a *named* player, untouched (the renderer's player and
  ball timelines). Unnamed player tracks are dropped: the renderer skips records without a ``player_id`` and nothing
  else in the app reads ``tracks.jsonl``.
- replays, highlights and closeups: the first record of each named player per segment, in first-seen order (the
  renderer only reads which players a cutaway shows, ``Scene.cutaway_players``). Ball and unnamed records are dropped.

The other records, the clips and the Who's who questions are copied unchanged. Answering the questions (``POST
/api/matches/{id}/identity-review``) needs the identity result, the video and the vision models, which stay on the
machine that ran the vision layer (docs/vision.md, "Who's who"). There the full vision output lives in the work root,
``data/vision/<match_id>/`` by default (``REGISTA_VISION_WORK``; git-ignored and left out of the image). ``work_dir_for``
finds it, an answer is applied to it, and ``repackage`` carries the corrected match, the answers and the next questions
into the committed package. Without it (the live app) answers are refused and nothing changes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from regista.schema import iter_jsonl, validate_match_dir, write_jsonl
from regista.vision.review import ANSWERS_FILE
from regista.vision.review import QUEUE_FILE as REVIEW_QUEUE

Record = dict[str, Any]
# Absolute paths that would name the machine (home folders, temp folders); a packaged match must hold none.
MACHINE_PATH_RE = re.compile(r"(/Users/|/home/|/private/|/tmp/|/var/folders/|[A-Za-z]:\\\\)")
DEFAULT_WORK_ROOT = Path("data/vision")
IDENTITY_FILE = Path(".vision_work") / "identity.joblib"
KEPT_FIELDS = ("title", "subtitle")  # the Product's heading for the match, written by hand


def downsample_tracks(records: Iterable[Record], track_hz: float, segment_ids: set[str] | None = None) -> list[Record]:
    """Every record of the sampled frames at ``track_hz``, per camera segment, in their original order. Only segments
    in ``segment_ids`` are downsampled (all when None); records of the others pass through.

    The same rule as ``regista.vision.identity.track_records``: in each segment, keep the first frame at or after the
    next due time, then the next one ``1 / track_hz`` later. All objects of a kept frame are kept together."""
    step = 1.0 / track_hz
    next_t: dict[str, float] = {}
    kept: dict[str, float] = {}  # segment -> t of the frame being kept
    out: list[Record] = []
    for r in records:
        seg, t = r["segment_id"], float(r["t"])
        if segment_ids is not None and seg not in segment_ids:
            out.append(r)
            continue
        if kept.get(seg) != t:
            if t + 1e-6 < next_t.get(seg, float("-inf")):
                continue
            kept[seg] = t
            next_t[seg] = t + step - 1e-6
        out.append(r)
    return out


def trim_tracks(records: Iterable[Record], main_segment_ids: set[str]) -> list[Record]:
    """The track records the renderer reads, in their original order (see the module docstring)."""
    out: list[Record] = []
    seen: set[tuple[str, str]] = set()
    for r in records:
        seg = r["segment_id"]
        if seg in main_segment_ids:
            if r["object"] == "ball" or (r["object"] == "player" and r.get("player_id")):
                out.append(r)
        elif r["object"] == "player" and r.get("player_id") and (seg, r["player_id"]) not in seen:
            seen.add((seg, r["player_id"]))
            out.append(r)
    return out


def _score(header: Record, events: list[Record]) -> dict[str, int]:
    """Goals the vision layer spotted, per team (not the generator's score: this match's events came from video)."""
    score = {t["team_id"]: 0 for t in header["teams"]}
    for e in events:
        if e.get("event_type") == "goal" and e.get("team_id") in score:
            score[e["team_id"]] += 1
    return score


def machine_paths(directory: Path | str) -> list[str]:
    """Files under ``directory`` (text only) that mention an absolute machine path."""
    hits = []
    for p in sorted(Path(directory).rglob("*")):
        if p.is_file() and p.suffix in (".json", ".jsonl", ".md", ".txt"):
            if MACHINE_PATH_RE.search(p.read_text(encoding="utf-8")):
                hits.append(str(p.relative_to(directory)))
    return hits


def package_match(src: Path | str, dest: Path | str, *, player_id: str, note: str, rendering: Record | None = None,
                  track_hz: float | None = 1.0) -> Record:
    """Copy a vision match directory ``src`` (run, then given clips by ``python3 -m regista.agents``) to ``dest``.

    ``dest`` is replaced. Returns the manifest written. Raises ``ValueError`` if the result does not validate or still
    holds a machine path."""
    src, dest = Path(src), Path(dest)
    for need in ("events.jsonl", "tracks.jsonl", "clips.jsonl"):
        if not (src / need).exists():
            raise FileNotFoundError(f"{src / need} is missing (run the vision layer, then python3 -m regista.agents)")
    stream = list(iter_jsonl(src / "events.jsonl"))
    header = stream[0]
    if header.get("source") != "vision":
        raise ValueError(f"{src} was not written by the vision layer (match source {header.get('source')!r})")
    if header["match_id"] != dest.name:
        raise ValueError(f"the directory name must equal the match_id ({header['match_id']!r}), not {dest.name!r}")
    main_ids = {r["id"] for r in stream if r["type"] == "camera_segment" and r["kind"] == "main"}
    clips = list(iter_jsonl(src / "clips.jsonl"))

    kept: Record = {}  # what the app shows about the match (set by hand in the committed manifest) survives repackaging
    if (dest / "manifest.json").exists():
        old = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        kept = {k: old[k] for k in KEPT_FIELDS if k in old}
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "review" / "crops").mkdir(parents=True)
    events = [r for r in stream if r["type"] == "event"]
    # The vision header has no score; the match endpoint reads it from there, so give it the goals spotted in the video.
    stream[0] = {**header, "score": _score(header, events)}
    write_jsonl(dest / "events.jsonl", stream)
    shutil.copyfile(src / "clips.jsonl", dest / "clips.jsonl")
    n_full = sum(1 for _ in iter_jsonl(src / "tracks.jsonl"))
    tracks: Iterable[Record] = iter_jsonl(src / "tracks.jsonl")
    if track_hz:
        tracks = downsample_tracks(tracks, track_hz, main_ids)  # cutaways keep every frame until trim_tracks
    n_tracks = write_jsonl(dest / "tracks.jsonl", trim_tracks(tracks, main_ids))

    questions: list[Record] = []
    queue = src / "review" / REVIEW_QUEUE
    if queue.exists():
        questions = json.loads(queue.read_text(encoding="utf-8"))["items"]
        for it in questions:
            if it.get("image"):
                shutil.copyfile(src / "review" / "crops" / it["image"], dest / "review" / "crops" / it["image"])
        (dest / "review" / REVIEW_QUEUE).write_text(json.dumps({"items": questions}, indent=1) + "\n", encoding="utf-8")
    answered = list(iter_jsonl(src / "review" / ANSWERS_FILE)) if (src / "review" / ANSWERS_FILE).exists() else []
    if answered:  # identity a person confirmed or corrected on the machine that ran the vision layer
        write_jsonl(dest / "review" / ANSWERS_FILE, answered)

    clips_for = [c for c in clips if c["type"] == "clip" and c.get("player_id") == player_id]
    manifest: Record = {
        "match_id": header["match_id"],
        **kept,
        "source": "vision",
        "note": note,
        "rendering": rendering or {},
        "score": stream[0]["score"],
        "video": {k: header["video"][k] for k in ("video_id", "fps", "width", "height", "duration_s") if k in header["video"]},
        "files": {"events.jsonl": len(stream), "tracks.jsonl": n_tracks, "clips.jsonl": len(clips)},
        "tracks_trimmed": {"from": n_full, "to": n_tracks, "track_hz": track_hz,
                           "how": "regista.vision.package: downsample_tracks, then trim_tracks (what the renderer reads)"},
        "record_counts": dict(Counter(r["type"] for r in stream)),
        "event_type_counts": dict(sorted(Counter(e["event_type"] for e in events).items())),
        "clips_for": player_id,
        "clip_reasons": dict(Counter(c["reason"] for c in clips_for)),
        "review": {"questions": len(questions), "kinds": dict(Counter(it["kind"] for it in questions)),
                   "crops": sum(1 for it in questions if it.get("image")), "answers": len(answered),
                   "answered_by": sorted({a.get("annotator", "") for a in answered if a.get("source") == "human"})},
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    problems = {k: v for k, v in validate_match_dir(dest).items() if v}
    if problems:
        raise ValueError(f"packaged match does not validate: {problems}")
    if hits := machine_paths(dest):
        raise ValueError(f"packaged files still hold machine paths: {hits}")
    return manifest


def work_root() -> Path:
    """Where full vision outputs live on the machine that ran the vision layer (read per call, so tests can move it)."""
    return Path(os.environ.get("REGISTA_VISION_WORK") or DEFAULT_WORK_ROOT)


def work_dir_for(match_dir: Path | str) -> Path | None:
    """The full vision output an answer to ``match_dir``'s questions is applied to, if it is on this machine: the match
    directory itself when it is an unpackaged vision run, else ``work_root() / <match_id>`` when that holds the identity
    result and a manifest naming a video that exists. None on the live app, which has neither."""
    match_dir = Path(match_dir)
    if (match_dir / IDENTITY_FILE).exists():
        return match_dir
    work = work_root() / match_dir.name
    if not (work / IDENTITY_FILE).exists() or not (work / "manifest.json").exists():
        return None
    video = json.loads((work / "manifest.json").read_text(encoding="utf-8")).get("video", {}).get("path")
    return work if video and Path(video).exists() else None


def write_clips(work: Path | str, player_id: str) -> int:
    """``clips.jsonl`` for one player, as the local intelligence pipeline writes it (clip rule, rules-v0 labeller, the
    flags for human review), with no model learned from verdicts, so a package does not depend on whose verdicts are
    on the machine."""
    from regista.agents.roles import flag_for_review
    from regista.clips import derive_clips

    clips, labels = derive_clips(list(iter_jsonl(Path(work) / "events.jsonl")), player_id)
    return write_jsonl(Path(work) / "clips.jsonl", clips + flag_for_review(labels))


def repackage(work: Path | str, dest: Path | str) -> Record:
    """Package ``work`` into ``dest`` again with ``dest``'s own settings (player, note, rendering, track rate), after
    identity answers changed ``work``. Clips are derived again for the package's player."""
    old = json.loads((Path(dest) / "manifest.json").read_text(encoding="utf-8"))
    write_clips(work, old["clips_for"])
    return package_match(work, dest, player_id=old["clips_for"], note=old["note"], rendering=old.get("rendering") or {},
                         track_hz=(old.get("tracks_trimmed") or {}).get("track_hz"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m regista.vision.package", description=__doc__.split("\n\n")[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("dest", type=Path)
    ap.add_argument("--player", required=True)
    ap.add_argument("--note", required=True)
    ap.add_argument("--track-hz", type=float, default=1.0, help="downsample tracks to this rate (0: keep the vision layer's)")
    ap.add_argument("--rendering", default="{}", help="JSON: how the video was rendered (seed, size, fps, captions)")
    ap.add_argument("--derive-clips", action="store_true", help="write src/clips.jsonl for --player first (see write_clips)")
    args = ap.parse_args(argv)
    if args.derive_clips:
        write_clips(args.src, args.player)
    m = package_match(args.src, args.dest, player_id=args.player, note=args.note, rendering=json.loads(args.rendering),
                      track_hz=args.track_hz or None)
    print(json.dumps({k: m[k] for k in ("match_id", "score", "files", "tracks_trimmed", "clip_reasons", "review")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
