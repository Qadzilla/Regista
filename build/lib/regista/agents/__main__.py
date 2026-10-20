"""CLI: run the agent pipeline over a match directory.

    python -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from regista.agents.orchestrator import Orchestrator
from regista.agents.roles import default_agents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Regista's agent pipeline.")
    parser.add_argument("match_dir", type=Path)
    parser.add_argument("--player", action="append", default=[], help="player_id (repeatable); default: the player in manifest.json or t_home_09")
    parser.add_argument("--query", action="append", default=[], help="question for the Librarian (repeatable)")
    parser.add_argument("--state-dir", type=Path, default=None, help="where trace.jsonl, dead_letter.jsonl, state.json go (default: <match_dir>/agents)")
    parser.add_argument("--max-retries", type=int, default=2)
    args = parser.parse_args(argv)

    players = args.player
    if not players:
        manifest = args.match_dir / "manifest.json"
        if manifest.exists():
            import json

            players = [json.loads(manifest.read_text()).get("clips_for") or "t_home_09"]
        else:
            players = ["t_home_09"]
    orchestrator = Orchestrator(default_agents(), args.state_dir or args.match_dir / "agents", max_retries=args.max_retries)
    result = orchestrator.run({"match_dir": str(args.match_dir), "player_ids": players, "queries": args.query})
    for row in result.trace:
        extra = f"  {row['error']}" if row["error"] else ""
        print(f"{row['agent']:<11} attempt {row['attempt']}  {row['status']:<8} {row['elapsed_ms'] or 0:>8} ms{extra}")
    for pid, clips in result.state.get("clips", {}).items():
        print(f"{pid}: {len(clips)} clips")
    for q, ans in zip(args.query, result.state.get("answers", [])):
        print(f"Q: {q}\n   {ans['message']}")
        for r in ans["results"][:5]:
            print(f"   {r['clip_id']}  {r['watchability']:.2f}  {r['title']}")
    print(f"trace: {result.state_dir / 'trace.jsonl'}   dead letters: {len(result.dead_letters)}   ok: {result.ok}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
