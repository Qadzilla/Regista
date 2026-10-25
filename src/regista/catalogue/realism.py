"""How far each metric can be called realistic at each level, honestly (design.md §10).

The Regista League's generator was tuned to Premier League bands (``regista.season.metrics.REALISM``,
``regista.synth.report``). Below the professional line almost nothing is published, so every catalogue level says which
kind of check its numbers get:

- ``band``: a published band read for this level: pass or fail. One exists below senior level: the mean peak match speed
  of U17 outfielders [S5].
- ``order``: a direction a source reports between levels (that amateurs complete fewer passes than semi-pros, that
  women's high-intensity distance is lower than men's, that youth speed rises with age), checked on pooled measurement
  seasons: pass, fail, or not separated (the margin is inside season-to-season noise).
- ``reference``: a band from a higher level shown beside the number, with no verdict (an upper reference): Premier League
  bands for senior semi-pro and college men, elite women's figures for women's physical output.
- ``none``: no published band. The number is shown; nothing is claimed.

England semi-pro men keep the existing report's Premier League bands, now labelled for what they are: the generator was
tuned to them and no semi-pro band was read, so every level's absolute values sit on a Premier-League-calibrated scale
(each level is scaled from England's) and likely overstate real football below the professional line: read them within
their pools. The checks run on measurement seasons (``regista.catalogue.measure``), never on the 3-8 uploaded matches.
Sources [S1]-[S11] are design.md §14's.

**What is served is the verdict, not the source's sentence.** Every band and order carries ``label``, what the source
reports, and the committed verdict measured on the catalogue (``data/catalogue/realism.json``, written by
``python -m regista.catalogue reliability``): the value or values, the margin, and pass, fail or not separated. A note
says what was checked and what was measured; it never states the source's direction as a property of the numbers.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
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
     "label": "highly trained U17 academy outfielders' mean peak match speed is 26.8 +/- 1.9 km/h"},
]

# Sourced directions between levels: ``levels`` from lowest to highest value. ``path`` reads a level aggregate
# (``measure.level_aggregates``).
ORDERS: list[Record] = [
    {"id": "amateur_sprint_distance", "metric": "sprint_distance", "path": ("outfield_per90", "sprint_distance"),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S9"],
     "label": "amateurs sprint less than semi-pros (distance at 25 km/h or more per 90)", "unit": "m per 90"},
    {"id": "amateur_pass_pct", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S10"],
     "label": "amateurs complete fewer passes than semi-pros", "unit": "%"},
    {"id": "youth_peak_speed_mean", "metric": "peak_speed_mean", "path": ("peak_speed_mean",), "levels": YOUTH_ORDER,
     "sources": ["S5", "S6"], "label": "peak match speed rises with age: U17 < U18 < U19 < U20 < senior",
     "unit": "km/h"},
    {"id": "youth_distance", "metric": "distance", "path": ("outfield_per90", "distance"), "levels": YOUTH_ORDER,
     "sources": ["S8"], "label": "match running distance per 90 rises with age: U17 < U18 < U19 < U20 < senior",
     "unit": "m per 90"},
    {"id": "women_pass_pct_semi_pro", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1"],
     "label": "women complete fewer passes than men (semi-pro)", "unit": "%"},
    {"id": "women_pass_pct_college", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1"],
     "label": "women complete fewer passes than men (college)", "unit": "%"},
    {"id": "women_ball_losses_semi_pro", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": [SEMI_PRO_MEN, "semi_pro/senior/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (semi-pro)", "unit": "per 90"},
    {"id": "women_ball_losses_college", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": ["college/college/men", "college/college/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (college)", "unit": "per 90"},
    {"id": "women_hi_distance_semi_pro", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1", "S2"],
     "label": "women cover less distance at 20 km/h or more than men (semi-pro; men's FIFA zones for both)",
     "unit": "m per 90"},
    {"id": "women_hi_distance_college", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1", "S2"],
     "label": "women cover less distance at 20 km/h or more than men (college; men's FIFA zones for both)",
     "unit": "m per 90"},
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
WOMEN_LEVELS = {"semi_pro/senior/women", "college/college/women"}

# The men's FIFA speed zones every level is measured on. Women's pools read them too, so their counts carry a note.
ZONE_KEYS = ("hsr_distance", "hi_distance", "sprint_distance", "sprints", "hi_efforts")
WOMEN_ZONE_NOTE = ("Speed zones are the men's FIFA zones (20 and 25 km/h) at every level; women's tournaments are "
                   "analysed with 19 and 23 km/h [S11], so these women's numbers are lower than on women's zones and many "
                   "players have none: compare them within women's pools only.")
SCALE_NOTE = ("Absolute values at every level sit on a Premier-League-calibrated scale (the Regista League was tuned to "
              "Premier League bands and every level is scaled from it), so they likely overstate real football below "
              "the professional line: read numbers within their pools.")

FILE_NAME = "realism.json"
SEPARATION_SE = 2.0   # a margin is separated from noise when it is at least this many standard errors


# ============================================================================ the committed verdicts

def default_path() -> Path:
    from regista.catalogue.store import index_path

    return index_path().with_name(FILE_NAME)


_loaded: dict[str, tuple[int, Record]] = {}


def load(path: Path | str | None = None, league: Record | None = None, comps: list[Record] | None = None) -> Record:
    """The committed verdicts (``bands``, ``orders``), or an empty file with ``stale`` saying why: missing, or measured
    for another generator or catalogue (checked when ``league`` and ``comps`` are given, as ``reliability.load`` does).
    Without verdicts a check is served with ``verdict: null`` and "not measured"."""
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    path = Path(path) if path else default_path()
    try:
        mtime = path.stat().st_mtime_ns
        hit = _loaded.get(str(path))
        if hit is None or hit[0] != mtime:
            hit = (mtime, json.loads(path.read_text()))
            _loaded[str(path)] = hit
        data = hit[1]
    except (OSError, ValueError):
        return {"bands": [], "orders": [], "stale": f"no {FILE_NAME} beside the catalogue index"}
    if data.get("generator_version") != LEAGUE_GENERATOR_VERSION:
        return {"bands": [], "orders": [], "stale": f"{FILE_NAME} was measured for generator {data.get('generator_version')}"}
    if league is not None and comps is not None:
        from regista.catalogue.reliability import catalogue_fingerprint

        if data.get("catalogue_fingerprint") != catalogue_fingerprint(league, comps, data.get("seasons", 0)):
            return {"bands": [], "orders": [], "stale": f"{FILE_NAME} was measured for another catalogue"}
    return data


def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "not measured"
    return f"{v:,.2f}{'%' if unit == '%' else ' ' + unit}"


def _band_note(b: Record, check: Record | None) -> str:
    src = ", ".join(b["sources"])
    head = f"Band check [{src}]: the source reports that {b['label']} (band {b['low']}-{b['high']} {b['unit']})."
    if not check or check.get("verdict") is None:
        return head + " Not measured on this catalogue."
    out = f"{head} Measured at this level ({check.get('seasons', '?')} full regenerated seasons): {_fmt(check['value'], b['unit'])}"
    if check["verdict"] == "pass":
        return out + ": inside the band."
    side = "above" if check["value"] > b["high"] else "below"
    return out + f": fails, {check['outside_by']:.2f} {b['unit']} {side} the band."


def _order_note(o: Record, check: Record | None) -> str:
    src = ", ".join(o["sources"])
    head = f"Order check [{src}]: the source reports that {o['label']}."
    if not check or check.get("verdict") is None:
        return head + " Not measured on this catalogue."
    vals = ", ".join(f"{lv} {_fmt(v, o['unit'])}" for lv, v in zip(o["levels"], check["values"]))
    steps = check.get("steps") or []
    worst = [st for st in steps if st["verdict"] != "pass"]
    out = f"{head} Measured (lowest expected first): {vals}"
    if check["verdict"] == "pass":
        return out + ": as reported, every step beyond season-to-season noise."
    parts = []

    def noise(st: Record) -> str:
        return "season-to-season noise" if st.get("se") is None else \
            f"season-to-season noise of +/- {SEPARATION_SE * st['se']:.2f}"

    for st in worst:
        if st["verdict"] == "fail":
            parts.append(f"{st['lower']} to {st['higher']} goes the other way by {abs(st['margin']):.2f}, beyond "
                         f"{noise(st)}")
        else:
            parts.append(f"{st['lower']} to {st['higher']} differs by {st['margin']:+.2f}, inside "
                         f"{noise(st)}")
    verdict = "fails" if check["verdict"] == "fail" else "not separated"
    return out + f": {verdict} ({'; '.join(parts)})."


def level_kinds(level: str, competition_id: str | None = None) -> Record:
    """The kinds of check a level's numbers get, for the catalogue's levels list and the realism report."""
    england = competition_id == ENGLAND_ID
    if level in PL_LEVELS:
        events = physical = "reference"
        note = (("Premier League bands: the generator was tuned to keep the Regista League inside them; no semi-pro band "
                 "was read, so they are shown for reference, with no verdict. " if england else
                 "Premier League bands shown for reference, no verdict. ") + SCALE_NOTE)
    else:
        events, physical = "none", "reference" if level in REFERENCES else "none"
        note = "No published band for this level's event rates. " + SCALE_NOTE
    if level == "academy/U17/men":
        physical = "band"
    orders = [o["id"] for o in ORDERS if level in o["levels"]]
    return {"level": level, "events": events, "physical": physical, "orders": orders, "note": note}


def realism(key: str, competition_id: str, checks: Record | None = None) -> Record:
    """How far one metric is checked in one competition: its strongest kind (band, order, reference, none), the checks
    behind it with their committed verdicts (``checks``: ``load()``'s file; default the committed one), and a note that
    says what was checked and what was measured. Never a claim the checks do not make."""
    from regista.season.metrics import realism as league_realism

    checks = load() if checks is None else checks
    band_v = {b["id"]: b for b in checks.get("bands", [])}
    order_v = {o["id"]: o for o in checks.get("orders", [])}
    level = BY_ID[competition_id].level_key
    pl = league_realism(key)
    bands = [b for b in BANDS if b["level"] == level and b["metric"] == key]
    orders = [o for o in ORDERS if o["metric"] == key and level in o["levels"]]
    refs = list(REFERENCES.get(level, {}).get(key, []))
    pl_bands = pl["bands"] if level in PL_LEVELS and pl.get("checked") else []
    tuned = competition_id == ENGLAND_ID and bool(pl_bands)
    order_notes = [_order_note(o, order_v.get(o["id"])) for o in orders]
    verdict = None
    if bands:
        kind, note = "band", _band_note(bands[0], band_v.get(bands[0]["id"]))
        verdict = (band_v.get(bands[0]["id"]) or {}).get("verdict")
    elif tuned:
        kind = "reference"
        note = ("Tuned: the generator keeps the Regista League inside these Premier League bands; no semi-pro band was "
                "read, so they are shown for reference, with no verdict. " + SCALE_NOTE + " " + pl["note"])
    elif orders:
        kind, note = "order", " ".join(order_notes)
        vs = [(order_v.get(o["id"]) or {}).get("verdict") for o in orders]
        verdict = None if None in vs else "fail" if "fail" in vs else "not separated" if "not separated" in vs else "pass"
    elif pl_bands:
        kind, note = "reference", "Premier League bands shown for reference, no verdict at this level. " + SCALE_NOTE
    elif refs:
        kind, note = "reference", "An upper reference from elite football, no verdict. " + SCALE_NOTE
    else:
        kind, note = "none", "No published band at this level: the number is shown, nothing is claimed. " + SCALE_NOTE
    if orders and kind != "order":
        note += " Also: " + " ".join(order_notes)
    zone_note = WOMEN_ZONE_NOTE if level in WOMEN_LEVELS and key in ZONE_KEYS else None
    if zone_note:
        note += " " + zone_note

    def band_out(b: Record) -> Record:
        v = band_v.get(b["id"]) or {}
        return {**{k: b[k] for k in ("id", "low", "high", "unit", "sources", "label")},
                "value": v.get("value"), "outside_by": v.get("outside_by"), "verdict": v.get("verdict")}

    def order_out(o: Record) -> Record:
        v = order_v.get(o["id"]) or {}
        return {**{k: o[k] for k in ("id", "levels", "sources", "label", "unit")},
                "values": v.get("values"), "steps": v.get("steps"), "verdict": v.get("verdict")}

    return {"level": level, "kind": kind, "tuned": tuned, "verdict": verdict,
            "premier_league_bands": pl_bands, "references": refs,
            "band": band_out(bands[0]) if bands else None, "orders": [order_out(o) for o in orders],
            "zone_note": zone_note, "verdicts_from": FILE_NAME if not checks.get("stale") else checks["stale"],
            "note": note}


# ============================================================================ computing the verdicts

def _read(agg: Record, path: tuple[str, ...]) -> float | None:
    v: Any = agg
    for p in path:
        if not isinstance(v, dict):
            return None
        v = v.get(p)
    return v


def _se(values: list[float]) -> float | None:
    """The standard error of the mean of per-season values (None with fewer than two)."""
    if len(values) < 2:
        return None
    mu = sum(values) / len(values)
    var = sum((v - mu) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(var / len(values))


def band_checks(aggregates: dict[str, Record], per_season: dict[str, list[Record]] | None = None) -> list[Record]:
    """Each band against the level's pooled measurement (``measure.level_aggregates``): pass or fail, how far outside
    (``outside_by``, 0 inside), or not measured."""
    out = []
    for b in BANDS:
        v = (aggregates.get(b["level"]) or {}).get(b["metric"])
        outside = None if v is None else round(max(0.0, b["low"] - v, v - b["high"]), 3)
        out.append({**{k: b[k] for k in ("id", "level", "metric", "low", "high", "unit", "sources", "label")}, "value": v,
                    "outside_by": outside, "seasons": len((per_season or {}).get(b["level"], [])) or None,
                    "verdict": None if v is None else "pass" if b["low"] <= v <= b["high"] else "fail"})
    return out


def order_checks(aggregates: dict[str, Record], per_season: dict[str, list[Record]] | None = None) -> list[Record]:
    """Each sourced order between levels: the pooled values in order and, per step, the margin (higher level minus lower,
    positive as the source says), its standard error from the per-season values (``per_season``: one aggregate per level
    and measurement season) and a verdict: pass (as reported, at least ``SEPARATION_SE`` standard errors), fail (the other
    way, as clearly) or not separated (inside the noise). Without ``per_season`` every step is judged on its sign alone."""
    out = []
    for o in ORDERS:
        values = [_read(aggregates.get(lv) or {}, o["path"]) for lv in o["levels"]]
        measured = all(v is not None for v in values)
        steps = []
        if measured:
            for (la, va), (lb, vb) in zip(zip(o["levels"], values), list(zip(o["levels"], values))[1:]):
                margin = vb - va
                sa = [x for x in (_read(a, o["path"]) for a in (per_season or {}).get(la, [])) if x is not None]
                sb = [x for x in (_read(b, o["path"]) for b in (per_season or {}).get(lb, [])) if x is not None]
                ea, eb = _se(sa), _se(sb)
                se = math.sqrt(ea * ea + eb * eb) if ea is not None and eb is not None else None
                separated = se is None or abs(margin) >= SEPARATION_SE * se
                verdict = "not separated" if not separated else "pass" if margin > 0 else "fail"
                steps.append({"lower": la, "higher": lb, "margin": round(margin, 3),
                              "se": None if se is None else round(se, 3), "separated": separated, "verdict": verdict})
        vs = [st["verdict"] for st in steps]
        verdict = None if not measured else "fail" if "fail" in vs else "not separated" if "not separated" in vs else "pass"
        out.append({**{k: o[k] for k in ("id", "metric", "levels", "sources", "label", "unit")}, "values": values,
                    "steps": steps, "verdict": verdict})
    return out


def compute(league: Record, comps: list[Record], repeats: int, results: list[Record]) -> Record:
    """The committed verdicts file from ``measure.measure``'s results: level aggregates pooled over every measurement
    season, one aggregate per level and season for the noise, and every band and order check."""
    from regista.catalogue.measure import level_aggregates
    from regista.catalogue.reliability import catalogue_fingerprint
    from regista.synth.generator import LEAGUE_GENERATOR_VERSION

    agg = level_aggregates(results)
    per_season: dict[str, list[Record]] = {}
    for k in sorted({r["repeat"] for r in results}):
        for level, a in level_aggregates([r for r in results if r["repeat"] == k]).items():
            per_season.setdefault(level, []).append(a)
    return {"generator_version": LEAGUE_GENERATOR_VERSION, "catalogue_fingerprint": catalogue_fingerprint(league, comps, repeats),
            "seasons": repeats, "synthetic": True, "sources": SOURCES, "separation_se": SEPARATION_SE,
            "method": "level aggregates pooled over every competition of the level and every measurement season "
                      "(regista.catalogue.measure: each competition's full double round robin regenerated "
                      f"{repeats} times). A band passes when the pooled value is inside it. An order step's margin is "
                      "the higher level's value minus the lower's; its standard error combines the two levels' "
                      f"per-season standard errors; the step passes at {SEPARATION_SE:g} standard errors or more the way "
                      "the source reports, fails as clearly the other way, and is otherwise not separated.",
            "not_checked": NOT_CHECKED, "levels": agg, "per_season": per_season,
            "bands": band_checks(agg, per_season), "orders": order_checks(agg, per_season)}


def levels() -> list[Record]:
    """Every level's kinds of check, in the taxonomy's order."""
    return [level_kinds(k) for k in LEVELS]
