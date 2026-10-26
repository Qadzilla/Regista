"""The catalogue's classification: tiers, age groups, genders, the level scales, and the 14 competitions.

Regista's catalogue is uploaded footage below the professional line (docs/catalogue/build/design.md). Every competition
is classified on four axes; percentile pools are keyed on three of them, ``(tier, age_group, gender)``. ``professional``
is not a tier, by decision. The data stays synthetic: competition and club names are invented, countries, regions and
levels are classification labels only.

``LEVELS`` holds the scale each pool key applies to its players' hidden ratings and physical capacities, on one absolute
rating scale whose reference (offset 0) is the Regista League, now labelled England semi-pro men, and each level's
technical execution against absolute football (``execution``: the generator's ``LEAGUE["exec_*"]``), which ratings
cannot carry because a level's passers and markers drop together and cancel. Where a number comes
from is in ``source``: ``sourced`` (a published figure, cited in design.md §14), ``direction`` (the sign is sourced, the
size is Regista's) or ``assumption`` (Regista's definition of the level). The scales are hidden like the ratings they
shape: no API or page serves them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TIERS: list[tuple[str, str]] = [("semi_pro", "Semi-pro"), ("amateur", "Amateur"), ("college", "College / university"),
                                ("academy", "Academy / youth")]
AGE_GROUPS: list[tuple[str, str]] = [("senior", "Senior"), ("college", "College"), ("U20", "Under 20"), ("U19", "Under 19"),
                                     ("U18", "Under 18"), ("U17", "Under 17")]
GENDERS: list[tuple[str, str]] = [("men", "Men"), ("women", "Women")]
FORMAT = "11-a-side"
SEASON = "2026/27"
# The catalogue is a library of uploaded footage, so it holds matches already played: every uploaded match is dated on
# or before this day (``regista.catalogue.define`` draws uploads only from rounds played by then). Served as ``as_of``.
AS_OF = "2026-10-24"


@dataclass(frozen=True)
class Level:
    """The scale a pool key applies to a person's draws (design.md §4.3)."""

    key: str                       # "tier/age_group/gender"
    skill_offset: int              # added to every 1-99 rating mean (and to the rating clamps)
    stamina_offset: int            # added to stamina on top of skill_offset
    speed_mult: float              # top speed mean, sd and range
    accel_mult: float              # acceleration and its range
    height_shift: int              # cm, added to the role's mean height and the height range
    age_range: tuple[int, int]     # whole years on 1 August 2026
    age_mode: float                # the triangular draw's mode
    age_mode_gk_cb: float | None = None   # keepers and centre-backs peak later (senior men only, as the league)
    execution: float = 0.0         # technical execution below the reference, against absolute football (the generator's
                                   # LEAGUE["exec_*"]: pass completion, first touch, keeping the ball); 0 at the reference
    source: dict[str, str] = field(default_factory=dict)

    @property
    def tier(self) -> str:
        return self.key.split("/")[0]

    @property
    def age_group(self) -> str:
        return self.key.split("/")[1]

    @property
    def gender(self) -> str:
        return self.key.split("/")[2]

    def style_offset(self) -> dict[str, float]:
        """TEAM_STYLE's centres moved to this level: ``keep`` averages passing and vision (both carry ``skill_offset``),
        ``press`` averages defending and stamina (stamina also carries ``stamina_offset``). Empty at the reference."""
        if not (self.skill_offset or self.stamina_offset):
            return {}
        return {"keep": float(self.skill_offset), "press": self.skill_offset + self.stamina_offset / 2}

    def record(self) -> dict[str, Any]:
        """What a competition file records of the scale it was drawn with (hidden: never served)."""
        return {"key": self.key, "skill_offset": self.skill_offset, "stamina_offset": self.stamina_offset,
                "speed_mult": self.speed_mult, "accel_mult": self.accel_mult, "height_shift": self.height_shift,
                "age_range": list(self.age_range), "style_offset": self.style_offset(), "execution": self.execution}


_ASSUMED = "assumption"
# Technical execution (``Level.execution``): no source puts a number on it per level. The directions are sourced (women
# complete fewer passes and lose the ball more [S1, S12]; amateurs too [S10]; pass completion falls down England's
# professional standards [S13]); the women's size is sourced (8 points of pass completion at the World Cups [S12]); every
# other size is Regista's, set so the levels' pass completion lands on the targets in docs/catalogue/build/levels.md.
_EXEC = "direction [S10, S13]; size an assumption (docs/catalogue/build/levels.md)"
_EXEC_YOUTH = "assumption: no youth pass completion was found; rises with age (docs/catalogue/build/levels.md)"
_EXEC_WOMEN = "sourced gap [S1, S12]: 8 points of pass completion below same-tier men (docs/catalogue/build/levels.md)"
_YOUTH_SPEED = "interpolated in match peak speed between U17 [S5] and senior; direction [S7, S8]"
LEVELS: dict[str, Level] = {lv.key: lv for lv in [
    Level("semi_pro/senior/men", 0, 0, 1.00, 1.00, 0, (17, 35), 26, 28,
          source={"all": "reference: the Regista League's own scales, tuned against Premier League bands"}),
    Level("college/college/men", -3, 0, 0.99, 0.99, 0, (18, 23), 20, execution=1.4,
          source={"skill": _ASSUMED, "speed": _ASSUMED, "execution": _EXEC}),
    Level("amateur/senior/men", -8, -4, 0.97, 0.97, 0, (18, 38), 27, execution=2.65,
          source={"skill": "direction [S10]; size an assumption", "speed": _ASSUMED, "stamina": _ASSUMED,
                  "execution": _EXEC}),
    Level("academy/U20/men", -4, 0, 0.92, 0.97, 0, (17, 19), 18, execution=1.2,
          source={"skill": _ASSUMED, "speed": _YOUTH_SPEED, "execution": _EXEC_YOUTH}),
    Level("academy/U19/men", -5, 0, 0.88, 0.96, -1, (16, 18), 17, execution=1.3,
          source={"skill": _ASSUMED, "speed": _YOUTH_SPEED, "execution": _EXEC_YOUTH}),
    Level("academy/U18/men", -6, 0, 0.85, 0.95, -2, (16, 17), 16, execution=2.3,
          source={"skill": _ASSUMED, "speed": _YOUTH_SPEED, "execution": _EXEC_YOUTH}),
    Level("academy/U17/men", -9, -2, 0.81, 0.92, -3, (15, 16), 16, execution=3.0,
          source={"skill": _ASSUMED, "execution": _EXEC_YOUTH,
                  "speed": "sourced [S5]: set so U17 outfielders' mean peak match speed lands on 26.8 km/h, the source's "
                           "mean (band 24.9-28.7); match peak is 87% of the sprint-test maximum at U17 [S5], so the "
                           "sprint-test 30.7 km/h [S6] is not the target"}),
    Level("semi_pro/senior/women", -3, -3, 0.83, 0.90, -12, (17, 35), 25, execution=2.3,
          source={"skill": "direction [S1]; size an assumption", "stamina": "direction [S1, S2]; size an assumption",
                  "speed": "sourced [S3]: peak sprint speed 27.3 km/h, 27.3 / 33.4 = 0.82; the match peaks it gives sit "
                           "below elite women's (28.0-29.4 km/h at the 2023 Women's World Cup [S14])", "accel": _ASSUMED,
                  "height": _ASSUMED, "execution": _EXEC_WOMEN}),
    Level("college/college/women", -4, -3, 0.82, 0.90, -12, (18, 23), 20, execution=2.8,
          source={"skill": "direction [S1]; size an assumption", "stamina": "direction [S1, S2]; size an assumption",
                  "speed": "sourced [S3]: peak sprint speed 27.3 km/h, 27.3 / 33.4 = 0.82; the match peaks it gives sit "
                           "below elite women's (28.0-29.4 km/h at the 2023 Women's World Cup [S14])", "accel": _ASSUMED,
                  "height": _ASSUMED, "execution": _EXEC_WOMEN}),
]}

# Camera types by tier (weights) and the chance that a team account, not a player, uploads (design.md §2.5). Camera
# type is a label: every match is rendered the same way.
CAMERAS = ("tripod", "phone", "drone", "broadcast")
CAMERA_WEIGHTS: dict[str, dict[str, float]] = {
    "semi_pro": {"tripod": 0.50, "broadcast": 0.25, "phone": 0.15, "drone": 0.10},
    "college": {"broadcast": 0.55, "tripod": 0.35, "drone": 0.10},
    "amateur": {"phone": 0.55, "tripod": 0.35, "drone": 0.10},
    "academy": {"tripod": 0.55, "drone": 0.20, "phone": 0.15, "broadcast": 0.10},
}
TEAM_UPLOAD_P = {"semi_pro": 0.70, "college": 0.80, "amateur": 0.40, "academy": 0.75}


@dataclass(frozen=True)
class Competition:
    competition_id: str
    code: str
    name: str
    country: str
    region: str
    tier: str
    age_group: str
    gender: str
    teams: int
    uploads: int
    k: int                          # 1..13: the competition's seed index (comp_seed = 202700 + k); 0 for England
    # the competition's season inside 2026/27: its rounds are spread over it in whole weeks, and only the rounds played
    # by AS_OF can have been uploaded (a competition that started in August or September contributes its opening rounds)
    window: tuple[str, str] = ("2026-08-15", "2027-05-15")
    nationalities: tuple[tuple[str, int], ...] = ()

    @property
    def level_key(self) -> str:
        return f"{self.tier}/{self.age_group}/{self.gender}"

    @property
    def level(self) -> Level:
        return LEVELS[self.level_key]

    @property
    def eligibility(self) -> str | None:
        """The competition's birth-date rule (youth only), as a public label."""
        cut = BIRTH_CUTOFFS.get(self.competition_id)
        return cut[1] if cut else None

    def labels(self) -> dict[str, Any]:
        return {"competition_id": self.competition_id, "code": self.code, "name": self.name, "country": self.country,
                "region": self.region, "tier": self.tier, "age_group": self.age_group, "gender": self.gender,
                "format": FORMAT, "season": SEASON, "eligibility": self.eligibility}


ENGLAND_ID = "co_eng_sp_men"

# Youth competitions' birth-date rules: (earliest date of birth, the rule as a public label). Ages are drawn as whole
# years on 1 August 2026 (``Level.age_range``); a date of birth before the competition's cut-off moves forward whole years
# until it is inside (``regista.catalogue.define``; dates of birth do not reach the generator, so no match moves). Each
# rule follows the country's usual convention for that age group, applied to an invented competition.
BIRTH_CUTOFFS: dict[str, tuple[str, str]] = {
    "co_eng_u18": ("2008-09-01", "born on or after 1 September 2008 (England's school-year cut-off for U18 in 2026/27)"),
    "co_esp_u19": ("2008-01-01", "born 2008-2010 (the juvenil age group in Spain's 2026/27 season)"),
    "co_bra_u20": ("2006-01-01", "born 2006 or later (calendar-year cut-off for a 2026 Sub-20 competition)"),
    "co_gha_u17": ("2010-01-01", "born 2010 or later (calendar-year cut-off for U17 in 2026/27)"),
    "co_mar_u19": ("2008-01-01", "born 2008 or later (calendar-year cut-off for U19 in 2026/27)"),
}
# The 14 competitions, in design.md §2.2's order. England semi-pro men is the existing Regista League (league.json).
COMPETITIONS: list[Competition] = [
    Competition(ENGLAND_ID, "rl", "Regista League", "England", "Northern England", "semi_pro", "senior", "men", 6, 30, 0),
    Competition("co_eng_sp_women", "ewo", "Pennine Women's League", "England", "Yorkshire", "semi_pro", "senior", "women",
                5, 5, 1, ("2026-08-16", "2027-05-02"), (("England", 80), ("Scotland", 7), ("Wales", 7), ("Ireland", 6))),
    Competition("co_eng_u18", "eu18", "Shires Academy League U18", "England", "West Midlands", "academy", "U18", "men",
                4, 4, 2, ("2026-08-29", "2027-04-24"), (("England", 86), ("Ireland", 5), ("Scotland", 5), ("Wales", 4))),
    Competition("co_usa_col_men", "ucm", "Atlantic Collegiate Soccer Conference", "USA", "New England", "college", "college",
                "men", 6, 6, 3, ("2026-08-29", "2026-11-14"),
                (("USA", 72), ("England", 6), ("Germany", 5), ("Mexico", 5), ("Canada", 4), ("Ghana", 3), ("Japan", 3),
                 ("Spain", 2))),
    Competition("co_usa_col_women", "ucw", "Pacific Coast Collegiate Conference", "USA", "California", "college", "college",
                "women", 5, 5, 4, ("2026-08-22", "2026-11-07"),
                (("USA", 76), ("Canada", 8), ("England", 6), ("Mexico", 5), ("Germany", 3), ("Japan", 2))),
    Competition("co_esp_am_men", "eam", "Regional Preferente Levante Interior", "Spain", "Valencian Community", "amateur",
                "senior", "men", 5, 5, 5, ("2026-09-12", "2027-05-08"), (("Spain", 90), ("Morocco", 6), ("Brazil", 4))),
    Competition("co_esp_u19", "eu19", "Liga Juvenil Levante Interior", "Spain", "Valencian Community", "academy", "U19", "men",
                5, 5, 6, ("2026-09-05", "2027-04-24"), (("Spain", 92), ("Morocco", 5), ("Brazil", 3))),
    Competition("co_ger_sp_men", "gsp", "Weserland-Liga", "Germany", "Lower Saxony", "semi_pro", "senior", "men",
                6, 8, 7, ("2026-08-08", "2027-04-10"),
                (("Germany", 86), ("Ghana", 3), ("Nigeria", 3), ("Japan", 3), ("Brazil", 3), ("Spain", 2))),
    Competition("co_bra_u20", "bu20", "Campeonato Serrano Sub-20", "Brazil", "Minas Gerais", "academy", "U20", "men",
                4, 4, 8, ("2026-08-08", "2026-11-28"), (("Brazil", 100),)),
    Competition("co_nga_am_men", "nam", "Ogun Riverside Amateur League", "Nigeria", "Ogun State", "amateur", "senior", "men",
                4, 4, 9, ("2026-09-05", "2027-05-15"), (("Nigeria", 94), ("Ghana", 6))),
    Competition("co_gha_u17", "gu17", "Ashanti Colts Academy League U17", "Ghana", "Ashanti", "academy", "U17", "men",
                4, 3, 10, ("2026-09-05", "2027-05-01"), (("Ghana", 94), ("Nigeria", 6))),
    Competition("co_jpn_uni_men", "jum", "Minato Bay University League", "Japan", "Kanagawa", "college", "college", "men",
                4, 4, 11, ("2026-08-29", "2026-11-21"), (("Japan", 100),)),
    Competition("co_mex_am_men", "mam", "Liga Amateur del Valle Alto", "Mexico", "Jalisco", "amateur", "senior", "men",
                4, 4, 12, ("2026-08-15", "2026-12-12"), (("Mexico", 94), ("USA", 4), ("Spain", 2))),
    Competition("co_mar_u19", "mu19", "Ligue Juniors Atlas Centre U19", "Morocco", "Fès-Meknès", "academy", "U19", "men",
                4, 3, 13, ("2026-09-12", "2027-05-08"), (("Morocco", 97), ("Spain", 3))),
]
BY_ID: dict[str, Competition] = {c.competition_id: c for c in COMPETITIONS}


def pool_key(tier: str, age_group: str, gender: str) -> str:
    return f"{tier}/{age_group}/{gender}"


TIER_WORDS = {"semi_pro": "semi-pro", "amateur": "amateur", "college": "college", "academy": "academy"}
POSITION_WORDS = {"GK": "goalkeepers", "DF": "defenders", "MF": "midfielders", "FW": "forwards"}


def level_words(level_key: str) -> str:
    """A level in plain words: "semi-pro men", "academy U18 men", "college women" (the age group only where it is not
    the tier's own: senior and college say nothing more)."""
    tier, age_group, gender = level_key.split("/")
    age = "" if age_group in ("senior", "college") else f" {age_group}"
    return f"{TIER_WORDS[tier]}{age} {gender}"


def level_label(level_key: str) -> str:
    """A level as a heading: "Semi-pro, senior, men", "Academy / youth, under 18, men"."""
    tier, age_group, gender = level_key.split("/")
    return f"{dict(TIERS)[tier]}, {dict(AGE_GROUPS)[age_group].lower()}, {dict(GENDERS)[gender].lower()}"


def levels_public(words: bool = False) -> dict[str, Any]:
    """The taxonomy as labels (what ``catalogue.json`` and the API may show): no scale. With ``words`` (the API) each
    pool also carries its ``key``, its plain ``words`` ("semi-pro men") and its ``label`` ("Semi-pro, senior, men");
    ``catalogue.json`` keeps the plain shape."""
    pools: dict[str, list[str]] = {}
    for c in COMPETITIONS:
        pools.setdefault(c.level_key, []).append(c.competition_id)
    return {"tiers": [{"key": k, "label": v} for k, v in TIERS],
            "age_groups": [{"key": k, "label": v} for k, v in AGE_GROUPS],
            "genders": [{"key": k, "label": v} for k, v in GENDERS],
            "pools": [{"tier": k.split("/")[0], "age_group": k.split("/")[1], "gender": k.split("/")[2], "competitions": v,
                       **({"key": k, "words": level_words(k), "label": level_label(k)} if words else {})}
                      for k, v in pools.items()]}
