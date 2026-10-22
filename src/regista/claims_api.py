"""Claims for the Scout view: "that's me". Links a player in an uploaded match to a league player (regista.season.claims).

GET  /api/claims                        every claim, newest first, with counts per status; filters status, match_id,
                                        global_id                                                                  [studio]
POST /api/claims                        {match_id, player_id, global_id, claimant?, note?}: a pending claim         [write]
POST /api/claims/{claim_id}/decision    {decision: confirm|reject, annotator?, note?}: the operator's call. A confirm
                                        runs the intelligence workflow on the match for the claimed player (clip, label,
                                        persist, then the Profile agent refreshes the profile); a reject rebuilds the
                                        profiles directly                                                          [write]

Claims are human annotations in ``claims.jsonl`` in the feedback folder, and in Cosmos DB's ``annotations`` container
when it is configured (merged both ways, at most every 30 s, like verdicts). The claimant's note and name are Studio
data: the public pages never read this API. Only matches uploaded to this replica (the vision layer's output, through
POST /api/matches) can be claimed; league matches already carry global ids. Synthetic league players only.
"""

from __future__ import annotations

import threading
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, StringConstraints

from regista.access import StudioReader, Writer, write_mode
from regista.season import claims as store

router = APIRouter()
SYNC_TTL_S = 30.0
_sync_lock = threading.Lock()
_last_sync = {"t": 0.0}

Name = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_ .\-]{1,40}$")]


class ClaimIn(BaseModel):
    match_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")]
    player_id: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.\-]{1,64}$")]
    global_id: Annotated[str, StringConstraints(pattern=r"^pl_[a-z0-9_]{1,40}$")]
    claimant: Name = "claimant"
    note: str = Field("", max_length=store.MAX_NOTE)


class DecisionIn(BaseModel):
    decision: Literal["confirm", "reject"]
    annotator: Name = "zaid"
    note: str = Field("", max_length=store.MAX_NOTE)


# ---------------------------------------------------------------------------- Cosmos DB (when configured)

def _sync(force: bool = False) -> None:
    """Merge claims between this replica's file and Cosmos DB: the container's disk is wiped on restart."""
    from regista import api

    db = api._feedback_store()
    if db is None:
        return
    with _sync_lock:
        if not force and time.time() - _last_sync["t"] < SYNC_TTL_S:
            return
        try:
            remote = db.all_annotations()
        except Exception:  # noqa: BLE001 - claims keep working locally if Cosmos is unreachable
            return
        for rec in store.merge(store.records(), remote):
            try:
                db.write_annotation(rec)
            except Exception:  # noqa: BLE001 - pushed on the next sync
                pass
        _last_sync["t"] = time.time()


def _push(rec: dict[str, Any]) -> bool:
    from regista import api

    db = api._feedback_store()
    if db is None:
        return False
    try:
        db.write_annotation(rec)
        return True
    except Exception:  # noqa: BLE001 - stays local; the next sync pushes it
        return False


# ---------------------------------------------------------------------------- helpers

def _people() -> dict[str, dict[str, Any]]:
    from regista import api
    from regista.season.league import load_league_cached, people

    if not api.SEASON_LEAGUE.exists():
        raise HTTPException(404, "no league on this server (data/season/league.json)")
    return people(load_league_cached(api.SEASON_LEAGUE))


def _uploaded_match(match_id: str) -> tuple[Any, dict[str, Any]]:
    """An uploaded match on this replica and its header; league and Cosmos-only matches cannot be claimed."""
    from regista import api

    api._check_id(match_id)
    if api._is_season_match(match_id):
        raise HTTPException(422, f"{match_id} is a league match: its team sheet already carries global player ids")
    d = api.DATA_ROOT / match_id
    if not (d / "events.jsonl").exists():
        if match_id in api._library():
            raise HTTPException(409, f"match {match_id!r} is stored in Cosmos DB without its event stream: upload it again to claim in it")
        raise HTTPException(404, f"no match {match_id!r}")
    return d, api._header(d)


def _links(c: dict[str, Any]) -> dict[str, Any]:
    from urllib.parse import quote

    mid, pid = quote(c["match_id"]), quote(c["player_id"])
    return {**c, "links": {"match": f"/?match={mid}&player={pid}", "profile": f"/players/{quote(c['global_id'])}",
                           "clips": f"/api/matches/{mid}/clips?player={pid}", "run": f"/studio#runs/{mid}"}}


def _profile_refresh():
    """The Profile agent's refresh, bound to the folders this API serves."""
    from regista import api
    from regista.season.claims import claimed_matches
    from regista.season.profiles import refresh

    return lambda gids: refresh(api.SEASON_LEAGUE, api.SEASON_ROOT, claimed_matches(api.DATA_ROOT), gids)


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out = {"pending": 0, "confirmed": 0, "rejected": 0}
    for c in rows:
        out[c["status"]] += 1
    return out


# ---------------------------------------------------------------------------- endpoints

@router.get("/api/claims", dependencies=[StudioReader])
async def list_claims(status: Annotated[str | None, Query(pattern="^(pending|confirmed|rejected)$")] = None,
                      match_id: Annotated[str | None, Query(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")] = None,
                      global_id: Annotated[str | None, Query(pattern=r"^pl_[a-z0-9_]{1,40}$")] = None) -> dict[str, Any]:
    await run_in_threadpool(_sync)
    rows = await run_in_threadpool(store.all_claims)
    shown = [_links(c) for c in rows if (not status or c["status"] == status) and (not match_id or c["match_id"] == match_id)
             and (not global_id or c["global_id"] == global_id)]
    return {"claims": shown, "counts": counts(rows), "total": len(rows), "writes": write_mode()}


@router.post("/api/claims", status_code=201, dependencies=[Writer])
async def create_claim(body: ClaimIn) -> dict[str, Any]:
    """'Which one is you?': a pending claim that this match's player is this league player. The Studio decides."""
    _d, header = await run_in_threadpool(_uploaded_match, body.match_id)
    person = _people().get(body.global_id)
    if person is None:
        raise HTTPException(404, f"no player {body.global_id!r} in the league")
    await run_in_threadpool(_sync, True)
    try:
        rec = await run_in_threadpool(lambda: store.new_claim(header, body.player_id, person, claimant=body.claimant, note=body.note))
    except store.ClaimError as exc:
        raise HTTPException(exc.status, str(exc))
    stored = await run_in_threadpool(_push, rec)
    return {"claim": _links(store.get(rec["id"])), "stored_in_cosmos": stored}


@router.post("/api/claims/{claim_id}/decision", dependencies=[Writer])
async def decide_claim(claim_id: str, body: DecisionIn) -> dict[str, Any]:
    """Confirm or reject. A confirm runs the Agent Framework workflow on the claimed match for the claimed player (and
    everyone who already has clips there): the claimed player's moments are cut and labelled, and the Profile agent
    adds the match to the profile. A reject rebuilds the profiles without it."""
    from regista import api
    from regista.agents.workflow import WorkflowPipeline

    if not store.CLAIM_ID_RE.match(claim_id):
        raise HTTPException(400, "bad claim id")
    await run_in_threadpool(_sync, True)
    claim = await run_in_threadpool(store.get, claim_id)
    if claim is None:
        raise HTTPException(404, f"no claim {claim_id}")
    if body.decision == "confirm":
        d, header = await run_in_threadpool(_uploaded_match, claim["match_id"])  # still here, before anything is written
    try:
        rec = await run_in_threadpool(lambda: store.decide(claim_id, body.decision, annotator=body.annotator, note=body.note))
    except store.ClaimError as exc:
        raise HTTPException(exc.status, str(exc))
    stored = await run_in_threadpool(_push, rec)
    out: dict[str, Any] = {"claim": _links(store.get(claim_id)), "stored_in_cosmos": stored, "run": None, "profiles": None}
    if body.decision == "confirm":
        roster = {p["player_id"] for p in header["players"]}
        clips_path = d / "clips.jsonl"
        keep = []
        if clips_path.exists():
            from regista.schema import iter_jsonl

            keep = [r["player_id"] for r in iter_jsonl(clips_path) if r.get("type") == "clip" and r.get("player_id") in roster]
        players = list(dict.fromkeys([*keep, claim["player_id"]]))  # the Persist agent rewrites clips.jsonl for these
        await run_in_threadpool(api._sync_feedback, True)
        pipeline = WorkflowPipeline(api._pipeline_agents(), d / "agents", profile_refresh=_profile_refresh())
        result = await pipeline.start({"match_dir": str(d), "player_ids": players, "queries": [], "review": False,
                                       "annotator": body.annotator})
        out["run"] = api._run_summary(claim["match_id"], players, result)
        out["profiles"] = result.state.get("profiles_refreshed")
    else:
        out["profiles"] = await run_in_threadpool(_profile_refresh(), [claim["global_id"]])
    return out
