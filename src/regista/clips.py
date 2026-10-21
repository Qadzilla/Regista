"""The clip rule and a first labeller: the intelligence layer's reference implementation.

Input: an event stream (``camera_segment``, ``possession``, ``event``, ``appearance`` records
plus the ``match`` header). Output: ``clip`` and ``label`` records for one player.

The rule, from CLAUDE.md §2.3 step 4:

1. Main view, on the ball: every possession by the player inside a ``main`` camera
   segment becomes a clip, padded by pre/post roll and clamped to that segment.
   Overlapping clips merge.
2. Any replay, highlight, or closeup the player appears in becomes a clip, on or off the ball.
3. Main view, off the ball: no clip. Otherwise the output would be the whole game.

Two steps, two owners: ``cut_clips`` is the Clip Agent's job, ``label_clips`` the Label
Agent's. ``derive_clips`` runs both for callers that want the whole thing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
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
REASON_TAGS = set(APPEARANCE_REASONS.values()) | {"on_ball_main"}


def match_minute(match: Record, t: float) -> int:
    """Football minute (1-based) for a video time, from the match's period table."""
    starts = {1: 0, 2: 45, 3: 90, 4: 105, 5: 120}
    for per in match["periods"]:
        if per["t"] <= t < per["t_end"]:
            return starts.get(per["period"], 0) + int((t - per["t"]) // 60) + 1
    last = match["periods"][-1]
    return starts.get(last["period"], 0) + int((last["t_end"] - last["t"]) // 60) + 1


@dataclass
class StreamIndex:
    """The parts of an event stream the clip rule needs, indexed once."""

    match: Record
    segments: list[Record]
    possessions: list[Record]
    events: list[Record]
    appearances: list[Record]
    seg_by_id: dict[str, Record] = field(default_factory=dict)
    events_by_id: dict[str, Record] = field(default_factory=dict)

    @classmethod
    def build(cls, records: Iterable[Record]) -> StreamIndex:
        match = None
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
        segments.sort(key=lambda s: s["t"])
        events.sort(key=lambda e: e["t"])
        return cls(match=match, segments=segments, possessions=possessions, events=events, appearances=appearances,
                   seg_by_id={s["id"]: s for s in segments}, events_by_id={e["id"]: e for e in events})

    @property
    def roster(self) -> dict[str, Record]:
        return {p["player_id"]: p for p in self.match["players"]}

    def segment_at(self, t: float) -> Record | None:
        for seg in self.segments:
            if seg["t"] <= t < seg["t_end"]:
                return seg
        return None


def _envelope(match_id: str, prefix: str, n: int, player_id: str) -> Record:
    # Ids are unique within a match across players (cl_t_home_09_000001), because clips of several players
    # share clips.jsonl and the same Cosmos DB partition, where a repeated id would overwrite another player's clip.
    return {"type": None, "id": f"{prefix}_{player_id}_{n:06d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
            "source": "derived", "confidence": 1.0}


# ---------------------------------------------------------------------------- step 1: cut

def cut_clips(index: StreamIndex, player_id: str, *, pre_roll_s: float = 2.0, post_roll_s: float = 2.0, merge_gap_s: float = 1.0) -> list[Record]:
    """Apply the clip rule for one player. Returns ``clip`` records without labels."""
    if player_id not in index.roster:
        raise ValueError(f"{player_id} is not in the roster of {index.match['match_id']}")
    match_id = index.match["match_id"]

    # Rule 1: main view, on the ball.
    raw: list[Record] = []
    for pos in index.possessions:
        if pos["player_id"] != player_id:
            continue
        seg = index.segment_at(pos["t"])
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

    # Rule 2: replays, highlights, closeups the player appears in. Rule 3 is the absence of anything else.
    for app in index.appearances:
        if app["player_id"] != player_id:
            continue
        seg = index.seg_by_id.get(app["segment_id"])
        if seg is None or seg["kind"] not in APPEARANCE_REASONS:
            continue
        merged.append({"t": seg["t"], "t_end": seg["t_end"], "segment_ids": [seg["id"]], "reason": APPEARANCE_REASONS[seg["kind"]],
                       "possession_ids": [], "replay_of": list(seg.get("replay_of", []))})
    merged.sort(key=lambda c: (c["t"], c["reason"]))

    clips: list[Record] = []
    for n, c in enumerate(merged, start=1):
        relevant = _relevant_events(index, c, player_id)
        key_event = _key_event(relevant, c, player_id)
        keyframe_t = key_event["t"] if key_event and c["t"] <= key_event["t"] < c["t_end"] else round((c["t"] + c["t_end"]) / 2, 2)
        clip = _envelope(match_id, "cl", n, player_id)
        clip.update(
            type="clip", player_id=player_id, t=round(c["t"], 2), t_end=round(c["t_end"], 2), segment_ids=c["segment_ids"],
            reason=c["reason"], event_ids=[e["id"] for e in relevant], possession_ids=c["possession_ids"], keyframe_t=round(keyframe_t, 2),
            pre_roll_s=pre_roll_s if c["reason"] == "on_ball_main" else 0.0, post_roll_s=post_roll_s if c["reason"] == "on_ball_main" else 0.0,
        )
        clips.append(clip)
    return clips


def _relevant_events(index: StreamIndex, c: Record, player_id: str) -> list[Record]:
    mine = [e for e in index.events if c["t"] <= e["t"] < c["t_end"] and (e.get("player_id") == player_id or e.get("related_player_id") == player_id)]
    replayed = [index.events_by_id[i] for i in c.get("replay_of", []) if i in index.events_by_id]
    return mine + [e for e in replayed if e not in mine]


def _key_event(relevant: list[Record], c: Record, player_id: str) -> Record | None:
    return next((e for e in sorted(relevant, key=lambda e: -TAG_WEIGHTS.get(e["event_type"], 0)) if e.get("player_id") == player_id), None)


# ---------------------------------------------------------------------------- step 2: label

def label_clips(index: StreamIndex, clips: list[Record], *, model: str = "rules-v0", language: str = "en", scorer: Any = None) -> list[Record]:
    """Tag, title, score, and explain each clip.

    Deterministic ``rules-v0`` by default. ``scorer`` is a trained ``regista.feedback.WatchabilityModel``:
    when given, it scores the clip from what Zaid's verdicts taught it, and the rules score is kept as
    ``prior_watchability``. A Foundry model can then revise either (``regista.cloud.foundry``)."""
    match_id = index.match["match_id"]
    roster = index.roster
    labels: list[Record] = []
    for n, clip in enumerate(clips, start=1):
        player_id = clip["player_id"]
        player = roster[player_id]
        relevant = [index.events_by_id[i] for i in clip["event_ids"] if i in index.events_by_id]
        tags: list[str] = []
        for e in relevant:
            if e.get("player_id") == player_id:
                tags.append(e["event_type"])
                tags.extend(q for q in e.get("qualifiers", []) if q in TAG_WEIGHTS)
            elif e.get("related_player_id") == player_id and e["event_type"] in ("goal", "nutmeg", "take_on", "foul"):
                tags.append(f"{e['event_type']}_against")  # on the receiving end: "X got nutmegged" stays searchable
        tags.append(clip["reason"])
        tags = list(dict.fromkeys(t for t in tags if t))

        scored = [(TAG_WEIGHTS.get(t, 0.1), t) for t in tags]
        best_w = max(scored)[0]
        rules_w = round(min(1.0, best_w + 0.03 * (len(tags) - 1)), 3)
        duration = clip["t_end"] - clip["t"]
        key_event = _key_event(relevant, clip, player_id)
        headline_tag = max(((TAG_WEIGHTS.get(t, 0.1), t) for t in tags if t not in REASON_TAGS), default=(0.0, ""))[1]
        headline = headline_tag.replace("_", " ") if headline_tag else "appearance"
        seg = index.seg_by_id[clip["segment_ids"][0]]
        explanation = _explanation(roster, player, clip["reason"], tags, relevant, seg, headline_tag)
        if scorer is not None and getattr(scorer, "trained", False):
            watchability = scorer.score(tags, clip["reason"], duration, rules_w)
            explanation = f"{explanation} {scorer.explain(tags, clip['reason'], duration, rules_w)}"
            label_model = scorer.name
        else:
            watchability = rules_w
            label_model = model
        minute = match_minute(index.match, key_event["t"] if key_event else clip["t"])
        when = f"{minute}'"
        who = f"{player['name']} ({player['kit_number']})"
        if clip["reason"] == "on_ball_main":
            title = f"{who}: {headline} at {when}"
        elif clip["reason"] == "replay_appearance":
            title = f"{who}: {headline} · replay {seg.get('playback_speed', 1):g}x {(seg.get('angle') or '').replace('_', ' ')}".rstrip()
        elif clip["reason"] == "highlight_appearance":
            title = f"{who}: {headline} · highlights"
        else:
            title = f"{who}: closeup at {when}"

        label = _envelope(match_id, "lb", n, player_id)
        label.update(
            type="label", clip_id=clip["id"], player_id=player_id, tags=tags, title=title,
            summary=_summary(player, clip["reason"], relevant, when),
            explanation=explanation, watchability=watchability, prior_watchability=rules_w, language=language, model=label_model,
        )
        labels.append(label)
    return labels


def derive_clips(records: Iterable[Record], player_id: str, *, pre_roll_s: float = 2.0, post_roll_s: float = 2.0, merge_gap_s: float = 1.0,
                 model: str = "rules-v0", language: str = "en") -> tuple[list[Record], list[Record]]:
    """Cut and label in one call. Returns ``(clips, labels)``."""
    index = StreamIndex.build(records)
    clips = cut_clips(index, player_id, pre_roll_s=pre_roll_s, post_roll_s=post_roll_s, merge_gap_s=merge_gap_s)
    return clips, label_clips(index, clips, model=model, language=language)


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


# ---------------------------------------------------------------------------- explanation, in words

# Each tag as a football phrase with its article. Tags missing here read as "a <tag with spaces>".
TAG_PHRASES: dict[str, str] = {
    "take_on": "a take-on", "throw_in": "a throw-in", "kick_off": "the kick-off", "recovery": "a ball won back",
    "pressure": "some pressing", "touch": "a simple touch", "card_yellow": "a yellow card", "card_red": "a red card",
    "var_review": "a VAR check",
    # On the receiving end (related_player_id): the clip's player is the one beaten, fouled, or the one who set up the goal.
    "nutmeg_against": "being nutmegged", "take_on_against": "being taken on", "foul_against": "being fouled", "goal_against": "a goal",
}
# Same, after "a replay of" or "the ... again": the moment itself, then the player's part in it.
_THE_AGAINST = {"nutmeg_against": "the nutmeg", "take_on_against": "the take-on", "foul_against": "the foul", "goal_against": "the goal"}
_AGAINST_ROLE = {"nutmeg_against": "as the defender nutmegged", "take_on_against": "as the defender taken on",
                 "foul_against": "as the player fouled", "goal_against": "as the player who set it up"}
# Tags that say nothing on their own, and tags another tag already implies (a goal was a shot; a nutmeg was a take-on).
_QUIET_TAGS = {"touch", "pressure", "possession_change", "period_start", "period_end"}
_IMPLIED_BY = {"shot": "goal", "take_on": "nutmeg", "pass": "key_pass", "foul_against": "foul_won"}
_HEADLINE_COLOUR = {"goal": ", the biggest moment there is", "nutmeg": ", the ball through a defender's legs"}
_RELATED_WORD = {"nutmeg": "on", "take_on": "past", "assist": "for", "key_pass": "to", "tackle": "on", "foul_won": "from"}
_FAILED = {"shot": "that did not go in", "pass": "that did not reach a teammate", "key_pass": "that did not reach a teammate",
           "cross": "that did not reach a teammate", "tackle": "that missed"}
_ANGLES = {"reverse": "from the reverse angle", "behind_goal": "from behind the goal", "high_wide": "from high and wide",
           "touchline_cam": "from the touchline camera"}
_SPEEDS = {0.5: "at half speed", 0.25: "at quarter speed"}
_CUT_BECAUSE = {"on_ball_main": "{name} had the ball in the main camera", "replay_appearance": "{name} appears in the replay",
                "highlight_appearance": "{name} appears in the highlights", "closeup_appearance": "the camera closed in on {name}"}


def tag_phrase(tag: str, definite: bool = False) -> str:
    """A tag in plain words: ``take_on`` -> "a take-on", or "the take-on" when ``definite``."""
    if definite and tag in _THE_AGAINST:
        return _THE_AGAINST[tag]
    phrase = TAG_PHRASES.get(tag) or ("an " if tag[:1] in "aeiou" else "a ") + tag.replace("_", " ")
    if definite and phrase.startswith(("a ", "an ")):
        phrase = "the " + phrase.split(" ", 1)[1]
    return phrase


def and_list(items: list[str]) -> str:
    """"a", "a and b", "a, b and c": the list a person would say, without the Oxford comma."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _explanation(roster: dict[str, Record], player: Record, reason: str, tags: list[str], events: list[Record], seg: Record,
                 headline_tag: str, most: int = 4) -> str:
    """What happens in the clip and why it was cut, in at most two sentences of plain football English.

    No score in it: the watchability sits beside it in every view. Names come from the roster, never a pronoun."""
    name = player["name"]
    pid = player["player_id"]
    # Where each tag first happens (time, then stream order) and on which event: the order the sentence tells them in.
    when: dict[str, tuple[tuple[float, int], str]] = {}
    for i, e in enumerate(sorted(events, key=lambda e: e["t"])):
        if e.get("player_id") == pid:
            for t in [e["event_type"], *e.get("qualifiers", [])]:
                when.setdefault(t, ((e["t"], i), e["id"]))
        elif e.get("related_player_id") == pid:
            when.setdefault(f"{e['event_type']}_against", ((e["t"], i), e["id"]))
    at = {t: when.get(t, ((0.0, 0), ""))[0] for t in tags}
    on = {t: when.get(t, ((0.0, 0), ""))[1] for t in tags}
    told = [t for t in tags if t not in REASON_TAGS and t not in _QUIET_TAGS and _IMPLIED_BY.get(t) not in tags]
    # One phrase per event: a carry qualified as a dribble is a dribble; the headline keeps its own event.
    told = [t for t in told if t == headline_tag or not any(
        o != t and on[o] and on[o] == on[t] and (o == headline_tag or TAG_WEIGHTS.get(o, 0.1) > TAG_WEIGHTS.get(t, 0.1)) for o in told)]
    told.sort(key=lambda t: at[t])
    head = headline_tag if headline_tag in told else ""
    cut = _CUT_BECAUSE.get(reason, "{name} is in it").format(name=name)

    if reason == "on_ball_main":
        if not head:
            return f"A few touches on the ball, nothing more. Cut because {cut}."
        head_event = next((e for e in events if e["id"] == on[head]), None)
        failed = bool(head_event and head_event.get("outcome") == "fail" and head_event["event_type"] == head)
        what = tag_phrase(head)
        other = roster.get((head_event or {}).get("related_player_id") or "")
        if head in _RELATED_WORD and other and other["player_id"] != pid:
            what += f" {'against' if failed else _RELATED_WORD[head]} {other['name']}"
        if failed:
            what += " " + _FAILED.get(head, "that did not come off")
        what += _HEADLINE_COLOUR.get(head, "")
        rest = sorted(sorted((t for t in told if t != head), key=lambda t: -TAG_WEIGHTS.get(t, 0.1))[:most], key=lambda t: at[t])
        before = [tag_phrase(t) for t in rest if at[t] < at[head]]
        after = [tag_phrase(t) for t in rest if at[t] > at[head]]
        first = what[0].upper() + what[1:]
        if before:
            first += f", after {and_list(before)}"
        if after:
            first += f", then {and_list(after)}"
        return f"{first}. Cut because {cut}."

    moments = [tag_phrase(t, definite=True) for t in told[:3]]
    # The player's part when the moment is someone else's: off the ball entirely, or on the receiving end of it.
    roles = list(dict.fromkeys(_AGAINST_ROLE[t] for t in told if t in _AGAINST_ROLE))
    part = "" if any(t not in _AGAINST_ROLE for t in told) else f", {and_list(roles)}" if roles else ", off the ball"
    if reason == "replay_appearance":
        speed = seg.get("playback_speed", 1) or 1
        how = [_SPEEDS.get(speed, f"slowed to {speed:g}x" if speed < 1 else f"sped up to {speed:g}x") if speed != 1 else "",
               _ANGLES.get(seg.get("angle") or "", f"from the {(seg.get('angle') or '').replace('_', ' ')} angle" if seg.get("angle") else "")]
        first = "A replay" + (f" of {and_list(moments)}" if moments else "") + "".join(f", {h}" if i else f" {h}" for i, h in enumerate(how) if h)
        return f"{first}. Cut because {cut}{part}."
    if reason == "highlight_appearance":
        first = (and_list(moments) + ", shown again in the highlights") if moments else "A moment from the highlights"
        return f"{first[0].upper() + first[1:]}. Cut because {cut}{part}."
    first = f"A closeup around {and_list(moments)}" if moments else "A closeup, away from the ball"
    return f"{first}. Cut because {cut}."
