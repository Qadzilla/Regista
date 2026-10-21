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
             "minutes": [1, 9999], "limit": 10_000, "offset": -4, "order": "<b>"}
    assert clean_state(dirty, MATCH) == {"player_ids": ["t_home_09"], "team_id": None, "tags": ["nutmeg"], "reasons": ["replay_appearance"],
                                         "minutes": None, "limit": None, "offset": 0, "order": None}
    assert describe(clean_state(dirty, MATCH), MATCH) == "Sami Castellanos (9) · nutmeg · replays only"


def test_replies_say_what_exists_when_nothing_matches():
    out = chat_turn(MATCH_DIR, "Ibarra shots", None)
    assert out["results"] == [] and out["reply"].startswith("No moments for Ivan Ibarra (10) · shot.")
    assert "pass" in out["reply"] and "on_ball_main" not in out["reply"] and "touch" not in out["reply"]
    assert "didn't catch who" in chat_turn(MATCH_DIR, "find me zzqx doing it", None)["reply"]
    reel = chat_turn(MATCH_DIR, "make that a reel", chat_turn(MATCH_DIR, "Castellanos", None)["state"])
    assert reel["intent"] == "reel" and 1 <= len(reel["reel"]) <= 8


def _chat(*messages, state=None):
    outs = []
    for m in messages:
        outs.append(chat_turn(MATCH_DIR, m, state))
        state = outs[-1]["state"]
    return outs


def test_replies_say_moments_and_each_minute_once():
    """Audit J3 S4: "3 clip(s) ... Best: Sami Castellanos (9): goal at 1' (1')" becomes "3 moments ... Best: goal at 1'"."""
    (nutmeg,) = _chat("Find me Sami Castellanos doing a nutmeg")
    assert nutmeg["reply"] == "3 moments for Sami Castellanos (9) · nutmeg. Best: goal at 1'."
    (replays,) = _chat("now the replays", state=nutmeg["state"])
    clip = replays["results"][0]
    assert clip["reason"] == "replay_appearance" and replays["reply"].endswith(f": nutmeg · half-speed replay from high and wide, at {clip['minute']}'.")
    for out in (nutmeg, replays, *_chat("Castellanos", "more", "more")):
        assert "clip" not in out["reply"] and not out["reply"].count("(1')"), out["reply"]


def test_match_order_returns_every_moment_and_offers_no_more():
    """Audit J3 S4: "Every touch ... in match order" showed 11 in order while the reply said 'Say "more" for the next 5'."""
    (out,) = _chat("Every touch by Castellanos, in match order")
    assert out["total"] == len(out["results"]) == 11 and "more" not in out["reply"] and "in match order" in out["reply"]
    assert [r["t"] for r in out["results"]] == sorted(r["t"] for r in out["results"])
    replays, more, best = _chat("now the replays", "more", "best first", state=out["state"])
    assert replays["state"]["order"] == "time" and len(replays["results"]) == replays["total"]  # the order carries over
    assert more["results"] == [] and more["reply"].startswith("That's all of them")
    assert best["state"]["order"] is None


def test_a_reel_request_says_it_makes_a_reel():
    """Audit J3 S4: "Make a reel of Castellanos's best moments" replied with the search sentence and never named the reel."""
    (out,) = _chat("Make a reel of Castellanos's best moments")
    assert out["intent"] == "reel" and len(out["reel"]) == 8 and out["reel"] == [r["clip_id"] for r in out["results"]]
    assert out["reply"].startswith("Here is a reel of the best 8 of 11 moments for Sami Castellanos (9)") and "goal at 1'" in out["reply"]


def test_filters_that_leave_nothing_say_so_and_offer_the_way_out():
    """Audit J3 S1: nutmeg -> replays -> Ibarra left "No clips for Ivan Ibarra (10) · nutmeg · replays only." and a reel request
    that said to ask first. Now the reply names the filters, counts the moments without them, and ``suggest`` clears them."""
    a, b, ibarra, reel, reset = _chat("Find me Sami Castellanos doing a nutmeg", "now the replays", "what about Ibarra?",
                                      "make that a reel", "start over")
    assert ibarra["results"] == [] and ibarra["reply"].startswith("No moments for Ivan Ibarra (10) · nutmeg · replays only.")
    assert "Without those filters (nutmeg, replays only), Ivan Ibarra has 5 moments" in ibarra["reply"]
    sg = ibarra["suggest"]
    assert sg["clears"] == ["tags", "reasons"] and sg["total"] == 5 and sg["label"] == "Show all 5 moments of Ivan Ibarra"
    for state in (sg["state"], ibarra["state"]):  # the message alone clears the filters; its state too
        after = chat_turn(MATCH_DIR, sg["message"], state)
        assert after["total"] == 5 and after["state"]["player_ids"] == ["t_home_10"] and not after["state"]["tags"] + after["state"]["reasons"]
    assert reel["intent"] == "reel" and reel["reel"] == [] and "nutmeg · replays only" in reel["reply"] and reel["suggest"] == sg
    assert "Ask for a player" not in reel["reply"]
    assert reset["state"] == EMPTY and reset["results"] == [] and reset["reel"] == [] and "suggest" not in reset
    assert "suggest" not in a and "suggest" not in b
    (minutes,) = _chat("Ibarra nutmegs in the first 2 minutes")
    assert minutes["suggest"]["clears"] == ["tags", "minutes"] and "whole match" in minutes["suggest"]["message"]
    assert chat_turn(MATCH_DIR, minutes["suggest"]["message"], minutes["state"])["total"] == 5


def test_the_suggestion_keeps_the_player_when_a_first_name_is_shared():
    """Fix K3's find: "everything by Ivan Brennan" was read as Ivan Ibarra (the first known name part wins), so the
    suggestion names nobody and the state carries the player."""
    names = {p["player_id"]: p["name"] for p in MATCH["players"]}
    assert names["t_away_01"].split()[0] == names["t_home_10"].split()[0]  # two players share a first name
    (out,) = _chat("nutmegs", state={**EMPTY, "player_ids": ["t_away_01"]})
    sg = out["suggest"]
    assert names["t_away_01"] not in sg["message"] and sg["state"]["player_ids"] == ["t_away_01"]
    for state in (sg["state"], out["state"]):
        after = chat_turn(MATCH_DIR, sg["message"], state)
        assert after["state"]["player_ids"] == ["t_away_01"] and after["total"] == sg["total"]


def test_the_titles_people_read_in_replies():
    """Audit J3 S2/S9: the assister is not "goal against"; replays and take-ons in plain words."""
    (ibarra,) = _chat("every touch by Ibarra")
    titles = [r["title"] for r in ibarra["results"]]
    assert "Ivan Ibarra (10): assist · half-speed replay from high and wide" in titles and not any("against" in t for t in titles)
    (take_ons,) = _chat("Castellanos take-ons")
    assert "take-on" in take_ons["reply"] and "take on" not in take_ons["reply"]


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
