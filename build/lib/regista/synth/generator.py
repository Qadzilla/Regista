"""Synthetic match generator: a football-realistic broadcast, with no footage.

Simulates a period of play as a chain of possessions (touches, carries, passes, take-ons,
shots, tackles, interceptions, set pieces) on a 105x68 m pitch, and a broadcast director
who cuts away from the main camera for replays, closeups, and crowd shots at dead balls.
Every record it emits conforms to data/synthetic/schema/regista-events.schema.json.

Deterministic for a given seed. Tunable with ``minutes`` and ``track_hz``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from regista.camera import MAIN_K, MAIN_WINDOW_M, camera_centre, screen_x
from regista.schema import SCHEMA_VERSION

GENERATOR_NAME = "regista-synth"
GENERATOR_VERSION = "0.1.0"

PITCH_L = 105.0
PITCH_W = 68.0
SIM_DT = 0.1          # simulation step, seconds
PLAYER_SPEED = 7.0    # m/s cap for off-ball movement

Record = dict[str, Any]
Point = tuple[float, float]

FIRST_NAMES = [
    "Amari", "Bruno", "Cole", "Dani", "Emeka", "Farid", "Gino", "Hugo", "Idris", "Jonah", "Kwame", "Luca",
    "Mateo", "Nico", "Owen", "Pavel", "Rafa", "Sami", "Teo", "Yusuf", "Zane", "Ade", "Benji", "Caio",
    "Dario", "Elias", "Femi", "Gael", "Haruki", "Ivan", "Jamal", "Kenan", "Leon", "Milan", "Noel", "Otis",
]
LAST_NAMES = [
    "Okafor", "Lindqvist", "Marchetti", "Dubois", "Ferreira", "Haddad", "Novak", "Petrov", "Quinn", "Rahman",
    "Santos", "Tanaka", "Vargas", "Weber", "Yilmaz", "Adeyemi", "Brennan", "Castellanos", "Delgado", "Eriksen",
    "Fontaine", "Gallagher", "Ibarra", "Kowalski", "Mensah", "Nakamura", "Oliveira", "Popescu", "Reyes", "Sorensen",
    "Toure", "Ustinov", "Valente", "Whitfield", "Zidane", "Bakker",
]

# (position, kit number, x, y) anchors for a team attacking toward x = 105.
FORMATION_433 = [
    ("GK", 1, 5, 34),
    ("DF", 2, 24, 8), ("DF", 4, 21, 25), ("DF", 5, 21, 43), ("DF", 3, 24, 60),
    ("MF", 8, 44, 20), ("MF", 6, 37, 34), ("MF", 10, 56, 44),  # the 10 plays between the lines
    ("FW", 7, 66, 10), ("FW", 9, 70, 34), ("FW", 11, 66, 58),
]
BENCH = [("GK", 13), ("DF", 15), ("MF", 14), ("MF", 16), ("FW", 17), ("FW", 20), ("DF", 22)]

TEAM_SPECS = [
    dict(team_id="t_home", name="Northbridge FC", short_name="NOR", kit={"primary": "#C8102E", "secondary": "#FFFFFF", "gk": "#1DB954"}, attack_sign=1),
    dict(team_id="t_away", name="Southgate United", short_name="SOU", kit={"primary": "#1E3A8A", "secondary": "#F5D90A", "gk": "#FF6F00"}, attack_sign=-1),
]

REPLAY_ANGLES = ["reverse", "behind_goal", "high_wide", "touchline_cam"]

# Tuning profiles. "demo" packs a short sample with action; "realistic" lands inside the
# Premier League bands in regista.synth.report over a full match. See that module.
PROFILES: dict[str, dict[str, Any]] = {
    "demo": {
        "hold": (0.8, 3.5), "shot_weights": (20.0, 0.5, 30.0, 0.25, 38.0, 0.06), "take_on": 1.0, "lose": 1.0,
        "nutmeg": 0.18, "skill": 0.20, "foul_on_take_on": 0.25, "foul_on_tackle": 0.0,
        "failed_pass": {"interception": 1.0, "recovery": 0.0, "out": 0.0, "clearance": 0.0},
        "corner_after_off_target": 0.0, "corner_after_block": 0.0, "replay_xg": 0.08,
    },
    "realistic": {  # tuned 2026-10-19 over 8 seeds x 30 min: 13 of 13 bands in regista.synth.report
        "hold": (1.0, 4.0), "shot_weights": (16.0, 0.24, 24.0, 0.08, 32.0, 0.02), "take_on": 0.3, "lose": 0.68,
        "nutmeg": 0.06, "skill": 0.12, "foul_on_take_on": 0.55, "foul_on_tackle": 0.4,
        "failed_pass": {"interception": 0.12, "recovery": 0.64, "out": 0.06, "clearance": 0.18},
        "corner_after_off_target": 0.55, "corner_after_block": 0.55, "replay_xg": 0.15,
    },
}


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pt(x: float, y: float) -> dict[str, float]:
    return {"x": round(clamp(x, 0.0, PITCH_L), 2), "y": round(clamp(y, 0.0, PITCH_W), 2)}


@dataclass
class Team:
    team_id: str
    name: str
    short_name: str
    kit: dict[str, str]
    attack_sign: int
    players: list[Player] = field(default_factory=list)

    @property
    def goal(self) -> Point:
        return (PITCH_L if self.attack_sign > 0 else 0.0, PITCH_W / 2)

    @property
    def starters(self) -> list[Player]:
        return [p for p in self.players if p.starter]

    @property
    def keeper(self) -> Player:
        return next(p for p in self.starters if p.position == "GK")


@dataclass
class Player:
    player_id: str
    team: Team
    name: str
    kit_number: int
    position: str
    anchor: Point
    starter: bool = True
    x: float = 0.0
    y: float = 0.0

    @property
    def pos(self) -> Point:
        return (self.x, self.y)

    @property
    def anchor_abs(self) -> Point:
        ax, ay = self.anchor
        return (ax if self.team.attack_sign > 0 else PITCH_L - ax, ay)


@dataclass
class Segment:
    id: str
    kind: str
    t: float
    t_end: float
    playback_speed: float = 1.0
    replay_of: list[str] = field(default_factory=list)
    replays_window: tuple[float, float] | None = None
    angle: str | None = None
    in_frame: list[Player] | None = None  # None means the main camera projection decides


@dataclass
class SynthResult:
    match: Record
    events: list[Record]        # camera_segment, possession, event, appearance, annotation (sorted by t)
    tracks: list[Record]        # sorted by t
    score: dict[str, int]

    @property
    def stream(self) -> list[Record]:
        return [self.match, *self.events]


class MatchSim:
    def __init__(self, seed: int = 42, minutes: float = 3.0, track_hz: float = 1.0, fps: float = 25.0, profile: str = "demo"):
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; choose from {', '.join(PROFILES)}")
        self.profile = profile
        self.tune = PROFILES[profile]
        self.seed = seed
        self.minutes = minutes
        self.track_hz = track_hz
        self.fps = fps
        self.rng = random.Random(seed)
        # Track sampling has its own stream so the camera model and --track-hz never change the match itself.
        self.track_rng = random.Random(seed * 7919 + 1)
        self.match_id = f"syn_{seed:04d}"

        self.t = 0.0
        self.next_sample_t = 0.0
        self.counters: dict[str, int] = {}
        self.events: list[Record] = []
        self.possessions: list[Record] = []
        self.tracks: list[Record] = []
        self.segments: list[Segment] = []
        self.pending_replays: list[Record] = []
        self.score = {"t_home": 0, "t_away": 0}

        self.ball: list[float] = [PITCH_L / 2, PITCH_W / 2]
        self.ball_speed = 0.0  # m/s
        self.holder: Player | None = None
        self.receiver: Player | None = None
        self.cur_pos: Record | None = None
        self.last_pass: Record | None = None
        self.last_team: Team | None = None

        self.home, self.away = self._build_teams()
        self.teams = {self.home.team_id: self.home, self.away.team_id: self.away}
        self.players = {p.player_id: p for p in self.home.players + self.away.players}
        self._reset_positions()
        self._open_main()

    # ------------------------------------------------------------------ setup
    def _build_teams(self) -> tuple[Team, Team]:
        used: set[str] = set()
        teams: list[Team] = []
        for spec in TEAM_SPECS:
            team = Team(**spec)
            for position, number, ax, ay in FORMATION_433:
                team.players.append(Player(f"{team.team_id}_{number:02d}", team, self._name(used), number, position, (ax, ay)))
            for position, number in BENCH:
                team.players.append(Player(f"{team.team_id}_{number:02d}", team, self._name(used), number, position, (-8.0, 34.0), starter=False))
            teams.append(team)
        return teams[0], teams[1]

    def _name(self, used: set[str]) -> str:
        while True:
            name = f"{self.rng.choice(FIRST_NAMES)} {self.rng.choice(LAST_NAMES)}"
            if name not in used:
                used.add(name)
                return name

    def _reset_positions(self) -> None:
        for team in (self.home, self.away):
            for p in team.starters:
                p.x, p.y = p.anchor_abs
        self.ball = [PITCH_L / 2, PITCH_W / 2]
        self.ball_speed = 0.0

    def _id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}_{n:06d}"

    def _conf(self, lo: float = 0.82, hi: float = 0.99) -> float:
        return round(self.rng.uniform(lo, hi), 3)

    def _clock(self, t: float) -> dict[str, int]:
        return {"period": 1, "minute": int(t // 60), "second": int(t % 60)}

    def other(self, team: Team) -> Team:
        return self.away if team is self.home else self.home

    def nearest(self, point: Point, team: Team, exclude: Player | None = None, outfield: bool = False) -> Player:
        cands = [p for p in team.starters if p is not exclude and (not outfield or p.position != "GK")]
        return min(cands, key=lambda p: dist(p.pos, point))

    # ------------------------------------------------------------------ time
    def advance(self, duration: float, mode: str = "live", ball_to: Point | None = None) -> None:
        """Step the world forward. ``ball_to`` moves the ball linearly over the duration."""
        if duration <= 0:
            return
        start = (self.ball[0], self.ball[1])
        end_t = self.t + duration
        elapsed = 0.0
        while self.t < end_t - 1e-9:
            step = min(SIM_DT, end_t - self.t)
            elapsed += step
            if ball_to is not None:
                f = clamp(elapsed / duration, 0.0, 1.0)
                self.ball[0] = start[0] + (ball_to[0] - start[0]) * f
                self.ball[1] = start[1] + (ball_to[1] - start[1]) * f
            self._move_players(step, mode)
            self.t += step
            if self.t + 1e-9 >= self.next_sample_t:
                self._sample_tracks()
                self.next_sample_t += 1.0 / self.track_hz

    def _move_players(self, step: float, mode: str) -> None:
        ball = (self.ball[0], self.ball[1])
        for team in (self.home, self.away):
            for p in team.starters:
                if p is self.holder:
                    p.x, p.y = ball
                    continue
                ax, ay = p.anchor_abs
                if p is self.receiver:
                    tx, ty = ball
                elif mode == "live":
                    # Team shape: the side in possession pushes up, the other side drops off.
                    if p.position != "GK" and self.last_team is not None:
                        shift = 14.0 if team is self.last_team else -9.0
                        ax = clamp(ax + team.attack_sign * shift, 2.0, PITCH_L - 2.0)
                    pull = 0.08 if p.position == "GK" else 0.35
                    tx, ty = ax + (ball[0] - ax) * pull, ay + (ball[1] - ay) * pull
                else:
                    tx, ty = ax, ay
                dx, dy = tx - p.x, ty - p.y
                d = math.hypot(dx, dy)
                if d > 1e-6:
                    move = min(d, PLAYER_SPEED * step)
                    p.x += dx / d * move + self.rng.gauss(0, 0.05)
                    p.y += dy / d * move + self.rng.gauss(0, 0.05)
                p.x = clamp(p.x, 0.0, PITCH_L)
                p.y = clamp(p.y, 0.0, PITCH_W)

    # ------------------------------------------------------------------ camera
    def _open_main(self) -> None:
        self.segments.append(Segment(self._id("cs"), "main", self.t, self.t))

    def _close_main(self) -> None:
        cur = self.segments[-1]
        if cur.kind == "main":
            if cur.t_end <= cur.t and cur.t >= self.t - 1e-9:
                self.segments.pop()
            else:
                cur.t_end = self.t

    def _cut(self, kind: str, duration: float, **kw: Any) -> Segment:
        """Leave the main camera for ``duration`` seconds, then come back."""
        self._close_main()
        seg = Segment(self._id("cs"), kind, self.t, self.t + duration, **kw)
        self.segments.append(seg)
        self.advance(duration, mode="dead")
        seg.t_end = self.t
        self._open_main()
        return seg

    def _project(self, px: float, py: float) -> dict[str, float] | None:
        """Main-camera bbox (normalised) using the shared camera model; None when out of frame."""
        cx = camera_centre(self.ball[0], MAIN_WINDOW_M)
        xn = screen_x(px, py, cx, MAIN_WINDOW_M, MAIN_K)
        depth = py / PITCH_W
        yc = 0.86 - 0.72 * depth
        s = 1.0 - MAIN_K * depth
        w, h = 0.032 * s, 0.11 * s
        if xn < -w or xn > 1 + w:
            return None
        return {"x": round(clamp(xn - w / 2, 0, 1), 4), "y": round(clamp(yc - h, 0, 1), 4), "w": round(w, 4), "h": round(h, 4)}

    def _sample_tracks(self) -> None:
        seg = self.segments[-1]
        t = round(self.t, 2)
        frame = int(round(self.t * self.fps))

        trng = self.track_rng

        def base(obj: str, track_id: str) -> Record:
            return {
                "type": "track", "id": self._id("tr"), "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
                "source": "synthetic", "confidence": round(trng.uniform(0.8, 0.99), 3),
                "t": t, "frame": frame, "segment_id": seg.id, "object": obj, "track_id": track_id,
            }

        if seg.in_frame is None:
            for team in (self.home, self.away):
                for p in team.starters:
                    bbox = self._project(p.x, p.y)
                    if bbox is None:
                        continue
                    rec = base("player", f"{seg.id}:{p.player_id}")
                    sees_number = trng.random() < 0.72
                    rec.update(
                        player_id=p.player_id, team_id=team.team_id, pitch=pt(p.x, p.y), bbox=bbox,
                        identity={
                            "confidence": round(trng.uniform(0.86, 0.99), 3) if sees_number else round(trng.uniform(0.6, 0.85), 3),
                            "evidence": ["kit_number", "team_colour", "continuity"] if sees_number else ["team_colour", "continuity"],
                        },
                    )
                    self.tracks.append(rec)
            bbox = self._project(self.ball[0], self.ball[1])
            if bbox is not None:
                rec = base("ball", f"{seg.id}:ball")
                rec.update(player_id=None, team_id=None, pitch=pt(self.ball[0], self.ball[1]), speed_kmh=round(self.ball_speed * 3.6, 1),
                           bbox={"x": bbox["x"], "y": round(clamp(bbox["y"] + bbox["h"] - 0.02, 0, 1), 4), "w": 0.012, "h": 0.02})
                self.tracks.append(rec)
            return

        n = max(1, len(seg.in_frame))
        for i, p in enumerate(seg.in_frame):
            width = 0.5 if n == 1 else 0.8 / n
            x0 = 0.25 if n == 1 else 0.1 + i * (0.8 / n)
            rec = base("player", f"{seg.id}:{p.player_id}")
            rec.update(
                player_id=p.player_id, team_id=p.team.team_id, pitch=pt(p.x, p.y),
                bbox={"x": round(x0, 4), "y": 0.08, "w": round(width, 4), "h": 0.84},
                identity={"confidence": round(trng.uniform(0.9, 0.995), 3), "evidence": ["kit_number", "team_colour"]},
            )
            self.tracks.append(rec)
        if seg.kind in ("replay", "highlight"):
            rec = base("ball", f"{seg.id}:ball")
            rec.update(player_id=None, team_id=None, pitch=pt(self.ball[0], self.ball[1]), speed_kmh=0.0,
                       bbox={"x": 0.49, "y": 0.8, "w": 0.03, "h": 0.05})
            self.tracks.append(rec)

    # ------------------------------------------------------------------ records
    def _event(self, event_type: str, player: Player | None, *, t: float | None = None, related: Player | None = None,
               pitch: Point | None = None, pitch_end: Point | None = None, outcome: str = "neutral",
               qualifiers: list[str] | None = None, metrics: dict[str, float] | None = None, under_pressure: bool = False,
               body_part: str | None = None, t_end: float | None = None, team: Team | None = None) -> Record:
        t = self.t if t is None else t
        rec: Record = {
            "type": "event", "id": self._id("ev"), "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
            "source": "synthetic", "confidence": self._conf(),
            "t": round(t, 2), "clock": self._clock(t), "event_type": event_type,
            "player_id": player.player_id if player else None,
            "team_id": (team or (player.team if player else None)).team_id if (team or player) else None,
            "related_player_id": related.player_id if related else None,
            "possession_id": self.cur_pos["id"] if self.cur_pos else None,
            "segment_id": self.segments[-1].id,
            "outcome": outcome,
            "under_pressure": under_pressure,
        }
        if t_end is not None:
            rec["t_end"] = round(t_end, 2)
        if pitch is not None:
            rec["pitch"] = pt(*pitch)
        if pitch_end is not None:
            rec["pitch_end"] = pt(*pitch_end)
        if body_part:
            rec["body_part"] = body_part
        if qualifiers:
            rec["qualifiers"] = qualifiers
        if metrics:
            rec["metrics"] = {k: round(v, 3) for k, v in metrics.items()}
        self.events.append(rec)
        return rec

    def _start_possession(self, p: Player, gained_by: str, *, from_player: Player | None = None) -> None:
        self.holder = p
        self.receiver = None
        self.ball = [p.x, p.y]
        self.ball_speed = 0.0
        self.cur_pos = {
            "type": "possession", "id": self._id("po"), "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
            "source": "synthetic", "confidence": self._conf(),
            "t": round(self.t, 2), "player_id": p.player_id, "team_id": p.team.team_id,
            "gained_by": gained_by, "touches": 0, "pitch": pt(p.x, p.y), "under_pressure": False,
        }
        if self.last_team is not None and self.last_team is not p.team:
            self._event("possession_change", p, related=from_player, pitch=p.pos)
        self.last_team = p.team

    def _end_possession(self, lost_by: str) -> None:
        if self.cur_pos is None:
            return
        pos = self.cur_pos
        pos["t_end"] = round(max(self.t, pos["t"] + 0.1), 2)
        pos["lost_by"] = lost_by
        pos["pitch_end"] = pt(self.ball[0], self.ball[1])
        self.possessions.append(pos)
        self.cur_pos = None
        self.holder = None

    # ------------------------------------------------------------------ director
    def _dead_ball(self, total: float, *, closeup_of: Player | None = None, crowd: bool = False) -> None:
        """Spend ``total`` seconds of dead time: linger, closeup, crowd, then replays of pending events."""
        budget = total
        self.holder = None
        self.receiver = None
        linger = min(1.5, budget)
        self.advance(linger, mode="dead")
        budget -= linger
        if closeup_of is not None and budget >= 4.5:
            self._cut("closeup", 3.0, in_frame=[closeup_of])
            budget -= 3.0
        if crowd and budget >= 4.0:
            self._cut("crowd", 2.5, in_frame=[])
            budget -= 2.5
        # Replays: most recent first, drop anything older than a minute.
        self.pending_replays = [e for e in self.pending_replays if self.t - e["t"] < 60]
        while self.pending_replays and budget >= 7.0:
            ev = self.pending_replays.pop()
            speed = self.rng.choice([0.5, 0.5, 0.25])
            window_len = 4.0 if speed == 0.5 else 2.0
            window = (max(0.0, ev["t"] - window_len * 0.75), ev["t"] + window_len * 0.25)
            duration = round((window[1] - window[0]) / speed, 1)
            if duration > budget:
                break
            involved = [self.players[i] for i in (ev.get("player_id"), ev.get("related_player_id")) if i]
            self._cut("replay", duration, playback_speed=speed, replay_of=[ev["id"]], replays_window=window,
                      angle=self.rng.choice(REPLAY_ANGLES), in_frame=involved)
            budget -= duration
        if budget > 0:
            self.advance(budget, mode="dead")

    def _queue_replay(self, ev: Record) -> None:
        self.pending_replays.append(ev)

    # ------------------------------------------------------------------ play
    def run(self) -> SynthResult:
        end_t = self.minutes * 60.0
        self._event("period_start", None, pitch=(PITCH_L / 2, PITCH_W / 2))
        kicker = next(p for p in self.home.starters if p.kit_number == 9)
        kicker.x, kicker.y = PITCH_L / 2, PITCH_W / 2
        self._event("kick_off", kicker, pitch=kicker.pos)
        self._start_possession(kicker, "kickoff")
        while self.t < end_t:
            self._play_possession()
        self._end_possession("period_end")
        self._event("period_end", None, pitch=(self.ball[0], self.ball[1]))
        period_end_t = self.t
        self.advance(1.0, mode="dead")
        self._highlight_package()
        self._close_main()

        duration = round(self.segments[-1].t_end, 2)
        match = self._match_record(duration, period_end_t)
        appearances = self._appearances()
        annotations = self._annotations()
        order = {"camera_segment": 0, "possession": 1, "event": 2, "appearance": 3, "annotation": 4}
        rows = [self._segment_record(s) for s in self.segments] + self.possessions + self.events + appearances + annotations
        rows.sort(key=lambda r: (r["t"], order[r["type"]], r["id"]))
        self.tracks.sort(key=lambda r: (r["t"], r["id"]))
        return SynthResult(match=match, events=rows, tracks=self.tracks, score=dict(self.score))

    def _play_possession(self) -> None:
        p = self.holder
        assert p is not None and self.cur_pos is not None
        team, opp = p.team, self.other(p.team)
        rng = self.rng
        sign = team.attack_sign

        marker = self.nearest(p.pos, opp)
        pressure = dist(marker.pos, p.pos) < 3.5
        if pressure:
            self.cur_pos["under_pressure"] = True
            self._event("pressure", marker, related=p, pitch=marker.pos, under_pressure=False)

        hold = rng.uniform(*self.tune["hold"])
        touches = max(1, int(hold / 0.8))
        self.cur_pos["touches"] += touches
        for k in range(touches):
            self._event("touch", p, t=self.t + k * hold / touches, pitch=p.pos, under_pressure=pressure,
                        qualifiers=["first_touch"] if k == 0 and self.cur_pos["touches"] == touches else None)

        # Carry: drift toward goal when there is space.
        start = p.pos
        ahead = self.nearest((p.x + 6 * sign, p.y), opp)
        space = dist(ahead.pos, (p.x + 6 * sign, p.y)) > 5.0
        if space and rng.random() < 0.7:
            speed = rng.uniform(3.0, 7.0)
            target = (clamp(p.x + sign * speed * hold, 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, 4.0), 1.0, PITCH_W - 1.0))
        else:
            target = (clamp(p.x + rng.gauss(0, 1.0), 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, 1.0), 1.0, PITCH_W - 1.0))
        t0 = self.t
        self.ball_speed = dist(start, target) / hold
        self.advance(hold, ball_to=target)
        self.ball_speed = 0.0
        carried = dist(start, p.pos)
        if carried > 3.0:
            self._event("carry", p, t=t0, t_end=self.t, pitch=start, pitch_end=p.pos, outcome="success", under_pressure=pressure,
                        metrics={"carry_distance_m": carried, "sprint_speed_kmh": carried / hold * 3.6},
                        qualifiers=["dribble"] if pressure else None)

        dgoal = dist(p.pos, team.goal)
        d1, w1, d2, w2, d3, w3 = self.tune["shot_weights"]
        w_pass = 0.6
        w_take_on = (0.07 + (0.12 if pressure else 0.0)) * self.tune["take_on"]
        w_shot = w1 if dgoal < d1 else w2 if dgoal < d2 else w3 if dgoal < d3 else 0.0
        w_lose = (0.02 + (0.08 if pressure else 0.0)) * self.tune["lose"]
        w_out = 0.02
        action = rng.choices(["pass", "take_on", "shot", "lose", "out"], weights=[w_pass, w_take_on, w_shot, w_lose, w_out])[0]
        if action == "pass":
            self._do_pass(p, pressure)
        elif action == "take_on":
            self._do_take_on(p, marker)
        elif action == "shot":
            self._do_shot(p)
        elif action == "lose":
            if rng.random() < self.tune["foul_on_tackle"]:
                self._foul(marker, p)
            else:
                self._end_possession("dispossessed")
                self._event("tackle", marker, related=p, pitch=marker.pos, outcome="success")
                self._start_possession(marker, "tackle", from_player=p)
        else:
            self._do_out_of_play(p)

    def _pick_pass_target(self, p: Player) -> Player:
        sign = p.team.attack_sign
        cands = []
        for q in p.team.starters:
            if q is p:
                continue
            d = dist(p.pos, q.pos)
            forward = (q.x - p.x) * sign
            w = math.exp(-(((d - 16.0) / 13.0) ** 2)) * (1.0 + 0.06 * clamp(forward, -10.0, 30.0)) + 0.02
            if q.position == "GK":
                w *= 0.15
            cands.append((q, max(w, 0.001)))
        players, weights = zip(*cands)
        return self.rng.choices(players, weights=weights)[0]

    def _do_pass(self, p: Player, pressure: bool) -> None:
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        sign = team.attack_sign
        target = self._pick_pass_target(p)
        d = max(dist(p.pos, target.pos), 1.0)
        forward = (target.x - p.x) * sign
        success_p = clamp(0.97 - 0.008 * d - (0.12 if pressure else 0.0) - (0.06 if forward > 20 else 0.0), 0.4, 0.97)
        ok = rng.random() < success_p
        speed = rng.uniform(10.0, 19.0)
        difficulty = clamp(0.6 * d / 45.0 + (0.25 if pressure else 0.0) + (0.15 if forward > 15 else 0.0), 0.0, 1.0)
        wide = abs(p.y - PITCH_W / 2) > 18
        in_final_third = (p.x if sign > 0 else PITCH_L - p.x) > 70
        kind = "cross" if wide and in_final_third and rng.random() < 0.7 else "pass"
        if ok:
            end = target.pos
        else:
            interceptor = self.nearest(target.pos, opp)
            end = (clamp(interceptor.x + rng.gauss(0, 1.0), 0, PITCH_L), clamp(interceptor.y + rng.gauss(0, 1.0), 0, PITCH_W))
        qualifiers = []
        if forward > 10:
            qualifiers.append("forward")
        if d > 30:
            qualifiers.append("long")
        if kind == "pass" and forward > 15 and in_final_third:
            qualifiers.append("through_ball")
        ev = self._event(kind, p, related=target, pitch=p.pos, pitch_end=end, outcome="success" if ok else "fail",
                         under_pressure=pressure, qualifiers=qualifiers or None,
                         metrics={"pass_distance_m": d, "pass_difficulty": difficulty, "ball_speed_kmh": speed * 3.6},
                         body_part="right_foot" if rng.random() < 0.75 else "left_foot")
        self._end_possession("pass")
        self.receiver = target if ok else None
        self.ball_speed = speed
        self.advance(d / speed, ball_to=end)
        self.ball_speed = 0.0
        if ok:
            self.last_pass = ev
            self._start_possession(target, "pass_received", from_player=p)
            return
        self.last_pass = None
        fp = self.tune["failed_pass"]
        how = rng.choices(list(fp), weights=list(fp.values()))[0]
        here = (self.ball[0], self.ball[1])
        if how == "out" or (kind == "cross" and rng.random() < 0.3):
            # Misplaced ball runs out of play: a throw-in, or a corner when a cross drifts over the goal line.
            if kind == "cross" and rng.random() < 0.35:
                self._corner(team, p)
            else:
                side = 0.0 if here[1] < PITCH_W / 2 else PITCH_W
                self.ball = [clamp(here[0], 1, PITCH_L - 1), side]
                self._dead_ball(rng.uniform(6.0, 9.0))
                thrower = self.nearest((self.ball[0], self.ball[1]), opp, outfield=True)
                thrower.x, thrower.y = self.ball[0], clamp(side, 0.5, PITCH_W - 0.5)
                self._event("throw_in", thrower, pitch=thrower.pos)
                self._start_possession(thrower, "set_piece", from_player=p)
            return
        winner = self.nearest(here, opp)
        if how == "interception":
            self._event("interception", winner, related=p, pitch=winner.pos, outcome="success")
            self._start_possession(winner, "interception", from_player=p)
        elif how == "clearance":
            self._event("clearance", winner, related=p, pitch=winner.pos, outcome="success")
            far = (clamp(winner.x + opp.attack_sign * rng.uniform(25.0, 40.0), 1, PITCH_L - 1), clamp(winner.y + rng.gauss(0, 10.0), 1, PITCH_W - 1))
            self.ball_speed = 18.0
            self.advance(dist(winner.pos, far) / 18.0, ball_to=far)
            self.ball_speed = 0.0
            cands = team.starters + opp.starters
            taker = min(cands, key=lambda q: dist(q.pos, far))
            taker.x, taker.y = far
            self._event("recovery", taker, pitch=far, outcome="success")
            self._start_possession(taker, "loose_ball", from_player=winner)
        else:
            winner.x, winner.y = here
            self._event("recovery", winner, related=p, pitch=winner.pos, outcome="success")
            self._start_possession(winner, "loose_ball", from_player=p)

    def _do_take_on(self, p: Player, defender: Player) -> None:
        rng = self.rng
        team = p.team
        sign = team.attack_sign
        if rng.random() < 0.5:
            ev = self._event("take_on", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True)
            flourish = rng.random()
            if flourish < self.tune["nutmeg"]:
                nut = self._event("nutmeg", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True, qualifiers=["nutmeg"])
                ev["qualifiers"] = ["nutmeg"]
                self._queue_replay(nut)
            elif flourish < self.tune["nutmeg"] + self.tune["skill"]:
                sm = self._event("skill_move", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True,
                                 qualifiers=[rng.choice(["stepover", "elastico", "drag_back", "roulette", "body_feint"])])
                if rng.random() < 0.5:
                    self._queue_replay(sm)
            past = (clamp(p.x + sign * 4.0, 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, 1.5), 1.0, PITCH_W - 1.0))
            self.ball_speed = 5.0
            self.advance(0.8, ball_to=past)
            self.ball_speed = 0.0
            return
        if rng.random() < self.tune["foul_on_take_on"]:
            self._event("take_on", p, related=defender, pitch=p.pos, outcome="fail", under_pressure=True)
            self._foul(defender, p)
            return
        self._event("take_on", p, related=defender, pitch=p.pos, outcome="fail", under_pressure=True)
        self._event("tackle", defender, related=p, pitch=defender.pos, outcome="success")
        self._end_possession("tackled")
        self._start_possession(defender, "tackle", from_player=p)

    def _foul(self, defender: Player, victim: Player) -> None:
        """Defender fouls the ball carrier: free kick to the victim's team from the spot."""
        rng = self.rng
        foul = self._event("foul", defender, related=victim, pitch=defender.pos, outcome="fail")
        self._event("foul_won", victim, related=defender, pitch=victim.pos, outcome="success")
        if rng.random() < 0.15:
            self._event("card_yellow", defender, related=victim, pitch=defender.pos)
        self._queue_replay(foul)
        spot = victim.pos
        team = victim.team
        self._end_possession("foul")
        self._dead_ball(rng.uniform(9.0, 13.0), closeup_of=victim if rng.random() < 0.5 else None)
        self.ball = [spot[0], spot[1]]
        taker = self.nearest(spot, team, outfield=True)
        taker.x, taker.y = spot
        self._event("free_kick", taker, pitch=spot)
        self._start_possession(taker, "set_piece")

    def _corner(self, team: Team, last: Player) -> None:
        """Ball over the goal line off a defender: corner to ``team``."""
        rng = self.rng
        gx = PITCH_L if team.attack_sign > 0 else 0.0
        spot = (gx, 0.0 if rng.random() < 0.5 else PITCH_W)
        self.ball = [clamp(spot[0], 0.3, PITCH_L - 0.3), clamp(spot[1], 0.3, PITCH_W - 0.3)]
        self._dead_ball(rng.uniform(10.0, 14.0))
        taker = self.nearest((self.ball[0], self.ball[1]), team, outfield=True)
        taker.x, taker.y = self.ball[0], self.ball[1]
        self._event("corner", taker, pitch=taker.pos)
        self._start_possession(taker, "set_piece", from_player=last)

    def _do_shot(self, p: Player) -> None:
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        goal = team.goal
        d = max(dist(p.pos, goal), 1.0)
        xg = clamp(1.1 * math.exp(-0.12 * d), 0.02, 0.85)
        speed_kmh = rng.uniform(65.0, 115.0)
        headed = self.last_pass is not None and self.last_pass["event_type"] == "cross" and rng.random() < 0.6
        body_part = "head" if headed else ("right_foot" if rng.random() < 0.7 else "left_foot")
        r = rng.random()
        if r < xg:
            result = "goal"
        else:
            rest = (r - xg) / (1 - xg)
            result = "saved" if rest < 0.4 else "blocked" if rest < 0.65 else "off_target"
        if result in ("goal", "saved"):
            end = (goal[0], clamp(goal[1] + rng.uniform(-3.2, 3.2), 0, PITCH_W))
        elif result == "off_target":
            end = (goal[0], clamp(goal[1] + rng.choice([-1, 1]) * rng.uniform(4.0, 9.0), 0, PITCH_W))
        else:
            end = (clamp(p.x + team.attack_sign * 2.0, 0, PITCH_L), p.y)
        shot = self._event("shot", p, pitch=p.pos, pitch_end=end, outcome="success" if result == "goal" else "fail",
                           qualifiers=[result] + (["header"] if headed else []), body_part=body_part,
                           under_pressure=bool(self.cur_pos and self.cur_pos["under_pressure"]),
                           metrics={"shot_distance_m": d, "shot_speed_kmh": speed_kmh, "xg": xg})
        if result == "goal" or xg > self.tune["replay_xg"]:
            self._queue_replay(shot)
        self._end_possession("shot")
        self.ball_speed = speed_kmh / 3.6
        self.advance(dist(p.pos, end) / self.ball_speed, ball_to=end)
        self.ball_speed = 0.0

        if result == "goal":
            assist_by = None
            if self.last_pass and self.last_pass["team_id"] == team.team_id and self.t - self.last_pass["t"] < 8.0:
                assist_by = self.players[self.last_pass["player_id"]]
            goal_ev = self._event("goal", p, related=assist_by, pitch=p.pos, pitch_end=end, outcome="success", body_part=body_part,
                                  metrics={"xg": xg, "shot_distance_m": d})
            if assist_by is not None:
                self._event("assist", assist_by, related=p, pitch=assist_by.pos, outcome="success")
                self.last_pass["qualifiers"] = list(dict.fromkeys(self.last_pass.get("qualifiers", []) + ["key_pass", "assist"]))
            self.score[team.team_id] += 1
            self._queue_replay(goal_ev)
            self._dead_ball(rng.uniform(24.0, 32.0), closeup_of=p, crowd=True)
            self._reset_positions()
            kicker = next(q for q in opp.starters if q.kit_number == 9)
            kicker.x, kicker.y = PITCH_L / 2, PITCH_W / 2
            self._event("kick_off", kicker, pitch=kicker.pos)
            self._start_possession(kicker, "kickoff", from_player=p)
        elif result == "saved":
            keeper = opp.keeper
            self._event("save", keeper, related=p, pitch=keeper.pos, outcome="success")
            if self.last_pass and self.last_pass["team_id"] == team.team_id and self.t - self.last_pass["t"] < 8.0:
                self.last_pass["qualifiers"] = list(dict.fromkeys(self.last_pass.get("qualifiers", []) + ["key_pass"]))
            keeper.x, keeper.y = self.ball[0], self.ball[1]
            self._start_possession(keeper, "goalkeeper_claim", from_player=p)
        elif result == "blocked":
            blocker = self.nearest(p.pos, opp, outfield=True)
            self._event("block", blocker, related=p, pitch=blocker.pos, outcome="success")
            if rng.random() < self.tune["corner_after_block"]:
                self._corner(team, blocker)
                self.last_pass = None
                return
            loose = (clamp(self.ball[0] + rng.gauss(0, 4.0), 1, PITCH_L - 1), clamp(self.ball[1] + rng.gauss(0, 4.0), 1, PITCH_W - 1))
            self.ball_speed = 6.0
            self.advance(0.7, ball_to=loose)
            self.ball_speed = 0.0
            cands = team.starters + opp.starters
            winner = min(cands, key=lambda q: dist(q.pos, loose))
            winner.x, winner.y = loose
            self._event("recovery", winner, pitch=loose, outcome="success")
            self._start_possession(winner, "rebound" if winner.team is team else "loose_ball", from_player=p)
        elif rng.random() < self.tune["corner_after_off_target"]:
            self._dead_ball(1.5, closeup_of=p if rng.random() < 0.5 else None)
            self._corner(team, self.nearest(p.pos, opp, outfield=True))
        else:
            self._dead_ball(rng.uniform(10.0, 14.0), closeup_of=p if rng.random() < 0.5 else None)
            keeper = opp.keeper
            spot = (5.5 if opp.attack_sign > 0 else PITCH_L - 5.5, PITCH_W / 2 + rng.choice([-1, 1]) * 9.0)
            keeper.x, keeper.y = spot
            self.ball = [spot[0], spot[1]]
            self._event("goal_kick", keeper, pitch=spot)
            self._start_possession(keeper, "set_piece", from_player=p)
        self.last_pass = None

    def _do_out_of_play(self, p: Player) -> None:
        rng = self.rng
        opp = self.other(p.team)
        side = 0.0 if p.y < PITCH_W / 2 else PITCH_W
        out_pt = (clamp(p.x + rng.gauss(0, 3.0), 1, PITCH_L - 1), side)
        self._event("touch", p, pitch=p.pos, pitch_end=out_pt, outcome="fail", qualifiers=["out_of_play"])
        self._end_possession("out_of_play")
        self.ball_speed = 8.0
        self.advance(dist(p.pos, out_pt) / 8.0, ball_to=out_pt)
        self.ball_speed = 0.0
        self._dead_ball(rng.uniform(6.0, 9.0), closeup_of=p if rng.random() < 0.4 else None)
        thrower = self.nearest(out_pt, opp, outfield=True)
        thrower.x, thrower.y = out_pt[0], clamp(side, 0.5, PITCH_W - 0.5)
        self.ball = [thrower.x, thrower.y]
        self._event("throw_in", thrower, pitch=thrower.pos)
        self._start_possession(thrower, "set_piece", from_player=p)

    def _highlight_package(self) -> None:
        """End-of-period montage: goals, best chances, and skill, as ``highlight`` segments."""
        picks = [e for e in self.events if e["event_type"] in ("goal", "nutmeg")]
        shots = sorted((e for e in self.events if e["event_type"] == "shot" and e["outcome"] != "success"),
                       key=lambda e: -e["metrics"]["xg"])
        picks += shots[:2]
        picks = sorted({e["id"]: e for e in picks}.values(), key=lambda e: e["t"])[:5]
        for ev in picks:
            involved = [self.players[i] for i in (ev.get("player_id"), ev.get("related_player_id")) if i]
            window = (max(0.0, ev["t"] - 3.5), ev["t"] + 1.5)
            self._cut("highlight", 5.0, playback_speed=1.0, replay_of=[ev["id"]], replays_window=window, angle="high_wide", in_frame=involved)

    # ------------------------------------------------------------------ post-processing
    def _segment_record(self, s: Segment) -> Record:
        rec: Record = {
            "type": "camera_segment", "id": s.id, "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
            "source": "synthetic", "confidence": round(self.track_rng.uniform(0.9, 0.995), 3),
            "t": round(s.t, 2), "t_end": round(s.t_end, 2), "kind": s.kind, "playback_speed": s.playback_speed,
        }
        if s.replay_of:
            rec["replay_of"] = s.replay_of
        if s.replays_window:
            rec["replays_window"] = {"t": round(s.replays_window[0], 2), "t_end": round(s.replays_window[1], 2)}
        if s.angle:
            rec["angle"] = s.angle
        return rec

    def _match_record(self, duration: float, period_end_t: float) -> Record:
        return {
            "type": "match", "id": f"ma_{self.match_id}", "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
            "source": "synthetic",
            "competition": "Regista Synthetic League", "season": "2026/27", "date": "2026-10-19", "venue": "Northbridge Arena",
            "home_team_id": self.home.team_id, "away_team_id": self.away.team_id,
            "teams": [{"team_id": t.team_id, "name": t.name, "short_name": t.short_name, "kit": t.kit} for t in (self.home, self.away)],
            "players": [
                {"player_id": p.player_id, "team_id": p.team.team_id, "name": p.name, "kit_number": p.kit_number,
                 "position": p.position, "starter": p.starter}
                for t in (self.home, self.away) for p in t.players
            ],
            "video": {"video_id": f"{self.match_id}_broadcast", "fps": self.fps, "width": 1920, "height": 1080,
                      "duration_s": duration, "main_camera": "broadcast_wide"},
            "periods": [{"period": 1, "t": 0.0, "t_end": round(period_end_t, 2), "left_to_right_team_id": self.home.team_id}],
            "score": dict(self.score),
            "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "seed": self.seed,
                          "params": {"minutes": self.minutes, "track_hz": self.track_hz, "fps": self.fps, "profile": self.profile}},
        }

    def _appearances(self) -> list[Record]:
        seg_by_id = {s.id: s for s in self.segments}
        gap = 1.5 / self.track_hz
        runs: dict[tuple[str, str], list[Record]] = {}
        for tr in self.tracks:
            if tr["object"] != "player" or not tr.get("player_id"):
                continue
            runs.setdefault((tr["segment_id"], tr["player_id"]), []).append(tr)
        out: list[Record] = []
        for (seg_id, player_id), rows in runs.items():
            seg = seg_by_id[seg_id]
            rows.sort(key=lambda r: r["t"])
            chunk: list[Record] = []
            for r in rows + [None]:
                if r is not None and (not chunk or r["t"] - chunk[-1]["t"] <= gap + 1e-9):
                    chunk.append(r)
                    continue
                if chunk:
                    t0 = chunk[0]["t"]
                    t1 = min(seg.t_end, chunk[-1]["t"] + 1.0 / self.track_hz)
                    if t1 > t0:
                        area = sum(c["bbox"]["w"] * c["bbox"]["h"] for c in chunk) / len(chunk)
                        on_ball = any(p["player_id"] == player_id and p["t"] < t1 and t0 < p["t_end"] for p in self.possessions)
                        out.append({
                            "type": "appearance", "id": self._id("ap"), "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
                            "source": "synthetic", "confidence": round(self.track_rng.uniform(0.85, 0.99), 3),
                            "t": round(t0, 2), "t_end": round(t1, 2), "segment_id": seg_id, "player_id": player_id,
                            "on_ball": on_ball, "prominence": round(clamp(area / 0.3, 0.0, 1.0), 3),
                        })
                chunk = [r] if r is not None else []
        return out

    def _annotations(self) -> list[Record]:
        """Placeholder annotations showing the shape of human feedback. No person produced these:
        they are ``source: synthetic`` with ``simulates: human`` so nothing downstream can mistake
        them for real review data."""
        out: list[Record] = []

        def ann(target: Record, verdict: str, note: str, correction: Record | None = None) -> None:
            rec: Record = {
                "type": "annotation", "id": self._id("an"), "match_id": self.match_id, "schema_version": SCHEMA_VERSION,
                "source": "synthetic", "simulates": "human", "confidence": 1,
                "t": target["t"], "target_id": target["id"], "target_type": target["type"], "verdict": verdict,
                "note": note, "annotator": "placeholder", "annotated_at": f"2026-10-19T18:{len(out):02d}:00Z",
            }
            if correction:
                rec["correction"] = correction
            out.append(rec)

        nut = next((e for e in self.events if e["event_type"] == "nutmeg"), None)
        if nut:
            ann(nut, "confirm", "Clean nutmeg, keep it.")
        pressure = next((e for e in self.events if e["event_type"] == "pressure"), None)
        if pressure:
            ann(pressure, "reject", "Defender was jogging, not pressing.")
        track = next((tr for tr in self.tracks if tr["object"] == "player" and "kit_number" not in tr["identity"]["evidence"]), None)
        if track:
            team = self.teams[track["team_id"]]
            other = next(p for p in team.starters if p.player_id != track["player_id"])
            ann(track, "correct", "Number was hidden; this is actually the other full-back.", {"player_id": other.player_id})
        return out


def generate(seed: int = 42, minutes: float = 3.0, track_hz: float = 1.0, fps: float = 25.0, profile: str = "demo") -> SynthResult:
    return MatchSim(seed=seed, minutes=minutes, track_hz=track_hz, fps=fps, profile=profile).run()
