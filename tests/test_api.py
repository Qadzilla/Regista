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
    assert page.status_code == 200 and "REGI" in page.text and "/static/product/app.js" in page.text
    assert "/api/matches" in client.get("/static/product/app.js").text


def test_list_and_get_match(client):
    matches = client.get("/api/matches").json()
    assert matches and matches[0]["match_id"] == client.match_id
    info = client.get(f"/api/matches/{client.match_id}").json()
    assert info["players_with_clips"] == [PLAYER] and info["clip_count"] > 0
    assert client.get("/api/matches/nope").status_code == 404
    assert client.get("/api/matches/..%2Fetc").status_code in (400, 404)


def test_the_committed_sample_features_syn_0294(monkeypatch, tmp_path):
    """The Product opens on the featured match: the flagship (Castellanos's nutmeg and goal), not the first by name."""
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)
    listed = {m["match_id"]: m for m in TestClient(api.app).get("/api/matches").json()}
    assert [mid for mid, m in listed.items() if m["featured"]] == ["syn_0294"]
    assert all(m["clip_count"] > 0 and m["video"] for m in listed.values())


def test_sample_matches_have_human_titles_and_every_player_with_moments_is_counted(monkeypatch, tmp_path):
    """The Product names matches in words (manifest title and subtitle, never the id) and lists first the players who
    have moments, with how many: the count GET /clips?player= returns, derived on the fly for players with none on disk."""
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)
    c = TestClient(api.app)
    listed = c.get("/api/matches").json()
    titles = [m["title"] for m in listed]
    assert all(titles) and len(set(titles)) == len(titles) and all(m["subtitle"] for m in listed)
    assert not any(m["match_id"] in m["title"] + m["subtitle"] for m in listed)
    info = c.get("/api/matches/syn_0294").json()
    assert info["title"] == next(m["title"] for m in listed if m["match_id"] == "syn_0294")
    counts = info["moment_counts"]
    assert counts["t_home_09"] == 11 and len(counts) > 1 and all(n > 0 for n in counts.values())
    for pid in ("t_home_10", sorted(counts)[0]):
        assert counts[pid] == len(c.get("/api/matches/syn_0294/clips", params={"player": pid}).json()), pid


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


def test_clip_render_on_demand_and_cache(client, monkeypatch):
    from regista import api

    monkeypatch.setattr(api, "RENDER_FPS", {5})
    monkeypatch.setattr(api, "RENDER_WIDTHS", {320})  # small and quick
    clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()
    clip = clips[-1]
    url = f"/api/matches/{client.match_id}/clips/{clip['id']}.mp4"
    r = client.get(url, params={"fps": 5, "width": 320})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) > 1000
    cached = api.CACHE_ROOT / client.match_id / f"{clip['id']}_5fps_320.mp4"
    assert cached.exists()
    assert count_frames(cached) == len(frame_times(clip["t"], clip["t_end"], 5.0))
    assert client.get(url, params={"fps": 5, "width": 320}).content == r.content  # served from cache
    assert client.get(f"/api/matches/{client.match_id}/clips/cl_t_home_09_999999.mp4", params={"fps": 5, "width": 320}).status_code == 404


def test_render_once_under_concurrent_requests(tmp_path):
    """A cold cache asked for the same video by many requests renders it once, never serves a half-written file, and
    leaves no temporary files (the live app answered 503 on a cold start before this)."""
    import threading
    import time

    from regista import api

    calls, out = [], tmp_path / "m" / "clip_25fps_1280.mp4"

    def render(tmp):
        calls.append(tmp)
        tmp.write_bytes(b"half")
        time.sleep(0.2)
        tmp.write_bytes(b"whole video")
        return {"path": str(tmp)}

    seen = []
    threads = [threading.Thread(target=lambda: seen.append(api._render_once(out, render).read_bytes())) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and seen == [b"whole video"] * 8
    assert sorted(p.name for p in out.parent.iterdir()) == [out.name] and not api._render_locks


def test_render_failure_leaves_nothing_and_renders_are_capped(tmp_path, monkeypatch):
    import threading
    import time

    from regista import api

    def broken(tmp):
        tmp.write_bytes(b"partial")
        raise RuntimeError("renderer crashed")

    out = tmp_path / "bad.mp4"
    with pytest.raises(RuntimeError):
        api._render_once(out, broken)
    assert list(tmp_path.iterdir()) == [] and not api._render_locks

    monkeypatch.setattr(api, "_render_slots", threading.BoundedSemaphore(2))
    running, peak, guard = [0], [0], threading.Lock()

    def slow(tmp):
        with guard:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.1)
        with guard:
            running[0] -= 1
        tmp.write_bytes(b"v")
        return {"path": str(tmp)}

    threads = [threading.Thread(target=api._render_once, args=(tmp_path / f"c{i}.mp4", slow)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2 and len(list(tmp_path.glob("c*.mp4"))) == 6


def test_prerender_fills_the_cache_the_endpoint_reads(client, monkeypatch):
    from regista import api

    monkeypatch.setattr(api, "RENDER_FPS", {4})
    monkeypatch.setattr(api, "RENDER_WIDTHS", {160})

    done = api._prerender(fps=4.0, width=160)
    clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()
    assert done and {p.name for p in done} == {f"{c['id']}_4fps_160.mp4" for c in clips}
    first = done[0]
    assert client.get(f"/api/matches/{client.match_id}/clips/{first.name.split('_4fps')[0]}.mp4",
                      params={"fps": 4, "width": 160}).content == first.read_bytes()


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


# ----------------------------------------------------------------------------- review findings (2026-10-20)

def _clip_ids(client):
    return [c["id"] for c in client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()]


def test_writes_need_the_token_when_one_is_set(client, monkeypatch):
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", "s3cret-token")
    cid = _clip_ids(client)[0]
    url = f"/api/matches/{client.match_id}/clips/{cid}/verdict"
    assert client.post(url, json={"verdict": "keep"}).status_code == 401
    assert client.post(url, json={"verdict": "keep"}, headers={"X-Regista-Token": "wrong"}).status_code == 401
    assert client.post(url, json={"verdict": "keep", "annotator": "test-reviewer"}, headers={"X-Regista-Token": "s3cret-token"}).status_code == 200
    assert client.post("/api/feedback/train").status_code == 401
    assert client.get("/api/health").json()["writes"] == "token"
    assert client.get(f"/api/matches/{client.match_id}/clips").status_code == 200, "reads stay open"


def test_read_only_deployment_refuses_every_write(client, monkeypatch):
    monkeypatch.setenv("REGISTA_READONLY", "1")
    cid = _clip_ids(client)[0]
    assert client.post(f"/api/matches/{client.match_id}/clips/{cid}/verdict", json={"verdict": "keep"}).status_code == 403
    assert client.post("/api/feedback/train").status_code == 403
    assert client.post(f"/api/matches/{client.match_id}/review", json={"verdicts": []}).status_code == 403
    assert client.post("/api/matches", files={"events": ("e.jsonl", "{}\n", "application/x-ndjson")}).status_code == 403


@pytest.mark.parametrize("body", [
    {"verdict": "keep", "annotator": "<img src=x onerror=alert(1)>"},
    {"verdict": "keep", "annotator": "x" * 41},
    {"verdict": "fix", "watchability": "0.5"},
    {"verdict": "fix", "watchability": True},
    {"verdict": "fix", "watchability": 1.5},
    {"verdict": "drop", "watchability": 0.9},
    {"verdict": "fix", "tags": "goal"},
    {"verdict": "fix", "tags": [1]},
    {"verdict": "fix", "tags": ["<script>"]},
    {"verdict": "fix", "tags": ["t"] * 21},
    {"verdict": "keep", "note": "n" * 501},
    {"verdict": "maybe"},
])
def test_bad_verdict_bodies_get_422_and_write_nothing(client, body):
    from regista.feedback import load_annotations

    before = len(load_annotations())
    cid = _clip_ids(client)[0]
    r = client.post(f"/api/matches/{client.match_id}/clips/{cid}/verdict", json=body)
    assert r.status_code == 422, (body, r.status_code, r.text[:200])
    assert len(load_annotations()) == before


def test_verdicts_work_for_clips_derived_on_the_fly(client):
    other = next(p["player_id"] for p in client.result.match["players"] if p["team_id"] == "t_away" and p["kit_number"] == 9)
    clips = client.get(f"/api/matches/{client.match_id}/clips", params={"player": other}).json()
    assert clips, "the away 9 has no clips on disk; they are derived"
    r = client.post(f"/api/matches/{client.match_id}/clips/{clips[0]['id']}/verdict", json={"verdict": "keep", "annotator": "test-reviewer"})
    assert r.status_code == 200, r.text
    after = client.get(f"/api/matches/{client.match_id}/clips", params={"player": other}).json()
    assert next(c for c in after if c["id"] == clips[0]["id"])["verdict"]["keep"] is True


def test_upload_under_a_new_match_id_is_relabelled(client):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    events = "\n".join(json.dumps(x) for x in r.stream) + "\n"
    up = client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")},
                     params={"player": PLAYER, "match_id": "copy_of_294"})
    assert up.status_code == 201, up.text
    clips = client.get("/api/matches/copy_of_294/clips", params={"player": PLAYER}).json()
    assert clips and all(c["match_id"] == "copy_of_294" for c in clips)
    assert client.post(f"/api/matches/copy_of_294/clips/{clips[0]['id']}/verdict", json={"verdict": "drop", "annotator": "test-reviewer"}).status_code == 200
    copy = {c["id"]: c for c in client.get("/api/matches/copy_of_294/clips", params={"player": PLAYER}).json()}
    orig = {c["id"]: c for c in client.get(f"/api/matches/{client.match_id}/clips", params={"player": PLAYER}).json()}
    assert copy[clips[0]["id"]]["verdict"] is not None
    assert orig[clips[0]["id"]]["verdict"] is None or orig[clips[0]["id"]]["verdict"]["annotator"] != "test-reviewer" or orig[clips[0]["id"]]["verdict"]["keep"]


def test_a_review_can_only_be_answered_once(client):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    events = "\n".join(json.dumps(x) for x in r.stream) + "\n"
    up = client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")},
                     params={"player": PLAYER, "match_id": "once_294", "review": "true"}).json()
    assert up["paused"]
    req = up["review"][0]
    unknown = client.post("/api/matches/once_294/review", json={"request_id": req["request_id"], "verdicts": [{"clip_id": "cl_x_000001", "verdict": "keep"}]})
    assert unknown.status_code == 422
    body = {"request_id": req["request_id"], "annotator": "test-reviewer", "verdicts": [{"clip_id": i["clip_id"], "verdict": "keep"} for i in req["items"]]}
    assert client.post("/api/matches/once_294/review", json=body).status_code == 200
    assert client.post("/api/matches/once_294/review", json=body).status_code == 404


def test_viewer_escapes_everything_it_renders():
    """Static check: no API value reaches innerHTML unescaped (the Product page and its script)."""
    from pathlib import Path

    product = Path(__file__).resolve().parents[1] / "src/regista/static/product"
    html = (product / "index.html").read_text() + (product / "app.js").read_text()
    assert "const esc = " in html
    for needle in ("${r.title}", "${r.explanation", "${p.name}", "${team.name}", "${out.reply}", "${out.understood", "${out.answered_by}",
                   "${out.detail}", "${s.name}", "${s.kind}", "${t}</span>", "${message}"):
        assert needle not in html, needle
    assert "esc(r.title)" in html and "esc(p.name)" in html and "esc(message)" in html
    # Replies and the Foundry Librarian's words are model output; tool and step names come from MCP servers: all escaped.
    assert "esc(out.reply)" in html and "esc(out.understood" in html and "esc(by)" in html
    assert "esc(s.name)" in html and "esc(s.kind)" in html and "esc(t)}</span>" in html
