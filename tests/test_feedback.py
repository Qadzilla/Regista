"""Human verdicts are stored faithfully, the model learns from them, and the Label agent knows when to ask.

The "reviewer" in these tests is a deterministic stand-in defined here. No verdict in this file is
attributed to a real person; the annotator is "test-reviewer".
"""

from __future__ import annotations

import json

import pytest

from regista.clips import StreamIndex, cut_clips, label_clips
from regista.feedback import (MIN_SAMPLES, WatchabilityModel, evaluate, load_annotations, needs_review, record_verdict, target_of,
                              train)
from regista.schema import clips_validator, events_validator
from regista.synth import generate

REVIEWER = "test-reviewer"


@pytest.fixture(scope="module")
def corpus():
    """Clips and rules labels for several players across a few matches."""
    rows = []
    for seed in (294, 5, 77, 140):
        r = generate(seed=seed, minutes=3.0, track_hz=1.0)
        index = StreamIndex.build(r.stream)
        for pid in ("t_home_09", "t_home_10", "t_away_09", "t_home_07", "t_away_11"):
            clips = cut_clips(index, pid)
            rows += list(zip(clips, label_clips(index, clips)))
    return rows


def reviewer_keeps(label) -> bool:
    """A consistent taste the model should be able to learn: goals, shots, nutmegs and replays are keepers."""
    return bool({"goal", "shot", "nutmeg", "skill_move", "take_on"} & set(label["tags"])) or label["tags"][-1] == "replay_appearance"


def test_verdicts_are_schema_valid_human_annotations(corpus, tmp_path):
    path = tmp_path / "annotations.jsonl"
    clip, label = corpus[0]
    a = record_verdict(clip, label, "fix", watchability=0.8, tags=["Goal", "nutmeg "], note="great finish", annotator=REVIEWER, path=path)
    assert events_validator().is_valid(a)
    assert a["source"] == "human" and a["verdict"] == "correct" and a["annotator"] == REVIEWER
    assert a["correction"] == {"keep": True, "watchability": 0.8, "tags": ["goal", "nutmeg"]}
    assert a["context"]["tags"] == label["tags"] and a["context"]["clip_id"] == clip["id"]
    b = record_verdict(clip, label, "drop", annotator=REVIEWER, path=path)
    assert b["id"] == "an_000002" and target_of(b) == 0.0 and target_of(a) == 0.8
    assert [r["id"] for r in load_annotations(path)] == ["an_000001", "an_000002"]
    with pytest.raises(ValueError):
        record_verdict(clip, label, "maybe", path=path)
    with pytest.raises(ValueError):
        record_verdict(clip, label, "fix", watchability=1.5, path=path)


def test_model_refuses_too_little_or_one_sided_feedback(corpus, tmp_path):
    path = tmp_path / "a.jsonl"
    for clip, label in corpus[: MIN_SAMPLES - 1]:
        record_verdict(clip, label, "keep", annotator=REVIEWER, path=path)
    with pytest.raises(ValueError, match="at least"):
        train(load_annotations(path))
    clip, label = corpus[MIN_SAMPLES]
    record_verdict(clip, label, "keep", annotator=REVIEWER, path=path)
    with pytest.raises(ValueError, match="both"):
        train(load_annotations(path))


def test_model_learns_the_reviewers_taste_and_beats_the_rules(corpus, tmp_path):
    """Two-fold: train on each half, score the other. With ~30 verdicts a single split swings by >10 points,
    so the bar is: every fold beats the hand-set rules, and the average held-out agreement is at least 0.85."""
    folds = []
    for k, (train_rows, held_out) in enumerate(((corpus[::2], corpus[1::2]), (corpus[1::2], corpus[::2]))):
        path = tmp_path / f"fold{k}.jsonl"
        for clip, label in train_rows:
            record_verdict(clip, label, "keep" if reviewer_keeps(label) else "drop", annotator=REVIEWER, path=path)
        model = train(load_annotations(path))
        assert model.trained and model.n_samples == len(train_rows) and model.version == 1

        def agreement(score):
            return sum((score(lb, c) >= 0.5) == reviewer_keeps(lb) for c, lb in held_out) / len(held_out)

        learned = agreement(lambda lb, c: model.score(lb["tags"], c["reason"], c["t_end"] - c["t"], lb["watchability"]))
        rules = agreement(lambda lb, c: lb["watchability"])
        assert learned > rules, (k, learned, rules)
        folds.append(learned)
    assert sum(folds) / len(folds) >= 0.85, folds
    # Persistence is readable JSON with one coefficient per feature, and round-trips exactly.
    saved = model.save(tmp_path / "model.json")
    data = json.loads(saved.read_text())
    assert "tag:goal" in data["features"] and data["features"]["tag:goal"] > 0
    again = WatchabilityModel.load(saved)
    c, lb = corpus[0]
    assert again.score(lb["tags"], c["reason"], 5.0, 0.4) == model.score(lb["tags"], c["reason"], 5.0, 0.4)
    assert again.name.startswith("learned-v1")


def test_retraining_bumps_the_version_and_latest_verdict_wins(corpus, tmp_path):
    path = tmp_path / "a.jsonl"
    for clip, label in corpus[:30]:
        record_verdict(clip, label, "keep" if reviewer_keeps(label) else "drop", annotator=REVIEWER, path=path)
    v1 = train(load_annotations(path))
    clip, label = corpus[0]
    record_verdict(clip, label, "drop" if reviewer_keeps(label) else "keep", annotator=REVIEWER, path=path)  # change of mind
    v2 = train(load_annotations(path), previous=v1)
    assert v2.version == 2 and v2.n_samples == v1.n_samples == 30


def test_label_clips_uses_the_learned_model_as_prior(corpus, tmp_path):
    path = tmp_path / "a.jsonl"
    for clip, label in corpus:
        record_verdict(clip, label, "keep" if reviewer_keeps(label) else "drop", annotator=REVIEWER, path=path)
    model = train(load_annotations(path))
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    index = StreamIndex.build(r.stream)
    clips = cut_clips(index, "t_home_09")
    labels = label_clips(index, clips, scorer=model)
    v = clips_validator()
    assert all(v.is_valid(lb) for lb in labels)
    assert all(lb["model"] == model.name for lb in labels)
    assert all("learned from" in lb["explanation"] and "Rules alone gave" in lb["explanation"] for lb in labels)
    assert all(0.0 <= lb["prior_watchability"] <= 1.0 for lb in labels)


def test_needs_review_rules():
    assert needs_review(0.9, prior=0.4).startswith("prior")
    assert needs_review(0.5).startswith("score")
    assert needs_review(0.95, prior=0.9) is None
    assert needs_review(0.1) is None


def test_evaluate_reports_agreement_per_scorer(corpus, tmp_path):
    path = tmp_path / "a.jsonl"
    for clip, label in corpus:
        record_verdict(clip, label, "keep" if reviewer_keeps(label) else "drop", annotator=REVIEWER, path=path)
    anns = load_annotations(path)
    model = train(anns)
    report = evaluate(anns, model)
    assert report["n"] == len(corpus)
    assert {"as_reviewed", "rules_prior", model.name} <= set(report)
    assert report[model.name]["agreement"] >= report["rules_prior"]["agreement"]
