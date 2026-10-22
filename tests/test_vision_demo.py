"""The demo vision match (data/synthetic/sample/vis_0201) and the packager that made it (regista.vision.package).

The committed match must validate, serve its Who's who questions with crops, refuse answers without changing anything
(the identity result stays on the machine that ran the vision layer, in data/vision/, which the tests never see), and
render with the trimmed tracks. It was cut from footage without name labels, so no crop shows the answer.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.render.scene import Scene
from regista.schema import iter_jsonl, validate_match_dir
from regista.vision.package import downsample_tracks, machine_paths, package_match, trim_tracks
from regista.vision.review import QUEUE_FILE

VIS = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample" / "vis_0201"


def _digest(d: Path) -> dict[str, str]:
    return {p.relative_to(d).as_posix(): hashlib.md5(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture()
def api_on(monkeypatch, tmp_path):
    """The API serving a data root (a copy, so nothing a test does can touch the committed files)."""
    from regista import api

    def serve(root: Path) -> TestClient:
        monkeypatch.setattr(api, "DATA_ROOT", root)
        monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
        return TestClient(api.app)

    return serve


def test_committed_vision_match_validates():
    assert {k: v for k, v in validate_match_dir(VIS).items() if v} == {}
    header = next(iter_jsonl(VIS / "events.jsonl"))
    assert header["match_id"] == VIS.name and header["source"] == "vision"
    manifest = json.loads((VIS / "manifest.json").read_text())
    assert manifest["source"] == "vision" and manifest["clips_for"] == "t_home_09"
    assert "vision layer" in manifest["note"] and "rendered" in manifest["note"]
    assert manifest["rendering"]["captions"] is False
    assert manifest["rendering"]["name_labels"] is False and manifest["rendering"]["holder_ring"] is False  # crops must not print the answer
    assert manifest["score"] == header["score"]
    clips = [c for c in iter_jsonl(VIS / "clips.jsonl") if c["type"] == "clip"]
    assert clips and all(c["player_id"] == "t_home_09" for c in clips)
    assert not (VIS / "agents").exists() and not (VIS / ".vision_work").exists()
    assert machine_paths(VIS) == []
    size = sum(p.stat().st_size for p in VIS.rglob("*") if p.is_file())
    assert size < 3_000_000, f"vis_0201 grew to {size} bytes"


def test_review_queue_loads_with_crops():
    items = json.loads((VIS / "review" / QUEUE_FILE).read_text())["items"]
    assert len(items) >= 3
    assert {"track", "cutaway"} <= {it["kind"] for it in items}
    assert any(it.get("segment_kind") == "replay" for it in items)
    for it in items:
        assert it["image"] and (VIS / "review" / "crops" / it["image"]).stat().st_size > 1000
        assert it["candidates"]


def test_identity_review_served_with_crops(api_on, tmp_path, monkeypatch):
    shutil.copytree(VIS, tmp_path / "data" / VIS.name)
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", "admin-key")
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", "view-key")
    c = api_on(tmp_path / "data")
    assert c.get(f"/api/matches/{VIS.name}/identity-review").status_code in (401, 403)  # reviewers' data: Studio keys only
    out = c.get(f"/api/matches/{VIS.name}/identity-review", headers={"X-Regista-Token": "view-key"}).json()
    assert len(out["items"]) == len(json.loads((VIS / "review" / QUEUE_FILE).read_text())["items"])
    assert set(out["teams"]) == {"t_home", "t_away"}
    for it in out["items"]:
        r = c.get(it["image_url"], headers={"X-Regista-Token": "view-key"})
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"


def test_answering_the_packaged_match_changes_nothing(api_on, tmp_path, monkeypatch):
    """What the live app holds: the questions without the identity result. An answer is refused and nothing moves."""
    d = tmp_path / "data" / VIS.name
    shutil.copytree(VIS, d)
    before = _digest(d)
    c = api_on(tmp_path / "data")
    item = json.loads((d / "review" / QUEUE_FILE).read_text())["items"][0]
    r = c.post(f"/api/matches/{VIS.name}/identity-review",
               json={"answers": [{"item_id": item["item_id"], "player_id": item["candidates"][0]["player_id"]}]})
    assert r.status_code == 409
    assert _digest(d) == before


def test_trimmed_tracks_render_like_the_full_ones():
    """trim_tracks keeps every record the renderer reads: the scene comes out the same."""
    stream = list(iter_jsonl(VIS / "events.jsonl"))
    main = {r["id"] for r in stream if r["type"] == "camera_segment" and r["kind"] == "main"}
    cut = next(r["id"] for r in stream if r["type"] == "camera_segment" and r["kind"] == "replay")
    full = list(iter_jsonl(VIS / "tracks.jsonl"))
    base = {k: full[0][k] for k in ("match_id", "schema_version", "source")} | {"type": "track", "confidence": 0.5,
                                                                                 "bbox": {"x": 0.1, "y": 0.1, "w": 0.02, "h": 0.04}}
    extra = [  # what the packager drops: an unnamed player on the main camera, a replay's ball and repeated players
        {**base, "id": "tr_x1", "t": full[0]["t"], "segment_id": full[0]["segment_id"], "object": "player", "track_id": "u",
         "player_id": None, "pitch": {"x": 1.0, "y": 1.0}},
        {**base, "id": "tr_x2", "t": 200.0, "segment_id": cut, "object": "ball", "track_id": "b", "pitch": {"x": 2.0, "y": 2.0}},
        {**base, "id": "tr_x3", "t": 200.0, "segment_id": cut, "object": "player", "track_id": "p", "player_id": "t_away_10",
         "pitch": {"x": 3.0, "y": 3.0}},
        {**base, "id": "tr_x4", "t": 200.5, "segment_id": cut, "object": "player", "track_id": "p", "player_id": "t_away_10",
         "pitch": {"x": 3.5, "y": 3.0}},
    ]
    trimmed = trim_tracks(full + extra, main)
    assert {"tr_x1", "tr_x2", "tr_x4"}.isdisjoint(r["id"] for r in trimmed)
    a, b = Scene.from_records(stream, full + extra), Scene.from_records(stream, trimmed)
    assert a.cutaway_players == b.cutaway_players and a.sample_gap == b.sample_gap
    assert {k: (t.ts, t.xs, t.ys) for k, t in a.players.items()} == {k: (t.ts, t.xs, t.ys) for k, t in b.players.items()}
    assert (a.ball.ts, a.ball.xs) == (b.ball.ts, b.ball.xs)


def test_downsample_tracks_keeps_whole_frames_per_segment():
    recs = []
    for seg, t0 in (("cs_a", 0.0), ("cs_b", 10.0), ("cs_c", 20.0)):
        for i in range(10):  # a frame every 0.6 s, three objects per frame
            recs += [{"segment_id": seg, "t": round(t0 + 0.6 * i, 1), "object": o} for o in ("player", "player", "ball")]
    out = downsample_tracks(recs, 1.0, segment_ids={"cs_a", "cs_b"})
    kept = {seg: sorted({r["t"] for r in out if r["segment_id"] == seg}) for seg in ("cs_a", "cs_b", "cs_c")}
    assert kept["cs_a"] == [0.0, 1.2, 2.4, 3.6, 4.8]
    assert kept["cs_b"] == [10.0, 11.2, 12.4, 13.6, 14.8]
    assert len(kept["cs_c"]) == 10  # not in segment_ids: passes through
    assert all(sum(1 for r in out if (r["segment_id"], r["t"]) == (s, t)) == 3 for s, ts in kept.items() for t in ts)


def test_closeup_without_tracks_takes_its_player_from_appearances():
    """The vision layer names a closeup's player in an appearance, not a track; the renderer must show that player."""
    stream = list(iter_jsonl(VIS / "events.jsonl"))
    closeup = next(r for r in stream if r["type"] == "camera_segment" and r["kind"] == "closeup")
    named = [a["player_id"] for a in stream if a["type"] == "appearance" and a["segment_id"] == closeup["id"]]
    assert named and not any(r["segment_id"] == closeup["id"] and r.get("player_id") for r in iter_jsonl(VIS / "tracks.jsonl"))
    assert Scene.load(VIS).cutaway_players[closeup["id"]] == named


def test_package_match_round_trip_and_path_guard(tmp_path):
    src = tmp_path / "run" / VIS.name
    shutil.copytree(VIS, src)
    (src / "agents").mkdir()
    (src / "agents" / "trace.jsonl").write_text('{"dir": "/Users/someone/run"}\n')
    m = package_match(src, tmp_path / "out" / VIS.name, player_id="t_home_09", note="test", track_hz=None)
    out = tmp_path / "out" / VIS.name
    assert not (out / "agents").exists() and machine_paths(out) == []
    assert m["review"]["questions"] == len(json.loads((VIS / "review" / QUEUE_FILE).read_text())["items"])
    assert m["files"]["tracks.jsonl"] == sum(1 for _ in iter_jsonl(VIS / "tracks.jsonl"))  # already trimmed: unchanged
    edited = {**json.loads((out / "manifest.json").read_text()), "title": "A heading", "subtitle": "set by hand"}
    (out / "manifest.json").write_text(json.dumps(edited))
    again = package_match(src, out, player_id="t_home_09", note="test", track_hz=None)  # e.g. after a Who's who answer
    assert (again["title"], again["subtitle"]) == ("A heading", "set by hand")
    with pytest.raises(ValueError, match="directory name"):
        package_match(src, tmp_path / "out" / "other", player_id="t_home_09", note="test")
    q = json.loads((src / "review" / QUEUE_FILE).read_text())
    q["items"][0]["question"] = "Who is this? (/Users/someone/video.mp4)"
    (src / "review" / QUEUE_FILE).write_text(json.dumps(q))
    with pytest.raises(ValueError, match="machine paths"):
        package_match(src, tmp_path / "out" / VIS.name, player_id="t_home_09", note="test")
