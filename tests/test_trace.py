"""The answer trace: /chat and /ask say what ran, in order. The rules engine lists its in-process steps; the Foundry
engine lists the Agent Framework spans of the request (agent, model calls, tool calls with their MCP server), or the
tools it called without timings when no spans were recorded. Foundry is never reached: a fake chat client runs inside a
real Agent Framework agent, so the spans are the framework's own."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from regista.aio import run_sync
from regista.cloud.config import CloudConfig
from regista.cloud.foundry import TRACE_FALLBACK_NOTE, FoundryLibrarianAgent, foundry_trace, tool_server
from regista.cloud.telemetry import SpanCollector, capture_spans, span_collector, spans_to_trace

SAMPLE = Path(__file__).resolve().parents[1] / "data/synthetic/sample"
KINDS = {"step", "agent", "model", "tool"}


@pytest.fixture
def client(monkeypatch):
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", SAMPLE)
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(10, 100, 100, 100, 2))
    return TestClient(api.app)


def _well_formed(trace):
    for s in trace:
        assert set(s) == {"name", "kind", "server", "ms"} and s["kind"] in KINDS and s["server"] in (None, "regista-mcp", "azure-mcp")
        assert s["ms"] is None or (isinstance(s["ms"], (int, float)) and s["ms"] >= 0)


# ---------------------------------------------------------------------------- a real agent, a fake model

def _fake_agent_run(tools=("search_clips", "search_index_query"), answer="Two clips: the nutmeg (1') and the goal (2')."):
    """A coroutine factory: a real Agent Framework agent whose chat client is a stand-in. The model asks for each tool
    in turn, then answers; the tools are local functions named like the MCP tools. Returns (text, tools called)."""
    from agent_framework import Agent, BaseChatClient, ChatResponse, Content, Message, tool
    from agent_framework._tools import FunctionInvocationLayer
    from agent_framework.observability import ChatTelemetryLayer

    from regista.cloud.foundry import tools_used

    class FakeFoundry(FunctionInvocationLayer, ChatTelemetryLayer, BaseChatClient):
        OTEL_PROVIDER_NAME = "fake"

        def __init__(self, **kw):
            super().__init__(**kw)
            self.turn = 0

        async def _inner_get_response(self, *, messages, stream, options, **kwargs):
            self.turn += 1
            if self.turn <= len(tools):
                call = Content.from_function_call(call_id=f"c{self.turn}", name=tools[self.turn - 1], arguments={"query": "nutmeg"})
                return ChatResponse(messages=[Message("assistant", [call])], model="gpt-test")
            return ChatResponse(messages=[Message("assistant", [answer])], model="gpt-test")

    def make(name):
        @tool(name=name, description=f"stand-in for the MCP tool {name}")
        def fn(query: str) -> str:
            return "2 clips"
        return fn

    async def run():
        agent = Agent(client=FakeFoundry(), name="regista-librarian", instructions="find clips")
        result = await agent.run("find me Castellanos doing a nutmeg", tools=[make(t) for t in tools])
        return result.text, tools_used(result)

    return run


def _trace_kinds(trace):
    return [(s["kind"], s["name"], s["server"]) for s in trace]


# ---------------------------------------------------------------------------- rules: honest in-process steps

def test_rules_chat_trace_lists_only_in_process_steps(client):
    out = client.post("/api/matches/syn_0294/chat", json={"message": "find me Castellanos doing a nutmeg"}).json()
    trace = out["trace"]
    _well_formed(trace)
    assert [s["name"] for s in trace] == ["librarian.load_match", "conversation.step", "librarian.search_clips"]
    assert all(s["kind"] == "step" and s["server"] is None and s["ms"] is not None for s in trace)  # no model, no MCP
    assert out["answered_by"] == "rules" and out["tools_used"] == [] and "trace_note" not in out


def test_rules_chat_trace_counts_the_second_search_for_alternatives(client):
    out = client.post("/api/matches/syn_0294/chat", json={"message": "Castellanos headers"}).json()
    names = [s["name"] for s in out["trace"]]
    assert out["trace"] and names[:2] == ["librarian.load_match", "conversation.step"] and set(names) <= {
        "librarian.load_match", "conversation.step", "librarian.search_clips"}


def test_ask_without_foundry_traces_the_rules_search(client):
    out = client.post("/api/matches/syn_0294/ask", json={"q": "find me Castellanos doing a nutmeg"}).json()
    assert out["answered_by"].startswith("rules") and out["tools_used"] == []
    assert [(s["name"], s["kind"], s["server"]) for s in out["trace"]] == [("librarian.search_clips", "step", None)]


def test_chat_with_foundry_not_configured_adds_no_foundry_steps(client):
    out = client.post("/api/matches/syn_0294/chat", json={"message": "Castellanos", "engine": "foundry"}).json()
    assert out["answered_by"].startswith("rules (Foundry is not configured")
    assert all(s["kind"] == "step" for s in out["trace"]) and "trace_note" not in out


# ---------------------------------------------------------------------------- Foundry, with the framework's spans

def test_ask_with_foundry_traces_agent_model_and_tools_from_spans(client, monkeypatch):
    from regista import api

    run = _fake_agent_run()
    agent = FoundryLibrarianAgent(answerer=lambda md, q: run(), cloud=CloudConfig())
    monkeypatch.setattr(api, "_librarian_agent", lambda: agent)
    out = client.post("/api/matches/syn_0294/ask", json={"q": "find me Castellanos doing a nutmeg"}).json()
    assert out["answered_by"] == "foundry:test" and out["tools_used"] == ["search_clips", "search_index_query"]
    _well_formed(out["trace"])
    assert _trace_kinds(out["trace"]) == [
        ("step", "librarian.search_clips", None),
        ("agent", "regista-librarian", None),
        ("model", "gpt-test", None),
        ("tool", "search_clips", "regista-mcp"),
        ("model", "gpt-test", None),
        ("tool", "search_index_query", "azure-mcp"),
        ("model", "gpt-test", None),
    ]
    assert all(s["ms"] is not None for s in out["trace"]) and "trace_note" not in out
    agent_ms = out["trace"][1]["ms"]
    assert all(s["ms"] <= agent_ms for s in out["trace"][2:])  # the model and tool calls happen inside the agent run


def test_chat_with_foundry_traces_the_search_then_the_reply_spans(client, monkeypatch):
    from regista import api

    run = _fake_agent_run(tools=("search_library",))

    def reply(d, body, out):
        text, tools = run_sync(run())
        return text, tools, "foundry:test"

    monkeypatch.setattr(api, "_chat_reply_foundry", reply)
    out = client.post("/api/matches/syn_0294/chat", json={"message": "Castellanos nutmegs", "engine": "foundry"}).json()
    assert out["answered_by"] == "foundry:test" and out["tools_used"] == ["search_library"] and out["reply"].startswith("Two clips")
    _well_formed(out["trace"])
    assert _trace_kinds(out["trace"]) == [
        ("step", "librarian.load_match", None), ("step", "conversation.step", None), ("step", "librarian.search_clips", None),
        ("agent", "regista-librarian", None), ("model", "gpt-test", None), ("tool", "search_library", "regista-mcp"),
        ("model", "gpt-test", None),
    ]
    assert "trace_note" not in out


# ---------------------------------------------------------------------------- Foundry without spans: the fallback

def test_ask_falls_back_to_tool_order_without_timings_when_no_spans(client, monkeypatch):
    from regista import api

    async def answerer(md, q):  # no Agent Framework agent ran, so no span was recorded
        return "2 clips matched.", ["search_clips", "cosmos_database_container_item_query"]

    monkeypatch.setattr(api, "_librarian_agent", lambda: FoundryLibrarianAgent(answerer=answerer, cloud=CloudConfig()))
    out = client.post("/api/matches/syn_0294/ask", json={"q": "nutmegs"}).json()
    assert out["trace"][1:] == [{"name": "search_clips", "kind": "tool", "server": "regista-mcp", "ms": None},
                                {"name": "cosmos_database_container_item_query", "kind": "tool", "server": "azure-mcp", "ms": None}]
    assert out["trace"][0]["name"] == "librarian.search_clips" and out["trace_note"] == TRACE_FALLBACK_NOTE
    assert out["tools_used"] == ["search_clips", "cosmos_database_container_item_query"]  # unchanged


def test_chat_falls_back_to_tool_order_without_timings_when_no_spans(client, monkeypatch):
    from regista import api

    monkeypatch.setattr(api, "_chat_reply_foundry", lambda d, body, out: ("Two clips.", ["search_clips"], "foundry:test"))
    out = client.post("/api/matches/syn_0294/chat", json={"message": "Castellanos", "engine": "foundry"}).json()
    assert out["trace"][-1] == {"name": "search_clips", "kind": "tool", "server": "regista-mcp", "ms": None}
    assert [s["kind"] for s in out["trace"][:-1]] == ["step"] * 3 and out["trace_note"] == TRACE_FALLBACK_NOTE


def test_a_failed_foundry_answer_keeps_the_rules_trace(client, monkeypatch):
    from regista import api

    async def answerer(md, q):
        raise RuntimeError("model down")

    monkeypatch.setattr(api, "_librarian_agent", lambda: FoundryLibrarianAgent(answerer=answerer, cloud=CloudConfig()))
    out = client.post("/api/matches/syn_0294/ask", json={"q": "nutmegs"}).json()
    assert out["answered_by"] == "rules (foundry fallback: RuntimeError)"
    assert [s["name"] for s in out["trace"]] == ["librarian.search_clips"] and "trace_note" not in out


# ---------------------------------------------------------------------------- the collector and the mapping

def _span(name, trace_id, start, end, **attrs):
    return SimpleNamespace(name=name, context=SimpleNamespace(trace_id=trace_id), start_time=start, end_time=end, attributes=attrs)


def test_the_collector_keeps_only_the_traces_it_watches():
    col = SpanCollector()
    col.watch(1)
    for s in (_span("chat m", 1, 0, 1), _span("chat m", 2, 0, 1), _span("execute_tool search_clips", 1, 2, 3)):
        col.on_end(s)
    got = col.take(1)
    assert [s.name for s in got] == ["chat m", "execute_tool search_clips"]
    assert col.take(1) == [] and col.take(2) == []  # trace 2 was never watched; trace 1 is no longer watched
    col.on_end(_span("chat m", 1, 0, 1))
    assert col.take(1) == []


def test_spans_map_to_steps_in_start_order_with_servers_and_ms():
    ms = 1_000_000
    spans = [  # in the order they ended, as the collector receives them
        _span("execute_tool search_index_query", 7, 30 * ms, 45 * ms, **{"gen_ai.operation.name": "execute_tool",
                                                                          "gen_ai.tool.name": "search_index_query"}),
        _span("tools/call search_index_query", 7, 31 * ms, 44 * ms),  # MCP protocol span: left out
        _span("chat gpt-5-mini", 7, 10 * ms, 25 * ms, **{"gen_ai.operation.name": "chat", "gen_ai.request.model": "gpt-5-mini"}),
        _span("invoke_agent regista-librarian", 7, 0, 120_500_000),
        _span("regista.ask", 7, 0, 121 * ms),  # the root: left out
    ]
    assert spans_to_trace(spans, tool_server) == [
        {"name": "regista-librarian", "kind": "agent", "server": None, "ms": 120.5},
        {"name": "gpt-5-mini", "kind": "model", "server": None, "ms": 15.0},
        {"name": "search_index_query", "kind": "tool", "server": "azure-mcp", "ms": 15.0},
    ]


def test_tools_map_to_their_mcp_server():
    assert [tool_server(t) for t in ("search_clips", "search_library", "list_matches", "derive_clips", "validate_stream", "render_clip")] \
        == ["regista-mcp"] * 6
    assert [tool_server(t) for t in ("search_index_query", "cosmos_list", "cosmos_database_container_item_query")] == ["azure-mcp"] * 3
    assert tool_server("something_else") is None
    assert foundry_trace([], []) == ([], TRACE_FALLBACK_NOTE)


def test_capture_follows_the_context_into_run_sync_from_a_running_loop():
    """The Agent Framework workflow calls agents from a running loop; run_sync then uses a worker thread, which must
    carry the request's span context or the spans land in a trace nobody watches."""
    from opentelemetry import trace

    assert span_collector() is not None  # spans are recorded in-process without Application Insights

    async def inner():
        with trace.get_tracer("test").start_as_current_span("execute_tool search_clips",
                                                             attributes={"gen_ai.operation.name": "execute_tool"}):
            await asyncio.sleep(0)

    async def outer():
        with capture_spans("regista.test") as cap:
            run_sync(inner())  # a loop is running here, so this goes through the worker thread
        return cap

    cap = asyncio.run(outer())
    assert [s.name for s in cap.spans] == ["execute_tool search_clips"] and cap.trace_id
