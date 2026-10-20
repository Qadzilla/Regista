"""Read kit numbers: the local twin of the Azure AI Vision OCR path.

The interface is ``KitNumberReader.read(crops) -> list[NumberReading]``, where each reading holds
probabilities for the tens digit (or none) and the units digit. ``decode`` turns a reading into a
kit number, optionally constrained to the numbers on the team sheet (the ``lineup_prior``
evidence in the event contract), which is how a real system would use OCR too.

Implemented backend: ``DigitClassifierReader``, two small scikit-learn MLP heads (tens: none/1-9,
units: 0-9) on 20x20 crops normalised as "distance from the shirt colour", so a white number on a
red shirt and a black number on a yellow shirt look the same to the model. Training data:

- crops cut from rendered training matches at detected player positions, labelled with the
  roster number of the ground-truth player there (numbers 1-11 in the synthetic league), and
- extra discs drawn with the renderer's own font for every number 1-99, run through blur, chroma
  subsampling and JPEG, so the model can read numbers the league never shows.

``AzureVisionOCRReader`` marks where the cloud path plugs in. It is not implemented and makes no
calls: on real footage, crop the player's back/torso from the person box, send batches to the
Azure AI Vision Read (OCR) API, and map the returned digit strings and confidences into
``NumberReading`` objects. The decoding and the tracker vote stay as they are.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

CROP = 20
DEFAULT_MODELS_DIR = Path("models/vision")
READER_FILE = "kit_number_reader.joblib"


@dataclass
class NumberReading:
    tens: np.ndarray    # (10,) P(no tens digit), P(1), ..., P(9)
    units: np.ndarray   # (10,) P(0) ... P(9)

    def number_logp(self, n: int) -> float:
        t, u = divmod(int(n), 10)
        return float(np.log(self.tens[t] + 1e-6) + np.log(self.units[u] + 1e-6))


class KitNumberReader(Protocol):
    def read(self, crops: np.ndarray) -> list[NumberReading]: ...


def decode(reading: NumberReading, candidates: list[int] | None = None) -> tuple[int, float]:
    """Most likely number (and its probability among the candidates). Without candidates: any of 1-99."""
    cands = candidates or list(range(1, 100))
    lp = np.array([reading.number_logp(n) for n in cands])
    p = np.exp(lp - lp.max())
    p /= p.sum()
    i = int(p.argmax())
    return cands[i], float(p[i])


# ---------------------------------------------------------------------------- crops

def crop_disc(rgb: np.ndarray, u: float, v: float, r: float, kit_lab: np.ndarray) -> np.ndarray:
    """A CROP x CROP float32 patch of the disc at (u, v) with radius r: per-pixel CIELAB distance from the shirt
    colour (numbers bright, shirt dark), with everything outside the disc zeroed."""
    import cv2

    from regista.vision.detect import rgb_to_lab

    half = r * 1.05
    src = np.float32([[u - half, v - half], [u + half, v - half], [u - half, v + half]])
    dst = np.float32([[0, 0], [CROP, 0], [0, CROP]])
    m = cv2.getAffineTransform(src, dst)
    patch = cv2.warpAffine(rgb, m, (CROP, CROP), flags=cv2.INTER_AREA if r * 2 > CROP else cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)
    d = np.linalg.norm(rgb_to_lab(patch) - kit_lab, axis=2) / 60.0
    yy, xx = np.mgrid[0:CROP, 0:CROP]
    c = (CROP - 1) / 2.0
    inside = ((xx - c) ** 2 + (yy - c) ** 2) <= (CROP / 2.0 * 0.92) ** 2
    return np.where(inside, np.clip(d, 0, 1.5), 0.0).astype(np.float32)


def synth_discs(n: int, seed: int = 0, r_range: tuple[float, float] = (4.5, 15.0)) -> tuple[np.ndarray, np.ndarray]:
    """Draw ``n`` discs exactly as the renderer does (same font, outline, text colour rule) with random numbers 1-99,
    radii, kit colours, sub-pixel positions and video-like degradation; return (crops, numbers)."""
    import cv2
    from PIL import Image, ImageDraw

    from regista.render.draw import font
    from regista.vision.detect import is_light, rgb_to_lab

    rng = np.random.default_rng(seed)
    crops = np.zeros((n, CROP, CROP), dtype=np.float32)
    nums = rng.integers(1, 100, size=n)
    # Bias toward the numbers football actually uses, without dropping any.
    common = rng.random(n) < 0.35
    nums[common] = rng.integers(1, 24, size=int(common.sum()))
    for i in range(n):
        r = float(rng.uniform(*r_range))
        size = int(math.ceil(r * 4 + 8))
        size += size % 2
        grass = (36, 122, 54) if rng.random() < 0.5 else (42, 134, 60)
        img = Image.new("RGB", (size, size), grass)
        d = ImageDraw.Draw(img)
        fill = tuple(int(v) for v in rng.integers(0, 256, size=3))
        text = (17, 17, 17) if is_light(fill) else (255, 255, 255)
        sx = size / 2 + float(rng.uniform(-0.5, 0.5))
        sy = size / 2 + r + float(rng.uniform(-0.5, 0.5))
        s = r / 7.0 * 0.5  # style scale implied by this radius at 640 px wide
        d.ellipse([sx - r, sy - 2 * r, sx + r, sy], fill=fill, outline=(20, 20, 20), width=max(1, int(1.5 * s)))
        d.text((sx, sy - r), str(int(nums[i])), font=font(int(r * 1.15), bold=True), fill=text, anchor="mm")
        a = np.asarray(img)
        if rng.random() < 0.7:  # chroma subsampling, as yuv420p video does
            ycc = cv2.cvtColor(a, cv2.COLOR_RGB2YCrCb)
            small = cv2.resize(ycc[..., 1:], (size // 2, size // 2), interpolation=cv2.INTER_AREA)
            ycc[..., 1:] = cv2.resize(small, (size, size), interpolation=cv2.INTER_LINEAR)
            a = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
        if rng.random() < 0.5:
            a = cv2.GaussianBlur(a, (0, 0), float(rng.uniform(0.3, 0.7)))
        if rng.random() < 0.7:
            ok, enc = cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, int(rng.integers(50, 95))])
            a = cv2.cvtColor(cv2.imdecode(enc, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        ju, jv = rng.normal(0, 0.08 * r, size=2)
        jr = r * float(rng.uniform(0.9, 1.1))
        crops[i] = crop_disc(a, sx + ju, sy - r + jv, jr, rgb_to_lab(np.array(fill)))
    return crops, nums


# ---------------------------------------------------------------------------- the local reader

@dataclass
class DigitClassifierReader:
    tens_clf: Any = None
    units_clf: Any = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def read(self, crops: np.ndarray) -> list[NumberReading]:
        if len(crops) == 0:
            return []
        X = np.asarray(crops, dtype=np.float32).reshape(len(crops), -1)
        pt = _full_proba(self.tens_clf, X, 10)
        pu = _full_proba(self.units_clf, X, 10)
        return [NumberReading(tens=pt[i], units=pu[i]) for i in range(len(X))]

    def fit(self, crops: np.ndarray, numbers: np.ndarray, seed: int = 0, max_iter: int = 60,
            hidden: tuple[int, ...] = (256, 128)) -> DigitClassifierReader:
        import warnings

        from sklearn.exceptions import ConvergenceWarning
        from sklearn.neural_network import MLPClassifier

        X = np.asarray(crops, dtype=np.float32).reshape(len(crops), -1)
        numbers = np.asarray(numbers, dtype=int)
        tens, units = numbers // 10, numbers % 10
        from threadpoolctl import threadpool_limits

        # Small dense layers: BLAS threads cost more in synchronisation than they save.
        with warnings.catch_warnings(), threadpool_limits(2):
            warnings.simplefilter("ignore", ConvergenceWarning)  # early stopping on a validation split decides when to stop
            self.tens_clf = MLPClassifier(hidden_layer_sizes=hidden, alpha=1e-4, max_iter=max_iter, early_stopping=True,
                                          random_state=seed).fit(X, tens)
            self.units_clf = MLPClassifier(hidden_layer_sizes=hidden, alpha=1e-4, max_iter=max_iter, early_stopping=True,
                                           random_state=seed + 1).fit(X, units)
        self.metrics["train_crops"] = int(len(X))
        return self

    def save(self, path: Path | str = DEFAULT_MODELS_DIR) -> Path:
        import joblib

        path = Path(path)
        if path.suffix != ".joblib":
            path = path / READER_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODELS_DIR) -> DigitClassifierReader:
        import joblib

        path = Path(path)
        if path.suffix != ".joblib":
            path = path / READER_FILE
        obj = joblib.load(path)
        if not isinstance(obj, cls):
            raise TypeError(f"{path} does not hold a DigitClassifierReader")
        return obj


def _full_proba(clf: Any, X: np.ndarray, n: int) -> np.ndarray:
    p = clf.predict_proba(X)
    out = np.full((len(X), n), 1e-4, dtype=np.float64)
    for j, c in enumerate(clf.classes_):
        out[:, int(c)] = p[:, j]
    return out / out.sum(axis=1, keepdims=True)


class AzureVisionOCRReader:
    """Placeholder for the cloud OCR backend (Azure AI Vision Read). Not implemented; never calls Azure.

    To implement on real footage: batch torso crops (upscaled to at least 50 px high), call the Read
    API through ``azure-ai-vision-imageanalysis`` with keyless (Entra ID) auth, keep only 1-2 digit
    results, and convert each result's confidence into a ``NumberReading`` (put the confidence on the
    read digits and spread the rest uniformly). Then ``decode`` with the team sheet as candidates,
    exactly as for the local reader."""

    def read(self, crops: np.ndarray) -> list[NumberReading]:  # pragma: no cover - deliberately not implemented
        raise NotImplementedError("Azure AI Vision OCR backend is planned, not implemented; use DigitClassifierReader")
