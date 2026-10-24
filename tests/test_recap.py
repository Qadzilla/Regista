"""The match recap (regista.recap, CLAUDE.md §2.7): every sentence cites a real clip or event, the numbers hold, the reel
plays, and the Foundry engine is checked, rate-limited, cached and replaced by the rules when it fails. No test reaches
Azure: the Foundry engine here is a stand-in that returns JSON."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import recap as rc
from regista.clips import derive_clips
from regista.schema import iter_jsonl

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "synthetic" / "sample"
LEAGUE = ROOT / "data" / "season" / "league.json"


@pytest.fixture(scope="module")
def league_match(tmp_path_factory):
    from regista.season.build import materialise
    from regista.season.league import load_league

    league = load_league(LEAGUE)
    # fixture 0 (rl_r01_ash_fai) has assisted goals (generator 0.7.0: 1-1, both goals assisted)
    return materialise(league, league["fixtures"][0], tmp_path_factory.mktemp("league"))


def _stream(d: Path) -> list[dict]:
    return list(iter_jsonl(d / "events.jsonl"))


def _served_clips(d: Path) -> dict[str, dict]:
    """Every clip id the app can serve for this match: persisted ones, and the clip rule's for every other player."""
    stream = _stream(d)
    out = {}
    persisted = {r["player_id"] for r in iter_jsonl(d / "clips.jsonl") if r["type"] == "clip"} if (d / "clips.jsonl").exists() else set()
    if persisted:
        out.update({r["id"]: r for r in iter_jsonl(d / "clips.jsonl") if r["type"] == "clip"})
    for p in stream[0]["players"]:
        if p["player_id"] not in persisted:
            out.update({c["id"]: c for c in derive_clips(stream, p["player_id"])[0]})
    return out


def assert_cited(r: dict, d: Path) -> None:
    """Every sentence cites at least one real clip or event; the reel and the clips map agree with the match."""
    events = {e["id"]: e for e in _stream(d) if e.get("type") == "event"}
    served = _served_clips(d)
    duration = _stream(d)[0]["video"]["duration_s"]
    assert r["headline"] and r["paragraphs"]
    for p in r["paragraphs"]:
        assert p["sentences"] and p["text"] == " ".join(s["text"] for s in p["sentences"])
        for s in p["sentences"]:
            assert s["cites"], f"uncited sentence: {s['text']}"
            for c in s["cites"]:
                assert c.get("clip_id") or c.get("event_id")
                if c.get("clip_id"):
                    clip = served[c["clip_id"]]
                    assert c["clip_id"] in r["clips"] and c["player_id"] == clip["player_id"]
                    if c.get("event_id"):
                        assert c["event_id"] in clip["event_ids"], "a cited clip shows the event it is cited for"
                if c.get("event_id"):
                    assert c["event_id"] in events and abs(events[c["event_id"]]["t"] - c["t"]) < 0.01
                assert 0 <= c["t"] <= duration
            text = s["text"]
            assert not rc.JARGON_RE.search(text), text
            assert not rc.numbers_not_in_facts(text, rc.prepare(d, r["player_id"]).facts), text
    assert 1 <= len(r["reel"]) <= rc.REEL_MAX and len(set(r["reel"])) == len(r["reel"])
    assert all(cid in served and cid in r["clips"] for cid in r["reel"])
    assert [r["clips"][c]["t"] for c in r["reel"]] == sorted(r["clips"][c]["t"] for c in r["reel"]), "the reel plays in match order"
    assert r["checked"]["dropped"] == [] and r["checked"]["numbers_not_in_facts"] == []


# ---------------------------------------------------------------------------- the rules engine

def test_the_sample_recap_tells_the_score_the_goal_and_who_stood_out():
    d = SAMPLE / "syn_0294"
    r = rc.recap(d)
    assert r["answered_by"] == "rules" and r["player_id"] is None
    assert_cited(r, d)
    text = rc.as_text(r)
    assert "Northbridge FC beat Southgate United 1–0" in text
    assert "Sami Castellanos scored for Northbridge FC in the 1st minute, set up by Ivan Ibarra." in text
    assert "saved by Ivan Brennan" in text and "stood out" in text
    goal = next(s for p in r["paragraphs"] for s in p["sentences"] if "set up by" in s["text"])
    assert goal["cites"][0]["event_id"] == "ev_000023" and goal["cites"][0]["clip_id"].startswith("cl_t_home_09_")
    assert REEL_OK(r)


def REEL_OK(r):  # noqa: N802 - reads as a claim in the test above
    return rc.REEL_MIN <= len(r["reel"]) <= rc.REEL_MAX


def test_a_league_match_recap(league_match):
    r = rc.recap(league_match)
    assert_cited(r, league_match)
    header = _stream(league_match)[0]
    home, away = (t["name"] for t in header["teams"])
    assert home in r["headline"] and away in r["headline"]
    goals = [e for e in _stream(league_match) if e.get("event_type") == "goal"]
    cited = {c.get("event_id") for p in r["paragraphs"] for c in p["cites"]}
    assert {g["id"] for g in goals} <= cited, "every goal is told and cited"
    assert REEL_OK(r)


def test_a_recap_told_from_one_players_side():
    d = SAMPLE / "syn_0294"
    r = rc.recap(d, player_id="t_home_09")
    assert_cited(r, d)
    assert r["player"]["name"] == "Sami Castellanos" and r["headline"].startswith("Sami Castellanos:")
    text = rc.as_text(r)
    assert "Sami Castellanos scored the only goal" in text and "nutmegged" in text and "replays" in text
    assert all(r["clips"][c]["player_id"] == "t_home_09" for c in r["reel"]), "a personal reel is the player's own clips"
    # The keeper on the other side: his save, from his side.
    k = rc.recap(d, player_id="t_away_01")
    assert_cited(k, d)
    assert "Southgate United lost 1–0 to Northbridge FC" in rc.as_text(k) and "saved from Sami Castellanos" in rc.as_text(k)


def test_a_league_recap_from_a_players_side_and_a_vision_match(league_match):
    header = _stream(league_match)[0]
    assister = next(e["player_id"] for e in _stream(league_match) if e.get("event_type") == "assist")
    r = rc.recap(league_match, player_id=assister)
    assert_cited(r, league_match)
    assert "set up" in r["paragraphs"][0]["text"]
    assert header["players"][0]["global_player_id"]  # league rosters carry global ids; the recap uses names only
    v = rc.recap(SAMPLE / "vis_0201")
    assert_cited(v, SAMPLE / "vis_0201")
    assert "Northbridge Arena" not in rc.as_text(v), "a vision header's venue is not trusted"


def test_a_player_who_never_played_still_gets_a_cited_recap():
    d = SAMPLE / "syn_0294"
    r = rc.recap(d, player_id="t_home_17")  # an unused substitute: no clips, no events
    assert r["reel"] == [] and r["paragraphs"]
    assert all(s["cites"] for p in r["paragraphs"] for s in p["sentences"])
    with pytest.raises(ValueError):
        rc.prepare(d, "t_nobody_99")


def test_the_facts_hold_no_ids_and_the_model_sees_no_internals():
    facts = rc.prepare(SAMPLE / "syn_0294", "t_home_09").facts
    seen = json.dumps(rc.model_facts(facts))
    assert '"_' not in seen and not rc.JARGON_RE.search(seen)
    assert "xg" not in seen.lower()


# ---------------------------------------------------------------------------- the numbers check

def test_numbers_must_be_in_the_facts():
    facts = rc.prepare(SAMPLE / "syn_0294").facts
    assert rc.numbers_not_in_facts("Castellanos scored in the 1st minute to win 1–0.", facts) == []
    assert rc.numbers_not_in_facts("Castellanos scored in the 77th minute.", facts) == ["77"]
    assert rc.numbers_not_in_facts("He ran 11.4 km.", facts) == ["11.4"]


# ---------------------------------------------------------------------------- the Foundry engine (a stand-in)

def _writer(obj, answered_by="foundry:test"):
    calls = []

    def write(prompt: str) -> str:
        calls.append(json.loads(prompt.split("\n\n")[0]))
        if isinstance(obj, Exception):
            raise obj
        return obj if isinstance(obj, str) else json.dumps(obj)

    write.answered_by = answered_by
    write.calls = calls
    return write


GOOD = {"headline": "Castellanos settles it in the 1st minute", "paragraphs": [
    {"sentences": [{"text": "Northbridge FC beat Southgate United 1–0.", "refs": ["G1"]},
                   {"text": "Sami Castellanos scored in the 1st minute, set up by Ivan Ibarra.", "refs": ["G1"]}]},
    {"sentences": [{"text": "Ivan Brennan kept the score down with a save in the 2nd minute.", "refs": ["C1"]},
                   {"text": "Castellanos also hit the post in the 77th minute.", "refs": ["G1"]},          # a number not in the facts
                   {"text": "It was a lovely afternoon.", "refs": []},                                       # cites nothing
                   {"text": "His shot was worth 0.18 xG.", "refs": ["C1"]},                                  # jargon (and a number)
                   {"text": "A ghost scored.", "refs": ["Z9"]}]},                                            # an unknown ref
    {"sentences": [{"text": "Milan Whitfield caught the eye.", "refs": ["S2"]}]}]}


def test_a_foundry_recap_is_checked_sentence_by_sentence():
    d = SAMPLE / "syn_0294"
    w = _writer(GOOD)
    r = rc.recap(d, engine="foundry", writer=w)
    assert r["answered_by"] == "foundry:test" and r["engine"] == "foundry"
    kept = [s["text"] for p in r["paragraphs"] for s in p["sentences"]]
    assert kept == ["Northbridge FC beat Southgate United 1–0.", "Sami Castellanos scored in the 1st minute, set up by Ivan Ibarra.",
                    "Ivan Brennan kept the score down with a save in the 2nd minute.", "Milan Whitfield caught the eye."]
    why = {x["text"]: x["why"] for x in r["checked"]["dropped"]}
    assert why["Castellanos also hit the post in the 77th minute."].startswith("numbers not in the facts")
    assert why["It was a lovely afternoon."] == "cites no fact" and why["A ghost scored."] == "cites no fact"
    assert why["His shot was worth 0.18 xG."].startswith("numbers not in the facts")
    assert r["checked"]["unknown_refs"] == ["Z9"] and "77" in r["checked"]["numbers_not_in_facts"]
    assert r["checked"]["sentences"] == 8 and r["checked"]["kept"] == 4
    assert r["headline"] == GOOD["headline"]
    # Citations resolve exactly as the rules engine's do.
    assert r["paragraphs"][0]["sentences"][0]["cites"][0]["event_id"] == "ev_000023"
    assert all(s["cites"] for p in r["paragraphs"] for s in p["sentences"])
    # The model saw the facts, refs and all, but no internals and no ids.
    seen = w.calls[0]
    assert seen["goals"][0]["ref"] == "G1" and "_" not in seen and "ev_000023" not in json.dumps(seen)
    assert any(t["kind"] == "agent" for t in r["trace"])


def test_a_foundry_headline_with_a_wrong_number_is_replaced():
    r = rc.recap(SAMPLE / "syn_0294", engine="foundry", writer=_writer({**GOOD, "headline": "Castellanos wins it 3–0"}))
    assert r["headline"] == rc.recap(SAMPLE / "syn_0294")["headline"] and r["checked"]["headline"].startswith("replaced")


@pytest.mark.parametrize("bad, why", [
    (RuntimeError("boom"), "rules (foundry fallback: RuntimeError)"),
    ("not json at all", "rules (foundry fallback: JSONDecodeError)"),
    ({"headline": "x", "paragraphs": [{"sentences": [{"text": "Nobody cites anything.", "refs": []}]}]},
     "rules (foundry fallback: no sentence of the model's recap held)"),
])
def test_a_failing_foundry_recap_falls_back_to_the_rules(bad, why):
    r = rc.recap(SAMPLE / "syn_0294", player_id="t_home_09", engine="foundry", writer=_writer(bad))
    rules = rc.recap(SAMPLE / "syn_0294", player_id="t_home_09")
    assert r["answered_by"] == why and r["paragraphs"] == rules["paragraphs"] and r["reel"] == rules["reel"]


def test_foundry_without_configuration_says_so():
    r = rc.recap(SAMPLE / "syn_0294", engine="foundry")  # tests clear FOUNDRY_* (conftest)
    assert r["answered_by"] == "rules (Foundry is not configured on this deployment)" and r["paragraphs"]


# ---------------------------------------------------------------------------- the endpoint

@pytest.fixture
def client(monkeypatch, tmp_path):
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", SAMPLE)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(api, "SEASON_LEAGUE", LEAGUE)
    monkeypatch.setattr(api, "SEASON_ROOT", tmp_path / "season")
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(per_visitor_per_min=2, per_visitor_per_hour=100, total_per_hour=100,
                                                            total_per_day=100, concurrent=2))
    return TestClient(api.app)


def test_the_endpoint_serves_a_cited_recap_with_its_reel(client):
    from regista import api

    r = client.get("/api/matches/syn_0294/recap", params={"player": "t_home_09"})
    assert r.status_code == 200
    out = r.json()
    assert out["answered_by"] == "rules" and out["player_id"] == "t_home_09"
    assert all(c["video_url"] == f"/api/matches/syn_0294/clips/{cid}.mp4" for cid, c in out["clips"].items())
    assert out["reel_url"] == "/api/matches/syn_0294/reel.mp4?clips=" + ",".join(out["reel"])
    chosen, _labels = api._clips_by_id("syn_0294", out["reel"])  # what reel.mp4 would render: every clip resolves
    assert [c["id"] for c in chosen] == out["reel"]
    assert client.get("/api/matches/syn_0294/recap", params={"player": "t_nobody_99"}).status_code == 404
    assert client.get("/api/matches/syn_0294/recap", params={"player": "../x"}).status_code == 422
    assert client.get("/api/matches/syn_0294/recap", params={"engine": "gpt"}).status_code == 422
    assert client.get("/api/matches/no_such/recap").status_code == 404


def test_the_endpoint_serves_league_and_player_view_matches(client, monkeypatch, tmp_path):
    from regista import api, player_api

    league = client.get("/api/matches/rl_r01_ash_fai/recap").json()
    assert league["match_id"] == "rl_r01_ash_fai" and league["paragraphs"] and league["reel"]
    pv = tmp_path / "pv_0123abcd"
    shutil.copytree(SAMPLE / "vis_0201", pv)
    api._relabel(pv / "events.jsonl", "pv_0123abcd")
    (pv / "clips.jsonl").unlink(missing_ok=True)
    monkeypatch.setattr(player_api, "player_match_dir", lambda mid: pv if mid == "pv_0123abcd" else None)
    out = client.get("/api/matches/pv_0123abcd/recap", params={"player": "t_home_09"}).json()
    assert out["match_id"] == "pv_0123abcd" and out["player"]["name"] and out["paragraphs"]
    assert_cited(out, pv)


def test_foundry_recaps_are_limited_cached_and_fall_back(client, monkeypatch):
    from regista import api

    w = _writer(GOOD)
    monkeypatch.setattr(api, "_recap_writer", lambda: w)
    first = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry"}).json()
    assert first["answered_by"] == "foundry:test" and len(w.calls) == 1 and not first.get("cached")
    again = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry"}).json()
    assert again["cached"] is True and len(w.calls) == 1 and again["paragraphs"] == first["paragraphs"]
    assert (api.CACHE_ROOT / "syn_0294" / "recap_match.json").exists()
    mine = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry", "player": "t_home_09"}).json()
    assert mine["answered_by"] == "foundry:test" and len(w.calls) == 2, "cached per (match, player)"
    busy = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry", "player": "t_away_01"}).json()  # third this minute
    assert busy["answered_by"].startswith("rules (Foundry is busy: 2 per 60s per visitor") and busy["paragraphs"] and len(w.calls) == 2
    # A cached recap whose facts no longer hold is never served.
    path = api.CACHE_ROOT / "syn_0294" / "recap_match.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "basis": "stale"}))
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(10, 100, 100, 100, 2))
    monkeypatch.setattr(api, "_recap_writer", lambda: _writer(RuntimeError("boom")))
    fell = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry"}).json()
    assert fell["answered_by"] == "rules (foundry fallback: RuntimeError)" and fell["paragraphs"] and not fell.get("cached")
    monkeypatch.setattr(api, "_recap_writer", lambda: None)
    off = client.get("/api/matches/syn_0294/recap", params={"engine": "foundry", "player": "t_away_01"}).json()
    assert off["answered_by"] == "rules (Foundry is not configured on this deployment)"


# ---------------------------------------------------------------------------- the workflow step and the MCP tool

def test_the_recap_step_runs_in_the_workflow_and_writes_recap_json(tmp_path):
    from regista.agents.roles import default_agents
    from regista.agents.workflow import WorkflowPipeline

    d = tmp_path / "syn_0294"
    d.mkdir()
    shutil.copy(SAMPLE / "syn_0294" / "events.jsonl", d / "events.jsonl")
    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(
        {"match_dir": str(d), "player_ids": ["t_home_09"], "queries": []})
    assert wf.ok and wf.statuses["recap"] == "ok"
    order = [r["agent"] for r in wf.trace if r["status"] == "ok"]
    assert order.index("label") < order.index("review") < order.index("recap") < order.index("persist")
    row = next(r for r in wf.trace if r["agent"] == "recap")
    assert row["records_in"]["clips"] == 1 and row["state_keys"]
    out = json.loads((d / "recap.json").read_text())
    assert out["answered_by"] == "rules" and wf.state["recap"]["headline"] == out["headline"]
    assert_cited(out, d)

    # With --cloud the Foundry Recap agent writes it (a stand-in here), and recap.json says so.
    from regista.cloud.foundry import FoundryRecapAgent

    agents = [FoundryRecapAgent(writer=_writer(GOOD)) if a.role == "recap" else a for a in default_agents()]
    wf = WorkflowPipeline(agents, state_dir=tmp_path / "s2", feedback_dir=tmp_path / "fb").run(
        {"match_dir": str(d), "player_ids": ["t_home_09"], "queries": []})
    assert wf.ok and json.loads((d / "recap.json").read_text())["answered_by"] == "foundry:test"
    assert wf.state["recap"]["dropped"] == 4


def test_agents_for_swaps_in_the_foundry_recap_agent():
    from regista.cloud import CloudConfig, agents_for
    from regista.cloud.foundry import FoundryRecapAgent

    cfg = CloudConfig(foundry_project_endpoint="https://example.invalid/api/projects/x", foundry_model="m")
    assert isinstance(next(a for a in agents_for(cfg) if a.role == "recap"), FoundryRecapAgent)


def test_match_recap_over_mcp():
    import asyncio
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        import os

        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")])}  # this checkout's code
        params = StdioServerParameters(command=sys.executable, args=["-m", "regista.mcp_server"], cwd=str(ROOT), env=env)
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            res = await session.call_tool("match_recap", {"match_dir": str(SAMPLE / "syn_0294"), "player_id": "t_home_09"})
            sc = res.structuredContent or {}
            return tools, sc.get("result", sc) if sc else json.loads("".join(c.text for c in res.content if getattr(c, "type", "") == "text"))

    tools, out = asyncio.run(go())
    assert "match_recap" in tools
    assert out["player_id"] == "t_home_09" and out["paragraphs"] and "trace" not in out
    assert out["headline"] == rc.recap(SAMPLE / "syn_0294", player_id="t_home_09")["headline"]
