"""The Studio's backend: overview, runs, data, usage, cache, local vision jobs, and the status CLI.

Every test runs on a temporary data folder (a copy of the sample match), never on Azure: Cosmos DB and Search are fakes,
and jobs run a harmless script in place of ``python3 -m regista.vision``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api, studio_api
from regista.feedback import WatchabilityModel, save_annotations
from regista.studio import __main__ as cli
from regista.studio import facts
from regista.studio import jobs as jobs_mod
from regista.studio import progress
from regista.studio.jobs import JobError, JobRunner, build_argv

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample" / "syn_0294"
ADMIN, VIEW = "admin-key-for-tests", "view-key-for-tests"
STUDIO_GETS = ["/api/studio/overview", "/api/studio/runs", "/api/studio/runs/syn_0294", "/api/studio/data", "/api/studio/usage",
               "/api/studio/cache", "/api/studio/jobs"]


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    """A Studio over a temporary copy of the sample match, with both keys configured, no cloud and no vision models."""
    data, cache, models = tmp_path / "data", tmp_path / "cache", tmp_path / "models"
    data.mkdir()
    shutil.copytree(SAMPLE, data / "syn_0294", ignore=shutil.ignore_patterns("agents"))
    monkeypatch.setattr(api, "DATA_ROOT", data)
    monkeypatch.setattr(api, "CACHE_ROOT", cache)
    monkeypatch.setattr(api, "MODELS_DIR", models)
    monkeypatch.setattr(api, "_library", lambda: {})
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(3, 20, 60, 300, 2))
    monkeypatch.setattr(facts, "_data_cache", {"t": None, "value": None})
    monkeypatch.setattr(studio_api, "JOBS", JobRunner(tmp_path / "jobs"))
    monkeypatch.setenv("REGISTA_ADMIN_TOKEN", ADMIN)
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", VIEW)
    for var in ("IMAGE_TAG", "CONTAINER_APP_REVISION", "REGISTA_PRERENDER"):
        monkeypatch.delenv(var, raising=False)
    with TestClient(api.app) as c:
        c.root = tmp_path
        c.match = data / "syn_0294"
        yield c


def _get(c, path, key=VIEW):
    r = c.get(path, headers={"X-Regista-Token": key} if key else {})
    assert r.status_code == 200, (path, r.status_code, r.text)
    return r.json()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _row(agent, status, attempt=1, ms=10.0, error=None):
    return {"at": "2026-10-21T10:00:00Z", "agent": agent, "attempt": attempt, "status": status, "elapsed_ms": ms, "records_in": None,
            "records_out": None, "error": error, "state_keys": []}


# ---------------------------------------------------------------------------- access

@pytest.mark.parametrize("path", STUDIO_GETS)
def test_every_studio_read_needs_a_studio_key(studio, path):
    assert studio.get(path).status_code == 401
    assert studio.get(path, headers={"X-Regista-Token": "wrong"}).status_code == 401
    _get(studio, path, VIEW)
    _get(studio, path, ADMIN)


# ---------------------------------------------------------------------------- overview

def test_overview_has_every_section(studio, monkeypatch):
    monkeypatch.setenv("CONTAINER_APP_REVISION", "regista-api--abc123")
    monkeypatch.setenv("IMAGE_TAG", "f01d587")
    o = _get(studio, "/api/studio/overview")
    assert set(o) == {"generated_at", "role", "capabilities", "health", "todo", "usage", "data", "cache"}
    assert o["role"] == "view" and o["capabilities"]["jobs"] is False
    assert o["health"]["revision"] == "regista-api--abc123" and o["health"]["image"] == "f01d587" and o["health"]["ok"] is True
    assert {"foundry", "cosmos", "search"} <= set(o["health"]["cloud"]) and "azure_mcp" in o["health"] and "tracing" in o["health"]
    assert o["data"]["cosmos"] == {"configured": False} and o["data"]["search"] == {"configured": False}
    assert o["usage"]["limits"]["total_per_day"] == 300 and o["cache"]["files"] == 0
    for t in o["todo"]:
        assert set(t) == {"kind", "match_id", "count", "detail", "link", "api"}


def test_overview_without_images_or_revision_says_null(studio):
    h = _get(studio, "/api/studio/overview")["health"]
    assert h["image"] is None and h["revision"] is None


def test_todo_lists_what_waits_on_zaid_most_urgent_first(studio):
    m = studio.match
    _write_jsonl(m / "agents" / "trace.jsonl", [_row("ingest", "ok"), _row("label", "retry", 1, error="Timeout"),
                                               _row("label", "failed", 2, error="AgentError: Foundry down")])
    _write_jsonl(m / "agents" / "dead_letter.jsonl", [{"at": "2026-10-21T10:00:01Z", "agent": "label", "attempts": 2, "error": "AgentError: Foundry down"}])
    (m / "agents" / "pending_review.json").write_text(json.dumps([{"request_id": "r1", "checkpoint_id": "c1",
                                                                   "request": {"question": "?", "items": [{"clip_id": "a"}, {"clip_id": "b"}]}}]))
    (m / "review").mkdir()
    (m / "review" / "identity_review.json").write_text(json.dumps({"items": [{"item_id": "tr_1"}, {"item_id": "tr_2"}, {"item_id": "cw_3"}]}))
    todo = _get(studio, "/api/studio/overview")["todo"]
    kinds = [t["kind"] for t in todo]
    assert kinds[:3] == ["failed_run", "workflow_review", "whos_who"]
    failed, review, whos = todo[:3]
    assert failed["match_id"] == "syn_0294" and "label failed: AgentError: Foundry down" in failed["detail"]
    assert failed["link"] == "/studio#runs/syn_0294" and failed["api"] == "/api/studio/runs/syn_0294"
    assert review["count"] == 2 and review["api"] == "/api/matches/syn_0294/review"
    assert whos["count"] == 3 and whos["api"] == "/api/matches/syn_0294/identity-review"


def test_unsure_clips_count_only_flagged_clips_without_a_verdict(studio):
    flagged = [c for c in studio.get(f"/api/matches/syn_0294/clips", headers={"X-Regista-Token": VIEW}).json() if c["review"]]
    before = [t for t in _get(studio, "/api/studio/overview")["todo"] if t["kind"] == "unsure_clips"]
    assert before and before[0]["count"] == len(flagged) > 0
    r = studio.post(f"/api/matches/syn_0294/clips/{flagged[0]['id']}/verdict", json={"verdict": "keep"}, headers={"X-Regista-Token": ADMIN})
    assert r.status_code == 200, r.text
    after = [t for t in _get(studio, "/api/studio/overview")["todo"] if t["kind"] == "unsure_clips"]
    assert (after[0]["count"] if after else 0) == len(flagged) - 1


def _annotation(i: int, at: str) -> dict:
    return {"type": "annotation", "id": f"an_{i}", "target_type": "label", "target_id": f"lb_{i}", "match_id": "other", "source": "human",
            "verdict": "accept", "annotator": "zaid", "annotated_at": at, "correction": {"keep": True},
            "context": {"clip_id": f"cl_x_{i:06d}", "player_id": "x", "tags": ["shot"], "reason": "on_ball_main", "duration_s": 5.0,
                        "prior_watchability": 0.5}}


def test_a_model_is_stale_when_verdicts_came_after_it(studio):
    save_annotations([_annotation(1, "2026-10-21T09:00:00Z"), _annotation(2, "2026-10-21T11:00:00Z")])
    assert not [t for t in facts.model_todo()]  # two verdicts, no model, fewer than the minimum to train: nothing to do
    WatchabilityModel(feature_names=["x"], coef=[0.1], n_samples=8, trained_at="2026-10-21T10:00:00Z", version=3).save()
    (stale,) = facts.model_todo()
    assert stale["kind"] == "stale_model" and stale["count"] == 1 and stale["match_id"] is None and "learned-v3" in stale["detail"]
    WatchabilityModel(feature_names=["x"], coef=[0.1], n_samples=8, trained_at="2026-10-21T12:00:00Z", version=4).save()
    assert facts.model_todo() == []


def test_never_trained_with_enough_verdicts_is_on_the_list(studio):
    save_annotations([_annotation(i, f"2026-10-21T09:{i:02d}:00Z") for i in range(8)])
    (t,) = facts.model_todo()
    assert t["kind"] == "stale_model" and t["count"] == 8 and "no model trained yet" in t["detail"]


# ---------------------------------------------------------------------------- runs

def test_a_match_with_no_run_is_empty_not_an_error(studio):
    run = _get(studio, "/api/studio/runs/syn_0294")
    assert run["has_run"] is False and run["status"] == "none" and run["rows"] == [] and run["agents"] == [] and run["source"] == "local"
    assert run["label_models"] == {"rules-v0": 11}
    assert _get(studio, "/api/studio/runs")[0]["status"] == "none"


def test_vision_matches_say_whether_who_s_who_can_be_answered_here(studio):
    """The Studio shows Who's who read-only up front when the identity result an answer rewrites is not on this server."""
    run = _get(studio, "/api/studio/runs/syn_0294")
    assert run["kind"] == "intelligence" and run["identity_result"] is None and run["clips"] == 11
    (studio.match / "review").mkdir()
    assert _get(studio, "/api/studio/runs/syn_0294")["identity_result"] is False  # a copy without it, like the live app
    (studio.match / ".vision_work").mkdir()
    (studio.match / ".vision_work" / "identity.joblib").write_bytes(b"")
    assert _get(studio, "/api/studio/runs")[0]["identity_result"] is True


def test_todo_words_are_singular_or_plural(studio):
    clip = next(json.loads(line) for line in (studio.match / "clips.jsonl").read_text().splitlines() if '"type":"clip"' in line)
    (studio.match / "review").mkdir()
    (studio.match / "review" / "identity_review.json").write_text(json.dumps({"items": [{"item_id": "tr_1"}]}))
    whos = next(t for t in _get(studio, "/api/studio/overview")["todo"] if t["kind"] == "whos_who")
    assert whos["detail"] == "1 identity call the vision layer is unsure of"
    assert all("(s)" not in t["detail"] for t in _get(studio, "/api/studio/overview")["todo"]), clip["id"]


def test_run_detail_summarises_each_agent_and_keeps_every_row(studio):
    m = studio.match
    _write_jsonl(m / "agents" / "trace.jsonl", [_row("ingest", "ok", ms=5), _row("label", "retry", 1, ms=100, error="Timeout"),
                                               _row("label", "ok", 2, ms=50), {"not": "a trace row"}])
    (m / "agents" / "trace.jsonl").write_text((m / "agents" / "trace.jsonl").read_text() + "{broken json\n")
    run = _get(studio, "/api/studio/runs/syn_0294")
    assert run["status"] == "ok" and run["has_run"] and run["finished_at"] == "2026-10-21T10:00:00Z"
    label = next(a for a in run["agents"] if a["agent"] == "label")
    assert label == {"agent": "label", "status": "ok", "attempts": 2, "elapsed_ms": 150.0, "error": "Timeout"}
    assert [r["status"] for r in run["rows"] if r["agent"] == "label"] == ["retry", "ok"]
    listed = _get(studio, "/api/studio/runs")[0]
    assert listed["status"] == "ok" and "rows" not in listed


def test_paused_and_failed_runs(studio):
    m = studio.match
    _write_jsonl(m / "agents" / "trace.jsonl", [_row("label", "ok"), {**_row("review", "waiting"), "note": "asked a human about 2 clip(s)"}])
    (m / "agents" / "pending_review.json").write_text(json.dumps([{"request_id": "r1", "request": {"items": [{"clip_id": "a"}]}}]))
    run = _get(studio, "/api/studio/runs/syn_0294")
    assert run["status"] == "paused" and run["review"]["pending_requests"] == 1 and run["review"]["pending_items"] == 1
    assert next(a for a in run["agents"] if a["agent"] == "review")["note"] == "asked a human about 2 clip(s)"
    (m / "agents" / "pending_review.json").unlink()
    _write_jsonl(m / "agents" / "dead_letter.jsonl", [{"agent": "persist", "error": "CosmosHttpResponseError", "attempts": 3, "at": "t"}])
    run = _get(studio, "/api/studio/runs/syn_0294")
    assert run["status"] == "failed" and run["dead_letters"] == [{"agent": "persist", "error": "CosmosHttpResponseError", "attempts": 3, "at": "t"}]


def test_cosmos_only_matches_are_listed_without_a_run_and_unknown_ones_404(studio, monkeypatch):
    monkeypatch.setattr(api, "_library", lambda: {"syn_0141": {"match_id": "syn_0141"}})
    run = _get(studio, "/api/studio/runs/syn_0141")
    assert run["source"] == "cosmos" and run["status"] == "none" and run["rows"] == []
    assert [r["match_id"] for r in _get(studio, "/api/studio/runs")] == ["syn_0294", "syn_0141"]
    assert studio.get("/api/studio/runs/nope", headers={"X-Regista-Token": VIEW}).status_code == 404
    assert studio.get("/api/studio/runs/..", headers={"X-Regista-Token": VIEW}).status_code in (400, 404)


# ---------------------------------------------------------------------------- data

class _CountContainer:
    def __init__(self, n, fail=False):
        self.n, self.fail, self.queries = n, fail, []

    def query_items(self, query, parameters=None, enable_cross_partition_query=False, partition_key=None):
        self.queries.append(query)
        assert query == "SELECT VALUE COUNT(1) FROM c" and enable_cross_partition_query  # read-only, nothing else
        if self.fail:
            raise RuntimeError("forbidden")
        return iter([self.n])


class _Store:
    def __init__(self):
        self.matches, self.clips, self.labels, self.annotations = _CountContainer(3), _CountContainer(8), _CountContainer(8), _CountContainer(2)


def test_data_counts_documents_and_caches_them(studio, monkeypatch):
    store = _Store()
    monkeypatch.setenv("REGISTA_COSMOS_ENDPOINT", "https://fake.documents.azure.com:443/")
    monkeypatch.setenv("REGISTA_SEARCH_ENDPOINT", "https://fake.search.windows.net")
    monkeypatch.setattr(api, "_feedback_store", lambda: store)
    calls = []
    monkeypatch.setattr(facts, "_search_count", lambda: calls.append(1) or 8)
    d = _get(studio, "/api/studio/data")
    assert d["cosmos"] == {"configured": True, "database": "regista", "containers": {"matches": 3, "clips": 8, "labels": 8, "annotations": 2}, "error": None}
    assert d["search"] == {"configured": True, "index": "regista-clips", "documents": 8, "error": None}
    _get(studio, "/api/studio/overview")
    assert len(store.clips.queries) == 1 and calls == [1]  # cached for a minute


def test_data_reports_failures_as_strings(studio, monkeypatch):
    store = _Store()
    store.annotations = _CountContainer(0, fail=True)
    monkeypatch.setenv("REGISTA_COSMOS_ENDPOINT", "https://fake.documents.azure.com:443/")
    monkeypatch.setenv("REGISTA_SEARCH_ENDPOINT", "https://fake.search.windows.net")
    monkeypatch.setattr(api, "_feedback_store", lambda: store)

    def boom():
        raise PermissionError("no role")

    monkeypatch.setattr(facts, "_search_count", boom)
    d = _get(studio, "/api/studio/data")
    assert d["cosmos"]["containers"]["annotations"] is None and d["cosmos"]["containers"]["clips"] == 8
    assert d["cosmos"]["error"] == "annotations: RuntimeError: forbidden"
    assert d["search"]["documents"] is None and d["search"]["error"] == "PermissionError: no role"


def test_cosmos_configured_but_unreachable(studio, monkeypatch):
    monkeypatch.setenv("REGISTA_COSMOS_ENDPOINT", "https://fake.documents.azure.com:443/")
    monkeypatch.setattr(api, "_feedback_store", lambda: None)
    assert "could not be reached" in _get(studio, "/api/studio/data")["cosmos"]["error"]


# ---------------------------------------------------------------------------- usage and the limiter

def test_usage_counts_questions_against_the_limits(studio):
    lim = api._ask_limiter
    for visitor in ("a", "b"):
        assert lim.acquire(visitor)[0]
        lim.release()
    assert lim.acquire("a")[0]  # still in flight
    u = _get(studio, "/api/studio/usage")
    assert (u["last_minute"], u["last_hour"], u["last_day"], u["visitors_last_hour"], u["in_flight"]) == (3, 3, 3, 2, 1)
    assert u["remaining"] == {"hour": 57, "day": 297} and u["foundry"] is False


def test_the_hourly_visitor_cap_and_the_daily_cap_bind():
    """Each window used to prune the list the next one counted, so the hour and day caps never bound."""
    lim = api.AskLimiter(per_visitor_per_min=100, per_visitor_per_hour=3, total_per_hour=100, total_per_day=5, concurrent=10)
    for t in (0, 1, 2):
        assert lim.acquire("a", now=t)[0]
        lim.release()
    ok, wait, which = lim.acquire("a", now=61)
    assert not ok and which == "3 per 3600s per visitor" and wait == pytest.approx(3539, abs=1)
    for t in (3700, 3701):
        assert lim.acquire(f"v{t}", now=t)[0]
        lim.release()
    ok, _, which = lim.acquire("z", now=3702)
    assert not ok and which == "5 per 86400s"
    snap = lim.snapshot(now=3702)
    assert (snap["last_minute"], snap["last_hour"], snap["last_day"]) == (2, 2, 5)
    assert lim.acquire("z", now=90000)[0]


# ---------------------------------------------------------------------------- cache and prerender progress

def test_cache_counts_files_per_match_and_partial_renders(studio):
    d = studio.root / "cache" / "syn_0294"
    d.mkdir(parents=True)
    (d / "cl_a_25fps_1280.mp4").write_bytes(b"x" * 1000)
    (d / "cl_b_25fps_1280.mp4").write_bytes(b"x" * 500)
    (d / ".cl_c_25fps_1280.1234abcd.part.mp4").write_bytes(b"x" * 7)
    c = _get(studio, "/api/studio/cache")
    assert c["files"] == 2 and c["bytes"] == 1500
    assert c["matches"] == [{"match_id": "syn_0294", "files": 2, "bytes": 1500, "partial": 1}]
    assert set(c["prerender"]) == {"enabled", "running", "total", "rendered", "failed", "started_at", "finished_at"}


def test_prerender_reports_its_progress(studio, monkeypatch):
    seen = []

    def fake_render(d, clip, label, fps, width):
        seen.append(dict(api.PRERENDER_PROGRESS))
        if len(seen) == 2:
            raise RuntimeError("bad clip")
        return Path("x.mp4")

    monkeypatch.setattr(api, "PRERENDER_PROGRESS", dict(api.PRERENDER_PROGRESS))
    monkeypatch.setattr(api, "_render_clip_cached", fake_render)
    api._prerender()
    p = api.PRERENDER_PROGRESS
    assert seen[0]["running"] is True and seen[0]["total"] == len(seen) > 2
    assert p["running"] is False and p["rendered"] == len(seen) - 1 and p["failed"] == 1 and p["finished_at"] >= p["started_at"]
    c = _get(studio, "/api/studio/cache")["prerender"]
    assert c["total"] == len(seen) and c["failed"] == 1 and c["finished_at"].endswith("Z")


# ---------------------------------------------------------------------------- jobs: the allow-list

def _argv(kind, args, studio):
    return build_argv(kind, args, data_root=api.DATA_ROOT, models_dir=api.MODELS_DIR, job_dir=studio.root / "jobs" / "j")


def test_allow_list_builds_only_known_shapes(studio):
    video = studio.root / "match.mp4"
    video.write_bytes(b"\x00")
    models = str(api.MODELS_DIR.resolve())
    argv = _argv("vision-run", {"video": str(video), "roster": "syn_0294", "out": "vis_0001"}, studio)
    assert argv == ["run", str(video.resolve()), "--roster", str(studio.match.resolve()), "--out", str((api.DATA_ROOT / "vis_0001").resolve()),
                    "--models", models, "--match-id", "vis_0001", "--workflow"]
    assert "--workflow" not in _argv("vision-run", {"video": str(video), "roster": "syn_0294", "out": "v2", "workflow": False}, studio)
    assert _argv("evaluate", {}, studio) == ["evaluate", "--set", "dev", "--models", models, "--out", str((studio.root / "jobs" / "j" / "result.json").resolve())]
    assert _argv("evaluate", {"set": "fresh", "e2e_seed": 301}, studio)[-2:] == ["--e2e-seed", "301"]
    assert _argv("train-events", None, studio) == ["train-events", "--models", models]
    (studio.match / "review").mkdir()
    assert _argv("learn-from-reviews", {"match_ids": ["syn_0294"]}, studio) == ["learn-from-reviews", str(studio.match.resolve()), "--models", models]


def test_cut_clips_picks_the_featured_player_and_keeps_players_who_have_clips(studio):
    d = str(studio.match.resolve())
    assert _argv("cut-clips", {"match": "syn_0294"}, studio) == [d, "--player", "t_home_09"]  # manifest clips_for, already cut
    assert _argv("cut-clips", {"match": "syn_0294", "player": "t_home_10"}, studio) == [d, "--player", "t_home_09", "--player", "t_home_10"]
    manifest = json.loads((studio.match / "manifest.json").read_text())
    (studio.match / "manifest.json").write_text(json.dumps({**manifest, "clips_for": None}))
    (studio.match / "clips.jsonl").unlink()
    assert _argv("cut-clips", {"match": "syn_0294"}, studio) == [d, "--player", "t_home_06"]  # most possessions and events
    (studio.match / "manifest.json").unlink()
    assert _argv("cut-clips", {"match": "syn_0294", "player": ""}, studio) == [d, "--player", "t_home_06"]


@pytest.mark.parametrize("kind, args, why", [
    ("shell", {}, "unknown job kind"),
    ("train-events", {"models": "/tmp/x"}, "does not take"),
    ("evaluate", {"root": "/"}, "does not take"),
    ("evaluate", {"set": "--help"}, "dev or fresh"),
    ("evaluate", {"e2e_seed": True}, "integer"),
    ("evaluate", {"e2e_seed": "301"}, "integer"),
    ("vision-run", {"roster": "syn_0294", "out": "v"}, "needs video"),
    ("vision-run", {"video": "/nonexistent.mp4", "roster": "syn_0294", "out": "v"}, "existing"),
    ("vision-run", {"video": "VIDEO_TXT", "roster": "syn_0294", "out": "v"}, "existing"),
    ("vision-run", {"video": "VIDEO", "roster": "../syn_0294", "out": "v"}, "match id"),
    ("vision-run", {"video": "VIDEO", "roster": "nope", "out": "v"}, "no match"),
    ("vision-run", {"video": "VIDEO", "roster": "syn_0294", "out": "syn_0294"}, "already exists"),
    ("vision-run", {"video": "VIDEO", "roster": "syn_0294", "out": "--rf"}, "match id"),
    ("vision-run", {"video": "VIDEO", "roster": "syn_0294", "out": "v", "workflow": "yes"}, "true or false"),
    ("vision-run", {"video": "VIDEO", "roster": "syn_0294", "out": "v", "review": True}, "does not take"),
    ("learn-from-reviews", {"match_ids": []}, "1 to 20"),
    ("learn-from-reviews", {"match_ids": "syn_0294"}, "1 to 20"),
    ("learn-from-reviews", {"match_ids": ["syn_0294"]}, "no who's who reviews"),
    ("cut-clips", {}, "needs match"),
    ("cut-clips", {"match": "../syn_0294"}, "match id"),
    ("cut-clips", {"match": "nope"}, "no match"),
    ("cut-clips", {"match": "syn_0294", "player": "t_away_99"}, "team sheet"),
    ("cut-clips", {"match": "syn_0294", "player": "--cloud"}, "team sheet"),
    ("cut-clips", {"match": "syn_0294", "player": ["t_home_09"]}, "team sheet"),
    ("cut-clips", {"match": "syn_0294", "query": "x"}, "does not take"),
])
def test_allow_list_refuses_everything_else(studio, kind, args, why):
    (studio.root / "match.mp4").write_bytes(b"\x00")
    (studio.root / "notes.txt").write_text("x")
    args = {k: (str(studio.root / "match.mp4") if v == "VIDEO" else str(studio.root / "notes.txt") if v == "VIDEO_TXT" else v)
            for k, v in args.items()}
    with pytest.raises(JobError, match=why):
        _argv(kind, args, studio)


# ---------------------------------------------------------------------------- jobs: running them

@pytest.fixture()
def jobs_on(studio, monkeypatch):
    api.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (api.MODELS_DIR / "shot_model.joblib").write_bytes(b"")
    return studio


def _runner(studio, monkeypatch, script: str) -> JobRunner:
    runner = JobRunner(studio.root / "jobs", prefix=[sys.executable, "-c", script])
    monkeypatch.setattr(studio_api, "JOBS", runner)
    return runner


def _post(c, body, key=ADMIN):
    return c.post("/api/studio/jobs", json=body, headers={"X-Regista-Token": key})


def test_jobs_are_refused_on_the_cloud_app(jobs_on, monkeypatch):
    monkeypatch.setenv("REGISTA_CLOUD", "1")
    listing = _get(jobs_on, "/api/studio/jobs")
    assert listing["available"] is False and "only on a local Regista" in listing["reason"]
    r = _post(jobs_on, {"kind": "train-events"})
    assert r.status_code == 409 and "only on a local Regista" in r.json()["detail"]
    assert not (jobs_on.root / "jobs").exists()


def test_jobs_are_refused_without_vision_models(studio):
    r = _post(studio, {"kind": "train-events"})
    assert r.status_code == 409 and "no vision models" in r.json()["detail"]


def test_only_the_admin_key_starts_a_job(jobs_on, monkeypatch):
    _runner(jobs_on, monkeypatch, "print('hi')")
    assert _post(jobs_on, {"kind": "train-events"}, key=VIEW).status_code == 403
    assert jobs_on.post("/api/studio/jobs", json={"kind": "train-events"}).status_code == 401
    assert _post(jobs_on, {"kind": "rm -rf"}).status_code == 422
    assert _post(jobs_on, {"kind": "evaluate", "args": {"set": "x"}}).status_code == 422


def test_a_job_runs_logs_and_keeps_its_result(jobs_on, monkeypatch):
    script = ("import sys, json, os; a = sys.argv[1:]; print('ARGS', a); print('TOKEN', os.environ.get('REGISTA_ADMIN_TOKEN'));"
              "open(a[a.index('--out') + 1], 'w').write(json.dumps({'clips': {'recall': 0.76, 'precision': 0.94}}))")
    runner = _runner(jobs_on, monkeypatch, script)
    r = _post(jobs_on, {"kind": "evaluate", "args": {"set": "fresh"}})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "running" and job["argv"][:4] == ["python3", "-m", "regista.vision", "evaluate"]
    done = runner.wait(job["id"])
    assert done["status"] == "ok" and done["returncode"] == 0 and done["result"] == {"clips": {"recall": 0.76, "precision": 0.94}}
    assert _get(jobs_on, f"/api/studio/jobs/{job['id']}")["status"] == "ok"
    log = _get(jobs_on, f"/api/studio/jobs/{job['id']}/log")
    assert "ARGS ['evaluate', '--set', 'fresh'" in log["text"] and "TOKEN None" in log["text"]  # the child never sees the keys
    assert log["next_offset"] == log["size"] > 0
    tail = _get(jobs_on, f"/api/studio/jobs/{job['id']}/log?offset={log['size'] + 100}")
    assert tail["text"] == "" and tail["offset"] == log["size"]
    listing = _get(jobs_on, "/api/studio/jobs")
    assert listing["available"] and listing["running"] is None and [j["id"] for j in listing["jobs"]] == [job["id"]]


def test_one_job_at_a_time_and_failures_are_recorded(jobs_on, monkeypatch):
    runner = _runner(jobs_on, monkeypatch, "import time, sys; time.sleep(1.0); sys.exit(3)")
    first = _post(jobs_on, {"kind": "train-events"}).json()
    assert _get(jobs_on, "/api/studio/jobs")["running"]["id"] == first["id"]
    busy = _post(jobs_on, {"kind": "train-events"})
    assert busy.status_code == 409 and "one job at a time" in busy.json()["detail"]
    done = runner.wait(first["id"])
    assert done["status"] == "failed" and done["returncode"] == 3
    assert _post(jobs_on, {"kind": "train-events"}).status_code == 201
    runner.wait(_get(jobs_on, "/api/studio/jobs")["jobs"][0]["id"])


def test_jobs_run_their_module_under_the_progress_wrapper(jobs_on, monkeypatch):
    runner = JobRunner(jobs_on.root / "jobs")
    monkeypatch.setattr(studio_api, "JOBS", runner)
    seen = []
    monkeypatch.setattr(jobs_mod.subprocess, "Popen", lambda cmd, **kw: seen.append(cmd) or (_ for _ in ()).throw(OSError("not here")))
    job = _post(jobs_on, {"kind": "cut-clips", "args": {"match": "syn_0294"}}).json()
    assert job["argv"][:3] == ["python3", "-m", "regista.agents"] and job["status"] == "failed"
    assert seen[0][1:5] == ["-u", "-m", "regista.studio.progress", "regista.agents"]
    _post(jobs_on, {"kind": "train-events"})
    assert seen[1][1:5] == ["-u", "-m", "regista.studio.progress", "regista.vision"]


def test_the_progress_wrapper_prints_each_agent_as_it_runs(tmp_path):
    """A real cut-clips run: the log has a line per agent before the CLI's own summary, and the clips are written."""
    match = tmp_path / "syn_0294"
    shutil.copytree(SAMPLE, match, ignore=shutil.ignore_patterns("agents", "clips.jsonl"))
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "REGISTA_DOTENV": "",
           "REGISTA_FEEDBACK_DIR": str(tmp_path / "feedback")}
    out = subprocess.run([sys.executable, "-u", "-m", "regista.studio.progress", "regista.agents", str(match), "--player", "t_home_09"],
                         capture_output=True, text=True, env=env, timeout=300)
    assert out.returncode == 0, out.stdout + out.stderr
    lines = out.stdout.splitlines()
    assert lines[0].startswith("[studio ") and "started: python3 -m regista.agents" in lines[0]
    started = [i for i, line in enumerate(lines) if line.endswith("ingest: started")]
    done = [i for i, line in enumerate(lines) if "persist: done in" in line]
    summary = next(i for i, line in enumerate(lines) if line.startswith("engine: Microsoft Agent Framework workflow"))
    assert started and done and started[0] < done[0] < summary and lines[-1].endswith("finished with exit code 0")
    assert sum(1 for line in (match / "clips.jsonl").read_text().splitlines() if '"type": "clip"' in line or '"type":"clip"' in line) == 11


def test_the_progress_wrapper_runs_only_regista_commands(capsys):
    assert progress.main(["os", "-c", "x"]) == 2 and "usage" in capsys.readouterr().err


def test_a_job_left_running_by_an_earlier_process_is_lost(jobs_on):
    d = jobs_on.root / "jobs" / "20261021-101500-train-events-abc123"
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"id": d.name, "kind": "train-events", "status": "running"}))
    (jobs_on.root / "jobs" / "not-a-job").mkdir()
    jobs = _get(jobs_on, "/api/studio/jobs")["jobs"]
    assert [(j["id"], j["status"]) for j in jobs] == [(d.name, "lost")]
    assert jobs_on.get("/api/studio/jobs/not-a-job", headers={"X-Regista-Token": VIEW}).status_code == 404
    assert jobs_on.get("/api/studio/jobs/..%2F..%2Fetc/log", headers={"X-Regista-Token": VIEW}).status_code == 404


# ---------------------------------------------------------------------------- the status CLI

def test_status_prints_the_overview_without_the_key(studio, monkeypatch, capsys):
    overview = _get(studio, "/api/studio/overview")
    seen = {}

    def fake_fetch(url, key, timeout=30.0):
        seen.update(url=url, key=key)
        return overview

    monkeypatch.setattr(cli, "fetch_overview", fake_fetch)
    monkeypatch.setenv("REGISTA_APP_URL", "https://example.test")
    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert seen == {"url": "https://example.test", "key": VIEW}  # the view key wins over the admin key
    assert "Regista Studio  https://example.test  (role view, view key)" in out and "To do" in out and "Render cache" in out
    assert VIEW not in out and ADMIN not in out
    monkeypatch.delenv("REGISTA_STUDIO_VIEW_TOKEN")
    assert cli.main(["status", "--url", "http://127.0.0.1:9", "--json"]) == 0
    assert seen["key"] == ADMIN and seen["url"] == "http://127.0.0.1:9" and json.loads(capsys.readouterr().out)["role"] == "view"


def test_status_reads_the_key_from_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("REGISTA_STUDIO_VIEW_TOKEN=from-dotenv\n")
    for var in ("REGISTA_STUDIO_VIEW_TOKEN", "REGISTA_ADMIN_TOKEN"):
        monkeypatch.setenv(var, "x")  # registers the variable, so what load_dotenv sets is removed after the test
        monkeypatch.delenv(var)
    monkeypatch.setenv("REGISTA_DOTENV", str(env))
    assert cli._key() == ("from-dotenv", "view key")


def test_status_sends_the_key_only_in_the_header(monkeypatch):
    sent = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"role": "view"}'

    def fake_urlopen(req, timeout):
        sent.update(url=req.full_url, headers=dict(req.header_items()))
        return Resp()

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    assert cli.fetch_overview("https://example.test/", "secret") == {"role": "view"}
    assert sent["url"] == "https://example.test/api/studio/overview" and "secret" not in sent["url"]
    assert sent["headers"]["X-regista-token"] == "secret"


def test_status_says_why_it_failed(monkeypatch, capsys):
    import urllib.error

    def refused(url, key, timeout=30.0):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(cli, "fetch_overview", refused)
    assert cli.main(["status", "--url", "https://example.test"]) == 2
    assert "key was refused" in capsys.readouterr().err
