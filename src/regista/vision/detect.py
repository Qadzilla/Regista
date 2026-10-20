"""Player and ball detection in pitch views, plus team assignment by kit colour.

**Synthetic footage (implemented).** Regista's renderer draws each player as a disc in the
team's kit colour with the kit number on it, and the ball as a small white disc. Detection is
classical computer vision:

1. **Kit palette.** The four kit colours from the match header (home, home goalkeeper, away,
   away goalkeeper) seed a palette; ``KitPalette.adapt`` re-estimates each colour from the
   footage by clustering the pixels near it (k-means in CIELAB), because encoded video never
   shows the nominal hex value. Team assignment is "which palette cluster does this blob
   belong to", so it is kit-colour clustering anchored to the roster.
2. **Discs.** Per kit colour: a CIELAB distance mask, holes filled (the number is printed in a
   contrasting colour), thin structures removed (pitch lines, the renderer's holder ring and
   name label), connected components kept when round and full. Components bigger than one
   disc are split with k-means on pixel coordinates, using the disc radius the camera model
   predicts for that image row.
3. **Ball.** A small, round, bright, unsaturated blob after a morphological opening that
   deletes 1-px lines and number strokes. The best-scoring candidate wins, with a bonus for
   staying near the previous frame's ball.

**Real footage (what changes).** Players are people, not discs: swap ``DiscDetector`` for a
person detector (a YOLO-class model fine-tuned on broadcast football and hosted in Microsoft
Foundry, or Azure AI Vision object detection) that returns boxes; keep everything after it. The
ground contact point becomes the bottom-centre of the box, and team assignment keeps the same
kit-colour clustering, run on the torso region of each box (referees and goalkeepers become
extra clusters). The ball needs a dedicated small-object detector with temporal filtering;
broadcast balls are 3-10 px and often blurred or occluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from regista.vision.pitch import MainCameraGeometry

Record = dict[str, Any]


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """CIELAB (L 0..100) for uint8 RGB of any shape (..., 3)."""
    import cv2

    a = np.asarray(rgb, dtype=np.float32).reshape(-1, 1, 3) / 255.0
    return cv2.cvtColor(a, cv2.COLOR_RGB2LAB).reshape(np.asarray(rgb).shape[:-1] + (3,))


def is_light(rgb: tuple[int, int, int] | np.ndarray) -> bool:
    r, g, b = (float(v) for v in rgb)
    return 0.299 * r + 0.587 * g + 0.114 * b > 150


GRASS_RGB = [(36, 122, 54), (42, 134, 60)]
NEUTRALS_RGB = [(24, 30, 34), (236, 244, 236), (250, 250, 250)]  # off-pitch surround, lines, ball
SHADOW_RGB = [(22, 73, 32), (25, 80, 36)]  # players' shadows on grass (grass at 60%)
GREYS_RGB = [(v, v, v) for v in (15, 60, 100, 140, 180, 215)] + [(150, 156, 166)]  # achromatic: goal frames, text, shadows


@dataclass
class Kit:
    team_id: str
    is_gk: bool
    nominal: tuple[int, int, int]
    lab: np.ndarray
    threshold: float = 20.0

    @property
    def light(self) -> bool:
        return is_light(self.nominal)


@dataclass
class KitPalette:
    kits: list[Kit]
    adapted: bool = False

    @classmethod
    def from_match(cls, match: Record) -> KitPalette:
        kits = []
        for team in match["teams"]:
            kits.append(Kit(team["team_id"], False, hex_rgb(team["kit"]["primary"]), rgb_to_lab(np.array(hex_rgb(team["kit"]["primary"])))))
            kits.append(Kit(team["team_id"], True, hex_rgb(team["kit"]["gk"]), rgb_to_lab(np.array(hex_rgb(team["kit"]["gk"])))))
        pal = cls(kits)
        pal._set_thresholds()
        return pal

    def _set_thresholds(self) -> None:
        others = [rgb_to_lab(np.array(c)) for c in GRASS_RGB + SHADOW_RGB + NEUTRALS_RGB]
        for k in self.kits:
            d = [float(np.linalg.norm(k.lab - o)) for o in others]
            d += [float(np.linalg.norm(k.lab - j.lab)) for j in self.kits if j is not k]
            k.threshold = float(np.clip(0.48 * min(d), 6.0, 24.0))

    def neutrals_lab(self) -> np.ndarray:
        return np.stack([rgb_to_lab(np.array(c)) for c in GRASS_RGB + SHADOW_RGB + NEUTRALS_RGB + GREYS_RGB]).astype(np.float32)

    def nearest(self, lab: np.ndarray, neutrals: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Nearest of (kits + scene neutrals) per pixel of an (N, 3) Lab array: (kit index or -1, distance)."""
        kits = np.stack([k.lab for k in self.kits]).astype(np.float32)
        cents = np.vstack([kits, self.neutrals_lab() if neutrals is None else neutrals])
        d = np.linalg.norm(lab[:, None, :] - cents[None, :, :], axis=2)
        nearest = d.argmin(axis=1)
        return np.where(nearest < len(kits), nearest, -1), d[np.arange(len(lab)), nearest]

    def adapt(self, frames: list[np.ndarray], band: tuple[int, int] | None = None, max_shift: float = 12.0, **_ignored: Any) -> KitPalette:
        """Re-estimate each kit colour from footage, because encoded video never shows the nominal hex value.

        Pixels are clustered by nearest colour against the kits *and* the scene neutrals (grass, shadows,
        lines, greys), so blurred edge pixels between a shirt and the grass fall to the grass rather than
        dragging the shirt colour toward it; each kit's new centre is the median of its cluster's core."""
        if not frames:
            return self
        neutrals = self.neutrals_lab()
        pix: list[list[np.ndarray]] = [[] for _ in self.kits]
        for f in frames:
            reg = f[band[0]:band[1]] if band else f
            lab = rgb_to_lab(reg).reshape(-1, 3)
            gl = rgb_to_lab(np.array(GRASS_RGB))
            cand = np.minimum(np.linalg.norm(lab - gl[0], axis=1), np.linalg.norm(lab - gl[1], axis=1)) > 6.0
            lab = lab[cand]
            if not len(lab):
                continue
            idx, dist = self.nearest(lab, neutrals)
            for k in range(len(self.kits)):
                core = (idx == k) & (dist < 0.6 * self.kits[k].threshold + 6.0)
                if core.any():
                    pix[k].append(lab[core])
        for k, kit in zip(pix, self.kits):
            if not k:
                continue
            P = np.vstack(k)
            if len(P) < 30:
                continue
            c = np.median(P, axis=0)
            shift = float(np.linalg.norm(c - kit.lab))
            if shift > max_shift:
                c = kit.lab + (c - kit.lab) * (max_shift / shift)
            kit.lab = c.astype(np.float32)
        self._set_thresholds()
        self.adapted = True
        return self


@dataclass
class Detection:
    kind: str                  # "player" | "ball"
    u: float                   # centre, pixels
    v: float
    r: float                   # radius, pixels
    foot_u: float              # ground contact point, pixels
    foot_v: float
    kit: int = -1              # index into the palette
    team_id: str | None = None
    is_gk: bool = False
    score: float = 1.0
    occluded_below: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.u - self.r, self.v - self.r, 2 * self.r, 2 * self.r)


class DiscDetector:
    """Detect player discs and the ball in a pitch view (see module docstring)."""

    def __init__(self, palette: KitPalette, width: int, height: int, geom: MainCameraGeometry | None = None):
        self.palette = palette
        self.width, self.height = width, height
        self.geom = geom
        s = width / 1280.0
        self.base_r = 14.0 * s
        self.ball_r = max(3.0, 5.5 * s)
        self.r_min = max(2.5, 0.55 * self.base_r)
        self.r_max = 1.6 * self.base_r
        self.max_kit_dist = 38.0
        self._cents: np.ndarray | None = None
        if geom is not None:
            # From the top of a far-touchline disc (radius floored at 0.72 of the base) to just below the near touchline.
            # Rows above stay out: that is where broadcasters put the score bug.
            self.band = (max(0, int(geom.y_top - 2.2 * 0.72 * self.base_r) - 1), min(height, int(geom.y_bottom + 4)))
        else:
            self.band = (int(0.12 * height), int(0.87 * height))

    def expected_r(self, v_centre: float) -> float:
        """Disc radius the main camera model predicts for a disc centred on image row ``v_centre``."""
        if self.geom is None:
            return getattr(self, "_r_frame", None) or self.base_r * 0.9
        g = self.geom
        r = self.base_r
        for _ in range(3):
            d = float(np.clip(g.depth_of_row(v_centre + r), 0.0, 1.0))
            r = self.base_r * max(0.72, 1.0 - g.k * d)
        return r

    # ------------------------------------------------------------------ players
    def label_pixels(self, lab: np.ndarray, rgb: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        """Nearest-colour labelling: each pixel gets the closest of the kit colours and the scene neutrals
        (grass, surround, white, greys). Returns (kit index or -1, distance to that kit). Pixels that are
        plainly grass are skipped, which is most of a wide shot."""
        kits = np.stack([k.lab for k in self.palette.kits])
        if self._cents is None:
            self._cents = self.palette.neutrals_lab()
        cents = np.vstack([kits, self._cents]).astype(np.float32)
        h, w = lab.shape[:2]
        kit_idx = np.full((h, w), -1, dtype=np.int32)
        dist = np.full((h, w), 1e3, dtype=np.float32)
        cand = np.ones((h, w), dtype=bool)
        if rgb is not None:
            gl = rgb_to_lab(np.array(GRASS_RGB))
            near_grass = np.minimum(np.linalg.norm(lab - gl[0], axis=2), np.linalg.norm(lab - gl[1], axis=2)) < 6.0
            kit_near_grass = min(float(np.linalg.norm(k.lab - g)) for k in self.palette.kits for g in gl) < 12.0
            cand = ~near_grass if not kit_near_grass else cand
        px = lab[cand]
        if len(px):
            d = np.linalg.norm(px[:, None, :] - cents[None, :, :], axis=2)
            nearest = d.argmin(axis=1)
            nk = len(kits)
            kit_idx[cand] = np.where(nearest < nk, nearest, -1)
            dist[cand] = d[np.arange(len(px)), nearest]
        return kit_idx, dist

    def detect_players(self, rgb: np.ndarray) -> list[Detection]:
        import cv2

        y0, y1 = self.band
        band = rgb[y0:y1]
        lab = rgb_to_lab(band)
        kit_idx, kdist = self.label_pixels(lab, band)
        out: list[Detection] = []
        close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        comps = []
        for ki, kit in enumerate(self.palette.kits):
            raw = ((kit_idx == ki) & (kdist < self.max_kit_dist)).astype(np.uint8)
            if raw.sum() < 4:
                continue
            m = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, close_k)
            m = _fill_holes(m)
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, open_k)
            n, labels, stats, cents = cv2.connectedComponentsWithStats(m, connectivity=8)
            for c in range(1, n):
                x, y, w, h, area = stats[c]
                if area < np.pi * self.r_min ** 2 * 0.6:
                    continue
                comp = labels[y:y + h, x:x + w] == c
                fill = float(raw[y:y + h, x:x + w][comp].mean())  # a ring or outline is mostly hollow
                if fill < 0.3:
                    continue
                # A ring drawn around another player's disc (the renderer marks the ball holder that way) encloses
                # pixels of a different kit: it is decoration, not a player.
                # Blurred number strokes can also look like another kit, but only a few pixels' worth: a ring
                # is hollow (low fill) and holds a whole disc of the other colour.
                if fill < 0.6:
                    inner = kit_idx[y:y + h, x:x + w][comp & (raw[y:y + h, x:x + w] == 0)]
                    if np.count_nonzero((inner >= 0) & (inner != ki)) > 0.25 * area:
                        continue
                comps.append((ki, kit, x, y, w, h, area, comp, fill, float(cents[c][1])))
        # Without a camera model (replays, other angles) disc size comes from the frame: the median isolated disc.
        self._r_frame = None
        if self.geom is None:
            rs = [np.sqrt(a / np.pi) + 0.8 for (_ki, _k, _x, _y, w, h, a, _c, f, _v) in comps if f > 0.5 and 0.75 < w / max(h, 1) < 1.33]
            self._r_frame = float(np.median(rs)) if rs else self.base_r * 0.9
        for ki, kit, x, y, w, h, area, comp, fill, cy in comps:
            vc = y0 + cy
            r_exp = self.expected_r(vc)
            single = np.pi * r_exp ** 2
            k = int(round(area / (0.9 * single))) if area > 1.45 * single else 1
            if k <= 1:
                if w > 2.6 * r_exp or h > 2.6 * r_exp:  # elongated: not one disc
                    k = 2
            if k <= 1:
                r_meas = float(np.sqrt(area / np.pi))
                u = x + w / 2.0
                top = y0 + y
                occl = area < 0.72 * single
                v = top + r_exp if occl else vc  # partly covered (usually by the ball at the feet): trust the top edge
                out.append(Detection("player", u, v, r_exp, u, v + r_exp, ki, kit.team_id, kit.is_gk,
                                     score=min(1.0, fill), occluded_below=occl, extra={"r_meas": r_meas}))
            else:
                ys, xs = np.nonzero(comp)
                pts = np.stack([xs + x, ys + y + y0], axis=1).astype(np.float32)
                k = min(k, max(1, len(pts) // 12))
                centres = _kmeans_points(pts, k)
                for cu, cv_ in centres:
                    r_e = self.expected_r(cv_)
                    out.append(Detection("player", float(cu), float(cv_), r_e, float(cu), float(cv_) + r_e, ki, kit.team_id, kit.is_gk,
                                         score=0.7 * fill, extra={"split": k}))
        return out

    # ------------------------------------------------------------------ ball
    def detect_ball(self, rgb: np.ndarray, players: list[Detection], prev: tuple[float, float] | None = None) -> Detection | None:
        """The ball is the brightest, unsaturated, *filled* round spot of the right size. A distance transform of
        the white mask separates it from pitch lines and number strokes (both about one pixel thick) even when
        it touches them, which it does whenever a player has it at their feet."""
        import cv2

        y0, y1 = self.band
        band = rgb[y0:y1]
        hsv = cv2.cvtColor(band, cv2.COLOR_RGB2HSV)
        white = ((hsv[..., 2] > 215) & (hsv[..., 1] < 60)).astype(np.uint8)
        if not white.any():
            return None
        dt = cv2.distanceTransform(white, cv2.DIST_L2, 3)
        r_in = self.ball_r - 0.5  # the ball's dark outline is not white
        peaks = (dt >= 0.72 * r_in) & (dt == cv2.dilate(dt, np.ones((5, 5), np.uint8)))
        ys, xs = np.nonzero(peaks)
        if len(xs) == 0:
            return None
        best, best_score = None, -1e9
        for x, y in zip(xs, ys):
            u, v = float(x), y0 + float(y)
            depth = float(dt[y, x])
            score = -abs(np.log(depth / r_in)) - 0.6 * max(0.0, _elongation(white, x, y, int(round(2.2 * self.ball_r))) - 1.6)
            for p in players:  # numbers sit at a disc's centre; the ball sits at a disc's feet
                if (u - p.u) ** 2 + (v - p.v) ** 2 < (0.4 * p.r) ** 2:
                    score -= 1.5
            if prev is not None:
                d = np.hypot(u - prev[0], v - prev[1])
                score += 0.8 * np.exp(-d / (6 * self.ball_r))
            if score > best_score:
                best, best_score = (u, v), score
        if best is None:
            return None
        u, v = best
        return Detection("ball", u, v, self.ball_r, u, v + self.ball_r, score=float(best_score))

    def detect(self, rgb: np.ndarray, prev_ball: tuple[float, float] | None = None) -> tuple[list[Detection], Detection | None]:
        players = _dedupe(self.detect_players(rgb))
        return players, self.detect_ball(rgb, players, prev_ball)


def _elongation(mask: np.ndarray, x: int, y: int, rad: int) -> float:
    """Elongation (sqrt of the eigenvalue ratio) of the mask pixels in a window: ~1 for a blob, large for a line."""
    h, w = mask.shape
    win = mask[max(0, y - rad): min(h, y + rad + 1), max(0, x - rad): min(w, x + rad + 1)]
    ys, xs = np.nonzero(win)
    if len(xs) < 4:
        return 1.0
    ev = np.linalg.eigvalsh(np.cov(np.stack([xs, ys]).astype(float)))
    return float(np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-2)))


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    import cv2

    h, w = mask.shape
    flood = mask.copy()
    ff = np.zeros((h + 2, w + 2), np.uint8)
    # Flood the background from the border; whatever is not reached and not mask is a hole.
    flood = np.pad(flood, 1)
    cv2.floodFill(flood, np.zeros((h + 4, w + 4), np.uint8), (0, 0), 1)
    holes = (flood[1:-1, 1:-1] == 0)
    del ff
    return (mask.astype(bool) | holes).astype(np.uint8)


def _kmeans_points(pts: np.ndarray, k: int) -> list[tuple[float, float]]:
    import cv2

    if k <= 1 or len(pts) < k:
        c = pts.mean(axis=0)
        return [(float(c[0]), float(c[1]))]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1)
    _ret, _lab, centres = cv2.kmeans(pts, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    return [(float(c[0]), float(c[1])) for c in centres]


def _dedupe(dets: list[Detection]) -> list[Detection]:
    """Drop duplicates: fragments of one disc in the same kit (the ball at a player's feet can cut a disc in
    two), and different kits claiming the same spot. Keeps the fuller, bigger detection."""
    keep: list[Detection] = []
    for d in sorted(dets, key=lambda d: (-d.score, -d.extra.get("r_meas", d.r))):
        dup = False
        for k in keep:
            dd = (d.u - k.u) ** 2 + (d.v - k.v) ** 2
            lim = 1.1 * max(d.r, k.r) if d.kit == k.kit else 0.9 * min(d.r, k.r)
            if dd < lim ** 2:
                dup = True
                break
        if not dup:
            keep.append(d)
    return keep


def detect_closeup(rgb: np.ndarray, palette: KitPalette, max_dist: float = 14.0) -> list[Detection]:
    """Big player cards in a closeup shot: the round, solid kit-coloured shapes covering a good part of the frame.

    On real footage a closeup is a person filling the frame; the equivalent step is a person detector
    plus torso crop, and identity comes from the number on the shirt or the on-screen name caption."""
    import cv2

    h, w = rgb.shape[:2]
    scale = 160.0 / w
    small = cv2.resize(rgb, (160, max(1, int(round(h * scale)))), interpolation=cv2.INTER_AREA)
    lab = rgb_to_lab(small)
    out: list[Detection] = []
    for ki, kit in enumerate(palette.kits):
        m = (np.linalg.norm(lab - kit.lab, axis=2) < max_dist).astype(np.uint8)
        m = _fill_holes(cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))))
        n, labels, stats, cents = cv2.connectedComponentsWithStats(m, connectivity=8)
        for c in range(1, n):
            x, y, bw, bh, area = stats[c]
            if area < (0.12 * small.shape[0]) ** 2 or not (0.7 < bw / max(bh, 1) < 1.4):
                continue
            if not (0.6 < area / float(bw * bh) < 0.9):  # a disc fills pi/4 of its box
                continue
            r = float(np.sqrt(area / np.pi)) / scale
            u, v = float(cents[c][0]) / scale, float(cents[c][1]) / scale
            out.append(Detection("player", u, v, r, u, v + r, ki, kit.team_id, kit.is_gk, score=1.0, extra={"closeup": True}))
    return _dedupe(out)
