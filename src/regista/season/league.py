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

from regista.synth.generator import (BENCH, FIRST_NAMES, FORMATION_433, GENERATOR_NAME, LAST_NAMES, LEAGUE_GENERATOR_VERSION,
                                     ROLE_OF_KIT)

Record = dict[str, Any]

LEAGUE_NAME = "Regista League"
SEASON = "2026/27"
DEFAULT_SEED = 2026
MATCH_MINUTES = 15.0   # per half: 30-minute matches, about 300 minutes per player over the season
PROFILE = "league"     # "realistic" retuned for two halves and player ratings (regista.synth.generator.PROFILES)
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


# ---------------------------------------------------------------------------- players: bio and hidden ratings
#
# Every league player gets a public bio (date of birth, height, preferred foot, nationality) and hidden ratings that the
# generator reads (``attributes``). Scouts must judge players from what they do: the ratings never leave this module
# through ``people()``, and no API or page shows them. Scales are documented in data/synthetic/README.md ("League
# players"). Drawn from their own random stream (``ATTRIBUTE_SEED_OFFSET``), so names and fixtures are unchanged.

ATTRIBUTES_VERSION = 2                 # 2: the star's ratings (STAR_RATINGS), finishing 99 and dribbling 72; 1: finishing 97
ATTRIBUTE_SEED_OFFSET = 1_000_003      # the attribute stream is random.Random(league seed + this)
AGE_ON = dt.date(2026, 8, 1)           # age at season start, FBref's convention for an August-May league
AGE_RANGE = (17, 35)
STAR = "pl_bro_09"                     # Femi Toure: the league's best finisher among forwards (decided by Zaid)
# The star's ratings (attributes version 2, Zaid's decision 2026-10-24: make him clearly the league's star). Set after the
# draws and the standouts, so no other player's ratings move. Finishing 99 is the league's only 99 (standouts stop at
# STANDOUT_CAP): he converts more of his chances. Dribbling 72 lifts his drawn 66, below the striker mean of 70, to a
# little above it: he carries the ball toward goal more often and is dispossessed less, so more of his possessions end in
# a shot from close in. Chosen with the realism bands in view: over six pooled seasons his lead over the next player in
# npxG per 90 must stay inside the leader_npxg_gap band (regista.synth.report), and the Premier League's best was 1.28
# times the next (docs/scout-terminal/build/femi-edge.md has the numbers and how this pair was chosen).
STAR_RATINGS = {"finishing": 99, "dribbling": 72}

# The 4-3-3 slot behind each kit number (the formation never changes): starters 1-11, bench 13-22. ROLE_OF_KIT lives in
# the generator, which reads it in league mode.
ROLE_NAMES = {"GK": "goalkeeper", "FB": "full-back", "CB": "centre-back", "DM": "holding midfielder", "CM": "central midfielder",
              "AM": "attacking midfielder", "W": "winger", "ST": "striker"}

RATINGS = ("finishing", "passing", "vision", "dribbling", "defending", "aerial", "stamina")  # 1-99, every player
GK_RATINGS = ("shot_stopping", "handling", "distribution")                                # 1-99, goalkeepers only
PHYSICAL = ("top_speed_kmh", "acceleration_ms2")                                         # physical units, every player
ATTRIBUTE_KEYS = (*RATINGS, *GK_RATINGS, *PHYSICAL)
BIO_KEYS = ("date_of_birth", "height_cm", "preferred_foot", "nationality")

# Role means on the 1-99 scale, in RATINGS order then GK_RATINGS. Shaped by position: centre-backs defend and win headers,
# wingers dribble, holding midfielders defend and pass, strikers finish. Within a role every rating spreads with
# RATING_SD around its mean (a shared quality draw plus the rating's own), so two players in one role really differ.
ROLE_MEANS: dict[str, tuple[int, ...]] = {
    #      fin pas vis dri def aer sta | stop hand dist
    "GK": (15, 52, 40, 25, 30, 60, 55, 72, 70, 64),
    "FB": (42, 66, 58, 64, 68, 58, 78),
    "CB": (35, 60, 48, 45, 76, 77, 68),
    "DM": (48, 74, 66, 58, 74, 64, 76),
    "CM": (58, 74, 70, 66, 62, 58, 78),
    "AM": (66, 74, 77, 74, 45, 48, 70),
    "W":  (66, 66, 66, 78, 40, 46, 72),
    "ST": (74, 60, 60, 68, 36, 68, 68),
}
RATING_SD = 7.0
QUALITY_SHARE = 0.55     # how much of a rating's spread is the player's overall quality (the rest is the rating's own)
STARTER_EDGE = 0.35      # starters' quality sits this many SDs above the bench's on average
# Height (mean, sd) in cm by role; top speed (mean, sd) in km/h by role.
ROLE_HEIGHT = {"GK": (190, 4), "CB": (188, 4), "FB": (178, 5), "DM": (182, 5), "CM": (179, 5), "AM": (176, 5), "W": (175, 5),
               "ST": (183, 6)}
ROLE_SPEED = {"GK": (28.5, 1.8), "CB": (33.0, 1.2), "FB": (34.4, 1.2), "DM": (32.0, 1.2), "CM": (32.6, 1.2),
              "AM": (33.0, 1.2), "W": (35.0, 1.2), "ST": (33.8, 1.2)}
# Premier League 2024-25 top speeds (Opta, The Analyst): outfielders 29.4 (slowest) to just over 37 km/h (fastest);
# goalkeepers 23.6 to 32.7 km/h. Ratings never leave these ranges.
SPEED_RANGE = {"outfield": (29.4, 37.4), "GK": (23.6, 32.7)}
ACCEL_RANGE = {"outfield": (3.0, 5.2), "GK": (2.6, 4.2)}   # peak acceleration, m/s^2 (>3 is "high" for Wyscout)
HEIGHT_RANGE = (163, 201)
# A few clear standouts per position group: (role, rating) pairs whose best player is lifted well clear of the rest.
STANDOUTS = [("GK", "shot_stopping"), ("CB", "aerial"), ("CB", "defending"), ("FB", "stamina"), ("DM", "defending"),
             ("CM", "passing"), ("AM", "vision"), ("W", "dribbling"), ("ST", "aerial")]
STANDOUT_LIFT = 10       # the standout sits this far above the next best starter in the role (at most STANDOUT_CAP)
NATURAL_CAP, STANDOUT_CAP = 95, 97   # drawn ratings stop at 95; only standouts and the star go above
# Nationalities: synthetic players, so a plausible Premier League-like spread (about a third home-grown), never real bios.
NATIONALITIES: list[tuple[str, int]] = [
    ("England", 34), ("France", 7), ("Spain", 5), ("Brazil", 5), ("Portugal", 4), ("Netherlands", 4), ("Scotland", 3),
    ("Ireland", 3), ("Wales", 3), ("Germany", 3), ("Belgium", 3), ("Nigeria", 3), ("Ghana", 2), ("Senegal", 2),
    ("Ivory Coast", 2), ("Argentina", 2), ("Denmark", 2), ("Norway", 2), ("Sweden", 2), ("Morocco", 2), ("Japan", 1),
    ("South Korea", 1), ("United States", 1), ("Colombia", 1), ("Uruguay", 1), ("Croatia", 1), ("Poland", 1),
    ("Switzerland", 1), ("Italy", 1), ("Jamaica", 1),
]


def role_of(kit_number: int) -> str:
    """The detailed role of a kit number in the fixed 4-3-3 (``ROLE_OF_KIT``)."""
    return ROLE_OF_KIT[int(kit_number)]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _foot(rng: random.Random, kit: int) -> str:
    """About 75% right, 20% left, 5% both overall; left-backs (3) and left wingers (11) lean left."""
    left = {3: 0.55, 11: 0.35}.get(kit, 0.14)
    r = rng.random()
    return "both" if r < 0.05 else "left" if r < 0.05 + left else "right"


def _age(rng: random.Random, role: str) -> int:
    """Ages 17-35 at season start, most players 22-30; keepers and centre-backs a little older (they peak later)."""
    mode = 28 if role in ("GK", "CB") else 26
    return int(_clamp(round(rng.triangular(AGE_RANGE[0], AGE_RANGE[1] + 0.49, mode)), *AGE_RANGE))


def _person_attributes(rng: random.Random, p: Record) -> tuple[Record, Record]:
    """(bio, attributes) for one squad entry; the draws happen in a fixed order so the league regenerates exactly."""
    kit = int(p["kit_number"])
    role = role_of(kit)
    quality = rng.gauss(STARTER_EDGE / 2 if p["starter"] else -STARTER_EDGE / 2, 1.0)
    age = _age(rng, role)
    dob = dt.date(AGE_ON.year - age, AGE_ON.month, AGE_ON.day) - dt.timedelta(days=rng.randrange(0, 365))
    h_mean, h_sd = ROLE_HEIGHT[role]
    height = int(_clamp(round(rng.gauss(h_mean, h_sd)), *HEIGHT_RANGE))
    names = RATINGS + (GK_RATINGS if role == "GK" else ())
    means = ROLE_MEANS[role]
    own = [rng.gauss(0.0, 1.0) for _ in names]
    w_own = (1 - QUALITY_SHARE ** 2) ** 0.5
    ratings = {n: means[i] + RATING_SD * (QUALITY_SHARE * quality + w_own * own[i]) for i, n in enumerate(names)}
    ratings["aerial"] += 0.9 * (height - h_mean)              # taller players win more headers
    ratings["stamina"] -= 0.8 * max(0, age - 30)              # and stamina fades after 30
    attrs: Record = {n: int(_clamp(round(v), 1, NATURAL_CAP)) for n, v in ratings.items()}
    s_mean, s_sd = ROLE_SPEED[role]
    band = "GK" if role == "GK" else "outfield"
    speed = rng.gauss(s_mean, s_sd) - 0.05 * (height - h_mean) - 0.12 * max(0, age - 29)
    speed = _clamp(speed, *SPEED_RANGE[band])
    accel = _clamp(3.0 + 0.22 * (speed - SPEED_RANGE["outfield"][0]) + rng.gauss(0.0, 0.25) - (0.5 if role == "GK" else 0.0),
                   *ACCEL_RANGE[band])
    attrs["top_speed_kmh"] = round(speed, 1)
    attrs["acceleration_ms2"] = round(accel, 2)
    bio = {"date_of_birth": dob.isoformat(), "height_cm": height, "preferred_foot": _foot(rng, kit),
           "nationality": rng.choices([n for n, _w in NATIONALITIES], [w for _n, w in NATIONALITIES])[0]}
    return bio, attrs


def assign_attributes(clubs: list[Record], seed: int = DEFAULT_SEED) -> None:
    """Give every squad entry (in place) its role, bio and hidden ``attributes``, then lift one standout per
    ``STANDOUTS`` pair and give ``STAR`` his ratings (``STAR_RATINGS``: the best finisher among forwards). Seeded: same squads + seed, same players."""
    rng = random.Random(seed + ATTRIBUTE_SEED_OFFSET)
    everyone = [p for c in clubs for p in c["squad"]]
    for p in everyone:
        bio, attrs = _person_attributes(rng, p)
        p.update(role=role_of(p["kit_number"]), **bio, attributes=attrs)
    for role, key in STANDOUTS:  # the best in the role at this rating, lifted clear of the next best
        group = sorted((p for p in everyone if p["role"] == role and p["starter"]), key=lambda p: (-p["attributes"][key], p["global_id"]))
        best, runner_up = group[0], group[1]
        best["attributes"][key] = min(STANDOUT_CAP, max(best["attributes"][key], runner_up["attributes"][key] + STANDOUT_LIFT))
    star = next((p for p in everyone if p["global_id"] == STAR), None)
    if star is not None:  # the striker standout: the league's best finisher by a distance (since generator 0.4.0
        # finishing is worth a realistic edge, about a quarter over xG, so the star needs a clear one), plus STAR_RATINGS
        for key, value in STAR_RATINGS.items():
            star["attributes"][key] = max(star["attributes"][key], value)


def age_on(date_of_birth: str, on: dt.date = AGE_ON) -> int:
    """Whole years on ``on`` (default: the season's start, 1 August 2026)."""
    b = dt.date.fromisoformat(date_of_birth)
    return on.year - b.year - ((on.month, on.day) < (b.month, b.day))


def bio(person: Record) -> Record:
    """The public facts about a player: age (at season start), height, preferred foot, nationality, date of birth.
    Never the ratings. Empty values (None) for people without a bio (a league file from before attributes)."""
    dob = person.get("date_of_birth")
    return {"age": age_on(dob) if dob else None, "date_of_birth": dob, "height_cm": person.get("height_cm"),
            "preferred_foot": person.get("preferred_foot"), "nationality": person.get("nationality")}


def player_attributes(league: Record) -> dict[str, Record]:
    """global id -> hidden ratings (``attributes``), for the generator only. Never serve this."""
    return {p["global_id"]: dict(p["attributes"]) for c in league["clubs"] for p in c["squad"] if "attributes" in p}


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
    assign_attributes(clubs, seed)  # its own random stream: names and fixtures are what they were before attributes
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
            "generator": {"name": GENERATOR_NAME, "version": LEAGUE_GENERATOR_VERSION, "profile": PROFILE, "minutes": MATCH_MINUTES,
                          "periods": 2, "track_hz": TRACK_HZ},
            "attributes": {"version": ATTRIBUTES_VERSION, "seed": seed + ATTRIBUTE_SEED_OFFSET, "age_on": AGE_ON.isoformat(),
                           "scales": "data/synthetic/README.md#league-players-bio-and-hidden-ratings", "hidden": True,
                           "note": "Synthetic players. Ratings drive the generator and are never shown."},
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
    """global id -> person, with their club and bio. Without the hidden ratings: those are for the generator only
    (``player_attributes``)."""
    return {p["global_id"]: {**{k: v for k, v in p.items() if k != "attributes"}, "club_id": c["club_id"], "club": c["name"],
                             "short_name": c["short_name"], "kit": c["kit"]}
            for c in league["clubs"] for p in c["squad"]}


LEAGUE_FIELDS = ("attributes", "role", "height_cm", "preferred_foot")  # what league mode reads from a squad entry


def generate_kwargs(league: Record, fixture: Record, *, ratings: bool = True) -> Record:
    """Arguments for ``regista.synth.generator.generate`` that reproduce this fixture exactly. With ``ratings`` (the
    default) each squad member carries its hidden ratings, role, height and foot, which switches the generator into
    league mode; ``ratings=False`` gives ids and names only (the generator as it was before ratings). A catalogue
    competition file (``regista.catalogue``) carries a ``level`` whose ``style_offset`` re-centres team style on that
    level; ``league.json`` has none, so the Regista League's arguments are what they always were."""
    clubs = club_by_id(league)
    g = league["generator"]

    def member(p: Record) -> Record:
        out = {"global_id": p["global_id"], "name": p["name"]}
        if ratings and "attributes" in p:
            out.update({k: p[k] for k in LEAGUE_FIELDS if k in p})
        return out

    def side(club_id: str) -> Record:
        c = clubs[club_id]
        return {"name": c["name"], "short_name": c["short_name"], "kit": c["kit"], "club_id": c["club_id"],
                "squad": [member(p) for p in c["squad"]]}

    home = clubs[fixture["home"]]
    teams = [side(fixture["home"]), side(fixture["away"])]
    style_offset = (league.get("level") or {}).get("style_offset")
    if ratings and style_offset:  # a catalogue competition on another level (regista.catalogue); league.json has no level
        for t in teams:
            t["style_offset"] = dict(style_offset)
    return {"seed": fixture["seed"], "minutes": g["minutes"], "track_hz": g["track_hz"], "profile": g["profile"],
            "periods": g["periods"], "teams": teams, "match_id": fixture["match_id"],
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
