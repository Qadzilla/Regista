"""The Scout agent, the player MCP tools, and the Profile agent's summaries. Foundry is always a stand-in here."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.season import scout, summaries
from regista.season.league import new_league, save_league
from regista.season.profiles import Season, load_season

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The real league's clubs with only its first four fixtures (every club plays at least once): quick to build."""
    league = new_league(2026)
    small = {**league, "fixtures": league["fixtures"][:4]}
    root = tmp_path_factory.mktemp("season")
    return small, root, Season.build(small, root)


@pytest.fixture(scope="module")
def season(built):
    return built[2]


def _top(season, position, key):
    """The player the tools should rank first: most of ``key`` per 90 among those with enough minutes."""
    floor = scout.default_min_minutes(season)
    rows = [p for p in season.profiles.values() if p["appearances"] and p["position"] == position and p["minutes"] >= floor]
    return max(rows, key=lambda p: (p["per90"][key], [-ord(c) for c in p["name"]]))


# ---------------------------------------------------------------------------- the rules engine reads questions

@pytest.mark.parametrize("question, position, sort", [
    ("a winger with the most take-ons", "FW", "take_ons_won"),
    ("midfielders who win the ball back", "MF", "recoveries"),
    ("the best finisher", None, "goals"),
    ("defenders who play forward passes", "DF", "forward_passes"),  # "forward passes" is a stat, not forwards
    ("which striker shoots the most?", "FW", "shots"),
    ("keeper with the most saves", "GK", "saves"),
    ("who is the best playmaker", "MF", "key_passes"),
    ("best pass accuracy among centre-backs", "DF", "pass_accuracy"),
])
def test_questions_become_filters_and_a_sort(season, question, position, sort):
    q = scout.parse(season, question)
    assert (q["mode"], q["position"], q["sort"]) == ("rank", position, sort)
    assert q["heard"], "it always says what it heard"


def test_a_winger_with_the_most_take_ons_is_answered_from_the_numbers(season):
    out = scout.answer_rules(season, "a winger with the most take-ons")
    best = _top(season, "FW", "take_ons_won")
    assert out["players"][0]["global_id"] == best["global_id"] and all(c["position"] == "FW" for c in out["players"])
    assert best["name"] in out["reply"] and f"{best['per90']['take_ons_won']:g} per 90" in out["reply"]
    assert out["understood"].startswith("forwards · most take-ons won per 90 · top 5") and "“winger” → forwards (FW)" in out["understood"]
    card = out["players"][0]
    assert card["stat"]["key"] == "take_ons_won" and card["stat"]["rank"] == 1 and card["profile_url"] == f"/players/{best['global_id']}"
    assert {"global_id", "name", "club", "headline", "best_moment"} <= set(card)
    assert out["answered_by"] == "rules" and [s["name"] for s in out["trace"]] == ["scout.parse", "scout.search_players"]


def test_limits_order_clubs_names_and_nonsense(season):
    q = scout.parse(season, "top 3 Ashby midfielders with the fewest fouls won")
    assert (q["limit"], q["club"], q["position"], q["order"], q["sort"]) == (3, "cl_ashby", "MF", "asc", "fouls_won")
    p = next(p for p in season.profiles.values() if p["appearances"])
    one = scout.answer_rules(season, f"{p['name']} tackles")
    assert one["query"]["mode"] == "player" and one["players"][0]["global_id"] == p["global_id"] and "tackles won" in one["reply"]
    a, b = [x for x in season.profiles.values() if x["appearances"]][:2]
    both = scout.answer_rules(season, f"compare {a['name']} and {b['name']}")
    assert both["query"]["mode"] == "compare" and {c["global_id"] for c in both["players"]} == {a["global_id"], b["global_id"]}
    none = scout.answer_rules(season, "what's the weather like")
    assert none["query"]["mode"] == "none" and none["players"] == [] and "Try:" in none["reply"]
    assert none["understood"] == "nothing I recognise"


def test_a_shared_surname_asks_for_the_full_name(season):
    by_surname: dict[str, list] = {}
    for p in season.profiles.values():
        if p["appearances"]:
            by_surname.setdefault(p["name"].split()[-1], []).append(p)
    surname, shared = next((s, ps) for s, ps in by_surname.items() if len(ps) > 1)
    out = scout.answer_rules(season, surname)
    assert out["query"]["mode"] == "ambiguous" and len(out["players"]) == len(shared) and "full name" in out["reply"]
    assert "candidates" in scout.get_profile(season, surname)


# ---------------------------------------------------------------------------- the tools

def test_search_players_sorts_filters_and_explains(season):
    out = scout.search_players(season, position="FW", sort="shots", limit=50)
    vals = [r["stat"]["value"] for r in out["players"]]
    assert vals == sorted(vals, reverse=True) and len(vals) <= scout.MAX_LIMIT
    assert out["note"].startswith("players with at least") and out["sort_label"] == "Shots"
    asc = scout.search_players(season, position="FW", sort="shots", order="asc")
    assert [r["stat"]["value"] for r in asc["players"]] == sorted(r["stat"]["value"] for r in asc["players"])
    acc = scout.search_players(season, sort="pass_accuracy")
    assert all(r["stat"]["of"] >= scout.RATIO_MIN["pass_accuracy"] for r in acc["players"])
    assert "error" in scout.search_players(season, sort="charisma") and "error" in scout.search_players(season, position="ST")
    by_min = scout.search_players(season, sort="minutes")
    assert by_min["min_minutes"] == 0.0 and by_min["players"][0]["stat"]["kind"] == "total"


def test_get_profile_and_compare(season):
    p = next(p for p in season.profiles.values() if p["appearances"])
    prof = scout.get_profile(season, p["global_id"])
    assert "evidence" not in prof and "grid" not in prof and len(prof["best_moments"]) <= 5
    assert prof["stats"]["goals"]["count"] == p["counts"]["goals"] and prof["summary"]
    assert scout.get_profile(season, p["name"])["global_id"] == p["global_id"]
    assert "error" in scout.get_profile(season, "pl_nobody_99")
    a, b = [x for x in season.profiles.values() if x["appearances"]][:2]
    cmp = scout.compare_players(season, [a["global_id"], b["name"]])
    assert [x["global_id"] for x in cmp["players"]] == [a["global_id"], b["global_id"]]
    assert "error" in scout.compare_players(season, [a["global_id"]])


@pytest.fixture(scope="module")
def league_files(built, tmp_path_factory):
    small, root, _ = built
    d = tmp_path_factory.mktemp("league")
    return save_league(small, d / "league.json"), root


def test_the_player_tools_over_mcp(league_files):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    league_path, root = league_files
    env = {**os.environ, "REGISTA_SEASON": str(league_path), "REGISTA_SEASON_ROOT": str(root), "PYTHONPATH": str(ROOT / "src")}

    async def go():
        params = StdioServerParameters(command=sys.executable, args=["-m", "regista.mcp_server"], cwd=str(ROOT), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = {t.name: t.description for t in (await session.list_tools()).tools}
                ranked = await session.call_tool("search_players", {"position": "FW", "sort": "take_ons_won", "limit": 3})
                first = json.loads(ranked.content[0].text)["players"][0]["global_id"]
                prof = await session.call_tool("get_profile", {"player": first})
                return names, json.loads(ranked.content[0].text), json.loads(prof.content[0].text)

    names, ranked, prof = asyncio.run(go())
    assert {"search_players", "get_profile", "compare_players", "search_clips"} <= set(names)
    assert "take_ons_won" in names["search_players"] and "FW" in names["search_players"]
    assert len(ranked["players"]) == 3 and ranked["sort"] == "take_ons_won"
    assert prof["global_id"] == ranked["players"][0]["global_id"] and "evidence" not in prof


def test_list_tools_includes_the_player_tools():
    import subprocess

    out = subprocess.run([sys.executable, "-m", "regista.mcp_server", "--list-tools"], capture_output=True, text=True, cwd=ROOT,
                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, check=True).stdout
    assert all(f"{t}:" in out for t in ("search_players", "get_profile", "compare_players", "search_clips"))


# ---------------------------------------------------------------------------- the Foundry engine, with a stand-in model

def _fake_scout_run(calls, answer):
    """A real Agent Framework agent whose chat client is a stand-in: it asks for each tool call in turn, then answers.
    The tools are local functions named like the MCP tools. Returns (text, tool calls with arguments)."""
    from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message, tool
    from agent_framework._tools import FunctionInvocationLayer

    from regista.cloud.foundry import tool_calls

    class FakeFoundry(FunctionInvocationLayer, BaseChatClient):
        def __init__(self, **kw):
            super().__init__(**kw)
            self.turn = 0

        async def _inner_get_response(self, *, messages, stream, options, **kwargs):
            self.turn += 1
            if self.turn <= len(calls):
                name, args = calls[self.turn - 1]
                call = Content.from_function_call(call_id=f"c{self.turn}", name=name, arguments=json.dumps(args))
                return ChatResponse(messages=[Message("assistant", [call])], model="gpt-test")
            return ChatResponse(messages=[Message("assistant", [answer])], model="gpt-test")

    @tool(name="search_players", description="stand-in")
    def search_players(position: str = "", sort: str = "minutes", limit: int = 5) -> str:
        return "players"

    async def run():
        agent = Agent(client=FakeFoundry(), name="regista-scout", instructions="scout")
        result = await agent.run("q", tools=[search_players])
        return result.text, tool_calls(result)

    return asyncio.run(run())


def test_foundry_cards_are_its_own_tool_call_and_its_numbers_are_checked(season):
    best = _top(season, "FW", "take_ons_won")
    v = best["per90"]["take_ons_won"]
    text, calls = _fake_scout_run([("search_players", {"position": "FW", "sort": "take_ons_won", "limit": 3})],
                                  f"{best['name']} leads the forwards with {v:g} take-ons won per 90 and 77.7 dribbles.")
    assert calls == [("search_players", {"position": "FW", "sort": "take_ons_won", "limit": 3})]
    rules = scout.answer_rules(season, "who dribbles past people?")
    out = scout.from_foundry(season, rules, text, calls, "foundry:test")
    assert out["answered_by"] == "foundry:test" and out["reply"] == text and out["tools_used"] == ["search_players"]
    assert [c["global_id"] for c in out["players"]][0] == best["global_id"] and len(out["players"]) == 3
    assert out["understood"].startswith("Foundry called search_players(position=FW, sort=take_ons_won, limit=3)")
    assert out["checked"] == {"tool_calls": 1, "numbers_not_in_tool_results": ["77.7"]}
    bare = scout.from_foundry(season, rules, "No idea.", [], "foundry:test")
    assert bare["players"] == rules["players"] and "without a player tool" in bare["understood"]


# ---------------------------------------------------------------------------- the endpoint

@pytest.fixture
def client(league_files, monkeypatch, tmp_path):
    from regista import api

    league_path, root = league_files
    monkeypatch.setattr(api, "SEASON_LEAGUE", league_path)
    monkeypatch.setattr(api, "SEASON_ROOT", root)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(per_visitor_per_min=2, per_visitor_per_hour=100, total_per_hour=100,
                                                            total_per_day=100, concurrent=2))
    return TestClient(api.app)


def test_scout_ask_with_rules_and_without_foundry(client):
    r = client.post("/api/scout/ask", json={"q": "a winger with the most take-ons", "engine": "rules"}).json()
    assert r["answered_by"] == "rules" and r["players"] and r["understood"].startswith("forwards")
    assert set(r) >= {"reply", "understood", "query", "players", "trace", "answered_by"}
    d = client.post("/api/scout/ask", json={"q": "a winger with the most take-ons"}).json()  # engine defaults to foundry
    assert d["answered_by"] == "rules (Foundry is not configured on this deployment)" and d["players"] == r["players"]


def test_scout_ask_with_foundry_its_trace_limits_and_fallbacks(client, monkeypatch):
    from regista import season_api

    seen = {}

    def fake(s, q, rules):
        seen["understood"] = rules["understood"]
        return "Top forward: see the cards.", [("search_players", {"position": "FW", "sort": "shots", "limit": 2})], "foundry:test"

    monkeypatch.setattr(season_api, "_scout_foundry", fake)
    first = client.post("/api/scout/ask", json={"q": "which striker shoots the most?"}).json()
    assert first["answered_by"] == "foundry:test" and first["tools_used"] == ["search_players"] and len(first["players"]) == 2
    assert all(c["stat"]["key"] == "shots" for c in first["players"]) and seen["understood"].startswith("forwards")
    assert [s["name"] for s in first["trace"][:2]] == ["scout.parse", "scout.search_players"]
    assert first["trace"][2] == {"name": "search_players", "kind": "tool", "server": "regista-mcp", "ms": None} and first["trace_note"]
    assert client.post("/api/scout/ask", json={"q": "the best finisher"}).json()["answered_by"] == "foundry:test"
    busy = client.post("/api/scout/ask", json={"q": "which striker shoots the most?"}).json()  # third this minute (limit 2)
    assert busy["answered_by"].startswith("rules (Foundry is busy: 2 per 60s per visitor") and busy["players"]

    from regista import api

    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(10, 100, 100, 100, 2))
    monkeypatch.setattr(season_api, "_scout_foundry", lambda s, q, rules: (_ for _ in ()).throw(RuntimeError("boom")))
    fell = client.post("/api/scout/ask", json={"q": "the best finisher"}).json()
    assert fell["answered_by"] == "rules (foundry fallback: RuntimeError)" and fell["reply"] and fell["players"]


@pytest.mark.parametrize("body", [{"q": ""}, {"q": "x" * 201}, {"q": "hi", "engine": "gpt"}, {}])
def test_scout_ask_rejects_bad_bodies(client, body):
    assert client.post("/api/scout/ask", json=body).status_code == 422


def test_a_profile_carries_its_summary(client, built):
    _small, _root, season = built
    gid = next(g for g, p in season.profiles.items() if p["appearances"])
    s = client.get(f"/api/players/{gid}").json()["summary"]
    assert s["model"] == "rules-v0 (live)" and s["text"] and s["sentences"] and s["sources"]


# ---------------------------------------------------------------------------- the Profile agent's summaries

def test_every_rules_summary_cites_facts_that_hold_its_numbers(season):
    for p in summaries.players_with_minutes(season):
        s = summaries.rules_summary(season, p)
        fs = summaries.facts(season, p)
        assert 2 <= len(s["sentences"]) <= 3 and s["model"] == "rules-v0"
        summaries.check_sentences({"sentences": s["sentences"]}, fs)  # the same check a Foundry answer must pass
        assert {x["id"] for x in s["sources"]} == {i for st in s["sentences"] for i in st["sources"]}
        assert s["text"].startswith(p["name"]) and not summaries.GENDERED.search(s["text"])


def test_a_model_answer_is_refused_when_it_does_not_hold_up(season):
    p = summaries.players_with_minutes(season)[0]
    fs = summaries.facts(season, p)
    stat = next(f for f in fs if f["type"] == "stat" and f["kind"] == "per90")
    good = {"sentences": [{"text": f"{p['name']} plays for {p['club']}.", "sources": ["P1"]},
                          {"text": f"{stat['value']:g} {stat['label'].lower()} per 90.", "sources": [stat["id"]]}]}
    assert len(summaries.check_sentences(good, fs)) == 2
    bad = [
        {"sentences": good["sentences"][:1]},  # one sentence
        {"sentences": [good["sentences"][0], {"text": "Plays well.", "sources": []}]},  # cites nothing
        {"sentences": [good["sentences"][0], {"text": "Plays well.", "sources": ["S99"]}]},  # cites what does not exist
        {"sentences": [good["sentences"][0], {"text": "Scores 77.7 per 90.", "sources": [stat["id"]]}]},  # a made-up number
        {"sentences": [good["sentences"][0], {"text": "He plays well.", "sources": [stat["id"]]}]},  # a gendered pronoun
    ]
    for obj in bad:
        with pytest.raises(ValueError):
            summaries.check_sentences(obj, fs)


def test_foundry_summaries_retry_once_then_fall_back(season):
    p = summaries.players_with_minutes(season)[0]
    good = json.dumps({"sentences": [{"text": f"{p['name']} plays for {p['club']}.", "sources": ["P1"]},
                                     {"text": f"{p['appearances']} appearances.", "sources": ["P1"]}]})
    prompts = []

    def runner_of(answers):
        async def run(instructions, prompt):
            prompts.append(prompt)
            return answers.pop(0)
        return run

    s, note = asyncio.run(summaries.foundry_summary(season, p, runner_of(['{"sentences": []}', good]), "foundry:test"))
    assert s["model"] == "foundry:test" and note is None and "was refused" in prompts[-1]
    s, note = asyncio.run(summaries.foundry_summary(season, p, runner_of(["nope", "nope"]), "foundry:test"))
    assert s["model"] == "rules-v0 (foundry fallback)" and note
    doc = summaries.summarise(season, runner=runner_of([good] * 200), model="foundry:test")
    assert len(doc["players"]) == len(summaries.players_with_minutes(season))


def test_a_stored_summary_is_served_only_while_its_numbers_hold(season, tmp_path):
    p = summaries.players_with_minutes(season)[0]
    stored = {**summaries.rules_summary(season, p), "model": "foundry:test"}
    path = summaries.write_summaries({"players": {p["global_id"]: stored}}, tmp_path / "summaries.json")
    assert summaries.summary_for(season, p, path)["model"] == "foundry:test"
    stale = {**stored, "basis": "0" * 16}
    summaries.write_summaries({"players": {p["global_id"]: stale}}, path)
    os.utime(path, ns=(1, 1))  # a new mtime even on coarse clocks
    assert summaries.summary_for(season, p, path)["model"] == "rules-v0 (live)"


def test_the_committed_summaries_match_the_committed_league():
    """Every player with minutes has a stored summary written from today's numbers, and it holds up."""
    path = ROOT / "data" / "season" / "summaries.json"
    doc = json.loads(path.read_text())
    full = load_season(ROOT / "data" / "season" / "league.json", ROOT / "data" / "season" / "matches")
    players = summaries.players_with_minutes(full)
    assert set(doc["players"]) == {p["global_id"] for p in players}
    for p in players:
        s = doc["players"][p["global_id"]]
        assert s["basis"] == summaries.basis(p), f"{p['global_id']}: summary written from other numbers; run summarise again"
        summaries.check_sentences({"sentences": s["sentences"]}, summaries.facts(full, p))
        assert summaries.summary_for(full, p, path) == s


def test_rate_limits_are_waited_out_and_a_rerun_keeps_current_summaries(season, monkeypatch):
    monkeypatch.setattr(summaries, "RATE_LIMIT_WAIT_S", 0.0)
    p = summaries.players_with_minutes(season)[0]
    good = json.dumps({"sentences": [{"text": "A regular in the side.", "sources": ["P1"]},  # holds for every player
                                     {"text": "Plays every minute.", "sources": ["P1"]}]})
    answers = [RuntimeError("Error code: 429 rate_limit_exceeded")] * 3 + [good]

    async def run(instructions, prompt):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    s, note = asyncio.run(summaries.foundry_summary(season, p, run, "foundry:test"))
    assert s["model"] == "foundry:test" and note is None and not answers  # three waits, no refused answer
    calls = []

    async def counting(instructions, prompt):
        calls.append(prompt)
        return good

    first = summaries.summarise(season, runner=counting, model="foundry:test")
    n = len(calls)
    stale = dict(first["players"])
    stale[p["global_id"]] = {**stale[p["global_id"]], "model": "rules-v0 (foundry fallback)"}
    again = summaries.summarise(season, runner=counting, model="foundry:test", keep=stale)
    assert len(calls) == n + 1 and again["players"].keys() == first["players"].keys()


def test_an_mcp_tool_call_is_one_step_in_the_trace():
    """Agent Framework tags the MCP client's ``tools/call`` span ``execute_tool`` too, under the tool call it carries
    out (seen with Foundry on 2026-10-22): the trace keeps the outer one only."""
    from types import SimpleNamespace as NS

    from regista.cloud.foundry import tool_server
    from regista.cloud.telemetry import spans_to_trace

    def span(name, sid, parent, start, end, **attrs):
        return NS(name=name, context=NS(span_id=sid), parent=NS(span_id=parent) if parent else None, start_time=start,
                  end_time=end, attributes=attrs)

    ms = 1_000_000
    spans = [span("invoke_agent regista-scout", 2, 1, 0, 100 * ms),
             span("chat gpt-5-mini", 3, 2, 1 * ms, 40 * ms, **{"gen_ai.operation.name": "chat", "gen_ai.request.model": "gpt-5-mini"}),
             span("execute_tool search_players", 4, 2, 41 * ms, 60 * ms, **{"gen_ai.operation.name": "execute_tool"}),
             span("tools/call search_players", 5, 4, 42 * ms, 59 * ms, **{"gen_ai.operation.name": "execute_tool"})]
    steps = spans_to_trace(spans, tool_server)
    assert [(s["kind"], s["name"], s["server"], s["ms"]) for s in steps] == [
        ("agent", "regista-scout", None, 100.0), ("model", "gpt-5-mini", None, 39.0), ("tool", "search_players", "regista-mcp", 19.0)]
