"""Warm for judging: the clips the guided tour (static/shared/tour.js) and the demo video (docs/demo-storyboard.md) play,
rendered before anyone asks for them.

Every clip renders on its first request and is then served from the replica's cache, which a new revision starts empty.
A judge who opens Femi Toure's Goal reel on a fresh revision would otherwise wait while five clips render. At startup
(``REGISTA_PRERENDER=1``, set in the Dockerfile) ``regista.api._prerender`` renders the featured player's clips, then the
URLs this module plans, one at a time, in this order:

1. Femi Toure's Goal reel on ``/players/pl_bro_09``: his goals on the ball in the main view, in match order, each once
   (``profile-view.js`` ``goalReelIds``);
2. the demo match's recap (Instant, told from Sami Castellanos's side): every clip "Play recap reel" plays, then the
   joined reel "Download recap reel" links (``app.js`` ``recapButtons``), and the joined reel "Download reel" links for
   his moments (``app.js`` ``reelLinks``);
3. Hector Santos's take-ons won: the moments the number opens on his profile (``profile-view.js`` ``openStat``);
4. one competition page (Liga Juvenil Levante Interior, Spain U19): its newest uploaded match as "Watch in the Clip
   view" opens it, the first cards of the grid (``app.js`` ``fillPlayers`` and the grid, best first).

The URLs are not built from scratch here: :func:`plan` reads the same JSON the pages read, through the app itself, and
picks the URLs the same way the pages do, so the cache keys are exactly the ones a browser asks for. :func:`asgi_get`
sends each request into the app in-process (no network, no port), as a plain GET with no key: nothing here writes.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable
from urllib.parse import quote

TOUR_PLAYER = "pl_bro_09"            # Femi Toure, the Regista League's top scorer (the hook)
DEMO_MATCH, DEMO_PLAYER = "syn_0294", "t_home_09"   # the featured demo match and Sami Castellanos
SCOUT_PLAYER, SCOUT_STAT = "pl_pnr_11", "take_ons_won"   # Hector Santos (Spain U19), the Scout beat's number
COMPETITION = "co_esp_u19"           # the competition page the tour opens (Hector Santos's)
GRID_FIRST = 8                       # the grid cards a judge sees first on the competition's match
RECAP_REEL_MAX = 12                  # what /api/matches/{id}/reel.mp4 accepts (app.js REEL_MAX)

GetJson = Callable[[str], Any]


def _enc(v: str) -> str:
    return quote(str(v), safe="")


def _mkey(m: dict[str, Any]) -> str:
    return f"{m['match_id']}|{m['clip_id']}"


def _clip_url(url: Any) -> str | None:
    return url if isinstance(url, str) and url.startswith("/api/matches/") and url.endswith(".mp4") else None


def goal_reel(profile: dict[str, Any]) -> list[str]:
    """The clips the profile's Goal reel plays: every goal on the ball in the main view, in match order, each once (the
    catalogue profile's moments across all its competitions; profile-view.js goalReelIds)."""
    moments = [m for r in profile.get("rows") or [] for m in ((r.get("profile") or {}).get("moments") or [])]
    goals = [m for m in moments if "goal" in (m.get("tags") or []) and m.get("reason") == "on_ball_main" and _clip_url(m.get("video_url"))]
    goals.sort(key=lambda m: (m.get("round") is None, m.get("round") or 0, m["match_id"], m.get("t") or 0))
    seen, out = set(), []
    for m in goals:
        if _mkey(m) not in seen:
            seen.add(_mkey(m))
            out.append(m["video_url"])
    return out


def recap_reel(recap: dict[str, Any], match_id: str) -> list[str]:
    """Every clip "Play recap reel" plays, then the joined reel "Download recap reel" links (app.js recapButtons)."""
    clips = recap.get("clips") or {}
    ids = [i for i in recap.get("reel") or [] if _clip_url((clips.get(i) or {}).get("video_url"))]
    out = [clips[i]["video_url"] for i in ids]
    if ids:
        out.append(f"/api/matches/{_enc(match_id)}/reel.mp4?clips={','.join(_enc(i) for i in ids[:RECAP_REEL_MAX])}")
    return out


def evidence(profile: dict[str, Any], stat: str) -> list[str]:
    """The moments a number opens on a catalogue profile: its first competition's (most minutes) evidence items that
    have a clip (profile-view.js openStat)."""
    rows = sorted(profile.get("rows") or [], key=lambda r: -((r.get("sample") or {}).get("minutes") or 0))
    if not rows:
        return []
    items = (((rows[0].get("profile") or {}).get("evidence") or {}).get(stat) or {}).get("items") or []
    return [e["video_url"] for e in items if e.get("clip_id") and _clip_url(e.get("video_url"))]


def default_player(info: dict[str, Any]) -> str | None:
    """The player the Clip view picks for a match opened without one: the most moments first, else the first player, with
    players ordered by team, then kit number (app.js fillPlayers, no preferred player)."""
    counts = info.get("moment_counts") or {}
    ps = sorted(info.get("players") or [], key=lambda p: (p.get("team_id") or "", p.get("kit_number") or 0))
    have = sorted((p for p in ps if counts.get(p["player_id"])), key=lambda p: -counts[p["player_id"]])
    pick = (have or ps or [None])[0]
    return pick["player_id"] if pick else None


def _best_first(clips: list[dict[str, Any]], player: str) -> list[dict[str, Any]]:
    """One player's moments that have a video, as the Clip view's grid orders them by default ("Best first")."""
    mine = [c for c in clips if c.get("player_id") == player and _clip_url(c.get("video_url"))]

    def w(c: dict[str, Any]) -> float:  # app.js row(): the clip's own watchability, else its label's
        v = c.get("watchability")
        return float(v if v is not None else (c.get("label") or {}).get("watchability") or 0.0)

    return sorted(mine, key=lambda c: (-w(c), c.get("t") or 0))


def grid_first(clips: list[dict[str, Any]], player: str, n: int = GRID_FIRST) -> list[str]:
    """The first cards of the Clip view's grid for one player: their moments, best first (app.js, sort "best")."""
    return [c["video_url"] for c in _best_first(clips, player)[:n]]


def download_reel(clips: list[dict[str, Any]], match_id: str, player: str) -> list[str]:
    """The joined reel "Download reel" links on a match opened on a player: their moments, best first, at most 12
    (app.js reelIds and reelLinks). Its clips are the featured player's, which the startup warm-up renders first."""
    ids = [c.get("id") or c.get("clip_id") for c in _best_first(clips, player)][:RECAP_REEL_MAX]
    return [f"/api/matches/{_enc(match_id)}/reel.mp4?clips={','.join(_enc(i) for i in ids)}"] if ids else []


def plan(get_json: GetJson, log: Callable[[str], None] = print) -> list[str]:
    """Every URL to warm, in order, without repeats. Each part reads what its page reads; a part that fails is skipped
    and said, so one missing player never stops the rest."""
    out: list[str] = []

    def part(name: str, build: Callable[[], list[str]]) -> None:
        try:
            urls = build()
        except Exception as exc:  # noqa: BLE001  (warming is best effort; the pages still render on demand)
            log(f"warm: {name} skipped: {exc!r}")
            return
        out.extend(u for u in urls if u not in out)

    part("goal reel", lambda: goal_reel(get_json(f"/api/catalogue/players/{TOUR_PLAYER}?include=profile&moments=0")))
    part("recap reel", lambda: recap_reel(get_json(f"/api/matches/{DEMO_MATCH}/recap?player={DEMO_PLAYER}&engine=rules"), DEMO_MATCH))
    part("download reel", lambda: download_reel(get_json(f"/api/matches/{DEMO_MATCH}/clips"), DEMO_MATCH, DEMO_PLAYER))
    part("scout evidence", lambda: evidence(get_json(f"/api/catalogue/players/{SCOUT_PLAYER}?include=profile&moments=0"), SCOUT_STAT))

    def competition() -> list[str]:
        comp = get_json(f"/api/competitions/{COMPETITION}")
        matches = sorted(comp.get("matches") or [], key=lambda m: (str(m.get("date")), m.get("round") or 0), reverse=True)
        if not matches:
            return []
        mid = matches[0]["match_id"]
        info = get_json(f"/api/matches/{_enc(mid)}")
        pid = default_player(info)
        if pid is None:
            return []
        clips = get_json(f"/api/matches/{_enc(mid)}/clips")
        if not any(c.get("player_id") == pid for c in clips):
            clips = get_json(f"/api/matches/{_enc(mid)}/clips?player={_enc(pid)}")
        return grid_first(clips, pid)

    part("competition page", competition)
    return out


# ---------------------------------------------------------------------------- in-process GETs

async def asgi_get(app: Any, path: str, keep_body: bool = True) -> tuple[int, dict[str, str], bytes]:
    """GET ``path`` (with its query) from an ASGI app in-process: status, headers, and the body (or b"" when
    ``keep_body`` is False: a video is streamed and dropped, which still leaves it rendered in the cache)."""
    raw_path, _, query = path.partition("?")
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
             "path": raw_path, "raw_path": raw_path.encode(), "query_string": query.encode(), "root_path": "",
             "headers": [(b"host", b"regista.warm"), (b"user-agent", b"regista-warm")],
             "client": ("127.0.0.1", 0), "server": ("regista.warm", 80)}
    sent = False
    status, headers, body = 0, {}, bytearray()

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(3600)  # nothing more to send; the app never waits on this for a GET
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status
        if message["type"] == "http.response.start":
            status = message["status"]
            headers.update({k.decode().lower(): v.decode() for k, v in message.get("headers", [])})
        elif message["type"] == "http.response.body" and keep_body:
            body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return status, headers, bytes(body)


def fetchers(app: Any) -> tuple[GetJson, Callable[[str], tuple[int, str]]]:
    """(get_json, get_video) over the app in-process, for a plain thread (each call runs its own event loop)."""

    def get_json(path: str) -> Any:
        status, _h, body = asyncio.run(asgi_get(app, path))
        if status != 200:
            raise RuntimeError(f"GET {path} answered {status}")
        return json.loads(body)

    def get_video(path: str) -> tuple[int, str]:
        status, h, _b = asyncio.run(asgi_get(app, path, keep_body=False))
        return status, h.get("content-type", "")

    return get_json, get_video
