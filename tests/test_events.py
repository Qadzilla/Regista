"""Event spotting: the generator stages take-ons and nutmegs so a camera could see them, without changing a single
event; captions can be switched off; and the spotter finds events from vision-shaped positions. No video needed."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from regista.schema import events_validator  # noqa: E402
from regista.synth import generate  # noqa: E402
from regista.vision.events import (EventSpotter, Positions, evaluate_events, generated_example_set, merge_reports,  # noqa: E402
                                   pseudo_identity_frames, spot_events)
from regista.vision.possession import infer_possessions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_choreography_never_changes_the_match():
    committed = [json.loads(line) for line in open(ROOT / "data/synthetic/sample/syn_0294/events.jsonl")]
    assert generate(seed=294, minutes=3.0, track_hz=1.0).stream == committed  # the committed sample, exactly
    fast = generate(seed=294, minutes=3.0, track_hz=10.0).stream  # appearances and confidences depend on the rate; play does not
    for kind in ("event", "possession"):
        assert [r for r in fast if r["type"] == kind] == [r for r in committed if r["type"] == kind]


def _positions(r, hz):
    pos = defaultdict(dict)
    for tr in r.tracks:
        if tr.get("pitch"):
            pos[round(tr["t"] * hz)]["ball" if tr["object"] == "ball" else tr["player_id"]] = (tr["pitch"]["x"], tr["pitch"]["y"])
    return pos


def test_a_nutmeg_goes_through_the_defender_and_a_take_on_goes_round_him():
    seen = {"nutmeg": [], "beat": []}
    for seed in (294, 101, 102, 103, 104, 105):
        r = generate(seed=seed, minutes=3.0, track_hz=10.0)
        pos = _positions(r, 10)
        for e in r.stream:
            if e["type"] != "event" or e["event_type"] != "take_on" or e["outcome"] != "success":
                continue
            d, a = e["related_player_id"], e["player_id"]
            frames = [pos.get(round(e["t"] * 10) + k, {}) for k in range(9)]
            ball_def = min(math.dist(f["ball"], f[d]) for f in frames if "ball" in f and d in f)
            carrier_def = max(math.dist(f[a], f[d]) for f in frames[3:6] if a in f and d in f)  # mid-run
            seen["nutmeg" if "nutmeg" in (e.get("qualifiers") or []) else "beat"].append((ball_def, carrier_def))
    assert seen["nutmeg"] and seen["beat"]
    assert all(b < 0.6 and c > 1.0 for b, c in seen["nutmeg"]), seen["nutmeg"]  # ball between the legs, carrier round
    assert all(b > 1.0 for b, _c in seen["beat"]), seen["beat"]                 # ball and carrier round together


def test_captions_can_be_switched_off():
    import numpy as np

    from regista.render.draw import Style, render_frame
    from regista.render.scene import Scene

    r = generate(seed=294, minutes=3.0, track_hz=2.0)
    scene = Scene.from_records(r.stream, r.tracks)
    nut = next(e for e in r.stream if e.get("event_type") == "nutmeg")
    t = nut["t"] + 0.5
    assert scene.caption_at(t) is not None
    with_caps = np.asarray(render_frame(scene, t, Style(640, 360)))
    no_caps = np.asarray(render_frame(scene, t, Style(640, 360, captions=False)))
    strip = slice(int(360 - 92 / 2), int(360 - 44 / 2))  # the caption strip at 640x360
    assert np.abs(with_caps[strip].astype(int) - no_caps[strip].astype(int)).sum() > 0
    assert np.array_equal(with_caps[:200], no_caps[:200])  # nothing else differs


@pytest.fixture(scope="module")
def spotter():
    return EventSpotter().fit(*generated_example_set(list(range(401, 409)), minutes=5.0))


def _vision_shaped(seed):
    r = generate(seed=seed, minutes=5.0, track_hz=10.0)
    segs = [x for x in r.stream if x["type"] == "camera_segment"]
    frames = pseudo_identity_frames(r.stream, r.tracks, seed=seed)
    poss = infer_possessions(frames, r.match, r.match["match_id"], fps=5.0, segment_end={x["id"]: x["t_end"] for x in segs})
    return r, Positions.from_frames(frames), poss, [s for s in segs if s["kind"] == "main"]


def test_spotter_finds_events_in_vision_shaped_positions(spotter):
    reports, records = [], []
    for seed in (411, 412, 413):
        r, pos, poss, main = _vision_shaped(seed)
        ev = spot_events(pos, poss, r.match, spotter, r.match["match_id"])
        records += ev
        reports.append(evaluate_events(ev, r.stream, main))
    rep = merge_reports(reports)
    assert rep["pass"]["precision"] >= 0.85 and rep["pass"]["recall"] >= 0.85, rep["pass"]
    assert rep["tackle"]["recall"] >= 0.6 and rep["interception"]["recall"] >= 0.6, (rep["tackle"], rep["interception"])
    assert rep["shot"]["recall"] >= 0.5 and rep["take_on"]["recall"] >= 0.4, (rep["shot"], rep["take_on"])
    assert rep["pass"]["player_ok"] >= 0.95
    v = events_validator()
    assert not [(e["event_type"], v.errors(e)) for e in records if v.errors(e)]
    assert all(e["source"] == "vision" for e in records)


def test_spotted_events_are_ordered_unique_and_nutmegs_come_with_their_take_on(spotter):
    r, pos, poss, _main = _vision_shaped(414)
    ev = spot_events(pos, poss, r.match, spotter, r.match["match_id"])
    assert [e["t"] for e in ev] == sorted(e["t"] for e in ev)
    assert len({e["id"] for e in ev}) == len(ev)
    for n in [e for e in ev if e["event_type"] == "nutmeg"]:
        assert any(e["event_type"] == "take_on" and e["t"] == n["t"] and "nutmeg" in e.get("qualifiers", []) for e in ev)
