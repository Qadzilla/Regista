"""Synthetic-data realism report: how a generated match compares with Premier League norms.

    python -m regista.synth.report data/synthetic/sample/syn_0294
    python -m regista.synth.report --profile realistic --seeds 11 12 13 --minutes 20
    python -m regista.synth.report --league data/season/league.json [--repeat 3]

League streams also carry ``physical`` records (every player's 10 Hz motion summarised, regista.synth.physical); the
report checks them against physical bands from the Premier League (The Analyst / Opta) and the 2022 World Cup (FIFA's
tracking, Bradley 2023), each band with its source below. League streams also get team-style bands (PPDA, possession)
and individual-leader bands (each metric's top player against the Premier League's third best), computed with the Scout
terminal's own engine (regista.season.metrics). A season is about ten full matches: check rare events and leaders over
three seasons (``--league --repeat 3``).

The generator has two profiles. ``demo`` packs a 3-minute sample with action so a
short clip reel has something in it; ``realistic`` is tuned to land inside the bands
below over a full match. The report prints every metric beside its band and says which
side of the band it falls on, so nobody has to take "football-realistic" on trust.

Norm bands are approximate season averages for both teams combined per 90 minutes,
compiled from publicly reported Premier League statistics (FBref / Opta, 2021-22 to
2023-24 seasons). They are sanity bands for a simulator, not a research dataset.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from regista.schema import iter_jsonl

Record = dict[str, Any]

NORMS_SOURCE = "Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth."

# metric -> (low, high, unit, note)
NORMS: dict[str, tuple[float, float, str, str]] = {
    "passes_per90": (800.0, 1100.0, "passes", "attempted passes and crosses, both teams"),
    "pass_completion": (0.78, 0.87, "ratio", "completed / attempted"),
    "shots_per90": (20.0, 32.0, "shots", "both teams"),
    "goals_per90": (2.2, 3.6, "goals", "both teams"),
    "xg_per_shot": (0.08, 0.13, "xG", "mean expected goals per shot"),
    "tackles_per90": (28.0, 45.0, "tackles", "both teams"),
    "interceptions_per90": (14.0, 30.0, "interceptions", "both teams"),
    "take_ons_per90": (28.0, 50.0, "take-ons", "attempted dribbles past a defender"),
    "nutmegs_per90": (0.5, 3.0, "nutmegs", "rarely reported; broadcast estimate"),
    "fouls_per90": (18.0, 28.0, "fouls", "both teams"),
    "corners_per90": (8.0, 13.0, "corners", "both teams"),
    "throw_ins_per90": (35.0, 55.0, "throw-ins", "both teams"),
    "possession_mean_s": (1.5, 4.5, "seconds", "mean time one player holds the ball"),
}
# League mode (schema 0.2.0: substitutions, penalties, aerial duels, red cards, offsides). Checked only on streams whose
# generator ran with player ratings; their sources are cited one by one because no single table covers them.
LEAGUE_NORMS: dict[str, tuple[float, float, str, str]] = {
    "penalties_per90": (0.15, 0.45, "penalties", "Premier League 72-125 penalties a season (1997/98-2023/24), 0.19-0.33 a "
                        "match: The Analyst on premierleague.com, 2 Jun 2024 (premierleague.com/news/4029218)"),
    "red_cards_per90": (0.04, 0.25, "red cards", "Premier League 30-47 a season 2018/19-2022/23 (premierleague.com/news/3533373), "
                        "0.08-0.12 a match; 2023/24 ran at 0.22 a match by December (theanalyst.com)"),
    "offsides_per90": (2.5, 5.5, "offsides", "about 2 a team a match: Leeds United 76 in 38 Premier League games 2020/21 "
                       "(leedsunited.com); Liverpool's opponents 95-144 a season (anfieldindex.com). Secondary sources"),
    "aerial_duels_per90": (20.0, 40.0, "contests", "Premier League 22,917 aerial duels in a season, 60.3 a game counted per player "
                           "(Opta counts a won and a lost duel for every contest), so about 30 contests a game "
                           "(anfieldindex.com, an older season; secondary)"),
    "substitutions_per_match": (6.0, 9.5, "per match", "Premier League 7.89 substitutions a match in 2023/24, both teams "
                                "(The Analyst, theanalyst.com). Per match, not per 90: a league match is 30 minutes"),
    "cross_completion": (0.16, 0.26, "ratio", "open-play crosses completed: Premier League 18.8% (2020/21), 19.6%, 21.1%, "
                         "20.9% (2023/24), 21.7% (2024/25 after seven rounds), 10-season average 19.5% (Adrian Clarke, "
                         "premierleague.com/news/4148090, 13 Oct 2024). The margins either side are ours"),
    "prog_pass_carry_ratio": (1.2, 3.0, "ratio", "progressive passes per progressive carry (FBref rules, regista.season.metrics). "
                              "FBref 2023/24 via Football365 (20 May 2024): the five most progressive passers made 1,602, the five "
                              "most progressive carriers 840, about 1.9 to 1 (our arithmetic). A derived band: no league total "
                              "could be read (FBref answered 403)"),
}
# Individual leaders (league mode). A scout reads the leaderboards first, so the top of each distribution is banded too.
# V is the Premier League 2023/24 per-90 value of the third-best player with 900+ minutes (StatMuse, Opta data, read
# 2026-10-23, unless noted): six clubs are about a third of the Premier League, so the league's leader compares with the
# Premier League's third best. The band runs from 0.75 V to 1.5 V. The upper margin is ours: a Regista season gives a
# qualified player 100-300 minutes (a third of a club's minutes, the Scout terminal's pool), so its leaders sit above a
# 900-minute pool by chance. Goals are the noisiest count, so their upper bound is 2 V.
LEADER_V: dict[str, tuple[float, str, float, float]] = {   # key: (V, where it comes from, low multiple, high multiple)
    "shots": (4.12, "1 Nunez 4.75, 2 Haaland 4.27, 3 Muniz 4.12", 0.75, 1.5),
    "npxg": (0.81, "xG per 90 (penalties included, so npxG sits a little lower): 1 Haaland 1.04, 2 Isak 0.81, 3 Wilson 0.81",
             0.75, 1.5),
    "goals": (0.82, "our arithmetic from StatMuse goals and minutes: Haaland 27 in 2,553 min (0.95), Isak 21 in 2,255 (0.84), "
              "Wilson 9 in 991 (0.82)", 0.75, 2.0),
    "key_passes": (3.03, "1 De Bruyne 3.54, 2 Robertson 3.19, 3 Bruno Fernandes 3.03", 0.75, 1.5),
    "xa": (0.34, "1 De Bruyne 0.53, 2 Olise 0.35, 3 Saka 0.34", 0.75, 1.5),
    "touches_in_box": (9.33, "1 Doku 14.32, 2 Gabriel Jesus 9.55, 3 Garnacho 9.33", 0.75, 1.5),
    "tackles_won": (4.28, "tackles (Regista's tackle events are the tackles the league band counts): 1 Palhinha 5.14, "
                    "2 Joao Gomes 4.35, 3 Vinicius Souza 4.28", 0.75, 1.5),
    "interceptions": (1.97, "1 Antonee Robinson 2.23, 2 Lewis Cook 2.16, 3 Wan-Bissaka 1.97", 0.75, 1.5),
    "crosses": (9.78, "crosses attempted: 1 Doughty 10.46, 2 De Bruyne 10.02, 3 Robertson 9.78", 0.75, 1.5),
    "progressive_carries": (12.29, "the leader, not the third best (per-90 ranks could not be read): Doku, 218 (FBref via "
                            "Football365, 20 May 2024) in 1,596 min (StatMuse), our arithmetic. Doku is an outlier (the "
                            "next of the season's top five carriers, Garnacho, made 6.2 per 90), so the lower bound is 0.5 V",
                            0.5, 1.5),
}
INDIVIDUAL_NORMS: dict[str, tuple[float, float, str, str]] = {
    f"leader_{k}_per90": (round(lo * v, 2), round(hi * v, 2), "per 90",
                          f"the league's top qualified player against V = {v}, Premier League 2023/24 ({why}); band "
                          f"{lo:g} V to {hi:g} V")
    for k, (v, why, lo, hi) in LEADER_V.items()
}
INDIVIDUAL_NORMS["top_shooter_share"] = (0.12, 0.35, "share", "the largest share of a club's non-penalty shots taken by one "
                                         "player. Premier League 2023/24: Liverpool took 790 shots, their top shooters Salah "
                                         "114 (14%) and Nunez 108 (14%) (StatMuse). The upper bound, for a team built around "
                                         "one striker, is ours")
# Team style (league mode), per club over the season.
STYLE_NORMS: dict[str, tuple[float, float, str, str]] = {
    "ppda_team_min": (7.5, 12.5, "passes", "the most intense press (lowest PPDA). Premier League: Liverpool 8.62, the lowest "
                      "in 2021/22 (Wyscout, premierleague.com/news/4250153); in 2024/25 the ten best pressers ran from 9.9 to "
                      "12.3 (Playmakerstats, via Yahoo Sports, 9 Jun 2025)"),
    "ppda_team_max": (12.0, 17.5, "passes", "the most passive (highest PPDA). 2021/22: Norwich 16.93, the highest in Europe's "
                      "top five leagues, Wolves 14.78, Everton 14.63 (Wyscout, premierleague.com/news/4250153)"),
    "possession_team_max": (52.0, 66.0, "%", "the highest possession share: Premier League 2023/24 Man City 65.7%, then "
                            "62.0, 61.8 (StatMuse, Opta data). Six clubs span less of the range than twenty"),
    "possession_team_min": (34.0, 48.0, "%", "the lowest possession share: Premier League 2023/24 Sheffield United 35.3%, then "
                            "40.2, 40.6 (StatMuse, Opta data)"),
}
# Physical (league mode: ``physical`` records). Outfield players unless noted; per 90 minutes on the pitch, pooled. Source
# keys refer to docs/scout-terminal/industry-metrics.md; definitions are in regista.synth.physical.DEFINITIONS.
PHYSICAL_NORMS: dict[str, tuple[float, float, str, str]] = {
    "distance_per90_km": (9.5, 11.5, "km", "Premier League 2024/25 per-90 distances run from 8.5 km (lowest regular starter) "
                          "to 12.3 (highest regular starter) and 12.9 (highest, 600+ min) (The Analyst, OA-PHYS); 2022 World "
                          "Cup teams ran 108.1 ± 3.6 km a match, about 10 km per outfield player (Bradley 2023, FIFA-PHYS)"),
    "distance_per90_min_km": (8.5, 10.0, "km", "the lowest regular outfielder: 8.5 km (Murillo), then 8.8-9.0 "
                              "(The Analyst 2024/25, 1,500+ min). Regulars here: at least 40% of the most minutes anyone played"),
    "distance_per90_max_km": (11.0, 13.0, "km", "the highest: 12.3 km (Kulusevski, 1,500+ min), 12.9 (Yarmoliuk, 600+ min) "
                              "(The Analyst 2024/25)"),
    "hi_distance_per90_m": (600.0, 1100.0, "m", ">= 20 km/h. 2022 World Cup: 9,001 ± 850 m a team a match, about 800-900 per "
                            "outfield player; central roles about 0.5-0.8 km, wide roles 1.0-1.1 (Bradley 2023 Parts 1-2, "
                            "FIFA-PHYS); > 19.8 km/h about 760 m a match, range 618-1,001 (systematic review, HSR-REV)"),
    "sprint_distance_per90_m": (150.0, 330.0, "m", ">= 25 km/h. 2022 World Cup: 2,345 ± 314 m a team a match, about 210-235 per "
                                "outfield player (FIFA-PHYS); > 25.1 km/h about 200 m a match, range 153-295 (HSR-REV)"),
    "sprints_per90": (6.0, 24.0, "sprints", ">= 25 km/h for >= 1 s. No published league mean: the Premier League's most "
                      "frequent sprinter had 702 by 23 March 2025 (The Analyst), about 24 a match over the 29 rounds played "
                      "(our arithmetic); 33 ± 11 a match at the 2014 World Cup above 25.2 km/h (Chmura 2017, via "
                      "HSR-REV). A derived band"),
    "walking_share_min": (0.48, 0.60, "share", "the regular who walks least (time below 6 km/h): Premier League 2024/25 "
                          "lowest 54.2% (Soucek) (The Analyst, OA-PHYS). Individual extreme against individual extreme; the "
                          "margins are ours"),
    "walking_share_max": (0.66, 0.84, "share", "the regular who walks most: Premier League 2024/25 highest 77.6% (Cunha) "
                          "(The Analyst). The margins are ours; the inner one is wider because six clubs have about a third of "
                          "the Premier League's regulars, and the extreme of a smaller group sits further inside"),
    "jogging_share_max": (0.28, 0.38, "share", "the regular who jogs most (6-15 km/h): Premier League 2024/25 highest 34.7% "
                          "(Soucek), then 32-33% (The Analyst). The margins are ours"),
    "cb_hi_distance_per90_m": (450.0, 900.0, "m", "centre-backs (regulars), >= 20 km/h: central roles about 0.5-0.8 km a match "
                               "at the 2022 World Cup (Bradley 2023 Parts 1-2, FIFA-PHYS). The lower margin is ours"),
    "dec_acc_high_ratio": (1.0, 2.5, "ratio", "high decelerations per high acceleration (both 3 m/s^2 or more, held 1 s): in "
                           "soccer high and very high decelerations are more frequent than accelerations, the largest gap of any "
                           "team sport (SMD -1.74 and -3.19; Harper, Carling and Kiely 2019, Sports Medicine 49:1923-47, "
                           "pmc.ncbi.nlm.nih.gov/articles/PMC6851047). The upper bound is ours"),
    "peak_speed_mean_kmh": (29.0, 33.0, "km/h", "mean of each outfielder's top speed in a match (60%+ of it played). 2022 World "
                            "Cup, complete matches: 30.2-30.8 (centre-backs, holding and central midfielders), 32.1-32.3 (wide "
                            "and attacking roles, centre-forwards) (Bradley 2023 Part 1). A league match is 30 minutes, so its "
                            "peaks sit a little lower"),
    "peak_speed_max_kmh": (35.0, 37.5, "km/h", "the league's fastest: in the 2024/25 Premier League only van de Ven passed "
                           "37 km/h, then 36.2-36.7 (The Analyst); the 2022 World Cup's top ten were 35.3-35.7 (Bradley 2023 Part 1)"),
    "second_half_distance_drop": (0.02, 0.12, "share", "per-minute distance, second half against first: about 7% lower at the "
                                  "2022 World Cup, 6.0-9.8% by role (Bradley 2023 Part 1)"),
}
PHYSICAL_DIAGNOSTICS = ("players_measured", "walking_time_share", "jogging_time_share", "cb_distance_per90_km", "zone3_per90_m", "hi_efforts_per90", "accelerations_high_per90",
                        "decelerations_high_per90", "second_half_hi_drop", "gk_distance_per90_km", "relocated_per90_m",
                        "cm_dm_distance_over_others", "wide_hi_over_central", "wide_peak_minus_central_kmh")
WIDE_ROLES = ("W", "FB")
CENTRAL_ROLES = ("CB", "DM", "CM")
LEAGUE_DIAGNOSTICS = ("matches", "through_balls_per90", "yellow_cards_per90", "penalty_conversion", "npxg_per90",
                      "np_goals_minus_xg", "key_passes_per_shot", "progressive_passes_team_per90",
                      "progressive_carries_team_per90")
# Shape checks without a numeric band (league mode): centre-backs contest among the most aerial duels (FBref 2023/24 via
# Football365: three of the five players with the most aerial duels won were centre-backs).
SHAPE_DIAGNOSTICS = ("aerial_duels_per90_by_role", "cb_aerial_rank", "field_tilt_team_range")
DIAGNOSTICS = ("replays_per_goal", "tracks_kit_number_share", "minutes", "possession_changes_per90", "carries_per90", "pressures_per90")


def compute_metrics(stream: list[Record], tracks: list[Record] | None = None) -> dict[str, float]:
    """Per-90 rates and ratios for one or more concatenated matches (period tables give the minutes)."""
    matches = [r for r in stream if r["type"] == "match"]
    minutes = sum((per["t_end"] - per["t"]) / 60.0 for m in matches for per in m["periods"]) or 1e-9
    scale = 90.0 / minutes
    events = [r for r in stream if r["type"] == "event"]
    counts = Counter(e["event_type"] for e in events)
    passes = [e for e in events if e["event_type"] in ("pass", "cross")]
    shots = [e for e in events if e["event_type"] == "shot"]
    possessions = [r for r in stream if r["type"] == "possession"]
    segments = [r for r in stream if r["type"] == "camera_segment"]
    replays = sum(1 for s in segments if s["kind"] == "replay")
    goals = counts["goal"]
    out = {
        "minutes": round(minutes, 2),
        "passes_per90": round(len(passes) * scale, 1),
        "pass_completion": round(sum(1 for p in passes if p["outcome"] == "success") / len(passes), 3) if passes else 0.0,
        "shots_per90": round(len(shots) * scale, 1),
        "goals_per90": round(goals * scale, 2),
        "xg_per_shot": round(sum(s.get("metrics", {}).get("xg", 0.0) for s in shots) / len(shots), 3) if shots else 0.0,
        "tackles_per90": round(counts["tackle"] * scale, 1),
        "interceptions_per90": round(counts["interception"] * scale, 1),
        "take_ons_per90": round(counts["take_on"] * scale, 1),
        "nutmegs_per90": round(counts["nutmeg"] * scale, 2),
        "fouls_per90": round(counts["foul"] * scale, 1),
        "corners_per90": round(counts["corner"] * scale, 1),
        "throw_ins_per90": round(counts["throw_in"] * scale, 1),
        "possession_mean_s": round(sum(p["t_end"] - p["t"] for p in possessions) / len(possessions), 2) if possessions else 0.0,
        "possession_changes_per90": round(counts["possession_change"] * scale, 1),
        "carries_per90": round(counts["carry"] * scale, 1),
        "pressures_per90": round(counts["pressure"] * scale, 1),
        "replays_per_goal": round(replays / goals, 2) if goals else float(replays),
    }
    if any(_version(m.get("generator", {}).get("version", "0.1.0")) >= (0, 2, 0) for m in matches):  # league mode: 0.2.0 events
        out.update(_league_metrics(events, shots, counts, scale, len(matches)))
    if any(r["type"] == "physical" for r in stream):
        out.update(physical_metrics(stream))
    if "penalties_per90" in out:
        out.update(season_metrics(stream))
    if tracks:
        players = [t for t in tracks if t["object"] == "player"]
        out["tracks_kit_number_share"] = round(sum(1 for t in players if "kit_number" in t.get("identity", {}).get("evidence", [])) / len(players), 3) if players else 0.0
    return out


def _version(text: str) -> tuple[int, ...]:
    """"0.10.0" -> (0, 10, 0): versions compare as numbers, not strings."""
    try:
        return tuple(int(x) for x in text.split("."))
    except ValueError:
        return (0,)


def _league_metrics(events: list[Record], shots: list[Record], counts: Counter, scale: float, matches: int) -> dict[str, float]:
    pens = [s for s in shots if "penalty" in s.get("qualifiers", [])]
    open_play = [s for s in shots if "penalty" not in s.get("qualifiers", [])]
    crosses = [e for e in events if e["event_type"] == "cross"]
    npxg = sum(s.get("metrics", {}).get("xg", 0.0) for s in open_play)
    key_passes = sum(1 for e in events if e["event_type"] in ("pass", "cross") and "key_pass" in e.get("qualifiers", []))
    return {
        "matches": matches,
        "penalties_per90": round(counts["penalty"] * scale, 2),
        "red_cards_per90": round(counts["card_red"] * scale, 2),
        "offsides_per90": round(counts["offside"] * scale, 2),
        "aerial_duels_per90": round(counts["aerial_duel"] * scale, 1),
        "substitutions_per_match": round(counts["substitution"] / max(1, matches), 2),
        "through_balls_per90": round(sum(1 for e in events if e["event_type"] == "pass" and "through_ball" in e.get("qualifiers", []))
                                     * scale, 1),
        "yellow_cards_per90": round(counts["card_yellow"] * scale, 2),
        "cross_completion": round(sum(1 for e in crosses if e["outcome"] == "success") / len(crosses), 3) if crosses else 0.0,
        "penalty_conversion": round(sum(1 for s in pens if s["outcome"] == "success") / len(pens), 3) if pens else 0.0,
        "npxg_per90": round(npxg * scale, 2),
        "np_goals_minus_xg": round(sum(1 for s in open_play if s["outcome"] == "success") - npxg, 1),
        "key_passes_per_shot": round(key_passes / len(open_play), 3) if open_play else 0.0,
    }


def season_metrics(stream: list[Record]) -> dict[str, Any]:
    """League mode: the leaders, team style and progression, from the Scout terminal's own engine
    (``regista.season.metrics.analyse_match``, the same definitions a scout reads) run on every match in the stream and
    added up per person (global id) and per club. Leaders count players with the qualifying minutes, the terminal's pool."""
    from regista.season.metrics import analyse_match, qualifying_minutes
    from regista.synth.generator import ROLE_OF_KIT

    groups: list[list[Record]] = []   # one per match: a match record opens it (pooled seasons repeat match ids)
    for r in stream:
        if r["type"] == "match" or not groups:
            groups.append([])
        groups[-1].append(r)
    people: dict[str, dict[str, float]] = {}
    minutes: Counter = Counter()
    club_of: dict[str, str] = {}
    role_of: dict[str, str] = {}
    clubs: dict[str, Counter] = {}
    for recs in groups:
        header = next((r for r in recs if r["type"] == "match"), None)
        if header is None:
            continue
        mm = analyse_match(recs)
        club = {t["team_id"]: t.get("club_id") or t["team_id"] for t in header["teams"]}
        for p in header["players"]:
            gid = p.get("global_player_id") or f"{header['match_id']}:{p['player_id']}"
            role_of[gid] = ROLE_OF_KIT.get(p["kit_number"], "?")
            club_of[gid] = club[p["team_id"]]
            if p["player_id"] in mm.minutes:
                minutes[gid] += mm.minutes[p["player_id"]]
                acc = people.setdefault(gid, Counter())
                acc.update(mm.counts.get(p["player_id"], {}))
        for team, c in mm.teams.items():
            clubs.setdefault(club[team], Counter()).update(c)
    club_minutes = {c: t["minutes"] for c, t in clubs.items()}
    qual = qualifying_minutes(max(club_minutes.values(), default=0.0))
    pool = [g for g in people if minutes[g] >= qual and minutes[g] > 0]
    out: dict[str, Any] = {}
    for key in LEADER_V:
        rates = [people[g].get(key, 0.0) * 90.0 / minutes[g] for g in pool]
        out[f"leader_{key}_per90"] = round(max(rates), 2) if rates else 0.0
    shots: dict[str, Counter] = {}
    for g, c in people.items():
        shots.setdefault(club_of[g], Counter())[g] += c.get("shots", 0.0)
    shares = [max(v.values()) / sum(v.values()) for v in shots.values() if sum(v.values())]
    out["top_shooter_share"] = round(max(shares), 3) if shares else 0.0
    ppda = [t["opp_build_up_passes"] / t["ppda_actions"] for t in clubs.values() if t.get("ppda_actions")]
    poss = [100.0 * t["possession_s"] / (t["possession_s"] + t["opp_possession_s"]) for t in clubs.values()
            if t.get("possession_s", 0.0) + t.get("opp_possession_s", 0.0) > 0]
    tilt = [100.0 * t["final_third_passes"] / (t["final_third_passes"] + t["opp_final_third_passes"]) for t in clubs.values()
            if t.get("final_third_passes", 0.0) + t.get("opp_final_third_passes", 0.0) > 0]
    out |= {"ppda_team_min": round(min(ppda), 1) if ppda else 0.0, "ppda_team_max": round(max(ppda), 1) if ppda else 0.0,
            "possession_team_max": round(max(poss), 1) if poss else 0.0,
            "possession_team_min": round(min(poss), 1) if poss else 0.0,
            "field_tilt_team_range": f"{min(tilt):.1f}-{max(tilt):.1f}" if tilt else "n/a"}
    team_minutes = sum(club_minutes.values()) or 1e-9
    prog_p = sum(c.get("progressive_passes", 0.0) for c in people.values())
    prog_c = sum(c.get("progressive_carries", 0.0) for c in people.values())
    out["prog_pass_carry_ratio"] = round(prog_p / prog_c, 2) if prog_c else 0.0
    out["progressive_passes_team_per90"] = round(prog_p * 90.0 / team_minutes, 1)
    out["progressive_carries_team_per90"] = round(prog_c * 90.0 / team_minutes, 1)
    roles: dict[str, list[float]] = {}
    for g in pool:
        if role_of[g] != "GK":
            duels = people[g].get("aerial_duels_won", 0.0) + people[g].get("aerial_duels_lost", 0.0)
            roles.setdefault(role_of[g], []).append(duels * 90.0 / minutes[g])
    by_role = {r: round(sum(v) / len(v), 2) for r, v in sorted(roles.items())}
    out["aerial_duels_per90_by_role"] = by_role
    order = sorted(by_role, key=lambda r: -by_role[r])
    out["cb_aerial_rank"] = order.index("CB") + 1 if "CB" in order else 0
    return out


def _roles(stream: list[Record]) -> dict[tuple[str, str], tuple[str, str]]:
    """(match id, player id) -> (role from the kit number, the person: global id when the match is a season's)."""
    from regista.synth.generator import ROLE_OF_KIT

    out = {}
    for m in (r for r in stream if r["type"] == "match"):
        for p in m["players"]:
            out[(m["match_id"], p["player_id"])] = (ROLE_OF_KIT.get(p["kit_number"], "?"),
                                                    p.get("global_player_id") or f"{m['match_id']}:{p['player_id']}")
    return out


def physical_metrics(stream: list[Record]) -> dict[str, float]:
    """The physical bands' metrics from ``physical`` records (league mode). Outfield players unless named otherwise."""
    from regista.synth.physical import per90

    roles = _roles(stream)
    periods = {m["match_id"]: m["periods"] for m in stream if m["type"] == "match"}
    phys = [r for r in stream if r["type"] == "physical"]
    # role and person in side tables keyed by the record's identity: the caller's records are never modified (they must
    # still validate against the events schema, which allows no extra fields)
    role_of: dict[int, str] = {}
    who_of: dict[int, str] = {}
    for r in phys:
        role_of[id(r)], who_of[id(r)] = roles.get((r["match_id"], r["player_id"]), ("?", r["player_id"]))
    out_ = [r for r in phys if role_of[id(r)] != "GK"]
    gk = [r for r in phys if role_of[id(r)] == "GK"]
    played = sum(r["played_s"] for r in out_) or 1e-9
    # season per-90 distance of regular outfielders
    by_who: dict[str, list[float]] = {}
    for r in out_:
        acc = by_who.setdefault(who_of[id(r)], [0.0, 0.0])
        acc[0] += r["metrics"]["distance_m"]
        acc[1] += r["played_s"]
    most = max((v[1] for v in by_who.values()), default=0.0)
    regular = [v[0] / v[1] * 5.4 for v in by_who.values() if v[1] >= 0.4 * most and v[1] > 0]   # km per 90
    # match peaks of outfielders who played most of the match
    long_ = [r for r in out_ if r["played_s"] >= 0.6 * sum(p["t_end"] - p["t"] for p in periods.get(r["match_id"], []))]
    halves: dict[int, list[float]] = {}
    for r in long_:
        for per in r.get("periods", []):
            h = halves.setdefault(per["period"], [0.0, 0.0, 0.0])
            h[0] += per["played_s"]
            h[1] += per["distance_m"]
            h[2] += per["hi_distance_m"]

    def drop(i: int) -> float:
        if 1 not in halves or 2 not in halves or not halves[1][i] or not halves[2][0]:
            return 0.0
        return round(1.0 - (halves[2][i] / halves[2][0]) / (halves[1][i] / halves[1][0]), 3)

    def role_rate(rs: tuple[str, ...], key: str) -> float:
        sel = [r for r in out_ if role_of[id(r)] in rs]
        return per90(sel, key) if sel else 0.0

    def role_peak(rs: tuple[str, ...]) -> float:
        sel = [r["metrics"]["peak_speed_kmh"] for r in long_ if role_of[id(r)] in rs]
        return sum(sel) / len(sel) if sel else 0.0

    others = tuple(sorted({role_of[id(r)] for r in out_} - {"CM", "DM"}))
    # each regular outfielder's season shares of walking and jogging time, and centre-backs' high-intensity distance
    shares: dict[str, list[float]] = {}
    cb: dict[str, list[float]] = {}
    for r in out_:
        acc = shares.setdefault(who_of[id(r)], [0.0, 0.0, 0.0])
        acc[0] += r["metrics"]["walking_s"]
        acc[1] += r["metrics"]["jogging_s"]
        acc[2] += r["played_s"]
        if role_of[id(r)] == "CB":
            c = cb.setdefault(who_of[id(r)], [0.0, 0.0, 0.0])
            c[0] += r["metrics"]["hi_distance_m"]
            c[1] += r["played_s"]
            c[2] += r["metrics"]["distance_m"]
    reg = {w for w, v in by_who.items() if v[1] >= 0.4 * most and v[1] > 0}
    walk = [v[0] / v[2] for w, v in shares.items() if w in reg and v[2]]
    jog = [v[1] / v[2] for w, v in shares.items() if w in reg and v[2]]
    cb_reg = [v for w, v in cb.items() if w in reg and v[1]]
    acc_h, dec_h = per90(out_, "accelerations_high"), per90(out_, "decelerations_high")
    return {
        "walking_share_min": round(min(walk), 3) if walk else 0.0,
        "walking_share_max": round(max(walk), 3) if walk else 0.0,
        "jogging_share_max": round(max(jog), 3) if jog else 0.0,
        "cb_hi_distance_per90_m": round(sum(v[0] for v in cb_reg) / sum(v[1] for v in cb_reg) * 5400.0, 0) if cb_reg else 0.0,
        "cb_distance_per90_km": round(sum(v[2] for v in cb_reg) / sum(v[1] for v in cb_reg) * 5.4, 2) if cb_reg else 0.0,
        "dec_acc_high_ratio": round(dec_h / acc_h, 2) if acc_h else 0.0,
        "players_measured": len(phys),
        "distance_per90_km": round(per90(out_, "distance_m") / 1000.0, 2),
        "distance_per90_min_km": round(min(regular), 2) if regular else 0.0,
        "distance_per90_max_km": round(max(regular), 2) if regular else 0.0,
        "hi_distance_per90_m": round(per90(out_, "hi_distance_m"), 0),
        "sprint_distance_per90_m": round(per90(out_, "sprint_distance_m"), 0),
        "sprints_per90": round(per90(out_, "sprints"), 1),
        "walking_time_share": round(sum(r["metrics"]["walking_s"] for r in out_) / played, 3),
        "jogging_time_share": round(sum(r["metrics"]["jogging_s"] for r in out_) / played, 3),
        "peak_speed_mean_kmh": round(sum(r["metrics"]["peak_speed_kmh"] for r in long_) / len(long_), 1) if long_ else 0.0,
        "peak_speed_max_kmh": max((r["metrics"]["peak_speed_kmh"] for r in out_), default=0.0),
        "second_half_distance_drop": drop(1),
        "second_half_hi_drop": drop(2),
        "zone3_per90_m": round(per90(out_, "zone3_m"), 0),
        "hi_efforts_per90": round(per90(out_, "hi_efforts"), 1),
        "accelerations_high_per90": round(per90(out_, "accelerations_high"), 1),
        "decelerations_high_per90": round(per90(out_, "decelerations_high"), 1),
        "gk_distance_per90_km": round(per90(gk, "distance_m") / 1000.0, 2) if gk else 0.0,
        "relocated_per90_m": round(per90(out_, "relocated_m"), 0),
        "cm_dm_distance_over_others": round(role_rate(("CM", "DM"), "distance_m") / (role_rate(others, "distance_m") or 1e-9), 3),
        "wide_hi_over_central": round(role_rate(WIDE_ROLES[:1], "hi_distance_m") / (role_rate(CENTRAL_ROLES + ("ST",), "hi_distance_m") or 1e-9), 3),
        "wide_peak_minus_central_kmh": round(role_peak(("W", "FB", "AM", "ST")) - role_peak(CENTRAL_ROLES), 2),
    }


def verdicts(metrics: dict[str, float], norms: dict[str, tuple[float, float, str, str]] | None = None) -> dict[str, str]:
    out = {}
    for key, (lo, hi, _unit, _note) in (NORMS if norms is None else norms).items():
        v = metrics.get(key)
        if v is None:
            out[key] = "n/a"
        elif v < lo:
            out[key] = "low"
        elif v > hi:
            out[key] = "high"
        else:
            out[key] = "in band"
    return out


def render_markdown(metrics: dict[str, float], title: str, profile: str | None = None, note: str | None = None) -> str:
    v = verdicts(metrics)
    lines = [f"# Synthetic realism report: {title}", ""]
    if profile:
        lines.append(f"Generator profile: **{profile}**. " + ("The demo profile is deliberately dense so a 3-minute sample fills a clip reel; its rates are expected to sit above the bands. " if profile == "demo" else "The league profile is the realistic one retuned for two halves and player ratings; with ratings it is checked against every band, the league-mode ones included. " if profile == "league" else "The realistic profile is tuned to sit inside the bands over a full match. "))
    if note:
        lines.append(note)
    lines += ["", f"Simulated minutes: {metrics.get('minutes', 0)}", "", f"Norms: {NORMS_SOURCE}", "",
              "| Metric | Value | Band | Verdict | Note |", "|---|---|---|---|---|"]
    for key, (lo, hi, unit, note_) in NORMS.items():
        val = metrics.get(key)
        shown = f"{val:.3f}" if isinstance(val, float) and val < 1.5 and key in ("pass_completion", "xg_per_shot") else f"{val}"
        lines.append(f"| {key} | {shown} {unit} | {lo}–{hi} | {v[key]} | {note_} |")
    inb = sum(1 for x in v.values() if x == "in band")
    lines += ["", f"**{inb} of {len(NORMS)} metrics in band.**", "", "Diagnostics (no band): " + ", ".join(f"{k}={metrics[k]}" for k in DIAGNOSTICS if k in metrics), ""]
    if "penalties_per90" in metrics:
        lv = verdicts(metrics, LEAGUE_NORMS)
        lines += ["## League mode (schema 0.2.0 events, players with ratings)", "",
                  "Rare events: a season is 30 thirty-minute matches (about ten full matches), so check these over several "
                  "seasons (`--repeat`).", "", "| Metric | Value | Band | Verdict | Source |", "|---|---|---|---|---|"]
        for key, (lo, hi, unit, note_) in LEAGUE_NORMS.items():
            lines.append(f"| {key} | {metrics.get(key)} {unit} | {lo}–{hi} | {lv[key]} | {note_} |")
        linb = sum(1 for x in lv.values() if x == "in band")
        lines += ["", f"**{linb} of {len(LEAGUE_NORMS)} league-mode metrics in band.**", "",
                  "Diagnostics (no band): " + ", ".join(f"{k}={metrics[k]}" for k in LEAGUE_DIAGNOSTICS if k in metrics), ""]
    if "distance_per90_km" in metrics:
        pv = verdicts(metrics, PHYSICAL_NORMS)
        lines += ["## Physical (league mode: every player's motion at 10 Hz)", "",
                  "Outfield players, per 90 minutes on the pitch, pooled. Synthetic: the simulator's own players, measured "
                  "exactly. Definitions: `regista.synth.physical.DEFINITIONS`.", "",
                  "| Metric | Value | Band | Verdict | Source |", "|---|---|---|---|---|"]
        for key, (lo, hi, unit, note_) in PHYSICAL_NORMS.items():
            lines.append(f"| {key} | {metrics.get(key)} {unit} | {lo}–{hi} | {pv[key]} | {note_} |")
        pinb = sum(1 for x in pv.values() if x == "in band")
        lines += ["", f"**{pinb} of {len(PHYSICAL_NORMS)} physical metrics in band.**", "",
                  "Diagnostics (no band): " + ", ".join(f"{k}={metrics[k]}" for k in PHYSICAL_DIAGNOSTICS if k in metrics), ""]
    if "leader_shots_per90" in metrics:
        for title, norms, intro in (
                ("Team style (league mode)", STYLE_NORMS, "Per club over the stream: the most and least pressing club "
                 "(PPDA, the Scout terminal's rule) and the clubs with the most and least of the ball. Field tilt (no "
                 f"published Premier League norm we could cite): {metrics.get('field_tilt_team_range')}%."),
                ("Individual leaders (league mode)", INDIVIDUAL_NORMS, "Each metric's top qualified player (the Scout "
                 "terminal's engine and pool) against the Premier League's third best (LEADER_V). One season gives a regular "
                 "about 300 minutes, so check leaders over three seasons (`--repeat 3`, about 900 minutes each, the "
                 "Premier League pool's minimum)."),
        ):
            v = verdicts(metrics, norms)
            lines += [f"## {title}", "", intro, "", "| Metric | Value | Band | Verdict | Source |", "|---|---|---|---|---|"]
            for key, (lo, hi, unit, note_) in norms.items():
                lines.append(f"| {key} | {metrics.get(key)} {unit} | {lo}–{hi} | {v[key]} | {note_} |")
            lines += ["", f"**{sum(1 for x in v.values() if x == 'in band')} of {len(norms)} in band.**", ""]
        lines += ["Shape checks (no numeric band): " + ", ".join(f"{k}={metrics[k]}" for k in SHAPE_DIAGNOSTICS if k in metrics), ""]
    return "\n".join(lines)


def report_match_dir(match_dir: Path) -> tuple[dict[str, float], str]:
    stream = list(iter_jsonl(match_dir / "events.jsonl"))
    tracks_path = match_dir / "tracks.jsonl"
    tracks = list(iter_jsonl(tracks_path)) if tracks_path.exists() else None
    match = next(r for r in stream if r["type"] == "match")
    gen = match.get("generator", {})
    profile = gen.get("params", {}).get("profile")
    metrics = compute_metrics(stream, tracks)
    return metrics, render_markdown(metrics, match["match_id"], profile)


def report_profile(profile: str, seeds: list[int], minutes: float) -> tuple[dict[str, float], str]:
    from regista.synth.generator import generate

    stream: list[Record] = []
    for seed in seeds:
        stream += generate(seed=seed, minutes=minutes, track_hz=1.0, profile=profile).stream
    metrics = compute_metrics(stream)
    return metrics, render_markdown(metrics, f"profile '{profile}', seeds {seeds}, {minutes:g} min each", profile)


def league_stream(league_path: Path | str, repeat: int = 1) -> list[Record]:
    """Every fixture of the league regenerated in memory with its players' ratings (league mode); ``repeat`` > 1 adds
    whole seasons with every seed shifted by 1000 per repeat (for rare events). Events only, no tracks."""
    from regista.season.audit import season_matches
    from regista.season.league import load_league

    return [r for _rnd, _header, s in season_matches(load_league(league_path), seasons=repeat) for r in s]


def report_league(league_path: Path | str, repeat: int = 1) -> tuple[dict[str, float], str]:
    metrics = compute_metrics(league_stream(league_path, repeat))
    title = f"the Regista League ({league_path})" + (f", {repeat} seasons (seeds +0, +1000, ...)" if repeat > 1 else "")
    return metrics, render_markdown(metrics, title, "league")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare synthetic match statistics with Premier League norms.")
    parser.add_argument("match_dir", nargs="?", type=Path, help="a generated match directory (events.jsonl)")
    parser.add_argument("--profile", choices=["demo", "realistic", "league"], help="instead of a directory, simulate this profile")
    parser.add_argument("--league", type=Path, nargs="?", const=Path("data/season/league.json"),
                        help="instead of a directory, regenerate this league's fixtures with their players' ratings")
    parser.add_argument("--repeat", type=int, default=1, help="with --league: this many seasons, seeds shifted by 1000 each")
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13])
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.match_dir:
        metrics, md = report_match_dir(args.match_dir)
    elif args.league:
        metrics, md = report_league(args.league, args.repeat)
    elif args.profile:
        metrics, md = report_profile(args.profile, args.seeds, args.minutes)
    else:
        parser.error("give a match directory or --profile")
    if args.json:
        out = {"metrics": metrics, "verdicts": verdicts(metrics)}
        if "penalties_per90" in metrics:
            out["league_verdicts"] = verdicts(metrics, LEAGUE_NORMS)
        if "distance_per90_km" in metrics:
            out["physical_verdicts"] = verdicts(metrics, PHYSICAL_NORMS)
        if "leader_shots_per90" in metrics:
            out["style_verdicts"] = verdicts(metrics, STYLE_NORMS)
            out["individual_verdicts"] = verdicts(metrics, INDIVIDUAL_NORMS)
        print(json.dumps(out, indent=2))
    else:
        print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
