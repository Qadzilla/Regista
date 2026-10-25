"""How far each metric can be called realistic at each level, honestly (design.md §10).

The Regista League's generator was tuned to Premier League bands (``regista.season.metrics.REALISM``,
``regista.synth.report``). Below the professional line almost nothing is published, so every catalogue level says which
kind of check its numbers get:

- ``band``: a published band read for this level: pass or fail. One exists below senior level: the mean peak match speed
  of U17 outfielders [S5].
- ``order``: a sourced direction between levels (amateurs complete fewer passes than semi-pros, women's high-intensity
  distance is lower than men's, youth speed rises with age), checked on pooled measurement seasons: pass or fail.
- ``reference``: a band from a higher level shown beside the number, with no verdict (an upper reference): Premier League
  bands for senior semi-pro and college men, elite women's figures for women's physical output.
- ``none``: no published band. The number is shown; nothing is claimed.

England semi-pro men keep the existing report's Premier League bands, now labelled for what they are: the generator was
tuned to them, and no semi-pro band was read, so they are an upper reference. The checks run on measurement seasons
(``regista.catalogue.measure``), never on the 3-8 uploaded matches. Sources [S1]-[S11] are design.md §14's.
"""

from __future__ import annotations

from typing import Any

from regista.catalogue.taxonomy import BY_ID, ENGLAND_ID, LEVELS

Record = dict[str, Any]

SEMI_PRO_MEN = "semi_pro/senior/men"
YOUTH_ORDER = ["academy/U17/men", "academy/U18/men", "academy/U19/men", "academy/U20/men", SEMI_PRO_MEN]

SOURCES: dict[str, str] = {
    "S1": "Bradley et al. 2014, Hum Mov Sci 33:159-171 (UEFA Champions League, women vs men)",
    "S2": "Datson et al. 2017, J Strength Cond Res 31(9):2379-2387 (elite women's internationals)",
    "S3": "Vescovi 2012, FAiM study (high-level American female players' sprint speed)",
    "S4": "Match demands of NCAA Division I men's soccer, J Strength Cond Res 2018",
    "S5": "Peak match speed and maximal sprinting speed in young soccer players, IJSPP 2015;10(7):888-896",
    "S6": "Age-related differences in peak match running speed in highly-trained young soccer players",
    "S8": "Buchheit et al. 2010, Int J Sports Med 31(11):818-825 (youth match running, U13-U18)",
    "S9": "Match running performance on three competitive standards in Norwegian soccer",
    "S10": "Professional vs amateur players in small-sided games (as summarised in PMC6815094; direction only)",
    "S11": "FIFA Training Centre, Women's World Cup 2023 physical analysis, part 2",
}

# The one band read below senior level: mean peak match speed of outfielders (the engine's peak_speed_mean), U17.
BANDS: list[Record] = [
    {"id": "u17_peak_speed_mean", "level": "academy/U17/men", "metric": "peak_speed_mean", "low": 24.9, "high": 28.7,
     "unit": "km/h", "sources": ["S5"],
     "label": "mean peak match speed of U17 outfielders within 26.8 +/- 1.9 km/h (highly trained academy players)"},
]

# Sourced directions between levels: ``levels`` from lowest to highest value. ``path`` reads a level aggregate
# (``measure.level_aggregates``).
ORDERS: list[Record] = [
    {"id": "amateur_sprint_distance", "metric": "sprint_distance", "path": ("outfield_per90", "sprint_distance"),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S9"],
     "label": "amateurs sprint less than semi-pros (distance at 25 km/h or more per 90)"},
    {"id": "amateur_pass_pct", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S10"],
     "label": "amateurs complete fewer passes than semi-pros"},
    {"id": "youth_peak_speed_mean", "metric": "peak_speed_mean", "path": ("peak_speed_mean",), "levels": YOUTH_ORDER,
     "sources": ["S5", "S6"], "label": "peak match speed rises with age: U17 < U18 < U19 < U20 < senior"},
    {"id": "youth_distance", "metric": "distance", "path": ("outfield_per90", "distance"), "levels": YOUTH_ORDER,
     "sources": ["S8"], "label": "match running distance per 90 rises with age: U17 < U18 < U19 < U20 < senior"},
    {"id": "women_pass_pct_semi_pro", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1"],
     "label": "women complete fewer passes than men (semi-pro)"},
    {"id": "women_pass_pct_college", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1"],
     "label": "women complete fewer passes than men (college)"},
    {"id": "women_ball_losses_semi_pro", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": [SEMI_PRO_MEN, "semi_pro/senior/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (semi-pro)"},
    {"id": "women_ball_losses_college", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": ["college/college/men", "college/college/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (college)"},
    {"id": "women_hi_distance_semi_pro", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1", "S2"],
     "label": "women cover less distance at 20 km/h or more than men (semi-pro; men's FIFA zones for both)"},
    {"id": "women_hi_distance_college", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1", "S2"],
     "label": "women cover less distance at 20 km/h or more than men (college; men's FIFA zones for both)"},
]
NOT_CHECKED = ["women's second-half drop in high-intensity distance [S1]: the engine's metrics do not split halves"]

# Upper references by level and metric: elite or higher-level figures, shown beside the number, never a verdict.
WOMEN_REFERENCES: dict[str, list[Record]] = {
    "distance": [{"text": "total distance per 90 about 9.5-11.0 km from positional means in elite women's internationals",
                  "sources": ["S2"]},
                 {"text": "teams 103.3 +/- 4.4 km per match at the 2023 Women's World Cup", "sources": ["S11"]}],
    "peak_speed": [{"text": "peak sprint speed 27.3 +/- 1.4 km/h, maxima above 30 km/h (high-level American players)",
                    "sources": ["S3"]}],
}
REFERENCES: dict[str, dict[str, list[Record]]] = {
    "college/college/men": {"distance": [{"text": "about 9,367 m per match in NCAA Division I men's soccer (per match, "
                                                  "not per 90: re-entry substitutions)", "sources": ["S4"]}]},
    "semi_pro/senior/women": WOMEN_REFERENCES,
    "college/college/women": WOMEN_REFERENCES,
}
PL_LEVELS = {SEMI_PRO_MEN, "college/college/men"}   # levels where Premier League bands may stand as an upper reference


def level_kinds(level: str, competition_id: str | None = None) -> Record:
    """The kinds of check a level's numbers get, for the catalogue's levels list and the realism report."""
    england = competition_id == ENGLAND_ID
    if level in PL_LEVELS:
        events = physical = "reference"
        note = ("Premier League bands: the generator was tuned to keep the Regista League inside them; no semi-pro band "
                "was read, so they are an upper reference" if england else
                "Premier League bands as an upper reference, no verdict: the same rating scale as England semi-pro men")
    else:
        events, physical = "none", "reference" if level in REFERENCES else "none"
        note = "no published band for this level's event rates"
    if level == "academy/U17/men":
        physical = "band"
    orders = [o["id"] for o in ORDERS if level in o["levels"]]
    return {"level": level, "events": events, "physical": physical, "orders": orders, "note": note}


def realism(key: str, competition_id: str) -> Record:
    """How far one metric is checked in one competition: its strongest kind (band, order, reference, none), the checks
    behind it, and a note. Never a claim the checks do not make."""
    from regista.season.metrics import realism as league_realism

    level = BY_ID[competition_id].level_key
    pl = league_realism(key)
    bands = [b for b in BANDS if b["level"] == level and b["metric"] == key]
    orders = [o for o in ORDERS if o["metric"] == key and level in o["levels"]]
    refs = list(REFERENCES.get(level, {}).get(key, []))
    pl_bands = pl["bands"] if level in PL_LEVELS and pl.get("checked") else []
    tuned = competition_id == ENGLAND_ID and bool(pl_bands)
    if bands:
        kind, note = "band", bands[0]["label"]
    elif tuned:
        kind = "reference"
        note = ("tuned: the generator keeps the Regista League inside these Premier League bands (no semi-pro band was "
                "read, so they are an upper reference). " + pl["note"])
    elif orders:
        kind, note = "order", "; ".join(o["label"] for o in orders)
    elif pl_bands:
        kind, note = "reference", "Premier League bands as an upper reference, no verdict at this level"
    elif refs:
        kind, note = "reference", "an upper reference from elite football, no verdict"
    else:
        kind, note = "none", "no published band at this level: the number is shown, nothing is claimed"
    if orders and kind != "order":
        note += " Also checked as an order between levels: " + "; ".join(o["label"] for o in orders) + "."
    return {"level": level, "kind": kind, "tuned": tuned,
            "premier_league_bands": pl_bands, "references": refs,
            "band": {k: bands[0][k] for k in ("id", "low", "high", "unit", "sources", "label")} if bands else None,
            "orders": [{k: o[k] for k in ("id", "levels", "sources", "label")} for o in orders], "note": note}


def _read(agg: Record, path: tuple[str, ...]) -> float | None:
    v: Any = agg
    for p in path:
        if not isinstance(v, dict):
            return None
        v = v.get(p)
    return v


def band_checks(aggregates: dict[str, Record]) -> list[Record]:
    """Each band against the level's pooled measurement (``measure.level_aggregates``): pass, fail, or not measured."""
    out = []
    for b in BANDS:
        v = (aggregates.get(b["level"]) or {}).get(b["metric"])
        out.append({**{k: b[k] for k in ("id", "level", "metric", "low", "high", "unit", "sources", "label")}, "value": v,
                    "verdict": None if v is None else "pass" if b["low"] <= v <= b["high"] else "fail"})
    return out


def order_checks(aggregates: dict[str, Record]) -> list[Record]:
    """Each sourced order between levels: the values in order and whether they rise strictly, as the source says."""
    out = []
    for o in ORDERS:
        values = [_read(aggregates.get(lv) or {}, o["path"]) for lv in o["levels"]]
        measured = all(v is not None for v in values)
        ok = measured and all(a < b for a, b in zip(values, values[1:]))
        out.append({**{k: o[k] for k in ("id", "metric", "levels", "sources", "label")}, "values": values,
                    "verdict": None if not measured else "pass" if ok else "fail"})
    return out


def levels() -> list[Record]:
    """Every level's kinds of check, in the taxonomy's order."""
    return [level_kinds(k) for k in LEVELS]
