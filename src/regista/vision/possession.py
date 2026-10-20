"""Possession agent: who is on the ball, from ball and player positions over time.

Input: the identity agent's per-frame observations in main-camera segments (ball and named
players in pitch metres). For each frame the candidate holder is the player whose ground point
is nearest the ball, if within ``on_ball_m``. The per-frame sequence is mode-filtered over
``smooth_s`` (a ball rolling past a player for one frame is not a possession), short gaps where
the ball was not detected are bridged, and runs shorter than ``min_s`` are dropped. Each run
becomes a ``possession`` record.

What vision cannot see directly is filled in conservatively: ``gained_by``/``lost_by`` are
``pass_received``/``pass`` when the previous/next possession is a team-mate's within a few
seconds, ``unknown`` otherwise; ``touches`` is an estimate from duration (one touch per
``touch_every_s``); ``under_pressure`` means an opponent within ``pressure_m`` for most of the run.

Real footage: the logic is unchanged, but the inputs get noisier (ball 3-10 px, often occluded or
in the air), so the upgrade path is a learned possession model over short windows of tracked
positions (and ball height), trained on human-labelled possessions with this module's rule as the
baseline. Possessions in replays are never created: replays are mapped back to live time instead.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from regista.schema import SCHEMA_VERSION

Record = dict[str, Any]


@dataclass
class PossessionConfig:
    on_ball_m: float = 1.3
    smooth_s: float = 0.6
    bridge_s: float = 0.6
    min_s: float = 0.4
    pass_gap_s: float = 4.0
    touch_every_s: float = 0.9
    pressure_m: float = 2.5


def holder_sequence(frames: list[dict[str, Any]], cfg: PossessionConfig) -> list[tuple[float, str | None, str | None, bool]]:
    """Per frame: (t, player_id or None, segment_id, ball seen). None when nobody is close enough or the ball is unseen."""
    out = []
    for fr in frames:
        b = fr.get("ball")
        pid = None
        if b is not None:
            best, bd = None, cfg.on_ball_m
            for o in fr["obs"]:
                if not o.get("player_id"):
                    continue
                d = float(np.hypot(o["x"] - b["x"], o["y"] - b["y"]))
                if d <= bd:
                    best, bd = o["player_id"], d
            pid = best
        out.append((fr["t"], pid, fr["segment_id"], b is not None))
    return out


def infer_possessions(frames: list[dict[str, Any]], match: Record, match_id: str, cfg: PossessionConfig | None = None,
                      fps: float = 5.0, segment_end: dict[str, float] | None = None) -> list[Record]:
    """``possession`` records from per-frame holders. ``segment_end`` (segment id -> end time) keeps a possession
    from running past the cut that ends its shot."""
    cfg = cfg or PossessionConfig()
    segment_end = segment_end or {}
    team_of = {p["player_id"]: p["team_id"] for p in match["players"]}
    seq = holder_sequence(frames, cfg)
    if not seq:
        return []
    dt = 1.0 / fps
    k = max(0, int(round(cfg.smooth_s * fps / 2)))
    labels = [s[1] for s in seq]
    smoothed = []
    for i, (t, pid, sid, seen) in enumerate(seq):
        win = [labels[j] for j in range(max(0, i - k), min(len(seq), i + k + 1)) if seq[j][2] == sid]
        c = Counter(win).most_common()
        top = c[0][0]
        # Ties go to the frame's own label so short possessions keep their edges.
        if len(c) > 1 and c[0][1] == c[1][1]:
            top = pid
        smoothed.append(top)
    # Runs per segment, bridging short gaps of "nobody" between frames of the same holder.
    runs: list[dict[str, Any]] = []
    for i, (t, _pid, sid, _seen) in enumerate(seq):
        p = smoothed[i]
        if p is None:
            continue
        last = runs[-1] if runs else None
        if last and last["player_id"] == p and last["segment_id"] == sid and t - last["t_last"] <= cfg.bridge_s + 1e-6:
            last["t_last"] = t
            last["idx"].append(i)
        else:
            runs.append({"player_id": p, "segment_id": sid, "t": t, "t_last": t, "idx": [i]})
    runs = [r for r in runs if (r["t_last"] - r["t"] + dt) >= cfg.min_s]
    recs: list[Record] = []
    by_idx = {i: fr for i, fr in enumerate(frames)}
    for n, r in enumerate(runs, start=1):
        pid = r["player_id"]
        team = team_of.get(pid, "unknown")
        t0, t1 = r["t"], min(r["t_last"] + dt, segment_end.get(r["segment_id"], float("inf")))
        prev = runs[n - 2] if n >= 2 else None
        nxt = runs[n] if n < len(runs) else None
        gained = "pass_received" if prev and team_of.get(prev["player_id"]) == team and t0 - (prev["t_last"] + dt) <= cfg.pass_gap_s else "unknown"
        lost = "pass" if nxt and team_of.get(nxt["player_id"]) == team and nxt["t"] - t1 <= cfg.pass_gap_s else "unknown"
        balls = [by_idx[i]["ball"] for i in r["idx"] if by_idx[i].get("ball")]
        pressure = 0
        for i in r["idx"]:
            fr = by_idx[i]
            me = next((o for o in fr["obs"] if o.get("player_id") == pid), None)
            if me is None:
                continue
            if any(o["team_id"] != team and np.hypot(o["x"] - me["x"], o["y"] - me["y"]) <= cfg.pressure_m for o in fr["obs"]):
                pressure += 1
        conf = float(np.mean([o.get("id_conf") or 0.5 for i in r["idx"] for o in by_idx[i]["obs"] if o.get("player_id") == pid] or [0.5]))
        rec: Record = {"type": "possession", "id": f"po_v{n:06d}", "match_id": match_id, "schema_version": SCHEMA_VERSION,
                       "source": "vision", "confidence": round(min(1.0, conf * min(1.0, len(r["idx"]) / 3.0)), 3),
                       "t": round(t0, 3), "t_end": round(t1, 3), "player_id": pid, "team_id": team, "gained_by": gained,
                       "lost_by": lost, "touches": max(1, int(round((t1 - t0) / cfg.touch_every_s))),
                       "under_pressure": bool(pressure > 0.5 * len(r["idx"]))}
        if balls:
            rec["pitch"] = {"x": round(balls[0]["x"], 2), "y": round(balls[0]["y"], 2)}
            rec["pitch_end"] = {"x": round(balls[-1]["x"], 2), "y": round(balls[-1]["y"], 2)}
        recs.append(rec)
    return recs


# ---------------------------------------------------------------------------- evaluation

def _iou(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def evaluate_possessions(pred: list[Record], truth: list[Record], main_segments: list[Record], frame_times: list[float]) -> dict[str, Any]:
    """Compare with ground-truth possessions inside main-camera segments.

    - frame accuracy: at each analysed frame, predicted holder (or nobody) equals the true holder (or nobody)
    - window recall/precision: a true possession is found when a predicted one of the same player overlaps it
      with time IoU >= 0.5; mean IoU of each true possession's best same-player match
    - player-id accuracy: of true possessions overlapped by any predicted window, the share whose
      most-overlapping predicted window names the right player"""
    def in_main(t: float) -> bool:
        return any(s["t"] <= t < s["t_end"] for s in main_segments)

    truth = [p for p in truth if in_main(p["t"]) or in_main(min(p["t_end"] - 1e-3, p["t"] + 0.05))]

    def holder(ps: list[Record], t: float) -> str | None:
        for p in ps:
            if p["t"] <= t < p["t_end"]:
                return p["player_id"]
        return None

    agree = both = tp_f = fp_f = fn_f = 0
    for t in frame_times:
        a, b = holder(pred, t), holder(truth, t)
        agree += int(a == b)
        both += 1
        if a is not None and b is not None and a == b:
            tp_f += 1
        else:
            fp_f += int(a is not None)
            fn_f += int(b is not None)
    found = 0
    ious, id_ok, overl = [], 0, 0
    for g in truth:
        same = [_iou((g["t"], g["t_end"]), (p["t"], p["t_end"])) for p in pred if p["player_id"] == g["player_id"]]
        best = max(same, default=0.0)
        ious.append(best)
        found += int(best >= 0.5)
        ov = [(min(g["t_end"], p["t_end"]) - max(g["t"], p["t"]), p) for p in pred]
        ov = [x for x in ov if x[0] > 0]
        if ov:
            overl += 1
            id_ok += int(max(ov, key=lambda x: x[0])[1]["player_id"] == g["player_id"])
    matched_pred = sum(1 for p in pred if any(g["player_id"] == p["player_id"] and _iou((g["t"], g["t_end"]), (p["t"], p["t_end"])) >= 0.5
                                              for g in truth))
    return {
        "true_possessions": len(truth), "predicted_possessions": len(pred),
        "frame_accuracy": round(agree / max(1, both), 4),
        "frame_holder_precision": round(tp_f / max(1, tp_f + fp_f), 4), "frame_holder_recall": round(tp_f / max(1, tp_f + fn_f), 4),
        "window_recall_iou50": round(found / max(1, len(truth)), 4),
        "window_precision_iou50": round(matched_pred / max(1, len(pred)), 4),
        "mean_best_iou": round(float(np.mean(ious)) if ious else 0.0, 4),
        "player_id_accuracy": round(id_ok / max(1, overl), 4),
    }
