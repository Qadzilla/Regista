"""The back-compat snapshot of the catalogue round (docs/catalogue/build/design.md §11, phase 0).

Hashes of the canonical JSON of every existing Scout, season and terminal endpoint and of the three player MCP tools,
recorded on ``main``'s code before the catalogue changed anything (``tests/data/catalogue_backcompat.json``).
``tests/test_catalogue_backcompat.py`` recomputes them: the catalogue must never move an existing response.

Canonical: ``json.dumps(sort_keys=True)`` after dropping fields that are not the data (``warm``: the background
warm-up's state; ``ms``, ``elapsed_ms``, ``took_ms``: timings, such as the Scout agent trace's step times). Record
again with ``python3 tests/catalogue_snapshot.py --write`` only when a change to an existing response is intended and
reviewed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "tests" / "data" / "catalogue_backcompat.json"
VOLATILE = {"warm", "ms", "elapsed_ms", "took_ms", "timing", "timings"}

# (key, method, path, params or body)
HTTP_CALLS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    ("season", "GET", "/api/season", None),
    ("players", "GET", "/api/players", None),
    ("players_fw_goals", "GET", "/api/players", {"sort": "goals", "position": "FW"}),
    ("player_star", "GET", "/api/players/pl_bro_09", None),
    ("player_star_moments", "GET", "/api/players/pl_bro_09/moments", None),
    ("compare", "GET", "/api/compare", {"ids": "pl_bro_09,pl_ash_09"}),
    ("scout_ask_rules", "POST", "/api/scout/ask", {"q": "who scored the most goals", "engine": "rules"}),
    ("metrics", "GET", "/api/metrics", None),
    ("screen", "GET", "/api/terminal/screen", None),
    ("screen_fw", "GET", "/api/terminal/screen", {"position": "FW"}),
    ("rank_npxg", "GET", "/api/terminal/rank", {"metric": "npxg"}),
    ("scatter", "GET", "/api/terminal/scatter", {"x": "npxg", "y": "xa"}),
    ("player_metrics", "GET", "/api/players/pl_bro_09/metrics", None),
    ("player_form", "GET", "/api/players/pl_bro_09/form", None),
    ("player_similar", "GET", "/api/players/pl_bro_09/similar", None),
    ("player_shots", "GET", "/api/players/pl_bro_09/shots", None),
    ("player_heatmap", "GET", "/api/players/pl_bro_09/heatmap", None),
    ("teams", "GET", "/api/teams", None),
    ("team_style", "GET", "/api/teams/cl_brookfield/style", None),
    ("team_shots", "GET", "/api/teams/cl_brookfield/shots", None),
    ("unknown_player", "GET", "/api/players/pl_zzz_09", None),
]
MCP_CALLS: list[tuple[str, str, dict[str, Any]]] = [
    ("mcp_search_players", "search_players", {"position": "FW", "sort": "goals"}),
    ("mcp_search_players_default", "search_players", {}),
    ("mcp_get_profile", "get_profile", {"player": "pl_bro_09"}),
    ("mcp_compare_players", "compare_players", {"players": ["pl_bro_09", "pl_ash_09"]}),
]


def canonical(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: canonical(v) for k, v in obj.items() if k not in VOLATILE}
    if isinstance(obj, list):
        return [canonical(v) for v in obj]
    return obj


def digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(canonical(obj), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def snapshot() -> dict[str, str]:
    """{call key: sha256 of its canonical JSON (with the status code)} on this checkout's code and data."""
    from fastapi.testclient import TestClient

    from regista import api, mcp_server

    client = TestClient(api.app)
    out: dict[str, str] = {}
    for key, method, path, args in HTTP_CALLS:
        r = client.get(path, params=args) if method == "GET" else client.post(path, json=args)
        out[key] = digest({"status": r.status_code, "body": r.json()})
    for key, tool, args in MCP_CALLS:
        out[key] = digest(getattr(mcp_server, tool)(**args))
    return out


if __name__ == "__main__":
    import os

    os.environ.setdefault("REGISTA_DOTENV", "")
    os.environ.setdefault("REGISTA_SEASON_WARM", "0")
    got = snapshot()
    if "--write" in sys.argv:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        print(f"wrote {len(got)} hashes to {SNAPSHOT}")
    else:
        print(json.dumps(got, indent=1, sort_keys=True))
