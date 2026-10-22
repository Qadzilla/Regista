"""The Regista League: six synthetic clubs, fixed squads with global player ids, and a double round robin.

The league is defined once (``new_league``) and committed as ``data/season/league.json``: clubs, squads, fixtures, the
seed of every match and the generator settings. Matches are not committed; ``regista.season.build`` regenerates each one
deterministically from its fixture (well under a second each). A player keeps one global id (``pl_ash_09``) across every match,
which is what a profile is keyed on; inside a match the usual per-match ids (``t_home_09``) stay as they are.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path
from typing import Any

from regista.synth.generator import BENCH, FIRST_NAMES, FORMATION_433, GENERATOR_NAME, GENERATOR_VERSION, LAST_NAMES

Record = dict[str, Any]

LEAGUE_NAME = "Regista League"
SEASON = "2026/27"
DEFAULT_SEED = 2026
MATCH_MINUTES = 15.0   # per half: 30-minute matches, about 300 minutes per player over the season
PROFILE = "realistic"
TRACK_HZ = 1.0
FIRST_ROUND = dt.date(2026, 8, 15)

# Six synthetic clubs; primaries far apart, keeper colours distinct from every primary and from each other.
CLUBS: list[Record] = [
    {"club_id": "cl_ashby", "name": "Ashby Athletic", "short_name": "ASH", "ground": "Ashby Park",
     "kit": {"primary": "#C8102E", "secondary": "#FFFFFF", "gk": "#111111"}},
    {"club_id": "cl_brookfield", "name": "Brookfield Rovers", "short_name": "BRO", "ground": "The Brook",
     "kit": {"primary": "#1E3A8A", "secondary": "#F5D90A", "gk": "#C6FF00"}},
    {"club_id": "cl_calder", "name": "Calder Town", "short_name": "CAL", "ground": "Calder Road",
     "kit": {"primary": "#00A650", "secondary": "#FFFFFF", "gk": "#FF1493"}},
    {"club_id": "cl_dunmore", "name": "Dunmore City", "short_name": "DUN", "ground": "Dunmore Stadium",
     "kit": {"primary": "#6A0DAD", "secondary": "#FFFFFF", "gk": "#FFD700"}},
    {"club_id": "cl_eastwick", "name": "Eastwick United", "short_name": "EAS", "ground": "Eastwick Lane",
     "kit": {"primary": "#FF8C00", "secondary": "#000000", "gk": "#9E9E9E"}},
    {"club_id": "cl_fairhaven", "name": "Fairhaven FC", "short_name": "FAI", "ground": "Harbour Ground",
     "kit": {"primary": "#00B5E2", "secondary": "#002147", "gk": "#8B4513"}},
]


def _squad(club: Record, rng: random.Random, used: set[str]) -> list[Record]:
    """18 people in the generator's order: the 4-3-3 starters in formation order, then the bench."""
    slots = [(pos, num, True) for pos, num, _x, _y in FORMATION_433] + [(pos, num, False) for pos, num in BENCH]
    out = []
    for position, number, starter in slots:
        while True:
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used:
                used.add(name)
                break
        out.append({"global_id": f"pl_{club['short_name'].lower()}_{number:02d}", "name": name, "kit_number": number,
                    "position": position, "starter": starter})
    return out


def _round_robin(n: int) -> list[list[tuple[int, int]]]:
    """Circle method: n-1 rounds in which every club meets every other once; home and away alternate."""
    clubs = list(range(n))
    rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = clubs[i], clubs[n - 1 - i]
            pairs.append((a, b) if (r + i) % 2 == 0 else (b, a))
        rounds.append(pairs)
        clubs = [clubs[0], clubs[-1], *clubs[1:-1]]
    return rounds


def new_league(seed: int = DEFAULT_SEED) -> Record:
    """The league definition: clubs with squads, then a double round robin (10 rounds, 30 matches, one seed each)."""
    rng = random.Random(seed)
    used: set[str] = set()
    clubs = [{**c, "squad": _squad(c, rng, used)} for c in CLUBS]
    first = _round_robin(len(clubs))
    rounds = first + [[(b, a) for a, b in pairs] for pairs in first]
    fixtures = []
    for r, pairs in enumerate(rounds, start=1):
        for k, (h, a) in enumerate(pairs):
            home, away = clubs[h], clubs[a]
            fixtures.append({"match_id": f"rl_r{r:02d}_{home['short_name'].lower()}_{away['short_name'].lower()}", "round": r,
                             "date": (FIRST_ROUND + dt.timedelta(days=7 * (r - 1))).isoformat(),
                             "home": home["club_id"], "away": away["club_id"], "seed": seed * 10 + r * 10 + k})
    return {"league": LEAGUE_NAME, "season": SEASON, "seed": seed,
            "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "profile": PROFILE, "minutes": MATCH_MINUTES,
                          "periods": 2, "track_hz": TRACK_HZ},
            "clubs": clubs, "fixtures": fixtures}


def save_league(league: Record, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(league, indent=1) + "\n")
    return path


def load_league(path: Path | str) -> Record:
    return json.loads(Path(path).read_text())


def club_by_id(league: Record) -> dict[str, Record]:
    return {c["club_id"]: c for c in league["clubs"]}


def people(league: Record) -> dict[str, Record]:
    """global id -> person, with their club."""
    return {p["global_id"]: {**p, "club_id": c["club_id"], "club": c["name"], "short_name": c["short_name"], "kit": c["kit"]}
            for c in league["clubs"] for p in c["squad"]}


def generate_kwargs(league: Record, fixture: Record) -> Record:
    """Arguments for ``regista.synth.generator.generate`` that reproduce this fixture exactly."""
    clubs = club_by_id(league)
    g = league["generator"]

    def side(club_id: str) -> Record:
        c = clubs[club_id]
        return {"name": c["name"], "short_name": c["short_name"], "kit": c["kit"], "club_id": c["club_id"],
                "squad": [{"global_id": p["global_id"], "name": p["name"]} for p in c["squad"]]}

    home = clubs[fixture["home"]]
    return {"seed": fixture["seed"], "minutes": g["minutes"], "track_hz": g["track_hz"], "profile": g["profile"],
            "periods": g["periods"], "teams": [side(fixture["home"]), side(fixture["away"])], "match_id": fixture["match_id"],
            "meta": {"competition": league["league"], "season": league["season"], "date": fixture["date"], "venue": home["ground"]}}


_cached: dict[str, tuple[int, Record]] = {}


def load_league_cached(path: Path | str) -> Record:
    """``load_league``, read again only when the file changes (the API asks on every season-match request)."""
    path = Path(path)
    mtime = path.stat().st_mtime_ns
    hit = _cached.get(str(path))
    if hit is None or hit[0] != mtime:
        hit = (mtime, load_league(path))
        _cached[str(path)] = hit
    return hit[1]
