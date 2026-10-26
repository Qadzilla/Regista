"""The catalogue UI port's backend (docs/redesign/catalogue/port-map.md §3, items B2-B15; report backend.md).

- B2  catalogue pages count England's league fixtures only; Player-view uploads and claims are named (``not_counted``).
- B3  ``include=profile``: the profile page's shape for every catalogue row (ratios and passes from the metrics engine,
      goalkeepers' outfield numbers decided by it, none yet, evidence, matches with uploader and camera).
- B4  summaries worded for the competition (the league profile's own summary unchanged: the back-compat snapshot).
- B5  none yet: a count at 0 has no percentile and no place; with_any / none_yet on lists and boards.
- B6  pool words; B7 the sample in plain words; B8 squads with playing time, clubs, player uploads.
- B9  tier lists, min_percentile, sort=minutes and sort=name; B10 compare's best; B11 similar in plain words; B12 links.
- B15 uploads from catalogue clubs (LocalStore only): the form, the record, the worker's roster and manifest, never
      counted, named on the competition page and the player's career.

Reads the committed catalogue and the Regista League as the app builds them. Nothing reaches Azure or the live app.
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api, player_api
from regista.catalogue.metrics import build_catalogue_metrics
from regista.catalogue.taxonomy import ENGLAND_ID
from regista.season.league import ATTRIBUTE_KEYS
from regista.season.metrics import CATALOGUE, COUNT_METRICS, load_metrics

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes", "skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift",
                                "execution", "style_offset", "level_scale", "seed", "age_range", "level"}
STAR, CRUZ, GER = "pl_bro_09", "pl_sot_09", "co_ger_sp_men"
NGA, NGA_CLUB, NGA_OPP, NGA_GID = "co_nga_am_men", "cl_adire_stars", "cl_riverbank", "pl_ads_09"
ADMIN = "admin-key-for-tests"
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64


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
            if k in HIDDEN and not (k == "level" and isinstance(v, (str, type(None)))):   # "level": a label, never a scale
                found.append(f"{path}.{k}")
            found += _hidden(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += _hidden(v, f"{path}[{i}]")
    return found


def _fake_upload(monkeypatch, tmp_path, gid=STAR, club="cl_brookfield"):
    """A finished Player-view upload for ``gid`` the league profile counts (as tests/test_catalogue_api.py does)."""
    from regista.schema import iter_jsonl
    from regista.season import profiles
    from regista.season.league import load_league

    league = load_league(LEAGUE)
    fx = next(f for f in league["fixtures"] if club in (f["home"], f["away"]))
    d = shutil.copytree(SEASON_ROOT / fx["match_id"], tmp_path / "pv_fake")
    header = next(iter_jsonl(d / "events.jsonl"))
    pid = next(p["player_id"] for p in header["players"] if p.get("global_player_id") == gid)
    row = {"match_id": d.name, "match_dir": str(d), "player_id": pid, "global_id": gid, "upload_id": "up_fake"}
    monkeypatch.setattr(player_api, "uploaded_matches", lambda force=False: [row])
    profiles.invalidate()
    return row


# ---------------------------------------------------------------------------- B2: England counts the fixtures only

def test_catalogue_pages_count_englands_fixtures_only_and_name_the_upload(client, monkeypatch, tmp_path):
    from regista.season import profiles

    _fake_upload(monkeypatch, tmp_path)
    try:
        league = ok(client, f"/api/players/{STAR}")
        assert league["appearances"] == 11            # the league profile counts the upload, as today
        d = ok(client, f"/api/catalogue/players/{STAR}", include="profile")
        row = d["rows"][0]
        pr = row["profile"]
        assert (pr["appearances"], pr["minutes"], pr["counts"]["goals"]) == (10, 274.3, 5)
        assert row["sample"]["appearances"] == 10 and row["metrics"]["np_goals"]["total"] == 5
        assert [u["match_id"] for u in row["not_counted"]] == ["pv_fake"] == [u["match_id"] for u in d["not_counted"]]
        assert row["not_counted"][0]["source"] == "upload" and row["not_counted"][0]["opponent"]
        assert "fixtures only (10 matches)" in row["basis"] and "not counted here" in row["basis"]
        assert "Player view" in row["basis"] and d["basis"] and d["profile_url"] == f"/players/{STAR}"
        assert all(m["source"] == "league" for m in pr["matches"]) and len(pr["matches"]) == 10
        assert sum(map(sum, pr["grid"])) == sum(map(sum, row["touch_map"]))
        assert "Toure" in row["summary"]["text"] and row["summary"]["engine"] == "rules"
    finally:
        profiles.invalidate()


def test_without_uploads_the_basis_says_only_what_counts(client):
    row = ok(client, f"/api/catalogue/players/{CRUZ}")["rows"][1]
    assert row["not_counted"] == [] and row["basis"] == ("These numbers count Regional Preferente Levante Interior's "
                                                         f"uploaded matches only ({row['sample']['appearances']} matches).")


# ---------------------------------------------------------------------------- B3: the profile page's shape

def test_a_catalogue_profile_has_the_profile_pages_shape(client, cm):
    from regista.season.profiles import METRIC_OF, RATIOS, STATS

    d = ok(client, f"/api/catalogue/players/{CRUZ}", include="profile", scope="level")
    assert [r["competition_id"] for r in d["rows"]] == ["co_esp_u19", "co_esp_am_men"]
    for row in d["rows"]:
        cid, pr = row["competition_id"], row["profile"]
        assert set(pr["stats"]) == set(STATS) and set(pr["ratios"]) == set(RATIOS) and pr["scope"] == "level"
        assert len(pr["grid"]) == 8 and pr["moments"] and len(pr["moments"]) <= 40
        assert pr["matches"] and all(m["uploader"] and m["camera"] and m["clip_view"].startswith(f"/?match={m['match_id']}")
                                     for m in pr["matches"])
        assert [m["date"] for m in pr["matches"]] == sorted((m["date"] for m in pr["matches"]), reverse=True)
        for r, ratio in pr["ratios"].items():       # the metrics engine's ratio, value and denominator
            want = cm.cell(cid, CRUZ, METRIC_OF[r], "level")
            assert (ratio["value"], ratio["den"], ratio["percentile"]) == (want["value"], want["den"], want["percentile"])
        for k in ("passes", "passes_completed"):    # passes from the metrics engine (crosses included)
            want = cm.cell(cid, CRUZ, k, "level")
            assert pr["stats"][k]["per90"] == want["value"] and pr["stats"][k]["count"] == round(want["total"])
            assert "crosses included" in pr["stats"][k]["label"] and pr["counts"][k] == pr["stats"][k]["count"]
        for k, st in pr["stats"].items():
            assert st["pool"]["words"] and st["pool"]["scope"] == "level"
            assert st["evidence_total"] >= len(pr["evidence"][k]["items"]) and len(pr["evidence"][k]["items"]) <= 10
            if st["none_yet"]:
                assert st["count"] == 0 and st["percentile"] is None and st["none_yet"]["of"] == st["pool"]["size"]
        ev = [i for e in pr["evidence"].values() for i in e["items"]]
        assert ev and all(i["minute"] is None or 1 <= i["minute"] <= 95 for i in ev)
        assert all(i["video_url"] == f"/api/matches/{i['match_id']}/clips/{i['clip_id']}.mp4" for i in ev if i["clip_id"])
    assert not _hidden(d)


def test_goalkeepers_outfield_numbers_follow_the_metrics_engine(client):
    gk = next(p for p in ok(client, "/api/catalogue/players", position="GK", competition=ENGLAND_ID, limit=5)["players"])
    pr = ok(client, f"/api/catalogue/players/{gk['global_id']}", include="profile")["rows"][0]["profile"]
    for k in ("interceptions", "tackles_won", "key_passes", "forward_passes", "goals"):
        st = pr["stats"][k]
        assert st["percentile"] is None and st["reason"] == "not ranked for goalkeepers" and st["none_yet"] is None, k
    assert pr["stats"]["saves"]["percentile"] is not None and pr["stats"]["saves"]["reason"] is None
    assert pr["stats"]["passes"]["percentile"] is not None          # passes are scored for keepers


def test_fewer_is_better_counts_are_never_none_yet(client):
    rows = ok(client, "/api/catalogue/players", position="FW", competition=ENGLAND_ID, limit=50)["players"]
    seen = 0
    for p in rows[:12]:
        pr = ok(client, f"/api/catalogue/players/{p['global_id']}", include="profile")["rows"][0]["profile"]
        for k in ("offsides", "aerial_duels_lost"):
            if pr["stats"][k]["count"] == 0:
                seen += 1
                assert pr["stats"][k]["none_yet"] is None
    assert seen


# ---------------------------------------------------------------------------- B4: summary wording

def test_summaries_are_worded_for_their_competition(client, cm):
    star = ok(client, f"/api/catalogue/players/{STAR}")["rows"][0]["summary"]["text"]
    assert "the best of the Regista League's 18 forwards" in star and "1.64 goals per 90" in star
    assert "matchday" not in star and "the league's" not in star
    league = ok(client, f"/api/players/{STAR}")["summary"]["text"]
    assert "the league's 18 forwards" in league                      # the league profile's own summary is unchanged
    sparse = ok(client, f"/api/catalogue/players/{CRUZ}")["rows"][1]["summary"]["text"]
    assert "with enough minutes in Regional Preferente Levante Interior's uploaded matches" in sparse
    import re

    rates = re.findall(r"\d+\.(\d+) (?:[a-z -]+ )?per 90", sparse)
    assert rates and all(len(x) == 2 for x in rates)                    # two decimals
    short = next((cid, ps) for cid in cm.order if cid != ENGLAND_ID for ps in cm.metrics[cid].players.values()
                 if 0 < ps.minutes < cm.metrics[cid].min_minutes and ps.appearances)
    d = ok(client, f"/api/catalogue/players/{short[1].info['global_id']}", competition=short[0])
    text = next(r for r in d["rows"] if r["competition_id"] == short[0])["summary"]["text"]
    assert "Not ranked:" in text and "needed" in text and "also ranks" not in text and " of the " not in text


# ---------------------------------------------------------------------------- B5: none yet

def test_none_yet_has_no_place_and_lists_say_how_many_have_any(client):
    r = ok(client, "/api/catalogue/rank", metric="goals", country="England", limit=200)
    assert (r["ranked"], r["with_any"], r["none_yet"]) == (25, 25, 116)
    assert all(p["value"] > 0 and not p["none_yet"] for p in r["players"])
    assert all(b["with_any"] == b["size"] and b["with_any"] + b["none_yet"] <= 141 for b in r["boards"])
    assert sum(b["none_yet"] for b in r["boards"]) == 116 and r["none_yet_rule"]
    zeros = [p for p in r["unranked"] if p["none_yet"]]
    assert zeros and all(p["percentile"] is None and p["value"] == 0 and p["zeros"]["of"] == p["pool"]["size"]
                         for p in zeros)
    # the screen lists none yet after the ranked rows on each board
    scr = ok(client, "/api/catalogue/players", country="England", metrics="goals", sort="goals", limit=200)
    for b in scr["boards"]:
        flags = [p["values"]["goals"]["none_yet"] for p in scr["players"][b["offset"]:b["offset"] + b["size"]]
                 if b["offset"] + b["size"] <= 200]
        assert flags == sorted(flags)                                   # False (ranked) first, then True
    # measures at 0 keep their percentile: xG is not a count
    assert "npxg" not in COUNT_METRICS and "goals" in COUNT_METRICS and len(COUNT_METRICS) == 70
    x = ok(client, "/api/catalogue/rank", metric="npxg", competition=GER, position="DF", limit=200)
    assert x["with_any"] is None and any(p["value"] == 0 and p["percentile"] is not None for p in x["players"])
    # the metric list's public shape carries no count flag (the snapshot of /api/metrics)
    assert all("count" not in m for m in ok(client, "/api/metrics")["metrics"])


def test_the_mcp_tool_and_the_terminal_follow_none_yet(client):
    from regista import mcp_server

    t = mcp_server.search_catalogue_players(competition=ENGLAND_ID, sort="assists", limit=50)
    assert t["with_any"] + t["none_yet"] <= t["total"] and t["none_yet"]
    vals = [p["stat"]["none_yet"] for p in t["players"]]
    assert vals == sorted(vals) and all(p["stat"]["pool"]["words"] for p in t["players"])
    tr = ok(client, "/api/terminal/rank", metric="assists", country="England")
    assert all(p["value"] > 0 for p in tr["players"])


# ---------------------------------------------------------------------------- B6, B7: pool words and sample words

def test_pool_words_and_sample_words(client):
    cell = lambda scope: ok(client, f"/api/catalogue/players/{STAR}", scope=scope)["rows"][0]["metrics"]["np_goals"]  # noqa: E731
    lvl, comp, every = cell("level"), cell("competition"), cell("all")
    assert lvl["pool"]["words"] == "semi-pro men forwards" and lvl["percentile"] == 98 and lvl["pool"]["size"] == 33
    assert comp["pool"]["words"] == "forwards in Regista League" and comp["percentile"] == 97 and comp["pool"]["size"] == 18
    assert every["pool"]["words"] == "men forwards at every level" and every["percentile"] == 96 and every["pool"]["size"] == 123
    assert lvl["noisy"] is True                                          # the ≈ mark stays
    cat = ok(client, "/api/catalogue")
    words = {p["key"]: p["words"] for p in cat["levels"]["pools"]}
    assert words["semi_pro/senior/men"] == "semi-pro men" and words["academy/U19/men"] == "academy U19 men"
    assert cat["noisy_words"] and "≈" in cat["noisy_words"]
    g = ok(client, f"/api/competitions/{GER}")
    assert "8 uploaded matches" in g["sample"]["words"] and "regular's season" in g["sample"]["words"]
    assert "regista." not in g["sample"]["words"]
    s = ok(client, "/api/catalogue/players", country="Germany", limit=1)
    assert s["samples"][GER]["words"] == g["sample"]["words"]
    t = ok(client, "/api/terminal/screen", competition=GER)
    assert t["season"]["sample"]["words"] == g["sample"]["words"]


# ---------------------------------------------------------------------------- B8: squads, clubs, uploads named

def test_competition_squads_carry_playing_time_and_clubs_their_uploads(client, cm):
    d = ok(client, f"/api/competitions/{GER}")
    sm = cm.metrics[GER]
    for c in d["clubs"]:
        assert c["uploaded_matches"] == d["sample"]["club_matches"].get(c["club_id"], 0)
        for p in c["squad"]:
            ps = sm.players.get(p["global_id"])
            assert p["appearances"] == (ps.appearances if ps else 0) and p["played"] == bool(ps and ps.appearances)
            assert p["qualified"] == bool(ps and ps.minutes >= sm.min_minutes)
    assert d["player_uploads"] == [] and d["player_uploads_note"]
    cat = ok(client, "/api/catalogue")
    assert len(cat["clubs"]) == 66 and cat["count_metrics"] == sorted(COUNT_METRICS)
    assert {c["competition_id"] for c in cat["clubs"]} == {c["competition_id"] for c in cat["competitions"]}


# ---------------------------------------------------------------------------- B9: tier lists, fits, minutes and name

def test_tier_lists_min_percentile_and_list_sorts(client):
    below = ok(client, "/api/competitions", tier="amateur,college,academy", gender="men")
    assert {c["tier"] for c in below["competitions"]} == {"amateur", "college", "academy"}
    assert client.get("/api/competitions", params={"tier": "amateur,pro"}).status_code == 422
    r = ok(client, "/api/catalogue/rank", metric="goals", position="FW", tier="semi_pro", age_group="senior",
           gender="men", min_percentile=90, limit=200)
    assert r["ranked"] and all(p["percentile"] >= 90 for p in r["players"]) and r["players"][0]["global_id"] == STAR
    fits = ok(client, "/api/catalogue/rank", metric="interceptions", position="DF", tier="amateur,college,academy",
              gender="men", rank_by="pool", min_percentile=90, limit=200)
    assert all(p["percentile"] >= 90 and p["tier"] != "semi_pro" for p in fits["players"])
    scr = ok(client, "/api/catalogue/players", metrics="goals", sort="goals", position="FW", tier="semi_pro",
             min_percentile=95, limit=200)
    assert scr["total"] and all(p["values"]["goals"]["percentile"] >= 95 for p in scr["players"])
    mins = ok(client, "/api/catalogue/players", sort="minutes", min_minutes=0, limit=200)
    assert mins["rank_by"] == "value" and [b["by"] for b in mins["boards"]] == ["level"] * len(mins["boards"])
    for b in mins["boards"]:
        part = [p["minutes"] for p in mins["players"][b["offset"]:b["offset"] + b["size"]]]
        assert part == sorted(part, reverse=True)
    eng = ok(client, "/api/catalogue/players", sort="minutes", competition=ENGLAND_ID, min_minutes=0, q="toure", limit=5)
    assert eng["players"][0]["global_id"] == STAR and eng["players"][0]["minutes"] == 274.3
    names = ok(client, "/api/catalogue/players", sort="name", min_minutes=0, limit=50)
    assert names["rank_by"] == "name" and names["boards"] is None
    assert [p["name"] for p in names["players"]] == sorted(p["name"] for p in names["players"])
    assert client.get("/api/catalogue/players", params={"sort": "minutes", "min_percentile": 50}).status_code == 422
    assert client.get("/api/catalogue/players", params={"sort": "charisma"}).status_code == 422


# ---------------------------------------------------------------------------- B10, B11, B12

def test_compare_marks_the_best_by_the_one_rule(client):
    same = ok(client, "/api/catalogue/compare", ids=f"{STAR},pl_ash_09", metrics="np_goals,fouls")
    assert same["best"]["np_goals"] == [STAR] and same["best_rule"]["np_goals"]["by"] == "value"
    fouls = {p["global_id"]: p["values"]["fouls"]["value"] for p in same["players"]}
    assert same["best"]["fouls"] == [g for g, v in fouls.items() if v == min(fouls.values())]   # fewer is better
    cross = ok(client, "/api/catalogue/compare", ids=f"{STAR},{CRUZ}", metrics="np_goals")
    assert cross["best_rule"]["np_goals"]["by"] == "percentile"
    pct = {p["global_id"]: p["values"]["np_goals"]["percentile"] for p in cross["players"]}
    assert cross["best"]["np_goals"] == [g for g, v in pct.items() if v == max(v for v in pct.values() if v is not None)]
    mixed = ok(client, "/api/catalogue/compare", ids=f"{STAR},pl_sot_04", metrics="np_goals")   # a U19 defender
    assert {p["position"] for p in mixed["players"]} == {"FW", "DF"} and len({p["tier"] for p in mixed["players"]}) == 2
    assert mixed["best"]["np_goals"] == [] and mixed["best_rule"]["np_goals"]["by"] is None
    zero = ok(client, "/api/catalogue/compare", ids=f"{STAR},pl_ash_09", metrics="penalties_won")
    nobody = [p["global_id"] for p in zero["players"] if p["values"]["penalties_won"]["none_yet"]]
    assert not set(nobody) & set(zero["best"]["penalties_won"])         # never a none-yet row
    assert zero["best_rules"]


def test_similar_players_in_plain_words_and_every_row_links(client):
    sim = ok(client, f"/api/players/{CRUZ}/similar", competition="co_esp_am_men", scope="level")
    assert sim["similar"] and all(r["profile_url"] == f"/players/{r['global_id']}" for r in sim["similar"])
    for r in sim["similar"]:
        assert len(r["shared_strengths_words"]) == len(r["shared_strengths"])
    words = [w for r in sim["similar"] for w in r["shared_strengths_words"]]
    assert all(w == w[:1].lower() + w[1:] for w in words)
    from regista.catalogue.metrics import strength_words

    assert strength_words("npxg") == "getting good scoring chances" and strength_words("tackles_won") == "tackles won"
    assert "shared_strengths_words" not in json.dumps(ok(client, f"/api/players/{STAR}/similar"))   # the league default
    rows = ok(client, "/api/catalogue/players", country="Spain", limit=200)["players"]
    assert all(r["profile_url"] == f"/players/{r['global_id']}" for r in rows)
    cruz = [r for r in rows if r["global_id"] == CRUZ]
    assert sorted(x for r in cruz for x in r["also_in"]) == ["co_esp_am_men", "co_esp_u19"]


def test_no_hidden_rating_scale_or_seed_in_the_ported_payloads(client):
    for path, params in [(f"/api/catalogue/players/{CRUZ}", {"include": "profile"}),
                         (f"/api/catalogue/players/{STAR}", {"include": "profile", "scope": "all"}),
                         (f"/api/competitions/{GER}", {}), ("/api/catalogue", {}),
                         ("/api/catalogue/compare", {"ids": f"{STAR},{CRUZ}"}),
                         ("/api/catalogue/rank", {"metric": "goals", "tier": "amateur,academy"}),
                         ("/api/catalogue/players", {"sort": "minutes", "min_minutes": 0, "limit": 200}),
                         ("/api/catalogue/directory", {})]:
        assert not _hidden(ok(client, path, **params)), path


# ---------------------------------------------------------------------------- B15: uploads from catalogue clubs

@pytest.fixture()
def writer(client, monkeypatch, tmp_path):
    monkeypatch.setattr(player_api, "PLAYER_MATCHES", tmp_path / "player_matches")
    monkeypatch.setattr(player_api, "_checked", {})
    monkeypatch.setattr(player_api, "_listed", {"t": 0.0, "rows": []})
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", ADMIN)
    return client


def _post(c, **fields):
    data = {"global_id": NGA_GID, "opponent_club_id": NGA_OPP, "side": "home", "competition_id": NGA,
            "date": "2026-10-17", "camera": "phone", "consent": "yes", **fields}
    data = {k: v for k, v in data.items() if v is not None}
    return c.post("/api/player/uploads", data=data, files={"video": ("match.mp4", MP4, "video/mp4")},
                  headers={"X-Regista-Token": ADMIN})


def test_a_catalogue_club_upload_is_stored_with_its_competition(writer):
    r = _post(writer)
    assert r.status_code == 201, r.text
    up = r.json()["upload"]
    assert (up["competition_id"], up["camera"], up["date_played"], up["consent"]) == (NGA, "phone", "2026-10-17", True)
    assert up["player"]["global_id"] == NGA_GID and up["opponent"]["club_id"] == NGA_OPP
    assert up["competition"]["name"] == "Ogun Riverside Amateur League" and up["uploader_type"] == "player"
    rec = player_api.store().get_record(up["upload_id"])
    assert rec.competition_id == NGA and rec.club_id == NGA_CLUB
    old = writer.post("/api/player/uploads", data={"global_id": STAR, "opponent_club_id": "cl_calder", "side": "home"},
                      files={"video": ("m.mp4", MP4, "video/mp4")}, headers={"X-Regista-Token": ADMIN})
    assert old.status_code == 201 and old.json()["upload"]["competition_id"] is None    # the league form keeps working


@pytest.mark.parametrize("fields, words", [
    ({"date": None}, "when the match was played"), ({"camera": None}, "filmed on"), ({"consent": None}, "agreed"),
    ({"consent": "no"}, "agreed"), ({"camera": "satellite"}, "camera is one of"), ({"date": "17/10/2026"}, "YYYY-MM-DD"),
    ({"date": "2026-08-01"}, "season started"), ({"date": "2099-01-01"}, "future"),
    ({"opponent_club_id": NGA_CLUB}, "cannot play itself"), ({"opponent_club_id": "cl_brookfield"}, "not a club of"),
    ({"global_id": STAR}, "no player"), ({"competition_id": "co_nowhere"}, "no competition"),
    ({"competition_id": "England"}, "co_"),
])
def test_a_catalogue_upload_refuses_in_plain_words(writer, fields, words):
    r = _post(writer, **fields)
    assert r.status_code == 422 and words in r.json()["detail"], (fields, r.text)


def test_old_upload_records_load_with_the_new_defaults():
    from regista.player.store import UploadRecord

    rec = UploadRecord.from_json({"upload_id": "up_old0000001", "global_id": STAR, "club_id": "cl_brookfield",
                                  "opponent_club_id": "cl_calder", "side": "home", "kit_number": 9, "unknown": 1})
    assert (rec.competition_id, rec.camera, rec.date_played, rec.uploader_type, rec.consent) == (None, None, None,
                                                                                                "player", False)


def test_the_roster_and_manifest_of_a_catalogue_upload_hold_no_hidden_key(tmp_path):
    from regista.player.film import roster_for
    from regista.player.store import UploadRecord
    from regista.player.worker import build_manifest, catalogue_labels

    roster = roster_for(NGA_CLUB, NGA_OPP, "home", LEAGUE, competition_id=NGA, date="2026-10-17")
    assert roster["competition"] == "Ogun Riverside Amateur League" and roster["date"] == "2026-10-17"
    assert {p.get("global_player_id") for p in roster["players"]} >= {NGA_GID} and not _hidden(roster)
    rec = UploadRecord(upload_id="up_nga0000001", global_id=NGA_GID, club_id=NGA_CLUB, opponent_club_id=NGA_OPP,
                       side="home", kit_number=9, competition_id=NGA, camera="phone", date_played="2026-10-17", consent=True)
    labels = catalogue_labels(rec)
    assert labels["competition_id"] == NGA and labels["tier"] == "amateur" and labels["counted"] is False
    assert labels["uploader"] == {"type": "player", "global_id": NGA_GID, "club_id": NGA_CLUB}
    (tmp_path / "events.jsonl").write_text("{}\n")
    (tmp_path / "tracks.jsonl").write_text("{}\n")
    player = next(p for p in roster["players"] if p.get("global_player_id") == NGA_GID)

    class Info:
        fps, width, height, duration_s = 10.0, 640, 360, 30.0

    m = build_manifest(tmp_path, rec, roster, player, {}, Info(), {"t_home": 0, "t_away": 0}, [], [], [], [], seconds=1.0)
    assert m["competition_id"] == NGA and m["camera"] == "phone" and m["date"] == "2026-10-17"
    assert m["title"].endswith("Adire Stars FC v Riverbank Warriors FC") and not _hidden(m)
    league = roster_for("cl_brookfield", "cl_calder", "home", LEAGUE)
    assert league["competition"] == "Friendly (filmed by a player)" and catalogue_labels(
        UploadRecord("up_x00000001", STAR, "cl_brookfield", "cl_calder", "home", 9)) == {}


def test_a_done_catalogue_upload_is_named_never_counted(writer, monkeypatch, tmp_path):
    """A finished upload of a Nigerian club: named on its competition page and in the player's catalogue rows, counted
    nowhere (the league's season skips a player who is not in the league; the catalogue counts its fixtures only)."""
    from regista.player.film import friendly_kwargs, competition_for
    from regista.player.store import UploadRecord, match_id_for
    from regista.schema import write_jsonl
    from regista.season import profiles
    from regista.synth.generator import generate

    before = ok(writer, f"/api/catalogue/players/{NGA_GID}")
    s = player_api.store()
    rec = UploadRecord(upload_id="up_nga0000002", global_id=NGA_GID, club_id=NGA_CLUB, opponent_club_id=NGA_OPP,
                       side="home", kit_number=9, competition_id=NGA, camera="drone", date_played="2026-10-17",
                       consent=True, status="done")
    mid = match_id_for(rec.upload_id)
    kw = friendly_kwargs(competition_for(NGA), NGA_CLUB, NGA_OPP, "home", seed=4101, minutes=1.0, date="2026-10-17",
                         competition="Ogun Riverside Amateur League")
    kw["match_id"] = mid
    result = generate(**kw)
    folder = tmp_path / "work" / mid
    write_jsonl(folder / "events.jsonl", result.stream)
    write_jsonl(folder / "tracks.jsonl", result.tracks)
    (folder / "manifest.json").write_text(json.dumps({"match_id": mid, "title": "Ade's match: Adire Stars FC v Riverbank "
                                                      "Warriors FC", "competition_id": NGA, "date": "2026-10-17"}))
    s.put_match(mid, folder)
    rec.match_id = mid
    s.put_record(rec)
    monkeypatch.setattr(player_api, "_listed", {"t": 0.0, "rows": []})
    profiles.invalidate()
    try:
        page = ok(writer, f"/api/competitions/{NGA}")
        assert [u["match_id"] for u in page["player_uploads"]] == [mid]
        u = page["player_uploads"][0]
        assert u["counted"] is False and u["camera"] == "drone" and u["date"] == "2026-10-17" and u["name"]
        assert u["clip_view"].startswith(f"/?match={mid}") and u["opponent"] == "Riverbank Warriors FC"
        assert mid not in [m["match_id"] for m in page["matches"]]
        after = ok(writer, f"/api/catalogue/players/{NGA_GID}")
        row = next(r for r in after["rows"] if r["competition_id"] == NGA)
        assert [x["match_id"] for x in row["not_counted"]] == [mid] and "not counted here" in row["basis"]
        assert row["sample"] == next(r for r in before["rows"] if r["competition_id"] == NGA)["sample"]
        assert ok(writer, f"/api/competitions/{ENGLAND_ID}")["player_uploads"] == []
        assert player_api.uploaded_matches(force=True)[0]["competition_id"] == NGA
        assert ok(writer, "/api/players", limit=200)["total"] == ok(writer, "/api/players", limit=200)["total"]
        assert writer.get(f"/api/players/{NGA_GID}").status_code == 404      # never in the league's season
    finally:
        profiles.invalidate()


# ---------------------------------------------------------------------------- B14: the Scout agent on the catalogue

PLACE_CASES = [  # the sandbox's checks for terminal-place.js (tools/test_terminal_place.js), on the Python port
    ("U19 midfielders in Spain", {"where": {"country": "Spain", "age_group": "U19"}, "rest": "midfielders"}),
    ("best dribblers in academy", {"where": {"tier": "academy"}, "rest": "best dribblers"}),
    ("women forwards", {"where": {"gender": "women"}, "rest": "forwards"}),
    ("players in Nigeria", {"where": {"country": "Nigeria"}, "rest": "players"}),
    ("my level forwards", {"where": {"tier": "semi_pro", "age_group": "senior", "gender": "men"}, "reset": "mine",
                           "rest": "forwards"}),
    ("rank forwards non-penalty goals across the whole catalogue", {"reset": "all", "rest": "rank forwards non-penalty goals"}),
    ("rank forwards npxg women across the whole catalogue", {"where": {"gender": "women"}, "reset": "all",
                                                             "rest": "rank forwards npxg"}),
    ("under 17 midfielders in ghana", {"where": {"country": "Ghana", "age_group": "U17"}, "rest": "midfielders"}),
    ("u-18 keepers", {"where": {"age_group": "U18"}, "rest": "keepers"}),
    ("college women keepers", {"where": {"tier": "college", "age_group": "college", "gender": "women"}, "rest": "keepers"}),
    ("semi pro women", {"where": {"tier": "semi_pro", "gender": "women"}, "rest": ""}),
    ("best finishers in women's football", {"where": {"gender": "women"}, "rest": "best finishers"}),
    ("goals in the Regista League", {"where": {"competition": ENGLAND_ID}, "rest": "goals"}),
    ("Weserland strikers", {"where": {"competition": GER}, "rest": "strikers"}),
    ("amateur players in the united states", {"where": {"country": "USA", "tier": "amateur"}, "rest": "players"}),
    ("defenders at academy level", {"where": {"tier": "academy"}, "rest": "defenders"}),
    ("U21 forwards", {"unknown": ["U21"], "rest": "forwards"}),
    ("everywhere", {"reset": "all", "rest": ""}),
    ("best young defenders in Ghana", {"where": {"country": "Ghana", "tier": "academy"}, "rest": "best defenders"}),
    ("young players", {"where": {"tier": "academy"}, "rest": "players"}),
    ("youngsters in Spain", {"where": {"country": "Spain", "tier": "academy"}, "rest": ""}),
    ("young semi-pro forwards", {"where": {"tier": "semi_pro"}, "rest": "forwards"}),
    ("Ashley Young", {"found": False, "rest": "ashley young"}),
    *[(q, {"found": False, "rest": None}) for q in
      ["Femi Toure", "goals", "rank forwards non-penalty xG", "compare Femi Toure and Amari Ustinov", "team Calder Town",
       "best finishers", "who has the most assists", "best finishers at Brookfield", "top scorers", "who scores the most"]],
]


@pytest.mark.parametrize("q, want", PLACE_CASES)
def test_the_scout_agents_place_words_read_as_the_terminals(cm, q, want):
    from regista.catalogue.place import norm, parse
    from regista.catalogue.scout import place_vocab

    r = parse(q, place_vocab(cm))
    assert r["where"] == want.get("where", {}) and r["reset"] == want.get("reset")
    assert r["unknown"] == want.get("unknown", []) and r["found"] == want.get("found", True)
    assert r["rest"] == (norm(q) if want["rest"] is None else want["rest"])


def test_competition_words_never_collide_with_a_name(cm):
    from regista.catalogue.place import norm
    from regista.catalogue.scout import place_vocab

    names = {w for es in cm.people.values() for w in norm(es[0][1]["name"]).split(" ")}
    v = place_vocab(cm)
    assert v["words"] and not set(v["words"]) & names


@pytest.mark.parametrize("q, args", [
    ("Who are the best U19 dribblers up front?", {"age_group": "U19", "position": "FW", "sort": "take_ons_won"}),
    ("Find me women forwards who score", {"gender": "women", "position": "FW", "sort": "goals"}),
    ("Which amateur midfielders create the most chances?", {"tier": "amateur", "position": "MF", "sort": "key_passes"}),
    ("Who are the best U19 forwards?", {"age_group": "U19", "position": "FW", "sort": "np_goals"}),
])
def test_the_rules_engine_on_the_catalogue_gives_the_tools_rows(client, cm, q, args):
    from regista import mcp_server

    r = client.post("/api/scout/ask", json={"q": q, "engine": "rules", "where": "catalogue"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["where"] == "catalogue" and d["answered_by"] == "rules"
    assert {k: v for k, v in d["query"]["args"].items() if v is not None and k not in ("order", "limit")} == args
    tool = mcp_server.search_catalogue_players(**args, limit=d["query"]["limit"])
    assert [c["global_id"] for c in d["players"]] == [p["global_id"] for p in tool["players"]]
    top = d["players"][0]
    assert top["stat"]["pool"]["words"] and top["profile_url"] == f"/players/{top['global_id']}" and top["competition"]
    assert top["name"] in d["reply"] and "percentile among" in d["reply"] and "the catalogue" in d["understood"]
    assert not _hidden(d)


def test_the_catalogue_answer_names_a_player_and_my_level(client):
    d = client.post("/api/scout/ask", json={"q": "Sergio Cruz", "engine": "rules", "where": "catalogue"}).json()
    assert d["query"]["mode"] == "player" and d["players"][0]["global_id"] == CRUZ
    mine = client.post("/api/scout/ask", json={"q": "most interceptions at my level", "engine": "rules",
                                               "where": "catalogue"}).json()
    assert mine["query"]["where"] == {"tier": "semi_pro", "age_group": "senior", "gender": "men"}
    assert {c["tier"] for c in mine["players"]} == {"semi_pro"} and mine["query"]["sort"] == "interceptions"


def test_where_league_is_the_league_answer(client):
    base = client.post("/api/scout/ask", json={"q": "who scored the most goals", "engine": "rules"}).json()
    league = client.post("/api/scout/ask", json={"q": "who scored the most goals", "engine": "rules",
                                                 "where": "league"}).json()
    drop = lambda d: {k: v for k, v in d.items() if k != "trace"}  # noqa: E731 - the trace's step times differ
    assert drop(base) == drop(league) and "where" not in base
    assert client.post("/api/scout/ask", json={"q": "x", "engine": "rules", "where": "mars"}).status_code == 422


def test_the_foundry_scout_agent_holds_the_catalogue_tools_and_its_cards_are_its_calls(client, monkeypatch):
    from regista import season_api
    from regista.cloud.foundry import SCOUT_INSTRUCTIONS, SCOUT_TOOLS

    assert {"list_competitions", "search_catalogue_players", "get_catalogue_player"} <= set(SCOUT_TOOLS)
    assert not {"render_clip", "cosmos_database_container_item_query", "cosmos_list"} & set(SCOUT_TOOLS)
    assert "none yet" in SCOUT_INSTRUCTIONS and "own level" in SCOUT_INSTRUCTIONS
    from regista import mcp_server

    args = {"tier": "amateur", "position": "MF", "sort": "key_passes", "limit": 3}
    top = mcp_server.search_catalogue_players(**args)["players"][0]
    seen = {}

    def fake(s, q, rules):
        seen["rules"] = rules
        text = f"{top['name']} creates the most chances among amateur midfielders: {top['stat']['value']} per 90."
        return text, [("search_catalogue_players", args)], "foundry:stand-in"

    monkeypatch.setattr(season_api, "_scout_foundry", fake)
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(10, 100, 100, 100, 2))
    d = client.post("/api/scout/ask", json={"q": "Which amateur midfielders create the most chances?",
                                            "where": "catalogue"}).json()
    assert d["answered_by"] == "foundry:stand-in" and seen["rules"]["where"] == "catalogue"
    assert [c["global_id"] for c in d["players"]] == [p["global_id"] for p in mcp_server.search_catalogue_players(**args)["players"]]
    assert d["checked"] == {"tool_calls": 1, "numbers_not_in_tool_results": []}
    assert d["understood"].startswith("Foundry called search_catalogue_players(")

    def made_up(s, q, rules):
        return f"{top['name']} makes 99.9 key passes per 90.", [("search_catalogue_players", args)], "foundry:stand-in"

    monkeypatch.setattr(season_api, "_scout_foundry", made_up)
    d = client.post("/api/scout/ask", json={"q": "amateur midfielders chances", "where": "catalogue"}).json()
    assert d["checked"]["numbers_not_in_tool_results"] == ["99.9"]


def test_fewest_minutes_answers_count_every_player(client):
    """Minutes need no percentile, so a minutes answer lists every player, not only those with enough minutes for one
    (review B, pass 3): the fewest at my level is the player with the fewest minutes of all, and every card is ranked."""
    r = client.post("/api/scout/ask", json={"q": "who played the fewest minutes at my level", "engine": "rules",
                                            "where": "catalogue"})
    assert r.status_code == 200
    body = r.json()
    cards = body["players"]
    assert cards and all(c.get("ranked") is not False for c in cards)
    everyone = [p for p in ok(client, "/api/catalogue/players", tier="semi_pro", age_group="senior", gender="men",
                              min_minutes=0, sort="minutes", order="asc", limit=5)["players"]]
    assert cards[0]["minutes"] == everyone[0]["minutes"]
    assert " 1 minutes" not in body["reply"] and " 1 appearances" not in body["reply"]
