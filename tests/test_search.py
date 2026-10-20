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
        if filter:
            predicate = _compile(filter)
            rows = [r for r in rows if predicate(r)]
        if search_text and search_text != "*":
            words = search_text.lower().split()
            rows = [r for r in rows if any(w in (r["title"] + " " + " ".join(r["tags"])).lower() for w in words)]
        rows.sort(key=lambda r: (-r["watchability"], r["minute"]))
        return [{**r, "@search.score": 1.0} for r in rows[:top]]


def _compile(odata: str):
    """Translate the OData subset Regista emits (eq, ge, le, tags/any, and, or, parentheses, '' escapes) to a predicate."""
    import re
    lit = r"'((?:[^']|'')*)'"
    expr = re.sub(r"tags/any\(x: x eq " + lit + r"\)", lambda m: f"({m.group(1).replace(chr(39) * 2, chr(39))!r} in r['tags'])", odata)
    expr = re.sub(r"(\w+) eq " + lit, lambda m: f"(str(r.get({m.group(1)!r})) == {m.group(2).replace(chr(39) * 2, chr(39))!r})", expr)
    expr = re.sub(r"(\w+) ge ([\d.]+)", lambda m: f"(r[{m.group(1)!r}] >= {m.group(2)})", expr)
    expr = re.sub(r"(\w+) le ([\d.]+)", lambda m: f"(r[{m.group(1)!r}] <= {m.group(2)})", expr)
    assert re.fullmatch(r"[\s()a-zA-Z0-9_'\[\].=<>\"!\- ]*|.*", expr)
    return eval(compile("lambda r: " + expr, "<odata>", "eval"))  # test-only translation of our own filters


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


def test_library_search_tells_players_apart_across_matches(fake_index):
    """t_home_09 is a different person in every match; across the library a player is name + team."""
    from regista.clips import derive_clips as dc

    names = {}
    for seed in (294, 77):
        r = generate(seed=seed, minutes=3.0, track_hz=1.0)
        clips, labels = dc(r.stream, PLAYER)
        fake_index.upload([to_document(r.match, c, lb) for c, lb in zip(clips, labels)])
        names[seed] = next(p["name"] for p in r.match["players"] if p["player_id"] == PLAYER)
    assert names[294] != names[77]
    for seed in (294, 77):
        surname = names[seed].split()[-1]
        out = search_library(f"every clip by {surname}", index=fake_index)
        assert out["results"], seed
        assert {d["player_name"] for d in out["results"]} == {names[seed]}, (seed, {d["player_name"] for d in out["results"]})
    nobody = search_library("every clip by Zzyzx", index=fake_index)
    assert nobody["results"] == [] and "no player" in nobody["message"]
