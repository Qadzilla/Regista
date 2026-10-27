"""Is the live app still up for judging? Read-only checks, run daily by GitHub Actions (.github/workflows/live-check.yml)
until judging ends, so a broken demo is noticed (a failed run emails the repository's owner) instead of found by a judge.

    python -m regista.live_check                                # the live app, every check
    python -m regista.live_check --url http://127.0.0.1:8240 --services ""   # a local run (no Azure services to expect)
    python -m regista.live_check --until 2026-11-11             # after that date: says so and passes without a request

Every request is a plain GET with no key and no cookie: nothing here can write. Checks, in order:

- ``/api/health`` answers 200, says ok, and reports each expected service as running (Foundry, Cosmos DB, AI Search, the
  Azure MCP Server, tracing, Container Apps, Storage);
- the pages answer 200 with HTML: ``/``, ``/demo``, ``/scout``, ``/me``, ``/players/pl_bro_09``;
- ``/api/catalogue`` counts what the demo says (14 competitions, 10 countries, 90 matches);
- one clip of the demo match answers 200 with ``video/mp4`` (the first few kilobytes are read, then the connection closed).

Standard library only, so the workflow needs no install. ``fetch`` is injectable (tests/test_live_check.py).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

LIVE_URL = "https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io"
UNTIL = "2026-11-11"   # the day after judging ends (2026-11-10)
SERVICES = ("foundry", "cosmos", "search", "azure_mcp", "tracing", "container_apps", "storage")
PAGES = ("/", "/demo", "/scout", "/me", "/players/pl_bro_09")
CATALOGUE = {"competitions": 14, "countries": 10, "matches": 90}
DEMO_MATCH, DEMO_PLAYER = "syn_0294", "t_home_09"
PEEK = 4096   # bytes read from a video: enough to know it is one

# fetch(url, timeout) -> (status, content type, body); body is the whole answer, or its first PEEK bytes for a video.
Fetch = Callable[[str, float], tuple[int, str, bytes]]


def http_fetch(url: str, timeout: float) -> tuple[int, str, bytes]:
    """A plain GET: no key, no cookie, no body. HTTP errors are answers (their status), not exceptions."""
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "regista-live-check", "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  (the URL is ours: https, the live app)
            ctype = r.headers.get("content-type", "")
            body = r.read(PEEK) if ctype.startswith("video/") else r.read()
            return r.status, ctype, body
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", "") if e.headers else "", e.read()[:2000]


def _service(health: dict[str, Any], name: str) -> bool:
    cloud = health.get("cloud") or {}
    return bool(cloud.get(name)) if name in ("foundry", "cosmos", "search") else bool(health.get(name))


def run(base: str = LIVE_URL, fetch: Fetch = http_fetch, services: tuple[str, ...] = SERVICES,
        pages: tuple[str, ...] = PAGES, catalogue: dict[str, int] | None = None, timeout: float = 60.0,
        clip_timeout: float = 180.0) -> list[dict[str, Any]]:
    """Every check's result: {"check", "ok", "detail"}. A request that fails outright (DNS, timeout, refused) is a failed
    check, never a crash."""
    base = base.rstrip("/")
    catalogue = CATALOGUE if catalogue is None else catalogue
    out: list[dict[str, Any]] = []

    def get(path: str, t: float = timeout) -> tuple[int, str, bytes] | None:
        try:
            return fetch(base + path, t)
        except Exception as exc:  # noqa: BLE001  (a network failure is a failed check)
            out.append({"check": f"GET {path}", "ok": False, "detail": f"no answer: {exc!r}"})
            return None

    def add(check: str, ok: bool, detail: str) -> None:
        out.append({"check": check, "ok": bool(ok), "detail": detail})

    r = get("/api/health")
    if r is not None:
        status, ctype, body = r
        try:
            h = json.loads(body) if status == 200 else {}
        except ValueError:
            h = {}
        add("health", status == 200 and h.get("ok") is True, f"HTTP {status}, ok={h.get('ok')}")
        if status == 200:
            missing = [s for s in services if not _service(h, s)]
            add("health services", not missing, ("none expected" if not services else "all running: " + ", ".join(services))
                if not missing else "not running: " + ", ".join(missing))

    for path in pages:
        r = get(path)
        if r is not None:
            status, ctype, body = r
            add(f"page {path}", status == 200 and ctype.startswith("text/html") and b"REGI<span>STA</span>" in body,
                f"HTTP {status}, {ctype or 'no content type'}")

    if catalogue:
        r = get("/api/catalogue", max(timeout, 120.0))   # a cold revision builds the catalogue on first use
        if r is not None:
            status, _c, body = r
            try:
                totals = (json.loads(body) or {}).get("totals") or {} if status == 200 else {}
            except ValueError:
                totals = {}
            wrong = {k: totals.get(k) for k, v in catalogue.items() if totals.get(k) != v}
            add("catalogue totals", status == 200 and not wrong,
                f"HTTP {status}, " + (", ".join(f"{k} {v}" for k, v in catalogue.items()) if not wrong else f"expected {catalogue}, got {wrong}"))

    r = get(f"/api/matches/{DEMO_MATCH}/clips?player={DEMO_PLAYER}")
    if r is not None:
        status, _c, body = r
        try:
            clips = json.loads(body) if status == 200 else []
        except ValueError:
            clips = []
        url = next((c.get("video_url") for c in clips if isinstance(c, dict) and str(c.get("video_url", "")).startswith("/api/")), None)
        if url is None:
            add("clip video", False, f"HTTP {status}: no clip with a video for {DEMO_PLAYER} in {DEMO_MATCH}")
        else:
            r = get(url, clip_timeout)   # a clip nobody has played on this revision renders first
            if r is not None:
                status, ctype, body = r
                add("clip video", status == 200 and ctype.startswith("video/mp4") and len(body) > 0, f"{url}: HTTP {status}, {ctype}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.live_check", description=__doc__.split("\n\n")[0],
                                 allow_abbrev=False)
    ap.add_argument("--url", default=LIVE_URL, help="the app to check (default: the live app)")
    ap.add_argument("--services", default=",".join(SERVICES),
                    help="comma-separated services /api/health must report running; empty for none (a local run)")
    ap.add_argument("--until", default=None, help="YYYY-MM-DD: on or after this day, pass without checking (judging is over)")
    args = ap.parse_args(argv)
    if args.until and dt.date.today() >= dt.date.fromisoformat(args.until):
        print(f"Judging is over ({args.until}): nothing to check.")
        return 0
    services = tuple(s.strip() for s in args.services.split(",") if s.strip())
    results = run(args.url, services=services)
    for r in results:
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['check']}: {r['detail']}")
    failed = [r for r in results if not r["ok"]]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed on {args.url}")
    return 1 if failed or not results else 0


if __name__ == "__main__":
    sys.exit(main())
