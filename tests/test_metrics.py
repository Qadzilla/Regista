"""The Scout terminal's metrics engine (regista.season.metrics) and its API (regista.terminal_api).

Each rule is checked on a small hand-made stream first (progressive passes and carries, key-pass linking, shot-creating
actions, PPDA, pressure regains, possession adjustment, keepers), then the engine on a few real league fixtures, then the
API's shapes, validation, evidence and the rule that hidden ratings never appear.
"""

import math
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from regista.schema import iter_jsonl
from regista.season.league import ATTRIBUTE_KEYS, new_league, save_league
from regista.season.metrics import (CATALOGUE, HELPERS, PROGRESSIVE_M, SOURCES, TEAM_CATALOGUE, analyse_match, build_season,
                                    fbref_percentile, fit_xt, qualifying_minutes, thresholds)

HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes"}
STAR = "pl_bro_09"


# ---------------------------------------------------------------------------- hand-made streams

PLAYERS = [("t_home_01", "t_home", "GK"), ("t_home_04", "t_home", "DF"), ("t_home_08", "t_home", "MF"),
           ("t_home_09", "t_home", "FW"), ("t_away_01", "t_away", "GK"), ("t_away_04", "t_away", "DF"),
           ("t_away_08", "t_away", "MF"), ("t_away_09", "t_away", "FW")]


class S:
    """Build a tiny stream: home attacks toward x = 105 in period 1 and toward x = 0 in period 2."""

    def __init__(self):
        self.recs = []
        self.n = 0

    def header(self):
        return {"type": "match", "id": "ma_t", "match_id": "m_test", "home_team_id": "t_home", "away_team_id": "t_away",
                "teams": [{"team_id": "t_home", "club_id": "cl_h"}, {"team_id": "t_away", "club_id": "cl_a"}],
                "periods": [{"period": 1, "t": 0.0, "t_end": 900.0, "left_to_right_team_id": "t_home"},
                            {"period": 2, "t": 905.0, "t_end": 1805.0, "left_to_right_team_id": "t_away"}],
                "players": [{"player_id": p, "team_id": t, "position": pos, "starter": True, "kit_number": int(p[-2:]),
                             "global_player_id": None} for p, t, pos in PLAYERS],
                "score": {}}

    def _id(self, prefix):
        self.n += 1
        return f"{prefix}_{self.n:04d}"

    def po(self, t, t_end, pid, gained="pass_received", lost="pass", x=50.0, y=34.0, ex=None, ey=None):
        r = {"type": "possession", "id": self._id("po"), "t": t, "t_end": t_end, "player_id": pid, "team_id": pid[:6],
             "gained_by": gained, "lost_by": lost, "pitch": {"x": x, "y": y},
             "pitch_end": {"x": ex if ex is not None else x, "y": ey if ey is not None else y}}
        self.recs.append(r)
        return r["id"]

    def ev(self, t, et, pid, x=50.0, y=34.0, ex=None, ey=None, outcome="success", q=None, poss=None, rel=None, m=None,
           period=None, up=False):
        r = {"type": "event", "id": self._id("ev"), "t": t, "event_type": et, "player_id": pid, "team_id": pid[:6] if pid else None,
             "related_player_id": rel, "possession_id": poss, "pitch": {"x": x, "y": y}, "outcome": outcome,
             "under_pressure": up, "clock": {"period": period or (1 if t < 905 else 2)}}
        if ex is not None:
            r["pitch_end"] = {"x": ex, "y": ey if ey is not None else y}
        if q:
            r["qualifiers"] = list(q)
        if m:
            r["metrics"] = m
        self.recs.append(r)
        return r["id"]

    def stream(self):
        return [self.header(), *sorted(self.recs, key=lambda r: r["t"])]


def pass_(s, t, pid, rel, x, ex, y=34.0, ey=None, outcome="success", poss=None, **kw):
    return s.ev(t, "pass", pid, x, y, ex, ey if ey is not None else y, outcome=outcome, rel=rel, poss=poss, **kw)


def counts(stream, pid):
    return analyse_match(stream).counts[pid]


def test_progressive_pass_rule_edges():
    s = S()
    s.po(10, 12, "t_home_04", gained="loose_ball")
    pass_(s, 12, "t_home_04", "t_home_08", 50.0, 50.0 + PROGRESSIVE_M)          # exactly 10 yards: progressive
    s.po(13, 14, "t_home_08")
    pass_(s, 14, "t_home_08", "t_home_04", 50.0 + PROGRESSIVE_M, 55.0)           # backwards
    s.po(15, 16, "t_home_04")
    pass_(s, 16, "t_home_04", "t_home_09", 55.0, 64.0)                           # 9 m from start, < 10 yd past the furthest point
    s.po(17, 18, "t_home_09")
    pass_(s, 18, "t_home_09", "t_home_08", 64.0, 64.0 + PROGRESSIVE_M - 0.01)    # just under 10 yards
    s.po(30, 31, "t_away_08", gained="interception")                             # the opponent: the six-pass window resets
    s.po(40, 41, "t_home_04", gained="tackle")
    pass_(s, 41, "t_home_04", "t_home_08", 40.0, 70.0)                           # from the defending 40%: excluded
    s.po(42, 43, "t_home_08")
    pass_(s, 43, "t_home_08", "t_home_09", 85.0, 90.0)                           # 5 m but into the box: progressive
    s.po(44, 45, "t_home_09")
    pass_(s, 45, "t_home_09", "t_home_08", 70.0, 85.0, outcome="fail")           # failed passes never count
    s.po(950, 951, "t_home_04", gained="kickoff")                                # period 2: home attacks toward x = 0
    pass_(s, 951, "t_home_04", "t_home_08", 60.0, 60.0 - PROGRESSIVE_M - 0.5)
    mm = analyse_match(s.stream())
    assert mm.counts["t_home_04"]["progressive_passes"] == 2       # exactly 10 yd, and the second-half pass
    assert mm.counts["t_home_08"]["progressive_passes"] == 1       # into the box
    assert mm.counts["t_home_09"]["progressive_passes"] == 0
    assert mm.counts["t_home_08"]["progressive_passes_received"] == 2 and mm.counts["t_home_09"]["progressive_passes_received"] == 1
    assert mm.counts["t_home_08"]["passes_into_box"] == 1
    assert mm.counts["t_home_04"]["progressive_pass_distance"] == pytest.approx(PROGRESSIVE_M + 9.0 + 30.0 + PROGRESSIVE_M + 0.5)
    assert mm.counts["t_home_09"]["ball_losses"] == 1


def test_the_six_pass_window_holds_only_six_passes():
    def run(prior):
        s = S()
        t = 10.0
        for x0, x1 in prior:
            s.po(t, t + 1, "t_home_08")
            pass_(s, t + 1, "t_home_08", "t_home_04", x0, x1)
            t += 2
        s.po(t, t + 1, "t_home_04")
        last = prior[-1][1]
        pass_(s, t + 1, "t_home_04", "t_home_09", last, last + 10.3)
        return analyse_match(s.stream()).counts["t_home_04"]["progressive_passes"]

    six = [(60.0, 70.0), (50.0, 52.0), (52.0, 54.0), (54.0, 56.0), (56.0, 58.0), (58.0, 59.0)]
    assert run(six) == 0                          # 70 is among the last six passes: 69.3 is not 10 yards past it
    assert run(six + [(59.0, 59.5)]) == 1         # a seventh pass pushes 70 out: 69.8 is 10.3 m past 59.5


def test_progressive_carries_and_entries():
    s = S()
    p = s.po(10, 14, "t_home_08", gained="loose_ball")
    s.ev(10, "carry", "t_home_08", 30.0, 34.0, 45.0, 34.0, poss=p)      # 15 m but ends in the defending half: excluded
    s.ev(12, "carry", "t_home_08", 45.0, 34.0, 60.0, 34.0, poss=p)      # 15 m, ends past halfway: progressive
    s.ev(13, "carry", "t_home_08", 65.0, 30.0, 92.0, 30.0, poss=p)      # into the final third and the box
    c = counts(s.stream(), "t_home_08")
    assert c["progressive_carries"] == 2 and c["carries_final_third"] == 1 and c["carries_into_box"] == 1
    assert c["touches_in_box"] == 1 and c["carries"] == 3


def test_key_pass_links_the_shot_to_the_pass_received():
    s = S()
    s.po(10, 12, "t_home_08", gained="loose_ball")
    pass_(s, 12, "t_home_08", "t_home_09", 70.0, 90.0)
    p = s.po(13, 15, "t_home_09", gained="pass_received", lost="shot", x=90.0)
    s.ev(15, "shot", "t_home_09", 92.0, 34.0, 105.0, 34.0, outcome="fail", q=["saved"], poss=p, m={"xg": 0.25})
    p2 = s.po(20, 22, "t_home_09", gained="loose_ball", lost="shot", x=90.0)      # no pass received: no key pass
    s.ev(22, "shot", "t_home_09", 95.0, 34.0, 105.0, 34.0, outcome="fail", q=["off_target"], poss=p2, m={"xg": 0.4})
    s.po(30, 32, "t_home_09", gained="set_piece", lost="shot", x=94.0)            # a penalty: excluded from key passes
    s.ev(32, "shot", "t_home_09", 94.0, 34.0, 105.0, 34.0, q=["goal", "penalty"], poss=None, m={"xg": 0.79})
    mm = analyse_match(s.stream())
    passer, shooter = mm.counts["t_home_08"], mm.counts["t_home_09"]
    assert passer["key_passes"] == 1 and passer["xa"] == pytest.approx(0.25)
    assert shooter["shots"] == 2 and shooter["npxg"] == pytest.approx(0.65) and shooter["xg"] == pytest.approx(1.44)
    assert shooter["shots_on_target"] == 1 and shooter["penalties_taken"] == 1 and shooter["big_chances"] == 2
    assert mm.evidence["t_home_08"]["key_passes"][0][0].startswith("ev_")


def test_shot_creating_actions_take_the_two_actions_before_the_shot():
    s = S()
    s.po(5, 6, "t_away_08", gained="loose_ball")
    s.ev(6, "pass", "t_away_08", 40.0, 34.0, 60.0, 34.0, outcome="success", rel="t_away_09")   # opponent: never credited
    s.ev(7, "interception", "t_home_04", 55.0, 34.0)                                          # won the ball
    s.po(8, 10, "t_home_04", gained="interception")
    pass_(s, 10, "t_home_04", "t_home_08", 50.0, 60.0)
    s.po(11, 12, "t_home_08")
    s.ev(11.5, "take_on", "t_home_08", 62.0, 34.0, rel="t_away_04")
    s.ev(12, "foul_won", "t_home_08", 63.0, 34.0)
    s.po(14, 15, "t_home_09", gained="set_piece", lost="shot")
    goal = s.ev(15, "shot", "t_home_09", 80.0, 34.0, 105.0, 34.0, q=["goal"], m={"xg": 0.1})
    mm = analyse_match(s.stream())
    assert mm.counts["t_home_08"]["sca"] == 2 and mm.counts["t_home_08"]["gca"] == 2   # foul drawn, take-on
    assert mm.counts["t_home_04"]["sca"] == 0 and mm.counts["t_away_08"]["sca"] == 0
    notes = sorted(e[3] for e in mm.evidence["t_home_08"]["sca"])
    assert notes == ["foul drawn", "take-on"] and goal
    assert mm.counts["t_away_04"]["dribbled_past"] == 1


def test_sca_stops_at_the_opponents_possession():
    s = S()
    s.po(5, 6, "t_home_04", gained="loose_ball")
    pass_(s, 6, "t_home_04", "t_home_08", 50.0, 60.0)
    s.po(7, 8, "t_away_08", gained="interception")
    s.po(9, 10, "t_home_08", gained="tackle", lost="shot")
    s.ev(9, "tackle", "t_home_08", 60.0, 34.0, rel="t_away_08")
    s.ev(10, "shot", "t_home_08", 80.0, 34.0, 105.0, 34.0, outcome="fail", q=["off_target"], m={"xg": 0.05})
    mm = analyse_match(s.stream())
    assert mm.counts["t_home_08"]["sca"] == 1 and mm.counts["t_home_04"]["sca"] == 0   # the tackle; the pass was before the loss


def test_ppda_counts_opponent_build_up_passes_per_defensive_action_in_the_pressing_zone():
    s = S()
    s.po(10, 30, "t_away_04", gained="loose_ball")
    for i in range(6):                        # away passes in their own 60% (away attacks toward x = 0 in period 1)
        pass_(s, 11 + i, "t_away_04", "t_away_08", 90.0 - i, 85.0 - i)
    pass_(s, 18, "t_away_04", "t_away_08", 30.0, 20.0)       # in their attacking 40%: not counted
    s.ev(20, "tackle", "t_home_09", 70.0, 34.0, rel="t_away_04")      # home's frame x = 70 >= 42: counted
    s.ev(21, "foul", "t_home_08", 50.0, 34.0)                         # x = 50: counted
    s.ev(22, "interception", "t_home_04", 20.0, 34.0)                 # x = 20 < 42 in home's frame: not counted
    from regista.season.metrics import _team_values

    mm = analyse_match(s.stream())
    home = mm.teams["t_home"]
    assert home["ppda_actions"] == 2 and home["opp_build_up_passes"] == 6
    assert _team_values(home)["ppda"] == pytest.approx(3.0)


def test_pressure_regains_need_an_open_play_win_within_five_seconds():
    s = S()
    s.po(10, 12, "t_away_08", gained="loose_ball", lost="tackled")
    s.ev(10, "pressure", "t_home_08", 50.0, 34.0, rel="t_away_08")
    s.po(14.5, 16, "t_home_08", gained="tackle")                     # 4.5 s: a regain
    s.po(20, 22, "t_away_08", gained="loose_ball", lost="out_of_play")
    s.ev(20, "pressure", "t_home_09", 50.0, 34.0, rel="t_away_08")
    s.po(26, 27, "t_home_04", gained="loose_ball")                    # 6 s: too late
    s.po(30, 31, "t_away_08", gained="loose_ball", lost="out_of_play")
    s.ev(30, "pressure", "t_home_04", 50.0, 34.0, rel="t_away_08")
    s.po(32, 33, "t_home_04", gained="set_piece")                     # a throw-in is not winning the ball
    c = analyse_match(s.stream()).counts
    assert c["t_home_08"]["pressure_regains"] == 1 and c["t_home_09"]["pressure_regains"] == 0
    assert c["t_home_04"]["pressure_regains"] == 0 and c["t_home_04"]["pressures"] == 1


def test_possession_adjustment_uses_opponent_possession_while_on_the_pitch():
    s = S()
    s.po(100, 110, "t_away_08", gained="loose_ball", lost="pass")
    pass_(s, 110, "t_away_08", "t_away_09", 50.0, 40.0)
    s.po(112, 122, "t_away_09", gained="pass_received", lost="pass")  # the 2 s flight counts: 22 s of away possession
    pass_(s, 122, "t_away_09", "t_away_08", 40.0, 30.0, outcome="fail")
    s.ev(123, "interception", "t_home_04", 70.0, 34.0)
    s.po(124, 130, "t_home_04", gained="interception", lost="out_of_play")
    s.po(140, 158, "t_away_04", gained="set_piece", lost="period_end")   # 18 s more: 40 s in all
    s.ev(150, "tackle", "t_home_04", 60.0, 34.0, rel="t_away_04")
    mm = analyse_match(s.stream())
    c = mm.counts["t_home_04"]
    assert c["opp_possession_s"] == pytest.approx(40.0) and mm.teams["t_away"]["possession_s"] == pytest.approx(40.0)
    assert c["tkl_int"] == 2
    from regista.season.metrics import CATALOGUE as CAT, _match_value

    row = {"counts": c, "minutes": c.get("played_s", 0) or 30.0}
    assert _match_value(CAT["tkl_int_padj"], row) == pytest.approx(2 / (40 / 60) * 30)


def test_keepers_shots_faced_saves_and_clean_sheets():
    s = S()
    s.ev(100, "shot", "t_away_09", 20.0, 34.0, 0.0, 34.0, outcome="fail", q=["saved"], m={"xg": 0.1})
    s.ev(100.5, "save", "t_home_01", 2.0, 34.0, rel="t_away_09")
    s.ev(200, "shot", "t_away_09", 20.0, 34.0, 0.0, 34.0, q=["goal"], m={"xg": 0.3})
    s.ev(200.4, "goal", "t_away_09", 1.0, 34.0)
    s.ev(300, "shot", "t_away_09", 20.0, 34.0, 0.0, 20.0, outcome="fail", q=["off_target"], m={"xg": 0.05})
    mm = analyse_match(s.stream())
    home_gk, away_gk = mm.counts["t_home_01"], mm.counts["t_away_01"]
    assert home_gk["sot_faced"] == 2 and home_gk["saves"] == 1 and home_gk["goals_conceded"] == 1
    assert home_gk["full_matches"] == 1 and home_gk["clean_sheets"] == 0
    assert away_gk["clean_sheets"] == 1 and away_gk["sot_faced"] == 0
    assert mm.counts["t_home_04"]["onpitch_xg_against"] == pytest.approx(0.45) and mm.counts["t_home_04"]["onpitch_goals_diff"] == -1


def test_save_pct_leaves_penalties_out_as_fbref_does():
    """FBref's Save% excludes penalty kicks (industry-metrics.md row 4); they are counted apart."""
    s = S()
    s.ev(100, "shot", "t_away_09", 20.0, 34.0, 0.0, 34.0, outcome="fail", q=["saved"], m={"xg": 0.1})
    s.ev(100.5, "save", "t_home_01", 2.0, 34.0, rel="t_away_09")
    s.ev(200, "shot", "t_away_09", 11.0, 34.0, 0.0, 34.0, outcome="fail", q=["penalty", "saved"], m={"xg": 0.79})
    s.ev(200.5, "save", "t_home_01", 2.0, 34.0, rel="t_away_09")
    s.ev(300, "shot", "t_away_09", 11.0, 34.0, 0.0, 34.0, q=["penalty", "goal"], m={"xg": 0.79})
    s.ev(300.4, "goal", "t_away_09", 1.0, 34.0, q=["penalty"])
    gk = analyse_match(s.stream()).counts["t_home_01"]
    assert gk["sot_faced"] == 1 and gk["saves"] == 1                      # the open-play shot only: Save% 100%
    assert gk["penalties_faced"] == 2 and gk["penalties_saved"] == 1 and gk["goals_conceded"] == 1


def test_fbref_percentile_and_thresholds():
    vals = sorted([1.0, 2.0, 2.0, 3.0])
    assert fbref_percentile(vals, 3.0) == pytest.approx(87.5)    # (3/4 + 4/4) / 2
    assert fbref_percentile(vals, 2.0) == pytest.approx(50.0)    # (1/4 + 3/4) / 2
    assert fbref_percentile(vals, 1.0) == pytest.approx(12.5)
    t = thresholds(301.5)   # ten 30-minute matches: 3.35 of FBref's 90-minute squad games
    assert t["shots"]["min"] == 2 and t["take_ons"]["min"] == 2 and t["aerials"]["min"] == 4 and t["challenges"]["min"] == 3
    assert "club minutes / 90" in t["aerials"]["rule"]
    t = thresholds(900.0)   # ten 90-minute matches: FBref's own rule, times 10
    assert t["shots"]["min"] == 4 and t["take_ons"]["min"] == 5 and t["aerials"]["min"] == 10 and t["challenges"]["min"] == 7
    assert qualifying_minutes(301.5) == pytest.approx(100.5)


def test_xt_in_a_zone_with_only_shots_is_its_xg_and_moves_carry_threat_back():
    near, far = (100.0, 34.0), (50.0, 34.0)
    model = fit_xt(moves=[(*far, *near)], shots=[(*near, 0.3)])
    assert model.value(*near) == pytest.approx(0.3)
    assert model.value(*far) == pytest.approx(0.3)                 # every move from far reaches near
    assert model.added(*far, *near) == pytest.approx(0.0)
    half = fit_xt(moves=[(*far, *near)], shots=[(*near, 0.3)], all_moves=[far, far])   # half the moves fail
    assert half.value(*far) == pytest.approx(0.15)


def test_every_metric_has_a_definition_and_a_known_source():
    for m in [*CATALOGUE.values(), *TEAM_CATALOGUE.values()]:
        assert m.label and m.definition and m.rule and m.unit, m.key
        assert m.sources and all(s in SOURCES for s in m.sources), m.key
        assert m.kind in ("per90", "ratio", "padj", "max", "mean", "total"), m.key
        if m.kind == "ratio" and m.key in CATALOGUE:   # team ratios are computed by _team_values
            assert m.num and m.den, m.key
        assert m.key not in HIDDEN and m.key not in HELPERS
    assert not HIDDEN & {m.group for m in CATALOGUE.values()}


# ---------------------------------------------------------------------------- the engine on league fixtures

@pytest.fixture(scope="module")
def small(tmp_path_factory):
    league = new_league(2026)
    small = {**league, "fixtures": league["fixtures"][:3]}   # round 1: every club plays once
    root = tmp_path_factory.mktemp("metrics_season")
    return small, root, build_season(small, root)


def test_engine_agrees_with_the_streams(small):
    league, root, sm = small
    tagged, shots, sot, pen_goals = Counter(), 0, 0, 0
    for fx in league["fixtures"]:
        for e in iter_jsonl(root / fx["match_id"] / "events.jsonl"):
            if e["type"] != "event":
                continue
            q = e.get("qualifiers") or []
            if e["event_type"] in ("pass", "cross") and "key_pass" in q:
                tagged["key_passes"] += 1
            if e["event_type"] == "shot" and "penalty" not in q:
                shots += 1
            if e["event_type"] == "shot" and {"goal", "saved"} & set(q) and "penalty" not in q:   # FBref Save%: no penalties
                sot += 1
            if e["event_type"] == "goal" and "penalty" in q:
                pen_goals += 1
    totals = Counter()
    for ps in sm.players.values():
        totals.update({k: v for k, v in ps.totals.items()})
    assert totals["key_passes"] == tagged["key_passes"]      # the generator tags the same pass the engine links
    assert totals["shots"] == shots and totals["sot_faced"] == sot
    assert totals["saves"] + totals["goals_conceded"] - pen_goals == totals["sot_faced"]
    assert totals["progressive_passes"] == totals["progressive_passes_received"]
    assert len(sm.match_rows) == 3 and sm.matches_per_club == 1
    shares = [t["values"]["possession_pct"] for t in sm.teams.values()]
    assert sum(shares) == pytest.approx(300.0)   # each match's two shares add to 100
    near = sum(row[x] for row in sm.xt.grid for x in (9, 10, 11))
    far = sum(row[x] for row in sm.xt.grid for x in (0, 1, 2))
    assert near > 2 * far   # threat rises toward the opponent's goal (three matches: zone by zone it is noisy)


def test_values_percentiles_and_evidence(small):
    _league, root, sm = small
    star = sm.player(STAR)
    assert star.info["position"] == "FW" and star.appearances == 1
    cell = sm.cell(star, "np_goals")
    assert cell["value"] == pytest.approx(star.totals["np_goals"] * 90 / star.minutes, abs=0.01)
    assert sm.evidence(star, "shots")["total"] == star.totals["shots"]
    ev = sm.evidence(star, "touches")
    assert ev["total"] == star.totals["touches"] > 0
    first = ev["items"][0]
    events = {r["id"]: r for r in iter_jsonl(root / first["match_id"] / "events.jsonl")}
    assert events[first["event_id"]]["event_type"] == "touch" and events[first["event_id"]]["player_id"] == first["player_id"]
    with_clip = [i for i in ev["items"] if i["clip_id"]]
    assert with_clip and all(i["video_url"].endswith(f"{i['clip_id']}.mp4") for i in with_clip)
    phys = sm.evidence(star, "distance")
    assert phys["per_match"] and phys["items"][0]["minutes"] > 0
    for ps in sm.players.values():
        for k, p in ps.percentiles.items():
            assert p is None or 0 <= p <= 100
            if p is not None:
                assert ps.minutes >= sm.min_minutes and ps.info["position"] in CATALOGUE[k].positions


def test_the_profile_and_the_terminal_give_one_percentile_for_one_stat(small):
    """The profile page and the Scout terminal use one rule (FBref's) and one pool (the qualifying minutes)."""
    from regista.season.profiles import Season

    league, root, sm = small
    season = Season.build(league, root)
    assert season.min_minutes == sm.min_minutes
    # (the profile's "shots" include penalty kicks, and say so in their label; the terminal's follow FBref and leave them
    # out, so they are not here)
    same = {"goals": "goals", "key_passes": "key_passes", "interceptions": "interceptions", "take_ons_won": "take_ons_won",
            "assists": "assists"}
    checked = 0
    for gid, p in season.profiles.items():
        ps = sm.player(gid)
        if ps is None or not p["appearances"]:
            continue
        for pk, mk in same.items():
            # the two pages must count a shared stat the same way (review A round 2: skipping differences hid that bug class)
            assert p["per90"][pk] == pytest.approx(round(ps.values[mk], 2), abs=0.011), (gid, pk)
            if p["percentiles"].get(pk) is not None and ps.percentiles.get(mk) is not None:
                assert p["percentiles"][pk] == ps.percentiles[mk], (gid, pk, p["percentiles"][pk], ps.percentiles[mk])
                checked += 1
    assert checked > 50


def test_evidence_limits(small):
    _league, _root, sm = small
    star = sm.player(STAR)
    for key in ("touches", "distance"):          # an event metric and a physical one behave alike
        full = sm.evidence(star, key)
        assert len(full["items"]) == full["total"] > 0
        assert sm.evidence(star, key, limit=0)["items"] == [] and sm.evidence(star, key, limit=0)["total"] == full["total"]
        assert len(sm.evidence(star, key, limit=1)["items"]) == 1


# ---------------------------------------------------------------------------- the API

@pytest.fixture
def client(small, monkeypatch, tmp_path):
    from regista import api

    league, root, _ = small
    monkeypatch.setattr(api, "SEASON_LEAGUE", save_league(league, tmp_path / "league.json"))
    monkeypatch.setattr(api, "SEASON_ROOT", root)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    return TestClient(api.app)


def _hidden_keys(obj, path="$"):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in HIDDEN:
                found.append(f"{path}.{k}")
            found += _hidden_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _hidden_keys(v, f"{path}[{i}]")
    return found


def test_api_shapes(client):
    cat = client.get("/api/metrics").json()
    assert len(cat["metrics"]) == len(CATALOGUE) and cat["season"]["synthetic"] and "synthetic" in cat["note"].lower()
    assert cat["xt"]["grid_x"] == 12 and len(cat["xt"]["values"]) == 8
    assert all({"definition", "rule", "sources", "unit", "positions", "higher_is_better", "kind"} <= set(m) for m in cat["metrics"])

    scr = client.get("/api/terminal/screen", params={"position": "FW", "metrics": "npxg,xa,take_on_pct", "min_minutes": 0}).json()
    assert [c["key"] for c in scr["columns"]] == ["npxg", "xa", "take_on_pct"] and scr["players"]
    assert all(p["position"] == "FW" for p in scr["players"])
    vals = [p["values"]["npxg"]["value"] for p in scr["players"]]
    assert vals == sorted(vals, reverse=True)
    assert {"value", "percentile", "qualified", "peers", "total"} <= set(scr["players"][0]["values"]["npxg"])
    assert {"num", "den"} <= set(scr["players"][0]["values"]["take_on_pct"])

    rk = client.get("/api/terminal/rank", params={"metric": "goals_conceded", "position": "GK", "min_minutes": 0}).json()
    assert rk["metric"]["higher_is_better"] is False
    ranked = [p["value"] for p in rk["players"]]
    assert ranked == sorted(ranked) and rk["players"][0]["rank"] == 1

    sc = client.get("/api/terminal/scatter", params={"x": "progressive_passes", "y": "progressive_carries", "min_minutes": 0}).json()
    assert sc["points"] and {"x", "y", "global_id"} <= set(sc["points"][0]) and sc["median"]["x"] is not None

    pm = client.get(f"/api/players/{STAR}/metrics", params={"evidence_limit": 3}).json()
    assert set(pm["metrics"]) == set(CATALOGUE) and pm["name"] == "Femi Toure"
    assert pm["metrics"]["shots"]["evidence"]["total"] >= len(pm["metrics"]["shots"]["evidence"]["items"])
    one = client.get(f"/api/players/{STAR}/metrics", params={"evidence": "touches"}).json()
    assert one["metric"]["key"] == "touches" and one["evidence"]["total"] == one["total"]
    assert len(one["evidence"]["items"]) == one["evidence"]["total"] > 10     # evidence=KEY: all of it (up to 500)
    assert len(pm["metrics"]["touches"]["evidence"]["items"]) == 3
    table = client.get(f"/api/players/{STAR}/metrics", params={"group": "passes"}).json()
    assert max(len(c["evidence"]["items"]) for c in table["metrics"].values()) == 10   # the table: 10 per metric by default
    for key in ("touches", "distance"):
        none = client.get(f"/api/players/{STAR}/metrics", params={"evidence": key, "evidence_limit": 0}).json()
        assert none["evidence"]["items"] == [] and none["evidence"]["total"] > 0

    fm = client.get(f"/api/players/{STAR}/form", params={"metrics": "np_goals,distance"}).json()
    assert len(fm["matches"]) == 1 and len(fm["metrics"]["distance"]["values"]) == 1 and "consistency_rule" in fm

    sim = client.get(f"/api/players/{STAR}/similar", params={"n": 3}).json()
    assert len(sim["similar"]) <= 3 and all(s["position"] == "FW" for s in sim["similar"])
    assert all(-1.0 <= s["similarity"] <= 1.0 for s in sim["similar"])

    st = client.get("/api/teams/cl_brookfield/style").json()
    assert {"possession_pct", "field_tilt_pct", "ppda", "direct_speed", "set_piece_xg"} <= set(st["values"])
    assert st["values"]["possession_pct"]["rank"] in range(1, 7) and len(st["per_match"]) == 1
    assert len(client.get("/api/teams").json()["teams"]) == 6


@pytest.mark.parametrize("url,code", [
    ("/api/terminal/rank?metric=bogus", 422),
    ("/api/terminal/rank", 422),
    ("/api/terminal/rank?metric=BAD-KEY", 422),
    ("/api/terminal/screen?metrics=npxg,nope", 422),
    ("/api/terminal/screen?position=XX", 422),
    ("/api/terminal/screen?role=ZZ", 422),
    ("/api/terminal/screen?foot=middle", 422),
    ("/api/terminal/screen?age_min=30&age_max=20", 422),
    ("/api/terminal/screen?limit=0", 422),
    ("/api/terminal/screen?sort=unknown_metric", 422),
    ("/api/terminal/scatter?x=npxg", 422),
    ("/api/players/pl_nobody_99/metrics", 404),
    ("/api/players/not-an-id/metrics", 400),
    ("/api/players/pl_bro_09/metrics?evidence=bogus", 422),
    ("/api/players/pl_bro_09/metrics?group=nogroup", 422),
    ("/api/players/pl_bro_09/form?metrics=bogus", 422),
    ("/api/players/pl_bro_09/similar?n=0", 422),
    ("/api/teams/cl_nowhere/style", 404),
    ("/api/teams/NOT/style", 400),
])
def test_api_validates_inputs(client, url, code):
    assert client.get(url).status_code == code


def test_filters(client):
    rows = client.get("/api/terminal/screen", params={"min_minutes": 0, "foot": "left", "limit": 200}).json()["players"]
    assert rows and all(p["preferred_foot"] == "left" for p in rows)
    rows = client.get("/api/terminal/screen", params={"min_minutes": 0, "age_min": 25, "age_max": 28, "limit": 200}).json()["players"]
    assert rows and all(25 <= p["age"] <= 28 for p in rows)
    rows = client.get("/api/terminal/screen", params={"min_minutes": 0, "role": "CB", "club": "BRO"}).json()["players"]
    assert rows and all(p["role"] == "CB" and p["club_id"] == "cl_brookfield" for p in rows)


def test_ratings_never_appear_in_terminal_json(client):
    payloads = {
        "catalogue": client.get("/api/metrics").json(),
        "screen": client.get("/api/terminal/screen", params={"min_minutes": 0, "limit": 200}).json(),
        "rank": client.get("/api/terminal/rank", params={"metric": "distance", "min_minutes": 0}).json(),
        "scatter": client.get("/api/terminal/scatter", params={"x": "peak_speed", "y": "sprints", "min_minutes": 0}).json(),
        "metrics": client.get(f"/api/players/{STAR}/metrics", params={"evidence_limit": 2}).json(),
        "form": client.get(f"/api/players/{STAR}/form").json(),
        "similar": client.get(f"/api/players/{STAR}/similar").json(),
        "teams": client.get("/api/teams").json(),
        "style": client.get("/api/teams/cl_brookfield/style").json(),
    }
    for name, body in payloads.items():
        assert not _hidden_keys(body), (name, _hidden_keys(body)[:5])
    assert not math.isnan(payloads["metrics"]["minutes"])
