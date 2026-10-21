"""Event spotting: what happened on the ball, from what the vision layer sees.

Input: the identity stage's named player and ball positions on the pitch (main camera, 5 per second) and the
possession agent's ``possession`` records. Output: ``event`` records (pass, cross, shot, save, goal, tackle,
interception, carry, take_on, nutmeg) with ``source: vision``, so clips cut from video carry the same tags as clips
from the generator and the Librarian can answer "find me X doing a nutmeg" from footage.

How
- Candidates come from geometry and are built for recall:
  - every hand-over between consecutive possessions (the ball left one player and reached a team-mate, an opponent,
    or nobody): pass, cross, shot, tackle, interception, or none of these;
  - every one-on-one inside a possession (an opponent goal-side within reach who ends up behind the carrier):
    take-on, nutmeg, or neither;
  - every stretch of a possession over which the carrier moves the ball 3 m or more: carry (a definition, no model).
- Two scikit-learn gradient-boosting classifiers decide what each candidate was. They are trained on Regista's
  rendered matches, labelled from the generator's events. A nutmeg is a take-on in which the ball goes through the
  defender while the carrier goes round him; the positions show that, as a camera would.
- Derived from a spotted shot, by broadcast logic: a save when the opposing goalkeeper has the ball straight after;
  a goal when the ball ends in the goal mouth, nobody claims it, and play restarts from the centre spot.
- Never used: on-screen captions (event-spotting footage is rendered without them) and anything from the generator
  at inference. Each team's attacking direction comes from where its goalkeeper stands in each period.
"""

from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from regista.schema import SCHEMA_VERSION

Record = dict[str, Any]
PITCH_L, PITCH_W = 105.0, 68.0
GOAL_HALF_WIDTH = 3.66
BOUNDARY_CLASSES = ["none", "pass", "cross", "shot", "tackle", "interception"]
DUEL_CLASSES = ["none", "take_on", "nutmeg"]
MODEL_FILE = "event_spotter.joblib"
CARRY_MIN_M = 3.0
MATCH_TOLERANCE_S = 1.0


# ---------------------------------------------------------------------------- positions over time

@dataclass
class View:
    t: float
    segment_id: str
    ball: tuple[float, float] | None
    players: dict[str, tuple[float, float, str, bool]]  # player id -> (x, y, team id, is goalkeeper)


class Positions:
    """Named player and ball positions per analysed main-camera frame, with nearest-in-time lookups."""

    def __init__(self, views: list[View]):
        self.views = sorted(views, key=lambda v: v.t)
        self.ts = [v.t for v in self.views]

    @classmethod
    def from_identity(cls, result: Any) -> Positions:
        return cls.from_frames(result.frames)

    @classmethod
    def from_frames(cls, frames: list[dict[str, Any]]) -> Positions:
        views = []
        for fr in frames:
            players = {o["player_id"]: (float(o["x"]), float(o["y"]), o["team_id"], bool(o.get("is_gk")))
                       for o in fr["obs"] if o.get("player_id")}
            b = fr.get("ball")
            views.append(View(float(fr["t"]), fr["segment_id"], (float(b["x"]), float(b["y"])) if b else None, players))
        return cls(views)

    @classmethod
    def from_tracks(cls, stream: list[Record], tracks: list[Record]) -> Positions:
        """The same view built from a generator's tracks (main-camera segments only): clean positions for fast tests and
        for comparing the spotter on perfect input against the same spotter on vision output."""
        header = next(r for r in stream if r["type"] == "match")
        main = {r["id"] for r in stream if r["type"] == "camera_segment" and r["kind"] == "main"}
        gk = {p["player_id"] for p in header["players"] if p.get("position") == "GK"}
        by_t: dict[float, View] = {}
        for tr in tracks:
            if tr.get("segment_id") not in main or not tr.get("pitch"):
                continue
            v = by_t.setdefault(float(tr["t"]), View(float(tr["t"]), tr["segment_id"], None, {}))
            xy = (float(tr["pitch"]["x"]), float(tr["pitch"]["y"]))
            if tr["object"] == "ball":
                v.ball = xy
            elif tr.get("player_id"):
                v.players[tr["player_id"]] = (*xy, tr["team_id"], tr["player_id"] in gk)
        return cls(list(by_t.values()))

    def window(self, t0: float, t1: float) -> list[View]:
        return self.views[bisect.bisect_left(self.ts, t0): bisect.bisect_right(self.ts, t1)]

    def player(self, pid: str, t: float, within: float = 0.45) -> tuple[float, float] | None:
        best = None
        for v in self.window(t - within, t + within):
            if pid in v.players and (best is None or abs(v.t - t) < abs(best[0] - t)):
                best = (v.t, v.players[pid][:2])
        return best[1] if best else None

    def ball(self, t: float, within: float = 0.45) -> tuple[float, float] | None:
        best = None
        for v in self.window(t - within, t + within):
            if v.ball is not None and (best is None or abs(v.t - t) < abs(best[0] - t)):
                best = (v.t, v.ball)
        return best[1] if best else None

    def segment(self, t: float) -> str | None:
        i = bisect.bisect_right(self.ts, t) - 1
        return self.views[i].segment_id if i >= 0 else None


def attack_signs(pos: Positions, periods: list[Record], team_ids: list[str]) -> list[tuple[float, float, dict[str, int]]]:
    """Per period: (t, t_end, team id -> +1 when attacking toward x = 105). The team whose goalkeeper stands nearer
    x = 0 attacks toward x = 105; read from the footage, not from the match data."""
    out = []
    for p in periods or [{"t": 0.0, "t_end": float("inf")}]:
        xs: dict[str, list[float]] = defaultdict(list)
        for v in pos.window(p["t"], p.get("t_end", float("inf"))):
            for x, _y, team, gk in v.players.values():
                if gk:
                    xs[team].append(x)
        mean = {t: float(np.mean(v)) for t, v in xs.items() if v}
        a, b = team_ids
        if a in mean and b in mean:
            left = a if mean[a] < mean[b] else b
        elif mean:
            known, x = next(iter(mean.items()))
            left = known if x < PITCH_L / 2 else (b if known == a else a)
        else:
            left = a
        out.append((p["t"], p.get("t_end", float("inf")), {left: 1, (b if left == a else a): -1}))
    return out


def _sign(signs: list[tuple[float, float, dict[str, int]]], team: str, t: float) -> int:
    for t0, t1, m in signs:
        if t0 <= t < t1:
            return m.get(team, 1)
    return signs[-1][2].get(team, 1) if signs else 1


def _goal(sign: int) -> tuple[float, float]:
    return (PITCH_L if sign > 0 else 0.0, PITCH_W / 2)


def _d(a: tuple[float, float] | None, b: tuple[float, float] | None, default: float = 99.0) -> float:
    return math.dist(a, b) if a is not None and b is not None else default


# ---------------------------------------------------------------------------- candidates and features

@dataclass
class Candidate:
    kind: str                      # "boundary" or "duel"
    t: float
    player_id: str
    team_id: str
    related_id: str | None
    features: dict[str, float]
    context: dict[str, Any] = field(default_factory=dict)


def boundary_candidates(poss: list[Record], pos: Positions, signs, gk_ids: set[str]) -> list[Candidate]:
    """One candidate per hand-over: possession p ends, possession q (if any) begins."""
    poss = sorted(poss, key=lambda r: r["t"])
    out = []
    for i, p in enumerate(poss):
        q = poss[i + 1] if i + 1 < len(poss) else None
        ta = float(p["t_end"])
        tb = float(q["t"]) if q else ta + 3.0
        s = _sign(signs, p["team_id"], ta)
        goal = _goal(s)
        path = [(v.t, v.ball) for v in pos.window(ta - 0.4, min(tb, ta + 3.0) + 0.4) if v.ball is not None]
        b0 = pos.ball(ta) or pos.player(p["player_id"], ta)
        b1 = path[-1][1] if path else b0
        travel = sum(math.dist(path[k][1], path[k + 1][1]) for k in range(len(path) - 1)) if len(path) > 1 else 0.0
        speeds = [math.dist(path[k][1], path[k + 1][1]) / max(0.05, path[k + 1][0] - path[k][0]) for k in range(len(path) - 1)]
        min_goal = min((math.dist(b, goal) for _t, b in path), default=_d(b0, goal))
        closest = min(path, key=lambda tb_: math.dist(tb_[1], goal))[1] if path else b0
        pa = pos.player(p["player_id"], ta)
        q_at_a = pos.player(q["player_id"], ta) if q else None
        q_at_b = pos.player(q["player_id"], tb) if q else None
        start_attack_x = ((b0[0] if s > 0 else PITCH_L - b0[0]) if b0 else 50.0)
        f = {
            "gap_s": min(tb - ta, 30.0),
            "same_team": float(q is not None and q["team_id"] == p["team_id"]),
            "opp_team": float(q is not None and q["team_id"] != p["team_id"]),
            "no_next": float(q is None),
            "q_is_opp_gk": float(q is not None and q["team_id"] != p["team_id"] and q["player_id"] in gk_ids),
            "holder_dist_at_change": _d(pa, q_at_a),
            "pass_dist": _d(pa, q_at_b),
            "ball_travel": travel,
            "ball_straight": _d(b0, b1, 0.0),
            "ball_max_speed": max(speeds, default=0.0),
            "ball_progress": ((b1[0] - b0[0]) * s) if b0 and b1 else 0.0,
            "ball_seen": float(len(path)),
            "start_goal_dist": _d(b0, goal),
            "min_goal_dist": min_goal,
            "closest_goal_dy": abs(closest[1] - PITCH_W / 2) if closest else 34.0,
            "closest_goal_dx": abs(closest[0] - goal[0]) if closest else 105.0,
            "start_wide": abs(b0[1] - PITCH_W / 2) if b0 else 0.0,
            "start_attack_x": start_attack_x,
            "p_len": float(p["t_end"]) - float(p["t"]),
            "q_len": (float(q["t_end"]) - float(q["t"])) if q else 0.0,
            "segment_change": float(q is not None and pos.segment(ta) != pos.segment(tb)),
        }
        out.append(Candidate("boundary", ta, p["player_id"], p["team_id"], q["player_id"] if q else None, f,
                             {"p": p, "q": q, "b0": b0, "b1": b1, "closest": closest, "sign": s}))
    return out


def duel_candidates(poss: list[Record], pos: Positions, signs) -> list[Candidate]:
    """One candidate per moment the carrier passes an opponent: the opponent is goal-side (ahead in the attacking
    direction) within reach in one frame and behind the carrier in the next frame both are seen. The candidate is
    timed at that crossing, and its features cover the approach before it and the second after."""
    out = []
    for p in poss:
        a, team = p["player_id"], p["team_id"]
        views = pos.window(float(p["t"]) - 0.6, float(p["t_end"]) + 1.0)
        if len(views) < 3:
            continue
        s = _sign(signs, team, float(p["t"]))
        opponents = {d for v in views for d, info in v.players.items() if info[2] != team}
        for d in opponents:
            both = [v for v in views if a in v.players and d in v.players]
            last_t = -1e9
            for v, w in zip(both, both[1:]):
                rel_v = (v.players[d][0] - v.players[a][0]) * s
                rel_w = (w.players[d][0] - w.players[a][0]) * s
                if not (rel_v > 0 >= rel_w and w.t - v.t <= 1.0 and v.t - last_t > 1.5):
                    continue
                approach = [u for u in both if v.t - 1.2 <= u.t <= v.t]
                near = [u for u in approach if math.dist(u.players[a][:2], u.players[d][:2]) <= 3.2
                        and 0.0 < (u.players[d][0] - u.players[a][0]) * s <= 3.5]
                if not near:
                    continue
                last_t = v.t
                first = near[0]
                span = [u for u in views if first.t <= u.t <= w.t + 0.4]
                ball_d = [math.dist(u.ball, u.players[d][:2]) for u in span if u.ball is not None and d in u.players]
                ball_a = [math.dist(u.ball, u.players[a][:2]) for u in span if u.ball is not None and a in u.players]
                car_d = [math.dist(u.players[a][:2], u.players[d][:2]) for u in span if a in u.players and d in u.players]
                ax, ay = first.players[a][:2]
                a_end = w.players[a][:2]
                f = {
                    "duration": w.t - first.t,
                    "start_ahead": (first.players[d][0] - ax) * s,
                    "start_dist": math.dist((ax, ay), first.players[d][:2]),
                    "min_ball_def": min(ball_d, default=9.0),
                    "mean_ball_def": float(np.mean(ball_d)) if ball_d else 9.0,
                    "max_ball_carrier": max(ball_a, default=0.0),
                    "mean_ball_carrier": float(np.mean(ball_a)) if ball_a else 0.0,
                    "min_carrier_def": min(car_d, default=9.0),
                    "carrier_progress": (a_end[0] - ax) * s,
                    "carrier_speed": math.dist(a_end, (ax, ay)) / max(0.1, w.t - first.t),
                    "ball_seen": float(len(ball_d)),
                    "in_possession": float(float(p["t"]) <= v.t <= float(p["t_end"])),
                }
                out.append(Candidate("duel", v.t, a, team, d, f, {"p": p, "where": (ax, ay)}))
    return out


def carry_spans(poss: list[Record], pos: Positions, split_at: dict[str, list[float]]) -> list[tuple[Record, float, float, tuple, tuple, float]]:
    """(possession, t0, t1, start, end, metres) for stretches of a possession where the carrier moved 3 m or more.
    A possession is split at the take-ons spotted in it, as a carry ends where a take-on begins."""
    out = []
    for p in poss:
        cuts = [float(p["t"])] + sorted(t for t in split_at.get(p["id"], []) if float(p["t"]) < t < float(p["t_end"])) + [float(p["t_end"])]
        for t0, t1 in zip(cuts, cuts[1:]):
            a, b = pos.player(p["player_id"], t0), pos.player(p["player_id"], t1)
            if a and b and math.dist(a, b) >= CARRY_MIN_M:
                out.append((p, t0, t1, a, b, math.dist(a, b)))
    return out


# ---------------------------------------------------------------------------- generated training data shaped like vision output

def pseudo_identity_frames(stream: list[Record], tracks: list[Record], *, fps: float = 5.0, noise_m: float = 0.2,
                           drop_player: float = 0.02, drop_ball: float = 0.02, seed: int = 0) -> list[dict[str, Any]]:
    """Identity-stage frames from a generator's tracks: main camera only, sampled at the vision layer's rate, with the
    position noise and missed detections the vision layer measures on rendered footage (about 0.2 m, a few per cent).
    Training on these alongside real vision output gives the classifiers enough rare events (nutmegs) without
    training on perfect positions. Tracks should be sampled at ``fps`` or faster."""
    rng = np.random.default_rng(seed)
    header = next(r for r in stream if r["type"] == "match")
    main = {r["id"] for r in stream if r["type"] == "camera_segment" and r["kind"] == "main"}
    gk = {p["player_id"] for p in header["players"] if p.get("position") == "GK"}
    step = 1.0 / fps
    # The generator samples whenever its clock passes the next sample time, so sample times are irregular: keep, per
    # frame slot, the sample nearest to it (the vision layer likewise sees one frame per slot).
    nearest: dict[int, float] = {}
    for t in {float(tr["t"]) for tr in tracks if tr.get("segment_id") in main}:
        k = round(t / step)
        if abs(t - k * step) <= step / 2 and (k not in nearest or abs(t - k * step) < abs(nearest[k] - k * step)):
            nearest[k] = t
    keep = set(nearest.values())
    frames: dict[float, dict[str, Any]] = {}
    for tr in tracks:
        t = float(tr["t"])
        if t not in keep or tr.get("segment_id") not in main or not tr.get("pitch"):
            continue
        fr = frames.setdefault(t, {"t": t, "frame": int(round(t * 25)), "segment_id": tr["segment_id"], "ball": None, "obs": []})
        x, y = float(tr["pitch"]["x"]) + rng.normal(0, noise_m), float(tr["pitch"]["y"]) + rng.normal(0, noise_m)
        if tr["object"] == "ball":
            if rng.random() >= drop_ball:
                fr["ball"] = {"x": x, "y": y}
        elif tr.get("player_id") and rng.random() >= drop_player:
            fr["obs"].append({"t": t, "x": x, "y": y, "team_id": tr["team_id"], "is_gk": tr["player_id"] in gk,
                              "player_id": tr["player_id"], "id_conf": 1.0})
    return [frames[t] for t in sorted(frames)]


def generated_example_set(seeds: list[int], minutes: float = 5.0, fps: float = 5.0) -> tuple[list, list]:
    """Labelled candidates from freshly generated matches, run through the same possession agent as vision output."""
    from regista.synth import generate
    from regista.vision.possession import infer_possessions

    B, D = [], []
    for seed in seeds:
        r = generate(seed=seed, minutes=minutes, track_hz=fps * 2)
        segs = [x for x in r.stream if x["type"] == "camera_segment"]
        frames = pseudo_identity_frames(r.stream, r.tracks, fps=fps, seed=seed)
        poss = infer_possessions(frames, r.match, r.match["match_id"], fps=fps, segment_end={x["id"]: x["t_end"] for x in segs})
        b, d = examples(Positions.from_frames(frames), poss, r.match, r.stream)
        B += b
        D += d
    return B, D


# ---------------------------------------------------------------------------- labels from the generator (training and evaluation only)

def _truth_index(events: list[Record]) -> dict[str, list[Record]]:
    by_type: dict[str, list[Record]] = defaultdict(list)
    for e in events:
        if e.get("type") == "event":
            by_type[e["event_type"]].append(e)
    return by_type


def _near(evs: list[Record], t: float, tol: float, player: str | None = None, related: str | None = None, outcome: str | None = None):
    for e in evs:
        if abs(float(e["t"]) - t) <= tol and (player is None or e.get("player_id") == player) \
                and (related is None or e.get("related_player_id") == related) and (outcome is None or e.get("outcome") == outcome):
            return e
    return None


def label_boundary(c: Candidate, truth: dict[str, list[Record]], tol: float = 1.2) -> str:
    q = c.related_id
    if _near(truth["shot"], c.t, tol, c.player_id):
        return "shot"
    if q and c.features["same_team"]:
        if _near(truth["cross"], c.t, tol, c.player_id, outcome="success"):
            return "cross"
        if _near(truth["pass"], c.t, tol, c.player_id, outcome="success"):
            return "pass"
    if q and c.features["opp_team"]:
        if _near(truth["tackle"], c.t, tol, q):
            return "tackle"
        if _near(truth["interception"], c.t, tol + 1.0, q):
            return "interception"
    return "none"


def label_duel(c: Candidate, truth: dict[str, list[Record]], tol: float = 1.2) -> str:
    e = _near(truth["take_on"], c.t, tol, c.player_id, c.related_id, outcome="success")
    if e is None:
        return "none"
    return "nutmeg" if "nutmeg" in (e.get("qualifiers") or []) else "take_on"


# ---------------------------------------------------------------------------- the model

@dataclass
class EventSpotter:
    boundary_model: Any = None
    duel_model: Any = None
    boundary_features: list[str] = field(default_factory=list)
    duel_features: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def _xy(cands: list[Candidate], names: list[str]) -> np.ndarray:
        return np.array([[c.features[n] for n in names] for c in cands], dtype=float) if cands else np.zeros((0, len(names)))

    def fit(self, boundary: list[tuple[Candidate, str]], duel: list[tuple[Candidate, str]], seed: int = 0,
            boundary_weights: list[float] | None = None, duel_weights: list[float] | None = None) -> EventSpotter:
        from sklearn.ensemble import GradientBoostingClassifier

        self.boundary_features = sorted(boundary[0][0].features)
        self.duel_features = sorted(duel[0][0].features)
        self.boundary_model = GradientBoostingClassifier(n_estimators=200, max_depth=3, learning_rate=0.08, random_state=seed)
        self.boundary_model.fit(self._xy([c for c, _ in boundary], self.boundary_features), [y for _, y in boundary],
                                sample_weight=boundary_weights)
        self.duel_model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.08, random_state=seed)
        self.duel_model.fit(self._xy([c for c, _ in duel], self.duel_features), [y for _, y in duel], sample_weight=duel_weights)
        self.info = {"boundary_examples": len(boundary), "duel_examples": len(duel),
                     "boundary_labels": dict(sorted(_count(y for _, y in boundary).items())),
                     "duel_labels": dict(sorted(_count(y for _, y in duel).items()))}
        return self

    def classify(self, cands: list[Candidate], kind: str) -> list[tuple[str, float]]:
        if not cands:
            return []
        model, names = (self.boundary_model, self.boundary_features) if kind == "boundary" else (self.duel_model, self.duel_features)
        proba = model.predict_proba(self._xy(cands, names))
        classes = list(model.classes_)
        return [(classes[int(np.argmax(p))], float(np.max(p))) for p in proba]

    def save(self, models_dir: Path | str) -> Path:
        import joblib

        path = Path(models_dir) / MODEL_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        (Path(models_dir) / "event_spotter.json").write_text(json.dumps(self.info, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, models_dir: Path | str) -> EventSpotter:
        import joblib

        path = Path(models_dir) / MODEL_FILE
        if not path.exists():
            raise FileNotFoundError(f"no event model at {path}; train one with python -m regista.vision train-events")
        return joblib.load(path)


def _count(items) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for x in items:
        out[x] += 1
    return out


# ---------------------------------------------------------------------------- spotting: candidates -> event records

def spot_events(pos: Positions, possessions: list[Record], match: Record, spotter: EventSpotter, match_id: str) -> list[Record]:
    """``event`` records for one match from the vision layer's positions and possessions."""
    team_ids = [t["team_id"] for t in match["teams"]]
    gk_ids = {p["player_id"] for p in match["players"] if p.get("position") == "GK"}
    signs = attack_signs(pos, match.get("periods") or [], team_ids)
    poss = sorted(possessions, key=lambda r: r["t"])
    out: list[Record] = []

    def add(event_type: str, t: float, player: str | None, team: str | None, conf: float, **kw: Any) -> None:
        rec: Record = {"type": "event", "id": f"ev_v{len(out) + 1:06d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
                       "source": "vision", "confidence": round(min(1.0, max(0.0, conf)), 3), "t": round(t, 3), "event_type": event_type,
                       "player_id": player, "team_id": team, "related_player_id": kw.pop("related", None),
                       "possession_id": kw.pop("possession_id", None), "segment_id": pos.segment(t), "outcome": kw.pop("outcome", "success")}
        for k, v in kw.items():
            if v is not None:
                rec[k] = v
        out.append(rec)

    duels = duel_candidates(poss, pos, signs)
    take_on_times: dict[str, list[float]] = defaultdict(list)
    for c, (label, conf) in zip(duels, spotter.classify(duels, "duel")):
        if label == "none":
            continue
        take_on_times[c.context["p"]["id"]].append(c.t)
        quals = ["nutmeg"] if label == "nutmeg" else None
        add("take_on", c.t, c.player_id, c.team_id, conf, related=c.related_id, possession_id=c.context["p"]["id"],
            pitch=_pt(c.context["where"]), qualifiers=quals, under_pressure=True)
        if label == "nutmeg":
            add("nutmeg", c.t, c.player_id, c.team_id, conf, related=c.related_id, possession_id=c.context["p"]["id"],
                pitch=_pt(c.context["where"]), qualifiers=["nutmeg"], under_pressure=True)

    for p, t0, t1, a, b, metres in carry_spans(poss, pos, take_on_times):
        add("carry", t0, p["player_id"], p["team_id"], 0.8, possession_id=p["id"], t_end=round(t1, 3), pitch=_pt(a), pitch_end=_pt(b),
            metrics={"carry_distance_m": round(metres, 2)})

    bounds = boundary_candidates(poss, pos, signs, gk_ids)
    for c, (label, conf) in zip(bounds, spotter.classify(bounds, "boundary")):
        if label == "none":
            continue
        p, q, f = c.context["p"], c.context["q"], c.features
        if label in ("pass", "cross"):
            add(label, c.t, c.player_id, c.team_id, conf, related=c.related_id, possession_id=p["id"], pitch=_pt(c.context["b0"]),
                pitch_end=_pt(pos.player(q["player_id"], float(q["t"])) if q else c.context["b1"]),
                metrics={"pass_distance_m": round(min(f["pass_dist"], 120.0), 2)} if f["pass_dist"] < 99 else None)
        elif label == "interception":
            add("pass", c.t, c.player_id, c.team_id, conf, related=None, possession_id=p["id"], pitch=_pt(c.context["b0"]), outcome="fail")
            add("interception", float(q["t"]), q["player_id"], q["team_id"], conf, related=c.player_id, possession_id=q["id"],
                pitch=_pt(pos.player(q["player_id"], float(q["t"]))))
        elif label == "tackle":
            add("tackle", c.t, q["player_id"], q["team_id"], conf, related=c.player_id, possession_id=q["id"],
                pitch=_pt(pos.player(q["player_id"], c.t)))
        elif label == "shot":
            in_mouth = f["closest_goal_dy"] <= GOAL_HALF_WIDTH + 0.5 and f["closest_goal_dx"] <= 1.5
            restart_from_centre = q is not None and q["team_id"] != c.team_id and f["gap_s"] >= 8.0 and \
                _d(pos.player(q["player_id"], float(q["t"])), (PITCH_L / 2, PITCH_W / 2)) <= 6.0
            saved = bool(f["q_is_opp_gk"]) and f["gap_s"] <= 3.0
            scored = in_mouth and not saved and (q is None or restart_from_centre)
            add("shot", c.t, c.player_id, c.team_id, conf, possession_id=p["id"], pitch=_pt(c.context["b0"]),
                pitch_end=_pt(c.context["closest"]), outcome="success" if scored else "fail",
                qualifiers=["goal" if scored else "saved" if saved else "off_target" if not in_mouth else "unknown"],
                metrics={"shot_distance_m": round(f["start_goal_dist"], 2)} if f["start_goal_dist"] < 99 else None)
            if saved:
                add("save", float(q["t"]), q["player_id"], q["team_id"], conf, related=c.player_id, possession_id=q["id"],
                    pitch=_pt(pos.player(q["player_id"], float(q["t"]))))
            if scored:
                add("goal", c.t + 0.5, c.player_id, c.team_id, conf, pitch=_pt(c.context["b0"]), pitch_end=_pt(c.context["closest"]))
    out.sort(key=lambda r: (r["t"], r["id"]))
    for i, r in enumerate(out, start=1):
        r["id"] = f"ev_v{i:06d}"
    return out


def _pt(p: tuple[float, float] | None) -> dict[str, float] | None:
    if p is None:
        return None
    return {"x": round(min(PITCH_L, max(0.0, p[0])), 2), "y": round(min(PITCH_W, max(0.0, p[1])), 2)}


# ---------------------------------------------------------------------------- training and evaluation on rendered matches

def examples(pos: Positions, possessions: list[Record], match: Record, truth_events: list[Record]):
    """Labelled candidates for one match: (boundary [(candidate, label)], duel [(candidate, label)])."""
    team_ids = [t["team_id"] for t in match["teams"]]
    gk_ids = {p["player_id"] for p in match["players"] if p.get("position") == "GK"}
    signs = attack_signs(pos, match.get("periods") or [], team_ids)
    truth = _truth_index(truth_events)
    poss = sorted(possessions, key=lambda r: r["t"])
    b = [(c, label_boundary(c, truth)) for c in boundary_candidates(poss, pos, signs, gk_ids)]
    d = [(c, label_duel(c, truth)) for c in duel_candidates(poss, pos, signs)]
    return b, d


SCORED_TYPES = ["pass", "cross", "shot", "goal", "save", "tackle", "interception", "take_on", "nutmeg", "carry"]


def evaluate_events(pred: list[Record], truth_events: list[Record], main_segments: list[Record],
                    tol: float = MATCH_TOLERANCE_S) -> dict[str, dict[str, Any]]:
    """Per event type: precision and recall against the generator's events that happened in main-camera footage.

    A prediction matches a true event of the same type within ``tol`` seconds; ``player_ok`` is the share of matches
    that also name the right player. Only successful take-ons and passes/crosses count as truth (the rest are
    scored as their outcome events: tackles and interceptions)."""
    def in_main(t: float) -> bool:
        return any(s["t"] <= t < s["t_end"] for s in main_segments)

    def truth_of(kind: str) -> list[Record]:
        evs = [e for e in truth_events if e.get("type") == "event" and e["event_type"] == kind and in_main(float(e["t"]))]
        if kind in ("pass", "cross", "take_on"):
            evs = [e for e in evs if e.get("outcome") == "success"]
        return evs

    report: dict[str, dict[str, Any]] = {}
    for kind in SCORED_TYPES:
        tr = truth_of(kind)
        pr = [e for e in pred if e["event_type"] == kind and (kind not in ("pass", "cross") or e.get("outcome") == "success")]
        used = [False] * len(tr)
        hit, player_ok = 0, 0
        for e in sorted(pr, key=lambda r: -r["confidence"]):
            best, bdt = None, None
            for j, g in enumerate(tr):
                if used[j]:
                    continue
                dt = abs(float(g["t"]) - float(e["t"]))
                if kind == "carry":  # a carry is a span: overlap counts
                    dt = 0.0 if (float(e["t"]) < float(g.get("t_end", g["t"])) + tol and float(g["t"]) < float(e.get("t_end", e["t"])) + tol) else 9.0
                if dt <= tol and (bdt is None or dt < bdt):
                    best, bdt = j, dt
            if best is not None:
                used[best] = True
                hit += 1
                player_ok += int(tr[best].get("player_id") == e.get("player_id"))
        report[kind] = {"true": len(tr), "predicted": len(pr), "matched": hit,
                        "precision": round(hit / len(pr), 3) if pr else None, "recall": round(hit / len(tr), 3) if tr else None,
                        "player_ok": round(player_ok / hit, 3) if hit else None}
    return report


def merge_reports(reports: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    out = {}
    for kind in SCORED_TYPES:
        t = sum(r[kind]["true"] for r in reports)
        p = sum(r[kind]["predicted"] for r in reports)
        m = sum(r[kind]["matched"] for r in reports)
        ok = sum((r[kind]["player_ok"] or 0) * r[kind]["matched"] for r in reports)
        out[kind] = {"true": t, "predicted": p, "matched": m, "precision": round(m / p, 3) if p else None,
                     "recall": round(m / t, 3) if t else None, "player_ok": round(ok / m, 3) if m else None}
    return out


# ---------------------------------------------------------------------------- reproducible training and scoring (python -m regista.vision ...)

EVENTS_ROOT = Path("/tmp/regista_events")
EVENT_DATA = {"track_hz": 10.0, "captions": False}  # event-spotting footage: positions at 10 Hz, no on-screen captions
GENERATED_SEEDS = list(range(1001, 1061))           # 60 matches that are only generated, never rendered


def event_dataset(specs, root: Path | str = EVENTS_ROOT, models_dir: Path | str = "models/vision") -> list[dict[str, Any]]:
    """Render ``specs`` for event spotting and run the identity stage on true camera segments (cached under ``root``)."""
    import joblib

    from regista.vision.dataset import make_match
    from regista.vision.frames import probe
    from regista.vision.identity import IdentityConfig, run_identity
    from regista.vision.kitnumber import DigitClassifierReader
    from regista.vision.truth import Truth, load_match_header

    items = []
    for spec in specs:
        it = make_match(spec, root, **EVENT_DATA)
        path = Path(root) / "identity" / f"{spec.match_id}.joblib"
        if not path.exists():
            info = probe(it["video"])
            segs = Truth(it["match_dir"], info.width, info.height).segments(info.duration_s)
            res = run_identity(it["video"], load_match_header(it["match_dir"]), segs, DigitClassifierReader.load(models_dir),
                               IdentityConfig.load(models_dir))
            path.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(res, path)
        items.append({**it, "identity": str(path)})
    return items


def _vision_inputs(item: dict[str, Any]):
    import joblib

    from regista.schema import iter_jsonl
    from regista.vision.possession import infer_possessions
    from regista.vision.truth import load_match_header

    res = joblib.load(item["identity"])
    header = load_match_header(item["match_dir"])
    stream = list(iter_jsonl(Path(item["match_dir"]) / "events.jsonl"))
    segs = [r for r in stream if r["type"] == "camera_segment"]
    poss = infer_possessions(res.frames, header, header["match_id"], fps=res.info.get("sample_fps", 5.0),
                             segment_end={s["id"]: s["t_end"] for s in segs})
    return Positions.from_identity(res), poss, header, stream, [s for s in segs if s["kind"] == "main"]


VISION_WEIGHT = 3.0  # an example from real vision output counts this many generated ones (generated positions are cleaner)


def train_event_spotter(train_items: list[dict[str, Any]], models_dir: Path | str, generated_seeds: list[int] = GENERATED_SEEDS) -> EventSpotter:
    """Fit on vision output of the rendered training matches plus vision-shaped generated matches; save to ``models_dir``.

    Generated matches supply volume (rare events such as nutmegs); vision output supplies how events really measure
    through the camera (the vision layer reads a ball crossing a defender as further from him than it is), so its
    examples weigh more."""
    B, D = generated_example_set(generated_seeds)
    n_gen = (len(B), len(D))
    for it in train_items:
        pos, poss, header, stream, _main = _vision_inputs(it)
        b, d = examples(pos, poss, header, stream)
        B += b
        D += d
    bw = [1.0] * n_gen[0] + [VISION_WEIGHT] * (len(B) - n_gen[0])
    dw = [1.0] * n_gen[1] + [VISION_WEIGHT] * (len(D) - n_gen[1])
    spotter = EventSpotter().fit(B, D, boundary_weights=bw, duel_weights=dw)
    spotter.info.update(rendered_matches=[Path(i["match_dir"]).name for i in train_items], generated_matches=len(generated_seeds),
                        generated_examples={"boundary": n_gen[0], "duel": n_gen[1]}, vision_weight=VISION_WEIGHT)
    spotter.save(models_dir)
    return spotter


def score_event_spotter(items: list[dict[str, Any]], spotter: EventSpotter) -> dict[str, Any]:
    """Event spotting on its own: identity on true camera segments, then possessions and events, scored per type."""
    per_match = {}
    for it in items:
        pos, poss, header, stream, main = _vision_inputs(it)
        per_match[header["match_id"]] = evaluate_events(spot_events(pos, poss, header, spotter, header["match_id"]), stream, main)
    return {"matches": sorted(per_match), "all": merge_reports(list(per_match.values())), "per_match": per_match}
