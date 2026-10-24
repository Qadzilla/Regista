"""The Scout view's API: the Regista League, players and their profiles (``regista.season``). All reads, all public.

GET  /api/season                       league, clubs with their squads, table, rounds with their matches (each opens in the
                                       Clip view)
GET  /api/players                      profile cards; filters position, club, q, min_minutes; sort by any stat per 90
GET  /api/players/{global_id}          one profile: per-90 rates, percentiles, touch map, moments, matches, evidence,
                                       and the Profile agent's summary (every sentence citing its sources)
GET  /api/players/{global_id}/moments  the player's moments across the season, best first; tag= filters
GET  /api/players/{global_id}/reel.mp4 the player's best moments across matches, back to back (cached); tag=, reason=
                                       (on_ball_main: each goal once, without its replays), order=best|match
GET  /api/compare?ids=a,b[,c]          two or three profiles side by side (cards plus every per-90 rate)
POST /api/scout/ask                    the Scout agent: a plain question in, players out (rules, or Foundry: rate-limited)
GET  /scout, /players/{global_id}      the Scout view and the player profile pages (static files under static/)

Season matches themselves are ordinary matches to the rest of the API (``/api/matches/rl_…/clips`` and so on): they are
regenerated from ``data/season/league.json`` on first use (``regista.api._match_dir``).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, StringConstraints

from regista.season.profiles import HEADLINE, PERCENTILE_RULE, RATIOS, STATS, Season, card, load_season

router = APIRouter()
STATIC = Path(__file__).resolve().parent / "static"
GID_PATTERN = r"^pl_[a-z0-9_]{1,40}$"
MAX_PROFILE_REEL = 8
REASON_PATTERN = "^(on_ball_main|replay_appearance|highlight_appearance|closeup_appearance)$"  # a clip's reason (the clips schema)
SQUAD_FIELDS = ("global_id", "name", "kit_number", "position", "starter")  # each club's squad in /api/season, from league.json
SQUAD_BIO = ("age", "date_of_birth", "height_cm", "preferred_foot", "nationality")  # plus the public bio; never the ratings
WARM = {"state": "idle", "error": None}
_warm_lock = threading.Lock()


def season() -> Season:
    from regista.api import DATA_ROOT, SEASON_LEAGUE, SEASON_ROOT
    from regista.player_api import uploaded_matches
    from regista.season.claims import claimed_matches

    if not SEASON_LEAGUE.exists():
        raise HTTPException(404, "no league on this server (data/season/league.json)")
    # Confirmed claims count too (claims_api), and the Player view's finished uploads (player_api)
    return load_season(SEASON_LEAGUE, SEASON_ROOT, claimed_matches(DATA_ROOT), uploaded_matches())


def warm_season() -> None:
    """Build the season (matches and profiles) in the background at startup, so the first scout does not wait."""
    with _warm_lock:
        WARM.update(state="building", error=None)
        try:
            season()
            WARM["state"] = "ready"
            from regista.terminal_api import warm_metrics

            warm_metrics()  # the Scout terminal's metrics, after the profiles
        except Exception as exc:  # noqa: BLE001 - reported by /api/season, never fatal to the app
            WARM.update(state="failed", error=f"{type(exc).__name__}: {exc}")


def _profile(gid: str) -> dict[str, Any]:
    p = season().player(gid)
    if p is None or not p["appearances"]:
        raise HTTPException(404, f"no player {gid!r} in the league")
    return p


def stat_catalogue() -> list[dict[str, Any]]:
    """Every sortable stat, for filters and the Scout agent: key, label, kind (per90 or ratio), headline or not."""
    return ([{"key": k, "label": lbl, "kind": "per90", "headline": k in HEADLINE} for k, (lbl, _t) in STATS.items()]
            + [{"key": k, "label": lbl, "kind": "ratio", "headline": True} for k, (lbl, _n, _d) in RATIOS.items()])


@router.get("/scout", response_class=HTMLResponse, include_in_schema=False)
def scout_page() -> str:
    return (STATIC / "scout" / "index.html").read_text(encoding="utf-8")


@router.get("/players/{gid}", response_class=HTMLResponse, include_in_schema=False)
def player_page(gid: str) -> str:
    _check_gid(gid)  # the page reads its id from the URL; the API answers 404 for players not in the league
    return (STATIC / "player" / "index.html").read_text(encoding="utf-8")


@router.get("/api/season")
async def get_season() -> dict[str, Any]:
    s = await run_in_threadpool(season)
    from regista.season.league import bio, club_by_id

    clubs = club_by_id(s.league)
    rounds: dict[int, list[dict[str, Any]]] = {}
    for m in s.matches:
        rounds.setdefault(m["round"], []).append({**m, "home_name": clubs[m["home"]]["name"], "away_name": clubs[m["away"]]["name"]})
    return {"league": s.league["league"], "season": s.league["season"],
            "clubs": [{**{k: c[k] for k in ("club_id", "name", "short_name", "kit", "ground")},
                       "squad": [{**{k: p.get(k) for k in SQUAD_FIELDS}, **{k: v for k, v in bio(p).items() if k in SQUAD_BIO}}
                                 for p in c.get("squad", [])]} for c in s.league["clubs"]],
            "table": s.table, "rounds": [{"round": r, "date": ms[0]["date"], "matches": ms} for r, ms in sorted(rounds.items())],
            "generator": s.league["generator"], "stats": stat_catalogue(), "warm": dict(WARM),
            "percentiles": {"rule": PERCENTILE_RULE, "min_minutes": s.min_minutes},
            "note": "Synthetic players and clubs generated by Regista; every number comes from the league's event streams. "
                    "Bios (age at 1 August 2026, height, foot, nationality) are synthetic too."}


@router.get("/api/players")
async def list_players(position: Annotated[str | None, Query(pattern="^(GK|DF|MF|FW)$")] = None,
                       club: Annotated[str | None, Query(max_length=40)] = None,
                       q: Annotated[str | None, Query(max_length=80)] = None,
                       min_minutes: float = Query(0.0, ge=0.0, le=10000.0),
                       sort: Annotated[str, Query(pattern=r"^[a-z0-9_]{1,40}$")] = "minutes",
                       limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Profile cards, filtered and sorted (highest first; ``sort=name`` is alphabetical)."""
    s = await run_in_threadpool(season)
    try:
        rows = s.players(position=position, club=club, q=q, min_minutes=min_minutes, sort=sort, limit=limit)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"players": rows, "total": len(rows), "sort": sort, "stats": stat_catalogue()}


@router.get("/api/players/{gid}")
async def get_player(gid: str) -> dict[str, Any]:
    """The profile, plus ``summary: {text, sentences: [{text, sources}], sources, model}`` from the Profile agent: the
    stored one (data/season/summaries.json) while the numbers it was written from still hold, else the rules summary."""
    from regista.season.summaries import summary_for

    _check_gid(gid)

    def build() -> dict[str, Any]:
        p = _profile(gid)
        return {**p, "card": card(p), "headline_keys": HEADLINE, "summary": summary_for(season(), p)}

    return await run_in_threadpool(build)


@router.get("/api/players/{gid}/moments")
async def player_moments(gid: str, tag: Annotated[str | None, Query(pattern=r"^[a-z_]{1,30}$")] = None,
                         limit: int = Query(20, ge=1, le=40)) -> dict[str, Any]:
    _check_gid(gid)
    p = await run_in_threadpool(_profile, gid)
    ms = [m for m in p["moments"] if not tag or tag in m["tags"]]
    return {"global_id": gid, "name": p["name"], "moments": ms[:limit], "total": len(ms)}


@router.get("/api/players/{gid}/reel.mp4")
async def player_reel(gid: str, n: int = Query(6, ge=1, le=MAX_PROFILE_REEL), tag: Annotated[str | None, Query(pattern=r"^[a-z_]{1,30}$")] = None,
                      reason: Annotated[str | None, Query(pattern=REASON_PATTERN)] = None,
                      order: Literal["best", "match"] = "best",
                      fps: float = Query(25.0, gt=0, le=60), width: int = Query(1280, ge=160, le=1920)) -> FileResponse:
    """The player's best ``n`` moments across the season (or the best with ``tag``), each with its title card.
    ``reason=on_ball_main`` keeps only the moments on the ball in the main view, so a goal plays once instead of with its
    replays and highlights; ``order=match`` plays the chosen moments in match order (round, then time) instead of best first."""
    from regista import api
    from regista.render.video import concat_mp4

    _check_gid(gid)
    api._check_size(fps, width)
    p = await run_in_threadpool(_profile, gid)
    chosen = [m for m in p["moments"] if (not tag or tag in m["tags"]) and (not reason or m["reason"] == reason)][:n]
    if not chosen:
        what = " ".join(x for x in (f"tagged {tag}" if tag else "", f"with reason {reason}" if reason else "") if x)
        raise HTTPException(404, f"{p['name']} has no moments{f' {what}' if what else ''} to put in a reel")
    if order == "match":
        chosen.sort(key=lambda m: (m["round"] is None, m["round"] or 0, m["match_id"], m["t"]))

    def resolve(m: dict[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any] | None]:
        d = api._match_dir(m["match_id"])
        clips, labels = api._clips(d)
        clip = next(c for c in clips if c["id"] == m["clip_id"])
        return d, clip, labels.get(clip["id"])

    # Each clip renders (or comes from the cache) on its own first, taking the render slot itself; the reel only joins
    # them. Rendering the clips inside the reel's own render would wait forever for the slot the reel holds.
    import asyncio

    loop = asyncio.get_running_loop()
    part_paths = []
    for m in chosen:
        d, clip, label = await run_in_threadpool(resolve, m)
        part_paths.append(await loop.run_in_executor(api._render_pool, api._render_clip_cached, d, clip, label, fps, width))

    key = hashlib.sha256(json.dumps([gid, [(m["match_id"], m["clip_id"]) for m in chosen], fps, width]).encode()).hexdigest()[:20]

    def render(tmp: Any) -> dict[str, Any]:
        # concat_mp4 names its parts relative to one folder, and these come from several matches' caches: link them
        # into a private folder first (a hard link also keeps a part alive if the cache evicts it meanwhile).
        import os
        import shutil
        import tempfile
        from pathlib import Path

        work = Path(tempfile.mkdtemp(prefix=".reel.", dir=Path(tmp).parent))
        try:
            linked = []
            for k, part in enumerate(part_paths):
                dst = work / f"{k:02d}.mp4"
                try:
                    os.link(part, dst)
                except OSError:
                    shutil.copyfile(part, dst)
                linked.append(dst)
            concat_mp4(linked, Path(tmp))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        return {"path": str(tmp)}

    return await api._video(api.CACHE_ROOT / "players" / f"{gid}_reel_{key}.mp4", render, filename=f"regista_{gid}_reel.mp4")


@router.get("/api/compare")
async def compare(ids: Annotated[str, Query(pattern=r"^pl_[a-z0-9_]{1,40}(,pl_[a-z0-9_]{1,40}){1,2}$")]) -> dict[str, Any]:
    """Two or three players side by side: their cards, every per-90 rate and ratio, and the percentiles."""
    s = await run_in_threadpool(season)
    out = []
    for gid in dict.fromkeys(ids.split(",")):
        p = s.player(gid)
        if p is None or not p["appearances"]:
            raise HTTPException(404, f"no player {gid!r} in the league")
        out.append({"card": card(p), "per90": p["per90"], "ratios": p["ratios"], "percentiles": p["percentiles"],
                    "minutes": p["minutes"]})
    if len(out) < 2:
        raise HTTPException(422, "compare needs two or three different players")
    return {"players": out, "stats": stat_catalogue()}


# ---------------------------------------------------------------------------- the Scout agent

class ScoutAskIn(BaseModel):
    q: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    engine: Literal["rules", "foundry"] = "foundry"


def _scout_foundry(s: Season, q: str, rules: dict[str, Any]) -> tuple[str, list[tuple[str, dict[str, Any]]], str]:
    """The Foundry Scout agent's answer (tests replace this). Returns (answer, tool calls with arguments, answered by);
    without Foundry, the rules reply and an ``answered_by`` that says so."""
    from regista.api import SEASON_LEAGUE, SEASON_ROOT
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.foundry_enabled:
        return rules["reply"], [], "rules (Foundry is not configured on this deployment)"
    from regista.aio import run_sync
    from regista.cloud.foundry import SCOUT_TOOLS, foundry_scout_answer

    env = {"REGISTA_SEASON": str(SEASON_LEAGUE.resolve()), "REGISTA_SEASON_ROOT": str(SEASON_ROOT.resolve())}
    text, calls = run_sync(foundry_scout_answer(cfg, q, rules["understood"], env, SCOUT_TOOLS))
    return text, calls, f"foundry:{cfg.foundry_model}"


@router.post("/api/scout/ask")
async def scout_ask(body: ScoutAskIn, request: Request) -> dict[str, Any]:
    """Ask the Scout agent about the league's players. Returns ``{reply, understood, query, players: [cards], trace,
    answered_by, tools_used}``; each card is a profile card plus ``stat`` (the number the answer is about, with its rank)
    and ``profile_url``. The rules engine always reads the question first (``understood`` says how). With
    ``engine=foundry`` (the default) a Foundry agent then answers through Regista's MCP player tools, with the same
    rate limits and public read-only tools as Ask Foundry; its cards are its own last tool call run again, and
    ``checked`` lists any number in its reply no tool returned. Without Foundry, over the limits, or if it fails, the
    rules answer stands and ``answered_by`` says why."""
    from regista import api
    from regista.season.scout import answer_rules, from_foundry

    s = await run_in_threadpool(season)
    out = await run_in_threadpool(answer_rules, s, body.q)
    if body.engine != "foundry":
        return out
    ok, wait, which = api._ask_limiter.acquire(api._visitor(request))
    if not ok:
        out["answered_by"] = f"rules (Foundry is busy: {which}; try again in {max(1, int(wait))}s)"
        return out

    def run() -> tuple[tuple[str, list[tuple[str, dict[str, Any]]], str], list[Any]]:
        from regista.cloud.telemetry import capture_spans

        try:  # the slot frees when the work ends, even if the request has already timed out
            with capture_spans("regista.scout") as cap:  # the Agent Framework spans of this answer, for its trace
                answer = _scout_foundry(s, body.q, out)
            return answer, cap.spans
        finally:
            api._ask_limiter.release()

    try:
        (text, calls, answered_by), spans = await asyncio.wait_for(run_in_threadpool(run), api.ASK_TIMEOUT_S)
    except asyncio.TimeoutError:
        out["answered_by"] = "rules (Foundry took too long)"
        return out
    except Exception as exc:  # noqa: BLE001 - the rules answer stands
        out["answered_by"] = f"rules (foundry fallback: {type(exc).__name__})"
        return out
    if not answered_by.startswith("foundry"):
        out["answered_by"] = answered_by
        return out
    from regista.cloud.foundry import foundry_trace

    final = await run_in_threadpool(from_foundry, s, out, text, calls, answered_by)
    steps, note = foundry_trace(spans, [n for n, _a in calls])
    final["trace"] = out["trace"] + steps
    if note:
        final["trace_note"] = note
    return final


def _check_gid(gid: str) -> None:
    import re

    if not re.match(GID_PATTERN, gid):
        raise HTTPException(400, "bad player id")
