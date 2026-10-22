"""The Player view's store: the local backend the tests and offline runs use has the same contract as Azure's."""

import io
import os

import pytest

from regista.player.store import LocalStore, UploadRecord, match_id_for, new_upload_id, store_from_env


def test_store_from_env_is_local_without_an_account(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTA_PLAYER_DIR", str(tmp_path))
    s = store_from_env()
    assert s.kind == "local" and (tmp_path / "uploads").is_dir()
    assert "REGISTA_STORAGE_ACCOUNT" not in os.environ  # tests never reach Azure


def test_upload_record_and_video_round_trip(tmp_path):
    s = LocalStore(tmp_path)
    uid = new_upload_id()
    assert uid.startswith("up_") and match_id_for(uid) == "pv_" + uid[3:]
    n = s.put_video(uid, io.BytesIO(b"x" * 1000))
    rec = UploadRecord(uid, "pl_bro_09", "cl_brookfield", "cl_calder", "home", 9, size_bytes=n)
    s.put_record(rec)
    assert s.get_record(uid).global_id == "pl_bro_09" and s.get_record("up_missing") is None
    s.update(uid, status="running", stages=[{"role": "shots", "status": "ok"}])
    assert s.get_record(uid).status == "running" and [r.upload_id for r in s.list_records()] == [uid]
    out = s.get_video(uid, tmp_path / "work" / "v.mp4")
    assert out.read_bytes() == b"x" * 1000


def test_queue_hands_each_message_to_one_worker(tmp_path):
    s = LocalStore(tmp_path)
    s.enqueue({"upload_id": "up_a", "kind": "vision"})
    s.enqueue({"upload_id": "up_b", "kind": "vision"})
    first, r1 = s.receive()
    second, r2 = s.receive()
    assert {first["upload_id"], second["upload_id"]} == {"up_a", "up_b"} and s.receive() is None
    s.done(r1)
    s.done(r2)


def test_match_folders_and_names_stay_inside_the_store(tmp_path):
    s = LocalStore(tmp_path)
    src = tmp_path / "src"
    (src / "review").mkdir(parents=True)
    (src / "events.jsonl").write_text("{}\n")
    (src / "review" / "q.json").write_text("[]")
    assert s.put_match("pv_1", src) == 2 and s.list_matches() == ["pv_1"]
    assert s.get_match("pv_1", tmp_path / "back") == 2 and (tmp_path / "back" / "review" / "q.json").exists()
    with pytest.raises(ValueError):
        s.get_record("../../etc")


def test_roster_for_footage_carries_both_squads_with_global_ids():
    from regista.player.film import roster_for

    r = roster_for("cl_brookfield", "cl_calder", "away")
    assert [t["club_id"] for t in r["teams"]] == ["cl_calder", "cl_brookfield"]
    assert len(r["players"]) == 36 and all(p["global_player_id"].startswith("pl_") for p in r["players"])
    assert roster_for("cl_brookfield", "cl_calder", "away") == r  # independent of any seed: the worker rebuilds it
    with pytest.raises(ValueError):
        roster_for("cl_brookfield", "cl_brookfield", "home")


def test_film_renders_synthetic_footage_in_the_vision_format(tmp_path):
    from regista.player.film import film
    from regista.vision.frames import probe

    r = film("cl_brookfield", "cl_calder", "home", seed=7, minutes=0.2, out=tmp_path)
    info = probe(r["video"])
    assert (info.width, info.height, round(info.fps)) == (640, 360, 10)
    assert (tmp_path / r["match_id"] / "events.jsonl").exists()
