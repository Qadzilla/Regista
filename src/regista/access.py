"""Who may do what: the Product is open, the Studio needs a key, and writes need the admin key.

Two keys, both Container Apps secrets on the live app and lines in ``.env`` locally:

- ``REGISTA_ADMIN_TOKEN``: everything (uploads, verdicts, reviews, Who's who answers, retraining) and the whole Studio.
- ``REGISTA_STUDIO_VIEW_TOKEN``: the whole Studio, read-only. Given to judges, and what Claude reads the live Studio with.

With neither key set, a plain local run (development) is open, except for writes a page on another site sends (a foreign
``Origin``). The model fails closed: with ``REGISTA_READONLY=1`` or ``REGISTA_CLOUD`` set and no key configured, nothing
opens: Studio reads answer 401 and writes refuse ("locked"). ``REGISTA_READONLY=1`` switches writes off whatever the key.
Keys travel only in the ``X-Regista-Token`` header, never in a URL.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, Header, HTTPException, Request

Role = Literal["open", "view", "admin"]
ADMIN_ENV = "REGISTA_ADMIN_TOKEN"
VIEW_ENV = "REGISTA_STUDIO_VIEW_TOKEN"


def _matches(given: str | None, env: str) -> bool:
    expected = os.environ.get(env, "")
    return bool(expected) and bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def keys_configured() -> bool:
    return bool(os.environ.get(ADMIN_ENV) or os.environ.get(VIEW_ENV))


def open_allowed() -> bool:
    """Open (no key needed) only on a plain local run: no keys, not read-only, not the cloud app. A deployment that lost
    its key secret, or one switched to read-only with the keys dropped, must not fall open."""
    return not keys_configured() and os.environ.get("REGISTA_READONLY") != "1" and not os.environ.get("REGISTA_CLOUD")


def write_mode() -> str:
    if os.environ.get("REGISTA_READONLY") == "1":
        return "read-only"
    if keys_configured():
        return "token"
    return "open" if open_allowed() else "locked"


def role_of(token: str | None) -> Role | None:
    """The caller's role for this key, or None when this one matches neither (or no key is configured on a deployment
    that must not be open)."""
    if open_allowed():
        return "open"
    if _matches(token, ADMIN_ENV):
        return "admin"
    if _matches(token, VIEW_ENV):
        return "view"
    return None


def require_studio_reader(x_regista_token: Annotated[str | None, Header()] = None) -> Role:
    """Studio reads: reviewers' data, run traces, usage. The view key or the admin key."""
    role = role_of(x_regista_token)
    if role is None:
        if not keys_configured():
            raise HTTPException(401, "this deployment has no Studio key configured, so the Studio is closed")
        raise HTTPException(401, "a valid X-Regista-Token header (the Studio view key or the admin key) is required")
    return role


def _foreign_origin(request: Request) -> bool:
    """True when the request names an Origin other than this server. Browsers send Origin on cross-site POSTs, and a
    multipart upload needs no preflight, so in open mode any page Zaid visits could otherwise write to a local Regista."""
    origin = request.headers.get("origin")
    if origin is None:
        return False  # not a browser cross-site request (curl, the CLI, the tests)
    return urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower()


def require_writer(request: Request, x_regista_token: Annotated[str | None, Header()] = None) -> None:
    """Writes are the only way to spend Foundry credit or change what the model learns, so they are guarded."""
    mode = write_mode()
    if mode == "read-only":
        raise HTTPException(403, "this deployment is read-only")
    if mode == "locked":
        raise HTTPException(403, "this deployment has no admin key configured, so writes are off")
    if mode == "open" and _foreign_origin(request):
        raise HTTPException(403, "a write from another site's page is refused (Origin does not match this server)")
    if mode == "token" and not _matches(x_regista_token, ADMIN_ENV):
        if _matches(x_regista_token, VIEW_ENV):
            raise HTTPException(403, "the Studio view key can read but not write")
        raise HTTPException(401, "a valid X-Regista-Token header is required to write")


Writer = Depends(require_writer)
StudioReader = Depends(require_studio_reader)
