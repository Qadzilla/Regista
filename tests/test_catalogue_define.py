"""The catalogue's definition (docs/catalogue/build/design.md §2, §4 and §11, items 2-5): 13 new competitions with invented
clubs and people, hidden ratings scaled by level, sparse uploaded matches with uploader and camera, five careers, and the
Regista League kept as the England semi-pro men competition by reference (league.json is never written).
"""

from __future__ import annotations

import itertools
import json
import re
from collections import Counter
from pathlib import Path
from statistics import fmean

import pytest

from regista.catalogue import define as D
from regista.catalogue import store
from regista.catalogue.clubs import RESERVED_SHORT_NAMES
from regista.catalogue.taxonomy import BY_ID, CAMERAS, COMPETITIONS, ENGLAND_ID, LEVELS, TIERS
from regista.season.league import (ATTRIBUTE_KEYS, GK_RATINGS, RATINGS, ROLE_OF_KIT, STAR, STAR_RATINGS, STANDOUTS, age_on,
                                   load_league)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"


@pytest.fixture(scope="module")
def league():
    return load_league(ROOT / "data" / "season" / "league.json")


@pytest.fixture(scope="module")
def index():
    return json.loads(INDEX.read_text())


@pytest.fixture(scope="module")
def comps(index):
    return {e["competition_id"]: json.loads((ROOT / e["path"]).read_text()) for e in index["competitions"]
            if e["source"] == "catalogue"}


@pytest.fixture(scope="module")
def careers(index):
    return {c["global_id"]: c for c in index["careers"]}


def _people(comp):
    return [(c, p) for c in comp["clubs"] for p in c["squad"]]


# ---------------------------------------------------------------------------------------------------------- files

def test_the_committed_catalogue_is_what_the_definition_writes(league, index, comps):
    want_index, want = D.new_catalogue(league)
    assert INDEX.read_text() == D.dumps(want_index)
    assert set(want) == set(comps)
    for cid, comp in want.items():
        assert (ROOT / "data" / "catalogue" / "competitions" / f"{cid}.json").read_text() == D.dumps(comp), cid


def test_the_definition_runs_on_the_detmath_stream_and_is_repeatable(league):
    a, b = D.new_catalogue(league), D.new_catalogue(league)
    assert D.dumps(a[0]) == D.dumps(b[0]) and all(D.dumps(a[1][k]) == D.dumps(b[1][k]) for k in a[1])
    assert "from regista.detmath import Random" in Path(D.__file__).read_text()
    assert "import random" not in Path(D.__file__).read_text()


def test_fourteen_competitions_with_their_labels_and_no_professional_tier(index, comps):
    entries = index["competitions"]
    assert [e["competition_id"] for e in entries] == [c.competition_id for c in COMPETITIONS]
    assert len(entries) == 14 and len({e["country"] for e in entries}) == 10
    for e in entries:
        c = BY_ID[e["competition_id"]]
        assert {k: e[k] for k in ("name", "country", "region", "tier", "age_group", "gender")} == \
            {"name": c.name, "country": c.country, "region": c.region, "tier": c.tier, "age_group": c.age_group,
             "gender": c.gender}
        assert e["format"] == "11-a-side" and e["season"] == "2026/27"
        assert e["tier"] in dict(TIERS) and e["tier"] != "professional"
    eng = entries[0]
    assert eng["competition_id"] == ENGLAND_ID and eng["source"] == "league" and eng["path"] == "data/season/league.json"
    assert ENGLAND_ID not in comps and not (ROOT / "data" / "catalogue" / "competitions" / f"{ENGLAND_ID}.json").exists()
    for cid, comp in comps.items():
        assert comp["competition"]["competition_id"] == cid and comp["league"] == BY_ID[cid].name
        assert comp["generator"]["profile"] == "league" and comp["generator"]["minutes"] == 15.0
        assert comp["level"]["key"] == BY_ID[cid].level_key


def test_squads_of_eighteen_in_the_433_numbering(comps):
    for cid, comp in comps.items():
        assert 4 <= len(comp["clubs"]) <= 6 and len(comp["clubs"]) == BY_ID[cid].teams
        for club in comp["clubs"]:
            kits = [p["kit_number"] for p in club["squad"]]
            assert kits == [1, 2, 4, 5, 3, 8, 6, 10, 7, 9, 11, 13, 15, 14, 16, 17, 20, 22], club["club_id"]
            assert [p["starter"] for p in club["squad"]] == [True] * 11 + [False] * 7
            assert all(p["role"] == ROLE_OF_KIT[p["kit_number"]] for p in club["squad"])


def test_ids_names_and_short_names_are_unique_and_invented(league, comps):
    league_names = {p["name"] for c in league["clubs"] for p in c["squad"]}
    shorts = [c["short_name"] for comp in comps.values() for c in comp["clubs"]]
    assert len(shorts) == 60 and len(set(shorts)) == 60 and not set(shorts) & RESERVED_SHORT_NAMES
    assert all(re.fullmatch(r"[A-Z]{3,4}", s) for s in shorts)
    club_ids = [c["club_id"] for comp in comps.values() for c in comp["clubs"]]
    assert len(set(club_ids)) == 60 and all(re.fullmatch(r"cl_[a-z0-9_]+", c) for c in club_ids)
    assert not set(club_ids) & {c["club_id"] for c in league["clubs"]}
    people: dict[str, dict] = {}
    for comp in comps.values():
        for club, p in _people(comp):
            assert re.fullmatch(r"pl_[a-z]{3,4}_\d\d", p["global_id"])
            people.setdefault(p["global_id"], p)
    names = [p["name"] for p in people.values()]
    assert len(people) == 1075 and len(set(names)) == len(names)
    assert not set(names) & league_names
    assert not set(people) & {p["global_id"] for c in league["clubs"] for p in c["squad"]}


def test_every_seed_is_unique(league, comps):
    seeds = [f["seed"] for f in league["fixtures"]] + [f["seed"] for comp in comps.values() for f in comp["fixtures"]]
    streams = [comp["seed"] for comp in comps.values()] + [comp["attributes"]["seed"] for comp in comps.values()]
    assert len(set(seeds)) == len(seeds) == 90
    assert all(20270101 <= f["seed"] <= 20271399 for comp in comps.values() for f in comp["fixtures"])
    assert len(set(streams)) == len(streams)


def test_kits_are_distinct_within_each_competition(comps):
    for cid, comp in comps.items():
        prim = [c["kit"]["primary"] for c in comp["clubs"]]
        gks = [c["kit"]["gk"] for c in comp["clubs"]]
        assert min(D.colour_distance(a, b) for a, b in itertools.combinations(prim, 2)) >= D.PRIMARY_MIN, cid
        assert min(D.colour_distance(g, p) for g in gks for p in prim) >= D.GK_PRIMARY_MIN, cid
        assert min(D.colour_distance(a, b) for a, b in itertools.combinations(gks, 2)) >= D.GK_GK_MIN, cid


# ---------------------------------------------------------------------------------------------------------- levels

def test_ages_heights_ratings_and_physical_inside_each_levels_clamps(comps, careers):
    for cid, comp in comps.items():
        lv = LEVELS[comp["level"]["key"]]
        for club, p in _people(comp):
            home = careers.get(p["global_id"], {}).get("competitions", [cid])[0]
            plv = LEVELS[comps[home]["level"]["key"]]   # a career player keeps his first competition's scale
            age = age_on(p["date_of_birth"])
            assert plv.age_range[0] <= age <= plv.age_range[1], (cid, p["global_id"], age)
            assert D.height_range(plv)[0] <= p["height_cm"] <= D.height_range(plv)[1]
            a = p["attributes"]
            keys = RATINGS + (GK_RATINGS if p["role"] == "GK" else ())
            assert set(a) == set(keys) | {"top_speed_kmh", "acceleration_ms2"}
            assert all(1 <= a[k] <= D.standout_cap(plv) for k in keys)
            band = "GK" if p["role"] == "GK" else "outfield"
            lo, hi = D.speed_range(plv, band)
            assert lo - 0.05 <= a["top_speed_kmh"] <= hi + 0.05
            lo, hi = D.accel_range(plv, band)
            assert lo - 0.005 <= a["acceleration_ms2"] <= hi + 0.005
            if p["global_id"] not in careers:
                assert lv is plv


def _mean(comps, keys, what, outfield=True):
    vals = [what(p) for cid, comp in comps.items() if comp["level"]["key"] in keys for _c, p in _people(comp)
            if not outfield or p["role"] != "GK"]
    return fmean(vals)


def test_levels_genuinely_differ_in_the_designed_order(comps):
    speed = lambda p: p["attributes"]["top_speed_kmh"]  # noqa: E731
    skill = lambda p: fmean(p["attributes"][k] for k in RATINGS)  # noqa: E731
    by = lambda key, what: _mean(comps, {key}, what)  # noqa: E731
    # women below men of the same tier (top speed, sourced [S3]; skill, direction sourced [S1])
    assert by("semi_pro/senior/women", speed) < by("semi_pro/senior/men", speed) - 4
    assert by("college/college/women", speed) < by("college/college/men", speed) - 4
    assert by("college/college/women", skill) < by("college/college/men", skill)
    # youth: U17 < U18 < U19 < U20 < senior in top speed (direction sourced [S5, S6, S8])
    order = ["academy/U17/men", "academy/U18/men", "academy/U19/men", "academy/U20/men", "semi_pro/senior/men"]
    speeds = [by(k, speed) for k in order]
    assert speeds == sorted(speeds), speeds
    # amateur below semi-pro in skill; college between them
    assert by("amateur/senior/men", skill) < by("college/college/men", skill) < by("semi_pro/senior/men", skill)


def test_every_competition_has_standouts_and_no_star_outside_england(comps, careers):
    for cid, comp in comps.items():
        lv = LEVELS[comp["level"]["key"]]
        # standouts are lifted among the competition's own draws; a career player arrived from another competition
        arrived = {g for g, car in careers.items() if car["competitions"][1] == cid}
        starters = [p for _c, p in _people(comp) if p["starter"] and p["global_id"] not in arrived]
        for role, key in STANDOUTS:
            group = sorted((p["attributes"][key] for p in starters if p["role"] == role), reverse=True)
            assert group[0] >= min(D.standout_cap(lv), group[1] + 10) or group[0] == D.standout_cap(lv), (cid, role, key)
        assert all(p["attributes"]["finishing"] < STAR_RATINGS["finishing"] for _c, p in _people(comp))
    assert STAR not in {p["global_id"] for comp in comps.values() for _c, p in _people(comp)}


def test_scales_and_ratings_stay_hidden_in_the_index(index):
    text = json.dumps(index)
    for key in (*ATTRIBUTE_KEYS, "skill_offset", "speed_mult", "accel_mult", "stamina_offset", "style_offset"):
        assert f'"{key}"' not in text, key


# ---------------------------------------------------------------------------------------------------------- careers

def test_five_careers_one_person_two_competitions(comps, careers):
    assert len(careers) == 5
    for gid, car in careers.items():
        src, dst = car["competitions"]
        assert (src, dst) in {(s, d) for s, d, *_ in D.CAREERS}
        entries = {}
        for cid in (src, dst):
            hits = [(c, p) for c, p in _people(comps[cid]) if p["global_id"] == gid]
            assert len(hits) == 1, (gid, cid)
            entries[cid] = hits[0]
        (c1, p1), (c2, p2) = entries[src], entries[dst]
        assert [c1["club_id"], c2["club_id"]] == car["clubs"] and p1["name"] == car["name"]
        assert {k: v for k, v in p1.items() if k != "kit_number"} == {k: v for k, v in p2.items() if k != "kit_number"}
        assert p1["starter"] and p2["starter"] and p1["role"] == p2["role"]
        assert BY_ID[src].gender == BY_ID[dst].gender
        if BY_ID[src].age_group == "U19":
            assert 17 <= age_on(p1["date_of_birth"]) <= 18
    nats = {careers[g]["competitions"][1]: next(p for _c, p in _people(comps[careers[g]["competitions"][1]])
                                                 if p["global_id"] == g)["nationality"] for g in careers}
    assert nats["co_eng_sp_women"] == "England" and nats["co_ger_sp_men"] == "Germany" and nats["co_mex_am_men"] == "Mexico"


def test_a_career_player_has_matches_in_both_competitions_never_two_on_one_date(comps, careers):
    for gid, car in careers.items():
        dates = []
        for cid, club in zip(car["competitions"], car["clubs"]):
            played = [f for f in comps[cid]["fixtures"] if club in (f["home"], f["away"])]
            assert played, (gid, cid)
            dates += [f["date"] for f in played]
        assert len(dates) == len(set(dates)), (gid, dates)


def test_each_career_story_fits_its_fixtures_and_registration(comps, careers):
    """Review B M2 and S5: a story never contradicts the player's own fixtures, and a Spanish juvenil plays for a senior
    side in his own territorial federation (one licence a season: his club's affiliated senior side)."""
    for gid, car in careers.items():
        (src, dst), (src_club, dst_club) = car["competitions"], car["clubs"]
        story = car["story"]
        dst_fx = sorted((f for f in comps[dst]["fixtures"] if dst_club in (f["home"], f["away"])), key=lambda f: f["date"])
        src_end = BY_ID[src].window[1]
        if "outside the college season" in story:
            assert all(f["date"] > src_end or f["date"] < BY_ID[src].window[0] for f in dst_fx), (gid, story)
        if "after the college season" in story:   # Olivia King: her home club's opening match, then after the season
            assert dst_fx[0]["round"] == 1 and all(f["date"] > src_end for f in dst_fx[1:]), (gid, story)
        if BY_ID[src].country == "Spain":
            assert BY_ID[src].region == BY_ID[dst].region and BY_ID[src].region in story
            assert "affiliated" in story and "territorial federation" in story


def test_youth_birth_dates_meet_each_competitions_cut_off(comps, index):
    """Review B S6: every youth squad is born inside its competition's rule (taxonomy.BIRTH_CUTOFFS), which is a public
    label (eligibility); moving a date of birth never touched a rating or a match (dates of birth do not reach the
    generator)."""
    from regista.catalogue.taxonomy import BIRTH_CUTOFFS
    from regista.season.league import LEAGUE_FIELDS

    assert "date_of_birth" not in LEAGUE_FIELDS
    youth = {c.competition_id for c in COMPETITIONS if c.tier == "academy"}
    assert set(BIRTH_CUTOFFS) == youth
    for cid in youth:
        earliest, rule = BIRTH_CUTOFFS[cid]
        assert all(p["date_of_birth"] >= earliest for _c, p in _people(comps[cid])), cid
        assert comps[cid]["competition"]["eligibility"] == rule
        assert next(e for e in index["competitions"] if e["competition_id"] == cid)["eligibility"] == rule
    assert D.within_cutoff("2007-11-03", "co_esp_u19") == "2008-11-03"
    assert D.within_cutoff("2009-08-20", "co_gha_u17") == "2010-08-20"
    assert D.within_cutoff("2007-11-03", "co_ger_sp_men") == "2007-11-03"


# ---------------------------------------------------------------------------------------------------------- coverage

def test_sparse_uploads_cover_every_club_with_uploader_and_camera(comps):
    assert sum(len(c["fixtures"]) for c in comps.values()) == 60
    for cid, comp in comps.items():
        fx = comp["fixtures"]
        assert 3 <= len(fx) <= 8 and len(fx) == BY_ID[cid].uploads
        assert {f["home"] for f in fx} | {f["away"] for f in fx} == {c["club_id"] for c in comp["clubs"]}
        squads = {c["club_id"]: c["squad"] for c in comp["clubs"]}
        for f in fx:
            assert re.fullmatch(rf"cm_{comp['competition']['code']}_\d\d_[a-z]{{3,4}}_[a-z]{{3,4}}", f["match_id"])
            assert f["camera"] in CAMERAS
            up = f["uploader"]
            assert up["club_id"] in (f["home"], f["away"])
            if up["type"] == "player":
                assert any(p["global_id"] == up["global_id"] and p["starter"] for p in squads[up["club_id"]])
            else:
                assert up["type"] == "team" and set(up) == {"type", "club_id"}
            assert "2026-08-01" <= f["date"] <= "2027-05-31"
        assert len({f["match_id"] for f in fx}) == len(fx)
        # a club plays at most once on a date
        busy = Counter((d, c) for f in fx for d, c in ((f["date"], f["home"]), (f["date"], f["away"])))
        assert max(busy.values()) == 1


def test_the_england_overlay_labels_all_thirty_league_fixtures(league, index):
    eng = index["competitions"][0]
    assert set(eng["uploads"]) == {f["match_id"] for f in league["fixtures"]}
    squads = {c["club_id"]: c["squad"] for c in league["clubs"]}
    for f in league["fixtures"]:
        u = eng["uploads"][f["match_id"]]
        assert u["camera"] in CAMERAS and u["uploader"]["club_id"] in (f["home"], f["away"])
        if u["uploader"]["type"] == "player":
            assert any(p["global_id"] == u["uploader"]["global_id"] and p["starter"] for p in squads[u["uploader"]["club_id"]])
    assert store.england_upload("rl_r01_ash_fai", INDEX) == eng["uploads"]["rl_r01_ash_fai"]


def test_the_store_reads_every_competition_and_resolves_matches(league, comps):
    assert store.competition(ENGLAND_ID, INDEX)["fixtures"] == league["fixtures"]
    assert [c["competition"]["competition_id"] for c in store.new_competitions(INDEX)] == list(comps)
    fx = comps["co_ger_sp_men"]["fixtures"][0]
    comp, got = store.resolve_match(fx["match_id"], INDEX)
    assert got == fx and comp["league"] == "Weserland-Liga"
    assert store.resolve_match("cm_nope_01_aaa_bbb", INDEX) is None and store.resolve_match("rl_r01_ash_fai", INDEX) is None
