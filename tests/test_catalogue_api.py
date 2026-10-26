"""The catalogue's API (docs/catalogue/build/design.md §8 and §11, items 9 and 10; docs/catalogue/build/api.md): the new
endpoints, the optional catalogue parameters on existing ones, the three catalogue MCP tools, input validation, and a
walk of every new payload for a hidden rating, a level scale or a match seed.

Every test reads the committed catalogue and the Regista League as the app builds them (``data/season/matches`` and
``data/catalogue/matches``, git-ignored, built once). Nothing here writes anywhere else or reaches Azure. Existing
responses without the new parameters are pinned by ``tests/test_catalogue_backcompat.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api
from regista.catalogue.metrics import build_catalogue_metrics
from regista.catalogue.taxonomy import ENGLAND_ID
from regista.season.league import ATTRIBUTE_KEYS
from regista.season.metrics import fbref_percentile, load_metrics, rank_value

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes", "skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift",
                                "execution", "style_offset", "level_scale", "seed", "age_range"}
STAR = "pl_bro_09"
CRUZ = "pl_sot_09"          # career: Spain U19 striker, then Spain amateur men
GER = "co_ger_sp_men"
MAR = "co_mar_u19"


@pytest.fixture(scope="module")
def client():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api, "SEASON_LEAGUE", LEAGUE)
        mp.setattr(api, "SEASON_ROOT", SEASON_ROOT)
        mp.setattr(api, "CATALOGUE", INDEX)
        mp.setattr(api, "CATALOGUE_ROOT", MATCHES)
        mp.setenv("REGISTA_SEASON", str(LEAGUE))
        mp.setenv("REGISTA_SEASON_ROOT", str(SEASON_ROOT))
        mp.setenv("REGISTA_CATALOGUE", str(INDEX))
        mp.setenv("REGISTA_CATALOGUE_ROOT", str(MATCHES))
        yield TestClient(api.app)


@pytest.fixture(scope="module")
def cm(client):
    return build_catalogue_metrics(INDEX, MATCHES, LEAGUE, SEASON_ROOT, england=load_metrics(LEAGUE, SEASON_ROOT))


def ok(client, path, **params):
    r = client.get(path, params=params)
    assert r.status_code == 200, (path, params, r.text[:300])
    return r.json()


def _hidden(obj, path="$"):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in HIDDEN:
                found.append(f"{path}.{k}")
            found += _hidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _hidden(v, f"{path}[{i}]")
    return found


def _cells(payload):
    for row in payload["players"]:
        yield from row["values"].values()


# ---------------------------------------------------------------------------- the catalogue and its competitions

def test_the_catalogue_lists_14_competitions_with_totals_levels_and_careers(client):
    d = ok(client, "/api/catalogue")
    assert [c["competition_id"] for c in d["competitions"]][0] == ENGLAND_ID and len(d["competitions"]) == 14
    assert d["totals"] == {"competitions": 14, "countries": 10, "clubs": 66, "players": 1183, "matches": 90}
    eng = d["competitions"][0]
    assert eng["uploaded_matches"] == 30 and eng["coverage"] == "full" and sum(eng["cameras"].values()) == 30
    assert sum(c["uploaded_matches"] for c in d["competitions"][1:]) == 60
    assert all(set(c["cameras"]) <= {"tripod", "phone", "drone", "broadcast"} for c in d["competitions"])
    assert len(d["careers"]) == 5 and all(len(c["competitions"]) == 2 and c["api_url"] for c in d["careers"])
    pools = {(p["tier"], p["age_group"], p["gender"]): p["competitions"] for p in d["levels"]["pools"]}
    assert pools[("semi_pro", "senior", "men")] == [ENGLAND_ID, GER]
    assert "label" in d["camera_note"].lower() and d["synthetic"] is True and "warm" in d
    # review B round 3 S-A: the catalogue is dated, and holds only matches played by then
    assert d["as_of"] == "2026-10-24" and d["as_of_note"]
    assert all(c["dates"][1] <= d["as_of"] for c in d["competitions"])
    listed = ok(client, "/api/catalogue/matches", limit=200)
    assert listed["total"] == 90 and max(m["date"] for m in listed["matches"]) <= d["as_of"]


@pytest.mark.parametrize("params, want", [
    ({"country": "Spain"}, ["co_esp_am_men", "co_esp_u19"]),
    ({"country": "spain"}, ["co_esp_am_men", "co_esp_u19"]),
    ({"level": "academy"}, ["co_eng_u18", "co_esp_u19", "co_bra_u20", "co_gha_u17", MAR]),
    ({"tier": "college", "gender": "women"}, ["co_usa_col_women"]),
    ({"age_group": "U19"}, ["co_esp_u19", MAR]),
    ({"gender": "women"}, ["co_eng_sp_women", "co_usa_col_women"]),
    ({"country": "Atlantis"}, []),
])
def test_competitions_filter_by_country_level_age_group_and_gender(client, params, want):
    d = ok(client, "/api/competitions", **params)
    assert [c["competition_id"] for c in d["competitions"]] == want and d["total"] == len(want)


def test_the_england_competition_carries_the_league_table_and_all_30_uploads(client):
    d = ok(client, f"/api/competitions/{ENGLAND_ID}")
    season = ok(client, "/api/season")
    assert d["table"] == season["table"] and d["results_note"] is None and d["coverage"] == "full"
    assert len(d["matches"]) == 30 and all(m["camera"] and m["uploader"]["type"] in ("team", "player") for m in d["matches"])
    assert d["level_pool"]["competitions"] == [ENGLAND_ID, GER]


def test_a_sparse_competition_has_results_of_uploads_only_never_a_table(client, cm):
    d = ok(client, f"/api/competitions/{GER}")
    assert d["table"] is None and d["results_note"] == "uploaded matches only, not a league table"
    assert len(d["matches"]) == 8 and d["sample"]["matches_uploaded"] == 8 and d["sample"]["qualifying_minutes"] == 45.0
    for m in d["matches"]:
        assert m["match_id"].startswith("cm_gsp_") and m["clip_view"] == f"/?match={m['match_id']}"
        assert m["camera"] in ("tripod", "phone", "drone", "broadcast") and m["home_name"] and m["away_name"]
        up = m["uploader"]
        assert up["club_id"] in (m["home"], m["away"]) and up["club"]
        assert up["type"] == "team" or (up["type"] == "player" and up["name"])
    assert sum(r["played"] for r in d["results"]) == 16
    squads = [p for c in d["clubs"] for p in c["squad"]]
    assert len(d["clubs"]) == 6 and len(squads) == 108 and all("age" in p and "nationality" in p for p in squads)
    careers = [p for p in squads if p["career"]]
    assert careers and all(p["global_id"] in cm.careers for p in careers)
    assert all(GER not in p["career"] for p in careers)


def test_competition_ids_are_validated(client):
    assert client.get("/api/competitions/co_nowhere").status_code == 404
    assert client.get("/api/competitions/nope").status_code == 400
    assert client.get("/api/competitions/co_nowhere/players").status_code == 404
    assert client.get("/api/competitions", params={"tier": "professional"}).status_code == 422
    r = client.get("/api/competitions", params={"tier": "academy", "level": "college"})
    assert r.status_code == 422 and "same filter" in r.json()["detail"]
    assert client.get("/api/competitions", params={"gender": "mixed"}).status_code == 422
    assert client.get("/api/competitions", params={"age_group": "U21"}).status_code == 422
    assert client.get("/api/competitions", params={"country": "x" * 41}).status_code == 422


# ---------------------------------------------------------------------------- players across the catalogue

def test_the_cross_country_screen_pages_through_every_row_with_pools(client, cm):
    first = ok(client, "/api/catalogue/players", limit=200)
    total = first["total"]
    assert total == len(cm.select()) and first["scope"] == "level" and first["warning"]   # mixed levels
    rows = first["players"]
    while len(rows) < total:
        rows += ok(client, "/api/catalogue/players", limit=200, offset=len(rows))["players"]
    keys = [(r["competition_id"], r["global_id"]) for r in rows]
    assert len(set(keys)) == total
    assert {r["competition_id"] for r in rows} == set(cm.order)
    for cell in _cells(first):
        assert cell["pool"]["scope"] == "level" and cell["sample"]["competition_id"]
        assert cell["pool"]["size"] == cell["peers"] and "evidence_total" in cell
    assert all(r["api_url"] == f"/api/catalogue/players/{r['global_id']}" for r in rows)
    assert all(r["profile_url"] is None for r in rows if r["competition_id"] != ENGLAND_ID)


def test_screen_filters_sort_and_order(client):
    # academy spans four levels: sorted by each row's percentile within its own pool, best first
    acad = ok(client, "/api/catalogue/players", tier="academy", position="FW", sort="npxg", limit=200)
    assert acad["players"] and all(r["tier"] == "academy" and r["position"] == "FW" for r in acad["players"])
    assert acad["rank_by"] == "pool" and acad["boards"] is None and acad["rank_rule"]
    pcts = [r["values"]["npxg"]["percentile"] for r in acad["players"] if r["values"]["npxg"]["percentile"] is not None]
    assert pcts and pcts == sorted(pcts, reverse=True)
    # rank_by=value keeps the raw ranking as an explicit option, within each level (raw numbers never cross levels)
    raw = ok(client, "/api/catalogue/players", tier="academy", position="FW", sort="npxg", rank_by="value", limit=200)
    asc = ok(client, "/api/catalogue/players", tier="academy", position="FW", sort="npxg", order="asc", rank_by="value",
             limit=200)
    assert raw["rank_by"] == asc["rank_by"] == "value" and [b["by"] for b in raw["boards"]] == ["level"] * 4
    for b in raw["boards"]:
        vals = [r["values"]["npxg"]["value"] for r in raw["players"] if r["board"] == b["board"]
                and r["values"]["npxg"]["value"] is not None]
        assert vals == sorted(vals, reverse=True) and all(r["board"] == b["board"]
                                                          for r in raw["players"][b["offset"]:b["offset"] + b["size"]])
        up = [r["values"]["npxg"]["value"] for r in asc["players"] if r["board"] == b["board"]
              and r["values"]["npxg"]["value"] is not None]
        assert up == sorted(vals)
    one = ok(client, f"/api/competitions/{GER}/players", position="FW", sort="npxg", limit=200)   # one level: by value
    assert one["rank_by"] == "value"
    women = ok(client, "/api/catalogue/players", gender="women", limit=200)
    assert {r["competition_id"] for r in women["players"]} == {"co_eng_sp_women", "co_usa_col_women"}
    careers = ok(client, "/api/catalogue/players", career="true", min_minutes=0, limit=200)
    assert careers["players"] and all(r["career"] for r in careers["players"])
    assert {r["global_id"] for r in careers["players"]} <= set(ok(client, "/api/catalogue")["careers"][i]["global_id"]
                                                                for i in range(5))
    drone = ok(client, "/api/catalogue/players", camera="drone", limit=5)
    assert drone["camera_note"] and drone["total"] > 0
    mx = ok(client, "/api/catalogue/players", country="Mexico", limit=200)
    assert all(r["country"] == "Mexico" for r in mx["players"])
    allm = ok(client, "/api/catalogue/players", scope="all", gender="men", limit=5)
    assert allm["warning"] and all(c["pool"]["scope"] == "all" and c["pool"]["tier"] is None for c in _cells(allm))


def test_a_competitions_players_default_to_the_level_pool(client):
    d = ok(client, f"/api/competitions/{GER}/players", position="FW", limit=200)
    assert d["scope"] == "level" and all(r["competition_id"] == GER for r in d["players"])
    for cell in _cells(d):
        assert cell["pool"]["competitions"] == [ENGLAND_ID, GER]
    comp = ok(client, f"/api/competitions/{GER}/players", position="FW", scope="competition", limit=200)
    assert all(c["pool"]["competitions"] == [GER] for c in _cells(comp))


def test_small_and_too_small_pools_say_so(client):
    d = ok(client, f"/api/competitions/{MAR}/players", scope="competition", min_minutes=0, limit=200)
    cells = list(_cells(d))
    under = [c for c in cells if c["pool"]["size"] < 5]
    assert under and all(c["percentile"] is None and c["pool"]["reason"] for c in under)    # three uploads: tiny pools
    assert all(c["pool"]["small"] for c in cells) and all(c["pool"]["reason"] is None for c in cells if c not in under)
    level = ok(client, f"/api/competitions/{MAR}/players", position="DF", limit=200)
    assert any(c["percentile"] is not None for c in _cells(level))      # pooled with Spain U19
    assert all(c["pool"]["small"] == (c["pool"]["size"] < 15) for c in _cells(level))


def test_one_player_across_the_catalogue_keeps_a_row_per_competition(client, cm):
    d = ok(client, f"/api/catalogue/players/{CRUZ}")
    assert [r["competition_id"] for r in d["rows"]] == ["co_esp_u19", "co_esp_am_men"]
    assert [c["competition_id"] for c in d["career"]] == ["co_esp_u19", "co_esp_am_men"]
    assert d["overall"]["minutes"] == pytest.approx(sum(c["minutes"] for c in d["career"]), abs=0.11)
    assert "per90" not in d["overall"] and d["overall"]["note"]
    for row in d["rows"]:
        assert row["touch_map"] and len(row["touch_map"]) == 8 and row["summary"]["text"]
        lvl = {c["pool"]["tier"] for c in row["metrics"].values()}
        assert lvl == {row["tier"]}
    assert d["moments"] and all(m["competition_id"] in ("co_esp_u19", "co_esp_am_men") for m in d["moments"])
    assert d["profile_url"] is None and ok(client, f"/api/catalogue/players/{STAR}")["profile_url"] == f"/players/{STAR}"
    ev = ok(client, f"/api/catalogue/players/{CRUZ}", evidence="shots", competition="co_esp_am_men", evidence_limit=2)
    assert ev["competition_id"] == "co_esp_am_men" and ev["evidence"]["total"] >= len(ev["evidence"]["items"])
    assert all(i["match_id"].startswith("cm_eam_") for i in ev["evidence"]["items"])
    assert client.get(f"/api/catalogue/players/{CRUZ}", params={"evidence_offset": 3}).status_code == 422
    assert client.get(f"/api/catalogue/players/{CRUZ}", params={"evidence": "shots", "competition": GER}).status_code == 404
    assert client.get("/api/catalogue/players/pl_nobody_99").status_code == 404
    assert client.get("/api/catalogue/players/Robert").status_code == 400


def test_career_endpoint_and_include_career(client):
    car = ok(client, f"/api/players/{CRUZ}/career")
    assert [c["competition_id"] for c in car["career"]] == ["co_esp_u19", "co_esp_am_men"] and car["story"]
    star = ok(client, f"/api/players/{STAR}/career")
    assert [c["competition_id"] for c in star["career"]] == [ENGLAND_ID] and star["story"] is None
    plain = ok(client, f"/api/players/{STAR}")
    withc = ok(client, f"/api/players/{STAR}", include="career")
    assert {k: v for k, v in withc.items() if k != "career"} == plain and "career" not in plain
    assert withc["career"]["career"] == star["career"]
    assert client.get(f"/api/players/{STAR}", params={"include": "ratings"}).status_code == 422
    assert client.get("/api/players/pl_nobody_99/career").status_code == 404


def test_rank_compare_matches_and_pools(client):
    r = ok(client, "/api/catalogue/rank", metric="npxg", gender="men", limit=30)
    ranks = [p["rank"] for p in r["players"]]
    assert ranks == sorted(ranks) and r["warning"] and all(p["pool"]["gender"] == "men" for p in r["players"])
    page2 = ok(client, "/api/catalogue/rank", metric="npxg", gender="men", limit=10, offset=10)
    assert [p["global_id"] for p in page2["players"]] == [p["global_id"] for p in r["players"][10:20]]
    one = ok(client, "/api/catalogue/rank", metric="npxg", competition=ENGLAND_ID, position="FW")
    assert one["players"][0]["global_id"] == STAR and one["warning"] is None

    same = ok(client, "/api/catalogue/compare", ids=f"{STAR},pl_ash_09")
    assert same["same_pool"] is True and same["warning"] is None and len(same["players"]) == 2
    diff = ok(client, "/api/catalogue/compare", ids=f"{STAR},{CRUZ}")
    assert diff["same_pool"] is False and diff["warning"]
    picked = ok(client, "/api/catalogue/compare", ids=f"{STAR},{CRUZ}", competitions=f"{ENGLAND_ID},co_esp_u19")
    assert [p["competition_id"] for p in picked["players"]] == [ENGLAND_ID, "co_esp_u19"]
    assert client.get("/api/catalogue/compare", params={"ids": f"{STAR},{CRUZ}", "competitions": ENGLAND_ID}).status_code == 422
    assert client.get("/api/catalogue/compare", params={"ids": f"{STAR},{STAR}"}).status_code == 422

    m = ok(client, "/api/catalogue/matches", limit=200)
    assert m["total"] == 90 and len(m["matches"]) == 90
    drones = ok(client, "/api/catalogue/matches", camera="drone", limit=200)["matches"]
    assert drones and all(x["camera"] == "drone" for x in drones)
    players = ok(client, "/api/catalogue/matches", uploader_type="player", tier="amateur")["matches"]
    assert players and all(x["uploader"]["type"] == "player" and x["uploader"]["name"] and x["tier"] == "amateur" for x in players)
    hb = ok(client, "/api/catalogue/matches", club="cl_hollenburg")["matches"]
    assert hb and all("cl_hollenburg" in (x["home"], x["away"]) for x in hb)
    assert ok(client, "/api/catalogue/matches", limit=5, offset=88)["matches"] == m["matches"][88:]

    pools = ok(client, "/api/catalogue/pools")
    assert len(pools["pools"]) == 9 and pools["min_pool"] == 5 and pools["small_pool"] == 15
    assert ok(client, "/api/catalogue/pools", scope="all")["warning"]


# ---------------------------------------------------------------------------- existing endpoints with catalogue parameters

def test_england_in_competition_scope_is_todays_screen_and_cards(client):
    """The optional parameters reach the same numbers the existing endpoints serve when the pool is England's own."""
    today = ok(client, "/api/terminal/screen", limit=200)
    cat = ok(client, "/api/terminal/screen", competition=ENGLAND_ID, scope="competition", limit=200)
    assert set(cat) == set(today) | {"rank_by", "rank_rule", "boards"} and cat["total"] == today["total"]
    assert cat["rank_by"] == "value" and cat["boards"] is None      # one level, one gender: today's order
    want = {r["global_id"]: r["values"] for r in today["players"]}
    for row in cat["players"]:
        for k, cell in row["values"].items():
            assert {f: cell[f] for f in want[row["global_id"]][k]} == want[row["global_id"]][k]
    cards = ok(client, "/api/players", limit=200)
    ccards = ok(client, "/api/players", competition=ENGLAND_ID, scope="competition", limit=200)
    pct = {c["global_id"]: {k: h["percentile"] for k, h in c["headline"].items()} for c in cards["players"]}
    assert {c["global_id"]: {k: h["percentile"] for k, h in c["headline"].items()} for c in ccards["players"]} == pct


def test_englands_catalogue_cards_count_a_confirmed_upload_as_todays_cards_do(client, monkeypatch, tmp_path):
    """Review A #1: England's catalogue-mode cards come from the app's own season, so a finished Player-view upload counts
    there exactly as on today's cards; the terminal metrics and the career rows stay on the league's fixtures (as the
    Scout terminal does), say so (``basis``) and name the matches only the profile counts."""
    import shutil

    from regista import player_api
    from regista.schema import iter_jsonl
    from regista.season import profiles
    from regista.season.league import load_league

    league = load_league(LEAGUE)
    base_card = next(c for c in ok(client, "/api/players", limit=200)["players"] if c["global_id"] == STAR)
    fx = next(f for f in league["fixtures"] if "cl_brookfield" in (f["home"], f["away"]))
    d = shutil.copytree(SEASON_ROOT / fx["match_id"], tmp_path / "pv_fake")
    header = next(iter_jsonl(d / "events.jsonl"))
    pid = next(p["player_id"] for p in header["players"] if p.get("global_player_id") == STAR)
    row = {"match_id": d.name, "match_dir": str(d), "player_id": pid, "global_id": STAR, "upload_id": "up_fake"}
    monkeypatch.setattr(player_api, "uploaded_matches", lambda force=False: [row])
    profiles.invalidate()
    try:
        today = {c["global_id"]: c for c in ok(client, "/api/players", limit=200)["players"]}
        assert today[STAR]["appearances"] == base_card["appearances"] + 1
        for params in ({"competition": ENGLAND_ID, "scope": "competition"}, {"competition": ENGLAND_ID}):
            cat = ok(client, "/api/players", limit=200, **params)
            assert cat["basis"] and "Player-view uploads" in cat["basis"]
            mine = next(c for c in cat["players"] if c["global_id"] == STAR)
            assert (mine["appearances"], mine["minutes"]) == (today[STAR]["appearances"], today[STAR]["minutes"])
            assert {k: h["per90"] for k, h in mine["headline"].items()} == \
                {k: h["per90"] for k, h in today[STAR]["headline"].items()}
            if params.get("scope") == "competition":
                for gid, c in ((c["global_id"], c) for c in cat["players"]):
                    assert {k: h["percentile"] for k, h in c["headline"].items()} == \
                        {k: h["percentile"] for k, h in today[gid]["headline"].items()}
        prof = ok(client, f"/api/players/{STAR}", include="career")
        eng = next(r for r in prof["career"]["career"] if r["competition_id"] == ENGLAND_ID)
        assert prof["appearances"] == eng["appearances"] + 1          # the career rows: league fixtures only, said so
        assert prof["career"]["profile_only_matches"] == ["pv_fake"] and prof["career"]["basis"]
    finally:
        profiles.invalidate()


def test_players_total_counts_every_card_when_paged(client):
    """Review A #2: without offset /api/players is what it always was; with offset, total counts every filtered card."""
    plain = ok(client, "/api/players", limit=5)
    assert plain["total"] == len(plain["players"]) == 5 and "offset" not in plain
    every = ok(client, "/api/players", limit=200)["total"]
    page = ok(client, "/api/players", limit=5, offset=10)
    assert page["total"] == every and page["offset"] == 10 and len(page["players"]) == 5
    assert [c["global_id"] for c in page["players"]] == \
        [c["global_id"] for c in ok(client, "/api/players", limit=200)["players"][10:15]]
    assert ok(client, "/api/players", limit=5, offset=0)["total"] == every
    cat = ok(client, "/api/players", limit=5, offset=10, competition=ENGLAND_ID)
    assert cat["total"] == every


def test_existing_endpoints_answer_other_competitions_in_todays_shapes(client):
    base_screen = ok(client, "/api/terminal/screen")
    s = ok(client, "/api/terminal/screen", country="Germany")
    added = {"rank_by", "rank_rule", "boards"}                     # catalogue mode only: how the rows were ranked
    assert set(s) == set(base_screen) | added and all(r["competition_id"] == GER for r in s["players"])
    assert s["season"]["scope"] == "level" and s["season"]["competition_id"] == GER
    r = ok(client, "/api/terminal/rank", metric="npxg", tier="college", gender="men")
    assert set(r) == set(ok(client, "/api/terminal/rank", metric="npxg")) | added and r["season"]["warning"] is None
    sc = ok(client, "/api/terminal/scatter", x="npxg", y="xa", gender="women")
    assert set(sc) == set(ok(client, "/api/terminal/scatter", x="npxg", y="xa"))
    assert sc["points"] and all("x_pool" in p and p["gender"] == "women" for p in sc["points"])
    lvl = ok(client, "/api/terminal/screen", scope="level")                  # scope alone: England, level pools
    assert {r["competition_id"] for r in lvl["players"]} == {ENGLAND_ID}
    assert all(c["pool"]["competitions"] == [ENGLAND_ID, GER] for c in _cells(lvl))
    pool_alias = ok(client, "/api/terminal/screen", pool="all")
    assert pool_alias["season"]["scope"] == "all" and pool_alias["season"]["warning"]
    assert client.get("/api/terminal/screen", params={"scope": "level", "pool": "all"}).status_code == 422
    assert client.get("/api/terminal/screen", params={"scope": "league"}).status_code == 422

    base_metrics = ok(client, f"/api/players/{STAR}/metrics", group="shooting")
    pm = ok(client, f"/api/players/{CRUZ}/metrics", competition="co_esp_am_men", group="shooting", evidence_limit=1)
    assert set(base_metrics) <= set(pm) and pm["competition_id"] == "co_esp_am_men"
    assert all(len(c["evidence"]["items"]) <= 1 and "pool" in c for c in pm["metrics"].values())
    one = ok(client, f"/api/players/{CRUZ}/metrics", competition="co_esp_u19", evidence="shots")
    assert one["competition_id"] == "co_esp_u19" and "evidence" in one
    form = ok(client, f"/api/players/{CRUZ}/form", scope="level")
    assert form["competition_id"] == "co_esp_am_men" and set(ok(client, f"/api/players/{STAR}/form")) <= set(form)
    sim = ok(client, f"/api/players/{STAR}/similar", scope="all")
    assert sim["warning"] and sim["similar"] and all("same_level" in x for x in sim["similar"])
    shots = ok(client, f"/api/players/{CRUZ}/shots", competition="co_esp_u19")
    assert all(x["match_id"].startswith("cm_eu19_") for x in shots["shots"])
    heat = ok(client, f"/api/players/{CRUZ}/heatmap", competition="co_esp_u19")
    assert len(heat["grid"]) == 8 and heat["total"] == sum(map(sum, heat["grid"]))
    assert client.get(f"/api/players/{CRUZ}/shots", params={"competition": GER}).status_code == 404

    teams = ok(client, "/api/teams", country="Ghana")
    assert teams["competitions"] == ["co_gha_u17"] and len(teams["teams"]) == 4
    assert all("level_rank" in t["values"]["possession_pct"] for t in teams["teams"])
    style = ok(client, "/api/teams/cl_hollenburg/style", competition=GER)
    assert style["values"]["possession_pct"]["level_of"] == 12 and style["competition_id"] == GER
    tshots = ok(client, "/api/teams/cl_hollenburg/shots", competition=GER, side="against")
    assert tshots["side"] == "against" and tshots["competition_id"] == GER
    assert client.get("/api/teams/cl_hollenburg/style", params={"competition": ENGLAND_ID}).status_code == 404
    met = ok(client, "/api/metrics", competition="co_gha_u17")
    assert len(met["metrics"]) == len(ok(client, "/api/metrics")["metrics"]) and met["season"]["competition_id"] == "co_gha_u17"


def test_season_and_players_take_a_competition(client):
    today = ok(client, "/api/season")
    eng = ok(client, "/api/season", competition=ENGLAND_ID)
    assert {k: v for k, v in eng.items() if k not in ("competition", "table_note", "warm")} == \
        {k: v for k, v in today.items() if k != "warm"}
    mar = ok(client, "/api/season", competition=MAR)
    assert set(today) <= set(mar) and mar["league"] == "Ligue Juniors Atlas Centre U19"
    assert mar["table_note"] == "uploaded matches only, not a league table" and mar["percentiles"]["min_minutes"] == 45.0
    assert sum(len(r["matches"]) for r in mar["rounds"]) == 3
    assert client.get("/api/season", params={"competition": "co_nowhere"}).status_code == 422

    women = ok(client, "/api/players", gender="women", position="FW", min_minutes=45, sort="goals", limit=200)
    assert women["total"] == len(women["players"]) and women["scope"] == "level"
    assert {p["competition_id"] for p in women["players"]} == {"co_eng_sp_women", "co_usa_col_women"}
    for p in women["players"]:
        assert all(h["pool"]["gender"] == "women" for h in p["headline"].values())
    page = ok(client, "/api/players", gender="women", position="FW", min_minutes=45, sort="goals", limit=3, offset=3)
    assert [p["global_id"] for p in page["players"]] == [p["global_id"] for p in women["players"][3:6]]
    assert client.get("/api/players", params={"gender": "women", "sort": "nonsense"}).status_code == 422


def test_a_pooled_profile_percentile_is_fbrefs_rule_by_hand(client):
    """College men: USA and Japan pooled. Recompute one forward's goals percentile from the cards themselves."""
    rows = ok(client, "/api/players", tier="college", gender="men", position="FW", limit=200)["players"]
    from regista.catalogue_api import catalogue_profiles

    cp = catalogue_profiles()
    pool = []
    for cid in ("co_usa_col_men", "co_jpn_uni_men"):
        s = cp.seasons[cid]
        for p in s.profiles.values():
            mins = cp.exact_minutes.get((cid, p["global_id"]), p["minutes"])
            if p["position"] == "FW" and p["appearances"] and mins >= s.min_minutes:
                pool.append(rank_value(p["counts"]["goals"] * 90.0 / mins))
    pool.sort()
    target = next(r for r in rows if r["headline"]["goals"]["percentile"] is not None)
    cid = target["competition_id"]
    p = cp.seasons[cid].profiles[target["global_id"]]
    mins = cp.exact_minutes[(cid, p["global_id"])]
    assert target["headline"]["goals"]["percentile"] == round(fbref_percentile(pool, rank_value(p["counts"]["goals"] * 90.0 / mins)))
    assert target["headline"]["goals"]["pool"]["size"] == len(pool)


def test_404s_hint_at_the_catalogue_only_for_catalogue_ids(client):
    r = client.get(f"/api/players/{CRUZ}")
    assert r.status_code == 404 and f"GET /api/catalogue/players/{CRUZ}" in r.json()["detail"]
    assert client.get("/api/players/pl_zzz_09").json()["detail"] == "no player 'pl_zzz_09' in the league"
    r = client.get(f"/api/players/{CRUZ}/similar")
    assert r.status_code == 404 and "catalogue player" in r.json()["detail"]
    r = client.get("/api/teams/cl_hollenburg/style")
    assert r.status_code == 404 and f"competition={GER}" in r.json()["detail"]


def test_bad_inputs_are_refused(client):
    bad = [("/api/catalogue/players", {"camera": "satellite"}), ("/api/catalogue/players", {"age_min": 20, "age_max": 18}),
           ("/api/catalogue/players", {"metrics": "npxg,warp_speed"}), ("/api/catalogue/players", {"limit": 500}),
           ("/api/catalogue/players", {"offset": -1}), ("/api/catalogue/rank", {"metric": "warp_speed"}),
           ("/api/catalogue/rank", {}), ("/api/catalogue/matches", {"uploader_type": "fan"}),
           ("/api/catalogue/matches", {"club": "Hollenburg"}), ("/api/catalogue/pools", {"scope": "galaxy"}),
           ("/api/terminal/rank", {"metric": "npxg", "competition": "co_nowhere"}),
           ("/api/players", {"competition": "eng"}), ("/api/catalogue/compare", {"ids": STAR}),
           (f"/api/players/{STAR}/metrics", {"competition": "co_nowhere"})]
    for path, params in bad:
        assert client.get(path, params=params).status_code in (400, 422), (path, params)


def test_a_catalogue_match_opens_in_the_clip_view(client):
    mid = ok(client, f"/api/competitions/{GER}")["matches"][0]["match_id"]
    clips = client.get(f"/api/matches/{mid}/clips")
    assert clips.status_code == 200 and clips.json()


# ---------------------------------------------------------------------------- never a hidden rating, scale or seed

def test_no_hidden_rating_scale_or_seed_in_any_new_payload(client):
    paths = [("/api/catalogue", {}), ("/api/competitions", {}), (f"/api/competitions/{GER}", {}),
             (f"/api/competitions/{ENGLAND_ID}", {}), (f"/api/competitions/{MAR}/players", {"min_minutes": 0}),
             ("/api/catalogue/players", {"limit": 200}), ("/api/catalogue/players", {"scope": "all", "limit": 200}),
             (f"/api/catalogue/players/{CRUZ}", {}), (f"/api/catalogue/players/{CRUZ}", {"evidence": "npxg"}),
             (f"/api/catalogue/players/{STAR}", {"scope": "competition"}),
             ("/api/catalogue/rank", {"metric": "peak_speed"}), ("/api/catalogue/compare", {"ids": f"{STAR},{CRUZ}"}),
             ("/api/catalogue/matches", {"limit": 200}), ("/api/catalogue/pools", {}), (f"/api/players/{CRUZ}/career", {}),
             (f"/api/players/{STAR}", {"include": "career"}), ("/api/season", {"competition": GER}),
             ("/api/players", {"tier": "academy", "limit": 200}), ("/api/terminal/screen", {"country": "Ghana"}),
             ("/api/terminal/rank", {"metric": "npxg", "gender": "women"}),
             ("/api/terminal/scatter", {"x": "peak_speed", "y": "distance", "tier": "amateur"}),
             (f"/api/players/{CRUZ}/metrics", {"competition": "co_esp_u19"}), (f"/api/players/{CRUZ}/form", {"scope": "all"}),
             (f"/api/players/{CRUZ}/similar", {"scope": "level"}), (f"/api/players/{CRUZ}/shots", {"scope": "level"}),
             (f"/api/players/{CRUZ}/heatmap", {"scope": "level"}), ("/api/teams", {"tier": "academy"}),
             ("/api/teams/cl_hollenburg/style", {"competition": GER}), ("/api/teams/cl_hollenburg/shots", {"competition": GER}),
             ("/api/metrics", {"competition": MAR})]
    for path, params in paths:
        found = _hidden(ok(client, path, **params))
        assert not found, (path, params, found[:5])


# ---------------------------------------------------------------------------- one board shape on every surface

BOARD_KEYS = {"board", "by", "label", "gender", "level", "position", "size", "offset", "top"}


def test_every_surface_serves_one_board_shape(client):
    """Review A round 3 nit: the MCP tool, the rank lists, the screens and /api/players carry the same board keys."""
    from regista import mcp_server

    lists = [ok(client, "/api/catalogue/rank", metric="np_goals", position="FW"),
             ok(client, "/api/catalogue/players", metrics="np_goals", sort="np_goals", position="FW"),
             ok(client, "/api/terminal/rank", metric="np_goals", position="FW", country="England"),
             ok(client, "/api/terminal/screen", metrics="np_goals", sort="np_goals", position="FW", country="England"),
             ok(client, "/api/players", position="FW", sort="goals", country="England"),
             ok(client, "/api/catalogue/rank", metric="goals", country="England"),
             mcp_server.search_catalogue_players(position="FW", sort="np_goals", limit=3)]
    for d in lists:
        assert d["boards"] and all(set(b) == BOARD_KEYS for b in d["boards"]), d["boards"][0].keys()
        assert sum(b["size"] for b in d["boards"]) <= max(d.get("total") or 0, d.get("ranked") or 0)
        assert all(b["top"] and all(r["board"] == b["board"] for r in b["top"]) for b in d["boards"])


def test_ratio_pools_on_cards_need_the_minimum_attempts(client, cm):
    """Review A round 3 nit: a profile ratio's pooled percentile on /api/players needs its competition's minimum attempts,
    as the terminal's ratio metrics do (pass accuracy: 10 passes)."""
    from regista.catalogue_api import catalogue_profiles

    cp = catalogue_profiles()
    assert cp.min_attempts(GER, "pass_accuracy") == cm.metrics[GER].thresholds["attempts"]["min"] == 10
    assert cp.min_attempts(GER, "take_on_success") == cm.metrics[GER].thresholds["take_ons"]["min"]
    d = ok(client, "/api/players", tier="semi_pro", position="FW", sort="pass_accuracy", limit=200)
    assert d["rank_by"] == "pool"
    for card in d["players"]:
        cid, gid = card["competition_id"], card["global_id"]
        p = cp.seasons[cid].profiles[gid]
        pct, _small = cp.sort_percentile(cid, gid, "pass_accuracy", "level")
        if p["counts"]["passes"] < cp.min_attempts(cid, "pass_accuracy"):
            assert pct is None, (gid, p["counts"]["passes"])


# ---------------------------------------------------------------------------- the catalogue MCP tools

def test_the_catalogue_mcp_tools_are_listed_and_answer(client):
    from regista import mcp_server

    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"list_competitions", "search_catalogue_players", "get_catalogue_player",
            "search_players", "get_profile", "compare_players"} <= names
    lc = mcp_server.list_competitions(gender="women")
    assert [c["competition_id"] for c in lc["competitions"]] == ["co_eng_sp_women", "co_usa_col_women"]
    assert "error" in mcp_server.list_competitions(tier="professional")
    sp = mcp_server.search_catalogue_players(gender="men", position="FW", sort="npxg", limit=5)
    assert len(sp["players"]) == 5 and all(p["stat"]["pool"]["scope"] == "level" for p in sp["players"])
    assert sp["warning"]                                    # men across levels
    eng = mcp_server.search_catalogue_players(competition=ENGLAND_ID, position="FW", sort="np_goals", limit=1)
    assert eng["players"][0]["global_id"] == STAR and eng["warning"] is None
    assert sp["rank_by"] == "pool" and all(p["board"] == "men" for p in sp["players"])
    both = mcp_server.search_catalogue_players(position="FW", sort="np_goals", limit=50)
    assert [b["gender"] for b in both["boards"]] == ["men", "women"] and both["players"][0]["global_id"] == STAR
    raw = mcp_server.search_catalogue_players(gender="men", position="FW", sort="npxg", limit=5, rank_by="value")
    assert raw["rank_by"] == "value" and "error" in mcp_server.search_catalogue_players(sort="npxg", rank_by="luck")
    assert "error" in mcp_server.search_catalogue_players(sort="charisma")
    assert "error" in mcp_server.search_catalogue_players(competition="co_nowhere")
    gp = mcp_server.get_catalogue_player("Sergio Cruz")
    assert gp["global_id"] == CRUZ and len(gp["rows"]) == 2 and not _hidden(gp)
    assert "candidates" in mcp_server.get_catalogue_player("nobody at all")
    assert not _hidden(sp) and not _hidden(lc)


# ---------------------------------------------------------------------------- review round 2: order, boards, /api/players

def _oriented(rows, key="fouls"):
    return [r["values"][key]["percentile"] for r in rows if r["values"][key]["percentile"] is not None]


def test_order_is_the_raw_direction_in_both_rank_modes(client, cm):
    """Review A round 2 #1: "most fouls" (order=desc) lists the largest numbers first in value mode and in pool mode, so
    a lower-is-better metric's desc puts the lowest (oriented) percentiles first across levels; no order: best first."""
    from regista.season.metrics import CATALOGUE

    assert CATALOGUE["fouls"].higher_is_better is False and CATALOGUE["fouls"].kind == "per90"
    base = {"metric": "fouls", "position": "MF", "country": "England", "gender": "men", "limit": 200}   # two levels
    desc = ok(client, "/api/catalogue/rank", **base, order="desc")
    asc = ok(client, "/api/catalogue/rank", **base, order="asc")
    best = ok(client, "/api/catalogue/rank", **base)
    assert desc["rank_by"] == asc["rank_by"] == best["rank_by"] == "pool"
    assert {p["competition_id"] for p in desc["players"]} == {ENGLAND_ID, "co_eng_u18"}
    pd, pa, pb = ([p["percentile"] for p in d["players"]] for d in (desc, asc, best))
    assert pd == sorted(pd) and pa == sorted(pa, reverse=True) and pb == sorted(pb, reverse=True)
    assert pd[0] < pd[-1]
    # the top of "most fouls" commits more fouls than the top of "fewest fouls", within each pool
    for cid in (ENGLAND_ID, "co_eng_u18"):
        d = [p["value"] for p in desc["players"] if p["competition_id"] == cid]
        a = [p["value"] for p in asc["players"] if p["competition_id"] == cid]
        assert d == sorted(d, reverse=True) and a == sorted(a)
    # one level (value mode): the same direction
    one = ok(client, "/api/catalogue/rank", metric="fouls", position="MF", competition=GER, order="desc", limit=200)
    vals = [p["value"] for p in one["players"]]
    assert one["rank_by"] == "value" and vals == sorted(vals, reverse=True)
    # the terminal's screen and the cross-country screen agree
    for path in ("/api/terminal/screen", "/api/catalogue/players"):
        scr = ok(client, path, metrics="fouls", sort="fouls", order="desc", position="MF", country="England",
                 gender="men", limit=200)
        assert scr["rank_by"] == "pool" and _oriented(scr["players"]) == sorted(_oriented(scr["players"]))
        best_first = ok(client, path, metrics="fouls", sort="fouls", position="MF", country="England", gender="men",
                        limit=200)
        assert _oriented(best_first["players"]) == sorted(_oriented(best_first["players"]), reverse=True)


def test_catalogue_cards_rank_within_pools_on_gender_boards(client):
    """Review A round 2 #2 and review B round 3 S-B: /api/players in catalogue mode ranks a per-90 sort of one position
    across levels by each card's percentile in its pool, men and women on separate boards; cards of more than one
    position across levels by value within each level, one board per level; and says how it ranked."""
    fw = ok(client, "/api/players", country="England", position="FW", sort="goals", limit=200, offset=0)
    assert fw["rank_by"] == "pool" and fw["rank_rule"] and [b["board"] for b in fw["boards"]] == ["men", "women"]
    boards = [p["board"] for p in fw["players"]]
    assert boards == sorted(boards, key=["men", "women"].index)       # men's board, then women's: never mixed
    men, women = fw["boards"]
    assert men["offset"] == 0 and women["offset"] == men["size"] and men["size"] + women["size"] == fw["total"]
    assert all(p["board"] == "women" for p in fw["players"][women["offset"]:]) and women["top"][0]["board"] == "women"
    for g in ("men", "women"):
        pct = [p["headline"]["goals"]["percentile"] for p in fw["players"] if p["board"] == g]
        ranked = [x for x in pct if x is not None]
        assert ranked == sorted(ranked, reverse=True) and pct[:len(ranked)] == ranked   # unranked cards follow
    semi = ok(client, "/api/players", tier="semi_pro", position="FW", sort="goals", limit=200)
    first = [p for p in semi["players"] if p["board"] == "men"]
    assert first and semi["players"][:len(first)] == first and semi["rank_by"] == "pool"   # semi-pro men and women
    assert {p["competition_id"] for p in first} == {ENGLAND_ID, GER} and first[0]["global_id"] == STAR
    # every position across levels: by value within each level, one board per level
    d = ok(client, "/api/players", country="England", sort="goals", limit=200)
    assert d["rank_by"] == "value" and [b["board"] for b in d["boards"]] == \
        ["semi_pro/senior/men", "academy/U18/men", "semi_pro/senior/women"]
    assert d["players"][0]["global_id"] == STAR and d["boards"][0]["top"][0]["global_id"] == STAR
    for b in d["boards"]:
        per90 = [p["headline"]["goals"]["per90"] for p in d["players"][b["offset"]:b["offset"] + b["size"]]]
        rises = sum(1 for a, c in zip(per90, per90[1:]) if c > a)
        assert rises <= 1 and b["label"] and b["by"] == "level"   # qualified cards by value, then the rest by value
    men_only = ok(client, "/api/players", tier="semi_pro", gender="men", position="FW", sort="goals", limit=200)
    assert men_only["rank_by"] == "value" and men_only["boards"] is None                # one level: by value
    raw = ok(client, "/api/players", country="England", gender="men", position="FW", sort="goals", rank_by="value",
             limit=200)
    assert raw["rank_by"] == "value" and [b["by"] for b in raw["boards"]] == ["level", "level"]
    acc = ok(client, "/api/players", country="England", gender="men", position="MF", sort="pass_accuracy", limit=200)
    assert acc["rank_by"] == "pool"                                    # a ratio ranks by its percentile too
    plain = ok(client, "/api/players", limit=5)                        # no catalogue parameter: today's response
    assert "rank_by" not in plain and "boards" not in plain


def test_most_goals_in_england_puts_the_top_scorer_first_on_every_surface(client):
    """Review B round 3 S-B: a list across levels and positions never interleaves positions by percentile (a one-goal
    defender at the top of his position above the five-goal top scorer). It ranks by value within each level, one board
    per level, so "most goals in England" opens on Femi Toure everywhere."""
    from regista import mcp_server

    def first_board_ok(d, rows_key="players"):
        assert d["rank_by"] == "value" and d["boards"][0]["board"] == "semi_pro/senior/men", d.get("rank_by")
        assert d[rows_key][0]["global_id"] == STAR and d["boards"][0]["top"][0]["global_id"] == STAR
        assert len({b["board"] for b in d["boards"]}) == len(d["boards"]) == 3

    r = ok(client, "/api/catalogue/rank", metric="goals", country="England")
    first_board_ok(r)
    assert r["players"][0]["rank"] == 1 and r["players"][0]["position"] == "FW"
    men = [p for p in r["players"] if p["board"] == "semi_pro/senior/men"]
    assert [p["value"] for p in men] == sorted((p["value"] for p in men), reverse=True)
    first_board_ok(ok(client, "/api/catalogue/players", country="England", metrics="goals", sort="goals", order="desc"))
    first_board_ok(ok(client, "/api/terminal/rank", metric="goals", country="England"))
    first_board_ok(ok(client, "/api/terminal/screen", metrics="goals", sort="goals", order="desc", country="England"))
    first_board_ok(ok(client, "/api/players", country="England", sort="goals"))
    tool = mcp_server.search_catalogue_players(country="England", sort="goals", limit=5)
    first_board_ok(tool)
    assert tool["hint"] and {b["by"] for b in tool["boards"]} == {"level"}
    # one position across levels still ranks by percentile within pools, which the rule says plainly
    fw = ok(client, "/api/catalogue/rank", metric="goals", country="England", position="FW")
    assert fw["rank_by"] == "pool" and fw["players"][0]["global_id"] == STAR
    assert "never outranks" in fw["rank_rule"] and "not the largest numbers" in fw["rank_rule"]
    # rank_by=pool across positions keeps positions apart: one board per gender and position
    forced = ok(client, "/api/catalogue/rank", metric="goals", country="England", rank_by="pool", limit=200)
    assert {b["by"] for b in forced["boards"]} == {"gender_position"}
    assert all(len({p["position"] for p in forced["players"] if p["board"] == b["board"]}) == 1 for b in forced["boards"])


def test_terminal_catalogue_payloads_say_how_they_ranked(client):
    r = ok(client, "/api/terminal/rank", metric="np_goals", position="FW", country="England")
    assert r["rank_by"] == "pool" and r["rank_rule"] and [b["gender"] for b in r["boards"]] == ["men", "women"]
    assert r["boards"][1]["top"] and all(p["board"] == "women" for p in r["boards"][1]["top"])
    v = ok(client, "/api/terminal/rank", metric="npxg", tier="academy", gender="men", rank_by="value", limit=200)
    assert v["rank_by"] == "value" and len(v["boards"]) == 4
    for b in v["boards"]:   # by value within each level
        vals = [p["value"] for p in v["players"] if p["board"] == b["board"]]
        assert vals == sorted(vals, reverse=True) and vals[0] == b["top"][0]["value"]
    s = ok(client, "/api/terminal/screen", metrics="npxg", tier="academy", gender="men", rank_by="value", limit=200)
    assert s["rank_by"] == "value" and [b["board"] for b in s["boards"]] == [b["board"] for b in v["boards"]]
    for b in s["boards"]:
        vals = [p["values"]["npxg"]["value"] for p in s["players"] if p["board"] == b["board"]
                and p["values"]["npxg"]["value"] is not None]
        assert vals == sorted(vals, reverse=True)
    assert "rank_by" not in ok(client, "/api/terminal/rank", metric="npxg")    # today's response keeps its keys


def test_a_mixed_gender_rank_shows_the_womens_board_on_its_first_page(client):
    """Review B round 2 #4: the women's board is reachable from the first page and from the MCP tool."""
    from regista import mcp_server

    r = ok(client, "/api/catalogue/rank", metric="np_goals", position="FW")
    men, women = r["boards"]
    assert (men["gender"], women["gender"]) == ("men", "women") and women["size"] > 0
    assert women["offset"] == men["size"] and men["offset"] == 0
    assert women["top"] and all(p["board"] == "women" and p["rank"] >= 1 for p in women["top"])
    assert women["top"][0]["rank"] == 1 and men["top"][0]["global_id"] == r["players"][0]["global_id"]
    there = ok(client, "/api/catalogue/rank", metric="np_goals", position="FW", offset=women["offset"], limit=5)
    assert [p["global_id"] for p in there["players"]] == [p["global_id"] for p in women["top"]]
    scr = ok(client, "/api/catalogue/players", metrics="np_goals", sort="np_goals", position="FW", limit=10)
    assert scr["boards"][1]["gender"] == "women" and scr["boards"][1]["top"]
    assert all(p["board"] == "women" for p in scr["boards"][1]["top"])
    tool = mcp_server.search_catalogue_players(position="FW", sort="np_goals", limit=10)
    assert any(p["board"] == "women" for p in tool["players"]) and tool["hint"]
    assert [b["board"] for b in tool["boards"]] == ["men", "women"]
    assert [sum(p["board"] == g for p in tool["players"]) for g in ("men", "women")] == [10, 10]
    assert sum(b["size"] for b in tool["boards"]) == tool["total"]
    only = mcp_server.search_catalogue_players(position="FW", sort="np_goals", gender="women", limit=10)
    assert only["boards"] is None and only["hint"] is None
    assert [p["global_id"] for p in only["players"]] == [p["global_id"] for p in tool["players"] if p["board"] == "women"]
