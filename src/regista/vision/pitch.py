"""Image <-> pitch mapping for the main camera, and the calibrator that finds it per frame.

The contract every downstream step uses is ``PitchMapping``: ``image_to_pitch(u, v)`` and
``pitch_to_image(x, y)``, with ``(u, v)`` in pixels and ``(x, y)`` in pitch metres
(``x`` 0..105 along the length, ``y`` 0..68 across, origin at the corner to the main camera's
left, as in ``data/synthetic/README.md``).

**Synthetic footage (implemented).** Regista's renderer uses one camera family
(``regista.camera`` / ``regista.render.draw.Camera``): a high camera on the near touchline that
pans along the pitch. Rows are linear in depth and columns scale by ``1 - k * depth``; the only
per-frame unknown is the pan ``cx`` (the pitch ``x`` at the centre of the frame).
``MainCameraCalibrator`` recovers ``cx`` from the frame alone: it rectifies every pitch pixel
into "metres from the frame centre", builds three 1-D profiles along the pitch length (white
line fraction, mown-stripe shade, off-pitch surround), and slides them against the same
profiles of a 105 x 68 pitch model. Players are masked out first. This is a genuine
image-to-pitch registration, just with one degree of freedom instead of eight.

**Real footage (what changes).** A real broadcast camera pans, tilts, and zooms, and lenses
distort, so the mapping is a full homography per frame (``HomographyMapping`` below already
implements the interface). The calibrator becomes: detect pitch line segments and keypoints
(penalty-box corners, centre-circle tangents, goal-area corners), match them to the pitch
model (a learned keypoint detector is the practical choice), solve ``cv2.findHomography`` with
RANSAC, and track it across frames. Nothing downstream changes, because everything downstream
only calls ``image_to_pitch``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from regista.camera import MAIN_K, MAIN_WINDOW_M, PITCH_L, PITCH_W

BIN_M = 0.1                    # profile resolution, metres
OFFSET_M = 42.0                # half-width of the rectified band (covers the far touchline's 74 m view)
MODEL_LO, MODEL_HI = -50.0, 155.0
CX_LO, CX_HI = MAIN_WINDOW_M / 2, PITCH_L - MAIN_WINDOW_M / 2  # the renderer never pans past the goal lines


class PitchMapping(Protocol):
    def image_to_pitch(self, u: float, v: float) -> tuple[float, float]: ...

    def pitch_to_image(self, x: float, y: float) -> tuple[float, float]: ...


@dataclass(frozen=True)
class MainCameraGeometry:
    """The renderer's main ("live") camera at a given frame size; ``cx`` is the per-frame pan."""

    width: int
    height: int
    window: float = MAIN_WINDOW_M
    k: float = MAIN_K

    @property
    def s(self) -> float:
        return self.width / 1280.0

    @property
    def y_top(self) -> float:
        return 96 * self.s

    @property
    def y_bottom(self) -> float:
        return self.height - 96 * self.s

    @property
    def S(self) -> float:
        return self.width / self.window

    def depth_of_row(self, v: np.ndarray | float) -> np.ndarray | float:
        return (self.y_bottom - v) / (self.y_bottom - self.y_top)

    def at(self, cx: float) -> SyntheticCameraMapping:
        return SyntheticCameraMapping(self, float(cx))


@dataclass(frozen=True)
class SyntheticCameraMapping:
    geom: MainCameraGeometry
    cx: float

    def pitch_to_image(self, x: float, y: float) -> tuple[float, float]:
        g = self.geom
        d = y / PITCH_W
        u = g.width / 2 + (x - self.cx) * g.S * (1.0 - g.k * d)
        v = g.y_bottom - d * (g.y_bottom - g.y_top)
        return float(u), float(v)

    def image_to_pitch(self, u: float, v: float) -> tuple[float, float]:
        g = self.geom
        d = float(g.depth_of_row(v))
        x = self.cx + (u - g.width / 2) / (g.S * (1.0 - g.k * d))
        return float(x), float(d * PITCH_W)


@dataclass(frozen=True)
class HomographyMapping:
    """A general planar mapping: ``H`` takes pitch metres to pixels. What a real-footage calibrator returns."""

    H: np.ndarray

    def pitch_to_image(self, x: float, y: float) -> tuple[float, float]:
        p = self.H @ np.array([x, y, 1.0])
        return float(p[0] / p[2]), float(p[1] / p[2])

    def image_to_pitch(self, u: float, v: float) -> tuple[float, float]:
        p = np.linalg.solve(self.H, np.array([u, v, 1.0]))
        return float(p[0] / p[2]), float(p[1] / p[2])


def clamp_pitch(x: float, y: float) -> tuple[float, float]:
    return float(min(PITCH_L, max(0.0, x))), float(min(PITCH_W, max(0.0, y)))


# ---------------------------------------------------------------------------- the pitch model

def _blur(a: np.ndarray, sigma_bins: float) -> np.ndarray:
    r = int(3 * sigma_bins) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma_bins) ** 2)
    return np.convolve(a, k / k.sum(), mode="same")


def pitch_model_profiles() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """1-D profiles of the 105 x 68 pitch along its length: x grid, white-line fraction, stripe sign, surround fraction.

    Fractions are over the width of the pitch (uniform in y), which is how a rectified image
    samples it (image rows are linear in depth)."""
    xs = np.arange(MODEL_LO, MODEL_HI, BIN_M)
    white = np.zeros_like(xs)

    def vline(x0: float, frac: float) -> None:
        white[int(round((x0 - MODEL_LO) / BIN_M))] += frac / BIN_M * 0.1

    for x0 in (0.0, PITCH_L, PITCH_L / 2):
        vline(x0, 1.0)
    for x0 in (16.5, PITCH_L - 16.5):
        vline(x0, 40.3 / PITCH_W)
    for x0 in (5.5, PITCH_L - 5.5):
        vline(x0, 18.32 / PITCH_W)
    # Horizontal box lines and the centre circle cross each column in a couple of rows.
    for lo, hi, rows in ((0.0, 16.5, 2), (PITCH_L - 16.5, PITCH_L, 2), (0.0, 5.5, 2), (PITCH_L - 5.5, PITCH_L, 2)):
        white[(xs >= lo) & (xs <= hi)] += rows * 0.25 / PITCH_W
    circ = np.abs(xs - PITCH_L / 2) <= 9.15
    white[circ] += 2 * 0.25 / PITCH_W / np.sqrt(np.clip(1 - ((xs[circ] - PITCH_L / 2) / 9.15) ** 2, 0.05, 1))
    stripe = np.zeros_like(xs)
    inside = (xs >= 0) & (xs < PITCH_L)
    stripe[inside] = np.where((np.floor(xs[inside] / (PITCH_L / 10)) % 2) == 0, -1.0, 1.0)
    surround = np.where(inside, 0.0, 1.0)
    surround[(xs >= -2.0) & (xs < 0)] = 1.0 - 7.32 / PITCH_W  # the goal frame covers part of those columns
    surround[(xs >= PITCH_L) & (xs < PITCH_L + 2.0)] = 1.0 - 7.32 / PITCH_W
    return xs, _blur(white, 2.0), _blur(stripe, 1.0), _blur(surround, 1.0)


# ---------------------------------------------------------------------------- the calibrator

@dataclass
class Calibration:
    cx: float
    score: float
    mapping: SyntheticCameraMapping


class MainCameraCalibrator:
    """Estimate the main camera's pan from a frame (synthetic camera family; see module docstring)."""

    def __init__(self, width: int, height: int, step_m: float = 0.1):
        self.geom = MainCameraGeometry(width, height)
        g = self.geom
        rows = np.arange(int(np.ceil(g.y_top)) + 3, int(np.floor(g.y_bottom)) - 2)
        self.rows = rows
        cols = np.arange(width) + 0.5
        d = g.depth_of_row(rows.astype(float) + 0.5)
        off = (cols[None, :] - width / 2) / (g.S * (1.0 - g.k * d[:, None]))  # metres from the frame centre
        self.nbins = int(round(2 * OFFSET_M / BIN_M))
        self.bins = np.clip(((off + OFFSET_M) / BIN_M).astype(int), 0, self.nbins - 1)
        self.offsets = -OFFSET_M + (np.arange(self.nbins) + 0.5) * BIN_M
        xs, self.m_white, self.m_stripe, self.m_surround = pitch_model_profiles()
        self.model_x = xs
        self.cands = np.arange(CX_LO, CX_HI + 1e-9, step_m)
        # For each candidate pan and offset bin, the model index of pitch x = cx + offset.
        idx = np.round((self.cands[:, None] + self.offsets[None, :] - MODEL_LO) / BIN_M).astype(int)
        self.idx = np.clip(idx, 0, len(xs) - 1)

    def profiles(self, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        import cv2

        band = rgb[self.rows]
        hsv = cv2.cvtColor(band, cv2.COLOR_RGB2HSV)
        H, S, V = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
        grass = (H >= 30) & (H <= 90) & (S > 60) & (V > 50)
        white = (V > 170) & (S < 60)
        surround = (V < 70) & (S < 110)
        valid = grass | white | surround
        G = band[..., 1].astype(np.float32)
        Gm = np.where(grass, G, np.nan)
        with np.errstate(all="ignore"):
            row_med = np.nanmedian(Gm, axis=1, keepdims=True)
        shade = np.where(grass, np.clip(G - np.nan_to_num(row_med), -12, 12), 0.0)
        b = self.bins.ravel()
        n_valid = np.bincount(b, weights=valid.ravel(), minlength=self.nbins)
        n_grass = np.bincount(b, weights=grass.ravel(), minlength=self.nbins)
        w = np.bincount(b, weights=white.ravel(), minlength=self.nbins) / np.maximum(n_valid, 1)
        st = np.bincount(b, weights=shade.ravel(), minlength=self.nbins) / np.maximum(n_grass, 1)
        su = np.bincount(b, weights=surround.ravel(), minlength=self.nbins) / np.maximum(n_valid, 1)
        return w, st, su, n_valid

    def estimate(self, rgb: np.ndarray, prior_cx: float | None = None, prior_sigma: float = 6.0) -> Calibration:
        w, st, su, n = self.profiles(rgb)
        ok = n >= max(3, 0.25 * np.median(n[n > 0]) if (n > 0).any() else 3)
        wz = np.where(ok, w - w[ok].mean(), 0.0) if ok.any() else np.zeros_like(w)
        stz = np.where(ok, st / (np.abs(st[ok]).mean() + 1e-6), 0.0) if ok.any() else np.zeros_like(st)
        mw = self.m_white[self.idx]
        ms = self.m_stripe[self.idx]
        mu = self.m_surround[self.idx]
        score = (mw * wz[None, :]).sum(axis=1) * 4.0 / (wz.std() + 1e-3)
        score += (ms * stz[None, :]).sum(axis=1) * 0.02
        score -= (((mu - su[None, :]) ** 2) * ok[None, :]).sum(axis=1) * 0.05
        if prior_cx is not None:
            score -= 0.5 * ((self.cands - prior_cx) / prior_sigma) ** 2 * (np.abs(score).max() / 200.0)
        i = int(np.argmax(score))
        cx = float(self.cands[i])
        if 0 < i < len(score) - 1:  # sub-step refinement by parabola
            a, b, c = score[i - 1], score[i], score[i + 1]
            den = a - 2 * b + c
            if den < 0:
                cx += float(0.5 * (a - c) / den) * float(self.cands[1] - self.cands[0])
        return Calibration(cx=cx, score=float(score[i]), mapping=self.geom.at(cx))
