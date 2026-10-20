"""What a judge sees on the live app: matches read back from Cosmos DB, the Foundry Librarian behind an open but
rate-limited endpoint with read-only public tools, and a health line naming what runs. Fakes only: no Azure."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fakes import FakeContainer
from regista.clips import derive_clips
from regista.cloud.config import CloudConfig
from regista.cloud.cosmos import ClipStore
from regista.cloud.foundry import FoundryLibrarianAgent, azure_mcp_args, azure_mcp_env, azure_mcp_tool
from regista.synth import generate

PLAYER = "t_home_09"
COSMOS_ONLY = "syn_9001"


def _library_store(local_header: dict) -> ClipStore:
    """A Cosmos library holding the local match and one match only Cosmos still has, with one current and one
    stale (pre-0.1.1 id) clip."""
    remote = {**local_header, "match_id": COSMOS_ONLY, "id": COSMOS_ONLY}
    current = {"type": "clip", "id": f"cl_{PLAYER}_000001", "match_id": COSMOS_ONLY, "player_id": PLAYER, "t": 10.0, "t_end": 15.0,
               "reason": "on_ball_main", "segment_ids": [], "event_ids": [], "possession_ids": []}
    stale = {**current, "id": "cl_000001"}
    label = {"type": "label", "id": f"lb_{PLAYER}_000001", "clip_id": current["id"], "match_id": COSMOS_ONLY, "player_id": PLAYER,
             "title": "Remote clip", "tags": ["on_ball_main"], "watchability": 0.5, "explanation": "Scored 0.50."}
    stale_label = {**label, "id": "lb_000001", "clip_id": "cl_000001", "title": "Stale clip"}
    matches = FakeContainer([{**local_header, "id": local_header["match_id"]}, remote])
    return ClipStore(matches, FakeContainer([current, stale]), FakeContainer([label, stale_label]), FakeContainer())


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    from regista import api

    root = tmp_path_factory.mktemp("data")
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = root / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    (d / "tracks.jsonl").write_text("\n".join(json.dumps(x) for x in r.tracks) + "\n")
    clips, labels = derive_clips(r.stream, PLAYER)
    (d / "clips.jsonl").write_text("\n".join(json.dumps(x) for x in clips + labels) + "\n")
    saved = (api.DATA_ROOT, api.CACHE_ROOT)
    api.DATA_ROOT, api.CACHE_ROOT = root, tmp_path_factory.mktemp("cache")
    with TestClient(api.app) as c:
        c.match_id = r.match["match_id"]
        c.header = r.match
        yield c
    api.DATA_ROOT, api.CACHE_ROOT = saved


@pytest.fixture
def library(live, monkeypatch):
    from regista import api

    store = _library_store(live.header)
    monkeypatch.setattr(api, "_feedback_store", lambda: store)
    monkeypatch.setattr(api, "_library_cache", {"t": None, "matches": {}})
    return store


@pytest.fixture
def limiter(monkeypatch):
    from regista import api

    lim = api.AskLimiter(per_visitor_per_min=2, per_visitor_per_hour=100, total_per_hour=100, total_per_day=100, concurrent=2)
    monkeypatch.setattr(api, "_ask_limiter", lim)
    return lim


# ---------------------------------------------------------------------------- health

def test_health_names_the_librarian_and_the_tools(live):
    h = live.get("/api/health").json()
    assert h["librarian"] == "rules"  # tests never configure Foundry
    assert isinstance(h["azure_mcp"], bool) and h["tracing"] is False


# ---------------------------------------------------------------------------- Cosmos DB library

def test_matches_only_cosmos_holds_are_listed_and_marked(live, library):
    rows = {m["match_id"]: m for m in live.get("/api/matches").json()}
    assert rows[live.match_id]["source"] == "local" and rows[live.match_id]["video"] is True and rows[live.match_id]["in_cosmos"] is True
    remote = rows[COSMOS_ONLY]
    assert remote["source"] == "cosmos" and remote["video"] is False and remote["teams"][0]["team_id"] == "t_home"


def test_cosmos_clips_skip_stale_ids_and_have_no_video(live, library):
    info = live.get(f"/api/matches/{COSMOS_ONLY}").json()
    assert info["source"] == "cosmos" and info["clip_count"] == 1 and info["players_with_clips"] == [PLAYER]
    clips = live.get(f"/api/matches/{COSMOS_ONLY}/clips", params={"player": PLAYER}).json()
    assert [c["id"] for c in clips] == [f"cl_{PLAYER}_000001"]
    assert clips[0]["label"]["title"] == "Remote clip" and clips[0]["video_url"] is None and clips[0]["source"] == "cosmos"
    # Reads stay inside the match's partition.
    assert all(q["partition_key"] == COSMOS_ONLY for q in library.clips.queries)


def test_cosmos_only_matches_explain_what_they_cannot_do(live, library):
    for path in (f"/api/matches/{COSMOS_ONLY}/search?q=goal", f"/api/matches/{COSMOS_ONLY}/clips/cl_{PLAYER}_000001.mp4",
                 f"/api/matches/{COSMOS_ONLY}/video.mp4", f"/api/matches/{COSMOS_ONLY}/review"):
        r = live.get(path)
        assert r.status_code == 409 and "Cosmos DB" in r.json()["detail"], path
    assert live.post(f"/api/matches/{COSMOS_ONLY}/ask", json={"q": "goals"}).status_code == 409
    r = live.post(f"/api/matches/{COSMOS_ONLY}/clips/cl_{PLAYER}_000001/verdict", json={"verdict": "keep"})
    assert r.status_code == 409 and library.annotations.items == {}
    assert live.get("/api/matches/syn_nope").status_code == 404


def test_store_reads_the_library_back():
    header = {"type": "match", "match_id": "m1", "id": "m1", "teams": []}
    store = ClipStore(FakeContainer([header]), FakeContainer([{"type": "clip", "id": "cl_000003", "match_id": "m1", "player_id": "p"}]),
                      FakeContainer(), FakeContainer())
    assert [m["match_id"] for m in store.list_matches()] == ["m1"]
    assert store.get_match("m1")["match_id"] == "m1" and store.get_match("m2") is None
    assert "_rid" not in store.list_matches()[0]
    assert store.clips_for("m1") == ([], {})  # the only clip is stale


# ---------------------------------------------------------------------------- the Foundry Librarian endpoint

def test_ask_without_foundry_answers_with_the_rules_and_says_so(live):
    r = live.post(f"/api/matches/{live.match_id}/ask", json={"q": "find me Castellanos doing a nutmeg"})
    assert r.status_code == 200
    out = r.json()
    assert out["answered_by"].startswith("rules") and "not configured" in out["answered_by"] and out["tools_used"] == []
    assert out["results"] and all(x["video_url"].endswith(".mp4") for x in out["results"])


def _fake_foundry(monkeypatch, answer="2 clips matched.", tools=("search_clips", "search_index_query")):
    from regista import api

    async def answerer(match_dir, query):
        return answer, list(tools)

    agent = FoundryLibrarianAgent(answerer=answerer, cloud=CloudConfig(foundry_project_endpoint="https://invalid.example", foundry_model="m"))
    monkeypatch.setattr(api, "_librarian_agent", lambda: agent)
    return agent


def test_ask_returns_the_foundry_answer_and_the_tools_it_called(live, monkeypatch, limiter):
    _fake_foundry(monkeypatch)
    out = live.post(f"/api/matches/{live.match_id}/ask", json={"q": "find me Castellanos doing a nutmeg"}).json()
    assert out["answer"] == "2 clips matched." and out["answered_by"] == "foundry:test"
    assert out["tools_used"] == ["search_clips", "search_index_query"]
    assert out["results"] and out["results"][0]["video_url"].startswith(f"/api/matches/{live.match_id}/clips/")
    assert limiter.in_flight == 0


def test_ask_is_rate_limited_per_visitor(live, monkeypatch, limiter):
    _fake_foundry(monkeypatch)
    url = f"/api/matches/{live.match_id}/ask"
    me, other = {"X-Forwarded-For": "1.1.1.1, 10.0.0.9"}, {"X-Forwarded-For": "10.0.0.8"}
    assert [live.post(url, json={"q": "goals"}, headers=me).status_code for _ in range(2)] == [200, 200]
    r = live.post(url, json={"q": "goals"}, headers=me)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and "per visitor" in r.json()["detail"]
    assert live.post(url, json={"q": "goals"}, headers=other).status_code == 200  # a different visitor is unaffected


@pytest.mark.parametrize("q", ["", "   ", "x" * 201])
def test_ask_rejects_empty_and_long_questions(live, q):
    assert live.post(f"/api/matches/{live.match_id}/ask", json={"q": q}).status_code == 422


def test_limiter_caps_everyone_and_questions_in_flight():
    from regista.api import AskLimiter

    lim = AskLimiter(per_visitor_per_min=10, per_visitor_per_hour=10, total_per_hour=3, total_per_day=100, concurrent=2)
    assert lim.acquire("a", now=0)[0] and lim.acquire("b", now=1)[0]
    ok, wait, which = lim.acquire("c", now=2)
    assert not ok and which == "busy"
    lim.release(); lim.release()
    assert lim.acquire("c", now=3)[0]
    lim.release()
    ok, wait, which = lim.acquire("d", now=4)
    assert not ok and which == "3 per 3600s" and wait == pytest.approx(3596.0)
    assert lim.acquire("d", now=3601)[0]  # the window slides


def test_the_public_librarian_holds_only_read_only_public_tools(monkeypatch):
    from regista import api

    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://invalid.example")
    monkeypatch.setenv("FOUNDRY_MODEL", "m")
    agent = api._librarian_agent()
    assert agent.config["regista_tools"] == ["search_clips", "search_library", "list_matches"]
    assert agent.config["azure_namespaces"] == ("search",)


def test_azure_mcp_arguments_follow_namespaces_and_configured_services(monkeypatch):
    both = CloudConfig(cosmos_endpoint="https://c.documents.azure.com:443/", search_endpoint="https://s.search.windows.net")
    args, allowed = azure_mcp_args(both, ("search",))
    assert "--read-only" in args and args.count("--namespace") == 1 and "cosmos" not in args and allowed == ["search_index_query"]
    args, allowed = azure_mcp_args(both)
    assert "cosmos_database_container_item_query" in allowed and "search_index_query" in allowed
    no_search = CloudConfig(cosmos_endpoint="https://c.documents.azure.com:443/")
    assert azure_mcp_args(no_search, ("search",))[1] == []
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/azmcp")
    assert azure_mcp_tool(no_search, ("search",)) is None  # nothing it may use is configured


def test_azmcp_runs_without_icu_and_without_secrets(monkeypatch):
    monkeypatch.setenv("REGISTA_COSMOS_KEY", "secret")
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=secret")
    env = azure_mcp_env()
    assert env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] == "1" and env["AZURE_MCP_COLLECT_TELEMETRY"] == "false"
    assert "REGISTA_COSMOS_KEY" not in env and "APPLICATIONINSIGHTS_CONNECTION_STRING" not in env
