"""The catalogue round never moves what exists (docs/catalogue/build/design.md §9 and §11, item 1).

- ``data/season/league.json`` (the England semi-pro men competition, the Regista League) is byte-identical to ``main``.
- Every existing Scout, season and terminal endpoint and the three player MCP tools answer exactly as on ``main``: their
  canonical JSON hashes were recorded before the first code change (``tests/catalogue_snapshot.py``).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import catalogue_snapshot  # noqa: E402

# sha256 of data/season/league.json on main (c349c3d): the frozen competition, never written by the catalogue
LEAGUE_SHA256 = "04dbb30f7cc9efad0253d505c3fb28f1a89b49aab15e2b4b98e73a50ce0b1a34"


def test_the_league_file_is_byte_identical_to_main():
    assert hashlib.sha256((ROOT / "data" / "season" / "league.json").read_bytes()).hexdigest() == LEAGUE_SHA256


def test_existing_endpoints_and_player_tools_answer_as_on_main():
    want = json.loads(catalogue_snapshot.SNAPSHOT.read_text())
    got = catalogue_snapshot.snapshot()
    assert set(got) == set(want)
    moved = sorted(k for k in want if got[k] != want[k])
    assert not moved, f"responses changed: {moved}"
