"""Who may do what, route by route: the Product is open, the Studio needs a key, writes need the admin key.

ACCESS lists every route. A new route fails the first test until it is classified here, so nothing reaches the live app
with an access level nobody chose. The other tests check the rules with real requests: no key, the view key, the admin key.
"""

from __future__ import annotations

from pathlib import Path

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
    "GET /api/matches/{match_id}/reel.mp4": "public",
    "GET /api/matches/{match_id}/moments.csv": "public",
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
    "GET /api/studio/overview": "studio",
    "GET /api/studio/runs": "studio",
    "GET /api/studio/runs/{match_id}": "studio",
    "GET /api/studio/data": "studio",
    "GET /api/studio/usage": "studio",
    "GET /api/studio/cache": "studio",
    "GET /api/studio/jobs": "studio",
    "GET /api/studio/jobs/{job_id}": "studio",
    "GET /api/studio/jobs/{job_id}/log": "studio",
    # Writes (admin key)
    "POST /api/matches": "admin",
    "POST /api/matches/{match_id}/identity-review": "admin",
    "POST /api/matches/{match_id}/review": "admin",
    "POST /api/matches/{match_id}/clips/{clip_id}/verdict": "admin",
    "POST /api/feedback/train": "admin",
    "POST /api/studio/jobs": "admin",
}

ADMIN, VIEW = "admin-key-for-tests", "view-key-for-tests"
SAMPLE = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample"


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
def sample(monkeypatch, tmp_path):
    """The committed sample matches (other test modules point api.DATA_ROOT elsewhere), with a cache of its own."""
    monkeypatch.setattr(api, "DATA_ROOT", SAMPLE)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")


@pytest.fixture()
def keyed(sample, monkeypatch):
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
    assert keyed.get("/static/studio/index.html").status_code == 200 and keyed.get("/static/../access.py").status_code == 404


def _no_keys(monkeypatch):
    monkeypatch.delenv("REGISTA_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("REGISTA_STUDIO_VIEW_TOKEN", raising=False)


def test_no_keys_on_a_plain_local_run_means_everything_open(sample, monkeypatch):
    _no_keys(monkeypatch)
    with TestClient(api.app) as c:
        assert c.get("/api/studio/session").json()["role"] == "open"
        assert c.get("/api/feedback").status_code == 200
        assert c.get("/api/health").json()["writes"] == "open"


# Fail closed (audit J2): a deployment that is read-only or on the cloud never falls open because a key is missing.
@pytest.mark.parametrize("flag, writes, write_status", [("REGISTA_READONLY", "read-only", 403), ("REGISTA_CLOUD", "locked", 403)])
def test_no_keys_with_readonly_or_cloud_opens_nothing(sample, monkeypatch, flag, writes, write_status):
    _no_keys(monkeypatch)
    monkeypatch.setenv(flag, "1")
    with TestClient(api.app) as c:
        assert c.get("/api/health").json()["writes"] == writes
        for path in ("/api/studio/session", "/api/studio/overview", "/api/feedback", "/api/matches/syn_0294/review",
                     "/api/matches/vis_0201/identity-review"):
            r = c.get(path, headers={"X-Regista-Token": "anything"})
            assert r.status_code == 401 and "no Studio key configured" in r.json()["detail"], path
        assert c.post("/api/feedback/train").status_code == write_status
        assert c.post("/api/studio/jobs", json={"kind": "train-events"}).status_code == write_status
        clips = c.get("/api/matches/syn_0294/clips").json()
        assert clips and all(v is None or set(v) == {"verdict", "keep"} for v in (x["verdict"] for x in clips))


@pytest.mark.parametrize("flag", [None, "REGISTA_READONLY", "REGISTA_CLOUD"])
def test_keys_with_readonly_or_cloud_still_open_the_studio(keyed, monkeypatch, flag):
    if flag:
        monkeypatch.setenv(flag, "1")
    assert keyed.get("/api/studio/session", headers={"X-Regista-Token": VIEW}).json()["role"] == "view"
    assert keyed.get("/api/studio/session").status_code == 401
    expected = 403 if flag == "REGISTA_READONLY" else 401
    assert keyed.post("/api/feedback/train").status_code == expected


def test_open_mode_refuses_writes_from_another_sites_page(monkeypatch):
    """A keyless local Regista must not take an upload a web page on another site posts (no preflight for multipart)."""
    _no_keys(monkeypatch)
    with TestClient(api.app) as c:
        events = {"events": ("e.jsonl", "{}\n", "application/x-ndjson")}
        r = c.post("/api/matches", files=events, headers={"Origin": "https://evil.example"})
        assert r.status_code == 403 and "another site" in r.json()["detail"]
        assert c.post("/api/feedback/train", headers={"Origin": "null"}).status_code == 403
        # Same origin (the Studio page itself) and no Origin (curl, the CLI) still write.
        assert c.post("/api/matches", files=events, headers={"Origin": "http://testserver"}).status_code == 422
        assert c.post("/api/matches", files=events).status_code == 422


@pytest.mark.parametrize("bad", [".", ".hidden", "-x", "_x"])
def test_ids_must_start_alphanumeric(keyed, bad):
    from regista.studio import jobs

    assert not api.ID_RE.match(bad) and not jobs.ID_RE.match(bad)
    if bad != ".":  # a client normalises "/runs/." to "/runs/" before it is sent
        assert keyed.get(f"/api/matches/{bad}/clips").status_code == 400
        assert keyed.get(f"/api/studio/runs/{bad}", headers={"X-Regista-Token": VIEW}).status_code == 400
    assert api.ID_RE.match("syn_0294") and api.ID_RE.match("cl_t_home_09_000001") and jobs.ID_RE.match("vis_0201")


def test_pages_send_a_strict_content_security_policy(keyed):
    for path in ("/", "/studio", "/api/health", "/static/studio/studio.js"):
        h = keyed.get(path).headers
        assert "script-src 'self'" in h["content-security-policy"] and "frame-ancestors 'none'" in h["content-security-policy"], path
        assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    for page in ("/", "/studio"):
        html = keyed.get(page).text
        assert "<script>" not in html and " on" + "click=" not in html, "inline scripts would be blocked by the CSP"


def test_head_works_on_get_routes(keyed):
    for path in ("/", "/studio", "/api/health", "/api/matches", "/static/shared/regista.js"):
        r = keyed.head(path)
        assert r.status_code == 200 and r.content == b"", path
    assert keyed.head("/api/feedback").status_code == 401  # HEAD is a GET: the same rules apply


def test_a_view_key_alone_never_opens_writes(monkeypatch):
    monkeypatch.delenv("REGISTA_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    with TestClient(api.app) as c:
        assert c.post("/api/feedback/train").status_code == 401
        assert c.post("/api/feedback/train", headers={"X-Regista-Token": VIEW}).status_code == 403


def test_public_clips_hide_who_gave_a_verdict(keyed):
    """Verdicts show what was decided to everyone, and who decided only to the Studio."""
    match = "syn_0294"  # named, so a match a Studio upload or vision job leaves in the sample does not change the test
    clips = keyed.get(f"/api/matches/{match}/clips").json()
    clip = clips[0]
    r = keyed.post(f"/api/matches/{match}/clips/{clip['id']}/verdict", headers={"X-Regista-Token": ADMIN},
                   json={"verdict": "keep", "annotator": "zaid"})
    assert r.status_code == 200, r.text
    public = {c["id"]: c for c in keyed.get(f"/api/matches/{match}/clips").json()}[clip["id"]]["verdict"]
    studio = {c["id"]: c for c in keyed.get(f"/api/matches/{match}/clips", headers={"X-Regista-Token": VIEW}).json()}[clip["id"]]["verdict"]
    assert set(public) == {"verdict", "keep"} and public["keep"] is True
    assert studio["annotator"] == "zaid" and studio["verdict"] == public["verdict"]


def test_a_reviewers_name_never_reaches_public_text(keyed, monkeypatch, tmp_path):
    """Audit J2 #1: an answered workflow review once wrote "Reviewed by Jane Reviewer: keep." into the label explanation,
    which /clips, /search, Cosmos DB and the Search index serve to everyone. Who reviewed stays in the annotation."""
    from regista.feedback import load_annotations

    monkeypatch.setattr(api, "DATA_ROOT", tmp_path / "data")
    admin = {"X-Regista-Token": ADMIN}
    events = (SAMPLE / "syn_0294" / "events.jsonl").read_bytes()
    r = keyed.post("/api/matches", params={"match_id": "rv1", "player": "t_home_09", "review": "true"}, headers=admin,
                   files={"events": ("events.jsonl", events, "application/x-ndjson")})
    assert r.status_code == 201 and r.json().get("paused"), r.text
    pending = keyed.get("/api/matches/rv1/review", headers=admin).json()["pending"][0]
    verdicts = [{"clip_id": i["clip_id"], "verdict": "keep", "note": "private note"} for i in pending["request"]["items"]]
    r = keyed.post("/api/matches/rv1/review", headers=admin,
                   json={"request_id": pending["request_id"], "verdicts": verdicts, "annotator": "Jane Reviewer"})
    assert r.status_code == 200, r.text

    clips = keyed.get("/api/matches/rv1/clips")
    found = keyed.get("/api/matches/rv1/search", params={"q": "Castellanos"})
    assert clips.status_code == found.status_code == 200
    assert "Reviewed by a person: kept." in clips.text
    for text in (clips.text, found.text, (tmp_path / "data" / "rv1" / "clips.jsonl").read_text()):
        assert "Jane" not in text and "private note" not in text
    assert {a["annotator"] for a in load_annotations()} == {"Jane Reviewer"}, "the annotation still says who reviewed"
