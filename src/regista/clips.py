"""The clip rule and a first labeller: the intelligence layer's reference implementation.

Input: an event stream (``camera_segment``, ``possession``, ``event``, ``appearance`` records
plus the ``match`` header). Output: ``clip`` and ``label`` records for one player.

The rule, from CLAUDE.md §2.3 step 4:

1. Main view, on the ball: every possession by the player inside a ``main`` camera
   segment becomes a clip, padded by pre/post roll and clamped to that segment.
   Overlapping clips merge.
2. Any replay, highlight, or closeup the player appears in becomes a clip, on or off the ball.
3. Main view, off the ball: no clip. Otherwise the output would be the whole game.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from regista.schema import SCHEMA_VERSION

Record = dict[str, Any]

# Watchability weights per tag. The labeller takes the strongest tag and adds a small
# bonus for richness. A learned model replaces this table later; the schema does not change.
TAG_WEIGHTS: dict[str, float] = {
    "goal": 1.0,
    "nutmeg": 0.95,
    "assist": 0.85,
    "skill_move": 0.8,
    "penalty": 0.8,
    "shot": 0.7,
    "save": 0.65,
    "take_on": 0.6,
    "key_pass": 0.55,
    "highlight_appearance": 0.5,
    "cross": 0.45,
    "tackle": 0.45,
    "foul_won": 0.4,
    "interception": 0.4,
    "dribble": 0.4,
    "block": 0.35,
    "replay_appearance": 0.35,
    "carry": 0.3,
    "recovery": 0.3,
    "free_kick": 0.3,
    "corner": 0.3,
    "header": 0.3,
    "clearance": 0.25,
    "closeup_appearance": 0.2,
    "pass": 0.2,
    "pressure": 0.15,
    "throw_in": 0.1,
    "touch": 0.1,
}

APPEARANCE_REASONS = {
    "replay": "replay_appearance",
    "highlight": "highlight_appearance",
    "closeup": "closeup_appearance",
}


def _overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return a0 < b1 and b0 < a1


def derive_clips(
    records: Iterable[Record],
    player_id: str,
    *,
    pre_roll_s: float = 2.0,
    post_roll_s: float = 2.0,
    merge_gap_s: float = 1.0,
    model: str = "rules-v0",
    language: str = "en",
) -> tuple[list[Record], list[Record]]:
    """Apply the clip rule for ``player_id`` and label each clip. Returns ``(clips, labels)``."""
    match: Record | None = None
    segments: list[Record] = []
    possessions: list[Record] = []
    events: list[Record] = []
    appearances: list[Record] = []
    for rec in records:
        t = rec.get("type")
        if t == "match":
            match = rec
        elif t == "camera_segment":
            segments.append(rec)
        elif t == "possession":
            possessions.append(rec)
        elif t == "event":
            events.append(rec)
        elif t == "appearance":
            appearances.append(rec)
    if match is None:
        raise ValueError("event stream has no match header")

    match_id = match["match_id"]
    roster = {p["player_id"]: p for p in match["players"]}
    if player_id not in roster:
        raise ValueError(f"{player_id} is not in the roster of {match_id}")
    player = roster[player_id]
    segments.sort(key=lambda s: s["t"])
    events.sort(key=lambda e: e["t"])

    def envelope(prefix: str, n: int) -> Record:
        return {
            "type": None,
            "id": f"{prefix}_{n:06d}",
            "match_id": match_id,
            "schema_version": SCHEMA_VERSION,
            "source": "derived",
            "confidence": 1.0,
        }

    def segment_at(t: float) -> Record | None:
        for seg in segments:
            if seg["t"] <= t < seg["t_end"]:
                return seg
        return None

    # --- rule 1: main view, on the ball -------------------------------------------------
    raw: list[Record] = []
    for pos in possessions:
        if pos["player_id"] != player_id:
            continue
        seg = segment_at(pos["t"])
        if seg is None or seg["kind"] != "main":
            continue
        t0 = max(seg["t"], pos["t"] - pre_roll_s)
        t1 = min(seg["t_end"], pos["t_end"] + post_roll_s)
        if t1 <= t0:
            continue
        raw.append({"t": t0, "t_end": t1, "segment_ids": [seg["id"]], "reason": "on_ball_main", "possession_ids": [pos["id"]]})
    raw.sort(key=lambda c: c["t"])
    merged: list[Record] = []
    for c in raw:
        if merged and c["t"] <= merged[-1]["t_end"] + merge_gap_s and merged[-1]["segment_ids"] == c["segment_ids"]:
            merged[-1]["t_end"] = max(merged[-1]["t_end"], c["t_end"])
            merged[-1]["possession_ids"] += c["possession_ids"]
        else:
            merged.append(c)

    # --- rule 2: replays, highlights, closeups the player appears in ----------------------
    seg_by_id = {s["id"]: s for s in segments}
    for app in appearances:
        if app["player_id"] != player_id:
            continue
        seg = seg_by_id.get(app["segment_id"])
        if seg is None or seg["kind"] not in APPEARANCE_REASONS:
            continue
        merged.append(
            {
                "t": seg["t"],
                "t_end": seg["t_end"],
                "segment_ids": [seg["id"]],
                "reason": APPEARANCE_REASONS[seg["kind"]],
                "possession_ids": [],
                "replay_of": list(seg.get("replay_of", [])),
            }
        )
    merged.sort(key=lambda c: (c["t"], c["reason"]))

    # --- attach events, keyframes, labels -------------------------------------------------
    events_by_id = {e["id"]: e for e in events}
    clips: list[Record] = []
    labels: list[Record] = []
    for n, c in enumerate(merged, start=1):
        mine = [
            e
            for e in events
            if c["t"] <= e["t"] < c["t_end"] and (e.get("player_id") == player_id or e.get("related_player_id") == player_id)
        ]
        replayed = [events_by_id[i] for i in c.get("replay_of", []) if i in events_by_id]
        relevant = mine + [e for e in replayed if e not in mine]

        tags: list[str] = []
        for e in relevant:
            if e.get("player_id") == player_id:
                tags.append(e["event_type"])
                tags.extend(q for q in e.get("qualifiers", []) if q in TAG_WEIGHTS)
            elif e.get("related_player_id") == player_id and e["event_type"] in ("goal", "nutmeg", "take_on", "foul"):
                # Player was on the receiving end: still worth tagging so "X got nutmegged" is searchable.
                tags.append(f"{e['event_type']}_against")
        tags.append(c["reason"])
        tags = list(dict.fromkeys(t for t in tags if t))  # dedupe, keep order

        scored = [(TAG_WEIGHTS.get(t, 0.1), t) for t in tags]
        best_w, best_tag = max(scored)
        watchability = round(min(1.0, best_w + 0.03 * (len(tags) - 1)), 3)

        key_event = next((e for e in sorted(relevant, key=lambda e: -TAG_WEIGHTS.get(e["event_type"], 0)) if e.get("player_id") == player_id), None)
        keyframe_t = key_event["t"] if key_event and c["t"] <= key_event["t"] < c["t_end"] else round((c["t"] + c["t_end"]) / 2, 2)

        clip = envelope("cl", n)
        clip.update(
            type="clip",
            player_id=player_id,
            t=round(c["t"], 2),
            t_end=round(c["t_end"], 2),
            segment_ids=c["segment_ids"],
            reason=c["reason"],
            event_ids=[e["id"] for e in relevant],
            possession_ids=c["possession_ids"],
            keyframe_t=round(keyframe_t, 2),
            pre_roll_s=pre_roll_s if c["reason"] == "on_ball_main" else 0.0,
            post_roll_s=post_roll_s if c["reason"] == "on_ball_main" else 0.0,
        )
        clips.append(clip)

        headline = best_tag.replace("_", " ")
        clock = key_event.get("clock") if key_event else None
        when = f"{clock['minute']}'" if clock else f"{int(c['t'] // 60)}:{int(c['t'] % 60):02d} video time"
        label = envelope("lb", n)
        label.update(
            type="label",
            clip_id=clip["id"],
            player_id=player_id,
            tags=tags,
            title=f"{player['name']} ({player['kit_number']}): {headline} at {when}",
            summary=_summary(player, c["reason"], relevant, when),
            explanation=(
                f"Scored {watchability:.2f}: strongest tag '{best_tag}' weighs {best_w:.2f}, "
                f"plus {len(tags) - 1} supporting tag(s). Reason for the cut: {c['reason'].replace('_', ' ')}."
            ),
            watchability=watchability,
            language=language,
            model=model,
        )
        labels.append(label)

    return clips, labels


def _summary(player: Record, reason: str, events: list[Record], when: str) -> str:
    name = player["name"]
    if reason != "on_ball_main":
        what = reason.split("_")[0]
        types = sorted({e["event_type"] for e in events if e.get("player_id") == player["player_id"]})
        if types:
            return f"{name} appears in a {what} of: {', '.join(t.replace('_', ' ') for t in types)}."
        return f"{name} appears in a {what} segment."
    verbs = []
    for e in events:
        if e.get("player_id") != player["player_id"]:
            continue
        et = e["event_type"]
        if et in ("touch", "possession_change", "pressure"):
            continue
        outcome = e.get("outcome", "neutral")
        verbs.append(et.replace("_", " ") + ("" if outcome == "neutral" else f" ({outcome})"))
    if not verbs:
        return f"{name} on the ball at {when}."
    return f"{name} on the ball at {when}: " + ", ".join(verbs[:6]) + ("..." if len(verbs) > 6 else "") + "."
