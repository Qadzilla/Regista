"""CLI for the private vision layer.

    python3 -m regista.vision data                       # render training + development matches (with ground truth) to /tmp/regista_vision
    python3 -m regista.vision train --models models/vision
    python3 -m regista.vision evaluate --models models/vision --out /tmp/regista_vision/eval.json
    python3 -m regista.vision run VIDEO --roster MATCH_DIR_OR_EVENTS_JSONL --out OUT_DIR [--workflow]
    python3 -m regista.vision compare OUT_DIR TRUTH_MATCH_DIR --player t_home_09
    python3 -m regista.vision mermaid

``models/vision`` must not be committed (trained weights are build artefacts).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from regista.vision.dataset import DEFAULT_ROOT, FRESH_SPECS, TEST_SPECS, TRAIN_SPECS, make_match
from regista.vision.shots import DEFAULT_MODELS_DIR


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m regista.vision", description="Regista vision layer: broadcast video in, event stream out.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("data", help="generate and render the training and development matches")
    d.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    d.add_argument("--workers", type=int, default=None)

    t = sub.add_parser("train", help="train the shot model and kit-number reader; tune cutaway thresholds")
    t.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    t.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    t.add_argument("--synth", type=int, default=20000, help="synthetic number discs added to the reader's training set")

    e = sub.add_parser("evaluate", help="measure every stage on the development set or the fresh matches")
    e.add_argument("--set", choices=["dev", "fresh"], default="dev", dest="match_set",
                   help="dev: seeds 201-206, used while tuning; fresh: seeds 301-303, scored once with frozen models")
    e.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    e.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    e.add_argument("--out", type=Path, default=None, help="write the full report as JSON")
    e.add_argument("--e2e-seed", type=int, default=None, help="match for the end-to-end clip comparison (default: the set's first)")

    r = sub.add_parser("run", help="run the vision layer on a video and write a match directory")
    r.add_argument("video", type=Path)
    r.add_argument("--roster", type=Path, required=True, help="match directory, events.jsonl, or a match-record JSON (team sheet + kits)")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--models", type=Path, default=DEFAULT_MODELS_DIR)
    r.add_argument("--match-id", default=None)
    r.add_argument("--workflow", action="store_true", help="run as the Microsoft Agent Framework workflow (shots -> identity -> possession -> writer)")

    c = sub.add_parser("compare", help="clips derived from a vision match directory vs from a ground-truth match directory")
    c.add_argument("vision_dir", type=Path)
    c.add_argument("truth_dir", type=Path)
    c.add_argument("--player", action="append", default=None)

    sub.add_parser("mermaid", help="print the vision workflow graph")
    args = ap.parse_args(argv)

    if args.cmd == "data":
        for spec in TRAIN_SPECS + TEST_SPECS:
            t0 = time.perf_counter()
            item = make_match(spec, args.root, workers=args.workers)
            print(f"{spec.match_id}: {item['video']}  ({time.perf_counter() - t0:.1f}s)")
        return 0

    if args.cmd == "train":
        from regista.vision.evaluate import train_all

        out = train_all(args.root, args.models, n_synth=args.synth)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "evaluate":
        from regista.vision.evaluate import evaluate_all

        report = evaluate_all(args.root, args.models, test_specs=FRESH_SPECS if args.match_set == "fresh" else TEST_SPECS,
                              e2e_seed=args.e2e_seed)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
            print(f"report: {args.out}")
        return 0

    if args.cmd == "run":
        from regista.vision.truth import load_match_header

        roster = load_match_header(args.roster)
        t0 = time.perf_counter()
        if args.workflow:
            from regista.vision.agents import run_vision_workflow

            run = run_vision_workflow({"video_path": str(args.video), "roster": roster, "out_dir": str(args.out),
                                       "match_id": args.match_id or ""}, config={"models_dir": str(args.models)},
                                      state_dir=args.out / "agents")
            for row in run.trace:
                print(f"{row['agent']:<18} attempt {row['attempt']}  {row['status']:<8} {row.get('elapsed_ms') or 0:>10.1f} ms  {row.get('error') or ''}")
            print(json.dumps(run.state.get("vision_summary"), indent=2))
            return 0 if run.ok else 1
        from regista.vision.pipeline import run_vision

        summ = run_vision(args.video, roster, args.out, models_dir=args.models, match_id=args.match_id)
        print(json.dumps({k: summ[k] for k in ("match_id", "out_dir", "record_counts", "segments", "timings", "validation")}, indent=2))
        print(f"({time.perf_counter() - t0:.1f}s)  next: python3 -m regista.validate {args.out}")
        return 0 if not any(summ["validation"].values()) else 1

    if args.cmd == "compare":
        from regista.schema import iter_jsonl
        from regista.vision.pipeline import compare_clips

        vs = list(iter_jsonl(args.vision_dir / "events.jsonl"))
        ts = list(iter_jsonl(args.truth_dir / "events.jsonl"))
        for pid in args.player or ["t_home_09"]:
            print(json.dumps(compare_clips(vs, ts, pid), indent=2))
        return 0

    if args.cmd == "mermaid":
        from regista.vision.agents import mermaid

        print(mermaid())
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
