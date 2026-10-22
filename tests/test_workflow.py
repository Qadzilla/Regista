"""The pipeline as a Microsoft Agent Framework workflow: handoffs, parallelism, shared state, failure recovery,
human in the loop, and checkpoint resume. Verdicts here come from a test reviewer, never a real person."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from regista.agents import AgentError, Orchestrator, default_agents
from regista.agents.roles import LabelAgent, PersistAgent
from regista.agents.workflow import ReviewVerdicts, WorkflowPipeline
from regista.feedback import load_annotations
from regista.synth import generate

PLAYER = "t_home_09"


@pytest.fixture
def match_dir(tmp_path):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = tmp_path / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    return d


def _surname(match_dir):
    match = json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])
    return next(p["name"].split()[-1] for p in match["players"] if p["player_id"] == PLAYER)


def _req(match_dir, **kw):
    return {"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": kw.pop("queries", []), **kw}


def test_workflow_runs_end_to_end_and_matches_the_orchestrator(match_dir, tmp_path):
    q = [f"find me {_surname(match_dir)} doing a nutmeg"]
    wf = WorkflowPipeline(state_dir=match_dir / "agents", feedback_dir=tmp_path / "fb").run(_req(match_dir, queries=q))
    assert wf.ok, (wf.statuses, wf.dead_letters)
    assert set(wf.statuses) == {"ingest", "validator", "possession", "clip", "label", "review", "persist", "librarian"}
    # Same work as the hand-written orchestrator: same clips, same labels, same answer.
    ref = Orchestrator(default_agents(), tmp_path / "ref").run(_req(match_dir, queries=q))
    assert [c["id"] for c in wf.state["clips"][PLAYER]] == [c["id"] for c in ref.state["clips"][PLAYER]]
    assert [lb["title"] for lb in wf.state["labels"][PLAYER]] == [lb["title"] for lb in ref.state["labels"][PLAYER]]
    assert [r["clip_id"] for r in wf.state["answers"][0]["results"]] == [r["clip_id"] for r in ref.state["answers"][0]["results"]]
    # Trace files in the original format.
    rows = [json.loads(l) for l in (match_dir / "agents" / "trace.jsonl").read_text().splitlines()]
    assert {"at", "agent", "attempt", "status", "elapsed_ms"} <= set(rows[0])
    assert json.loads((match_dir / "agents" / "state.json").read_text())["clips"][PLAYER] == len(wf.state["clips"][PLAYER])


def test_validator_and_possession_run_in_parallel_then_join(match_dir, tmp_path):
    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir))
    order = [r["agent"] for r in wf.trace if r["status"] == "ok"]
    assert order[0] == "ingest"
    assert set(order[1:3]) == {"validator", "possession"}  # same superstep, either order
    assert order[3] == "clip"
    # Parallel roles wrote different state keys; neither overwrote the other.
    assert "validation" in wf.state and "on_ball" in wf.state


def test_retry_then_success(match_dir, tmp_path):
    calls = {"n": 0}

    @dataclass
    class FlakyLabel(LabelAgent):
        def handle(self, state):
            calls["n"] += 1
            if calls["n"] == 1:
                raise AgentError("model endpoint timed out", retryable=True)
            return super().handle(state)

    agents = [FlakyLabel() if a.role == "label" else a for a in default_agents()]
    wf = WorkflowPipeline(agents, tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir))
    assert wf.ok
    assert [r["status"] for r in wf.trace if r["agent"] == "label"] == ["retry", "ok"]
    assert calls["n"] == 2


def test_permanent_failure_routes_to_dead_letter_and_skips_the_rest(match_dir, tmp_path):
    @dataclass
    class BrokenLabel(LabelAgent):
        def handle(self, state):
            raise RuntimeError("labeller crashed")

    agents = [BrokenLabel() if a.role == "label" else a for a in default_agents()]
    wf = WorkflowPipeline(agents, tmp_path / "s", max_retries=2, feedback_dir=tmp_path / "fb").run(_req(match_dir, queries=["goal"]))
    assert not wf.ok and wf.output and wf.output.failed_role == "label"
    assert [r["status"] for r in wf.trace if r["agent"] == "label"] == ["retry", "retry", "failed"]
    assert wf.statuses["review"] == wf.statuses["persist"] == wf.statuses["librarian"] == "skipped"
    dead = [json.loads(l) for l in (tmp_path / "s" / "dead_letter.jsonl").read_text().splitlines()]
    assert dead[0]["agent"] == "label" and dead[0]["attempts"] == 3 and dead[0]["error"] == "RuntimeError: labeller crashed"
    assert wf.state["clips"][PLAYER], "work done before the failure survives"


def test_non_retryable_error_is_not_retried(match_dir, tmp_path):
    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(
        {"match_dir": str(match_dir), "player_ids": ["t_nobody_99"], "queries": []})
    assert [r["status"] for r in wf.trace if r["agent"] == "possession"] == ["failed"]
    assert wf.dead_letters[0]["retryable"] is False


def test_human_in_the_loop_pauses_records_verdicts_and_resumes(match_dir, tmp_path):
    fb = tmp_path / "fb"
    seen = []

    def reviewer(req):
        seen.append(req)
        return ReviewVerdicts(verdicts=[{"clip_id": i["clip_id"], "verdict": "drop", "note": "test"} for i in req.items],
                              annotator="test-reviewer")

    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=fb).run(_req(match_dir, review=True), reviewer=reviewer)
    assert wf.ok
    assert seen and seen[0].items, "the sample has a borderline clip the Label agent must ask about"
    statuses = [r["status"] for r in wf.trace if r["agent"] == "review"]
    assert statuses == ["waiting", "ok"]
    asked = {i["clip_id"] for i in seen[0].items}
    for lb in wf.state["labels"][PLAYER]:
        if lb["clip_id"] in asked:
            assert lb["watchability"] == 0.0 and "Reviewed by a person: dropped." in lb["explanation"]
            assert "test-reviewer" not in lb["explanation"] and "review" not in lb
    anns = load_annotations(fb / "annotations.jsonl")
    assert {a["context"]["clip_id"] for a in anns} == asked
    assert all(a["source"] == "human" and a["annotator"] == "test-reviewer" for a in anns)
    assert wf.state["review_log"]["retrained"]["skipped"].startswith("need at least")


def test_review_off_never_asks(match_dir, tmp_path):
    def reviewer(req):
        raise AssertionError("should not be asked")

    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir, review=False), reviewer=reviewer)
    assert wf.ok and not wf.pending


def test_paused_review_resumes_from_a_checkpoint_on_a_fresh_pipeline(match_dir, tmp_path):
    ckpt, fb = tmp_path / "ckpt", tmp_path / "fb"
    first = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=fb, checkpoint_dir=ckpt)
    paused = asyncio.run(first.start(_req(match_dir, review=True)))
    assert paused.paused and paused.pending[0].checkpoint_id
    assert json.loads((tmp_path / "s" / "pending_review.json").read_text())[0]["request_id"] == paused.pending[0].request_id
    # A new process: rebuild the pipeline and answer from the checkpoint on disk.
    second = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=fb, checkpoint_dir=ckpt)
    second._reset_files()
    p = paused.pending[0]
    done = asyncio.run(second.resume({p.request_id: {"verdicts": [{"clip_id": i["clip_id"], "verdict": "keep"} for i in p.request.items],
                                                     "annotator": "test-reviewer"}}, checkpoint_id=p.checkpoint_id))
    assert done.output and done.output.ok
    assert done.state["review_log"]["applied"]
    assert len(load_annotations(fb / "annotations.jsonl")) == len(p.request.items)


def test_runs_inside_a_running_event_loop(match_dir, tmp_path):
    """The API calls the pipeline from FastAPI's loop."""
    async def inside():
        return await WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").start(_req(match_dir))

    assert asyncio.run(inside()).ok


def test_graph_renders_to_mermaid(tmp_path):
    m = WorkflowPipeline(state_dir=tmp_path / "s").mermaid()
    assert m.startswith("flowchart TD")
    for node in ("ingest", "validator", "possession", "clip", "label", "review", "persist", "librarian", "finish", "dead_letter"):
        assert node in m
    assert "fan-in" in m


# ----------------------------------------------------------------------------- review findings (2026-10-20)

def test_a_failing_branch_does_not_mark_its_finished_sibling_skipped(match_dir, tmp_path):
    from regista.agents.roles import ValidatorAgent

    @dataclass
    class BrokenValidator(ValidatorAgent):
        def handle(self, state):
            raise AgentError("schema service down", retryable=False)

    agents = [BrokenValidator() if a.role == "validator" else a for a in default_agents()]
    wf = WorkflowPipeline(agents, tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir))
    assert wf.statuses["validator"] == "failed"
    assert wf.statuses["possession"] == "ok", "possession ran in parallel and must keep its own status"
    assert [r["status"] for r in wf.trace if r["agent"] == "possession"] == ["ok"]
    assert wf.statuses["clip"] == "skipped" and len(wf.dead_letters) == 1


def test_both_branches_failing_end_the_run_once(match_dir, tmp_path):
    from regista.agents.roles import PossessionAgent, ValidatorAgent

    @dataclass
    class BadV(ValidatorAgent):
        def handle(self, state):
            raise AgentError("v down", retryable=False)

    @dataclass
    class BadP(PossessionAgent):
        def handle(self, state):
            raise AgentError("p down", retryable=False)

    agents = [BadV() if a.role == "validator" else BadP() if a.role == "possession" else a for a in default_agents()]
    wf = WorkflowPipeline(agents, tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir))
    assert wf.statuses["validator"] == wf.statuses["possession"] == "failed"
    assert len(wf.dead_letters) == 2
    assert sum(1 for r in wf.trace if r["agent"] == "clip" and r["status"] == "skipped") == 1


def test_an_invalid_verdict_writes_nothing_and_dead_letters(match_dir, tmp_path):
    fb = tmp_path / "fb"

    def reviewer(req):
        good = {"clip_id": req.items[0]["clip_id"], "verdict": "keep"}
        bad = {"clip_id": req.items[0]["clip_id"], "verdict": "maybe"}
        return ReviewVerdicts(verdicts=[good, bad], annotator="test-reviewer")

    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=fb).run(_req(match_dir, review=True), reviewer=reviewer)
    assert not wf.ok and wf.output.failed_role == "review"
    assert not (fb / "annotations.jsonl").exists() or not load_annotations(fb / "annotations.jsonl")
    assert wf.statuses["persist"] == "skipped"


def test_a_verdict_for_a_clip_not_asked_about_is_rejected(match_dir, tmp_path):
    def reviewer(req):
        return ReviewVerdicts(verdicts=[{"clip_id": "cl_t_home_09_999999", "verdict": "keep"}], annotator="test-reviewer")

    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(_req(match_dir, review=True), reviewer=reviewer)
    assert not wf.ok and "not asked about" in wf.dead_letters[0]["error"]


def test_a_missing_match_dead_letters_instead_of_crashing(tmp_path):
    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb").run(
        {"match_dir": str(tmp_path / "nope"), "player_ids": [PLAYER], "queries": []})
    assert not wf.ok and wf.statuses["ingest"] == "failed" and "does not exist" in wf.dead_letters[0]["error"]


def test_the_pipeline_feedback_dir_reaches_the_label_agent(match_dir, tmp_path):
    """A model trained elsewhere must not leak into a pipeline pointed at an empty feedback folder."""
    import os
    from regista.feedback import WatchabilityModel

    elsewhere = tmp_path / "elsewhere"
    WatchabilityModel(feature_names=["tag:goal"], coef=[3.0], intercept=-1.0, n_samples=9, version=4).save(elsewhere / "watchability-model.json")
    os.environ["REGISTA_FEEDBACK_DIR"] = str(elsewhere)  # the conftest fixture restores it after the test
    wf = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "empty").run(_req(match_dir))
    assert {lb["model"] for lb in wf.state["labels"][PLAYER]} == {"rules-v0"}
    wf2 = WorkflowPipeline(state_dir=tmp_path / "s2", feedback_dir=elsewhere).run(_req(match_dir))
    assert {lb["model"] for lb in wf2.state["labels"][PLAYER]} == {"learned-v4 (9 verdicts)"}


def test_reusing_a_pipeline_does_not_leak_the_previous_run(match_dir, tmp_path):
    p = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb")

    def reviewer(req):
        return ReviewVerdicts(verdicts=[{"clip_id": i["clip_id"], "verdict": "keep"} for i in req.items], annotator="test-reviewer")

    first = p.run(_req(match_dir, review=True), reviewer=reviewer)
    assert first.state.get("review_log")
    second = p.run(_req(match_dir, review=False))
    assert second.ok and "review_log" not in second.state
    assert not (tmp_path / "s" / "pending_review.json").exists()


def test_resume_on_a_fresh_pipeline_needs_no_private_calls(match_dir, tmp_path):
    ckpt = tmp_path / "ckpt"
    paused = asyncio.run(WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb", checkpoint_dir=ckpt).start(_req(match_dir, review=True)))
    p = paused.pending[0]
    fresh = WorkflowPipeline(state_dir=tmp_path / "s", feedback_dir=tmp_path / "fb", checkpoint_dir=ckpt)
    done = asyncio.run(fresh.resume({p.request_id: {"verdicts": [], "annotator": "test-reviewer"}}, checkpoint_id=p.checkpoint_id))
    assert done.ok
    agents = [r["agent"] for r in done.trace]
    assert agents[0] == "ingest", "the resumed trace continues the one written before the pause"
