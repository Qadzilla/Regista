"""Who may do what, route by route: the Product is open, the Studio needs a key, writes need the admin key.

ACCESS lists every route. A new route fails the first test until it is classified here, so nothing reaches the live app
with an access level nobody chose. The other tests check the rules with real requests: no key, the view key, the admin key.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from regista import access, api

ACCESS = {
    # The Product (open)
    "GET /": "public",
    "GET /api/health": "public",
    "GET /api/matches": "public",
    "GET /api/matches/{match_id}": "public",
    "GET /api/matches/{match_id}/clips": "public",
    "GET /api/matches/{match_id}/search": "public",
    "GET /api/matches/{match_id}/clips/{clip_id}.mp4": "public",
    "GET /api/matches/{match_id}/video.mp4": "public",
    "GET /api/matches/{match_id}/report": "public",
    "POST /api/matches/{match_id}/ask": "public",
    "POST /api/matches/{match_id}/chat": "public",
    "GET /studio": "public",  # the page itself holds no data
    # Studio reads (view key or admin key)
    "GET /api/matches/{match_id}/identity-review": "studio",
    "GET /api/matches/{match_id}/identity-review/crops/{name}": "studio",
    "GET /api/matches/{match_id}/review": "studio",
    "GET /api/feedback": "studio",
    "GET /api/studio/session": "studio",
    # Writes (admin key)
    "POST /api/matches": "admin",
    "POST /api/matches/{match_id}/identity-review": "admin",
    "POST /api/matches/{match_id}/review": "admin",
    "POST /api/matches/{match_id}/clips/{clip_id}/verdict": "admin",
    "POST /api/feedback/train": "admin",
}

ADMIN, VIEW = "admin-key-for-tests", "view-key-for-tests"


def _declared() -> dict[str, str]:
    out = {}
    for r in api.app.routes:
        if not isinstance(r, APIRoute):
            continue
        calls = {d.call for d in r.dependant.dependencies}
        level = "admin" if access.require_writer in calls else "studio" if access.require_studio_reader in calls else "public"
        for m in r.methods:
            out[f"{m} {r.path}"] = level
    return out


def test_every_route_has_the_access_level_in_the_table():
    declared = _declared()
    assert declared == ACCESS, {k: (declared.get(k), ACCESS.get(k)) for k in set(declared) | set(ACCESS) if declared.get(k) != ACCESS.get(k)}


def test_studio_api_is_never_public():
    assert all(level != "public" for route, level in _declared().items() if route.split(" ", 1)[1].startswith("/api/studio/"))


@pytest.fixture()
def keyed(monkeypatch):
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    with TestClient(api.app) as c:
        yield c


@pytest.mark.parametrize("key, status, role", [(None, 401, None), ("wrong", 401, None), (VIEW, 200, "view"), (ADMIN, 200, "admin")])
def test_studio_reads_need_a_studio_key(keyed, key, status, role):
    headers = {"X-Regista-Token": key} if key else {}
    r = keyed.get("/api/studio/session", headers=headers)
    assert r.status_code == status and (role is None or r.json()["role"] == role)
    assert keyed.get("/api/feedback", headers=headers).status_code == status


@pytest.mark.parametrize("key, status", [(None, 401), ("wrong", 401), (VIEW, 403)])
def test_writes_refuse_everything_but_the_admin_key(keyed, key, status):
    headers = {"X-Regista-Token": key} if key else {}
    r = keyed.post("/api/feedback/train", headers=headers)
    assert r.status_code == status
    if key == VIEW:
        assert "view key" in r.json()["detail"]


def test_the_product_stays_open_with_keys_configured(keyed):
    assert keyed.get("/").status_code == 200 and keyed.get("/studio").status_code == 200
    assert keyed.get("/api/health").json()["writes"] == "token"
    assert keyed.get("/static/shared/regista.js").status_code == 200


def test_no_keys_means_everything_open(monkeypatch):
    monkeypatch.delenv("REGISTA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("REGISTA_STUDIO_VIEW_TOKEN", raising=False)
    with TestClient(api.app) as c:
        assert c.get("/api/studio/session").json()["role"] == "open"
        assert c.get("/api/feedback").status_code == 200


def test_a_view_key_alone_never_opens_writes(monkeypatch):
    monkeypatch.delenv("REGISTA_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    with TestClient(api.app) as c:
        assert c.post("/api/feedback/train").status_code == 401
        assert c.post("/api/feedback/train", headers={"X-Regista-Token": VIEW}).status_code == 403


def test_public_clips_hide_who_gave_a_verdict(keyed):
    """Verdicts show what was decided to everyone, and who decided only to the Studio."""
    match = sorted(p.name for p in api.DATA_ROOT.iterdir() if (p / "events.jsonl").exists())[0]
    clips = keyed.get(f"/api/matches/{match}/clips").json()
    clip = clips[0]
    r = keyed.post(f"/api/matches/{match}/clips/{clip['id']}/verdict", headers={"X-Regista-Token": ADMIN},
                   json={"verdict": "keep", "annotator": "zaid"})
    assert r.status_code == 200, r.text
    public = {c["id"]: c for c in keyed.get(f"/api/matches/{match}/clips").json()}[clip["id"]]["verdict"]
    studio = {c["id"]: c for c in keyed.get(f"/api/matches/{match}/clips", headers={"X-Regista-Token": VIEW}).json()}[clip["id"]]["verdict"]
    assert set(public) == {"verdict", "keep"} and public["keep"] is True
    assert studio["annotator"] == "zaid" and studio["verdict"] == public["verdict"]
