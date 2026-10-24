"""League players' bio and hidden ratings (``regista.season.league.assign_attributes``).

Every player has every field, inside its range; the ratings are shaped by role and really differ within a role; Femi
Toure is the best finisher among forwards; the league regenerates exactly; and the ratings never reach a public API.
"""

from __future__ import annotations

import hashlib
import json
import statistics as st
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.season.league import (ACCEL_RANGE, AGE_ON, AGE_RANGE, ATTRIBUTE_KEYS, BIO_KEYS, GK_RATINGS, HEIGHT_RANGE,
                                   PHYSICAL, RATINGS, ROLE_OF_KIT, SPEED_RANGE, STANDOUT_CAP, STANDOUT_LIFT, STANDOUTS, STAR,
                                   age_on, bio, new_league, people, player_attributes, save_league)
from regista.season.profiles import Season

ROOT = Path(__file__).resolve().parents[1]
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes"}


@pytest.fixture(scope="module")
def league():
    return new_league(2026)


@pytest.fixture(scope="module")
def everyone(league):
    return [p for c in league["clubs"] for p in c["squad"]]


def _role(everyone, role, starters_only=False):
    return [p for p in everyone if p["role"] == role and (p["starter"] or not starters_only)]


def _mean(players, key):
    return st.mean(p["attributes"][key] for p in players)


# ---------------------------------------------------------------------------- fields and ranges

def test_every_player_has_every_field(everyone):
    assert len(everyone) == 108
    for p in everyone:
        assert p["role"] == ROLE_OF_KIT[p["kit_number"]]
        assert all(p.get(k) is not None for k in BIO_KEYS), p["global_id"]
        want = set(RATINGS) | set(PHYSICAL) | (set(GK_RATINGS) if p["role"] == "GK" else set())
        assert set(p["attributes"]) == want, p["global_id"]


def test_ranges(everyone):
    for p in everyone:
        a = p["attributes"]
        assert all(isinstance(a[k], int) and 1 <= a[k] <= 99 for k in (*RATINGS, *GK_RATINGS) if k in a), p["global_id"]
        band = "GK" if p["role"] == "GK" else "outfield"
        assert SPEED_RANGE[band][0] <= a["top_speed_kmh"] <= SPEED_RANGE[band][1]
        assert ACCEL_RANGE[band][0] <= a["acceleration_ms2"] <= ACCEL_RANGE[band][1]
        assert HEIGHT_RANGE[0] <= p["height_cm"] <= HEIGHT_RANGE[1]
        assert AGE_RANGE[0] <= age_on(p["date_of_birth"]) <= AGE_RANGE[1]
        assert p["preferred_foot"] in ("right", "left", "both") and p["nationality"]
    feet = Counter(p["preferred_foot"] for p in everyone)
    assert 0.65 <= feet["right"] / 108 <= 0.85 and 0.12 <= feet["left"] / 108 <= 0.28 and 1 <= feet["both"] <= 10
    nations = Counter(p["nationality"] for p in everyone)
    assert len(nations) >= 15 and max(nations.values()) / 108 <= 0.4


def test_age_is_whole_years_at_season_start():
    assert AGE_ON.isoformat() == "2026-08-01"
    assert age_on("2000-08-01") == 26 and age_on("2000-08-02") == 25
    assert bio({"global_id": "x"})["age"] is None  # a league file from before attributes: no bio, no crash


# ---------------------------------------------------------------------------- shaped by role, different within a role

def test_ratings_are_shaped_by_role(everyone):
    roles = {r: _role(everyone, r) for r in set(ROLE_OF_KIT.values())}
    outfield = [r for r in roles if r != "GK"]

    def top(key):
        return max(outfield, key=lambda r: _mean(roles[r], key))

    assert top("aerial") == "CB" and top("defending") in ("CB", "DM") and top("dribbling") == "W"
    assert top("finishing") == "ST" and top("vision") == "AM" and top("top_speed_kmh") == "W"
    assert _mean(roles["DM"], "defending") > max(_mean(roles[r], "defending") for r in ("CM", "AM", "W", "ST"))
    assert _mean(roles["DM"], "passing") >= 70
    height = {r: st.mean(p["height_cm"] for p in ps) for r, ps in roles.items()}
    assert height["GK"] > height["W"] and height["CB"] > max(height[r] for r in ("FB", "AM", "W"))
    gk = roles["GK"]
    assert _mean(gk, "shot_stopping") > 65 and _mean(gk, "finishing") < 25


def test_players_in_one_role_really_differ(everyone):
    signature = {"CB": "defending", "FB": "stamina", "DM": "defending", "CM": "passing", "AM": "vision", "W": "dribbling",
                 "ST": "finishing", "GK": "shot_stopping"}
    for role, key in signature.items():
        values = [p["attributes"][key] for p in _role(everyone, role)]
        assert max(values) - min(values) >= 12 and st.pstdev(values) >= 3, (role, key, values)


def test_standouts_stand_out(everyone):
    for role, key in STANDOUTS:
        values = sorted((p["attributes"][key] for p in _role(everyone, role, starters_only=True)), reverse=True)
        assert values[0] - values[1] >= STANDOUT_LIFT or values[0] == STANDOUT_CAP, (role, key, values[:3])


def test_femi_toure_is_the_best_finisher_among_forwards(everyone):
    star = next(p for p in everyone if p["global_id"] == STAR)
    assert star["name"] == "Femi Toure" and star["role"] == "ST"
    others = [p["attributes"]["finishing"] for p in everyone if p["position"] == "FW" and p is not star]
    assert star["attributes"]["finishing"] >= max(others) + 5
    assert star["attributes"]["finishing"] == max(p["attributes"]["finishing"] for p in everyone)


# ---------------------------------------------------------------------------- determinism

def test_regenerates_exactly_and_leaves_names_and_fixtures_alone(league):
    assert new_league(2026) == league
    assert json.loads((ROOT / "data" / "season" / "league.json").read_text()) == json.loads(json.dumps(league))
    assert new_league(2027)["clubs"][0]["squad"][0]["attributes"] != league["clubs"][0]["squad"][0]["attributes"]
    # Squads (ids, names, numbers, positions) and fixtures (seeds included) hash as on main (e3da71d) before attributes.
    # The generator settings changed on purpose with league mode (profile "league", generator 0.2.0), with motion at
    # 10 Hz and physical records (generator 0.3.0), with the retune against individual leader bands (0.4.0) and with shot
    # outcomes, keepers' launches and take-ons at the Premier League's rates (0.5.0).
    core = {"squads": [[{k: p[k] for k in ("global_id", "name", "kit_number", "position", "starter")} for p in c["squad"]]
                       for c in league["clubs"]], "fixtures": league["fixtures"]}
    assert hashlib.sha256(json.dumps(core, sort_keys=True).encode()).hexdigest() == \
        "6ef762c94d856aa980e2021d96c3c57de165c8ea05e665d22f82ab2692007de7"
    assert league["generator"] == {"name": "regista-synth", "version": "0.6.0", "profile": "league", "minutes": 15.0,
                                   "periods": 2, "track_hz": 1.0}


def test_player_attributes_is_the_generators_view(league):
    attrs = player_attributes(league)
    assert len(attrs) == 108 and attrs[STAR]["finishing"] >= 90


# ---------------------------------------------------------------------------- never public

def _hidden_keys(obj, path="$"):
    """Every place in a JSON value where a hidden rating's key appears."""
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


def test_people_carries_the_bio_but_not_the_ratings(league):
    who = people(league)
    assert not any(_hidden_keys(p) for p in who.values())
    assert who[STAR]["height_cm"] and who[STAR]["nationality"]


@pytest.fixture(scope="module")
def built(league, tmp_path_factory):
    small = {**league, "fixtures": league["fixtures"][:3]}  # round 1: every club plays once
    root = tmp_path_factory.mktemp("season_attrs")
    return small, root, Season.build(small, root)


@pytest.fixture
def client(built, monkeypatch, tmp_path):
    from regista import api

    small, root, _ = built
    monkeypatch.setattr(api, "SEASON_LEAGUE", save_league(small, tmp_path / "league.json"))
    monkeypatch.setattr(api, "SEASON_ROOT", root)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    return TestClient(api.app)


def test_ratings_never_appear_in_public_json(client, built):
    _small, _root, season = built
    season_json = client.get("/api/season").json()
    squad = season_json["clubs"][1]["squad"]
    star = next(p for p in squad if p["global_id"] == STAR)
    assert {"age", "height_cm", "preferred_foot", "nationality", "date_of_birth"} <= set(star)
    cards = client.get("/api/players", params={"limit": 200}).json()
    assert all({"age", "height_cm", "preferred_foot", "nationality"} <= set(c) for c in cards["players"])
    prof = client.get(f"/api/players/{STAR}").json()
    assert prof["age"] == age_on(prof["date_of_birth"]) and prof["card"]["height_cm"] == prof["height_cm"]
    payloads = {"season": season_json, "players": cards, "profile": prof,
                "moments": client.get(f"/api/players/{STAR}/moments").json(),
                "compare": client.get("/api/compare", params={"ids": f"{STAR},pl_ash_09"}).json(),
                "scout_rules": client.post("/api/scout/ask", json={"q": "the best finisher", "engine": "rules"}).json()}
    from regista.season.scout import compare_players, get_profile, search_players  # the MCP player tools' bodies

    payloads |= {"mcp_search": search_players(season, position="FW", sort="goals"), "mcp_profile": get_profile(season, STAR),
                 "mcp_compare": compare_players(season, [STAR, "pl_ash_09"])}
    assert payloads["mcp_profile"]["bio"]["height_cm"] == prof["height_cm"]
    for name, body in payloads.items():
        assert not _hidden_keys(body), (name, _hidden_keys(body)[:5])
