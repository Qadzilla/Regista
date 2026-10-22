"""Claims ("that's me"): storage, access, profiles that count confirmed claims, and the Profile agent in the workflow."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from regista import api
from regista.agents.workflow import WorkflowPipeline, affected_profiles
from regista.schema import events_validator, iter_jsonl
from regista.season import claims
from regista.season.build import materialise
from regista.season.league import new_league, people, save_league
from regista.season.profiles import Season
from regista.synth.generator import generate

ADMIN, VIEW = "admin-key-for-tests", "view-key-for-tests"
GID, PID = "pl_bro_09", "t_home_09"


@pytest.fixture(scope="module")
def league():
    full = new_league(2026)
    return {**full, "fixtures": full["fixtures"][:2]}  # two matches: quick to build


@pytest.fixture(scope="module")
def season_root(tmp_path_factory, league):
    root = tmp_path_factory.mktemp("season")
    for fx in league["fixtures"]:
        materialise(league, fx, root)
    return root


@pytest.fixture(scope="module")
def upload_events():
    """A vision-layer-style match: per-match ids, no global ids."""
    r = generate(seed=7, minutes=2.0)
    return "\n".join(json.dumps(x) for x in r.stream) + "\n"


@pytest.fixture()
def app(tmp_path, monkeypatch, league, season_root):
    path = save_league(league, tmp_path / "league.json")
    monkeypatch.setattr(api, "SEASON_LEAGUE", path)
    monkeypatch.setattr(api, "SEASON_ROOT", season_root)
    monkeypatch.setattr(api, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    with TestClient(api.app) as c:
        yield c


def _upload(c, events, mid="up1"):
    r = c.post("/api/matches", params={"match_id": mid, "player": "t_home_10"}, headers={"X-Regista-Token": ADMIN},
               files={"events": ("events.jsonl", events, "application/x-ndjson")})
    assert r.status_code == 201, r.text
    return r.json()


def _header(events):
    return json.loads(events.splitlines()[0])


# ---------------------------------------------------------------------------- storage

def test_claims_are_schema_valid_annotations_and_the_newest_decision_wins(league, upload_events, tmp_path):
    path = tmp_path / "claims.jsonl"
    person = people(league)[GID]
    c = claims.new_claim(_header(upload_events), PID, person, claimant="Sam", note="I wore 9", path=path)
    assert claims.get(c["id"], path)["status"] == "pending"
    assert claims.CLAIM_ID_RE.match(c["id"])
    claims.decide(c["id"], "confirm", annotator="zaid", path=path)
    assert claims.get(c["id"], path)["status"] == "confirmed"
    claims.decide(c["id"], "reject", annotator="zaid", note="wrong team", path=path)
    folded = claims.get(c["id"], path)
    assert folded["status"] == "rejected" and [h["decision"] for h in folded["history"]] == ["confirmed", "rejected"]
    assert folded["player"]["kit_number"] == 9 and folded["person"]["name"] == person["name"] and folded["kit_matches"] is True
    rows = list(iter_jsonl(path))
    assert len(rows) == 3 and all(not events_validator().errors(r) for r in rows)
    assert {r["source"] for r in rows} == {"human"} and [r["verdict"] for r in rows] == ["correct", "confirm", "reject"]


def test_one_player_one_person_per_match(league, upload_events, tmp_path):
    path = tmp_path / "claims.jsonl"
    who, header = people(league), _header(upload_events)
    first = claims.new_claim(header, PID, who[GID], path=path)
    for pid, gid in ((PID, "pl_ash_09"), ("t_home_10", GID)):  # the same player again, or the same person again
        with pytest.raises(claims.ClaimError) as e:
            claims.new_claim(header, pid, who[gid], path=path)
        assert e.value.status == 409
    claims.decide(first["id"], "reject", path=path)
    second = claims.new_claim(header, PID, who["pl_ash_09"], path=path)  # a rejected claim no longer blocks
    assert claims.get(second["id"], path)["status"] == "pending"
    with pytest.raises(claims.ClaimError, match="not on match"):
        claims.new_claim(header, "t_home_99", who[GID], path=path)
    with pytest.raises(claims.ClaimError, match="already carries global player ids"):
        claims.new_claim({**header, "players": [{**p, "global_player_id": "pl_x"} for p in header["players"]]}, PID, who[GID], path=path)


# ---------------------------------------------------------------------------- profiles

def test_profiles_count_a_confirmed_claims_match_for_the_claimed_player_only(league, season_root, upload_events, tmp_path):
    d = tmp_path / "data" / "up1"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text(upload_events)
    base = Season.build(league, season_root)
    claimed = [{"match_id": "up1", "match_dir": str(d), "player_id": PID, "global_id": GID, "claim_id": "an_x"}]
    s = Season.build(league, season_root, claimed)
    before, after = base.player(GID), s.player(GID)
    assert after["appearances"] == before["appearances"] + 1
    assert after["minutes"] > before["minutes"]
    added = [m for m in after["matches"] if m["source"] == "claim"]
    assert added == [{**added[0], "match_id": "up1", "player_id": PID, "claim_id": "an_x"}]
    assert {m["source"] for m in after["matches"]} == {"league", "claim"}
    stream = list(iter_jsonl(d / "events.jsonl"))
    passes = sum(1 for r in stream if r["type"] == "event" and r.get("player_id") == PID and r["event_type"] == "pass")
    assert after["counts"]["passes"] == before["counts"]["passes"] + passes
    assert any(e["match_id"] == "up1" for e in after["evidence"]["passes"]) or not passes
    assert any(m["match_id"] == "up1" for m in after["moments"]), "the claimed player's moments are cut on the fly"
    # Nobody else changes, and the league table counts fixtures only.
    assert s.player("pl_ash_09")["counts"] == base.player("pl_ash_09")["counts"] and s.table == base.table


# ---------------------------------------------------------------------------- the API

@pytest.mark.parametrize("key, status", [(None, 401), ("wrong", 401), (VIEW, 403)])
def test_claim_writes_need_the_admin_key(app, key, status):
    headers = {"X-Regista-Token": key} if key else {}
    body = {"match_id": "up1", "player_id": PID, "global_id": GID}
    assert app.post("/api/claims", json=body, headers=headers).status_code == status
    assert app.post("/api/claims/an_20261022000000000000_abcdef/decision", json={"decision": "confirm"}, headers=headers).status_code == status


def test_claims_list_needs_a_studio_key(app):
    assert app.get("/api/claims").status_code == 401
    r = app.get("/api/claims", headers={"X-Regista-Token": VIEW})
    assert r.status_code == 200 and r.json()["counts"] == {"pending": 0, "confirmed": 0, "rejected": 0}


def test_add_a_match_claim_confirm_and_the_profile_follows(app, upload_events):
    admin, view = {"X-Regista-Token": ADMIN}, {"X-Regista-Token": VIEW}
    up = _upload(app, upload_events)
    assert up["profiles"]["affected"] == [], "an upload with per-match ids speaks for nobody yet"
    before = app.get(f"/api/players/{GID}").json()

    bad = app.post("/api/claims", json={"match_id": "rl_r01_ash_fai", "player_id": PID, "global_id": GID}, headers=admin)
    assert bad.status_code in (404, 422)  # league matches are never claimed
    assert app.post("/api/claims", json={"match_id": "up1", "player_id": PID, "global_id": "pl_zzz_01"}, headers=admin).status_code == 404
    r = app.post("/api/claims", json={"match_id": "up1", "player_id": PID, "global_id": GID, "claimant": "Sam"}, headers=admin)
    assert r.status_code == 201, r.text
    claim = r.json()["claim"]
    assert claim["status"] == "pending" and claim["links"]["profile"] == f"/players/{GID}"
    assert app.post("/api/claims", json={"match_id": "up1", "player_id": PID, "global_id": GID}, headers=admin).status_code == 409
    assert app.get(f"/api/players/{GID}").json()["appearances"] == before["appearances"], "a pending claim does not count"
    listed = app.get("/api/claims", headers=view).json()
    assert listed["counts"]["pending"] == 1 and listed["claims"][0]["claim_id"] == claim["claim_id"]
    todo = app.get("/api/studio/overview", headers=view).json()["todo"]
    assert any(t["kind"] == "pending_claims" and t["match_id"] == "up1" for t in todo)

    r = app.post(f"/api/claims/{claim['claim_id']}/decision", json={"decision": "confirm"}, headers=admin)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["claim"]["status"] == "confirmed" and out["run"]["pipeline_ok"], out["run"]
    assert set(out["run"]["players"]) == {"t_home_10", PID}, "clips already cut stay; the claimed player's are added"
    assert [p["global_id"] for p in out["profiles"]["profiles"]] == [GID] and out["profiles"]["profiles"][0]["claimed_matches"] == ["up1"]
    trace = app.get("/api/studio/runs/up1", headers=view).json()
    row = next(a for a in trace["agents"] if a["agent"] == "profiles")
    assert row["status"] == "ok" and GID in row["note"] and claim["claim_id"] in row["note"]
    after = app.get(f"/api/players/{GID}").json()
    assert after["appearances"] == before["appearances"] + 1
    assert any(m["match_id"] == "up1" and m["source"] == "claim" for m in after["matches"])

    r = app.post(f"/api/claims/{claim['claim_id']}/decision", json={"decision": "reject", "note": "not him"}, headers=admin)
    assert r.status_code == 200 and r.json()["claim"]["status"] == "rejected" and r.json()["run"] is None
    assert app.get(f"/api/players/{GID}").json()["appearances"] == before["appearances"]


def test_claims_reach_cosmos_when_it_is_configured(app, upload_events, monkeypatch):
    from regista.cloud.cosmos import ClipStore
    from tests.fakes import FakeContainer

    db = ClipStore(FakeContainer(), FakeContainer(), FakeContainer(), FakeContainer())
    _upload(app, upload_events)
    monkeypatch.setattr(api, "_feedback_store", lambda: db)
    r = app.post("/api/claims", json={"match_id": "up1", "player_id": PID, "global_id": GID}, headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 201 and r.json()["stored_in_cosmos"] is True
    assert [a["context"]["kind"] for a in db.all_annotations()] == ["identity_claim"]
    claims.claims_path().unlink()  # a restarted replica: the claim comes back from Cosmos DB
    from regista import claims_api

    claims_api._last_sync["t"] = 0.0
    assert app.get("/api/claims", headers={"X-Regista-Token": VIEW}).json()["counts"]["pending"] == 1


# ---------------------------------------------------------------------------- the Profile agent in the workflow

def test_the_profile_agent_refreshes_league_players_and_records_them(league, season_root, tmp_path):
    asked = []

    def refresh(gids):
        asked.append(gids)
        return {"profiles": [{"global_id": g, "known": True, "appearances": 1, "minutes": 30.0, "claimed_matches": []} for g in gids]}

    fx = league["fixtures"][0]
    d = materialise(league, fx, tmp_path / "s")  # a league match: its team sheet carries global ids
    header = next(iter_jsonl(d / "events.jsonl"))
    pid = next(p["player_id"] for p in header["players"] if p["starter"] and p["kit_number"] == 9)
    wf = WorkflowPipeline(state_dir=tmp_path / "agents", feedback_dir=tmp_path / "fb", profile_refresh=refresh).run(
        {"match_dir": str(d), "player_ids": [pid], "queries": []})
    assert wf.ok, (wf.statuses, wf.dead_letters)
    order = [r["agent"] for r in wf.trace if r["status"] == "ok"]
    assert order.index("persist") < order.index("profiles") < order.index("librarian")
    row = next(r for r in wf.trace if r["agent"] == "profiles")
    gids = sorted(p["global_player_id"] for p in header["players"])
    assert asked == [[a["global_id"] for a in affected_profiles(str(d))]] and sorted(asked[0]) == gids
    assert row["records_in"] == {"global_ids": len(gids), "claims": 0} and row["records_out"] == {"profiles": len(gids)}
    assert sorted(row["profiles"]) == gids and "refreshed" in row["note"]
    assert wf.state["profiles_refreshed"]["affected"][0]["source"] == "global_id"


def test_the_profile_agent_passes_a_match_that_speaks_for_nobody(tmp_path, upload_events):
    d = tmp_path / "m"
    d.mkdir()
    (d / "events.jsonl").write_text(upload_events)
    called = []
    wf = WorkflowPipeline(state_dir=tmp_path / "agents", feedback_dir=tmp_path / "fb", profile_refresh=called.append).run(
        {"match_dir": str(d), "player_ids": [PID], "queries": []})
    assert wf.ok and wf.statuses["profiles"] == "ok" and not called
    assert "no global ids or confirmed claims" in next(r for r in wf.trace if r["agent"] == "profiles")["note"]


def test_a_failing_refresh_dead_letters_and_skips_the_librarian(league, tmp_path):
    def broken(_gids):
        raise RuntimeError("season unreadable")

    d = materialise(league, league["fixtures"][0], tmp_path / "s")
    header = next(iter_jsonl(d / "events.jsonl"))
    pid = next(p["player_id"] for p in header["players"] if p["starter"])
    wf = WorkflowPipeline(state_dir=tmp_path / "agents", feedback_dir=tmp_path / "fb", profile_refresh=broken).run(
        {"match_dir": str(d), "player_ids": [pid], "queries": []})
    assert not wf.ok and wf.statuses["profiles"] == "failed" and wf.statuses["librarian"] == "skipped"
    assert wf.dead_letters[0]["agent"] == "profiles" and "season unreadable" in wf.dead_letters[0]["error"]


# ---------------------------------------------------------------------------- the profile page's Add a match

def test_add_match_script_fills_only_its_section_and_keeps_the_key_like_the_studio():
    from pathlib import Path

    js = (Path(api.STATIC) / "player" / "add-match.js").read_text()
    assert "document.getElementById('addMatch')" in js and "if (!root) return;" in js
    assert "getElementById(" not in js.replace("document.getElementById('addMatch')", "")  # touches no other element
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js  # API text goes in through textContent only
    assert "const KEY = 'regista-key';" in js and "sessionStorage" in js and "localStorage" not in js
    assert "'X-Regista-Token'" in js and "?token=" not in js
    assert "Video processing runs on the operator" in js and "machine, where the vision layer lives" in js
    for path in ("'/api/claims'", "/api/matches", "'/api/studio/jobs'", "kind: 'vision-run'"):
        assert path in js, path
    with TestClient(api.app) as c:
        r = c.get("/static/player/add-match.js")
        assert r.status_code == 200 and "javascript" in r.headers["content-type"]


def test_moments_from_a_claimed_match_sort_beside_league_moments():
    """A claimed match has no round; at equal watchability its moments once failed to sort (None < int)."""
    from regista.season.profiles import _empty, _finish

    a = _empty({"global_id": GID, "name": "x", "kit_number": 9, "position": "FW", "starter": True, "club_id": "c", "club": "C",
                "short_name": "C", "kit": {}})
    a["moments"] = [{"watchability": 0.7, "round": None, "match_id": "up1", "t": 5.0},
                    {"watchability": 0.7, "round": 2, "match_id": "rl_b", "t": 9.0},
                    {"watchability": 0.9, "round": None, "match_id": "up1", "t": 1.0}]
    order = [(m["match_id"], m["t"]) for m in _finish(a)["moments"]]
    assert order == [("up1", 1.0), ("rl_b", 9.0), ("up1", 5.0)]
