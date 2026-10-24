"""Shot agent: cut the broadcast into shots and say what each one shows.

Pipeline, all on 128x72 frames:

1. **Per-frame features** that do not depend on one broadcaster's graphics package: grass
   fraction (overall and on a 4x4 grid), a coarse 8x6 grid of mean Lab colour and luminance
   texture, hue/saturation/value histograms, edge density, dark and white fractions, and
   motion against the previous frame (overall, on a grid, and averaged over a second, which is
   how slow motion shows up).
2. **Cut detection** from colour-histogram change between consecutive frames (total variation
   distance of hue/saturation histograms on a 2x2 grid, plus mean absolute grey difference).
   The threshold is learned from training footage by maximising boundary F1.
3. **A scikit-learn classifier** (histogram gradient boosting) trained on rendered frames
   labelled from ``camera_segment`` ground truth: main / replay / highlight / closeup / crowd /
   graphic / other.
4. **Temporal smoothing into segments**: shots run between detected cuts; each shot takes the
   class with the highest mean probability; a sustained change of class inside a shot (a cut
   the detector missed) also splits it; adjacent ``main`` shots merge (the director never cuts
   from the main camera to the main camera); shots shorter than ``min_shot_s`` fold into a
   neighbour.

Output: ``camera_segment`` records that validate against ``regista-events.schema.json``.

Real footage: the code path is identical, and the model retrains from human-labelled segments
(``train_shot_model`` takes any list of (video, segments)). What changes is what the classifier
leans on. On Regista's renderer the strongest replay cue is the red REPLAY badge plus slow
motion; real broadcasts signal replays with a branded wipe/stinger, slow motion, and unusual
angles, and have dissolves that a hard-cut detector misses (a dissolve detector, or a
learned boundary model such as TransNetV2 hosted in Foundry, is the upgrade path). Expect to
relabel at least a few matches per broadcaster before trusting the numbers here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from regista.schema import LEGACY_SCHEMA_VERSION as SCHEMA_VERSION  # vision output uses nothing added in 0.2.0
from regista.vision.frames import iter_frames, probe

Record = dict[str, Any]

FEATURE_SIZE = (128, 72)
CUT_SIZE = (320, 180)
KINDS = ["main", "replay", "highlight", "closeup", "crowd", "graphic", "bench", "other"]
DEFAULT_MODELS_DIR = Path("models/vision")
SHOT_MODEL_FILE = "shot_model.joblib"


# ---------------------------------------------------------------------------- features

def _grid_means(a: np.ndarray, gx: int, gy: int) -> np.ndarray:
    """Mean of a 2-D (or H x W x C) array over a gy x gx grid, flattened."""
    h, w = a.shape[:2]
    ys = np.linspace(0, h, gy + 1).astype(int)
    xs = np.linspace(0, w, gx + 1).astype(int)
    out = []
    for i in range(gy):
        for j in range(gx):
            cell = a[ys[i]:ys[i + 1], xs[j]:xs[j + 1]]
            out.append(cell.reshape(-1, *a.shape[2:]).mean(axis=0))
    return np.asarray(out, dtype=np.float32).ravel()


def _grid_std(a: np.ndarray, gx: int, gy: int) -> np.ndarray:
    h, w = a.shape[:2]
    ys = np.linspace(0, h, gy + 1).astype(int)
    xs = np.linspace(0, w, gx + 1).astype(int)
    return np.asarray([a[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].std() for i in range(gy) for j in range(gx)], dtype=np.float32)


def hs_histograms(rgb: np.ndarray) -> np.ndarray:
    """Hue x saturation histograms on a 2x2 grid plus the whole frame, each normalised to sum 1. Shape (5, 64)."""
    import cv2

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, w = rgb.shape[:2]
    regions = [hsv, hsv[: h // 2, : w // 2], hsv[: h // 2, w // 2:], hsv[h // 2:, : w // 2], hsv[h // 2:, w // 2:]]
    out = []
    for reg in regions:
        hist = cv2.calcHist([reg], [0, 1], None, [16, 4], [0, 180, 0, 256]).ravel()
        out.append(hist / max(1.0, hist.sum()))
    return np.asarray(out, dtype=np.float32)


@dataclass
class _CutState:
    hist: np.ndarray
    grey: np.ndarray
    edges: np.ndarray
    edges_dil: np.ndarray
    fg: np.ndarray
    grass: float


def _cut_state(rgb: np.ndarray) -> _CutState:
    """What the cut detector remembers about a frame (computed at CUT_SIZE)."""
    import cv2

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    grass = (H >= 30) & (H <= 90) & (S > 60) & (V > 50)
    h = rgb.shape[0]
    band = slice(int(0.27 * h), int(0.84 * h))  # the pitch band of a wide view, away from score bug and captions
    fg = (~grass) & (S > 80) & (V > 60)
    fg[: band.start] = False
    fg[band.stop:] = False
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(grey, 50, 120) > 0
    edges_dil = cv2.dilate(edges.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    return _CutState(hist=hs_histograms(rgb), grey=grey, edges=edges, edges_dil=edges_dil, fg=fg, grass=float(grass.mean()))


def cut_features(prev: _CutState | None, cur: _CutState) -> np.ndarray:
    """Evidence of a hard cut between two consecutive frames.

    Colour-histogram change (total variation of hue x saturation histograms, whole frame and the
    most-changed quadrant) is the primary cue. Grey-level difference and the edge change ratio
    catch cuts between similar-coloured shots. The motion-compensated foreground jump catches the
    hardest case in broadcast football: a cut between two wide shots with the same framing but a
    different moment (back-to-back replays or highlights), where only the players jump."""
    import cv2

    if prev is None:
        return np.zeros(8, dtype=np.float32)
    tv = 0.5 * np.abs(cur.hist - prev.hist).sum(axis=1)
    grey = float(np.abs(cur.grey.astype(np.int16) - prev.grey.astype(np.int16)).mean()) / 64.0
    e_in = float((cur.edges & ~prev.edges_dil).sum()) / max(1, int(cur.edges.sum()))
    e_out = float((prev.edges & ~cur.edges_dil).sum()) / max(1, int(prev.edges.sum()))
    jump = 0.0
    if cur.grass > 0.3 and prev.grass > 0.3 and cur.fg.sum() > 30:
        h = cur.grey.shape[0]
        band = slice(int(0.27 * h), int(0.84 * h))
        (dx, dy), _ = cv2.phaseCorrelate(prev.grey[band].astype(np.float32), cur.grey[band].astype(np.float32))
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(prev.fg, m, (cur.fg.shape[1], cur.fg.shape[0]))
        covered = cv2.dilate(shifted, np.ones((5, 5), np.uint8)) > 0
        jump = float(((cur.fg > 0) & ~covered).sum()) / float(cur.fg.sum())
    return np.asarray([tv[0], tv[1:].max(), min(grey, 2.0), max(e_in, e_out), jump, prev.grass, cur.grass,
                       abs(cur.grass - prev.grass)], dtype=np.float32)


def _cut_context(C: np.ndarray) -> np.ndarray:
    """Each cut feature relative to its median over the previous five frames (an adaptive threshold)."""
    n = len(C)
    rel = np.zeros((n, 5), dtype=np.float32)
    for i in range(n):
        base = np.median(C[max(0, i - 5): i, :5], axis=0) if i else np.zeros(5)
        rel[i] = C[i, :5] / (base + 0.02)
    return np.hstack([C, np.log1p(rel)])


def frame_features(rgb: np.ndarray, prev_grey: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """Feature vector for one 128x72 frame, and its grey image (for the next frame's motion)."""
    import cv2

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    H, S, V = hsv[..., 0].astype(np.int16), hsv[..., 1].astype(np.int16), hsv[..., 2].astype(np.int16)
    grass = ((H >= 30) & (H <= 90) & (S > 60) & (V > 50)).astype(np.float32)
    dark = (V < 50).astype(np.float32)
    white = ((V > 200) & (S < 40)).astype(np.float32)
    edges = (cv2.Canny(grey, 60, 150) > 0).astype(np.float32)
    hue_hist = np.bincount((H // 15).ravel().clip(0, 11), weights=(S / 255.0).ravel(), minlength=12)[:12]
    hue_hist = hue_hist / max(1e-6, hue_hist.sum())
    sat_hist = np.bincount((S // 64).ravel(), minlength=4)[:4] / S.size
    val_hist = np.bincount((V // 64).ravel(), minlength=4)[:4] / V.size
    if prev_grey is None:
        motion = np.zeros_like(grey, dtype=np.float32)
    else:
        motion = np.abs(grey.astype(np.float32) - prev_grey.astype(np.float32)) / 255.0
    feats = np.concatenate([
        [grass.mean(), dark.mean(), white.mean(), edges.mean(), motion.mean(), grey.std() / 255.0],
        _grid_means(grass, 4, 4),
        _grid_means(lab / 255.0, 8, 6),
        _grid_std(grey.astype(np.float32) / 255.0, 8, 6),
        _grid_means(edges, 4, 4),
        _grid_means(dark, 4, 4),
        _grid_means(white, 4, 4),
        _grid_means(motion, 4, 4),
        hue_hist, sat_hist, val_hist,
    ]).astype(np.float32)
    return feats, grey


@dataclass
class FeatureTrack:
    """Per-frame shot features and cut features for one video."""

    times: np.ndarray        # (n,)
    frames: np.ndarray       # (n,) frame indices
    X: np.ndarray            # (n, d) per-frame features, with temporal context appended
    C: np.ndarray            # (n, k) evidence of a cut between frame i-1 and frame i
    fps: float               # sampled frames per second
    duration_s: float


def _context(X: np.ndarray, motion_col: int, fps: float) -> np.ndarray:
    """Append temporal context: mean motion over ~1 s, and features averaged over ~0.6 s."""
    n = len(X)
    k = max(1, int(round(fps * 0.5)))
    m = X[:, motion_col]
    cs = np.concatenate([[0.0], np.cumsum(m)])
    lo = np.clip(np.arange(n) - k, 0, n)
    hi = np.clip(np.arange(n) + k + 1, 0, n)
    win_motion = (cs[hi] - cs[lo]) / np.maximum(1, hi - lo)
    k2 = max(1, int(round(fps * 0.3)))
    csX = np.vstack([np.zeros((1, X.shape[1])), np.cumsum(X, axis=0)])
    lo2 = np.clip(np.arange(n) - k2, 0, n)
    hi2 = np.clip(np.arange(n) + k2 + 1, 0, n)
    smooth = (csX[hi2] - csX[lo2]) / np.maximum(1, hi2 - lo2)[:, None]
    return np.hstack([X, smooth, win_motion[:, None]]).astype(np.float32)


def extract_features(video: Path | str, sample_fps: float | None = 10.0) -> FeatureTrack:
    """Decode ``video`` once at 320x180; cut features there, shot features at 128x72."""
    from regista.vision.frames import resize

    info = probe(video)
    feats, times, idx, cuts = [], [], [], []
    prev_grey = None
    prev_cut: _CutState | None = None
    for i, t, rgb in iter_frames(video, sample_fps=sample_fps, size=CUT_SIZE):
        cs = _cut_state(rgb)
        cuts.append(cut_features(prev_cut, cs))
        small = resize(rgb, FEATURE_SIZE)
        f, grey = frame_features(small, prev_grey)
        feats.append(f)
        times.append(t)
        idx.append(i)
        prev_grey, prev_cut = grey, cs
    fps = min(info.fps, sample_fps) if sample_fps else info.fps
    X = _context(np.asarray(feats, dtype=np.float32), 4, fps)
    C = _cut_context(np.asarray(cuts, dtype=np.float32))
    return FeatureTrack(times=np.asarray(times), frames=np.asarray(idx), X=X, C=C, fps=fps, duration_s=info.duration_s)


# ---------------------------------------------------------------------------- labels from ground truth

def labels_for(times: np.ndarray, segments: list[Record]) -> np.ndarray:
    """The segment kind at each time (``segments`` are {t, t_end, kind} covering the video)."""
    starts = np.asarray([s["t"] for s in segments])
    pos = np.searchsorted(starts, times + 1e-6, side="right") - 1
    pos = np.clip(pos, 0, len(segments) - 1)
    return np.asarray([segments[p]["kind"] for p in pos])


# ---------------------------------------------------------------------------- model

def cut_labels(times: np.ndarray, segments: list[Record]) -> np.ndarray:
    """1 where a segment boundary falls between frame i-1 and frame i."""
    y = np.zeros(len(times), dtype=int)
    for s in segments[1:]:
        j = int(np.searchsorted(times, s["t"] - 1e-6))
        if 0 < j < len(times):
            y[j] = 1
    return y


@dataclass
class ShotModel:
    clf: Any                       # frame classifier: features -> shot kind
    classes: list[str]
    cut_clf: Any = None            # cut classifier: cut features -> P(cut between i-1 and i)
    cut_threshold: float = 0.5
    min_shot_s: float = 0.6
    switch_s: float = 1.5          # a class change sustained this long inside a shot splits it
    sample_fps: float = 10.0
    trained_on: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path | str = DEFAULT_MODELS_DIR) -> Path:
        import joblib

        path = Path(path)
        if path.suffix != ".joblib":
            path = path / SHOT_MODEL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODELS_DIR) -> ShotModel:
        import joblib

        path = Path(path)
        if path.suffix != ".joblib":
            path = path / SHOT_MODEL_FILE
        model = joblib.load(path)
        if not isinstance(model, cls):
            raise TypeError(f"{path} does not hold a ShotModel")
        return model

    def frame_proba(self, ft: FeatureTrack) -> np.ndarray:
        return self.clf.predict_proba(ft.X)

    def cut_proba(self, ft: FeatureTrack) -> np.ndarray:
        if self.cut_clf is None:
            return np.clip(ft.C[:, 0] * 2, 0, 1)
        p = self.cut_clf.predict_proba(ft.C)[:, 1]
        p[0] = 0.0
        return p

    def segment(self, ft: FeatureTrack) -> list[Record]:
        return segment_track(ft, self.frame_proba(ft), self.cut_proba(ft), self.classes, self.cut_threshold, self.min_shot_s,
                             self.switch_s)

    def predict(self, video: Path | str) -> list[Record]:
        """``{t, t_end, kind, confidence}`` segments covering the whole video."""
        return self.segment(extract_features(video, self.sample_fps))


def _peaks(cut: np.ndarray, threshold: float, min_gap: int) -> list[int]:
    idx = [i for i in range(1, len(cut)) if cut[i] >= threshold and cut[i] == cut[max(0, i - min_gap): i + min_gap + 1].max()]
    out: list[int] = []
    for i in idx:
        if not out or i - out[-1] > min_gap:
            out.append(i)
    return out


def segment_track(ft: FeatureTrack, proba: np.ndarray, cut_p: np.ndarray, classes: list[str], cut_threshold: float,
                  min_shot_s: float = 0.6, switch_s: float = 1.5) -> list[Record]:
    """Turn per-frame class probabilities and cut probabilities into contiguous labelled segments."""
    n = len(ft.times)
    if n == 0:
        return []
    dt = 1.0 / ft.fps
    bounds = sorted({0, n} | set(_peaks(cut_p, cut_threshold, max(1, int(round(0.3 * ft.fps))))))
    # Split shots where the smoothed class changes and stays changed for switch_s (a cut the detector missed).
    k = max(1, int(round(0.5 * ft.fps)))
    cs = np.vstack([np.zeros((1, proba.shape[1])), np.cumsum(proba, axis=0)])
    lo = np.clip(np.arange(n) - k, 0, n)
    hi = np.clip(np.arange(n) + k + 1, 0, n)
    lab = ((cs[hi] - cs[lo]) / (hi - lo)[:, None]).argmax(axis=1)
    run = max(2, int(round(switch_s * ft.fps)))
    extra = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        i = a
        while i < b:
            j = i
            while j < b and lab[j] == lab[i]:
                j += 1
            if i > a and j - i >= run:
                extra.append(i)
            i = j
    bounds = sorted(set(bounds) | set(extra))
    shots = [{"a": a, "b": b, "p": proba[a:b].mean(axis=0)} for a, b in zip(bounds[:-1], bounds[1:])]
    # Fold very short shots into the neighbour whose class they most resemble.
    min_n = max(1, int(round(min_shot_s * ft.fps)))
    changed = True
    while changed and len(shots) > 1:
        changed = False
        for i, s in enumerate(shots):
            if s["b"] - s["a"] >= min_n:
                continue
            cands = [j for j in (i - 1, i + 1) if 0 <= j < len(shots)]
            j = max(cands, key=lambda j: float(np.dot(shots[j]["p"], s["p"])))
            lo_i, hi_i = (j, i) if j < i else (i, j)
            a, b = shots[lo_i]["a"], shots[hi_i]["b"]
            shots[lo_i:hi_i + 1] = [{"a": a, "b": b, "p": proba[a:b].mean(axis=0)}]
            changed = True
            break
    # Adjacent main shots merge: the director never cuts from the main camera to the main camera.
    merged: list[dict[str, Any]] = []
    for s in shots:
        kind = classes[int(np.argmax(s["p"]))]
        if merged and merged[-1]["kind"] == kind == "main":
            m = merged[-1]
            m["b"] = s["b"]
            m["p"] = proba[m["a"]:m["b"]].mean(axis=0)
            continue
        merged.append({**s, "kind": kind})
    out = []
    for s in merged:
        t0 = float(ft.times[s["a"]])
        t1 = float(ft.times[s["b"]]) if s["b"] < n else float(ft.duration_s)
        t1 = max(t1, t0 + dt)
        out.append({"t": round(t0, 3), "t_end": round(t1, 3), "kind": s["kind"], "confidence": round(float(np.max(s["p"])), 3)})
    out[0]["t"] = 0.0
    out[-1]["t_end"] = round(max(out[-1]["t_end"], float(ft.duration_s)), 3)
    for a, b in zip(out[:-1], out[1:]):
        b["t"] = a["t_end"]
    return out


def segments_to_records(segments: list[Record], match_id: str, prefix: str = "cs_v") -> list[Record]:
    """Schema-valid ``camera_segment`` records (``source: vision``)."""
    recs = []
    for n, s in enumerate(segments, start=1):
        recs.append({"type": "camera_segment", "id": f"{prefix}{n:05d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
                     "source": "vision", "confidence": float(min(1.0, max(0.0, s.get("confidence", 0.5)))),
                     "t": float(s["t"]), "t_end": float(s["t_end"]), "kind": s["kind"]})
    return recs


# ---------------------------------------------------------------------------- training and evaluation

def boundary_prf(pred: list[Record], truth: list[Record], tol: float = 0.5) -> dict[str, float]:
    """Precision, recall, F1 of segment boundaries (interior starts) matched one-to-one within ``tol`` seconds."""
    pb = [s["t"] for s in pred[1:]]
    tb = [s["t"] for s in truth[1:]]
    used: set[int] = set()
    tp = 0
    for b in pb:
        best, bj = None, None
        for j, c in enumerate(tb):
            if j in used:
                continue
            d = abs(b - c)
            if d <= tol and (best is None or d < best):
                best, bj = d, j
        if bj is not None:
            used.add(bj)
            tp += 1
    p = tp / len(pb) if pb else 1.0
    r = tp / len(tb) if tb else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tp": tp, "pred": len(pb), "truth": len(tb)}


def frame_report(pred_labels: np.ndarray, true_labels: np.ndarray) -> dict[str, Any]:
    classes = sorted(set(true_labels) | set(pred_labels), key=lambda k: KINDS.index(k) if k in KINDS else 99)
    per = {}
    for c in classes:
        m = true_labels == c
        if m.sum():
            per[c] = {"accuracy": round(float((pred_labels[m] == c).mean()), 4), "frames": int(m.sum())}
    confusion = {c: {d: int(((true_labels == c) & (pred_labels == d)).sum()) for d in classes if ((true_labels == c) & (pred_labels == d)).any()}
                 for c in classes if (true_labels == c).any()}
    return {"accuracy": round(float((pred_labels == true_labels).mean()), 4), "per_class": per, "confusion": confusion}


def _tune_threshold(tracks: list[FeatureTrack], probas: list[np.ndarray], cuts: list[np.ndarray], truths: list[list[Record]],
                    classes: list[str], min_shot_s: float, switch_s: float) -> float:
    best_t, best_f = 0.5, -1.0
    for th in np.arange(0.1, 0.95, 0.05):
        tp = npred = ntrue = 0
        for ft, pr, cp, tr in zip(tracks, probas, cuts, truths):
            m = boundary_prf(segment_track(ft, pr, cp, classes, float(th), min_shot_s, switch_s), tr)
            tp += m["tp"]
            npred += m["pred"]
            ntrue += m["truth"]
        p = tp / npred if npred else 0.0
        r = tp / ntrue if ntrue else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        if f > best_f + 1e-9:
            best_t, best_f = float(th), f
    return round(best_t, 3)


def train_shot_model(items: Iterable[tuple[Path | str, list[Record]]], sample_fps: float = 10.0, *, max_iter: int = 200,
                     seed: int = 0) -> ShotModel:
    """Train on ``(video, segments)`` pairs, where segments are ``{t, t_end, kind}`` covering each video.

    Two classifiers are fitted: frame -> shot kind, and frame pair -> cut. On synthetic footage the
    segments come from the generator (``Truth.segments``); on real footage from a human marking
    shots in a review tool. The cut threshold is then tuned for boundary F1 on the same videos
    (out-of-fold cut probabilities would be stricter; with one scalar the optimism is small)."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    tracks, truths, names = [], [], []
    Xs, ys, Cs, cys = [], [], [], []
    for video, segs in items:
        ft = extract_features(video, sample_fps)
        tracks.append(ft)
        truths.append(segs)
        names.append(Path(video).name)
        Xs.append(ft.X)
        ys.append(labels_for(ft.times, segs))
        Cs.append(ft.C)
        cys.append(cut_labels(ft.times, segs))
    X, y = np.vstack(Xs), np.concatenate(ys)
    C, cy = np.vstack(Cs), np.concatenate(cys)
    clf = HistGradientBoostingClassifier(max_iter=max_iter, learning_rate=0.1, max_leaf_nodes=31, class_weight="balanced",
                                         random_state=seed)
    clf.fit(X, y)
    cut_clf = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.1, max_leaf_nodes=15, random_state=seed)
    cut_clf.fit(C, cy)
    classes = [str(c) for c in clf.classes_]
    model = ShotModel(clf=clf, classes=classes, cut_clf=cut_clf, sample_fps=sample_fps, trained_on=names)
    probas = [clf.predict_proba(ft.X) for ft in tracks]
    cuts = [model.cut_proba(ft) for ft in tracks]
    model.cut_threshold = _tune_threshold(tracks, probas, cuts, truths, classes, model.min_shot_s, model.switch_s)
    model.metrics = {"train_frames": int(len(y)), "train_cuts": int(cy.sum()),
                     "train_class_counts": {c: int((y == c).sum()) for c in classes}}
    return model


def evaluate_shot_model(model: ShotModel, items: Iterable[tuple[Path | str, list[Record]]], tol: float = 0.5) -> dict[str, Any]:
    """Frame accuracy per class (after segmentation) and boundary P/R/F1 within ``tol`` seconds, pooled over videos."""
    preds, trues = [], []
    raw_preds = []
    tp = npred = ntrue = 0
    per_video = []
    for video, segs in items:
        ft = extract_features(video, model.sample_fps)
        proba = model.frame_proba(ft)
        out = segment_track(ft, proba, model.cut_proba(ft), model.classes, model.cut_threshold, model.min_shot_s, model.switch_s)
        y_true = labels_for(ft.times, segs)
        y_pred = labels_for(ft.times, out)
        preds.append(y_pred)
        trues.append(y_true)
        raw_preds.append(np.asarray(model.classes)[proba.argmax(axis=1)])
        b = boundary_prf(out, segs, tol)
        tp += b["tp"]
        npred += b["pred"]
        ntrue += b["truth"]
        per_video.append({"video": Path(video).name, "frame_accuracy": round(float((y_pred == y_true).mean()), 4), "boundaries": b,
                          "segments_pred": len(out), "segments_true": len(segs)})
    y_pred = np.concatenate(preds)
    y_true = np.concatenate(trues)
    p = tp / npred if npred else 1.0
    r = tp / ntrue if ntrue else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    rep = frame_report(y_pred, y_true)
    rep["raw_frame_accuracy"] = round(float((np.concatenate(raw_preds) == y_true).mean()), 4)
    rep["boundaries"] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "tolerance_s": tol, "tp": tp,
                         "pred": npred, "truth": ntrue}
    rep["per_video"] = per_video
    return rep
