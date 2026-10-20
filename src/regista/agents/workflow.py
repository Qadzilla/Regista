"""Regista's agent pipeline as a Microsoft Agent Framework workflow.

The same roles as ``regista.agents.roles`` (and their Foundry and Cosmos DB variants), wired as
Agent Framework executors in a graph:

    ingest ──┬── validator ──┐
             └── possession ─┴─▶ clip ─▶ label ─▶ review ─▶ persist ─▶ librarian ─▶ finish
                                                    ▲  │
       every role ── DeadLetter ──▶ dead_letter     └──┘ pauses for a human verdict when the
                                                         Label agent is unsure (request_info)

What Agent Framework provides here, and what the tests prove:
- **Typed handoffs.** Roles send ``Handoff`` messages; a failing role sends ``DeadLetter``, which only
  the ``dead_letter`` executor accepts, so failures route themselves.
- **Parallelism.** Validation and possession analysis fan out from ingest and fan back in at the clip role.
- **Shared state.** Every pipeline value lives in workflow state under its own key, so parallel roles never
  overwrite each other. The large, rebuildable stream index is cached per match instead of copied.
- **Failure recovery.** Retryable errors are retried in the role; exhausted or non-retryable ones dead-letter
  with the remaining roles recorded as skipped.
- **Human in the loop.** The review executor asks for verdicts with ``ctx.request_info`` and resumes in its
  ``@response_handler``; verdicts are stored as human annotations and retrain the watchability model.
- **Checkpointing.** With a checkpoint directory, a paused review survives a restart and resumes from disk.
- **Visualisation.** ``mermaid()`` renders the graph for the docs.

The trace (``trace.jsonl``), dead letters, and state summary keep the exact format of the original
orchestrator, so tools that read them do not care which engine ran.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_framework import (Executor, FileCheckpointStorage, WorkflowBuilder, WorkflowContext, WorkflowEvent, WorkflowViz, handler,
                             register_checkpoint_type, response_handler)
from typing_extensions import Never

from regista.agents.base import Agent, AgentError
from regista.agents.orchestrator import RunResult, summarise_state
from regista.agents.roles import default_agents
from regista.aio import run_sync
from regista.clips import StreamIndex
from regista.schema import iter_jsonl

Record = dict[str, Any]
WORKFLOW_NAME = "regista-pipeline"
TRACE_EVENT = "regista_trace"
DEAD_EVENT = "regista_dead_letter"
HEAVY_KEYS = ("stream", "index")           # rebuildable from match_dir; kept out of workflow state
ROLE_ORDER = ["ingest", "validator", "possession", "clip", "label", "review", "persist", "librarian"]


# ---------------------------------------------------------------------------- messages

@dataclass
class PipelineRequest:
    match_dir: str
    player_ids: list[str]
    queries: list[str] = field(default_factory=list)
    review: bool = False
    annotator: str = "zaid"
    run_id: str = ""


@dataclass
class Handoff:
    from_role: str
    run_id: str


@dataclass
class DeadLetter:
    role: str
    error: str
    retryable: bool
    attempts: int
    inputs: dict[str, Any]
    run_id: str


@dataclass
class ReviewRequest:
    """What the review executor asks the human: the clips the Label agent was unsure about."""

    question: str
    items: list[dict[str, Any]]


@dataclass
class ReviewVerdicts:
    """The human's answer: one entry per clip, {"clip_id", "verdict": keep|drop|fix, "watchability"?, "tags"?, "note"?}."""

    verdicts: list[dict[str, Any]]
    annotator: str = "zaid"


@dataclass
class PipelineOutput:
    ok: bool
    state: dict[str, Any]
    failed_role: str | None = None


for _t in (PipelineRequest, Handoff, DeadLetter, ReviewRequest, ReviewVerdicts, PipelineOutput):
    register_checkpoint_type(_t)


# ---------------------------------------------------------------------------- state helpers

_INDEX_CACHE: dict[str, tuple[float, list[Record], StreamIndex]] = {}


def stream_and_index(match_dir: str) -> tuple[list[Record], StreamIndex]:
    """The parsed stream and its index, cached per match file (rebuilt if the file changes)."""
    path = Path(match_dir) / "events.jsonl"
    mtime = path.stat().st_mtime
    hit = _INDEX_CACHE.get(match_dir)
    if hit and hit[0] == mtime:
        return hit[1], hit[2]
    stream = list(iter_jsonl(path))
    index = StreamIndex.build(stream)
    _INDEX_CACHE[match_dir] = (mtime, stream, index)
    return stream, index


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _size(value: Any) -> int | None:
    return len(value) if isinstance(value, (list, dict, str)) else None


def _key(name: str) -> str:
    return f"p.{name}"


def _known_keys(agents: list[Agent]) -> list[str]:
    keys = {"match_dir", "player_ids", "queries", "review", "annotator", "match", "record_counts", "label_notes", "review_log"}
    for a in agents:
        keys.update(a.inputs)
        keys.update(a.outputs)
    return sorted(k for k in keys if k not in HEAVY_KEYS)


def _read_state(ctx: WorkflowContext, keys: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for k in keys:
        v = ctx.get_state(_key(k), None)
        if v is not None:
            state[k] = v
    return state


def _write_changes(ctx: WorkflowContext, before: dict[str, Any], after: dict[str, Any]) -> None:
    """Write only the keys this role changed, each under its own state key, so parallel roles never collide."""
    for k, v in after.items():
        if k in HEAVY_KEYS:
            continue
        if k not in before or before[k] != v:
            ctx.set_state(_key(k), v)


# ---------------------------------------------------------------------------- executors

class RoleExecutor(Executor):
    """Runs one Regista role (an ``Agent``) as a workflow step, with retries and dead-lettering."""

    def __init__(self, agent: Agent, keys: list[str], max_retries: int = 2):
        super().__init__(id=agent.role)
        self.agent = agent
        self.keys = keys
        self.max_retries = max_retries

    @handler
    async def start(self, request: PipelineRequest, ctx: WorkflowContext[Handoff | DeadLetter]) -> None:
        for k, v in (("match_dir", request.match_dir), ("player_ids", request.player_ids), ("queries", request.queries),
                     ("review", request.review), ("annotator", request.annotator), ("run_id", request.run_id)):
            ctx.set_state(_key(k), v)
        await self._run(ctx, request.run_id)

    @handler
    async def step(self, message: Handoff, ctx: WorkflowContext[Handoff | DeadLetter]) -> None:
        await self._run(ctx, message.run_id)

    @handler
    async def join(self, messages: list[Handoff], ctx: WorkflowContext[Handoff | DeadLetter]) -> None:
        await self._run(ctx, messages[0].run_id)

    async def _run(self, ctx: WorkflowContext, run_id: str) -> None:
        agent = self.agent
        before = _read_state(ctx, self.keys)
        state = copy.deepcopy(before)
        if "match_dir" in state and ({"stream", "index"} & set(agent.inputs) or agent.role == "ingest"):
            state["stream"], state["index"] = stream_and_index(state["match_dir"])
        missing = agent.missing_inputs(state)
        if missing:
            await self._dead(ctx, run_id, 0, AgentError(f"missing inputs: {missing}", retryable=False), state)
            return
        for attempt in range(1, self.max_retries + 2):
            started = time.perf_counter()
            snapshot = {k: _size(state.get(k)) for k in agent.inputs}
            try:
                result = await asyncio.to_thread(agent.handle, dict(state))
                not_written = agent.missing_outputs(result)
                if not_written:
                    raise AgentError(f"{agent.role} promised {agent.outputs} but did not write {not_written}", retryable=False)
                _write_changes(ctx, before, result)
                await self._trace(ctx, attempt, "ok", started, records_in=snapshot,
                                  records_out={k: _size(result.get(k)) for k in agent.outputs}, keys=result)
                await ctx.send_message(Handoff(from_role=agent.role, run_id=run_id))
                return
            except Exception as exc:  # noqa: BLE001 - every failure is recorded, whatever it is
                retryable = getattr(exc, "retryable", True)
                last = attempt == self.max_retries + 1 or not retryable
                await self._trace(ctx, attempt, "failed" if last else "retry", started, error=f"{type(exc).__name__}: {exc}", keys=state)
                if last:
                    await self._dead(ctx, run_id, attempt, exc, state, traced=True)
                    return

    async def _trace(self, ctx: WorkflowContext, attempt: int, status: str, started: float | None, *, error: str | None = None,
                     records_in: dict | None = None, records_out: dict | None = None, keys: dict | None = None) -> None:
        row = {"at": _now(), "agent": self.agent.role, "attempt": attempt, "status": status,
               "elapsed_ms": round((time.perf_counter() - started) * 1000, 1) if started else None,
               "records_in": records_in, "records_out": records_out, "error": error, "state_keys": sorted(keys or {})}
        await ctx.add_event(WorkflowEvent(TRACE_EVENT, data=row))

    async def _dead(self, ctx: WorkflowContext, run_id: str, attempts: int, exc: BaseException, state: dict, traced: bool = False) -> None:
        if not traced:
            await self._trace(ctx, attempts, "failed", None, error=f"{type(exc).__name__}: {exc}", keys=state)
        await ctx.send_message(DeadLetter(role=self.agent.role, error=f"{type(exc).__name__}: {exc}",
                                          retryable=getattr(exc, "retryable", True), attempts=attempts,
                                          inputs={k: _size(state.get(k)) for k in self.agent.inputs}, run_id=run_id))


class ReviewExecutor(Executor):
    """Asks a human about the clips the Label agent flagged, then records the verdicts and applies them."""

    def __init__(self, keys: list[str], feedback_dir: Path | None = None, retrain: bool = True):
        super().__init__(id="review")
        self.keys = keys
        self.feedback_dir = feedback_dir
        self.retrain = retrain

    @handler
    async def check(self, message: Handoff, ctx: WorkflowContext[Handoff]) -> None:
        state = _read_state(ctx, self.keys)
        flagged = []
        for pid, labels in (state.get("labels") or {}).items():
            clips = {c["id"]: c for c in state.get("clips", {}).get(pid, [])}
            for lb in labels:
                if lb.get("review") and lb["clip_id"] in clips:
                    c = clips[lb["clip_id"]]
                    flagged.append({"clip_id": c["id"], "player_id": pid, "title": lb["title"], "tags": lb["tags"],
                                    "watchability": lb["watchability"], "prior_watchability": lb.get("prior_watchability"),
                                    "reason": lb["review"], "t": c["t"], "t_end": c["t_end"], "cut": c["reason"]})
        if not state.get("review") or not flagged:
            note = "review off" if not state.get("review") else "no clips flagged"
            await ctx.add_event(WorkflowEvent(TRACE_EVENT, data=self._row("ok", note=note, flagged=len(flagged))))
            await ctx.send_message(Handoff(from_role="review", run_id=message.run_id))
            return
        ctx.set_state(_key("review_run_id"), message.run_id)
        await ctx.add_event(WorkflowEvent(TRACE_EVENT, data=self._row("waiting", note=f"asked a human about {len(flagged)} clip(s)",
                                                                      flagged=len(flagged))))
        await ctx.request_info(ReviewRequest(question=f"Keep, drop, or fix these {len(flagged)} clip(s)?", items=flagged), ReviewVerdicts)

    @response_handler
    async def on_verdicts(self, request: ReviewRequest, answer: ReviewVerdicts, ctx: WorkflowContext[Handoff]) -> None:
        from regista.feedback import ANNOTATIONS_FILE, FEEDBACK_DIR, WatchabilityModel, load_annotations, record_verdict, train

        state = _read_state(ctx, self.keys)
        fdir = Path(self.feedback_dir or FEEDBACK_DIR)
        clips = {c["id"]: c for cs in state.get("clips", {}).values() for c in cs}
        labels = state.get("labels", {})
        by_clip = {v["clip_id"]: v for v in answer.verdicts}
        applied = []
        for pid, ls in labels.items():
            for lb in ls:
                v = by_clip.get(lb["clip_id"])
                if v is None:
                    continue
                verdict = v.get("verdict", "keep")
                rec = record_verdict(clips[lb["clip_id"]], lb, verdict, watchability=v.get("watchability"), tags=v.get("tags"),
                                     note=v.get("note", ""), annotator=answer.annotator, path=fdir / ANNOTATIONS_FILE)
                if verdict == "drop":
                    lb["watchability"] = 0.0
                elif v.get("watchability") is not None:
                    lb["watchability"] = round(float(v["watchability"]), 3)
                if v.get("tags"):
                    lb["tags"] = rec["correction"]["tags"] + [t for t in lb["tags"] if t.endswith("_appearance") or t == "on_ball_main"]
                lb["explanation"] = f"{lb['explanation']} Reviewed by {answer.annotator}: {verdict}."
                lb.pop("review", None)
                applied.append({"clip_id": lb["clip_id"], "verdict": verdict, "annotation_id": rec["id"]})
        retrained = None
        if self.retrain:
            try:
                previous = WatchabilityModel.load(fdir / "watchability-model.json")
                model = train(load_annotations(fdir / ANNOTATIONS_FILE), previous=previous)
                model.save(fdir / "watchability-model.json")
                retrained = {"model": model.name, "metrics": model.metrics}
            except ValueError as exc:
                retrained = {"skipped": str(exc)}
        ctx.set_state(_key("labels"), labels)
        ctx.set_state(_key("review_log"), {"applied": applied, "retrained": retrained, "annotator": answer.annotator})
        await ctx.add_event(WorkflowEvent(TRACE_EVENT, data=self._row("ok", note=f"applied {len(applied)} verdict(s)", flagged=len(request.items))))
        await ctx.send_message(Handoff(from_role="review", run_id=ctx.get_state(_key("review_run_id"), "")))

    @staticmethod
    def _row(status: str, *, note: str, flagged: int) -> Record:
        return {"at": _now(), "agent": "review", "attempt": 1, "status": status, "elapsed_ms": None,
                "records_in": {"flagged": flagged}, "records_out": None, "error": None, "state_keys": [], "note": note}


class FinishExecutor(Executor):
    def __init__(self, keys: list[str]):
        super().__init__(id="finish")
        self.keys = keys

    @handler
    async def finish(self, message: Handoff, ctx: WorkflowContext[Never, PipelineOutput]) -> None:
        await ctx.yield_output(PipelineOutput(ok=True, state=_read_state(ctx, self.keys)))


class DeadLetterExecutor(Executor):
    """Receives any role's DeadLetter, records the roles that will not run, and ends the run with the work done so far."""

    def __init__(self, keys: list[str], order: list[str]):
        super().__init__(id="dead_letter")
        self.keys = keys
        self.order = order

    @handler
    async def receive(self, letter: DeadLetter, ctx: WorkflowContext[Never, PipelineOutput]) -> None:
        await ctx.add_event(WorkflowEvent(DEAD_EVENT, data={"at": _now(), "agent": letter.role, "attempts": letter.attempts,
                                                             "error": letter.error, "retryable": letter.retryable, "inputs": letter.inputs}))
        if letter.role in self.order:
            for role in self.order[self.order.index(letter.role) + 1:]:
                await ctx.add_event(WorkflowEvent(TRACE_EVENT, data={
                    "at": _now(), "agent": role, "attempt": 0, "status": "skipped", "elapsed_ms": None, "records_in": None,
                    "records_out": None, "error": f"upstream {letter.role} failed", "state_keys": []}))
        await ctx.yield_output(PipelineOutput(ok=False, state=_read_state(ctx, self.keys), failed_role=letter.role))


# ---------------------------------------------------------------------------- the pipeline

@dataclass
class PendingReview:
    request_id: str
    request: ReviewRequest
    checkpoint_id: str | None = None


@dataclass
class WorkflowRun(RunResult):
    pending: list[PendingReview] = field(default_factory=list)
    output: PipelineOutput | None = None

    @property
    def paused(self) -> bool:
        return bool(self.pending)


class WorkflowPipeline:
    """Builds and runs the Agent Framework workflow, writing the same trace files as the original orchestrator."""

    def __init__(self, agents: list[Agent] | None = None, state_dir: Path | str = "agents", *, max_retries: int = 2,
                 feedback_dir: Path | str | None = None, checkpoint_dir: Path | str | None = None, retrain: bool = True):
        self.agents = agents or default_agents()
        self.by_role = {a.role: a for a in self.agents}
        self.state_dir = Path(state_dir)
        self.max_retries = max_retries
        self.feedback_dir = Path(feedback_dir) if feedback_dir else None
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else None
        self.retrain = retrain
        self.keys = _known_keys(self.agents) + ["run_id", "review_run_id"]
        self.workflow = self.build()

    def build(self):
        roles = {r: RoleExecutor(self.by_role[r], self.keys, self.max_retries) for r in self.by_role}
        review = ReviewExecutor(self.keys, self.feedback_dir, self.retrain)
        finish = FinishExecutor(self.keys)
        order = [r for r in ROLE_ORDER if r in roles or r == "review"]
        dead = DeadLetterExecutor(self.keys, order)
        storage = FileCheckpointStorage(self.checkpoint_dir) if self.checkpoint_dir else None
        b = WorkflowBuilder(name=WORKFLOW_NAME, description="Regista: broadcast match in, labelled clip library out.",
                            start_executor=roles["ingest"], checkpoint_storage=storage, output_from=[finish, dead])
        b.add_fan_out_edges(roles["ingest"], [roles["validator"], roles["possession"]])
        b.add_fan_in_edges([roles["validator"], roles["possession"]], roles["clip"])
        b.add_chain([roles["clip"], roles["label"], review, roles["persist"], roles["librarian"], finish])
        for ex in roles.values():
            b.add_edge(ex, dead)  # only DeadLetter messages reach it; handoffs are routed by type to the next role
        return b.build()

    def mermaid(self) -> str:
        return WorkflowViz(self.workflow).to_mermaid()

    # -- running
    async def start(self, initial: dict[str, Any]) -> WorkflowRun:
        req = PipelineRequest(match_dir=str(initial["match_dir"]), player_ids=list(initial["player_ids"]),
                              queries=list(initial.get("queries", [])), review=bool(initial.get("review", False)),
                              annotator=initial.get("annotator", "zaid"), run_id=initial.get("run_id") or uuid.uuid4().hex[:12])
        self._reset_files()
        events = await self.workflow.run(req)
        return await self._collect(events)

    async def resume(self, answers: dict[str, ReviewVerdicts | dict], checkpoint_id: str | None = None) -> WorkflowRun:
        responses = {rid: (a if isinstance(a, ReviewVerdicts) else ReviewVerdicts(**a)) for rid, a in answers.items()}
        if checkpoint_id:
            events = await self.workflow.run(checkpoint_id=checkpoint_id, responses=responses)
        else:
            events = await self.workflow.run(responses=responses)
        return await self._collect(events)

    def run(self, initial: dict[str, Any], reviewer: Callable[[ReviewRequest], ReviewVerdicts] | None = None) -> WorkflowRun:
        """Synchronous convenience: run to completion, answering review requests with ``reviewer`` if given."""

        async def go() -> WorkflowRun:
            result = await self.start(initial)
            while result.paused and reviewer is not None:
                result = await self.resume({p.request_id: reviewer(p.request) for p in result.pending})
            return result

        return run_sync(go())

    # -- files
    def _reset_files(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        for name in ("trace.jsonl", "dead_letter.jsonl"):
            (self.state_dir / name).write_text("", encoding="utf-8")
        self._trace: list[Record] = []
        self._dead: list[Record] = []

    async def _collect(self, events) -> WorkflowRun:
        pending: list[PendingReview] = []
        for ev in events:
            if ev.type == TRACE_EVENT:
                self._trace.append(ev.data)
                with (self.state_dir / "trace.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ev.data) + "\n")
            elif ev.type == DEAD_EVENT:
                self._dead.append(ev.data)
                with (self.state_dir / "dead_letter.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(ev.data) + "\n")
            elif ev.type == "request_info":
                pending.append(PendingReview(request_id=ev.request_id, request=ev.data))
        if pending and self.checkpoint_dir:
            storage = FileCheckpointStorage(self.checkpoint_dir)
            latest = await storage.get_latest(workflow_name=WORKFLOW_NAME)
            for p in pending:
                p.checkpoint_id = latest.checkpoint_id if latest else None
        outputs = [o for o in events.get_outputs() if isinstance(o, PipelineOutput)]
        output = outputs[-1] if outputs else None
        state = dict(output.state) if output else {}
        if output:
            (self.state_dir / "state.json").write_text(json.dumps(summarise_state(state), indent=2, default=str) + "\n", encoding="utf-8")
        else:
            (self.state_dir / "pending_review.json").write_text(json.dumps([{"request_id": p.request_id, "checkpoint_id": p.checkpoint_id,
                                                                           "request": asdict(p.request)} for p in pending], indent=2) + "\n",
                                                                         encoding="utf-8")
        return WorkflowRun(state=state, trace=list(self._trace), dead_letters=list(self._dead), state_dir=self.state_dir,
                           pending=pending, output=output)
