"""A conversation with the Librarian: plan step 7, "a chatbot that finds clips".

The Librarian's parser (``regista.librarian.parse_query``) understands one message. This module keeps the query a
conversation has built so far and merges each follow-up into it, the way a producer talks to an editor:

    "find me Castellanos doing a nutmeg"   player Castellanos, tag nutmeg
    "now the replays"                      ... only replays
    "and in the second half?"              ... minutes 46-90
    "what about Ibarra?"                   same filters, another player
    "also shots"                           ... nutmeg or shot
    "show me more"                         the next page of the same search
    "make that a reel"                     the current results, best first, as a playlist
    "start over"                           an empty query

Rules, in order: a player named in the message replaces the player ("he", "his", "that player" keep it); tags,
replay/highlight filters and minutes in the message replace the old ones unless the message says "also", "and",
"plus" or "too"; "anything", "every angle", "whole match" and "all of them" clear a filter. The merged state is a
plain dict (``EMPTY`` shape), returned to the client and sent back with the next message, so the server keeps
nothing between turns. ``describe`` says in words how the conversation is understood, so the answer is always
checkable.

Every turn also returns a ``trace``: the in-process steps it ran (merge the message, search the clips), each with its
measured time in ms. The rule-based engine calls no model and no MCP server, and its trace says only what it did.
"""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from regista.librarian import _load, _normalise, parse_query, search_parsed

Record = dict[str, Any]
EMPTY: Record = {"player_ids": [], "team_id": None, "tags": [], "reasons": [], "minutes": None, "limit": None, "offset": 0}
PAGE = 6
REEL_MAX = 8
REASONS = {"on_ball_main", "replay_appearance", "highlight_appearance", "closeup_appearance"}
INTERNAL_TAGS = REASONS | {"touch", "possession_change", "kick_off", "period_start", "period_end", "goal_against", "nutmeg_against",
                           "take_on_against", "foul_against"}

KEEP_PLAYER = re.compile(r"\b(he|his|him|himself|she|her|hers|they|them|their|same player|that player|this player)\b")
ADD = re.compile(r"\b(also|and|plus|as well|too|add)\b")
RESET = re.compile(r"\b(start over|start again|new search|reset|forget (that|it|all that)|clear (it|that|everything))\b")
MORE = re.compile(r"^(?:ok |okay |and |now )?(?:show (?:me )?|give (?:me )?)?(?:some |any )?(more|next|others?|the rest|keep going)\b")
REEL = re.compile(r"\b(reel|montage|compilation|playlist|play (?:them|those|these|it|all|that)|watch (?:them|those|these|all))\b")
ANY_TAG = re.compile(r"\b(any ?thing|every ?thing|any moments?|all (?:his|her|their|the) (?:moments|clips|touches))\b")
ALL_ANGLES = re.compile(r"\b(all angles|every angle|any angle|including replays|replays too)\b")
LIVE_ONLY = re.compile(r"\b(live (?:only|action)|main (?:view|camera)|no replays|on the ball only|only on the ball)\b")
WHOLE = re.compile(r"\b(whole (?:match|game)|all (?:match|game)|any ?time|full (?:match|game))\b")
ALL_RESULTS = re.compile(r"\b(all of them|every one|all clips)\b")


def timed_step(trace: list[Record], name: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Run one in-process step and append it to ``trace`` as {name, kind: "step", server: None, ms}."""
    t0 = time.perf_counter()
    try:
        return fn(*args)
    finally:
        trace.append({"name": name, "kind": "step", "server": None, "ms": round((time.perf_counter() - t0) * 1000, 1)})


def step(message: str, state: Record | None, match: Record) -> Record:
    """Merge one message into the conversation's query. Returns {"state", "intent", "parsed"}; intent is
    ``search``, ``more`` (next page), ``reel`` (play the current results) or ``reset``."""
    text = _normalise(message)
    parsed = parse_query(message, match)
    new = copy.deepcopy(clean_state(state, match))
    names_something = bool(parsed["player_ids"] or parsed["team_id"] or parsed["tags"] or parsed["reasons"] or parsed["minutes"])
    if RESET.search(text):
        new = copy.deepcopy(EMPTY)
        intent = "reset" if not names_something else "search"
    elif REEL.search(text) and not names_something:
        return {"state": new, "intent": "reel", "parsed": parsed}
    elif MORE.search(text) and not names_something:
        new["offset"] = int(new.get("offset") or 0) + int(new.get("limit") or PAGE)
        return {"state": new, "intent": "more", "parsed": parsed}
    else:
        intent = "search"
    new["offset"] = 0
    adding = bool(ADD.search(text))
    if parsed["player_ids"]:
        new["player_ids"], new["team_id"] = parsed["player_ids"], parsed["team_id"]
    elif parsed["team_id"] and not KEEP_PLAYER.search(text):
        new["player_ids"], new["team_id"] = [], parsed["team_id"]
    everything = bool(ANY_TAG.search(text)) and not parsed["tags"]
    if parsed["tags"]:
        new["tags"] = sorted(set(new["tags"]) | set(parsed["tags"])) if adding else parsed["tags"]
    elif everything:
        new["tags"] = []
    if everything and not parsed["reasons"]:
        new["reasons"] = []  # "everything he did" means every angle too
    elif parsed["reasons"]:
        new["reasons"] = sorted(set(new["reasons"]) | set(parsed["reasons"])) if adding else parsed["reasons"]
    elif LIVE_ONLY.search(text):
        new["reasons"] = ["on_ball_main"]
    elif ALL_ANGLES.search(text):
        new["reasons"] = []
    if parsed["minutes"]:
        new["minutes"] = parsed["minutes"]
    elif WHOLE.search(text):
        new["minutes"] = None
    if parsed["limit"]:
        new["limit"] = parsed["limit"]
    elif ALL_RESULTS.search(text):
        new["limit"] = None
    return {"state": new, "intent": intent, "parsed": parsed}


def clean_state(state: Record | None, match: Record) -> Record:
    """A state from a client is untrusted: keep only known players, tags, reasons and sane numbers."""
    from regista.clips import REASON_TAGS, TAG_WEIGHTS

    if not state:
        return copy.deepcopy(EMPTY)
    roster = {p["player_id"] for p in match["players"]}
    teams = {t["team_id"] for t in match["teams"]}
    known_tags = set(TAG_WEIGHTS) | set(REASON_TAGS)
    minutes = state.get("minutes")
    ok_minutes = (isinstance(minutes, (list, tuple)) and len(minutes) == 2 and all(isinstance(m, int) and 0 <= m <= 200 for m in minutes))
    limit = state.get("limit")
    offset = state.get("offset") or 0
    return {
        "player_ids": [p for p in (state.get("player_ids") or [])[:22] if p in roster],
        "team_id": state.get("team_id") if state.get("team_id") in teams else None,
        "tags": [t for t in (state.get("tags") or [])[:10] if t in known_tags],
        "reasons": [r for r in (state.get("reasons") or [])[:4] if r in REASONS],
        "minutes": list(minutes) if ok_minutes else None,
        "limit": limit if isinstance(limit, int) and 1 <= limit <= 50 else None,
        "offset": offset if isinstance(offset, int) and 0 <= offset <= 500 else 0,
    }


def as_query(state: Record, match: Record) -> Record:
    """The state in the shape ``search_parsed`` takes."""
    names = {p["player_id"]: p["name"] for p in match["players"]}
    ids = state["player_ids"]
    return {"player_ids": ids, "player_id": ids[0] if len(ids) == 1 else None, "player": " / ".join(names[i] for i in ids) or None,
            "player_how": None, "team_id": state["team_id"], "tags": state["tags"], "reasons": state["reasons"],
            "minutes": state["minutes"], "limit": state["limit"], "unparsed": []}


def describe(state: Record, match: Record) -> str:
    """How the conversation is understood, in a line: who, what, which angles, when, how many."""
    players = {p["player_id"]: p for p in match["players"]}
    teams = {t["team_id"]: t for t in match["teams"]}
    who = ", ".join(f"{players[i]['name']} ({players[i]['kit_number']})" for i in state["player_ids"]) \
        or (f"anyone at {teams[state['team_id']]['name']}" if state["team_id"] else "any player")
    parts = [who, " + ".join(t.replace("_", " ") for t in state["tags"]) or "any moment"]
    if state["reasons"]:
        parts.append(" + ".join({"on_ball_main": "live on the ball", "replay_appearance": "replays", "highlight_appearance": "highlights",
                                 "closeup_appearance": "close-ups"}[r] for r in state["reasons"]) + " only")
    if state["minutes"]:
        parts.append(f"minutes {state['minutes'][0]}-{state['minutes'][1]}")
    if state["limit"]:
        parts.append(f"top {state['limit']}")
    return " · ".join(parts)


def chat_turn(match_dir: str | Path, message: str, state: Record | None) -> Record:
    """One rule-based turn: merge the message, search, and write the reply. Returns {"reply", "results",
    "understood", "state", "intent", "reel", "total", "trace"}."""
    trace: list[Record] = []
    match, _stream, _clips, _labels = timed_step(trace, "librarian.load_match", _load, str(match_dir))
    turn = timed_step(trace, "conversation.step", step, message, state, match)
    st = turn["state"]
    if turn["intent"] == "reset":
        return {"reply": "Starting over. Who and what are you looking for?", "results": [], "understood": describe(st, match),
                "state": st, "intent": "reset", "reel": [], "total": 0, "trace": trace}
    if turn["intent"] == "reel":
        out = timed_step(trace, "librarian.search_clips", search_parsed, match_dir, {**as_query(st, match), "limit": REEL_MAX}, REEL_MAX, 0)
        reel = [r["clip_id"] for r in out["results"]]
        reply = (f"Here is a reel of {len(reel)} clip(s), best first: {describe(st, match)}." if reel
                 else "There is nothing to put in a reel yet. Ask for a player or a moment first.")
        return {"reply": reply, "results": out["results"], "understood": describe(st, match), "state": st, "intent": "reel",
                "reel": reel, "total": out["total"], "trace": trace}
    parsed = turn["parsed"]
    recognised = any(parsed[k] for k in ("player_ids", "team_id", "tags", "reasons", "minutes", "limit"))
    if turn["intent"] == "search" and not recognised and parsed["unparsed"] and not (st["player_ids"] or st["team_id"]):
        return {"reply": f"I didn't catch who you mean ({' '.join(parsed['unparsed'])}). Try a surname, a kit number, or a role like "
                         "'the home striker'.", "results": [], "understood": describe(st, match), "state": st, "intent": "search",
                "reel": [], "total": 0, "trace": trace}
    page = st["limit"] or PAGE
    out = timed_step(trace, "librarian.search_clips", search_parsed, match_dir, as_query(st, match), page, st["offset"])
    results, total = out["results"], out["total"]
    if turn["intent"] == "more" and not results:
        reply = f"That's all of them: {total} clip(s) for {describe(st, match)}."
    elif results:
        best = results[0]
        shown_to = st["offset"] + len(results)
        reply = (f"{total} clip(s) for {describe(st, match)}" + (" (no clip has every tag; showing the closest)" if out["relaxed"] else "")
                 + (f". Showing {st['offset'] + 1}-{shown_to}" if turn["intent"] == "more" else "")
                 + f". Best: {best['title']} ({best['minute']}')."
                 + (f" Say \"more\" for the next {min(page, total - shown_to)}." if total > shown_to else ""))
    elif not st["player_ids"] and not st["team_id"] and turn["parsed"]["unparsed"]:
        reply = f"I didn't catch who you mean ({' '.join(turn['parsed']['unparsed'])}). Try a surname, a kit number, or a role like 'the home striker'."
    else:
        reply = f"No clips for {describe(st, match)}."
        if st["tags"]:  # say what the same player(s) do have, in football words
            loose = timed_step(trace, "librarian.search_clips", search_parsed, match_dir, {**as_query(st, match), "tags": [], "limit": 200},
                               200, 0)
            have = sorted({t for r in loose["results"] for t in r["tags"]} - INTERNAL_TAGS - set(st["tags"]))
            if have:
                reply += " With the same filters there are: " + ", ".join(t.replace("_", " ") for t in have) + "."
    return {"reply": reply, "results": results, "understood": describe(st, match), "state": st, "intent": turn["intent"],
            "reel": [], "total": total, "trace": trace}
