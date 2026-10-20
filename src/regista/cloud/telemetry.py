"""Tracing Regista's agents to Microsoft Foundry through Application Insights.

Agent Framework instruments agent runs, model calls, tool calls, and workflow steps with OpenTelemetry.
This module sends those spans to the Application Insights resource connected to the Foundry project,
so every run shows up on the project's Tracing page: which agent ran, which tools it called, tokens,
latency, and failures. Prompts and model outputs are not recorded unless REGISTA_TRACE_CONTENT=1.

    from regista.cloud.telemetry import configure_tracing
    configure_tracing()          # once per process; a no-op without APPLICATIONINSIGHTS_CONNECTION_STRING
"""

from __future__ import annotations

import os

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
