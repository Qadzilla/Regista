"""Load a match directory into a Scene that answers "where is everyone at time t?".

The event stream is sparse (tracks at 1-2 Hz, events at irregular times). The renderer
needs smooth motion at 15-30 fps, so the Scene interpolates player and ball positions
between samples, uses pass and shot events as extra ball waypoints, and precomputes the
captions, score, and clock timeline once.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from regista.schema import iter_jsonl

Record = dict[str, Any]
Point = tuple[float, float]

PITCH_L = 105.0
PITCH_W = 68.0

# Captions: event_type -> (priority, duration seconds). Higher priority wins when two overlap.
CAPTION_RULES: dict[str, tuple[int, float]] = {
    "goal": (100, 4.0),
    "nutmeg": (90, 3.0),
    "card_red": (85, 3.0),
    "card_yellow": (80, 3.0),
    "save": (70, 2.5),
    "skill_move": (60, 2.5),
    "shot": (50, 2.5),
    "foul": (40, 2.5),
    "take_on": (30, 2.0),
    "assist": (20, 2.0),
}


@dataclass
class Caption:
    t: float
    t_end: float
    text: str
    priority: int
    event_id: str
    kind: str


@dataclass
class Timeline:
    """Sorted (t, x, y) samples for one object, with gap-aware interpolation."""

    ts: list[float] = field(default_factory=list)
    xs: list[float] = field(default_factory=list)
    ys: list[float] = field(default_factory=list)

    def add(self, t: float, x: float, y: float) -> None:
        self.ts.append(t)
        self.xs.append(x)
        self.ys.append(y)

    def finalize(self) -> None:
        order = sorted(range(len(self.ts)), key=lambda i: self.ts[i])
        self.ts = [self.ts[i] for i in order]
        self.xs = [self.xs[i] for i in order]
        self.ys = [self.ys[i] for i in order]

    def at(self, t: float, max_gap: float, hold: float) -> Point | None:
        """Linear interpolation inside gaps <= max_gap; nearest sample within ``hold``; else None."""
        n = len(self.ts)
        if n == 0:
            return None
        i = bisect.bisect_left(self.ts, t)
        if i < n and abs(self.ts[i] - t) < 1e-9:
            return (self.xs[i], self.ys[i])
        if 0 < i < n:
            t0, t1 = self.ts[i - 1], self.ts[i]
            if t1 - t0 <= max_gap:
                f = (t - t0) / (t1 - t0)
                return (self.xs[i - 1] + (self.xs[i] - self.xs[i - 1]) * f, self.ys[i - 1] + (self.ys[i] - self.ys[i - 1]) * f)
        # Out of range or across a gap: hold the nearest sample briefly.
        cands = [j for j in (i - 1, i) if 0 <= j < n]
        j = min(cands, key=lambda j: abs(self.ts[j] - t))
        if abs(self.ts[j] - t) <= hold:
            return (self.xs[j], self.ys[j])
        return None


@dataclass
class Scene:
    match: Record
    segments: list[Record]
    events: list[Record]
    possessions: list[Record]
    roster: dict[str, Record]
    teams: dict[str, Record]
    players: dict[str, Timeline]
    ball: Timeline
    cutaway_players: dict[str, list[str]]  # segment_id -> player_ids in frame (replays, closeups, highlights)
    captions: list[Caption]
    goal_times: dict[str, list[float]]
    duration: float
    sample_gap: float
    stream: list[Record] = field(default_factory=list)
    _seg_ts: list[float] = field(default_factory=list, repr=False)
    _poss_ts: list[float] = field(default_factory=list, repr=False)
    _events_by_id: dict[str, Record] = field(default_factory=dict, repr=False)
    _event_ts: list[float] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, match_dir: Path | str) -> Scene:
        match_dir = Path(match_dir)
        stream = list(iter_jsonl(match_dir / "events.jsonl"))
        tracks_path = match_dir / "tracks.jsonl"
        tracks = list(iter_jsonl(tracks_path)) if tracks_path.exists() else []
        return cls.from_records(stream, tracks)

    @classmethod
    def from_records(cls, stream: list[Record], tracks: list[Record]) -> Scene:
        match = next(r for r in stream if r["type"] == "match")
        segments = sorted((r for r in stream if r["type"] == "camera_segment"), key=lambda s: s["t"])
        events = sorted((r for r in stream if r["type"] == "event"), key=lambda e: e["t"])
        possessions = sorted((r for r in stream if r["type"] == "possession"), key=lambda p: p["t"])
        roster = {p["player_id"]: p for p in match["players"]}
        teams = {t["team_id"]: t for t in match["teams"]}
        main_ids = {s["id"] for s in segments if s["kind"] == "main"}

        players: dict[str, Timeline] = {}
        ball = Timeline()
        cutaway: dict[str, list[str]] = {}
        gaps: list[float] = []
        last_t: dict[str, float] = {}
        for tr in tracks:
            seg_id = tr["segment_id"]
            if seg_id not in main_ids:
                if tr["object"] == "player" and tr.get("player_id"):
                    ids = cutaway.setdefault(seg_id, [])
                    if tr["player_id"] not in ids:
                        ids.append(tr["player_id"])
                continue
            if "pitch" not in tr:
                continue
            x, y = tr["pitch"]["x"], tr["pitch"]["y"]
            if tr["object"] == "ball":
                ball.add(tr["t"], x, y)
                if "ball" in last_t:
                    gaps.append(tr["t"] - last_t["ball"])
                last_t["ball"] = tr["t"]
            elif tr["object"] == "player" and tr.get("player_id"):
                players.setdefault(tr["player_id"], Timeline()).add(tr["t"], x, y)

        # Pass and shot events are precise ball waypoints: start at t, end at t + distance/speed.
        for e in events:
            m = e.get("metrics", {})
            if e["event_type"] in ("pass", "cross", "shot") and "pitch" in e and "pitch_end" in e:
                speed_kmh = m.get("ball_speed_kmh") or m.get("shot_speed_kmh")
                if not speed_kmh:
                    continue
                p0, p1 = e["pitch"], e["pitch_end"]
                d = ((p1["x"] - p0["x"]) ** 2 + (p1["y"] - p0["y"]) ** 2) ** 0.5
                flight = d / (speed_kmh / 3.6)
                ball.add(e["t"], p0["x"], p0["y"])
                ball.add(e["t"] + flight, p1["x"], p1["y"])
        for tl in players.values():
            tl.finalize()
        ball.finalize()

        sample_gap = sorted(gaps)[len(gaps) // 2] if gaps else 1.0
        captions = _build_captions(events, roster, teams)
        goal_times: dict[str, list[float]] = {t: [] for t in teams}
        for e in events:
            if e["event_type"] == "goal" and e.get("team_id"):
                goal_times.setdefault(e["team_id"], []).append(e["t"])
        duration = segments[-1]["t_end"] if segments else match["video"]["duration_s"]
        return cls(
            match=match, segments=segments, events=events, possessions=possessions, roster=roster, teams=teams,
            players=players, ball=ball, cutaway_players=cutaway, captions=captions, goal_times=goal_times,
            duration=duration, sample_gap=sample_gap, stream=stream,
            _seg_ts=[s["t"] for s in segments], _poss_ts=[p["t"] for p in possessions],
            _events_by_id={e["id"]: e for e in events}, _event_ts=[e["t"] for e in events],
        )

    # ------------------------------------------------------------------ queries
    def segment_at(self, t: float) -> Record:
        i = bisect.bisect_right(self._seg_ts, t) - 1
        i = max(0, min(i, len(self.segments) - 1))
        return self.segments[i]

    def segment_by_id(self, seg_id: str) -> Record:
        return next(s for s in self.segments if s["id"] == seg_id)

    def event_by_id(self, event_id: str) -> Record | None:
        return self._events_by_id.get(event_id)

    def last_player_before(self, t: float) -> str | None:
        """The player of the most recent event at or before ``t`` (who the director would cut to)."""
        i = bisect.bisect_right(self._event_ts, t) - 1
        while i >= 0:
            pid = self.events[i].get("player_id")
            if pid and pid in self.roster:
                return pid
            i -= 1
        return None

    def positions_at(self, t: float) -> dict[str, Point]:
        # Cutaway tracks are not in the timelines, so right after a cut back to the main camera the
        # nearest sample can be a full sampling period away; hold at least that long so nobody vanishes.
        max_gap = self.sample_gap * 1.6
        hold = self.sample_gap * 1.05
        out: dict[str, Point] = {}
        for pid, tl in self.players.items():
            p = tl.at(t, max_gap, hold)
            if p is not None:
                out[pid] = p
        return out

    def ball_at(self, t: float) -> Point:
        p = self.ball.at(t, max_gap=self.sample_gap * 2.5, hold=self.sample_gap * 1.5)
        if p is not None:
            return p
        # Nothing nearby: fall back to the last known ball position (dead ball spells).
        if self.ball.ts:
            i = max(0, bisect.bisect_right(self.ball.ts, t) - 1)
            return (self.ball.xs[i], self.ball.ys[i])
        return (PITCH_L / 2, PITCH_W / 2)

    def holder_at(self, t: float) -> str | None:
        i = bisect.bisect_right(self._poss_ts, t) - 1
        if i >= 0:
            p = self.possessions[i]
            if p["t"] <= t < p["t_end"]:
                return p["player_id"]
        return None

    def score_at(self, t: float) -> dict[str, int]:
        return {team: sum(1 for gt in times if gt <= t) for team, times in self.goal_times.items()}

    def clock_at(self, t: float) -> str:
        """Match clock from the period table: MM:SS inside a period, HT between periods, FT after the last."""
        periods = self.match["periods"]
        for per in periods:
            if t < per["t"]:
                # Before this period starts: either pre-match (first period) or an interval.
                return "00:00" if per is periods[0] else ("HT" if per["period"] == 2 else "ET")
            if per["t"] <= t < per["t_end"]:
                start_min = {1: 0, 2: 45, 3: 90, 4: 105, 5: 120}.get(per["period"], 0)
                secs = start_min * 60 + (t - per["t"])
                return f"{int(secs // 60):02d}:{int(secs % 60):02d}"
        # The stream holds every period there is, so after the last one the match is over.
        return "FT"

    def caption_at(self, t: float) -> Caption | None:
        active = [c for c in self.captions if c.t <= t < c.t_end]
        if not active:
            return None
        return max(active, key=lambda c: (c.priority, c.t))

    def describe_event(self, event_id: str) -> str:
        e = self._events_by_id.get(event_id)
        if e is None:
            return event_id
        return _caption_text(e, self.roster, self.teams) or e["event_type"].replace("_", " ")

    def player_name(self, pid: str) -> str:
        p = self.roster.get(pid)
        return p["name"] if p else pid

    def kit_number(self, pid: str) -> str:
        p = self.roster.get(pid)
        return str(p["kit_number"]) if p else ""

    def kit(self, pid: str) -> tuple[str, str]:
        """(fill, text) colours for a player's disc. Unknown ids (vision-layer tracks the roster lacks) get grey."""
        p = self.roster.get(pid)
        team = self.teams.get(p["team_id"]) if p else None
        if p is None or team is None:
            return "#8C8C8C", "#111111"
        if p["position"] == "GK":
            return team["kit"]["gk"], "#111111" if _is_light(team["kit"]["gk"]) else "#FFFFFF"
        fill = team["kit"]["primary"]
        return fill, "#111111" if _is_light(fill) else "#FFFFFF"


def _is_light(hex_colour: str) -> bool:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def _short(roster: dict[str, Record], pid: str | None) -> str:
    if not pid or pid not in roster:
        return "?"
    p = roster[pid]
    return f"{p['name']} ({p['kit_number']})"


def _caption_text(e: Record, roster: dict[str, Record], teams: dict[str, Record]) -> str | None:
    et = e["event_type"]
    who = _short(roster, e.get("player_id"))
    other = _short(roster, e.get("related_player_id"))
    quals = e.get("qualifiers", [])
    if et == "goal":
        team = teams.get(e.get("team_id") or "", {}).get("short_name", "")
        return f"GOAL!  {who}  {team}".rstrip()
    if et == "nutmeg":
        return f"NUTMEG!  {who} through the legs of {other}"
    if et == "skill_move":
        trick = next((q for q in quals), "skill move").replace("_", " ")
        return f"{trick.title()}  {who}"
    if et == "shot":
        how = next((q for q in quals if q in ("saved", "blocked", "off_target", "goal")), "")
        how = {"saved": "saved", "blocked": "blocked", "off_target": "off target", "goal": "goal"}.get(how, how)
        return f"Shot  {who}" + (f"  ({how})" if how else "")
    if et == "save":
        return f"Save  {who}"
    if et == "foul":
        return f"Foul  {who} on {other}"
    if et == "card_yellow":
        return f"Yellow card  {who}"
    if et == "card_red":
        return f"Red card  {who}"
    if et == "take_on":
        return f"TAKE-ON  {who} beats {other}" if e.get("outcome") == "success" else None
    if et == "assist":
        return f"Assist  {who}"
    return None


def _build_captions(events: list[Record], roster: dict[str, Record], teams: dict[str, Record]) -> list[Caption]:
    out: list[Caption] = []
    for e in events:
        rule = CAPTION_RULES.get(e["event_type"])
        if rule is None:
            continue
        text = _caption_text(e, roster, teams)
        if not text:
            continue
        priority, duration = rule
        out.append(Caption(t=e["t"], t_end=e["t"] + duration, text=text, priority=priority, event_id=e["id"], kind=e["event_type"]))
    return out
