"""Training and evaluation of every vision step against the generator's exact ground truth.

Everything here needs a rendered match *and* its match directory (``regista.vision.dataset``),
because the labels come from ``regista.vision.truth``. Inference code never imports this module.

Reproduce the numbers in docs/vision.md with:

    python3 -m regista.vision data                     # render 10 training + 6 development matches to /tmp/regista_vision
    python3 -m regista.vision train --models models/vision
    python3 -m regista.vision evaluate --models models/vision --out /tmp/regista_vision/eval.json
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np

from regista.vision.dataset import MatchSpec, make_match
from regista.vision.detect import DiscDetector, KitPalette, detect_closeup
from regista.vision.frames import iter_frames, probe
from regista.vision.kitnumber import DigitClassifierReader, crop_disc, decode, synth_discs
from regista.vision.pitch import MainCameraCalibrator
from regista.vision.truth import Truth

Record = dict[str, Any]


def _match(item: dict[str, Any]) -> tuple[Truth, str]:
    info = probe(item["video"])
    return Truth(item["match_dir"], info.width, info.height), item["video"]


def _pairs(dets, gts, max_r: float = 0.7) -> list[tuple[int, int]]:
    from scipy.optimize import linear_sum_assignment

    if not dets or not gts:
        return []
    D = np.array([[np.hypot(d.u - g.cx, d.v - g.cy) / g.r for g in gts] for d in dets])
    ri, ci = linear_sum_assignment(D)
    return [(int(a), int(b)) for a, b in zip(ri, ci) if D[a, b] < max_r]


# ---------------------------------------------------------------------------- kit numbers

def collect_number_crops(item: dict[str, Any], sample_fps: float = 2.0, kinds: tuple[str, ...] = ("main", "replay", "highlight", "closeup")
                         ) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Crops at *detected* discs matched to ground-truth players, labelled with their roster number.

    Discs whose number is hidden (another disc on top, or the ball at the feet) are skipped: their label
    would be a guess. At inference those crops still get read; the track vote absorbs them."""
    truth, video = _match(item)
    pal = KitPalette.from_match(truth.match)
    cal = MainCameraCalibrator(truth.width, truth.height)
    det_main = DiscDetector(pal, truth.width, truth.height, cal.geom)
    det_other = DiscDetector(pal, truth.width, truth.height, None)
    crops, nums, kind_of = [], [], []
    for _i, t, rgb in iter_frames(video, sample_fps=sample_fps):
        ft = truth.objects_at(t)
        if ft.kind not in kinds:
            continue
        if ft.kind == "closeup":
            dets = detect_closeup(rgb, pal)
        else:
            dets, _ball = (det_main if ft.kind == "main" else det_other).detect(rgb)
        for a, b in _pairs(dets, ft.players):
            g = ft.players[b]
            if g.occluded > 0.25 or g.holder:
                continue
            if ft.ball is not None and np.hypot(ft.ball.cx - g.cx, ft.ball.cy - g.cy) < g.r + ft.ball.r:
                continue
            d = dets[a]
            crops.append(crop_disc(rgb, d.u, d.v, d.r, pal.kits[d.kit].lab))
            nums.append(g.kit_number)
            kind_of.append(ft.kind)
    return (np.stack(crops) if crops else np.zeros((0, 20, 20), np.float32)), np.asarray(nums, dtype=int), kind_of


def train_reader(items: list[dict[str, Any]], n_synth: int = 20000, sample_fps: float = 2.0, seed: int = 0, max_iter: int = 60,
                 hidden: tuple[int, ...] = (256, 128)) -> DigitClassifierReader:
    Xs, ys = [], []
    for it in items:
        c, n, _k = collect_number_crops(it, sample_fps)
        Xs.append(c)
        ys.append(n)
    real = int(sum(len(y) for y in ys))
    if n_synth:
        c, n = synth_discs(n_synth, seed=seed)
        Xs.append(c)
        ys.append(n)
    reader = DigitClassifierReader().fit(np.concatenate(Xs), np.concatenate(ys), seed=seed, max_iter=max_iter, hidden=hidden)
    reader.metrics.update({"real_crops": real, "synthetic_crops": n_synth})
    return reader


def evaluate_reader(reader: DigitClassifierReader, items: list[dict[str, Any]], sample_fps: float = 2.0) -> dict[str, Any]:
    """Per-crop accuracy on evaluation matches: free reading (1-99) and constrained to the team sheet."""
    from regista.vision.identity import team_numbers

    out: dict[str, Any] = {"by_kind": {}}
    tot = {"n": 0, "free": 0, "sheet": 0}
    for it in items:
        truth, _video = _match(it)
        crops, nums, kinds = collect_number_crops(it, sample_fps)
        sheet = team_numbers(truth.match)
        # The sheet for a crop is its team's (outfield or keeper) numbers; recover team from the roster number + kind is
        # ambiguous, so use the union of both teams' numbers of the same role, which is what the tracker sees at worst.
        all_nums = sorted({n for v in sheet.values() for n, _ in v})
        for rd, n, k in zip(reader.read(crops), nums, kinds):
            free, _ = decode(rd)
            con, _ = decode(rd, all_nums)
            b = out["by_kind"].setdefault(k, {"n": 0, "free": 0, "sheet": 0})
            for acc in (b, tot):
                acc["n"] += 1
                acc["free"] += int(free == n)
                acc["sheet"] += int(con == n)
    for b in list(out["by_kind"].values()) + [tot]:
        b["free_accuracy"] = round(b["free"] / max(1, b["n"]), 4)
        b["sheet_accuracy"] = round(b["sheet"] / max(1, b["n"]), 4)
    out["all"] = tot
    return out


def evaluate_reader_synthetic(reader: DigitClassifierReader, n: int = 3000, seed: int = 12345) -> dict[str, Any]:
    """Free-reading accuracy on freshly drawn discs with numbers 1-99 (numbers the league never shows)."""
    crops, nums = synth_discs(n, seed=seed)
    pred = np.array([decode(rd)[0] for rd in reader.read(crops)])
    two = nums >= 12
    return {"n": int(n), "accuracy": round(float((pred == nums).mean()), 4),
            "accuracy_numbers_12_99": round(float((pred[two] == nums[two]).mean()), 4)}


# ---------------------------------------------------------------------------- detection + identity

def evaluate_identity(result, truth: Truth) -> dict[str, Any]:
    """Score an ``IdentityResult`` frame by frame against the projected ground truth.

    - detection precision/recall: detections within 0.7 disc radii of a ground-truth disc centre;
      recall counts discs fully inside the frame and less than 40% covered by others
    - team accuracy over matched detections
    - identity accuracy: matched detections whose track was named, named correctly
    - position error: pitch metres between the detection's mapped ground point and the true position
    - ball precision/recall (within 2.5 ball radii) and position error"""
    from scipy.optimize import linear_sum_assignment

    W = truth.width
    c = {"tp": 0, "fp": 0, "fn": 0, "team_ok": 0, "named": 0, "named_ok": 0, "matched": 0,
         "ball_tp": 0, "ball_fp": 0, "ball_fn": 0}
    perr, berr, cxerr = [], [], []
    for fr in result.frames:
        ft = truth.objects_at(fr["t"])
        if ft.kind != "main":
            continue
        if ft.cam_cx is not None:
            cxerr.append(abs(fr["cx"] - ft.cam_cx))
        obs, gts = fr["obs"], ft.players
        pairs = []
        if obs and gts:
            D = np.array([[np.hypot(o["u"] - g.cx, o["v"] - g.cy) / g.r for g in gts] for o in obs])
            ri, ci = linear_sum_assignment(D)
            pairs = [(a, b) for a, b in zip(ri, ci) if D[a, b] < 0.7]
        mg = {b for _, b in pairs}
        vis = [j for j, g in enumerate(gts) if g.occluded < 0.4 and g.r <= g.cx <= W - g.r]
        c["tp"] += sum(1 for j in vis if j in mg)
        c["fn"] += sum(1 for j in vis if j not in mg)
        c["fp"] += len(obs) - len(pairs)
        for a, b in pairs:
            o, g = obs[a], gts[b]
            c["matched"] += 1
            c["team_ok"] += int(o["team_id"] == g.team_id)
            if o.get("player_id"):
                c["named"] += 1
                c["named_ok"] += int(o["player_id"] == g.player_id)
            perr.append(float(np.hypot(o["x"] - g.pitch[0], o["y"] - g.pitch[1])))
        b, gb = fr.get("ball"), ft.ball
        bvis = gb is not None and gb.r <= gb.cx <= W - gb.r
        if b is not None and bvis and np.hypot(b["u"] - gb.cx, b["v"] - gb.cy) < 2.5 * gb.r:
            c["ball_tp"] += 1
            berr.append(float(np.hypot(b["x"] - gb.pitch[0], b["y"] - gb.pitch[1])))
        else:
            c["ball_fp"] += int(b is not None)
            c["ball_fn"] += int(bvis)
    r = {
        "frames": len(result.frames),
        "detection_precision": round(c["tp"] / max(1, c["tp"] + c["fp"]), 4),
        "detection_recall": round(c["tp"] / max(1, c["tp"] + c["fn"]), 4),
        "team_accuracy": round(c["team_ok"] / max(1, c["matched"]), 4),
        "named_fraction": round(c["named"] / max(1, c["matched"]), 4),
        "identity_accuracy": round(c["named_ok"] / max(1, c["named"]), 4),
        "identity_accuracy_all_matched": round(c["named_ok"] / max(1, c["matched"]), 4),
        "position_error_m_mean": round(float(np.mean(perr)), 3) if perr else None,
        "position_error_m_p95": round(float(np.percentile(perr, 95)), 3) if perr else None,
        "camera_pan_error_m_mean": round(float(np.mean(cxerr)), 3) if cxerr else None,
        "ball_precision": round(c["ball_tp"] / max(1, c["ball_tp"] + c["ball_fp"]), 4),
        "ball_recall": round(c["ball_tp"] / max(1, c["ball_tp"] + c["ball_fn"]), 4),
        "ball_error_m_mean": round(float(np.mean(berr)), 3) if berr else None,
        "counts": c,
        "_perr": perr, "_berr": berr, "_cxerr": cxerr,
    }
    return r


def aggregate_identity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pool per-match ``evaluate_identity`` results (sums of counts, means over all detections)."""
    c: dict[str, int] = {}
    perr, berr, cx = [], [], []
    for r in rows:
        for k, v in r["counts"].items():
            c[k] = c.get(k, 0) + v
        perr += r["_perr"]
        berr += r["_berr"]
        cx += r["_cxerr"]
    return {
        "frames": sum(r["frames"] for r in rows),
        "detection_precision": round(c["tp"] / max(1, c["tp"] + c["fp"]), 4),
        "detection_recall": round(c["tp"] / max(1, c["tp"] + c["fn"]), 4),
        "team_accuracy": round(c["team_ok"] / max(1, c["matched"]), 4),
        "named_fraction": round(c["named"] / max(1, c["matched"]), 4),
        "identity_accuracy": round(c["named_ok"] / max(1, c["named"]), 4),
        "identity_accuracy_all_matched": round(c["named_ok"] / max(1, c["matched"]), 4),
        "position_error_m_mean": round(float(np.mean(perr)), 3) if perr else None,
        "position_error_m_p95": round(float(np.percentile(perr, 95)), 3) if perr else None,
        "camera_pan_error_m_mean": round(float(np.mean(cx)), 3) if cx else None,
        "ball_precision": round(c["ball_tp"] / max(1, c["ball_tp"] + c["ball_fp"]), 4),
        "ball_recall": round(c["ball_tp"] / max(1, c["ball_tp"] + c["ball_fn"]), 4),
        "ball_error_m_mean": round(float(np.mean(berr)), 3) if berr else None,
        "counts": c,
    }


def evaluate_cutaways(result, truth: Truth) -> dict[str, Any]:
    """Cutaway appearances vs the generator's appearance records (players listed per replay/highlight/closeup)."""
    true_by_seg: dict[tuple[float, float], set[str]] = {}
    seg_by_id = {s["id"]: s for s in truth.scene.segments}
    for a in truth.appearances():
        s = seg_by_id.get(a["segment_id"])
        if s is None or s["kind"] == "main":
            continue
        true_by_seg.setdefault((round(s["t"], 1), round(s["t_end"], 1)), set()).add(a["player_id"])
    tp = fp = fn = 0
    by_kind: dict[str, dict[str, int]] = {}
    for cseg in result.cutaway:
        key = (round(cseg["t"], 1), round(cseg["t_end"], 1))
        pred = set(cseg["players"])
        true = true_by_seg.get(key)
        if true is None:  # predicted segment boundaries that do not line up with a true cutaway
            best = [k for k in true_by_seg if k[0] < cseg["t_end"] and cseg["t"] < k[1]]
            true = set().union(*(true_by_seg[k] for k in best)) if best else set()
        k = by_kind.setdefault(cseg["kind"], {"tp": 0, "fp": 0, "fn": 0})
        k["tp"] += len(pred & true)
        k["fp"] += len(pred - true)
        k["fn"] += len(true - pred)
        tp += len(pred & true)
        fp += len(pred - true)
        fn += len(true - pred)
    return {"precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4), "tp": tp, "fp": fp, "fn": fn,
            "by_kind": by_kind}


def cutaway_truth(truth: Truth) -> dict[tuple[float, float], set[str]]:
    seg_by_id = {s["id"]: s for s in truth.scene.segments}
    out: dict[tuple[float, float], set[str]] = {}
    for s in truth.scene.segments:
        if s["kind"] in ("replay", "highlight", "closeup"):
            out[(round(s["t"], 1), round(s["t_end"], 1))] = set()
    for a in truth.appearances():
        s = seg_by_id.get(a["segment_id"])
        if s is not None and s["kind"] != "main":
            out.setdefault((round(s["t"], 1), round(s["t_end"], 1)), set()).add(a["player_id"])
    return out


def tune_cutaway(items: list[dict[str, Any]], reader, cfg=None) -> dict[str, Any]:
    """Choose the replay/highlight involvement thresholds that maximise appearance F1 on training matches."""
    from regista.vision.identity import IdentityConfig, adapt_palette, cutaway_identity, select_involved

    cfg = cfg or IdentityConfig()
    runs = []
    for it in items:
        truth, video = _match(it)
        segs = truth.segments(probe(video).duration_s)
        pal = adapt_palette(video, truth.match, segs, cfg.adapt_frames)
        runs.append((cutaway_identity(video, truth.match, segs, reader, pal, cfg), cutaway_truth(truth)))
    best = None
    for on in np.arange(0.05, 0.6, 0.05):
        for near in np.arange(0.1, 1.01, 0.05):
            cfg.involved_on, cfg.involved_near = float(on), float(near)
            tp = fp = fn = 0
            for cut, true in runs:
                for c in cut:
                    if c["kind"] == "closeup":
                        continue
                    pred = set(select_involved(c["kind"], c["candidates"], cfg))
                    tr = true.get((round(c["t"], 1), round(c["t_end"], 1)), set())
                    tp += len(pred & tr)
                    fp += len(pred - tr)
                    fn += len(tr - pred)
            f = 2 * tp / max(1, 2 * tp + fp + fn)
            if best is None or f > best["f1"] + 1e-9:
                best = {"involved_on": round(float(on), 3), "involved_near": round(float(near), 3), "f1": round(f, 4),
                        "tp": tp, "fp": fp, "fn": fn}
    cfg.involved_on, cfg.involved_near = best["involved_on"], best["involved_near"]
    return best


# ---------------------------------------------------------------------------- everything

def _items(specs: list[MatchSpec], root: Path | str) -> list[dict[str, Any]]:
    return [make_match(s, root) for s in specs]


def segment_items(items: list[dict[str, Any]]) -> list[tuple[str, list[Record]]]:
    out = []
    for it in items:
        truth, video = _match(it)
        out.append((video, truth.segments(probe(video).duration_s)))
    return out


def train_all(root: Path | str, models_dir: Path | str, train_specs: list[MatchSpec] | None = None, n_synth: int = 20000,
              log=print) -> dict[str, Any]:
    """Train the shot model and the kit-number reader, tune the cutaway thresholds, save everything to ``models_dir``."""
    from regista.vision.dataset import TRAIN_SPECS
    from regista.vision.identity import IdentityConfig
    from regista.vision.shots import train_shot_model

    items = _items(train_specs or TRAIN_SPECS, root)
    t0 = time.perf_counter()
    shot = train_shot_model(segment_items(items))
    shot.save(models_dir)
    log(f"shot model: {shot.metrics} cut threshold {shot.cut_threshold}  ({time.perf_counter() - t0:.0f}s)")
    t0 = time.perf_counter()
    reader = train_reader(items, n_synth=n_synth)
    reader.save(models_dir)
    log(f"kit-number reader: {reader.metrics}  ({time.perf_counter() - t0:.0f}s)")
    t0 = time.perf_counter()
    cfg = IdentityConfig()
    tuned = tune_cutaway(items, reader, cfg)
    cfg.save(models_dir)
    log(f"cutaway thresholds: {tuned}  ({time.perf_counter() - t0:.0f}s)")
    return {"shot_model": shot.metrics | {"cut_threshold": shot.cut_threshold}, "reader": reader.metrics, "cutaway": tuned,
            "train_matches": [it["spec"].match_id for it in items]}


def evaluate_all(root: Path | str, models_dir: Path | str, test_specs: list[MatchSpec] | None = None, e2e_seed: int | None = None,
                 log=print) -> dict[str, Any]:
    """Every metric in docs/vision.md, on the development set (default) or the given matches."""
    from regista.schema import iter_jsonl
    from regista.vision.dataset import TEST_SPECS
    from regista.vision.identity import IdentityConfig, run_identity
    from regista.vision.pipeline import compare_clips, run_vision
    from regista.vision.possession import evaluate_possessions, infer_possessions
    from regista.vision.shots import ShotModel, evaluate_shot_model
    from regista.vision.truth import load_match_header

    specs = test_specs or TEST_SPECS
    items = _items(specs, root)
    report: dict[str, Any] = {"test_matches": [it["spec"].match_id for it in items]}
    shot = ShotModel.load(models_dir)
    reader = DigitClassifierReader.load(models_dir)
    cfg = IdentityConfig.load(models_dir)

    t0 = time.perf_counter()
    rep = evaluate_shot_model(shot, segment_items(items))
    report["shots"] = rep
    log(f"shots: frame accuracy {rep['accuracy']} boundaries {rep['boundaries']}  ({time.perf_counter() - t0:.0f}s)")

    t0 = time.perf_counter()
    report["kit_numbers"] = evaluate_reader(reader, items)
    report["kit_numbers_synthetic_1_99"] = evaluate_reader_synthetic(reader)
    log(f"kit numbers: {report['kit_numbers']['all']}  synthetic 1-99: {report['kit_numbers_synthetic_1_99']}  ({time.perf_counter() - t0:.0f}s)")

    # Identity, cutaways and possession measured on true camera segments, so each stage is scored on its own.
    id_rows, cut_rows, poss_rows = [], [], []
    for it in items:
        t0 = time.perf_counter()
        truth, video = _match(it)
        segs = truth.segments(probe(video).duration_s)
        res = run_identity(video, truth.match, segs, reader, cfg)
        idr = evaluate_identity(res, truth)
        cut = evaluate_cutaways(res, truth)
        main = [s for s in segs if s["kind"] == "main"]
        poss = evaluate_possessions(infer_possessions(res.frames, truth.match, "eval", fps=cfg.sample_fps,
                                                      segment_end={s["id"]: s["t_end"] for s in segs}), truth.possessions(), main,
                                    [f["t"] for f in res.frames])
        id_rows.append(idr)
        cut_rows.append(cut)
        poss_rows.append(poss)
        log(f"{it['spec'].match_id}: identity {idr['identity_accuracy']} det P/R {idr['detection_precision']}/{idr['detection_recall']} "
            f"cutaway P/R {cut['precision']}/{cut['recall']} possession frame acc {poss['frame_accuracy']}  ({time.perf_counter() - t0:.0f}s)")
    report["identity"] = aggregate_identity(id_rows)
    report["identity_per_match"] = [{k: v for k, v in r.items() if not k.startswith("_") and k != "counts"} for r in id_rows]
    tp, fp, fn = (sum(c[k] for c in cut_rows) for k in ("tp", "fp", "fn"))
    report["cutaway_appearances"] = {"precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4),
                                     "tp": tp, "fp": fp, "fn": fn}
    report["possession_per_match"] = poss_rows
    keys = ["frame_accuracy", "frame_holder_precision", "frame_holder_recall", "window_recall_iou50", "window_precision_iou50",
            "mean_best_iou", "player_id_accuracy"]
    w = [p["true_possessions"] for p in poss_rows]
    report["possession"] = {k: round(float(np.average([p[k] for p in poss_rows], weights=w)), 4) for k in keys}
    report["possession"]["true_possessions"] = int(sum(w))
    report["possession"]["predicted_possessions"] = int(sum(p["predicted_possessions"] for p in poss_rows))

    # End to end on one evaluation match: predicted segments, the full pipeline, then the intelligence layer's clip rule.
    e2e_item = next((it for it in items if e2e_seed is None or it["spec"].seed == e2e_seed), items[0])
    t0 = time.perf_counter()
    out_dir = Path(root) / "out" / f"vis_{e2e_item['spec'].match_id}"
    summ = run_vision(e2e_item["video"], load_match_header(e2e_item["match_dir"]), out_dir, models_dir=models_dir)
    vs = list(iter_jsonl(out_dir / "events.jsonl"))
    ts = list(iter_jsonl(Path(e2e_item["match_dir"]) / "events.jsonl"))
    header = next(r for r in ts if r["type"] == "match")
    starters = [p["player_id"] for p in header["players"] if p["starter"]]
    per_player = {pid: compare_clips(vs, ts, pid) for pid in starters}
    tot = {k: sum(r[k] for r in per_player.values()) for k in ("true_clips", "vision_clips")}
    hits = sum(r["matched_true"] for r in per_player.values())
    used = sum(r["matched_vision"] for r in per_player.values())
    tsec = sum(r["true_seconds"] for r in per_player.values())
    cov = sum(r["true_seconds_covered"] * r["true_seconds"] for r in per_player.values())
    report["end_to_end"] = {"match": e2e_item["spec"].match_id, "summary": {k: summ[k] for k in ("record_counts", "segments", "timings", "validation")},
                            "t_home_09": per_player.get("t_home_09"),
                            "all_starters": {"players": len(starters), **tot, "recall_iou50": round(hits / max(1, tot["true_clips"]), 3),
                                             "precision_iou50": round(used / max(1, tot["vision_clips"]), 3),
                                             "true_seconds_covered": round(cov / max(1e-6, tsec), 3)}}
    log(f"end to end on {e2e_item['spec'].match_id}: {report['end_to_end']['all_starters']}  ({time.perf_counter() - t0:.0f}s)")
    return report
