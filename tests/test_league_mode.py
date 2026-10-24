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
from regista.season.league import generate_kwargs, load_league
from regista.season.playing_time import played_seconds
from regista.synth.generator import LEAGUE_GENERATOR_VERSION, MatchSim, generate
from regista.synth.report import LEAGUE_NORMS, NORMS, compute_metrics, verdicts

ROOT = Path(__file__).resolve().parents[1]
LEAGUE_PATH = ROOT / "data" / "season" / "league.json"
FIXTURES = (0, 1, 2)          # fixtures generated for the fast tests
PENALTY_AND_RED = 18          # rl_r07_ash_eas: the committed league's fixture with a penalty and a red card


@pytest.fixture(scope="module")
def league():
    return load_league(LEAGUE_PATH)


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

def test_league_matches_validate_and_say_they_are_league_mode(matches):
    v = events_validator()
    for result in matches.values():
        bad = [(r["id"], v.errors(r)) for r in result.stream + result.tracks if not v.is_valid(r)]
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


def test_through_balls_are_real_now(matches):
    ev = [e for r in matches.values() for e in _events(r)]
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


def test_penalty_and_red_card(league):
    """A penalty is foul (penalty_conceded), foul_won (penalty_won), the penalty set piece and the taker's penalty shot;
    a red card takes the player off for the rest of the match. Fixture 18 (rl_r07_ash_eas) has both."""
    result = generate(**generate_kwargs(league, league["fixtures"][PENALTY_AND_RED]))
    ev = _events(result)
    kinds = Counter(e["event_type"] for e in ev)
    assert kinds["penalty"] and kinds["card_red"]
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
    a.attrs["finishing"] = 93
    hi = sim.goal_probability(a, keeper, 0.1)
    a.attrs["finishing"] = 60
    lo = sim.goal_probability(a, keeper, 0.1)
    assert hi > 0.12 > 0.1 > lo
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


def test_report_has_league_bands_only_for_league_streams(matches):
    m = compute_metrics([r for res in matches.values() for r in res.stream])
    assert set(LEAGUE_NORMS) <= set(m) and set(verdicts(m, LEAGUE_NORMS)) == set(LEAGUE_NORMS)
    old = compute_metrics(generate(seed=77, minutes=5.0, periods=2, profile="realistic").stream)
    assert set(NORMS) <= set(old) and not set(LEAGUE_NORMS) & set(old)


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
def test_players_in_the_same_role_now_differ(league, season):
    """The audit's split-half test (docs/scout-terminal/regista-data.md, section 0): before ratings, r within a kit
    slot was about 0 for every stat. Now the stats ratings drive must repeat from one half of the season to the other."""
    from regista.season.audit import split_half

    r = split_half(league, season)
    # Stats with clear signal in one season; rarer ones (take-on success, aerial duels) need several seasons to show it,
    # see docs/scout-terminal/build/generator.md.
    for key in ("passes", "shots", "goals", "interceptions", "carries", "key_passes"):
        assert r[key]["r_slot"] is not None and r[key]["r_slot"] > 0.3, (key, r[key])


@pytest.mark.slow
def test_the_league_season_sits_in_every_band(league, season):
    m = compute_metrics([r for _rnd, _h, stream in season for r in stream])
    assert all(v == "in band" for v in verdicts(m).values()), verdicts(m)
