"""Synthetic-data realism report: how a generated match compares with Premier League norms.

    python -m regista.synth.report data/synthetic/sample/syn_0294
    python -m regista.synth.report --profile realistic --seeds 11 12 13 --minutes 20
    python -m regista.synth.report --league data/season/league.json [--repeat 6]
    python -m regista.synth.report --catalogue [--out docs/catalogue/realism.md] [--regenerate [--level L] [--repeat 6]]

League streams also carry ``physical`` records (every player's 10 Hz motion summarised, regista.synth.physical); the
report checks them against physical bands from the Premier League (The Analyst / Opta) and the 2022 World Cup (FIFA's
tracking, Bradley 2023), each band with its source below. League streams also get team-style bands (PPDA, possession)
and individual-leader bands (each metric's top player against the Premier League's third best), computed with the Scout
terminal's own engine (regista.season.metrics). A season is about ten full matches, so the leader bands and the
rare-event bands (penalties, red cards) are a verdict only over six pooled seasons (``--league --repeat 6``, about 1,800
minutes a regular); on fewer (one season: about 300 minutes a regular, a handful of penalties) those verdicts are
printed as indicative, with each leader's minutes beside the value.

``--catalogue`` reports each level of the catalogue (docs/catalogue/build/design.md §10) against what can honestly be
checked below the professional line: one sourced band (U17 peak match speed), sourced orders between levels, assumed
orders (shown, never counted) and "no published band", with Premier League and elite figures beside some levels as
upper references only. It reads the committed measurement (data/catalogue/realism.json, six regenerated seasons of every
competition) and re-runs the checks on its stored aggregates, so it is fast; ``--regenerate`` measures the seasons
again and compares them with the committed file (writing it is ``python -m regista.catalogue reliability``'s job).

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
    "shot_accuracy_ex_blocks": (0.40, 0.54, "ratio", "non-penalty shots on target (goals and saves) / shots, blocked shots "
                                "left out, Opta's way: Premier League 49.9% in 2023/24 (a record), 45.1% over the twenty seasons "
                                "since 2003/04; the ten most accurate teams of 2023/24 ran from 50.3% to 57.3% (Adrian Clarke, "
                                "premierleague.com/news/4027257, 27 May 2024). The margins are ours"),
    "save_pct": (0.58, 0.735, "ratio", "non-penalty saves / non-penalty shots on target faced, FBref's Save% rule. Premier "
                 "League 2024/25 keepers with 500+ minutes ran from 51.5% (Walton) to 73.5% (Raya, the best) (Opta Analyst, "
                 "'The Best Goalkeeper Stats from the 2024-25 Premier League', 23 Apr 2025). The league as a whole sits between "
                 "its worst and best keepers; no league-wide figure could be read, so the band is ours inside that range"),
    "take_on_success": (0.30, 0.45, "ratio", "take-ons won / attempted: Premier League league average 36.7% in 2025/26 (Ryan "
                        "Benson, 'Creating Chaos: Who Are the Premier League's Most Impactful Dribblers?', Opta Analyst, 17 "
                        "Feb 2026; mid-season). The margins are ours"),
    "gk_long_pass_share": (0.37, 0.57, "ratio", "share of keepers' passes, goal kicks included, of 32 m or more: Premier League "
                           "46.6% in 2023/24 and 47.0% in 2024/25, down from 79.3% in 2014/15 (Opta Analyst, Ali Tweedale, "
                           "12 Sep 2025). Across 36 leagues in 2021/22 the share of keepers' passes of 40 m or more ran from "
                           "35.7% to 58.4% by league (CIES Football Observatory, Weekly Post 381). The margins are ours"),
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
    "shots_on_target": (2.08, "the leader, not the third best (the rest of the ranking could not be read): Haaland 2.08 "
                        "non-penalty and penalty shots on target per 90, 59 in all (StatMuse, Opta data, read 2026-10-24)",
                        0.5, 1.5),
    # (no touches-in-the-box leader band since review closing round 1: Regista's touch records follow its own rule,
    # regista.season.metrics.TOUCH_RECORDS, not FBref's touches, so its touches in the box are not comparable with FBref's
    # Att Pen either)
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
# One designed star must not be the league's only scoring threat (review closing round 1): the leader's lead over the
# next player, and the largest share of a club's chances one player takes. The lower bounds of the two gaps are 1 by
# definition (the leader is the leader); the upper bounds are the check.
INDIVIDUAL_NORMS["leader_npxg_gap"] = (1.0, 1.75, "ratio", "the leader's npxG per 90 over the second best's. Premier League "
                                       "2023/24, the ranking LEADER_V cites: Haaland 1.04, Isak 0.81, a ratio of 1.28. "
                                       "The upper bound is ours: six clubs give a smaller pool, whose leader sits further "
                                       "clear by chance")
INDIVIDUAL_NORMS["leader_goals_gap"] = (1.0, 2.0, "ratio", "the leader's goals per 90 over the second best's. Premier League "
                                        "2023/24, the ranking LEADER_V cites: Haaland 0.95, Isak 0.84, a ratio of 1.13. "
                                        "The upper bound is ours and wider than npxG's: goals are the noisiest count")
INDIVIDUAL_NORMS["top_npxg_share"] = (0.20, 0.40, "share", "the largest share of a club's non-penalty xG taken by one "
                                      "player. Premier League 2023/24 (StatMuse, Opta data, read 2026-10-24; xG with "
                                      "penalties): Haaland 29.37 of Man City's 82.63 (35.5%), Isak 20.29 of Newcastle's "
                                      "78.14 (26.0%), Watkins 16.92 of Aston Villa's 65.66 (25.8%). The margins are ours")
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
                      "progressive_carries_team_per90", "shot_outcomes", "gk_launch_pct_range", "gk_avg_pass_length_range")
# Role shapes (league mode, review closing round 1): which roles make the numbers, not only how many there are. Per-90
# means of qualified players by kit role (regista.synth.generator.ROLE_OF_KIT), each check an order between roles. The
# Premier League figures are examples of each role (mostly StatMuse, Opta data, 2023/24, read 2026-10-24; each check names
# its source), not role means; the order they show is what is checked. Verdicts over six pooled seasons (LEADER_SEASONS),
# like the leaders. Review closing round 2 added full-backs' touches, defenders' progressive and long passes, and where
# full-backs' crosses start.
ROLE_SHAPE_KEYS = ("passes", "touches", "passes_received", "crosses", "tackles_won", "fouls", "fouls_won",
                   "progressive_passes", "progressive_carries", "long_passes")
# A full-back's cross must start where crosses start (review closing round 2: before generator 0.7.0 half of them were
# 50 m balls from his own half): the check also asks that full-backs' open-play crosses start, at the median, within
# this many metres of the opponent's goal line, the final third plus the overlap.
FB_CROSS_START_MAX_M = 40.0
CB_LONG_PASSES_FLOOR = 2.5   # per 90, passes over 30 yards (the terminal's long_passes); the floor is ours, below Saliba's
ROLE_SHAPES: dict[str, tuple[str, str]] = {   # name: (the order checked, its source)
    "passes_cb_dm_over_st": ("centre-backs and holding midfielders each attempt more passes per 90 than strikers",
                             "StatMuse (Opta data, 2023/24), completed passes per 90: Rodri (DM) 103.48, van Dijk (CB) 74.73, against Watkins (ST) 12.87 "
                             "and Haaland (ST) 10.47"),
    "touches_cb_dm_over_st": ("centre-backs and holding midfielders each touch the ball more per 90 than strikers",
                              "StatMuse (Opta data, 2023/24), touches per 90: Rodri 126.54, van Dijk 92.38, against Watkins 29.95 and Haaland 24.64"),
    "touches_fb_over_w": ("full-backs touch the ball more per 90 than wingers",
                          "StatMuse (Opta data, 2023/24, read 2026-10-24), touches per 90: Trippier (FB) 98.61 and Robertson (FB) "
                          "92.60, against Saka (W) 65.55; the season's ten most touches include a full-back (Porro, 2,786) and no "
                          "winger (FBref via Football365, 20 May 2024)"),
    "fb_crosses_third_of_w": ("full-backs cross at least a third as often as wingers, and their open-play crosses start (median) "
                              f"within {FB_CROSS_START_MAX_M:g} m of the opponent's goal line",
                              "StatMuse (Opta data, 2023/24), crosses per 90: Trippier (FB) 8.61 against Saka (W) 5.58; two of the top three crossers "
                              "LEADER_V cites, Doughty and Robertson, play at full-back or wing-back. The start-position condition is "
                              "ours: a cross is a ball from a wide area into the centre (Opta), not a long ball from his own half"),
    "prog_passes_cb_fb_over_st": ("centre-backs and full-backs each make more progressive passes per 90 than strikers",
                                  "two centre-backs, van Dijk (457) and van Hecke (449), made the most Premier League progressive "
                                  "passes from the start of 2024/25 to October 2025 (Brighton & Hove Albion, 'Albion Analytics', 24 "
                                  "Oct 2025; provider not named); the 2023/24 top ten includes a full-back (Zinchenko, 229) and no "
                                  "striker (FBref via Football365, 20 May 2024)"),
    "cb_long_passes_floor": (f"centre-backs attempt at least {CB_LONG_PASSES_FLOOR:g} long passes per 90, and more than strikers",
                             "StatMuse (Opta data, 2023/24, read 2026-10-24), long ball passes per 90: van Dijk (CB) 7.20, Saliba (CB) "
                             "3.42, against Haaland (ST) 0.18. Opta's long ball and the terminal's long pass (over 30 yards) are "
                             "not the same cut; the floor is ours, below Saliba's"),
    "st_tackles_below_fb_cb_dm": ("strikers win fewer tackles per 90 than full-backs, centre-backs and holding midfielders",
                                  "StatMuse (Opta data, 2023/24), tackles per 90: Haaland 0.21 and Watkins 0.34, against van Dijk (CB) 1.10, Antonee "
                                  "Robinson (FB) 2.56, and the holding midfielders who lead LEADER_V's tackles (Palhinha "
                                  "5.14)"),
    "fouls_won_w_st_over_cb": ("wingers and strikers are each fouled more per 90 than centre-backs",
                               "StatMuse (Opta data, 2023/24), fouls drawn per 90: Saka (W) 2.13, Watkins 1.15 and Haaland 1.06 (ST), against van Dijk "
                               "(CB) 0.37"),
}


def role_shape_checks(by_role: dict[str, dict[str, float]], fb_cross_start_m: float | None = None) -> dict[str, bool]:
    """``by_role``: metric -> role -> per-90 mean; ``fb_cross_start_m``: the median distance from the opponent's goal line
    at which full-backs' open-play crosses start (None: no such cross). True where the league's roles keep the order
    ROLE_SHAPES names."""
    def r(key: str, role: str) -> float:
        return by_role.get(key, {}).get(role, 0.0)

    return {
        "passes_cb_dm_over_st": min(r("passes", "CB"), r("passes", "DM")) > r("passes", "ST"),
        "touches_cb_dm_over_st": min(r("touches", "CB"), r("touches", "DM")) > r("touches", "ST"),
        "touches_fb_over_w": r("touches", "FB") > r("touches", "W"),
        "fb_crosses_third_of_w": r("crosses", "FB") >= r("crosses", "W") / 3.0 > 0.0
        and fb_cross_start_m is not None and fb_cross_start_m <= FB_CROSS_START_MAX_M,
        "prog_passes_cb_fb_over_st": min(r("progressive_passes", "CB"), r("progressive_passes", "FB"))
        > r("progressive_passes", "ST"),
        "cb_long_passes_floor": r("long_passes", "CB") >= CB_LONG_PASSES_FLOOR and r("long_passes", "CB") > r("long_passes", "ST"),
        "st_tackles_below_fb_cb_dm": r("tackles_won", "ST") < min(r("tackles_won", "FB"), r("tackles_won", "CB"),
                                                                   r("tackles_won", "DM")),
        "fouls_won_w_st_over_cb": min(r("fouls_won", "W"), r("fouls_won", "ST")) > r("fouls_won", "CB"),
    }


# Shape checks without a numeric band (league mode): centre-backs win the most aerial duels (FBref 2023/24 via
# Football365: three of the five players with the most aerial duels won were centre-backs, the other two target
# forwards). Contests are a diagnostic: since generator 0.5.0 keepers launch long to the front three, so strikers contest
# about as many as centre-backs (and win far fewer), as target forwards do.
# Crosses (generator 0.7.0, review closing round 2): where open-play crosses start, by the crosser's role (median metres
# from the opponent's goal line; corners left out), and who receives the completed ones (share by role). No band: no
# sourced figure was read; a cross is a ball from a wide area into the centre (Opta), so it starts near the box and is
# met by the players attacking it, mostly forwards.
SHAPE_DIAGNOSTICS = ("aerial_duels_won_per90_by_role", "cb_aerial_won_rank", "aerial_duels_per90_by_role", "cb_aerial_rank",
                     "field_tilt_team_range", "cross_start_m_by_role", "crosses_received_by_role")
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
    outcome = Counter("goal" if s["outcome"] == "success" else next((q for q in s.get("qualifiers", [])
                      if q in ("saved", "blocked", "off_target")), "other") for s in open_play)
    unblocked = len(open_play) - outcome["blocked"]
    on_target = outcome["goal"] + outcome["saved"]
    return {
        "shot_accuracy_ex_blocks": round(on_target / unblocked, 3) if unblocked else 0.0,
        "take_on_success": round(sum(1 for e in events if e["event_type"] == "take_on" and e["outcome"] == "success")
                                 / counts["take_on"], 3) if counts["take_on"] else 0.0,
        "save_pct": round(outcome["saved"] / on_target, 3) if on_target else 0.0,
        "shot_outcomes": "/".join(f"{k} {outcome[k]}" for k in ("goal", "saved", "blocked", "off_target")),
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
    gk_passes = gk_long = 0
    cross_start: dict[str, list[float]] = {}
    cross_to: Counter = Counter()
    for recs in groups:
        header = next((r for r in recs if r["type"] == "match"), None)
        if header is None:
            continue
        keepers = {p["player_id"] for p in header["players"] if p.get("position") == "GK"}
        _crosses(recs, header, cross_start, cross_to)
        for r in recs:   # keepers' passes, goal kicks included, and how many travel 32 m or more (Opta's long pass)
            if r.get("event_type") in ("pass", "cross") and r.get("player_id") in keepers:
                gk_passes += 1
                gk_long += r.get("metrics", {}).get("pass_distance_m", 0.0) >= 32.0
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
    ids = [h["match_id"] for h in (next((r for r in recs if r["type"] == "match"), None) for recs in groups) if h]
    out["seasons"] = max(1, round(len(ids) / max(1, len(set(ids)))))   # pooled seasons repeat every match id
    for key in LEADER_V:
        rates = sorted(((people[g].get(key, 0.0) * 90.0 / minutes[g], g) for g in pool), reverse=True)
        out[f"leader_{key}_per90"] = round(rates[0][0], 2) if rates else 0.0
        out[f"leader_{key}_minutes"] = round(minutes[rates[0][1]]) if rates else 0
        if key in ("npxg", "goals"):   # the leader's lead over the next player
            out[f"leader_{key}_gap"] = round(rates[0][0] / rates[1][0], 2) if len(rates) > 1 and rates[1][0] > 0 else 0.0
    out["gk_long_pass_share"] = round(gk_long / gk_passes, 3) if gk_passes else 0.0
    gks = [c for g, c in people.items() if role_of[g] == "GK" and c.get("gk_open_passes", 0.0) >= 10]
    launch = [100.0 * c.get("gk_launches", 0.0) / c["gk_open_passes"] for c in gks]
    length = [c.get("gk_pass_length_sum", 0.0) / c["gk_open_passes"] for c in gks]
    out["gk_launch_pct_range"] = f"{min(launch):.1f}-{max(launch):.1f}%" if launch else "n/a"
    out["gk_avg_pass_length_range"] = f"{min(length):.1f}-{max(length):.1f} m" if length else "n/a"
    shots: dict[str, Counter] = {}
    for g, c in people.items():
        shots.setdefault(club_of[g], Counter())[g] += c.get("shots", 0.0)
    shares = [max(v.values()) / sum(v.values()) for v in shots.values() if sum(v.values())]
    out["top_shooter_share"] = round(max(shares), 3) if shares else 0.0
    chances: dict[str, Counter] = {}
    for g, c in people.items():
        chances.setdefault(club_of[g], Counter())[g] += c.get("npxg", 0.0)
    shares = [max(v.values()) / sum(v.values()) for v in chances.values() if sum(v.values())]
    out["top_npxg_share"] = round(max(shares), 3) if shares else 0.0
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
    won: dict[str, list[float]] = {}
    for g in pool:
        if role_of[g] != "GK":
            duels = people[g].get("aerial_duels_won", 0.0) + people[g].get("aerial_duels_lost", 0.0)
            roles.setdefault(role_of[g], []).append(duels * 90.0 / minutes[g])
            won.setdefault(role_of[g], []).append(people[g].get("aerial_duels_won", 0.0) * 90.0 / minutes[g])
    by_role = {r: round(sum(v) / len(v), 2) for r, v in sorted(roles.items())}
    won_by_role = {r: round(sum(v) / len(v), 2) for r, v in sorted(won.items())}
    out["aerial_duels_per90_by_role"] = by_role
    out["aerial_duels_won_per90_by_role"] = won_by_role
    order = sorted(by_role, key=lambda r: -by_role[r])
    out["cb_aerial_rank"] = order.index("CB") + 1 if "CB" in order else 0
    order = sorted(won_by_role, key=lambda r: -won_by_role[r])
    out["cb_aerial_won_rank"] = order.index("CB") + 1 if "CB" in order else 0
    out["cross_start_m_by_role"] = {r: round(_median(v), 1) for r, v in sorted(cross_start.items()) if r != "GK"}
    total = sum(cross_to.values())
    out["crosses_received_by_role"] = {r: round(n / total, 3) for r, n in sorted(cross_to.items())} if total else {}
    by_role: dict[str, dict[str, float]] = {}
    for key in ROLE_SHAPE_KEYS:
        acc: dict[str, list[float]] = {}
        for g in pool:
            if role_of[g] != "GK":
                acc.setdefault(role_of[g], []).append(people[g].get(key, 0.0) * 90.0 / minutes[g])
        by_role[key] = {r: round(sum(v) / len(v), 2) for r, v in sorted(acc.items())}
    out["role_per90"] = by_role
    fb_start = out["cross_start_m_by_role"].get("FB")
    out |= {f"shape_{k}": v for k, v in role_shape_checks(by_role, fb_start).items()}
    return out


def _median(xs: list[float]) -> float:
    ys = sorted(xs)
    n = len(ys)
    return 0.0 if not n else ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2.0


def _crosses(recs: list[Record], header: Record, start: dict[str, list[float]], received: Counter) -> None:
    """One match's open-play crosses (corners left out): the distance from the opponent's goal line where each starts,
    by the crosser's kit role, into ``start``; the receiver's role of each completed one into ``received``."""
    from regista.synth.generator import PITCH_L, ROLE_OF_KIT

    role = {p["player_id"]: ROLE_OF_KIT.get(p["kit_number"], "?") for p in header["players"]}
    ltr = {p["period"]: p.get("left_to_right_team_id") for p in header.get("periods", [])}
    corner_poss = {r["id"] for r in recs if r["type"] == "possession" and r.get("gained_by") == "set_piece"}
    for e in recs:
        if e.get("event_type") != "cross" or "pitch" not in e:
            continue
        x = e["pitch"]["x"]
        period = e.get("clock", {}).get("period")
        to_line = PITCH_L - x if ltr.get(period) == e.get("team_id") else x
        if to_line < 3.0 and e.get("possession_id") in corner_poss:   # a corner from the flag
            continue
        start.setdefault(role.get(e["player_id"], "?"), []).append(to_line)
        if e.get("outcome") == "success" and e.get("related_player_id"):
            received[role.get(e["related_player_id"], "?")] += 1


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


# Individual leader bands and rare events (penalties, red cards) are a verdict over at least this many pooled seasons
# (``--repeat 6``, about 1,800 minutes a regular). Three seasons proved too few in review round 2: the first three hold one
# penalty where about six are expected, and one season's star can sit a tenth above a leader band by chance.
LEADER_SEASONS = 6
INDICATIVE = f"indicative (under {LEADER_SEASONS} seasons)"


RARE_EVENTS = ("penalties_per90", "red_cards_per90")   # about 0.3 and 0.1 a match: a season holds a handful of each


def league_verdicts(metrics: dict[str, Any]) -> dict[str, str]:
    """The league-mode bands' verdicts. Penalties and red cards are rare (a season of 30 thirty-minute matches has about
    five penalties and one or two red cards; none at all is common), so below ``LEADER_SEASONS`` pooled seasons their
    verdicts are marked indicative, like the leaders'. Every other league-mode band is a verdict on one season."""
    v = verdicts(metrics, LEAGUE_NORMS)
    if metrics.get("seasons", 1) >= LEADER_SEASONS:
        return v
    return {k: f"{x}, {INDICATIVE}" if k in RARE_EVENTS and x != "n/a" else x for k, x in v.items()}


def individual_verdicts(metrics: dict[str, Any]) -> dict[str, str]:
    """The leader bands' verdicts. One season gives a regular about 300 minutes (about three full matches), so a single
    season's leaders are a small sample: below ``LEADER_SEASONS`` pooled seasons each verdict is marked indicative, and
    only the pooled check (``--league --repeat 6``, about 1,800 minutes a regular, twice the Premier League pool's
    900-minute minimum) is the rule the tests apply."""
    v = verdicts(metrics, INDIVIDUAL_NORMS)
    if metrics.get("seasons", 1) >= LEADER_SEASONS:
        return v
    return {k: f"{x}, {INDICATIVE}" if x != "n/a" else x for k, x in v.items()}


def role_shape_verdicts(metrics: dict[str, Any]) -> dict[str, str]:
    """"holds" or "fails" for each ROLE_SHAPES order; below ``LEADER_SEASONS`` pooled seasons marked indicative, like the
    leaders (one season gives each role's regulars about 300 minutes each)."""
    out = {}
    for k in ROLE_SHAPES:
        v = metrics.get(f"shape_{k}")
        out[k] = "n/a" if v is None else "holds" if v else "fails"
    if metrics.get("seasons", 1) >= LEADER_SEASONS:
        return out
    return {k: f"{x}, {INDICATIVE}" if x != "n/a" else x for k, x in out.items()}


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
        lv = league_verdicts(metrics)
        lines += ["## League mode (schema 0.2.0 events, players with ratings)", "",
                  "Rare events: a season is 30 thirty-minute matches (about ten full matches), so penalties and red cards "
                  f"are a verdict only over {LEADER_SEASONS} or more pooled seasons (`--repeat {LEADER_SEASONS}`); on one "
                  f"season they are marked '{INDICATIVE}'.", "", "| Metric | Value | Band | Verdict | Source |",
                  "|---|---|---|---|---|"]
        for key, (lo, hi, unit, note_) in LEAGUE_NORMS.items():
            lines.append(f"| {key} | {metrics.get(key)} {unit} | {lo}–{hi} | {lv[key]} | {note_} |")
        linb = sum(1 for x in lv.values() if x.startswith("in band"))
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
                 "terminal's engine and pool) against the Premier League's third best (LEADER_V), with the leader's minutes "
                 "beside the value. One season gives a regular about 300 minutes (about three full matches), so these bands "
                 f"are a verdict only over {LEADER_SEASONS} or more pooled seasons (`--repeat {LEADER_SEASONS}`, about "
                 "1,800 minutes each, twice the Premier League pool's 900-minute minimum); on fewer every verdict is marked "
                 f"'{INDICATIVE}'. This stream: {metrics.get('seasons', 1)} season(s)."),
        ):
            leaders = norms is INDIVIDUAL_NORMS
            v = individual_verdicts(metrics) if leaders else verdicts(metrics, norms)
            lines += [f"## {title}", "", intro, "", "| Metric | Value | Band | Verdict | Source |", "|---|---|---|---|---|"]
            for key, (lo, hi, unit, note_) in norms.items():
                mins = (metrics.get(key.replace("_per90", "_minutes")) if leaders and key.startswith("leader_") and key.endswith("_per90")
                        else None)   # the gap rows are ratios: no minutes beside them
                shown = f"{metrics.get(key)} {unit}" + (f" ({mins} min)" if mins is not None else "")
                lines.append(f"| {key} | {shown} | {lo}–{hi} | {v[key]} | {note_} |")
            inb = sum(1 for x in v.values() if x.startswith("in band"))
            lines += ["", f"**{inb} of {len(norms)} in band" + (f" ({INDICATIVE}).**" if leaders and
                                                                  metrics.get("seasons", 1) < LEADER_SEASONS else ".**"), ""]
        lines += ["Shape checks (no numeric band): " + ", ".join(f"{k}={metrics[k]}" for k in SHAPE_DIAGNOSTICS if k in metrics), ""]
        rv = role_shape_verdicts(metrics)
        lines += ["## Role shapes (league mode)", "", "Which roles make the numbers: per-90 means of qualified players by kit "
                  "role, each check an order between roles. The Premier League figures are examples of each role, not role "
                  f"means (each check names its source; mostly StatMuse, Opta data, 2023/24). Verdicts over {LEADER_SEASONS} or more pooled seasons; on fewer "
                  f"marked '{INDICATIVE}'.", "", "| Check | Order | Verdict | Premier League |", "|---|---|---|---|"]
        for k, (order, source) in ROLE_SHAPES.items():
            lines.append(f"| {k} | {order} | {rv[k]} | {source} |")
        table = metrics.get("role_per90", {})
        roles = [r for r in ("CB", "FB", "DM", "CM", "AM", "W", "ST") if any(r in v for v in table.values())]
        lines += ["", "| Per 90 | " + " | ".join(roles) + " |", "|---|" + "---|" * len(roles)]
        for key, v in table.items():
            lines.append(f"| {key} | " + " | ".join(f"{v.get(r, 0.0)}" for r in roles) + " |")
        lines.append("")
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


# ============================================================================ the catalogue (--catalogue)
#
# Each catalogue level against the checks it can honestly get (regista.catalogue.realism): a sourced band, sourced orders
# between levels, assumed orders (measured, shown, never counted) and "no published band". By default the report reads
# the committed measurement (data/catalogue/realism.json: six regenerated seasons of every competition, written by
# ``python -m regista.catalogue reliability``) and re-runs the checks on its stored aggregates, so it takes well under a
# second; ``--regenerate`` measures the seasons again (a few minutes on ten cores; ``--level`` limits it to some levels)
# and compares them with the committed file. It never writes the committed file.

CATALOGUE_LEVEL_LABELS = {
    "semi_pro/senior/men": "Semi-pro men", "college/college/men": "College men", "amateur/senior/men": "Amateur men",
    "academy/U20/men": "Academy U20", "academy/U19/men": "Academy U19", "academy/U18/men": "Academy U18",
    "academy/U17/men": "Academy U17", "semi_pro/senior/women": "Semi-pro women", "college/college/women": "College women",
}
# Premier League bands shown beside the senior semi-pro and college men's levels as an upper reference (no verdict):
# (label, band key in NORMS or PHYSICAL_NORMS, how a level aggregate is read in the band's unit, what differs).
CATALOGUE_PL_REFERENCES: list[tuple[str, str, Any, str]] = [
    ("pass completion", "pass_completion", lambda a: a["pass_pct"] / 100.0,
     "outfield players' passes here; the band counts every pass"),
    ("shots per 90, both teams", "shots_per90", lambda a: 2.0 * a["team_shots_per90"], ""),
    ("goals per 90, both teams", "goals_per90", lambda a: 2.0 * a["team_goals_per90"], ""),
    ("distance per 90 (km)", "distance_per90_km", lambda a: a["outfield_per90"]["distance"] / 1000.0, ""),
    ("distance at 20 km/h or more per 90 (m)", "hi_distance_per90_m", lambda a: a["outfield_per90"]["hi_distance"], ""),
    ("distance at 25 km/h or more per 90 (m)", "sprint_distance_per90_m", lambda a: a["outfield_per90"]["sprint_distance"], ""),
    ("mean peak match speed (km/h)", "peak_speed_mean_kmh", lambda a: a["peak_speed_mean"],
     "matches with 10+ minutes played here; the band's matches had 60%+ played"),
]
# Women's and college references (regista.catalogue.realism.REFERENCES): the level aggregate shown beside each, where
# one measures the same thing; the reference's own text says what differs (per match, sprint test, women's zones).
CATALOGUE_REFERENCE_VALUES = {
    "distance": ("distance per 90", lambda a: f"{a['outfield_per90']['distance']:,.0f} m"),
    "peak_speed_mean": ("mean peak match speed", lambda a: f"{a['peak_speed_mean']:.2f} km/h"),
}
CATALOGUE_NOT_COMPARABLE = {
    ("S11",): "not comparable (a team's total per match)",
    ("S3",): "not comparable (a sprint-test top speed)",
}


def _catalogue_league(index: Path | None):
    from regista.catalogue import store
    from regista.catalogue.taxonomy import ENGLAND_ID
    from regista.season.league import load_league

    league = load_league(store.competition_path(store.entry(ENGLAND_ID, index), index))
    return league, store.new_competitions(index)


def catalogue_matches_measured(seasons: int, levels: list[str] | None = None) -> int:
    """Matches in ``seasons`` measurement seasons of every competition (of ``levels``): each full double round robin."""
    from regista.catalogue.taxonomy import COMPETITIONS

    return sum(c.teams * (c.teams - 1) * seasons for c in COMPETITIONS if levels is None or c.level_key in levels)


def _check_fields(c: Record) -> Record:
    return {k: c.get(k) for k in ("value", "outside_by", "values", "steps", "verdict")}


def catalogue_drift(committed: Record, rechecked: Record) -> list[str]:
    """The checks whose committed verdict differs from the checks' code re-run on the same stored aggregates."""
    out = []
    for kind in ("bands", "orders"):
        old = {c["id"]: _check_fields(c) for c in committed.get(kind, [])}
        new = {c["id"]: _check_fields(c) for c in rechecked.get(kind, [])}
        out += sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
    return out


def catalogue_summary(data: Record) -> Record:
    """Counts: sourced checks (the band and the sourced orders) and assumed orders, by verdict; for the sourced checks
    also how many are calibrated to their source (``calibrated``) and how many follow level scales set in the source's
    direction (``scaled``), counted among those that pass."""
    sourced = list(data.get("bands", [])) + [o for o in data.get("orders", []) if o.get("basis", "sourced") != "assumed"]
    assumed = [o for o in data.get("orders", []) if o.get("basis") == "assumed"]

    def count(checks: list[Record]) -> Record:
        verdicts = [c.get("verdict") for c in checks]
        return {"total": len(checks), "pass": verdicts.count("pass"), "fail": verdicts.count("fail"),
                "not separated": verdicts.count("not separated"), "not measured": verdicts.count(None)}

    passing = [c for c in sourced if c.get("verdict") == "pass"]
    return {"sourced": {**count(sourced), "bands": len(data.get("bands", [])),
                        "calibrated": sum(1 for c in passing if c.get("calibrated")),
                        "scaled": sum(1 for c in passing if not c.get("calibrated")),
                        "extended": sum(1 for c in sourced if c.get("extends"))},
            "assumed": count(assumed)}


def regenerate_catalogue(repeats: int, workers: int | None = None, levels: list[str] | None = None,
                         index: Path | None = None) -> Record:
    """Measure the catalogue again: every competition (of ``levels``) for ``repeats`` regenerated seasons, in memory,
    and the realism checks on the result (``regista.catalogue.realism.compute``). Nothing is written. A run over some
    levels leaves every check that needs another level "not measured"."""
    import os

    from regista.catalogue.measure import level_of, measure
    from regista.catalogue.realism import compute
    from regista.season.metrics import load_metrics
    from regista.catalogue import store
    from regista.catalogue.taxonomy import ENGLAND_ID

    league, comps = _catalogue_league(index)
    league_path = store.competition_path(store.entry(ENGLAND_ID, index), index)
    xt = load_metrics(league_path, Path(os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))).xt
    chosen = [c for c in [league, *comps] if levels is None or level_of(c) in levels]
    return compute(league, comps, repeats, measure(chosen, repeats, xt, workers))


def _num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "not measured"
    if isinstance(v, float) and abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:,.{digits}f}" if isinstance(v, float) else str(v)


def _val(v: Any, unit: str) -> str:
    """An order's value in its unit: metres as whole numbers, everything else to two decimals."""
    if v is None:
        return "not measured"
    return f"{v:,.0f}" if unit.startswith("m ") else f"{v:,.2f}"


def _step_ratio(st: Record) -> str:
    return f"{st['margin'] / st['se']:.1f}" if st.get("se") else "n/a"


def _weakest(o: Record) -> str:
    """The step closest to failing: the lowest margin over its standard error (the margin alone without one)."""
    steps = o.get("steps") or []
    if not steps:
        return "not measured"
    st = min(steps, key=lambda s: (s["margin"] / s["se"]) if s.get("se") else s["margin"])
    lv = CATALOGUE_LEVEL_LABELS
    digits = 1 if o["unit"].startswith("m ") else 2
    return (f"{lv.get(st['lower'], st['lower'])} to {lv.get(st['higher'], st['higher'])}: {st['margin']:+,.{digits}f} "
            f"({_step_ratio(st)} SE)")


CATALOGUE_COMMAND = "python -m regista.synth.report --catalogue --out docs/catalogue/realism.md"


def render_catalogue(data: Record, *, source: str, stale: str | None = None, drift: list[str] | None = None,
                     comparison: Record | None = None, command: str = CATALOGUE_COMMAND) -> str:
    """The catalogue realism report in Markdown, from a realism verdicts record (the committed file, re-checked, or a
    fresh measurement). Deterministic: no dates or timings, so docs/catalogue/realism.md can be checked against it."""
    from regista.catalogue.realism import (NOT_CHECKED, REFERENCES, SCALE_NOTE, SOURCES, WOMEN_ZONE_NOTE, YOUTH_ZONE_NOTE,
                                           level_kinds)
    from regista.catalogue.taxonomy import COMPETITIONS, LEVELS

    lv_label = CATALOGUE_LEVEL_LABELS
    levels = data.get("levels") or {}
    seasons = data.get("seasons")
    measured_levels = [k for k in LEVELS if k in levels]
    summary = catalogue_summary(data)
    s, a = summary["sourced"], summary["assumed"]
    lines = ["# Catalogue realism report", "",
             f"Generated by `{command}`; do not edit by hand. "
             "Everything in it is synthetic: Regista's own simulated players, measured exactly, set against what published "
             "studies report. Below the professional line almost nothing is published, so each level gets only the checks "
             "a source supports, and says so.", "",
             f"**Measurement:** {source}. Generator {data.get('generator_version')}, catalogue fingerprint "
             f"`{data.get('catalogue_fingerprint')}`, {seasons} regenerated seasons of "
             f"{'every' if len(measured_levels) == len(LEVELS) else 'each measured'} competition's full double round "
             f"robin ({catalogue_matches_measured(seasons or 0, measured_levels):,} matches), never the 3-8 uploaded "
             "matches, which are far too few for a verdict.", ""]
    if stale:
        lines += [f"**Stale:** {stale}. The numbers below are the file's own and may not describe the current catalogue; "
                  "run `python -m regista.catalogue reliability` to measure again.", ""]
    if drift:
        lines += [f"**The committed verdicts differ from the checks' code** for {', '.join(drift)}: shown as the code "
                  "computes them on the committed aggregates; run `python -m regista.catalogue recheck-realism`.", ""]
    if comparison:
        lines += [f"**Compared with the committed measurement:** {comparison['text']}", ""]
    lines += ["## Verdicts at a glance", "",
              f"- **Sourced checks: {s['pass']} of {s['total']} pass** ({s['bands']} published band and "
              f"{s['total'] - s['bands']} sourced orders between levels; {s['fail']} fail, {s['not separated']} not separated, "
              f"{s['not measured']} not measured). Of those that pass, {s['calibrated']} confirm a calibration (a level "
              "scale was set from the same source: the U17 band and the two women's pass gaps) and the other "
              f"{s['scaled']} follow from level scales set in the source's direction; none independently validates "
              "football below the professional line. "
              f"{s['extended']} of the {s['total'] - s['bands']} sourced orders extend a direction the source reports "
              "between other levels (amateurs against internationals in small-sided games, elite women against elite "
              "men) to the catalogue's levels, and say so.",
              f"- **Assumed orders: {a['pass']} of {a['total']} hold, {a['fail']} fail** ({a['not separated']} not "
              f"separated, {a['not measured']} not measured). No source covers these steps; they are measured and shown, "
              "never counted as a check.",
              "- **Event rates** have no published band at any level below the professional line. Premier League bands "
              "stand beside senior semi-pro and college men as an upper reference only, with no verdict.",
              "- **England semi-pro men** (the Regista League) keep their own report against Premier League bands, "
              "unchanged: `python -m regista.synth.report --league` (docs/realism-report.md). The generator was tuned to "
              "those bands, so they are a tuning target there, not independent evidence.", "",
              f"{SCALE_NOTE}", "",
              "## Kinds of check", "",
              "- **band**: a published band read for this level: pass or fail.",
              "- **order**: a direction a source reports, checked on the pooled seasons. A step passes at "
              f"{data.get('separation_se', 2.0):g} standard errors or more the way the source reports, fails as clearly the "
              "other way, and is otherwise not separated. Where the source also gives a size (the women's pass gap), the "
              "step must fall inside it. Where the source compares other levels, the order is marked *extended*: the "
              "build extends the source's direction to the catalogue's levels.",
              "- **calibrated / scaled**: every sourced check says how the build relates to it. *Calibrated*: a level "
              "scale was set from the same source's number, so a pass confirms the build follows its source. *Scaled*: "
              "the level scales were set in the source's direction, so a pass shows that direction carries through the "
              "simulation. Neither is independent evidence about football.",
              "- **assumed order**: a direction no source covers at these levels (Regista's assumption). Measured the same "
              "way, never counted.",
              "- **reference**: a figure from a higher level shown beside the number, no verdict.",
              "- **none**: no published band. The number is shown; nothing is claimed.", "",
              "| Level | Competitions | Event rates | Physical | Sourced orders | Assumed orders |",
              "|---|---|---|---|---|---|"]
    for key in LEVELS:
        k = level_kinds(key)
        comps = ", ".join(c.name for c in COMPETITIONS if c.level_key == key)
        lines.append(f"| {lv_label[key]} | {comps} | {k['events']} | {k['physical']} | "
                     f"{', '.join(k['orders']) or 'none'} | {', '.join(k['assumed_orders']) or 'none'} |")
    lines += ["", "## The levels as measured", "",
              "Pooled over every competition of the level and every measurement season. Per-90 rates are per outfield "
              "player; shots and goals are per team per 90, penalties included; peak match speed is the mean of "
              "outfielders' match top speeds (matches with 10+ minutes played). A match is two halves of 15 minutes, as "
              "in the league, and per-90 rates normalise it.", "",
              "| Level | Seasons | Outfield minutes | Pass % | Ball losses | Passes | Team shots | Team goals | Peak speed (km/h) "
              "| Distance (m) | 20+ km/h (m) | 25+ km/h (m) | Tackles won | Fouls |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in measured_levels:
        g = levels[key]
        p = g["outfield_per90"]
        lines.append(f"| {lv_label[key]} | {g['seasons']} | {g['outfield_minutes']:,.0f} | {_num(g['pass_pct'])} | "
                     f"{_num(p['ball_losses'])} | {_num(p['passes'])} | {_num(g['team_shots_per90'])} | "
                     f"{_num(g['team_goals_per90'])} | {_num(g['peak_speed_mean'])} | {p['distance']:,.0f} | "
                     f"{p['hi_distance']:,.0f} | {p['sprint_distance']:,.0f} | {_num(p['tackles_won'])} | {_num(p['fouls'])} |")
    for key in LEVELS:
        if key not in levels:
            lines.append(f"| {lv_label[key]} | not measured in this run | | | | | | | | | | | | |")
    lines += ["", "\"Seasons\" counts competition-seasons: a level with two competitions measured six times has 12.", "",
              "## Band (sourced)", "", "| Check | Level | Measured | Band | Verdict | Source |", "|---|---|---|---|---|---|"]
    for b in data.get("bands", []):
        lines.append(f"| {b['label']} | {lv_label.get(b['level'], b['level'])} | {_num(b['value'])} {b['unit']} | "
                     f"{b['low']}-{b['high']} {b['unit']} | **{b['verdict'] or 'not measured'}** | "
                     f"{', '.join(b['sources'])} |")
    for b in data.get("bands", []):
        if b.get("calibration"):
            lines += ["", f"Calibrated ({b['id']}): {b['calibration']}."]

    def order_table(orders: list[Record], assumed: bool) -> list[str]:
        head = ("| Check | Levels, lowest expected first | Weakest step (margin, SE ratio) | Verdict | "
                + ("Sources cover only |" if assumed else "Sources |"))
        out = [head, "|---|---|---|---|---|"]
        for o in orders:
            vals = ", ".join(f"{lv_label.get(level, level)} {_val(v, o['unit'])}" for level, v in
                             zip(o["levels"], o.get("values") or [None] * len(o["levels"])))
            if assumed:
                cov = o.get("covers") or {}
                src = (f"{', '.join(cov.get('sources', []))}: {cov['span']}" if cov.get("span") else "none")
                if o.get("by_construction"):
                    src += "; holds by construction (the youth speed scales are interpolated)"
                if o.get("contrary"):
                    src += f"; against it: {o['contrary']}"
            else:
                src = ", ".join(o["sources"]) + (f"; the step must fall inside {o['gap'][0]:g}-{o['gap'][1]:g}"
                                                 if o.get("gap") else "")
                src += "; extended by the build" if o.get("extends") else ""
                src += "; calibrated" if o.get("calibrated") else "; scaled"
            out.append(f"| {o['label']} ({o['unit']}) | {vals} | {_weakest(o)} | **{o['verdict'] or 'not measured'}** "
                       f"| {src} |")
        return out

    orders = data.get("orders", [])
    lines += ["", "## Orders between levels (sourced)", ""]
    sourced_orders = [o for o in orders if o.get("basis", "sourced") != "assumed"]
    lines += order_table(sourced_orders, assumed=False)
    lines += ["", "How the build relates to each sourced order:", ""]
    for o in sourced_orders:
        rel = [f"extended: {o['extends']}"] if o.get("extends") else []
        if o.get("calibration"):
            rel.append(f"{'calibrated' if o.get('calibrated') else 'scaled'}: {o['calibration']}")
        lines.append(f"- {o['id']}: {'; '.join(rel) or 'the source compares these levels itself'}.")
    lines += ["", "## Assumed orders (no published band)", "",
              "No source covers these steps. They state Regista's assumption, are measured exactly like the sourced "
              "orders and are never counted as checks.", ""]
    lines += order_table([o for o in orders if o.get("basis") == "assumed"], assumed=True)
    failing = [(o, st) for o in orders for st in (o.get("steps") or []) if st["verdict"] != "pass"]
    if failing:
        lines += ["", "Steps that do not pass:", ""]
        for o, st in failing:
            kind = "assumed order" if o.get("basis") == "assumed" else "sourced order"
            lines.append(f"- {o['id']} ({kind}): {lv_label.get(st['lower'], st['lower'])} to "
                         f"{lv_label.get(st['higher'], st['higher'])} {st['margin']:+,.2f} {o['unit']}"
                         + (f", against season-to-season noise of +/- {2.0 * st['se']:,.2f} (2 standard errors)"
                            if st.get("se") else "")
                         + f": **{st['verdict']}**" + (", outside the sourced gap" if st.get("outside_gap") else "") + ".")
    lines += ["", "## References (no verdict)", "",
              "Premier League bands (the Regista League's report) beside the two levels that may be read against them. "
              "They are upper references: the catalogue's levels are below the professional line, and every level is "
              "scaled from the Regista League, which was tuned to these bands.", "",
              "| Measure | Band | " + " | ".join(lv_label[k] for k in ("semi_pro/senior/men", "college/college/men"))
              + " | What differs |", "|---|---|---|---|---|"]
    all_norms = {**NORMS, **PHYSICAL_NORMS}
    for label, key, read, differs in CATALOGUE_PL_REFERENCES:
        lo, hi, _unit, _note = all_norms[key]
        cells = []
        for level in ("semi_pro/senior/men", "college/college/men"):
            g = levels.get(level)
            cells.append("not measured" if g is None else _num(round(read(g), 3), 3 if hi < 2 else 2))
        lines.append(f"| {label} | {lo:g}-{hi:g} | {' | '.join(cells)} | {differs or 'same measure'} |")
    lines += ["", "Elite and higher-level figures beside the levels they are quoted for (realism.REFERENCES):", "",
              "| Level | Reference | Source | Measured here |", "|---|---|---|---|"]
    for level, refs in REFERENCES.items():
        for metric, items in refs.items():
            for r in items:
                g = levels.get(level)
                shown = CATALOGUE_NOT_COMPARABLE.get(tuple(r["sources"]), "not comparable")
                if metric in CATALOGUE_REFERENCE_VALUES and tuple(r["sources"]) not in CATALOGUE_NOT_COMPARABLE:
                    name, fmt = CATALOGUE_REFERENCE_VALUES[metric]
                    shown = "not measured" if g is None else f"{name} {fmt(g)}"
                lines.append(f"| {lv_label[level]} | {r['text']} | {', '.join(r['sources'])} | {shown} |")
    lines += ["", "## Speed zones", "", f"- Women's pools: {WOMEN_ZONE_NOTE}", f"- Youth pools: {YOUTH_ZONE_NOTE}", "",
              "## Not checked", ""]
    lines += [f"- {x}" for x in NOT_CHECKED]
    lines += ["- Long-ball share, or any 'more direct' style, by level: no source was found.",
              "- Event rates of any single level against a band: none is published below the professional line.",
              "- Each competition's uploaded matches (3-8): far too few for a verdict. The checks run on the levels' full "
              "regenerated seasons.", "",
              "## Method", "", data.get("method", ""), "",
              "Every competition is classified on tier, age group and gender; its level is the pool key "
              "`tier/age_group/gender`. Competitions of one level are pooled: "
              + "; ".join(f"{lv_label[k]}: {', '.join(c.name for c in COMPETITIONS if c.competition_id in levels[k]['competitions'])}"
                          for k in measured_levels) + ".", "",
              "## Sources", ""]
    lines += [f"- [{k}] {v}" for k, v in sorted(SOURCES.items(), key=lambda kv: int(kv[0][1:]))]
    lines += [f"- Premier League bands: {NORMS_SOURCE} Physical bands: each band's own source in "
              "`regista.synth.report.PHYSICAL_NORMS` (The Analyst / Opta; FIFA's 2022 World Cup physical analysis, "
              "Bradley 2023).", ""]
    return "\n".join(lines)


def report_catalogue(index: Path | None = None, regenerate: bool = False, repeats: int | None = None,
                     workers: int | None = None, levels: list[str] | None = None) -> tuple[Record, str, bool]:
    """The catalogue realism report: (the verdicts record, the Markdown, ok). By default from the committed measurement
    beside the catalogue index, its checks re-run on its stored aggregates (no season regenerated). ``ok`` is False when
    the committed file is missing or stale, when its verdicts differ from the checks' code, or (with ``regenerate``) when
    the fresh measurement differs from it."""
    from regista.catalogue import realism as rea
    from regista.catalogue import store
    from regista.catalogue.measure import DEFAULT_REPEATS

    path = Path(index or store.index_path()).with_name(rea.FILE_NAME)
    try:
        shown = str(path.resolve().relative_to(store.repo_root(path.parent / "catalogue.json")))
    except ValueError:
        shown = str(path)
    try:
        committed = json.loads(path.read_text())
    except (OSError, ValueError):
        committed = None
    stale = None
    if committed is None:
        stale = f"no {rea.FILE_NAME} beside the catalogue index"
    else:
        league, comps = _catalogue_league(index)
        stale = rea.load(path, league, comps).get("stale")
    if not regenerate:
        if committed is None:
            return {"stale": stale}, f"# Catalogue realism report\n\n**{stale}**: run `python -m regista.catalogue reliability`.\n", False
        data = rea.recheck(committed)
        drift = catalogue_drift(committed, data)
        md = render_catalogue(data, source=f"the committed file `{shown}`, its checks re-run on its stored aggregates",
                              stale=stale, drift=drift)
        return {**data, "stale": stale, "drift": drift}, md, not stale and not drift
    repeats = repeats or DEFAULT_REPEATS
    data = json.loads(json.dumps(regenerate_catalogue(repeats, workers, levels, index), sort_keys=True))
    names = ", ".join(CATALOGUE_LEVEL_LABELS.get(k, k) for k in sorted(data["levels"]))
    if not data["levels"]:
        same, text = False, "nothing was measured."
    elif committed is None or committed.get("seasons") != repeats:
        same, text = False, (f"not compared ({'no committed file' if committed is None else 'the committed file has ' + str(committed.get('seasons')) + ' seasons'}).")
    else:
        differ = [k for k in data["levels"] if data["levels"][k] != committed["levels"].get(k)
                  or data["per_season"][k] != committed["per_season"].get(k)]
        same = not differ and not stale
        text = (f"the regenerated levels ({names}) equal the committed file's aggregates, season by season."
                if not differ else f"these levels differ from the committed file: {', '.join(differ)}.")
    cmd = ("python -m regista.synth.report --catalogue --regenerate"
           + "".join(f" --level {lv}" for lv in levels or []) + (f" --repeat {repeats}" if repeats != DEFAULT_REPEATS else ""))
    md = render_catalogue(data, source=f"regenerated now ({repeats} seasons; levels: {names})", stale=stale,
                          comparison={"text": text, "same": same}, command=cmd)
    return {**data, "stale": stale, "comparison": {"text": text, "same": same}}, md, same


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare synthetic match statistics with Premier League norms.")
    parser.add_argument("match_dir", nargs="?", type=Path, help="a generated match directory (events.jsonl)")
    parser.add_argument("--profile", choices=["demo", "realistic", "league"], help="instead of a directory, simulate this profile")
    parser.add_argument("--league", type=Path, nargs="?", const=Path("data/season/league.json"),
                        help="instead of a directory, regenerate this league's fixtures with their players' ratings")
    parser.add_argument("--repeat", type=int, default=None,
                        help="with --league: this many seasons, seeds shifted by 1000 each (default 1); with --catalogue "
                             "--regenerate: this many measurement seasons (default 6, the committed measurement's)")
    parser.add_argument("--catalogue", type=Path, nargs="?", const=None, default=False, metavar="INDEX",
                        help="each catalogue level against its sourced band, sourced orders, assumed orders and 'no "
                             "published band', from the committed measurement beside the index (default "
                             "data/catalogue/catalogue.json); fast, nothing regenerated unless --regenerate")
    parser.add_argument("--regenerate", action="store_true",
                        help="with --catalogue: measure every level again on regenerated seasons (a few minutes on ten "
                             "cores) and compare with the committed measurement; never writes it")
    parser.add_argument("--level", action="append", default=None,
                        help="with --catalogue --regenerate: only this level (tier/age_group/gender; repeatable)")
    parser.add_argument("--workers", type=int, default=None, help="with --catalogue --regenerate: worker processes")
    parser.add_argument("--seeds", type=int, nargs="+", default=[11, 12, 13])
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.catalogue is not False:
        return _catalogue_main(args, parser)
    if args.match_dir:
        metrics, md = report_match_dir(args.match_dir)
    elif args.league:
        metrics, md = report_league(args.league, args.repeat or 1)
    elif args.profile:
        metrics, md = report_profile(args.profile, args.seeds, args.minutes)
    else:
        parser.error("give a match directory or --profile")
    if args.json:
        out = {"metrics": metrics, "verdicts": verdicts(metrics)}
        if "penalties_per90" in metrics:
            out["league_verdicts"] = league_verdicts(metrics)
        if "distance_per90_km" in metrics:
            out["physical_verdicts"] = verdicts(metrics, PHYSICAL_NORMS)
        if "leader_shots_per90" in metrics:
            out["style_verdicts"] = verdicts(metrics, STYLE_NORMS)
            out["individual_verdicts"] = individual_verdicts(metrics)
            out["role_shape_verdicts"] = role_shape_verdicts(metrics)
            out["individual_rule"] = (f"leader bands are a verdict over {LEADER_SEASONS}+ pooled seasons (--repeat "
                                      f"{LEADER_SEASONS}); this stream has {metrics.get('seasons', 1)}")
        print(json.dumps(out, indent=2))
    else:
        print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    return 0


def _catalogue_main(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from regista.catalogue.taxonomy import LEVELS

    if args.match_dir or args.league or args.profile:
        parser.error("--catalogue reports the catalogue's levels: give no match directory, --league or --profile with it")
    if (args.level or args.workers or args.repeat) and not args.regenerate:
        parser.error("--level, --workers and --repeat go with --catalogue --regenerate")
    bad = [lv for lv in args.level or [] if lv not in LEVELS]
    if bad:
        parser.error(f"unknown level {bad[0]!r}: one of {', '.join(LEVELS)}")
    data, md, ok = report_catalogue(args.catalogue, args.regenerate, args.repeat, args.workers, args.level)
    if args.json:
        print(json.dumps({**data, "summary": catalogue_summary(data), "ok": ok}, indent=2, sort_keys=True))
    else:
        print(md)
    if args.out:
        args.out.write_text(md, encoding="utf-8")
    if not ok:
        print("catalogue realism: not current (see the report's first lines)", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
