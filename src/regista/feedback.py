"""Learning from Zaid: human verdicts on clips, and a watchability model retrained from them.

This is plan steps 3, 5 and 6 (CLAUDE.md §2.3) in their honest form: Regista asks a person when
it is unsure, stores every verdict as an ``annotation`` record, and retrains the model that scores
clips from those verdicts. It is learning from human feedback, not reinforcement learning, and the
docs say so.

Pieces
------
- ``record_verdict``     one human decision on one clip, as a schema-valid ``annotation`` with a snapshot
                         of what the reviewer saw (so training never depends on regenerating the match)
- ``needs_review``       the Label agent's rule for pausing and asking: the rule-based prior and the model
                         disagree, or the score sits on the keep/drop boundary
- ``WatchabilityModel``  logistic regression over tags, cut reason, and duration, trained on verdicts;
                         saved as readable JSON (coefficients per feature), never a pickle
- ``evaluate``           how well each scorer (rules-v0, Foundry, learned) agrees with the human

    python -m regista.feedback status
    python -m regista.feedback train
    python -m regista.feedback evaluate data/synthetic/sample/syn_0294
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from regista.schema import SCHEMA_VERSION, events_validator, iter_jsonl

Record = dict[str, Any]

FEEDBACK_DIR = Path(os.environ.get("REGISTA_FEEDBACK_DIR", "data/feedback"))  # where real verdicts and the model live
ANNOTATIONS_FILE = "annotations.jsonl"
MODEL_FILE = "watchability-model.json"
MIN_SAMPLES = 8           # fewer verdicts than this and the model refuses to train
DISAGREEMENT = 0.30       # |prior - model| at or above this asks the human
BOUNDARY = (0.40, 0.60)   # scores in this band are undecided and ask the human
REGULARISATION = 3.0      # logistic regression C; chosen on held-out agreement with tens of verdicts
VERDICTS = {"keep": "confirm", "drop": "reject", "fix": "correct"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------- verdicts

def snapshot(clip: Record, label: Record) -> Record:
    """What the reviewer saw: enough to train on without the match files."""
    return {
        "match_id": clip["match_id"], "clip_id": clip["id"], "player_id": clip["player_id"],
        "reason": clip["reason"], "duration_s": round(clip["t_end"] - clip["t"], 2),
        "tags": list(label.get("tags", [])), "title": label.get("title", ""),
        "model": label.get("model", ""), "watchability": float(label.get("watchability", 0.0)),
        "prior_watchability": float(label.get("prior_watchability", label.get("watchability", 0.0))),
    }


def record_verdict(clip: Record, label: Record, verdict: str, *, watchability: float | None = None, tags: list[str] | None = None,
                   note: str = "", annotator: str = "zaid", path: Path | str | None = None, n: int | None = None) -> Record:
    """Store one human verdict. ``verdict`` is keep, drop, or fix (fix = keep, but with corrected tags or score)."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(VERDICTS)}")
    if watchability is not None and not 0.0 <= watchability <= 1.0:
        raise ValueError("watchability must be between 0 and 1")
    correction: Record = {"keep": verdict != "drop"}
    if watchability is not None:
        correction["watchability"] = round(float(watchability), 3)
    if tags is not None:
        correction["tags"] = [t.strip().lower().replace(" ", "_") for t in tags if t.strip()]
    path = Path(path) if path else FEEDBACK_DIR / ANNOTATIONS_FILE
    existing = sum(1 for _ in iter_jsonl(path)) if path.exists() else 0
    rec: Record = {
        "type": "annotation", "id": f"an_{(n or existing + 1):06d}", "match_id": clip["match_id"], "schema_version": SCHEMA_VERSION,
        "source": "human", "confidence": 1, "t": clip["t"], "target_id": label["id"], "target_type": "label",
        "verdict": VERDICTS[verdict], "correction": correction, "annotator": annotator, "annotated_at": _now(),
        "context": snapshot(clip, label),
    }
    if note:
        rec["note"] = note
    problems = events_validator().errors(rec)
    if problems:
        raise ValueError(f"invalid annotation: {problems[0]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_annotations(path: Path | str | None = None, *, humans_only: bool = True) -> list[Record]:
    path = Path(path) if path else FEEDBACK_DIR / ANNOTATIONS_FILE
    if not path.exists():
        return []
    rows = [r for r in iter_jsonl(path) if r.get("type") == "annotation" and r.get("target_type") == "label" and "context" in r]
    return [r for r in rows if r.get("source") == "human"] if humans_only else rows


def latest_per_label(annotations: Iterable[Record]) -> list[Record]:
    """A reviewer may change their mind: the newest verdict on each clip wins."""
    latest: dict[tuple[str, str, str], Record] = {}
    for a in annotations:
        ctx = a.get("context", {})
        latest[(a["match_id"], ctx.get("player_id", ""), a["target_id"])] = a
    return list(latest.values())


def target_of(a: Record) -> float:
    """The training target: an explicit score when the reviewer gave one, else 1 for keep and 0 for drop."""
    c = a.get("correction", {})
    if "watchability" in c:
        return float(c["watchability"])
    return 1.0 if c.get("keep", a["verdict"] != "reject") else 0.0


# ---------------------------------------------------------------------------- when to ask

def needs_review(watchability: float, prior: float | None = None) -> str | None:
    """Why the human should look at this clip, or None. Used by the Label agent to pause the workflow."""
    if prior is not None and abs(watchability - prior) >= DISAGREEMENT:
        return f"prior {prior:.2f} and model {watchability:.2f} disagree"
    if BOUNDARY[0] <= watchability <= BOUNDARY[1]:
        return f"score {watchability:.2f} is on the keep/drop boundary"
    return None


# ---------------------------------------------------------------------------- the model

def features(tags: Iterable[str], reason: str, duration_s: float, prior: float | None = None) -> dict[str, float]:
    """Tags, cut reason, duration, and the rules score. With the rules score as an input the model learns
    corrections to the rules rather than starting from nothing, which matters with tens of verdicts."""
    f: dict[str, float] = {f"tag:{t}": 1.0 for t in tags if not t.endswith("_appearance") and t != "on_ball_main"}
    f[f"reason:{reason}"] = 1.0
    f["duration_s"] = min(float(duration_s), 30.0) / 30.0
    if prior is not None:
        f["rules_prior"] = float(prior)
    return f


@dataclass
class WatchabilityModel:
    """Logistic regression from clip features to "a human would keep this". Readable and diffable as JSON."""

    feature_names: list[str] = field(default_factory=list)
    coef: list[float] = field(default_factory=list)
    intercept: float = 0.0
    n_samples: int = 0
    trained_at: str = ""
    version: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"learned-v{self.version} ({self.n_samples} verdicts)"

    @property
    def trained(self) -> bool:
        return bool(self.feature_names)

    def score(self, tags: Iterable[str], reason: str, duration_s: float, prior: float | None = None) -> float:
        f = features(tags, reason, duration_s, prior)
        z = self.intercept + sum(c * f.get(n, 0.0) for n, c in zip(self.feature_names, self.coef))
        return round(1.0 / (1.0 + math.exp(-z)), 3)

    def explain(self, tags: Iterable[str], reason: str, duration_s: float, prior: float | None = None, top: int = 3) -> str:
        f = features(tags, reason, duration_s, prior)
        contrib = sorted(((c * f.get(n, 0.0), n) for n, c in zip(self.feature_names, self.coef) if f.get(n)), key=lambda x: -abs(x[0]))
        parts = [f"{n.split(':', 1)[-1].replace('_', ' ')} {'+' if v >= 0 else '-'}{abs(v):.2f}" for v, n in contrib[:top]]
        return f"learned from {self.n_samples} verdicts: " + (", ".join(parts) if parts else "no known features")

    # -- persistence
    def to_json(self) -> Record:
        return {"version": self.version, "trained_at": self.trained_at, "n_samples": self.n_samples, "intercept": self.intercept,
                "features": dict(zip(self.feature_names, self.coef)), "metrics": self.metrics}

    @classmethod
    def from_json(cls, data: Record) -> WatchabilityModel:
        feats = data.get("features", {})
        return cls(feature_names=list(feats), coef=[float(v) for v in feats.values()], intercept=float(data.get("intercept", 0.0)),
                   n_samples=int(data.get("n_samples", 0)), trained_at=data.get("trained_at", ""), version=int(data.get("version", 0)),
                   metrics=data.get("metrics", {}))

    def save(self, path: Path | str | None = None) -> Path:
        path = Path(path) if path else FEEDBACK_DIR / MODEL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path | str | None = None) -> WatchabilityModel | None:
        path = Path(path) if path else FEEDBACK_DIR / MODEL_FILE
        if not path.exists():
            return None
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))


def train(annotations: list[Record], *, previous: WatchabilityModel | None = None) -> WatchabilityModel:
    """Fit on the latest verdict per label. Raises ValueError when there is too little or one-sided feedback."""
    rows = latest_per_label(annotations)
    if len(rows) < MIN_SAMPLES:
        raise ValueError(f"need at least {MIN_SAMPLES} verdicts to train, have {len(rows)}")
    y_bin = [1 if target_of(a) >= 0.5 else 0 for a in rows]
    if len(set(y_bin)) < 2:
        raise ValueError("verdicts are all keep or all drop; the model needs both to learn the difference")
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score

    feats = [features(a["context"]["tags"], a["context"]["reason"], a["context"]["duration_s"], a["context"]["prior_watchability"]) for a in rows]
    names = sorted({k for f in feats for k in f})
    X = [[f.get(n, 0.0) for n in names] for f in feats]
    clf = LogisticRegression(C=REGULARISATION, max_iter=2000)
    clf.fit(X, y_bin)
    folds = min(5, min(y_bin.count(0), y_bin.count(1)))
    cv = float(cross_val_score(LogisticRegression(C=REGULARISATION, max_iter=2000), X, y_bin, cv=folds).mean()) if folds >= 2 else None
    model = WatchabilityModel(feature_names=names, coef=[round(float(c), 4) for c in clf.coef_[0]], intercept=round(float(clf.intercept_[0]), 4),
                              n_samples=len(rows), trained_at=_now(), version=(previous.version + 1) if previous else 1)
    model.metrics = {"train_accuracy": round(float(clf.score(X, y_bin)), 3), "cv_accuracy": round(cv, 3) if cv is not None else None,
                     "keep": y_bin.count(1), "drop": y_bin.count(0)}
    return model


# ---------------------------------------------------------------------------- evaluation

def evaluate(annotations: list[Record], model: WatchabilityModel | None = None) -> dict[str, Any]:
    """Agreement with the human, per scorer that saw these clips: the label as reviewed, its rules prior, and the learned model."""
    rows = latest_per_label(annotations)
    if not rows:
        return {"n": 0}
    out: dict[str, Any] = {"n": len(rows)}

    def agree(score_of) -> dict[str, float]:
        hits, err = 0, 0.0
        for a in rows:
            s, t = score_of(a), target_of(a)
            hits += (s >= 0.5) == (t >= 0.5)
            err += abs(s - t)
        return {"agreement": round(hits / len(rows), 3), "mean_abs_error": round(err / len(rows), 3)}

    by_model: dict[str, list[Record]] = {}
    for a in rows:
        by_model.setdefault(a["context"].get("model", "?"), []).append(a)
    out["as_reviewed"] = agree(lambda a: a["context"]["watchability"])
    out["as_reviewed_by_model"] = {m: len(v) for m, v in by_model.items()}
    out["rules_prior"] = agree(lambda a: a["context"]["prior_watchability"])
    if model and model.trained:
        out[model.name] = agree(lambda a: model.score(a["context"]["tags"], a["context"]["reason"], a["context"]["duration_s"],
                                                      a["context"]["prior_watchability"]))
    return out


# ---------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human feedback and the learned watchability model.")
    parser.add_argument("command", choices=["status", "train", "evaluate"])
    parser.add_argument("--dir", type=Path, default=FEEDBACK_DIR, help="feedback directory (annotations.jsonl, watchability-model.json)")
    args = parser.parse_args(argv)
    ann_path, model_path = args.dir / ANNOTATIONS_FILE, args.dir / MODEL_FILE
    annotations = load_annotations(ann_path)
    model = WatchabilityModel.load(model_path)
    if args.command == "status":
        rows = latest_per_label(annotations)
        keep = sum(1 for a in rows if target_of(a) >= 0.5)
        print(f"{len(annotations)} verdicts ({len(rows)} distinct clips: {keep} keep, {len(rows) - keep} drop) in {ann_path}")
        print(f"model: {model.name if model else 'none yet'}" + (f"  {model.metrics}" if model else ""))
        return 0
    if args.command == "train":
        try:
            new = train(annotations, previous=model)
        except ValueError as exc:
            print(f"not trained: {exc}")
            return 1
        print(f"trained {new.name}: {new.metrics} -> {new.save(model_path)}")
        return 0
    print(json.dumps(evaluate(annotations, model), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
