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
# (fixture index, seed shift): league fixtures replayed with seeds shifted as the audit's extra seasons shift them. The
# committed season (generator 0.4.0) has no penalty and no red card: they are rare, about 0.3 and 0.1 a match.
PENALTY = (4, 1000)           # rl_r02_fai_dun, second season: a penalty (and a through ball)
RED = (9, 1000)               # rl_r04_cal_ash, second season: a red card (and through balls)


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

# sha256 of three committed fixtures' events.jsonl (as regista.schema.write_jsonl writes it), generator 0.4.0. A generator
# edit that moves them changes the season every page shows: re-record these, then re-check the demo's claims and clip ids
# (src/regista/static/shared/demo.js, docs/demo-storyboard.md) and regenerate data/season/summaries.json.
LEAGUE_PINS = {0: "e79b572dd1ba03782c462de4b58121826574034340d735e790461e695335e6aa",
               1: "e5edf0790b116767b8f885ba5efe51edea0ab5932a157d0b0896b8a7ac5a115b",
               2: "45227d1f657bd0f16c5230c5015dc1288c4d8c0aff8819607e748c45a40a7969"}
DEMO_JS = ROOT / "src" / "regista" / "static" / "shared" / "demo.js"


def test_the_committed_season_is_pinned(matches, tmp_path):
    from regista.schema import write_jsonl

    for i, want in LEAGUE_PINS.items():
        write_jsonl(tmp_path / f"{i}.jsonl", matches[i].stream)
        assert hashlib.sha256((tmp_path / f"{i}.jsonl").read_bytes()).hexdigest() == want, i


def test_every_clip_the_demo_cites_exists_and_is_the_stars_goal(league, tmp_path):
    """demo.js hard-codes clips of Femi Toure's goals (match id + clip id): each must be his clip, with his goal in it."""
    import re

    from regista.schema import iter_jsonl
    from regista.season.build import fixture_of, materialise

    refs = set(re.findall(r"match_id: '(rl_[a-z0-9_]+)', clip_id: '(cl_[a-z0-9_]+)'", DEMO_JS.read_text()))
    assert refs
    for match_id in {m for m, _c in refs}:
        folder = materialise(league, fixture_of(league, match_id), tmp_path)
        stream = list(iter_jsonl(folder / "events.jsonl"))
        star = next(p["player_id"] for p in stream[0]["players"] if p.get("global_player_id") == "pl_bro_09")
        clips = {c["id"]: c for c in iter_jsonl(folder / "clips.jsonl") if c["type"] == "clip"}
        goals = {e["id"] for e in stream if e.get("event_type") == "goal" and e.get("player_id") == star}
        for m, clip_id in refs:
            if m == match_id:
                assert clip_id in clips and clips[clip_id]["player_id"] == star, (m, clip_id)
                assert goals & set(clips[clip_id]["event_ids"]), (m, clip_id)


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
    """demo.js says how many goals Femi Toure scored this season ("Four goals this season"): it must be his tally."""
    import re

    from regista.season.audit import top_scorers

    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    said = {words[w.lower()] for w in re.findall(r"\b(\w+) goals this season", DEMO_JS.read_text()) if w.lower() in words}
    star = next(r for r in top_scorers(league, season, n=200) if r["global_id"] == "pl_bro_09")
    assert said == {star["goals"]}, (said, star)


@pytest.mark.slow
def test_players_in_the_same_role_now_differ(league, pooled):
    """The audit's split-half test (docs/scout-terminal/regista-data.md, section 0): before ratings, r within a kit
    slot was about 0 for every stat. Now the stats ratings drive must repeat from one half of the season to the other.
    Measured over three seasons: since generator 0.4.0 ratings move outcomes by realistic margins (the leaders sit near
    real leaders), so one season's halves (about five full matches each) are too short; goals (r about 0.25-0.3 over
    three seasons), tackles, interceptions and pressures no longer separate players in a role clearly
    (docs/scout-terminal/build/review-fixes-1.md, open issues)."""
    from regista.season.audit import split_half

    r = split_half(league, pooled)
    for key in ("passes", "shots", "xg", "carries", "key_passes", "take_ons_won", "distance_m", "sprints"):
        assert r[key]["r_slot"] is not None and r[key]["r_slot"] > 0.3, (key, r[key])


@pytest.fixture(scope="module")
def pooled(league):
    """Three seasons (seeds +0, +1000, +2000): about 900 minutes per regular, the Premier League pool's minimum, and about
    30 full matches, so rare events and leaders are measured on enough football. One season is about ten full matches:
    its goals per 90 alone swing by about 0.5 from seed to seed."""
    from regista.season.audit import season_matches

    return season_matches(league, seasons=3)


def _metrics(matches):
    return compute_metrics([r for _rnd, _h, stream in matches for r in stream])


@pytest.mark.slow
def test_the_committed_season_sits_in_every_physical_and_style_band(league, season):
    m = _metrics(season)
    for norms in (PHYSICAL_NORMS, STYLE_NORMS):
        assert all(v == "in band" for v in verdicts(m, norms).values()), {k: (m[k], norms[k][:2]) for k, v in
                                                                          verdicts(m, norms).items() if v != "in band"}


@pytest.mark.slow
def test_three_seasons_sit_in_every_event_league_and_leader_band(league, pooled):
    """Event rates, league-mode rates (penalties, red cards, crosses completed, progressive passes per carry) and the
    individual leaders (each league leader against the Premier League's third best, regista.synth.report.LEADER_V)."""
    m = _metrics(pooled)
    for norms in (NORMS, LEAGUE_NORMS, INDIVIDUAL_NORMS, PHYSICAL_NORMS):
        bad = {k: (m[k], norms[k][:2]) for k, v in verdicts(m, norms).items() if v != "in band"}
        assert not bad, bad


@pytest.mark.slow
def test_centre_backs_contest_the_most_aerial_duels(pooled):
    """FBref 2023/24 (via Football365): three of the five players with the most aerial duels won were centre-backs."""
    m = _metrics(pooled)
    assert m["cb_aerial_rank"] == 1, m["aerial_duels_per90_by_role"]


@pytest.mark.slow
def test_the_star_leads_the_league_in_npxg_over_three_seasons(league, pooled):
    """Finishing is worth a realistic edge (about a quarter over xG), so any scoring chart over a few matches is partly
    luck: over these three seasons Ustinov outscores him 8 to 6 from about 5 npxG to his 7.6 (over six, Toure leads 17
    to 15). What the star's ratings decide is the chances: he has the most non-penalty xG by a distance."""
    from regista.season.audit import top_scorers

    chart = sorted(top_scorers(league, pooled, n=200), key=lambda r: -r["np_xg"])
    assert chart[0]["global_id"] == "pl_bro_09" and chart[0]["np_xg"] > 1.3 * chart[1]["np_xg"], chart[:2]


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
