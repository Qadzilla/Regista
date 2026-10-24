"""Regista as an HTTP service, with the clip viewer built in. Container-ready; no cloud dependency.

    uvicorn regista.api:app --reload            # http://localhost:8000  (viewer) and /docs (OpenAPI)
    REGISTA_DATA=data/synthetic/sample uvicorn regista.api:app

Two pages: the Product at ``/`` (open) and the Studio at ``/studio`` (regista.studio_api). Product reads are open.
Studio reads (reviewers' data, marked [studio]) need the ``X-Regista-Token`` header with the Studio view key or the
admin key; writes (marked [write]) need the admin key. REGISTA_READONLY=1 switches writes off entirely. With no key
configured, a plain local run (development) is open; with REGISTA_READONLY or REGISTA_CLOUD set it fails closed. The rules
live in regista.access.

Endpoints
---------
GET  /                                          the Product
GET  /studio                                    the Studio (data behind the Studio keys; see regista.studio_api)
GET  /api/health
GET  /api/matches                               match directories under REGISTA_DATA
POST /api/matches                               upload events.jsonl (+ tracks.jsonl); runs the Agent Framework workflow       [write]
GET  /api/matches/{match_id}                    roster, score, periods, duration_s, origin, key_moments (goals, for the timeline)
GET  /api/matches/{match_id}/clips?player=&tag=&min_watchability=&reason=
GET  /api/matches/{match_id}/reel.mp4?clips=    1 to 12 clips back to back, in the order given; rendered once, cached
GET  /api/matches/{match_id}/moments.csv?player=&clips=   the given clips in order, or a player's in match order (download)
GET  /api/matches/{match_id}/search?q=          the Librarian (rule-based, instant)
POST /api/matches/{match_id}/ask                the Foundry Librarian with its MCP tools; open, rate-limited, read-only tools; with its trace
POST /api/matches/{match_id}/chat               a conversation with the Librarian: follow-ups refine the search (rules, or Foundry: rate-limited);
                                                with its trace
GET  /api/matches/{match_id}/recap?player=&engine=   the match recap, told from a player's side if asked: every sentence cites its
                                                moment, a reel of its best clips (rules, or Foundry: rate-limited, checked, cached)
GET  /api/matches/{match_id}/clips/{clip_id}.mp4   rendered on demand, cached under REGISTA_CACHE (sizes, queue, budget: below)
GET  /api/matches/{match_id}/video.mp4          the whole broadcast, rendered on demand, cached
GET  /api/matches/{match_id}/report             synthetic realism report (markdown)
GET  /api/matches/{match_id}/review             the workflow's open review request                                           [studio]
POST /api/matches/{match_id}/review             answer it; the workflow resumes from its checkpoint                          [write]
POST /api/matches/{match_id}/clips/{clip_id}/verdict   one verdict from the viewer                                         [write]
GET  /api/matches/{match_id}/identity-review    open "who's who" questions for a vision match (crops, candidates, team sheets) [studio]
POST /api/matches/{match_id}/identity-review    answer them; identity is corrected and possession, events, clips recomputed   [write]
GET  /api/claims                                "that's me" claims: uploaded-match players linked to league players     [studio]
POST /api/claims                                claim one (pending until the Studio decides; regista.claims_api)          [write]
POST /api/claims/{claim_id}/decision            confirm (runs the workflow; the Profile agent refreshes) or reject        [write]
GET  /me, /api/player/uploads[/{id}[/questions|/crops/{name}]]   the Player view: uploads and their progress (regista.player_api)
POST /api/player/uploads                        a player's footage: stored, queued for the vision worker              [write]
POST /api/player/uploads/{id}/answers           "is this you?" answered; identity corrected, the match recomputed    [write]
GET  /api/feedback                              verdict counts, the learned model, agreement per scorer                       [studio]
POST /api/feedback/train                        retrain the watchability model                                             [write]

The service only reads and writes under REGISTA_DATA, REGISTA_CACHE, REGISTA_FEEDBACK_DIR and, for the Player view,
REGISTA_PLAYER_MATCHES and the Player store (REGISTA_PLAYER_DIR, or Azure Storage with REGISTA_STORAGE_ACCOUNT).
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
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StringConstraints, model_validator
from starlette.background import BackgroundTask

from regista import __version__
from regista.access import StudioReader, Writer, require_studio_reader, require_writer, role_of, write_mode  # noqa: F401
from regista.agents.roles import default_agents
from regista.clips import title_word
from regista.librarian import search_clips
from regista.schema import iter_jsonl, validate_jsonl

DATA_ROOT = Path(os.environ.get("REGISTA_DATA", "data/synthetic/sample"))
CACHE_ROOT = Path(os.environ.get("REGISTA_CACHE", "data/clips"))
# The Regista League (regista.season): a committed definition, matches regenerated from it into SEASON_ROOT on demand.
SEASON_LEAGUE = Path(os.environ.get("REGISTA_SEASON", "data/season/league.json"))
SEASON_ROOT = Path(os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
STATIC = Path(__file__).resolve().parent / "static"  # product/, studio/, shared/
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SYNC_TTL_S = 30.0
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")  # starts alphanumeric: never ".", ".hidden" or "-x"

@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Agent Framework and request spans go to Application Insights (and the Foundry project's Tracing page) whenever
    # the connection string is set, which deploy-app.sh does from a Container Apps secret. A no-op otherwise.
    from regista.cloud.telemetry import configure_tracing, flush_tracing

    configure_tracing("regista-api")
    if os.environ.get("REGISTA_PRERENDER") == "1":
        threading.Thread(target=_prerender, name="regista-prerender", daemon=True).start()
    if os.environ.get("REGISTA_SEASON_WARM", "1") == "1" and SEASON_LEAGUE.exists():
        from regista.season_api import warm_season

        threading.Thread(target=warm_season, name="regista-season", daemon=True).start()
    yield
    flush_tracing()


app = FastAPI(title="Regista", version=__version__, description="Every touch. Every replay. Every player. Found instantly.",
              lifespan=_lifespan)


# Access control (write_mode, require_writer, require_studio_reader) lives in regista.access.

# Defence in depth for the key the Studio keeps in sessionStorage: scripts only from this server (both pages load
# external files and run no inline script), no framing, no plugins. Styles stay inline-able: the pages set style
# attributes and the timeline injects its own <style>. /docs and /redoc (Swagger UI from a CDN) are left alone.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
SECURITY_HEADERS = [(b"content-security-policy", CSP.encode()), (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"), (b"referrer-policy", b"same-origin")]


class _Hardening:
    """Pure ASGI middleware: security headers on every response, and HEAD answered as GET without the body (uptime
    checkers use HEAD; FastAPI routes are GET-only and would say 405)."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        head = scope["method"] == "HEAD" and not path.startswith("/static/")  # StaticFiles answers HEAD itself
        if head:
            scope = {**scope, "method": "GET"}
        headers = not (path.startswith("/docs") or path.startswith("/redoc"))

        async def wrapped(message: dict) -> None:
            if message["type"] == "http.response.start" and headers:
                message = {**message, "headers": [*message.get("headers", []), *SECURITY_HEADERS]}
            elif message["type"] == "http.response.body" and head:
                message = {**message, "body": b""}
            await send(message)

        await self.app(scope, receive, wrapped)


app.add_middleware(_Hardening)


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
        season_dir = _season_match_dir(match_id)
        if season_dir is not None:
            return season_dir
        if match_id.startswith("pv_"):  # a Player-view upload the worker finished, fetched from the store (regista.player_api)
            from regista.player_api import player_match_dir

            player_dir = player_match_dir(match_id)
            if player_dir is not None:
                return player_dir
        if match_id in _library():
            raise HTTPException(409, f"match {match_id!r} is stored in Cosmos DB without its event stream: clips and labels can be "
                                     "read, but video, search and verdicts need the match on this replica")
        raise HTTPException(404, f"no match {match_id!r}")
    return d


def _is_season_match(match_id: str) -> bool:
    if not match_id.startswith("rl_") or not SEASON_LEAGUE.exists():
        return False
    from regista.season.build import fixture_of
    from regista.season.league import load_league_cached as load_league

    return fixture_of(load_league(SEASON_LEAGUE), match_id) is not None


def _season_match_dir(match_id: str) -> Path | None:
    """A Regista League match, regenerated from its fixture if needed (with tracks, for video); None if it is not one."""
    if not match_id.startswith("rl_") or not SEASON_LEAGUE.exists():
        return None
    from regista.season.build import ensure_tracks, fixture_of
    from regista.season.league import load_league_cached as load_league

    league = load_league(SEASON_LEAGUE)
    fx = fixture_of(league, match_id)
    return ensure_tracks(league, fx, SEASON_ROOT) if fx else None


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


def _profile_refresh():
    from regista.claims_api import _profile_refresh as bound

    return bound()


def _run_summary(mid: str, players: list[str], result) -> dict[str, Any]:
    labels = result.state.get("labels", {})
    out = {"match_id": mid, "players": players, "clips": {p: len(c) for p, c in result.state.get("clips", {}).items()},
           "pipeline_ok": result.ok, "statuses": result.statuses, "engine": "microsoft-agent-framework-workflow",
           "label_models": sorted({lb.get("model", "") for ls in labels.values() for lb in ls}),
           "cosmos": result.state.get("cosmos"), "search_index": result.state.get("search_index"),
           "review_log": result.state.get("review_log"), "profiles": result.state.get("profiles_refreshed"),
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
#
# The render endpoints are public, so anyone can ask for a render. Three more rules keep that from stalling the app or
# filling its disk (audit J2, 2026-10-21: 46 parallel requests at odd sizes kept /api/health from answering for a minute):
# - only the sizes the pages use are accepted (RENDER_WIDTHS x RENDER_FPS; anything else is 400), so the cache holds at
#   most a few files per clip;
# - renders run on their own small thread pool, so requests waiting for one hold no thread of the pool every other
#   endpoint runs on, and at most REGISTA_RENDER_QUEUE of them wait at once (more get 503 with Retry-After);
# - the cache keeps at most REGISTA_CACHE_MAX_MB (default 1024 MB): after each render the least recently served files go
#   first, never one that is being rendered or served right now.
RENDER_CONCURRENCY = max(1, int(os.environ.get("REGISTA_RENDER_CONCURRENCY", "1")))
RENDER_WIDTHS = {640, 1280}       # 1280 is what both pages ask for (the default); 640 a lighter size for slow links
RENDER_FPS = {25}
RENDER_QUEUE_MAX = max(1, int(os.environ.get("REGISTA_RENDER_QUEUE", "24")))
CACHE_MAX_BYTES = max(1, int(os.environ.get("REGISTA_CACHE_MAX_MB", "1024"))) * 1024 * 1024
_render_slots = threading.BoundedSemaphore(RENDER_CONCURRENCY)
_render_locks: dict[Path, threading.Lock] = {}
_render_locks_guard = threading.Lock()
_render_pool = ThreadPoolExecutor(max_workers=RENDER_CONCURRENCY + 2, thread_name_prefix="regista-render")
_render_waiting = {"n": 0}        # requests waiting for a render; touched only on the event loop
_serving: dict[Path, int] = {}    # cached files a response is sending right now, never evicted
_serving_guard = threading.Lock()


def _check_size(fps: float, width: int) -> None:
    if fps not in RENDER_FPS or width not in RENDER_WIDTHS:
        raise HTTPException(400, f"videos come at fps {sorted(RENDER_FPS)} and width {sorted(RENDER_WIDTHS)}")


def _evict_cache(keep: Path) -> None:
    """Delete the least recently served videos until the cache fits CACHE_MAX_BYTES. Files being rendered (temporary
    names start with ".") or served, and ``keep``, stay."""
    if not CACHE_ROOT.exists():
        return
    files = []
    for f in CACHE_ROOT.glob("*/*.mp4"):
        try:
            st = f.stat()
        except FileNotFoundError:
            continue
        files.append((st.st_mtime, st.st_size, f))
    total = sum(size for _t, size, _f in files)
    for _t, size, f in sorted(files, key=lambda x: x[0]):
        if total <= CACHE_MAX_BYTES:
            break
        with _serving_guard:
            if f.name.startswith(".") or f == keep or _serving.get(f) or _render_locks.get(f):
                continue
            f.unlink(missing_ok=True)
        total -= size


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
            _evict_cache(keep=out)
    finally:
        with _render_locks_guard:
            if _render_locks.get(out) is lock and not lock.locked():
                del _render_locks[out]
    return out


async def _video(out: Path, render: Any, filename: str | None = None) -> FileResponse:
    """Serve ``out``, rendering it first on the render pool if it is not cached. Marked as served until sent."""
    if not out.exists():
        if _render_waiting["n"] >= RENDER_QUEUE_MAX:
            raise HTTPException(503, "too many videos are rendering right now; try again shortly", headers={"Retry-After": "10"})
        _render_waiting["n"] += 1
        try:
            await asyncio.get_running_loop().run_in_executor(_render_pool, _render_once, out, render)
        finally:
            _render_waiting["n"] -= 1
    with _serving_guard:
        if not out.exists():  # evicted between the render and now: render it again on the next request
            raise HTTPException(503, "the video was just evicted from the cache; try again", headers={"Retry-After": "1"})
        _serving[out] = _serving.get(out, 0) + 1
        os.utime(out)  # recently served: evicted last

    def done() -> None:
        with _serving_guard:
            _serving[out] -= 1
            if not _serving[out]:
                del _serving[out]

    return FileResponse(out, media_type="video/mp4", filename=filename or out.name, background=BackgroundTask(done))


def _clip_cache_path(match_id: str, clip_id: str, fps: float, width: int) -> Path:
    return CACHE_ROOT / match_id / f"{clip_id}_{int(fps)}fps_{width}.mp4"


def _render_clip_cached(d: Path, clip: dict, label: dict | None, fps: float, width: int) -> Path:
    return _render_once(*_render_clip_job(d, clip, label, fps, width))


PRERENDER_PROGRESS: dict[str, Any] = {"running": False, "total": 0, "rendered": 0, "failed": 0, "started_at": None, "finished_at": None}


def _prerender(fps: float = 25.0, width: int = 1280) -> list[Path]:
    """Render the featured player's clips for every local match, best first, so the first visitor after a deploy finds
    them cached. Runs in a background thread at startup when REGISTA_PRERENDER=1 (set in the Dockerfile). Progress is
    kept in PRERENDER_PROGRESS for the Studio."""
    done, todo = [], []
    PRERENDER_PROGRESS.update(running=True, total=0, rendered=0, failed=0, started_at=time.time(), finished_at=None)
    try:
        for d in sorted(DATA_ROOT.iterdir()) if DATA_ROOT.exists() else []:
            manifest = d / "manifest.json"
            player = json.loads(manifest.read_text()).get("clips_for") if manifest.exists() else None
            if not player or not (d / "events.jsonl").exists():
                continue
            clips, labels = _clips(d, player)
            todo += [(d, c, labels.get(c["id"])) for c in sorted((c for c in clips if c["player_id"] == player),
                                                                  key=lambda c: (-labels.get(c["id"], {}).get("watchability", 0.0), c["t"]))]
        PRERENDER_PROGRESS["total"] = len(todo)
        for d, c, label in todo:
            try:
                done.append(_render_clip_cached(d, c, label, fps, width))
                PRERENDER_PROGRESS["rendered"] += 1
            except Exception as exc:  # noqa: BLE001  (one bad clip must not stop the rest)
                PRERENDER_PROGRESS["failed"] += 1
                print(f"prerender: {d.name}/{c['id']} failed: {exc!r}", flush=True)
    finally:
        PRERENDER_PROGRESS.update(running=False, finished_at=time.time())
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
            "tracing": bool(os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")),
            # Azure Container Apps sets CONTAINER_APP_NAME on every replica it runs; the Player store uses Azure Storage
            # (Blob and the vision-jobs queue) exactly when REGISTA_STORAGE_ACCOUNT is set (regista.player.store).
            "container_apps": bool(os.environ.get("CONTAINER_APP_NAME")),
            "storage": bool(os.environ.get("REGISTA_STORAGE_ACCOUNT"))}


@app.get("/api/matches")
def list_matches() -> list[dict[str, Any]]:
    """Matches on this replica (``source: local``, full features) and matches only Cosmos DB still holds
    (``source: cosmos``: clips and labels, no video). ``in_cosmos`` marks local matches the library also holds;
    ``featured`` (from manifest.json) marks the match the Product opens on; ``clip_count`` counts the clips on disk;
    ``title`` and ``subtitle`` (manifest.json, may be None) name the match for people."""
    library = _library()
    out = []
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            if (d / "events.jsonl").exists():
                m = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
                h = _header(d)
                n_clips = sum(r["type"] == "clip" for r in iter_jsonl(d / "clips.jsonl")) if (d / "clips.jsonl").exists() else 0
                out.append({"match_id": d.name, "score": m.get("score", h.get("score")), "clips_for": m.get("clips_for"),
                            "teams": _team_summary(h), "video_duration_s": h["video"]["duration_s"], "source": "local",
                            "video": True, "in_cosmos": d.name in library, "featured": bool(m.get("featured")),
                            "clip_count": n_clips, "title": m.get("title"), "subtitle": m.get("subtitle")})
    local = {m["match_id"] for m in out}
    for mid, h in sorted(library.items()):
        if mid not in local:
            out.append({"match_id": mid, "score": h.get("score"), "clips_for": None, "teams": _team_summary(h),
                        "video_duration_s": h.get("video", {}).get("duration_s"), "source": "cosmos", "video": False, "in_cosmos": True,
                        "featured": False, "clip_count": None, "title": None, "subtitle": None})
    return out


def _cosmos_match(match_id: str) -> dict[str, Any] | None:
    """The header of a match only Cosmos DB holds, or None when the match is local or unknown."""
    _check_id(match_id)
    if (DATA_ROOT / match_id / "events.jsonl").exists() or _is_season_match(match_id):
        return None  # a season match is always served from its regenerated stream, even if Cosmos DB holds a copy
    return _library().get(match_id)


@app.get("/api/matches/{match_id}")
def get_match(match_id: str) -> dict[str, Any]:
    h = _cosmos_match(match_id)
    if h is not None:
        clips, _labels = _feedback_store().clips_for(match_id)
        source, key_moments, manifest = "cosmos", [], {}  # the library keeps the header, not the event stream
        moments = {}
        for c in clips:
            moments[c["player_id"]] = moments.get(c["player_id"], 0) + 1
    else:
        d = _match_dir(match_id)
        h = _header(d)
        clips, _labels = _clips(d)
        source, key_moments = "local", _key_moments(d, h)
        manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        moments = _moment_counts(d, h, clips)
    players_with_clips = sorted({c["player_id"] for c in clips})
    return {"match_id": match_id, "teams": h["teams"], "players": h["players"], "score": h.get("score"), "video": h["video"],
            "periods": h["periods"], "players_with_clips": players_with_clips, "clip_count": len(clips), "source": source,
            "duration_s": (h.get("video") or {}).get("duration_s"), "origin": h.get("source"),
            "key_moments": key_moments, "moment_counts": moments, "title": manifest.get("title"), "subtitle": manifest.get("subtitle")}


def _moment_counts(d: Path, h: dict[str, Any], clips: list[dict]) -> dict[str, int]:
    """How many moments each player has, as GET /clips?player= would return them: the persisted clips for players who
    have them, else the clips derived on the fly. Players with none are left out."""
    from regista.clips import derive_clips

    counts: dict[str, int] = {}
    for c in clips:
        counts[c["player_id"]] = counts.get(c["player_id"], 0) + 1
    stream = None
    for p in h["players"]:
        if p["player_id"] in counts:
            continue
        stream = stream if stream is not None else list(iter_jsonl(d / "events.jsonl"))
        try:
            n = len(derive_clips(stream, p["player_id"])[0])
        except ValueError:
            n = 0
        if n:
            counts[p["player_id"]] = n
    return counts


def _match_minute(t: float, r: dict[str, Any], h: dict[str, Any]) -> int:
    """The minute a fan would say (0:13 is the 1st minute). Vision events carry no clock, so it comes from the periods."""
    if r.get("clock"):
        return r["clock"]["minute"] + 1
    period = next((p for p in reversed(h.get("periods") or []) if p["t"] <= t), None)
    if period is None:
        return int(t // 60) + 1
    return 45 * (period["period"] - 1) + int((t - period["t"]) // 60) + 1


def _key_moments(d: Path, h: dict[str, Any]) -> list[dict[str, Any]]:
    """Goals in match order, for the timeline: {t, kind, player_id, team_id, label}."""
    players = {p["player_id"]: p for p in h["players"]}
    out = []
    for r in iter_jsonl(d / "events.jsonl"):
        if r["type"] != "event" or r.get("event_type") != "goal":
            continue
        p = players.get(r.get("player_id"))
        who = f"{p['name']} ({p['kit_number']})" if p else "unknown scorer"
        out.append({"t": r["t"], "kind": "goal", "player_id": r.get("player_id"), "team_id": r.get("team_id"),
                    "label": f"Goal: {who}, {_match_minute(r['t'], r, h)}'"})
    return sorted(out, key=lambda m: m["t"])


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


def _render_clip_job(d: Path, clip: dict, label: dict | None, fps: float, width: int) -> tuple[Path, Any]:
    from regista.render.clips import render_clip
    from regista.render.draw import Style
    from regista.render.scene import Scene

    return (_clip_cache_path(d.name, clip["id"], fps, width),
            lambda tmp: render_clip(Scene.load(d), clip, label, tmp, fps, Style(width, round(width * 9 / 16))))


def _find_clip(match_id: str, clip_id: str) -> tuple[Path, dict, dict | None]:
    d = _match_dir(match_id)
    if not ID_RE.match(clip_id):
        raise HTTPException(400, "bad clip id")
    clips, labels = _clips(d, _player_of(clip_id))
    clip = next((c for c in clips if c["id"] == clip_id), None)
    if clip is None:
        raise HTTPException(404, f"no clip {clip_id}")
    return d, clip, labels.get(clip_id)


@app.get("/api/matches/{match_id}/clips/{clip_id}.mp4")
async def clip_video(match_id: str, clip_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    _check_size(fps, width)
    d, clip, label = await run_in_threadpool(_find_clip, match_id, clip_id)
    return await _video(*_render_clip_job(d, clip, label, fps, width))


@app.get("/api/matches/{match_id}/video.mp4")
async def match_video(match_id: str, fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    _check_size(fps, width)
    d = await run_in_threadpool(_match_dir, match_id)
    from regista.render.draw import Style
    from regista.render.scene import Scene
    from regista.render.video import render_video

    return await _video(CACHE_ROOT / match_id / f"broadcast_{int(fps)}fps_{width}.mp4",
                        lambda tmp: render_video(Scene.load(d), tmp, fps=fps, style=Style(width, round(width * 9 / 16)), end_card_s=3.0))


# ---------------------------------------------------------------------------- take-aways: a reel to download, moments to export

MAX_REEL_CLIPS = 12       # a reel renders on the replica's one CPU; twelve clips is about two minutes of video
MAX_EXPORT_CLIPS = 500
READABLE_REASONS = {"on_ball_main": "On the ball", "replay_appearance": "Replay", "highlight_appearance": "Highlight",
                    "closeup_appearance": "Closeup"}


def _clip_ids(raw: str, cap: int) -> list[str]:
    """Comma-separated clip ids, order kept: each must look like an id, none repeated, 1 to ``cap`` of them."""
    ids = [s.strip() for s in raw.split(",")]
    if not ids or not all(ID_RE.match(i) for i in ids):
        raise HTTPException(400, "clips must be comma-separated clip ids")
    if len(ids) > cap:
        raise HTTPException(400, f"at most {cap} clips at a time")
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "a clip id is repeated")
    return ids


def _clips_by_id(match_id: str, ids: list[str]) -> tuple[list[dict], dict[str, dict]]:
    """The clips named, in the order given, with their labels; 404 naming any that do not exist. Clips derived on the fly
    (a player with none on disk) count, as they do for the clip endpoint. Cosmos-only matches read the library."""
    if _cosmos_match(match_id) is not None:
        clips, labels = _feedback_store().clips_for(match_id)
    else:
        d = _match_dir(match_id)
        clips, labels = [], {}
        for player in dict.fromkeys(_player_of(i) for i in ids):
            more, more_labels = _clips(d, player)
            clips += more
            labels.update(more_labels)
    by_id = {c["id"]: c for c in clips}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise HTTPException(404, f"no clip(s) {', '.join(missing[:5])} in match {match_id}")
    return [by_id[i] for i in ids], labels


@app.get("/api/matches/{match_id}/reel.mp4")
async def reel_video(match_id: str, clips: str = Query(..., min_length=1, max_length=2000), fps: float = Query(25.0, gt=0, le=60),
                     width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    """The clips back to back in the order given, each with its title card. Rendered once and cached by its content."""
    import hashlib

    from regista.render.clips import render_reel
    from regista.render.draw import Style
    from regista.render.scene import Scene

    _check_size(fps, width)

    def find() -> tuple[Path, list[str], list[dict], dict[str, dict]]:
        d = _match_dir(match_id)
        ids = _clip_ids(clips, MAX_REEL_CLIPS)
        return (d, ids, *_clips_by_id(match_id, ids))

    d, ids, chosen, labels = await run_in_threadpool(find)
    key = hashlib.sha256(json.dumps([ids, fps, width]).encode()).hexdigest()[:20]
    return await _video(CACHE_ROOT / match_id / f"reel_{key}.mp4",
                        lambda tmp: render_reel(Scene.load(d), chosen, labels, tmp, fps, Style(width, round(width * 9 / 16)), keep_order=True),
                        filename=f"regista_{match_id}_reel.mp4")


def _csv_cell(v: Any) -> Any:
    """Text a spreadsheet would run as a formula (titles and tags can come from uploads or models) is quoted as text."""
    return f"'{v}" if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@app.get("/api/matches/{match_id}/moments.csv", response_class=PlainTextResponse)
def moments_csv(match_id: str, player: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_]{1,40}$")] = None,
                clips: Annotated[str | None, Query(min_length=1, max_length=20000)] = None) -> PlainTextResponse:
    """A scout's list: the clips given, in that order, or every clip of ``player`` in match order. ``clips`` wins when
    both are given. Columns: time, end (m:ss), kind, tags, title, watchability, then time_s, end_s and clip_id."""
    import csv
    import io

    _check_id(match_id)
    if clips:
        chosen, labels = _clips_by_id(match_id, _clip_ids(clips, MAX_EXPORT_CLIPS))
    elif player:
        if _cosmos_match(match_id) is not None:
            found, labels = _feedback_store().clips_for(match_id, player)
        else:
            d = _match_dir(match_id)
            if player not in {p["player_id"] for p in _header(d)["players"]}:
                raise HTTPException(404, f"no player {player!r} in match {match_id}")
            found, labels = _clips(d, player)
        chosen = sorted((c for c in found if c["player_id"] == player), key=lambda c: (c["t"], c["id"]))
    else:
        raise HTTPException(400, "give player= or clips=")

    def mmss(t: float) -> str:
        return f"{int(t // 60)}:{int(t % 60):02d}"

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["time", "end", "kind", "tags", "title", "watchability", "time_s", "end_s", "clip_id"])
    for c in chosen:
        lb = labels.get(c["id"]) or {}
        tags = "; ".join(dict.fromkeys(title_word(t) for t in lb.get("tags", []) if t not in READABLE_REASONS))  # "take-on", "assist"
        w.writerow([mmss(c["t"]), mmss(c["t_end"]), READABLE_REASONS.get(c["reason"], c["reason"].replace("_", " ")), _csv_cell(tags),
                    _csv_cell(lb.get("title", "")), "" if lb.get("watchability") is None else round(lb["watchability"], 2),
                    round(c["t"], 2), round(c["t_end"], 2), c["id"]])
    name = f"regista_{match_id}_{player if player and not clips else 'selection'}_moments.csv"
    return PlainTextResponse(buf.getvalue(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


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
    from regista.vision.package import work_dir_for

    d = _match_dir(match_id)
    work = work_dir_for(d)  # d itself for a vision run; for a packaged match, its full output if it is on this machine
    if work is None:
        raise HTTPException(409, "this match has no identity result to correct (it was not written by the vision layer)")
    q = _queue_path(work)
    claimed = q.with_name(f"identity_review.claimed-{uuid.uuid4().hex[:8]}.json")
    try:
        os.rename(q, claimed)
    except FileNotFoundError:
        raise HTTPException(409, "no open identity questions (already answered, or none were asked)")
    try:
        out = await run_in_threadpool(_apply_identity_review, work, claimed, body, d)
    except ValueError as exc:
        os.rename(claimed, q)  # nothing was applied; the questions stay open
        raise HTTPException(422, str(exc))
    except Exception:
        os.rename(claimed, q)
        raise
    return out


def _apply_identity_review(d: Path, claimed: Path, body: IdentityReviewIn, served: Path | None = None,
                           models_dir: Path | None = None) -> dict[str, Any]:
    """Apply answers to the vision output ``d``; when the app serves a package of it (``served``), package it again.
    ``models_dir`` overrides the models the match was made with (a Player-view match made by the cloud worker)."""
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
    run = d / ".vision_work" / "run.json"  # the models the match was made with, when run_vision recorded them
    models = models_dir or (Path(json.loads(run.read_text())["models_dir"]) if run.exists() else MODELS_DIR)
    summary = refresh_from_identity(d, header, probe(manifest["video"]["path"]), header["match_id"], seg_recs, ident,
                                    models_dir=models if models.exists() else MODELS_DIR)
    joblib.dump(ident, d / ".vision_work" / "identity.joblib")
    claimed.rename(claimed.with_name(claimed.name.replace(".claimed-", ".").replace(".json", ANSWERED_SUFFIX)))
    (d / "clips.jsonl").unlink(missing_ok=True)  # clips are derived again from the corrected stream
    shutil.rmtree(CACHE_ROOT / d.name, ignore_errors=True)  # rendered clips may show old names
    librarian_cache.cache_clear()
    for path in (d / "review" / ANSWERS_FILE, feedback_dir() / "identity_annotations.jsonl"):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in records))
    if served is not None and served != d:
        from regista.vision.package import repackage

        repackage(d, served)  # the corrected match, the answers and the next questions, without machine paths
        shutil.rmtree(CACHE_ROOT / served.name, ignore_errors=True)
        librarian_cache.cache_clear()
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
            for key in (visitor, "*"):  # keep each key's hits for its longest window, so every window counts them
                longest = max(w for w, _cap, per_visitor in self.rules if per_visitor == (key != "*"))
                self.hits[key] = [t for t in self.hits.get(key, []) if now - t < longest]
            for window, cap, per_visitor in self.rules:
                times = [t for t in self.hits[visitor if per_visitor else "*"] if now - t < window]
                if len(times) >= cap:
                    return False, round(window - (now - times[0]), 1), f"{cap} per {int(window)}s" + (" per visitor" if per_visitor else "")
            for key in (visitor, "*"):
                self.hits[key].append(now)
            self.in_flight += 1
            return True, 0.0, ""

    def release(self) -> None:
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        """Read-only counts for the Studio: questions from everyone in the last minute, hour and day, against the limits."""
        now = time.monotonic() if now is None else now
        with self.lock:
            everyone = list(self.hits.get("*", []))
            visitors = sum(1 for k, ts in self.hits.items() if k != "*" and any(now - t < 3600 for t in ts))
            in_flight = self.in_flight
        (_, per_min, _), (_, per_hour, _), (_, total_hour, _), (_, total_day, _) = self.rules
        return {"last_minute": sum(1 for t in everyone if now - t < 60), "last_hour": sum(1 for t in everyone if now - t < 3600),
                "last_day": sum(1 for t in everyone if now - t < 86400), "visitors_last_hour": visitors, "in_flight": in_flight,
                "limits": {"per_visitor_per_min": per_min, "per_visitor_per_hour": per_hour, "total_per_hour": total_hour,
                           "total_per_day": total_day, "concurrent": self.concurrent}}


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


# ---------------------------------------------------------------------------- the match recap

def _recap_writer():
    """The Foundry Recap agent on this deployment, or None when Foundry is not configured (tests replace this)."""
    from regista.recap import foundry_writer

    return foundry_writer()


def _recap_cache_path(match_id: str, player: str | None) -> Path:
    return CACHE_ROOT / match_id / f"recap_{player or 'match'}.json"


def _cached_recap(d: Path, match_id: str, player: str | None, basis: str) -> dict[str, Any] | None:
    """A Foundry recap already written from these same facts: cached on this replica, or the workflow's recap.json."""
    for path, who in ((_recap_cache_path(match_id, player), player), (d / "recap.json", None)):
        if who != player or not path.exists():
            continue
        try:
            out = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if out.get("basis") == basis and out.get("player_id") == player and str(out.get("answered_by", "")).startswith("foundry:"):
            return out
    return None


def _recap_out(match_id: str, out: dict[str, Any]) -> dict[str, Any]:
    out = dict(out)
    out["clips"] = {cid: {**c, "video_url": f"/api/matches/{match_id}/clips/{cid}.mp4"} for cid, c in out.get("clips", {}).items()}
    out["reel_url"] = f"/api/matches/{match_id}/reel.mp4?clips={','.join(out['reel'])}" if out.get("reel") else None
    return out


@app.get("/api/matches/{match_id}/recap")
async def match_recap(match_id: str, request: Request, player: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_]{1,40}$")] = None,
                      engine: Literal["rules", "foundry"] = "rules") -> dict[str, Any]:
    """The match recap (regista.recap): ``{headline, paragraphs: [{text, cites, sentences: [{text, cites}]}], reel, reel_url,
    clips, answered_by, trace, checked}``, told from ``player``'s side when given. Every sentence cites a clip or an
    event (``{t, clip_id?, event_id?}``); ``clips`` holds the cited and reel clips with their video. With
    ``engine=foundry`` a Foundry agent writes it from the same facts, under the Ask limits; sentences that cite nothing,
    use numbers the facts do not hold, or use jargon are dropped and ``checked`` lists them. A Foundry recap is cached on
    this replica for as long as the facts it was written from hold. Without Foundry, over the limits, slow or failing,
    the rules recap stands and ``answered_by`` says why (never a 429)."""
    from regista.recap import prepare, write

    d = _match_dir(match_id)
    try:
        prepared = await run_in_threadpool(prepare, d, player)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if engine == "rules":
        return _recap_out(match_id, await run_in_threadpool(write, prepared, "rules"))
    cached = await run_in_threadpool(_cached_recap, d, match_id, player, prepared.basis)
    if cached is not None:
        return _recap_out(match_id, {**cached, "cached": True})
    writer = _recap_writer()
    if writer is None:
        out = await run_in_threadpool(write, prepared, "rules")
        return _recap_out(match_id, {**out, "engine": "foundry", "answered_by": "rules (Foundry is not configured on this deployment)"})
    ok, wait, which = _ask_limiter.acquire(_visitor(request))
    if not ok:
        out = await run_in_threadpool(write, prepared, "rules")
        return _recap_out(match_id, {**out, "engine": "foundry",
                                     "answered_by": f"rules (Foundry is busy: {which}; try again in {max(1, int(wait))}s)"})

    def run() -> dict[str, Any]:
        try:  # the slot frees when the work ends, even if the request has already timed out
            return write(prepared, "foundry", writer)
        finally:
            _ask_limiter.release()

    try:
        out = await asyncio.wait_for(run_in_threadpool(run), ASK_TIMEOUT_S)
    except asyncio.TimeoutError:
        out = {**await run_in_threadpool(write, prepared, "rules"), "engine": "foundry", "answered_by": "rules (Foundry took too long)"}
    if str(out.get("answered_by", "")).startswith("foundry:"):
        path = _recap_cache_path(match_id, player)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{uuid.uuid4().hex[:8]}.tmp")
            tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass  # a cache miss next time, nothing worse
    return _recap_out(match_id, out)


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

        pipeline = WorkflowPipeline(_pipeline_agents(), dest / "agents", checkpoint_dir=dest / "agents" / "checkpoints" if review else None,
                                    profile_refresh=_profile_refresh())
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
    pipeline = WorkflowPipeline(_pipeline_agents(), d / "agents", checkpoint_dir=d / "agents" / "checkpoints",
                                profile_refresh=_profile_refresh())
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

from regista.claims_api import router as _claims_router  # noqa: E402
from regista.player_api import router as _player_router  # noqa: E402
from regista.season_api import router as _season_router  # noqa: E402
from regista.studio_api import router as _studio_router  # noqa: E402
from regista.terminal_api import router as _terminal_router  # noqa: E402

app.include_router(_season_router)
app.include_router(_terminal_router)
app.include_router(_claims_router)
app.include_router(_player_router)
app.include_router(_studio_router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")  # product/, studio/, shared/: public files, no data
