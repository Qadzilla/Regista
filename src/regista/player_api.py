"""The Player view's API (``/me``): a (synthetic) player uploads their match footage, Regista's vision workflow runs on
it in the cloud, and the match joins their profile.

POST /api/player/uploads                     multipart: video (mp4, at most 300 MB), global_id, opponent_club_id, side
                                             (home or away); for a catalogue club also competition_id, date, camera and
                                             consent (all required then). Stores the video, writes the upload record,
                                             queues the vision job                                              [write]
GET  /api/player/uploads?global_id=          the uploads, newest first, each with its stages (live progress)
GET  /api/player/uploads/{upload_id}         one upload: record, stages, the player, and links once the match is ready
GET  /api/player/uploads/{upload_id}/questions          "is this you?": the match's Who's who questions about the
                                                        uploader (their kit number on their team), with crops
GET  /api/player/uploads/{upload_id}/crops/{name}       a question's picture
POST /api/player/uploads/{upload_id}/answers [write]    {answers: [{item_id, is_me}]}: applied through the identity
                                             review path (identity corrected; possession, events and clips recomputed
                                             here), the match pushed back to the store, the record set to done
GET  /me                                     the Player view page (static/me/)

The store (``regista.player.store``: Azure Blob + Queue, or a local folder) is the contract with the worker. A match the
worker finished (``status`` done or needs_review) is fetched from the store into ``REGISTA_PLAYER_MATCHES`` on first use;
``regista.api._match_dir`` asks ``player_match_dir`` for ``pv_…`` ids, so clips, video, reels and the Clip view work on
it like any other match. ``uploaded_matches`` lists the done ones for the profiles (``regista.season.profiles``): each
counts in its uploader's profile, under the global id the team sheet already carries.

Reads are public: synthetic players, no secrets (the record holds no paths or keys). Writes need the admin key.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, StringConstraints
from starlette.datastructures import UploadFile

from regista.access import Writer
from regista.player.store import MAX_VIDEO_BYTES, LocalStore, Store, UploadRecord, match_id_for, new_upload_id

router = APIRouter()
STATIC = Path(__file__).resolve().parent / "static"
PLAYER_MATCHES = Path(os.environ.get("REGISTA_PLAYER_MATCHES", "data/player/matches"))
UPLOAD_RE = re.compile(r"^up_[a-z0-9]{4,40}$")
MATCH_RE = re.compile(r"^pv_[a-z0-9]{4,40}$")
GID_RE = re.compile(r"^pl_[a-z0-9_]{1,40}$")
CLUB_RE = re.compile(r"^cl_[a-z0-9_]{1,40}$")
CROP_RE = re.compile(r"^(tr|cw)_[A-Za-z0-9_.\-]{1,80}\.jpg$")
COMP_RE = re.compile(r"^co_[a-z0-9_]{1,40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CAMERAS = ("tripod", "phone", "drone", "broadcast")   # a label of the upload (regista.catalogue.taxonomy.CAMERAS)
CONSENT_YES = ("yes", "true", "on", "1")
UPLOADS_NOTE = ("Uploaded through the Player view; not counted in the catalogue's numbers, which count each competition's "
                "own uploaded matches only (England: the Regista League's fixtures).")
READY = ("done", "needs_review")      # the worker has written the match folder
FORM_SLACK = 1 << 20                  # multipart framing and the three small fields, on top of the video
SYNC_TTL_S = 15.0                     # how often a served match checks the store for a newer version
LIST_TTL_S = 30.0                     # how often the profiles list the store's finished uploads

UploadId = Annotated[str, StringConstraints(pattern=UPLOAD_RE.pattern)]


# ---------------------------------------------------------------------------- the store, the league

_stores: dict[tuple[str, str], Store] = {}
_stores_lock = threading.Lock()


def store() -> Store:
    """``store_from_env()``, kept per backend: Azure clients connect once; tests point REGISTA_PLAYER_DIR per test."""
    account = os.environ.get("REGISTA_STORAGE_ACCOUNT")
    key = ("azure", account) if account else ("local", os.environ.get("REGISTA_PLAYER_DIR", "data/player"))
    with _stores_lock:
        s = _stores.get(key)
        if s is None:
            if account:
                from regista.player.store import AzureStore

                s = AzureStore(account)
            else:
                s = LocalStore(key[1])
            _stores[key] = s
        return s


def _league() -> dict[str, Any]:
    from regista import api
    from regista.season.league import load_league_cached

    if not api.SEASON_LEAGUE.exists():
        raise HTTPException(404, "no league on this server (data/season/league.json)")
    return load_league_cached(api.SEASON_LEAGUE)


def _competition(competition_id: str | None) -> dict[str, Any]:
    """The league-shaped competition an upload belongs to: the Regista League (None, or England's id), else a catalogue
    competition (``regista.catalogue.store``). Public fields only are read from it (squads, clubs, season)."""
    from regista import api
    from regista.catalogue import store as cat_store
    from regista.catalogue.taxonomy import ENGLAND_ID

    if competition_id is None or competition_id == ENGLAND_ID:
        return _league()
    if not COMP_RE.match(competition_id):
        raise HTTPException(422, "competition_id must be a catalogue competition id (co_…)")
    comp = cat_store.competition(competition_id, api.CATALOGUE) if api.CATALOGUE.exists() else None
    if comp is None:
        raise HTTPException(422, f"no competition {competition_id!r} in the catalogue")
    return comp


def _person(gid: str, competition_id: str | None = None) -> dict[str, Any]:
    from regista.season.league import people

    comp = _competition(competition_id)
    p = people(comp).get(gid)
    if p is None:
        where = "the league" if competition_id is None else comp["league"]
        raise HTTPException(404 if competition_id is None else 422, f"no player {gid!r} in {where}")
    return p


def upload_id_for(match_id: str) -> str:
    return "up_" + match_id.removeprefix("pv_")


# ---------------------------------------------------------------------------- finished matches reach the app

_sync_locks: dict[str, threading.Lock] = {}
_checked: dict[str, float] = {}


def _marker(match_id: str) -> Path:
    return PLAYER_MATCHES / f".{match_id}.synced.json"


def _synced_version(match_id: str) -> float | None:
    m = _marker(match_id)
    try:
        return float(json.loads(m.read_text())["updated_at"]) if m.exists() else None
    except (ValueError, KeyError, OSError):
        return None


def _mark(match_id: str, rec: UploadRecord) -> None:
    PLAYER_MATCHES.mkdir(parents=True, exist_ok=True)
    _marker(match_id).write_text(json.dumps({"upload_id": rec.upload_id, "updated_at": rec.updated_at, "status": rec.status}))


def _fetch(rec: UploadRecord) -> Path | None:
    """Copy ``matches/{match_id}`` from the store into PLAYER_MATCHES, replacing an older copy in one rename."""
    from regista import api

    mid = rec.match_id or match_id_for(rec.upload_id)
    PLAYER_MATCHES.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{mid}.", dir=PLAYER_MATCHES))
    try:
        if store().get_match(mid, tmp) == 0 or not (tmp / "events.jsonl").exists():
            return None
        dest = PLAYER_MATCHES / mid
        old = None
        if dest.exists():
            old = dest.with_name(f".{mid}.old.{time.time_ns()}")
            os.rename(dest, old)
        os.rename(tmp, dest)
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)
        shutil.rmtree(api.CACHE_ROOT / mid, ignore_errors=True)  # rendered clips of the older version
        _mark(mid, rec)
        _forget_listing()  # the profiles see the new version on their next read
        return dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_match(rec: UploadRecord) -> Path | None:
    """The upload's match folder on this replica, fetched (again) when the store holds a newer version; None while the
    worker has not finished it."""
    if rec.status not in READY:
        return None
    mid = rec.match_id or match_id_for(rec.upload_id)
    with _stores_lock:
        lock = _sync_locks.setdefault(mid, threading.Lock())
    with lock:
        d = PLAYER_MATCHES / mid
        have = _synced_version(mid)
        if (d / "events.jsonl").exists() and have is not None and have >= rec.updated_at:
            return d
        return _fetch(rec) or ((d / "events.jsonl").exists() and d) or None


def player_match_dir(match_id: str) -> Path | None:
    """For ``regista.api._match_dir``: the folder of a finished Player-view match, else None. The local copy is served
    as it is between checks; at most every SYNC_TTL_S the record is read again for a newer version."""
    if not MATCH_RE.match(match_id):
        return None
    d = PLAYER_MATCHES / match_id
    if (d / "events.jsonl").exists() and time.time() - _checked.get(match_id, 0.0) < SYNC_TTL_S:
        return d
    try:
        rec = store().get_record(upload_id_for(match_id))
        out = ensure_match(rec) if rec is not None else None
    except Exception:  # noqa: BLE001 - the store is unreachable: serve the copy this replica has
        return d if (d / "events.jsonl").exists() else None
    _checked[match_id] = time.time()
    return out


_listed: dict[str, Any] = {"t": 0.0, "rows": []}
_list_lock = threading.RLock()  # _fetch, called while listing, forgets the listing too


def uploaded_matches(force: bool = False) -> list[dict[str, Any]]:
    """Done Player-view matches on this replica, for the profiles: {match_id, match_dir, player_id, global_id,
    upload_id}, one per upload. The uploader counts, found by the global id on the team sheet (else their club's kit
    number on their side). Never raises: without the store, the profiles are the league's and the claims'."""
    with _list_lock:
        if not force and time.time() - _listed["t"] < LIST_TTL_S:
            return list(_listed["rows"])
        rows = []
        try:
            records = [r for r in store().list_records() if r.status == "done"]
        except Exception:  # noqa: BLE001 - no store (or unreachable): nothing uploaded counts yet
            records = []
        for rec in sorted(records, key=lambda r: r.created_at):
            try:
                d = ensure_match(rec)
            except Exception:  # noqa: BLE001 - one broken upload never hides the others
                d = None
            pid = _uploader_pid(d, rec) if d else None
            if d and pid:
                rows.append({"match_id": d.name, "match_dir": str(d), "player_id": pid, "global_id": rec.global_id,
                             "upload_id": rec.upload_id, "competition_id": rec.competition_id})
        _listed.update(t=time.time(), rows=rows)
        return list(rows)


def _forget_listing() -> None:
    with _list_lock:
        _listed["t"] = 0.0


def player_uploads(competition_id: str | None = None, global_id: str | None = None) -> list[dict[str, Any]]:
    """Finished Player-view uploads, named for the catalogue's pages and never counted there (``UPLOADS_NOTE``): those
    of one competition's clubs (England's: the Regista League's own friendlies too, whose records name no competition)
    and/or of one player. Newest first. Never raises: without the store there are none."""
    from regista.catalogue.taxonomy import ENGLAND_ID
    from regista.season.league import people

    try:
        records = [r for r in store().list_records() if r.status == "done"]
    except Exception:  # noqa: BLE001 - no store (or unreachable): nothing to name
        return []
    out = []
    for rec in sorted(records, key=lambda r: -r.created_at):
        cid = rec.competition_id or ENGLAND_ID
        if (competition_id and cid != competition_id) or (global_id and rec.global_id != global_id):
            continue
        try:
            d = ensure_match(rec)
        except Exception:  # noqa: BLE001 - the record still names the upload
            d = None
        manifest = json.loads((d / "manifest.json").read_text()) if d and (d / "manifest.json").exists() else {}
        try:
            comp = _competition(rec.competition_id)
            p = people(comp).get(rec.global_id) or {}
            opp = next((c for c in comp["clubs"] if c["club_id"] == rec.opponent_club_id), None)
        except HTTPException:
            p, opp = {}, None
        mid = rec.match_id or match_id_for(rec.upload_id)
        pid = _uploader_pid(d, rec) if d else None
        out.append({"upload_id": rec.upload_id, "match_id": mid, "competition_id": cid, "global_id": rec.global_id,
                    "name": p.get("name"), "club_id": rec.club_id, "club": p.get("club"),
                    "opponent_club_id": rec.opponent_club_id, "opponent": opp["name"] if opp else None, "side": rec.side,
                    "date": rec.date_played or manifest.get("date"), "camera": rec.camera,
                    "uploader": {"type": rec.uploader_type, "global_id": rec.global_id, "name": p.get("name")},
                    "title": manifest.get("title"), "source": "upload",
                    "kind": "friendly" if rec.competition_id is None else "match",
                    "clip_view": f"/?match={mid}" + (f"&player={pid}" if pid else ""), "counted": False,
                    "note": UPLOADS_NOTE})
    return out


def _uploader_pid(d: Path, rec: UploadRecord) -> str | None:
    from regista.schema import iter_jsonl

    header = next(iter_jsonl(d / "events.jsonl"))
    for p in header.get("players", []):
        if p.get("global_player_id") == rec.global_id:
            return p["player_id"]
    team = header.get(f"{rec.side}_team_id")
    return next((p["player_id"] for p in header.get("players", []) if p["team_id"] == team and p["kit_number"] == rec.kit_number), None)


# ---------------------------------------------------------------------------- what the page reads

STAGE_LABELS = {"queued": "Queued", "shots": "Shots", "identity": "Identity", "identity_review": "Is this you?",
                "possession_vision": "Possession", "events_vision": "Events", "vision_writer": "Writer"}


def _view(rec: UploadRecord, d: Path | None = None) -> dict[str, Any]:
    """The record as the page reads it: no paths, plus who uploaded and, once the match is here, where to watch it."""
    from urllib.parse import quote

    out = rec.to_json()
    try:
        p = _person(rec.global_id, rec.competition_id)
        out["player"] = {"global_id": rec.global_id, "name": p["name"], "club": p["club"], "short_name": p["short_name"],
                         "kit_number": p["kit_number"], "position": p["position"]}
        comp = _competition(rec.competition_id)
        clubs = {c["club_id"]: c for c in comp["clubs"]}
        opp = clubs.get(rec.opponent_club_id)
        out["opponent"] = {"club_id": rec.opponent_club_id, "name": opp["name"], "short_name": opp["short_name"]} if opp else None
        if rec.competition_id:
            lab = comp.get("competition") or {}
            out["competition"] = {"competition_id": rec.competition_id, "name": comp["league"],
                                  **{k: lab.get(k) for k in ("country", "tier", "age_group", "gender")}}
    except HTTPException:
        out["player"], out["opponent"] = None, None
    out["links"] = None
    if d is not None:
        pid = _uploader_pid(d, rec)
        mid = quote(d.name)
        manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        out["match"] = {"match_id": d.name, "player_id": pid, "title": manifest.get("title")}
        out["links"] = {"clip_view": f"/?match={mid}" + (f"&player={quote(pid)}" if pid else ""),
                        "profile": f"/players/{quote(rec.global_id)}",
                        "clips": f"/api/matches/{mid}/clips" + (f"?player={quote(pid)}" if pid else "")}
    return out


def _record(upload_id: str) -> UploadRecord:
    if not UPLOAD_RE.match(upload_id):
        raise HTTPException(400, "bad upload id")
    rec = store().get_record(upload_id)
    if rec is None:
        raise HTTPException(404, f"no upload {upload_id}")
    return rec


@router.get("/me", response_class=HTMLResponse, include_in_schema=False)
def me_page() -> str:
    return (STATIC / "me" / "index.html").read_text(encoding="utf-8")


@router.get("/api/player/uploads")
async def list_uploads(global_id: Annotated[str | None, Query(pattern=GID_RE.pattern)] = None,
                       limit: int = Query(20, ge=1, le=100)) -> dict[str, Any]:
    def run() -> list[dict[str, Any]]:
        rows = [r for r in store().list_records() if not global_id or r.global_id == global_id][:limit]
        return [_view(r, _ready_dir(r)) for r in rows]

    return {"uploads": await run_in_threadpool(run), "max_mb": MAX_VIDEO_BYTES // (1 << 20), "store": store().kind}


def _ready_dir(rec: UploadRecord) -> Path | None:
    try:
        return ensure_match(rec)
    except Exception:  # noqa: BLE001 - the record still reads; the match follows on the next poll
        return None


@router.get("/api/player/uploads/{upload_id}")
async def get_upload(upload_id: str) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        rec = _record(upload_id)
        return _view(rec, _ready_dir(rec))

    return await run_in_threadpool(run)


# ---------------------------------------------------------------------------- the upload

def _bad(status: int, message: str) -> HTTPException:
    return HTTPException(status, message)


@router.post("/api/player/uploads", status_code=201, dependencies=[Writer])
async def create_upload(request: Request) -> dict[str, Any]:
    """Take the player's footage. The body is read only after the key is checked (no form parameters, so FastAPI does
    not parse it first), its declared size is checked before a byte is read, and the video is streamed to the store
    from the spooled upload, never held in memory."""
    length = request.headers.get("content-length")
    if length is None or not length.isdigit():
        raise _bad(411, "send the upload with a Content-Length")
    if int(length) > MAX_VIDEO_BYTES + FORM_SLACK:
        raise _bad(413, f"the video is larger than {MAX_VIDEO_BYTES // (1 << 20)} MB")
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise _bad(415, "send multipart/form-data with video, global_id, opponent_club_id and side")
    form = await request.form(max_files=1, max_fields=12)
    try:
        video = form.get("video")
        gid, opp, side = (str(form.get(k) or "").strip() for k in ("global_id", "opponent_club_id", "side"))
        cid, played, camera, consent = (str(form.get(k) or "").strip() for k in ("competition_id", "date", "camera",
                                                                                  "consent"))
        side = side or "home"
        if not isinstance(video, UploadFile):
            raise _bad(422, "attach the footage as the video field")
        if not GID_RE.match(gid):
            raise _bad(422, "global_id must be a league player id (pl_…)")
        if not CLUB_RE.match(opp):
            raise _bad(422, "opponent_club_id must be a league club id (cl_…)")
        if side not in ("home", "away"):
            raise _bad(422, "side is home or away")
        extra = _catalogue_fields(cid or None, played or None, camera or None, consent)
        name = (video.filename or "").lower()
        if not name.endswith(".mp4") or (video.content_type or "video/mp4") not in ("video/mp4", "application/octet-stream"):
            raise _bad(415, "the footage must be an MP4 file (.mp4)")
        head = await video.read(12)
        if len(head) < 12 or head[4:8] != b"ftyp":
            raise _bad(415, "that file is not an MP4 video")
        await video.seek(0)
        comp_id = extra["competition_id"]
        person = _person(gid, comp_id)
        if opp == person["club_id"]:
            raise _bad(422, f"{person['club']} cannot play itself: pick another club")
        if opp not in {c["club_id"] for c in _competition(comp_id)["clubs"]}:
            if comp_id is None:
                raise _bad(404, f"no club {opp!r} in the league")
            raise _bad(422, f"{opp!r} is not a club of {_competition(comp_id)['league']}: pick a club from that competition")
        rec = UploadRecord(upload_id=new_upload_id(), global_id=gid, club_id=person["club_id"], opponent_club_id=opp,
                           side=side, kit_number=int(person["kit_number"]), filename="video.mp4", **extra)
        rec.match_id = match_id_for(rec.upload_id)
        s = store()
        try:
            rec.size_bytes = await run_in_threadpool(s.put_video, rec.upload_id, video.file)
        except ValueError as exc:
            raise _bad(413, str(exc))
        rec.stages = [{"role": "queued", "status": "ok", "ms": 0, "note": f"{rec.size_bytes / (1 << 20):.1f} MB stored"}]
        await run_in_threadpool(s.put_record, rec)
        await run_in_threadpool(s.enqueue, {"upload_id": rec.upload_id, "kind": "vision"})
        return {"upload": _view(rec), "store": s.kind}
    finally:
        await form.close()


def _catalogue_fields(competition_id: str | None, played: str | None, camera: str | None, consent: str) -> dict[str, Any]:
    """The upload's competition, date, camera and consent. With a ``competition_id`` (a catalogue club's match) the date,
    the camera and ``consent=yes`` are all required; without one (the Regista League's friendly form, as before) they
    are optional and checked when given. Plain 422 messages."""
    from datetime import date, datetime, timezone

    from regista.catalogue.taxonomy import BY_ID

    if competition_id is not None:
        if not COMP_RE.match(competition_id):
            raise _bad(422, "competition_id must be a catalogue competition id (co_…)")
        _competition(competition_id)   # known, else a plain 422
        if not played:
            raise _bad(422, "say when the match was played (date, YYYY-MM-DD)")
        if not camera:
            raise _bad(422, "say what the match was filmed on (camera: tripod, phone, drone or broadcast)")
        if consent.lower() not in CONSENT_YES:
            raise _bad(422, "tick the box to confirm that everyone you filmed agreed to be filmed and shown (consent=yes)")
    if camera and camera not in CAMERAS:
        raise _bad(422, f"camera is one of {', '.join(CAMERAS)}")
    if played:
        if not DATE_RE.match(played):
            raise _bad(422, "date is the day the match was played, YYYY-MM-DD")
        try:
            day = date.fromisoformat(played)
        except ValueError:
            raise _bad(422, f"{played} is not a date")
        lab = BY_ID.get(competition_id) if competition_id else None
        start = date.fromisoformat(lab.window[0]) if lab else date(2026, 8, 1)
        if day < start:
            raise _bad(422, f"the season started on {start.isoformat()}: a match before it is not this season's")
        if day > datetime.now(timezone.utc).date():
            raise _bad(422, "that date is in the future: upload a match that has been played")
    return {"competition_id": competition_id, "camera": camera, "date_played": played,
            "consent": consent.lower() in CONSENT_YES}


# ---------------------------------------------------------------------------- "is this you?"

def _review_items(d: Path) -> list[dict[str, Any]]:
    from regista.vision.review import QUEUE_FILE

    q = d / "review" / QUEUE_FILE
    return json.loads(q.read_text())["items"] if q.exists() else []


def _about(item: dict[str, Any], me: str, my_team: str) -> bool:
    """A question about the uploader: a track on their team with them as a candidate or the current name, or a replay
    that lists them."""
    named = {c["player_id"] for c in item.get("candidates", [])}
    if item["kind"] == "track":
        return item.get("team_id") == my_team and (me in named or item.get("current") == me)
    return me in named or me in (item.get("current") or [])


def _questions(rec: UploadRecord, d: Path) -> tuple[str | None, list[dict[str, Any]]]:
    from regista.schema import iter_jsonl

    me = _uploader_pid(d, rec)
    if me is None:
        return None, []
    header = next(iter_jsonl(d / "events.jsonl"))
    my_team = next(p["team_id"] for p in header["players"] if p["player_id"] == me)
    names = {p["player_id"]: p["name"] for p in header["players"]}
    out = []
    for it in _review_items(d):
        if not _about(it, me, my_team):
            continue
        mine = next((c for c in it.get("candidates", []) if c["player_id"] == me), None)
        current = it.get("current")
        thinks = current == me if it["kind"] == "track" else me in (current or [])
        out.append({"item_id": it["item_id"], "kind": it["kind"], "segment_kind": it.get("segment_kind"),
                    "t": it.get("t"), "t0": it.get("t0"), "t1": it.get("t1"), "regista_thinks_its_you": thinks,
                    "named_as": names.get(current) if it["kind"] == "track" and current and current != me else None,
                    "p": mine["p"] if mine else None,
                    "question": "Is this you?" if it["kind"] == "track" else f"Are you in this {it.get('segment_kind') or 'replay'}?",
                    "image_url": f"/api/player/uploads/{rec.upload_id}/crops/{it['image']}" if it.get("image") else None})
    return me, out


@router.get("/api/player/uploads/{upload_id}/questions")
async def questions(upload_id: str) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        rec = _record(upload_id)
        d = ensure_match(rec)
        if d is None:
            return {"upload_id": upload_id, "status": rec.status, "player_id": None, "items": []}
        me, items = _questions(rec, d)
        return {"upload_id": upload_id, "status": rec.status, "player_id": me, "items": items if rec.status == "needs_review" else []}

    return await run_in_threadpool(run)


@router.get("/api/player/uploads/{upload_id}/crops/{name}", include_in_schema=False)
def crop(upload_id: str, name: str) -> FileResponse:
    if not CROP_RE.match(name):
        raise HTTPException(400, "bad crop name")
    rec = _record(upload_id)
    d = ensure_match(rec)
    path = d / "review" / "crops" / name if d else None
    if path is None or not path.exists():
        raise HTTPException(404, "no such picture")
    return FileResponse(path, media_type="image/jpeg")


class AnswerIn(BaseModel):
    item_id: Annotated[str, StringConstraints(pattern=r"^(tr|cw)_[A-Za-z0-9_.\-]{1,80}$")]
    is_me: bool


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list, max_length=50)  # none: "nothing here is me", finish as it is
    annotator: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_ .\-]{1,40}$")] = "player"


def _identity_answers(items: list[dict[str, Any]], body: AnswersIn, me: str) -> list[dict[str, Any]]:
    """Yes or no, turned into the Who's who answers the identity review applies. A track: yes names it the uploader; no
    leaves the identity agent's call (``unknown``), except where the agent had named it the uploader, which unnames it
    (``not_a_player``: the person said who it is not, not who it is). A replay: the uploader is added or taken out."""
    from regista.vision.review import NOT_A_PLAYER, UNKNOWN

    asked = {it["item_id"]: it for it in items}
    out = []
    for a in body.answers:
        it = asked.get(a.item_id)
        if it is None:
            raise HTTPException(422, f"{a.item_id} is not one of the questions about you")
        if it["kind"] == "track":
            pid = me if a.is_me else (NOT_A_PLAYER if it.get("current") == me else UNKNOWN)
            out.append({"item_id": a.item_id, "player_id": pid})
        else:
            players = [p for p in (it.get("current") or []) if p != me] + ([me] if a.is_me else [])
            out.append({"item_id": a.item_id, "players": players[:6]})
    return out


def _models_dir(d: Path) -> Path | None:
    """The vision models for the recompute: the ones the worker recorded, if on this machine; this app's own
    (REGISTA_MODELS); else the store's ``models/vision``, fetched once next to the matches."""
    from regista import api

    run = d / ".vision_work" / "run.json"
    if run.exists():
        recorded = Path(json.loads(run.read_text()).get("models_dir", ""))
        if recorded.is_dir() and any(recorded.iterdir()):
            return recorded
    if api.MODELS_DIR.is_dir() and any(api.MODELS_DIR.iterdir()):
        return api.MODELS_DIR
    local = PLAYER_MATCHES / ".models" / "vision"
    if not (local.is_dir() and any(local.iterdir())):
        tmp = Path(tempfile.mkdtemp(prefix=".models.", dir=PLAYER_MATCHES))
        if store().get_dir("models", "vision", tmp) == 0:
            shutil.rmtree(tmp, ignore_errors=True)
            return None
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(local, ignore_errors=True)
        os.rename(tmp, local)
    return local


def _point_at_video(d: Path, rec: UploadRecord) -> None:
    """The manifest names the video where the worker read it; the recompute reads it here, from the store's copy
    (kept beside the matches, never inside the folder that goes back to the store)."""
    video = PLAYER_MATCHES / ".videos" / f"{rec.upload_id}.mp4"
    if not video.exists():
        store().get_video(rec.upload_id, video.with_suffix(".part"))
        os.replace(video.with_suffix(".part"), video)
    manifest = json.loads((d / "manifest.json").read_text())
    manifest.setdefault("video", {})["path"] = str(video.resolve())
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")


def _finish(rec: UploadRecord, note: str, ms: int) -> UploadRecord:
    stages = [*rec.stages, {"role": "identity_review", "status": "ok", "ms": ms, "note": note}]
    rec = store().update(rec.upload_id, status="done", stages=stages, notes=[*rec.notes, note])
    _mark(rec.match_id or match_id_for(rec.upload_id), rec)
    _forget_listing()
    from regista.season.profiles import invalidate

    invalidate()  # the season rebuilds with this match in the uploader's profile on its next read
    return rec


_answer_locks: dict[str, threading.Lock] = {}


@router.post("/api/player/uploads/{upload_id}/answers", dependencies=[Writer])
async def answer(upload_id: str, body: AnswersIn) -> dict[str, Any]:
    """The player's answers. Applied through the identity review (``regista.api._apply_identity_review``): identity
    corrected, then possession, events and clips recomputed on this replica; the uploader's clips are cut again, the
    folder goes back to the store, and the record becomes done. No answers: finish with the match as the agents left it."""
    return await run_in_threadpool(_answer, upload_id, body)


def _answer(upload_id: str, body: AnswersIn) -> dict[str, Any]:
    import uuid

    from regista import api
    from regista.vision.package import write_clips

    t0 = time.perf_counter()
    rec = _record(upload_id)
    if rec.status != "needs_review":
        raise HTTPException(409, f"this upload is {rec.status}: there is nothing to answer")
    with _stores_lock:
        lock = _answer_locks.setdefault(upload_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "these answers are already being applied")
    try:
        d = ensure_match(rec)
        if d is None:
            raise HTTPException(409, "the match is not ready yet")
        me, items = _questions(rec, d)
        if me is None:
            raise HTTPException(409, "you are not on this match's team sheet")
        if not body.answers:
            rec = _finish(rec, "no answers: the agents' calls stand", int((time.perf_counter() - t0) * 1000))
            return {"upload": _view(rec, d), "answers": 0, "changed": None}
        answers = _identity_answers(items, body, me)
        if not (d / ".vision_work" / "identity.joblib").exists():
            raise HTTPException(409, "this match has no identity result to correct (the worker did not keep .vision_work)")
        _point_at_video(d, rec)
        models = _models_dir(d)
        from regista.vision.review import QUEUE_FILE

        q = d / "review" / QUEUE_FILE
        claimed = q.with_name(f"identity_review.claimed-{uuid.uuid4().hex[:8]}.json")
        try:
            os.rename(q, claimed)
        except FileNotFoundError:
            raise HTTPException(409, "no open questions (already answered)")
        review = api.IdentityReviewIn(answers=[api.IdentityAnswerIn(**a) for a in answers], annotator=body.annotator)
        try:
            changed = api._apply_identity_review(d, claimed, review, None, models_dir=models)
        except ValueError as exc:
            os.rename(claimed, q)
            raise HTTPException(422, str(exc))
        except Exception:
            os.rename(claimed, q)
            raise
        write_clips(d, me)  # the uploader's moments, cut again from the corrected stream
        store().put_match(d.name, d)
        yes = sum(a.is_me for a in body.answers)
        rec = _finish(rec, f"{len(answers)} answer(s) from the player ({yes} yes)", int((time.perf_counter() - t0) * 1000))
        return {"upload": _view(rec, d), "answers": len(answers), "changed": changed}
    finally:
        lock.release()
