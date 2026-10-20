"""The broadcast main-camera model, shared by the generator and the renderer.

The generator uses it to decide which players are in frame (and so get tracks); the
renderer uses it to decide where to draw them. Keeping one model in one place means
a player is drawn exactly when the vision layer would have seen them.

The model is a wide camera on the near touchline, high up: ``window`` metres of pitch
length are visible along the near touchline, shrinking by factor ``k`` toward the far
touchline, so the far side shows more pitch per pixel (mild perspective).
"""

from __future__ import annotations

PITCH_L = 105.0
PITCH_W = 68.0

MAIN_WINDOW_M = 52.0  # metres of pitch length visible at the near touchline
MAIN_K = 0.30         # perspective shrink toward the far touchline (0 = none)


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def camera_centre(ball_x: float, window: float = MAIN_WINDOW_M) -> float:
    """Where the camera points: the ball, except it never looks past the goal lines."""
    if window >= PITCH_L:
        return PITCH_L / 2
    return clamp(ball_x, window / 2, PITCH_L - window / 2)


def depth(py: float, flip: bool = False) -> float:
    d = py / PITCH_W
    return 1.0 - d if flip else d


def screen_x(px: float, py: float, cx: float, window: float = MAIN_WINDOW_M, k: float = MAIN_K, mirror: bool = False, flip: bool = False) -> float:
    """Normalised horizontal screen position: 0 is the left frame edge, 1 the right."""
    s = (1.0 - k * depth(py, flip)) / window
    dx = (px - cx) * s
    return 0.5 + (-dx if mirror else dx)


def in_frame(px: float, py: float, cx: float, window: float = MAIN_WINDOW_M, k: float = MAIN_K, margin: float = 0.01) -> bool:
    x = screen_x(px, py, cx, window, k)
    return -margin <= x <= 1.0 + margin
