"""League mode: when squads carry hidden ratings, the players decide outcomes and the 0.2.0 events appear.

Fast tests generate a few league fixtures (under a second each). Tests marked ``slow`` regenerate whole seasons and are
left out of the default run: ``python3 -m pytest -m slow``.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from regista.clips import derive_clips
from regista.schema import SCHEMA_VERSION, clips_validator, events_validator
from regista.season.league import generate_kwargs, load_league, player_attributes
from regista.season.playing_time import played_seconds
from regista.synth.generator import LEAGUE_GENERATOR_VERSION, MatchSim, generate
from regista.synth.physical import DEFINITIONS, METRICS
from regista.synth.report import (INDIVIDUAL_NORMS, LEAGUE_NORMS, NORMS, PHYSICAL_NORMS, STYLE_NORMS, compute_metrics,
                                  verdicts)

ROOT = Path(__file__).resolve().parents[1]
LEAGUE_PATH = ROOT / "data" / "season" / "league.json"
FIXTURES = (0, 1, 2)          # fixtures generated for the fast tests
# (fixture index, seed shift): league fixtures, replayed with seeds shifted as the audit's extra seasons shift them when
# the committed season lacks an event. Penalties and red cards are rare (about 0.07 and 0.06 a 30-minute match: 0.2 and
# 0.17 per 90 over six seasons, generator 0.7.0); the committed season has one penalty and two red cards.
PENALTY = (5, 0)              # rl_r02_cal_bro, the committed season: a penalty
RED = (2, 1000)               # rl_r01_cal_dun, second season: a red card (and a through ball)


@pytest.fixture(scope="module")
def league():
    return load_league(LEAGUE_PATH)


@pytest.fixture(scope="module")
def special(league):
    """The fixtures with a penalty and with a red card."""
    out = {}
    for i, shift in (PENALTY, RED):
        kw = generate_kwargs(league, league["fixtures"][i])
        kw["seed"] += shift
        out[(i, shift)] = generate(**kw)
    return out


@pytest.fixture(scope="module")
def matches(league):
    return {i: generate(**generate_kwargs(league, league["fixtures"][i])) for i in FIXTURES}


def _events(result):
    return [r for r in result.stream if r["type"] == "event"]


def _sha(records) -> str:
    h = hashlib.sha256()
    for r in records:
        h.update(json.dumps(r, separators=(",", ":"), ensure_ascii=False).encode())
    return h.hexdigest()


# ---------------------------------------------------------------------------- contract

TRACK_SAMPLE = 97   # every 97th track record (about 1,000 a match, every object and phase); every other record in full


def test_league_matches_validate_and_say_they_are_league_mode(matches):
    v = events_validator()
    for result in matches.values():
        bad = [(r["id"], v.errors(r)) for r in result.stream + result.tracks[::TRACK_SAMPLE] if not v.is_valid(r)]
        assert not bad, bad[:3]
        assert {r["schema_version"] for r in result.stream} == {SCHEMA_VERSION}
        assert result.match["generator"]["version"] == LEAGUE_GENERATOR_VERSION
        assert result.match["generator"]["params"]["profile"] == "league"


def test_same_league_and_seed_give_the_same_match(league, matches):
    again = generate(**generate_kwargs(league, league["fixtures"][FIXTURES[0]]))
    assert _sha(again.stream) == _sha(matches[FIXTURES[0]].stream)
    assert _sha(again.tracks) == _sha(matches[FIXTURES[0]].tracks)


def test_without_ratings_the_league_fixture_is_the_old_generator(league):
    kw = generate_kwargs(league, league["fixtures"][0], ratings=False)
    assert all(set(m) == {"global_id", "name"} for t in kw["teams"] for m in t["squad"])
    assert MatchSim(**{**kw, "minutes": 0.1}).league is False


def test_ratings_for_only_some_players_are_refused(league):
    kw = copy.deepcopy(generate_kwargs(league, league["fixtures"][0]))
    del kw["teams"][1]["squad"][4]["attributes"]
    with pytest.raises(ValueError, match="every member"):
        MatchSim(**kw)


# ---------------------------------------------------------------------------- the committed season, pinned

# sha256 of three committed fixtures' events.jsonl (as regista.schema.write_jsonl writes it), generator 0.7.1. A generator
# edit that moves them changes the season every page shows: re-record these and regista.season.pins, then re-check the
# demo's claims and clip ids (src/regista/static/shared/demo.js, docs/demo-storyboard.md), regenerate
# data/season/summaries.json and data/season/reliability.json. Recorded on macOS; CI checks them on Linux, where the live
# app builds the league (they agree since 0.7.1, which takes its transcendental functions from regista.detmath, not libm).
LEAGUE_PINS = {0: "f1c2807a9f3883ebdc0ae53195a7d6c9f74837cb62690e3deabf00c5029a4936",
               1: "afc1b9d9b86a2508e86bccb1931ef9ab7a4bcef496565a98d7ddfaac9ae97a65",
               2: "0172a8f04cba71b0e3e1d11c8bc46f6cbdcc8f6c1ff51f38eefee1c470f6e808"}
DEMO_JS = ROOT / "src" / "regista" / "static" / "shared" / "demo.js"


def test_the_committed_season_is_pinned(matches, tmp_path):
    from regista.schema import write_jsonl

    for i, want in LEAGUE_PINS.items():
        write_jsonl(tmp_path / f"{i}.jsonl", matches[i].stream)
        assert hashlib.sha256((tmp_path / f"{i}.jsonl").read_bytes()).hexdigest() == want, i


def test_the_whole_committed_season_is_the_same_on_every_platform(league):
    """Every fixture of the committed season, built as the server builds it (regista.season.build), matches the hashes
    recorded on macOS (regista.season.pins). On CI this runs on Linux: before 0.7.1 libm's last bits made fixtures
    differ there."""
    from regista.season.build import build_all
    from regista.season.pins import SEASON_PINS, drift

    root = ROOT / "data" / "season" / "matches"
    build_all(league, root)
    assert set(SEASON_PINS) == {fx["match_id"] for fx in league["fixtures"]}
    assert all(SEASON_PINS[league["fixtures"][i]["match_id"]] == LEAGUE_PINS[i][:16] for i in LEAGUE_PINS)
    moved = drift(league, root)
    assert not moved, f"{len(moved)} of {len(SEASON_PINS)} matches generated differently here: {sorted(moved)}"


def test_every_clip_the_demo_cites_exists_and_shows_what_its_title_says(league, tmp_path):
    """demo.js hard-codes clips of Femi Toure (match id + clip id + title): each must be his clip, and hold his goal when
    its title names a goal, his take-on when it names a take-on."""
    import re

    from regista.schema import iter_jsonl
    from regista.season.build import fixture_of, materialise

    refs = set(re.findall(r"match_id: '(rl_[a-z0-9_]+)', clip_id: '(cl_[a-z0-9_]+)', title: \"Femi Toure \(9\): ([a-z-]+) at",
                          DEMO_JS.read_text()))
    assert refs and {kind for _m, _c, kind in refs} == {"goal", "take-on"}
    assert len(refs) == DEMO_JS.read_text().count("clip_id: 'cl_")
    for match_id in {m for m, _c, _k in refs}:
        folder = materialise(league, fixture_of(league, match_id), tmp_path)
        stream = list(iter_jsonl(folder / "events.jsonl"))
        star = next(p["player_id"] for p in stream[0]["players"] if p.get("global_player_id") == "pl_bro_09")
        clips = {c["id"]: c for c in iter_jsonl(folder / "clips.jsonl") if c["type"] == "clip"}
        for m, clip_id, kind in refs:
            if m == match_id:
                assert clip_id in clips and clips[clip_id]["player_id"] == star, (m, clip_id)
                want = {e["id"] for e in stream if e.get("event_type") == kind.replace("-", "_") and e.get("player_id") == star}
                assert want & set(clips[clip_id]["event_ids"]), (m, clip_id, kind)


# ---------------------------------------------------------------------------- the new events

def test_substitutions_from_about_the_hour_mark_like_for_like(matches):
    for result in matches.values():
        roster = {p["player_id"]: p for p in result.match["players"]}
        subs = [e for e in _events(result) if e["event_type"] == "substitution"]
        per_team = Counter(e["team_id"] for e in subs)
        assert all(1 <= n <= 5 for n in per_team.values()), per_team
        seen = set()
        second_half = next(p for p in result.match["periods"] if p["period"] == 2)
        for e in subs:
            off, on = roster[e["player_id"]], roster[e["related_player_id"]]
            assert off["team_id"] == on["team_id"] == e["team_id"]
            assert not on["starter"] and off["position"] != "GK" and on["position"] != "GK"
            assert e["player_id"] not in seen and e["related_player_id"] not in seen   # nobody goes twice or comes back
            seen |= {e["player_id"], e["related_player_id"]}
            assert e["t"] >= second_half["t"]   # 58% of a two-half match is in the second half
            # the player who came off does nothing afterwards; the one who came on does nothing before
            later = [x for x in _events(result) if x["t"] > e["t"] and x.get("player_id") == e["player_id"]]
            earlier = [x for x in _events(result) if x["t"] < e["t"] and x.get("player_id") == e["related_player_id"]]
            assert not later and not earlier


def test_aerial_duels_are_one_record_for_two_players_of_opposite_teams(matches):
    duels = [e for r in matches.values() for e in _events(r) if e["event_type"] == "aerial_duel"]
    assert duels
    for result in matches.values():
        team = {p["player_id"]: p["team_id"] for p in result.match["players"]}
        for e in _events(result):
            if e["event_type"] == "aerial_duel":
                assert team[e["player_id"]] == e["team_id"] != team[e["related_player_id"]]
                assert e["outcome"] == "success" and e["qualifiers"][0] in ("cross", "long_ball", "goal_kick")


def test_offsides_end_the_pass_and_restart_with_an_indirect_free_kick(matches):
    found = 0
    for result in matches.values():
        ev = _events(result)
        for i, e in enumerate(ev):
            if e["event_type"] != "offside":
                continue
            found += 1
            passed = next(x for x in reversed(ev[:i]) if x["event_type"] in ("pass", "cross"))
            assert passed["outcome"] == "fail" and "offside" in passed["qualifiers"]
            assert passed["related_player_id"] == e["player_id"] and passed["player_id"] == e["related_player_id"]
            restart = next(x for x in ev[i + 1:] if x["event_type"] in ("free_kick", "throw_in", "corner", "goal_kick", "kick_off"))
            assert restart["event_type"] == "free_kick" and restart["qualifiers"] == ["indirect"]
            assert restart["team_id"] != e["team_id"]
        lost = [p for p in result.events if p["type"] == "possession" and p["lost_by"] == "offside"]
        assert len(lost) == sum(1 for e in ev if e["event_type"] == "offside")
    assert found


def test_through_balls_are_real_now(special):
    ev = [e for r in special.values() for e in _events(r)]
    through = [e for e in ev if e["event_type"] == "pass" and "through_ball" in e.get("qualifiers", [])]
    assert through and all("forward" in e["qualifiers"] for e in through)


def test_every_shot_after_a_completed_pass_makes_it_a_key_pass(matches):
    for result in matches.values():
        ev = _events(result)
        by_id = {e["id"]: e for e in ev}
        poss = {p["id"]: p for p in result.events if p["type"] == "possession"}
        for shot in (e for e in ev if e["event_type"] == "shot" and "penalty" not in e.get("qualifiers", [])):
            po = poss[shot["possession_id"]]
            if po["gained_by"] != "pass_received":
                continue
            feeder = next(e for e in reversed(ev) if e["t"] <= po["t"] and e["event_type"] in ("pass", "cross")
                          and e["outcome"] == "success" and e["related_player_id"] == shot["player_id"])
            assert "key_pass" in by_id[feeder["id"]]["qualifiers"], (shot["id"], feeder["id"])
        kp = sum(1 for e in ev if "key_pass" in e.get("qualifiers", []))
        assert kp <= sum(1 for e in ev if e["event_type"] == "shot")


@pytest.mark.parametrize("which", [PENALTY, RED])
def test_penalty_and_red_card(special, which):
    """A penalty is foul (penalty_conceded), foul_won (penalty_won), the penalty set piece and the taker's penalty shot;
    a red card takes the player off for the rest of the match."""
    result = special[which]
    ev = _events(result)
    kinds = Counter(e["event_type"] for e in ev)
    assert kinds["penalty" if which == PENALTY else "card_red"]
    for i, e in enumerate(ev):
        if e["event_type"] == "penalty":
            foul = next(x for x in reversed(ev[:i]) if x["event_type"] == "foul")
            won = next(x for x in reversed(ev[:i]) if x["event_type"] == "foul_won")
            assert foul["qualifiers"] == ["penalty_conceded"] and won["qualifiers"] == ["penalty_won"]
            shot = next(x for x in ev[i:] if x["event_type"] == "shot")
            assert shot["player_id"] == e["player_id"] and "penalty" in shot["qualifiers"] and shot["metrics"]["xg"] == 0.79
            assert not any("key_pass" in x.get("qualifiers", []) for x in ev if x["t"] <= shot["t"] and x["t"] >= foul["t"])
        if e["event_type"] == "card_red":
            assert e["qualifiers"][0] in ("second_yellow", "straight_red")
            assert not [x for x in ev[i + 1:] if x.get("player_id") == e["player_id"]]
            assert played_seconds(result.stream)[e["player_id"]] < sum(p["t_end"] - p["t"] for p in result.match["periods"])


# ---------------------------------------------------------------------------- ratings move outcomes

def test_ratings_move_the_probabilities(league):
    sim = MatchSim(**{**generate_kwargs(league, league["fixtures"][0]), "minutes": 0.1})
    a, b = sim.home.players[9], sim.away.players[3]   # a striker, a centre-back
    keeper = sim.away.keeper
    a.attrs, keeper.attrs = dict(a.attrs), dict(keeper.attrs)
    keeper.attrs["shot_stopping"] = 75   # an average keeper (SKILL_CENTRE)
    a.attrs["finishing"] = 97
    hi = sim.goal_probability(a, keeper, 0.1)
    a.attrs["finishing"] = 45
    lo = sim.goal_probability(a, keeper, 0.1)
    assert 0.14 > hi > 0.12 > 0.1 > lo   # the league's best finisher beats xG by about a quarter, not by double
    keeper.attrs["shot_stopping"] = 95
    assert sim.goal_probability(a, keeper, 0.1) < lo
    assert sim.goal_probability(a, keeper, 0.1, weak=True) < sim.goal_probability(a, keeper, 0.1)
    a.attrs["dribbling"], b.attrs = 90, dict(b.attrs)
    b.attrs["defending"] = 50
    easy = sim.take_on_probability(a, b)
    b.attrs["defending"] = 90
    assert easy > 0.5 > sim.take_on_probability(a, b)
    a.attrs["aerial"], b.attrs["aerial"] = 60, 60
    a.height_cm, b.height_cm = 170, 195
    short = sim.aerial_probability(a, b)
    a.height_cm = 195
    assert short < sim.aerial_probability(a, b) < 0.5   # equal men: the defender's small edge


# ---------------------------------------------------------------------------- clips, profiles, report

def test_clips_accept_the_new_events_and_never_use_substitutions(matches):
    result = matches[FIXTURES[0]]
    ev = {e["id"]: e for e in _events(result)}
    v = clips_validator()
    played = played_seconds(result.stream)
    tags = Counter()
    for pid in played:
        clips, labels = derive_clips(result.stream, pid)
        assert all(v.is_valid(r) for r in clips + labels)
        for c in clips:
            assert not any(ev[i]["event_type"] == "substitution" for i in c["event_ids"] if i in ev)
        for lb in labels:
            tags.update(lb["tags"])
    assert "substitution" not in tags


def test_time_on_the_pitch(matches):
    for result in matches.values():
        played = played_seconds(result.stream)
        whole = sum(p["t_end"] - p["t"] for p in result.match["periods"])
        roster = {p["player_id"]: p for p in result.match["players"]}
        subs = [e for e in _events(result) if e["event_type"] == "substitution"]
        for e in subs:
            assert 0 < played[e["player_id"]] < whole and 0 < played[e["related_player_id"]] < whole
            assert played[e["player_id"]] + played[e["related_player_id"]] == pytest.approx(whole, abs=1e-6)
        assert all(roster[p]["starter"] or p in {e["related_player_id"] for e in subs} for p in played)
        unchanged = [p for p in played if roster[p]["starter"] and p not in {e["player_id"] for e in subs}]
        sent_off = {e["player_id"] for e in _events(result) if e["event_type"] == "card_red"}
        assert all(played[p] == whole for p in unchanged if p not in sent_off)


def test_the_report_never_modifies_the_stream_it_reads(matches):
    """compute_metrics once wrote helper fields into the physical records, which then failed the schema (no extra fields)."""
    stream = copy.deepcopy(matches[FIXTURES[0]].stream)
    before = _sha(stream)
    compute_metrics(stream)
    assert _sha(stream) == before
    v = events_validator()
    assert all(v.is_valid(r) for r in stream if r["type"] == "physical")


def test_report_has_league_bands_only_for_league_streams(matches):
    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert set(LEAGUE_NORMS) <= set(m) and set(verdicts(m, LEAGUE_NORMS)) == set(LEAGUE_NORMS)
    old = compute_metrics(generate(seed=77, minutes=5.0, periods=2, profile="realistic").stream)
    assert set(NORMS) <= set(old) and not set(LEAGUE_NORMS) & set(old)


def test_one_seasons_leaders_and_rare_events_are_indicative(matches):
    """Review round 2: the report the realism rule names printed failures for one season's leaders. A regular's season is
    about 300 minutes, so leader bands (and penalties and red cards) are a verdict only over six pooled seasons; on fewer
    they are marked indicative, with each leader's minutes beside his value."""
    from regista.synth.report import (INDICATIVE, LEADER_SEASONS, LEADER_V, individual_verdicts, league_verdicts,
                                      render_markdown)

    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert m["seasons"] == 1
    assert all(v.endswith(INDICATIVE) or v == "n/a" for v in individual_verdicts(m).values())
    lv = league_verdicts(m)
    assert lv["penalties_per90"].endswith(INDICATIVE) and lv["red_cards_per90"].endswith(INDICATIVE)
    assert not any(lv[k].endswith(INDICATIVE) for k in ("cross_completion", "save_pct", "shot_accuracy_ex_blocks"))
    assert all(f"leader_{k}_minutes" in m for k in LEADER_V)
    pooled = dict(m, seasons=LEADER_SEASONS)
    assert individual_verdicts(pooled) == verdicts(pooled, INDIVIDUAL_NORMS)
    assert league_verdicts(pooled) == verdicts(pooled, LEAGUE_NORMS)
    md = render_markdown(m, "three fixtures", "league")
    assert INDICATIVE in md and " min) |" in md


def test_shot_keeper_and_take_on_bands_are_computed(matches):
    """Round 2's new league bands, each with its source in LEAGUE_NORMS: shot accuracy without blocks, save %, keepers'
    long-pass share and take-on success; and the leader's shots on target among the leader bands."""
    m = compute_metrics([r for res in matches.values() for r in res.stream])
    for key in ("shot_accuracy_ex_blocks", "save_pct", "gk_long_pass_share", "take_on_success"):
        assert key in LEAGUE_NORMS and 0.0 < m[key] < 1.0, key
        assert any(w in LEAGUE_NORMS[key][3] for w in ("premierleague.com", "Opta Analyst")), key
    assert "leader_shots_on_target_per90" in INDIVIDUAL_NORMS and m["leader_shots_on_target_per90"] > 0
    assert m["shot_outcomes"].startswith("goal ")


def test_role_shapes_and_leader_gaps_are_computed_and_reported(matches):
    """Review closing round 1: role shapes (ROLE_SHAPES, an order between roles with StatMuse examples), the leader's
    lead over the next player and the largest share of a club's npxG; touches in the box have no leader band (Regista's
    touch records are not FBref's touches)."""
    from regista.synth.report import LEADER_V, ROLE_SHAPES, render_markdown, role_shape_checks, role_shape_verdicts

    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert "touches_in_box" not in LEADER_V and "leader_touches_in_box_per90" not in INDIVIDUAL_NORMS
    for key in ("leader_npxg_gap", "leader_goals_gap", "top_npxg_share"):
        assert key in INDIVIDUAL_NORMS and key in m, key
    assert "StatMuse" in INDIVIDUAL_NORMS["top_npxg_share"][3] and "Haaland" in INDIVIDUAL_NORMS["leader_npxg_gap"][3]
    assert set(m["role_per90"]) >= {"passes", "touches", "crosses", "tackles_won", "fouls_won"}
    assert all(isinstance(m[f"shape_{k}"], bool) for k in ROLE_SHAPES)
    assert all(v.endswith("(under 6 seasons)") for v in role_shape_verdicts(m).values())   # three matches: indicative
    assert all("StatMuse" in src or "LEADER_V" in src or "Palhinha" in src or "FBref" in src for _o, src in ROLE_SHAPES.values())
    md = render_markdown(m, "three matches", "league")
    assert "## Role shapes (league mode)" in md and all(f"| {k} |" in md for k in ROLE_SHAPES)
    # the orders themselves, on a hand-made table: 0.5.0's role means (review closing round 1) fail every check
    old = {"passes": {"CB": 32.0, "DM": 40.9, "ST": 62.6}, "touches": {"CB": 41.4, "DM": 55.3, "ST": 84.6},
           "crosses": {"FB": 0.31, "W": 6.46}, "tackles_won": {"CB": 1.45, "FB": 2.17, "DM": 3.14, "ST": 2.96},
           "fouls_won": {"CB": 1.26, "W": 0.89, "ST": 0.98}}
    assert not any(role_shape_checks(old).values())
    # 0.6.0's role means (review closing round 2): full-backs "crossed" a third as often as wingers, but from a median 52.6
    # m out (their own half); centre-backs progressed and went long less than strikers; full-backs touched it less than
    # wingers
    v060 = {"passes": {"CB": 44.1, "DM": 56.2, "ST": 30.2}, "touches": {"CB": 52.8, "FB": 46.2, "DM": 70.3, "W": 58.9,
            "ST": 46.4}, "crosses": {"FB": 3.1, "W": 8.0}, "tackles_won": {"CB": 1.91, "FB": 1.73, "DM": 3.56, "ST": 1.09},
            "fouls_won": {"CB": 0.49, "W": 1.72, "ST": 1.55}, "progressive_passes": {"CB": 0.95, "FB": 1.41, "ST": 1.47},
            "long_passes": {"CB": 1.89, "ST": 2.17}}
    failed = {k for k, ok in role_shape_checks(v060, fb_cross_start_m=52.6).items() if not ok}
    assert failed == {"touches_fb_over_w", "fb_crosses_third_of_w", "prog_passes_cb_fb_over_st", "cb_long_passes_floor"}
    new = {"passes": {"CB": 46.0, "DM": 53.0, "ST": 32.0}, "touches": {"CB": 54.0, "FB": 57.5, "DM": 65.0, "W": 47.4,
           "ST": 47.1}, "crosses": {"FB": 3.4, "W": 7.7}, "tackles_won": {"CB": 2.0, "FB": 1.8, "DM": 3.8, "ST": 0.8},
           "fouls_won": {"CB": 0.6, "W": 1.4, "ST": 1.4}, "progressive_passes": {"CB": 2.1, "FB": 3.3, "ST": 1.4},
           "long_passes": {"CB": 4.0, "ST": 2.6}}
    assert all(role_shape_checks(new, fb_cross_start_m=35.4).values())
    assert not role_shape_checks(new, fb_cross_start_m=None)["fb_crosses_third_of_w"]   # no full-back cross at all


def test_a_cross_starts_near_the_box_and_is_for_a_teammate_attacking_it(matches):
    """Review closing round 2: the target was picked first (in build-up, mostly centre-backs and the holding midfielder)
    and any wide pass past a line measured from the passer's own goal line became a cross into the box. Now the cross is
    decided first, from the final 35-40 m (regista.synth.generator.LEAGUE["cross_zone_m"]), and aimed at an outfielder
    attacking the box; the report shows where crosses start and who receives them."""
    from regista.synth.generator import LEAGUE, PITCH_L, ROLE_OF_KIT

    seen = 0
    for res in matches.values():
        header = res.match
        role = {p["player_id"]: ROLE_OF_KIT[p["kit_number"]] for p in header["players"]}
        ltr = {p["period"]: p["left_to_right_team_id"] for p in header["periods"]}
        for e in _events(res):
            if e["event_type"] != "cross":
                continue
            seen += 1
            to_line = PITCH_L - e["pitch"]["x"] if ltr[e["clock"]["period"]] == e["team_id"] else e["pitch"]["x"]
            assert to_line < LEAGUE["cross_zone_m"].get(role[e["player_id"]], 35.0), (e["id"], to_line)
            assert role[e["related_player_id"]] != "GK"
    assert seen > 10
    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert m["cross_start_m_by_role"]["W"] < 40.0 and sum(m["crosses_received_by_role"].values()) == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------- physical: motion at 10 Hz

def _physical(result):
    return {r["player_id"]: r for r in result.stream if r["type"] == "physical"}


def test_every_player_who_played_has_one_physical_record(league, matches):
    for result in matches.values():
        phys = [r for r in result.stream if r["type"] == "physical"]
        played = played_seconds(result.stream)
        assert sorted(r["player_id"] for r in phys) == sorted(played)
        assert result.stream[-len(phys):] == phys                       # they close the stream
        for r in phys:
            # the meters count every 0.1 s step he is on the pitch while the clock runs: video time inside the periods
            assert r["played_s"] == pytest.approx(played[r["player_id"]], abs=1.0)
            assert sum(p["played_s"] for p in r["periods"]) == pytest.approx(r["played_s"], abs=0.2)
            assert r["method"]["sample_hz"] == 10 and r["source"] == "synthetic"


def test_physical_metrics_add_up_and_stay_within_each_players_pace(league, matches):
    attrs = player_attributes(league)
    for result in matches.values():
        gid = {p["player_id"]: p["global_player_id"] for p in result.match["players"]}
        for pid, r in _physical(result).items():
            m = r["metrics"]
            assert set(m) == set(METRICS) and all(k in DEFINITIONS for k in m)
            zones = sum(m[f"zone{i}_m"] for i in range(1, 6))
            assert zones == pytest.approx(m["distance_m"], abs=0.6)
            assert m["hi_distance_m"] == pytest.approx(m["zone4_m"] + m["zone5_m"], abs=0.2)
            assert m["sprint_distance_m"] == m["zone5_m"]
            a = attrs[gid[pid]]
            assert m["peak_speed_kmh"] <= a["top_speed_kmh"] + 0.05      # nobody runs faster than his own top speed
            assert m["sprints"] <= m["hi_efforts"] or m["sprints"] == 0
            if r["played_s"] >= 600 and a.get("shot_stopping") is None:  # outfielders with ten minutes or more
                per90 = m["distance_m"] / r["played_s"] * 5.4
                assert 6.0 < per90 < 14.0, (pid, per90)
                assert m["walking_s"] + m["jogging_s"] <= r["played_s"] + 0.1


def test_motion_never_runs_without_ratings(league):
    plain = generate(seed=77, minutes=3.0, periods=2, profile="realistic").stream
    assert not [r for r in plain if r["type"] == "physical"]
    kw = generate_kwargs(league, league["fixtures"][0], ratings=False)
    assert not [r for r in generate(**kw).stream if r["type"] == "physical"]


def test_physical_bands_appear_for_league_streams(matches):
    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert set(PHYSICAL_NORMS) <= set(m)
    old = compute_metrics(generate(seed=77, minutes=5.0, periods=2, profile="realistic").stream)
    assert not set(PHYSICAL_NORMS) & set(old)


def test_the_renderer_draws_a_league_match(league, tmp_path):
    from regista.render.draw import render_frame
    from regista.render.scene import Scene
    from regista.season.build import ensure_tracks

    fx = league["fixtures"][0]
    folder = ensure_tracks(league, fx, tmp_path)
    scene = Scene.load(folder)
    for t in (5.0, 300.0, 1000.0):
        img = render_frame(scene, t)
        assert img.size[0] > 0 and img.getbbox() is not None


# ---------------------------------------------------------------------------- whole seasons (slow)

@pytest.fixture(scope="module")
def season(league):
    from regista.season.audit import season_matches

    return season_matches(league)


@pytest.mark.slow
def test_femi_toure_is_the_leagues_top_scorer(league, season):
    from regista.season.audit import top_scorers

    chart = top_scorers(league, season)
    assert chart[0]["global_id"] == "pl_bro_09" and chart[0]["goals"] > chart[1]["goals"]


@pytest.mark.slow
def test_the_demos_goal_count_is_the_stars(league, season):
    """demo.js says how many goals Femi Toure scored this season ("Three league goals"): it must be his tally."""
    import re

    from regista.season.audit import top_scorers

    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    said = {words[w.lower()] for w in re.findall(r"\b(\w+) (?:league goals|goals this season)", DEMO_JS.read_text()) if w.lower() in words}
    star = next(r for r in top_scorers(league, season, n=200) if r["global_id"] == "pl_bro_09")
    assert said == {star["goals"]}, (said, star)
    assert len(re.findall(r"\b(?:\w+) (?:league goals|goals this season)", DEMO_JS.read_text())) >= 3  # message, note, report


@pytest.mark.slow
def test_players_in_the_same_role_now_differ(league, pooled):
    """The audit's split-half test (docs/scout-terminal/regista-data.md, section 0): before ratings, r within a kit
    slot was about 0 for every stat. Now the stats ratings drive must repeat from one half of the season to the other.
    Measured over six seasons: since generator 0.4.0 ratings move outcomes by realistic margins (the leaders sit near
    real leaders), so one season's halves (about five full matches each) are too short; goals, tackles, interceptions and
    pressures no longer separate players in a role clearly over one season, and the Scout terminal marks such metrics
    noisy (regista.season.reliability, data/season/reliability.json)."""
    from regista.season.audit import split_half

    r = split_half(league, pooled)
    for key in ("passes", "shots", "xg", "carries", "key_passes", "take_ons_won", "distance_m", "sprints"):
        assert r[key]["r_slot"] is not None and r[key]["r_slot"] > 0.3, (key, r[key])


@pytest.fixture(scope="module")
def pooled(league):
    """Six seasons (seeds +0, +1000, ..., +5000): about 1,800 minutes per regular and about 60 full matches, so rare events
    and leaders are measured on enough football (regista.synth.report.LEADER_SEASONS). One season is about ten full
    matches: its goals per 90 alone swing by about 0.5 from seed to seed, and three seasons proved too few in review round
    2 (the first three hold one penalty where about six are expected)."""
    from regista.season.audit import season_matches
    from regista.synth.report import LEADER_SEASONS

    return season_matches(league, seasons=LEADER_SEASONS)


def _metrics(matches):
    return compute_metrics([r for _rnd, _h, stream in matches for r in stream])


@pytest.mark.slow
def test_the_committed_season_sits_in_every_band_that_is_a_verdict_on_one_season(league, season):
    """The season every page shows: event, league-mode (shot accuracy, save %, keepers' long passes, take-ons, crosses,
    ...), physical and style bands. Leaders, penalties and red cards are verdicts over six seasons (below)."""
    from regista.synth.report import INDICATIVE, league_verdicts

    m = _metrics(season)
    for norms in (NORMS, PHYSICAL_NORMS, STYLE_NORMS):
        assert all(v == "in band" for v in verdicts(m, norms).values()), {k: (m[k], norms[k][:2]) for k, v in
                                                                          verdicts(m, norms).items() if v != "in band"}
    bad = {k: (m[k], LEAGUE_NORMS[k][:2]) for k, v in league_verdicts(m).items() if v != "in band" and INDICATIVE not in v}
    assert not bad, bad


@pytest.mark.slow
def test_six_seasons_sit_in_every_event_league_and_leader_band(league, pooled):
    """Event rates, league-mode rates (penalties, red cards, crosses completed, progressive passes per carry) and the
    individual leaders (each league leader against the Premier League's third best, regista.synth.report.LEADER_V; the
    leader's lead over the next player; the largest share of a club's npxG)."""
    m = _metrics(pooled)
    for norms in (NORMS, LEAGUE_NORMS, INDIVIDUAL_NORMS, PHYSICAL_NORMS):
        bad = {k: (m[k], norms[k][:2]) for k, v in verdicts(m, norms).items() if v != "in band"}
        assert not bad, bad


@pytest.mark.slow
def test_centre_backs_win_the_most_aerial_duels(pooled):
    """FBref 2023/24 (via Football365): three of the five players with the most aerial duels won were centre-backs, the
    other two target forwards. Since generator 0.5.0 keepers launch long to the front three, so strikers contest about as
    many duels as centre-backs; centre-backs must still win the most, and contest more than any other defender."""
    m = _metrics(pooled)
    assert m["cb_aerial_won_rank"] == 1, m["aerial_duels_won_per90_by_role"]
    assert m["cb_aerial_rank"] <= 2, m["aerial_duels_per90_by_role"]


@pytest.mark.slow
def test_the_star_leads_the_league_in_npxg_over_six_seasons(league, pooled):
    """Finishing is worth a realistic edge (about a quarter over xG), so any scoring chart over a few matches is partly
    luck (generator 0.7.0: he is the outright top scorer in 5 of 12 regenerated seasons, the committed one included;
    a season's top scorer has three to six goals; 4 of 12 with 0.6.0). What the star's ratings decide is the chances: he has the most
    non-penalty xG by a distance, but not by an unrealistic one (the leader-gap bands, below)."""
    from regista.season.audit import top_scorers

    chart = sorted(top_scorers(league, pooled, n=200), key=lambda r: -r["np_xg"])
    assert chart[0]["global_id"] == "pl_bro_09" and chart[0]["np_xg"] > 1.3 * chart[1]["np_xg"], chart[:2]


@pytest.mark.slow
def test_the_star_is_not_the_leagues_only_scoring_threat(pooled):
    """Review closing round 1: over six seasons the star had 2.4 times the next player's npxG per 90 and took 46% of his
    club's npxG. Now the leader's lead over the second best and the largest share of a club's chances are banded
    (regista.synth.report: leader_npxg_gap, leader_goals_gap, top_npxg_share, each with its source)."""
    from regista.synth.report import INDIVIDUAL_NORMS

    m = _metrics(pooled)
    for key in ("leader_npxg_gap", "leader_goals_gap", "top_npxg_share"):
        lo, hi = INDIVIDUAL_NORMS[key][:2]
        assert lo <= m[key] <= hi, (key, m[key], (lo, hi))


@pytest.mark.slow
def test_roles_make_the_numbers_they_make_in_football(season, pooled):
    """Review closing round 1: strikers passed and touched the ball the most, full-backs hardly crossed, strikers won as
    many tackles as holding midfielders and were fouled the least. regista.synth.report.ROLE_SHAPES checks the order
    between roles, each against StatMuse's Premier League examples; it holds over six seasons and in the committed one."""
    from regista.synth.report import ROLE_SHAPES, role_shape_verdicts

    for matches in (pooled, season):
        m = _metrics(matches)
        v = role_shape_verdicts(m)
        assert set(v) == set(ROLE_SHAPES)
        assert all(x.startswith("holds") for x in v.values()), (v, m["role_per90"])


@pytest.mark.slow
def test_crosses_are_met_by_the_players_attacking_the_box(pooled):
    """Review closing round 2: 40% of completed crosses went to centre-backs, holding midfielders and full-backs, who were
    a median 40-60 m from where the ball came down. Over six seasons the forwards (strikers, wingers, the 10) must receive
    the great majority, and every role's open-play crosses start, at the median, within 40 m of the opponent's goal line."""
    m = _metrics(pooled)
    got = m["crosses_received_by_role"]
    assert sum(got.get(r, 0.0) for r in ("ST", "W", "AM")) >= 0.85, got
    assert got.get("CB", 0.0) + got.get("DM", 0.0) + got.get("FB", 0.0) <= 0.05, got
    assert max(m["cross_start_m_by_role"].values()) <= 40.0, m["cross_start_m_by_role"]


@pytest.mark.slow
def test_physical_output_varies_by_position_and_pace(league, season, pooled):
    """FIFA's 2022 World Cup tracking (Bradley 2023, Part 1): holding and central midfielders cover the most ground,
    wide players the most high-intensity distance, wide and attacking roles reach higher top speeds than centre-backs and
    central midfielders. And within a role, the faster player (``top_speed_kmh``) reaches the higher top speed."""
    import statistics

    m = compute_metrics([r for _rnd, _h, stream in season for r in stream])
    assert m["cm_dm_distance_over_others"] > 1.05
    assert m["wide_hi_over_central"] > 1.15
    assert m["wide_peak_minus_central_kmh"] > 1.0
    attrs = player_attributes(league)
    peaks: dict[str, float] = {}
    for _rnd, header, stream in pooled:   # three seasons: more chances for each player to reach his top speed
        gid = {p["player_id"]: p["global_player_id"] for p in header["players"]}
        for r in stream:
            if r["type"] == "physical" and r["played_s"] >= 600:
                g = gid[r["player_id"]]
                peaks[g] = max(peaks.get(g, 0.0), r["metrics"]["peak_speed_kmh"])
    outfield = [g for g in peaks if "shot_stopping" not in attrs[g]]
    r = statistics.correlation([attrs[g]["top_speed_kmh"] for g in outfield], [peaks[g] for g in outfield])
    assert r > 0.6, r
