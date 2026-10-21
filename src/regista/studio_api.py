"""Regista Studio: the control room. Everything Zaid (and Claude) needs to see and do, behind the Studio keys.

The page at ``/studio`` is public HTML with no data in it; every ``/api/studio/*`` endpoint needs the Studio view key or
the admin key (regista.access), and anything that changes state needs the admin key. The same code runs locally and on
the live app: ``capabilities`` says what this deployment can do, so local-only sections (vision jobs) say so on Azure
instead of failing. The facts come from regista.studio.facts and the jobs from regista.studio.jobs.

Endpoints
---------
GET  /studio                    the Studio page
GET  /api/studio/session        the caller's role (open, view, admin) and this deployment's capabilities  [studio]
GET  /api/studio/overview       the front page in one call: role, capabilities, health, to-do, usage, data, cache [studio]
GET  /api/studio/runs           every match with its last pipeline run (summary per agent)                [studio]
GET  /api/studio/runs/{match_id}   one match's last run: per-agent summary and every trace row             [studio]
GET  /api/studio/data           documents per Cosmos DB container and in the Search index (cached 60 s)   [studio]
GET  /api/studio/usage          Ask and Chat Foundry questions against their limits                      [studio]
GET  /api/studio/cache          render cache per match and prerender progress                            [studio]
GET  /api/studio/jobs           vision jobs (local only): what can run, what is running, past jobs       [studio]
POST /api/studio/jobs           start one: {"kind": ..., "args": {...}}; 409 on the cloud or while busy   [write]
GET  /api/studio/jobs/{job_id}  one job                                                                   [studio]
GET  /api/studio/jobs/{job_id}/log?offset=N   the job's log from byte N (poll with next_offset)         [studio]

Shapes (stable; the Studio page and ``python3 -m regista.studio status`` read them)
------
overview  {generated_at, role, capabilities, health, todo, usage, data, cache}
  health  /api/health plus {image, revision}: IMAGE_TAG and CONTAINER_APP_REVISION from the environment, or null
  todo    [{kind, match_id, count, detail, link, api}], most urgent first. kind is one of
          failed_run (last run failed or dead-lettered), workflow_review (a paused run waits for verdicts),
          whos_who (unanswered identity questions), unsure_clips (flagged clips with no verdict),
          stale_model (verdicts since the watchability model was trained; match_id null).
          link is a Studio anchor (/studio#runs/<id>, #review/<id>, #whos-who/<id>, #training); api is where the detail is.
run       {match_id, has_run, status: none|ok|paused|failed, kind: intelligence|vision|null, finished_at, source: local|cosmos,
           agents: [{agent, status, attempts, elapsed_ms, error, note?}], dead_letters: [{agent, error, attempts, at}],
           label_models: {model: labels}, review: {pending_requests, pending_items, log}}
          /runs/{id} adds rows: [{at, agent, attempt, status, elapsed_ms, error, note}] (every attempt, in order).
data      {cosmos: {configured: false} | {configured, database, containers: {matches, clips, labels, annotations: n|null}, error},
           search: {configured: false} | {configured, index, documents: n|null, error}, checked_at, age_s}
usage     {foundry, scope, last_minute, last_hour, last_day, visitors_last_hour, in_flight, limits: {per_visitor_per_min,
           per_visitor_per_hour, total_per_hour, total_per_day, concurrent}, remaining: {hour, day}}
cache     {cache_root, files, bytes, matches: [{match_id, files, bytes, partial}], render_concurrency,
           prerender: {enabled, running, total, rendered, failed, started_at, finished_at}}
jobs      {available, reason, kinds: {kind: {help, args: {field: description}}}, running: job|null, jobs: [job]}
  job     {id, kind, args, argv, status: running|ok|failed|lost, started_at, ended_at, returncode, result, log_bytes}
log       {job_id, status, offset, next_offset, size, text}
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from regista.access import require_studio_reader, require_writer, write_mode
from regista.studio import facts
from regista.studio.jobs import KINDS, JobBusy, JobError, JobRunner

STATIC = Path(__file__).resolve().parent / "static"

router = APIRouter()
JOBS = JobRunner(os.environ.get("REGISTA_STUDIO_JOBS", "data/studio/jobs"))


def capabilities() -> dict[str, Any]:
    """What this deployment can do. Vision jobs need the private models on disk and never run on the cloud app."""
    from regista import api
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    cloud = bool(os.environ.get("REGISTA_CLOUD"))
    vision_models = (api.MODELS_DIR / "shot_model.joblib").exists()
    return {"writes": write_mode(), "cloud": cloud, "foundry": cfg.foundry_enabled, "cosmos": cfg.cosmos_enabled,
            "search": cfg.search_enabled, "vision_models": vision_models, "jobs": vision_models and not cloud}


def _jobs_unavailable(caps: dict[str, Any]) -> str | None:
    from regista import api

    if caps["cloud"]:
        return "vision jobs run only on a local Regista: this is the cloud app (REGISTA_CLOUD is set), which has no footage or vision models"
    if not caps["vision_models"]:
        return f"no vision models in {api.MODELS_DIR} (train them first: python3 -m regista.vision train)"
    return None


@router.get("/studio", response_class=HTMLResponse, include_in_schema=False)
def studio_page() -> str:
    return (STATIC / "studio" / "index.html").read_text(encoding="utf-8")


@router.get("/api/studio/session")
def session(role: str = Depends(require_studio_reader)) -> dict[str, Any]:
    return {"role": role, "capabilities": capabilities()}


# ---------------------------------------------------------------------------- overview and its parts

def _health() -> dict[str, Any]:
    from regista import api

    return {**api.health(), "image": os.environ.get("IMAGE_TAG") or None, "revision": os.environ.get("CONTAINER_APP_REVISION") or None}


def _usage() -> dict[str, Any]:
    from regista import api
    from regista.cloud import CloudConfig

    snap = api._ask_limiter.snapshot()
    lim = snap["limits"]
    return {"foundry": CloudConfig.from_env().foundry_enabled,
            "scope": "Ask and Chat (engine=foundry) share one limiter; counts are this replica's, in memory since it started",
            **snap, "remaining": {"hour": max(0, lim["total_per_hour"] - snap["last_hour"]), "day": max(0, lim["total_per_day"] - snap["last_day"])}}


@router.get("/api/studio/overview")
def overview(role: str = Depends(require_studio_reader)) -> dict[str, Any]:
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"), "role": role,
            "capabilities": capabilities(), "health": _health(), "todo": facts.todo(), "usage": _usage(), "data": facts.data(),
            "cache": facts.cache()}


@router.get("/api/studio/runs", dependencies=[Depends(require_studio_reader)])
def runs() -> list[dict[str, Any]]:
    return facts.runs()


@router.get("/api/studio/runs/{match_id}", dependencies=[Depends(require_studio_reader)])
def run_detail(match_id: str) -> dict[str, Any]:
    from regista import api

    api._check_id(match_id)
    d = api.DATA_ROOT / match_id
    if (d / "events.jsonl").exists():
        return {**facts.run_of(d), "source": "local"}
    if match_id in api._library():
        return facts.empty_run(match_id, "cosmos")
    raise HTTPException(404, f"no match {match_id!r}")


@router.get("/api/studio/data", dependencies=[Depends(require_studio_reader)])
def data() -> dict[str, Any]:
    return facts.data()


@router.get("/api/studio/usage", dependencies=[Depends(require_studio_reader)])
def usage() -> dict[str, Any]:
    return _usage()


@router.get("/api/studio/cache", dependencies=[Depends(require_studio_reader)])
def cache() -> dict[str, Any]:
    return facts.cache()


# ---------------------------------------------------------------------------- vision jobs (local only)

class JobIn(BaseModel):
    kind: Literal["vision-run", "evaluate", "train-events", "learn-from-reviews"]
    args: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _small(self) -> JobIn:
        if len(self.args) > 8 or len(repr(self.args)) > 4000:
            raise ValueError("args is too large")
        return self


@router.get("/api/studio/jobs", dependencies=[Depends(require_studio_reader)])
def jobs() -> dict[str, Any]:
    reason = _jobs_unavailable(capabilities())
    return {"available": reason is None, "reason": reason, "kinds": KINDS, "running": JOBS.running(), "jobs": JOBS.list()}


@router.post("/api/studio/jobs", status_code=201, dependencies=[Depends(require_writer)])
def start_job(body: JobIn) -> dict[str, Any]:
    from regista import api

    reason = _jobs_unavailable(capabilities())
    if reason:
        raise HTTPException(409, reason)
    try:
        return JOBS.start(body.kind, body.args, data_root=api.DATA_ROOT, models_dir=api.MODELS_DIR)
    except JobBusy as exc:
        raise HTTPException(409, str(exc))
    except JobError as exc:
        raise HTTPException(422, str(exc))


@router.get("/api/studio/jobs/{job_id}", dependencies=[Depends(require_studio_reader)])
def job(job_id: str) -> dict[str, Any]:
    out = JOBS.get(job_id)
    if out is None:
        raise HTTPException(404, "no such job")
    return out


@router.get("/api/studio/jobs/{job_id}/log", dependencies=[Depends(require_studio_reader)])
def job_log(job_id: str, offset: int = Query(0, ge=0)) -> dict[str, Any]:
    out = JOBS.log(job_id, offset)
    if out is None:
        raise HTTPException(404, "no such job")
    return out
