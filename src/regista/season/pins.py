"""The committed season, pinned: the first 16 hex digits of each league fixture's ``events.jsonl`` as
``regista.season.build`` writes it, recorded on macOS (arm64, Python 3.13) with generator 0.7.1 and the league's
attributes version 2 (the star's ratings, docs/scout-terminal/build/femi-edge.md: only Brookfield's ten fixtures moved).

League matches are built on demand on the server (Linux, Python 3.11, the Docker image) and must be the same matches on
every machine. ``tests/test_league_mode.py`` checks these pins in CI (Linux) and ``python -m regista.cloud.smoke`` checks
them inside the built image against the season its Dockerfile builds, so a platform that generates any match
differently fails before it is deployed (docs/scout-terminal/build/determinism.md). A generator change that moves them
re-records them here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

SEASON_PINS = {
    "rl_r01_ash_fai": "f1c2807a9f3883eb", "rl_r01_eas_bro": "d54510ec6390b53a", "rl_r01_cal_dun": "0172a8f04cba71b0",
    "rl_r02_eas_ash": "7e6b8baea53bb494", "rl_r02_fai_dun": "1281f3025b9aaf87", "rl_r02_cal_bro": "60ae5ed6972c71e3",
    "rl_r03_ash_dun": "08818645da5240c0", "rl_r03_cal_eas": "5cfe351519e61c2e", "rl_r03_fai_bro": "c9d20e96cfe06b90",
    "rl_r04_cal_ash": "13479646c6dbc3a5", "rl_r04_dun_bro": "9f3b2d15ca099eba", "rl_r04_fai_eas": "2c9eda5285559326",
    "rl_r05_ash_bro": "15e6ab2b85435455", "rl_r05_fai_cal": "71dd5c0b9d3ce00f", "rl_r05_dun_eas": "c3bb78aec66c12c0",
    "rl_r06_fai_ash": "48317e2bebe792bf", "rl_r06_bro_eas": "6ce6788c8e90570d", "rl_r06_dun_cal": "e1eaf403e6d70963",
    "rl_r07_ash_eas": "6e819c246f6fafa6", "rl_r07_dun_fai": "4475724a4c7b6605", "rl_r07_bro_cal": "13845aabc7e2a9e8",
    "rl_r08_dun_ash": "7c8557ffab43cedd", "rl_r08_eas_cal": "81d528741a7faddf", "rl_r08_bro_fai": "e79912a41ce1ba2b",
    "rl_r09_ash_cal": "3d7ae0ea4ce1612e", "rl_r09_bro_dun": "4f8b21ec6cd03ec9", "rl_r09_eas_fai": "c4d528ce9fa50e0f",
    "rl_r10_bro_ash": "257b617cadfa393a", "rl_r10_cal_fai": "fad35dca4f094f30", "rl_r10_eas_dun": "454f07db023b3ff4",
}


def drift(league: dict[str, Any], root: Path | str) -> dict[str, str]:
    """{match_id: what this machine built} for every fixture whose built ``events.jsonl`` differs from its pin (missing
    folders included). Empty when the season here is the committed one, bit for bit."""
    root = Path(root)
    out = {}
    for fx in league["fixtures"]:
        path = root / fx["match_id"] / "events.jsonl"
        got = hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"
        if got != SEASON_PINS.get(fx["match_id"]):
            out[fx["match_id"]] = got
    return out
