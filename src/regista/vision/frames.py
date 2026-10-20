"""Read video frames: the first step of the private vision layer.

``iter_frames`` decodes a video with the ffmpeg binary bundled in ``imageio-ffmpeg`` and yields
``(frame_index, t_seconds, rgb)`` tuples, where ``rgb`` is an ``H x W x 3`` ``uint8`` array.
Downscaling happens inside ffmpeg (``-vf scale``), so feature extraction at 128x72 never pays
for full-resolution frames in Python.

Time is ``frame_index / fps``. That is exact for Regista's rendered footage (constant frame
rate, first frame at t = 0), which is what lets every evaluation line frames up with the
generator's ground truth.

Real footage: broadcast files are usually constant frame rate too (25 or 50 fps in Europe,
29.97 or 59.94 in North America), so the same formula holds. Two things change: interlaced
sources need a deinterlace filter (add ``yadif`` in front of ``scale``), and variable-frame-rate
files (phone recordings) need per-frame timestamps from ffprobe instead of ``index / fps``.
Neither changes the interface.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np

Frame = tuple[int, float, np.ndarray]


@dataclass(frozen=True)
class VideoInfo:
    path: str
    fps: float
    width: int
    height: int
    n_frames: int
    duration_s: float


def _ffmpeg():
    import imageio_ffmpeg

    return imageio_ffmpeg


def probe(path: Path | str) -> VideoInfo:
    """Frame rate, size, exact frame count, and duration of a video file."""
    ff = _ffmpeg()
    gen = ff.read_frames(str(path), pix_fmt="rgb24")
    meta = next(gen)
    gen.close()
    n_frames, _secs = ff.count_frames_and_secs(str(path))
    fps = float(meta["fps"])
    w, h = (int(v) for v in meta["size"])
    return VideoInfo(path=str(path), fps=fps, width=w, height=h, n_frames=int(n_frames), duration_s=round(n_frames / fps, 3))


def iter_frames(path: Path | str, sample_fps: float | None = None, size: tuple[int, int] | None = None,
                start_s: float = 0.0, end_s: float | None = None) -> Iterator[Frame]:
    """Yield ``(frame_index, t, rgb)`` for frames between ``start_s`` and ``end_s``.

    ``sample_fps`` keeps roughly that many frames per second (every frame when None or when it
    is at least the video's rate). ``size`` is ``(width, height)`` for downscaling; ffmpeg does
    the resize with area averaging, which is what feature extraction wants.
    """
    ff = _ffmpeg()
    params: list[str] = []
    if size is not None:
        params = ["-vf", f"scale={int(size[0])}:{int(size[1])}:flags=area"]
    gen = ff.read_frames(str(path), pix_fmt="rgb24", output_params=params or None)
    log = logging.getLogger("imageio_ffmpeg")
    level = log.level
    log.setLevel(logging.ERROR)  # it warns that the output size differs from the source, which is the point
    try:
        meta = next(gen)
    finally:
        log.setLevel(level)
    fps = float(meta["fps"])
    if size is not None:
        w, h = int(size[0]), int(size[1])
    else:
        w, h = (int(v) for v in meta["size"])
    step = 1.0 / sample_fps if sample_fps and sample_fps < fps else 0.0
    next_t = start_s
    try:
        for i, buf in enumerate(gen):
            t = i / fps
            if t + 1e-9 < start_s:
                continue
            if end_s is not None and t >= end_s:
                break
            if step and t + 1e-9 < next_t:
                continue
            if step:
                next_t += step
                while next_t <= t + 1e-9:  # never fall behind after a long skip
                    next_t += step
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            yield i, t, frame
    finally:
        gen.close()


def resize(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Area-averaged downscale to ``(width, height)``."""
    import cv2

    return cv2.resize(rgb, (int(size[0]), int(size[1])), interpolation=cv2.INTER_AREA)
