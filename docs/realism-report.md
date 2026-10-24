# Synthetic realism report

Regenerated on 2026-10-24 from the current code (league generator 0.7.0, event schema 0.2.0). Everything in it is
synthetic: Regista's own simulated players and matches, measured exactly, compared with published Premier League
figures. The bands are sanity checks, not ground truth. Each band names its source, and where a margin is ours the
report says so.

It covers two things:

1. **The Regista League**, the Scout view's data: the committed season in `data/season/league.json`. That is 30 matches
   of two 15-minute halves, 903.5 simulated minutes, generated in league mode, where hidden player ratings drive the
   outcomes. It has six sections: event rates, league-mode events (schema 0.2.0), physical output at 10 Hz, team style,
   individual leaders and role shapes. Command: `python3 -m regista.synth.report --league`.
2. **The realistic profile**: the generator without player ratings, as the vision layer's training matches and the
   CLAUDE.md demo seed use it. Seeds 21-28, 30 minutes each. Command:
   `python3 -m regista.synth.report --profile realistic --seeds 21 22 23 24 25 26 27 28 --minutes 30`. Its output is
   byte-identical to `main`, because league mode changes nothing without ratings (`tests/test_backcompat.py`).

**Verdicts at a glance**

| Section | One season (the committed league) | Six seasons pooled (`--repeat 6`, 180 matches, 5,423 minutes) |
|---|---|---|
| Event rates | 13 of 13 in band | 13 of 13 |
| League-mode events | 10 of 11; penalties are low, but that verdict is only indicative on one season | 11 of 11 |
| Physical (outfield players, 10 Hz) | 14 of 14 | 14 of 14 |
| Team style | 4 of 4 | 4 of 4 |
| Individual leaders | 12 of 14, all indicative; interceptions leader and top npxG share are high | 14 of 14 |
| Role shapes | 8 of 8 hold (indicative) | 8 of 8 hold |

One season gives a regular player about 300 minutes, so rare events (penalties, red cards), individual leaders and role
shapes count as verdicts only over six or more pooled seasons. On a single season the report marks them "indicative".
The pooled run is `python3 -m regista.synth.report --league --repeat 6`, with seeds shifted by 1000 for each season.

## 1. The Regista League (one season, as committed)

Generator profile: **league**. The league profile is the realistic one retuned for two halves and player ratings; with ratings it is checked against every band, the league-mode ones included. 

Simulated minutes: 903.54

Norms: Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth.

| Metric | Value | Band | Verdict | Note |
|---|---|---|---|---|
| passes_per90 | 887.9 passes | 800.0–1100.0 | in band | attempted passes and crosses, both teams |
| pass_completion | 0.807 ratio | 0.78–0.87 | in band | completed / attempted |
| shots_per90 | 25.0 shots | 20.0–32.0 | in band | both teams |
| goals_per90 | 2.49 goals | 2.2–3.6 | in band | both teams |
| xg_per_shot | 0.102 xG | 0.08–0.13 | in band | mean expected goals per shot |
| tackles_per90 | 38.6 tackles | 28.0–45.0 | in band | both teams |
| interceptions_per90 | 16.3 interceptions | 14.0–30.0 | in band | both teams |
| take_ons_per90 | 39.5 take-ons | 28.0–50.0 | in band | attempted dribbles past a defender |
| nutmegs_per90 | 0.9 nutmegs | 0.5–3.0 | in band | rarely reported; broadcast estimate |
| fouls_per90 | 20.6 fouls | 18.0–28.0 | in band | both teams |
| corners_per90 | 11.1 corners | 8.0–13.0 | in band | both teams |
| throw_ins_per90 | 48.6 throw-ins | 35.0–55.0 | in band | both teams |
| possession_mean_s | 2.59 seconds | 1.5–4.5 | in band | mean time one player holds the ball |

**13 of 13 metrics in band.**

Diagnostics (no band): replays_per_goal=7.32, minutes=903.54, possession_changes_per90=237.6, carries_per90=248.6, pressures_per90=331.4

### League mode (schema 0.2.0 events, players with ratings)

Rare events: a season is 30 thirty-minute matches (about ten full matches), so penalties and red cards are a verdict only over 6 or more pooled seasons (`--repeat 6`); on one season they are marked 'indicative (under 6 seasons)'.

| Metric | Value | Band | Verdict | Source |
|---|---|---|---|---|
| penalties_per90 | 0.1 penalties | 0.15–0.45 | low, indicative (under 6 seasons) | Premier League 72-125 penalties a season (1997/98-2023/24), 0.19-0.33 a match: The Analyst on premierleague.com, 2 Jun 2024 (premierleague.com/news/4029218) |
| red_cards_per90 | 0.2 red cards | 0.04–0.25 | in band, indicative (under 6 seasons) | Premier League 30-47 a season 2018/19-2022/23 (premierleague.com/news/3533373), 0.08-0.12 a match; 2023/24 ran at 0.22 a match by December (theanalyst.com) |
| offsides_per90 | 3.69 offsides | 2.5–5.5 | in band | about 2 a team a match: Leeds United 76 in 38 Premier League games 2020/21 (leedsunited.com); Liverpool's opponents 95-144 a season (anfieldindex.com). Secondary sources |
| aerial_duels_per90 | 25.1 contests | 20.0–40.0 | in band | Premier League 22,917 aerial duels in a season, 60.3 a game counted per player (Opta counts a won and a lost duel for every contest), so about 30 contests a game (anfieldindex.com, an older season; secondary) |
| substitutions_per_match | 7.53 per match | 6.0–9.5 | in band | Premier League 7.89 substitutions a match in 2023/24, both teams (The Analyst, theanalyst.com). Per match, not per 90: a league match is 30 minutes |
| cross_completion | 0.201 ratio | 0.16–0.26 | in band | open-play crosses completed: Premier League 18.8% (2020/21), 19.6%, 21.1%, 20.9% (2023/24), 21.7% (2024/25 after seven rounds), 10-season average 19.5% (Adrian Clarke, premierleague.com/news/4148090, 13 Oct 2024). The margins either side are ours |
| shot_accuracy_ex_blocks | 0.447 ratio | 0.4–0.54 | in band | non-penalty shots on target (goals and saves) / shots, blocked shots left out, Opta's way: Premier League 49.9% in 2023/24 (a record), 45.1% over the twenty seasons since 2003/04; the ten most accurate teams of 2023/24 ran from 50.3% to 57.3% (Adrian Clarke, premierleague.com/news/4027257, 27 May 2024). The margins are ours |
| save_pct | 0.714 ratio | 0.58–0.735 | in band | non-penalty saves / non-penalty shots on target faced, FBref's Save% rule. Premier League 2024/25 keepers with 500+ minutes ran from 51.5% (Walton) to 73.5% (Raya, the best) (Opta Analyst, 'The Best Goalkeeper Stats from the 2024-25 Premier League', 23 Apr 2025). The league as a whole sits between its worst and best keepers; no league-wide figure could be read, so the band is ours inside that range |
| take_on_success | 0.375 ratio | 0.3–0.45 | in band | take-ons won / attempted: Premier League league average 36.7% in 2025/26 (Ryan Benson, 'Creating Chaos: Who Are the Premier League's Most Impactful Dribblers?', Opta Analyst, 17 Feb 2026; mid-season). The margins are ours |
| gk_long_pass_share | 0.463 ratio | 0.37–0.57 | in band | share of keepers' passes, goal kicks included, of 32 m or more: Premier League 46.6% in 2023/24 and 47.0% in 2024/25, down from 79.3% in 2014/15 (Opta Analyst, Ali Tweedale, 12 Sep 2025). Across 36 leagues in 2021/22 the share of keepers' passes of 40 m or more ran from 35.7% to 58.4% by league (CIES Football Observatory, Weekly Post 381). The margins are ours |
| prog_pass_carry_ratio | 1.37 ratio | 1.2–3.0 | in band | progressive passes per progressive carry (FBref rules, regista.season.metrics). FBref 2023/24 via Football365 (20 May 2024): the five most progressive passers made 1,602, the five most progressive carriers 840, about 1.9 to 1 (our arithmetic). A derived band: no league total could be read (FBref answered 403) |

**10 of 11 league-mode metrics in band.**

Diagnostics (no band): matches=30, through_balls_per90=0.9, yellow_cards_per90=3.49, penalty_conversion=1.0, npxg_per90=2.48, np_goals_minus_xg=-0.9, key_passes_per_shot=0.704, progressive_passes_team_per90=27.9, progressive_carries_team_per90=20.4, shot_outcomes=goal 24/saved 60/blocked 62/off_target 104, gk_launch_pct_range=6.7-51.4%, gk_avg_pass_length_range=21.4-36.1 m

### Physical (league mode: every player's motion at 10 Hz)

Outfield players, per 90 minutes on the pitch, pooled. Synthetic: the simulator's own players, measured exactly. Definitions: `regista.synth.physical.DEFINITIONS`.

| Metric | Value | Band | Verdict | Source |
|---|---|---|---|---|
| distance_per90_km | 10.4 km | 9.5–11.5 | in band | Premier League 2024/25 per-90 distances run from 8.5 km (lowest regular starter) to 12.3 (highest regular starter) and 12.9 (highest, 600+ min) (The Analyst, OA-PHYS); 2022 World Cup teams ran 108.1 ± 3.6 km a match, about 10 km per outfield player (Bradley 2023, FIFA-PHYS) |
| distance_per90_min_km | 8.95 km | 8.5–10.0 | in band | the lowest regular outfielder: 8.5 km (Murillo), then 8.8-9.0 (The Analyst 2024/25, 1,500+ min). Regulars here: at least 40% of the most minutes anyone played |
| distance_per90_max_km | 12.18 km | 11.0–13.0 | in band | the highest: 12.3 km (Kulusevski, 1,500+ min), 12.9 (Yarmoliuk, 600+ min) (The Analyst 2024/25) |
| hi_distance_per90_m | 1049.0 m | 600.0–1100.0 | in band | >= 20 km/h. 2022 World Cup: 9,001 ± 850 m a team a match, about 800-900 per outfield player; central roles about 0.5-0.8 km, wide roles 1.0-1.1 (Bradley 2023 Parts 1-2, FIFA-PHYS); > 19.8 km/h about 760 m a match, range 618-1,001 (systematic review, HSR-REV) |
| sprint_distance_per90_m | 237.0 m | 150.0–330.0 | in band | >= 25 km/h. 2022 World Cup: 2,345 ± 314 m a team a match, about 210-235 per outfield player (FIFA-PHYS); > 25.1 km/h about 200 m a match, range 153-295 (HSR-REV) |
| sprints_per90 | 14.3 sprints | 6.0–24.0 | in band | >= 25 km/h for >= 1 s. No published league mean: the Premier League's most frequent sprinter had 702 by 23 March 2025 (The Analyst), about 24 a match over the 29 rounds played (our arithmetic); 33 ± 11 a match at the 2014 World Cup above 25.2 km/h (Chmura 2017, via HSR-REV). A derived band |
| walking_share_min | 0.508 share | 0.48–0.6 | in band | the regular who walks least (time below 6 km/h): Premier League 2024/25 lowest 54.2% (Soucek) (The Analyst, OA-PHYS). Individual extreme against individual extreme; the margins are ours |
| walking_share_max | 0.679 share | 0.66–0.84 | in band | the regular who walks most: Premier League 2024/25 highest 77.6% (Cunha) (The Analyst). The margins are ours; the inner one is wider because six clubs have about a third of the Premier League's regulars, and the extreme of a smaller group sits further inside |
| jogging_share_max | 0.368 share | 0.28–0.38 | in band | the regular who jogs most (6-15 km/h): Premier League 2024/25 highest 34.7% (Soucek), then 32-33% (The Analyst). The margins are ours |
| cb_hi_distance_per90_m | 785.0 m | 450.0–900.0 | in band | centre-backs (regulars), >= 20 km/h: central roles about 0.5-0.8 km a match at the 2022 World Cup (Bradley 2023 Parts 1-2, FIFA-PHYS). The lower margin is ours |
| dec_acc_high_ratio | 1.87 ratio | 1.0–2.5 | in band | high decelerations per high acceleration (both 3 m/s^2 or more, held 1 s): in soccer high and very high decelerations are more frequent than accelerations, the largest gap of any team sport (SMD -1.74 and -3.19; Harper, Carling and Kiely 2019, Sports Medicine 49:1923-47, pmc.ncbi.nlm.nih.gov/articles/PMC6851047). The upper bound is ours |
| peak_speed_mean_kmh | 31.6 km/h | 29.0–33.0 | in band | mean of each outfielder's top speed in a match (60%+ of it played). 2022 World Cup, complete matches: 30.2-30.8 (centre-backs, holding and central midfielders), 32.1-32.3 (wide and attacking roles, centre-forwards) (Bradley 2023 Part 1). A league match is 30 minutes, so its peaks sit a little lower |
| peak_speed_max_kmh | 36.7 km/h | 35.0–37.5 | in band | the league's fastest: in the 2024/25 Premier League only van de Ven passed 37 km/h, then 36.2-36.7 (The Analyst); the 2022 World Cup's top ten were 35.3-35.7 (Bradley 2023 Part 1) |
| second_half_distance_drop | 0.049 share | 0.02–0.12 | in band | per-minute distance, second half against first: about 7% lower at the 2022 World Cup, 6.0-9.8% by role (Bradley 2023 Part 1) |

**14 of 14 physical metrics in band.**

Diagnostics (no band): players_measured=886, walking_time_share=0.594, jogging_time_share=0.313, cb_distance_per90_km=10.08, zone3_per90_m=1615.0, hi_efforts_per90=66.7, accelerations_high_per90=69.0, decelerations_high_per90=129.0, second_half_hi_drop=0.081, gk_distance_per90_km=3.9, relocated_per90_m=41.0, cm_dm_distance_over_others=1.077, wide_hi_over_central=1.241, wide_peak_minus_central_kmh=2.39

### Team style (league mode)

Per club over the stream: the most and least pressing club (PPDA, the Scout terminal's rule) and the clubs with the most and least of the ball. Field tilt (no published Premier League norm we could cite): 36.9-59.7%.

| Metric | Value | Band | Verdict | Source |
|---|---|---|---|---|
| ppda_team_min | 11.6 passes | 7.5–12.5 | in band | the most intense press (lowest PPDA). Premier League: Liverpool 8.62, the lowest in 2021/22 (Wyscout, premierleague.com/news/4250153); in 2024/25 the ten best pressers ran from 9.9 to 12.3 (Playmakerstats, via Yahoo Sports, 9 Jun 2025) |
| ppda_team_max | 15.9 passes | 12.0–17.5 | in band | the most passive (highest PPDA). 2021/22: Norwich 16.93, the highest in Europe's top five leagues, Wolves 14.78, Everton 14.63 (Wyscout, premierleague.com/news/4250153) |
| possession_team_max | 52.5 % | 52.0–66.0 | in band | the highest possession share: Premier League 2023/24 Man City 65.7%, then 62.0, 61.8 (StatMuse, Opta data). Six clubs span less of the range than twenty |
| possession_team_min | 46.7 % | 34.0–48.0 | in band | the lowest possession share: Premier League 2023/24 Sheffield United 35.3%, then 40.2, 40.6 (StatMuse, Opta data) |

**4 of 4 in band.**

### Individual leaders (league mode)

Each metric's top qualified player (the Scout terminal's engine and pool) against the Premier League's third best (LEADER_V), with the leader's minutes beside the value. One season gives a regular about 300 minutes (about three full matches), so these bands are a verdict only over 6 or more pooled seasons (`--repeat 6`, about 1,800 minutes each, twice the Premier League pool's 900-minute minimum); on fewer every verdict is marked 'indicative (under 6 seasons)'. This stream: 1 season(s).

| Metric | Value | Band | Verdict | Source |
|---|---|---|---|---|
| leader_shots_per90 | 5.7 per 90 (300 min) | 3.09–6.18 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 4.12, Premier League 2023/24 (1 Nunez 4.75, 2 Haaland 4.27, 3 Muniz 4.12); band 0.75 V to 1.5 V |
| leader_npxg_per90 | 0.67 per 90 (270 min) | 0.61–1.22 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 0.81, Premier League 2023/24 (xG per 90 (penalties included, so npxG sits a little lower): 1 Haaland 1.04, 2 Isak 0.81, 3 Wilson 0.81); band 0.75 V to 1.5 V |
| leader_goals_per90 | 0.9 per 90 (300 min) | 0.61–1.64 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 0.82, Premier League 2023/24 (our arithmetic from StatMuse goals and minutes: Haaland 27 in 2,553 min (0.95), Isak 21 in 2,255 (0.84), Wilson 9 in 991 (0.82)); band 0.75 V to 2 V |
| leader_key_passes_per90 | 3.66 per 90 (270 min) | 2.27–4.54 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 3.03, Premier League 2023/24 (1 De Bruyne 3.54, 2 Robertson 3.19, 3 Bruno Fernandes 3.03); band 0.75 V to 1.5 V |
| leader_xa_per90 | 0.49 per 90 (247 min) | 0.26–0.51 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 0.34, Premier League 2023/24 (1 De Bruyne 0.53, 2 Olise 0.35, 3 Saka 0.34); band 0.75 V to 1.5 V |
| leader_shots_on_target_per90 | 2.4 per 90 (300 min) | 1.04–3.12 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 2.08, Premier League 2023/24 (the leader, not the third best (the rest of the ranking could not be read): Haaland 2.08 non-penalty and penalty shots on target per 90, 59 in all (StatMuse, Opta data, read 2026-10-24)); band 0.5 V to 1.5 V |
| leader_tackles_won_per90 | 4.93 per 90 (292 min) | 3.21–6.42 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 4.28, Premier League 2023/24 (tackles (Regista's tackle events are the tackles the league band counts): 1 Palhinha 5.14, 2 Joao Gomes 4.35, 3 Vinicius Souza 4.28); band 0.75 V to 1.5 V |
| leader_interceptions_per90 | 3.08 per 90 (292 min) | 1.48–2.96 | high, indicative (under 6 seasons) | the league's top qualified player against V = 1.97, Premier League 2023/24 (1 Antonee Robinson 2.23, 2 Lewis Cook 2.16, 3 Wan-Bissaka 1.97); band 0.75 V to 1.5 V |
| leader_crosses_per90 | 9.82 per 90 (247 min) | 7.33–14.67 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 9.78, Premier League 2023/24 (crosses attempted: 1 Doughty 10.46, 2 De Bruyne 10.02, 3 Robertson 9.78); band 0.75 V to 1.5 V |
| leader_progressive_carries_per90 | 11.87 per 90 (265 min) | 6.14–18.43 | in band, indicative (under 6 seasons) | the league's top qualified player against V = 12.29, Premier League 2023/24 (the leader, not the third best (per-90 ranks could not be read): Doku, 218 (FBref via Football365, 20 May 2024) in 1,596 min (StatMuse), our arithmetic. Doku is an outlier (the next of the season's top five carriers, Garnacho, made 6.2 per 90), so the lower bound is 0.5 V); band 0.5 V to 1.5 V |
| leader_npxg_gap | 1.04 ratio (1.04 min) | 1.0–1.75 | in band, indicative (under 6 seasons) | the leader's npxG per 90 over the second best's. Premier League 2023/24, the ranking LEADER_V cites: Haaland 1.04, Isak 0.81, a ratio of 1.28. The upper bound is ours: six clubs give a smaller pool, whose leader sits further clear by chance |
| leader_goals_gap | 1.35 ratio (1.35 min) | 1.0–2.0 | in band, indicative (under 6 seasons) | the leader's goals per 90 over the second best's. Premier League 2023/24, the ranking LEADER_V cites: Haaland 0.95, Isak 0.84, a ratio of 1.13. The upper bound is ours and wider than npxG's: goals are the noisiest count |
| top_npxg_share | 0.43 share | 0.2–0.4 | high, indicative (under 6 seasons) | the largest share of a club's non-penalty xG taken by one player. Premier League 2023/24 (StatMuse, Opta data, read 2026-10-24; xG with penalties): Haaland 29.37 of Man City's 82.63 (35.5%), Isak 20.29 of Newcastle's 78.14 (26.0%), Watkins 16.92 of Aston Villa's 65.66 (25.8%). The margins are ours |
| top_shooter_share | 0.294 share | 0.12–0.35 | in band, indicative (under 6 seasons) | the largest share of a club's non-penalty shots taken by one player. Premier League 2023/24: Liverpool took 790 shots, their top shooters Salah 114 (14%) and Nunez 108 (14%) (StatMuse). The upper bound, for a team built around one striker, is ours |

**12 of 14 in band (indicative (under 6 seasons)).**

Shape checks (no numeric band): aerial_duels_won_per90_by_role={'AM': 0.17, 'CB': 2.87, 'CM': 0.15, 'DM': 0.57, 'FB': 1.65, 'ST': 1.76, 'W': 0.43}, cb_aerial_won_rank=1, aerial_duels_per90_by_role={'AM': 0.8, 'CB': 3.68, 'CM': 0.57, 'DM': 0.82, 'FB': 2.3, 'ST': 5.44, 'W': 3.03}, cb_aerial_rank=2, field_tilt_team_range=36.9-59.7, cross_start_m_by_role={'AM': 31.0, 'CB': 33.5, 'CM': 19.8, 'DM': 32.1, 'FB': 35.2, 'ST': 24.3, 'W': 30.7}, crosses_received_by_role={'AM': 0.041, 'CB': 0.014, 'CM': 0.014, 'ST': 0.671, 'W': 0.26}

### Role shapes (league mode)

Which roles make the numbers: per-90 means of qualified players by kit role, each check an order between roles. The Premier League figures are examples of each role, not role means (each check names its source; mostly StatMuse, Opta data, 2023/24). Verdicts over 6 or more pooled seasons; on fewer marked 'indicative (under 6 seasons)'.

| Check | Order | Verdict | Premier League |
|---|---|---|---|
| passes_cb_dm_over_st | centre-backs and holding midfielders each attempt more passes per 90 than strikers | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24), completed passes per 90: Rodri (DM) 103.48, van Dijk (CB) 74.73, against Watkins (ST) 12.87 and Haaland (ST) 10.47 |
| touches_cb_dm_over_st | centre-backs and holding midfielders each touch the ball more per 90 than strikers | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24), touches per 90: Rodri 126.54, van Dijk 92.38, against Watkins 29.95 and Haaland 24.64 |
| touches_fb_over_w | full-backs touch the ball more per 90 than wingers | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24, read 2026-10-24), touches per 90: Trippier (FB) 98.61 and Robertson (FB) 92.60, against Saka (W) 65.55; the season's ten most touches include a full-back (Porro, 2,786) and no winger (FBref via Football365, 20 May 2024) |
| fb_crosses_third_of_w | full-backs cross at least a third as often as wingers, and their open-play crosses start (median) within 40 m of the opponent's goal line | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24), crosses per 90: Trippier (FB) 8.61 against Saka (W) 5.58; two of the top three crossers LEADER_V cites, Doughty and Robertson, play at full-back or wing-back. The start-position condition is ours: a cross is a ball from a wide area into the centre (Opta), not a long ball from his own half |
| prog_passes_cb_fb_over_st | centre-backs and full-backs each make more progressive passes per 90 than strikers | holds, indicative (under 6 seasons) | two centre-backs, van Dijk (457) and van Hecke (449), made the most Premier League progressive passes from the start of 2024/25 to October 2025 (Brighton & Hove Albion, 'Albion Analytics', 24 Oct 2025; provider not named); the 2023/24 top ten includes a full-back (Zinchenko, 229) and no striker (FBref via Football365, 20 May 2024) |
| cb_long_passes_floor | centre-backs attempt at least 2.5 long passes per 90, and more than strikers | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24, read 2026-10-24), long ball passes per 90: van Dijk (CB) 7.20, Saliba (CB) 3.42, against Haaland (ST) 0.18. Opta's long ball and the terminal's long pass (over 30 yards) are not the same cut; the floor is ours, below Saliba's |
| st_tackles_below_fb_cb_dm | strikers win fewer tackles per 90 than full-backs, centre-backs and holding midfielders | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24), tackles per 90: Haaland 0.21 and Watkins 0.34, against van Dijk (CB) 1.10, Antonee Robinson (FB) 2.56, and the holding midfielders who lead LEADER_V's tackles (Palhinha 5.14) |
| fouls_won_w_st_over_cb | wingers and strikers are each fouled more per 90 than centre-backs | holds, indicative (under 6 seasons) | StatMuse (Opta data, 2023/24), fouls drawn per 90: Saka (W) 2.13, Watkins 1.15 and Haaland 1.06 (ST), against van Dijk (CB) 0.37 |

| Per 90 | CB | FB | DM | CM | AM | W | ST |
|---|---|---|---|---|---|---|---|
| passes | 45.69 | 46.36 | 54.34 | 46.33 | 48.2 | 34.48 | 32.16 |
| touches | 54.35 | 54.76 | 66.02 | 59.04 | 60.49 | 48.39 | 47.29 |
| passes_received | 39.18 | 37.05 | 43.3 | 39.57 | 43.77 | 25.04 | 28.21 |
| crosses | 0.03 | 3.08 | 0.15 | 0.37 | 0.35 | 8.06 | 0.26 |
| tackles_won | 1.94 | 1.67 | 3.53 | 3.47 | 2.1 | 0.89 | 0.98 |
| fouls | 0.52 | 1.1 | 0.93 | 1.3 | 1.96 | 0.78 | 1.13 |
| fouls_won | 0.63 | 0.52 | 1.25 | 1.15 | 1.07 | 1.51 | 1.29 |
| progressive_passes | 2.0 | 3.88 | 2.42 | 3.18 | 4.12 | 2.56 | 1.29 |
| progressive_carries | 0.09 | 1.35 | 0.67 | 0.93 | 3.12 | 5.74 | 2.05 |
| long_passes | 4.21 | 6.89 | 2.47 | 2.98 | 2.95 | 11.11 | 2.86 |

## 2. The realistic profile (no player ratings)

Generator profile: **realistic**. The realistic profile is tuned to sit inside the bands over a full match. 

Simulated minutes: 240.54

Norms: Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth.

| Metric | Value | Band | Verdict | Note |
|---|---|---|---|---|
| passes_per90 | 1005.0 passes | 800.0–1100.0 | in band | attempted passes and crosses, both teams |
| pass_completion | 0.790 ratio | 0.78–0.87 | in band | completed / attempted |
| shots_per90 | 27.7 shots | 20.0–32.0 | in band | both teams |
| goals_per90 | 2.99 goals | 2.2–3.6 | in band | both teams |
| xg_per_shot | 0.117 xG | 0.08–0.13 | in band | mean expected goals per shot |
| tackles_per90 | 32.9 tackles | 28.0–45.0 | in band | both teams |
| interceptions_per90 | 26.2 interceptions | 14.0–30.0 | in band | both teams |
| take_ons_per90 | 47.1 take-ons | 28.0–50.0 | in band | attempted dribbles past a defender |
| nutmegs_per90 | 1.87 nutmegs | 0.5–3.0 | in band | rarely reported; broadcast estimate |
| fouls_per90 | 24.7 fouls | 18.0–28.0 | in band | both teams |
| corners_per90 | 10.9 corners | 8.0–13.0 | in band | both teams |
| throw_ins_per90 | 52.4 throw-ins | 35.0–55.0 | in band | both teams |
| possession_mean_s | 2.57 seconds | 1.5–4.5 | in band | mean time one player holds the ball |

**13 of 13 metrics in band.**

Diagnostics (no band): replays_per_goal=7.5, minutes=240.54, possession_changes_per90=268.6, carries_per90=478.5, pressures_per90=198.7
