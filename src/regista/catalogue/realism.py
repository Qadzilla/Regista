"""How far each metric can be called realistic at each level, honestly (design.md §10).

The Regista League's generator was tuned to Premier League bands (``regista.season.metrics.REALISM``,
``regista.synth.report``). Below the professional line almost nothing is published, so every catalogue level says which
kind of check its numbers get:

- ``band``: a published band read for this level: pass or fail. One exists below senior level: the mean peak match speed
  of U17 outfielders [S5].
- ``order``: a direction a source reports between levels (that amateurs complete fewer passes than semi-pros, that
  women's high-intensity distance is lower than men's, that youth running distance rises from U17 to U18), checked on
  pooled measurement seasons: pass, fail, or not separated (the margin is inside season-to-season noise). Where the source
  also gives a size (``gap``: women's pass completion 8 points below men's at the World Cups [S12]), the step must fall
  inside it as well. Only the span
  a source covers is sourced: the youth sources stop at U17 [S5, S6] and U18 [S8], so the steps beyond them (U18 to
  senior; for peak speed, U17 to senior) are **assumed orders** (``basis: "assumed"``), worded "no published band",
  measured the same way and never counted as a check. The youth peak-speed steps hold **by construction**: the youth
  speed scales are interpolated between U17 and senior (``taxonomy.LEVELS``), so they test the build, not football.
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
    "S1": "Bradley PS, Dellal A, Mohr M, Castellano J, Wilkie A. Gender differences in match performance characteristics of "
          "soccer players competing in the UEFA Champions League. Hum Mov Sci 2014;33:159-171. doi:10.1016/j.humov.2013.07.024",
    "S2": "Datson N, Drust B, Weston M, Jarman IH, Lisboa PJ, Gregson W. Match physical performance of elite female soccer "
          "players during international competition. J Strength Cond Res 2017;31(9):2379-2387. doi:10.1519/JSC.0000000000001575",
    "S3": "Vescovi JD. Sprint speed characteristics of high-level American female soccer players: Female Athletes in Motion "
          "(FAiM) study. J Sci Med Sport 2012;15(5):474-478. doi:10.1016/j.jsams.2012.03.006",
    "S4": "Curtis RM, Huggins RA, Looney DP, West CA, Fortunati A, Fontaine GJ, Casa DJ. Match demands of National "
          "Collegiate Athletic Association Division I men's soccer. J Strength Cond Res 2018;32(10):2907-2917. "
          "doi:10.1519/JSC.0000000000002719",
    "S5": "Al Haddad H, Simpson BM, Buchheit M, Di Salvo V, Mendez-Villanueva A. Peak match speed and maximal sprinting speed "
          "in young soccer players: effect of age and playing position. Int J Sports Physiol Perform 2015;10(7):888-896. "
          "doi:10.1123/ijspp.2014-0539",
    "S6": "Al Haddad H, Simpson BM, Buchheit M, Mendez-Villanueva A. Age-related differences in peak match running speed in "
          "highly-trained young soccer players. 17th Annual Congress of the ECSS, Bruges, 2012 (abstract); "
          "https://lida.sport-iat.de/ta/Record/4029276",
    "S8": "Buchheit M, Mendez-Villanueva A, Simpson BM, Bourdon PC. Match running performance and fitness in youth soccer. "
          "Int J Sports Med 2010;31(11):818-825. doi:10.1055/s-0030-1262838",
    "S9": "Saeterbakken A, Haug V, Fransson D, Grendstad HN, Gundersen HS, Moe VF, Ylvisaker E, Shaw M, Riiser A, Andersen V. "
          "Match running performance on three different competitive standards in Norwegian soccer. Sports Med Int Open "
          "2019;3(3):E82-E88. doi:10.1055/a-0943-3682",
    "S10": "Dellal A, Hill-Haas S, Lago-Penas C, Chamari K. Small-sided games in soccer: amateur vs. professional players' "
           "physiological responses, physical, and technical activities. J Strength Cond Res 2011;25(9):2371-2381. "
           "doi:10.1519/JSC.0b013e3181fb4296 (fourth-division French amateurs against international players, in small-sided games, "
           "not full matches: direction only)",
    "S11": "Bradley PS. Setting the benchmark, part 2: setting physical benchmarks across teams. FIFA Training Centre, FIFA "
           "Women's World Cup 2023 physical analysis, 2024. https://www.fifatrainingcentre.com/en/game/tournaments/"
           "fifa-womens-world-cup/2023/post-tournament-analysis/physical-analysis/"
           "part-2-setting-physical-benchmarks-across-teams.php",
    "S12": "Pappalardo L, Rossi A, Natilli M, Cintia P. Explaining the difference between men's and women's football. PLoS One "
           "2021;16(8):e0255407. doi:10.1371/journal.pone.0255407 (2018 men's and 2019 women's World Cups, Wyscout events)",
    "S13": "Bradley PS, Carling C, Gomez Diaz A, Hood P, Barnes C, Ade J, Boddy M, Krustrup P, Mohr M. Match performance and "
           "physical capacity of players in the top three competitive standards of English professional soccer. Hum Mov Sci "
           "2013;32(4):808-821. doi:10.1016/j.humov.2013.06.002",
    "S14": "Bradley PS. Setting the benchmark, part 3: setting physical benchmarks across positions. FIFA Training Centre, FIFA "
           "Women's World Cup 2023 physical analysis, 2024. https://www.fifatrainingcentre.com/en/game/tournaments/"
           "fifa-womens-world-cup/2023/post-tournament-analysis/physical-analysis/"
           "part-3-setting-physical-benchmarks-across-positions.php",
}

# The one band read below senior level: mean peak match speed of outfielders (the engine's peak_speed_mean), U17.
BANDS: list[Record] = [
    {"id": "u17_peak_speed_mean", "level": "academy/U17/men", "metric": "peak_speed_mean", "low": 24.9, "high": 28.7,
     "unit": "km/h", "sources": ["S5"],
     "label": "U17 academy players' peak match speed is 26.8 +/- 1.9 km/h (mean +/- SD across the study's U17 "
              "players, of 180 U13-U17 in all; the band is that SD around the mean, wide for a level's mean)"},
]

# The women's pass completion gap: 8 points at the World Cups (0.76 +/- 0.08 against 0.84 +/- 0.05 per team and match,
# [S12]); a step passes inside 8 +/- 3 points (the tolerance is Regista's: a same-tier gap below elite football is not
# published).
WOMEN_PASS_GAP = (5.0, 11.0)

# Sourced directions between levels: ``levels`` from lowest to highest value. ``gap`` (low, high): the step must also
# fall inside a sourced size, not only go the right way. ``path`` reads a level aggregate
# (``measure.level_aggregates``).
ORDERS: list[Record] = [
    {"id": "amateur_sprint_distance", "metric": "sprint_distance", "path": ("outfield_per90", "sprint_distance"),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S10"],
     "label": "amateurs sprint less than semi-pros (distance at 25 km/h or more per 90; the source compares fourth-division "
              "amateurs with internationals in small-sided games [S10]; in full matches [S9] found no difference between "
              "second-tier professionals and fourth-tier amateurs, only the top tier sprinted more)", "unit": "m per 90"},
    {"id": "amateur_pass_pct", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "sources": ["S10"],
     "label": "amateurs complete fewer passes than semi-pros", "unit": "%"},
    {"id": "amateur_ball_losses", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": [SEMI_PRO_MEN, "amateur/senior/men"], "sources": ["S10"],
     "label": "amateurs lose the ball more often than semi-pros", "unit": "per 90"},
    # No source puts numbers on pass completion by level below the professional line, so the steps between the men's
    # senior tiers are Regista's assumption; [S13] reports the direction within professional football only.
    {"id": "tier_pass_pct", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["amateur/senior/men", "college/college/men", SEMI_PRO_MEN], "basis": "assumed", "sources": [],
     "covers": {"sources": ["S10", "S13"], "span": "amateurs against internationals in small-sided games; England's top "
                                                   "three professional standards"},
     "label": "pass completion rises with the men's senior tier: amateur < college < semi-pro", "unit": "%"},
    {"id": "lower_standard_passes", "metric": "passes", "path": ("outfield_per90", "passes"),
     "levels": ["amateur/senior/men", SEMI_PRO_MEN], "basis": "assumed", "sources": [],
     "covers": {"sources": ["S13"], "span": "England's top three professional standards"},
     "label": "amateurs attempt fewer passes per 90 than semi-pros (shorter possessions, earlier shots)",
     "unit": "per 90"},
    # Youth passing: no published pass completion or ball losses by age group was found (the sources compare adult
    # standards and genders), so the whole youth order is assumed.
    {"id": "youth_pass_pct", "metric": "pass_pct", "path": ("pass_pct",), "levels": YOUTH_ORDER, "basis": "assumed",
     "sources": [], "covers": {"sources": ["S1", "S10", "S12", "S13"], "span": "adult football"},
     "label": "pass completion rises with age: U17 < U18 < U19 < U20 < senior", "unit": "%"},
    {"id": "youth_ball_losses", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": YOUTH_ORDER[::-1], "basis": "assumed", "sources": [],
     "covers": {"sources": ["S1", "S10", "S12"], "span": "adult football"},
     "label": "ball losses fall with age: U17 > U18 > U19 > U20 > senior", "unit": "per 90"},
    # [S5, S6] cover U13-U17: no catalogue step is inside their span, so the whole youth speed order is assumed, and the
    # youth speed scales are interpolated between U17 and senior (taxonomy.LEVELS): it holds by construction.
    {"id": "youth_peak_speed_mean", "metric": "peak_speed_mean", "path": ("peak_speed_mean",), "levels": YOUTH_ORDER,
     "basis": "assumed", "sources": [], "covers": {"sources": ["S5", "S6"], "span": "U13-U17"},
     "construction": "the youth speed scales are set from U17's peak match speed [S5] and interpolated to senior (the "
                     "level scales), so the order follows from the build's own assumption and tests the build, not football",
     "label": "peak match speed keeps rising from U17 to senior: U17 < U18 < U19 < U20 < senior", "unit": "km/h"},
    # [S8] covers U13-U18: the U17 to U18 step is sourced, the rest of the way to senior is assumed.
    {"id": "youth_distance", "metric": "distance", "path": ("outfield_per90", "distance"),
     "levels": YOUTH_ORDER[:2], "sources": ["S8"],
     "label": "match running distance per 90 rises with age through U13-U18 (the catalogue's step: U17 < U18)",
     "unit": "m per 90"},
    {"id": "youth_distance_extension", "metric": "distance", "path": ("outfield_per90", "distance"),
     "levels": YOUTH_ORDER[1:], "basis": "assumed", "sources": [], "covers": {"sources": ["S8"], "span": "U13-U18"},
     "label": "match running distance per 90 keeps rising from U18 to senior: U18 < U19 < U20 < senior",
     "unit": "m per 90"},
    {"id": "women_pass_pct_semi_pro", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1", "S12"], "gap": WOMEN_PASS_GAP,
     "label": "women complete fewer passes than men (semi-pro): 76% against 84% at the 2019 and 2018 World Cups [S12], a gap "
              "of 8 points", "unit": "%"},
    {"id": "women_pass_pct_college", "metric": "pass_pct", "path": ("pass_pct",),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1", "S12"], "gap": WOMEN_PASS_GAP,
     "label": "women complete fewer passes than men (college): 76% against 84% at the 2019 and 2018 World Cups [S12], a gap "
              "of 8 points", "unit": "%"},
    {"id": "women_ball_losses_semi_pro", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": [SEMI_PRO_MEN, "semi_pro/senior/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (semi-pro)", "unit": "per 90"},
    {"id": "women_ball_losses_college", "metric": "ball_losses", "path": ("outfield_per90", "ball_losses"),
     "levels": ["college/college/men", "college/college/women"], "sources": ["S1"],
     "label": "women lose the ball more often than men (college)", "unit": "per 90"},
    {"id": "women_hi_distance_semi_pro", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["semi_pro/senior/women", SEMI_PRO_MEN], "sources": ["S1"],
     "label": "women cover less distance at 20 km/h or more than men (semi-pro; men's FIFA zones for both)",
     "unit": "m per 90"},
    {"id": "women_hi_distance_college", "metric": "hi_distance", "path": ("outfield_per90", "hi_distance"),
     "levels": ["college/college/women", "college/college/men"], "sources": ["S1"],
     "label": "women cover less distance at 20 km/h or more than men (college; men's FIFA zones for both)",
     "unit": "m per 90"},
]
NOT_CHECKED = ["women's second-half drop in high-intensity distance [S1]: the engine's metrics do not split halves"]

# Upper references by level and metric: elite or higher-level figures, shown beside the number, never a verdict.
WOMEN_REFERENCES: dict[str, list[Record]] = {
    "distance": [{"text": "total distance per 90 about 9.5-11.0 km from positional means in elite women's internationals",
                  "sources": ["S2"]},
                 {"text": "teams covered 103.3 km per match on average at the 2023 Women's World Cup (match-to-match variation "
                          "3.9%)", "sources": ["S11"]}],
    "peak_speed": [{"text": "peak sprint speed 27.3 +/- 1.4 km/h, maxima above 30 km/h (high-level American players)",
                    "sources": ["S3"]}],
    "peak_speed_mean": [{"text": "top speeds in games 28.0-29.4 km/h by position at the 2023 Women's World Cup (central "
                                 "and defensive midfielders lowest, attacking and wide players highest)", "sources": ["S14"]}],
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
YOUTH_ZONE_NOTE = ("Speed zones are the men's senior FIFA zones (20 and 25 km/h) at every level; youth studies use lower "
                   "or individual thresholds (very high intensity above 16.1 km/h in [S8]) and U17 match peaks average "
                   "26.8 km/h [S5], so few academy players reach 25 km/h and many have no sprints: compare these numbers "
                   "within youth pools only.")
YOUTH_LEVELS = {"academy/U17/men", "academy/U18/men", "academy/U19/men", "academy/U20/men"}


def zone_note_for(level: str, key: str) -> str | None:
    """The threshold note a speed-zone number carries at this level (women's and youth pools), else None."""
    if key not in ZONE_KEYS:
        return None
    return WOMEN_ZONE_NOTE if level in WOMEN_LEVELS else YOUTH_ZONE_NOTE if level in YOUTH_LEVELS else None


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


def assumed(o: Record) -> bool:
    """An order no source covers (``basis: "assumed"``): measured, never counted as a check."""
    return o.get("basis") == "assumed"


def _order_note(o: Record, check: Record | None) -> str:
    if assumed(o):
        cov = o.get("covers") or {}
        srcs = cov.get("sources", [])
        span = (f" ({', '.join('[' + x + ']' for x in srcs)} {'covers' if len(srcs) == 1 else 'cover'} {cov['span']} "
                "only)" if cov.get("span") else "")
        head = f"Assumed order, no published band{span}: the build assumes that {o['label']}."
        if o.get("construction"):
            head += f" By construction: {o['construction']}."
    else:
        head = f"Order check [{', '.join(o['sources'])}]: the source reports that {o['label']}."
    if not check or check.get("verdict") is None:
        return head + " Not measured on this catalogue."
    vals = ", ".join(f"{lv} {_fmt(v, o['unit'])}" for lv, v in zip(o["levels"], check["values"]))
    steps = check.get("steps") or []
    worst = [st for st in steps if st["verdict"] != "pass"]
    out = f"{head} Measured (lowest expected first): {vals}"
    if check["verdict"] == "pass":
        gap = f", and inside the sourced gap of {o['gap'][0]:g}-{o['gap'][1]:g}" if o.get("gap") else ""
        return out + (": as assumed" if assumed(o) else ": as reported") + f", every step beyond season-to-season noise{gap}."
    parts = []

    def noise(st: Record) -> str:
        return "season-to-season noise" if st.get("se") is None else \
            f"season-to-season noise of +/- {SEPARATION_SE * st['se']:.2f}"

    for st in worst:
        if st.get("outside_gap"):
            parts.append(f"{st['lower']} to {st['higher']} differs by {st['margin']:+.2f}, outside the sourced gap of "
                         f"{st['gap'][0]:g}-{st['gap'][1]:g}")
        elif st["verdict"] == "fail":
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
    orders = [o["id"] for o in ORDERS if level in o["levels"] and not assumed(o)]
    extra = [o["id"] for o in ORDERS if level in o["levels"] and assumed(o)]
    return {"level": level, "events": events, "physical": physical, "orders": orders, "assumed_orders": extra,
            "note": note}


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
    every_order = [o for o in ORDERS if o["metric"] == key and level in o["levels"]]
    orders = [o for o in every_order if not assumed(o)]          # sourced: a check
    guesses = [o for o in every_order if assumed(o)]             # assumed: shown, measured, never a check
    refs = list(REFERENCES.get(level, {}).get(key, []))
    pl_bands = pl["bands"] if level in PL_LEVELS and pl.get("checked") else []
    tuned = competition_id == ENGLAND_ID and bool(pl_bands)
    order_notes = [_order_note(o, order_v.get(o["id"])) for o in orders]
    guess_notes = [_order_note(o, order_v.get(o["id"])) for o in guesses]
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
    if guess_notes:
        note += " " + " ".join(guess_notes)
    zone_note = zone_note_for(level, key)
    if zone_note:
        note += " " + zone_note

    def band_out(b: Record) -> Record:
        v = band_v.get(b["id"]) or {}
        return {**{k: b[k] for k in ("id", "low", "high", "unit", "sources", "label")},
                "value": v.get("value"), "outside_by": v.get("outside_by"), "verdict": v.get("verdict")}

    def order_out(o: Record) -> Record:
        v = order_v.get(o["id"]) or {}
        return {**{k: o[k] for k in ("id", "levels", "sources", "label", "unit")}, "gap": list(o["gap"]) if o.get("gap") else None,
                "basis": o.get("basis", "sourced"), "covers": o.get("covers"), "by_construction": bool(o.get("construction")),
                "values": v.get("values"), "steps": v.get("steps"), "verdict": v.get("verdict")}

    return {"level": level, "kind": kind, "tuned": tuned, "verdict": verdict,
            "premier_league_bands": pl_bands, "references": refs,
            "band": band_out(bands[0]) if bands else None, "orders": [order_out(o) for o in orders],
            "assumed_orders": [order_out(o) for o in guesses],
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
                step = {"lower": la, "higher": lb, "margin": round(margin, 3),
                        "se": None if se is None else round(se, 3), "separated": separated, "verdict": verdict}
                gap = o.get("gap")
                if gap:   # a sourced size: the step passes only inside it
                    step["gap"] = list(gap)
                    step["outside_gap"] = not gap[0] <= margin <= gap[1]
                    if step["outside_gap"] and verdict == "pass":
                        step["verdict"] = "fail"
                steps.append(step)
        vs = [st["verdict"] for st in steps]
        verdict = None if not measured else "fail" if "fail" in vs else "not separated" if "not separated" in vs else "pass"
        out.append({**{k: o[k] for k in ("id", "metric", "levels", "sources", "label", "unit")},
                    "gap": list(o["gap"]) if o.get("gap") else None, "basis": o.get("basis", "sourced"), "covers": o.get("covers"),
                    "by_construction": bool(o.get("construction")), "values": values, "steps": steps,
                    "verdict": verdict})
    return out


def recheck(data: Record) -> Record:
    """The committed verdicts file with its band and order checks re-run on its own stored aggregates (``levels``,
    ``per_season``): for a change in the checks' wording or spans, with no season regenerated (``python -m
    regista.catalogue recheck-realism``). The measurement, its fingerprint and its method are kept."""
    return {**data, "sources": SOURCES, "not_checked": NOT_CHECKED,
            "bands": band_checks(data["levels"], data.get("per_season")),
            "orders": order_checks(data["levels"], data.get("per_season"))}


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
