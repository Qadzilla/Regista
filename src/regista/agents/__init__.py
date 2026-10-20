"""Regista's multi-agent pipeline, local and deterministic (v0).

Six roles with distinct inputs and outputs, a shared state they hand along, an orchestrator
that retries, records a trace, and dead-letters what cannot be recovered. This is the shape
the Microsoft Agent Framework version keeps: same roles, same state keys, same trace; the
LLM-backed Label and Librarian agents replace the rule-based ones when Foundry is provisioned.

    python -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
"""

from regista.agents.base import Agent, AgentError, State
from regista.agents.orchestrator import Orchestrator, RunResult
from regista.agents.roles import ClipAgent, IngestAgent, LabelAgent, LibrarianAgent, PossessionAgent, ValidatorAgent, default_agents

__all__ = ["Agent", "AgentError", "State", "Orchestrator", "RunResult", "ClipAgent", "IngestAgent", "LabelAgent",
           "LibrarianAgent", "PossessionAgent", "ValidatorAgent", "default_agents"]
