"""Video + roster in, Regista match directory out: the whole private vision layer in one call.

    run_vision("broadcast.mp4", match_header, "out/vis_0201")

writes ``events.jsonl`` (the ``match`` header, then ``camera_segment``, ``possession`` and
``appearance`` records, sorted by time), ``tracks.jsonl`` (players and ball in pitch metres) and
``manifest.json``. The directory validates with ``python3 -m regista.validate`` and feeds the
intelligence layer unchanged (``python3 -m regista.agents <dir> --player t_home_09``).

The roster input is a ``match`` record: teams with kit colours, and players with kit numbers,
positions and starter flags (a team sheet). Its ``periods`` are kept when given; otherwise one
period covering the video is assumed, attacking direction inferred from where each goalkeeper
stands. The vision layer emits no ``event`` records yet (passes, shots, tackles): labels on
vision-derived clips therefore carry only the clip reason until an event-spotting model exists.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from regista.schema import SCHEMA_VERSION, validate_match_dir, write_jsonl
from regista.vision.frames import VideoInfo, probe
from regista.vision.identity import IdentityConfig, IdentityResult, appearance_records, run_identity, track_records
from regista.vision.kitnumber import DigitClassifierReader, KitNumberReader
from regista.vision.possession import PossessionConfig, infer_possessions
from regista.vision.shots import DEFAULT_MODELS_DIR, ShotModel, segments_to_records

Record = dict[str, Any]
HEADER_KEYS = ("competition", "season", "date", "venue", "home_team_id", "away_team_id", "teams", "players")


def vision_match_header(roster: Record, info: VideoInfo, match_id: str, identity: IdentityResult | None = None) -> Record:
    """The ``match`` record for a vision-derived stream: the roster's teams and players, this video's metadata."""
    rec: Record = {"type": "match", "id": f"ma_{match_id}", "match_id": match_id, "schema_version": SCHEMA_VERSION, "source": "vision"}
    for k in HEADER_KEYS:
        if k in roster:
            rec[k] = roster[k]
    rec["video"] = {"video_id": Path(info.path).stem, "fps": info.fps, "width": info.width, "height": info.height,
                    "duration_s": info.duration_s, "main_camera": "broadcast_wide"}
    periods = []
    for p in roster.get("periods") or []:
        if p["t"] < info.duration_s:
            periods.append({**p, "t_end": min(float(p["t_end"]), info.duration_s)})
    if not periods:
        periods = [{"period": 1, "t": 0.0, "t_end": info.duration_s, "left_to_right_team_id": _infer_direction(roster, identity)}]
    rec["periods"] = periods
    return rec


def _infer_direction(roster: Record, identity: IdentityResult | None) -> str:
    """The team whose goalkeeper stands nearer x = 0 attacks toward x = 105."""
    teams = [t["team_id"] for t in roster["teams"]]
    if identity is None:
        return roster.get("home_team_id", teams[0])
    xs: dict[str, list[float]] = defaultdict(list)
    for fr in identity.frames:
        for o in fr["obs"]:
            if o["is_gk"]:
                xs[o["team_id"]].append(o["x"])
    means = {t: float(np.median(v)) for t, v in xs.items() if v}
    if means:
        return min(means, key=means.get)
    return roster.get("home_team_id", teams[0])


def load_models(models_dir: Path | str = DEFAULT_MODELS_DIR) -> tuple[ShotModel, DigitClassifierReader]:
    return ShotModel.load(models_dir), DigitClassifierReader.load(models_dir)


def run_vision(video: Path | str, roster: Record, out_dir: Path | str, *, models_dir: Path | str = DEFAULT_MODELS_DIR,
               shot_model: ShotModel | None = None, reader: KitNumberReader | None = None, match_id: str | None = None,
               identity_cfg: IdentityConfig | None = None, possession_cfg: PossessionConfig | None = None,
               track_hz: float = 2.0, segments: list[Record] | None = None) -> dict[str, Any]:
    """Run shots -> identity -> possession on ``video`` and write a validated match directory.

    ``segments`` overrides the shot agent (for example ground-truth segments, to measure the later
    stages in isolation). Returns a summary with record counts, timings, and validation problems."""
    timings: dict[str, float] = {}
    out_dir = Path(out_dir)
    info = probe(video)
    match_id = match_id or f"{roster.get('match_id', Path(video).stem)}_vision"
    t0 = time.perf_counter()
    if segments is None:
        shot_model = shot_model or ShotModel.load(models_dir)
        segments = shot_model.predict(video)
    seg_recs = segments_to_records(segments, match_id)
    segs = [{**s, "id": r["id"]} for s, r in zip(segments, seg_recs)]
    timings["shots_s"] = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    reader = reader or DigitClassifierReader.load(models_dir)
    identity_cfg = identity_cfg or IdentityConfig.load(models_dir)
    ident = run_identity(video, roster, segs, reader, identity_cfg)
    timings["identity_s"] = round(time.perf_counter() - t0, 2)

    t0 = time.perf_counter()
    possessions = infer_possessions(ident.frames, roster, match_id, possession_cfg, fps=identity_cfg.sample_fps)
    timings["possession_s"] = round(time.perf_counter() - t0, 2)

    return write_match_dir(out_dir, roster, info, match_id, seg_recs, ident, possessions, track_hz, timings)


def write_match_dir(out_dir: Path | str, roster: Record, info: VideoInfo, match_id: str, seg_recs: list[Record], ident: IdentityResult,
                    possessions: list[Record], track_hz: float = 2.0, timings: dict[str, float] | None = None) -> dict[str, Any]:
    out_dir = Path(out_dir)
    appearances = appearance_records(ident, possessions, match_id)
    tracks = track_records(ident, match_id, info.fps, track_hz)
    header = vision_match_header(roster, info, match_id, ident)
    order = {"camera_segment": 0, "possession": 1, "appearance": 2}
    body = sorted(seg_recs + possessions + appearances, key=lambda r: (r["t"], order[r["type"]], r["id"]))
    out_dir.mkdir(parents=True, exist_ok=True)
    n_events = write_jsonl(out_dir / "events.jsonl", [header] + body)
    n_tracks = write_jsonl(out_dir / "tracks.jsonl", sorted(tracks, key=lambda r: (r["t"], r["id"])))
    problems = validate_match_dir(out_dir)
    counts: dict[str, int] = defaultdict(int)
    for r in [header] + body:
        counts[r["type"]] += 1
    summary = {"match_id": match_id, "video": info.__dict__, "out_dir": str(out_dir), "files": {"events.jsonl": n_events, "tracks.jsonl": n_tracks},
               "record_counts": dict(counts), "segments": {k: sum(1 for s in seg_recs if s["kind"] == k) for k in {s["kind"] for s in seg_recs}},
               "identity": ident.info, "timings": timings or {}, "validation": {k: len(v) for k, v in problems.items()},
               "source": "vision", "pipeline": "regista.vision v0 (synthetic-renderer models)"}
    (out_dir / "manifest.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------- clip comparison

def _iou(a: Record, b: Record) -> float:
    inter = max(0.0, min(a["t_end"], b["t_end"]) - max(a["t"], b["t"]))
    union = max(a["t_end"], b["t_end"]) - min(a["t"], b["t"])
    return inter / union if union > 0 else 0.0


def _covered(intervals: list[tuple[float, float]], by: list[tuple[float, float]]) -> float:
    total = 0.0
    for a0, a1 in intervals:
        pts = sorted((max(a0, b0), min(a1, b1)) for b0, b1 in by if b0 < a1 and a0 < b1)
        cur = a0
        for s, e in pts:
            if e > cur:
                total += e - max(s, cur)
                cur = max(cur, e)
    return total


def compare_clips(vision_stream: list[Record], truth_stream: list[Record], player_id: str) -> dict[str, Any]:
    """Clips the intelligence layer derives from the vision stream vs from the ground-truth stream, for one player."""
    from regista.clips import derive_clips

    pred, _ = derive_clips(vision_stream, player_id)
    true, _ = derive_clips(truth_stream, player_id)
    out: dict[str, Any] = {"player_id": player_id, "true_clips": len(true), "vision_clips": len(pred), "by_reason": {}}
    hit = [False] * len(true)
    used = [False] * len(pred)
    for i, g in enumerate(true):
        cands = [(j, _iou(g, p)) for j, p in enumerate(pred) if p["reason"] == g["reason"] and not used[j]]
        if cands:
            j, best = max(cands, key=lambda x: x[1])
            if best >= 0.5:
                hit[i] = used[j] = True
    for reason in sorted({c["reason"] for c in true + pred}):
        ti = [i for i, c in enumerate(true) if c["reason"] == reason]
        pj = [j for j, c in enumerate(pred) if c["reason"] == reason]
        out["by_reason"][reason] = {"true": len(ti), "vision": len(pj), "matched_iou50": sum(hit[i] for i in ti),
                                    "recall": round(sum(hit[i] for i in ti) / max(1, len(ti)), 3),
                                    "precision": round(sum(used[j] for j in pj) / max(1, len(pj)), 3)}
    out["matched_true"], out["matched_vision"] = sum(hit), sum(used)
    out["recall_iou50"] = round(sum(hit) / max(1, len(true)), 3)
    out["precision_iou50"] = round(sum(used) / max(1, len(pred)), 3)
    ti = [(c["t"], c["t_end"]) for c in true]
    pi = [(c["t"], c["t_end"]) for c in pred]
    tsec = sum(b - a for a, b in _merge(ti))
    psec = sum(b - a for a, b in _merge(pi))
    out["true_seconds"] = round(tsec, 1)
    out["vision_seconds"] = round(psec, 1)
    out["true_seconds_covered"] = round(_covered(_merge(ti), pi) / max(1e-6, sum(b - a for a, b in _merge(ti))), 3)
    out["vision_seconds_inside_true"] = round(_covered(_merge(pi), ti) / max(1e-6, sum(b - a for a, b in _merge(pi))), 3)
    return out


def _merge(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]
