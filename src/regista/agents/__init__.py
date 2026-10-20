"""Regista's multi-agent pipeline.

The roles (``roles.py``: Ingest, Validator, Possession, Clip, Label, Persist, Librarian) have distinct
inputs and outputs and hand a shared state along. ``workflow.py`` runs them as a Microsoft Agent Framework
workflow, the default engine: validator and possession fan out from ingest and fan in at clip, a review
step pauses for human verdicts (``request_info``, checkpointed), an indexer role is added after persist
when Azure AI Search is configured, and every role routes failures to a dead-letter executor.
``orchestrator.py`` is the original hand-written orchestrator, kept as a reference (``--engine orchestrator``)
with the same trace format. Locally the Label and Librarian roles are rule-based (Label uses the
watchability model learned from human verdicts when one exists); ``regista.cloud.agents_for`` swaps in
the Foundry, Cosmos DB, and AI Search variants.

    python -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
"""

from regista.agents.base import Agent, AgentError, State
from regista.agents.orchestrator import Orchestrator, RunResult
from regista.agents.roles import ClipAgent, IngestAgent, LabelAgent, LibrarianAgent, PossessionAgent, ValidatorAgent, default_agents

__all__ = ["Agent", "AgentError", "State", "Orchestrator", "RunResult", "ClipAgent", "IngestAgent", "LabelAgent",
           "LibrarianAgent", "PossessionAgent", "ValidatorAgent", "default_agents"]
