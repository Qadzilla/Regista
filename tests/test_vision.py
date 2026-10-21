"""The private vision layer on Regista's own rendered broadcast: every stage, trained and scored here on footage
the test renders itself (two short matches in tmp_path), so nothing outside the repo is needed.

The accuracy floors are the numbers measured on these exact clips minus a margin; the full-size numbers on six
held-out matches are in docs/vision.md."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
pytest.importorskip("sklearn")
pytest.importorskip("scipy")
pytest.importorskip("joblib")

from regista.schema import events_validator, iter_jsonl, validate_match_dir  # noqa: E402
from regista.vision.dataset import MatchSpec, make_match  # noqa: E402
from regista.vision.frames import iter_frames, probe  # noqa: E402
from regista.vision.truth import Truth, load_match_header  # noqa: E402

SIZE = (640, 360)
FPS = 5.0
TRAIN = MatchSpec(355, "Pinehurst,PIN,#0F766E,#FFFFFF,#F472B6", "Calder,CAL,#C2410C,#FFFFFF,#38BDF8", minutes=0.6)
TRAIN2 = MatchSpec(369, TRAIN.home, TRAIN.away, minutes=0.6)  # adds a touchline-camera replay to the shot classifier's diet
# Same clubs, different match: two short clips are too little to teach unseen kit colours and camera angles
# (the full evaluation in docs/vision.md trains on ten matches and tests on six with clubs it never saw).
TEST = MatchSpec(359, TRAIN.home, TRAIN.away, minutes=0.6)


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    root = tmp_path_factory.mktemp("vision")
    train = make_match(TRAIN, root, size=SIZE, fps=FPS, workers=1)
    train2 = make_match(TRAIN2, root, size=SIZE, fps=FPS, workers=1)
    test = make_match(TEST, root, size=SIZE, fps=FPS, workers=1)
    return {"root": root, "train": train, "train2": train2, "test": test}


def _segments(item):
    truth = Truth(item["match_dir"], *SIZE)
    return truth, truth.segments(probe(item["video"]).duration_s)


@pytest.fixture(scope="module")
def models(clips):
    from regista.vision.evaluate import train_reader
    from regista.vision.shots import train_shot_model

    shot = train_shot_model([(clips[k]["video"], _segments(clips[k])[1]) for k in ("train", "train2")], sample_fps=FPS, max_iter=40)
    reader = train_reader([clips["train"]], n_synth=1000, sample_fps=2.5, max_iter=30, hidden=(128,))
    d = clips["root"] / "models"
    shot.save(d)
    reader.save(d)
    from regista.vision.events import EventSpotter, generated_example_set

    spotter = EventSpotter().fit(*generated_example_set([401, 402, 403, 404], minutes=3.0))  # positions only: no rendering
    spotter.save(d)
    return {"dir": d, "shot": shot, "reader": reader, "events": spotter}


@pytest.fixture(scope="module")
def vision_run(clips, models):
    from regista.vision.agents import run_vision_workflow

    out = clips["root"] / "vis_test"
    run = run_vision_workflow({"video_path": clips["test"]["video"], "roster": load_match_header(clips["test"]["match_dir"]),
                               "out_dir": str(out)}, config={"models_dir": str(models["dir"])}, state_dir=out / "agents")
    return {"run": run, "out": out}


# ---------------------------------------------------------------------------- frames and ground truth

def test_frames_iterator_samples_and_downscales(clips):
    info = probe(clips["test"]["video"])
    assert info.fps == FPS and (info.width, info.height) == SIZE
    frames = list(iter_frames(clips["test"]["video"], sample_fps=2.0, size=(128, 72), end_s=5.0))
    # ffmpeg samples by timestamp, so a rate that does not divide the source rate is still evenly spaced; each frame
    # is the source frame nearest its time.
    assert [round(t, 2) for _i, t, _f in frames] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
    i, t, f = frames[3]
    assert f.shape == (72, 128, 3) and f.dtype == np.uint8 and abs(t - i / FPS) <= 0.5 / FPS + 1e-9
    # A rate that divides evenly keeps exactly every k-th source frame, pixel for pixel.
    every = {i: f for i, _t, f in iter_frames(clips["test"]["video"], size=(128, 72), end_s=4.0)}
    halves = list(iter_frames(clips["test"]["video"], sample_fps=FPS / 2, size=(128, 72), end_s=4.0))
    assert [i for i, _t, _f in halves] == list(range(0, len(every), 2))
    assert all(np.array_equal(f, every[i]) for i, _t, f in halves)
    # Seeking starts at the asked time without decoding what comes before.
    window = list(iter_frames(clips["test"]["video"], sample_fps=FPS, start_s=2.0, end_s=3.0))
    assert [round(t, 2) for _i, t, _f in window] == [round(2.0 + k / FPS, 2) for k in range(int(FPS))]


def test_ground_truth_discs_sit_on_kit_coloured_pixels(clips):
    from regista.vision.detect import hex_rgb

    truth, _ = _segments(clips["test"])
    for _i, t, rgb in iter_frames(clips["test"]["video"], start_s=2.0, end_s=2.3):
        ft = truth.objects_at(t)
        assert ft.kind == "main" and len(ft.players) >= 10 and ft.ball is not None
        for g in ft.players:
            if g.occluded > 0.1 or g.holder or not (g.r < g.cx < SIZE[0] - g.r):
                continue
            team = truth.teams[g.team_id]["kit"]
            want = np.array(hex_rgb(team["gk"] if g.is_gk else team["primary"]), dtype=float)
            ring = rgb[int(g.cy) - int(g.r * 0.7): int(g.cy) + int(g.r * 0.7), int(g.cx) - int(g.r * 0.7): int(g.cx) + int(g.r * 0.7)]
            assert np.min(np.linalg.norm(ring.reshape(-1, 3) - want, axis=1)) < 40


# ---------------------------------------------------------------------------- shot agent

def test_shot_agent_segments_validate_and_match_truth(clips, models):
    from regista.vision.shots import ShotModel, evaluate_shot_model, segments_to_records

    model = ShotModel.load(models["dir"])
    truth, segs = _segments(clips["test"])
    pred = model.predict(clips["test"]["video"])
    assert pred[0]["t"] == 0.0 and abs(pred[-1]["t_end"] - probe(clips["test"]["video"]).duration_s) < 1e-6
    assert all(a["t_end"] == b["t"] for a, b in zip(pred, pred[1:]))
    v = events_validator()
    for rec in segments_to_records(pred, "vis_test"):
        assert v.errors(rec) == [], rec
    rep = evaluate_shot_model(model, [(clips["test"]["video"], segs)])
    assert rep["accuracy"] >= 0.95, rep
    assert rep["per_class"]["main"]["accuracy"] >= 0.97
    assert rep["boundaries"]["f1"] >= 0.6, rep["boundaries"]


# ---------------------------------------------------------------------------- calibration, detection, identity

def test_main_camera_calibration_recovers_the_pan(clips):
    from regista.vision.pitch import HomographyMapping, MainCameraCalibrator

    truth, _ = _segments(clips["test"])
    cal = MainCameraCalibrator(*SIZE)
    errs = []
    for _i, t, rgb in iter_frames(clips["test"]["video"], sample_fps=1.0, end_s=20.0):
        ft = truth.objects_at(t)
        if ft.kind == "main":
            errs.append(abs(cal.estimate(rgb).cx - ft.cam_cx))
    assert errs and max(errs) < 0.5 and np.mean(errs) < 0.2
    # The real-footage mapping type honours the same interface.
    H = np.array([[10.0, 0.5, 20.0], [0.2, 4.0, 40.0], [0.0, 0.001, 1.0]])
    m = HomographyMapping(H)
    u, v = m.pitch_to_image(30.0, 20.0)
    assert np.allclose(m.image_to_pitch(u, v), (30.0, 20.0), atol=1e-6)


def test_identity_detects_reads_and_names_players(clips, vision_run):
    import joblib

    from regista.vision.evaluate import evaluate_identity

    run = vision_run["run"]
    assert run.ok, (run.failed_role, run.dead_letters)
    truth, _ = _segments(clips["test"])
    res = joblib.load(run.state["identity_path"])
    r = evaluate_identity(res, truth)
    assert r["detection_precision"] >= 0.93, r
    assert r["detection_recall"] >= 0.97, r
    assert r["team_accuracy"] >= 0.99, r
    assert r["identity_accuracy"] >= 0.95, r
    assert r["named_fraction"] >= 0.9, r  # most tracked players must carry a name, not just the few that were read
    assert r["position_error_m_mean"] < 0.4, r
    assert r["ball_recall"] >= 0.9 and r["ball_precision"] >= 0.9, r


def test_kit_number_reader_reads_held_out_crops(clips, models):
    from regista.vision.evaluate import collect_number_crops
    from regista.vision.kitnumber import AzureVisionOCRReader, decode

    crops, nums, _kinds = collect_number_crops(clips["test"], sample_fps=1.0, kinds=("main",))
    assert len(nums) > 100
    pred = np.array([decode(rd, list(range(1, 24)))[0] for rd in models["reader"].read(crops)])
    assert (pred == nums).mean() >= 0.95
    with pytest.raises(NotImplementedError):
        AzureVisionOCRReader().read(crops[:1])


def test_possession_agent_finds_who_is_on_the_ball(clips, vision_run):
    import joblib

    from regista.vision.possession import evaluate_possessions, infer_possessions

    truth, segs = _segments(clips["test"])
    res = joblib.load(vision_run["run"].state["identity_path"])
    main = [s for s in segs if s["kind"] == "main"]
    pred = infer_possessions(res.frames, truth.match, "vis_test")
    r = evaluate_possessions(pred, truth.possessions(), main, [f["t"] for f in res.frames])
    assert r["frame_accuracy"] >= 0.6, r
    assert r["player_id_accuracy"] >= 0.85, r
    assert r["window_recall_iou50"] >= 0.4, r
    v = events_validator()
    assert pred and all(v.errors(p) == [] for p in pred)


# ---------------------------------------------------------------------------- end to end

def test_vision_workflow_writes_a_valid_match_the_intelligence_layer_can_use(clips, vision_run):
    from regista.agents import Orchestrator, default_agents
    from regista.vision.pipeline import compare_clips

    run, out = vision_run["run"], vision_run["out"]
    assert [r["agent"] for r in run.trace if r["status"] == "ok"] == ["shots", "identity", "identity_review", "possession_vision",
                                                                      "events_vision", "vision_writer"]
    assert next(r for r in run.trace if r["agent"] == "identity_review")["note"] == "review off"
    assert run.state["match_dir"] == str(out)
    assert all(not v for v in validate_match_dir(out).values())
    stream = list(iter_jsonl(out / "events.jsonl"))
    assert stream[0]["type"] == "match" and stream[0]["source"] == "vision"
    kinds = {r["type"] for r in stream}
    assert {"camera_segment", "possession", "appearance", "event"} <= kinds
    assert {"pass", "carry"} <= {r["event_type"] for r in stream if r["type"] == "event"}
    assert all(r["source"] == "vision" for r in stream)
    assert (out / "tracks.jsonl").stat().st_size > 0
    assert json.loads((out / "manifest.json").read_text())["validation"] == {"events.jsonl": 0, "tracks.jsonl": 0}
    # The intelligence layer runs on the vision output unchanged.
    ref = Orchestrator(default_agents(), out / "agents_intel").run({"match_dir": str(out), "player_ids": ["t_home_09"], "queries": ["goal"]})
    assert ref.ok, ref.dead_letters
    truth_stream = list(iter_jsonl(clips["test"]["match_dir"] + "/events.jsonl"))
    cmp = compare_clips(stream, truth_stream, "t_home_09")
    assert cmp["true_clips"] > 0 and cmp["true_seconds_covered"] >= 0.5, cmp
    assert cmp["vision_seconds_inside_true"] >= 0.85, cmp  # what vision cuts must mostly be real moments


def test_vision_records_stay_inside_their_shot(vision_run):
    stream = list(iter_jsonl(vision_run["out"] / "events.jsonl"))
    seg = {r["id"]: r for r in stream if r["type"] == "camera_segment"}
    for r in stream:
        if r["type"] == "appearance":
            assert seg[r["segment_id"]]["t"] - 1e-6 <= r["t"] < r["t_end"] <= seg[r["segment_id"]]["t_end"] + 1e-6, r
        elif r["type"] == "possession":
            assert any(s["t"] - 1e-6 <= r["t"] and r["t_end"] <= s["t_end"] + 1e-6 for s in seg.values()), r


def test_vision_workflow_dead_letters_without_retrying_deterministic_failures(tmp_path, clips):
    from regista.vision.agents import run_vision_workflow

    roster = load_match_header(clips["test"]["match_dir"])
    # A missing video: the first role refuses, nothing downstream runs.
    run = run_vision_workflow({"video_path": str(tmp_path / "nope.mp4"), "roster": roster, "out_dir": str(tmp_path / "a")},
                              config={"models_dir": str(tmp_path / "no_models")})
    assert not run.ok and run.failed_role == "shots"
    assert [r["attempt"] for r in run.trace if r["agent"] == "shots"] == [1]
    assert len(run.dead_letters) == 1
    # Missing models behind known shot boundaries: identity fails on its first attempt and is not retried.
    segs = [{"id": "cs_1", "t": 0.0, "t_end": 5.0, "kind": "main"}]
    run = run_vision_workflow({"video_path": clips["test"]["video"], "roster": roster, "out_dir": str(tmp_path / "b")},
                              config={"models_dir": str(tmp_path / "no_models"), "segments": segs}, max_retries=2)
    assert not run.ok and run.failed_role == "identity", run.dead_letters
    assert [(r["attempt"], r["status"]) for r in run.trace if r["agent"] == "identity"] == [(1, "failed")]
    assert not (tmp_path / "b" / "events.jsonl").exists()


def test_vision_roles_declare_their_contract():
    from regista.agents.base import Agent
    from regista.vision.agents import VISION_ROLE_ORDER, build_vision_workflow, vision_agents

    agents = vision_agents({"models_dir": "unused"})
    assert [a.role for a in agents] == VISION_ROLE_ORDER == ["shots", "identity", "possession_vision", "events_vision", "vision_writer"]
    assert all(isinstance(a, Agent) and a.inputs and a.outputs for a in agents)
    assert agents[0].inputs == ("video_path",) and "roster" in agents[1].inputs
    workflow, keys = build_vision_workflow(agents)
    assert {"video_path", "roster", "camera_segments", "possessions", "vision_events", "match_dir"} <= set(keys)


def test_vision_cli_commands_reach_their_work(monkeypatch, tmp_path):
    """Every subcommand gets past argument handling (a function-local import once made `data` crash at once)."""
    from regista.vision import __main__ as cli

    seen = []
    monkeypatch.setattr(cli, "make_match", lambda spec, root, workers=None: seen.append(spec.match_id) or {"video": "v.mp4"})
    assert cli.main(["data", "--root", str(tmp_path)]) == 0
    assert seen[0] == "syn_0101" and "syn_0201" in seen
    import regista.vision.evaluate as ev

    calls = []
    monkeypatch.setattr(ev, "evaluate_all", lambda root, models, test_specs=None, e2e_seed=None: calls.append([s.seed for s in test_specs]) or {})
    assert cli.main(["evaluate", "--set", "fresh", "--root", str(tmp_path)]) == 0
    assert cli.main(["evaluate", "--root", str(tmp_path)]) == 0
    assert calls == [[301, 302, 303], [201, 202, 203, 204, 205, 206]]



def test_identity_review_pauses_the_workflow_asks_and_applies_answers(clips, models, tmp_path):
    """With review on, the workflow stops after identity with questions and crops, a reviewer answers, and the run
    resumes with the answers applied and recorded."""
    from regista.vision.agents import IdentityAnswers, run_vision_workflow
    from regista.vision.review import simulated_answers

    truth, _segs = _segments(clips["test"])
    roster = load_match_header(clips["test"]["match_dir"])
    asked = []

    def reviewer(request):
        import joblib

        asked.append(request)
        assert request.items and all((Path(request.review_dir) / "crops" / it["image"]).exists() for it in request.items)
        result = joblib.load(out / ".vision_work" / "identity.joblib")
        return IdentityAnswers(answers=simulated_answers(request.items, result, truth, roster), annotator="test reviewer")

    out = tmp_path / "reviewed"
    run = run_vision_workflow({"video_path": clips["test"]["video"], "roster": roster, "out_dir": str(out), "review": True},
                              config={"models_dir": str(models["dir"]), "review_questions": 4, "feedback_dir": str(tmp_path / "fb"),
                                      "review_min_doubt": 0.0},  # a tiny clip may have nothing uncertain; ask anyway
                              reviewer=reviewer)
    assert run.ok, (run.failed_role, run.dead_letters)
    assert len(asked) == 1 and 1 <= len(asked[0].items) <= 4
    statuses = [(r["agent"], r["status"]) for r in run.trace if r["agent"] == "identity_review"]
    assert statuses == [("identity_review", "waiting"), ("identity_review", "ok")]
    assert run.state["identity_review"]["answers"] == len(asked[0].items)
    recs = [json.loads(line) for line in (out / "review" / "identity_answers.jsonl").read_text().splitlines()]
    assert len(recs) == len(asked[0].items) and all(r["annotator"] == "test reviewer" and r["source"] == "human" for r in recs)
    assert (tmp_path / "fb" / "identity_annotations.jsonl").exists()
    assert all(not v for v in validate_match_dir(out).values())


def test_identity_review_rejects_bad_answers_without_applying_any(clips, models, tmp_path):
    from regista.vision.agents import IdentityAnswers, run_vision_workflow

    roster = load_match_header(clips["test"]["match_dir"])
    out = tmp_path / "bad"
    run = run_vision_workflow({"video_path": clips["test"]["video"], "roster": roster, "out_dir": str(out), "review": True},
                              config={"models_dir": str(models["dir"]), "review_questions": 3, "feedback_dir": str(tmp_path / "fb"),
                                      "review_min_doubt": 0.0},
                              reviewer=lambda req: IdentityAnswers(answers=[{"item_id": it["item_id"], "player_id": "nobody", "players": ["nobody"]}
                                                                             for it in req.items]))
    assert not run.ok and run.failed_role == "identity_review"
    assert "team sheet" in run.dead_letters[0]["error"] or "team-sheet" in run.dead_letters[0]["error"]
    assert not (out / "review" / "identity_answers.jsonl").exists() and not (tmp_path / "fb").exists()


def test_identity_review_through_the_api(clips, models, tmp_path, monkeypatch):
    """A vision match keeps its questions; answering them over HTTP corrects identity and recomputes the match."""
    from fastapi.testclient import TestClient

    from regista import api
    from regista.vision.pipeline import run_vision
    from regista.vision.review import simulated_answers

    roster = load_match_header(clips["test"]["match_dir"])
    out = tmp_path / "data" / "vis_api"
    summary = run_vision(clips["test"]["video"], roster, out, models_dir=models["dir"], match_id="vis_api")
    assert isinstance(summary["review_questions"], int)
    # A tiny clip may have nothing uncertain; prepare questions about confident calls too, so the flow is exercised.
    import shutil

    import joblib

    from regista.vision.review import prepare_review

    shutil.rmtree(out / "review", ignore_errors=True)
    assert prepare_review(out, clips["test"]["video"], joblib.load(out / ".vision_work" / "identity.joblib"), roster, min_doubt=0.0)
    monkeypatch.setattr(api, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setattr(api, "MODELS_DIR", models["dir"])
    monkeypatch.setenv("REGISTA_FEEDBACK_DIR", str(tmp_path / "fb"))
    c = TestClient(api.app)
    got = c.get("/api/matches/vis_api/identity-review").json()
    assert got["items"] and set(got["teams"]) == {t["team_id"] for t in roster["teams"]}
    first = got["items"][0]
    img = c.get(first["image_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert c.get("/api/matches/vis_api/identity-review/crops/..%2Fmanifest.json").status_code in (400, 404)

    before = (out / "events.jsonl").read_text()
    bad = {"answers": [{"item_id": first["item_id"], "player_id": "nobody", "players": ["nobody"]}]}
    assert c.post("/api/matches/vis_api/identity-review", json=bad).status_code == 422
    assert (out / "events.jsonl").read_text() == before and c.get("/api/matches/vis_api/identity-review").json()["items"]

    truth, _ = _segments(clips["test"])
    answers = simulated_answers(got["items"], joblib.load(out / ".vision_work" / "identity.joblib"), truth, roster)
    r = c.post("/api/matches/vis_api/identity-review", json={"answers": answers, "annotator": "zaid"})
    assert r.status_code == 200, r.text
    assert r.json()["answers"] == len(answers)
    assert all(not v for v in validate_match_dir(out).values())
    assert len((out / "review" / "identity_answers.jsonl").read_text().splitlines()) == len(answers)
    assert (tmp_path / "fb" / "identity_annotations.jsonl").exists()
    assert list((out / "review").glob("identity_review.*.answered.json"))
    # Asked items are never asked again; a repeat answer to the closed questions is refused.
    again = c.get("/api/matches/vis_api/identity-review").json()["items"]
    assert not {it["item_id"] for it in again} & {a["item_id"] for a in answers if "player_id" in a and a["player_id"] != "unknown"}

    # Plan step 6: answered reviews feed the reader. Track corrections give crops; replay answers alone give none.
    from regista.vision.review import learn_from_reviews

    learned = learn_from_reviews([out], models["dir"], save=False)
    if learned["fine_tuned"]:
        assert learned["crops"] > 0 and learned["matches"][0]["match"] == "vis_api"
    else:
        assert learned["reason"] == "no answered track corrections with usable crops"
