"""The Regista League and player profiles: the definition, regenerated matches, aggregates, and the Scout view's API."""

import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.schema import iter_jsonl, validate_match_dir
from regista.season.build import ensure_tracks, fingerprint, is_current, materialise
from regista.season.league import generate_kwargs, new_league, people, save_league
from regista.season.profiles import STATS, Season
from regista.synth.generator import generate

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def league():
    return new_league(2026)


@pytest.fixture(scope="module")
def small(league):
    """The real league's clubs with only its first four fixtures (two rounds would be 6): quick to build."""
    return {**league, "fixtures": league["fixtures"][:4]}


@pytest.fixture(scope="module")
def built(small, tmp_path_factory):
    root = tmp_path_factory.mktemp("season")
    return small, root, Season.build(small, root)


def test_the_committed_league_is_what_new_league_writes(league):
    committed = json.loads((ROOT / "data" / "season" / "league.json").read_text())
    assert committed == json.loads(json.dumps(league))


def test_double_round_robin_with_fixed_squads(league):
    fx = league["fixtures"]
    assert len(league["clubs"]) == 6 and len(fx) == 30 and {f["round"] for f in fx} == set(range(1, 11))
    games = Counter(c for f in fx for c in (f["home"], f["away"]))
    homes = Counter(f["home"] for f in fx)
    assert set(games.values()) == {10} and set(homes.values()) == {5}
    pairs = Counter(frozenset((f["home"], f["away"])) for f in fx)
    assert len(pairs) == 15 and set(pairs.values()) == {2}
    assert len({(f["home"], f["away"]) for f in fx}) == 30  # each meeting once at each ground
    for r in range(1, 11):
        in_round = [c for f in fx if f["round"] == r for c in (f["home"], f["away"])]
        assert sorted(in_round) == sorted(c["club_id"] for c in league["clubs"])
    everyone = people(league)
    assert len(everyone) == 6 * 18 and len({p["name"] for p in everyone.values()}) == 6 * 18
    assert len({f["seed"] for f in fx}) == 30 and len({f["match_id"] for f in fx}) == 30


def test_a_season_match_carries_global_ids_and_validates(built):
    small, root, _ = built
    fx = small["fixtures"][0]
    d = materialise(small, fx, root)
    assert validate_match_dir(d) == {name: [] for name in validate_match_dir(d)}
    header = next(iter_jsonl(d / "events.jsonl"))
    assert {t["club_id"] for t in header["teams"]} == {fx["home"], fx["away"]}
    assert all(p["global_player_id"].startswith("pl_") for p in header["players"])
    assert header["competition"] == "Regista League" and header["date"] == fx["date"] and len(header["periods"]) == 2
    manifest = json.loads((d / "manifest.json").read_text())
    assert manifest["collection"] == "season" and manifest["fingerprint"] == fingerprint(small, fx)
    assert not (d / "tracks.jsonl").exists()  # tracks only when video needs them


def test_rebuilding_is_deterministic_and_tracks_match_a_fresh_generate(built):
    small, root, _ = built
    fx = small["fixtures"][1]
    d = materialise(small, fx, root)
    first = (d / "events.jsonl").read_bytes()
    assert is_current(small, fx, root)
    ensure_tracks(small, fx, root)
    fresh = generate(**generate_kwargs(small, fx))
    assert list(iter_jsonl(d / "tracks.jsonl")) == json.loads(json.dumps(fresh.tracks))
    (d / "manifest.json").write_text(json.dumps({"fingerprint": "stale"}))
    materialise(small, fx, root)
    assert (d / "events.jsonl").read_bytes() == first


def test_profile_counts_are_the_events(built):
    small, root, season = built
    gid = "pl_" + small["clubs"][0]["short_name"].lower() + "_09"
    p = season.player(gid)
    assert p["appearances"] == sum(gid.split("_")[1] in f["match_id"] for f in small["fixtures"])
    want = Counter()
    for fx in small["fixtures"]:
        stream = list(iter_jsonl(root / fx["match_id"] / "events.jsonl"))
        local = {q["player_id"]: q["global_player_id"] for q in stream[0]["players"]}
        for e in stream:
            if e["type"] == "event" and local.get(e.get("player_id")) == gid:
                for key, (_label, test) in STATS.items():
                    want[key] += bool(test(e))
    assert {k: p["counts"][k] for k in STATS} == {k: want[k] for k in STATS}
    assert p["per90"]["passes"] == round(p["counts"]["passes"] * 90 / p["minutes"], 2)
    assert sum(map(sum, p["grid"])) > 0


def test_every_stat_links_to_its_events_and_clips(built):
    small, root, season = built
    p = max(season.profiles.values(), key=lambda q: q["counts"]["passes"])
    for key, ev in p["evidence"].items():
        assert len(ev) == min(p["counts"][key], 60)
    e = p["evidence"]["passes"][0]
    events = {r["id"]: r for r in iter_jsonl(root / e["match_id"] / "events.jsonl")}
    assert events[e["event_id"]]["event_type"] == "pass"
    clips = {(f.name, r["id"]): r for f in root.iterdir() if (f / "clips.jsonl").exists()
             for r in iter_jsonl(f / "clips.jsonl") if r["type"] == "clip"}  # clip ids repeat across matches
    linked = [x for x in p["evidence"]["passes"] if x["clip_id"]]
    assert linked and all(x["event_id"] in clips[(x["match_id"], x["clip_id"])]["event_ids"] for x in linked)
    assert all(clips[(x["match_id"], x["clip_id"])]["player_id"] == events_player(root, x) for x in linked[:10])
    ms = p["moments"]
    assert ms and [m["watchability"] for m in ms] == sorted((m["watchability"] for m in ms), reverse=True)


def test_players_filters_and_sorts(built):
    _small, _root, season = built
    fw = season.players(position="FW", sort="shots")
    assert fw and all(c["position"] == "FW" for c in fw)
    assert [c["headline"]["shots"]["per90"] for c in fw] == sorted((c["headline"]["shots"]["per90"] for c in fw), reverse=True)
    with pytest.raises(ValueError):
        season.players(sort="charisma")


# ---------------------------------------------------------------------------- the API

@pytest.fixture
def client(built, monkeypatch, tmp_path):
    from regista import api

    small, root, _ = built
    league_path = save_league(small, tmp_path / "league.json")
    monkeypatch.setattr(api, "SEASON_LEAGUE", league_path)
    monkeypatch.setattr(api, "SEASON_ROOT", root)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    return TestClient(api.app)


def test_season_and_players_endpoints(client, built):
    small, _root, _ = built
    s = client.get("/api/season").json()
    assert s["league"] == "Regista League" and len(s["table"]) == 6 and sum(len(r["matches"]) for r in s["rounds"]) == 4
    assert {x["key"] for x in s["stats"]} >= {"goals", "take_ons_won", "pass_accuracy"}
    cards = client.get("/api/players", params={"position": "MF", "sort": "key_passes", "limit": 5}).json()["players"]
    assert 0 < len(cards) <= 5 and all(c["position"] == "MF" for c in cards)
    gid = cards[0]["global_id"]
    prof = client.get(f"/api/players/{gid}").json()
    assert prof["global_id"] == gid and prof["card"]["name"] == prof["name"] and len(prof["grid"]) == 8
    assert client.get("/api/players/pl_nobody_99").status_code == 404
    assert client.get("/api/players/NOT-AN-ID").status_code == 400
    assert client.get("/api/players", params={"sort": "charisma"}).status_code == 422
    other = cards[1]["global_id"]
    cmp = client.get("/api/compare", params={"ids": f"{gid},{other}"}).json()
    assert [p["card"]["global_id"] for p in cmp["players"]] == [gid, other]
    assert client.get("/api/compare", params={"ids": f"{gid},{gid}"}).status_code == 422


def test_season_lists_each_clubs_squad_from_the_league_file(client, built):
    # The dashboards' Team sections show a club's squad: /api/season carries it, read-only, exactly as league.json has it.
    small, _root, _ = built
    clubs = client.get("/api/season").json()["clubs"]
    assert [c["club_id"] for c in clubs] == [c["club_id"] for c in small["clubs"]]
    for got, want in zip(clubs, small["clubs"]):
        assert got["squad"] == [{k: p[k] for k in ("global_id", "name", "kit_number", "position", "starter")} for p in want["squad"]]
        assert len(got["squad"]) == 18 and all(p["global_id"].startswith("pl_") for p in got["squad"])
        assert set(got) == {"club_id", "name", "short_name", "kit", "ground", "squad"}


def test_a_season_match_opens_like_any_match(client, built):
    small, _root, _ = built
    mid = small["fixtures"][2]["match_id"]
    clips = client.get(f"/api/matches/{mid}/clips").json()
    assert clips and all(c["match_id"] == mid for c in clips)
    assert client.get(f"/api/matches/{mid}").status_code == 200
    assert client.get("/api/matches/rl_r99_nob_ody/clips").status_code == 404
    gid = clips[0]["label"]["player_id"]
    moments = client.get(f"/api/players/pl_{small['clubs'][0]['short_name'].lower()}_09/moments", params={"limit": 3}).json()
    assert len(moments["moments"]) <= 3 and all(m["video_url"].startswith("/api/matches/rl_") for m in moments["moments"])
    assert gid  # labels carry the per-match player id; profiles map it to the global one


def events_player(root, x):
    return next(r["player_id"] for r in iter_jsonl(root / x["match_id"] / "events.jsonl") if r.get("id") == x["event_id"])


def test_a_profile_reel_joins_moments_from_different_matches(client, built):
    """Renders each clip first, then joins them: rendering inside the reel's own render slot used to deadlock."""
    small, _root, season = built
    p = next(q for q in season.profiles.values() if len({m["match_id"] for m in q["moments"][:4]}) >= 2)
    r = client.get(f"/api/players/{p['global_id']}/reel.mp4", params={"n": 4, "width": 640}, timeout=120)
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) > 10_000
    assert client.get("/api/players/pl_nobody_99/reel.mp4").status_code == 404
