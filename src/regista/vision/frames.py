"""Read video frames: the first step of the private vision layer.

``iter_frames`` decodes a video with the ffmpeg binary bundled in ``imageio-ffmpeg`` and yields
``(frame_index, t_seconds, rgb)`` tuples, where ``rgb`` is an ``H x W x 3`` ``uint8`` array.
Downscaling happens inside ffmpeg (``-vf scale``), so feature extraction at 128x72 never pays
for full-resolution frames in Python.

Time is counted from the first frame: ``frame_index / fps`` when every frame is read, and evenly spaced by
ffmpeg's ``fps`` filter when sampling. That is exact for Regista's rendered footage (constant frame rate, first
frame at t = 0), which is what lets every evaluation line frames up with the generator's ground truth.

Real footage: broadcast files are usually constant frame rate too (25 or 50 fps in Europe,
29.97 or 59.94 in North America), so the same formula holds. Two things change: interlaced
sources need a deinterlace filter (add ``yadif`` in front of ``scale``). Variable-frame-rate files (phone
recordings) are handled when sampling, because the ``fps`` filter works from timestamps; reading every frame of
such a file still assumes a constant rate.
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


_PROBES: dict[tuple[str, int, int], VideoInfo] = {}


def probe(path: Path | str) -> VideoInfo:
    """Frame rate, size, frame count, and duration of a video file.

    Read from the container's metadata, without decoding (counting frames by decoding is a full pass, minutes on a
    90-minute 1080p file, and a run probes the same file several times). Cached per file (path, size, modified
    time). Only a file whose metadata lacks a duration is counted by decoding."""
    path = Path(path)
    st = path.stat()
    key = (str(path.resolve()), st.st_size, int(st.st_mtime_ns))
    if key in _PROBES:
        return _PROBES[key]
    ff = _ffmpeg()
    gen = ff.read_frames(str(path), pix_fmt="rgb24")
    meta = next(gen)
    gen.close()
    fps = float(meta["fps"])
    w, h = (int(v) for v in meta["size"])
    duration = float(meta.get("duration") or 0.0)
    n_frames = int(round(duration * fps)) if duration > 0 else int(ff.count_frames_and_secs(str(path))[0])
    info = VideoInfo(path=str(path), fps=fps, width=w, height=h, n_frames=n_frames, duration_s=round(n_frames / fps, 3))
    _PROBES[key] = info
    return info


def iter_frames(path: Path | str, sample_fps: float | None = None, size: tuple[int, int] | None = None,
                start_s: float = 0.0, end_s: float | None = None) -> Iterator[Frame]:
    """Yield ``(frame_index, t, rgb)`` for frames between ``start_s`` and ``end_s``.

    ``sample_fps`` below the video's rate samples inside ffmpeg, so only the kept frames are converted and piped.
    When the rate divides evenly (10 -> 5, 25 -> 5, 30 -> 5, 5 -> 1) the frames are exactly every k-th source frame
    and their times are exact. Otherwise (25 -> 10, variable-frame-rate phone recordings) ffmpeg's ``fps`` filter
    spaces them evenly by timestamp, each within one output slot of its true time. ``size`` is ``(width, height)``:
    ffmpeg downscales with area averaging, which is what feature extraction wants. ``frame_index`` is the source
    frame nearest ``t``.
    """
    info = probe(path)
    ff = _ffmpeg()
    sampling = bool(sample_fps) and sample_fps < info.fps - 1e-6
    filters: list[str] = []
    extra: list[str] = []
    rate = info.fps
    if sampling:
        ratio = info.fps / float(sample_fps)
        k = int(round(ratio))
        if k >= 2 and abs(ratio - k) < 1e-3:
            # A whole-number ratio keeps exactly every k-th frame, so each frame's time is exact. (The fps filter
            # assigns frames to slots by rounding and keeps the last one, which can be up to a slot late.)
            filters.append(f"select=not(mod(n\\,{k}))")
            extra = ["-fps_mode", "passthrough"]
            rate = info.fps / k
        else:
            filters.append(f"fps={float(sample_fps):g}")  # uneven ratios and variable-rate files: evenly spaced by timestamp
            rate = float(sample_fps)
    if size is not None:
        filters.append(f"scale={int(size[0])}:{int(size[1])}:flags=area")
    params = (["-vf", ",".join(filters)] if filters else []) + extra or None
    seek = ["-ss", f"{start_s:.3f}"] if start_s > 0 else None
    gen = ff.read_frames(str(path), pix_fmt="rgb24", output_params=params, input_params=seek)
    log = logging.getLogger("imageio_ffmpeg")
    level = log.level
    log.setLevel(logging.ERROR)  # it warns that the output size differs from the source, which is the point
    try:
        meta = next(gen)
    finally:
        log.setLevel(level)
    if size is not None:
        w, h = int(size[0]), int(size[1])
    else:
        w, h = (int(v) for v in meta["size"])
    try:
        for k, buf in enumerate(gen):
            t = round(start_s + k / rate, 6)
            if end_s is not None and t >= end_s:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
            yield int(round(t * info.fps)), t, frame
    finally:
        gen.close()


def frame_at(path: Path | str, t: float) -> np.ndarray:
    """The frame shown at ``t`` seconds, decoded by seeking (for review crops; not for scanning a whole video)."""
    ff = _ffmpeg()
    gen = ff.read_frames(str(path), pix_fmt="rgb24", input_params=["-ss", f"{max(0.0, t):.3f}"])
    try:
        meta = next(gen)
        w, h = (int(v) for v in meta["size"])
        buf = next(gen)
    finally:
        gen.close()
    return np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3).copy()


def resize(rgb: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Area-averaged downscale to ``(width, height)``."""
    import cv2

    return cv2.resize(rgb, (int(size[0]), int(size[1])), interpolation=cv2.INTER_AREA)
