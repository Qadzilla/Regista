"""The timeline and the take-aways: the match endpoint gives the timeline its frame (duration, periods, goals), a reel
renders the clips asked for in the order asked, and a scout's CSV lists moments with timecodes."""

from __future__ import annotations

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from regista.clips import derive_clips
from regista.render.video import count_frames, frame_times
from regista.synth import generate
from test_live_app import COSMOS_ONLY, _library_store

PLAYER = "t_home_09"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from regista import api

    root = tmp_path_factory.mktemp("data")
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = root / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    (d / "tracks.jsonl").write_text("\n".join(json.dumps(x) for x in r.tracks) + "\n")
    clips, labels = derive_clips(r.stream, PLAYER)
    (d / "clips.jsonl").write_text("\n".join(json.dumps(x) for x in clips + labels) + "\n")
    saved = (api.DATA_ROOT, api.CACHE_ROOT)
    api.DATA_ROOT, api.CACHE_ROOT = root, tmp_path_factory.mktemp("cache")
    with TestClient(api.app) as c:
        c.match_id = r.match["match_id"]
        c.result = r
        c.clips = sorted(clips, key=lambda x: x["t"])
        yield c
    api.DATA_ROOT, api.CACHE_ROOT = saved


# ---------------------------------------------------------------------------- the match, framed for the timeline

def test_match_gives_duration_origin_and_goals(client):
    info = client.get(f"/api/matches/{client.match_id}").json()
    h = client.result.match
    assert info["duration_s"] == h["video"]["duration_s"] and info["origin"] == "synthetic" and info["periods"] == h["periods"]
    goals = [e for e in client.result.stream if e["type"] == "event" and e["event_type"] == "goal"]
    assert len(info["key_moments"]) == len(goals) > 0
    moment = info["key_moments"][0]
    scorer = next(p for p in h["players"] if p["player_id"] == goals[0]["player_id"])
    assert moment == {"t": goals[0]["t"], "kind": "goal", "player_id": scorer["player_id"], "team_id": goals[0]["team_id"],
                      "label": f"Goal: {scorer['name']} ({scorer['kit_number']}), {goals[0]['clock']['minute'] + 1}'"}


def test_goal_minutes_without_a_clock_come_from_the_periods():
    """Vision events carry no clock: the minute is counted from the start of the period they fall in."""
    from regista.api import _match_minute

    h = {"periods": [{"period": 1, "t": 0.0, "t_end": 2700.0}, {"period": 2, "t": 2900.0, "t_end": 5600.0}]}
    assert _match_minute(13.0, {}, h) == 1
    assert _match_minute(2650.0, {}, h) == 45
    assert _match_minute(2900.0 + 61.0, {}, h) == 47
    assert _match_minute(75.0, {}, {"periods": []}) == 2


def test_a_cosmos_only_match_returns_its_header_and_no_moments(client, monkeypatch):
    from regista import api

    store = _library_store(client.result.match)
    monkeypatch.setattr(api, "_feedback_store", lambda: store)
    monkeypatch.setattr(api, "_library_cache", {"t": None, "matches": {}})
    info = client.get(f"/api/matches/{COSMOS_ONLY}").json()
    assert info["source"] == "cosmos" and info["key_moments"] == []
    assert info["duration_s"] == client.result.match["video"]["duration_s"] and info["origin"] == "synthetic"
    # The scout's export works from the library too; the reel needs the event stream on this replica.
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/matches/{COSMOS_ONLY}/moments.csv", params={"player": PLAYER}).text)))
    assert [r["title"] for r in rows] == ["Remote clip"]
    assert client.get(f"/api/matches/{COSMOS_ONLY}/reel.mp4", params={"clips": rows[0]["clip_id"]}).status_code == 409


# ---------------------------------------------------------------------------- the reel

def test_reel_keeps_the_order_given_and_renders_once(client, monkeypatch):
    import regista.render.clips as render_clips

    calls = []
    real = render_clips.render_reel

    def spy(*args, **kwargs):
        out = real(*args, **kwargs)
        calls.append(out["order"])
        return out

    monkeypatch.setattr(render_clips, "render_reel", spy)
    worst_first = sorted(client.clips[:3], key=lambda c: c["t"], reverse=True)
    ids = [c["id"] for c in worst_first]
    url = f"/api/matches/{client.match_id}/reel.mp4"
    r = client.get(url, params={"clips": ",".join(ids), "fps": 5, "width": 320})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4" and len(r.content) > 1000
    assert calls == [ids]
    from regista import api

    reels = list((api.CACHE_ROOT / client.match_id).glob("reel_*.mp4"))
    assert len(reels) == 1 and count_frames(reels[0]) == sum(len(frame_times(c["t"], c["t_end"], 5.0)) for c in worst_first)
    assert client.get(url, params={"clips": ",".join(ids), "fps": 5, "width": 320}).content == r.content and len(calls) == 1
    client.get(url, params={"clips": ",".join(reversed(ids)), "fps": 5, "width": 320})  # another order is another reel
    assert calls[1] == list(reversed(ids)) and len(list((api.CACHE_ROOT / client.match_id).glob("reel_*.mp4"))) == 2


@pytest.mark.parametrize("clips, status", [
    ("../etc", 400),
    ("cl_t_home_09_000001,,cl_t_home_09_000002", 400),
    ("cl_t_home_09_000001,cl_t_home_09_000001", 400),
    (",".join(f"cl_t_home_09_{i:06d}" for i in range(1, 14)), 400),  # the cap is twelve
    ("cl_t_home_09_999999", 404),
    ("cl_t_home_09_000001,cl_nobody_000001", 404),
])
def test_reel_refuses_bad_lists(client, clips, status):
    r = client.get(f"/api/matches/{client.match_id}/reel.mp4", params={"clips": clips})
    assert r.status_code == status, r.text


def test_reel_needs_clips_and_a_real_match(client):
    assert client.get(f"/api/matches/{client.match_id}/reel.mp4").status_code == 422
    assert client.get("/api/matches/nope/reel.mp4", params={"clips": client.clips[0]["id"]}).status_code == 404


def test_reel_accepts_clips_derived_on_the_fly(client, monkeypatch):
    """A player with no clips on disk gets them derived, as the clip endpoint does; the renderer is stubbed here."""
    import regista.render.clips as render_clips

    other = next(p["player_id"] for p in client.result.match["players"] if p["team_id"] == "t_away" and p["kit_number"] == 9)
    derived = client.get(f"/api/matches/{client.match_id}/clips", params={"player": other}).json()
    if not derived:
        pytest.skip("this seed gives the away 9 no clips")

    def fake(scene, clips, labels, out, fps, style, keep_order=False):
        out.write_bytes(b"\0" * 2000)
        return {"path": str(out), "frames": 0, "order": [c["id"] for c in clips]}

    monkeypatch.setattr(render_clips, "render_reel", fake)
    ids = [derived[0]["id"], client.clips[0]["id"]]
    assert client.get(f"/api/matches/{client.match_id}/reel.mp4", params={"clips": ",".join(ids), "fps": 7}).status_code == 200


# ---------------------------------------------------------------------------- the scout's CSV

def _rows(r) -> list[dict[str, str]]:
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv") and r.headers["content-disposition"].startswith("attachment;")
    return list(csv.DictReader(io.StringIO(r.text)))


def test_moments_for_a_player_in_match_order(client):
    r = client.get(f"/api/matches/{client.match_id}/moments.csv", params={"player": PLAYER})
    assert r.text.splitlines()[0] == "time,end,kind,tags,title,watchability,time_s,end_s,clip_id"
    rows = _rows(r)
    assert [x["clip_id"] for x in rows] == [c["id"] for c in client.clips]
    first = rows[0]
    c = client.clips[0]
    assert first["time"] == f"{int(c['t'] // 60)}:{int(c['t'] % 60):02d}" and float(first["time_s"]) == round(c["t"], 2)
    assert {x["kind"] for x in rows} <= {"On the ball", "Replay", "Highlight", "Closeup"}
    assert all("_" not in x["tags"] and "on ball main" not in x["tags"] for x in rows)
    assert all(0 <= float(x["watchability"]) <= 1 for x in rows)
    assert f'filename="regista_{client.match_id}_{PLAYER}_moments.csv"' in r.headers["content-disposition"]


def test_moments_for_chosen_clips_keep_their_order(client):
    ids = [client.clips[4]["id"], client.clips[0]["id"], client.clips[2]["id"]]
    rows = _rows(client.get(f"/api/matches/{client.match_id}/moments.csv", params={"clips": ",".join(ids), "player": PLAYER}))
    assert [x["clip_id"] for x in rows] == ids


def test_moments_refuse_bad_requests(client):
    url = f"/api/matches/{client.match_id}/moments.csv"
    assert client.get(url).status_code == 400
    assert client.get(url, params={"player": "t_nobody"}).status_code == 404
    assert client.get(url, params={"player": "bad id!"}).status_code == 422
    assert client.get(url, params={"clips": "../x"}).status_code == 400
    assert client.get(url, params={"clips": "cl_t_home_09_999999"}).status_code == 404
    assert client.get("/api/matches/nope/moments.csv", params={"player": PLAYER}).status_code == 404


def test_csv_cells_never_run_as_formulas():
    from regista.api import _csv_cell

    assert _csv_cell("=HYPERLINK(\"x\")") == "'=HYPERLINK(\"x\")" and _csv_cell("-1+1") == "'-1+1" and _csv_cell("@sum") == "'@sum"
    assert _csv_cell("Goal at 1'") == "Goal at 1'" and _csv_cell(0.5) == 0.5


# ---------------------------------------------------------------------------- the component

def test_timeline_component_is_served_and_sets_text_never_markup(client):
    """Titles and goal labels can come from uploads or models: the timeline builds its nodes and sets them as text."""
    r = client.get("/static/product/timeline.js")
    assert r.status_code == 200 and "R.timeline = { render }" in r.text
    assert "innerHTML" not in r.text and "insertAdjacentHTML" not in r.text
