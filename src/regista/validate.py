"""CLI: validate a sample match directory or individual JSONL files.

    python -m regista.validate data/synthetic/sample/syn_0042
    python -m regista.validate path/to/events.jsonl path/to/clips.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from regista.schema import validate_jsonl, validate_match_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Regista JSONL streams against the schemas.")
    parser.add_argument("paths", nargs="+", help="match directories or .jsonl files")
    parser.add_argument("--max-errors", type=int, default=20, help="errors to print per file")
    args = parser.parse_args(argv)

    failed = False
    for raw in args.paths:
        path = Path(raw)
        if path.is_dir():
            results = validate_match_dir(path)
        else:
            results = {path.name: validate_jsonl(path)}
        for name, problems in results.items():
            label = f"{path}/{name}" if path.is_dir() else str(path)
            if problems:
                failed = True
                print(f"FAIL {label}: {len(problems)} problem(s)")
                for msg in problems[: args.max_errors]:
                    print(f"  {msg}")
                if len(problems) > args.max_errors:
                    print(f"  ... {len(problems) - args.max_errors} more")
            else:
                print(f"ok   {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
