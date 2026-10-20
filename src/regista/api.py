"""Regista as an HTTP service, with the clip viewer built in. Container-ready; no cloud dependency.

    uvicorn regista.api:app --reload            # http://localhost:8000  (viewer) and /docs (OpenAPI)
    REGISTA_DATA=data/synthetic/sample uvicorn regista.api:app

Read endpoints are open. Write endpoints (uploads, verdicts, reviews, retraining) need the
``X-Regista-Token`` header when REGISTA_ADMIN_TOKEN is set, and are switched off entirely with
REGISTA_READONLY=1. Without either (local development) they are open.

Endpoints
---------
GET  /                                          the viewer
GET  /api/health
GET  /api/matches                               match directories under REGISTA_DATA
POST /api/matches                               upload events.jsonl (+ tracks.jsonl); runs the Agent Framework workflow       [write]
GET  /api/matches/{match_id}                    manifest, roster, score
GET  /api/matches/{match_id}/clips?player=&tag=&min_watchability=&reason=
GET  /api/matches/{match_id}/search?q=          the Librarian
GET  /api/matches/{match_id}/clips/{clip_id}.mp4   rendered on demand, cached under REGISTA_CACHE
GET  /api/matches/{match_id}/video.mp4          the whole broadcast, rendered on demand, cached
GET  /api/matches/{match_id}/report             synthetic realism report (markdown)
GET  /api/matches/{match_id}/review             the workflow's open review request
POST /api/matches/{match_id}/review             answer it; the workflow resumes from its checkpoint                          [write]
POST /api/matches/{match_id}/clips/{clip_id}/verdict   one verdict from the viewer                                         [write]
GET  /api/feedback                              verdict counts, the learned model, agreement per scorer
POST /api/feedback/train                        retrain the watchability model                                             [write]

The service only reads and writes under REGISTA_DATA, REGISTA_CACHE and REGISTA_FEEDBACK_DIR.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StringConstraints, model_validator

from regista import __version__
from regista.agents.roles import default_agents
from regista.librarian import search_clips
from regista.schema import iter_jsonl, validate_jsonl

DATA_ROOT = Path(os.environ.get("REGISTA_DATA", "data/synthetic/sample"))
CACHE_ROOT = Path(os.environ.get("REGISTA_CACHE", "data/clips"))
STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SYNC_TTL_S = 30.0
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")

app = FastAPI(title="Regista", version=__version__, description="Every touch. Every replay. Every player. Found instantly.")


# ---------------------------------------------------------------------------- access control

def write_mode() -> str:
    if os.environ.get("REGISTA_READONLY") == "1":
        return "read-only"
    return "token" if os.environ.get("REGISTA_ADMIN_TOKEN") else "open"


def require_writer(x_regista_token: Annotated[str | None, Header()] = None) -> None:
    """Writes are the only way to spend Foundry credit or change what the model learns, so they are guarded."""
    mode = write_mode()
    if mode == "read-only":
        raise HTTPException(403, "this deployment is read-only")
    if mode == "token":
        expected = os.environ.get("REGISTA_ADMIN_TOKEN", "")
        if not x_regista_token or not hmac.compare_digest(x_regista_token.encode(), expected.encode()):
            raise HTTPException(401, "a valid X-Regista-Token header is required to write")


Writer = Depends(require_writer)


# ---------------------------------------------------------------------------- request bodies

Annotator = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_ .\-]{1,40}$")]
Tag = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_ ]{1,40}$")]
Score = Annotated[StrictFloat | StrictInt, Field(ge=0, le=1)]


class VerdictIn(BaseModel):
    verdict: Literal["keep", "drop", "fix"]
    watchability: Score | None = None
    tags: list[Tag] | None = Field(None, max_length=20)
    note: str = Field("", max_length=500)
    annotator: Annotator = "zaid"

    @model_validator(mode="after")
    def _drop_has_no_score(self) -> VerdictIn:
        if self.verdict == "drop" and self.watchability is not None:
            raise ValueError("a drop verdict cannot carry a watchability score; use fix with a score instead")
        return self


class ReviewVerdictIn(VerdictIn):
    clip_id: Annotated[str, StringConstraints(max_length=200)]


class ReviewIn(BaseModel):
    request_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    verdicts: list[ReviewVerdictIn] = Field(default_factory=list, max_length=200)
    annotator: Annotator = "zaid"


# ---------------------------------------------------------------------------- helpers

def _match_dir(match_id: str) -> Path:
    if not ID_RE.match(match_id) or ".." in match_id:
        raise HTTPException(400, "bad match id")
    d = DATA_ROOT / match_id
    if not (d / "events.jsonl").exists():
        raise HTTPException(404, f"no match {match_id!r}")
    return d


def _header(d: Path) -> dict[str, Any]:
    return next(iter_jsonl(d / "events.jsonl"))


_store_lock = threading.Lock()
_store_cache: dict[str, Any] = {}
_last_sync = {"t": 0.0}


def _feedback_store():
    """Cosmos DB store for verdicts and the model when configured, else None. Never fatal; connected once."""
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.cosmos_enabled:
        return None
    with _store_lock:
        if cfg.cosmos_endpoint in _store_cache:
            return _store_cache[cfg.cosmos_endpoint]
        try:
            from regista.cloud.cosmos import ClipStore

            store = ClipStore.connect(cfg)
        except Exception:  # noqa: BLE001 - feedback keeps working locally if Cosmos is unreachable
            return None
        _store_cache[cfg.cosmos_endpoint] = store
        return store


def _sync_feedback(force: bool = False) -> None:
    """Merge verdicts and the model between the local feedback folder and Cosmos DB.

    The container's disk is wiped on restart and several replicas may run, so Cosmos is the durable copy.
    Nothing is overwritten: verdicts are unioned by id, and local verdicts Cosmos lacks are pushed up."""
    from regista.feedback import WatchabilityModel, feedback_dir, load_annotations, merge_annotations, save_annotations

    store = _feedback_store()
    if store is None:
        return
    with _store_lock:
        if not force and time.time() - _last_sync["t"] < SYNC_TTL_S:
            return
        try:
            remote = store.all_annotations()
        except Exception:  # noqa: BLE001
            return
        merged, local_only = merge_annotations(load_annotations(humans_only=False), remote)
        for a in local_only:
            try:
                store.write_annotation(a)
            except Exception:  # noqa: BLE001 - retried on the next sync
                pass
        save_annotations(merged)
        try:
            remote_model = store.load_model()
            local_model = WatchabilityModel.load()
            if remote_model and (local_model is None or int(remote_model.get("version", 0)) > local_model.version):
                WatchabilityModel.from_json(remote_model).save()
            elif local_model and (remote_model is None or local_model.version > int(remote_model.get("version", 0))):
                store.save_model(local_model.to_json())
        except Exception:  # noqa: BLE001
            pass
        feedback_dir().mkdir(parents=True, exist_ok=True)
        _last_sync["t"] = time.time()


def _push_annotations(ids: set[str]) -> int:
    from regista.feedback import load_annotations

    store = _feedback_store()
    if store is None or not ids:
        return 0
    n = 0
    for a in load_annotations():
        if a["id"] in ids:
            try:
                store.write_annotation(a)
                n += 1
            except Exception:  # noqa: BLE001 - stays local; the next sync pushes it
                pass
    return n


def _push_model() -> None:
    from regista.feedback import WatchabilityModel

    store, model = _feedback_store(), WatchabilityModel.load()
    if store is not None and model is not None:
        try:
            store.save_model(model.to_json())
        except Exception:  # noqa: BLE001
            pass


def _verdicts_for(match_id: str) -> dict[str, dict]:
    """Latest human verdict per clip in this match."""
    from regista.feedback import latest_per_label, load_annotations

    out = {}
    for a in latest_per_label(load_annotations()):
        if a["match_id"] == match_id:
            out[a["context"]["clip_id"]] = {"verdict": a["verdict"], "keep": a["correction"].get("keep"), "annotator": a["annotator"],
                                            "at": a["annotated_at"], "watchability": a["correction"].get("watchability")}
    return out


def _pipeline_agents():
    if os.environ.get("REGISTA_CLOUD"):
        from regista.cloud import agents_for
        from regista.cloud.telemetry import configure_tracing

        configure_tracing()
        return agents_for()
    return default_agents()


def _run_summary(mid: str, players: list[str], result) -> dict[str, Any]:
    labels = result.state.get("labels", {})
    out = {"match_id": mid, "players": players, "clips": {p: len(c) for p, c in result.state.get("clips", {}).items()},
           "pipeline_ok": result.ok, "statuses": result.statuses, "engine": "microsoft-agent-framework-workflow",
           "label_models": sorted({lb.get("model", "") for ls in labels.values() for lb in ls}),
           "cosmos": result.state.get("cosmos"), "search_index": result.state.get("search_index"),
           "review_log": result.state.get("review_log"),
           "dead_letters": [{"agent": d["agent"], "error": d["error"]} for d in result.dead_letters]}
    if getattr(result, "paused", False):
        out["paused"] = True
        out["review"] = [{"request_id": p.request_id, "checkpoint_id": p.checkpoint_id, "question": p.request.question, "items": p.request.items}
                         for p in result.pending]
    return out


def _clips(d: Path, player: str | None = None) -> tuple[list[dict], dict[str, dict]]:
    """Persisted clips and labels, plus clips derived on the fly for a player who has none on disk yet."""
    clips, labels = [], {}
    p = d / "clips.jsonl"
    if p.exists():
        for r in iter_jsonl(p):
            (clips.append(r) if r["type"] == "clip" else labels.__setitem__(r["clip_id"], r))
    if player and player not in {c["player_id"] for c in clips}:
        from regista.clips import derive_clips

        try:
            new_clips, new_labels = derive_clips(list(iter_jsonl(d / "events.jsonl")), player)
        except ValueError:
            new_clips, new_labels = [], []
        clips += new_clips
        labels.update({lb["clip_id"]: lb for lb in new_labels})
    return clips, labels


def _player_of(clip_id: str) -> str | None:
    m = re.match(r"^cl_(.+)_\d{6}$", clip_id)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------- read endpoints

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def viewer() -> str:
    return (STATIC / "viewer.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    return {"ok": True, "version": __version__, "data_root": str(DATA_ROOT), "cache_root": str(CACHE_ROOT), "writes": write_mode(),
            "cloud": {"foundry": cfg.foundry_enabled, "model": cfg.foundry_model if cfg.foundry_enabled else None, "cosmos": cfg.cosmos_enabled,
                      "search": cfg.search_enabled}}


@app.get("/api/matches")
def list_matches() -> list[dict[str, Any]]:
    out = []
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            if (d / "events.jsonl").exists():
                m = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
                h = _header(d)
                out.append({"match_id": d.name, "score": m.get("score", h.get("score")), "clips_for": m.get("clips_for"),
                            "teams": [{"team_id": t["team_id"], "name": t["name"], "short_name": t["short_name"], "kit": t["kit"]} for t in h["teams"]],
                            "video_duration_s": h["video"]["duration_s"]})
    return out


@app.get("/api/matches/{match_id}")
def get_match(match_id: str) -> dict[str, Any]:
    d = _match_dir(match_id)
    h = _header(d)
    clips, labels = _clips(d)
    players_with_clips = sorted({c["player_id"] for c in clips})
    return {"match_id": match_id, "teams": h["teams"], "players": h["players"], "score": h.get("score"), "video": h["video"],
            "periods": h["periods"], "players_with_clips": players_with_clips, "clip_count": len(clips)}


@app.get("/api/matches/{match_id}/clips")
def get_clips(match_id: str, player: str | None = None, tag: str | None = None, reason: str | None = None,
              min_watchability: float = Query(0.0, ge=0.0, le=1.0)) -> list[dict[str, Any]]:
    from regista.feedback import needs_review

    d = _match_dir(match_id)
    clips, labels = _clips(d, player)
    _sync_feedback()
    verdicts = _verdicts_for(match_id)
    out = []
    for c in clips:
        lb = labels.get(c["id"])
        if lb is None or (player and c["player_id"] != player) or (reason and c["reason"] != reason):
            continue
        if tag and tag not in lb["tags"]:
            continue
        if lb["watchability"] < min_watchability:
            continue
        verdict = verdicts.get(c["id"])
        review = None if verdict else (lb.get("review") or needs_review(lb["watchability"], lb.get("prior_watchability")))
        out.append({**c, "label": lb, "review": review, "verdict": verdict, "video_url": f"/api/matches/{match_id}/clips/{c['id']}.mp4"})
    out.sort(key=lambda r: (-r["label"]["watchability"], r["t"]))
    return out


@app.get("/api/matches/{match_id}/search")
def search(match_id: str, q: str = Query(..., min_length=1, max_length=300), limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    d = _match_dir(match_id)
    out = search_clips(d, q, limit)
    for r in out["results"]:
        r["video_url"] = f"/api/matches/{match_id}/clips/{r['clip_id']}.mp4"
    return out


@app.get("/api/matches/{match_id}/clips/{clip_id}.mp4")
def clip_video(match_id: str, clip_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    d = _match_dir(match_id)
    if not ID_RE.match(clip_id):
        raise HTTPException(400, "bad clip id")
    clips, labels = _clips(d, _player_of(clip_id))
    clip = next((c for c in clips if c["id"] == clip_id), None)
    if clip is None:
        raise HTTPException(404, f"no clip {clip_id}")
    out = CACHE_ROOT / match_id / f"{clip_id}_{int(fps)}fps_{width}.mp4"
    if not out.exists():
        from regista.render.clips import render_clip
        from regista.render.draw import Style
        from regista.render.scene import Scene

        scene = Scene.load(d)
        render_clip(scene, clip, labels.get(clip_id), out, fps, Style(width, round(width * 9 / 16)))
    return FileResponse(out, media_type="video/mp4", filename=out.name)


@app.get("/api/matches/{match_id}/video.mp4")
def match_video(match_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    d = _match_dir(match_id)
    out = CACHE_ROOT / match_id / f"broadcast_{int(fps)}fps_{width}.mp4"
    if not out.exists():
        from regista.render.draw import Style
        from regista.render.scene import Scene
        from regista.render.video import render_video

        render_video(Scene.load(d), out, fps=fps, style=Style(width, round(width * 9 / 16)), end_card_s=3.0)
    return FileResponse(out, media_type="video/mp4", filename=out.name)


@app.get("/api/matches/{match_id}/report", response_class=PlainTextResponse)
def report(match_id: str) -> str:
    from regista.synth.report import report_match_dir

    _, md = report_match_dir(_match_dir(match_id))
    return md


# ---------------------------------------------------------------------------- uploads

def _relabel(path: Path, match_id: str) -> None:
    """Rewrite match_id on every record, so a match uploaded under a new id never collides with the original."""
    rows = list(iter_jsonl(path))
    for r in rows:
        r["match_id"] = match_id
        if r.get("type") == "match":
            r["id"] = f"ma_{match_id}"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


@app.post("/api/matches", status_code=201, dependencies=[Writer])
async def upload_match(events: UploadFile = File(...), tracks: UploadFile | None = File(None), player: str | None = None,
                       match_id: str | None = None, review: bool = False,
                       annotator: Annotated[str, Query(pattern=r"^[A-Za-z0-9_ .\-]{1,40}$")] = "zaid") -> dict[str, Any]:
    """Create a match from an events.jsonl (and optional tracks.jsonl), validate it, and run the Agent Framework workflow.

    With ``review=true`` the workflow pauses on clips the Label agent is unsure about; answer with POST /api/matches/{id}/review."""
    tmp = Path(tempfile.mkdtemp(prefix="regista_upload_"))
    try:
        data = await events.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"events.jsonl is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        ev_path = tmp / "events.jsonl"
        ev_path.write_bytes(data)
        problems = validate_jsonl(ev_path)
        if problems:
            raise HTTPException(422, {"message": "events.jsonl failed validation", "problems": problems[:20]})
        header = next(iter_jsonl(ev_path))
        mid = match_id or header["match_id"]
        if not ID_RE.match(mid) or ".." in mid:
            raise HTTPException(400, "bad match id")
        tracks_data = await tracks.read(MAX_UPLOAD_BYTES + 1) if tracks is not None else None
        if tracks_data is not None and len(tracks_data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "tracks.jsonl is too large")
        if player and player not in {p["player_id"] for p in header["players"]}:
            raise HTTPException(422, f"{player} is not in the roster")
        dest = DATA_ROOT / mid
        try:
            dest.mkdir(parents=True)
        except FileExistsError:
            raise HTTPException(409, f"match {mid} already exists")
        shutil.move(str(ev_path), dest / "events.jsonl")
        if tracks_data is not None:
            (dest / "tracks.jsonl").write_bytes(tracks_data)
        if mid != header["match_id"]:
            _relabel(dest / "events.jsonl", mid)
            if (dest / "tracks.jsonl").exists():
                _relabel(dest / "tracks.jsonl", mid)
        players = [player] if player else [p["player_id"] for p in header["players"] if p["starter"]][:1]
        (dest / "manifest.json").write_text(json.dumps({"match_id": mid, "score": header.get("score"), "clips_for": players[0],
                                                        "video_duration_s": header["video"]["duration_s"]}, indent=2))
        await run_in_threadpool(_sync_feedback, True)
        from regista.agents.workflow import WorkflowPipeline

        pipeline = WorkflowPipeline(_pipeline_agents(), dest / "agents", checkpoint_dir=dest / "agents" / "checkpoints" if review else None)
        result = await pipeline.start({"match_dir": str(dest), "player_ids": players, "queries": [], "review": review, "annotator": annotator})
        return _run_summary(mid, players, result)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------- human in the loop

@app.get("/api/matches/{match_id}/review")
def pending_review(match_id: str) -> dict[str, Any]:
    """The workflow's open review request for this match, if it paused for a human."""
    d = _match_dir(match_id)
    p = d / "agents" / "pending_review.json"
    return {"match_id": match_id, "pending": json.loads(p.read_text()) if p.exists() else []}


@app.post("/api/matches/{match_id}/review", dependencies=[Writer])
async def answer_review(match_id: str, body: ReviewIn) -> dict[str, Any]:
    """Answer a paused workflow. The workflow resumes from its checkpoint, records the verdicts, retrains the model, and finishes.
    A review is claimed atomically: a second answer to the same request gets 409."""
    from regista.agents.workflow import ReviewVerdicts, WorkflowPipeline

    d = _match_dir(match_id)
    p = d / "agents" / "pending_review.json"
    pending = json.loads(p.read_text()) if p.exists() else []
    match = next((x for x in pending if x["request_id"] == body.request_id),
                 pending[0] if len(pending) == 1 and not body.request_id else None)
    if match is None:
        raise HTTPException(404, "no pending review with that request_id")
    asked = {i["clip_id"] for i in match["request"]["items"]}
    unknown = [v.clip_id for v in body.verdicts if v.clip_id not in asked]
    if unknown:
        raise HTTPException(422, f"verdicts for clips that were not asked about: {unknown[:5]}")
    claimed = p.with_name(f"pending_review.claimed-{uuid.uuid4().hex[:8]}.json")
    try:
        os.rename(p, claimed)
    except FileNotFoundError:
        raise HTTPException(409, "this review is already being answered")
    await run_in_threadpool(_sync_feedback, True)
    pipeline = WorkflowPipeline(_pipeline_agents(), d / "agents", checkpoint_dir=d / "agents" / "checkpoints")
    answer = ReviewVerdicts(verdicts=[v.model_dump(exclude={"annotator"}, exclude_none=True) for v in body.verdicts], annotator=body.annotator)
    try:
        result = await pipeline.resume({match["request_id"]: answer}, checkpoint_id=match.get("checkpoint_id"))
    except Exception:
        os.rename(claimed, p)  # give the review back so it can be answered again
        raise
    claimed.unlink(missing_ok=True)
    applied = {a["annotation_id"] for a in (result.state.get("review_log") or {}).get("applied", [])}
    await run_in_threadpool(_push_annotations, applied)
    if (result.state.get("review_log") or {}).get("retrained", {}) and "model" in result.state["review_log"]["retrained"]:
        await run_in_threadpool(_push_model)
    manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
    return _run_summary(match_id, [manifest.get("clips_for", "")], result)


@app.post("/api/matches/{match_id}/clips/{clip_id}/verdict", dependencies=[Writer])
async def clip_verdict(match_id: str, clip_id: str, body: VerdictIn) -> dict[str, Any]:
    """Record a human verdict on one clip from the viewer."""
    from regista.feedback import record_verdict

    d = _match_dir(match_id)
    if not ID_RE.match(clip_id):
        raise HTTPException(400, "bad clip id")
    clips, labels = await run_in_threadpool(_clips, d, _player_of(clip_id))
    clip = next((c for c in clips if c["id"] == clip_id), None)
    if clip is None or clip_id not in labels:
        raise HTTPException(404, f"no clip {clip_id}")
    await run_in_threadpool(_sync_feedback)
    try:
        rec = await run_in_threadpool(lambda: record_verdict(clip, labels[clip_id], body.verdict, watchability=body.watchability,
                                                             tags=body.tags, note=body.note, annotator=body.annotator))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    stored = await run_in_threadpool(_push_annotations, {rec["id"]})
    return {"annotation": rec, "stored_in_cosmos": bool(stored)}


@app.get("/api/feedback")
async def feedback_status() -> dict[str, Any]:
    """How much the system has learned from people: verdict counts, the current model, and agreement per scorer."""
    from regista.feedback import WatchabilityModel, evaluate, latest_per_label, load_annotations, target_of

    await run_in_threadpool(_sync_feedback)
    anns = load_annotations()
    rows = latest_per_label(anns)
    model = WatchabilityModel.load()
    return {"verdicts": len(anns), "clips_reviewed": len(rows), "keep": sum(1 for a in rows if target_of(a) >= 0.5),
            "annotators": sorted({a["annotator"] for a in anns}), "model": model.to_json() if model else None,
            "model_name": model.name if model else None, "evaluation": evaluate(anns, model), "writes": write_mode()}


@app.post("/api/feedback/train", dependencies=[Writer])
async def feedback_train() -> dict[str, Any]:
    """Retrain the watchability model from every human verdict; the Label agent uses it as its prior from the next run."""
    from regista.feedback import WatchabilityModel, evaluate, load_annotations, train

    await run_in_threadpool(_sync_feedback, True)
    anns = load_annotations()
    try:
        model = await run_in_threadpool(lambda: train(anns, previous=WatchabilityModel.load()))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    model.save()
    await run_in_threadpool(_push_model)
    return {"model_name": model.name, "metrics": model.metrics, "evaluation": evaluate(anns, model)}
