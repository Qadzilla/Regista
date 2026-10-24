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
LEAGUE_GENERATOR_VERSION = "0.7.0"   # with them (league mode): player ratings drive outcomes, plus the 0.2.0 events;
# 0.3.0: every player moves at 10 Hz within his own pace and acceleration, and each gets a ``physical`` record
# 0.4.0: retuned against individual leader bands (review round 1): shots spread by role, finishing worth a realistic edge,
#        centre-backs attack the high balls, shorter carries, crosses completed at the Premier League's rate, hard braking
# 0.5.0: shots on target and saves at the Premier League's rates (review round 2), keepers launch long in open play
# 0.6.0: roles shape the game (review closing round 1): build-up through centre-backs and holding midfielders, full-backs
#        cross, midfielders and defenders win the tackles, forwards are fouled; the star's edge in chances softened
# 0.7.0: crosses decided first and aimed at the players attacking the box, from the final 35-40 m (review closing round 2);
#        the back line steps up in possession, full-backs and wingers hold the width, centre-backs hit some balls long

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
PROFILES["league"] = {**PROFILES["realistic"], "shot_weights": (16.0, 0.178, 24.0, 0.159, 32.0, 0.113), "lose": 0.42, "take_on": 0.24,
                      "foul_on_tackle": 0.21, "foul_on_take_on": 0.42,
                      "failed_pass": {"interception": 0.10, "recovery": 0.66, "out": 0.06, "clearance": 0.18}}
# (0.6.0: lose 0.48, take_on 0.27 and foul_on_tackle 0.24 before; with tacklers and fouls chosen by role, tackles,
# take-ons and fouls stay in band at these)

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
    "finishing": 66.0, "passing": 68.0, "vision": 66.0, "dribbling": 69.0, "defending": 62.0, "aerial": 66.0,
    "stamina": 73.0, "shot_stopping": 75.0, "handling": 72.0, "distribution": 64.0,
}
LEAGUE: dict[str, Any] = {
    "pass_bias": 0.25,         # league-wide completion shift (log-odds), tuned so completion stays in band (0.20 before
                               # 0.5.0: the keepers' launches complete less often)
    "cross_delivery": -2.05,   # crosses into a crowded box arrive less often than a pass of the same length: tuned to the
                               # Premier League's open-play cross accuracy, 19-22% (premierleague.com, 13 Oct 2024); -2.15
                               # before 0.6.0, when full-backs began crossing from deeper

    "pass_skill": 0.22,        # passer's passing on completion (log-odds per z)
    "pass_vision_tb": 0.25,    # passer's vision on a through ball's completion
    "pass_defender": 0.14,     # the nearest defender to the ball's end point (defending), against
    "pass_pressure": 0.10,     # the marker's defending, when the passer is under pressure
    "keep_pass": 0.18,         # team style (TEAM_STYLE): a side of good passers completes more (log-odds per style z) ...
    "keep_lose": 0.22,         # ... and is dispossessed less (log scale per style z)
    "press_base": 1.85,        # every side presses a little harder in the opponents' own 60% than deeper ...
    "press_lose": 0.15,        # ... and a pressing side much harder (log scale per style z)
    "vision_forward": 0.005,   # vision tilts target choice toward runners further forward (per z, per metre)
    "gk_target": 1.2,          # how readily a player in his own half passes back to the keeper (0.15 elsewhere, as in 0.1.0)
    "receive_passing": 0.15,   # (0.6.0) in build-up, teammates pick good passers as targets more often (log scale per z):
                               # the playmaker sees more of the ball, so passing volume repeats within a role (it was mostly
                               # noise once roles set the volume; 0.0 before)
    "find_finisher": 0.13,     # ... and, in the final third, good finishers (log scale per z; 0.14 before 0.6.0, when the
                               # star took 46% of his club's npxG over six seasons and 2.4 times the next player's per 90)
    "create_shot": 0.0,        # (0.30 in generator 0.3.0 made the best passer's key passes twice any real player's)
    "after_cross_shot": 0.5,   # a cross that arrives leads to a shot half as often as a pass would
    "touch_every_s": 1.92,     # (0.5.0) one touch record for every full this many seconds of a spell on the ball, at least
                               # one (0.8 in 0.1.0; spells of 1-4 s average one record per 2.3 s: regista.season.metrics.
                               # TOUCH_RECORDS states it for the terminal): 0.8 wrote about twice FBref's touches per team
                               # (review round 2). Every record draws a random confidence, so this also reshuffles the
                               # season's draws: any value from 1.4 to 2.0 halves the touches. 0.7.0 scanned 1.80-2.00 and
                               # picked 1.92 (1.82 in 0.5.0, 1.89 in 0.6.0) because the committed season then has the star as
                               # its outright top scorer and every one-season band in, and the six pooled seasons pass every
                               # band and role shape (data/synthetic/README.md, league mode)
    "carry_drive": 0.30,       # good dribblers carry the ball into space more often (0.15 before 0.6.0) ...
    "carry_speed": (1.35, 4.1), # a carry's pace toward goal (m/s over the hold): shorter than 0.1.0's 3-7, so progressive
                               # passes outnumber progressive carries as in FBref's Premier League data
    "carry_pace": 0.05,        # ... and faster (log scale per z, 0.6.0): with less of the ball the best carriers still lead
                               # the league in progressive carries
    "carry_role": {"ST": 0.55, "W": 0.7, "FB": 0.7},   # (0.7.0) strikers carry into space less often (with the ball high up
                               # the pitch they made more progressive carries than attacking midfielders, review closing round
                               # 2), and wide men a little less, so progressive passes still outnumber progressive carries
    "carry_side_m": 5.0,       # ... with this much sideways drift (sd)
    "lead_m": 1.0,             # completed forward passes into the final third lead the receiver into space, by vision
    "through_ball": 0.007,     # chance a forward pass to a runner in the attacking half is played in behind
    "through_vision": 0.30,    # ... rising with the passer's vision (log scale per z)
    "through_base": 0.55,      # through-ball completion for average players
    "offside_through": 0.30,   # mistimed runs on a ball in behind: offside
    "offside_long": 0.065,     # a long forward ball to the most advanced attacker: offside (0.06 before 0.6.0, when strikers
                               # began to see fewer long balls, 0.09 in 0.6.0; since 0.7.0 centre-backs hit some long too)
    "shot_drive": 0.19,        # finishers shoot more often from close in (weight, log scale per z; 0.28 before 0.6.0) ...
    "shot_drive_band": (1.0, 0.2, -0.5),  # ... in full inside 16 m, a little at 16-24 m, and less from further out: the
                                          # best finishers take better chances, not just more shots
    # How readily each role shoots from where it stands: multipliers on the profile's distance weights inside 16 m, 16-24 m
    # and 24-32 m. Without them the striker, nearest goal, took half his team's shots (in the Premier League the top
    # shooter takes about 15-25%); strikers shoot from close in, midfielders from further out. 0.5.0 lowered the striker's
    # and the winger's (1.8, 1.0, 0.33 and 1.55, 1.45, 1.15 before): the star took about 6 shots per 90 over many seasons,
    # above any Premier League player, and a striker still shoots more than a winger from close in. 0.6.0 raised the
    # striker's (1.6, 0.85, 0.25 before): he now has the ball less often (pass_role, receive_role) and shoots more of the
    # times he does. 0.7.0 lowered it again (2.2, 1.1, 0.3 before): crosses now look for the players attacking the box, so
    # strikers meet more of them, and one striker took more than 40% of his club's npxG.
    "shot_role": {"ST": (1.8, 0.9, 0.3), "AM": (2.4, 2.9, 2.3), "W": (1.4, 1.35, 1.1), "CM": (4.0, 5.7, 4.4),
                  "DM": (4.0, 5.3, 4.0), "FB": (5.5, 5.5, 3.3), "CB": (5.5, 5.5, 3.3), "GK": (0.0, 0.0, 0.0)},
    "finish": 0.06,            # finishing on goal probability (log-odds per z): the best finisher (z about 4.4) beats xG by
                               # about a quarter, as elite finishers do over a season (10-25%), not by double
    "keeper": 0.16,            # the keeper's shot stopping, against
    "on_target": 0.08,         # finishing on hitting the target when it is not a goal (0.15 before 0.5.0 gave the star
                               # more shots on target per 90 than any Premier League player)
    # How a shot that is not a goal ends (0.5.0). Of those shots, this share is saved (before the finishing term above) ...
    "shot_saved": 0.25,
    # ... and of the rest, this share is blocked; the others miss. Tuned to the Premier League: 49.9% of shots on target
    # with blocked shots left out in 2023/24, 45.1% over twenty seasons (Adrian Clarke, premierleague.com/news/4027257,
    # 27 May 2024); keepers with 500+ minutes saved 51.5-73.5% in 2024/25 (Opta Analyst, 23 Apr 2025). Before 0.5.0
    # (0.4 and 0.25/0.6, copied from 0.1.0) 60% of unblocked shots were on target and keepers saved 76%
    "shot_blocked": 0.40,
    "xg_scale": 1.0,           # the league's xG model: xg_scale * exp(-0.12 * distance), 1.1 in 0.1.0; strikers now shoot
                               # from closer in, so the scale comes down to keep xG per shot and goals in the Premier League's
                               # bands (1.0 in 0.4.0-0.5.0, 0.95 in 0.6.0, 1.0 again since 0.7.0: crosses met by forwards
                               # are headers and volleys, worth less, and goals stayed near the band's floor)
    "cross_volley_xg": 0.45,   # ... as is a first-time shot from a cross, struck under pressure in a crowded box
    "header_xg": 0.40,         # headers are worse chances than shots from the same spot (league xG model): a header from
                               # the penalty spot is worth about 0.11
    "strong_foot": 0.06,       # strong foot / weak foot on goal probability (balanced: 0.8 * 0.06 = 0.2 * 0.24)
    "weak_foot": 0.24,
    "hold": 0.30,              # keeper's handling on holding a save (else a parry and a rebound)
    "take_on_base": 0.33, "take_on_skill": 0.40,  # take-on: dribbling minus the defender's defending. Tuned to the Premier
                               # League's take-on success, 36.7% in 2025/26 (Opta Analyst, 17 Feb 2026); 0.5 before 0.5.0
                               # gave 57%
    "take_on_foul": 0.72,      # (0.5.0) more take-ons fail now, so fewer of the failures are fouls (fouls stay in band) ...
    "take_on_loose": 0.50,     # ... and some end with the ball running loose rather than a tackle (tackles stay in band)
    "take_on_drive": 0.18,     # good dribblers attempt more take-ons
    "flourish": 0.25,          # nutmeg and skill-move chances rise with dribbling
    "lose_defender": 0.05, "lose_dribbler": 0.12,  # dispossession: marker's defending against holder's dribbling
    "foul_discipline": 0.20,   # better defenders foul less
    "interception_skill": 0.06,  # a failed pass is read (interception) rather than picked up loose, by defending (0.10
                                 # before 0.5.0 put the best reader near 3.4 per 90 over three seasons; the band's top is 3)
    "interception_near": 6,    # ... by one of the six players nearest the ball
    "interception_rate": 1.3,  # (0.5.0) failed passes are read a little more often, so interceptions stay in band now that
                               # failed take-ons often run loose instead
    "long_interception": 0.6,  # ... and read less often when it was a long ball (0.5.0): one that drops short or overruns
                               # is mostly headed or picked up loose
    "box_foul_given": 0.55,    # contact in the box: given as a penalty this often, else the defender wins it cleanly (0.60
                               # before 0.5.0, 0.80 in 0.5.0; since 0.6.0 forwards in the box are fouled more often)
    "penalty_xg": 0.79,        # FBref/Opta penalty xG (docs/scout-terminal/industry-metrics.md #10)
    "straight_red": 0.003,      # per foul
    "yellow": 0.17,            # per foul (yellow cards are a diagnostic: no band)
    "second_yellow": 0.05,     # ... and for a player already booked
    # Crosses (0.7.0, review closing round 2). A wide player near the opponent's box first decides to cross, then aims
    # into the box at a teammate attacking it. Before 0.7.0 the build-up target was picked first and every wide pass past
    # a line measured from the passer's OWN goal line became a cross aimed into the box: full-backs "crossed" 50 m balls
    # from their own half, and centre-backs 60 m away "received" them.
    "cross_zone_m": {"FB": 40.0, "W": 39.0},   # a cross starts at most this far from the opponent's goal line (35 m for
                               # other roles): the final third, and for full-backs the overlap just outside it
    "cross_choice": {"FB": 1.0, "W": 1.0},     # in that zone, a wide player crosses this often (other roles: 1.0) when
                               # someone is attacking the box; else he plays an ordinary pass. A corner is always a cross
    "cross_box_m": 34.0,       # the teammates a cross can look for: outfielders this close to the goal line, arriving in or
                               # already in the box (they run onto it while it is in the air) ...
    "cross_role": {"ST": 1.3, "W": 1.8, "AM": 1.8, "CM": 0.8, "DM": 0.3, "FB": 0.4, "CB": 0.3},   # ... by role (the far
                               # winger and the 10 attack the back post and the edge of the box as well as the striker) ...
    "cross_finisher": 0.10,    # ... and finishing (log scale per z): the best finishers attack the cross (find_finisher's
                               # role for ordinary passes)
    "cross_near_m": 12.0,      # ... and nearer where the ball comes down (weight exp(-d / this)); no one there: no cross
    # Who gets the ball and what he does with it, by role (0.6.0, review closing round 1). Before, a pass looked for a
    # teammate 16 m away tilted forward, so strikers received, touched and passed the ball more than anyone and centre-backs
    # least, the reverse of football; whoever was nearest the ball won it, so pressing strikers won as many tackles as
    # holding midfielders and committed the most fouls. The checks are in regista.synth.report (ROLE_SHAPES).
    "forward_tilt": 0.075,     # how strongly a pass looks forward (per metre, up to 30 m; 0.06 in 0.1.0)
    "receive_role": {"CB": 3.0, "FB": 2.0, "DM": 1.8, "CM": 1.4, "AM": 1.0, "W": 0.5, "ST": 0.3},   # target weight by role,
                               # for a passer in his own 60%: build-up goes through the back line and the holding midfielder
    "receive_role_attack": {"CB": 1.6, "FB": 1.8, "DM": 1.5, "CM": 1.2, "AM": 1.0, "W": 0.65, "ST": 0.55},  # ... and further
                               # forward, where attacks are recycled back through midfield as well as played into the front three.
                               # 0.7.0 gave full-backs more of the ball and wingers and strikers less (FB 1.5/1.2, W 0.6/0.8, ST
                               # 0.7 in attack before): full-backs touched the ball less than wingers (review closing round 2)
    "attack_from": 60.0,       # metres from his own goal line where the second table takes over
    # (0.7.0, review closing round 2) a centre-back or full-back in his own half hits it long to one of the front three
    # this often (more with a better passer): before, 1.2% of centre-backs' passes travelled 32 m or more
    "long_ball_role": {"CB": 0.14, "FB": 0.05},
    "long_ball_passing": 0.25,  # ... log scale per z of passing
    "pass_role": {"ST": 0.5, "W": 0.65, "AM": 0.9},   # how readily the holder passes, by role: forwards shoot, take players
                               # on and lose the ball more and pass less (the pass weight is 0.6 for every role before 0.6.0)
    "take_on_role": {"CB": 0.35, "FB": 0.8, "DM": 0.6, "CM": 0.8, "AM": 1.3, "W": 1.5, "ST": 1.0, "GK": 0.1},  # take-ons
    "lose_role": {"ST": 0.55, "W": 0.8, "AM": 0.9},   # forwards pressing the holder win the ball less often ...
    "tackle_role": {"CB": 1.8, "FB": 1.8, "DM": 0.8, "CM": 0.75, "AM": 0.7, "W": 0.5, "ST": 0.2},   # ... and who wins it
                               # (or is the challenger on a take-on) among the opponents within tackle_reach_m, by role
    "tackle_reach_m": 10.0,
    "foul_role": {"ST": 1.6, "W": 1.1, "DM": 0.9},    # a challenge from a forward is more often a foul ...
    "fouled_role": {"ST": 1.6, "W": 1.6, "AM": 1.4, "DM": 0.9, "FB": 0.9, "CB": 0.6, "GK": 0.3},   # ... and forwards on the
                               # ball, holding it up or running at defenders, are fouled most
    "cross_depth_m": (6.0, 14.0),  # a cross comes down this far from the goal line ...
    "cross_spread_m": 6.0,     # ... around the middle of the goal (sd)
    "aerial_cross": 0.45, "aerial_long": 0.60,  # share of crosses / forward long balls contested in the air (if a defender
                                                # is near; many crosses are cut out low or overhit instead, many long balls
                                                # are run onto). aerial_long was 0.95 before 0.5.0: with the keepers'
                                                # launches, strikers would contest more duels than centre-backs
    "aerial_reach_m": 8.5,     # a defender this close to where the ball comes down contests it
    "aerial_reach_cross_m": 16.0,  # ... or this close, for a cross (it hangs in the air)
    # Who attacks a high ball among the defenders within reach: centre-backs first (FBref 2023/24: three of the five
    # players with the most aerial duels won were centre-backs, the other two target forwards), by role and aerial rating.
    "aerial_role": {"CB": 4.0, "FB": 1.0, "DM": 1.3, "CM": 0.7, "AM": 0.35, "W": 0.35, "ST": 0.8, "GK": 0.0},
    "aerial_pick": 0.30,       # ... aerial z on that choice (log scale)
    "aerial_failed": 0.95,     # a long ball that does not arrive is still contested in the air this often
    "aerial_skill": 0.25,      # aerial z difference (0.45 before 0.4.0 let centre-backs win 85% of their duels)
    "aerial_height": 0.15,     # per 10 cm of height difference
    "aerial_defender_edge": 0.25,  # defenders attacking the ball in front of them win a few more
    "aerial_cross_edge": 0.5,  # ... and more on a cross into the box (with cross_delivery and aerial_cross: cross
                               # completion near the Premier League's 19-22%, centre-backs winning about 70% of duels)
    "header_clear_corner": 0.08,   # a defender's header from a cross goes out for a corner (0.12 before 0.6.0: full-backs
                                   # cross too now, and corners stay in band)
    "corner_after_block": 0.15,  # a blocked shot goes behind for a corner (0.55 in the realistic profile; 0.5.0 blocks more
                                 # shots, so fewer of them go behind to keep corners in band; 0.38 in 0.5.0)
    "goal_kick_long": 0.5,     # goal kicks hit long to the front players
    # A keeper's pass in open play is launched long to the front players this often (0.5.0), less with a better
    # distributor and on a side of good passers (team style ``keep``), so keepers differ the way Ederson and Pickford do.
    # Tuned to the Premier League's share of keeper passes of 32 m or more: 46.6% in 2023/24, 47.0% in 2024/25 (Opta
    # Analyst, 12 Sep 2025). Before 0.5.0 keepers only played short in open play: 2.7% of their passes went over 40 yards
    "gk_launch": 0.38,
    "gk_launch_distribution": 0.5,   # log-odds per z of the keeper's distribution, against launching
    "gk_launch_keep": 1.0,           # log-odds per style z of the side's ``keep``, against launching
    "sub_window": (0.58, 0.95),  # substitutions happen at stoppages from about the hour mark
}
# League-mode motion (regista.synth.physical): every player on the pitch moves every 0.1 s within his own top speed and
# acceleration, tiring with his stamina. Speeds in m/s. The caps say how hard a player is willing to go in each situation;
# his own top speed (``top_speed_kmh``) and acceleration (``acceleration_ms2``) say what he can do. Tuned so the league
# lands inside the physical bands in regista.synth.report (Premier League and FIFA World Cup norms, sources cited there).
MOTION: dict[str, Any] = {
    "walk": 1.5,               # dead ball: walking back into shape
    "burst_to": 6.0,           # an urgent move to above this speed (21.6 km/h) uses his full acceleration ...
    "burst_acc": 2.6,          # ... a shorter urgent burst at most this (m/s^2)
    "brake_gap": 1.5,          # slowing down by more than this (m/s), urgent or not, a player brakes firmly ...
    "brake_end": 0.3,          # ... until he is within this of the speed he wants
    "brake": 3.4,              # ... at this rate (m/s^2, or his own braking if lower), over a second or more, rather than
                               # easing off or stopping dead: decelerations outnumber accelerations in soccer (Harper, Carling
                               # and Kiely 2019, Sports Medicine 49:1923-47)
    "jog": 3.4,                # jogging (12 km/h)
    "run": 5.0,                # running (18 km/h)
    "high": 6.4,               # the cap for a long move that is not a sprint (23 km/h)
    "gain": 0.9,               # desired speed per metre still to go (an arrive behaviour: slows down as he gets there)
    # off the ball: (metres from his target, cap). Walk while close, then run: players walk or run more than they jog
    # (Premier League 2024/25: the most any regular jogged was 34.7% of his time, The Analyst)
    "ramp": ((0.0, 0.0), (4.0, 1.4), (7.0, 1.8), (9.0, 4.8), (14.0, 6.6)),
    "ball_lag_s": 0.8,         # the shape follows where the ball has been over the last second or so, not every touch
    "comfort_acc": 1.4,        # m/s^2: unhurried moves speed up gently; urgent ones use his full acceleration
    "taper": 3.0,              # full acceleration up to two thirds of top speed, then tapering to nothing at top speed
    "shift": (16.0, -11.0),    # team shape: the side in possession pushes up, the other drops off
    "shift_rate": 6.0,         # ... at this speed (m/s), not in one jump
    # how far each role's shape position follows the ball: centre-backs shuffle across and step up with it (they ran too
    # little at 0.33: every regular below the Premier League's lowest, 8.5 km per 90)
    "pull": {"GK": 0.20, "CB": 0.55, "FB": 0.58, "DM": 0.70, "CM": 0.72, "AM": 0.56, "W": 0.50, "ST": 0.48},
    "box_push": {"AM": 4.0, "W": 3.0, "CM": 2.0, "ST": 6.0},   # metres further forward, in full with the ball at the goal
                               # line (ST since 0.7.0: the striker attacks the box for crosses)
    # (0.7.0, review closing round 2) metres further up in possession, on top of the team's shift: the back line steps up
    # and the full-backs push on, so they pass from beyond their own 40% and full-backs reach the crossing zone
    "push_role": {"CB": 12.0, "FB": 24.0},
    "width_pull": {"FB": 0.30, "W": 0.30},   # (0.7.0) in possession, full-backs and wingers follow the ball across this
                               # much (their pull, above, still applies up and down the pitch): they hold the width
    "wander_m": (0.9, 0.6),    # a slow personal drift around the shape position (Ornstein-Uhlenbeck step, each second):
                               # more in possession (finding space), less out of it
    "press_gap_m": 5.5,        # the presser closes the holder down to about this distance, goal-side
    "press_sprint_m": 10.0,    # ... sprinting when he is further away than this (if his reserve allows)
    "run_rate": {"W": 0.009, "ST": 0.003, "AM": 0.0035, "FB": 0.012, "CM": 0.014, "DM": 0.005, "CB": 0.0015, "GK": 0.0},
                               # (0.6.0: FB 0.0075, CM 0.005, DM 0.0025 before; with build-up through the back the ball spends
                               # more time deep, and midfielders and full-backs make more runs to stay in the physical bands;
                               # FB 0.012 since 0.7.0: full-backs overlap into the crossing zone)
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
# Team style (league mode): (ratings averaged over the starting outfielders, centre, sd), measured over the league's
# clubs: the sd is that of a club's mean, so z runs about -1.5 to 1.5 across six clubs. Weights in LEAGUE ("keep_*",
# "press_*"). Without it every club kept about half the ball and pressed alike; Premier League clubs run from 35% to 66%
# possession and from about 8.6 to 17 PPDA (sources in regista.synth.report.STYLE_NORMS).
TEAM_STYLE: dict[str, tuple[tuple[str, ...], float, float]] = {
    "keep": (("passing", "vision"), 66.2, 1.7),
    "press": (("defending", "stamina"), 66.9, 1.2),
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
    style: dict[str, float] = field(default_factory=dict)   # league mode: team style from the starters' ratings (TEAM_STYLE)

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
            for team in (self.home, self.away):
                team.style = self._team_style(team)

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

    def aerial_probability(self, attacker: Player, defender: Player, cross: bool = False) -> float:
        """Chance the attacker wins a contested header: aerial ratings and height, a small edge to the defender (a large
        one on a cross into the box, where he attacks the ball facing it)."""
        edge = LEAGUE["aerial_skill"] * (self.z(attacker, "aerial") - self.z(defender, "aerial")) \
            + LEAGUE["aerial_height"] * ((attacker.height_cm or 180.0) - (defender.height_cm or 180.0)) / 10.0 \
            - LEAGUE["aerial_defender_edge"] - (LEAGUE["aerial_cross_edge"] if cross else 0.0)
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

    def _team_style(self, team: Team) -> dict[str, float]:
        """The team's style from its starting outfielders' ratings (league mode), as a z against other clubs' starting XIs
        (``TEAM_STYLE``): ``keep`` from passing and vision (teams of good passers keep the ball), ``press`` from defending
        and stamina (teams of fit, good defenders win it back high up the pitch)."""
        out = {}
        xi = [p for p in team.players[:11] if p.position != "GK"]
        for key, (ratings, centre, sd) in TEAM_STYLE.items():
            mean = sum(sum((p.attrs or {}).get(r, SKILL_CENTRE[r]) for r in ratings) / len(ratings) for p in xi) / max(1, len(xi))
            out[key] = clamp((mean - centre) / sd, -2.5, 2.5)
        return out

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
                        push = M["push_role"].get(p.role or "", 0.0) * max(0.0, sh) / M["shift"][0] if team is att else 0.0
                        ax = clamp(ax + sign * (sh + push), 2.0, PITCH_L - 2.0)
                    pull = b.pull
                    if team is att and ball_att > 60.0:   # with the ball high up the pitch, the front players attack the box
                        ax += sign * M["box_push"].get(p.role or "", 0.0) * (ball_att - 60.0) / 45.0
                    pull_y = M["width_pull"].get(p.role or "", pull) if team is att else pull   # wide men hold the width
                    tx, ty = ax + (sx - ax) * pull + b.ox, ay + (sy - ay) * pull_y + b.oy
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
                # a big drop in speed starts a firm braking phase, which lasts until he is nearly at the speed he wants
                b.braking = vdes < s and (s - vdes > M["brake_gap"] or (b.braking and s - vdes > M["brake_end"]))
                if vdes > s:   # his full acceleration for an urgent move to sprinting pace, a firm one for a shorter burst
                    a = (b.acc if vdes > M["burst_to"] else min(b.acc, M["burst_acc"])) if urgent else min(b.acc, comfort)
                    lim = max(a * min(1.0, M["taper"] * (1.0 - s / vmax)), 0.8) * step
                elif b.braking:
                    lim = min(b.dec, M["brake"]) * step
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
        touches = max(1, int(hold / (LEAGUE["touch_every_s"] if self.league else 0.8)))
        self.cur_pos["touches"] += touches
        for k in range(touches):
            self._event("touch", p, t=self.t + k * hold / touches, pitch=p.pos, under_pressure=pressure,
                        qualifiers=["first_touch"] if k == 0 and self.cur_pos["touches"] == touches else None)

        # Carry: drift toward goal when there is space.
        start = p.pos
        ahead = self.nearest((p.x + 6 * sign, p.y), opp)
        space = dist(ahead.pos, (p.x + 6 * sign, p.y)) > 5.0
        carry_p = 0.7 if not self.league else clamp(0.7 * math.exp(LEAGUE["carry_drive"] * self.z(p, "dribbling"))
                                                    * LEAGUE["carry_role"].get(p.role or "", 1.0), 0.0, 0.95)
        if space and rng.random() < carry_p:
            speed = rng.uniform(*LEAGUE["carry_speed"]) * math.exp(LEAGUE["carry_pace"] * clamp(self.z(p, "dribbling"), -2.0, 4.0)) \
                if self.league else rng.uniform(3.0, 7.0)
            side = LEAGUE["carry_side_m"] if self.league else 4.0
            target = (clamp(p.x + sign * speed * hold, 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, side), 1.0, PITCH_W - 1.0))
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
            w_take_on *= math.exp(LEAGUE["take_on_drive"] * self.z(p, "dribbling")) * LEAGUE["take_on_role"].get(p.role or "", 1.0)
            w_pass *= LEAGUE["pass_role"].get(p.role or "", 1.0)
            band = 0 if dgoal < d1 else 1 if dgoal < d2 else 2
            w_shot *= math.exp(LEAGUE["shot_drive"] * LEAGUE["shot_drive_band"][band] * self.z(p, "finishing")) \
                * LEAGUE["shot_role"].get(p.role or "", (1.0,) * 3)[band]
            if self.pos_pass is not None:  # chance creation: a pass from a player with vision sets up a shot more often
                w_shot *= math.exp(LEAGUE["create_shot"] * self.z(self.players[self.pos_pass["player_id"]], "vision"))
                if self.pos_pass["event_type"] == "cross":   # a cross met in a crowded box is a shot less often
                    w_shot *= LEAGUE["after_cross_shot"]
            w_lose *= math.exp(LEAGUE["lose_defender"] * self.z(marker, "defending") - LEAGUE["lose_dribbler"] * self.z(p, "dribbling")
                               - LEAGUE["keep_lose"] * team.style.get("keep", 0.0))
            if self.att_x(team, p.x) < PITCH_L * 0.6:   # in his own 60%: the opponents' press (their PPDA zone)
                w_lose *= LEAGUE["press_base"] * math.exp(LEAGUE["press_lose"] * opp.style.get("press", 0.0))
            w_lose *= LEAGUE["lose_role"].get(marker.role or "", 1.0)
        action = rng.choices(["pass", "take_on", "shot", "lose", "out"], weights=[w_pass, w_take_on, w_shot, w_lose, w_out])[0]
        if action == "pass":
            self._do_pass(p, pressure)
        elif action == "take_on":
            self._do_take_on(p, self._tackler(p, marker) if self.league else marker)
        elif action == "shot":
            self._do_shot(p)
        elif action == "lose":
            foul_p = self.tune["foul_on_tackle"]
            if self.league:
                marker = self._tackler(p, marker)
                foul_p = clamp(foul_p * math.exp(-LEAGUE["foul_discipline"] * self.z(marker, "defending"))
                               * LEAGUE["foul_role"].get(marker.role or "", 1.0) * LEAGUE["fouled_role"].get(p.role or "", 1.0),
                               0.0, 0.9)
            if rng.random() < foul_p:
                self._foul(marker, p)
            else:
                self._end_possession("dispossessed")
                self._event("tackle", marker, related=p, pitch=marker.pos, outcome="success")
                self._start_possession(marker, "tackle", from_player=p)
        else:
            self._do_out_of_play(p)

    def _tackler(self, p: Player, marker: Player) -> Player:
        """League mode: who wins the ball off ``p``. The nearest man presses, but the ball is won by whoever of the
        opponents within ``tackle_reach_m`` steps in, by role (``tackle_role``: per man, defenders most and strikers least;
        midfielders are within reach most often, so they win the most); he closes the last metres before the tackle."""
        cands = sorted((q for q in self.other(p.team).starters if q.position != "GK"
                        and dist(q.pos, p.pos) < LEAGUE["tackle_reach_m"]), key=lambda q: q.player_id)
        if marker not in cands:
            cands.append(marker)
        tackler = self.rng.choices(cands, weights=[LEAGUE["tackle_role"].get(q.role or "", 1.0) for q in cands])[0]
        if tackler is not marker:
            self._reach(tackler, p.pos, max_s=1.0)
        return tackler

    def _pick_pass_target(self, p: Player) -> Player:
        sign = p.team.attack_sign
        cands = []
        for q in p.team.starters:
            if q is p:
                continue
            d = dist(p.pos, q.pos)
            forward = (q.x - p.x) * sign
            tilt = (LEAGUE["forward_tilt"] + LEAGUE["vision_forward"] * self.z(p, "vision")) if self.league else 0.06
            w = math.exp(-(((d - 16.0) / 13.0) ** 2)) * (1.0 + tilt * clamp(forward, -10.0, 30.0)) + 0.02
            if q.position == "GK":
                # league mode: a defender in his own half plays it back to the keeper far more often (Premier League
                # keepers make about 30 passes a match; 0.1.0's weight left some without a touch in a half)
                w *= LEAGUE["gk_target"] if self.league and self.att_x(p.team, p.x) < PITCH_L / 2 else 0.15
            if self.league:  # teammates look for the good passers, and near goal for the good finishers
                if self.att_x(p.team, p.x) < LEAGUE["attack_from"]:   # build-up looks for the good passers
                    w *= LEAGUE["receive_role"].get(q.role or "", 1.0) * math.exp(LEAGUE["receive_passing"] * self.z(q, "passing"))
                else:
                    w *= LEAGUE["receive_role_attack"].get(q.role or "", 1.0)
                if self.att_x(p.team, q.x) > 70:
                    w *= math.exp(LEAGUE["find_finisher"] * self.z(q, "finishing"))
            cands.append((q, max(w, 0.001)))
        players, weights = zip(*cands)
        return self.rng.choices(players, weights=weights)[0]

    def _pick_cross_target(self, p: Player, aim: Point) -> Player | None:
        """League mode (0.7.0): who a cross is for. Outfield teammates within ``cross_box_m`` of the opponent's goal line,
        arriving in or already in the box, by role (``cross_role``: strikers first, then wingers and attacking
        midfielders), nearness to where the ball comes down and (``cross_finisher``) finishing. None when nobody is there
        to aim at."""
        team = p.team
        cands = [q for q in sorted(team.starters, key=lambda q: q.player_id) if q is not p and q.position != "GK"
                 and PITCH_L - self.att_x(team, q.x) < LEAGUE["cross_box_m"]]
        if not cands:
            return None
        weights = [LEAGUE["cross_role"].get(q.role or "", 0.5) * math.exp(-dist(q.pos, aim) / LEAGUE["cross_near_m"]
                   + LEAGUE["cross_finisher"] * self.z(q, "finishing")) for q in cands]
        return self.rng.choices(cands, weights=weights)[0]

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
            foul_p = clamp(foul_p * LEAGUE["take_on_foul"] * math.exp(-LEAGUE["foul_discipline"] * self.z(defender, "defending"))
                           * LEAGUE["foul_role"].get(defender.role or "", 1.0) * LEAGUE["fouled_role"].get(p.role or "", 1.0),
                           0.0, 0.9)
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
        if self.league and rng.random() < LEAGUE["take_on_loose"]:
            # the defender gets a foot to it and the ball runs loose: whoever is nearest picks it up (a recovery, no tackle)
            self._end_possession("dispossessed")
            opp = self.other(team)
            loose = (clamp(p.x + sign * rng.uniform(2.0, 6.0), 1.0, PITCH_L - 1.0), clamp(p.y + rng.gauss(0, 3.0), 1.0, PITCH_W - 1.0))
            self._chase(loose, team, opp)
            self.ball_speed = 6.0
            self.advance(0.6, ball_to=loose)
            self.ball_speed = 0.0
            self.chasers.clear()
            # the dribbler has lost it: anyone else nearest gets there first
            winner = min((q for q in team.starters + opp.starters if q is not p), key=lambda q: (dist(q.pos, loose), q.player_id))
            self._reach(winner, loose)
            self._event("recovery", winner, pitch=loose, outcome="success")
            self._start_possession(winner, "rebound" if winner.team is team else "loose_ball", from_player=p)
            return
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
        launch = not goal_kick and p.position == "GK" and rng.random() < _sigmoid(
            _logit(LEAGUE["gk_launch"]) - LEAGUE["gk_launch_distribution"] * self.z(p, "distribution")
            - LEAGUE["gk_launch_keep"] * team.style.get("keep", 0.0))
        wide = abs(p.y - PITCH_W / 2) > 18   # in a wide channel, more than 18 m from the middle
        to_goal_line = PITCH_L - self.att_x(team, p.x)
        cross_aim: Point | None = None
        target: Player | None = None
        if not (goal_kick or launch) and wide and to_goal_line < LEAGUE["cross_zone_m"].get(p.role or "", 35.0) \
                and (to_goal_line < 3.0 or rng.random() < LEAGUE["cross_choice"].get(p.role or "", 1.0)):
            # a cross (always from the corner flag): into the box, at a teammate attacking it
            depth = PITCH_L - rng.uniform(*LEAGUE["cross_depth_m"])
            cross_aim = (depth if sign > 0 else PITCH_L - depth,
                         clamp(PITCH_W / 2 + rng.gauss(0.0, LEAGUE["cross_spread_m"]), 14.0, 54.0))
            target = self._pick_cross_target(p, cross_aim)
        kind = "cross" if target is not None else "pass"
        long_ball = False
        if target is None and not (goal_kick or launch) and self.att_x(team, p.x) < PITCH_L / 2:
            share = LEAGUE["long_ball_role"].get(p.role or "", 0.0)
            long_ball = share > 0 and rng.random() < share * math.exp(LEAGUE["long_ball_passing"] * self.z(p, "passing"))
        if goal_kick or launch or long_ball:  # hit long to one of the three players furthest forward
            front = sorted((q for q in team.starters if q.position != "GK"), key=lambda q: (-self.att_x(team, q.x), q.player_id))[:3]
            target = rng.choice(front)
        elif target is None:
            target = self._pick_pass_target(p)
        forward = (target.x - p.x) * sign
        aim = target.pos
        through = False
        if kind == "pass" and not (goal_kick or launch) and target.position != "GK" and forward > 6 \
                and self.att_x(team, target.x) > 60:
            through = rng.random() < LEAGUE["through_ball"] * math.exp(LEAGUE["through_vision"] * self.z(p, "vision"))
        if through:  # into the space behind the defence, ahead of the runner
            ahead = clamp(self.att_x(team, target.x) + rng.uniform(6.0, 12.0), 0.0, PITCH_L - 3.0)
            aim = (ahead if sign > 0 else PITCH_L - ahead, clamp(target.y + rng.gauss(0, 2.0), 2.0, PITCH_W - 2.0))
        elif kind == "cross":   # into the box, where the target attacks the ball (the defenders there are centre-backs)
            aim = cross_aim
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
            - LEAGUE["pass_defender"] * self.z(defender, "defending") + LEAGUE["keep_pass"] * team.style.get("keep", 0.0)
        if through:
            lo += LEAGUE["pass_vision_tb"] * self.z(p, "vision")
        if pressure:
            lo -= LEAGUE["pass_pressure"] * self.z(marker, "defending")
        if kind == "cross":
            lo += LEAGUE["cross_delivery"]
        ok = rng.random() < clamp(_sigmoid(lo), 0.05 if kind == "cross" else 0.2, 0.985)
        # Offside: a mistimed run on a ball in behind, or a long forward ball to the furthest man forward.
        furthest = max((q for q in team.starters if q.position != "GK"), key=lambda q: self.att_x(team, q.x))
        offside = False
        if through:
            offside = rng.random() < LEAGUE["offside_through"]
        elif forward_aim > 15 and target is furthest:
            offside = rng.random() < LEAGUE["offside_long"]
        # An aerial contest where the ball comes down: crosses, long balls, long goal kicks, if a defender is close.
        duel: tuple[Player, Player] | None = None
        high_ball = kind == "cross" or (long and (forward_aim > 10 or goal_kick))   # balls played back or across stay low
        # a cross hangs in the air long enough for defenders to come across from further away
        reach = LEAGUE["aerial_reach_cross_m"] if kind == "cross" else LEAGUE["aerial_reach_m"]
        if not offside and not through and high_ball and dist(defender.pos, aim) < reach:
            header = self._aerial_defender(aim, opp, reach)
            if kind == "cross" and rng.random() < LEAGUE["aerial_cross"]:
                # a contested cross is won in the air: the attacker's header is the cross arriving (Opta counts a cross
                # completed when a teammate wins it), the defender's is a clearance
                att_wins = rng.random() < self.aerial_probability(target, header, cross=True)
                duel = (target, header) if att_wins else (header, target)
                ok = att_wins
            elif kind != "cross" and ok and rng.random() < LEAGUE["aerial_long"]:
                att_wins = rng.random() < self.aerial_probability(target, header)
                duel = (target, header) if att_wins else (header, target)
                ok = att_wins
            elif kind != "cross" and not ok and dist(target.pos, aim) < LEAGUE["aerial_reach_m"] \
                    and rng.random() < LEAGUE["aerial_failed"]:
                # a ball that does not arrive is still contested: the defender heads it away, or the attacker wins the
                # header but cannot keep it (it runs loose); either way the duel is won in the air as often as on a
                # ball that does arrive
                att_wins = rng.random() < self.aerial_probability(target, header)
                duel = (target, header) if att_wins else (header, target)
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
            if not ok and winner.team is not team:
                self._header_away(winner, team, kind)
                return
        if ok:
            if through or aim != target.pos:
                self._reach(target, aim)
            self.last_pass = ev
            self._start_possession(target, "pass_received", from_player=p)
            self.pos_pass = ev
            return
        self._league_failed_pass(p, kind, long=long and kind == "pass")

    def _aerial_defender(self, aim: Point, opp: Team, reach: float) -> Player:
        """Who attacks a high ball coming down at ``aim``: one of the opponents' outfielders within ``reach``, centre-backs
        first, then by aerial rating (``LEAGUE["aerial_role"]``); the nearest when nobody else is in reach."""
        cands = sorted((q for q in opp.starters if q.position != "GK" and dist(q.pos, aim) < reach), key=lambda q: q.player_id)
        if not cands:
            return self.nearest(aim, opp, outfield=True)
        weights = [LEAGUE["aerial_role"].get(q.role or "", 1.0) * math.exp(LEAGUE["aerial_pick"] * self.z(q, "aerial"))
                   for q in cands]
        if sum(weights) <= 0:
            return self.nearest(aim, opp, outfield=True)
        return self.rng.choices(cands, weights=weights)[0]

    def _league_failed_pass(self, p: Player, kind: str, long: bool = False) -> None:
        """A pass that did not arrive: as in 0.1.0 (out of play, interception, clearance, loose ball), except that of the
        two defenders nearest the ball the better reader tends to get there, and reading it (an interception) rather than
        picking it up loose rises with defending. A long ball that drops short or overruns is read less often (0.5.0):
        it is mostly headed or picked up loose."""
        rng = self.rng
        team, opp = p.team, self.other(p.team)
        here = (self.ball[0], self.ball[1])
        near = sorted(opp.starters, key=lambda q: (dist(q.pos, here), q.player_id))[:LEAGUE["interception_near"]]
        winner = rng.choices(near, weights=[math.exp(LEAGUE["interception_skill"] * self.z(q, "defending")) for q in near])[0]
        fp = dict(self.tune["failed_pass"])
        fp["interception"] *= math.exp(LEAGUE["interception_skill"] * self.z(winner, "defending")) \
            * (LEAGUE["long_interception"] if long else 1.0) * LEAGUE["interception_rate"]
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
            crossed = kp is not None and kp["event_type"] == "cross"
            headed = crossed and rng.random() < 0.6
            factor = LEAGUE["header_xg"] if headed else LEAGUE["cross_volley_xg"] if crossed else 1.0
            xg = clamp(LEAGUE["xg_scale"] * math.exp(-0.12 * d) * factor, 0.02, 0.85)
            body_part, weak = ("head", False) if headed else self.foot_for(p, 0.8)
        speed_kmh = rng.uniform(40.0, 75.0) if headed else rng.uniform(65.0, 115.0)
        skill = self.z(p, "aerial" if headed else "finishing")
        if rng.random() < self.goal_probability(p, keeper, xg, headed=headed, weak=weak):
            result = "goal"
        elif penalty:
            result = "saved" if rng.random() < 0.7 else "off_target"
        else:
            on_target = _sigmoid(_logit(LEAGUE["shot_saved"]) + LEAGUE["on_target"] * skill)
            u = rng.random()
            result = "saved" if u < on_target else "blocked" if (u - on_target) / (1 - on_target) < LEAGUE["shot_blocked"] \
                else "off_target"
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
            if rng.random() < LEAGUE["corner_after_block"]:
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
