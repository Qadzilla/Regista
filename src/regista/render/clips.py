"""Cut one video per clip and a watchability-ordered reel for a player.

    python -m regista.render.clips data/synthetic/sample/syn_0109 --player t_home_10 --out docs/demo/clips_t_home_10

Reads ``clips.jsonl`` from the match directory. If that file was derived for another
player, the clip rule is re-run in memory for the requested player.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from regista.clips import derive_clips
from regista.render.draw import Style
from regista.render.scene import Scene
from regista.render.video import VideoWriter, frame_times, render_frames
from regista.schema import iter_jsonl

Record = dict[str, Any]

TITLE_SECONDS = 2.0


def load_clips(match_dir: Path, scene: Scene, player_id: str) -> tuple[list[Record], dict[str, Record]]:
    """Clips and labels (by clip id) for ``player_id``, from disk or derived on the fly."""
    path = match_dir / "clips.jsonl"
    clips: list[Record] = []
    labels: dict[str, Record] = {}
    if path.exists():
        for r in iter_jsonl(path):
            if r["type"] == "clip" and r["player_id"] == player_id:
                clips.append(r)
            elif r["type"] == "label" and r["player_id"] == player_id:
                labels[r["clip_id"]] = r
    if not clips:
        derived_clips, derived_labels = derive_clips(scene.stream, player_id)
        clips = derived_clips
        labels = {lb["clip_id"]: lb for lb in derived_labels}
    clips.sort(key=lambda c: c["t"])
    return clips, labels


def title_card(clip: Record, label: Record | None, offset: float) -> dict[str, Any]:
    """A title card active for the first ``TITLE_SECONDS`` of a clip. ``offset`` is on the *input* (match) timeline,
    the same axis ``render_frames`` evaluates titles on, so pass ``clip["t"]``."""
    title = label["title"] if label else f"{clip['player_id']} · {clip['reason'].replace('_', ' ')}"
    hide = {"on_ball_main", "replay_appearance", "highlight_appearance", "closeup_appearance", "touch"}
    tags = [t.replace("_", " ") for t in (label["tags"] if label else []) if t not in hide]
    span = f"{int(clip['t'] // 60)}:{int(clip['t'] % 60):02d}–{int(clip['t_end'] // 60)}:{int(clip['t_end'] % 60):02d}"
    subtitle = "  ·  ".join(filter(None, [", ".join(tags[:5]), span]))
    return {
        "t": offset,
        "t_end": offset + TITLE_SECONDS,
        "title": title,
        "subtitle": subtitle,
        "watchability": label["watchability"] if label else 0.0,
    }


def render_clip(scene: Scene, clip: Record, label: Record | None, out: Path, fps: float, style: Style) -> dict[str, Any]:
    times = frame_times(clip["t"], clip["t_end"], fps)
    card = title_card(clip, label, clip["t"])
    with VideoWriter(out, fps) as w:
        for img in render_frames(scene, times, style, titles=[card], focus=clip["player_id"]):
            w.append(img)
        return {"clip_id": clip["id"], "path": str(w.path), "frames": w.frames_written, "t": clip["t"], "t_end": clip["t_end"],
                "reason": clip["reason"], "watchability": label["watchability"] if label else None, "title": card["title"]}


def render_reel(scene: Scene, clips: list[Record], labels: dict[str, Record], out: Path, fps: float, style: Style,
                keep_order: bool = False) -> dict[str, Any]:
    """All clips back to back, each with its title card: best first, or in the order given with ``keep_order``."""
    ordered = list(clips) if keep_order else sorted(clips, key=lambda c: (-(labels.get(c["id"], {}).get("watchability", 0.0)), c["t"]))
    with VideoWriter(out, fps) as w:
        for clip in ordered:
            times = frame_times(clip["t"], clip["t_end"], fps)
            card = title_card(clip, labels.get(clip["id"]), clip["t"])
            for img in render_frames(scene, times, style, titles=[card], focus=clip["player_id"]):
                w.append(img)
        return {"path": str(w.path), "frames": w.frames_written, "order": [c["id"] for c in ordered]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut per-clip videos and a reel for one player.")
    parser.add_argument("match_dir", type=Path)
    parser.add_argument("--player", required=True, help="player_id, e.g. t_home_10")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--no-reel", action="store_true")
    args = parser.parse_args(argv)

    w, h = (int(v) for v in args.size.lower().split("x"))
    style = Style(width=w, height=h)
    scene = Scene.load(args.match_dir)
    if args.player not in scene.roster:
        print(f"error: {args.player} is not in the roster", file=sys.stderr)
        return 2
    clips, labels = load_clips(args.match_dir, scene, args.player)
    if not clips:
        print(f"no clips for {args.player}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results = []
    for clip in clips:
        res = render_clip(scene, clip, labels.get(clip["id"]), args.out / f"{clip['id']}.mp4", args.fps, style)
        results.append(res)
        print(f"  {Path(res['path']).name}  {res['frames']:>4} frames  {res['reason']:<21} {res['title']}")
    reel = None
    if not args.no_reel:
        reel = render_reel(scene, clips, labels, args.out / "reel.mp4", args.fps, style)
        print(f"  reel: {Path(reel['path']).name}  {reel['frames']} frames, {len(reel['order'])} clips best-first")
    index = {"player_id": args.player, "player": scene.player_name(args.player), "fps": args.fps, "clips": results, "reel": reel}
    (args.out / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    print(f"wrote {len(results)} clips to {args.out} in {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
