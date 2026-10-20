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

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse

from regista import __version__
from regista.agents.orchestrator import Orchestrator
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
    return {"ok": True, "version": __version__, "data_root": str(DATA_ROOT), "cache_root": str(CACHE_ROOT)}


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
    out = []
    for c in clips:
        lb = labels.get(c["id"])
        if lb is None or (player and c["player_id"] != player) or (reason and c["reason"] != reason):
            continue
        if tag and tag not in lb["tags"]:
            continue
        if lb["watchability"] < min_watchability:
            continue
        out.append({**c, "label": lb, "video_url": f"/api/matches/{match_id}/clips/{c['id']}.mp4"})
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
                       match_id: str | None = None) -> dict[str, Any]:
    """Create a match from an events.jsonl (and optional tracks.jsonl), validate it, run the agent pipeline."""
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
        result = Orchestrator(default_agents(), dest / "agents").run({"match_dir": str(dest), "player_ids": players, "queries": []})
        (dest / "manifest.json").write_text(json.dumps({"match_id": mid, "score": header.get("score"), "clips_for": players[0],
                                                        "video_duration_s": header["video"]["duration_s"]}, indent=2))
        return {"match_id": mid, "players": players, "clips": {p: len(c) for p, c in result.state.get("clips", {}).items()},
                "pipeline_ok": result.ok, "statuses": result.statuses}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
