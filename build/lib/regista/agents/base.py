"""Agent contract: a role with declared inputs and outputs that transforms shared state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

State = dict[str, Any]


class AgentError(RuntimeError):
    """An agent could not do its job. ``retryable`` tells the orchestrator whether trying again can help."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


@dataclass
class Agent:
    """Base role. Subclasses set ``role``, ``inputs``, ``outputs`` and implement ``handle``.

    ``inputs`` are state keys that must be present before the agent runs (the handoff contract);
    ``outputs`` are the keys it promises to write. The orchestrator checks both, so a broken
    handoff is reported as such rather than surfacing as a KeyError three agents later.
    """

    role: str = "agent"
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def handle(self, state: State) -> State:  # pragma: no cover - abstract
        raise NotImplementedError

    def missing_inputs(self, state: State) -> list[str]:
        return [k for k in self.inputs if k not in state]

    def missing_outputs(self, state: State) -> list[str]:
        return [k for k in self.outputs if k not in state]
