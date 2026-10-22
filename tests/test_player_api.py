"""The Player view's API (/me): uploads (admin only, size and type limits, a record and a queue message), status reads,
a finished match served like any other and counted in its uploader's profile, and "is this you?".

The worker is another session's code: these tests stand in for it with a small valid match folder written to the local
store, as the worker would write it (``matches/pv_…``), and a record set to done or needs_review.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api, player_api
from regista.player.film import friendly_kwargs
from regista.player.store import LocalStore, UploadRecord, match_id_for
from regista.schema import write_jsonl
from regista.season.build import materialise
from regista.season.league import new_league, save_league
from regista.synth.generator import generate

ADMIN, VIEW = "admin-key-for-tests", "view-key-for-tests"
GID, CLUB, OPP = "pl_bro_09", "cl_brookfield", "cl_calder"
MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64  # an MP4's first box: enough for the type check
ME = Path(__file__).resolve().parents[1] / "src/regista/static/me"


@pytest.fixture(scope="module")
def league():
    full = new_league(2026)
    return {**full, "fixtures": full["fixtures"][:2]}  # two league matches: quick to build


@pytest.fixture(scope="module")
def season_root(tmp_path_factory, league):
    root = tmp_path_factory.mktemp("season")
    for fx in league["fixtures"]:
        materialise(league, fx, root)
    return root


@pytest.fixture()
def client(tmp_path, monkeypatch, league, season_root):
    monkeypatch.setattr(api, "SEASON_LEAGUE", save_league(league, tmp_path / "league.json"))
    monkeypatch.setattr(api, "SEASON_ROOT", season_root)
    monkeypatch.setattr(api, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(player_api, "PLAYER_MATCHES", tmp_path / "player_matches")
    monkeypatch.setattr(player_api, "_checked", {})
    monkeypatch.setattr(player_api, "_listed", {"t": 0.0, "rows": []})
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    with TestClient(api.app) as c:
        yield c


def _store() -> LocalStore:
    s = player_api.store()
    assert isinstance(s, LocalStore)
    return s


def _upload(c, video=MP4, name="match.mp4", ctype="video/mp4", key=ADMIN, **fields):
    data = {"global_id": GID, "opponent_club_id": OPP, "side": "home", **fields}
    headers = {"X-Regista-Token": key} if key else {}
    return c.post("/api/player/uploads", data=data, files={"video": (name, video, ctype)}, headers=headers)


def _finished(league, status="done", questions=True) -> UploadRecord:
    """What the worker leaves behind: a record and ``matches/pv_…`` (events, tracks, clips derived later, manifest,
    review/ with one question about the uploader and one about someone else)."""
    s = _store()
    rec = UploadRecord(upload_id="up_test000001", global_id=GID, club_id=CLUB, opponent_club_id=OPP, side="home", kit_number=9)
    mid = match_id_for(rec.upload_id)
    kw = friendly_kwargs(league, CLUB, OPP, "home", seed=4101, minutes=1.5)
    kw["match_id"] = mid
    result = generate(**kw)
    folder = Path(s.root) / "work" / mid
    write_jsonl(folder / "events.jsonl", result.stream)
    write_jsonl(folder / "tracks.jsonl", result.tracks)
    (folder / "manifest.json").write_text(json.dumps({"match_id": mid, "title": "Friendly, filmed by the player",
                                                      "source": "vision", "video": {"path": "/job/video.mp4"}}))
    me = next(p for p in result.match["players"] if p.get("global_player_id") == GID)
    other = next(p for p in result.match["players"] if p["team_id"] != me["team_id"])
    who = lambda p, v: {"player_id": p["player_id"], "name": p["name"], "kit_number": p["kit_number"], "team": "", "p": v}  # noqa: E731
    items = [{"item_id": "tr_3", "kind": "track", "track_index": 3, "team_id": me["team_id"], "is_gk": False, "segment_id": "cs_1",
              "t": 20.0, "t0": 18.0, "t1": 24.0, "current": None, "confidence": 0.0, "candidates": [who(me, 0.6)],
              "question": "Who is this player?", "image": "tr_3.jpg"},
             {"item_id": "tr_8", "kind": "track", "track_index": 8, "team_id": other["team_id"], "is_gk": False, "segment_id": "cs_1",
              "t": 30.0, "t0": 29.0, "t1": 33.0, "current": other["player_id"], "confidence": 0.5, "candidates": [who(other, 0.5)],
              "question": "Who is this player?", "image": "tr_8.jpg"}]
    if questions:
        (folder / "review" / "crops").mkdir(parents=True)
        (folder / "review" / "identity_review.json").write_text(json.dumps({"items": items}))
        (folder / "review" / "crops" / "tr_3.jpg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    s.put_match(mid, folder)
    rec.match_id, rec.status = mid, status
    rec.stages = [{"role": r, "status": "ok", "ms": 100} for r in ("queued", "shots", "identity", "possession_vision",
                                                                    "events_vision", "vision_writer")]
    s.put_record(rec)
    return rec


# ---------------------------------------------------------------------------- the upload

def test_upload_stores_the_video_writes_a_record_and_queues_the_job(client):
    r = _upload(client)
    assert r.status_code == 201, r.text
    up = r.json()["upload"]
    assert re.match(r"^up_[0-9a-f]{10}$", up["upload_id"]) and up["match_id"] == "pv_" + up["upload_id"][3:]
    assert (up["global_id"], up["club_id"], up["opponent_club_id"], up["side"], up["kit_number"], up["status"]) == \
        (GID, CLUB, OPP, "home", 9, "queued")
    assert up["player"]["name"] and up["opponent"]["club_id"] == OPP and up["links"] is None
    s = _store()
    assert (Path(s.root) / "uploads" / up["upload_id"] / "video.mp4").read_bytes() == MP4
    assert s.get_record(up["upload_id"]).size_bytes == len(MP4)
    msg, receipt = s.receive()
    assert msg == {"upload_id": up["upload_id"], "kind": "vision"}
    s.done(receipt)


@pytest.mark.parametrize("key, status", [(None, 401), ("wrong", 401), (VIEW, 403)])
def test_upload_is_admin_only(client, key, status):
    r = _upload(client, key=key)
    assert r.status_code == status
    s = _store()
    assert s.list_records() == [] and s.receive() is None


def test_upload_refuses_what_is_not_an_mp4(client):
    assert _upload(client, name="match.mov").status_code == 415
    assert _upload(client, video=b"not a video at all, just text").status_code == 415
    assert _upload(client, ctype="text/plain").status_code == 415
    assert _store().list_records() == []


def test_upload_refuses_a_video_over_the_limit_before_reading_it(client, monkeypatch):
    monkeypatch.setattr(player_api, "MAX_VIDEO_BYTES", 50)
    monkeypatch.setattr(player_api, "FORM_SLACK", 1000)
    r = _upload(client, video=MP4 + b"\x00" * 2000)
    assert r.status_code == 413 and "MB" in r.json()["detail"]
    assert _store().list_records() == []


def test_the_store_enforces_the_limit_on_what_actually_arrives(client, monkeypatch):
    import regista.player.store as store_mod

    monkeypatch.setattr(store_mod, "MAX_VIDEO_BYTES", 40)
    r = _upload(client)
    assert r.status_code == 413
    assert _store().list_records() == [] and _store().receive() is None


@pytest.mark.parametrize("fields, status", [({"global_id": "pl_nobody_99"}, 404), ({"global_id": "Robert'); --"}, 422),
                                            ({"opponent_club_id": CLUB}, 422), ({"opponent_club_id": "cl_nowhere"}, 404),
                                            ({"side": "middle"}, 422)])
def test_upload_checks_the_player_the_club_and_the_side(client, fields, status):
    assert _upload(client, **fields).status_code == status


def test_upload_needs_a_multipart_body(client):
    r = client.post("/api/player/uploads", json={"global_id": GID}, headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 415


# ---------------------------------------------------------------------------- status reads

def test_status_reads_are_public_and_show_the_stages(client, league):
    up = _upload(client).json()["upload"]
    _store().update(up["upload_id"], status="running", stages=[*up["stages"], {"role": "shots", "status": "running"}])
    one = client.get(f"/api/player/uploads/{up['upload_id']}")
    assert one.status_code == 200 and one.json()["status"] == "running"
    assert [s["role"] for s in one.json()["stages"]] == ["queued", "shots"]
    listed = client.get("/api/player/uploads", params={"global_id": GID}).json()["uploads"]
    assert [u["upload_id"] for u in listed] == [up["upload_id"]]
    assert client.get("/api/player/uploads", params={"global_id": "pl_ash_01"}).json()["uploads"] == []
    assert client.get("/api/player/uploads/up_missing0000").status_code == 404
    assert client.get("/api/player/uploads/..%2F..%2Fetc").status_code in (400, 404)
    assert "/job/" not in one.text and "video.mp4" not in json.dumps(one.json().get("links"))


# ---------------------------------------------------------------------------- a finished match

def test_a_done_match_is_served_like_any_other(client, league):
    rec = _finished(league)
    view = client.get(f"/api/player/uploads/{rec.upload_id}").json()
    pid = view["match"]["player_id"]
    assert pid and view["links"]["clip_view"] == f"/?match={rec.match_id}&player={pid}"
    assert view["links"]["profile"] == f"/players/{GID}"
    m = client.get(f"/api/matches/{rec.match_id}")
    assert m.status_code == 200 and m.json()["title"] == "Friendly, filmed by the player"
    clips = client.get(f"/api/matches/{rec.match_id}/clips", params={"player": pid}).json()
    assert clips and all(c["player_id"] == pid for c in clips)
    assert (player_api.PLAYER_MATCHES / rec.match_id / "events.jsonl").exists()
    assert client.get("/api/matches/pv_nothing0000").status_code == 404


def test_a_running_upload_has_no_match_yet(client, league):
    rec = _finished(league, status="running")
    assert client.get(f"/api/matches/{rec.match_id}").status_code == 404
    assert client.get(f"/api/player/uploads/{rec.upload_id}").json()["links"] is None


def test_a_done_match_counts_in_the_uploaders_profile_and_only_theirs(client, league):
    before = client.get(f"/api/players/{GID}").json()
    rec = _finished(league)
    player_api._forget_listing()
    after = client.get(f"/api/players/{GID}").json()
    assert after["appearances"] == before["appearances"] + 1
    row = next(m for m in after["matches"] if m["match_id"] == rec.match_id)
    assert row["source"] == "upload" and row["upload_id"] == rec.upload_id and row["round"] is None
    assert any(m["match_id"] == rec.match_id for m in after["moments"]) or after["counts"]["touches"] > before["counts"]["touches"]
    # A teammate on the same footage did not upload it: their profile is untouched.
    mate = next(gid for gid in (p["global_id"] for p in league["clubs"][1]["squad"]) if gid != GID)
    assert all(m["match_id"] != rec.match_id for m in client.get(f"/api/players/{mate}").json()["matches"])


def test_a_match_waiting_for_answers_does_not_count_yet(client, league):
    before = client.get(f"/api/players/{GID}").json()["appearances"]
    _finished(league, status="needs_review")
    player_api._forget_listing()
    assert client.get(f"/api/players/{GID}").json()["appearances"] == before


# ---------------------------------------------------------------------------- "is this you?"

def test_questions_are_only_about_the_uploader(client, league):
    rec = _finished(league, status="needs_review")
    q = client.get(f"/api/player/uploads/{rec.upload_id}/questions").json()
    assert [it["item_id"] for it in q["items"]] == ["tr_3"]
    it = q["items"][0]
    assert it["question"] == "Is this you?" and it["regista_thinks_its_you"] is False and it["p"] == 0.6
    img = client.get(it["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/player/uploads/{rec.upload_id}/crops/..%2Fevents.jsonl").status_code in (400, 404)


@pytest.mark.parametrize("key, status", [(None, 401), (VIEW, 403)])
def test_answers_are_admin_only(client, league, key, status):
    rec = _finished(league, status="needs_review")
    headers = {"X-Regista-Token": key} if key else {}
    r = client.post(f"/api/player/uploads/{rec.upload_id}/answers", json={"answers": []}, headers=headers)
    assert r.status_code == status and _store().get_record(rec.upload_id).status == "needs_review"


def test_no_answers_finishes_the_match_as_the_agents_left_it(client, league):
    rec = _finished(league, status="needs_review")
    r = client.post(f"/api/player/uploads/{rec.upload_id}/answers", json={"answers": []}, headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 200 and r.json()["upload"]["status"] == "done"
    assert _store().get_record(rec.upload_id).status == "done"
    again = client.post(f"/api/player/uploads/{rec.upload_id}/answers", json={"answers": []}, headers={"X-Regista-Token": ADMIN})
    assert again.status_code == 409


def test_answers_go_through_the_identity_review_and_the_match_goes_back_to_the_store(client, league, monkeypatch):
    rec = _finished(league, status="needs_review")
    d = player_api.PLAYER_MATCHES / rec.match_id
    client.get(f"/api/player/uploads/{rec.upload_id}")  # fetched
    (d / ".vision_work").mkdir()
    (d / ".vision_work" / "identity.joblib").write_bytes(b"stand-in")
    monkeypatch.setattr(player_api, "_models_dir", lambda d: None)
    seen = {}

    def fake_apply(work, claimed, body, served=None, models_dir=None):
        seen.update(work=work, answers=[a.model_dump(exclude_none=True) for a in body.answers], annotator=body.annotator,
                    queue_claimed=claimed.exists(), video=json.loads((work / "manifest.json").read_text())["video"]["path"])
        (work / "recomputed.txt").write_text("yes")
        return {"renamed": [[3, None, "x"]]}

    monkeypatch.setattr(api, "_apply_identity_review", fake_apply)
    _store().put_video(rec.upload_id, io.BytesIO(MP4))
    pid = client.get(f"/api/player/uploads/{rec.upload_id}").json()["match"]["player_id"]
    r = client.post(f"/api/player/uploads/{rec.upload_id}/answers", json={"answers": [{"item_id": "tr_3", "is_me": True}]},
                    headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 200, r.text
    assert seen["answers"] == [{"item_id": "tr_3", "player_id": pid}] and seen["queue_claimed"] and seen["annotator"] == "player"
    assert Path(seen["video"]).read_bytes() == MP4 and not str(Path(seen["video"])).startswith(str(d))  # never pushed back
    assert (Path(_store().root) / "matches" / rec.match_id / "recomputed.txt").exists()       # pushed to the store
    assert (d / "clips.jsonl").exists() and _store().get_record(rec.upload_id).status == "done"
    assert _store().get_record(rec.upload_id).stages[-1]["role"] == "identity_review"


def test_an_answer_about_someone_else_is_refused(client, league):
    rec = _finished(league, status="needs_review")
    r = client.post(f"/api/player/uploads/{rec.upload_id}/answers", json={"answers": [{"item_id": "tr_8", "is_me": True}]},
                    headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 422 and _store().get_record(rec.upload_id).status == "needs_review"


def test_yes_and_no_become_who_s_who_answers():
    from regista.vision.review import NOT_A_PLAYER, UNKNOWN

    items = [{"item_id": "tr_1", "kind": "track", "current": None}, {"item_id": "tr_2", "kind": "track", "current": "me"},
             {"item_id": "cw_a", "kind": "cutaway", "current": ["x"]}, {"item_id": "cw_b", "kind": "cutaway", "current": ["x", "me"]}]
    body = player_api.AnswersIn(answers=[{"item_id": "tr_1", "is_me": False}, {"item_id": "tr_2", "is_me": False},
                                         {"item_id": "cw_a", "is_me": True}, {"item_id": "cw_b", "is_me": False}])
    assert player_api._identity_answers(items, body, "me") == [
        {"item_id": "tr_1", "player_id": UNKNOWN}, {"item_id": "tr_2", "player_id": NOT_A_PLAYER},
        {"item_id": "cw_a", "players": ["x", "me"]}, {"item_id": "cw_b", "players": ["x"]}]


# ---------------------------------------------------------------------------- the page

def test_me_serves_the_page_with_same_origin_scripts_only(client):
    r = client.get("/me", params={"player": GID})
    assert r.status_code == 200 and r.text == (ME / "index.html").read_text()
    assert "script-src 'self'" in r.headers["content-security-policy"]
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", r.text, flags=re.S)
    assert scripts
    for attrs, body in scripts:
        src = re.search(r'\bsrc="([^"]+)"', attrs)
        assert src and body.strip() == "" and src.group(1).startswith("/static/")
        assert client.get(src.group(1)).status_code == 200
    assert not re.search(r"\son[a-z]+=", r.text), "no inline event handlers"
    for href in re.findall(r'<link rel="stylesheet" href="([^"]+)"', r.text):
        assert client.get(href).status_code == 200


def test_the_page_never_parses_api_text_as_markup():
    script = (ME / "me.js").read_text()
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "eval(" not in script
    assert "X-Regista-Token" in script and "sessionStorage." not in script  # the key: shared/regista.js keeps it


@pytest.mark.parametrize("path, current", [("/", "/"), ("/scout", "/scout"), (f"/players/{GID}", "/scout"), ("/me", "/me")])
def test_every_view_links_to_the_player_view(client, path, current):
    nav = re.search(r'<nav class="views"[^>]*>(.*?)</nav>', client.get(path).text, flags=re.S).group(1)
    assert re.findall(r'href="([^"]+)"', nav) == ["/", "/scout", "/me"]
    assert f'href="{current}" aria-current="page"' in nav
