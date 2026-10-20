"""Synthetic-data realism report: how a generated match compares with Premier League norms.

    python -m regista.synth.report data/synthetic/sample/syn_0294
    python -m regista.synth.report --profile realistic --seeds 11 12 13 --minutes 20

The generator has two profiles. ``demo`` packs a 3-minute sample with action so a
short clip reel has something in it; ``realistic`` is tuned to land inside the bands
below over a full match. The report prints every metric beside its band and says which
side of the band it falls on, so nobody has to take "football-realistic" on trust.

Norm bands are approximate season averages for both teams combined per 90 minutes,
compiled from publicly reported Premier League statistics (FBref / Opta, 2021-22 to
2023-24 seasons). They are sanity bands for a simulator, not a research dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from regista.schema import iter_jsonl

Record = dict[str, Any]

NORMS_SOURCE = "Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth."

# metric -> (low, high, unit, note)
NORMS: dict[str, tuple[float, float, str, str]] = {
    "passes_per90": (800.0, 1100.0, "passes", "attempted passes and crosses, both teams"),
    "pass_completion": (0.78, 0.87, "ratio", "completed / attempted"),
    "shots_per90": (20.0, 32.0, "shots", "both teams"),
    "goals_per90": (2.2, 3.6, "goals", "both teams"),
    "xg_per_shot": (0.08, 0.13, "xG", "mean expected goals per shot"),
    "tackles_per90": (28.0, 45.0, "tackles", "both teams"),
    "interceptions_per90": (14.0, 30.0, "interceptions", "both teams"),
    "take_ons_per90": (28.0, 50.0, "take-ons", "attempted dribbles past a defender"),
    "nutmegs_per90": (0.5, 3.0, "nutmegs", "rarely reported; broadcast estimate"),
    "fouls_per90": (18.0, 28.0, "fouls", "both teams"),
    "corners_per90": (8.0, 13.0, "corners", "both teams"),
    "throw_ins_per90": (35.0, 55.0, "throw-ins", "both teams"),
    "possession_mean_s": (1.5, 4.5, "seconds", "mean time one player holds the ball"),
}
DIAGNOSTICS = ("replays_per_goal", "tracks_kit_number_share", "minutes", "possession_changes_per90", "carries_per90", "pressures_per90")


def compute_metrics(stream: list[Record], tracks: list[Record] | None = None) -> dict[str, float]:
    """Per-90 rates and ratios for one or more concatenated matches (period tables give the minutes)."""
    matches = [r for r in stream if r["type"] == "match"]
    minutes = sum((per["t_end"] - per["t"]) / 60.0 for m in matches for per in m["periods"]) or 1e-9
    scale = 90.0 / minutes
    events = [r for r in stream if r["type"] == "event"]
    counts = Counter(e["event_type"] for e in events)
    passes = [e for e in events if e["event_type"] in ("pass", "cross")]
    shots = [e for e in events if e["event_type"] == "shot"]
    possessions = [r for r in stream if r["type"] == "possession"]
    segments = [r for r in stream if r["type"] == "camera_segment"]
    replays = sum(1 for s in segments if s["kind"] == "replay")
    goals = counts["goal"]
    out = {
        "minutes": round(minutes, 2),
        "passes_per90": round(len(passes) * scale, 1),
        "pass_completion": round(sum(1 for p in passes if p["outcome"] == "success") / len(passes), 3) if passes else 0.0,
        "shots_per90": round(len(shots) * scale, 1),
        "goals_per90": round(goals * scale, 2),
        "xg_per_shot": round(sum(s.get("metrics", {}).get("xg", 0.0) for s in shots) / len(shots), 3) if shots else 0.0,
        "tackles_per90": round(counts["tackle"] * scale, 1),
        "interceptions_per90": round(counts["interception"] * scale, 1),
        "take_ons_per90": round(counts["take_on"] * scale, 1),
        "nutmegs_per90": round(counts["nutmeg"] * scale, 2),
        "fouls_per90": round(counts["foul"] * scale, 1),
        "corners_per90": round(counts["corner"] * scale, 1),
        "throw_ins_per90": round(counts["throw_in"] * scale, 1),
        "possession_mean_s": round(sum(p["t_end"] - p["t"] for p in possessions) / len(possessions), 2) if possessions else 0.0,
        "possession_changes_per90": round(counts["possession_change"] * scale, 1),
        "carries_per90": round(counts["carry"] * scale, 1),
        "pressures_per90": round(counts["pressure"] * scale, 1),
        "replays_per_goal": round(replays / goals, 2) if goals else float(replays),
    }
    if tracks:
        players = [t for t in tracks if t["object"] == "player"]
        out["tracks_kit_number_share"] = round(sum(1 for t in players if "kit_number" in t.get("identity", {}).get("evidence", [])) / len(players), 3) if players else 0.0
    return out


def verdicts(metrics: dict[str, float]) -> dict[str, str]:
    out = {}
    for key, (lo, hi, _unit, _note) in NORMS.items():
        v = metrics.get(key)
        if v is None:
            out[key] = "n/a"
        elif v < lo:
            out[key] = "low"
        elif v > hi:
            out[key] = "high"
        else:
            out[key] = "in band"
    return out


def render_markdown(metrics: dict[str, float], title: str, profile: str | None = None, note: str | None = None) -> str:
    v = verdicts(metrics)
    lines = [f"# Synthetic realism report: {title}", ""]
    if profile:
        lines.append(f"Generator profile: **{profile}**. " + ("The demo profile is deliberately dense so a 3-minute sample fills a clip reel; its rates are expected to sit above the bands. " if profile == "demo" else "The realistic profile is tuned to sit inside the bands over a full match. "))
    if note:
        lines.append(note)
    lines += ["", f"Simulated minutes: {metrics.get('minutes', 0)}", "", f"Norms: {NORMS_SOURCE}", "",
              "| Metric | Value | Band | Verdict | Note |", "|---|---|---|---|---|"]
    for key, (lo, hi, unit, note_) in NORMS.items():
        val = metrics.get(key)
        shown = f"{val:.3f}" if isinstance(val, float) and val < 1.5 and key in ("pass_completion", "xg_per_shot") else f"{val}"
        lines.append(f"| {key} | {shown} {unit} | {lo}–{hi} | {v[key]} | {note_} |")
    inb = sum(1 for x in v.values() if x == "in band")
    lines += ["", f"**{inb} of {len(NORMS)} metrics in band.**", "", "Diagnostics (no band): " + ", ".join(f"{k}={metrics[k]}" for k in DIAGNOSTICS if k in metrics), ""]
    return "\n".join(lines)


def report_match_dir(match_dir: Path) -> tuple[dict[str, float], str]:
    stream = list(iter_jsonl(match_dir / "events.jsonl"))
    tracks_path = match_dir / "tracks.jsonl"
    tracks = list(iter_jsonl(tracks_path)) if tracks_path.exists() else None
    match = next(r for r in stream if r["type"] == "match")
    gen = match.get("generator", {})
    profile = gen.get("params", {}).get("profile")
    metrics = compute_metrics(stream, tracks)
    return metrics, render_markdown(metrics, match["match_id"], profile)


def report_profile(profile: str, seeds: list[int], minutes: float) -> tuple[dict[str, float], str]:
    from regista.synth.generator import generate

    stream: list[Record] = []
    for seed in seeds:
        stream += generate(seed=seed, minutes=minutes, track_hz=1.0, profile=profile).stream
    metrics = compute_metrics(stream)
    return metrics, render_markdown(metrics, f"profile '{profile}', seeds {seeds}, {minutes:g} min each", profile)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare synthetic match statistics with Premier League norms.")
    parser.add_argument("match_dir", nargs="?", type=Path, help="a generated match directory (events.jsonl)")
    parser.add_argument("--profile", choices=["demo", "realistic"], help="instead of a directory, simulate this profile")
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13])
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.match_dir:
        metrics, md = report_match_dir(args.match_dir)
    elif args.profile:
        metrics, md = report_profile(args.profile, args.seeds, args.minutes)
    else:
        parser.error("give a match directory or --profile")
    if args.json:
        print(json.dumps({"metrics": metrics, "verdicts": verdicts(metrics)}, indent=2))
    else:
        print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
