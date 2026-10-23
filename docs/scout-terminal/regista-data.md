# What Regista's own data can compute: an audit

Audited 2026-10-23 on `main` (9b00972), read-only. Sources: `data/synthetic/README.md`, `src/regista/schemas/regista-events.schema.json`,
`src/regista/synth/generator.py`, `src/regista/synth/report.py`, `src/regista/season/{league,build,profiles,scout}.py`,
`src/regista/vision/{events,possession,identity,package,pitch}.py`, `docs/vision.md`, the committed samples `syn_0294` (demo
profile) and `vis_0201` (vision output), and all 30 Regista League fixtures regenerated in memory (nothing written, no Azure).

**How to read the verdicts.** COMPUTABLE NOW: the metric is a count, filter or ratio over fields that are already emitted
(no geometry, no chaining); "built" means `profiles.py` already computes it. DERIVABLE: the data supports it, but it needs new
code (attacking-direction geometry, linking records into sequences, a fitted model, or tracks). NEEDS GENERATOR CHANGE: the
field is not emitted, or is emitted in a way that carries no information. NOT POSSIBLE: cannot be done even with changes.

---

## 0. The finding that matters most

**Players have no ability.** The generator has no per-player attributes (no skill, pace, finishing, passing, height, foot). Every
probability depends only on geometry: pass success on distance, pressure and forwardness; shot outcome on distance; take-on
outcome is a coin flip (`rng.random() < 0.5`). A player's numbers come from **his formation slot** (kit number in the fixed
4-3-3) **plus luck**.

Measured over the 30 league fixtures: split-half correlation of per-player counts (rounds 1-5 vs 6-10).

| Count | r, all starters | r, within the same kit slot |
|---|---|---|
| passes | 0.95 | -0.08 |
| shots | 0.74 | -0.08 |
| take-ons | 0.47 | -0.11 |
| tackles | 0.79 | 0.16 |
| interceptions | 0.68 | 0.00 |
| recoveries | 0.80 | 0.01 |
| pressures | 0.97 | 0.29 |
| carries | 0.88 | 0.06 |
| crosses | 0.92 | -0.05 |

Across slots, stats look stable because a 9 shoots more than a 4. Within a slot (the comparison a scout actually makes: this
left winger against that one) the signal is essentially zero. Any ranking, percentile, "form" or "consistency" between two
players in the same role is noise. This is fixable only in the generator (section 5, last rows).

Other cross-cutting facts:

- **League size:** 6 clubs x 18, 30 fixtures, **30-minute matches** (15-minute halves, `MATCH_MINUTES = 15.0`;
  CLAUDE.md §2.5 says "8 minutes", which is stale). 902 simulated minutes in total; each starter has about 301 minutes
  (3.3 full matches). Per-90 rates are extrapolated from small samples.
- **Every starter plays every minute of every match; the 7 bench players per club never play** (no substitution events,
  no injuries, no red cards). Minutes and availability are constant.
- **Season totals (all 30 fixtures):** 9,919 passes, 440 crosses, 4,821 carries, 30,751 touches, 228 shots (xG 32.4,
  44 goals), 463 take-ons, 17 nutmegs, 29 skill moves, 343 tackles, 239 interceptions, 1,764 recoveries, 373 clearances,
  48 blocks, 2,017 pressures, 269 fouls, 44 yellow cards, 72 saves, 79 corners, 459 throw-ins, 23 goal kicks.

---

## 1. Event types and fields

Envelope on every record: `type`, `id`, `match_id`, `schema_version` (0.1.1), `source` (`synthetic` / `vision` / `human` /
`derived`), `confidence` (jittered 0.82-0.99 on synthetic data; it means nothing there).

**Fields on every generator `event`:** `t` (video seconds), `clock` {period, minute, second}, `event_type`, `player_id`,
`team_id`, `related_player_id`, `possession_id` (null on events emitted between possessions: tackle, interception, recovery,
clearance, save, goal, assist), `segment_id` (camera segment), `pitch` {x 0-105, y 0-68, absolute frame}, `outcome`
(success/fail/neutral), `under_pressure`. Optional: `pitch_end`, `t_end` (carries only), `body_part`, `qualifiers`, `metrics`.
Attacking direction per period is in `match.periods[].left_to_right_team_id`; consumers flip.

`clock.minute` in the second half is 45 + elapsed, so a 15-minute half reads 45'-60'. Minute-of-match splits (for example
"after 75'") need rescaling.

### 1.1 Emitted by the generator (28 of the schema's 36 types)

Examples are real, from fixture `rl_r01_ash_fai` (envelope trimmed).

| Type | What it carries | Example |
|---|---|---|
| `pass` | recipient (`related_player_id`), start/end, `body_part` (75% right foot, 25% left, random for everyone), outcome, under_pressure; qualifiers `forward` (>10 m toward goal), `long` (>30 m), `key_pass`, `assist`, `through_ball` (coded, **never fires**: 0 of 9,919); metrics `pass_distance_m`, `pass_difficulty` (0-1, a formula of distance, pressure, forwardness), `ball_speed_kmh` | `pass t_home_09→t_home_11 (70.22,44.64)→(76.54,53.21) right_foot success {pass_distance_m:10.6, pass_difficulty:0.142, ball_speed_kmh:39.3}` |
| `pass` (failed) | end = near the opponent who won it | `pass t_home_07 (104.0,19.51)→(64.8,12.09) fail [long] {57.1 m, difficulty 0.762}` |
| `cross` | as pass; 70% of wide final-third balls, chosen at random | `cross t_home_11→t_home_10 (85.91,56.57)→(75.46,48.44) right_foot success {13.2 m}` |
| `carry` | start/end, `t_end`, metrics `carry_distance_m`, `sprint_speed_kmh` (= distance / hold time, i.e. carry speed 3-7 m/s); qualifier `dribble` when under pressure | `carry t_home_09 t 0.0-2.86 (52.5,34.0)→(70.22,44.64) {carry_distance_m:20.7, sprint_speed_kmh:26.0}` |
| `touch` | one per ~0.8 s of possession; **all touches of a possession share its start location**; qualifiers `first_touch`, `out_of_play` (with `pitch_end`, outcome fail) | `touch t_home_09 (52.5,34.0) [first_touch]` |
| `take_on` | defender in `related_player_id`; success/fail; always under_pressure; qualifier `nutmeg` | `take_on t_home_06 vs t_away_06 (64.08,32.13) success` |
| `nutmeg` | separate record beside a successful take-on | `nutmeg t_home_11 vs t_away_11 (59.71,61.94) [nutmeg]` |
| `skill_move` | beside a successful take-on; qualifier `stepover`/`elastico`/`drag_back`/`roulette`/`body_feint` | `skill_move t_away_04 vs t_home_09 (63.31,34.34) [stepover]` |
| `shot` | start, `pitch_end` on the goal line (y only, no height), `body_part` (`head` after a cross, 60%), under_pressure; qualifier `goal`/`saved`/`blocked`/`off_target` (+`header`); metrics `xg`, `shot_distance_m`, `shot_speed_kmh` | `shot t_away_07 (18.36,25.47)→(0.0,33.79) right_foot [saved] {xg:0.097, 20.2 m, 95.9 km/h}` |
| `goal` | scorer, assister in `related_player_id`, xg, distance | `goal t_home_11 (assist t_home_09) (91.08,46.6)→(105.0,32.81) {xg:0.198}` |
| `assist` | passer, scorer in `related_player_id` (last completed team pass within 8 s) | `assist t_home_09 → t_home_11 (90.8,34.23)` |
| `save` | keeper, shooter in `related_player_id` | `save t_home_01 vs t_away_07 (4.65,34.01)` |
| `block` | outfielder nearest the shooter (shot blocks only) | `block <defender> vs <shooter>` |
| `tackle` | winner, loser in `related_player_id`; **always success** (failed tackles are never emitted) | `tackle t_away_06 vs t_home_11 (76.4,37.75) success` |
| `interception` | after a failed pass; **randomly chosen vs `recovery`** with identical movement | `interception t_home_10 from t_away_06 (43.64,47.91)` |
| `recovery` | loose ball after a failed pass, clearance or block | `recovery t_away_08 (64.8,12.09)` |
| `clearance` | only after a failed pass (realistic profile); ball sent 25-40 m | `clearance t_home_06 (27.74,36.43)` |
| `pressure` | nearest opponent within 3.5 m at the **start** of a possession; at most one per possession | `pressure t_away_08 on t_home_07 (71.37,19.13)` |
| `foul` / `foul_won` | pair, each pointing at the other | `foul t_away_08 on t_home_07 (75.01,18.52)` |
| `card_yellow` | 15% of fouls | `card_yellow t_away_06 (66.8,33.93)` |
| `free_kick`, `corner`, `throw_in`, `goal_kick`, `kick_off` | taker and spot; no `pitch_end`, no delivery type (the taker then plays an ordinary possession) | `corner t_away_07 (0.3,0.3)` |
| `possession_change` | new team's player, previous holder in `related_player_id` | `possession_change t_away_08 from t_home_07` |
| `period_start`, `period_end` | match structure | `period_end t 901.77` |

### 1.2 In the schema but never emitted

`dribble` (exists only as a carry qualifier), `header` (only as a shot qualifier), `offside`, `card_red`, `substitution`,
`penalty`, `injury_stoppage`, `var_review`.

### 1.3 The other record types

| Record | Fields | Example |
|---|---|---|
| `match` | teams (`team_id`, name, short name, kit colours, `club_id`), roster (`player_id`, name, `kit_number`, `position` GK/DF/MF/FW, `starter`, `global_player_id`), video, `periods` (video t, attacking direction), `score`, competition, season, date, venue, generator seed | `{"player_id":"t_home_01","name":"Hugo Fontaine","kit_number":1,"position":"GK","starter":true,"global_player_id":"pl_ash_01"}` |
| `possession` | `t`/`t_end`, player, team, `gained_by` (pass_received, loose_ball, set_piece, tackle, kickoff, interception, goalkeeper_claim, rebound), `lost_by` (pass, foul, out_of_play, shot, dispossessed, tackled, period_end), `touches`, `pitch`/`pitch_end`, `under_pressure` | `po t_home_07 23.22-25.93 pass_received→foul touches 3 (72.41,19.53)→(84.38,15.69) under_pressure` |
| `camera_segment` | kind (main/replay/highlight/closeup/crowd/graphic), playback speed, `replay_of`, `replays_window`, angle | `replay 30.43-38.43 x0.5 of ev_000033 behind_goal` |
| `appearance` | player visible in a segment, `on_ball`, `prominence` | `ap t_home_08 0.1-27.43 on_ball false prominence 0.009` |
| `annotation` | human verdicts (placeholders on synthetic data, `simulates: human`) | |

A league fixture has about 377 possessions (in `rl_r01_ash_fai`, 273 of 377 were gained by a received pass).

---

## 2. Tracking

- **Where:** `tracks.jsonl`, written only when something needs positions (`ensure_tracks`; about 17 MB per 30-minute match).
  Profiles never read it.
- **Frequency:** 1 Hz (`TRACK_HZ = 1.0` for the league and the committed sample). Sample times are irregular (1.00-1.03 s apart;
  longer gaps across cutaways, up to 7 s).
- **Fields:** `t`, `frame`, `segment_id`, `object` (player/ball), `track_id`, `player_id`, `team_id`, `pitch` {x, y},
  `bbox`, `identity` {confidence, evidence}; the ball also has `speed_kmh` (the speed the simulator assigned to the current
  action). No ball height; no player speed field; no referee.
- **Coverage:** only players inside the main camera's window are written (median 20 of 22 per sample, minimum 12). Measured
  per player over a match: outfielders observed for 76-93% of the time, goalkeepers 23-31%. In replays and closeups the
  recorded positions are where the players stand during the dead ball, **not** the replayed moment.
- **Movement model:** players steer toward a target (formation anchor shifted by possession and pulled toward the ball) at
  **a hard cap of 7 m/s (25.2 km/h) for everyone**, plus 5 cm Gaussian jitter per 0.1 s step. The ball carrier is pinned to
  the ball. Set-piece takers are teleported to the spot.
- **Speeds and distances, measured from consecutive samples (main camera, gaps <= 1.2 s):** p50 7.4 km/h, p95 25.2, p99 26.0
  (the cap plus jitter), max 154 km/h (teleports, must be filtered). Distance extrapolated to 90 minutes: 13.8-15.2 km for
  outfielders, about 3-3.6 km for keepers. Premier League outfielders run roughly 10-12 km, so the steering model over-runs.
- **Verdict:** average positions and positional heat maps are derivable and fair. Distance covered is derivable but not
  credible. Sprints, high-speed running and top speed carry no information: every player has the same ceiling, and 1 Hz
  is too coarse for accelerations (sprint detection normally uses 10-25 Hz).

---

## 3. Player attributes and context

| Available | Not available |
|---|---|
| name, global id (`pl_ash_09`), club (id, name, short name, kit colours, ground), kit number, position (GK/DF/MF/FW), starter flag | age / date of birth, height, weight, preferred foot, nationality, contract, market value, any ability rating |

- **Detailed role is implicit:** the formation is a fixed 4-3-3 and the kit number fixes the slot (1 GK; 2/3 full-backs;
  4/5 centre-backs; 6 holding mid; 8 central mid; 10 attacking mid; 7/11 wingers; 9 striker). Squads are the same in every match.
- **Match context present:** home/away (header; profiles store a `home` flag per match), date, round, venue, final score,
  periods and attacking directions, clock on every event, possession chains, camera context.
- **Derivable context:** score state at any moment (running sum of `goal` events by `t`), possession share, opponent strength
  (league table).
- **Absent context:** substitutions, lineups that change, weather, referee, competition stage beyond the round number.

---

## 4. What `profiles.py` computes today

Built from the league's event streams (plus confirmed claims and Player-view uploads), keyed on global id. Every starter
in a fixture is credited with the whole match.

- **Appearances, minutes** (minutes = sum of period lengths in video time).
- **22 counts with per-90 rates** (`STATS`), each a filter on one event:
  touches, passes, passes completed, forward passes (qualifier `forward`), key passes (qualifier `key_pass` on pass or cross),
  assists, crosses, crosses completed, carries, take-ons, take-ons won, nutmegs, shots, shots on target (qualifier `goal` or
  `saved`), goals, tackles won, interceptions, recoveries, clearances, pressures, saves, fouls won.
- **3 ratios:** pass accuracy (passes only, crosses excluded), take-on success, shot accuracy.
- **Percentiles** of every per-90 rate among players of the same position (GK/DF/MF/FW) with at least 40% of the most minutes
  (in practice: all 66 starters, since all have equal minutes).
- **Touch map:** a 12 x 8 grid of event locations (touch, pass, cross, carry, take-on, shot, tackle, interception, recovery,
  clearance), flipped so the team attacks left to right.
- **Evidence:** for each stat, up to 60 contributing events with the clip each sits in. **Moments:** the 40 best labelled
  clips by watchability.
- **Match list** per player (match, round, date, opponent, home flag, score, source league/claim/upload). No per-match stats.
- `scout.py` adds rankings within position, search/compare, and minimum-count thresholds for ratios; `summaries.py` turns them
  into sentences. Neither adds new football metrics.

**Not used anywhere in the season code:** xG (on every shot), pass distance, carry distance, `under_pressure`, body part,
pass end locations, skill moves, fouls committed, cards, blocks, set pieces, possessions.

**A mislabelled stat:** `key_passes` counts the generator's `key_pass` qualifier, which is added only when the shot that
follows is a goal or is saved. Blocked and off-target shots get no key pass, so the stat is really "passes leading to a shot
on target" (110 tagged in the season for 228 shots).

---

## 5. Candidate metrics

Counts are for the synthetic (generator) path. The vision path is in section 6.

| Metric | Verdict | How, or what is missing |
|---|---|---|
| **Shooting** | | |
| Shots, shots on target, goals, shot accuracy | COMPUTABLE NOW | built |
| xG per shot, total xG | COMPUTABLE NOW | `metrics.xg` on every shot and goal. Distance only: `1.1·e^(-0.12·d)` clamped 0.02-0.85; no angle, no header or pressure term. The goal is drawn with exactly that probability, so in this world xG is the true scoring chance |
| npxG | COMPUTABLE NOW | equals xG: penalties never happen |
| xG per shot (player) | COMPUTABLE NOW | mean `metrics.xg` |
| Goals minus xG (finishing) | COMPUTABLE NOW | pure noise by construction (no finishing skill) |
| Shot locations, shot maps | COMPUTABLE NOW | `pitch`, `pitch_end` (y on the goal line), body part, `header`, under_pressure, outcome |
| Big chances | DERIVABLE | threshold on xG (for example >= 0.3); the Opta definition is subjective |
| Shot placement / PSxG | NEEDS GENERATOR CHANGE | no shot height; on-target end y is uniform within ±3.2 m and save vs goal is drawn independently of placement, so placement carries no information. Add a goal-mouth (y, z) target and a keeper model whose save chance depends on it |
| Penalties, direct free-kick shots | NEEDS GENERATOR CHANGE | never simulated |
| **Chance creation** | | |
| Assists | COMPUTABLE NOW | built |
| Key passes (true definition) | DERIVABLE | today's stat undercounts (section 4). Link each shot to its possession (`possession_id`), whose `gained_by: pass_received` points back to the completed pass with the shooter as `related_player_id` |
| xA | DERIVABLE | the xG of the shot each key pass led to (same chain) |
| Shot-creating / goal-creating actions | DERIVABLE | the two offensive actions (pass, take-on, foul won, shot, carry) before each shot within the team's sequence; all exist with times |
| Through balls | NEEDS GENERATOR CHANGE | the `through_ball` qualifier is coded but its condition never holds (0 of 9,919 passes). A line-breaking proxy from tracks is possible when tracks are built |
| Crosses, cross completion | COMPUTABLE NOW | built; note 30% of wide final-third balls are called passes at random |
| Switches of play | DERIVABLE | `abs(pitch_end.y - pitch.y) >= 36 m`; rare by design (25 of 10,359 passes), because pass targets cluster around 16 m |
| Progressive passes, progressive passing distance | DERIVABLE | flip by `left_to_right_team_id`, then the FBref rule on start/end x (at least 10 m closer to goal, or into the box) |
| Passes into the final third, into the box | DERIVABLE | end location in the attacking frame |
| Pass completion by length | COMPUTABLE NOW | `metrics.pass_distance_m` (and qualifier `long` > 30 m) |
| Pass completion by zone | DERIVABLE | start location in the attacking frame |
| Passes under pressure | COMPUTABLE NOW | `under_pressure` on pass/cross (opponent within 3.5 m at the start of the possession) |
| Expected pass completion, completion above expected | DERIVABLE | the success formula is reproducible from distance, pressure and forward distance; completion above expected is zero-mean noise (no passing skill) |
| Long passes, forward passes | COMPUTABLE NOW | qualifiers `long`, `forward` (forward passes built) |
| Pass networks | DERIVABLE | completed passes: `player_id` → `related_player_id`; node positions from pass origins or tracks |
| **Carrying and dribbling** | | |
| Carries, carry distance | COMPUTABLE NOW | carries built; `metrics.carry_distance_m` on each, not aggregated yet |
| Progressive carries, progressive carry distance | DERIVABLE | carry start/end in the attacking frame |
| Carries into the final third, into the box | DERIVABLE | same |
| Take-ons attempted, won, success % | COMPUTABLE NOW | built; outcome is a coin flip for everyone |
| Nutmegs | COMPUTABLE NOW | built |
| Skill moves (with type) | COMPUTABLE NOW | `skill_move` + qualifier; not in profiles |
| Times dribbled past (defender) | DERIVABLE | successful `take_on` where the player is `related_player_id` |
| Touches | COMPUTABLE NOW | built (one per 0.8 s held, so it mirrors time on the ball) |
| Touches in the box, by third | DERIVABLE | touch location in the attacking frame; all touches of a possession share its start point |
| Ball losses (dispossessed, miscontrols, failed passes) | DERIVABLE | possession `lost_by` (dispossessed, tackled, out_of_play) plus failed passes |
| **Defending** | | |
| Tackles | COMPUTABLE NOW | built; only won tackles exist |
| Tackle success % (challenges won vs lost) | DERIVABLE | tackles won / (tackles + times dribbled past) |
| Interceptions | COMPUTABLE NOW | built; interception vs recovery is chosen at random with identical play, so the split is noise |
| Recoveries | COMPUTABLE NOW | built |
| Pressures | COMPUTABLE NOW | built; at most one per possession, so 2,017 in 902 min for both teams (about 100 per team per 90), well below what event providers that log pressures record |
| Pressure regains (ball won within 5 s) | DERIVABLE | pressure → change of possession to the presser's team within 5 s |
| Clearances | COMPUTABLE NOW | built; only after failed passes |
| Blocks | COMPUTABLE NOW | shot blocks only (no pass blocks) |
| Defensive actions by zone (tackles, interceptions, recoveries, pressures, clearances, blocks) | DERIVABLE | every one has `pitch`; flip to the defending frame |
| Ground duels won/lost | DERIVABLE | take-ons (both sides) plus tackles |
| Aerial duels | NEEDS GENERATOR CHANGE | the simulation is 2D: no ball height, no aerial contests; headers exist only on 16 shots |
| Fouls committed, fouls won, yellow cards | COMPUTABLE NOW | fouls won built; fouls committed and cards not in profiles |
| Red cards, offsides | NEEDS GENERATOR CHANGE | never emitted |
| Errors leading to a shot | DERIVABLE | failed pass / dispossession → opponent shot within N seconds |
| **Team and match** | | |
| Possession % | DERIVABLE | sum of possession durations per team (or pass share) |
| Field tilt | DERIVABLE | share of final-third passes |
| PPDA | DERIVABLE | opponent passes in their own 60% / tackles + interceptions + fouls in that zone |
| Score state, game-state splits | DERIVABLE | running score from `goal` events by `t` |
| Home/away splits | COMPUTABLE NOW | header and the per-match `home` flag |
| Sequences (passes per sequence, directness, build-up speed) | DERIVABLE | possession chains by team with times and locations |
| **Set pieces** | | |
| Corners, free kicks, throw-ins, goal kicks (counts) | COMPUTABLE NOW | events with taker and spot |
| Shots and xG from set pieces | DERIVABLE | follow the possession that starts with `gained_by: set_piece` |
| Set-piece delivery (inswing, near post, delivery quality) | NEEDS GENERATOR CHANGE | a set piece has no `pitch_end`; the taker then plays an ordinary possession |
| **Possession value** | | |
| xT | DERIVABLE | fit a 12 x 8 move/shoot model on the season's passes and carries (start/end, success) and shots; it will mostly learn the generator's own distance rules back |
| VAEP / action-value models | DERIVABLE | all action fields exist; same circularity |
| EPV, pitch control, off-ball runs, space creation | NEEDS GENERATOR CHANGE | need all 22 players and the ball with velocities at 10+ Hz; tracks are 1 Hz and in-frame only |
| **Tracking** | | |
| Average positions | DERIVABLE | tracks (1 Hz, main camera) or event locations |
| Heat maps (event-based) | COMPUTABLE NOW | built (12 x 8 touch map) |
| Heat maps (positional, from tracks) | DERIVABLE | tracks; keepers are seen 23-31% of the time |
| Distance covered | DERIVABLE | sum of track steps, teleports filtered; values (13.8-15.2 km per 90) are not credible |
| Sprints, top speed, high-speed running | NEEDS GENERATOR CHANGE | every player is capped at 25.2 km/h; needs per-player top speed and acceleration, and 10+ Hz tracks |
| **Goalkeeping** | | |
| Saves | COMPUTABLE NOW | built |
| Save %, shots on target faced, goals conceded, clean sheets | DERIVABLE | opponent shots `saved`/`goal` while the keeper is on (keepers always play the full match) |
| PSxG, PSxG minus goals allowed | NEEDS GENERATOR CHANGE | see shot placement above |
| Cross claims, punches, sweeper actions | NEEDS GENERATOR CHANGE | `goalkeeper_claim` happens only after a save |
| Distribution (pass length, completion, goal kicks) | COMPUTABLE NOW | the keeper's passes carry distance and outcome; `goal_kick` events |
| **Player and season** | | |
| Detailed role (full-back, winger, holding mid) | DERIVABLE | kit number → 4-3-3 slot (fixed) |
| Minutes, appearances | COMPUTABLE NOW | built, but constant: every starter about 301 min, bench 0 |
| Availability (injuries, rotation, suspensions, subs) | NEEDS GENERATOR CHANGE | no substitutions, injuries or red cards |
| Age, age curves | NEEDS GENERATOR CHANGE | no date of birth; one season; no ability to evolve with age |
| Height, preferred foot, nationality | NEEDS GENERATOR CHANGE | not in the league file; body part is random 75/25 for everyone |
| Form over time (match by match) | DERIVABLE | aggregate per match (profiles keep the match list but not per-match stats; evidence is capped at 60 per stat). Shows noise only until players have ability |
| Consistency (variance across matches) | DERIVABLE | same; noise only |
| Percentiles within position | COMPUTABLE NOW | built |
| Real differences between players in the same role | NEEDS GENERATOR CHANGE | section 0. Add per-player ratings in `league.json` (passing, finishing, dribbling, defending, pace, aerial, foot, height, age) and feed them into each probability |

**Counts (synthetic path, 79 rows):** COMPUTABLE NOW 30, DERIVABLE 35, NEEDS GENERATOR CHANGE 14, NOT POSSIBLE 0.
Of the 30 computable now, 18 rows are already covered (fully or partly) by `profiles.py`. The other 12 are fields nobody
aggregates yet: xG, npxG, xG per shot, goals minus xG, shot maps, pass completion by length, passes under pressure, skill
moves, blocks, home/away splits, set-piece counts, keeper distribution. Nothing is NOT POSSIBLE on the synthetic path: every
gap can be closed in the generator, though a metric the generator is told to produce (an age curve, say) only shows back
what was programmed into it.

---

## 6. The vision path (real footage) is a subset

Everything above is the generator's output. When a match comes from video (`source: vision`; Player-view uploads, `vis_0201`),
the stream is much thinner. And it has only ever been measured on Regista's rendered footage (flat discs, one camera family),
never on real broadcast video: the person detector, real homography and ball detector for real footage are not built
(`docs/vision.md`, last section).

| | Generator | Vision |
|---|---|---|
| Event types | 28 | 10: `pass`, `cross`, `shot`, `save`, `goal`, `tackle`, `interception` (really "ball won": interceptions and recoveries together), `carry`, `take_on`, `nutmeg` |
| Missing types | | `touch`, `pressure`, `recovery`, `clearance`, `block`, `foul`/`foul_won`, cards, every set piece, `assist`, `skill_move`, `possession_change`, kick-offs and period markers |
| `clock` | yes | no (video time only) |
| `body_part` | yes | no |
| `under_pressure` | every event | only on take-ons/nutmegs; possessions carry it (opponent within range for most of the run) |
| Qualifiers | forward, long, key_pass, assist, dribble, first_touch, skill type, shot outcome, header | shot outcome (`goal`/`saved`/`off_target`/`unknown`, no `blocked`), `nutmeg` |
| Metrics | pass distance, difficulty, ball speed, shot distance, shot speed, xG, carry distance, carry speed | `pass_distance_m`, `shot_distance_m`, `carry_distance_m` only. No xG (derivable from shot distance with the same formula) |
| Failed passes | end location | no `pitch_end`; only those intercepted are found |
| Possessions | full `gained_by`/`lost_by` | mostly `pass_received`/`pass` or `unknown`; `touches` estimated from duration |
| Tracks | 1 Hz, in-frame players, ball with speed | identity frames at 5 fps, written at 2 Hz, packaged at 1 Hz; named and unnamed players (the package keeps named only), ball without speed |
| Score | true | goals the spotter found |

**Measured accuracy (spotter v4, fresh rendered matches, precision / recall):** pass 1.00 / 0.76, shot 0.80 / 0.80,
ball won 0.85 / 0.62, tackle 1.00 / 0.44, take-on 0.82 / 0.50, nutmeg 0.67 / 0.67 (4 of 6), carry 0.85 / 0.84, goal 1 of 1,
save 3 of 4. The possession agent finds about 72% of possession frames, which caps recall. Clearances are not spotted at all.

**So on the vision path:** shots, shot locations, shot distance (and an xG from it), passes and completion by length, crosses,
carries and progressive carries, take-ons, nutmegs, tackles, ball wins, saves, average positions and positional heat maps are
available, with recall well below 1. Not available: touches, pressures and anything under pressure, key passes, assists, xA,
SCA, fouls, cards, set pieces, recoveries vs interceptions, clearances, blocks, body part, minute of match, and every metric
already marked NEEDS GENERATOR CHANGE.

**A consequence for profiles today:** an upload or confirmed claim adds a full match of minutes to a league profile but no
touches, pressures, recoveries, key passes or assists (vision never emits them), and its "interceptions" include recoveries.
Mixing the two sources lowers some per-90 rates and raises interceptions. Profiles should either keep the two sources apart or
count each stat only over matches whose source can produce it.

---

## 7. The most important gaps, in order

1. **No player ability.** Within a role, every comparison is noise (section 0). Fix in the generator and `league.json`.
2. **Undercounted key passes** in `profiles.py`, and no xA / SCA, though the chains to derive them exist.
3. **xG is there but unused** by profiles; it is distance-only, and there is no PSxG, no penalties and no shot height.
4. **Everyone plays every minute**: no substitutions, injuries or rotation, so minutes and availability say nothing.
5. **No age, height or foot**, so no age curves or physical filters.
6. **Tracking is 1 Hz, in-frame only, with one speed cap**: positions are fine; physical metrics are not.
7. **The 2D simulation** has no aerial game, no through balls in practice, almost no switches, and no set-piece deliveries.
8. **The vision path is a 10-type subset**, measured only on rendered footage, and it mixes unevenly with generator stats in profiles.
