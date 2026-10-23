"""The match recap (CLAUDE.md §2.7): a headline, a few short paragraphs and a reel, every sentence citing its moment.

    python -m regista.recap data/synthetic/sample/syn_0294                      # the match
    python -m regista.recap data/synthetic/sample/syn_0294 --player t_home_09   # told from one player's side

One set of **facts** is read from the event stream and the labelled clips (``prepare``): the score, the goals with
scorer, assister and minute, the best chances that did not go in and who saved them, who stood out, and, for a recap
told from a player's side, that player's part: their goals, the goals they set up, their best moments, their replays.
Every fact carries a **ref** ("G1", "C2", "M1") that resolves to real clips and events of the match.

Two engines write from the same facts, in one shape (``write``):

- **rules**: plain sentences built here, deterministic, no model.
- **foundry**: a Microsoft Foundry model (Agent Framework, ``regista.cloud.foundry.foundry_recap_text``) writes the
  headline and paragraphs as JSON, each sentence listing the refs it relies on. Nothing it writes is shown unchecked
  (``check_written``): a sentence that cites no known ref, uses a number the facts do not hold, or slips into jargon or
  ids is dropped, and ``checked`` says which and why. If nothing usable is left, or the model fails, the rules recap
  stands and ``answered_by`` says so.

Output: ``{match_id, player_id, player, headline, paragraphs: [{text, cites, sentences: [{text, cites}]}], reel,
clips, answered_by, engine, trace, checked, basis}``. A cite is ``{t, event_id?, clip_id?, player_id?}``: always at
least one of the two ids, both real. ``reel`` is the recap's 4 to 6 best clips (the player's own when personalised),
in match order, for ``/api/matches/{id}/reel.mp4``. ``basis`` fingerprints the facts, so a written recap can be reused
for as long as the facts it was written from still hold.

English only. No jargon in the text: no expected goals, no "per 90", no scores of how watchable a clip is, no ids.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from regista.agents.base import Agent, State
from regista.clips import TAG_WEIGHTS, StreamIndex, and_list, cut_clips, label_clips, match_minute
from regista.schema import iter_jsonl

Record = dict[str, Any]
Writer = Callable[[str], str]  # the Foundry engine: prompt in, the model's JSON text out
ENGINES = ("rules", "foundry")
REEL_MIN, REEL_MAX = 4, 6
# Words a fan should never meet in a recap: model jargon and the stream's ids.
JARGON_RE = re.compile(r"\bx ?g\b|expected goals|per[ -]?90|watchab|\b(?:ev|cl|lb|pl|po|cs|ap|ma|rl|pv|syn|vis)_[a-z0-9_]+"
                       r"|\bt_(?:home|away)\w*", re.I)
WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]

# A player's notable actions, as counted from the stream: key, the words for one, the words for several, the weight
# with which it makes a player stand out (goals and assists most).
DEEDS: list[tuple[str, str, str, float]] = [
    ("goals", "a goal", "goals", 5.0), ("assists", "an assist", "assists", 4.0), ("nutmegs", "a nutmeg", "nutmegs", 3.0),
    ("saves", "a save", "saves", 2.0), ("chances_created", "a chance created", "chances created", 1.5),
    ("take_ons_won", "a take-on won", "take-ons won", 1.2), ("skill_moves", "a skill move", "skill moves", 1.0),
    ("shots", "a shot", "shots", 0.8), ("tackles_won", "a tackle won", "tackles won", 0.8),
    ("interceptions", "an interception", "interceptions", 0.8), ("balls_won", "a ball won back", "balls won back", 0.3),
]
DEED_WORDS = {k: (one, many) for k, one, many, _w in DEEDS}


# ---------------------------------------------------------------------------- small words

def words(n: int) -> str:
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def counted(key: str, n: int) -> str:
    one, many = DEED_WORDS[key]
    return one if n == 1 else f"{words(n)} {many}"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def surname(name: str) -> str:
    return name.split()[-1] if name else name


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _first_upper(s: str) -> str:
    return s[:1].upper() + s[1:]


# ---------------------------------------------------------------------------- the facts

@dataclass
class Prepared:
    """What both engines write from: the facts (refs only, no ids), what each ref cites, and the clips considered."""

    match_id: str
    match_dir: str
    index: StreamIndex
    player_id: str | None
    facts: Record
    refs: dict[str, list[Record]]
    clips: dict[str, Record]
    basis: str
    trace: list[Record] = field(default_factory=list)

    @property
    def player(self) -> Record | None:
        return self.index.roster.get(self.player_id) if self.player_id else None


def _timed(trace: list[Record], name: str, fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    t0 = time.perf_counter()
    try:
        return fn(*args, **kw)
    finally:
        trace.append({"name": name, "kind": "step", "server": None, "ms": round((time.perf_counter() - t0) * 1000, 1)})


def match_clips(match_dir: str | Path, index: StreamIndex, known: dict[str, tuple[list[Record], list[Record]]] | None = None
                ) -> tuple[list[Record], dict[str, Record]]:
    """Every player's clips and labels as the app serves them: ``known`` first (the workflow's own, before they are
    persisted), then clips.jsonl, then the clip rule for players with neither (the same ids /clips derives)."""
    by_player: dict[str, tuple[list[Record], list[Record]]] = dict(known or {})
    path = Path(match_dir) / "clips.jsonl"
    if path.exists():
        persisted: dict[str, tuple[list[Record], list[Record]]] = {}
        for r in iter_jsonl(path):
            if r.get("type") in ("clip", "label") and r.get("player_id"):
                persisted.setdefault(r["player_id"], ([], []))[0 if r["type"] == "clip" else 1].append(r)
        for pid, pair in persisted.items():
            by_player.setdefault(pid, pair)
    for pid in index.roster:
        if pid not in by_player:
            clips = cut_clips(index, pid)
            by_player[pid] = (clips, label_clips(index, clips))
    clips = [c for cs, _ls in by_player.values() for c in cs]
    labels = {lb["clip_id"]: lb for _cs, ls in by_player.values() for lb in ls}
    return clips, labels


def prepare(match_dir: str | Path, player_id: str | None = None, *, index: StreamIndex | None = None,
            known: dict[str, tuple[list[Record], list[Record]]] | None = None) -> Prepared:
    """Read the facts of one match (from one player's side when ``player_id`` is given). ValueError for a player
    who is not on the team sheet."""
    trace: list[Record] = []
    if index is None:
        index = _timed(trace, "recap.read_match", lambda: StreamIndex.build(iter_jsonl(Path(match_dir) / "events.jsonl")))
    if player_id is not None and player_id not in index.roster:
        raise ValueError(f"{player_id} is not on the team sheet of {index.match['match_id']}")
    clips, labels = _timed(trace, "recap.clips", match_clips, match_dir, index, known)
    facts, refs, summaries = _timed(trace, "recap.facts", _facts, index, clips, labels, player_id)
    basis = hashlib.sha256(json.dumps(facts, sort_keys=True).encode()).hexdigest()[:16]
    return Prepared(match_id=index.match["match_id"], match_dir=str(match_dir), index=index, player_id=player_id, facts=facts,
                    refs=refs, clips=summaries, basis=basis, trace=trace)


class _Match:
    """The match as the facts need it: names, teams, the clips that hold each event, each player's counts."""

    def __init__(self, index: StreamIndex, clips: list[Record], labels: dict[str, Record]):
        self.index = index
        self.m = index.match
        self.roster = index.roster
        self.teams = {t["team_id"]: t for t in self.m["teams"]}
        self.home, self.away = self.m.get("home_team_id"), self.m.get("away_team_id")
        if self.home not in self.teams or self.away not in self.teams:
            self.home, self.away = [t["team_id"] for t in self.m["teams"]][:2]
        self.clips = sorted(clips, key=lambda c: (c["t"], c["id"]))
        self.labels = labels
        self.by_event: dict[str, list[Record]] = {}
        for c in self.clips:
            for eid in c.get("event_ids", []):
                self.by_event.setdefault(eid, []).append(c)
        # A save answers the shot just before it (the shooter is its related player).
        self.keeper_of: dict[str, str] = {}
        saves = [e for e in index.events if e["event_type"] == "save"]
        for e in index.events:
            if e["event_type"] == "shot":
                s = next((s for s in saves if 0 <= s["t"] - e["t"] <= 4 and s.get("related_player_id") in (None, e.get("player_id"))), None)
                if s and s.get("player_id") in self.roster:
                    self.keeper_of[e["id"]] = s["player_id"]

    def name(self, pid: str | None) -> str | None:
        p = self.roster.get(pid or "")
        return p["name"] if p else None

    def team_name(self, tid: str | None) -> str:
        return self.teams.get(tid or "", {}).get("name", "")

    def minute(self, t: float) -> int:
        return match_minute(self.m, t)

    def watch(self, c: Record) -> float:
        return float(self.labels.get(c["id"], {}).get("watchability", 0.0))

    def clip_for(self, e: Record, pid: str | None = None) -> Record | None:
        """The clip that best shows an event: the actor's live clip, else their replay, else anyone's that holds it."""
        holders = self.by_event.get(e["id"], [])
        pid = pid or e.get("player_id")
        ranked = sorted(holders, key=lambda c: (c["player_id"] != pid, c["reason"] != "on_ball_main", -self.watch(c)))
        return ranked[0] if ranked else None

    def key_event(self, c: Record) -> Record | None:
        """The clip's biggest moment: the clip player's own strongest event, else the strongest event it shows."""
        evs = [self.index.events_by_id[i] for i in c.get("event_ids", []) if i in self.index.events_by_id]
        evs = [e for e in evs if deed(e, self) is not None]
        if not evs:
            return None
        return max(evs, key=lambda e: (e.get("player_id") == c["player_id"], _weight(e), -e["t"]))

    def score(self) -> dict[str, int]:
        s = self.m.get("score")
        if isinstance(s, dict) and self.home in s and self.away in s:
            return {self.home: int(s[self.home]), self.away: int(s[self.away])}
        out = {self.home: 0, self.away: 0}
        for e in self.index.events:
            if e["event_type"] == "goal" and e.get("team_id") in out:
                out[e["team_id"]] += 1
        return out

    def counts(self, pid: str) -> dict[str, int]:
        n: dict[str, int] = {}
        for e in self.index.events:
            if e.get("player_id") != pid:
                continue
            et, q, ok = e["event_type"], set(e.get("qualifiers", [])), e.get("outcome") != "fail"
            key = {"goal": "goals", "assist": "assists", "nutmeg": "nutmegs", "save": "saves", "shot": "shots",
                   "interception": "interceptions", "skill_move": "skill_moves", "recovery": "balls_won", "ball_won": "balls_won"}.get(et)
            if et == "take_on" and ok:
                key = "take_ons_won"
            elif et == "tackle" and ok:
                key = "tackles_won"
            elif et in ("pass", "cross") and "key_pass" in q and "assist" not in q:
                key = "chances_created"
            if et == "pass":
                n["passes"] = n.get("passes", 0) + 1
                n["passes_completed"] = n.get("passes_completed", 0) + (e.get("outcome") == "success")
            if key:
                n[key] = n.get(key, 0) + 1
        return n


def _weight(e: Record) -> float:
    w = TAG_WEIGHTS.get(e["event_type"], 0.1)
    if e["event_type"] == "shot" and "goal" in e.get("qualifiers", []):
        w = TAG_WEIGHTS["goal"]
    if e.get("outcome") == "fail" and e["event_type"] not in ("shot",):
        w *= 0.3
    return w


def deed(e: Record, mx: _Match, *, whose: bool = False) -> str | None:
    """What a player did in one event, as a verb phrase ("nutmegged Pavel Brennan"); None for events that tell nothing.
    ``whose`` gives the noun form for someone else's moment ("Whitfield's goal")."""
    et, q, ok = e["event_type"], set(e.get("qualifiers", [])), e.get("outcome") != "fail"
    other = mx.name(e.get("related_player_id"))
    head = "header" in q or e.get("body_part") == "head"
    if whose:
        noun = {"goal": "goal", "shot": "goal" if "goal" in q else "header" if head else "shot", "nutmeg": "nutmeg",
                "take_on": "take-on", "save": "save", "assist": "assist", "tackle": "tackle", "skill_move": "skill move"}.get(et)
        who = mx.name(e.get("player_id"))
        return f"{possessive(surname(who))} {noun}" if noun and who else None
    if et == "goal" or (et == "shot" and "goal" in q):
        return "scored with a header" if head else "scored"
    if et == "shot":
        keeper = mx.name(mx.keeper_of.get(e["id"]))
        if "saved" in q:
            return f"forced a save from {keeper}" if keeper else "had a header saved" if head else "had a shot saved"
        if "blocked" in q:
            return "had a shot blocked"
        return "headed wide" if head else "shot wide" if "off_target" in q else "had a shot"
    if et == "nutmeg":
        return f"nutmegged {other}" if other else "nutmegged a defender"
    if et == "take_on":
        return (f"went past {other}" if other else "beat a defender") if ok else None
    if et == "assist":
        return f"set up {possessive(other)} goal" if other else "set up a goal"
    if et in ("pass", "cross") and "assist" in q:
        return f"set up {possessive(other)} goal" if other else "set up a goal"
    if et in ("pass", "cross") and "key_pass" in q:
        return f"set up a chance for {other}" if other else "set up a chance"
    if et == "save":
        return f"saved from {other}" if other else "made a save"
    if et == "tackle":
        return (f"won the ball from {other}" if other else "won a tackle") if ok else None
    if et == "interception":
        return "intercepted a pass"
    if et in ("recovery", "ball_won"):
        return "won the ball back"
    if et == "skill_move":
        return "pulled off a stepover" if "stepover" in q else "pulled off a skill move"
    if et == "cross":
        return "put in a cross" if ok else None
    return None


def _cite(t: float, event: Record | None = None, clip: Record | None = None) -> Record:
    """A citation: the event's time when it names an event, else the clip's key frame."""
    out: Record = {"t": round(float(t), 2)}
    if event is not None:
        out["event_id"] = event["id"]
    if clip is not None:
        out["clip_id"] = clip["id"]
        out["player_id"] = clip["player_id"]
    return out


def _facts(index: StreamIndex, clips: list[Record], labels: dict[str, Record], player_id: str | None
           ) -> tuple[Record, dict[str, list[Record]], dict[str, Record]]:
    mx = _Match(index, clips, labels)
    refs: dict[str, list[Record]] = {}
    score = mx.score()
    home, away = mx.team_name(mx.home), mx.team_name(mx.away)
    hg, ag = score[mx.home], score[mx.away]
    result = (f"{home} won" if hg > ag else f"{away} won" if ag > hg else "a draw")
    facts: Record = {"match": {"home": home, "away": away, "home_goals": hg, "away_goals": ag, "score": f"{hg}–{ag}", "result": result,
                               "venue": mx.m.get("venue") if mx.m.get("source") != "vision" else None, "competition": mx.m.get("competition")}}

    # Goals, in match order.
    goals = []
    for e in mx.index.events:
        if e["event_type"] != "goal":
            continue
        scorer = e.get("player_id")
        assister = e.get("related_player_id") if mx.roster.get(e.get("related_player_id") or "", {}).get("team_id") == e.get("team_id") else None
        ref = f"G{len(goals) + 1}"
        clip = mx.clip_for(e, scorer)
        refs[ref] = [_cite(e["t"], e, clip)]
        goals.append({"ref": ref, "minute": mx.minute(e["t"]), "team": mx.team_name(e.get("team_id")), "scorer": mx.name(scorer),
                      "assisted_by": mx.name(assister), "header": e.get("body_part") == "head", "_scorer": scorer, "_assister": assister})

    # The best chances that did not go in: saved ones first, then the likeliest (the model of shot quality stays inside).
    shots = [e for e in mx.index.events if e["event_type"] == "shot" and "goal" not in e.get("qualifiers", []) and e.get("player_id") in mx.roster]
    shots.sort(key=lambda e: (e["id"] not in mx.keeper_of, -float((e.get("metrics") or {}).get("xg", 0.0)), e["t"]))
    chances = []
    for i, e in enumerate(sorted(shots[:3], key=lambda e: e["t"]), 1):  # refs in match order: C1 is the first chance
        q = set(e.get("qualifiers", []))
        how = (f"saved by {mx.name(mx.keeper_of[e['id']])}" if e["id"] in mx.keeper_of else "blocked" if "blocked" in q
               else "wide" if "off_target" in q else "missed")
        refs[f"C{i}"] = [_cite(e["t"], e, mx.clip_for(e))]
        chances.append({"ref": f"C{i}", "minute": mx.minute(e["t"]), "team": mx.team_name(e.get("team_id")), "shooter": mx.name(e["player_id"]),
                        "result": how, "header": "header" in q})

    # Who stood out: the weighted count of what each player did, top two.
    ranked = []
    for pid in mx.roster:
        n = mx.counts(pid)
        s = sum(w * n.get(k, 0) for k, _o, _m, w in DEEDS)
        if s >= 2.0:
            ranked.append((s, pid, n))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    standouts = []
    for s, pid, n in ranked[:2]:
        best = _best_clip(mx, pid)
        ref = f"S{len(standouts) + 1}"
        ke = mx.key_event(best) if best else None
        refs[ref] = [_cite(ke["t"] if ke else best["keyframe_t"], ke, best)] if best else []
        if not refs[ref]:
            refs.pop(ref)
            continue
        standouts.append({"ref": ref, "name": mx.name(pid), "team": mx.team_name(mx.roster[pid]["team_id"]),
                          "did": {DEED_WORDS[k][1]: v for k, v in _ordered(n)}, "best_moment": _moment_words(mx, best, pid), "_n": n})

    facts["goals"] = [_public(g) for g in goals]
    facts["chances"] = [_public(c) for c in chances]
    facts["standouts"] = [_public(s) for s in standouts]

    # The match's best moment, for a sentence that has nothing else to cite (a goalless match without a shot).
    allbest = max(mx.clips, key=lambda c: (mx.watch(c), -c["t"]), default=None)
    if allbest is not None:
        ke = mx.key_event(allbest)
        refs["B1"] = [_cite(ke["t"] if ke else allbest["keyframe_t"], ke, allbest)]
        facts["best_moment"] = {"ref": "B1", "minute": mx.minute(ke["t"] if ke else allbest["keyframe_t"]), "what": _moment_words(mx, allbest, None)}

    facts["_"] = {"goals": goals, "chances": chances, "standouts": standouts}  # for the rules writer; the model never sees "_"
    if player_id is not None:
        facts["perspective"] = _perspective(mx, player_id, goals, refs)
    return facts, refs, {c["id"]: _summary(c, labels.get(c["id"])) for c in mx.clips}


def _public(d: Record) -> Record:
    return {k: v for k, v in d.items() if not k.startswith("_") and v not in (None, False)}


def _ordered(n: dict[str, int]) -> list[tuple[str, int]]:
    order = [k for k, *_r in DEEDS]
    return [(k, n[k]) for k in order if n.get(k)]


def _best_clip(mx: _Match, pid: str) -> Record | None:
    mine = [c for c in mx.clips if c["player_id"] == pid]
    return max(mine, key=lambda c: (mx.watch(c), c["reason"] == "on_ball_main", -c["t"]), default=None)


def _moment_words(mx: _Match, c: Record, pid: str | None) -> str:
    """One clip in words, from ``pid``'s side when given: "nutmegged Pavel Brennan in the 1st minute"."""
    ke = mx.key_event(c)
    t = ke["t"] if ke else c["keyframe_t"]
    when = f"in the {ordinal(mx.minute(t))} minute"
    if ke is None:
        return f"on the ball {when}" if c["reason"] == "on_ball_main" else f"in a {c['reason'].split('_')[0]} {when}"
    actor = ke.get("player_id")
    if pid is None or actor == pid:
        did = deed(ke, mx)
        lead = "" if pid is not None else f"{mx.name(actor)} "
        seen = "" if c["reason"] == "on_ball_main" else " (seen again in a replay)" if c["reason"] == "replay_appearance" else ""
        return f"{lead}{did} {when}{seen}"
    where = {"replay_appearance": "the replay of", "highlight_appearance": "the highlights of", "closeup_appearance": "the close-up after"}
    return f"in {where.get(c['reason'], 'the build-up to')} {deed(ke, mx, whose=True) or 'a moment'} {when}"


def _perspective(mx: _Match, pid: str, goals: list[Record], refs: dict[str, list[Record]]) -> Record:
    p = mx.roster[pid]
    mine = [c for c in mx.clips if c["player_id"] == pid]
    n = mx.counts(pid)
    on_ball = sum(1 for pos in mx.index.possessions if pos["player_id"] == pid)
    # Their best moments: one per key event (a replay of the same moment adds nothing), best first.
    picked, seen_events, seen_what = [], set(), set()
    for c in sorted(mine, key=lambda c: (-mx.watch(c), c["t"])):
        ke = mx.key_event(c)
        if ke is None or ke["id"] in seen_events or _moment_words(mx, c, pid).rsplit(" in the ", 1)[0] in seen_what:
            continue
        seen_events.add(ke["id"])
        seen_what.add(_moment_words(mx, c, pid).rsplit(" in the ", 1)[0])
        own = ke.get("player_id") == pid
        if (not own and c["reason"] == "on_ball_main") or (own and _is_goal_or_assist(ke)):
            continue  # their goals and assists are told with the goals
        picked.append((c, ke, own))
        if len(picked) == 3:
            break
    moments = []
    for i, (c, ke, own) in enumerate(sorted(picked, key=lambda x: x[1]["t"]), 1):  # refs in match order
        refs[f"M{i}"] = [_cite(ke["t"], ke, c)]
        moments.append({"ref": f"M{i}", "minute": mx.minute(ke["t"]), "what": _moment_words(mx, c, pid).rsplit(" in the ", 1)[0],
                        "seen_in": {"on_ball_main": "live", "replay_appearance": "a replay", "highlight_appearance": "the highlights",
                                    "closeup_appearance": "a close-up"}[c["reason"]], "_own": own})
    replays = [c for c in mine if c["reason"] == "replay_appearance"]
    highlights = [c for c in mine if c["reason"] == "highlight_appearance"]
    shown = sorted(replays + highlights, key=lambda c: -mx.watch(c))[:3]
    if shown:
        refs["R1"] = [_cite(c["keyframe_t"], None, c) for c in sorted(shown, key=lambda c: c["t"])]  # the appearances themselves
    first = min((c for c in mine if c["reason"] == "on_ball_main"), key=lambda c: (-mx.watch(c), c["t"]), default=None)
    if first is not None:
        ke = mx.key_event(first)
        refs["P1"] = [_cite(ke["t"] if ke else first["keyframe_t"], ke, first)]
    team = p["team_id"]
    opp = mx.away if team == mx.home else mx.home
    out = {"name": p["name"], "team": mx.team_name(team), "opponent": mx.team_name(opp), "position": p.get("position"),
           "times_on_the_ball": on_ball, "did": {DEED_WORDS[k][1]: v for k, v in _ordered(n)},
           "passes": n.get("passes", 0), "passes_completed": n.get("passes_completed", 0),
           "scored": [g["ref"] for g in goals if g["_scorer"] == pid], "set_up": [g["ref"] for g in goals if g["_assister"] == pid],
           "moments": [_public(m) for m in moments], "replays": len(replays), "highlights": len(highlights)}
    if shown:
        out["replays_ref"] = "R1"
    if first is not None:
        out["on_the_ball_ref"] = "P1"
    out["_"] = {"pid": pid, "team": team, "opp": opp, "moments": moments, "n": n}
    return out


def _is_goal_or_assist(e: Record) -> bool:
    q = e.get("qualifiers", [])
    return e["event_type"] in ("goal", "assist") or (e["event_type"] == "shot" and "goal" in q) or (e["event_type"] in ("pass", "cross") and "assist" in q)


def _summary(c: Record, lb: Record | None) -> Record:
    lb = lb or {}
    return {"player_id": c["player_id"], "t": c["t"], "t_end": c["t_end"], "reason": c["reason"], "title": lb.get("title"),
            "tags": lb.get("tags", []), "watchability": lb.get("watchability", 0.0), "explanation": lb.get("explanation", ""),
            "summary": lb.get("summary", "")}


def model_facts(facts: Record) -> Record:
    """The facts as the model sees them: everything public, nothing internal."""
    def strip(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if not k.startswith("_")}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    return strip(facts)


# ---------------------------------------------------------------------------- the rules engine

Sentence = tuple[str, list[str]]  # (text, refs)


class _Names:
    """A name in full (with the team, where it helps) the first time, the surname after."""

    def __init__(self) -> None:
        self.said: set[str] = set()

    def __call__(self, name: str | None, team: str | None = None) -> str:
        if not name:
            return "an unknown player"
        if name in self.said:
            return surname(name)
        self.said.add(name)
        return f"{name} of {team}" if team else name


def write_rules(facts: Record) -> Record:
    """The recap in plain sentences, each citing the refs it is built from: {headline, paragraphs: [[(text, refs)]]}."""
    if "perspective" in facts:
        return _rules_player(facts)
    m, inner = facts["match"], facts["_"]
    goals, chances, standouts = inner["goals"], inner["chances"], inner["standouts"]
    say = _Names()
    paras: list[list[Sentence]] = []
    lead_refs = [g["ref"] for g in goals] or [c["ref"] for c in chances[:1]] or (["B1"] if "best_moment" in facts else [])
    if lead_refs:
        paras.append([(_result_sentence(m), lead_refs)])
    if goals:
        paras.append(_goal_sentences(goals, say))
    if chances:
        paras.append(_chance_sentences(chances, say, scored=bool(goals)))
    if standouts:
        paras.append([(_standout_sentence(s, say, i), [s["ref"]]) for i, s in enumerate(standouts)])
    return {"headline": _headline(m, goals), "paragraphs": [p for p in paras if p]}


def _result_sentence(m: Record, team_first: str | None = None) -> str:
    home, away, hg, ag = m["home"], m["away"], m["home_goals"], m["away_goals"]
    venue = f" at {m['venue']}" if m.get("venue") and not team_first else ""
    if hg == ag:
        a, b = (home, away) if team_first in (None, home) else (away, home)
        return f"{a} and {b} drew {hg}–{ag}{venue}."
    win, lose, w, lo = (home, away, hg, ag) if hg > ag else (away, home, ag, hg)
    if team_first is not None and team_first == lose:
        return f"{lose} lost {w}–{lo} to {win}."
    return f"{win} beat {lose} {w}–{lo}{venue}."


def _headline(m: Record, goals: list[Record]) -> str:
    home, away, hg, ag = m["home"], m["away"], m["home_goals"], m["away_goals"]
    if hg == ag:
        return f"{home} and {away} share a goalless draw" if hg == 0 else f"{home} and {away} draw {hg}–{ag}"
    win, lose, w, lo = (home, away, hg, ag) if hg > ag else (away, home, ag, hg)
    scorers = [g["scorer"] for g in goals if g["team"] == win and g["scorer"]]
    if len(set(scorers)) == 1:
        who = surname(scorers[0])
        return f"{who} {'double gives' if len(scorers) == 2 else 'hat-trick gives' if len(scorers) == 3 else 'gives'} {win} a {w}–{lo} win over {lose}"
    return f"{win} beat {lose} {w}–{lo}"


def _who_when(g: Record, say: _Names) -> str:
    return f"{say(g['scorer'])} in the {ordinal(g['minute'])} minute"


def _goal_sentences(goals: list[Record], say: _Names) -> list[Sentence]:
    out = []
    for g in goals[:4]:
        how = "headed in" if g.get("header") else "scored"
        setup = f", set up by {say(g['assisted_by'])}" if g.get("assisted_by") else ""
        out.append((f"{_first_upper(say(g['scorer']))} {how} for {g['team']} in the {ordinal(g['minute'])} minute{setup}.", [g["ref"]]))
    rest = goals[4:]
    if rest:
        out.append((f"Further goals came from {and_list([_who_when(g, say) for g in rest])}.", [g["ref"] for g in rest]))
    return out


def _chance_sentences(chances: list[Record], say: _Names, scored: bool) -> list[Sentence]:
    out = []
    for i, c in enumerate(chances[:2]):
        shot = "header" if c.get("header") else "shot"
        res = c["result"]
        keeper = res.removeprefix("saved by ") if res.startswith("saved by ") else None
        what = (f"saw a {shot} saved by {say(keeper)}" if keeper else
                {"wide": f"put a {shot} wide", "blocked": f"had a {shot} blocked"}.get(res, f"missed with a {shot}"))
        when = f"in the {ordinal(c['minute'])} minute"
        if i == 0:
            lead = "The best chance that did not go in fell to " if scored else "The best chance fell to "
            out.append((f"{lead}{say(c['shooter'], c['team'])}, who {what} {when}.", [c["ref"]]))
        else:
            out.append((f"Later, {say(c['shooter'], c['team'])} {what} {when}.", [c["ref"]]))
    return out


def _standout_sentence(s: Record, say: _Names, i: int) -> str:
    did = [counted(k, v) for k, v in _ordered(s["_n"])][:3]
    verb = "stood out" if i == 0 else "also caught the eye"
    return f"{_first_upper(say(s['name'], s['team']))} {verb}" + (f", with {and_list(did)}." if did else ".")


POSITION_PHRASE = {"GK": "in goal", "DF": "in defence", "MF": "in midfield", "FW": "up front"}


def _rules_player(facts: Record) -> Record:
    m, inner, me = facts["match"], facts["_"], facts["perspective"]
    goals = inner["goals"]
    pid, team, n = me["_"]["pid"], me["team"], me["_"]["n"]
    name, sur = me["name"], surname(me["name"])
    say = _Names()
    say.said.add(name)
    scored = [g for g in goals if g["_scorer"] == pid]
    set_up = [g for g in goals if g["_assister"] == pid]
    others = [g for g in goals if g not in scored and g not in set_up]
    any_ref = (["P1"] if "on_the_ball_ref" in me else []) or [x["ref"] for x in me["moments"][:1]] or (
        ["R1"] if "replays_ref" in me else []) or [g["ref"] for g in goals[:1]] or (["B1"] if "best_moment" in facts else [])
    paras: list[list[Sentence]] = []

    # 1. The result, from their team's side, and their part in it.
    lead = _result_sentence(m, team_first=team).rstrip(".")
    if scored:
        part = f", and {name} scored " + ("the only goal" if len(goals) == 1 else "twice" if len(scored) == 2 else
                                          "three times" if len(scored) == 3 else "once" if len(scored) == 1 else f"{len(scored)} times")
        refs = [g["ref"] for g in scored]
    elif set_up:
        part = f", and {name} set up " + ("the only goal" if len(goals) == 1 else counted("goals", len(set_up)).replace("a goal", "one of the goals"))
        refs = [g["ref"] for g in set_up]
    else:
        part, refs = f", with {name} {POSITION_PHRASE.get(me.get('position') or '', 'in the side')}", [g["ref"] for g in goals] or any_ref
    if refs:
        paras.append([(f"{lead}{part}.", refs)])

    # 2. Their goals and the goals they set up, then the rest briefly.
    told: list[Sentence] = []
    for g in scored:
        setup = f", set up by {say(g['assisted_by'])}" if g.get("assisted_by") else ""
        told.append((f"{sur} {'headed in' if g.get('header') else 'scored'} in the {ordinal(g['minute'])} minute{setup}.", [g["ref"]]))
    for g in set_up:
        told.append((f"{sur} set up {possessive(say(g['scorer']))} goal in the {ordinal(g['minute'])} minute.", [g["ref"]]))
    if others and len(told) < 3:
        mine = [g for g in others if g["team"] == team]
        theirs = [g for g in others if g["team"] != team]
        if mine:
            told.append((f"{('The other goal' if len(mine) == 1 else 'Other goals') if told else ('The goal' if len(mine) == 1 else 'Goals')} for {team} came from "
                         f"{and_list([_who_when(g, say) for g in mine[:3]])}.", [g["ref"] for g in mine[:3]]))
        if theirs:
            told.append((f"{theirs[0]['team']} scored through {and_list([_who_when(g, say) for g in theirs[:3]])}.",
                         [g["ref"] for g in theirs[:3]]))
    if told:
        paras.append(told)

    # 3. Their time on the ball and their best moments.
    on: list[Sentence] = []
    if me["times_on_the_ball"] and "on_the_ball_ref" in me:
        did = [counted(k, v) for k, v in _ordered(n) if k not in ("goals", "assists")][:3]
        passes = (f", completing {words(me['passes_completed'])} of {words(me['passes'])} passes" if me["passes"] >= 3 else "")
        times = "once" if me["times_on_the_ball"] == 1 else "twice" if me["times_on_the_ball"] == 2 else f"{words(me['times_on_the_ball'])} times"
        on.append((f"{sur} had the ball {times}{passes}" + (f", and finished with {and_list(did)}." if did else "."), ["P1"]))
    for mo in me["_"]["moments"]:
        if mo["_own"]:
            seen = "" if mo["seen_in"] == "live" else f", shown again in {mo['seen_in']}"
            on.append((f"In the {ordinal(mo['minute'])} minute {sur} {mo['what']}{seen}.", [mo["ref"]]))
        else:
            on.append((f"{sur} is {mo['what']} in the {ordinal(mo['minute'])} minute.", [mo["ref"]]))
    if on:
        paras.append(on)

    # 4. Replays and highlights they appear in.
    if "replays_ref" in me:
        parts = [p for p in (f"{words(me['replays'])} {'replay' if me['replays'] == 1 else 'replays'}" if me["replays"] else "",
                             "the highlights" if me["highlights"] else "") if p]
        paras.append([(f"{sur} also appears in {and_list(parts).replace('one replay', 'a replay')}.", ["R1"])])

    if not any(paras) and any_ref:
        paras.append([(f"{name} did not get on the ball in this match.", any_ref)])
    return {"headline": _player_headline(m, me, scored, set_up, n), "paragraphs": [p for p in paras if p]}


def _player_headline(m: Record, me: Record, scored: list[Record], set_up: list[Record], n: dict[str, int]) -> str:
    team, opp = me["team"], me["opponent"]
    mine = m["home_goals"] if team == m["home"] else m["away_goals"]
    theirs = m["away_goals"] if team == m["home"] else m["home_goals"]
    res = (f"in a {mine}–{theirs} win over {opp}" if mine > theirs else f"in a {mine}–{theirs} draw with {opp}" if mine == theirs
           else f"in a {theirs}–{mine} defeat to {opp}")
    deeds = []
    if scored:
        deeds.append("the winning goal" if len(scored) == 1 and mine == 1 and theirs == 0 else counted("goals", len(scored)))
    if set_up:
        deeds.append(counted("assists", len(set_up)))
    if n.get("nutmegs") and len(deeds) < 2:
        deeds.append(counted("nutmegs", n["nutmegs"]))
    if n.get("saves") and len(deeds) < 2:
        deeds.append(counted("saves", n["saves"]))
    if deeds:
        return f"{me['name']}: {and_list(deeds)} {res}"
    return f"{me['name']} {res.replace('in a', 'plays in a', 1)}"


# ---------------------------------------------------------------------------- the Foundry engine's text, checked

RECAP_INSTRUCTIONS = """You are Regista's Recap agent, writing a short match recap for football fans.
You get the facts of one match as JSON. Every fact you may use has a "ref" ("G1" a goal, "C1" a chance, "S1" a player
who stood out, "B1" the best moment, "M1" one of the perspective player's moments, "P1" their time on the ball, "R1"
the replays they appear in). Write ONLY from these facts.

If the facts have a "perspective" player, tell the match from their side: their result, their part in the goals,
their best moments, the replays they appear in. Otherwise tell the match: the result, the goals (scorer, assister,
minute), the best chances and saves, who stood out.

Return JSON only: {"headline": "...", "paragraphs": [{"sentences": [{"text": "...", "refs": ["G1"]}]}]}
- headline: at most 80 characters, no ids.
- 3 or 4 short paragraphs, 1 to 3 sentences each. Plain English a fan reads in twenty seconds.
- EVERY sentence lists the refs of the facts it states (at least one). A sentence with no ref is thrown away.
- Numbers: only the ones in the facts (minutes, the score, counts). Write minutes as "in the 12th minute".
- No jargon: never "xG", "expected goals", "per 90", ratings, probabilities or how watchable a clip is; no ids, no refs
  in the text. Use names (full name first, then surname), never gendered pronouns. English only.
- Never invent players, events, scores or minutes."""


def model_prompt(facts: Record) -> str:
    return json.dumps(model_facts(facts), ensure_ascii=False) + "\n\nWrite the recap. Respond with JSON only."


def _held(facts: Record) -> list[float]:
    from regista.season.scout import held_numbers

    return held_numbers(model_facts(facts))


def numbers_not_in_facts(text: str, facts: Record) -> list[str]:
    """Numbers in ``text`` that the facts do not hold (the Scout agent's check: rounding allowed)."""
    from regista.season.scout import unheld

    return unheld(text, _held(facts))


def check_written(prepared: Prepared, obj: Any) -> tuple[Record | None, Record]:
    """The model's recap, kept only where it holds: sentences that cite known refs, use the facts' numbers and no
    jargon. Returns ({headline, paragraphs: [[(text, refs)]]} or None if nothing usable is left, checked)."""
    known = set(prepared.refs)
    checked: Record = {"sentences": 0, "kept": 0, "dropped": [], "numbers_not_in_facts": [], "unknown_refs": []}
    if not isinstance(obj, dict) or not isinstance(obj.get("paragraphs"), list):
        checked["error"] = "the model's answer was not a recap"
        return None, checked
    paras: list[list[Sentence]] = []
    for p in obj["paragraphs"]:
        sentences = p.get("sentences") if isinstance(p, dict) else p if isinstance(p, list) else None
        kept: list[Sentence] = []
        for s in sentences or []:
            if not isinstance(s, dict):
                continue
            text = " ".join(str(s.get("text") or "").split())
            if not text:
                continue
            checked["sentences"] += 1
            raw = s.get("refs") or s.get("cites") or []
            refs = [str(r).strip() for r in (raw if isinstance(raw, list) else [raw])]
            unknown = [r for r in refs if r not in known]
            checked["unknown_refs"] += unknown
            refs = list(dict.fromkeys(r for r in refs if r in known))
            bad_numbers = numbers_not_in_facts(text, prepared.facts)
            checked["numbers_not_in_facts"] += bad_numbers
            why = ("cites no fact" if not refs else f"numbers not in the facts: {', '.join(bad_numbers)}" if bad_numbers
                   else "jargon or an id in the text" if JARGON_RE.search(text) else None)
            if why:
                checked["dropped"].append({"text": text, "why": why})
                continue
            kept.append((text, refs))
        if kept:
            paras.append(kept)
    checked["kept"] = sum(len(p) for p in paras)
    headline = " ".join(str(obj.get("headline") or "").split())[:120]
    if not headline or numbers_not_in_facts(headline, prepared.facts) or JARGON_RE.search(headline):
        checked["headline"] = "replaced by the rules headline" if headline else "missing: the rules headline is used"
        if headline:
            checked["dropped"].append({"text": headline, "why": "headline: numbers not in the facts or jargon"})
        headline = write_rules(prepared.facts)["headline"]
    return ({"headline": headline, "paragraphs": paras} if paras else None), checked


def _parse_json(text: str) -> Any:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def foundry_writer() -> Writer | None:
    """The Foundry engine on this deployment, or None when Foundry is not configured. Tests pass their own writer."""
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.foundry_enabled:
        return None

    def write(prompt: str) -> str:
        from regista.aio import run_sync
        from regista.cloud.foundry import foundry_recap_text

        return run_sync(foundry_recap_text(cfg, prompt))

    write.answered_by = f"foundry:{cfg.foundry_model}"  # type: ignore[attr-defined]
    return write


# ---------------------------------------------------------------------------- one recap

def write(prepared: Prepared, engine: str = "rules", writer: Writer | None = None) -> Record:
    """The recap from prepared facts with one engine. With ``engine="foundry"`` and no ``writer``, the deployment's
    Foundry engine is used if configured; without one, or if it fails or leaves nothing usable, the rules recap stands
    and ``answered_by`` says why."""
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {ENGINES}")
    trace = list(prepared.trace)
    rules = _timed(trace, "recap.write_rules", write_rules, prepared.facts)
    if engine == "rules":
        return assemble(prepared, rules, "rules", trace, engine)
    if writer is None:
        writer = foundry_writer()
        if writer is None:
            return assemble(prepared, rules, "rules (Foundry is not configured on this deployment)", trace, engine)
    answered_by = getattr(writer, "answered_by", "foundry:test")
    from regista.cloud.telemetry import capture_spans

    try:
        with capture_spans("regista.recap") as cap:  # the Agent Framework spans of this recap, for its trace
            text = writer(model_prompt(prepared.facts))
        written, checked = check_written(prepared, _parse_json(text))
    except Exception as exc:  # noqa: BLE001 - the rules recap stands
        return assemble(prepared, rules, f"rules (foundry fallback: {type(exc).__name__})", trace, engine)
    from regista.cloud.foundry import foundry_trace

    steps, note = foundry_trace(cap.spans, [])
    trace += steps or [{"name": "recap", "kind": "agent", "server": None, "ms": None}]
    if written is None:
        out = assemble(prepared, rules, "rules (foundry fallback: no sentence of the model's recap held)", trace, engine)
        out["checked"] = checked
        return out
    out = assemble(prepared, written, answered_by, trace, engine, checked=checked)
    if note and steps:
        out["trace_note"] = note
    return out


def assemble(prepared: Prepared, written: Record, answered_by: str, trace: list[Record], engine: str, checked: Record | None = None) -> Record:
    """Written sentences with their refs resolved to cites, the reel, and the clips both point at."""
    paragraphs, cited_clips = [], []
    for para in written["paragraphs"]:
        sentences = []
        for text, refs in para:
            cites = _dedupe([c for r in refs for c in prepared.refs.get(r, [])])
            cited_clips += [c["clip_id"] for c in cites if c.get("clip_id")]
            sentences.append({"text": text, "cites": cites})
        paragraphs.append({"text": " ".join(s["text"] for s in sentences), "cites": _dedupe([c for s in sentences for c in s["cites"]]),
                           "sentences": sentences})
    reel = _reel(prepared, cited_clips)
    shown = set(cited_clips) | set(reel)
    if checked is None:
        text = " ".join([written["headline"]] + [s["text"] for p in paragraphs for s in p["sentences"]])
        checked = {"sentences": sum(len(p["sentences"]) for p in paragraphs), "kept": sum(len(p["sentences"]) for p in paragraphs),
                   "dropped": [], "numbers_not_in_facts": numbers_not_in_facts(text, prepared.facts), "unknown_refs": []}
    p = prepared.player
    return {"match_id": prepared.match_id, "player_id": prepared.player_id,
            "player": {"name": p["name"], "team_id": p["team_id"], "kit_number": p.get("kit_number")} if p else None,
            "headline": written["headline"], "paragraphs": paragraphs, "reel": reel,
            "clips": {cid: prepared.clips[cid] for cid in sorted(shown, key=lambda i: prepared.clips[i]["t"]) if cid in prepared.clips},
            "answered_by": answered_by, "engine": engine, "trace": trace, "checked": checked, "basis": prepared.basis}


def _dedupe(cites: list[Record]) -> list[Record]:
    seen, out = set(), []
    for c in cites:
        key = (c.get("clip_id"), c.get("event_id"))
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _reel(prepared: Prepared, cited: list[str]) -> list[str]:
    """The recap's 4 to 6 best clips in match order: the cited ones first (the player's own when personalised), then
    the best others to reach four."""
    pid = prepared.player_id
    pool = {cid: c for cid, c in prepared.clips.items() if pid is None or c["player_id"] == pid}
    w = lambda cid: (-pool[cid]["watchability"], pool[cid]["t"])  # noqa: E731
    chosen = sorted(dict.fromkeys(c for c in cited if c in pool), key=w)[:REEL_MAX]
    if len(chosen) < REEL_MIN:
        chosen += [c for c in sorted(pool, key=w) if c not in chosen][:REEL_MIN - len(chosen)]
    return sorted(chosen, key=lambda cid: (pool[cid]["t"], cid))


def recap(match_dir: str | Path, *, player_id: str | None = None, engine: str = "rules", writer: Writer | None = None) -> Record:
    """The recap of one match, told from ``player_id``'s side when given (see the module docstring)."""
    return write(prepare(match_dir, player_id), engine, writer)


def as_text(r: Record) -> str:
    return "\n\n".join([r["headline"]] + [p["text"] for p in r["paragraphs"]])


# ---------------------------------------------------------------------------- the Recap agent (workflow role)

@dataclass
class RecapAgent(Agent):
    """Writes the match recap after labelling, from the stream and the labelled clips; recap.json next to the match."""

    role: str = "recap"
    inputs: tuple[str, ...] = ("match_dir", "index", "clips", "labels")
    outputs: tuple[str, ...] = ("recap",)
    description: str = ("Writes the match recap: a headline and short paragraphs whose every sentence cites a clip or an event, "
                        "and a reel of the recap's best clips (recap.json).")
    engine: str = "rules"
    writer: Writer | None = None  # the Foundry engine; injectable for tests

    def handle(self, state: State) -> State:
        known = {pid: (cs, state["labels"].get(pid, [])) for pid, cs in state["clips"].items()}
        prepared = prepare(state["match_dir"], index=state["index"], known=known)
        out = write(prepared, self.engine, self.writer)
        path = Path(state["match_dir"]) / self.config.get("filename", "recap.json")
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        state["recap"] = {"path": str(path), "headline": out["headline"], "answered_by": out["answered_by"],
                          "sentences": sum(len(p["sentences"]) for p in out["paragraphs"]), "reel": len(out["reel"]),
                          "dropped": len(out["checked"].get("dropped", []))}
        return state


# ---------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write a match recap (rules, or Foundry with --engine foundry).")
    ap.add_argument("match_dir")
    ap.add_argument("--player", default=None, help="tell it from this player's side (per-match player id)")
    ap.add_argument("--engine", choices=ENGINES, default="rules")
    ap.add_argument("--json", action="store_true", help="print the whole recap as JSON")
    args = ap.parse_args(argv)
    out = recap(args.match_dir, player_id=args.player, engine=args.engine)
    if args.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        print(as_text(out))
        print(f"\n[{out['answered_by']} · reel {len(out['reel'])} clips · {out['checked']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
