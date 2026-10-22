"""The Studio overview at the terminal, for Claude at the start of a session (and for Zaid).

    python3 -m regista.studio status                       # the local app, http://127.0.0.1:8000
    python3 -m regista.studio status --url https://…       # the live app
    python3 -m regista.studio status --json                # the raw overview

The key is REGISTA_STUDIO_VIEW_TOKEN (or REGISTA_ADMIN_TOKEN only when there is no view key), from the environment or
``.env`` (REGISTA_DOTENV picks another file). It travels only in the X-Regista-Token header, is never printed, never
follows a redirect, and is not sent at all over plain http to a host other than this machine (use https). The URL is
--url, else REGISTA_APP_URL, else the local app.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:8000"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _key() -> tuple[str | None, str]:
    from regista.cloud.config import load_dotenv

    dotenv = os.environ.get("REGISTA_DOTENV", ".env")
    if dotenv:
        load_dotenv(dotenv)
    if os.environ.get("REGISTA_STUDIO_VIEW_TOKEN"):
        return os.environ["REGISTA_STUDIO_VIEW_TOKEN"], "view key"
    if os.environ.get("REGISTA_ADMIN_TOKEN"):
        return os.environ["REGISTA_ADMIN_TOKEN"], "admin key"
    return None, "no key"


def key_is_safe_to_send(url: str) -> bool:
    """https anywhere, or http to this machine. Plain http to another host would show the key to the network."""
    u = urlsplit(url)
    return u.scheme == "https" or (u.scheme == "http" and (u.hostname or "").lower() in LOCAL_HOSTS)


def fetch_overview(url: str, key: str | None, timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(url.rstrip("/") + "/api/studio/overview", headers={"Accept": "application/json"})
    if key:
        req.add_unredirected_header("X-Regista-Token", key)  # a redirect, even to another host, never carries the key
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - an http(s) URL the user chose
        return json.loads(r.read().decode("utf-8"))


def _mb(n: int) -> str:
    return f"{n / 1e6:.1f} MB"


def render(o: dict[str, Any], url: str, key_name: str) -> str:
    h, caps, u, c, d = o["health"], o["capabilities"], o["usage"], o["cache"], o["data"]
    cloud = h.get("cloud", {})
    on = [n for n in ("foundry", "cosmos", "search") if cloud.get(n)] + [n for n in ("azure_mcp", "tracing") if h.get(n)]
    lines = [f"Regista Studio  {url}  (role {o['role']}, {key_name})",
             f"  version {h.get('version')}  image {h.get('image') or '-'}  revision {h.get('revision') or '-'}  writes {h.get('writes')}",
             f"  services: {', '.join(on) or 'none (local, no cloud)'}  librarian {h.get('librarian')}  jobs {'yes' if caps.get('jobs') else 'no'}",
             ""]
    todo = o.get("todo") or []
    lines.append(f"To do ({len(todo)})" if todo else "To do: nothing waiting")
    for t in todo:
        lines.append(f"  - [{t['kind']}] {t['match_id'] or '-'}: {t['detail']}  ({t['link']})")
    lines += ["", f"Usage (Ask + Chat on Foundry): {u['last_minute']} this minute, {u['last_hour']}/{u['limits']['total_per_hour']} this hour, "
                  f"{u['last_day']}/{u['limits']['total_per_day']} today, {u['in_flight']} in flight"]
    cos, srch = d.get("cosmos", {}), d.get("search", {})
    cos_txt = ("not configured" if not cos.get("configured") else
               ", ".join(f"{k} {v if v is not None else '?'}" for k, v in (cos.get("containers") or {}).items()) + (f"  ERROR {cos['error']}" if cos.get("error") else ""))
    srch_txt = ("not configured" if not srch.get("configured") else
                f"{srch.get('index')} {srch.get('documents') if srch.get('documents') is not None else '?'} docs" + (f"  ERROR {srch['error']}" if srch.get("error") else ""))
    lines += [f"Cosmos DB: {cos_txt}", f"AI Search: {srch_txt}"]
    p = c["prerender"]
    lines.append(f"Render cache: {c['files']} files, {_mb(c['bytes'])}; prerender {p['rendered']}/{p['total']}"
                 + (" running" if p["running"] else "") + (f", {p['failed']} failed" if p["failed"] else ""))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m regista.studio", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status", help="print the Studio overview from a local or remote Regista")
    s.add_argument("--url", default=None, help=f"the app (default: REGISTA_APP_URL, else {DEFAULT_URL})")
    s.add_argument("--json", action="store_true", help="print the raw overview JSON")
    args = parser.parse_args(argv)
    key, key_name = _key()
    url = args.url or os.environ.get("REGISTA_APP_URL") or DEFAULT_URL
    if key and not key_is_safe_to_send(url):
        print(f"warning: {url} is plain http to another host, so the {key_name} is not sent (use https)", file=sys.stderr)
        key, key_name = None, "no key: not sent over http"
    try:
        o = fetch_overview(url, key)
    except urllib.error.HTTPError as exc:
        why = {401: "the key was refused or missing (set REGISTA_STUDIO_VIEW_TOKEN in .env)", 404: "this app has no Studio yet (an older deploy?)"}
        print(f"{url}: HTTP {exc.code}: {why.get(exc.code, exc.reason)}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, OSError) as exc:
        print(f"{url}: not reachable ({getattr(exc, 'reason', exc)}); start it with: uvicorn regista.api:app", file=sys.stderr)
        return 2
    print(json.dumps(o, indent=2) if args.json else render(o, url, key_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
