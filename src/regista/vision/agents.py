"""The vision layer as Regista agent roles, wired as a Microsoft Agent Framework workflow.

Roles (``regista.agents.base.Agent`` subclasses, same contract as ``regista.agents.roles``):

    shots ─▶ identity ─▶ possession_vision ─▶ vision_writer
      │         │              │                   │
      └─────────┴──────────────┴─── DeadLetter ────┴─▶ dead_letter

- ``shots``: video -> ``camera_segment`` records (trained shot model).
- ``identity``: video + roster + segments -> named player and ball positions per main frame, and
  who appears in each cutaway. The full result is large, so it goes to ``work_dir`` and the state
  carries its path and a summary (the same reason the main workflow keeps the stream index out of
  workflow state).
- ``possession_vision``: identity -> ``possession`` records.
- ``vision_writer``: everything -> a validated match directory (``match_dir``) that the
  intelligence-layer workflow (``regista.agents.workflow``) takes as its input.

``build_vision_workflow`` reuses ``RoleExecutor``, ``FinishExecutor`` and ``DeadLetterExecutor``
from ``regista.agents.workflow``, so retries, dead-lettering, typed handoffs and the trace format
are identical to the intelligence pipeline's. The only new executor is the start node, which puts
the video path and roster into workflow state.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, WorkflowViz, handler, register_checkpoint_type

from regista.agents.base import Agent, AgentError, State
from regista.agents.workflow import DEAD_EVENT, TRACE_EVENT, DeadLetterExecutor, FinishExecutor, Handoff, PipelineOutput, RoleExecutor
from regista.agents.workflow import state_key as _key
from regista.aio import run_sync
from regista.vision.shots import DEFAULT_MODELS_DIR

Record = dict[str, Any]
VISION_WORKFLOW_NAME = "regista-vision"
VISION_ROLE_ORDER = ["shots", "identity", "possession_vision", "vision_writer"]

_MODEL_CACHE: dict[tuple[str, str], Any] = {}


def _cached(kind: str, models_dir: str):
    key = (kind, str(Path(models_dir).resolve()))
    if key not in _MODEL_CACHE:
        if kind == "shots":
            from regista.vision.shots import ShotModel

            _MODEL_CACHE[key] = ShotModel.load(models_dir)
        else:
            from regista.vision.kitnumber import DigitClassifierReader

            _MODEL_CACHE[key] = DigitClassifierReader.load(models_dir)
    return _MODEL_CACHE[key]


def _not_retryable(handle):
    """Vision work is deterministic: a decode error or a bug fails the same way on a second try, and a retry
    of the identity pass costs minutes. Anything that is not already an ``AgentError`` dead-letters at once."""
    def wrapped(self, state: State) -> State:
        try:
            return handle(self, state)
        except AgentError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported in the dead letter with its type
            raise AgentError(f"{type(exc).__name__}: {exc}", retryable=False) from exc
    wrapped.__doc__ = handle.__doc__
    return wrapped


def _work_dir(state: State) -> Path:
    d = Path(state.get("work_dir") or (Path(state["out_dir"]) / ".vision_work"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _match_id(state: State) -> str:
    return state.get("match_id") or f"{state['roster'].get('match_id', Path(state['video_path']).stem)}_vision"


@dataclass
class ShotsAgent(Agent):
    role: str = "shots"
    inputs: tuple[str, ...] = ("video_path",)
    outputs: tuple[str, ...] = ("camera_segments",)
    description: str = "Cuts the broadcast into shots and classifies each (main, replay, highlight, closeup, crowd, graphic)."

    @_not_retryable
    def handle(self, state: State) -> State:
        from regista.vision.shots import segments_to_records

        video = Path(state["video_path"])
        if not video.exists():
            raise AgentError(f"{video} does not exist", retryable=False)
        # config["segments"] supplies known shot boundaries (evaluations that score identity on true segments).
        segments = self.config.get("segments")
        if not segments:
            model = self.config.get("shot_model") or _cached("shots", self.config.get("models_dir", str(DEFAULT_MODELS_DIR)))
            segments = model.predict(video)
        state["camera_segments"] = segments_to_records(segments, _match_id(state))
        return state


@dataclass
class IdentityAgent(Agent):
    role: str = "identity"
    inputs: tuple[str, ...] = ("video_path", "roster", "camera_segments")
    outputs: tuple[str, ...] = ("identity_path", "identity_summary")
    description: str = ("Detects players and the ball in main-camera frames, reads kit numbers, maps to pitch metres, tracks and "
                        "names players; finds who appears in each replay, highlight and closeup.")

    @_not_retryable
    def handle(self, state: State) -> State:
        import joblib

        from regista.vision.identity import IdentityConfig, run_identity

        reader = self.config.get("reader") or _cached("reader", self.config.get("models_dir", str(DEFAULT_MODELS_DIR)))
        cfg = self.config.get("identity_cfg") or IdentityConfig.load(self.config.get("models_dir", str(DEFAULT_MODELS_DIR)))
        segs = [{"id": r["id"], "t": r["t"], "t_end": r["t_end"], "kind": r["kind"]} for r in state["camera_segments"]]
        result = run_identity(state["video_path"], state["roster"], segs, reader, cfg)
        path = _work_dir(state) / "identity.joblib"
        joblib.dump(result, path)
        state["identity_path"] = str(path)
        state["identity_summary"] = {k: v for k, v in result.info.items() if k != "video"} | {"cutaway_segments": len(result.cutaway)}
        return state


@dataclass
class PossessionVisionAgent(Agent):
    role: str = "possession_vision"
    inputs: tuple[str, ...] = ("identity_path", "roster")
    outputs: tuple[str, ...] = ("possessions",)
    description: str = "Decides who is on the ball from ball and player positions over time; writes possession records."

    @_not_retryable
    def handle(self, state: State) -> State:
        import joblib

        from regista.vision.possession import PossessionConfig, infer_possessions

        result = joblib.load(state["identity_path"])
        cfg = self.config.get("possession_cfg") or PossessionConfig()
        state["possessions"] = infer_possessions(result.frames, state["roster"], _match_id(state), cfg,
                                                 fps=result.info.get("sample_fps", 5.0),
                                                 segment_end={r["id"]: r["t_end"] for r in state["camera_segments"]})
        return state


@dataclass
class VisionWriterAgent(Agent):
    role: str = "vision_writer"
    inputs: tuple[str, ...] = ("video_path", "roster", "out_dir", "camera_segments", "identity_path", "possessions")
    outputs: tuple[str, ...] = ("match_dir", "vision_summary")
    description: str = "Writes events.jsonl + tracks.jsonl + manifest.json and validates them against the event contract."

    @_not_retryable
    def handle(self, state: State) -> State:
        import joblib

        from regista.vision.frames import probe
        from regista.vision.pipeline import write_match_dir

        result = joblib.load(state["identity_path"])
        summary = write_match_dir(state["out_dir"], state["roster"], probe(state["video_path"]), _match_id(state),
                                  state["camera_segments"], result, state["possessions"], self.config.get("track_hz", 2.0))
        bad = {k: v for k, v in summary["validation"].items() if v}
        if bad:
            raise AgentError(f"vision output failed schema validation: {bad}", retryable=False)
        state["match_dir"] = str(state["out_dir"])
        state["vision_summary"] = {k: summary[k] for k in ("match_id", "record_counts", "segments", "validation")}
        return state


def vision_agents(config: dict[str, Any] | None = None) -> list[Agent]:
    """The four vision roles sharing one config (``models_dir``, or preloaded ``shot_model`` / ``reader``)."""
    cfg = dict(config or {})
    return [ShotsAgent(config=cfg), IdentityAgent(config=cfg), PossessionVisionAgent(config=cfg), VisionWriterAgent(config=cfg)]


# ---------------------------------------------------------------------------- Agent Framework workflow

@dataclass
class VisionRequest:
    video_path: str
    roster: dict[str, Any]
    out_dir: str
    work_dir: str = ""
    match_id: str = ""
    run_id: str = ""


@dataclass
class VisionRun:
    ok: bool
    state: dict[str, Any]
    trace: list[dict[str, Any]] = field(default_factory=list)
    dead_letters: list[dict[str, Any]] = field(default_factory=list)
    failed_role: str | None = None


def _state_keys(agents: list[Agent]) -> list[str]:
    keys = {"video_path", "roster", "out_dir", "work_dir", "match_id", "run_id"}
    for a in agents:
        keys.update(a.inputs)
        keys.update(a.outputs)
    return sorted(keys)


class VisionStartExecutor(Executor):
    """Puts the request (video path, roster, output paths) into workflow state and hands off to the shot agent."""

    def __init__(self) -> None:
        super().__init__(id="vision_start")

    @handler
    async def start(self, request: VisionRequest, ctx: WorkflowContext[Handoff]) -> None:
        run_id = request.run_id or uuid.uuid4().hex[:12]
        values = {"video_path": request.video_path, "roster": request.roster, "out_dir": request.out_dir,
                  "work_dir": request.work_dir or str(Path(request.out_dir) / ".vision_work"),
                  "match_id": request.match_id or f"{request.roster.get('match_id', Path(request.video_path).stem)}_vision",
                  "run_id": run_id}
        for k, v in values.items():
            ctx.set_state(_key(k), v)
        await ctx.send_message(Handoff(from_role="vision_start", run_id=run_id))


register_checkpoint_type(VisionRequest)


def build_vision_workflow(agents: list[Agent] | None = None, *, max_retries: int = 1, config: dict[str, Any] | None = None):
    """Wire the vision roles as an Agent Framework workflow. Returns ``(workflow, keys)``.

    Start it with ``await workflow.run(VisionRequest(video_path=..., roster=match_header, out_dir=...))``,
    or use ``run_vision_workflow`` for the synchronous, trace-collecting version."""
    agents = agents or vision_agents(config)
    by_role = {a.role: a for a in agents}
    missing = [r for r in VISION_ROLE_ORDER if r not in by_role]
    if missing:
        raise ValueError(f"vision workflow needs roles {missing}")
    keys = _state_keys(agents)
    start = VisionStartExecutor()
    roles = {r: RoleExecutor(by_role[r], keys, max_retries) for r in VISION_ROLE_ORDER}
    finish = FinishExecutor(keys)
    dead = DeadLetterExecutor(keys, VISION_ROLE_ORDER)
    b = WorkflowBuilder(name=VISION_WORKFLOW_NAME, description="Regista vision layer: broadcast video in, event stream out.",
                        start_executor=start, output_from=[finish, dead])
    b.add_chain([start] + [roles[r] for r in VISION_ROLE_ORDER] + [finish])
    for ex in roles.values():
        b.add_edge(ex, dead)  # only DeadLetter messages reach it
    return b.build(), keys


def run_vision_workflow(initial: dict[str, Any], *, agents: list[Agent] | None = None, config: dict[str, Any] | None = None,
                        state_dir: Path | str | None = None, max_retries: int = 1) -> VisionRun:
    """Run the vision workflow to completion. ``initial`` holds ``video_path``, ``roster`` (a match header) and ``out_dir``."""
    workflow, _keys = build_vision_workflow(agents, max_retries=max_retries, config=config)
    req = VisionRequest(video_path=str(initial["video_path"]), roster=initial["roster"], out_dir=str(initial["out_dir"]),
                        work_dir=str(initial.get("work_dir", "")), match_id=str(initial.get("match_id", "")),
                        run_id=str(initial.get("run_id", "")))

    async def go():
        return await workflow.run(req)

    events = run_sync(go())
    trace = [ev.data for ev in events if ev.type == TRACE_EVENT]
    dead = [ev.data for ev in events if ev.type == DEAD_EVENT]
    outputs = [o for o in events.get_outputs() if isinstance(o, PipelineOutput)]
    out = outputs[-1] if outputs else None
    state = dict(out.state) if out else {}
    run = VisionRun(ok=bool(out and out.ok), state=state, trace=trace, dead_letters=dead, failed_role=out.failed_role if out else None)
    if state_dir:
        sd = Path(state_dir)
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "trace.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in trace), encoding="utf-8")
        (sd / "dead_letter.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in dead), encoding="utf-8")
    return run


def mermaid(config: dict[str, Any] | None = None) -> str:
    workflow, _ = build_vision_workflow(config=config or {"models_dir": str(DEFAULT_MODELS_DIR)})
    return WorkflowViz(workflow).to_mermaid()
