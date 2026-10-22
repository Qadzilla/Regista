"""Tracing Regista's agents to Microsoft Foundry through Application Insights.

Agent Framework instruments agent runs, model calls, tool calls, and workflow steps with OpenTelemetry.
This module sends those spans to the Application Insights resource connected to the Foundry project,
so every run shows up on the project's Tracing page: which agent ran, which tools it called, tokens,
latency, and failures. Prompts and model outputs are not recorded unless REGISTA_TRACE_CONTENT=1.

    from regista.cloud.telemetry import configure_tracing
    configure_tracing()          # once per process; a no-op without APPLICATIONINSIGHTS_CONNECTION_STRING

The same spans also answer one request's "what ran?": ``capture_spans`` opens a root span, and an in-process span
processor (``SpanCollector``) keeps every span of that trace that ends while it is open. That works with or without
Application Insights: without it, Regista installs a plain SDK tracer provider so spans are still recorded in-process.

    with capture_spans("regista.ask") as cap:
        agent.run(...)
    cap.spans                    # the finished spans of this request, in the order they ended
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

try:  # the SDK comes with the cloud extra; without it nothing records spans and the collector is never attached
    from opentelemetry.sdk.trace import SpanProcessor as _SpanProcessor
except ImportError:  # pragma: no cover
    _SpanProcessor = object  # type: ignore[assignment,misc]

_configured = False


def configure_tracing(service_name: str = "regista") -> bool:
    """Export Agent Framework spans to Application Insights. Returns True when tracing is on."""
    global _configured
    if _configured:
        return True
    from regista.cloud.config import load_dotenv

    dotenv = os.environ.get("REGISTA_DOTENV", ".env")
    if dotenv:
        load_dotenv(dotenv)
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn:
        return False
    try:
        from agent_framework.observability import create_metric_views, create_resource, enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        return False
    # sampling_ratio=1.0: keep every trace. The distro's default rate-limited sampler drops traces under load,
    # and an agent audit trail with gaps is worse than none.
    configure_azure_monitor(connection_string=conn, resource=create_resource(service_name=service_name),
                            views=create_metric_views(), enable_live_metrics=False, sampling_ratio=1.0)
    enable_instrumentation(enable_sensitive_data=os.environ.get("REGISTA_TRACE_CONTENT") == "1")
    _configured = True
    return True


def flush_tracing(timeout_ms: int = 15000) -> None:
    """Send buffered spans now. Short-lived processes (the CLI) exit before the batch exporter's next tick."""
    if not _configured:
        return
    from opentelemetry import metrics, trace

    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        flush = getattr(provider, "force_flush", None)
        if flush:
            flush(timeout_ms)


# ---------------------------------------------------------------------------- one request's spans, in-process

class SpanCollector(_SpanProcessor):
    """An OpenTelemetry span processor that keeps the finished spans of the traces it is told to watch, and nothing
    else, so a request can read back what its agents, models and tools did. Thread-safe; every other span passes by."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._watching: dict[int, list[Any]] = {}

    def watch(self, trace_id: int) -> None:
        with self._lock:
            self._watching.setdefault(trace_id, [])

    def take(self, trace_id: int) -> list[Any]:
        """Stop watching a trace and return its finished spans."""
        with self._lock:
            return self._watching.pop(trace_id, [])

    def on_end(self, span: Any) -> None:
        ctx = getattr(span, "context", None)
        tid = getattr(ctx, "trace_id", None)
        with self._lock:
            if tid in self._watching:
                self._watching[tid].append(span)


_collector: SpanCollector | None = None
_collector_lock = threading.Lock()


def span_collector() -> SpanCollector | None:
    """The process's collector, attached to the global tracer provider on first use. Application Insights is
    configured first when it can be, so its provider is the one the collector joins; otherwise a plain SDK provider
    is installed so Agent Framework spans are recorded anyway. None without the OpenTelemetry SDK."""
    global _collector
    with _collector_lock:
        if _collector is not None:
            return _collector
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
        except ImportError:
            return None
        configure_tracing()
        provider = trace.get_tracer_provider()
        if not hasattr(provider, "add_span_processor"):  # the API's no-op proxy: nothing records spans yet
            trace.set_tracer_provider(TracerProvider())
            provider = trace.get_tracer_provider()
        if not hasattr(provider, "add_span_processor"):
            return None
        _collector = SpanCollector()
        provider.add_span_processor(_collector)
        return _collector


@dataclass
class Capture:
    """What ``capture_spans`` hands back: the finished spans of the request, filled when the block ends."""

    trace_id: int = 0
    spans: list[Any] = field(default_factory=list)


@contextmanager
def capture_spans(name: str, collector: SpanCollector | None = None) -> Iterator[Capture]:
    """Run the block under a new root span and collect every span of its trace that finishes inside it. Spans follow
    the context into coroutines (``asyncio.run`` copies it); the root span is exported like any other when Application
    Insights is on. If spans cannot be recorded, ``spans`` stays empty and the block still runs."""
    cap = Capture()
    col = collector or span_collector()
    if col is None:
        yield cap
        return
    from opentelemetry import trace

    with trace.get_tracer("regista").start_as_current_span(name) as root:
        cap.trace_id = root.get_span_context().trace_id
        if cap.trace_id:
            col.watch(cap.trace_id)
        try:
            yield cap
        finally:
            if cap.trace_id:
                cap.spans = col.take(cap.trace_id)


OPERATION_KINDS = {"invoke_agent": "agent", "chat": "model", "execute_tool": "tool"}


def spans_to_trace(spans: list[Any], server_of: Any = None) -> list[dict[str, Any]]:
    """Agent Framework's GenAI spans as answer-trace steps, in the order they started: ``invoke_agent <agent>`` is an
    agent, ``chat <model>`` a model call, ``execute_tool <tool>`` a tool call (``server_of(tool)`` names its MCP
    server). Every other span (the root, MCP protocol messages, HTTP) is left out."""
    steps = []
    for s in sorted(spans, key=lambda s: s.start_time or 0):
        attrs = dict(getattr(s, "attributes", None) or {})
        op, _, rest = (s.name or "").partition(" ")
        op = attrs.get("gen_ai.operation.name") or op
        kind = OPERATION_KINDS.get(op)
        if kind is None:
            continue
        if kind == "tool":
            label = attrs.get("gen_ai.tool.name") or rest
        elif kind == "agent":
            label = attrs.get("gen_ai.agent.name") or rest
        else:
            label = attrs.get("gen_ai.request.model") or rest
        ms = round((s.end_time - s.start_time) / 1e6, 1) if s.start_time is not None and s.end_time is not None else None
        steps.append({"name": label or op, "kind": kind, "server": server_of(label) if kind == "tool" and server_of else None, "ms": ms})
    return steps
