"""The Player view's worker on the local store: stages reported as the workflow runs, done versus needs_review, failures
recorded in plain English, ``--once`` on an empty queue, the manifest and clips, and the models in the store.

The vision roles are stand-ins (the real workflow, its streaming and its dead letters, with roles that write a small
generated match instead of watching video), because CI has no trained models. One test runs the real vision workflow
on ten seconds of footage when trained models are on this machine (``REGISTA_TEST_MODELS``, default ``models/vision``).
"""

from __future__ import annotations

import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pytest

from regista.agents.base import Agent, AgentError
from regista.player import worker
from regista.player.models import pull, push
from regista.player.store import LocalStore, UploadRecord, match_id_for, new_upload_id
from regista.schema import iter_jsonl, validate_match_dir, write_jsonl

CLUB, OPPONENT = "cl_brookfield", "cl_calder"


def tiny_video(path: Path, seconds: float = 2.0, size: tuple[int, int] = (640, 360), fps: float = 10.0) -> Path:
    import imageio_ffmpeg

    w = imageio_ffmpeg.write_frames(str(path), size, fps=fps, macro_block_size=1, quality=5)
    w.send(None)
    frame = np.full((size[1], size[0], 3), (40, 140, 60), dtype=np.uint8)
    for _ in range(int(seconds * fps)):
        w.send(frame.tobytes())
    w.close()
    return path


@pytest.fixture
def store(tmp_path):
    s = LocalStore(tmp_path / "store")
    models = tmp_path / "models"
    models.mkdir()
    for f in ("shot_model.joblib", "kit_number_reader.joblib", "identity_config.json", "event_spotter.joblib"):
        (models / f).write_bytes(b"stand-in")
    push(s, models)
    worker._PULLED.clear()
    return s


def queue_upload(store: LocalStore, video: Path, *, side: str = "home", global_id: str = "pl_bro_09", kit: int = 9) -> str:
    upload_id = new_upload_id()
    with video.open("rb") as fh:
        n = store.put_video(upload_id, fh)
    store.put_record(UploadRecord(upload_id=upload_id, global_id=global_id, club_id=CLUB, opponent_club_id=OPPONENT, side=side,
                                  kit_number=kit, size_bytes=n))
    store.enqueue({"upload_id": upload_id, "kind": "vision"})
    return upload_id


# ---------------------------------------------------------------------------- stand-in vision roles

@dataclass
class StandIn(Agent):
    fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def handle(self, state):
        return self.fn(state)


def stand_in_agents(questions: Callable[[dict], list[dict]] = lambda roster: [], fail: str | None = None) -> list[Agent]:
    """The five vision roles with the real roles' contracts; the writer writes a 30-second generated match for the
    roster's two clubs under the requested match id (a valid stream the clip rule can cut)."""
    from regista.vision.agents import vision_agents

    def shots(state):
        state["camera_segments"] = [{"id": "cs_1", "kind": "main", "t": 0.0, "t_end": 2.0}]
        return state

    def identity(state):
        if fail == "identity":
            raise AgentError("ValueError: no players found", retryable=False)
        state["identity_path"] = str(Path(state["out_dir"]) / ".vision_work" / "identity.joblib")
        state["identity_summary"] = {"tracks": 24, "named_tracks": 20, "cutaway_segments": 1}
        return state

    def possession(state):
        state["possessions"] = [{"id": "po_1"}, {"id": "po_2"}]
        return state

    def events(state):
        state["vision_events"] = [{"event_type": "pass"}, {"event_type": "pass"}, {"event_type": "shot"}]
        return state

    def writer(state):
        from regista.player.film import friendly_kwargs
        from regista.season.league import load_league_cached
        from regista.synth.generator import generate

        roster = state["roster"]
        clubs = {t["team_id"]: t["club_id"] for t in roster["teams"]}
        home, away = clubs[roster["home_team_id"]], clubs[roster["away_team_id"]]
        kw = friendly_kwargs(load_league_cached("data/season/league.json"), home, away, "home", seed=5, minutes=0.5)
        kw["match_id"] = state["match_id"]
        result = generate(**kw)
        out = Path(state["out_dir"])
        write_jsonl(out / "events.jsonl", result.stream)
        write_jsonl(out / "tracks.jsonl", result.tracks)
        (out / "manifest.json").write_text(json.dumps({"record_counts": {"match": 1}, "segments": {"main": 1}, "validation": {},
                                                       "video": {"path": "/somewhere/on/the/worker"}}))
        (out / ".vision_work").mkdir(parents=True, exist_ok=True)
        (out / ".vision_work" / "identity.joblib").write_bytes(b"identity")
        (out / ".vision_work" / "run.json").write_text(json.dumps({"models_dir": "/tmp/regista-models/vision"}))
        items = questions(roster)
        if items:
            (out / "review").mkdir(exist_ok=True)
            (out / "review" / "identity_review.json").write_text(json.dumps({"items": items}))
        state["match_dir"] = str(out)
        state["vision_summary"] = {"match_id": state["match_id"], "review_questions": len(items)}
        return state

    fns = {"shots": shots, "identity": identity, "possession_vision": possession, "events_vision": events, "vision_writer": writer}
    return [StandIn(role=a.role, inputs=a.inputs, outputs=a.outputs, fn=fns[a.role]) for a in vision_agents({})]


def track_question(team_id: str, current: str | None, candidates: list[str], item_id: str = "tr_1") -> dict:
    return {"item_id": item_id, "kind": "track", "team_id": team_id, "current": current,
            "candidates": [{"player_id": c, "p": 0.5} for c in candidates]}


@pytest.fixture
def snapshots(store, monkeypatch):
    """Every record the worker writes, in order: proves progress was written while the workflow ran."""
    seen: list[UploadRecord] = []
    put = store.put_record

    def spy(rec):
        seen.append(UploadRecord.from_json(json.loads(json.dumps(rec.to_json()))))
        put(rec)

    monkeypatch.setattr(store, "put_record", spy)
    return seen


# ---------------------------------------------------------------------------- the tests

def test_an_upload_becomes_a_match_with_every_stage_reported(store, snapshots, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents())
    upload_id = queue_upload(store, tiny_video(tmp_path / "v.mp4"))
    assert worker.handle_one(store) == upload_id

    rec = store.get_record(upload_id)
    assert rec.status == "done" and rec.error is None and rec.match_id == match_id_for(upload_id)
    roles = [s["role"] for s in rec.stages]
    assert roles == ["download", "shots", "identity", "identity_review", "possession_vision", "events_vision", "vision_writer",
                     "clips", "publish"]
    assert all(s["status"] == "ok" for s in rec.stages), rec.stages
    assert all(isinstance(s["ms"], int) for s in rec.stages)
    notes = {s["role"]: s["note"] for s in rec.stages}
    assert notes["shots"] == "1 camera shots: 1 main"
    assert notes["identity"].startswith("20 of 24 player tracks named")
    assert notes["events_vision"].startswith("3 events: 2 pass")
    assert "saved for you" in notes["identity_review"]

    # Live: each role was written as running before its result, in workflow order.
    order = []
    for snap in snapshots:
        for s in snap.stages:
            if (s["role"], s["status"]) not in order and s["status"] in ("running", "ok"):
                order.append((s["role"], s["status"]))
    for role in roles:
        assert order.index((role, "running")) < order.index((role, "ok"))
    assert order.index(("identity", "ok")) < order.index(("possession_vision", "running"))
    assert any(s.status == "running" for s in snapshots)
    assert store.receive() is None  # the message is gone


def test_the_match_folder_has_the_manifest_and_every_starters_clips(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents())
    upload_id = queue_upload(store, tiny_video(tmp_path / "v.mp4"), side="away", global_id="pl_bro_09")
    worker.handle_one(store)
    match_id = match_id_for(upload_id)
    assert store.list_matches() == [match_id]
    d = tmp_path / "got"
    store.get_match(match_id, d)
    for f in ("events.jsonl", "tracks.jsonl", "clips.jsonl", "manifest.json", ".vision_work/identity.joblib", "agents/trace.jsonl"):
        assert (d / f).exists(), f
    assert not any(validate_match_dir(d).values())

    m = json.loads((d / "manifest.json").read_text())
    assert m["title"] == f"{m['player']['name']}'s match: Calder Town v Brookfield Rovers"
    assert (m["collection"], m["source"], m["uploaded_by"], m["upload_id"]) == ("player", "vision", "pl_bro_09", upload_id)
    assert m["player"]["team_id"] == "t_away" and m["player"]["kit_number"] == 9
    assert m["video"]["blob"] == f"uploads/{upload_id}/video.mp4" and "path" not in m["video"]
    assert "/somewhere" not in json.dumps(m) and "/tmp/" not in (d / ".vision_work" / "run.json").read_text()

    header = next(iter_jsonl(d / "events.jsonl"))
    assert "score" in header
    starters = {p["player_id"] for p in header["players"] if p["starter"]}
    recs = list(iter_jsonl(d / "clips.jsonl"))
    clips = [r for r in recs if r["type"] == "clip"]
    assert clips and {c["player_id"] for c in clips} <= starters | {m["player"]["player_id"]}
    assert len({c["player_id"] for c in clips}) > 3  # more than the uploader: every starter
    assert m["clip_count"] == len(clips) and len([r for r in recs if r["type"] == "label"]) == len(clips)
    assert m["player_clip_count"] == sum(1 for c in clips if c["player_id"] == m["player"]["player_id"])


def test_questions_about_the_players_own_track_need_review(store, tmp_path, monkeypatch):
    video = tiny_video(tmp_path / "v.mp4")

    def mine(roster):
        return [track_question("t_home", "t_home_09", ["t_home_09", "t_home_06"]), track_question("t_away", None, ["t_away_09"], "tr_2")]

    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents(mine))
    up = queue_upload(store, video)
    worker.handle_one(store)
    rec = store.get_record(up)
    assert rec.status == "needs_review" and rec.match_id == match_id_for(up)
    d = tmp_path / "m"
    store.get_match(rec.match_id, d)
    m = json.loads((d / "manifest.json").read_text())
    assert m["review"] == {"questions": 2, "kinds": {"track": 2}, "about_player": ["tr_1"]}
    assert "1 about you" in next(s["note"] for s in rec.stages if s["role"] == "vision_writer")
    assert (d / "review" / "identity_review.json").exists()


def test_questions_about_other_players_only_leave_the_upload_done(store, tmp_path, monkeypatch):
    def others(roster):  # the uploader's kit number on the other team, and a teammate: not about them
        return [track_question("t_away", "t_away_09", ["t_away_09", "t_home_09"]), track_question("t_home", "t_home_06", ["t_home_06"], "tr_2")]

    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents(others))
    up = queue_upload(store, tiny_video(tmp_path / "v.mp4"))
    worker.handle_one(store)
    assert store.get_record(up).status == "done"


def test_a_failing_role_fails_the_upload_with_its_reason(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents(fail="identity"))
    up = queue_upload(store, tiny_video(tmp_path / "v.mp4"))
    worker.handle_one(store)
    rec = store.get_record(up)
    assert rec.status == "failed" and rec.match_id is None
    assert "identity step" in rec.error and "no players found" in rec.error
    status = {s["role"]: s["status"] for s in rec.stages}
    assert status["shots"] == "ok" and status["identity"] == "failed"
    assert all(status[r] == "skipped" for r in ("possession_vision", "events_vision", "vision_writer", "clips", "publish"))
    assert store.receive() is None and store.list_matches() == []  # no retry, nothing published


def test_unreadable_too_long_or_wrong_format_footage_fails_in_plain_english(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: pytest.fail("the workflow must not run"))
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a video")
    up1 = queue_upload(store, bad)
    up2 = queue_upload(store, tiny_video(tmp_path / "hd.mp4", size=(1280, 720)))
    up3 = queue_upload(store, tiny_video(tmp_path / "long.mp4", seconds=2.0))
    monkeypatch.setattr(worker, "MAX_FOOTAGE_S", 1.0)
    for _ in range(3):
        worker.handle_one(store)
    r1, r2, r3 = (store.get_record(u) for u in (up1, up2, up3))
    assert r1.status == "failed" and r1.error.startswith("The video could not be read")
    assert r2.status == "failed" and "640x360" in r2.error and "1280x720" in r2.error
    assert r3.status == "failed" and "up to 5 minutes" in r3.error
    assert next(s for s in r1.stages if s["role"] == "download")["status"] == "failed"


def test_a_player_not_in_the_club_or_no_models_fail(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents())
    up = queue_upload(store, tiny_video(tmp_path / "v.mp4"), global_id="pl_cal_09")  # Calder's 9, uploading as Brookfield
    worker.handle_one(store)
    assert "plays for the other team" in store.get_record(up).error

    empty = LocalStore(tmp_path / "empty")
    worker._PULLED.clear()
    up = queue_upload(empty, tiny_video(tmp_path / "v2.mp4"))
    worker.handle_one(empty)
    assert "models are not in storage" in empty.get_record(up).error


def test_a_message_for_an_upload_already_running_is_not_run_again(store, tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: pytest.fail("must not run twice"))
    up = queue_upload(store, tiny_video(tmp_path / "v.mp4"))
    store.update(up, status="running")
    worker.handle_one(store)
    rec = store.get_record(up)
    assert rec.status == "failed" and "earlier attempt" in rec.error
    done = queue_upload(store, tiny_video(tmp_path / "v2.mp4"))
    store.update(done, status="done")
    worker.handle_one(store)
    assert store.get_record(done).status == "done" and store.receive() is None


def test_once_with_an_empty_queue_exits_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("REGISTA_PLAYER_DIR", str(tmp_path / "p"))
    assert worker.main(["--once"]) == 0
    assert "queue empty" in capsys.readouterr().out


def test_once_takes_one_message_and_leaves_the_rest(store, tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTA_PLAYER_DIR", str(store.root))
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents())
    first = queue_upload(store, tiny_video(tmp_path / "a.mp4"))
    second = queue_upload(store, tiny_video(tmp_path / "b.mp4"))
    assert worker.main(["--once"]) == 0
    assert store.get_record(first).status == "done" and store.get_record(second).status == "queued"


def test_models_push_and_pull(tmp_path):
    s = LocalStore(tmp_path / "s")
    src = tmp_path / "m"
    src.mkdir()
    (src / "shot_model.joblib").write_bytes(b"x")
    with pytest.raises(ValueError, match="missing"):
        push(s, src)
    for f in ("kit_number_reader.joblib", "identity_config.json", "event_spotter.joblib"):
        (src / f).write_bytes(b"y")
    assert push(s, src) == 4
    assert pull(s, tmp_path / "back") == 4 and (tmp_path / "back" / "identity_config.json").read_bytes() == b"y"
    assert pull(LocalStore(tmp_path / "none"), tmp_path / "nothing") == 0


# ---------------------------------------------------------------------------- the real vision workflow

REAL_MODELS = Path(os.environ.get("REGISTA_TEST_MODELS", "models/vision"))


@pytest.mark.skipif(not (REAL_MODELS / "shot_model.joblib").exists(), reason=f"no trained vision models in {REAL_MODELS}")
def test_the_real_vision_workflow_on_ten_seconds_of_footage(tmp_path):
    pytest.importorskip("cv2")
    pytest.importorskip("sklearn")
    from regista.player.film import film

    s = LocalStore(tmp_path / "store")
    push(s, REAL_MODELS)
    worker._PULLED.clear()
    f = film(CLUB, OPPONENT, "home", seed=4101, minutes=10 / 60, out=tmp_path / "film")
    up = queue_upload(s, Path(f["video"]))
    worker.handle_one(s, work_root=tmp_path)
    rec = s.get_record(up)
    assert rec.status in ("done", "needs_review"), rec.error
    assert all(st["status"] == "ok" for st in rec.stages), rec.stages
    d = tmp_path / "m"
    s.get_match(rec.match_id, d)
    assert not any(validate_match_dir(d).values())
    assert json.loads((d / "manifest.json").read_text())["identity"]["named_tracks"] > 0


def test_a_new_work_folder_is_made_not_a_failure(store, tmp_path, monkeypatch):
    """The verify round: ``--work`` naming a folder that does not exist yet failed every upload (FileNotFoundError from
    the temporary directory); the worker now makes it."""
    monkeypatch.setenv("REGISTA_PLAYER_DIR", str(store.root))
    monkeypatch.setattr(worker, "vision_agents_for", lambda models_dir: stand_in_agents())
    up = queue_upload(store, tiny_video(tmp_path / "a.mp4"))
    work = tmp_path / "new" / "work"
    assert worker.main(["--once", "--work", str(work)]) == 0
    assert work.is_dir() and store.get_record(up).status == "done"
