"""Cloud agents keep the orchestrator contract, validate model output, and fall back honestly. No Azure needed here."""

from __future__ import annotations

import json

import pytest

from regista.agents import AgentError, Orchestrator
from regista.agents.roles import ClipAgent, IngestAgent, PossessionAgent, ValidatorAgent
from regista.cloud.config import CloudConfig, load_dotenv
from regista.cloud.cosmos import ClipStore, CosmosPersistAgent
from regista.cloud.foundry import ALLOWED_TAGS, FoundryLabelAgent, FoundryLibrarianAgent, LabelOut, validate_label
from regista.synth import generate
from fakes import FakeContainer  # noqa: E402

PLAYER = "t_home_09"


@pytest.fixture
def match_dir(tmp_path):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = tmp_path / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    return d


def test_config_from_env_and_dotenv(tmp_path, monkeypatch):
    # load_dotenv writes os.environ directly; register every key with monkeypatch so teardown removes them
    # (otherwise these values leak into later tests and switch the cloud paths on).
    for k in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL", "REGISTA_COSMOS_ENDPOINT"):
        monkeypatch.setenv(k, "")
        monkeypatch.delenv(k)
    env = tmp_path / ".env"
    env.write_text('FOUNDRY_PROJECT_ENDPOINT="https://x.services.ai.azure.com/api/projects/p"\nFOUNDRY_MODEL=gpt-5-mini\n# comment\nREGISTA_COSMOS_ENDPOINT=https://c.documents.azure.com:443/\n')
    cfg = CloudConfig.from_env(env)
    assert cfg.foundry_enabled and cfg.cosmos_enabled and cfg.foundry_model == "gpt-5-mini"
    assert "Foundry: on" in cfg.describe()
    monkeypatch.setenv("FOUNDRY_MODEL", "other")
    assert load_dotenv(env) == {}  # never overrides real env vars
    assert CloudConfig.from_env(env).foundry_model == "other"


def test_unconfigured_cloud_agents_fail_fast_and_are_not_retried(match_dir, monkeypatch):
    for k in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL", "REGISTA_COSMOS_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    agents = [IngestAgent(), ValidatorAgent(), PossessionAgent(), ClipAgent(), FoundryLabelAgent(cloud=CloudConfig())]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    assert result.statuses["label"] == "failed" and result.dead_letters[0]["retryable"] is False
    assert "not configured" in result.dead_letters[0]["error"]


def test_foundry_label_agent_uses_model_output_validated(match_dir):
    seen = []

    async def runner(instructions, prompt):
        seen.append(json.loads(prompt.split("\n\n")[0]))
        p = json.loads(prompt.split("\n\n")[0])
        return json.dumps({"title": f"{p['player']['name']} ({p['player']['kit_number']}): model title",
                           "tags": ["goal", "made_up_tag", "Skill Move"], "watchability": 1.7,
                           "summary": "A commentator line.", "explanation": "Scored high because of the goal."})

    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), FoundryLabelAgent(runner=runner, cloud=CloudConfig())]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    assert result.ok, result.statuses
    labels = result.state["labels"][PLAYER]
    assert labels and all(lb["model"] == "foundry:test" for lb in labels)
    assert all(lb["watchability"] == 1.0 for lb in labels)  # clamped
    assert all("made_up_tag" not in lb["tags"] and "skill_move" in lb["tags"] for lb in labels)
    assert all(any(t in lb["tags"] for t in ("on_ball_main", "replay_appearance", "highlight_appearance", "closeup_appearance")) for lb in labels)
    assert all("model title" in lb["title"] for lb in labels)
    assert seen and "prior_label" in seen[0] and "allowed_tags" in seen[0] and seen[0]["events"]
    assert any("dropped unknown tags" in n for n in result.state["label_notes"][PLAYER])


def test_foundry_label_agent_falls_back_per_clip(match_dir):
    calls = {"n": 0}

    async def runner(instructions, prompt):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            return "I cannot help with that."
        return json.dumps({"title": "t", "tags": ["pass"], "watchability": 0.3, "summary": "s", "explanation": "Scored 0.3"})

    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), FoundryLabelAgent(runner=runner, cloud=CloudConfig(), concurrency=1)]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    labels = result.state["labels"][PLAYER]
    models = {lb["model"] for lb in labels}
    assert models == {"foundry:test", "rules-v0 (foundry fallback)"}
    assert any("fell back" in n for n in result.state["label_notes"][PLAYER])


def test_clip_prompt_mentions_json_for_json_mode(match_dir):
    """The Responses API rejects json_object output unless the input itself says 'json'."""
    from regista.clips import StreamIndex, cut_clips, label_clips
    from regista.cloud.foundry import clip_prompt
    from regista.schema import iter_jsonl

    index = StreamIndex.build(list(iter_jsonl(match_dir / "events.jsonl")))
    clips = cut_clips(index, PLAYER)
    prompt = clip_prompt(index, clips[0], label_clips(index, clips[:1])[0])
    assert "json" in prompt.lower()
    json.loads(prompt.split("\n\n")[0])  # the structured part is still valid JSON


def test_validate_label_keeps_reason_and_vocabulary():
    prior = {"title": "p", "tags": ["goal", "on_ball_main"], "watchability": 1.0, "summary": "ps", "explanation": "pe"}
    out, notes = validate_label(LabelOut(title="", tags=["nonsense"], watchability=-1, summary="", explanation=""), prior)
    assert out.tags == ["on_ball_main"] and out.watchability == 0.0 and out.title == "p"
    assert notes and set(out.tags) <= ALLOWED_TAGS


def test_foundry_librarian_agent_adds_an_answer_and_keeps_structured_results(match_dir):
    async def answerer(md, q):
        return f"Two clips matched for '{q}'."

    surname = next(p["name"].split()[-1] for p in json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])["players"] if p["player_id"] == PLAYER)
    from regista.agents.roles import LabelAgent, PersistAgent

    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), LabelAgent(), PersistAgent(), FoundryLibrarianAgent(answerer=answerer, cloud=CloudConfig())]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": [f"{surname} nutmeg"]})
    assert result.ok
    ans = result.state["answers"][0]
    assert ans["answer"].startswith("Two clips") and ans["answered_by"] == "foundry:test" and ans["results"]


def test_cosmos_persist_agent_upserts_documents(match_dir):
    from regista.agents.roles import LabelAgent

    store = ClipStore(FakeContainer(), FakeContainer(), FakeContainer())
    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), LabelAgent(), CosmosPersistAgent(store=store, cloud=CloudConfig())]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    assert result.ok, result.statuses
    n_clips = len(result.state["clips"][PLAYER])
    assert result.state["cosmos"]["documents"] == 1 + 2 * n_clips
    assert (match_dir / "clips.jsonl").exists()
    clips, labels = store.clips_for(result.state["match"]["match_id"], PLAYER)
    assert len(clips) == n_clips and set(labels) == {c["id"] for c in clips}
    assert store.matches.items[result.state["match"]["match_id"]]["type"] == "match"


def test_cosmos_unconfigured_fails_fast(match_dir, monkeypatch):
    monkeypatch.delenv("REGISTA_COSMOS_ENDPOINT", raising=False)
    with pytest.raises(AgentError):
        ClipStore.connect(CloudConfig())


def test_foundry_agents_work_inside_a_running_event_loop(match_dir):
    """The API runs inside FastAPI's event loop; asyncio.run() there fails and labels were silently lost."""
    import asyncio

    async def runner(instructions, prompt):
        return json.dumps({"title": "t", "tags": ["goal"], "watchability": 0.9, "summary": "s", "explanation": "Scored 0.9"})

    async def answerer(md, q):
        return "answered"

    from regista.agents.roles import PersistAgent

    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), FoundryLabelAgent(runner=runner, cloud=CloudConfig()), PersistAgent(),
              FoundryLibrarianAgent(answerer=answerer, cloud=CloudConfig())]

    async def inside_loop():
        # Called synchronously from a coroutine, exactly like a sync helper inside an async endpoint.
        return Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": ["goal"]})

    result = asyncio.run(inside_loop())
    assert result.ok, (result.statuses, result.dead_letters)
    assert all(lb["model"] == "foundry:test" for lb in result.state["labels"][PLAYER])
    assert result.state["answers"][0]["answer"] == "answered"


def test_api_upload_reports_dead_letters(tmp_path, monkeypatch):
    """A failing cloud agent must be visible in the upload response, not only in the container's files."""
    from fastapi.testclient import TestClient

    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", tmp_path / "data")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    monkeypatch.setenv("REGISTA_CLOUD", "1")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://invalid.example/api/projects/x")
    monkeypatch.setenv("FOUNDRY_MODEL", "nope")
    monkeypatch.delenv("REGISTA_COSMOS_ENDPOINT", raising=False)

    def broken_agents():
        from regista.agents.roles import default_agents

        class Broken(FoundryLabelAgent):
            def handle(self, state):
                raise AgentError("endpoint unreachable", retryable=False)

        return [Broken(cloud=CloudConfig()) if a.role == "label" else a for a in default_agents()]

    import regista.cloud as cloud_pkg

    monkeypatch.setattr(cloud_pkg, "agents_for", lambda *a, **k: broken_agents())
    r = generate(seed=7, minutes=0.5)
    events = "\n".join(json.dumps(x) for x in r.stream) + "\n"
    with TestClient(api.app) as client:
        resp = client.post("/api/matches", files={"events": ("events.jsonl", events, "application/x-ndjson")}, params={"player": PLAYER})
    body = resp.json()
    assert resp.status_code == 201 and body["pipeline_ok"] is False
    assert body["dead_letters"] == [{"agent": "label", "error": "AgentError: endpoint unreachable"}]


def test_tests_never_see_real_cloud_configuration():
    """Guard: the project's .env must not leak into tests, or API tests would write to real Cosmos DB."""
    cfg = CloudConfig.from_env()
    assert not cfg.foundry_enabled and not cfg.cosmos_enabled


def test_foundry_labels_keep_the_rules_score_as_prior(match_dir, monkeypatch):
    """prior_watchability is the learned model's training input: it must stay the rules score, not a model's score."""
    from regista.feedback import WatchabilityModel, feedback_dir

    WatchabilityModel(feature_names=["tag:goal"], coef=[4.0], intercept=-2.0, n_samples=12, version=3).save()

    async def runner(instructions, prompt):
        return json.dumps({"title": "t", "tags": ["goal"], "watchability": 0.9, "summary": "s", "explanation": "Scored 0.9"})

    agents = [IngestAgent(), PossessionAgent(), ClipAgent(), FoundryLabelAgent(runner=runner, cloud=CloudConfig())]
    result = Orchestrator(agents, match_dir / "agents").run({"match_dir": str(match_dir), "player_ids": [PLAYER], "queries": []})
    from regista.clips import StreamIndex, cut_clips, label_clips
    from regista.schema import iter_jsonl

    index = StreamIndex.build(list(iter_jsonl(match_dir / "events.jsonl")))
    rules = {lb["clip_id"]: lb["watchability"] for lb in label_clips(index, cut_clips(index, PLAYER))}
    for lb in result.state["labels"][PLAYER]:
        assert lb["prior_watchability"] == rules[lb["clip_id"]]
