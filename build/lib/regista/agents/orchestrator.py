"""Runs agents in order over shared state, with retries, a trace, and a dead letter file.

Failure handling, in order:
1. An agent whose declared inputs are missing is skipped (status ``skipped``) with the missing keys named.
2. An agent that raises a retryable error is retried up to ``max_retries`` times.
3. An agent that still fails, or raises a non-retryable error, is written to ``dead_letter.jsonl``
   with its inputs' summary, and the run continues; downstream agents that depended on its outputs
   are then skipped by rule 1 rather than crashing.

Everything the orchestrator learns goes to ``<state_dir>/trace.jsonl`` (one line per attempt) and
``<state_dir>/state.json`` (a JSON-safe summary of the final state).
"""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from regista.agents.base import Agent, AgentError, State


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _size(value: Any) -> int | None:
    if isinstance(value, (list, dict, str)):
        return len(value)
    return None


def summarise_state(state: State) -> dict[str, Any]:
    """A JSON-safe view of the state: counts and small values, never the raw stream."""
    out: dict[str, Any] = {}
    for key, value in state.items():
        if key in ("stream", "index"):
            out[key] = {"records": _size(value)} if key == "stream" else {"segments": len(value.segments), "events": len(value.events)}
        elif isinstance(value, dict) and value and all(isinstance(v, list) for v in value.values()):
            out[key] = {k: len(v) for k, v in value.items()}
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = value if len(json.dumps(value, default=str)) < 20000 else {"items": len(value)}
        elif isinstance(value, dict):
            try:
                json.dumps(value)
                out[key] = value
            except TypeError:
                out[key] = {k: _size(v) for k, v in value.items()}
        else:
            out[key] = str(type(value).__name__)
    return out


@dataclass
class RunResult:
    state: State
    trace: list[dict[str, Any]]
    dead_letters: list[dict[str, Any]]
    state_dir: Path

    @property
    def statuses(self) -> dict[str, str]:
        last: dict[str, str] = {}
        for row in self.trace:
            last[row["agent"]] = row["status"]
        return last

    @property
    def ok(self) -> bool:
        return not self.dead_letters and all(s == "ok" for s in self.statuses.values())


@dataclass
class Orchestrator:
    agents: list[Agent]
    state_dir: Path
    max_retries: int = 2
    retry_delay_s: float = 0.0
    trace: list[dict[str, Any]] = field(default_factory=list)
    dead_letters: list[dict[str, Any]] = field(default_factory=list)

    def run(self, initial: State) -> RunResult:
        self.state_dir = Path(self.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.state_dir / "trace.jsonl"
        dead_path = self.state_dir / "dead_letter.jsonl"
        trace_path.write_text("", encoding="utf-8")
        dead_path.write_text("", encoding="utf-8")
        state: State = dict(initial)
        for agent in self.agents:
            missing = agent.missing_inputs(state)
            if missing:
                self._record(trace_path, agent, 0, "skipped", state, error=f"missing inputs: {missing}")
                continue
            for attempt in range(1, self.max_retries + 2):
                started = time.perf_counter()
                try:
                    before = {k: _size(state.get(k)) for k in agent.inputs}
                    state = agent.handle(state)
                    not_written = agent.missing_outputs(state)
                    if not_written:
                        raise AgentError(f"{agent.role} promised {agent.outputs} but did not write {not_written}", retryable=False)
                    after = {k: _size(state.get(k)) for k in agent.outputs}
                    self._record(trace_path, agent, attempt, "ok", state, started=started, records_in=before, records_out=after)
                    break
                except Exception as exc:  # noqa: BLE001 - every failure must be recorded, whatever it is
                    retryable = getattr(exc, "retryable", True)
                    last = attempt == self.max_retries + 1 or not retryable
                    status = "failed" if last else "retry"
                    self._record(trace_path, agent, attempt, status, state, started=started, error=f"{type(exc).__name__}: {exc}")
                    if last:
                        letter = {"at": _now(), "agent": agent.role, "attempts": attempt, "error": f"{type(exc).__name__}: {exc}",
                                  "retryable": retryable, "inputs": {k: _size(state.get(k)) for k in agent.inputs},
                                  "traceback": traceback.format_exc().splitlines()[-3:]}
                        self.dead_letters.append(letter)
                        with dead_path.open("a", encoding="utf-8") as fh:
                            fh.write(json.dumps(letter) + "\n")
                        break
                    if self.retry_delay_s:
                        time.sleep(self.retry_delay_s)
        (self.state_dir / "state.json").write_text(json.dumps(summarise_state(state), indent=2, default=str) + "\n", encoding="utf-8")
        return RunResult(state=state, trace=list(self.trace), dead_letters=list(self.dead_letters), state_dir=self.state_dir)

    def _record(self, trace_path: Path, agent: Agent, attempt: int, status: str, state: State, *, started: float | None = None,
                error: str | None = None, records_in: dict | None = None, records_out: dict | None = None) -> None:
        row = {"at": _now(), "agent": agent.role, "attempt": attempt, "status": status,
               "elapsed_ms": round((time.perf_counter() - started) * 1000, 1) if started else None,
               "records_in": records_in, "records_out": records_out, "error": error, "state_keys": sorted(state)}
        self.trace.append(row)
        with trace_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
