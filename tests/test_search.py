"""Azure AI Search behind the library: documents, filters, the Indexer role in the workflow. Fakes only; no Azure."""

from __future__ import annotations

import json

import pytest

from regista.agents.roles import default_agents
from regista.agents.workflow import WorkflowPipeline
from regista.clips import derive_clips
from regista.cloud.search import INDEX_NAME, ClipIndex, SearchIndexAgent, doc_key, index_definition, search_library, to_document
from regista.synth import generate

PLAYER = "t_home_09"


class FakeIndexClient:
    def __init__(self):
        self.indexes = {}

    def create_or_update_index(self, index):
        self.indexes[index.name] = index


class FakeSearchClient:
    """Implements the slice of SearchClient we use, including OData filters for eq, any(), ge/le, and order_by."""

    def __init__(self):
        self.docs = {}

    def merge_or_upload_documents(self, docs):
        class R:
            succeeded = True
        for d in docs:
            self.docs[d["id"]] = {**self.docs.get(d["id"], {}), **d}
        return [R() for _ in docs]

    def search(self, search_text="*", filter=None, order_by=None, top=50, **kw):
        rows = list(self.docs.values())
        for clause in (filter.split(" and ") if filter else []):
            rows = [r for r in rows if _match(r, clause)]
        if search_text and search_text != "*":
            words = search_text.lower().split()
            rows = [r for r in rows if any(w in (r["title"] + " " + " ".join(r["tags"])).lower() for w in words)]
        rows.sort(key=lambda r: (-r["watchability"], r["minute"]))
        return [{**r, "@search.score": 1.0} for r in rows[:top]]


def _match(r, clause):
    import re
    if m := re.match(r"tags/any\(x: x eq '(.+)'\)", clause):
        return m.group(1) in r["tags"]
    if m := re.match(r"(\w+) eq '(.+)'", clause):
        return str(r.get(m.group(1))) == m.group(2)
    if m := re.match(r"(\w+) ge ([\d.]+)", clause):
        return r[m.group(1)] >= float(m.group(2))
    if m := re.match(r"(\w+) le ([\d.]+)", clause):
        return r[m.group(1)] <= float(m.group(2))
    raise AssertionError(f"unhandled filter clause {clause!r}")


@pytest.fixture
def fake_index():
    return ClipIndex(index_client=FakeIndexClient(), search_client=FakeSearchClient())


@pytest.fixture(scope="module")
def match_and_clips():
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    clips, labels = derive_clips(r.stream, PLAYER)
    return r, clips, labels


def test_documents_are_search_safe_and_complete(match_and_clips):
    r, clips, labels = match_and_clips
    doc = to_document(r.match, clips[0], labels[0])
    assert doc["id"] == doc_key(r.match["match_id"], clips[0]["id"]) and all(c.isalnum() or c in "_-=" for c in doc["id"])
    assert doc["player_name"] and doc["kit_number"] == 9 and doc["team_id"] == "t_home" and doc["home"] is True
    assert doc["minute"] >= 1 and doc["tags"] == labels[0]["tags"]
    fields = {f.name for f in index_definition().fields}
    assert set(doc) <= fields, set(doc) - fields
    assert index_definition().name == INDEX_NAME


def test_index_search_filters(match_and_clips, fake_index):
    r, clips, labels = match_and_clips
    fake_index.ensure_index()
    n = fake_index.upload([to_document(r.match, c, lb) for c, lb in zip(clips, labels)])
    assert n == len(clips)
    nutmegs = fake_index.search(player_id=PLAYER, tags=["nutmeg"])
    assert nutmegs and all("nutmeg" in d["tags"] for d in nutmegs)
    w = [d["watchability"] for d in nutmegs]
    assert w == sorted(w, reverse=True)
    assert all(d["reason"] == "replay_appearance" for d in fake_index.search(reason="replay_appearance"))
    assert not fake_index.search(player_id="t_away_99")


def test_search_library_parses_plain_english(match_and_clips, fake_index):
    r, clips, labels = match_and_clips
    fake_index.upload([to_document(r.match, c, lb) for c, lb in zip(clips, labels)])
    surname = next(p["name"].split()[-1] for p in r.match["players"] if p["player_id"] == PLAYER)
    out = search_library(f"every nutmeg by {surname}", index=fake_index)
    assert out["backend"] == "azure-ai-search" and out["parsed"]["tags"] == ["nutmeg"]
    assert out["results"] and all(d["player_id"] == PLAYER and "nutmeg" in d["tags"] for d in out["results"])
    striker = search_library("replays of the home striker's goal", index=fake_index)
    assert striker["results"] and all(d["reason"] == "replay_appearance" and "goal" in d["tags"] for d in striker["results"])


def test_indexer_role_runs_in_the_workflow(tmp_path, fake_index):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = tmp_path / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    agents = default_agents()
    agents.insert(next(i for i, a in enumerate(agents) if a.role == "persist") + 1, SearchIndexAgent(clip_index=fake_index))
    pipe = WorkflowPipeline(agents, tmp_path / "s", feedback_dir=tmp_path / "fb")
    assert "indexer" in pipe.mermaid()
    run = pipe.run({"match_dir": str(d), "player_ids": [PLAYER], "queries": []})
    assert run.ok, run.statuses
    order = [t["agent"] for t in run.trace if t["status"] == "ok"]
    assert order.index("persist") < order.index("indexer") < order.index("librarian")
    assert run.state["search_index"]["documents"] == len(run.state["clips"][PLAYER])
    assert len(fake_index.search_client.docs) == len(run.state["clips"][PLAYER])


def test_unconfigured_search_fails_fast(monkeypatch):
    monkeypatch.delenv("REGISTA_SEARCH_ENDPOINT", raising=False)
    from regista.agents.base import AgentError
    with pytest.raises(AgentError):
        ClipIndex()
