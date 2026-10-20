"""The HTTP service must serve the viewer, list and filter clips, search, render on demand, and accept uploads."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.clips import derive_clips
from regista.render.video import count_frames, frame_times
from regista.synth import generate

PLAYER = "t_home_09"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = root / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    (d / "tracks.jsonl").write_text("\n".join(json.dumps(x) for x in r.tracks) + "\n")
    clips, labels = derive_clips(r.stream, PLAYER)
    (d / "clips.jsonl").write_text("\n".join(json.dumps(x) for x in clips + labels) + "\n")
    (d / "manifest.json").write_text(json.dumps({"score": r.score, "clips_for": PLAYER}))
    from regista import api

    api.DATA_ROOT = root
    api.CACHE_ROOT = tmp_path_factory.mktemp("cache")
    with TestClient(api.app) as c:
        c.match_id = r.match["match_id"]
        c.result = r
        yield c


def test_viewer_and_health(client):
    assert client.get("/api/health").json()["ok"] is True
    page = client.get("/")
    assert page.status_code == 200 and "REGI" in page.text and "/api/matches" in page.text


def test_list_and_get_match(client):
    matches = client.get("/api/matches").json()
    assert matches and matches[0]["match_id"] == client.match_id
    info = client.get(f"/api/matches/{client.match_id}").json()
    assert info["players_with_clips"] == [PLAYER] and info["clip_count"] > 0
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/..%2Fetc").status_code in (400, 404)


def test_clip_filters(client):
    all_clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()
    assert all_clips and all(c["video_url"].endswith(".mp4") for c in all_clips)
    watch = [c["label"]["watchability"] for c in all_clips]
    assert watch == sorted(watch, reverse=True)
    goals = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER, "tag": "goal"}).json()
    assert goals and all("goal" in c["label"]["tags"] for c in goals)
    replays = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER, "reason": "replay_appearance", "min_watchability": 0.9}).json()
    assert all(c["reason"] == "replay_appearance" and c["label"]["watchability"] >= 0.9 for c in replays)
    # A player with no clips on disk gets them derived on the fly.
    other = next(p["player_id"] for p in client.result.match["players"] if p["team_id"] == "t_away" and p["kit_number"] == 9)
    derived = client.get(f"/api/matches/{client.match_id}/clips", params={"player": other}).json()
    assert all(c["player_id"] == other for c in derived)


def test_search(client):
    surname = next(p["name"].split()[-1] for p in client.result.match["players"] if p["player_id"] == PLAYER)
    out = client.get(f"/api/matches/{client.match_id}/search", params={"q": f"find me {surname} doing a nutmeg"}).json()
    assert out["parsed"]["player_id"] == PLAYER and out["results"]
    assert all(r["video_url"].endswith(".mp4") and "nutmeg" in r["tags"] for r in out["results"])


def test_clip_render_on_demand_and_cache(client):
    clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()
    clip = clips[-1]
    url = f"/api/matches/{client.match_id}/clips/{clip['id']}.mp4"
    r = client.get(url, params={"fps": 5, "width": 320})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) > 1000
    from regista import api

    cached = api.CACHE_ROOT / client.match_id / f"{clip['id']}_5fps_320.mp4"
    assert cached.exists()
    assert count_frames(cached) == len(frame_times(clip["t"], clip["t_end"], 5.0))
    assert client.get(url, params={"fps": 5, "width": 320}).content == r.content  # served from cache
    assert client.get(f"/api/matches/{client.match_id}/clips/cl_t_home_09_999999.mp4").status_code == 404


def test_report_endpoint(client):
    md = client.get(f"/api/matches/{client.match_id}/report").text
    assert "Synthetic realism report" in md and "shots_per90" in md


def test_upload_runs_the_pipeline(client):
    r = generate(seed=7, minutes=1.0, track_hz=1.0)
    events = "\n".join(json.dumps(x) for x in r.stream) + "\n"
    resp = client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")}, params={"player": "t_home_09"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["match_id"] == r.match["match_id"] and body["pipeline_ok"] is True
    assert body["clips"]["t_home_09"] >= 0
    assert client.get(f"/api/matches/{r.match['match_id']}").status_code == 200
    # Second upload of the same id is a conflict; invalid JSONL is rejected with the problems listed.
    assert client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")}).status_code == 409
    bad = client.post("/api/matches", files={"events": ("events.jsonl", '{"type":"match"}\n', "application/x-ndjson")})
    assert bad.status_code == 422 and "problems" in json.dumps(bad.json())


def test_verdicts_feedback_and_retrain_through_the_api(client, tmp_path, monkeypatch):
    """The viewer's Keep/Drop buttons and Retrain button, end to end. Verdicts come from a test annotator."""
    clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()
    assert any(c["review"] for c in clips), "the sample has clips the Label agent is unsure about"
    assert all("verdict" in c for c in clips)
    first = clips[0]
    r = client.post(f"/api/matches/{client.match_id}/clips/{first['id']}/verdict", json={"verdict": "drop", "annotator": "test-reviewer"})
    assert r.status_code == 200 and r.json()["annotation"]["source"] == "human"
    after = {c["id"]: c for c in client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()}
    assert after[first["id"]]["verdict"]["keep"] is False and after[first["id"]]["review"] is None
    assert client.post(f"/api/matches/{client.match_id}/clips/{first['id']}/verdict", json={"verdict": "maybe"}).status_code == 422
    status = client.get("/api/feedback").json()
    assert status["verdicts"] >= 1 and "test-reviewer" in status["annotators"]
    # Too few verdicts: retraining refuses with a clear reason.
    assert client.post("/api/feedback/train").status_code == 422
    for c in clips[1:]:
        keep = c["label"]["watchability"] >= 0.5
        client.post(f"/api/matches/{client.match_id}/clips/{c['id']}/verdict", json={"verdict": "keep" if keep else "drop", "annotator": "test-reviewer"})
    trained = client.post("/api/feedback/train")
    if trained.status_code == 200:
        assert trained.json()["model_name"].startswith("learned-v")
    else:
        assert "both" in trained.json()["detail"] or "at least" in trained.json()["detail"]


def test_upload_with_review_pauses_and_resumes(client):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    stream = [dict(x) for x in r.stream]
    stream[0] = {**stream[0], "match_id": "syn_0294_review"}
    for x in stream[1:]:
        x["match_id"] = "syn_0294_review"
    events = "\n".join(json.dumps(x) for x in stream) + "\n"
    up = client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")},
                     params={"player": PLAYER, "review": "true", "annotator": "test-reviewer"})
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["paused"] is True and body["review"][0]["items"]
    pending = client.get("/api/matches/syn_0294_review/review").json()["pending"]
    assert pending and pending[0]["request_id"] == body["review"][0]["request_id"]
    items = body["review"][0]["items"]
    done = client.post("/api/matches/syn_0294_review/review", json={
        "request_id": pending[0]["request_id"], "annotator": "test-reviewer",
        "verdicts": [{"clip_id": i["clip_id"], "verdict": "keep"} for i in items]})
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["pipeline_ok"] is True and out["review_log"]["applied"]
    assert client.get("/api/matches/syn_0294_review/review").json()["pending"] == []
