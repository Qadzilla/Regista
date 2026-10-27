"""CLI: render a match directory to a broadcast-style video.

    python -m regista.render data/synthetic/sample/syn_0109 --out docs/demo/syn_0109.mp4
    python -m regista.render data/synthetic/sample/syn_0109 --out out.mp4 --frames-dir out_frames --fps 15
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from regista.render.draw import Style
from regista.render.scene import Scene
from regista.render.video import has_ffmpeg, render_video, stderr_is_tty


def parse_size(text: str) -> tuple[int, int]:
    w, h = (int(v) for v in text.lower().split("x"))
    return w - w % 2, h - h % 2  # libx264 needs even dimensions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Regista match to video.")
    parser.add_argument("match_dir", type=Path, help="directory with events.jsonl and tracks.jsonl")
    parser.add_argument("--out", type=Path, required=True, help="output .mp4 (or .gif)")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--size", type=parse_size, default=(1280, 720), help="WIDTHxHEIGHT, default 1280x720")
    parser.add_argument("--workers", type=int, default=None, help="render processes (default: usable CPUs - 1, counting a container quota, max 8)")
    parser.add_argument("--frames-dir", type=Path, default=None, help="also save one PNG per second and per segment start here")
    parser.add_argument("--start", type=float, default=0.0, help="start time in seconds")
    parser.add_argument("--end", type=float, default=None, help="end time in seconds (default: whole video)")
    parser.add_argument("--end-card", type=float, default=3.0, help="seconds of closing card after the last segment (0 to disable)")
    args = parser.parse_args(argv)

    scene = Scene.load(args.match_dir)
    style = Style(width=args.size[0], height=args.size[1])
    if not has_ffmpeg():
        print("note: ffmpeg not found, falling back to GIF", file=sys.stderr)

    started = time.perf_counter()

    def progress(done: int, total: int) -> None:
        if stderr_is_tty():
            print(f"\r  {done}/{total} frames", end="", file=sys.stderr, flush=True)

    manifest = render_video(scene, args.out, fps=args.fps, style=style, workers=args.workers, t0=args.start, t1=args.end,
                            frames_dir=args.frames_dir, end_card_s=args.end_card, progress=progress)
    elapsed = time.perf_counter() - started
    if stderr_is_tty():
        print(file=sys.stderr)
    print(f"wrote {manifest['path']}  ({manifest['frames']} frames @ {args.fps:g} fps incl. {manifest['end_card_frames']} end-card frames, "
          f"{manifest['mode']}, {manifest['workers']} worker(s), {elapsed:.1f}s)")
    if manifest["frames_dir"]:
        print(f"keyframes: {manifest['keyframes']} PNGs in {manifest['frames_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
