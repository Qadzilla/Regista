"""Identity agent: who is where, in every main-camera frame, plus who appears in each cutaway.

For each sampled main-camera frame: calibrate the camera (``pitch``), detect discs and the ball
(``detect``), read kit numbers (``kitnumber``), and map ground contact points to pitch metres.
A tracker links detections over time inside each camera segment (Hungarian assignment on pitch
distance, gated by team and goalkeeper kit), and each track is named by a vote: the summed
log-probability of every number on that team's sheet across the track's readings. A player can
only be one track at a time, so conflicting tracks are resolved greedily by vote margin. The
ball's number-covering habit (it is drawn at the holder's feet) is why identity comes from the
track, not the frame: continuity carries the name through the touches where the number is hidden.

Cutaways: replays and highlights are other camera angles of earlier play, so there is no pitch
mapping; discs are tracked in image space, named the same way, and a player "appears" in the
replay when their disc stays close to the ball for a good part of it (the generator's ground
truth lists the players involved in the replayed event, which is what this approximates).
Closeups are one or two big player cards, read directly.

Outputs: ``track`` and ``appearance`` records (``source: vision``) plus per-frame observations
(ball and named players in pitch metres) for the possession agent.

Real footage: the stages keep their interfaces. ``DiscDetector`` becomes a person detector,
``DigitClassifierReader`` becomes OCR on torso crops (Azure AI Vision, or a fine-tuned local model),
``MainCameraCalibrator`` becomes a homography estimator, and the tracker gains appearance
features (re-identification embeddings) because real players cross and occlude each other far
more than discs do. Faces are never used (see CLAUDE.md section 1.5).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from regista.schema import SCHEMA_VERSION
from regista.vision.detect import Detection, DiscDetector, KitPalette, detect_closeup
from regista.vision.frames import iter_frames, probe
from regista.vision.kitnumber import KitNumberReader, NumberReading, crop_disc
from regista.vision.pitch import MainCameraCalibrator, clamp_pitch

Record = dict[str, Any]
PITCH_KINDS = ("main",)
IDENTITY_CONFIG_FILE = "identity_config.json"
CUTAWAY_PITCH_KINDS = ("replay", "highlight")


@dataclass
class IdentityConfig:
    sample_fps: float = 5.0          # main-camera frames analysed per second
    cutaway_fps: float = 4.0         # replay/highlight/closeup frames analysed per second
    gate_m: float = 3.0              # max pitch distance between consecutive detections of one track
    gate_px_r: float = 2.5           # same, in disc radii, for cutaways (no pitch mapping)
    max_missed_s: float = 1.2        # a track survives this long without a detection
    min_track_obs: int = 2
    near_ball_r: float = 3.0         # cutaway involvement: "near the ball" = feet within this many disc radii of it
    on_ball_r: float = 1.6           # "on the ball" = the nearest player, feet within this many radii
    involved_on: float = 0.15        # involved when on the ball for this fraction of the segment's frames...
    involved_near: float = 0.45      # ...or near it for this fraction (tuned on training matches: tune_cutaway)
    adapt_frames: int = 24

    def save(self, models_dir: Path | str) -> Path:
        import json

        path = Path(models_dir) / IDENTITY_CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, indent=2) + "\n", encoding="utf-8")
        return path

    @classmethod
    def load(cls, models_dir: Path | str) -> IdentityConfig:
        """Defaults, overridden by the thresholds ``train`` tuned and saved next to the models (if any)."""
        import json

        path = Path(models_dir) / IDENTITY_CONFIG_FILE
        cfg = cls()
        if path.exists():
            for k, v in json.loads(path.read_text(encoding="utf-8")).items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        return cfg


# ---------------------------------------------------------------------------- roster helpers

BENCH_LOG_PRIOR = -5.0  # substitutes are on the sheet but usually not on the pitch


def team_numbers(match: Record) -> dict[tuple[str, bool], list[tuple[int, str]]]:
    """(team_id, is_gk) -> [(kit_number, player_id)] from the team sheet (starters and bench)."""
    out: dict[tuple[str, bool], list[tuple[int, str]]] = defaultdict(list)
    for p in match["players"]:
        out[(p["team_id"], p["position"] == "GK")].append((int(p["kit_number"]), p["player_id"]))
    return out


def lineup_prior(match: Record) -> dict[str, float]:
    """Log prior per player: 0 for starters, BENCH_LOG_PRIOR for substitutes (the ``lineup_prior`` evidence)."""
    return {p["player_id"]: (0.0 if p.get("starter", True) else BENCH_LOG_PRIOR) for p in match["players"]}


def adapt_palette(video: Path | str, match: Record, segments: list[Record], n_frames: int = 24) -> KitPalette:
    """Palette from the match header, re-estimated on frames sampled across the main-camera segments."""
    pal = KitPalette.from_match(match)
    main = [s for s in segments if s["kind"] == "main"]
    total = sum(s["t_end"] - s["t"] for s in main)
    if total <= 0:
        return pal
    every = max(total / n_frames, 0.5)
    frames = []
    for _i, t, rgb in iter_frames(video, sample_fps=1.0 / every):
        if any(s["t"] <= t < s["t_end"] for s in main):
            frames.append(rgb)
    if frames:
        h = frames[0].shape[0]
        pal.adapt(frames, (int(0.1 * h), int(0.9 * h)))
    return pal


def segment_at(segments: list[Record], t: float) -> Record | None:
    for s in segments:
        if s["t"] <= t < s["t_end"]:
            return s
    return None


# ---------------------------------------------------------------------------- tracker

@dataclass
class Track:
    tid: int
    team_id: str
    is_gk: bool
    obs: list[dict[str, Any]] = field(default_factory=list)
    missed: int = 0
    player_id: str | None = None
    id_conf: float = 0.0
    votes: dict[str, float] = field(default_factory=dict)

    @property
    def t0(self) -> float:
        return self.obs[0]["t"]

    @property
    def t1(self) -> float:
        return self.obs[-1]["t"]


class Tracker:
    """Frame-to-frame association inside one camera segment. ``space`` is "pitch" (metres) or "image" (radii)."""

    def __init__(self, space: str, gate: float, max_missed: int):
        self.space = space
        self.gate = gate
        self.max_missed = max_missed
        self.active: list[Track] = []
        self.done: list[Track] = []
        self._next = 0

    def _pos(self, o: dict[str, Any]) -> np.ndarray:
        return np.array([o["x"], o["y"]]) if self.space == "pitch" else np.array([o["u"], o["v"]])

    def _predict(self, tr: Track) -> np.ndarray:
        """Constant-velocity guess for the next frame (one step ahead of the last observation)."""
        p = self._pos(tr.obs[-1])
        if len(tr.obs) >= 2 and tr.obs[-1]["t"] > tr.obs[-2]["t"]:
            p = p + (p - self._pos(tr.obs[-2]))
        return p

    def step(self, obs: list[dict[str, Any]]) -> None:
        from scipy.optimize import linear_sum_assignment

        if self.active and obs:
            D = np.full((len(self.active), len(obs)), 1e6)
            for i, tr in enumerate(self.active):
                pred = self._predict(tr)
                for j, o in enumerate(obs):
                    if o["team_id"] != tr.team_id or o["is_gk"] != tr.is_gk:
                        continue
                    d = float(np.linalg.norm(pred - self._pos(o)))
                    if self.space == "image":
                        d /= max(1.0, o["r"])
                    gate = self.gate * (1 + 0.5 * tr.missed)
                    if d <= gate:
                        D[i, j] = d
            ri, ci = linear_sum_assignment(D)
            pairs = [(i, j) for i, j in zip(ri, ci) if D[i, j] < 1e6]
        else:
            pairs = []
        used_t = {i for i, _ in pairs}
        used_o = {j for _, j in pairs}
        for i, j in pairs:
            self.active[i].obs.append(obs[j])
            self.active[i].missed = 0
        still = []
        for i, tr in enumerate(self.active):
            if i in used_t:
                still.append(tr)
                continue
            tr.missed += 1
            (still if tr.missed <= self.max_missed else self.done).append(tr)
        self.active = still
        for j, o in enumerate(obs):
            if j not in used_o:
                self.active.append(Track(self._next, o["team_id"], o["is_gk"], [o]))
                self._next += 1

    def finish(self) -> list[Track]:
        self.done += self.active
        self.active = []
        return self.done


def name_tracks(tracks: list[Track], match: Record, min_obs: int = 2) -> list[Track]:
    """Give each track a player_id by number vote over its team sheet; one player per moment."""
    sheet = team_numbers(match)
    prior = lineup_prior(match)
    scored: list[tuple[float, float, Track, list[tuple[str, float]]]] = []
    for tr in tracks:
        if len(tr.obs) < min_obs:
            continue
        cands = sheet.get((tr.team_id, tr.is_gk)) or sheet.get((tr.team_id, not tr.is_gk), [])
        if not cands:
            continue
        lp = np.zeros(len(cands))
        n_read = 0
        for o in tr.obs:
            rd = o.get("reading")
            if rd is None:
                continue
            w = o.get("read_weight", 1.0)
            lp += w * np.array([rd.number_logp(n) for n, _ in cands])
            n_read += 1
        if n_read == 0:
            continue
        lp = lp / max(1.0, np.sqrt(n_read))  # readings of one track are correlated; temper the vote
        lp = lp + np.array([prior.get(pid, 0.0) for _n, pid in cands])
        p = np.exp(lp - lp.max())
        p /= p.sum()
        order = np.argsort(-p)
        ranked = [(cands[k][1], float(p[k])) for k in order]
        tr.votes = {pid: round(pv, 4) for pid, pv in ranked[:3]}
        margin = ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0)
        scored.append((margin, len(tr.obs), tr, ranked))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    taken: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for _margin, _n, tr, ranked in scored:
        for pid, pv in ranked:
            if pv < 0.02:
                break
            if any(not (tr.t1 < a or tr.t0 > b) for a, b in taken[pid]):
                continue
            tr.player_id, tr.id_conf = pid, pv
            taken[pid].append((tr.t0, tr.t1))
            break
    return tracks


# ---------------------------------------------------------------------------- main-camera identity

@dataclass
class IdentityResult:
    frames: list[dict[str, Any]]            # per sampled main frame: t, frame, segment_id, cx, ball, players[]
    tracks: list[Track]
    cutaway: list[dict[str, Any]]           # per cutaway segment: players involved, with confidence
    info: dict[str, Any] = field(default_factory=dict)


def _read(reader: KitNumberReader, rgb: np.ndarray, dets: list[Detection], palette: KitPalette) -> list[NumberReading]:
    if not dets:
        return []
    crops = np.stack([crop_disc(rgb, d.u, d.v, d.r, palette.kits[d.kit].lab) for d in dets])
    return reader.read(crops)


def run_identity(video: Path | str, match: Record, segments: list[Record], reader: KitNumberReader,
                 cfg: IdentityConfig | None = None, palette: KitPalette | None = None) -> IdentityResult:
    """Detect, read, map, track and name players in every sampled main-camera frame, then handle cutaways."""
    cfg = cfg or IdentityConfig()
    info = probe(video)
    palette = palette or adapt_palette(video, match, segments, cfg.adapt_frames)
    cal = MainCameraCalibrator(info.width, info.height)
    det = DiscDetector(palette, info.width, info.height, cal.geom)
    max_missed = max(1, int(round(cfg.max_missed_s * cfg.sample_fps)))
    frames: list[dict[str, Any]] = []
    all_tracks: list[Track] = []
    trackers: dict[str, Tracker] = {}
    prev_ball: tuple[float, float] | None = None
    prev_cx: float | None = None
    last_seg: str | None = None
    for fi, t, rgb in iter_frames(video, sample_fps=cfg.sample_fps):
        seg = segment_at(segments, t)
        if seg is None or seg["kind"] not in PITCH_KINDS:
            continue
        sid = seg.get("id") or f"seg@{seg['t']}"
        if sid != last_seg:
            prev_ball, prev_cx = None, None
            last_seg = sid
        calib = cal.estimate(rgb, prior_cx=prev_cx)
        prev_cx = calib.cx
        mapping = calib.mapping
        players, ball = det.detect(rgb, prev_ball)
        prev_ball = (ball.u, ball.v) if ball else None
        readings = _read(reader, rgb, players, palette)
        obs = []
        for d, rd in zip(players, readings):
            x, y = clamp_pitch(*mapping.image_to_pitch(d.foot_u, d.foot_v))
            # A disc whose lower half is hidden (by the ball, usually) has its number hidden too.
            obs.append({"t": t, "frame": fi, "u": d.u, "v": d.v, "r": d.r, "x": x, "y": y, "team_id": d.team_id, "is_gk": d.is_gk,
                        "reading": rd, "read_weight": 0.3 if d.occluded_below else 1.0})
        tracker = trackers.setdefault(sid, Tracker("pitch", cfg.gate_m, max_missed))
        tracker.step(obs)
        bxy = None
        if ball is not None:
            bxy = clamp_pitch(*mapping.image_to_pitch(ball.foot_u, ball.foot_v))
        frames.append({"t": round(t, 3), "frame": fi, "segment_id": sid, "cx": round(calib.cx, 3),
                       "ball": None if ball is None else {"u": ball.u, "v": ball.v, "x": bxy[0], "y": bxy[1]}, "obs": obs})
    for tr in trackers.values():
        all_tracks += tr.finish()
    name_tracks(all_tracks, match, cfg.min_track_obs)
    # Resolve the per-frame player lists to named players.
    for tr in all_tracks:
        for o in tr.obs:
            o["track_id"] = tr.tid
            o["player_id"] = tr.player_id
            o["id_conf"] = tr.id_conf
    cut = cutaway_identity(video, match, segments, reader, palette, cfg)
    return IdentityResult(frames=frames, tracks=all_tracks, cutaway=cut,
                          info={"video": info.__dict__, "sample_fps": cfg.sample_fps, "palette_adapted": palette.adapted, "main_frames": len(frames),
                                "tracks": len(all_tracks), "named_tracks": sum(1 for t in all_tracks if t.player_id)})


# ---------------------------------------------------------------------------- cutaways

def cutaway_identity(video: Path | str, match: Record, segments: list[Record], reader: KitNumberReader, palette: KitPalette,
                     cfg: IdentityConfig) -> list[dict[str, Any]]:
    """Who appears in each replay, highlight and closeup segment."""
    info = probe(video)
    det = DiscDetector(palette, info.width, info.height, geom=None)
    nominal = KitPalette.from_match(match)
    sheet = team_numbers(match)
    wanted = [s for s in segments if s["kind"] in CUTAWAY_PITCH_KINDS + ("closeup",)]
    if not wanted:
        return []
    per_seg: dict[str, dict[str, Any]] = {}
    trackers: dict[str, Tracker] = {}
    max_missed = max(1, int(round(cfg.max_missed_s * cfg.cutaway_fps)))
    prev_ball: dict[str, tuple[float, float] | None] = {}
    for fi, t, rgb in iter_frames(video, sample_fps=cfg.cutaway_fps):
        seg = segment_at(wanted, t)
        if seg is None:
            continue
        sid = seg.get("id") or f"seg@{seg['t']}"
        st = per_seg.setdefault(sid, {"segment": seg, "frames": 0, "closeup": []})
        st["frames"] += 1
        if seg["kind"] == "closeup":
            # Big flat cards show the true kit colour; the adapted palette is tuned to small, blurred discs.
            dets = detect_closeup(rgb, nominal)
            for d, rd in zip(dets, _read(reader, rgb, dets, nominal)):
                st["closeup"].append((d.team_id, d.is_gk, rd))
            continue
        players, ball = det.detect(rgb, prev_ball.get(sid))
        prev_ball[sid] = (ball.u, ball.v) if ball else None
        readings = _read(reader, rgb, players, palette)
        dists = [np.hypot(d.foot_u - ball.foot_u, d.foot_v - ball.foot_v) / d.r if ball is not None else 1e9 for d in players]
        nearest = int(np.argmin(dists)) if dists else -1
        obs = []
        for j, (d, rd) in enumerate(zip(players, readings)):
            obs.append({"t": t, "frame": fi, "u": d.u, "v": d.v, "r": d.r, "team_id": d.team_id, "is_gk": d.is_gk, "reading": rd,
                        "read_weight": 0.3 if d.occluded_below else 1.0, "near_ball": bool(dists[j] <= cfg.near_ball_r),
                        "on_ball": bool(j == nearest and dists[j] <= cfg.on_ball_r)})
        trackers.setdefault(sid, Tracker("image", cfg.gate_px_r, max_missed)).step(obs)
    prior = lineup_prior(match)
    out = []
    for sid, st in per_seg.items():
        seg = st["segment"]
        cands: dict[str, dict[str, float]] = {}
        if seg["kind"] == "closeup":
            votes: dict[tuple[str, bool], list[NumberReading]] = defaultdict(list)
            for team_id, is_gk, rd in st["closeup"]:
                votes[(team_id, is_gk)].append(rd)
            for key, rds in votes.items():
                sheet_c = sheet.get(key, [])
                if not sheet_c:
                    continue
                lp = np.sum([[rd.number_logp(n) for n, _ in sheet_c] for rd in rds], axis=0)
                lp = lp + np.array([prior.get(pid, 0.0) for _n, pid in sheet_c])
                p = np.exp(lp - lp.max())
                p /= p.sum()
                k = int(p.argmax())
                cands[sheet_c[k][1]] = {"id_conf": float(p[k]), "frac": len(rds) / max(1, st["frames"]), "near": 1.0, "on": 1.0}
        else:
            tracks = name_tracks(trackers[sid].finish() if sid in trackers else [], match, 1)
            n = max(1, st["frames"])
            for tr in tracks:
                if not tr.player_id:
                    continue
                c = cands.setdefault(tr.player_id, {"id_conf": 0.0, "frac": 0.0, "near": 0.0, "on": 0.0})
                c["id_conf"] = max(c["id_conf"], tr.id_conf)
                c["frac"] += len(tr.obs) / n
                c["near"] += sum(1 for o in tr.obs if o["near_ball"]) / n
                c["on"] += sum(1 for o in tr.obs if o["on_ball"]) / n
        out.append({"segment_id": sid, "kind": seg["kind"], "t": seg["t"], "t_end": seg["t_end"], "frames": st["frames"],
                    "candidates": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in cands.items()},
                    "players": select_involved(seg["kind"], cands, cfg)})
    return out


def select_involved(kind: str, cands: dict[str, dict[str, float]], cfg: IdentityConfig) -> dict[str, float]:
    """Players who appear in a cutaway, with confidence: closeup cards present for 40% of the shot; in replays and
    highlights, players on the ball or near it for long enough."""
    out = {}
    for pid, c in cands.items():
        if kind == "closeup":
            ok = c["frac"] >= 0.4
        else:
            ok = c["on"] >= cfg.involved_on or c["near"] >= cfg.involved_near
        if ok:
            out[pid] = round(float(min(1.0, c["id_conf"])), 3)
    return out


# ---------------------------------------------------------------------------- records

def _bbox(o: dict[str, Any], w: int, h: int) -> dict[str, float]:
    r = o["r"]
    x0, y0 = max(0.0, (o["u"] - r) / w), max(0.0, (o["v"] - r) / h)
    return {"x": round(min(1.0, x0), 4), "y": round(min(1.0, y0), 4), "w": round(min(1.0 - min(1.0, x0), 2 * r / w), 4),
            "h": round(min(1.0 - min(1.0, y0), 2 * r / h), 4)}


def track_records(result: IdentityResult, match_id: str, fps: float, track_hz: float = 2.0) -> list[Record]:
    """Schema-valid ``track`` records for players (named or not) and the ball, sampled at ``track_hz``."""
    w, h = result.info["video"]["width"], result.info["video"]["height"]
    out: list[Record] = []
    n = 0
    next_t: dict[str, float] = {}
    step = 1.0 / track_hz
    for fr in result.frames:
        t = fr["t"]
        key = fr["segment_id"]
        if t + 1e-6 < next_t.get(key, -1.0):
            continue
        next_t[key] = t + step - 1e-6
        for o in fr["obs"]:
            n += 1
            ev = ["team_colour", "continuity"]
            if o.get("player_id"):
                ev = ["kit_number", "team_colour", "continuity", "lineup_prior"]
            rec = {"type": "track", "id": f"tr_v{n:07d}", "match_id": match_id, "schema_version": SCHEMA_VERSION, "source": "vision",
                   "confidence": round(float(o.get("id_conf") or 0.5), 3), "t": float(t), "frame": int(fr["frame"]),
                   "segment_id": key, "object": "player", "track_id": f"{key}:v{o.get('track_id', 'x')}",
                   "player_id": o.get("player_id"), "team_id": o["team_id"],
                   "pitch": {"x": round(o["x"], 2), "y": round(o["y"], 2)}, "bbox": _bbox(o, w, h),
                   "identity": {"confidence": round(float(o.get("id_conf") or 0.0), 3), "evidence": ev}}
            out.append(rec)
        b = fr.get("ball")
        if b is not None:
            n += 1
            out.append({"type": "track", "id": f"tr_v{n:07d}", "match_id": match_id, "schema_version": SCHEMA_VERSION, "source": "vision",
                        "confidence": 0.9, "t": float(t), "frame": int(fr["frame"]), "segment_id": key, "object": "ball",
                        "track_id": f"{key}:ball", "player_id": None, "team_id": None,
                        "pitch": {"x": round(b["x"], 2), "y": round(b["y"], 2)},
                        "bbox": _bbox({"u": b["u"], "v": b["v"], "r": 3.0 * w / 640}, w, h)})
    return out


def appearance_records(result: IdentityResult, possessions: list[Record], match_id: str, gap_s: float = 1.0,
                       segment_end: dict[str, float] | None = None) -> list[Record]:
    """``appearance`` records: runs of a named player in a main segment, and every cutaway involvement.

    ``segment_end`` (segment id -> end time) clamps a run so it never outlasts its shot."""
    segment_end = segment_end or {}
    w, h = result.info["video"]["width"], result.info["video"]["height"]
    runs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for fr in result.frames:
        for o in fr["obs"]:
            if o.get("player_id"):
                runs[(fr["segment_id"], o["player_id"])].append(o)
    out: list[Record] = []
    n = 0
    dt = 1.0 / max(1e-6, result.info.get("sample_fps", 5.0))
    for (sid, pid), obs in runs.items():
        obs.sort(key=lambda o: o["t"])
        chunk: list[dict[str, Any]] = []
        for o in obs + [None]:
            if o is not None and (not chunk or o["t"] - chunk[-1]["t"] <= gap_s):
                chunk.append(o)
                continue
            if chunk:
                t0, t1 = chunk[0]["t"], min(chunk[-1]["t"] + dt, segment_end.get(sid, float("inf")))
                area = float(np.mean([(2 * c["r"] / w) * (2 * c["r"] / h) for c in chunk]))
                on_ball = any(p["player_id"] == pid and p["t"] < t1 and t0 < p["t_end"] for p in possessions)
                n += 1
                out.append({"type": "appearance", "id": f"ap_v{n:06d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
                            "source": "vision", "confidence": round(float(np.mean([c.get("id_conf") or 0 for c in chunk])), 3),
                            "t": round(t0, 3), "t_end": round(t1, 3), "segment_id": sid, "player_id": pid, "on_ball": on_ball,
                            "prominence": round(float(np.clip(area / 0.3, 0, 1)), 3)})
            chunk = [o] if o is not None else []
    for c in result.cutaway:
        for pid, conf in c["players"].items():
            n += 1
            on_ball = any(p["player_id"] == pid and p["t"] < c["t_end"] and c["t"] < p["t_end"] for p in possessions)
            out.append({"type": "appearance", "id": f"ap_v{n:06d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
                        "source": "vision", "confidence": round(float(conf), 3), "t": float(c["t"]), "t_end": float(c["t_end"]),
                        "segment_id": c["segment_id"], "player_id": pid, "on_ball": on_ball,
                        "prominence": 0.6 if c["kind"] == "closeup" else 0.2})
    out.sort(key=lambda r: (r["t"], r["id"]))
    return out
