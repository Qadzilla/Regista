"""CLI: generate a synthetic match and derive clips for one player.

    python -m regista.synth --minutes 3 --seed 294 --track-hz 1 --player t_home_09 --out data/synthetic/sample
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from regista.clips import derive_clips
from regista.schema import write_jsonl
from regista.synth.generator import GENERATOR_NAME, GENERATOR_VERSION, generate, parse_team_arg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a synthetic Regista match.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--minutes", type=float, default=3.0, help="minutes of play to simulate")
    parser.add_argument("--track-hz", type=float, default=1.0, help="track samples per second")
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--player", default="t_home_09", help="player_id to derive clips for")
    parser.add_argument("--profile", choices=["demo", "realistic"], default="demo", help="demo packs action into a short sample; realistic matches Premier League rates")
    parser.add_argument("--report", action="store_true", help="also write report.md comparing the match with Premier League norms")
    parser.add_argument("--periods", type=int, choices=[1, 2], default=1, help="1 or 2 halves; --minutes is per half")
    parser.add_argument("--home", help="home team as 'Name,SHORT,#primary[,#secondary[,#gk]]'")
    parser.add_argument("--away", help="away team as 'Name,SHORT,#primary[,#secondary[,#gk]]'")
    parser.add_argument("--out", type=Path, default=Path("data/synthetic/sample"), help="output root; a <match_id>/ folder is created inside")
    args = parser.parse_args(argv)

    teams = None
    if args.home or args.away:
        teams = [parse_team_arg(args.home) if args.home else {}, parse_team_arg(args.away) if args.away else {}]
    result = generate(seed=args.seed, minutes=args.minutes, track_hz=args.track_hz, fps=args.fps, profile=args.profile,
                      periods=args.periods, teams=teams)
    clips, labels = derive_clips(result.stream, args.player)

    out_dir = args.out / result.match["match_id"]
    n_events = write_jsonl(out_dir / "events.jsonl", result.stream)
    n_tracks = write_jsonl(out_dir / "tracks.jsonl", result.tracks)
    n_clips = write_jsonl(out_dir / "clips.jsonl", clips + labels)

    counts = Counter(r["type"] for r in result.stream)
    event_types = Counter(r["event_type"] for r in result.events if r["type"] == "event")
    manifest = {
        "match_id": result.match["match_id"],
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "seed": args.seed,
                      "params": {"minutes": args.minutes, "periods": args.periods, "track_hz": args.track_hz, "fps": args.fps}},
        "score": result.score,
        "video_duration_s": result.match["video"]["duration_s"],
        "files": {"events.jsonl": n_events, "tracks.jsonl": n_tracks, "clips.jsonl": n_clips},
        "record_counts": dict(counts),
        "event_type_counts": dict(sorted(event_types.items())),
        "clips_for": args.player,
        "clip_reasons": dict(Counter(c["reason"] for c in clips)),
    }
    manifest["generator"]["params"]["profile"] = args.profile
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if args.report:
        from regista.synth.report import compute_metrics, render_markdown

        md = render_markdown(compute_metrics(result.stream, result.tracks), result.match["match_id"], args.profile)
        (out_dir / "report.md").write_text(md, encoding="utf-8")

    print(f"wrote {out_dir}")
    print(f"  events.jsonl  {n_events:>7} records  {dict(counts)}")
    print(f"  tracks.jsonl  {n_tracks:>7} records")
    print(f"  clips.jsonl   {n_clips:>7} records  ({len(clips)} clips for {args.player}: {manifest['clip_reasons']})")
    print(f"  score {result.score}  duration {manifest['video_duration_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
