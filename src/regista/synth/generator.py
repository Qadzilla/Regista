"""Synthetic match generator: a football-realistic broadcast, with no footage.

Simulates a period of play as a chain of possessions (touches, carries, passes, take-ons,
shots, tackles, interceptions, set pieces) on a 105x68 m pitch, and a broadcast director
who cuts away from the main camera for replays, closeups, and crowd shots at dead balls.
Every record it emits conforms to regista/schemas/regista-events.schema.json.

Deterministic for a given seed. Tunable with ``minutes`` and ``track_hz``.
"""

from __future__ import annotations

import math
from collections import defaultdict
import random
from dataclasses import dataclass, field
from typing import Any

from regista.camera import MAIN_K, MAIN_WINDOW_M, camera_centre, screen_x
from regista.schema import LEGACY_SCHEMA_VERSION, SCHEMA_VERSION
from regista.synth.physical import METHOD as PHYSICAL_METHOD, Body

GENERATOR_NAME = "regista-synth"
GENERATOR_VERSION = "0.1.0"          # without player attributes: unchanged since 0.1.0, byte for byte
LEAGUE_GENERATOR_VERSION = "0.3.0"   # with them (league mode): player ratings drive outcomes, plus the 0.2.0 events;
# 0.3.0: every player moves at 10 Hz within his own pace and acceleration, and each gets a ``physical`` record

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
# The Regista League's profile: "realistic" retuned for two halves with player ratings (league mode, below). Without
# ratings it is only a tuning; with them, regista.synth.report --league checks it against every band.
PROFILES["league"] = {**PROFILES["realistic"], "shot_weights": (16.0, 0.135, 24.0, 0.12, 32.0, 0.085), "lose": 0.90,
                      "foul_on_tackle": 0.34,
                      "failed_pass": {"interception": 0.08, "recovery": 0.68, "out": 0.06, "clearance": 0.18}}

# ---------------------------------------------------------------------------- league mode: players with ratings
#
# A team whose squad carries hidden ratings (regista.season.league.assign_attributes) switches the match into league mode:
# outcomes depend on the players involved, and the 0.2.0 events appear (substitution, penalty, aerial_duel, card_red,
# offside, real through balls). Without ratings nothing below runs and every random draw happens exactly as in 0.1.0.
#
# A rating moves an outcome through its skill z = (rating - SKILL_CENTRE[key]) / RATING_SD, added in log-odds with the
# weight in LEAGUE. Each centre is about the rating of the average player who performs that action in the league, so
# league-wide rates stay where the profile was tuned. Finishing's centre (75 since generator 0.3.0, when players began
# to move within their own pace and more of the shots came from distance; 78.5 before) is set so the league's goals
# minus xG sums to about zero over several seasons, so xG stays the chance's quality and the rating decides who beats
# it. Defending's (62) is the average marker's, not the average tackler's: whoever is nearest the ball defends.
ROLE_OF_KIT: dict[int, str] = {1: "GK", 13: "GK", 2: "FB", 3: "FB", 22: "FB", 4: "CB", 5: "CB", 15: "CB", 6: "DM", 16: "DM",
                               8: "CM", 14: "CM", 10: "AM", 7: "W", 11: "W", 17: "W", 9: "ST", 20: "ST"}
RATING_SD = 7.0
SKILL_CENTRE: dict[str, float] = {  # measured over league seasons (see the comment above)
    "finishing": 75.0, "passing": 68.0, "vision": 66.0, "dribbling": 69.0, "defending": 62.0, "aerial": 66.0,
    "stamina": 73.0, "shot_stopping": 75.0, "handling": 72.0, "distribution": 64.0,
}
LEAGUE: dict[str, Any] = {
    "pass_bias": 0.20,         # league-wide completion shift (log-odds), tuned so completion stays in band
    "cross_delivery": -1.0,    # crosses into a crowded box arrive less often than a pass of the same length
    "pass_skill": 0.22,        # passer's passing on completion (log-odds per z)
    "pass_vision_tb": 0.25,    # passer's vision on a through ball's completion
    "pass_defender": 0.14,     # the nearest defender to the ball's end point (defending), against
    "pass_pressure": 0.10,     # the marker's defending, when the passer is under pressure
    "vision_forward": 0.012,   # vision tilts target choice toward runners further forward (per z, per metre)
    "receive_passing": 0.30,   # teammates pick good passers as targets more often (log scale per z)
    "find_finisher": 0.25,     # ... and, in the final third, good finishers (log scale per z)
    "create_shot": 0.30,       # a pass from a passer with vision sets up a shot more often (log scale per z)
    "carry_drive": 0.15,       # good dribblers carry the ball into space more often
    "lead_m": 1.5,             # completed forward passes into the final third lead the receiver into space, by vision
    "through_ball": 0.007,     # chance a forward pass to a runner in the attacking half is played in behind
    "through_vision": 0.45,    # ... rising with the passer's vision (log scale per z)
    "through_base": 0.55,      # through-ball completion for average players
    "offside_through": 0.30,   # mistimed runs on a ball in behind: offside
    "offside_long": 0.06,      # a long forward ball to the most advanced attacker: offside
    "shot_drive": 0.22,        # finishers shoot a little more often (weight, log scale per z)
    "finish": 0.45,            # finishing on goal probability (log-odds per z)
    "keeper": 0.16,            # the keeper's shot stopping, against
    "on_target": 0.15,         # finishing on hitting the target when it is not a goal
    "header_xg": 0.65,         # headers are worse chances than shots from the same spot (league xG model)
    "strong_foot": 0.06,       # strong foot / weak foot on goal probability (balanced: 0.8 * 0.06 = 0.2 * 0.24)
    "weak_foot": 0.24,
    "hold": 0.30,              # keeper's handling on holding a save (else a parry and a rebound)
    "take_on_base": 0.5, "take_on_skill": 0.40,   # take-on: dribbling minus the defender's defending
    "take_on_drive": 0.18,     # good dribblers attempt more take-ons
    "flourish": 0.25,          # nutmeg and skill-move chances rise with dribbling
    "lose_defender": 0.18, "lose_dribbler": 0.12,  # dispossession: marker's defending against holder's dribbling
    "foul_discipline": 0.20,   # better defenders foul less
    "interception_skill": 0.50,  # a failed pass is read (interception) rather than picked up loose, by defending
    "box_foul_given": 0.22,    # contact in the box: given as a penalty this often, else the defender wins it cleanly
    "penalty_xg": 0.79,        # FBref/Opta penalty xG (docs/scout-terminal/industry-metrics.md #10)
    "straight_red": 0.004,      # per foul
    "yellow": 0.17,            # per foul (yellow cards are a diagnostic: no band)
    "second_yellow": 0.08,     # ... and for a player already booked
    "aerial_cross": 0.80, "aerial_long": 0.65,  # share of crosses / long balls contested in the air (if a defender is near)
    "aerial_reach_m": 8.5,     # a defender this close to where the ball comes down contests it
    "aerial_skill": 0.45,      # aerial z difference
    "aerial_height": 0.25,     # per 10 cm of height difference
    "aerial_defender_edge": 0.25,  # defenders attacking the ball in front of them win a few more
    "header_clear_corner": 0.08,   # a defender's header from a cross goes out for a corner
    "goal_kick_long": 0.5,     # goal kicks hit long to the front players
    "sub_window": (0.58, 0.95),  # substitutions happen at stoppages from about the hour mark
}
# League-mode motion (regista.synth.physical): every player on the pitch moves every 0.1 s within his own top speed and
# acceleration, tiring with his stamina. Speeds in m/s. The caps say how hard a player is willing to go in each situation;
# his own top speed (``top_speed_kmh``) and acceleration (``acceleration_ms2``) say what he can do. Tuned so the league
# lands inside the physical bands in regista.synth.report (Premier League and FIFA World Cup norms, sources cited there).
MOTION: dict[str, Any] = {
    "walk": 1.5,               # dead ball: walking back into shape
    "jog": 3.4,                # jogging (12 km/h)
    "run": 5.0,                # running (18 km/h)
    "high": 6.4,               # the cap for a long move that is not a sprint (23 km/h)
    "gain": 0.9,               # desired speed per metre still to go (an arrive behaviour: slows down as he gets there)
    "ramp": ((0.0, 0.0), (4.0, 1.6), (6.0, 2.4), (9.0, 4.6), (16.0, 6.4)),  # off the ball: (metres from his target, cap)
    "ball_lag_s": 1.5,         # the shape follows where the ball has been over the last few seconds, not every touch
    "comfort_acc": 1.4,        # m/s^2: unhurried moves speed up gently; urgent ones use his full acceleration
    "taper": 3.0,              # full acceleration up to two thirds of top speed, then tapering to nothing at top speed
    "shift": (14.0, -9.0),     # team shape: the side in possession pushes up, the other drops off (as in 0.1.0)
    "shift_rate": 6.0,         # ... at this speed (m/s), not in one jump
    "pull": {"GK": 0.20, "CB": 0.33, "FB": 0.40, "DM": 0.58, "CM": 0.60, "AM": 0.44, "W": 0.40, "ST": 0.38},
    "wander_m": (0.7, 0.5),    # a slow personal drift around the shape position (Ornstein-Uhlenbeck step, each second):
                               # more in possession (finding space), less out of it
    "press_gap_m": 5.5,        # the presser closes the holder down to about this distance, goal-side
    "press_sprint_m": 10.0,    # ... sprinting when he is further away than this (if his reserve allows)
    "run_rate": {"W": 0.0055, "ST": 0.0015, "AM": 0.002, "FB": 0.0045, "CM": 0.003, "DM": 0.0015, "CB": 0.0006, "GK": 0.0},
    "run_s": (2.0, 4.0),       # an attacking run lasts this long
    "run_m": (14.0, 26.0),     # ... toward goal this far
    "transition_s": 3.0,       # after a turnover the side that lost the ball recovers at a sprint, if far out of shape
    "track_runs": True,        # the nearest defender follows an attacking run
    "recover_m": 12.0,
    "sprint_back": ("CB", "FB", "DM", "CM"),
    "dribble": 0.82,           # carrying the ball: at most this share of his top speed
    "fatigue": 0.35,           # willingness to run fades by up to this share over a match (less with stamina)
    "fatigue_vmax": 0.08,      # ... and top speed by a twelfth of that
    "reserve_drain": 0.065,    # anaerobic reserve drained per second per m/s above 5.5 m/s (19.8 km/h)
    "reserve_back": 0.020,     # ... and refilled per second below 4 m/s
    "reserve_min": 0.25,       # no sprint starts below this reserve
    "reach_m": 0.6,            # a player has reached a loose ball within this distance
}
SUB_COUNTS = ((2, 1), (3, 3), (4, 5), (5, 4))   # (substitutions per team, weight): mean 3.9, as the Premier League's 2023-24
SUB_GROUPS = {"FB": "DEF", "CB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID", "W": "ATT", "ST": "ATT"}


def _logit(p: float) -> float:
    p = clamp(p, 1e-4, 1 - 1e-4)
    return math.log(p / (1 - p))


def _sigmoid(v: float) -> float:
    return 1.0 / (1.0 + math.exp(-v))


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
    club_id: str | None = None                       # a club that exists across matches (regista.season)
    squad: list[dict[str, Any]] | None = None        # fixed names and global ids, formation order then bench
    players: list[Player] = field(default_factory=list)

    @property
    def goal(self) -> Point:
        return (PITCH_L if self.attack_sign > 0 else 0.0, PITCH_W / 2)

    @property
    def starters(self) -> list[Player]:
        """The players on the pitch now: the starters, until a substitution or a red card (league mode) changes them."""
        return [p for p in self.players if p.on]

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
    global_id: str | None = None   # the same person in every match of a season (regista.season)
    x: float = 0.0
    y: float = 0.0
    attrs: dict[str, float] | None = None   # hidden ratings (league mode); None otherwise
    role: str | None = None                 # 4-3-3 slot of the kit number (GK, FB, CB, DM, CM, AM, W, ST)
    height_cm: float | None = None
    foot: str | None = None                 # preferred foot: right, left or both
    on: bool | None = None                  # on the pitch now (starts as ``starter``)
    body: Body | None = None                # motion state and physical meters (league mode); None otherwise

    def __post_init__(self) -> None:
        if self.on is None:
            self.on = self.starter

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
    def __init__(self, seed: int = 42, minutes: float = 3.0, track_hz: float = 1.0, fps: float = 25.0, profile: str = "demo",
                 periods: int = 1, teams: list[dict[str, Any]] | None = None, match_id: str | None = None,
                 meta: dict[str, str] | None = None):
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; choose from {', '.join(PROFILES)}")
        if periods not in (1, 2):
            raise ValueError("periods must be 1 or 2")
        self.profile = profile
        self.tune = PROFILES[profile]
        self.periods = periods
        self.team_specs = _team_specs(teams)
        # League mode: the squads carry hidden ratings. Everything it changes is behind ``self.league``.
        self.league = any("attributes" in m for spec in self.team_specs for m in spec.get("squad") or [])
        self.schema_version = SCHEMA_VERSION if self.league else LEGACY_SCHEMA_VERSION
        self.period = 1
        self.period_start_t = 0.0
        self.period_table: list[dict[str, Any]] = []
        self.seed = seed
        self.minutes = minutes  # per period
        self.track_hz = track_hz
        self.fps = fps
        self.rng = random.Random(seed)
        # Track sampling has its own stream so the camera model and --track-hz never change the match itself.
        self.track_rng = random.Random(seed * 7919 + 1)
        self.match_id = match_id or f"syn_{seed:04d}"
        # competition, season, date, venue for the match record (a season's fixtures set them; defaults otherwise)
        self.meta = {k: str(v) for k, v in (meta or {}).items() if k in ("competition", "season", "date", "venue")}

        self.t = 0.0
        self.next_sample_t = 0.0
        self.counters: dict[str, int] = {}
        self.events: list[Record] = []
        self.possessions: list[Record] = []
        self.tracks: list[Record] = []
        self.segments: list[Segment] = []
        self.pending_replays: list[Record] = []
        self.score = {"t_home": 0, "t_away": 0}
        # Take-on choreography for the recorded tracks (see _choreograph); never read by the simulation itself.
        self.duels: list[dict[str, Any]] = []

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
        # League-mode state (never read otherwise).
        self.pos_pass: Record | None = None      # the completed pass that started the current possession
        self.yellows: set[str] = set()
        self.goal_kick_long = False              # the next pass is a goal kick hit long
        self.sub_plan: dict[str, list[float]] = {}
        self.subbed: set[str] = set()            # players who came off or came on (nobody comes back, nobody goes twice)
        self.in_period = False                   # the clock is running (physical meters count only then)
        self.flight: tuple[Point, float] | None = None   # a ball in the air or on the ground: (where it goes, when it gets there)
        self.chasers: dict[str, Point] = {}      # players running to where the ball will be
        self.dead_goto: dict[str, Point] = {}    # set-piece takers walking to the spot during a dead ball
        self.shift: dict[str, float] = {}        # each team's shape shift (league mode moves it gradually)
        self.transition_t = -1e9                 # when possession last changed sides
        self.ball_seen = [PITCH_L / 2, PITCH_W / 2]   # where the ball has been lately (the shape follows it)
        if self.league:
            self._plan_substitutions()
            # Motion has its own random stream, so the wander of 22 players never reorders the match's own draws.
            self.move_rng = random.Random(seed * 104729 + 3)
            for p in self.players.values():
                a = p.attrs or {}
                stz = (a.get("stamina", SKILL_CENTRE["stamina"]) - SKILL_CENTRE["stamina"]) / RATING_SD
                p.body = Body(vmax=a.get("top_speed_kmh", 32.0) / 3.6, acc=a.get("acceleration_ms2", 3.8), stamina_z=stz,
                              pull=MOTION["pull"].get(p.role or "", 0.35), run_rate=MOTION["run_rate"].get(p.role or "", 0.0))
            self.shift = {self.home.team_id: 0.0, self.away.team_id: 0.0}

    # ------------------------------------------------------------------ setup
    def _build_teams(self) -> tuple[Team, Team]:
        used: set[str] = set()
        teams: list[Team] = []
        for spec in self.team_specs:
            team = Team(**spec)
            # A season squad brings its own names and global ids, so the same people play every match; without one,
            # names are drawn from the match's own random stream (unchanged since 0.1.0).
            people = iter(team.squad or [])
            def who() -> tuple[str, str | None, dict[str, Any]]:
                if team.squad:
                    person = next(people)
                    return person["name"], person["global_id"], _league_fields(person)
                return self._name(used), None, {}
            for position, number, ax, ay in FORMATION_433:
                name, gid, extra = who()
                team.players.append(Player(f"{team.team_id}_{number:02d}", team, name, number, position, (ax, ay), global_id=gid,
                                           **extra))
            for position, number in BENCH:
                name, gid, extra = who()
                team.players.append(Player(f"{team.team_id}_{number:02d}", team, name, number, position, (-8.0, 34.0), starter=False,
                                           global_id=gid, **extra))
            for pl in team.players:
                if pl.attrs is not None:
                    pl.role = ROLE_OF_KIT.get(pl.kit_number, pl.role)
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
                ax, ay = p.anchor_abs
                self._place(p, ax, ay, stop=True)
        self.ball = [PITCH_L / 2, PITCH_W / 2]
        self.ball_speed = 0.0

    def _id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}_{n:06d}"

    def _conf(self, lo: float = 0.82, hi: float = 0.99) -> float:
        return round(self.rng.uniform(lo, hi), 3)

    def _clock(self, t: float) -> dict[str, int]:
        elapsed = max(0.0, t - self.period_start_t)
        return {"period": self.period, "minute": 45 * (self.period - 1) + int(elapsed // 60), "second": int(elapsed % 60)}

    def other(self, team: Team) -> Team:
        return self.away if team is self.home else self.home

    def nearest(self, point: Point, team: Team, exclude: Player | None = None, outfield: bool = False) -> Player:
        cands = [p for p in team.starters if p is not exclude and (not outfield or p.position != "GK")]
        return min(cands, key=lambda p: dist(p.pos, point))

    # ------------------------------------------------------------------ league mode: skills and helpers
    def z(self, p: Player, key: str) -> float:
        """The player's skill at ``key`` in standard deviations from the average player doing that action (league mode)."""
        return (p.attrs.get(key, SKILL_CENTRE[key]) - SKILL_CENTRE[key]) / RATING_SD if p.attrs else 0.0

    def goal_probability(self, shooter: Player, keeper: Player, xg: float, *, headed: bool = False, weak: bool = False) -> float:
        """Chance this shot goes in: its xG moved by the shooter's finishing (aerial for a header), the foot, and the
        keeper's shot stopping, in log-odds."""
        lo = _logit(xg) + LEAGUE["finish"] * self.z(shooter, "aerial" if headed else "finishing") \
            - LEAGUE["keeper"] * self.z(keeper, "shot_stopping")
        if not headed:
            lo += -LEAGUE["weak_foot"] if weak else LEAGUE["strong_foot"]
        return _sigmoid(lo)

    def take_on_probability(self, dribbler: Player, defender: Player) -> float:
        """Chance a take-on beats the defender: dribbling against defending."""
        edge = self.z(dribbler, "dribbling") - self.z(defender, "defending")
        return _sigmoid(_logit(LEAGUE["take_on_base"]) + LEAGUE["take_on_skill"] * edge)

    def aerial_probability(self, attacker: Player, defender: Player) -> float:
        """Chance the attacker wins a contested header: aerial ratings and height, a small edge to the defender."""
        edge = LEAGUE["aerial_skill"] * (self.z(attacker, "aerial") - self.z(defender, "aerial")) \
            + LEAGUE["aerial_height"] * ((attacker.height_cm or 180.0) - (defender.height_cm or 180.0)) / 10.0 \
            - LEAGUE["aerial_defender_edge"]
        return _sigmoid(edge)

    def att_x(self, team: Team, x: float) -> float:
        """x in ``team``'s attacking frame (it attacks toward 105)."""
        return x if team.attack_sign > 0 else PITCH_L - x

    def in_box(self, team: Team, point: Point) -> bool:
        """Inside the penalty area ``team`` attacks."""
        return self.att_x(team, point[0]) > PITCH_L - 16.5 and abs(point[1] - PITCH_W / 2) < 20.16

    def foot_for(self, p: Player, strong_share: float = 0.8) -> tuple[str, bool]:
        """(body part, weak foot?) for a kick, from the preferred foot."""
        if p.foot == "both":
            side = "right_foot" if self.rng.random() < 0.5 else "left_foot"
            return side, False
        strong = "left_foot" if p.foot == "left" else "right_foot"
        if self.rng.random() < strong_share:
            return strong, False
        return ("right_foot" if strong == "left_foot" else "left_foot"), True

    def _kicker(self, team: Team) -> Player:
        """Who kicks off: the 9; in league mode, whoever plays furthest forward when the 9 has gone off."""
        nine = next((q for q in team.starters if q.kit_number == 9), None)
        if nine is not None or not self.league:
            return nine if nine is not None else next(q for q in team.starters if q.kit_number == 9)
        return max(team.starters, key=lambda q: (q.anchor[0], -abs(q.anchor[1] - PITCH_W / 2), -q.kit_number))

    def _match_elapsed(self) -> float:
        """Fraction of the match played, by the clock."""
        played = (self.period - 1) * self.minutes * 60.0 + max(0.0, self.t - self.period_start_t)
        return played / (self.periods * self.minutes * 60.0)

    def _plan_substitutions(self) -> None:
        """Each team's substitutions: how many (SUB_COUNTS) and when (a fraction of the match, in LEAGUE["sub_window"]).
        They happen at the first stoppage after their time."""
        lo, hi = LEAGUE["sub_window"]
        for team in (self.home, self.away):
            n = self.rng.choices([c for c, _w in SUB_COUNTS], weights=[w for _c, w in SUB_COUNTS])[0]
            self.sub_plan[team.team_id] = sorted(self.rng.uniform(lo, hi) for _ in range(n))

    def _substitutions_due(self) -> None:
        """At a stoppage: make every substitution whose time has come. Who comes off is weighted toward low stamina;
        a bench player of the same role (or the same line) comes on and takes his place in the shape."""
        if not self.league:
            return
        now = self._match_elapsed()
        for team in (self.home, self.away):
            plan = self.sub_plan.get(team.team_id, [])
            while plan and plan[0] <= now:
                plan.pop(0)
                self._substitute(team)

    def _substitute(self, team: Team) -> None:
        rng = self.rng
        bench = [q for q in team.players if not q.on and not q.starter and q.player_id not in self.subbed and q.position != "GK"]
        outs = [q for q in team.starters if q.position != "GK" and q.player_id not in self.subbed and q is not self.holder]
        if not bench or not outs:
            return
        weights = [math.exp(-0.8 * self.z(q, "stamina")) for q in outs]
        off = rng.choices(outs, weights=weights)[0]
        same = [q for q in bench if q.role == off.role]
        line = [q for q in bench if SUB_GROUPS.get(q.role) == SUB_GROUPS.get(off.role)]
        on = rng.choice(same or line or bench)
        self._event("substitution", off, related=on, pitch=off.pos, outcome="neutral")
        off.on = False
        on.on = True
        on.anchor = off.anchor
        on.x, on.y = PITCH_L / 2, 0.0 if off.y < PITCH_W / 2 else PITCH_W   # comes on at the halfway line
        self.subbed.update({off.player_id, on.player_id})
        if off.body is not None and on.body is not None:
            off.body.stop()
            on.body.on_since = self.t

    # ------------------------------------------------------------------ time
    def advance(self, duration: float, mode: str = "live", ball_to: Point | None = None) -> None:
        """Step the world forward. ``ball_to`` moves the ball linearly over the duration."""
        if duration <= 0:
            return
        if self.league:
            self._advance_league(duration, mode, ball_to)
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

    # ------------------------------------------------------------------ league mode: motion at 10 Hz
    def _advance_league(self, duration: float, mode: str, ball_to: Point | None) -> None:
        """``advance`` in league mode. A ball played (no holder) travels to ``ball_to`` in a straight line while the
        receiver runs to meet it; a ball carried goes where the holder's legs take it: he runs toward ``ball_to`` within
        his own speed and acceleration and the ball stays at his feet."""
        start = (self.ball[0], self.ball[1])
        end_t = self.t + duration
        holder = self.holder
        carry = (ball_to, end_t) if ball_to is not None and holder is not None else None
        self.flight = (ball_to, end_t) if ball_to is not None and holder is None else None
        elapsed = 0.0
        while self.t < end_t - 1e-9:
            step = min(SIM_DT, end_t - self.t)
            elapsed += step
            if self.flight is not None:
                f = clamp(elapsed / duration, 0.0, 1.0)
                self.ball[0] = start[0] + (ball_to[0] - start[0]) * f
                self.ball[1] = start[1] + (ball_to[1] - start[1]) * f
            self._move_league(step, mode, carry)
            if self.holder is not None:
                self.ball[0], self.ball[1] = self.holder.x, self.holder.y
            self.t += step
            if self.t + 1e-9 >= self.next_sample_t:
                self._sample_tracks()
                self.next_sample_t += 1.0 / self.track_hz
        self.flight = None

    def _move_league(self, step: float, mode: str, carry: tuple[Point, float] | None) -> None:
        """Move every player on the pitch one step (league mode).

        Each player picks a target and a speed he wants to go at: his shape position (which follows where the ball has
        been over the last few seconds) plus a slow personal drift, walking when near it and running when far; the
        presser closes the holder down; attackers make runs toward goal and the nearest defender follows them; after a
        turnover the side that lost the ball sprints back if far out of shape; receivers and chasers run to where the
        ball will be; at a dead ball everyone walks back and the set-piece taker goes to the spot. Then his velocity
        turns toward that within his acceleration (``acceleration_ms2``, tapering to nothing at top speed; unhurried
        moves speed up gently) or his braking, never above his top speed (``top_speed_kmh``). Sprints drain a reserve
        that only slow running refills, and willingness and top speed fade over the match, less for players with
        stamina."""
        M = MOTION
        t = self.t
        bx, by = self.ball
        k = min(1.0, step / M["ball_lag_s"])
        self.ball_seen[0] += (bx - self.ball_seen[0]) * k
        self.ball_seen[1] += (by - self.ball_seen[1]) * k
        sx, sy = self.ball_seen
        holder = self.holder
        live = mode == "live"
        rng = self.move_rng
        tick = int(t * 10.0 + 1e-6) % 10 == 0          # once a second
        match_len = self.periods * self.minutes * 60.0
        att = self.last_team if live else None
        press: Player | None = None
        hx = hy = 0.0
        cover: Player | None = None
        recovering = live and t - self.transition_t < M["transition_s"]
        if live and holder is not None:
            hx, hy = holder.x, holder.y
            near = sorted((q for q in self.other(holder.team).starters if q.position != "GK"),
                          key=lambda q: (q.x - hx) ** 2 + (q.y - hy) ** 2)
            press = near[0]
            if recovering and len(near) > 1:
                cover = near[1]            # just after losing it, a second man joins the press (a counter-press)
        flight = self.flight
        receiver = self.receiver
        chasers = self.chasers
        trackers: dict[str, Player] = {}                 # defender id -> the runner he follows
        if live and att is not None and M["track_runs"]:
            for q in att.starters:
                if q.body.run_until > t:   # whoever is nearest the space he is running into goes with him
                    mark = self.nearest((q.body.run_x, q.body.run_y), self.other(att), outfield=True)
                    trackers.setdefault(mark.player_id, q)
        jog, run, high, gain, walk = M["jog"], M["run"], M["high"], M["gain"], M["walk"]
        ramp = M["ramp"]
        comfort = M["comfort_acc"]
        hypot = math.hypot
        for team in (self.home, self.away):
            sign = team.attack_sign
            sh = self.shift[team.team_id]
            want = (M["shift"][0] if team is att else M["shift"][1]) if live and self.last_team is not None else 0.0
            sh += clamp(want - sh, -M["shift_rate"] * step, M["shift_rate"] * step)
            self.shift[team.team_id] = sh
            lost = recovering and team is not self.last_team
            ball_att = bx if sign > 0 else PITCH_L - bx
            for p in team.starters:
                b = p.body
                if tick:
                    w = M["wander_m"][0 if team is att else 1]
                    b.ox = 0.95 * b.ox + rng.gauss(0.0, w)
                    b.oy = 0.95 * b.oy + rng.gauss(0.0, w)
                on_frac = clamp((t - (b.on_since or 0.0)) / match_len, 0.0, 1.0)
                will = 1.0 - M["fatigue"] * on_frac * (1.0 - 0.3 * clamp(b.stamina_z, -1.5, 1.5))
                vmax = b.vmax * (1.0 - M["fatigue_vmax"] * (1.0 - will))
                sprint_ok = b.reserve > M["reserve_min"]
                top = vmax if sprint_ok else min(vmax, high)
                pid = p.player_id
                urgent = True
                if p is holder:
                    if carry is not None:
                        (tx, ty), end = carry
                        d = hypot(tx - p.x, ty - p.y)
                        vdes = min(M["dribble"] * vmax, d / max(end - t, step))
                    else:
                        tx, ty, d, vdes = p.x, p.y, 0.0, 0.0
                elif pid in chasers:
                    tx, ty = chasers[pid]
                    d = hypot(tx - p.x, ty - p.y)
                    vdes = min(top, gain * d + 1.0)
                elif p is receiver and flight is not None:
                    (tx, ty), end = flight
                    d = hypot(tx - p.x, ty - p.y)
                    vdes = min(top, max(1.1 * d / max(end - t, step), min(jog * will, gain * d)))
                elif not live:
                    urgent = False
                    goto = self.dead_goto.get(pid)
                    if goto is not None:
                        tx, ty = goto
                        d = hypot(tx - p.x, ty - p.y)
                        vdes = min(run * will, gain * d)
                    else:
                        ax, ay = p.anchor_abs
                        if p.position != "GK":
                            ax = clamp(ax + sign * sh, 2.0, PITCH_L - 2.0)
                        tx, ty = ax + 0.5 * b.ox, ay + 0.5 * b.oy
                        d = hypot(tx - p.x, ty - p.y)
                        vdes = min(walk if d < 12.0 else jog * will, gain * d)
                elif p is press or p is cover:
                    gx = 0.0 if sign > 0 else PITCH_L          # his own goal
                    ux, uy = gx - hx, PITCH_W / 2 - hy
                    n = hypot(ux, uy) or 1.0
                    tx, ty = hx + ux / n * M["press_gap_m"], hy + uy / n * M["press_gap_m"]
                    d = hypot(tx - p.x, ty - p.y)
                    cap = top if d > M["press_sprint_m"] else high if d > 8.0 else run
                    vdes = min(cap, gain * d)
                elif team is att and b.run_until > t:
                    tx, ty = b.run_x, b.run_y
                    d = hypot(tx - p.x, ty - p.y)
                    vdes = top if d > 3.0 else gain * d
                elif pid in trackers:
                    r = trackers[pid]
                    tx, ty = r.body.run_x, r.body.run_y
                    d = hypot(tx - p.x, ty - p.y)
                    vdes = top if d > 3.0 else gain * d
                else:
                    if team is not att:
                        b.run_until = -1.0
                    ax, ay = p.anchor_abs
                    if p.position != "GK":
                        ax = clamp(ax + sign * sh, 2.0, PITCH_L - 2.0)
                    pull = b.pull
                    tx, ty = ax + (sx - ax) * pull + b.ox, ay + (sy - ay) * pull + b.oy
                    d = hypot(tx - p.x, ty - p.y)
                    if d >= ramp[-1][0]:
                        cap = ramp[-1][1]
                    else:
                        i = 1
                        while ramp[i][0] < d:
                            i += 1
                        (d0, c0), (d1, c1) = ramp[i - 1], ramp[i]
                        cap = c0 + (c1 - c0) * (d - d0) / (d1 - d0)
                    cap *= will if cap <= jog else 1.0 - 0.3 * (1.0 - will)   # tired legs jog less; hard running fades less
                    urgent = False
                    if lost and d > M["recover_m"] and p.position != "GK" and (p.x - tx) * sign > 0:
                        # a recovery run: he is upfield of where he should be; flat out for a defender with the ball in
                        # his own half, hard running otherwise
                        cap, urgent = (top if ball_att < PITCH_L / 2 and p.role in M["sprint_back"] else high), True
                    vdes = min(cap, gain * d)
                    if team is att and b.run_rate and ball_att > 45.0 and sprint_ok and rng.random() < b.run_rate * step:
                        b.run_until = t + rng.uniform(*M["run_s"])
                        ahead = clamp(self.att_x(team, p.x) + rng.uniform(*M["run_m"]), 0.0, PITCH_L - 6.0)
                        b.run_x = ahead if sign > 0 else PITCH_L - ahead
                        b.run_y = clamp(p.y + rng.gauss(0.0, 5.0), 3.0, PITCH_W - 3.0)
                # Steer: turn the velocity toward the wanted one within acceleration (or braking), cap at top speed.
                vx, vy = b.vx, b.vy
                s = hypot(vx, vy)
                if d > 1e-6:
                    wx, wy = (tx - p.x) / d * vdes, (ty - p.y) / d * vdes
                else:
                    wx = wy = 0.0
                dvx, dvy = wx - vx, wy - vy
                dv = hypot(dvx, dvy)
                if vdes > s:
                    a = b.acc if urgent else min(b.acc, comfort)
                    lim = max(a * min(1.0, M["taper"] * (1.0 - s / vmax)), 0.8) * step
                else:
                    lim = (b.dec if urgent else min(b.dec, comfort)) * step
                if dv > lim:
                    dvx, dvy = dvx * lim / dv, dvy * lim / dv
                vx += dvx
                vy += dvy
                s = hypot(vx, vy)
                if s > vmax:
                    vx, vy, s = vx * vmax / s, vy * vmax / s, vmax
                x, y = p.x + vx * step, p.y + vy * step
                if x < 0.0 or x > PITCH_L:
                    x, vx = clamp(x, 0.0, PITCH_L), 0.0
                if y < 0.0 or y > PITCH_W:
                    y, vy = clamp(y, 0.0, PITCH_W), 0.0
                moved = hypot(x - p.x, y - p.y) / step
                p.x, p.y, b.vx, b.vy = x, y, vx, vy
                if moved > 5.5:
                    b.reserve = max(0.0, b.reserve - M["reserve_drain"] * (moved - 5.5) * step / (1.0 + 0.25 * clamp(b.stamina_z, -1.5, 1.5)))
                elif moved < 4.0:
                    b.reserve = min(1.0, b.reserve + M["reserve_back"] * step)
                if self.in_period:
                    b.meter(moved, step, self.period)

    def _place(self, p: Player, x: float, y: float, stop: bool = False) -> None:
        """Put a player somewhere without simulated motion (0.1.0 always did this). In league mode the jump is logged
        as ``relocated_m`` and never counted as distance."""
        if p.body is not None:
            if self.in_period and p.on:
                p.body.relocated += math.hypot(x - p.x, y - p.y)
            if stop:
                p.body.vx = p.body.vy = 0.0
        p.x, p.y = x, y

    def _reach(self, p: Player, point: Point, max_s: float = 3.0) -> None:
        """The player gets to a loose ball. League mode: play goes on while he runs there (up to ``max_s``), then any
        last gap is a placement. Otherwise he is put there at once, as in 0.1.0."""
        if self.league:
            self.chasers[p.player_id] = point
            end = self.t + max_s
            while self.t < end - 1e-9 and p.on and dist(p.pos, point) > MOTION["reach_m"]:
                self.advance(SIM_DT)
            self.chasers.pop(p.player_id, None)
        self._place(p, point[0], point[1])

    def _set_piece(self, choose: Any, spot: Point, total: float, also: list[tuple[Player, Point]] | None = None, **dead: Any) -> Player:
        """League mode: the taker (``choose()``) walks to ``spot`` while the dead ball runs (as do the players in ``also``
        to theirs), then stands on it; if he was substituted meanwhile, whoever ``choose()`` gives now takes it."""
        taker = choose()
        self.dead_goto = {taker.player_id: spot, **{q.player_id: pt_ for q, pt_ in also or []}}
        self._dead_ball(total, **dead)
        self.dead_goto = {}
        if not taker.on:
            taker = choose()
        self._place(taker, spot[0], spot[1], stop=True)
        for q, pt_ in also or []:
            if q.on:
                self._place(q, pt_[0], pt_[1], stop=True)
        return taker

    def _chase(self, point: Point, *teams: Team) -> None:
        """The nearest outfield player of each team runs to where the ball is going (league mode)."""
        if self.league:
            for team in teams:
                q = min((q for q in team.starters if q.position != "GK"), key=lambda q: (dist(q.pos, point), q.player_id))
                self.chasers[q.player_id] = point

    def _physical(self) -> list[Record]:
        """One ``physical`` record per player who played (league mode): his 10 Hz motion summarised (regista.synth.physical)."""
        out: list[Record] = []
        spells = self._spells()
        for team in (self.home, self.away):
            for p in team.players:
                b = p.body
                if b is None or b.played <= 0:
                    continue
                t0, t1 = spells.get(p.player_id, (0.0, self.t))
                out.append({
                    "type": "physical", "id": self._id("ph"), "match_id": self.match_id, "schema_version": self.schema_version,
                    "source": "synthetic", "confidence": 1, "t": round(t0, 2), "t_end": round(t1, 2),
                    "player_id": p.player_id, "team_id": team.team_id, "played_s": round(b.played, 1),
                    "metrics": b.metrics(),
                    "periods": [{"period": k, "played_s": round(v[0], 1), "distance_m": round(v[1], 1), "hi_distance_m": round(v[2], 1)}
                                for k, v in sorted(b.by_period.items())],
                    "method": PHYSICAL_METHOD,
                })
        return out

    def _spells(self) -> dict[str, tuple[float, float]]:
        """player id -> (came on, went off) in video time."""
        first = self.period_table[0]["t"] if self.period_table else 0.0
        last = self.period_table[-1]["t_end"] if self.period_table else self.t
        out = {p.player_id: (first, last) for p in self.players.values() if p.starter}
        for e in self.events:
            if e["event_type"] == "substitution":
                out[e["player_id"]] = (out.get(e["player_id"], (first, last))[0], e["t"])
                out[e["related_player_id"]] = (e["t"], last)
            elif e["event_type"] == "card_red":
                out[e["player_id"]] = (out.get(e["player_id"], (first, last))[0], e["t"])
        return out

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

    def _project(self, px: float, py: float, ball_x: float | None = None) -> dict[str, float] | None:
        """Main-camera bbox (normalised) using the shared camera model; None when out of frame. The camera follows the
        ball: ``ball_x`` (default: the ball now) sets where it points."""
        cx = camera_centre(self.ball[0] if ball_x is None else ball_x, MAIN_WINDOW_M)
        xn = screen_x(px, py, cx, MAIN_WINDOW_M, MAIN_K)
        depth = py / PITCH_W
        yc = 0.86 - 0.72 * depth
        s = 1.0 - MAIN_K * depth
        w, h = 0.032 * s, 0.11 * s
        if xn < -w or xn > 1 + w:
            return None
        return {"x": round(clamp(xn - w / 2, 0, 1), 4), "y": round(clamp(yc - h, 0, 1), 4), "w": round(w, 4), "h": round(h, 4)}

    # ------------------------------------------------------------------ take-on choreography (recorded tracks only)
    DUEL_LEAD_S = 0.5    # the defender steps into the carrier's path this long before the duel
    DUEL_TRAIL_S = 0.6   # and drifts back to his own position this long after
    DUEL_SWERVE_M = 1.4  # how far the carrier (and, for a plain take-on, the ball) goes round the defender

    def _duel(self, kind: str, attacker: Player, defender: Player, start: Point, past: Point, t0: float, t1: float) -> None:
        """Remember a one-on-one so the recorded tracks show it the way a camera would see it on a real pitch.

        The simulation moves the carrier and the ball in a straight line and leaves the defender wherever team shape
        put him, so a beaten defender, a nutmeg and a plain take-on all looked alike in the footage. Here the defender
        stands goal-side in the carrier's path, 2 m ahead. ``beat``: carrier and ball swerve round him. ``nutmeg``:
        the ball goes straight through him (between the legs) while the carrier goes round. ``blocked``: he steps
        across 1 m in front and wins the ball or the foul. Only ``_apply_duels`` reads this, after the match is over;
        the match itself, its events and every random draw are unchanged."""
        dx, dy = past[0] - start[0], past[1] - start[1]
        n = math.hypot(dx, dy) or 1.0
        u = (dx / n, dy / n)
        normal = (-u[1], u[0])
        # Go round on the side facing the middle of the pitch, so nobody is pushed off it; deterministic, no random draw.
        side = 1.0 if (PITCH_W / 2 - start[1]) * normal[1] >= 0 else -1.0
        reach = 1.0 if kind == "blocked" else n / 2  # mid-run, so a run cut short by the goal line still goes round him
        spot = (start[0] + u[0] * reach, start[1] + u[1] * reach)
        self.duels.append({"kind": kind, "attacker": attacker.player_id, "defender": defender.player_id, "t0": t0, "t1": t1,
                           "spot": spot, "offset": (normal[0] * side * self.DUEL_SWERVE_M, normal[1] * side * self.DUEL_SWERVE_M)})

    def _apply_duels(self) -> None:
        """Rewrite the recorded main-camera positions around each one-on-one (see ``_duel``), after the match is over.

        A take-on is decided at the moment it happens, so only afterwards can the defender be shown stepping into the
        carrier's path over the half-second before it. Positions are blended from where the simulation had each player
        (smoothstep in and out), and every changed record's bbox is projected again with the camera where it pointed
        then (it follows the world ball, which is recorded)."""
        if not self.duels:
            return
        main = {sg.id for sg in self.segments if sg.in_frame is None}
        at: dict[float, dict[str, Record]] = defaultdict(dict)
        for tr in self.tracks:
            if tr["segment_id"] in main and tr.get("pitch"):
                at[tr["t"]]["ball" if tr["object"] == "ball" else tr["player_id"]] = tr
        world = {t: {k: (r["pitch"]["x"], r["pitch"]["y"]) for k, r in recs.items()} for t, recs in at.items()}
        for d in self.duels:
            for t in sorted(at):
                if not (d["t0"] - self.DUEL_LEAD_S <= t <= d["t1"] + self.DUEL_TRAIL_S):
                    continue
                recs, w0 = at[t], world[t]
                if t < d["t0"]:
                    w = (t - (d["t0"] - self.DUEL_LEAD_S)) / self.DUEL_LEAD_S
                elif t > d["t1"]:
                    w = 1.0 - (t - d["t1"]) / self.DUEL_TRAIL_S
                else:
                    w = 1.0
                w = w * w * (3 - 2 * w)  # smoothstep
                moved: dict[str, Point] = {}
                if d["defender"] in w0:
                    dx, dy = w0[d["defender"]]
                    moved[d["defender"]] = (dx + (d["spot"][0] - dx) * w, dy + (d["spot"][1] - dy) * w)
                if d["kind"] in ("beat", "nutmeg") and d["t0"] <= t <= d["t1"]:
                    bump = math.sin(math.pi * (t - d["t0"]) / max(1e-6, d["t1"] - d["t0"]))
                    ox, oy = d["offset"][0] * bump, d["offset"][1] * bump
                    if d["attacker"] in w0:
                        moved[d["attacker"]] = (w0[d["attacker"]][0] + ox, w0[d["attacker"]][1] + oy)
                    if d["kind"] == "beat" and "ball" in w0:
                        moved["ball"] = (w0["ball"][0] + ox, w0["ball"][1] + oy)
                ball_x = w0["ball"][0] if "ball" in w0 else None
                for key, (x, y) in moved.items():
                    x, y = clamp(x, 0.0, PITCH_L), clamp(y, 0.0, PITCH_W)
                    rec = recs[key]
                    rec["pitch"] = pt(x, y)
                    if key != "ball" and ball_x is not None:
                        rec["bbox"] = self._project(x, y, ball_x) or rec["bbox"]
                world[t].update({k: (recs[k]["pitch"]["x"], recs[k]["pitch"]["y"]) for k in moved})

    def _sample_tracks(self) -> None:
        seg = self.segments[-1]
        t = round(self.t, 2)
        frame = int(round(self.t * self.fps))

        trng = self.track_rng

        def base(obj: str, track_id: str) -> Record:
            return {
                "type": "track", "id": self._id("tr"), "match_id": self.match_id, "schema_version": self.schema_version,
                "source": "synthetic", "confidence": round(trng.uniform(0.8, 0.99), 3),
                "t": t, "frame": frame, "segment_id": seg.id, "object": obj, "track_id": track_id,
            }

        if seg.in_frame is None:
            for team in (self.home, self.away):
                for p in team.starters:
                    px, py = p.x, p.y
                    bbox = self._project(px, py)
                    if bbox is None:
                        continue
                    rec = base("player", f"{seg.id}:{p.player_id}")
                    sees_number = trng.random() < 0.72
                    rec.update(
                        player_id=p.player_id, team_id=team.team_id, pitch=pt(px, py), bbox=bbox,
                        identity={
                            "confidence": round(trng.uniform(0.86, 0.99), 3) if sees_number else round(trng.uniform(0.6, 0.85), 3),
                            "evidence": ["kit_number", "team_colour", "continuity"] if sees_number else ["team_colour", "continuity"],
                        },
                    )
                    self.tracks.append(rec)
            bx, by = self.ball[0], self.ball[1]
            bbox = self._project(bx, by)
            if bbox is not None:
                rec = base("ball", f"{seg.id}:ball")
                rec.update(player_id=None, team_id=None, pitch=pt(bx, by), speed_kmh=round(self.ball_speed * 3.6, 1),
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
            "type": "event", "id": self._id("ev"), "match_id": self.match_id, "schema_version": self.schema_version,
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
            "type": "possession", "id": self._id("po"), "match_id": self.match_id, "schema_version": self.schema_version,
            "source": "synthetic", "confidence": self._conf(),
            "t": round(self.t, 2), "player_id": p.player_id, "team_id": p.team.team_id,
            "gained_by": gained_by, "touches": 0, "pitch": pt(p.x, p.y), "under_pressure": False,
        }
        if self.last_team is not None and self.last_team is not p.team:
            self._event("possession_change", p, related=from_player, pitch=p.pos)
            if self.league:
                self.transition_t = self.t
        self.last_team = p.team
        self.pos_pass = None

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
        self._substitutions_due()
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
        self._play_period(1, kicking_off=self.home)
        if self.periods == 2:
            # Half time: a graphics card, then the teams swap ends and the away side kicks off.
            self.advance(1.0, mode="dead")
            self._cut("graphic", 6.0, in_frame=[])
            for team in (self.home, self.away):
                team.attack_sign *= -1
            self._play_period(2, kicking_off=self.away)
        self.advance(1.0, mode="dead")
        self._highlight_package()
        self._close_main()
        self._apply_duels()

        duration = round(self.segments[-1].t_end, 2)
        match = self._match_record(duration)
        appearances = self._appearances()
        annotations = self._annotations()
        order = {"camera_segment": 0, "possession": 1, "event": 2, "appearance": 3, "annotation": 4}
        rows = [self._segment_record(s) for s in self.segments] + self.possessions + self.events + appearances + annotations
        rows.sort(key=lambda r: (r["t"], order[r["type"]], r["id"]))
        if self.league:
            rows += self._physical()   # one per player who played; they close the stream
        self.tracks.sort(key=lambda r: (r["t"], r["id"]))
        return SynthResult(match=match, events=rows, tracks=self.tracks, score=dict(self.score))

    def _play_period(self, period: int, kicking_off: Team) -> None:
        self.period = period
        self.period_start_t = self.t
        self.last_team = None
        self.pending_replays.clear()
        self._reset_positions()
        end_t = self.t + self.minutes * 60.0
        self._event("period_start", None, pitch=(PITCH_L / 2, PITCH_W / 2))
        kicker = self._kicker(kicking_off)
        kicker.x, kicker.y = PITCH_L / 2, PITCH_W / 2
        self._event("kick_off", kicker, pitch=kicker.pos)
        self._start_possession(kicker, "kickoff")
        self.in_period = True
        while self.t < end_t:
            self._play_possession()
        self.in_period = False
        if self.league:
            for q in self.home.starters + self.away.starters:
                q.body.stop()
        self._end_possession("period_end")
        self._event("period_end", None, pitch=(self.ball[0], self.ball[1]))
        ltr = self.home if self.home.attack_sign > 0 else self.away
        self.period_table.append({"period": period, "t": round(self.period_start_t, 2), "t_end": round(self.t, 2), "left_to_right_team_id": ltr.team_id})

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
        carry_p = 0.7 if not self.league else clamp(0.7 * math.exp(LEAGUE["carry_drive"] * self.z(p, "dribbling")), 0.0, 0.95)
        if space and rng.random() < carry_p:
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
        if self.league:  # who has the ball matters: dribblers take players on, finishers shoot, good markers win it
            w_take_on *= math.exp(LEAGUE["take_on_drive"] * self.z(p, "dribbling"))
            w_shot *= math.exp(LEAGUE["shot_drive"] * self.z(p, "finishing"))
            if self.pos_pass is not None:  # chance creation: a pass from a player with vision sets up a shot more often
                w_shot *= math.exp(LEAGUE["create_shot"] * self.z(self.players[self.pos_pass["player_id"]], "vision"))
            w_lose *= math.exp(LEAGUE["lose_defender"] * self.z(marker, "defending") - LEAGUE["lose_dribbler"] * self.z(p, "dribbling"))
        action = rng.choices(["pass", "take_on", "shot", "lose", "out"], weights=[w_pass, w_take_on, w_shot, w_lose, w_out])[0]
        if action == "pass":
            self._do_pass(p, pressure)
        elif action == "take_on":
            self._do_take_on(p, marker)
        elif action == "shot":
            self._do_shot(p)
        elif action == "lose":
            foul_p = self.tune["foul_on_tackle"]
            if self.league:
                foul_p = clamp(foul_p * math.exp(-LEAGUE["foul_discipline"] * self.z(marker, "defending")), 0.0, 0.9)
            if rng.random() < foul_p:
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
            tilt = 0.06 + (LEAGUE["vision_forward"] * self.z(p, "vision") if self.league else 0.0)
            w = math.exp(-(((d - 16.0) / 13.0) ** 2)) * (1.0 + tilt * clamp(forward, -10.0, 30.0)) + 0.02
            if q.position == "GK":
                w *= 0.15
            if self.league:  # teammates look for the good passers, and near goal for the good finishers
                w *= math.exp(LEAGUE["receive_passing"] * self.z(q, "passing"))
                if self.att_x(p.team, q.x) > 70:
                    w *= math.exp(LEAGUE["find_finisher"] * self.z(q, "finishing"))
            cands.append((q, max(w, 0.001)))
        players, weights = zip(*cands)
        return self.rng.choices(players, weights=weights)[0]

    def _do_pass(self, p: Player, pressure: bool) -> None:
        if self.league:
            self._league_pass(p, pressure)
            return
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
        win_p, nutmeg_p, skill_p, foul_p = 0.5, self.tune["nutmeg"], self.tune["skill"], self.tune["foul_on_take_on"]
        if self.league:  # dribbling against the defender's defending
            win_p = self.take_on_probability(p, defender)
            flair = math.exp(LEAGUE["flourish"] * self.z(p, "dribbling"))
            nutmeg_p, skill_p = nutmeg_p * flair, skill_p * flair
            foul_p = clamp(foul_p * math.exp(-LEAGUE["foul_discipline"] * self.z(defender, "defending")), 0.0, 0.9)
        if rng.random() < win_p:
            ev = self._event("take_on", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True)
            flourish = rng.random()
            nutmeg = flourish < nutmeg_p
            if nutmeg:
                nut = self._event("nutmeg", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True, qualifiers=["nutmeg"])
                ev["qualifiers"] = ["nutmeg"]
                self._queue_replay(nut)
            elif flourish < nutmeg_p + skill_p:
                sm = self._event("skill_move", p, related=defender, pitch=p.pos, outcome="success", under_pressure=True,
                                 qualifiers=[rng.choice(["stepover", "elastico", "drag_back", "roulette", "body_feint"])])
                if rng.random() < 0.5:
                    self._queue_replay(sm)
            past = (clamp(p.x + sign * 4.0, 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, 1.5), 1.0, PITCH_W - 1.0))
            self._duel("nutmeg" if nutmeg else "beat", p, defender, p.pos, past, self.t, self.t + 0.8)
            self.ball_speed = 5.0
            self.advance(0.8, ball_to=past)
            self.ball_speed = 0.0
            return
        ahead = (clamp(p.x + sign * 4.0, 1.0, PITCH_L - 1.0), p.y)
        if rng.random() < foul_p:
            self._duel("blocked", p, defender, p.pos, ahead, self.t - 0.6, self.t)
            self._event("take_on", p, related=defender, pitch=p.pos, outcome="fail", under_pressure=True)
            self._foul(defender, p)
            return
        self._duel("blocked", p, defender, p.pos, ahead, self.t - 0.6, self.t)
        self._event("take_on", p, related=defender, pitch=p.pos, outcome="fail", under_pressure=True)
        self._event("tackle", defender, related=p, pitch=defender.pos, outcome="success")
        self._end_possession("tackled")
        self._start_possession(defender, "tackle", from_player=p)

    def _foul(self, defender: Player, victim: Player) -> None:
        """Defender fouls the ball carrier: free kick to the victim's team from the spot."""
        if self.league:
            self._league_foul(defender, victim)
            return
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
        if self.league:
            flag = (self.ball[0], self.ball[1])
            taker = self._set_piece(lambda: self.nearest(flag, team, outfield=True), flag, rng.uniform(10.0, 14.0))
        else:
            self._dead_ball(rng.uniform(10.0, 14.0))
            taker = self.nearest((self.ball[0], self.ball[1]), team, outfield=True)
            taker.x, taker.y = self.ball[0], self.ball[1]
        self._event("corner", taker, pitch=taker.pos)
        self._start_possession(taker, "set_piece", from_player=last)

    def _do_shot(self, p: Player) -> None:
        if self.league:
            self._league_shot(p)
            return
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
            kicker = self._kicker(opp)
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

    # ------------------------------------------------------------------ league mode: passes, fouls, shots
    def _league_pass(self, p: Player, pressure: bool) -> None:
        """A pass when players have ratings: the passer's passing and vision against the defender where the ball comes
        down; through balls played in behind (with offsides on mistimed runs), forward balls into the final third that
        lead the receiver into space, aerial duels on crosses, long balls and long goal kicks."""
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        sign = team.attack_sign
        marker = self.nearest(p.pos, opp)
        goal_kick = self.goal_kick_long and p.position == "GK"
        self.goal_kick_long = False
        if goal_kick:  # hit long to one of the three players furthest forward
            front = sorted((q for q in team.starters if q.position != "GK"), key=lambda q: (-self.att_x(team, q.x), q.player_id))[:3]
            target = rng.choice(front)
        else:
            target = self._pick_pass_target(p)
        forward = (target.x - p.x) * sign
        wide = abs(p.y - PITCH_W / 2) > 18
        in_final_third = self.att_x(team, p.x) > 70
        kind = "cross" if wide and in_final_third and rng.random() < 0.7 else "pass"
        aim = target.pos
        through = False
        if kind == "pass" and not goal_kick and target.position != "GK" and forward > 6 and self.att_x(team, target.x) > 60:
            through = rng.random() < LEAGUE["through_ball"] * math.exp(LEAGUE["through_vision"] * self.z(p, "vision"))
        if through:  # into the space behind the defence, ahead of the runner
            ahead = clamp(self.att_x(team, target.x) + rng.uniform(6.0, 12.0), 0.0, PITCH_L - 3.0)
            aim = (ahead if sign > 0 else PITCH_L - ahead, clamp(target.y + rng.gauss(0, 2.0), 2.0, PITCH_W - 2.0))
        elif kind == "pass" and forward > 10 and self.att_x(team, target.x) > 70:  # led into space, by vision
            lead = LEAGUE["lead_m"] * clamp(1.0 + 0.5 * self.z(p, "vision"), 0.0, 2.0) * rng.uniform(0.5, 1.0)
            ahead = clamp(self.att_x(team, target.x) + lead, 0.0, PITCH_L - 2.0)
            aim = (ahead if sign > 0 else PITCH_L - ahead, target.y)
        d = max(dist(p.pos, aim), 1.0)
        forward_aim = (aim[0] - p.x) * sign
        long = d > 30
        if through:
            base = LEAGUE["through_base"]
        else:
            base = clamp(0.97 - 0.008 * d - (0.12 if pressure else 0.0) - (0.06 if forward_aim > 20 else 0.0), 0.4, 0.97)
        defender = self.nearest(aim, opp, outfield=True)
        lo = _logit(base) + LEAGUE["pass_bias"] + LEAGUE["pass_skill"] * self.z(p, "passing") \
            - LEAGUE["pass_defender"] * self.z(defender, "defending")
        if through:
            lo += LEAGUE["pass_vision_tb"] * self.z(p, "vision")
        if pressure:
            lo -= LEAGUE["pass_pressure"] * self.z(marker, "defending")
        if kind == "cross":
            lo += LEAGUE["cross_delivery"]
        ok = rng.random() < clamp(_sigmoid(lo), 0.2, 0.985)
        # Offside: a mistimed run on a ball in behind, or a long forward ball to the furthest man forward.
        furthest = max((q for q in team.starters if q.position != "GK"), key=lambda q: self.att_x(team, q.x))
        offside = False
        if through:
            offside = rng.random() < LEAGUE["offside_through"]
        elif forward_aim > 15 and target is furthest:
            offside = rng.random() < LEAGUE["offside_long"]
        # An aerial contest where the ball comes down: crosses, long balls, long goal kicks, if a defender is close.
        duel: tuple[Player, Player] | None = None
        if ok and not offside and not through and (kind == "cross" or long) and dist(defender.pos, aim) < LEAGUE["aerial_reach_m"]:
            if rng.random() < (LEAGUE["aerial_cross"] if kind == "cross" else LEAGUE["aerial_long"]):
                att_wins = rng.random() < self.aerial_probability(target, defender)
                duel = (target, defender) if att_wins else (defender, target)
                ok = att_wins
        speed = rng.uniform(10.0, 19.0)
        difficulty = clamp(0.6 * d / 45.0 + (0.25 if pressure else 0.0) + (0.15 if forward_aim > 15 else 0.0), 0.0, 1.0)
        if ok or offside or duel:
            end = aim
        else:
            interceptor = self.nearest(aim, opp)
            end = (clamp(interceptor.x + rng.gauss(0, 1.0), 0, PITCH_L), clamp(interceptor.y + rng.gauss(0, 1.0), 0, PITCH_W))
        qualifiers = []
        if forward_aim > 10:
            qualifiers.append("forward")
        if long:
            qualifiers.append("long")
        if through:
            qualifiers.append("through_ball")
        if goal_kick:
            qualifiers.append("goal_kick")
        if offside:
            qualifiers.append("offside")
        body_part, _weak = self.foot_for(p, 0.82)
        ev = self._event(kind, p, related=target, pitch=p.pos, pitch_end=end, outcome="success" if ok and not offside else "fail",
                         under_pressure=pressure, qualifiers=qualifiers or None,
                         metrics={"pass_distance_m": d, "pass_difficulty": difficulty, "ball_speed_kmh": speed * 3.6},
                         body_part=body_part)
        offside_spot = target.pos
        self._end_possession("offside" if offside else "pass")
        self.receiver = target if (ok or offside or duel) else None
        if duel is not None:   # the defender attacks the ball too
            self.chasers[(duel[1] if duel[0] is target else duel[0]).player_id] = aim
        elif through or (long and ok):   # a ball in behind or over the top: the nearest defender races the receiver for it
            self.chasers[defender.player_id] = aim
        self.ball_speed = speed
        self.advance(d / speed, ball_to=end)
        self.ball_speed = 0.0
        self.chasers.clear()
        self.last_pass = None
        if offside:
            self._offside(target, p, offside_spot)
            return
        if duel is not None:
            winner, loser = duel
            self._place(winner, aim[0], aim[1])
            source = "goal_kick" if goal_kick else "cross" if kind == "cross" else "long_ball"
            self._event("aerial_duel", winner, related=loser, pitch=aim, outcome="success", qualifiers=[source])
            if not ok:
                self._header_away(winner, team, kind)
                return
        if ok:
            if through or aim != target.pos:
                self._reach(target, aim)
            self.last_pass = ev
            self._start_possession(target, "pass_received", from_player=p)
            self.pos_pass = ev
            return
        self._league_failed_pass(p, kind)

    def _league_failed_pass(self, p: Player, kind: str) -> None:
        """A pass that did not arrive: as in 0.1.0 (out of play, interception, clearance, loose ball), except that of the
        two defenders nearest the ball the better reader tends to get there, and reading it (an interception) rather than
        picking it up loose rises with defending."""
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        here = (self.ball[0], self.ball[1])
        near = sorted(opp.starters, key=lambda q: (dist(q.pos, here), q.player_id))[:2]
        winner = rng.choices(near, weights=[math.exp(LEAGUE["interception_skill"] * self.z(q, "defending")) for q in near])[0]
        fp = dict(self.tune["failed_pass"])
        fp["interception"] *= math.exp(LEAGUE["interception_skill"] * self.z(winner, "defending"))
        how = rng.choices(list(fp), weights=list(fp.values()))[0]
        if how == "out" or (kind == "cross" and rng.random() < 0.3):
            if kind == "cross" and rng.random() < 0.35:
                self._corner(team, p)
            else:
                side = 0.0 if here[1] < PITCH_W / 2 else PITCH_W
                self.ball = [clamp(here[0], 1, PITCH_L - 1), side]
                ball = (self.ball[0], self.ball[1])
                thrower = self._set_piece(lambda: self.nearest(ball, opp, outfield=True),
                                          (ball[0], clamp(side, 0.5, PITCH_W - 0.5)), rng.uniform(6.0, 9.0))
                self._event("throw_in", thrower, pitch=thrower.pos)
                self._start_possession(thrower, "set_piece", from_player=p)
            return
        if how == "interception":
            self._event("interception", winner, related=p, pitch=winner.pos, outcome="success")
            self._start_possession(winner, "interception", from_player=p)
        elif how == "clearance":
            self._clear(winner, p)
        else:
            self._reach(winner, here)
            self._event("recovery", winner, related=p, pitch=winner.pos, outcome="success")
            self._start_possession(winner, "loose_ball", from_player=p)

    def _clear(self, defender: Player, last: Player) -> None:
        """A clearance 25-40 m upfield; whoever is nearest where it lands picks it up."""
        rng = self.rng
        team = defender.team
        self._event("clearance", defender, related=last, pitch=defender.pos, outcome="success")
        far = (clamp(defender.x + team.attack_sign * rng.uniform(25.0, 40.0), 1, PITCH_L - 1),
               clamp(defender.y + rng.gauss(0, 10.0), 1, PITCH_W - 1))
        self._chase(far, self.home, self.away)
        self.ball_speed = 18.0
        self.advance(dist(defender.pos, far) / 18.0, ball_to=far)
        self.ball_speed = 0.0
        self.chasers.clear()
        cands = self.home.starters + self.away.starters
        taker = min(cands, key=lambda q: dist(q.pos, far))
        self._reach(taker, far)
        self._event("recovery", taker, pitch=far, outcome="success")
        self._start_possession(taker, "loose_ball", from_player=defender)

    def _header_away(self, defender: Player, attackers: Team, kind: str) -> None:
        """The defender won the header: from a cross it is cleared (sometimes behind for a corner); from a long ball it
        drops loose for whoever is nearest."""
        rng = self.rng
        if kind == "cross":
            if rng.random() < LEAGUE["header_clear_corner"]:
                self._corner(attackers, defender)
            else:
                self._clear(defender, defender)
            return
        drop = (clamp(defender.x + defender.team.attack_sign * rng.uniform(8.0, 15.0), 1, PITCH_L - 1),
                clamp(defender.y + rng.gauss(0, 5.0), 1, PITCH_W - 1))
        self._chase(drop, self.home, self.away)
        self.ball_speed = 12.0
        self.advance(dist(defender.pos, drop) / 12.0, ball_to=drop)
        self.ball_speed = 0.0
        self.chasers.clear()
        taker = min(self.home.starters + self.away.starters, key=lambda q: (dist(q.pos, drop), q.player_id))
        self._reach(taker, drop)
        self._event("recovery", taker, pitch=drop, outcome="success")
        self._start_possession(taker, "loose_ball", from_player=defender)

    def _offside(self, attacker: Player, passer: Player, spot: Point) -> None:
        """Flagged offside where the run started: an indirect free kick to the defending side."""
        rng = self.rng
        self._event("offside", attacker, related=passer, pitch=spot, outcome="fail")
        opp = self.other(attacker.team)
        taker = self._set_piece(lambda: self.nearest(spot, opp, outfield=True), spot, rng.uniform(6.0, 9.0))
        self.ball = [spot[0], spot[1]]
        self._event("free_kick", taker, pitch=spot, qualifiers=["indirect"])
        self._start_possession(taker, "set_piece", from_player=attacker)

    def _league_foul(self, defender: Player, victim: Player) -> None:
        """A foul when players have ratings: inside the box most contact is not given (the defender wins it cleanly);
        given, it is a penalty. Cards include second yellows and rare straight reds, and a sent-off player leaves."""
        rng = self.rng
        spot = victim.pos
        team = victim.team
        box = self.in_box(team, spot)
        if box and rng.random() > LEAGUE["box_foul_given"]:
            self._event("tackle", defender, related=victim, pitch=defender.pos, outcome="success")
            self._end_possession("tackled")
            self._start_possession(defender, "tackle", from_player=victim)
            return
        foul = self._event("foul", defender, related=victim, pitch=defender.pos, outcome="fail",
                           qualifiers=["penalty_conceded"] if box else None)
        self._event("foul_won", victim, related=defender, pitch=victim.pos, outcome="success",
                    qualifiers=["penalty_won"] if box else None)
        self._cards(defender, victim)
        self._queue_replay(foul)
        self._end_possession("foul")
        if box:
            self._penalty(team, victim)
            return
        taker = self._set_piece(lambda: self.nearest(spot, team, outfield=True), spot, rng.uniform(9.0, 13.0),
                                closeup_of=victim if rng.random() < 0.5 else None)
        self.ball = [spot[0], spot[1]]
        self._event("free_kick", taker, pitch=spot)
        self._start_possession(taker, "set_piece")

    def _cards(self, defender: Player, victim: Player) -> None:
        """17% of fouls are booked; a second yellow is a red; a few fouls are straight reds. Keepers are
        never sent off here (no substitute keeper is modelled)."""
        rng = self.rng
        booked = defender.player_id in self.yellows
        yellow = rng.random() < (LEAGUE["second_yellow"] if booked else LEAGUE["yellow"])   # a booked player is careful
        straight = rng.random() < LEAGUE["straight_red"] and defender.position != "GK"
        if defender.position == "GK" and defender.player_id in self.yellows:
            yellow = False
        if straight:
            self._event("card_red", defender, related=victim, pitch=defender.pos, qualifiers=["straight_red"])
            self._send_off(defender)
            return
        if yellow:
            self._event("card_yellow", defender, related=victim, pitch=defender.pos)
            if defender.player_id in self.yellows:
                self._event("card_red", defender, related=victim, pitch=defender.pos, qualifiers=["second_yellow"])
                self._send_off(defender)
            else:
                self.yellows.add(defender.player_id)

    def _send_off(self, p: Player) -> None:
        if p.body is not None:
            p.body.stop()
        p.on = False
        self.subbed.add(p.player_id)
        if self.receiver is p:
            self.receiver = None

    def _penalty(self, team: Team, victim: Player) -> None:
        """The team's best finisher on the pitch takes it from the spot, 11 m out."""
        rng = self.rng
        opp = self.other(team)
        gx = team.goal[0]
        spot = (gx - team.attack_sign * 11.0, PITCH_W / 2)
        keeper = opp.keeper
        taker = self._set_piece(lambda: max((q for q in team.starters if q.position != "GK"),
                                            key=lambda q: ((q.attrs or {}).get("finishing", 0.0), q.player_id)),
                                spot, rng.uniform(22.0, 30.0), also=[(keeper, (gx, PITCH_W / 2))], closeup_of=victim)
        self.ball = [spot[0], spot[1]]
        self._event("penalty", taker, pitch=spot)
        self._start_possession(taker, "set_piece", from_player=victim)
        self.advance(1.0)
        self._league_shot(taker, penalty=True)

    def _league_shot(self, p: Player, penalty: bool = False) -> None:
        """A shot when players have ratings. xG is still the chance's quality (distance, and in league mode a header
        discount); whether it goes in also depends on the shooter's finishing (aerial for headers), the foot he uses and
        the keeper's shot stopping, so a player's goals minus xG measures his finishing. Every shot after a completed
        pass to the shooter makes that pass a key pass; a goal makes it the assist."""
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        goal = team.goal
        keeper = opp.keeper
        kp = self.pos_pass if (not penalty and self.pos_pass is not None and self.pos_pass["team_id"] == team.team_id
                               and self.pos_pass["related_player_id"] == p.player_id) else None
        if penalty:
            d, xg, headed = 11.0, LEAGUE["penalty_xg"], False
            body_part, weak = self.foot_for(p, 0.95)
        else:
            d = max(dist(p.pos, goal), 1.0)
            headed = kp is not None and kp["event_type"] == "cross" and rng.random() < 0.6
            xg = clamp(1.1 * math.exp(-0.12 * d) * (LEAGUE["header_xg"] if headed else 1.0), 0.02, 0.85)
            body_part, weak = ("head", False) if headed else self.foot_for(p, 0.8)
        speed_kmh = rng.uniform(40.0, 75.0) if headed else rng.uniform(65.0, 115.0)
        skill = self.z(p, "aerial" if headed else "finishing")
        if rng.random() < self.goal_probability(p, keeper, xg, headed=headed, weak=weak):
            result = "goal"
        elif penalty:
            result = "saved" if rng.random() < 0.7 else "off_target"
        else:
            on_target = _sigmoid(_logit(0.4) + LEAGUE["on_target"] * skill)
            u = rng.random()
            result = "saved" if u < on_target else "blocked" if (u - on_target) / (1 - on_target) < 0.25 / 0.6 else "off_target"
        if result in ("goal", "saved"):
            end = (goal[0], clamp(goal[1] + rng.uniform(-3.2, 3.2), 0, PITCH_W))
        elif result == "off_target":
            end = (goal[0], clamp(goal[1] + rng.choice([-1, 1]) * rng.uniform(4.0, 9.0), 0, PITCH_W))
        else:
            end = (clamp(p.x + team.attack_sign * 2.0, 0, PITCH_L), p.y)
        shot = self._event("shot", p, pitch=p.pos, pitch_end=end, outcome="success" if result == "goal" else "fail",
                           qualifiers=[result] + (["header"] if headed else []) + (["penalty"] if penalty else []), body_part=body_part,
                           under_pressure=bool(self.cur_pos and self.cur_pos["under_pressure"]),
                           metrics={"shot_distance_m": d, "shot_speed_kmh": speed_kmh, "xg": xg})
        if kp is not None:
            kp["qualifiers"] = list(dict.fromkeys(kp.get("qualifiers", []) + ["key_pass"]))
        if result == "goal" or penalty or xg > self.tune["replay_xg"]:
            self._queue_replay(shot)
        self._end_possession("shot")
        if result in ("goal", "saved"):
            self.chasers[keeper.player_id] = end     # the keeper goes for it
        self.ball_speed = speed_kmh / 3.6
        self.advance(dist(p.pos, end) / self.ball_speed, ball_to=end)
        self.ball_speed = 0.0
        self.chasers.clear()
        self.last_pass = None

        if result == "goal":
            assist_by = self.players[kp["player_id"]] if kp is not None else None
            goal_ev = self._event("goal", p, related=assist_by, pitch=p.pos, pitch_end=end, outcome="success", body_part=body_part,
                                  qualifiers=["penalty"] if penalty else None, metrics={"xg": xg, "shot_distance_m": d})
            if assist_by is not None:
                self._event("assist", assist_by, related=p, pitch=assist_by.pos, outcome="success")
                kp["qualifiers"] = list(dict.fromkeys(kp["qualifiers"] + ["assist"]))
            self.score[team.team_id] += 1
            self._queue_replay(goal_ev)
            centre = (PITCH_L / 2, PITCH_W / 2)
            self.dead_goto = {self._kicker(opp).player_id: centre}   # everyone walks back; the kicker to the spot
            self._dead_ball(rng.uniform(24.0, 32.0), closeup_of=p, crowd=True)
            self.dead_goto = {}
            self._reset_positions()
            kicker = self._kicker(opp)
            self._place(kicker, *centre)
            self._event("kick_off", kicker, pitch=kicker.pos)
            self._start_possession(kicker, "kickoff", from_player=p)
        elif result == "saved":
            held = penalty or rng.random() < _sigmoid(_logit(0.6) + LEAGUE["hold"] * self.z(keeper, "handling"))
            self._event("save", keeper, related=p, pitch=keeper.pos, outcome="success", qualifiers=["held" if held else "parried"])
            if held:
                self._place(keeper, self.ball[0], self.ball[1], stop=True)
                self._start_possession(keeper, "goalkeeper_claim", from_player=p)
            else:  # parried: the ball runs loose in front of goal
                loose = (clamp(goal[0] - team.attack_sign * rng.uniform(4.0, 10.0), 1, PITCH_L - 1),
                         clamp(goal[1] + rng.gauss(0, 7.0), 1, PITCH_W - 1))
                self._chase(loose, team, opp)
                self.ball_speed = 8.0
                self.advance(dist((self.ball[0], self.ball[1]), loose) / 8.0, ball_to=loose)
                self.ball_speed = 0.0
                self.chasers.clear()
                winner = min(team.starters + opp.starters, key=lambda q: (dist(q.pos, loose), q.player_id))
                self._reach(winner, loose)
                self._event("recovery", winner, pitch=loose, outcome="success")
                self._start_possession(winner, "rebound" if winner.team is team else "loose_ball", from_player=keeper)
        elif result == "blocked":
            blocker = self.nearest(p.pos, opp, outfield=True)
            self._event("block", blocker, related=p, pitch=blocker.pos, outcome="success")
            if rng.random() < self.tune["corner_after_block"]:
                self._corner(team, blocker)
                return
            loose = (clamp(self.ball[0] + rng.gauss(0, 4.0), 1, PITCH_L - 1), clamp(self.ball[1] + rng.gauss(0, 4.0), 1, PITCH_W - 1))
            self._chase(loose, team, opp)
            self.ball_speed = 6.0
            self.advance(0.7, ball_to=loose)
            self.ball_speed = 0.0
            self.chasers.clear()
            winner = min(team.starters + opp.starters, key=lambda q: dist(q.pos, loose))
            self._reach(winner, loose)
            self._event("recovery", winner, pitch=loose, outcome="success")
            self._start_possession(winner, "rebound" if winner.team is team else "loose_ball", from_player=p)
        elif not penalty and rng.random() < self.tune["corner_after_off_target"]:
            self._dead_ball(1.5, closeup_of=p if rng.random() < 0.5 else None)
            self._corner(team, self.nearest(p.pos, opp, outfield=True))
        else:
            total, closeup = rng.uniform(10.0, 14.0), (p if rng.random() < 0.5 else None)
            spot = (5.5 if opp.attack_sign > 0 else PITCH_L - 5.5, PITCH_W / 2 + rng.choice([-1, 1]) * 9.0)
            keeper = self._set_piece(lambda: opp.keeper, spot, total, closeup_of=closeup)
            self.ball = [spot[0], spot[1]]
            self._event("goal_kick", keeper, pitch=spot)
            self._start_possession(keeper, "set_piece", from_player=p)
            self.goal_kick_long = rng.random() < LEAGUE["goal_kick_long"]

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
        if self.league:
            line = (out_pt[0], clamp(side, 0.5, PITCH_W - 0.5))
            thrower = self._set_piece(lambda: self.nearest(out_pt, opp, outfield=True), line, rng.uniform(6.0, 9.0),
                                      closeup_of=p if rng.random() < 0.4 else None)
        else:
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
            "type": "camera_segment", "id": s.id, "match_id": self.match_id, "schema_version": self.schema_version,
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

    def _match_record(self, duration: float) -> Record:
        return {
            "type": "match", "id": f"ma_{self.match_id}", "match_id": self.match_id, "schema_version": self.schema_version,
            "source": "synthetic",
            **{"competition": "Regista Synthetic League", "season": "2026/27", "date": "2026-10-19", "venue": "Northbridge Arena", **self.meta},
            "home_team_id": self.home.team_id, "away_team_id": self.away.team_id,
            "teams": [{"team_id": t.team_id, "name": t.name, "short_name": t.short_name, "kit": t.kit,
                       **({"club_id": t.club_id} if t.club_id else {})} for t in (self.home, self.away)],
            "players": [
                {"player_id": p.player_id, "team_id": p.team.team_id, "name": p.name, "kit_number": p.kit_number,
                 "position": p.position, "starter": p.starter, **({"global_player_id": p.global_id} if p.global_id else {})}
                for t in (self.home, self.away) for p in t.players
            ],
            "video": {"video_id": f"{self.match_id}_broadcast", "fps": self.fps, "width": 1920, "height": 1080,
                      "duration_s": duration, "main_camera": "broadcast_wide"},
            "periods": list(self.period_table),
            "score": dict(self.score),
            "generator": {"name": GENERATOR_NAME, "version": LEAGUE_GENERATOR_VERSION if self.league else GENERATOR_VERSION, "seed": self.seed,
                          "params": {"minutes": self.minutes, "periods": self.periods, "track_hz": self.track_hz, "fps": self.fps,
                                     "profile": self.profile, "teams": [t["name"] for t in self.team_specs]}},
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
                            "type": "appearance", "id": self._id("ap"), "match_id": self.match_id, "schema_version": self.schema_version,
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
                "type": "annotation", "id": self._id("an"), "match_id": self.match_id, "schema_version": self.schema_version,
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


def _team_specs(teams: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Two team specs (name, short_name, kit, and for a season club_id and squad) merged over the defaults; team ids
    and attack signs are fixed. A squad lists 18 people ({"global_id", "name"}): the 4-3-3 starters in formation order
    (kit numbers 1, 2, 4, 5, 3, 8, 6, 10, 7, 9, 11), then the bench (13, 15, 14, 16, 17, 20, 22)."""
    specs = [dict(s) for s in TEAM_SPECS]
    if teams is None:
        return specs
    if len(teams) != 2:
        raise ValueError("teams must have exactly two entries: home, away")
    for base, given in zip(specs, teams):
        for key in ("name", "short_name"):
            if key in given:
                base[key] = str(given[key])
        if "kit" in given:
            base["kit"] = {**base["kit"], **{k: str(v) for k, v in given["kit"].items()}}
        if "club_id" in given:
            base["club_id"] = str(given["club_id"])
        if "squad" in given:
            squad = [_squad_member(m) for m in given["squad"]]
            if len(squad) != len(FORMATION_433) + len(BENCH):
                raise ValueError(f"a squad needs {len(FORMATION_433) + len(BENCH)} people, got {len(squad)}")
            base["squad"] = squad
        if len(base["short_name"]) > 4:
            raise ValueError(f"short_name {base['short_name']!r} must be at most 4 characters")
    rated = [("attributes" in m) for spec in specs for m in spec.get("squad") or []]
    if any(rated) and not (all(rated) and all(spec.get("squad") for spec in specs)):
        raise ValueError("league mode needs ratings (attributes) for every member of both squads")
    return specs


def _squad_member(m: dict[str, Any]) -> dict[str, Any]:
    """A squad entry: global id and name; in league mode also ``attributes`` (hidden ratings), ``role``, ``height_cm``
    and ``preferred_foot`` (regista.season.league)."""
    out: dict[str, Any] = {"global_id": str(m["global_id"]), "name": str(m["name"])}
    if "attributes" in m:
        out["attributes"] = {str(k): float(v) for k, v in m["attributes"].items()}
        for key in ("role", "height_cm", "preferred_foot", "kit_number"):
            if m.get(key) is not None:
                out[key] = m[key]
    return out


def _league_fields(person: dict[str, Any]) -> dict[str, Any]:
    """Player keyword arguments from a league squad entry (empty without ratings)."""
    if "attributes" not in person:
        return {}
    return {"attrs": person["attributes"], "height_cm": float(person.get("height_cm") or 180.0),
            "foot": person.get("preferred_foot") or "right", "role": person.get("role")}


def parse_team_arg(text: str) -> dict[str, Any]:
    """'Name,SHORT,#primary[,#secondary[,#gk]]' as used by --home/--away."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 3:
        raise ValueError("team spec needs at least Name,SHORT,#primary")
    kit = {"primary": parts[2]}
    if len(parts) > 3:
        kit["secondary"] = parts[3]
    if len(parts) > 4:
        kit["gk"] = parts[4]
    return {"name": parts[0], "short_name": parts[1], "kit": kit}


def generate(seed: int = 42, minutes: float = 3.0, track_hz: float = 1.0, fps: float = 25.0, profile: str = "demo",
             periods: int = 1, teams: list[dict[str, Any]] | None = None, match_id: str | None = None,
             meta: dict[str, str] | None = None) -> SynthResult:
    return MatchSim(seed=seed, minutes=minutes, track_hz=track_hz, fps=fps, profile=profile, periods=periods, teams=teams,
                    match_id=match_id, meta=meta).run()
