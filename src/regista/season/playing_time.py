"""Time on the pitch, from an event stream.

Substitutions and red cards (schema 0.2.0, the league's generator in league mode) end or start a player's spell; a stream
without them (every 0.1.x stream: the committed samples, uploads, claims) gives each starter the whole match, exactly the
sum of the period lengths it always counted.
"""

from __future__ import annotations

from typing import Any

Record = dict[str, Any]


def played_seconds(stream: list[Record]) -> dict[str, float]:
    """player id -> seconds on the pitch (video time inside the periods), for every player who played. Starters are on
    from the start; a ``substitution`` (player off in ``player_id``, on in ``related_player_id``) and a ``card_red`` end
    or start a spell. Without either (every 0.1.x stream) each starter gets exactly the sum of the period lengths."""
    header = stream[0]
    periods = header.get("periods", [])
    start: dict[str, float] = {p["player_id"]: 0.0 for p in header.get("players", []) if p.get("starter")}
    end: dict[str, float] = {}
    for e in stream:
        if e.get("type") != "event":
            continue
        if e["event_type"] == "substitution" and e.get("player_id") and e.get("related_player_id"):
            end.setdefault(e["player_id"], e["t"])
            start.setdefault(e["related_player_id"], e["t"])
        elif e["event_type"] == "card_red" and e.get("player_id"):
            end.setdefault(e["player_id"], e["t"])
    out = {}
    for pid, t0 in start.items():
        t1 = end.get(pid)
        out[pid] = sum(p["t_end"] - p["t"] for p in periods) if t1 is None and t0 == 0.0 else \
            sum(max(0.0, min(p["t_end"], t1 if t1 is not None else p["t_end"]) - max(p["t"], t0)) for p in periods)
    return out
