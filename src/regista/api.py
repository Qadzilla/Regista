"""Regista as an HTTP service, with the clip viewer built in. Container-ready; no cloud dependency.

    uvicorn regista.api:app --reload            # http://localhost:8000  (viewer) and /docs (OpenAPI)
    REGISTA_DATA=data/synthetic/sample uvicorn regista.api:app

Two pages: the Product at ``/`` (open) and the Studio at ``/studio`` (regista.studio_api). Product reads are open.
Studio reads (reviewers' data, marked [studio]) need the ``X-Regista-Token`` header with the Studio view key or the
admin key; writes (marked [write]) need the admin key. REGISTA_READONLY=1 switches writes off entirely. With no key
configured (local development) everything is open. The rules live in regista.access.

Endpoints
---------
GET  /                                          the Product
GET  /studio                                    the Studio (data behind the Studio keys; see regista.studio_api)
GET  /api/health
GET  /api/matches                               match directories under REGISTA_DATA
POST /api/matches                               upload events.jsonl (+ tracks.jsonl); runs the Agent Framework workflow       [write]
GET  /api/matches/{match_id}                    manifest, roster, score
GET  /api/matches/{match_id}/clips?player=&tag=&min_watchability=&reason=
GET  /api/matches/{match_id}/search?q=          the Librarian (rule-based, instant)
POST /api/matches/{match_id}/ask                the Foundry Librarian with its MCP tools; open, rate-limited, read-only tools; with its trace
POST /api/matches/{match_id}/chat               a conversation with the Librarian: follow-ups refine the search (rules, or Foundry: rate-limited);
                                                with its trace
GET  /api/matches/{match_id}/clips/{clip_id}.mp4   rendered on demand, cached under REGISTA_CACHE
GET  /api/matches/{match_id}/video.mp4          the whole broadcast, rendered on demand, cached
GET  /api/matches/{match_id}/report             synthetic realism report (markdown)
GET  /api/matches/{match_id}/review             the workflow's open review request                                           [studio]
POST /api/matches/{match_id}/review             answer it; the workflow resumes from its checkpoint                          [write]
POST /api/matches/{match_id}/clips/{clip_id}/verdict   one verdict from the viewer                                         [write]
GET  /api/matches/{match_id}/identity-review    open "who's who" questions for a vision match (crops, candidates, team sheets) [studio]
POST /api/matches/{match_id}/identity-review    answer them; identity is corrected and possession, events, clips recomputed   [write]
GET  /api/feedback                              verdict counts, the learned model, agreement per scorer                       [studio]
POST /api/feedback/train                        retrain the watchability model                                             [write]

The service only reads and writes under REGISTA_DATA, REGISTA_CACHE and REGISTA_FEEDBACK_DIR.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StringConstraints, model_validator

from regista import __version__
from regista.access import StudioReader, Writer, require_studio_reader, require_writer, role_of, write_mode  # noqa: F401
from regista.agents.roles import default_agents
from regista.librarian import search_clips
from regista.schema import iter_jsonl, validate_jsonl

DATA_ROOT = Path(os.environ.get("REGISTA_DATA", "data/synthetic/sample"))
CACHE_ROOT = Path(os.environ.get("REGISTA_CACHE", "data/clips"))
STATIC = Path(__file__).resolve().parent / "static"  # product/, studio/, shared/
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SYNC_TTL_S = 30.0
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}$")

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Agent Framework and request spans go to Application Insights (and the Foundry project's Tracing page) whenever
    # the connection string is set, which deploy-app.sh does from a Container Apps secret. A no-op otherwise.
    from regista.cloud.telemetry import configure_tracing, flush_tracing

    configure_tracing("regista-api")
    if os.environ.get("REGISTA_PRERENDER") == "1":
        threading.Thread(target=_prerender, name="regista-prerender", daemon=True).start()
    yield
    flush_tracing()


app = FastAPI(title="Regista", version=__version__, description="Every touch. Every replay. Every player. Found instantly.",
              lifespan=_lifespan)


# Access control (write_mode, require_writer, require_studio_reader) lives in regista.access.


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

def _check_id(match_id: str) -> None:
    if not ID_RE.match(match_id) or ".." in match_id:
        raise HTTPException(400, "bad match id")


def _match_dir(match_id: str) -> Path:
    """The match's directory on this replica. A match that only Cosmos DB still holds has no event stream here, so
    anything that needs one (video, search, verdicts, review) gets a 409 that says so rather than a bare 404."""
    _check_id(match_id)
    d = DATA_ROOT / match_id
    if not (d / "events.jsonl").exists():
        if match_id in _library():
            raise HTTPException(409, f"match {match_id!r} is stored in Cosmos DB without its event stream: clips and labels can be "
                                     "read, but video, search and verdicts need the match on this replica")
        raise HTTPException(404, f"no match {match_id!r}")
    return d


def _header(d: Path) -> dict[str, Any]:
    return next(iter_jsonl(d / "events.jsonl"))


_store_lock = threading.Lock()
_store_cache: dict[str, Any] = {}
_last_sync = {"t": 0.0}


def _feedback_store():
    """Cosmos DB store (library, verdicts, the model) when configured, else None. Never fatal; connected once."""
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


LIBRARY_TTL_S = 60.0
_library_lock = threading.Lock()
_library_cache: dict[str, Any] = {"t": None, "matches": {}}


def _library() -> dict[str, dict[str, Any]]:
    """Match headers Cosmos DB holds (match_id -> header), refreshed at most once a minute. Uploads land on this
    replica's disk, which a restart wipes; the library is how they stay listed. Empty without Cosmos DB, and the
    last good copy when Cosmos is briefly unreachable."""
    store = _feedback_store()
    if store is None:
        return {}
    with _library_lock:
        now = time.monotonic()
        if _library_cache["t"] is not None and now - _library_cache["t"] < LIBRARY_TTL_S:
            return _library_cache["matches"]
        try:
            _library_cache["matches"] = {m["match_id"]: m for m in store.list_matches()}
        except Exception:  # noqa: BLE001 - keep serving what we had
            pass
        _library_cache["t"] = now
        return _library_cache["matches"]


def _team_summary(h: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"team_id": t["team_id"], "name": t["name"], "short_name": t["short_name"], "kit": t["kit"]} for t in h["teams"]]


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


# ---------------------------------------------------------------------------- on-demand rendering

# Videos are rendered on first request and cached on the replica's disk, which a new revision starts empty. The grid
# asks for every clip at once, so without these rules a cold replica rendered the same clip several times in parallel,
# starved its one CPU, and answered 503 (seen on the live app on 2026-10-21). Now each file is rendered once (later
# requests wait for it), into a temporary name that is renamed into place (a half-written file is never served), and at
# most REGISTA_RENDER_CONCURRENCY renders run at a time.
RENDER_CONCURRENCY = max(1, int(os.environ.get("REGISTA_RENDER_CONCURRENCY", "1")))
_render_slots = threading.BoundedSemaphore(RENDER_CONCURRENCY)
_render_locks: dict[Path, threading.Lock] = {}
_render_locks_guard = threading.Lock()


def _render_once(out: Path, render: Any) -> Path:
    """``out``, rendering it with ``render(tmp_path) -> {"path": ...}`` if it is not cached yet."""
    if out.exists():
        return out
    with _render_locks_guard:
        lock = _render_locks.setdefault(out, threading.Lock())
    try:
        with lock:
            if out.exists():  # another request rendered it while this one waited
                return out
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_name(f".{out.stem}.{uuid.uuid4().hex[:8]}.part{out.suffix}")
            try:
                with _render_slots:
                    written = Path(render(tmp)["path"])
                if written.suffix != out.suffix:
                    raise HTTPException(500, f"the renderer wrote {written.suffix}, not {out.suffix} (is ffmpeg missing?)")
                os.replace(written, out)
            finally:
                for leftover in (tmp, tmp.with_suffix(".gif")):
                    leftover.unlink(missing_ok=True)
    finally:
        with _render_locks_guard:
            if _render_locks.get(out) is lock and not lock.locked():
                del _render_locks[out]
    return out


def _clip_cache_path(match_id: str, clip_id: str, fps: float, width: int) -> Path:
    return CACHE_ROOT / match_id / f"{clip_id}_{int(fps)}fps_{width}.mp4"


def _render_clip_cached(d: Path, clip: dict, label: dict | None, fps: float, width: int) -> Path:
    from regista.render.clips import render_clip
    from regista.render.draw import Style
    from regista.render.scene import Scene

    return _render_once(_clip_cache_path(d.name, clip["id"], fps, width),
                        lambda tmp: render_clip(Scene.load(d), clip, label, tmp, fps, Style(width, round(width * 9 / 16))))


def _prerender(fps: float = 25.0, width: int = 1280) -> list[Path]:
    """Render the featured player's clips for every local match, best first, so the first visitor after a deploy finds
    them cached. Runs in a background thread at startup when REGISTA_PRERENDER=1 (set in the Dockerfile)."""
    done = []
    for d in sorted(DATA_ROOT.iterdir()) if DATA_ROOT.exists() else []:
        manifest = d / "manifest.json"
        player = json.loads(manifest.read_text()).get("clips_for") if manifest.exists() else None
        if not player or not (d / "events.jsonl").exists():
            continue
        clips, labels = _clips(d, player)
        for c in sorted((c for c in clips if c["player_id"] == player),
                        key=lambda c: (-labels.get(c["id"], {}).get("watchability", 0.0), c["t"])):
            try:
                done.append(_render_clip_cached(d, c, labels.get(c["id"]), fps, width))
            except Exception as exc:  # noqa: BLE001  (one bad clip must not stop the rest)
                print(f"prerender: {d.name}/{c['id']} failed: {exc!r}", flush=True)
    return done


# ---------------------------------------------------------------------------- read endpoints

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def viewer() -> str:
    return (STATIC / "product" / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health() -> dict[str, Any]:
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    return {"ok": True, "version": __version__, "data_root": str(DATA_ROOT), "cache_root": str(CACHE_ROOT), "writes": write_mode(),
            "cloud": {"foundry": cfg.foundry_enabled, "model": cfg.foundry_model if cfg.foundry_enabled else None, "cosmos": cfg.cosmos_enabled,
                      "search": cfg.search_enabled},
            "librarian": f"foundry:{cfg.foundry_model}" if cfg.foundry_enabled else "rules",
            "azure_mcp": bool(shutil.which("azmcp")),
            "tracing": bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"))}


@app.get("/api/matches")
def list_matches() -> list[dict[str, Any]]:
    """Matches on this replica (``source: local``, full features) and matches only Cosmos DB still holds
    (``source: cosmos``: clips and labels, no video). ``in_cosmos`` marks local matches the library also holds."""
    library = _library()
    out = []
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            if (d / "events.jsonl").exists():
                m = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
                h = _header(d)
                out.append({"match_id": d.name, "score": m.get("score", h.get("score")), "clips_for": m.get("clips_for"),
                            "teams": _team_summary(h), "video_duration_s": h["video"]["duration_s"], "source": "local",
                            "video": True, "in_cosmos": d.name in library})
    local = {m["match_id"] for m in out}
    for mid, h in sorted(library.items()):
        if mid not in local:
            out.append({"match_id": mid, "score": h.get("score"), "clips_for": None, "teams": _team_summary(h),
                        "video_duration_s": h.get("video", {}).get("duration_s"), "source": "cosmos", "video": False, "in_cosmos": True})
    return out


def _cosmos_match(match_id: str) -> dict[str, Any] | None:
    """The header of a match only Cosmos DB holds, or None when the match is local or unknown."""
    _check_id(match_id)
    if (DATA_ROOT / match_id / "events.jsonl").exists():
        return None
    return _library().get(match_id)


@app.get("/api/matches/{match_id}")
def get_match(match_id: str) -> dict[str, Any]:
    h = _cosmos_match(match_id)
    if h is not None:
        clips, _labels = _feedback_store().clips_for(match_id)
        source = "cosmos"
    else:
        d = _match_dir(match_id)
        h = _header(d)
        clips, _labels = _clips(d)
        source = "local"
    players_with_clips = sorted({c["player_id"] for c in clips})
    return {"match_id": match_id, "teams": h["teams"], "players": h["players"], "score": h.get("score"), "video": h["video"],
            "periods": h["periods"], "players_with_clips": players_with_clips, "clip_count": len(clips), "source": source}


@app.get("/api/matches/{match_id}/clips")
def get_clips(match_id: str, player: str | None = None, tag: str | None = None, reason: str | None = None,
              min_watchability: float = Query(0.0, ge=0.0, le=1.0),
              x_regista_token: Annotated[str | None, Header()] = None) -> list[dict[str, Any]]:
    """Clips with labels, best first. Without a Studio key, a verdict says only what was decided, not who decided it."""
    from regista.feedback import needs_review

    studio = role_of(x_regista_token) is not None

    cosmos = _cosmos_match(match_id) is not None
    if cosmos:
        clips, labels = _feedback_store().clips_for(match_id, player)
    else:
        clips, labels = _clips(_match_dir(match_id), player)
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
        if verdict and not studio:
            verdict = {"verdict": verdict["verdict"], "keep": verdict["keep"]}
        review = None if verdict else (lb.get("review") or needs_review(lb["watchability"], lb.get("prior_watchability")))
        out.append({**c, "label": lb, "review": review, "verdict": verdict, "source": "cosmos" if cosmos else "local",
                    "video_url": None if cosmos else f"/api/matches/{match_id}/clips/{c['id']}.mp4"})
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
    out = _render_clip_cached(d, clip, labels.get(clip_id), fps, width)
    return FileResponse(out, media_type="video/mp4", filename=out.name)


@app.get("/api/matches/{match_id}/video.mp4")
def match_video(match_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    d = _match_dir(match_id)
    from regista.render.draw import Style
    from regista.render.scene import Scene
    from regista.render.video import render_video

    out = _render_once(CACHE_ROOT / match_id / f"broadcast_{int(fps)}fps_{width}.mp4",
                       lambda tmp: render_video(Scene.load(d), tmp, fps=fps, style=Style(width, round(width * 9 / 16)), end_card_s=3.0))
    return FileResponse(out, media_type="video/mp4", filename=out.name)


@app.get("/api/matches/{match_id}/report", response_class=PlainTextResponse)
def report(match_id: str) -> str:
    from regista.synth.report import report_match_dir

    _, md = report_match_dir(_match_dir(match_id))
    return md


# ---------------------------------------------------------------------------- who's who: identity review for vision matches

# A match written by the vision layer keeps its identity result and a short list of questions (regista.vision.review).
# A person answers them here; identity is corrected, and possession, events and clips are recomputed from it. Vision
# matches live on a private, local deployment (the footage never reaches the public app).
MODELS_DIR = Path(os.environ.get("REGISTA_MODELS", "models/vision"))
CROP_RE = re.compile(r"^(tr|cw)_[A-Za-z0-9_.\-]{1,80}\.jpg$")
ReviewItemId = Annotated[str, StringConstraints(pattern=r"^(tr|cw)_[A-Za-z0-9_.\-]{1,80}$")]
PlayerRef = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_]{1,40}$")]


class IdentityAnswerIn(BaseModel):
    item_id: ReviewItemId
    player_id: PlayerRef | None = None              # for a track: a team-sheet id, "not_a_player" or "unknown"
    players: list[PlayerRef] | None = Field(None, max_length=6)  # for a replay: who is in it


class IdentityReviewIn(BaseModel):
    answers: list[IdentityAnswerIn] = Field(min_length=1, max_length=50)
    annotator: Annotator = "zaid"


def _queue_path(d: Path) -> Path:
    from regista.vision.review import QUEUE_FILE

    return d / "review" / QUEUE_FILE


@app.get("/api/matches/{match_id}/identity-review", dependencies=[StudioReader])
def identity_review(match_id: str) -> dict[str, Any]:
    d = _match_dir(match_id)
    q = _queue_path(d)
    if not q.exists():
        return {"items": [], "message": "no open identity questions for this match"}
    items = json.loads(q.read_text())["items"]
    for it in items:
        if it.get("image"):
            it["image_url"] = f"/api/matches/{match_id}/identity-review/crops/{it['image']}"
    header = _header(d)
    teams = {t["team_id"]: [{"player_id": p["player_id"], "name": p["name"], "kit_number": p["kit_number"], "position": p.get("position")}
                            for p in header["players"] if p["team_id"] == t["team_id"]] for t in header["teams"]}
    return {"items": items, "teams": teams, "question": f"{len(items)} call(s) the identity agent is unsure of."}


@app.get("/api/matches/{match_id}/identity-review/crops/{name}", include_in_schema=False, dependencies=[StudioReader])
def identity_review_crop(match_id: str, name: str) -> FileResponse:
    d = _match_dir(match_id)
    if not CROP_RE.match(name):
        raise HTTPException(400, "bad crop name")
    path = d / "review" / "crops" / name
    if not path.exists():
        raise HTTPException(404, "no such crop")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/matches/{match_id}/identity-review", dependencies=[Writer])
async def answer_identity_review(match_id: str, body: IdentityReviewIn) -> dict[str, Any]:
    """Correct identity from a person's answers, then recompute possession, events and clips. The open questions are
    claimed atomically (a second answer gets 409); answers that do not validate change nothing (422)."""
    d = _match_dir(match_id)
    q = _queue_path(d)
    if not (d / ".vision_work" / "identity.joblib").exists():
        raise HTTPException(409, "this match has no identity result to correct (it was not written by the vision layer)")
    claimed = q.with_name(f"identity_review.claimed-{uuid.uuid4().hex[:8]}.json")
    try:
        os.rename(q, claimed)
    except FileNotFoundError:
        raise HTTPException(409, "no open identity questions (already answered, or none were asked)")
    try:
        out = await run_in_threadpool(_apply_identity_review, d, claimed, body)
    except ValueError as exc:
        os.rename(claimed, q)  # nothing was applied; the questions stay open
        raise HTTPException(422, str(exc))
    except Exception:
        os.rename(claimed, q)
        raise
    return out


def _apply_identity_review(d: Path, claimed: Path, body: IdentityReviewIn) -> dict[str, Any]:
    import joblib

    from regista.feedback import feedback_dir
    from regista.librarian import _load as librarian_cache
    from regista.vision.frames import probe
    from regista.vision.pipeline import refresh_from_identity
    from regista.vision.review import ANSWERED_SUFFIX, ANSWERS_FILE, annotation_records, apply_answers, validate_answers

    items = json.loads(claimed.read_text())["items"]
    header = _header(d)
    answers = validate_answers(items, [a.model_dump(exclude_none=True) for a in body.answers], header)
    records = annotation_records(items, answers, header["match_id"], body.annotator)
    ident = joblib.load(d / ".vision_work" / "identity.joblib")
    changed = apply_answers(ident, items, answers)  # in memory until the recompute has succeeded
    manifest = json.loads((d / "manifest.json").read_text())
    seg_recs = [r for r in iter_jsonl(d / "events.jsonl") if r["type"] == "camera_segment"]
    summary = refresh_from_identity(d, header, probe(manifest["video"]["path"]), header["match_id"], seg_recs, ident, models_dir=MODELS_DIR)
    joblib.dump(ident, d / ".vision_work" / "identity.joblib")
    claimed.rename(claimed.with_name(claimed.name.replace(".claimed-", ".").replace(".json", ANSWERED_SUFFIX)))
    (d / "clips.jsonl").unlink(missing_ok=True)  # clips are derived again from the corrected stream
    shutil.rmtree(CACHE_ROOT / d.name, ignore_errors=True)  # rendered clips may show old names
    librarian_cache.cache_clear()
    for path in (d / "review" / ANSWERS_FILE, feedback_dir() / "identity_annotations.jsonl"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in records))
    return {"answers": len(answers), "annotator": body.annotator, **changed, "record_counts": summary["record_counts"],
            "next_questions": summary.get("review_questions")}


# ---------------------------------------------------------------------------- the Foundry Librarian, open to judges

# Anyone can ask, so every limit is about cost and the single replica: short questions, a few per visitor, a cap per
# hour and per day across everyone, two at a time. The tools are narrowed to reads of public data: Regista's own
# search tools (no rendering, no file access beyond the match), and the Azure MCP Server's AI Search namespace only,
# so a crafted question cannot reach the Cosmos DB annotations container where reviewers' verdicts and notes live.
ASK_MAX_CHARS = 200
ASK_TIMEOUT_S = 90.0
PUBLIC_REGISTA_TOOLS = ["search_clips", "search_library", "list_matches"]
PUBLIC_AZURE_NAMESPACES = ("search",)


def _limit(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except ValueError:
        return default


class AskLimiter:
    """Sliding-window limits per visitor and for everyone, plus a cap on questions in flight. In memory: the app runs
    one replica, and a restart forgetting the counts is acceptable."""

    def __init__(self, per_visitor_per_min: int, per_visitor_per_hour: int, total_per_hour: int, total_per_day: int, concurrent: int):
        self.rules = [(60.0, per_visitor_per_min, True), (3600.0, per_visitor_per_hour, True), (3600.0, total_per_hour, False),
                      (86400.0, total_per_day, False)]
        self.concurrent = concurrent
        self.in_flight = 0
        self.hits: dict[str, list[float]] = {}
        self.lock = threading.Lock()

    @classmethod
    def from_env(cls) -> AskLimiter:
        return cls(_limit("REGISTA_ASK_PER_MIN", 3), _limit("REGISTA_ASK_PER_HOUR", 20), _limit("REGISTA_ASK_TOTAL_PER_HOUR", 60),
                   _limit("REGISTA_ASK_TOTAL_PER_DAY", 300), max(1, _limit("REGISTA_ASK_CONCURRENT", 2)))

    def acquire(self, visitor: str, now: float | None = None) -> tuple[bool, float, str]:
        """(allowed, seconds until it would be, which limit). On success the question is counted and in flight."""
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.in_flight >= self.concurrent:
                return False, 5.0, "busy"
            for window, cap, per_visitor in self.rules:
                key = visitor if per_visitor else "*"
                times = [t for t in self.hits.get(key, []) if now - t < window]
                self.hits[key] = times
                if len(times) >= cap:
                    return False, round(window - (now - times[0]), 1), f"{cap} per {int(window)}s" + (" per visitor" if per_visitor else "")
            for key in (visitor, "*"):
                self.hits.setdefault(key, []).append(now)
            self.in_flight += 1
            return True, 0.0, ""

    def release(self) -> None:
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)


_ask_limiter = AskLimiter.from_env()


def _visitor(request: Request) -> str:
    """The client address. Behind Container Apps ingress the real client is the last X-Forwarded-For entry (the
    proxy appends it; earlier entries are whatever the client sent)."""
    fwd = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in fwd.split(",") if h.strip()]
    return hops[-1] if hops else (request.client.host if request.client else "unknown")


def _librarian_agent():
    """The Foundry Librarian with public-safe tools, or None when Foundry is not configured. Tests replace this."""
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.foundry_enabled:
        return None
    from regista.cloud.foundry import FoundryLibrarianAgent

    return FoundryLibrarianAgent(config={"limit": 10, "regista_tools": PUBLIC_REGISTA_TOOLS, "azure_namespaces": PUBLIC_AZURE_NAMESPACES},
                                 cloud=cfg)


class AskIn(BaseModel):
    q: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ASK_MAX_CHARS)]


@app.post("/api/matches/{match_id}/ask")
async def ask(match_id: str, body: AskIn, request: Request) -> dict[str, Any]:
    """Ask the Foundry Librarian (Microsoft Agent Framework + Foundry, calling Regista's MCP server and the Azure MCP
    Server). Returns its answer, the clips the search found, and the tools it called. Without Foundry, the rule-based
    Librarian answers and ``answered_by`` says so. ``trace`` lists what ran, in order: [{name, kind: step|agent|model|
    tool, server: regista-mcp|azure-mcp|null, ms}], from the Agent Framework spans of this request; ``trace_note`` says
    when no spans were recorded and the trace is only the tools called, without timings."""
    from fastapi.responses import JSONResponse

    from regista.conversation import timed_step

    d = _match_dir(match_id)
    agent = _librarian_agent()
    if agent is None:
        trace: list[dict[str, Any]] = []
        out = timed_step(trace, "librarian.search_clips", search_clips, d, body.q, 10)
        out.update(answer=out["message"], answered_by="rules (Foundry is not configured on this deployment)", tools_used=[], trace=trace)
    else:
        ok, wait, which = _ask_limiter.acquire(_visitor(request))
        if not ok:
            return JSONResponse({"detail": f"Too many questions right now ({which}); try again in {wait:.0f}s."}, status_code=429,
                                headers={"Retry-After": str(max(1, int(wait)))})
        def run() -> dict[str, Any]:
            try:  # the slot frees when the work ends, even if the request has already timed out
                return agent.handle({"match_dir": str(d), "queries": [body.q]})
            finally:
                _ask_limiter.release()

        try:
            state = await asyncio.wait_for(run_in_threadpool(run), ASK_TIMEOUT_S)
        except asyncio.TimeoutError:
            raise HTTPException(504, "the Librarian took too long; try a simpler question")
        out = state["answers"][0]
        out.setdefault("tools_used", [])
        out.setdefault("trace", [])
    for r in out.get("results", []):
        r["video_url"] = f"/api/matches/{match_id}/clips/{r['clip_id']}.mp4"
    return out


# ---------------------------------------------------------------------------- a conversation with the Librarian

class ChatTurnIn(BaseModel):
    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(max_length=600)]


class ChatIn(BaseModel):
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ASK_MAX_CHARS)]
    state: dict[str, Any] | None = None   # the query so far, as the last reply returned it (checked again here)
    history: list[ChatTurnIn] = Field(default_factory=list, max_length=12)
    engine: Literal["rules", "foundry"] = "rules"

    @model_validator(mode="after")
    def _small_state(self) -> ChatIn:
        if self.state is not None and len(json.dumps(self.state, default=str)) > 2000:
            raise ValueError("state is too large")
        return self


def _chat_reply_foundry(d: Path, body: ChatIn, out: dict[str, Any]) -> tuple[str, list[str], str]:
    """The Foundry Librarian's reply for one turn (tests replace this). Returns (reply, tools called, answered by)."""
    from regista.cloud import CloudConfig
    from regista.cloud.foundry import foundry_chat_reply

    cfg = CloudConfig.from_env()
    if not cfg.foundry_enabled:
        return out["reply"], [], "rules (Foundry is not configured on this deployment)"
    from regista.aio import run_sync

    text, tools = run_sync(foundry_chat_reply(cfg, str(d), [t.model_dump() for t in body.history], body.message, out["understood"],
                                              out["results"], out["reply"],
                                              {"regista_tools": PUBLIC_REGISTA_TOOLS, "azure_namespaces": PUBLIC_AZURE_NAMESPACES}))
    return text, tools, f"foundry:{cfg.foundry_model}"


@app.post("/api/matches/{match_id}/chat")
async def chat(match_id: str, body: ChatIn, request: Request) -> dict[str, Any]:
    """One turn of a conversation. The search and the merged query are deterministic (``regista.conversation``):
    "his", "now the replays", "second half", "what about Ibarra?", "more", "make that a reel". With
    ``engine=foundry`` a Foundry model writes the reply from the conversation and the results, with the same public
    tools and limits as /ask; without Foundry, or if it fails, the rule-based reply stands and ``answered_by`` says so.
    ``trace`` lists what ran, in order, as in /ask: the in-process steps of the search, then (Foundry) the agent, model
    and tool spans of the reply; ``trace_note`` says when Foundry ran but no spans were recorded."""
    from fastapi.responses import JSONResponse

    from regista.conversation import chat_turn

    d = _match_dir(match_id)
    out = await run_in_threadpool(chat_turn, d, body.message, body.state)
    answered_by, tools = "rules", []
    if body.engine == "foundry" and out["intent"] != "reset":
        ok, wait, which = _ask_limiter.acquire(_visitor(request))
        if not ok:
            return JSONResponse({"detail": f"Too many questions right now ({which}); try again in {wait:.0f}s."}, status_code=429,
                                headers={"Retry-After": str(max(1, int(wait)))})

        def run() -> tuple[tuple[str, list[str], str], list[Any]]:
            from regista.cloud.telemetry import capture_spans

            try:
                with capture_spans("regista.chat") as cap:  # the Agent Framework spans of this reply, for its trace
                    reply = _chat_reply_foundry(d, body, out)
                return reply, cap.spans
            finally:
                _ask_limiter.release()

        try:
            (out["reply"], tools, answered_by), spans = await asyncio.wait_for(run_in_threadpool(run), ASK_TIMEOUT_S)
            if answered_by.startswith("foundry"):
                from regista.cloud.foundry import foundry_trace

                steps, note = foundry_trace(spans, tools)
                out["trace"] = out["trace"] + steps
                if note:
                    out["trace_note"] = note
        except asyncio.TimeoutError:
            answered_by = "rules (Foundry took too long)"
        except Exception as exc:  # noqa: BLE001 - the deterministic reply stands
            answered_by = f"rules (foundry fallback: {type(exc).__name__})"
    for r in out["results"]:
        r["video_url"] = f"/api/matches/{match_id}/clips/{r['clip_id']}.mp4"
    history = [t.model_dump() for t in body.history] + [{"role": "user", "text": body.message}, {"role": "assistant", "text": out["reply"][:600]}]
    return {**out, "reel": [{"clip_id": c, "video_url": f"/api/matches/{match_id}/clips/{c}.mp4"} for c in out["reel"]],
            "answered_by": answered_by, "tools_used": tools, "history": history[-12:]}


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

@app.get("/api/matches/{match_id}/review", dependencies=[StudioReader])
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


@app.get("/api/feedback", dependencies=[StudioReader])
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


# ---------------------------------------------------------------------------- the Studio and shared static files

from fastapi.staticfiles import StaticFiles  # noqa: E402

from regista.studio_api import router as _studio_router  # noqa: E402

app.include_router(_studio_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")  # product/, studio/, shared/: public files, no data
