"""Distinct roles, shared state, handoffs, retries, dead letters: the multi-agent pipeline must prove each."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from regista.agents import Agent, AgentError, Orchestrator, default_agents
from regista.agents.roles import LabelAgent
from regista.agents.__main__ import main as agents_main
from regista.synth import generate

PLAYER = "t_home_09"


@pytest.fixture
def match_dir(tmp_path):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = tmp_path / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    (d / "tracks.jsonl").write_text("\n".join(json.dumps(x) for x in r.tracks) + "\n")
    return d


def _surname(match_dir):
    match = json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])
    return next(p["name"].split()[-1] for p in match["players"] if p["player_id"] == PLAYER)


def test_pipeline_runs_end_to_end_with_handoffs(match_dir):
    orch = Orchestrator(default_agents(), match_dir / "agents")
    result = orch.run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": [f"find me {_surname(match_dir)} doing a nutmeg"]})
    assert result.ok, result.statuses
    assert [r["agent"] for r in result.trace] == ["ingest", "validator", "possession", "clip", "label", "recap", "persist", "librarian"]
    assert all(r["status"] == "ok" for r in result.trace)
    # Shared state: each role's outputs are the next role's inputs.
    assert result.state["on_ball"][PLAYER] and result.state["clips"][PLAYER] and result.state["labels"][PLAYER]
    assert len(result.state["clips"][PLAYER]) == len(result.state["labels"][PLAYER])
    assert (match_dir / "clips.jsonl").exists()
    assert result.state["answers"][0]["results"]
    # Files the trace promises.
    assert (match_dir / "agents" / "trace.jsonl").exists() and (match_dir / "agents" / "state.json").exists()
    summary = json.loads((match_dir / "agents" / "state.json").read_text())
    assert summary["clips"][PLAYER] == len(result.state["clips"][PLAYER])
    assert "stream" in summary and isinstance(summary["stream"], dict)


def test_retry_then_success_is_traced(match_dir):
    calls = {"n": 0}

    @dataclass
    class FlakyLabel(LabelAgent):
        def handle(self, state):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AgentError("model endpoint timed out", retryable=True)
            return super().handle(state)

    agents = [a if a.role != "label" else FlakyLabel() for a in default_agents()]
    result = Orchestrator(agents, match_dir / "agents", max_retries=2).run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    assert result.ok
    label_rows = [r for r in result.trace if r["agent"] == "label"]
    assert [r["status"] for r in label_rows] == ["retry", "ok"]
    assert label_rows[0]["error"].startswith("AgentError: model endpoint timed out")
    assert calls["n"] == 2
    assert not result.dead_letters


def test_permanent_failure_dead_letters_and_downstream_is_skipped(match_dir):
    @dataclass
    class BrokenLabel(LabelAgent):
        def handle(self, state):
            raise RuntimeError("labeller crashed")

    agents = [a if a.role != "label" else BrokenLabel() for a in default_agents()]
    result = Orchestrator(agents, match_dir / "agents", max_retries=2).run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": ["goal"]})
    assert not result.ok
    label_rows = [r for r in result.trace if r["agent"] == "label"]
    assert [r["status"] for r in label_rows] == ["retry", "retry", "failed"]
    assert len(result.dead_letters) == 1 and result.dead_letters[0]["agent"] == "label"
    dead = [json.loads(l) for l in (match_dir / "agents" / "dead_letter.jsonl").read_text().splitlines()]
    assert dead[0]["error"] == "RuntimeError: labeller crashed" and dead[0]["attempts"] == 3
    # Persist needs labels, Librarian needs clips_path: both skipped with the missing key named, nothing crashed.
    assert result.statuses["persist"] == "skipped" and result.statuses["librarian"] == "skipped"
    skipped = next(r for r in result.trace if r["agent"] == "persist")
    assert "labels" in skipped["error"]
    # Earlier work survives in the state.
    assert result.state["clips"][PLAYER]


def test_non_retryable_error_is_not_retried(match_dir):
    result = Orchestrator(default_agents(), match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": ["t_nobody_99"], "queries": []})
    rows = [r for r in result.trace if r["agent"] == "possession"]
    assert [r["status"] for r in rows] == ["failed"]
    assert result.dead_letters[0]["retryable"] is False


def test_agent_that_breaks_its_output_contract_is_caught(match_dir):
    @dataclass
    class Silent(Agent):
        role: str = "silent"
        inputs: tuple = ("match_dir",)
        outputs: tuple = ("something",)

        def handle(self, state):
            return state

    result = Orchestrator([Silent()], match_dir / "agents").run({"match_dir": str(match_dir)})
    assert result.statuses["silent"] == "failed"
    assert "did not write" in result.dead_letters[0]["error"]


def test_cli(match_dir, capsys):
    code = agents_main([str(match_dir), "--player", PLAYER, "--query", f"{_surname(match_dir)} goal"])
    out = capsys.readouterr().out
    assert code == 0 and "librarian" in out and "ok: True" in out
