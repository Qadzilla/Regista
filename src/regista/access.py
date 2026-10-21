"""Who may do what: the Product is open, the Studio needs a key, and writes need the admin key.

Two keys, both Container Apps secrets on the live app and lines in ``.env`` locally:

- ``REGISTA_ADMIN_TOKEN``: everything (uploads, verdicts, reviews, Who's who answers, retraining) and the whole Studio.
- ``REGISTA_STUDIO_VIEW_TOKEN``: the whole Studio, read-only. Given to judges, and what Claude reads the live Studio with.

With neither key set (local development) everything is open. ``REGISTA_READONLY=1`` switches writes off whatever the key.
Keys travel only in the ``X-Regista-Token`` header, never in a URL.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException

Role = Literal["open", "view", "admin"]
ADMIN_ENV = "REGISTA_ADMIN_TOKEN"
VIEW_ENV = "REGISTA_STUDIO_VIEW_TOKEN"


def _matches(given: str | None, env: str) -> bool:
    expected = os.environ.get(env, "")
    return bool(expected) and bool(given) and hmac.compare_digest(given.encode(), expected.encode())


def keys_configured() -> bool:
    return bool(os.environ.get(ADMIN_ENV) or os.environ.get(VIEW_ENV))


def write_mode() -> str:
    if os.environ.get("REGISTA_READONLY") == "1":
        return "read-only"
    return "token" if keys_configured() else "open"


def role_of(token: str | None) -> Role | None:
    """The caller's role for this key, or None when keys are configured and this one matches neither."""
    if not keys_configured():
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
        raise HTTPException(401, "a valid X-Regista-Token header (the Studio view key or the admin key) is required")
    return role


def require_writer(x_regista_token: Annotated[str | None, Header()] = None) -> None:
    """Writes are the only way to spend Foundry credit or change what the model learns, so they are guarded."""
    mode = write_mode()
    if mode == "read-only":
        raise HTTPException(403, "this deployment is read-only")
    if mode == "token" and not _matches(x_regista_token, ADMIN_ENV):
        if _matches(x_regista_token, VIEW_ENV):
            raise HTTPException(403, "the Studio view key can read but not write")
        raise HTTPException(401, "a valid X-Regista-Token header is required to write")


Writer = Depends(require_writer)
StudioReader = Depends(require_studio_reader)
