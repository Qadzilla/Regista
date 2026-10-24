"""Physical output of a league match: every player's motion at 10 Hz, summarised the way tracking providers report it.

In league mode (players with ratings) the generator moves all 22 players on the pitch every 0.1 s, each within his own
top speed and acceleration (``top_speed_kmh``, ``acceleration_ms2``) and tiring with his ``stamina``. A :class:`Body`
holds one player's motion state and meters it as it happens; at full time each player who played gets one ``physical``
record (schema 0.2.0). Without ratings none of this runs.

Every number in the record has a definition and a source in :data:`DEFINITIONS` (rows of
``docs/scout-terminal/industry-metrics.md``). The data is synthetic: these are the simulator's own players, measured
exactly (no tracking noise), not anybody's real output.
"""

from __future__ import annotations

import math
from typing import Any

Record = dict[str, Any]

SAMPLE_HZ = 10                         # the simulation step is 0.1 s (generator.SIM_DT)
ZONES_KMH = (7.0, 15.0, 20.0, 25.0)    # FIFA speed zones (men): Z1 0-6.9, Z2 7.0-14.9, Z3 15.0-19.9, Z4 20.0-24.9, Z5 >= 25.0
WALK_KMH = 6.0                         # The Analyst: jogging is 6-15 km/h, walking below it
HI_KMH = 20.0                          # high intensity: >= 20 km/h (FIFA; Wyscout's HI = HSR + sprinting)
SPRINT_KMH = 25.0                      # sprinting: >= 25 km/h (FIFA zone 5; Wyscout, Premier League, Opta Analyst)
MIN_EFFORT_S = 1.0                     # an effort (sprint, high-intensity run, acceleration) lasts at least 1 s (Wyscout)
ACC_MEDIUM = 1.5                       # m/s^2: acceleration efforts peak at 1.5-3 (medium) or above 3 (high) (Wyscout)
ACC_HIGH = 3.0

_Z = tuple(z / 3.6 for z in ZONES_KMH)
_WALK = WALK_KMH / 3.6
_HI = HI_KMH / 3.6
_SPRINT = SPRINT_KMH / 3.6

# metric -> (definition, source keys in docs/scout-terminal/industry-metrics.md). Shown wherever these numbers are shown.
DEFINITIONS: dict[str, tuple[str, str]] = {
    "distance_m": ("Distance covered on the pitch, in metres, from the 10 Hz motion (#165)", "WY-physical_metrics, OA-PHYS"),
    "zone1_m": ("Distance at 0-6.9 km/h, FIFA speed zone 1 (#167)", "FIFA-PHYS"),
    "zone2_m": ("Distance at 7.0-14.9 km/h, FIFA speed zone 2 (#167)", "FIFA-PHYS"),
    "zone3_m": ("Distance at 15.0-19.9 km/h, FIFA speed zone 3 (#167)", "FIFA-PHYS"),
    "zone4_m": ("Distance at 20.0-24.9 km/h, FIFA speed zone 4: high-speed running (#167, #170)", "FIFA-PHYS, WY-physical_metrics"),
    "zone5_m": ("Distance at 25.0 km/h or more, FIFA speed zone 5: sprinting (#167, #172)", "FIFA-PHYS, WY-physical_metrics"),
    "hi_distance_m": ("High-intensity distance: at 20 km/h or more, zones 4 and 5 together (#171)", "FIFA-PHYS, WY-physical_metrics"),
    "sprint_distance_m": ("Sprint distance: at 25 km/h or more (#172; same as zone 5)", "FIFA-PHYS, WY-physical_metrics"),
    "walking_s": ("Seconds below 6 km/h (The Analyst: jogging is 6-15 km/h, walking below it) (#168)", "OA-PHYS"),
    "jogging_s": ("Seconds at 6-15 km/h (#168)", "OA-PHYS"),
    "hi_efforts": ("High-intensity runs: at 20 km/h or more for at least 1 s (#171)", "WY-physical_metrics"),
    "sprints": ("Sprints: at 25 km/h or more for at least 1 s (#172; Wyscout, Premier League, Opta Analyst)",
                "WY-physical_metrics, OA-PHYS"),
    "peak_speed_kmh": ("Top speed: the highest speed reached in the match (#174)", "SC-PV, OA-PHYS"),
    "accelerations_medium": ("Accelerations above 1.5 m/s^2 held for at least 1 s that peak below 3 m/s^2 (#176, Regista's "
                             "reading of Wyscout's rule)", "WY-physical_metrics"),
    "accelerations_high": ("Accelerations above 1.5 m/s^2 held for at least 1 s that peak at 3 m/s^2 or more (#176)",
                           "WY-physical_metrics"),
    "decelerations_medium": ("Decelerations below -1.5 m/s^2 held for at least 1 s that peak above -3 m/s^2 (#177)",
                             "WY-physical_metrics"),
    "decelerations_high": ("Decelerations below -1.5 m/s^2 held for at least 1 s that reach -3 m/s^2 or less (#177)",
                           "WY-physical_metrics"),
    "relocated_m": ("Not a football metric: position jumps the simulator made without motion (a keeper's dive to the ball, "
                    "the last metres to a set-piece spot, the reset after a goal). Never counted in any distance above", "Regista"),
}
METRICS = tuple(DEFINITIONS)
METHOD = {
    "sample_hz": SAMPLE_HZ, "zones_kmh": list(ZONES_KMH), "hi_kmh": HI_KMH, "sprint_kmh": SPRINT_KMH,
    "min_effort_s": MIN_EFFORT_S, "acc_medium_ms2": ACC_MEDIUM, "acc_high_ms2": ACC_HIGH,
    "note": "Synthetic: the simulator's own motion, metered exactly (no tracking noise or smoothing).",
}


class Body:
    """One player's motion state (league mode) and the meters that record it. Speeds in m/s, distances in metres."""

    __slots__ = ("vx", "vy", "vmax", "acc", "dec", "stamina_z", "reserve", "ox", "oy", "run_until", "run_x", "run_y",
                 "pull", "run_rate", "on_since", "played", "s_prev", "braking",
                 "dist", "zone", "walk_s", "jog_s", "hi_t", "hi_n", "sp_t", "sp_n", "peak",
                 "acc_t", "acc_pk", "dec_t", "dec_pk", "acc_med", "acc_high", "dec_med", "dec_high",
                 "relocated", "by_period")

    def __init__(self, vmax: float, acc: float, stamina_z: float, pull: float, run_rate: float):
        self.vx = self.vy = 0.0
        self.vmax = vmax
        self.acc = acc
        self.dec = min(6.5, 1.4 * acc)    # players brake harder than they speed up
        self.stamina_z = stamina_z
        self.reserve = 1.0                # the anaerobic reserve that repeated sprints drain
        self.ox = self.oy = 0.0           # a slowly wandering offset from the shape position
        self.run_until = -1.0
        self.run_x = self.run_y = 0.0
        self.pull = pull
        self.run_rate = run_rate
        self.on_since: float | None = None
        self.played = 0.0
        self.s_prev = 0.0
        self.braking = False              # in a firm braking phase (the generator's steering keeps it until nearly done)
        self.dist = 0.0
        self.zone = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.walk_s = self.jog_s = 0.0
        self.hi_t = self.sp_t = 0.0
        self.hi_n = self.sp_n = 0
        self.peak = 0.0
        self.acc_t = self.acc_pk = self.dec_t = self.dec_pk = 0.0
        self.acc_med = self.acc_high = self.dec_med = self.dec_high = 0
        self.relocated = 0.0
        self.by_period: dict[int, list[float]] = {}   # period -> [seconds, distance, hi distance]

    def meter(self, s: float, dt: float, period: int) -> None:
        """Record one step at speed ``s`` (m/s) lasting ``dt`` seconds."""
        d = s * dt
        self.dist += d
        self.played += dt
        z = self.zone
        if s < _Z[0]:
            z[0] += d
        elif s < _Z[1]:
            z[1] += d
        elif s < _Z[2]:
            z[2] += d
        elif s < _Z[3]:
            z[3] += d
        else:
            z[4] += d
        if s < _WALK:
            self.walk_s += dt
        elif s < _Z[1]:
            self.jog_s += dt
        if s > self.peak:
            self.peak = s
        bp = self.by_period.get(period)
        if bp is None:
            bp = self.by_period[period] = [0.0, 0.0, 0.0]
        bp[0] += dt
        bp[1] += d
        # efforts: a run above a threshold counts when it has lasted MIN_EFFORT_S
        if s >= _HI:
            bp[2] += d
            self.hi_t += dt
        else:
            if self.hi_t >= MIN_EFFORT_S - 1e-9:
                self.hi_n += 1
            self.hi_t = 0.0
        if s >= _SPRINT:
            self.sp_t += dt
        else:
            if self.sp_t >= MIN_EFFORT_S - 1e-9:
                self.sp_n += 1
            self.sp_t = 0.0
        a = (s - self.s_prev) / dt if dt > 0 else 0.0
        self.s_prev = s
        if a >= ACC_MEDIUM:
            self.acc_t += dt
            if a > self.acc_pk:
                self.acc_pk = a
        else:
            self._end_acc()
        if a <= -ACC_MEDIUM:
            self.dec_t += dt
            if -a > self.dec_pk:
                self.dec_pk = -a
        else:
            self._end_dec()

    def _end_acc(self) -> None:
        if self.acc_t >= MIN_EFFORT_S - 1e-9:
            if self.acc_pk >= ACC_HIGH:
                self.acc_high += 1
            else:
                self.acc_med += 1
        self.acc_t = self.acc_pk = 0.0

    def _end_dec(self) -> None:
        if self.dec_t >= MIN_EFFORT_S - 1e-9:
            if self.dec_pk >= ACC_HIGH:
                self.dec_high += 1
            else:
                self.dec_med += 1
        self.dec_t = self.dec_pk = 0.0

    def stop(self) -> None:
        """Close any effort still running (the player went off, or the period ended)."""
        if self.hi_t >= MIN_EFFORT_S - 1e-9:
            self.hi_n += 1
        if self.sp_t >= MIN_EFFORT_S - 1e-9:
            self.sp_n += 1
        self.hi_t = self.sp_t = 0.0
        self._end_acc()
        self._end_dec()
        self.s_prev = math.hypot(self.vx, self.vy)

    def metrics(self) -> dict[str, float]:
        z = self.zone
        return {
            "distance_m": round(self.dist, 1),
            "zone1_m": round(z[0], 1), "zone2_m": round(z[1], 1), "zone3_m": round(z[2], 1),
            "zone4_m": round(z[3], 1), "zone5_m": round(z[4], 1),
            "hi_distance_m": round(z[3] + z[4], 1), "sprint_distance_m": round(z[4], 1),
            "walking_s": round(self.walk_s, 1), "jogging_s": round(self.jog_s, 1),
            "hi_efforts": self.hi_n, "sprints": self.sp_n, "peak_speed_kmh": round(self.peak * 3.6, 1),
            "accelerations_medium": self.acc_med, "accelerations_high": self.acc_high,
            "decelerations_medium": self.dec_med, "decelerations_high": self.dec_high,
            "relocated_m": round(self.relocated, 1),
        }


def per90(records: list[Record], key: str) -> float:
    """Pooled per-90 rate of ``key`` over physical records (sum of the metric over sum of minutes played)."""
    played = sum(r["played_s"] for r in records)
    return sum(r["metrics"][key] for r in records) / played * 5400.0 if played else 0.0
