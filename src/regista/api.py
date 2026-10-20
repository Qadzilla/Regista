"""Regista as an HTTP service, with the clip viewer built in. Container-ready; no cloud dependency.

    uvicorn regista.api:app --reload            # http://localhost:8000  (viewer) and /docs (OpenAPI)
    REGISTA_DATA=data/synthetic/sample uvicorn regista.api:app

Endpoints
---------
GET  /                                          the viewer (player header, tag chips, clip grid, search box)
GET  /api/matches                               match directories under REGISTA_DATA
POST /api/matches                               upload events.jsonl (+ tracks.jsonl) as a new match; runs the agent pipeline
GET  /api/matches/{match_id}                    manifest, roster, score
GET  /api/matches/{match_id}/clips?player=&tag=&min_watchability=&reason=
GET  /api/matches/{match_id}/search?q=          the Librarian
GET  /api/matches/{match_id}/clips/{clip_id}.mp4   rendered on demand, cached under REGISTA_CACHE
GET  /api/matches/{match_id}/video.mp4          the whole broadcast, rendered on demand, cached
GET  /api/matches/{match_id}/report             synthetic realism report (markdown)

The service only reads and writes under REGISTA_DATA and REGISTA_CACHE.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from regista import __version__
from regista.agents.roles import default_agents
from regista.librarian import search_clips
from regista.schema import iter_jsonl, validate_jsonl

DATA_ROOT = Path(os.environ.get("REGISTA_DATA", "data/synthetic/sample"))
CACHE_ROOT = Path(os.environ.get("REGISTA_CACHE", "data/clips"))
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Regista", version=__version__, description="Every touch. Every replay. Every player. Found instantly.")


def _match_dir(match_id: str) -> Path:
    if "/" in match_id or ".." in match_id:
        raise HTTPException(400, "bad match id")
    d = DATA_ROOT / match_id
    if not (d / "events.jsonl").exists():
        raise HTTPException(404, f"no match {match_id!r} under {DATA_ROOT}")
    return d


def _header(d: Path) -> dict[str, Any]:
    return next(iter_jsonl(d / "events.jsonl"))


def _feedback_store():
    """Cosmos DB store for verdicts and the model when configured, else None. Never fatal."""
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.cosmos_enabled:
        return None
    try:
        from regista.cloud.cosmos import ClipStore

        return ClipStore.connect(cfg)
    except Exception:  # noqa: BLE001 - feedback must keep working locally if Cosmos is unreachable
        return None


def _sync_feedback_down() -> None:
    """Pull every verdict and the latest model from Cosmos DB into the local feedback folder (the container's disk is wiped on restart)."""
    from regista.feedback import ANNOTATIONS_FILE, FEEDBACK_DIR, MODEL_FILE

    store = _feedback_store()
    if store is None:
        return
    try:
        anns = store.all_annotations()
        model = store.load_model()
    except Exception:  # noqa: BLE001
        return
    FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    if anns:
        (FEEDBACK_DIR / ANNOTATIONS_FILE).write_text("".join(json.dumps(a) + "\n" for a in anns), encoding="utf-8")
    if model:
        (FEEDBACK_DIR / MODEL_FILE).write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")


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

        return agents_for()
    return default_agents()


def _run_summary(mid: str, players: list[str], result) -> dict[str, Any]:
    labels = result.state.get("labels", {})
    out = {"match_id": mid, "players": players, "clips": {p: len(c) for p, c in result.state.get("clips", {}).items()},
           "pipeline_ok": result.ok, "statuses": result.statuses, "engine": "microsoft-agent-framework-workflow",
           "label_models": sorted({lb.get("model", "") for ls in labels.values() for lb in ls}),
           "cosmos": result.state.get("cosmos"), "review_log": result.state.get("review_log"),
           "dead_letters": [{"agent": d["agent"], "error": d["error"]} for d in result.dead_letters]}
    if getattr(result, "paused", False):
        out["paused"] = True
        out["review"] = [{"request_id": p.request_id, "checkpoint_id": p.checkpoint_id, "question": p.request.question, "items": p.request.items}
                         for p in result.pending]
    return out


def _clips(d: Path) -> tuple[list[dict], dict[str, dict]]:
    clips, labels = [], {}
    p = d / "clips.jsonl"
    if p.exists():
        for r in iter_jsonl(p):
            (clips.append(r) if r["type"] == "clip" else labels.__setitem__(r["clip_id"], r))
    return clips, labels


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def viewer() -> str:
    return (STATIC / "viewer.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    return {"ok": True, "version": __version__, "data_root": str(DATA_ROOT), "cache_root": str(CACHE_ROOT),
            "cloud": {"foundry": cfg.foundry_enabled, "model": cfg.foundry_model if cfg.foundry_enabled else None, "cosmos": cfg.cosmos_enabled}}


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
    d = _match_dir(match_id)
    clips, labels = _clips(d)
    if player and player not in {c["player_id"] for c in clips}:
        # Not derived yet: run the Clip and Label agents for this player on the fly.
        from regista.clips import derive_clips

        stream = list(iter_jsonl(d / "events.jsonl"))
        new_clips, new_labels = derive_clips(stream, player)
        clips += new_clips
        labels.update({lb["clip_id"]: lb for lb in new_labels})
    from regista.feedback import needs_review

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
def search(match_id: str, q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    d = _match_dir(match_id)
    out = search_clips(d, q, limit)
    for r in out["results"]:
        r["video_url"] = f"/api/matches/{match_id}/clips/{r['clip_id']}.mp4"
    return out


@app.get("/api/matches/{match_id}/clips/{clip_id}.mp4")
def clip_video(match_id: str, clip_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    d = _match_dir(match_id)
    clips, labels = _clips(d)
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


@app.post("/api/matches", status_code=201)
async def upload_match(events: UploadFile = File(...), tracks: UploadFile | None = File(None), player: str | None = None,
                       match_id: str | None = None, review: bool = False, annotator: str = "zaid") -> dict[str, Any]:
    """Create a match from an events.jsonl (and optional tracks.jsonl), validate it, and run the Agent Framework workflow.

    With ``review=true`` the workflow pauses on clips the Label agent is unsure about; answer with POST /api/matches/{id}/review."""
    tmp = Path(tempfile.mkdtemp(prefix="regista_upload_"))
    try:
        ev_path = tmp / "events.jsonl"
        ev_path.write_bytes(await events.read())
        problems = validate_jsonl(ev_path)
        if problems:
            raise HTTPException(422, {"message": "events.jsonl failed validation", "problems": problems[:20]})
        header = next(iter_jsonl(ev_path))
        mid = match_id or header["match_id"]
        if "/" in mid or ".." in mid:
            raise HTTPException(400, "bad match id")
        dest = DATA_ROOT / mid
        if dest.exists():
            raise HTTPException(409, f"match {mid} already exists")
        dest.mkdir(parents=True)
        shutil.move(str(ev_path), dest / "events.jsonl")
        if tracks is not None:
            (dest / "tracks.jsonl").write_bytes(await tracks.read())
        players = [player] if player else [p["player_id"] for p in header["players"] if p["starter"]][:1]
        (dest / "manifest.json").write_text(json.dumps({"match_id": mid, "score": header.get("score"), "clips_for": players[0],
                                                        "video_duration_s": header["video"]["duration_s"]}, indent=2))
        await run_in_threadpool(_sync_feedback_down)
        from regista.agents.workflow import WorkflowPipeline

        pipeline = WorkflowPipeline(_pipeline_agents(), dest / "agents", checkpoint_dir=dest / "agents" / "checkpoints")
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


@app.post("/api/matches/{match_id}/review")
async def answer_review(match_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Answer a paused workflow: {"request_id", "verdicts": [{"clip_id", "verdict": keep|drop|fix, "watchability"?, "tags"?, "note"?}], "annotator"?}.
    The workflow resumes from its checkpoint, records the verdicts, retrains the model, and finishes."""
    from regista.agents.workflow import ReviewVerdicts, WorkflowPipeline
    from regista.feedback import ANNOTATIONS_FILE, FEEDBACK_DIR, MODEL_FILE, load_annotations

    d = _match_dir(match_id)
    p = d / "agents" / "pending_review.json"
    pending = json.loads(p.read_text()) if p.exists() else []
    match = next((x for x in pending if x["request_id"] == body.get("request_id")), pending[0] if len(pending) == 1 and not body.get("request_id") else None)
    if match is None:
        raise HTTPException(404, "no pending review with that request_id")
    before = {a["id"] for a in load_annotations()}
    pipeline = WorkflowPipeline(_pipeline_agents(), d / "agents", checkpoint_dir=d / "agents" / "checkpoints")
    pipeline._reset_files()
    answer = ReviewVerdicts(verdicts=list(body.get("verdicts", [])), annotator=body.get("annotator", "zaid"))
    result = await pipeline.resume({match["request_id"]: answer}, checkpoint_id=match.get("checkpoint_id"))
    p.unlink(missing_ok=True)
    store = await run_in_threadpool(_feedback_store)
    if store is not None:
        for a in load_annotations():
            if a["id"] not in before:
                await run_in_threadpool(store.write_annotation, a)
        mp = FEEDBACK_DIR / MODEL_FILE
        if mp.exists():
            await run_in_threadpool(store.save_model, json.loads(mp.read_text()))
    manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
    return _run_summary(match_id, [manifest.get("clips_for", "")], result)


@app.post("/api/matches/{match_id}/clips/{clip_id}/verdict")
async def clip_verdict(match_id: str, clip_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record a human verdict on one clip from the viewer: {"verdict": keep|drop|fix, "watchability"?, "tags"?, "note"?, "annotator"?}."""
    from regista.feedback import record_verdict

    d = _match_dir(match_id)
    clips, labels = _clips(d)
    clip = next((c for c in clips if c["id"] == clip_id), None)
    if clip is None or clip_id not in labels:
        raise HTTPException(404, f"no clip {clip_id}")
    await run_in_threadpool(_sync_feedback_down)
    try:
        rec = record_verdict(clip, labels[clip_id], body.get("verdict", ""), watchability=body.get("watchability"), tags=body.get("tags"),
                             note=body.get("note", ""), annotator=body.get("annotator", "zaid"))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    store = await run_in_threadpool(_feedback_store)
    stored = False
    if store is not None:
        try:
            await run_in_threadpool(store.write_annotation, rec)
            stored = True
        except Exception:  # noqa: BLE001
            stored = False
    return {"annotation": rec, "stored_in_cosmos": stored}


@app.get("/api/feedback")
async def feedback_status() -> dict[str, Any]:
    """How much the system has learned from people: verdict counts, the current model, and agreement per scorer."""
    from regista.feedback import WatchabilityModel, evaluate, latest_per_label, load_annotations, target_of

    await run_in_threadpool(_sync_feedback_down)
    anns = load_annotations()
    rows = latest_per_label(anns)
    model = WatchabilityModel.load()
    return {"verdicts": len(anns), "clips_reviewed": len(rows), "keep": sum(1 for a in rows if target_of(a) >= 0.5),
            "annotators": sorted({a["annotator"] for a in anns}), "model": model.to_json() if model else None,
            "model_name": model.name if model else None, "evaluation": evaluate(anns, model)}


@app.post("/api/feedback/train")
async def feedback_train() -> dict[str, Any]:
    """Retrain the watchability model from every human verdict; the Label agent uses it as its prior from the next run."""
    from regista.feedback import WatchabilityModel, evaluate, load_annotations, train

    await run_in_threadpool(_sync_feedback_down)
    anns = load_annotations()
    try:
        model = train(anns, previous=WatchabilityModel.load())
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    model.save()
    store = await run_in_threadpool(_feedback_store)
    if store is not None:
        await run_in_threadpool(store.save_model, model.to_json())
    return {"model_name": model.name, "metrics": model.metrics, "evaluation": evaluate(anns, model)}
