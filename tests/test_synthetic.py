"""The schema, the generator, and the clip rule must agree. These tests are the contract's teeth."""

from __future__ import annotations

import json
from collections import Counter

import pytest

from regista.clips import derive_clips
from regista.schema import SCHEMA_VERSION, clips_validator, events_validator
from regista.synth import generate

PLAYER = "t_home_09"


@pytest.fixture(scope="module")
def result():
    return generate(seed=294, minutes=3.0, track_hz=2.0)


@pytest.fixture(scope="module")
def derived(result):
    return derive_clips(result.stream, PLAYER)


def _by_type(records):
    out: dict[str, list] = {}
    for r in records:
        out.setdefault(r["type"], []).append(r)
    return out


# ----------------------------------------------------------------------------- schema

def test_every_event_record_validates(result):
    v = events_validator()
    bad = [(r["id"], v.errors(r)) for r in result.stream if not v.is_valid(r)]
    assert not bad, bad[:5]


def test_every_track_validates(result):
    v = events_validator()
    bad = [(r["id"], v.errors(r)) for r in result.tracks if not v.is_valid(r)]
    assert not bad, bad[:5]


def test_every_clip_and_label_validates(derived):
    clips, labels = derived
    v = clips_validator()
    bad = [(r["id"], v.errors(r)) for r in clips + labels if not v.is_valid(r)]
    assert not bad, bad[:5]


def test_validator_rejects_bad_records():
    v = events_validator()
    assert v.errors({"type": "nope"})
    assert v.errors({"type": "event", "id": "ev_1", "match_id": "m", "schema_version": SCHEMA_VERSION, "source": "synthetic",
                     "confidence": 0.9, "t": 1.0, "event_type": "teleport", "outcome": "success"})
    assert v.errors({"type": "event", "id": "ev_1", "match_id": "m", "schema_version": SCHEMA_VERSION, "source": "synthetic",
                     "confidence": 0.9, "t": 1.0, "event_type": "pass", "outcome": "success", "bogus": 1})


def test_schema_version_is_consistent(result):
    assert {r["schema_version"] for r in result.stream} == {SCHEMA_VERSION}


# ----------------------------------------------------------------------------- stream shape

def test_match_header_first_and_only_once(result):
    assert result.stream[0]["type"] == "match"
    assert sum(r["type"] == "match" for r in result.stream) == 1


def test_stream_sorted_by_time(result):
    ts = [r["t"] for r in result.events]
    assert ts == sorted(ts)


def test_roster_integrity(result):
    roster = {p["player_id"] for p in result.match["players"]}
    teams = {t["team_id"] for t in result.match["teams"]}
    for r in result.stream[1:] + result.tracks:
        for key in ("player_id", "related_player_id"):
            if r.get(key):
                assert r[key] in roster, (r["type"], key, r[key])
        if r.get("team_id"):
            assert r["team_id"] in teams


def test_segments_are_contiguous_and_cover_the_video(result):
    segs = sorted(_by_type(result.events)["camera_segment"], key=lambda s: s["t"])
    assert segs[0]["t"] == 0.0
    for a, b in zip(segs, segs[1:]):
        assert a["t_end"] == pytest.approx(b["t"], abs=1e-6), (a, b)
        assert a["t_end"] > a["t"]
    assert segs[-1]["t_end"] == pytest.approx(result.match["video"]["duration_s"])
    kinds = Counter(s["kind"] for s in segs)
    assert kinds["main"] >= 1
    assert kinds["replay"] + kinds["highlight"] + kinds["closeup"] >= 1, "director never cut away; clip rule 2 is untested"


def test_replays_point_at_real_events_in_the_past(result):
    by = _by_type(result.events)
    event_ids = {e["id"] for e in by["event"]}
    for seg in by["camera_segment"]:
        if seg["kind"] in ("replay", "highlight"):
            assert seg["replay_of"] and all(i in event_ids for i in seg["replay_of"])
            assert seg["replays_window"]["t_end"] <= seg["t"] + 1e-6


def test_possessions_do_not_overlap(result):
    poss = sorted(_by_type(result.events)["possession"], key=lambda p: p["t"])
    for a, b in zip(poss, poss[1:]):
        assert a["t_end"] <= b["t"] + 1e-6


def test_hackathon_vocabulary_is_present(result):
    types = {e["event_type"] for e in _by_type(result.events)["event"]}
    for required in ("pass", "shot", "tackle", "possession_change", "pressure", "touch"):
        assert required in types, f"no {required} events generated"


def test_tracks_have_identity_evidence_and_pitch(result):
    for tr in result.tracks:
        if tr["object"] == "player":
            assert tr["identity"]["evidence"]
            assert "face_local" not in tr["identity"]["evidence"], "synthetic tracks must not claim face evidence"
            assert 0 <= tr["pitch"]["x"] <= 105 and 0 <= tr["pitch"]["y"] <= 68


def test_placeholder_annotations_declare_themselves_and_target_real_records(result):
    by = _by_type(result.events)
    ids = {r["id"] for r in result.stream[1:] + result.tracks}
    assert by.get("annotation"), "generator should emit placeholder annotations so consumers see the shape"
    for a in by["annotation"]:
        assert a["source"] == "synthetic" and a.get("simulates") == "human" and a["confidence"] == 1
        assert a["annotator"] != "zaid", "no real person annotated synthetic data"
        assert a["target_id"] in ids


def test_schema_requires_simulates_on_synthetic_annotations():
    v = events_validator()
    base = {"type": "annotation", "id": "an_000001", "match_id": "m", "schema_version": SCHEMA_VERSION, "confidence": 1,
            "t": 1.0, "target_id": "ev_000001", "target_type": "event", "verdict": "confirm", "annotator": "x",
            "annotated_at": "2026-10-19T00:00:00Z"}
    assert not v.errors({**base, "source": "human"})
    assert v.errors({**base, "source": "synthetic"}), "synthetic annotation without simulates must fail"
    assert not v.errors({**base, "source": "synthetic", "simulates": "human"})


# ----------------------------------------------------------------------------- clip rule

def test_main_view_clips_only_where_player_had_the_ball(result, derived):
    clips, _ = derived
    by = _by_type(result.events)
    mine = [p for p in by["possession"] if p["player_id"] == PLAYER]
    main_clips = [c for c in clips if c["reason"] == "on_ball_main"]
    assert main_clips, "player never had the ball in main view; widen the test match"
    for c in main_clips:
        assert any(p["t"] < c["t_end"] and c["t"] < p["t_end"] for p in mine), c
        assert c["possession_ids"]


def test_every_possession_in_main_view_is_covered(result, derived):
    clips, _ = derived
    by = _by_type(result.events)
    main = [s for s in by["camera_segment"] if s["kind"] == "main"]
    for p in by["possession"]:
        if p["player_id"] != PLAYER:
            continue
        if not any(s["t"] <= p["t"] < s["t_end"] for s in main):
            continue
        assert any(c["reason"] == "on_ball_main" and c["t"] <= p["t"] and p["t_end"] <= c["t_end"] + 1e-6 for c in clips), p


def test_every_cutaway_appearance_becomes_a_clip(result, derived):
    clips, _ = derived
    by = _by_type(result.events)
    seg_kind = {s["id"]: s["kind"] for s in by["camera_segment"]}
    wanted = {a["segment_id"] for a in by["appearance"] if a["player_id"] == PLAYER and seg_kind[a["segment_id"]] in ("replay", "highlight", "closeup")}
    got = {c["segment_ids"][0] for c in clips if c["reason"] != "on_ball_main"}
    assert wanted == got


def test_no_clip_for_main_view_off_ball(result, derived):
    clips, _ = derived
    by = _by_type(result.events)
    seg_kind = {s["id"]: s["kind"] for s in by["camera_segment"]}
    for a in by["appearance"]:
        if a["player_id"] == PLAYER and seg_kind[a["segment_id"]] == "main" and not a["on_ball"]:
            for c in clips:
                if c["reason"] != "on_ball_main":
                    continue
                # An off-ball appearance may touch a clip only via pre/post roll, never be fully inside it.
                assert not (c["t"] <= a["t"] and a["t_end"] <= c["t_end"] and (a["t_end"] - a["t"]) > (c["pre_roll_s"] + c["post_roll_s"])), (a, c)


def test_labels_match_clips_and_explain_themselves(derived):
    clips, labels = derived
    assert len(clips) == len(labels)
    clip_ids = {c["id"] for c in clips}
    for lb in labels:
        assert lb["clip_id"] in clip_ids
        assert lb["tags"] and 0 <= lb["watchability"] <= 1
        assert "Scored" in lb["explanation"]


# ----------------------------------------------------------------------------- determinism

def test_same_seed_same_stream():
    a = generate(seed=3, minutes=0.5, track_hz=1.0)
    b = generate(seed=3, minutes=0.5, track_hz=1.0)
    assert json.dumps(a.stream, sort_keys=True) == json.dumps(b.stream, sort_keys=True)
    assert json.dumps(a.tracks, sort_keys=True) == json.dumps(b.tracks, sort_keys=True)


def test_track_rate_does_not_change_the_match():
    """Sampling is observation, not simulation: the same seed must give the same events at any track rate."""
    a = generate(seed=3, minutes=0.5, track_hz=1.0)
    b = generate(seed=3, minutes=0.5, track_hz=4.0)
    # Observation-side confidences (camera segments, appearances, tracks) may differ; the match may not.
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ("id",) and not (r["type"] == "camera_segment" and k == "confidence")}
                          for r in rows if r["type"] in ("event", "possession", "camera_segment")]
    assert json.dumps(strip(a.events), sort_keys=True) == json.dumps(strip(b.events), sort_keys=True)
    assert len(b.tracks) > len(a.tracks)


def test_different_seed_different_stream():
    a = generate(seed=3, minutes=0.5, track_hz=1.0)
    b = generate(seed=4, minutes=0.5, track_hz=1.0)
    assert json.dumps(a.events, sort_keys=True) != json.dumps(b.events, sort_keys=True)


# ----------------------------------------------------------------------------- realism

def test_realistic_profile_sits_inside_premier_league_bands():
    """The realistic profile must land inside most of the published bands over a decent sample of minutes.
    Variance over two simulated hours is still real, so the bar is 10 of 13 bands plus the five that define
    the shape of a football match."""
    from regista.synth.report import NORMS, compute_metrics, verdicts

    stream = []
    for seed in (31, 32, 33, 34):
        stream += generate(seed=seed, minutes=30.0, track_hz=1.0, profile="realistic").stream
    metrics = compute_metrics(stream)
    v = verdicts(metrics)
    in_band = [k for k, x in v.items() if x == "in band"]
    assert len(in_band) >= 10, {k: (metrics[k], v[k], NORMS[k][:2]) for k in v if v[k] != "in band"}
    for key in ("passes_per90", "pass_completion", "shots_per90", "interceptions_per90", "possession_mean_s"):
        assert v[key] == "in band", (key, metrics[key], NORMS[key][:2])


def test_demo_profile_is_denser_than_realistic():
    from regista.synth.report import compute_metrics

    demo = compute_metrics(generate(seed=5, minutes=10.0, profile="demo").stream)
    real = compute_metrics(generate(seed=5, minutes=10.0, profile="realistic").stream)
    assert demo["shots_per90"] > real["shots_per90"] * 1.5
    assert demo["take_ons_per90"] > real["take_ons_per90"] * 1.5


def test_report_markdown_names_every_band():
    from regista.synth.report import NORMS, compute_metrics, render_markdown

    r = generate(seed=5, minutes=2.0)
    md = render_markdown(compute_metrics(r.stream, r.tracks), r.match["match_id"], "demo")
    for key in NORMS:
        assert key in md
    assert "in band" in md or "high" in md


# ----------------------------------------------------------------------------- periods and teams

def test_two_periods_swap_ends_and_continue_the_clock():
    r = generate(seed=8, minutes=1.0, track_hz=1.0, periods=2)
    periods = r.match["periods"]
    assert [p["period"] for p in periods] == [1, 2]
    assert periods[0]["left_to_right_team_id"] == "t_home" and periods[1]["left_to_right_team_id"] == "t_away"
    assert periods[1]["t"] > periods[0]["t_end"], "there must be an interval between halves"
    events = [e for e in r.events if e["type"] == "event"]
    kickoffs = [e for e in events if e["event_type"] == "kick_off"]
    assert kickoffs[0]["player_id"] == "t_home_09" and kickoffs[0]["clock"]["period"] == 1
    second_half = next(e for e in kickoffs if e["clock"]["period"] == 2)
    assert second_half["player_id"] == "t_away_09" and second_half["clock"]["minute"] == 45
    assert all(e["clock"]["minute"] >= 45 for e in events if e["t"] >= periods[1]["t"])
    assert sum(1 for e in events if e["event_type"] == "period_end") == 2
    kinds = [s["kind"] for s in r.events if s["type"] == "camera_segment"]
    assert "graphic" in kinds
    # Highlights come once, after the second half.
    first_highlight = next(s["t"] for s in r.events if s["type"] == "camera_segment" and s["kind"] == "highlight")
    assert first_highlight >= periods[1]["t_end"]
    v = events_validator()
    assert all(v.is_valid(x) for x in r.stream)


def test_custom_teams_are_applied_and_validated():
    teams = [{"name": "Eastbury Rovers", "short_name": "EAS", "kit": {"primary": "#00A650"}},
             {"name": "Westfield Town", "short_name": "WES", "kit": {"primary": "#6A0DAD", "gk": "#FFD700"}}]
    r = generate(seed=8, minutes=0.5, teams=teams)
    names = [t["name"] for t in r.match["teams"]]
    assert names == ["Eastbury Rovers", "Westfield Town"]
    assert r.match["teams"][0]["kit"]["primary"] == "#00A650" and r.match["teams"][0]["kit"]["gk"] == "#1DB954"
    assert r.match["teams"][1]["kit"]["gk"] == "#FFD700"
    assert events_validator().is_valid(r.match)
    with pytest.raises(ValueError):
        generate(seed=8, minutes=0.5, teams=[{"name": "Only One"}])
    with pytest.raises(ValueError):
        generate(seed=8, minutes=0.5, teams=[{"short_name": "TOOLONG"}, {}])


def test_same_seed_same_match_regardless_of_team_names():
    a = generate(seed=9, minutes=0.5)
    b = generate(seed=9, minutes=0.5, teams=[{"name": "A FC", "short_name": "AFC"}, {"name": "B FC", "short_name": "BFC"}])
    ea = [(e["t"], e["event_type"], e.get("player_id")) for e in a.events if e["type"] == "event"]
    eb = [(e["t"], e["event_type"], e.get("player_id")) for e in b.events if e["type"] == "event"]
    assert ea == eb


def test_schemas_ship_inside_the_package():
    """Validation must work from an installed package, not only a repo checkout (the container broke on this)."""
    import tomllib
    from pathlib import Path

    import regista
    from regista.schema import CLIPS_SCHEMA, EVENTS_SCHEMA

    pkg = Path(regista.__file__).resolve().parent
    for path in (EVENTS_SCHEMA, CLIPS_SCHEMA):
        assert path.exists() and pkg in path.resolve().parents, path
    data = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    assert "schemas/*.json" in data["tool"]["setuptools"]["package-data"]["regista"]
