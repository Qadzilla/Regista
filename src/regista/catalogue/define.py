"""Define the catalogue once: 13 new competitions (clubs, squads, bios, hidden ratings, uploaded matches with uploader and
camera), five careers across competitions, and the England semi-pro men overlay. Committed as ``data/catalogue/``.

The England semi-pro men competition is the existing Regista League: ``data/season/league.json`` is never written here.
The index points at it and adds its catalogue labels (uploader and camera of its 30 fixtures) as an overlay.

Every draw comes from a ``regista.detmath.Random`` stream (its ``gauss`` gives the same bits on macOS and Linux), and
each competition has its own streams (design.md §4.1), so the definition regenerates byte for byte on any machine and
retuning one competition never moves another's people:

==========================================  ===============================================
names, nationalities, clubs and kits        ``Random(comp_seed)``
attributes (bio and hidden ratings)         ``Random(comp_seed * 1000 + 3)``
coverage (which fixtures were uploaded)     ``Random(comp_seed * 1000 + 7)``
uploader and camera                         ``Random(comp_seed * 1000 + 11)``
England overlay                             ``Random(CATALOGUE_SEED * 1000 + 1)``
careers                                     ``Random(CATALOGUE_SEED * 1000 + 13)``
==========================================  ===============================================

``comp_seed = 202700 + k`` (k = 1..13 in ``taxonomy.COMPETITIONS`` order) and match n of a competition (1-based, in
round order) has seed ``comp_seed * 100 + n``. One deviation from design.md §4.2, recorded here: a person's nationality
is drawn with the name (names stream), so the name comes from that nationality's pool; the attribute stream draws the
rest of the bio in the league's order.

Names stay unique across the whole catalogue and the league: a name already taken is drawn again. That is the one way
an earlier competition can touch a later one, and only on a repeated name (competitions are defined in table order).
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
from pathlib import Path
from typing import Any

from regista.catalogue import clubs as club_data
from regista.catalogue.names import pools
from regista.catalogue.taxonomy import (AS_OF, BIRTH_CUTOFFS, BY_ID, CAMERA_WEIGHTS, COMPETITIONS, ENGLAND_ID, SEASON,
                                        TEAM_UPLOAD_P, Competition, Level, levels_public)
from regista.detmath import Random
from regista.season import league as L
from regista.synth.generator import BENCH, FORMATION_433, GENERATOR_NAME, LEAGUE_GENERATOR_VERSION

Record = dict[str, Any]

CATALOGUE_NAME = "Regista catalogue"
CATALOGUE_SEED = 2027
CATALOGUE_VERSION = 1
COMP_SEED_BASE = 202700
ATTRIBUTES_VERSION = 1
NOTE = ("Synthetic: invented players, clubs and competition names. Countries, regions and levels are classification "
        "labels. Camera type is a label: every match is rendered the same way.")
COMPETITIONS_DIR = "data/catalogue/competitions"

# Kit distinctness, by the league's own spread (measured on league.json's six clubs with the redmean colour distance:
# primaries at least 156 apart, keepers at least 150 from every primary and 125 from each other).
PRIMARY_MIN, GK_PRIMARY_MIN, GK_GK_MIN = 150.0, 150.0, 120.0

# The five careers (design.md §2.4): (source, destination, roles, the person's nationality or None, story, when the
# person can play in the destination). ``BEFORE_SEASON``: only before the source competition's season starts (a student
# at home in the summer), so every uploaded destination match of their club is dated before the source's window opens.
# ``ANY``: any matchday (the two Spanish juveniles play both on weekends of the same autumn). The catalogue is dated
# ``taxonomy.AS_OF``, so no story speaks of matches after it.
ANY, BEFORE_SEASON = "any", "before_season"
CAREERS: list[tuple[str, str, tuple[str, ...], str | None, str, str]] = [
    ("co_esp_u19", "co_esp_am_men", ("ST",), None,
     "a juvenil striker who, while still eligible for the juvenil, also plays for the senior amateur club his academy "
     "side is affiliated with, in the same territorial federation (Valencian Community)", ANY),
    ("co_esp_u19", "co_esp_am_men", ("CM",), None,
     "a juvenil midfielder who, while still eligible for the juvenil, also plays for the senior amateur club his academy "
     "side is affiliated with, in the same territorial federation (Valencian Community)", ANY),
    ("co_usa_col_women", "co_eng_sp_women", ("W",), "England",
     "an English student-athlete at a US college who is also registered with her home club in Yorkshire: she played its "
     "opening match in August, before she flew out for the college season", BEFORE_SEASON),
    ("co_usa_col_men", "co_ger_sp_men", ("CB",), "Germany",
     "a German student-athlete who played for a semi-pro side at home in August, before the college season",
     BEFORE_SEASON),
    ("co_usa_col_men", "co_mex_am_men", ("ST", "W"), "Mexico",
     "a Mexican student-athlete who played for an amateur side at home in August, before the college season",
     BEFORE_SEASON),
]


def comp_seed(c: Competition) -> int:
    return COMP_SEED_BASE + c.k


# ---------------------------------------------------------------------------------------------------------- colours

def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def colour_distance(a: str, b: str) -> float:
    """The "redmean" approximation of perceived colour difference (0 for the same colour, about 765 black to white)."""
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    rm = (r1 + r2) / 2
    return ((2 + rm / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2 + (2 + (255 - rm) / 256) * (b1 - b2) ** 2) ** 0.5


def _kits(rng: Random, n: int) -> list[Record]:
    """n kits: primaries drawn until every pair is far apart, then keeper colours drawn (in a shuffled order) from those
    far from every primary and from each other; if too few qualify, the primaries are drawn again."""
    for _ in range(10_000):
        prim = rng.sample(club_data.PRIMARIES, n)
        if min(colour_distance(a, b) for a, b in itertools.combinations(prim, 2)) < PRIMARY_MIN:
            continue
        cands = [g for g in club_data.GK_COLOURS if min(colour_distance(g, p) for p in prim) >= GK_PRIMARY_MIN]
        rng.shuffle(cands)
        gks: list[str] = []
        for g in cands:
            if all(colour_distance(g, h) >= GK_GK_MIN for h in gks):
                gks.append(g)
        if len(gks) >= n:
            gks = gks[:n]
            break
    else:  # pragma: no cover - the palettes always allow six
        raise RuntimeError("no distinct kits")
    out = []
    for p, g in zip(prim, gks):
        sec = max(club_data.SECONDARIES, key=lambda s: colour_distance(s, p))   # the most contrasting trim, no draw
        out.append({"primary": p, "secondary": sec, "gk": g})
    return out


# ---------------------------------------------------------------------------------------------------------- squads

SLOTS = [(pos, num, True) for pos, num, _x, _y in FORMATION_433] + [(pos, num, False) for pos, num in BENCH]


def _draw_name(rng: Random, nationality: str, gender: str, used: set[str]) -> str:
    given, surnames = pools(nationality, gender)
    for _ in range(10_000):
        name = f"{rng.choice(given)} {rng.choice(surnames)}"
        if name not in used:
            used.add(name)
            return name
    raise RuntimeError(f"name pool for {nationality} {gender} exhausted")  # pragma: no cover


def _clubs_and_names(c: Competition, used: set[str]) -> list[Record]:
    """Clubs with kits, and every squad slot with a nationality and a name (the names stream)."""
    rng = Random(comp_seed(c))
    rows = club_data.CLUBS[c.competition_id]
    kits = _kits(rng, len(rows))
    nat_names = [n for n, _w in c.nationalities]
    nat_weights = [w for _n, w in c.nationalities]
    out = []
    for (slug, name, short, town, ground), kit in zip(rows, kits):
        squad = []
        for position, number, starter in SLOTS:
            nat = rng.choices(nat_names, nat_weights)[0]
            squad.append({"global_id": f"pl_{short.lower()}_{number:02d}", "name": _draw_name(rng, nat, c.gender, used),
                          "kit_number": number, "position": position, "starter": starter, "nationality": nat})
        out.append({"club_id": f"cl_{slug}", "name": name, "short_name": short, "city": town, "ground": ground, "kit": kit,
                    "squad": squad})
    return out


def _age(rng: Random, lv: Level, role: str) -> int:
    lo, hi = lv.age_range
    mode = lv.age_mode_gk_cb if (lv.age_mode_gk_cb is not None and role in ("GK", "CB")) else lv.age_mode
    return int(L._clamp(round(rng.triangular(lo, hi + 0.49, mode)), lo, hi))


def height_range(lv: Level) -> tuple[int, int]:
    return L.HEIGHT_RANGE[0] + lv.height_shift, L.HEIGHT_RANGE[1] + lv.height_shift


def speed_range(lv: Level, band: str) -> tuple[float, float]:
    lo, hi = L.SPEED_RANGE[band]
    return lo * lv.speed_mult, hi * lv.speed_mult


def accel_range(lv: Level, band: str) -> tuple[float, float]:
    lo, hi = L.ACCEL_RANGE[band]
    return lo * lv.accel_mult, hi * lv.accel_mult


def rating_cap(lv: Level) -> int:
    return L.NATURAL_CAP + lv.skill_offset


def standout_cap(lv: Level) -> int:
    return L.STANDOUT_CAP + lv.skill_offset


def person_attributes(rng: Random, p: Record, lv: Level) -> tuple[Record, Record]:
    """(bio without nationality, hidden attributes) for one squad entry: the league's ``_person_attributes`` with the
    level's scale applied (design.md §4.2). The draws happen in a fixed order, so the catalogue regenerates exactly."""
    kit = int(p["kit_number"])
    role = L.role_of(kit)
    quality = rng.gauss(L.STARTER_EDGE / 2 if p["starter"] else -L.STARTER_EDGE / 2, 1.0)
    age = _age(rng, lv, role)
    dob = dt.date(L.AGE_ON.year - age, L.AGE_ON.month, L.AGE_ON.day) - dt.timedelta(days=rng.randrange(0, 365))
    h_mean, h_sd = L.ROLE_HEIGHT[role]
    h_mean += lv.height_shift
    height = int(L._clamp(round(rng.gauss(h_mean, h_sd)), *height_range(lv)))
    names = L.RATINGS + (L.GK_RATINGS if role == "GK" else ())
    means = L.ROLE_MEANS[role]
    own = [rng.gauss(0.0, 1.0) for _ in names]
    w_own = (1 - L.QUALITY_SHARE ** 2) ** 0.5
    ratings = {n: means[i] + lv.skill_offset + (lv.stamina_offset if n == "stamina" else 0)
               + L.RATING_SD * (L.QUALITY_SHARE * quality + w_own * own[i]) for i, n in enumerate(names)}
    ratings["aerial"] += 0.9 * (height - h_mean)              # taller players win more headers (within the level)
    ratings["stamina"] -= 0.8 * max(0, age - 30)              # and stamina fades after 30
    attrs: Record = {n: int(L._clamp(round(v), 1, rating_cap(lv))) for n, v in ratings.items()}
    s_mean, s_sd = L.ROLE_SPEED[role]
    band = "GK" if role == "GK" else "outfield"
    speed = rng.gauss(s_mean * lv.speed_mult, s_sd * lv.speed_mult) - 0.05 * (height - h_mean) - 0.12 * max(0, age - 29)
    speed = L._clamp(speed, *speed_range(lv, band))
    # the league's formula on the speed in the league's frame (speed / speed_mult), then the level's multiplier
    accel = (3.0 + 0.22 * (speed / lv.speed_mult - L.SPEED_RANGE["outfield"][0]) + rng.gauss(0.0, 0.25)
             - (0.5 if role == "GK" else 0.0)) * lv.accel_mult
    accel = L._clamp(accel, *accel_range(lv, band))
    attrs["top_speed_kmh"] = round(speed, 1)
    attrs["acceleration_ms2"] = round(accel, 2)
    bio = {"date_of_birth": dob.isoformat(), "height_cm": height, "preferred_foot": L._foot(rng, kit)}
    return bio, attrs


def within_cutoff(date_of_birth: str, competition_id: str) -> str:
    """A youth competition's date of birth moved forward whole years until it meets the competition's birth-date rule
    (``taxonomy.BIRTH_CUTOFFS``). No random draw: the attribute stream is untouched, and dates of birth never reach the
    generator, so no rating and no match moves."""
    cut = BIRTH_CUTOFFS.get(competition_id)
    if not cut:
        return date_of_birth
    dob, earliest = dt.date.fromisoformat(date_of_birth), dt.date.fromisoformat(cut[0])
    while dob < earliest:
        dob = dob.replace(year=dob.year + 1, day=min(dob.day, 28) if (dob.month, dob.day) == (2, 29) else dob.day)
    return dob.isoformat()


def _assign_attributes(c: Competition, clubs: list[Record]) -> set[str]:
    """Bio and hidden ratings for every squad entry (in place), then one standout per ``STANDOUTS`` pair within the
    competition. Returns the standouts' global ids. No star: Femi Toure stays the one star (England)."""
    lv = c.level
    rng = Random(comp_seed(c) * 1000 + 3)
    everyone = [p for cl in clubs for p in cl["squad"]]
    for p in everyone:
        bio, attrs = person_attributes(rng, p, lv)
        bio["date_of_birth"] = within_cutoff(bio["date_of_birth"], c.competition_id)
        nat = p.pop("nationality")
        p.update(role=L.role_of(p["kit_number"]), **bio, nationality=nat, attributes=attrs)
    standouts: set[str] = set()
    for role, key in L.STANDOUTS:
        group = sorted((p for p in everyone if p["role"] == role and p["starter"]),
                       key=lambda p: (-p["attributes"][key], p["global_id"]))
        best, runner_up = group[0], group[1]
        best["attributes"][key] = min(standout_cap(lv), max(best["attributes"][key], runner_up["attributes"][key] + L.STANDOUT_LIFT))
        standouts.add(best["global_id"])
    return standouts


# ---------------------------------------------------------------------------------------------------------- matches

def round_robin(n: int) -> list[list[tuple[int, int]]]:
    """A double round robin of n clubs (the league's circle method; an odd n gets a bye each round)."""
    m = n + (n % 2)
    first = [[(a, b) for a, b in pairs if a < n and b < n] for pairs in L._round_robin(m)]
    return first + [[(b, a) for a, b in pairs] for pairs in first]


def round_dates(c: Competition, rounds: int) -> list[dt.date]:
    """One matchday a round, evenly spaced in whole weeks across the country's calendar window."""
    start, end = (dt.date.fromisoformat(d) for d in c.window)
    weeks = max(1, ((end - start).days // 7) // max(1, rounds - 1))
    return [start + dt.timedelta(days=7 * weeks * i) for i in range(rounds)]


def latest_dates(c: Competition, clubs: list[Record], careers: list[Record]) -> dict[str, str]:
    """{club_id: the last date a match of that club can be uploaded}: ``AS_OF`` for every club, and for the destination
    club of a ``BEFORE_SEASON`` career the day before the source competition's season starts."""
    out = {cl["club_id"]: AS_OF for cl in clubs}
    rule = {(src, dst): when for src, dst, _r, _n, _s, when in CAREERS}
    for car in careers:
        src_id, dst_id = car["competitions"]
        if dst_id == c.competition_id and rule.get((src_id, dst_id)) == BEFORE_SEASON:
            opens = dt.date.fromisoformat(BY_ID[src_id].window[0])
            out[car["clubs"][1]] = min(out[car["clubs"][1]], (opens - dt.timedelta(days=1)).isoformat())
    return out


def _coverage(c: Competition, clubs: list[Record], latest: dict[str, str] | None = None) -> list[Record]:
    """The uploaded matches: chosen at random from the double round robin's fixtures already played by ``AS_OF`` (and, for
    a club in ``latest``, by its own last date), every club in at least one (coverage stream). The whole round robin is
    shuffled first, then the unplayed fixtures are dropped, so the draw does not depend on the date."""
    rng = Random(comp_seed(c) * 1000 + 7)
    rounds = round_robin(len(clubs))
    dates = round_dates(c, len(rounds))
    latest = latest or {}
    all_fx = [(r, k, h, a) for r, pairs in enumerate(rounds, start=1) for k, (h, a) in enumerate(pairs)]
    order = list(all_fx)
    rng.shuffle(order)

    def played(fx: tuple[int, int, int, int]) -> bool:
        day = dates[fx[0] - 1].isoformat()
        return day <= AS_OF and all(day <= latest.get(clubs[i]["club_id"], AS_OF) for i in (fx[2], fx[3]))

    order = [fx for fx in order if played(fx)]
    chosen: list[tuple[int, int, int, int]] = []
    covered: set[int] = set()
    for fx in order:  # first, fixtures that bring a club not yet seen
        if len(covered) == len(clubs):
            break
        if fx[2] not in covered or fx[3] not in covered:
            chosen.append(fx)
            covered |= {fx[2], fx[3]}
    for fx in order:  # then the rest of the uploads, in the shuffled order
        if len(chosen) >= c.uploads:
            break
        if fx not in chosen:
            chosen.append(fx)
    if len(chosen) != c.uploads or len(covered) != len(clubs):
        raise RuntimeError(f"{c.competition_id}: {len(chosen)} uploads covering {len(covered)} clubs by {AS_OF}, "
                           f"want {c.uploads} covering {len(clubs)}")
    out = []
    for n, (r, _k, h, a) in enumerate(sorted(chosen), start=1):
        home, away = clubs[h], clubs[a]
        out.append({"match_id": f"cm_{c.code}_{r:02d}_{home['short_name'].lower()}_{away['short_name'].lower()}", "round": r,
                    "date": dates[r - 1].isoformat(), "home": home["club_id"], "away": away["club_id"],
                    "seed": comp_seed(c) * 100 + n})
    return out


def _upload(rng: Random, tier: str, home: Record, away: Record) -> tuple[Record, str]:
    """(uploader, camera) for one match: a team account, or a starter of either side (starters always play)."""
    weights = CAMERA_WEIGHTS[tier]
    camera = rng.choices(list(weights), list(weights.values()))[0]
    team = rng.random() < TEAM_UPLOAD_P[tier]
    side = home if rng.random() < 0.5 else away
    if team:
        return {"type": "team", "club_id": side["club_id"]}, camera
    starters = [p for p in side["squad"] if p["starter"]]
    p = rng.choice(starters)
    return {"type": "player", "global_id": p["global_id"], "club_id": side["club_id"]}, camera


def _uploads(c: Competition, clubs: list[Record], fixtures: list[Record]) -> None:
    rng = Random(comp_seed(c) * 1000 + 11)
    by_id = {cl["club_id"]: cl for cl in clubs}
    for fx in fixtures:
        fx["uploader"], fx["camera"] = _upload(rng, c.tier, by_id[fx["home"]], by_id[fx["away"]])


def england_overlay(league: Record) -> dict[str, Record]:
    """Uploader and camera of each of the Regista League's 30 fixtures (league.json itself is never written)."""
    rng = Random(CATALOGUE_SEED * 1000 + 1)
    by_id = L.club_by_id(league)
    out = {}
    for fx in league["fixtures"]:
        uploader, camera = _upload(rng, BY_ID[ENGLAND_ID].tier, by_id[fx["home"]], by_id[fx["away"]])
        out[fx["match_id"]] = {"uploader": uploader, "camera": camera}
    return out


# ---------------------------------------------------------------------------------------------------------- careers

PERSON_KEYS = ("global_id", "name", "role", "date_of_birth", "height_cm", "preferred_foot", "nationality", "attributes")


def _careers(comps: dict[str, Record], standouts: dict[str, set[str]], used: set[str]) -> list[Record]:
    """Five people who play in two competitions (career stream). The source person keeps their global id, bio and ratings;
    the destination slot (a starter in the same role, never a standout) was drawn like any other slot, so no other
    player's draws shift, and is then overwritten by the person, who takes the destination club's kit number."""
    rng = Random(CATALOGUE_SEED * 1000 + 13)
    taken: set[str] = set()
    out = []
    for src_id, dst_id, roles, nationality, story, _when in CAREERS:
        src, dst = comps[src_id], comps[dst_id]
        cands = [(cl, p) for cl in src["clubs"] for p in cl["squad"]
                 if p["starter"] and p["role"] in roles and p["global_id"] not in taken
                 and (BY_ID[src_id].age_group != "U19" or L.age_on(p["date_of_birth"]) >= 17)]
        src_club, person = rng.choice(cands)
        if nationality and person["nationality"] != nationality:
            used.discard(person["name"])
            person["nationality"] = nationality
            person["name"] = _draw_name(rng, nationality, BY_ID[src_id].gender, used)
        slots = [(cl, p) for cl in dst["clubs"] for p in cl["squad"]
                 if p["starter"] and p["role"] == person["role"] and p["global_id"] not in standouts[dst_id]]
        dst_club, slot = rng.choice(slots)
        used.discard(slot["name"])
        for key in PERSON_KEYS:
            slot[key] = person[key] if key != "attributes" else dict(person["attributes"])
        taken.add(person["global_id"])
        out.append({"global_id": person["global_id"], "name": person["name"], "competitions": [src_id, dst_id],
                    "clubs": [src_club["club_id"], dst_club["club_id"]], "story": story})
    return out


def _career_dates(comps: dict[str, Record], careers: list[Record]) -> None:
    """A career person never plays two matches on one date: a destination match on a source match's date moves to the
    next day, or to the day before when the next day is after ``AS_OF`` (a club plays once a round and rounds are a week
    or more apart, so no club is double-booked)."""
    for car in careers:
        src_id, dst_id = car["competitions"]
        src_club, dst_club = car["clubs"]
        busy = {fx["date"] for fx in comps[src_id]["fixtures"] if src_club in (fx["home"], fx["away"])}
        for fx in comps[dst_id]["fixtures"]:
            if dst_club in (fx["home"], fx["away"]):
                day = dt.date.fromisoformat(fx["date"])
                step = dt.timedelta(days=1 if (day + dt.timedelta(days=1)).isoformat() <= AS_OF else -1)
                while day.isoformat() in busy:
                    day += step
                fx["date"] = day.isoformat()
                busy.add(fx["date"])


# ---------------------------------------------------------------------------------------------------------- the whole

def competition_file(c: Competition, clubs: list[Record], fixtures: list[Record]) -> Record:
    lv = c.level
    return {"league": c.name, "season": SEASON, "seed": comp_seed(c), "competition": c.labels(),
            "generator": {"name": GENERATOR_NAME, "version": LEAGUE_GENERATOR_VERSION, "profile": L.PROFILE,
                          "minutes": L.MATCH_MINUTES, "periods": 2, "track_hz": L.TRACK_HZ},
            "attributes": {"version": ATTRIBUTES_VERSION, "seed": comp_seed(c) * 1000 + 3, "age_on": L.AGE_ON.isoformat(),
                           "hidden": True, "scales": "docs/catalogue/build/design.md#43-level-scales",
                           "note": "Synthetic players. Ratings drive the generator and are never shown."},
            "level": lv.record(), "clubs": clubs, "fixtures": fixtures}


def new_catalogue(league: Record) -> tuple[Record, dict[str, Record]]:
    """(index, {competition_id: competition file}) for the 13 new competitions, given the Regista League (read only)."""
    used = {p["name"] for cl in league["clubs"] for p in cl["squad"]}
    comps: dict[str, Record] = {}
    standouts: dict[str, set[str]] = {}
    for c in COMPETITIONS:
        if c.competition_id == ENGLAND_ID:
            continue
        clubs = _clubs_and_names(c, used)
        standouts[c.competition_id] = _assign_attributes(c, clubs)
        comps[c.competition_id] = competition_file(c, clubs, [])
    careers = _careers(comps, standouts, used)
    for c in COMPETITIONS:
        if c.competition_id == ENGLAND_ID:
            continue
        comp = comps[c.competition_id]
        comp["fixtures"] = _coverage(c, comp["clubs"], latest_dates(c, comp["clubs"], careers))
        _uploads(c, comp["clubs"], comp["fixtures"])
    _career_dates(comps, careers)
    entries = []
    for c in COMPETITIONS:
        e: Record = {**c.labels(), "teams": c.teams, "uploaded_matches": c.uploads}
        if c.competition_id == ENGLAND_ID:
            e.update(source="league", path="data/season/league.json", coverage="full", uploads=england_overlay(league))
        else:
            e.update(source="catalogue", path=f"{COMPETITIONS_DIR}/{c.competition_id}.json", coverage="sparse")
        entries.append(e)
    index = {"catalogue": CATALOGUE_NAME, "season": SEASON, "as_of": AS_OF, "seed": CATALOGUE_SEED, "version": CATALOGUE_VERSION,
             "generator": {"name": GENERATOR_NAME, "version": LEAGUE_GENERATOR_VERSION}, "note": NOTE,
             "levels": levels_public(), "competitions": entries, "careers": careers}
    return index, comps


def dumps(obj: Record) -> str:
    return json.dumps(obj, indent=1) + "\n"


def save_catalogue(index: Record, comps: dict[str, Record], root: Path | str = ".") -> list[Path]:
    """Write ``data/catalogue/catalogue.json`` and the competition files under ``root`` (the repo root)."""
    root = Path(root)
    out = [root / "data" / "catalogue" / "catalogue.json"]
    out[0].parent.mkdir(parents=True, exist_ok=True)
    out[0].write_text(dumps(index))
    for e in index["competitions"]:
        if e["source"] == "catalogue":
            p = root / e["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(dumps(comps[e["competition_id"]]))
            out.append(p)
    return out
