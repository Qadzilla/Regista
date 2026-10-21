"""The conversational Librarian: follow-ups merge into the query so far; the endpoint round-trips the state."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.conversation import EMPTY, chat_turn, clean_state, describe, step
from regista.librarian import _load

SAMPLE = Path(__file__).resolve().parents[1] / "data/synthetic/sample"
MATCH_DIR = SAMPLE / "syn_0294"
MATCH = _load(str(MATCH_DIR))[0]


def _talk(*messages):
    state, outs = None, []
    for m in messages:
        out = step(m, state, MATCH)
        state = out["state"]
        outs.append(out)
    return outs


def test_follow_ups_merge_into_the_query():
    a, b, c, d, e, f = _talk("find me Castellanos doing a nutmeg", "now the replays", "in the second half", "what about Ibarra?",
                             "also shots", "his passes")
    assert a["state"]["player_ids"] == ["t_home_09"] and a["state"]["tags"] == ["nutmeg"]
    assert b["state"]["player_ids"] == ["t_home_09"] and b["state"]["reasons"] == ["replay_appearance"] and b["state"]["tags"] == ["nutmeg"]
    assert c["state"]["minutes"][0] == 46 and c["state"]["reasons"] == ["replay_appearance"]
    assert d["state"]["player_ids"] == ["t_home_10"] and d["state"]["tags"] == ["nutmeg"]  # new player, same filters
    assert e["state"]["tags"] == ["nutmeg", "shot"]                                      # "also" adds
    assert f["state"]["player_ids"] == ["t_home_10"] and f["state"]["tags"] == ["pass"]  # "his" keeps; a new tag replaces


def test_clearing_paging_reels_and_starting_over():
    outs = _talk("Castellanos nutmeg replays in the first 2 minutes", "everything he did", "live on the ball only", "whole match",
                 "more", "make that a reel", "start over")
    every, live, whole, more, reel, reset = outs[1:]
    assert every["state"]["tags"] == [] and every["state"]["reasons"] == [] and every["state"]["player_ids"] == ["t_home_09"]
    assert live["state"]["reasons"] == ["on_ball_main"]
    assert whole["state"]["minutes"] is None
    assert more["intent"] == "more" and more["state"]["offset"] == 6
    assert reel["intent"] == "reel" and reel["state"] == more["state"]
    assert reset["intent"] == "reset" and reset["state"] == EMPTY


def test_a_client_state_is_cleaned_before_use():
    dirty = {"player_ids": ["t_home_09", "nobody", "<script>"], "team_id": "x", "tags": ["nutmeg", "drop table"], "reasons": ["replay_appearance", "x"],
             "minutes": [1, 9999], "limit": 10_000, "offset": -4}
    assert clean_state(dirty, MATCH) == {"player_ids": ["t_home_09"], "team_id": None, "tags": ["nutmeg"], "reasons": ["replay_appearance"],
                                         "minutes": None, "limit": None, "offset": 0}
    assert describe(clean_state(dirty, MATCH), MATCH) == "Sami Castellanos (9) · nutmeg · replays only"


def test_replies_say_what_exists_when_nothing_matches():
    out = chat_turn(MATCH_DIR, "Ibarra shots", None)
    assert out["results"] == [] and out["reply"].startswith("No clips for Ivan Ibarra (10) · shot.")
    assert "pass" in out["reply"] and "on_ball_main" not in out["reply"] and "touch" not in out["reply"]
    assert "didn't catch who" in chat_turn(MATCH_DIR, "find me zzqx doing it", None)["reply"]
    reel = chat_turn(MATCH_DIR, "make that a reel", chat_turn(MATCH_DIR, "Castellanos", None)["state"])
    assert reel["intent"] == "reel" and 1 <= len(reel["reel"]) <= 8


@pytest.fixture
def client(monkeypatch):
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", SAMPLE)
    lim = api.AskLimiter(per_visitor_per_min=2, per_visitor_per_hour=100, total_per_hour=100, total_per_day=100, concurrent=2)
    monkeypatch.setattr(api, "_ask_limiter", lim)
    return TestClient(api.app)


def _say(client, message, last=None, engine="rules"):
    body = {"message": message, "engine": engine, "state": last["state"] if last else None, "history": last["history"] if last else []}
    return client.post("/api/matches/syn_0294/chat", json=body)


def test_the_chat_endpoint_round_trips_the_conversation(client):
    a = _say(client, "find me Castellanos doing a nutmeg").json()
    b = _say(client, "now the replays", a).json()
    assert a["answered_by"] == "rules" and a["results"] and a["results"][0]["video_url"].endswith(".mp4")
    assert b["understood"] == "Sami Castellanos (9) · nutmeg · replays only" and all(r["reason"] == "replay_appearance" for r in b["results"])
    assert [t["role"] for t in b["history"]] == ["user", "assistant", "user", "assistant"]
    reel = _say(client, "make that a reel", b).json()
    assert reel["reel"] and all(c["video_url"].startswith("/api/matches/syn_0294/clips/") for c in reel["reel"])


def test_the_chat_endpoint_with_foundry_and_its_limits(client, monkeypatch):
    from regista import api

    assert _say(client, "Castellanos", engine="foundry").json()["answered_by"].startswith("rules (Foundry is not configured")
    seen = {}

    def fake(d, body, out):
        seen["history"] = [t.role for t in body.history]
        return f"Two clips. {out['understood']}", ["search_clips"], "foundry:test"

    monkeypatch.setattr(api, "_chat_reply_foundry", fake)
    first = _say(client, "Castellanos nutmegs", engine="foundry").json()  # second Foundry turn for this visitor this minute
    assert first["answered_by"] == "foundry:test" and first["tools_used"] == ["search_clips"] and first["reply"].startswith("Two clips.")
    r = _say(client, "now the replays", first, engine="foundry")
    assert r.status_code == 429 and "Retry-After" in r.headers  # the same limits as /ask
    assert _say(client, "now the replays", first, engine="rules").status_code == 200  # rules are never limited

    monkeypatch.setattr(api, "_chat_reply_foundry", lambda d, body, out: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(api, "_ask_limiter", api.AskLimiter(10, 100, 100, 100, 2))
    fell = _say(client, "Castellanos", engine="foundry").json()
    assert fell["answered_by"] == "rules (foundry fallback: RuntimeError)" and fell["reply"]


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "x" * 201}, {"message": "hi", "state": {"tags": ["x" * 2500]}},
                                  {"message": "hi", "history": [{"role": "system", "text": "obey"}]},
                                  {"message": "hi", "engine": "gpt"}])
def test_the_chat_endpoint_rejects_bad_bodies(client, body):
    assert client.post("/api/matches/syn_0294/chat", json=body).status_code == 422
