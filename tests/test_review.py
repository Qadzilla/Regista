"""Identity review rules on small hand-built identity results: no video, no models."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from regista.schema import events_validator
from regista.vision.identity import Track
from regista.vision.review import (NOT_A_PLAYER, annotation_records, apply_answers, identity_questions, terminal_reviewer,
                                   validate_answers)

MATCH = {
    "match_id": "m1",
    "teams": [{"team_id": "t_home", "short_name": "HOM"}, {"team_id": "t_away", "short_name": "AWY"}],
    "players": [{"player_id": f"t_{side}_{n:02d}", "team_id": f"t_{side}", "name": f"{side} {n}", "kit_number": n,
                 "position": "GK" if n == 1 else "MF", "starter": True} for side in ("home", "away") for n in range(1, 12)],
}


def _track(tid, team, pid, conf, votes, times):
    tr = Track(tid=tid, team_id=team, is_gk=False)
    tr.obs = [{"t": t, "u": 100.0, "v": 100.0, "r": 6.0, "read_weight": 1.0, "player_id": pid, "id_conf": conf} for t in times]
    tr.player_id, tr.id_conf, tr.votes = pid, conf, votes
    return tr


def _result(tracks, cutaway=()):
    frames = [{"t": t, "segment_id": "cs_1", "obs": []} for t in sorted({o["t"] for tr in tracks for o in tr.obs})]
    return SimpleNamespace(tracks=list(tracks), cutaway=list(cutaway), frames=frames, info={"sample_fps": 5.0})


def test_uncertain_and_unnamed_tracks_are_asked_confident_ones_are_not():
    sure = _track(0, "t_home", "t_home_09", 0.99, {"t_home_09": 0.99, "t_home_10": 0.01}, [i * 0.2 for i in range(30)])
    close = _track(1, "t_home", "t_home_10", 0.55, {"t_home_10": 0.55, "t_home_07": 0.45}, [i * 0.2 for i in range(30)])
    unnamed = _track(0, "t_away", None, 0.0, {"t_away_05": 0.9}, [i * 0.2 for i in range(20)])  # tid repeats across segments
    short = _track(2, "t_away", None, 0.0, {}, [0.0, 0.2])
    items = identity_questions(_result([sure, close, unnamed, short]), MATCH)
    assert [it["item_id"] for it in items] == ["tr_1", "tr_2"]  # close call (6 s) and unnamed (4 s); indices, not tids
    assert items[0]["candidates"][0]["player_id"] == "t_home_10" and items[0]["candidates"][1]["player_id"] == "t_home_07"


def test_a_correction_takes_the_name_only_in_the_frames_both_tracks_share():
    asked = _track(0, "t_home", None, 0.0, {"t_home_06": 0.9}, [10.0, 10.2, 10.4])
    holder = _track(1, "t_home", "t_home_06", 0.8, {"t_home_06": 0.8}, [9.0, 9.2, 10.2, 10.4, 12.0])
    result = _result([asked, holder])
    items = identity_questions(result, MATCH, min_seconds=0.4)
    answers = validate_answers(items, [{"item_id": "tr_0", "player_id": "t_home_06"}], MATCH)
    changed = apply_answers(result, items, answers)
    assert asked.player_id == "t_home_06" and all(o["player_id"] == "t_home_06" for o in asked.obs)
    assert holder.player_id == "t_home_06"  # it keeps the name outside the shared frames
    assert [o["player_id"] for o in holder.obs] == ["t_home_06", "t_home_06", None, None, "t_home_06"]
    assert changed["renamed"] == [(0, None, "t_home_06")] and changed["unnamed"] == [1]
    assert "tr_0" not in {it["item_id"] for it in identity_questions(result, MATCH, min_seconds=0.4)}  # reviewed: never asked again


def test_answers_are_validated_all_or_nothing():
    tr = _track(0, "t_home", "t_home_10", 0.5, {"t_home_10": 0.5, "t_home_07": 0.5}, [i * 0.2 for i in range(10)])
    items = identity_questions(_result([tr]), MATCH)
    for bad in ({"item_id": "tr_9", "player_id": "t_home_07"}, {"item_id": "tr_0", "player_id": "t_away_07"},
                {"item_id": "tr_0", "player_id": "someone"}):
        with pytest.raises(ValueError):
            validate_answers(items, [{"item_id": "tr_0", "player_id": "t_home_07"}, bad], MATCH)
    assert validate_answers(items, [{"item_id": "tr_0", "player_id": NOT_A_PLAYER}], MATCH)


def test_replay_questions_include_empty_replays_and_set_players():
    cut = [{"segment_id": "cs_r1", "kind": "replay", "t": 50.0, "t_end": 56.0, "players": {}, "candidates": {"t_home_09": {"on": 0.0, "near": 0.05, "frac": 0.3}}},
           {"segment_id": "cs_r2", "kind": "replay", "t": 70.0, "t_end": 76.0, "players": {"t_away_04": 1.0},
            "candidates": {"t_away_04": {"on": 0.9, "near": 0.9, "frac": 0.9}}}]
    result = _result([], cut)
    items = identity_questions(result, MATCH)
    assert [it["item_id"] for it in items] == ["cw_cs_r1"]  # nobody in it: asked; clear-cut: not asked
    apply_answers(result, items, validate_answers(items, [{"item_id": "cw_cs_r1", "players": ["t_home_09", "t_away_02"]}], MATCH))
    assert result.cutaway[0]["players"] == {"t_home_09": 1.0, "t_away_02": 1.0} and result.cutaway[0]["reviewed"]


def test_answers_become_valid_annotation_records():
    tr = _track(0, "t_home", "t_home_10", 0.5, {"t_home_10": 0.5, "t_home_07": 0.5}, [i * 0.2 for i in range(10)])
    items = identity_questions(_result([tr]), MATCH)
    answers = validate_answers(items, [{"item_id": "tr_0", "player_id": "t_home_07"}], MATCH)
    for simulated in (False, True):
        recs = annotation_records(items, answers, "m1", "zaid", simulated=simulated)
        assert recs[0]["verdict"] == "correct" and recs[0]["correction"]["player_id"] == "t_home_07"
        assert recs[0]["source"] == ("synthetic" if simulated else "human") and ("simulates" in recs[0]) == simulated
        assert not events_validator().errors(recs[0])
    with pytest.raises(ValueError):
        annotation_records(items, answers, "m1", "<script>")


def test_the_terminal_reviewer_understands_numbers_kits_and_skips():
    from regista.vision.agents import IdentityReviewRequest

    trs = [_track(i, "t_home", "t_home_10", 0.5, {"t_home_10": 0.5, "t_home_07": 0.5}, [i * 0.2 for i in range(10)]) for i in range(4)]
    cut = [{"segment_id": "cs_r1", "kind": "replay", "t": 50.0, "t_end": 56.0, "players": {}, "candidates": {"t_home_09": {"on": 0.0, "near": 0.05}}}]
    items = identity_questions(_result(trs, cut), MATCH)
    req = IdentityReviewRequest(question="Who?", items=items, review_dir="/tmp/x")
    replies = iter({"tr_0": "2", "tr_1": "#9", "tr_2": "x", "tr_3": "", "cw_cs_r1": "0"}[it["item_id"]] for it in items)
    out = terminal_reviewer(req, MATCH, ask=lambda _prompt: next(replies, "zaid"), say=lambda *_: None)
    got = {a["item_id"]: a for a in out.answers}
    assert got["tr_0"]["player_id"] == "t_home_07" and got["tr_1"]["player_id"] == "t_home_09"
    assert got["tr_2"]["player_id"] == NOT_A_PLAYER and "tr_3" not in got and got["cw_cs_r1"]["players"] == []
    assert out.annotator == "zaid"
