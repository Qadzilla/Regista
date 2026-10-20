"""Turn frames into a video file. MP4 through the bundled ffmpeg when available, GIF otherwise.

Rendering is CPU bound and embarrassingly parallel. ``render_video`` splits the timeline
into contiguous parts, each worker process renders and encodes its own part to MP4,
and the parent concatenates the parts with ffmpeg's concat demuxer (stream copy, so no
re-encode and no frame-accurate drift). Sending PNGs back through pipes was measured
slower than rendering in-process, which is why workers encode locally.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from regista.render.draw import Style, frame_info, render_frame
from regista.render.scene import Scene

Record = dict[str, Any]


def has_ffmpeg() -> bool:
    try:
        import imageio_ffmpeg

        imageio_ffmpeg.get_ffmpeg_exe()
        return True
    except Exception:  # pragma: no cover - depends on the environment
        return False


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def frame_times(t0: float, t1: float, fps: float) -> list[float]:
    n = int(round((t1 - t0) * fps))
    return [t0 + i / fps for i in range(max(n, 0))]


# ---------------------------------------------------------------------------- writer

class VideoWriter:
    """MP4 (libx264) via imageio + imageio-ffmpeg, or GIF fallback. Use as a context manager."""

    def __init__(self, path: Path | str, fps: float):
        self.path = Path(path)
        self.fps = fps
        self.frames_written = 0
        self._writer = None
        self._gif_frames: list[Image.Image] = []
        self.mode = "mp4"
        if self.path.suffix.lower() == ".gif" or not has_ffmpeg():
            self.mode = "gif"
            if self.path.suffix.lower() != ".gif":
                warnings.warn("ffmpeg not available: writing GIF instead of MP4", stacklevel=2)
                self.path = self.path.with_suffix(".gif")

    def __enter__(self) -> VideoWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.mode == "mp4":
            import imageio

            self._writer = imageio.get_writer(
                str(self.path), fps=self.fps, codec="libx264", quality=8, pixelformat="yuv420p", macro_block_size=1,
                ffmpeg_log_level="error",
            )
        return self

    def append(self, img: Image.Image) -> None:
        if self.mode == "mp4":
            assert self._writer is not None
            self._writer.append_data(np.asarray(img))
        else:
            self._gif_frames.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
        self.frames_written += 1

    def __exit__(self, *exc: object) -> None:
        if self.mode == "mp4":
            if self._writer is not None:
                self._writer.close()
        elif self._gif_frames:
            first, rest = self._gif_frames[0], self._gif_frames[1:]
            first.save(self.path, save_all=True, append_images=rest, duration=int(1000 / self.fps), loop=0, optimize=False)


def count_frames(path: Path | str) -> int:
    path = Path(path)
    if path.suffix.lower() == ".gif":
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1)
    import imageio

    reader = imageio.get_reader(str(path), "ffmpeg")
    try:
        n = reader.count_frames()
    finally:
        reader.close()
    return int(n)


def concat_mp4(parts: list[Path], out: Path) -> None:
    """Lossless concatenation of same-codec MP4 parts."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        for p in parts:
            fh.write(f"file '{p.resolve().as_posix()}'\n")
        list_path = fh.name
    try:
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", str(out)], check=True)
    finally:
        os.unlink(list_path)


# ---------------------------------------------------------------------------- in-process rendering

def render_frames(scene: Scene, times: Iterable[float], style: Style, titles: list[dict[str, Any]] | None = None) -> Iterator[Image.Image]:
    """Yield frames in order, in this process. Used for clips, which are short."""
    for t in times:
        yield render_frame(scene, t, style, _title_for(titles, t))


def _title_for(titles: list[dict[str, Any]] | None, t: float) -> dict[str, Any] | None:
    if not titles:
        return None
    for card in titles:
        if card["t"] <= t < card["t_end"]:
            return card
    return None


def write_frames(frames: Iterable[Image.Image], out: Path | str, fps: float) -> Path:
    with VideoWriter(out, fps) as w:
        for img in frames:
            w.append(img)
        return w.path


# ---------------------------------------------------------------------------- parallel parts

_SCENE: Scene | None = None
_STYLE: Style | None = None
_TITLES: list[dict[str, Any]] | None = None


def _init_worker(scene: Scene, style: Style, titles: list[dict[str, Any]] | None) -> None:
    global _SCENE, _STYLE, _TITLES
    _SCENE, _STYLE, _TITLES = scene, style, titles


def _render_part(job: dict[str, Any]) -> dict[str, Any]:
    """Render one contiguous run of frames to its own file. Runs in a worker or inline."""
    assert _SCENE is not None and _STYLE is not None
    frames_dir = Path(job["frames_dir"]) if job["frames_dir"] else None
    keyframes: dict[int, str] = job["keyframes"]
    with VideoWriter(job["path"], job["fps"]) as w:
        for i, t in zip(job["indices"], job["times"]):
            img = render_frame(_SCENE, t, _STYLE, _title_for(_TITLES, t))
            w.append(img)
            if frames_dir is not None and i in keyframes:
                frames_dir.mkdir(parents=True, exist_ok=True)
                img.save(frames_dir / keyframes[i])
        return {"part": job["part"], "path": str(w.path), "frames": w.frames_written, "mode": w.mode}


def _split(n: int, parts: int) -> list[tuple[int, int]]:
    parts = max(1, min(parts, n))
    size, extra = divmod(n, parts)
    out, start = [], 0
    for p in range(parts):
        end = start + size + (1 if p < extra else 0)
        out.append((start, end))
        start = end
    return out


def render_video(scene: Scene, out: Path | str, *, fps: float = 25.0, style: Style | None = None, workers: int | None = None,
                 t0: float = 0.0, t1: float | None = None, frames_dir: Path | str | None = None,
                 titles: list[dict[str, Any]] | None = None, keyframe_every: float = 1.0,
                 progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Render ``scene`` between ``t0`` and ``t1`` to ``out``. Returns a small manifest."""
    style = style or Style()
    out = Path(out)
    t1 = scene.duration if t1 is None else t1
    times = frame_times(t0, t1, fps)
    if not times:
        raise ValueError("nothing to render: empty time range")
    if workers is None:
        workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    frames_dir = Path(frames_dir) if frames_dir else None

    # Decide keyframes up front so every worker names them consistently.
    infos = [frame_info(scene, t) for t in times]
    keyframes: dict[int, str] = {}
    index: list[dict[str, Any]] = []
    seen: set[str] = set()
    if frames_dir is not None:
        for i, (t, info) in enumerate(zip(times, infos)):
            first = info["segment_id"] not in seen
            seen.add(info["segment_id"])
            on_second = keyframe_every > 0 and abs(((t - t0) / keyframe_every) - round((t - t0) / keyframe_every)) * keyframe_every < 0.5 / fps
            if first or on_second:
                name = f"frame_{i:06d}_t{t:07.2f}_{info['kind']}.png"
                keyframes[i] = name
                index.append({"file": name, "frame": i, "t": round(t, 3), "kind": info["kind"], "segment_id": info["segment_id"],
                              "caption": info.get("caption"), "badge": (info.get("badge") or {}).get("text")})

    gif = out.suffix.lower() == ".gif" or not has_ffmpeg()
    n_parts = 1 if (gif or workers <= 1 or len(times) < 2 * workers) else workers * 3
    ranges = _split(len(times), n_parts)
    tmp_dir = out.parent / f".{out.stem}_parts"
    jobs = []
    for p, (a, b) in enumerate(ranges):
        path = out if n_parts == 1 else tmp_dir / f"part_{p:03d}.mp4"
        jobs.append({"part": p, "indices": list(range(a, b)), "times": times[a:b], "path": str(path), "fps": fps,
                     "frames_dir": str(frames_dir) if frames_dir else None, "keyframes": keyframes})

    results: list[dict[str, Any]] = []
    if n_parts == 1:
        _init_worker(scene, style, titles)
        results.append(_render_part(jobs[0]))
        if progress:
            progress(len(times), len(times))
    else:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ctx = mp.get_context("spawn")
        done = 0
        with ctx.Pool(processes=workers, initializer=_init_worker, initargs=(scene, style, titles)) as pool:
            for res in pool.imap_unordered(_render_part, jobs):
                results.append(res)
                done += res["frames"]
                if progress:
                    progress(done, len(times))
        results.sort(key=lambda r: r["part"])
        out.parent.mkdir(parents=True, exist_ok=True)
        concat_mp4([Path(r["path"]) for r in results], out)
        for r in results:
            Path(r["path"]).unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass

    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)
        (frames_dir / "frames.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    final_path = Path(results[0]["path"]) if n_parts == 1 else out
    return {"path": str(final_path), "mode": results[0]["mode"], "fps": fps, "frames": sum(r["frames"] for r in results),
            "t0": t0, "t1": t1, "workers": workers if n_parts > 1 else 1, "parts": n_parts,
            "keyframes": len(index), "frames_dir": str(frames_dir) if frames_dir else None}


def stderr_is_tty() -> bool:
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
