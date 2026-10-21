"""Regista Studio: the control room. Everything Zaid (and Claude) needs to see and do, behind the Studio keys.

The page at ``/studio`` is public HTML with no data in it; every ``/api/studio/*`` endpoint needs the Studio view key or
the admin key (regista.access), and anything that changes state needs the admin key. The same code runs locally and on
the live app: ``capabilities`` says what this deployment can do, so local-only sections (vision jobs) say so on Azure
instead of failing.

Endpoints
---------
GET  /studio                    the Studio page
GET  /api/studio/session        the caller's role (open, view, admin) and this deployment's capabilities  [studio]
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from regista.access import require_studio_reader, write_mode

STATIC = Path(__file__).resolve().parent / "static"

router = APIRouter()


def capabilities() -> dict[str, Any]:
    """What this deployment can do. Vision jobs need the private models on disk and never run on the cloud app."""
    from regista import api
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    cloud = bool(os.environ.get("REGISTA_CLOUD"))
    vision_models = (api.MODELS_DIR / "shot_model.joblib").exists()
    return {"writes": write_mode(), "cloud": cloud, "foundry": cfg.foundry_enabled, "cosmos": cfg.cosmos_enabled,
            "search": cfg.search_enabled, "vision_models": vision_models, "jobs": vision_models and not cloud}


@router.get("/studio", response_class=HTMLResponse, include_in_schema=False)
def studio_page() -> str:
    return (STATIC / "studio" / "index.html").read_text(encoding="utf-8")


@router.get("/api/studio/session")
def session(role: str = Depends(require_studio_reader)) -> dict[str, Any]:
    return {"role": role, "capabilities": capabilities()}
