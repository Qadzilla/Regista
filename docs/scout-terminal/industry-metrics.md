# Industry metrics catalogue: football scouting and analytics (as of October 2026)

This catalogue lists the player and team metrics used in professional scouting and analytics, grouped by category. It is
built from primary sources read on 2026-10-23 (list at the end). Each metric gets one line: name, precise definition,
raw data it needs, typical presentation, whether it is a standard or proprietary metric, and the source key.

**Status note on FBref.** On 20 January 2026 Stats Perform ended FBref's access to Opta feeds and FBref removed its
advanced data (xG, progressive actions, SCA, PSxG and so on) [FBREF-2026]. The FBref definitions below come from
FBref's own table tooltips and explainer pages as archived in 2024 and 2025 (Wayback Machine). They are still the most
widely quoted public definitions, but FBref no longer serves those numbers.

## Legend

**Raw data tiers** (column "Data"):

| Code | Meaning |
|---|---|
| **E** | Event data: event type, player, team, timestamp, start x-y, outcome |
| **E2** | E plus end x-y (passes, carries, crosses) |
| **Q** | E plus qualifiers: body part, pass height, set-piece type, under-pressure flag, cross or through-ball tags |
| **SEQ** | Possession or sequence segmentation (events grouped into team possessions, with start and end reasons) |
| **FF** | Freeze frame at the moment of a shot or event: x-y of every visible player (StatsBomb shot freeze frame, StatsBomb 360) |
| **T** | Tracking: x-y of all 22 players and the ball, typically 10-25 Hz from optical or broadcast tracking, or 10 Hz GPS |
| **M** | Needs a trained model (xG, xPass, possession value) on a large historical sample |
| **MIN** | Minutes played, plus team possession share where an adjustment applies |

**Status** (column "Std"):

| Code | Meaning |
|---|---|
| **Std** | Industry standard: every provider has it with essentially the same meaning (goals, tackles, aerials) |
| **Std\*** | Standard concept, but thresholds or rules differ by provider (progressive pass, PPDA, sprint). Always say whose definition you use |
| **Prop** | Proprietary model or definition owned by one provider (OBV, xGOT, PSV-99, IMPECT, Wyscout Index) |
| **Open** | Published open method anyone can rebuild (xT, VAEP, g+ framework, xGChain) |

Presentation shorthand: **/90** per 90 minutes; **%** success rate; **pct** percentile vs position peers; **map** pitch
plot (shot map, pass map, heat map); **radar** radar or pizza chart.

---

## 1. Shooting

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 1 | Goals | Goals scored (FBref "Gls"); own goals are credited to the defending player | E | total, /90 | Std | FB-ST, OPTA-DEF |
| 2 | Non-penalty goals (npG, G-PK) | Goals minus penalty goals | E, Q (pattern = penalty) | /90, pct | Std | FB-ST |
| 3 | Shots | Deliberate attempts to score with any legal body part; FBref totals exclude penalty kicks | E | /90, pct | Std | FB-ST, SB-SPEC |
| 4 | Shots on target (SoT) | Attempts on target: goals, saved shots, and shots blocked by a last-line defender; FBref excludes penalties | E | /90 | Std | OPTA-DEF, FB-ST |
| 5 | Shots on target % | SoT / shots; Opta's "shooting accuracy" excludes blocked attempts and own goals | E | % (FBref min .395 shots per squad game) | Std\* | FB-ST, OPTA-DEF |
| 6 | Goals per shot (conversion) | Goals / shots; Opta excludes blocked shots and own goals from the denominator | E | ratio | Std\* | FB-ST, OPTA-DEF |
| 7 | Goals per shot on target | Goals / SoT (FBref min .111 SoT per squad game to qualify as leader) | E | ratio | Std | FB-ST |
| 8 | Average shot distance | Mean distance in yards from goal of all shots, excluding penalties | E (shot x-y) | yards | Std | FB-ST |
| 9 | Expected goals (xG) | Probability a shot scores given its features (location, angle, assist type, body part, attack type, big chance; Opta also pressure, clear path, GK position) | E, Q, M (FF improves it) | sum, /90, shot map sized by xG | Std\* (model Prop) | FB-XG, OPTA-DEF, WY-xg |
| 10 | Non-penalty xG (npxG) | xG excluding penalties (penalty xG is fixed: 0.79 at FBref/Opta, 0.76 at Wyscout) | E, Q, M | /90, pct (FBref summary stat) | Std\* | FB-XG, WY-xg |
| 11 | npxG per shot | npxG / non-penalty shots: average chance quality | E, Q, M | ratio, pct | Std\* | FB-ST, SB-RAD |
| 12 | Goals minus xG (G-xG, npG-npxG) | Finishing over or under expectation; noisy, needs large samples | E, M | difference, scatter vs xG | Std\* | FB-ST |
| 13 | Possession-level xG | Team xG per possession = 1 - product of (1 - xG_i) for shots in the same possession, so rebounds do not double count | E, SEQ, M | team xG totals | Std\* (FBref method) | FB-XG |
| 14 | Big chances | A chance a player "should reasonably be expected to score" (one-on-one or very close range, clear path, low-moderate pressure); penalties always count | E (tagger judgement) | count, /90 | Prop (Opta) | OPTA-DEF, OA-DEF |
| 15 | Big chances missed | Big chance where the player fails to score or does not get a shot away (air shot, chose not to shoot) | E | count | Prop (Opta) | OPTA-DEF |
| 16 | xGOT / post-shot xG (shooter) | Probability an on-target shot scores given pre-shot xG plus where it crosses the goal mouth; off-target shots are 0 | E, Q (end x-y-z in goal), M | sum, xGOT - xG ("shooting goals added") | Prop (Opta xGOT, SB PSxG, Wyscout xG2) | OA-XGOT, SB-PSXG, WY-save |
| 17 | Shot pattern of play | Each shot assigned one of 7 Opta patterns: regular play, set piece, throw-in, direct free kick, corner, fast break, penalty | E, SEQ | split bars | Prop (Opta taxonomy) | OPTA-DEF |
| 18 | Shots by body part | Right foot, left foot, head, other ("foot" includes any part of the leg) | Q | split, headed goals /90 | Std | OPTA-DEF, WY-player_metrics |
| 19 | Free-kick shots | Attempts direct from a free kick | Q | count, xG | Std | FB-ST, OPTA-DEF |
| 20 | Penalties made / attempted | Penalty goals and attempts (shootouts excluded) | Q | count, % | Std | FB-ST |
| 21 | Hit woodwork | Shot hits the frame and does not go in as a direct consequence; counted once per attempt | E | count | Std | OPTA-DEF |
| 22 | Shot touch % | Shots as a share of a player's touches (striker radar) | E | % | Prop (StatsBomb radar) | SB-RAD |

## 2. Passing and chance creation

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 23 | Passes attempted / completed | All passes incl. crosses, corners, throw-ins, free kicks and goal kicks (FBref); Opta's "pass" excludes crosses, keeper throws and throw-ins | E | /90 | Std\* | FB-PA, OPTA-DEF |
| 24 | Pass completion % | Completed / attempted; a completed pass reaches a teammate without an opponent touch (Wyscout: next touch is a teammate's) | E | % (FBref min 30 min per squad game) | Std | FB-PA, OPTA-DEF, WY-long_pass |
| 25 | Short / medium / long passes | FBref: short 5-15 yd, medium 15-30 yd, long >30 yd; Wyscout: long = ground >45 m or high >25 m, short/medium = everything else (generally <40 m) | E2 | count, % each | Std\* | FB-PA, WY-long_pass, WY-short_medium_pass |
| 26 | Total passing distance | Yards travelled by completed passes in any direction | E2 | yards /90 | Std | FB-PA |
| 27 | Progressive passing distance | Yards completed passes travel toward the opponent goal; backward passes count 0 | E2 | yards /90 | Std | FB-PA |
| 28 | Progressive passes (FBref/Opta) | Completed pass that moves the ball toward the goal line at least 10 yd from its furthest point in the last six passes, or any completed pass into the penalty area; excludes passes from the defending 40% of the pitch | E2, SEQ | /90, pct (summary stat) | Std\* | FB-PA |
| 29 | Progressive pass (Wyscout) | Forward pass that gets at least 30 m closer to goal if start and end are in own half, 15 m if it crosses halves, 10 m if both in opponent half (measured to the next touch) | E2 | /90, accuracy % | Std\* | WY-progressive_pass |
| 30 | Progressive pass (Opta Analyst) | Completed pass in the attacking two-thirds that moves the ball at least 25% closer to goal | E2 | /90 | Std\* | OA-DEF |
| 31 | Ball progression (metres) | Sum of metres each successful forward pass brings the ball closer to goal (Wyscout) | E2 | metres /90 | Prop (Wyscout) | WY-ball_progression |
| 32 | Passes into final third | Completed passes that enter the third nearest the opponent goal, excluding set pieces (Wyscout counts attempts from outside the third, next touch inside) | E2 | /90, % | Std | FB-PA, WY-pass_to_final_third |
| 33 | Passes into penalty area | Completed passes into the 18-yard box, excluding set pieces (Wyscout includes crosses, excludes throw-ins and carries) | E2 | /90, % | Std | FB-PA, WY-pass_to_penalty_area |
| 34 | Crosses | Ball from a wide position aimed at a teammate in front of goal, with lateral movement into the centre (Wyscout: open play only, flanks are the outer 23 m of a 68 m width) | E2, Q | /90, accuracy % | Std\* | OPTA-DEF, WY-cross |
| 35 | Crosses into penalty area | Completed crosses into the 18-yard box, excluding set pieces | E2, Q | /90 | Std | FB-PA |
| 36 | Successful box cross % | Share of a player's completed passes into the box that are crosses (style marker) | E2, Q | % | Prop (StatsBomb radar) | SB-RAD |
| 37 | Deep completions | Non-cross pass targeted to the zone within 20 m of the opponent goal (Wyscout) | E2 | /90 | Prop (Wyscout name; StatsBomb uses a 20-yard variant) | WY-deep_competion |
| 38 | Deep completed crosses | Cross targeted to the zone within 20 m of the opponent goal | E2, Q | /90 | Prop (Wyscout) | WY-deep_completed_cross |
| 39 | Key passes | Final pass before a teammate's shot that does not score (Opta); FBref counts all passes leading to a shot; Wyscout reports and search include assists | E, SEQ | /90 | Std\* | OPTA-DEF, FB-PA, WY-key_pass |
| 40 | Shot assists | Last action before a teammate's shot, intended or not; each carries the xA of that shot (Wyscout) | E, SEQ | /90 | Std\* | WY-shot_assist |
| 41 | Assists | Final touch by a teammate before a goal; none for own goals, direct free kicks, direct corners, penalties (unless the penalty is passed) | E, SEQ | total, /90 | Std | OPTA-DEF |
| 42 | Second assist / third assist | Last action by the scoring team before the assist (and before the second assist), with no opponent control in between | E, SEQ | /90 | Std\* | OPTA-DEF, WY-pre_assist, WY-pre_pre_assist |
| 43 | Fantasy assist | Opta's broader assist incl. heavy deflections, rebounds from saves or woodwork, penalty or free kick won | E | count (fantasy games) | Prop (Opta) | OPTA-DEF |
| 44 | Chances created | Assists + key passes | E | /90 | Std | OPTA-DEF |
| 45 | Expected assists, xA (Opta) | Probability each completed pass becomes an assist, from pass type, end point, length, phase of play; credited whether or not a shot follows | E2, Q, M | /90, pct | Prop (Opta) | FB-PA, FB-XG, OPTA-DEF |
| 46 | xAG / xG assisted / xA (Wyscout) | xG of the shot that a pass assisted; only shot-ending passes earn it (FBref "xAG", StatsBomb "xG Assisted", Wyscout "xA") | E, SEQ, M | /90, pct (summary stat) | Std\* | FB-PA, SB-RAD, WY-xa |
| 47 | npxG + xAG | Expected goal contribution per 90 | E, M | /90, pct | Std\* | FB-SR |
| 48 | Assists minus xAG | Over or under-performance of teammates' finishing on a player's passes | E, M | difference | Std\* | FB-PA |
| 49 | Shot-creating actions (SCA) | The two offensive actions directly before a shot (live pass, dead-ball pass, take-on, shot, foul drawn, defensive action); the shooter can earn credit | E, SEQ | /90 by type, pct | Prop (FBref/Opta definition) | FB-GCA |
| 50 | Goal-creating actions (GCA) | Same as SCA but for the two actions before a goal | E, SEQ | /90 by type | Prop (FBref/Opta) | FB-GCA |
| 51 | Through balls | Completed passes sent between the last defenders into open space (Opta: "splitting the defence") | E2, Q | /90 | Std | FB-PT, OPTA-DEF, WY-through_pass |
| 52 | Smart passes | Creative, penetrative pass trying to break the opponent's defensive lines (tagger judgement) | E, Q | /90, accuracy % | Prop (Wyscout) | WY-smart_pass |
| 53 | Switches | Passes that travel more than 40 yards of the pitch's width | E2 | /90 | Std\* | FB-PT, SB-SPEC |
| 54 | Cut-backs | Low or ground pass played backwards from the byline zone into the box (StatsBomb zone rule) | E2, Q | /90 | Std\* | SB-SPEC |
| 55 | Pass direction split | Forward, back, lateral passes by 90-degree sectors rotated 45 degrees (Wyscout: lateral passes >12 m) | E2 | count, % | Std\* | WY-metrics |
| 56 | Average pass length | Mean pass length (FBref GK version excludes goal kicks) | E2 | yards or metres | Std | FB-GK, WY-metrics |
| 57 | Live-ball vs dead-ball passes | Dead-ball = free kicks, corners, kick-offs, throw-ins, goal kicks | Q | split | Std | FB-PT |
| 58 | Corner types | In-swinging, out-swinging, straight corners | Q | count | Std | FB-PT |
| 59 | Passes blocked / offside | Passes blocked by an opponent in the path; passes that caught a teammate offside | E | count | Std | FB-PT |
| 60 | Pressured / unpressured long balls | Long balls or clearances attempted under pressure vs without (centre-back radar) | E2, Q (under_pressure) | /90 | Prop (StatsBomb) | SB-RAD, SB-SPEC |
| 61 | Expected pass completion (xPass, xP) | Probability a pass is completed given start x, mirrored y, angle, distance, head/foot, cross, set piece, height, prior actions | E2, Q, M (FF/T improve it) | mean xP per pass (risk) | Std\* (model Prop) | OA-XP |
| 62 | Passes completed above expected (PAx) | Sum of (outcome - xP); usually per 100 passes | E2, M | per 100 passes | Prop (Stats Perform) | OA-XP |
| 63 | Line breaks | Ball moved beyond the deepest player of an opposition unit (line) | T (or FF) | count, % completed | Std\* (FIFA EFI) | FIFA-LB |
| 64 | Packing / IMPECT | Opponents (Packing) or defenders (IMPECT) bypassed by a pass or dribble; passer and receiver both credited for passes | T or FF | bypassed opponents /90 | Prop (Impect) | IMPECT |
| 65 | xGChain | Sum of xG of every possession a player is involved in (any on-ball action), credited in full to each involved player | E, SEQ, M | /90 (StatsBomb used 600+ min) | Open (StatsBomb) | SB-XGC |
| 66 | xGBuildup | xGChain excluding possessions where the player only shot or assisted (credit for earlier involvement) | E, SEQ, M | /90, pct (CB/FB/MF radars) | Open (StatsBomb) | SB-XGC, SB-RAD |
| 67 | Open-play xG assisted | xG assisted excluding set pieces | E, Q, M | /90 | Prop (StatsBomb radar) | SB-RAD |

## 3. Possession and progression (carries, take-ons, entries, receiving)

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 68 | Touches | Times a player touched the ball; receive + dribble + pass counts as one touch (FBref); Opta excludes aerial or challenge lost | E | /90 | Std | FB-POS, OPTA-DEF |
| 69 | Touches by zone | Touches in defensive penalty area, defensive third, middle third, attacking third, attacking penalty area; live-ball touches exclude set pieces | E | /90, touch map | Std | FB-POS |
| 70 | Touches in box | Passes or touches in the opponent penalty area, excluding duels and fouls (Wyscout); StatsBomb counts successful footed touches incl. shots | E | /90, pct (summary stat) | Std\* | WY-touch_in_box, SB-RAD |
| 71 | Carries | Times a player controls the ball with their feet while moving or standing (StatsBomb event; Opta Analyst requires 5 m or more) | E2 (carry start/end) | /90 | Std\* | FB-POS, SB-SPEC, OA-DEF |
| 72 | Total carrying distance | Yards moved with the ball at feet in any direction | E2 | yards /90 | Std | FB-POS |
| 73 | Progressive carrying distance | Yards moved with the ball toward the opponent goal | E2 | yards /90 | Std | FB-POS |
| 74 | Progressive carries (FBref/Opta) | Carry that moves the ball toward the goal line at least 10 yd from its furthest point in the last six passes, or any carry into the box; excludes carries ending in the defending 50% | E2, SEQ | /90, pct (summary stat) | Std\* | FB-POS |
| 75 | Progressive runs (Wyscout) | Continuous ball control that gets 30 m closer if within own half, 15 m if crossing halves, 10 m if within opponent half | E2 | /90 | Std\* | WY-progressive_run |
| 76 | Progressive carry (Opta Analyst) | Carry moving the ball more than 5 m upfield | E2 | /90 | Std\* | OA-DEF |
| 77 | Carry directness | Upfield distance as a % of total carry distance | E2 | % | Prop (Opta Analyst) | OA-DEF |
| 78 | Carries into final third / penalty area | Carries that enter the attacking third / the 18-yard box | E2 | /90 | Std | FB-POS |
| 79 | Shot-ending / chance-ending carries | Carries resulting in a shot or goal / in a chance created or assist | E2, SEQ | /90 | Prop (Opta Analyst) | OA-DEF |
| 80 | Deep progressions | Passes and dribbles/carries into the opposition final third | E2 | /90, pct (FB/MF radars) | Prop (StatsBomb) | SB-RAD |
| 81 | Final third entries | Team moves the ball into the final third by pass or carry (FIFA EFI) | E2 or T | count by method and channel | Std\* | FIFA-EFI |
| 82 | Take-ons attempted / successful | Attempts to beat a defender while dribbling; unsuccessful includes keeping the ball but not getting past (FBref); Opta counts heavy-touch overruns as attempts | E | /90, pct (summary stat) | Std\* | FB-POS, OPTA-DEF |
| 83 | Take-on success % | Successful / attempted (FBref min .5 take-ons per squad game) | E | % | Std | FB-POS |
| 84 | Tackled during take-on (%) | Times (and share) a take-on attempt ended in a tackle | E | count, % | Std | FB-POS |
| 85 | Dribbles (Wyscout) | Attempt to move past an opponent keeping the ball; successful if next action is the same player closer to goal, or a teammate closer to goal, or a foul is drawn | E | /90, % | Std\* | WY-dribble |
| 86 | Offensive duels | Ground duel for the player in possession incl. shielding (a dribble is a subset) | E | /90, % won | Prop (Wyscout taxonomy) | WY-offensive_duel |
| 87 | Accelerations (with ball) | Meaningful run with the ball at least 10 m with a clear speed-up (event tag, not tracking) | E | /90 | Prop (Wyscout) | WY-acceleration |
| 88 | Miscontrols | Failed attempts to gain control of the ball (StatsBomb: ball lost due to bad touch) | E | /90 | Std | FB-POS, SB-SPEC |
| 89 | Dispossessed | Ball lost after a tackle without attempting a take-on | E | /90 | Std | FB-POS, SB-SPEC |
| 90 | Turnovers | Miscontrols + failed dribbles (StatsBomb radar) | E | /90 (lower is better) | Std\* | SB-RAD |
| 91 | Losses / own-half losses | Any action ending the team's possession, located where it is lost; zones low/mid/high; "leading to opponent shot" within 20 s | E, SEQ | /90 | Std\* (Wyscout) | WY-loss |
| 92 | Loss index | Ball losses / successful attacking actions (shots on target, accurate crosses, successful dribbles) | E | ratio | Prop (Wyscout) | WY-player_metrics |
| 93 | Passes received | Times a player successfully receives a pass | E2 | /90 | Std | FB-POS |
| 94 | Progressive passes received | Receptions of progressive passes (FBref rule) | E2, SEQ | /90, pct (summary stat) | Std\* | FB-POS |
| 95 | Received long passes | Receptions of long passes (forward reports) | E2 | /90 | Std | WY-player_reports |
| 96 | Fouls drawn | Free kicks or penalties won after being fouled (no foul won for handball, dive, back pass, etc.) | E | /90 | Std | FB-MISC, OPTA-DEF |
| 97 | Penalties won | Penalty kicks won | E | count | Std | FB-MISC |
| 98 | Link-up play | Attacker receives from a defender or midfielder with back to goal and lays it off | E (tag) | count | Prop (Wyscout) | WY-link_up_play |
| 99 | Sequence involvement | Number of sequences with at least one touch by the player | E, SEQ | count, % of team sequences | Std\* (Opta) | OPTA-DEF, OA-DEF |
| 100 | Shield ball out of play | Player shields the ball out to win a throw, corner or goal kick | E | count | Std | OPTA-DEF, SB-SPEC |

## 4. Defending

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 101 | Tackles | Legal ground challenge that takes the ball from a player in controlled possession (Opta); FBref "Tkl" counts players tackled | E | /90, pct (summary stat) | Std | OPTA-DEF, FB-DEF |
| 102 | Tackles won | Tackles where the tackler's team wins possession (or ball goes out safely) | E | /90 | Std | FB-DEF, OPTA-DEF |
| 103 | Tackles by third | Tackles in defensive / middle / attacking third | E | /90, map | Std | FB-DEF |
| 104 | Dribblers tackled / Tkl% vs dribblers | Dribblers tackled / (dribblers tackled + challenges lost) (FBref min .625 dribblers challenged per squad game) | E | % | Std | FB-DEF |
| 105 | Challenges lost (dribbled past) | Unsuccessful attempts to challenge a dribbling player | E | /90 | Std | FB-DEF, SB-SPEC |
| 106 | Tackle / dribbled-past % | Share of duels where the player tackles rather than being dribbled past (StatsBomb) | E | % | Std\* | SB-RAD |
| 107 | Missed tackles | Fouls with an attempted-tackle qualifier + times beaten by a dribble (Opta) | E | /90 | Prop (Opta) | OPTA-DEF |
| 108 | Interceptions | Reading a pass and moving into its line to cut it out; Wyscout also counts blocked shots as interceptions | E | /90, PAdj | Std\* | OPTA-DEF, FB-DEF, WY-interception |
| 109 | Tackles + interceptions (Tkl+Int) | Sum of the two | E | /90 | Std | FB-DEF |
| 110 | Blocks (shots, passes) | Blocking the ball by standing in its path; Opta: no block if the shot was going wide; last-line clearances count as shots on target, not blocks | E | /90 | Std\* | FB-DEF, OPTA-DEF |
| 111 | Clearances | Getting the ball away from danger with no intended recipient | E | /90 | Std | OPTA-DEF, SB-SPEC |
| 112 | Errors | On-ball mistakes leading to an opponent's shot (FBref) or shot or goal (Opta, incl. GK spills) | E | count | Std | FB-DEF, OPTA-DEF |
| 113 | Ball recoveries | Securing a loose ball or one played directly to you by an opponent (Opta); Wyscout: any action ending the opponent's possession and starting yours | E, SEQ | /90 | Std\* | OPTA-DEF, FB-MISC, WY-recovery |
| 114 | Opponent-half / high recoveries | Recoveries located in the opponent half or final third | E, SEQ | /90, map | Std\* | WY-recovery |
| 115 | Counterpressing recoveries | Recoveries that end an opponent possession lasting under 5 seconds | E, SEQ | /90 | Prop (Wyscout) | WY-counterpressing_recovery |
| 116 | Pressures | Defender applies pressure to a player receiving, carrying or releasing the ball; triggered within about 5 yards (up to 10 yards) and the duration is recorded | E (manual tag with duration) or T | /90, pct, map | Prop (StatsBomb event) | SB-SPEC, SB-CP |
| 117 | Pressure regains | Team wins the ball back within 5 seconds of the player pressuring an opponent | E, SEQ | /90 | Prop (StatsBomb) | SB-RAD |
| 118 | Counterpressures | Pressures within 5 seconds of an open-play turnover (StatsBomb "counterpress" flag; SkillCorner uses a 3-second window) | E or T | /90 | Std\* | SB-SPEC, SB-CP, SC-OBE |
| 119 | Under-pressure flag | Any on-ball event overlapping the time window of a pressure event (made or received under pressure) | E, Q | % of passes under pressure | Prop (StatsBomb) | SB-SPEC |
| 120 | Pressing duels | Player closes down a ball carrier without physical or ball contact | E | /90 | Prop (Wyscout) | WY-pressing_duel |
| 121 | Defensive duels | Attempt to dispossess a ball carrier; won if the attack is stopped without a foul (dispossess, kick out, force backwards) | E | /90, % won | Prop (Wyscout taxonomy) | WY-defensive_duel |
| 122 | Loose ball duels / 50-50s | Contest for a ball neither team controls | E | /90, % won | Std\* | WY-loose_ball_duel, SB-SPEC |
| 123 | Duels won % | All duels (offensive, defensive, loose, aerial) won / contested; Opta: every duel won has a matching duel lost | E | % | Std\* | OPTA-DEF, WY-metrics |
| 124 | Aerial duels won / % | Two or more opponents challenge in the air; won by the first to touch the ball, or by the player fouled | E | /90, % (FBref min .97 aerials per squad game) | Std | OPTA-DEF, WY-aerial_duel, FB-MISC |
| 125 | Sliding tackles | Aggressive slide to dispossess or clear; possession-adjusted per 30 min of opponent possession (Wyscout) | E, Q, MIN | PAdj | Prop (Wyscout) | WY-sliding_tackle |
| 126 | PAdj tackles / interceptions (StatsBomb) | Count x 2 / (1 + e^(-0.1 x (possession% - 50))): scales defensive counts to a 50% possession baseline | E, MIN (team possession) | /90 PAdj, radar | Prop (StatsBomb) | SB-PADJ |
| 127 | PAdj / Opp30 (Wyscout) | Count / opponent pure possession minutes x 30 (60 min ball-in-play baseline) | E, SEQ, MIN | per 30 min opp. possession | Prop (Wyscout) | WY-p_adj |
| 128 | Fouls committed | Infringements penalised by a free kick or penalty (offsides excluded) | E | /90 | Std | OPTA-DEF, FB-MISC |
| 129 | Cards | Yellow, second yellow, red; Opta discipline points 1 per foul, 3 per yellow, 6 per red | E | count | Std | OPTA-DEF, FB-MISC |
| 130 | Offside provoked | Deepest defender in the line when an offside is given | E | count | Prop (Opta) | OPTA-DEF |
| 131 | Progressive passes allowed | Opponent progressive passes made in the player's zone (e.g. defensive left flank for a left back) | E2 | /90 (lower is better) | Prop (Wyscout) | WY-player_metrics |
| 132 | Defensive coverage | Polygon (and area in m^2) of the zone implied by a player's defensive actions | E | map, m^2 | Prop (Opta) | OPTA-DEF |
| 133 | Covering depth / defensive positioning | Non-ball runs to cover a teammate's empty zone or recover shape (bad positioning tagged as an error) | E (manual non-ball tags) | count | Prop (Wyscout) | WY-covering_depth, WY-defensive_positioning |
| 134 | On-ball engagements (pressure, pressing, counter-pressure, recovery pressure) | From tracking: single-player engagement; coordinated multi-player chain; within 3 s of a loss; defender tracking back to press | T | /90, /30 min OTIP | Prop (SkillCorner) | SC-OBE |
| 135 | Forced turnovers | Turnovers forced by the defending team's pressure (FIFA EFI) | T, E | count, map | Std\* | FIFA-EFI |

## 5. Goalkeeping

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 136 | Goals against | Goals conceded while on the pitch (FBref splits penalties, free kicks, corners, own goals) | E | /90 | Std | FB-GK |
| 137 | Shots on target faced / saves / save % | On-target shots faced; saves with body part, type (caught, parried safe/danger, fingertip) and movement; save % = saves / SoT faced | E, Q | count, % | Std | OPTA-DEF, WY-save, WY-shot_against |
| 138 | Clean sheets | Matches with no goal conceded for the full match | E | count, % | Std | OPTA-DEF |
| 139 | PSxG faced | Post-shot xG of on-target shots faced (Opta model at FBref) | E, Q (goal-mouth end point), M | total, PSxG/SoT (difficulty) | Prop (Opta) | FB-GK, FB-XG |
| 140 | PSxG - GA (goals prevented) | PSxG faced minus goals allowed (own goals excluded); positive = better than average shot stopping | E, M | total, /90, pct | Std\* | FB-GK |
| 141 | GSAA% | (PSxG - goals) / shots faced; StatsBomb's PSxG deliberately ignores GK position so positioning is not penalised | E, FF, M | % | Prop (StatsBomb) | SB-PSXG |
| 142 | xCG / xG2, xG saved | Wyscout post-shot xG of shots on target against; xG saved = xCG - goals conceded | E, M | total, /90 | Prop (Wyscout) | WY-save, WY-player_reports |
| 143 | Penalties faced / saved | Penalty events with GK movement (dive left/right, stand) and outcome | E, Q | count, % | Std | OPTA-DEF |
| 144 | Crosses faced / stopped / stopped % | Opponent crosses into the box and the share the GK successfully stopped | E | count, % | Std\* | FB-GK |
| 145 | Catches, punches, drops, cross not claimed | High balls caught; punched with clenched fist; caught then dropped; came off line and missed | E | count | Std | OPTA-DEF |
| 146 | Catch success | (Catches + punches) / high balls the GK came for | E | % | Prop (Opta) | OPTA-DEF |
| 147 | Exits / GK leaving line | Attempts to claim or punch a high cross or long aerial pass (Wyscout) | E | /90 | Prop (Wyscout) | WY-gk_leaving_line |
| 148 | Keeper sweeper | GK rushes out to at least the edge of the area under some opponent pressure to cut out a pass or close down a forward | E | count | Prop (Opta) | OPTA-DEF |
| 149 | Defensive actions outside box (#OPA) | GK defensive actions outside the penalty area, and per 90 | E | count, /90 | Prop (FBref/Opta) | FB-GK |
| 150 | Average distance of defensive actions | Mean distance from goal (yards) of the GK's defensive actions (sweeper depth) | E | yards | Prop (FBref/Opta) | FB-GK |
| 151 | Smother | GK claims the ball at a forward's feet and holds it | E | count | Std | OPTA-DEF |
| 152 | Reflex saves | Saves from close range needing immediate reaction | E (tag) | count | Prop (Wyscout) | WY-reflex_save |
| 153 | Launch % / launched pass completion | Share of GK passes longer than 40 yd (excluding goal kicks), and their completion | E2 | % | Prop (FBref/Opta) | FB-GK |
| 154 | Goal kicks: launch % and average length | Share of goal kicks over 40 yd; mean goal-kick length | E2 | %, yards | Prop (FBref/Opta) | FB-GK |
| 155 | GK passes, throws, average pass length | GK passes attempted (excl. goal kicks), throws, mean length | E2 | count, yards | Std | FB-GK |
| 156 | GK positioning error | Average distance from the optimal position for facing a shot, from freeze frames | FF, M | metres | Prop (StatsBomb) | SB-PSXG |
| 157 | GK OBV | OBV earned by saves, claims, sweeping and distribution | E, FF, M | /90 | Prop (StatsBomb) | SB-OBV |

## 6. Possession-value models

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 158 | Expected Threat (xT) | 16x12 grid; xT(z) = s(z) g(z) + m(z) sum T(z->z') xT(z'), iterated about 5 times; action value = xT(end) - xT(start) for successful passes and dribbles only | E2, M (fitted on event history) | xT added /90, xT maps | Open (Karun Singh, 2018) | KS-XT, SB-PV |
| 159 | VAEP (offensive, defensive, total) | State value = P(score in next 10 actions) - P(concede in next 10); action value = change in each; two gradient-boosted classifiers on features of the last 3 SPADL actions (type, result, body part, locations, distance/angle to goal, time deltas, score) | E2, Q, M | VAEP /90, per action | Open (KU Leuven, socceraction) | VAEP |
| 160 | On-Ball Value (OBV) | Change in probability of scoring and conceding from each on-ball event; separate Goals For and Goals Against models trained on StatsBomb xG; no possession-history features; receivers get no direct credit | E2, Q (under pressure, body part), FF (via xG), M | OBV /90, split by pass, dribble & carry, defensive action, shot, GK; vs position | Prop (StatsBomb, 2021) | SB-OBV, SB-PV |
| 161 | Goals added (g+) | Change in two-possession value (xG for rest of own possession minus opponent's next-possession xG), from an xGBoost model on ball location, chain length, prior action, pass type, set-piece and velocity features | E2, SEQ, M | g+ above position average, split into shooting, passing, receiving, dribbling, interrupting, fouling | Open method (ASA) | ASA-G+, ASA-G+M |
| 162 | g+ passer/receiver split | Completed pass value split by xPass: passer gets xPass% of the value, receiver the rest; penalties: taker 0, earner 0.10 g+ | E2, M | g+ receiving vs passing | Open (ASA) | ASA-G+M |
| 163 | Possession Value (PV, PV+) | Probability the team in possession scores in the next 10 seconds; PV added credited to players for positive and negative contributions | E2, M | PV+ /90 | Prop (Stats Perform/Opta) | SP-PV, SB-PV |
| 164 | Wyscout Index | Position-specific ranking built from a set of stats per position (e.g. CB: duels won, interceptions, aerials, clearances, blocked shots, pass accuracy) | E | rank within competition | Prop (Wyscout) | WY-wyscout_index |

## 7. Physical and tracking

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 165 | Total distance | Distance covered (km) | T (optical 25 Hz, broadcast ~10 Hz) or GPS 10 Hz | km, /90 | Std | WY-physical_metrics, OA-PHYS |
| 166 | Metres per minute | Total distance / minutes played | T, MIN | m/min | Std | WY-physical_metrics |
| 167 | FIFA speed zones | Zone 1 0-6.9, Zone 2 7.0-14.9, Zone 3 15.0-19.9, Zone 4 20.0-24.9, Zone 5 >=25.0 km/h (men; same at 2018 and 2022 World Cups) | T | distance per zone, stacked bar | Std\* | FIFA-PHYS |
| 168 | Walking / jogging distance | Jogging 6-15 km/h (Opta Analyst); walking below that | T | km, % of time | Std\* | OA-PHYS |
| 169 | Running distance | Distance at 15-20 km/h | T | m /90 | Std\* | WY-physical_metrics |
| 170 | High-speed running (HSR) distance and count | Distance and number of efforts at 20-25 km/h (literature also uses 19.8 km/h) | T | m /90, count /90 | Std\* | WY-physical_metrics, HSR-REV |
| 171 | High-intensity (HI) distance and count | Distance and efforts above 20 km/h (HSR + sprints) | T | m /90, count /90 | Std\* | WY-physical_metrics, FIFA-PHYS |
| 172 | Sprint distance and sprint count | Above 25 km/h for at least 1 s (Wyscout, Premier League, Opta Analyst); older UEFA/Sky tables use 25.2 km/h; women's FIFA thresholds 19 and 23 km/h | T | m /90, count /90 | Std\* | WY-physical_metrics, OA-PHYS, HSR-REV |
| 173 | Relative speed thresholds | Sprint defined as a share of each player's max speed (80% recommended in the literature) instead of a fixed km/h | T | m /90 | Std\* (research) | HSR-REV |
| 174 | Top speed / Peak Velocity | Single highest speed reached in a match or set of matches (SkillCorner Peak Velocity, 2026) | T | km/h (max or mean of top 3) | Std (Peak Velocity Prop) | SC-PV, OA-PHYS |
| 175 | PSV-99 | 99th percentile of all a player's physical activities over 15 km/h; noise-robust proxy for top speed | T (broadcast) | km/h | Prop (SkillCorner) | SC-PV |
| 176 | Accelerations (medium, high) | Efforts peaking at 1.5-3 m/s^2 (medium) or above 3 m/s^2 (high), lasting at least 1 s | T | count /90 | Std\* | WY-physical_metrics |
| 177 | Decelerations (medium, high) | Efforts peaking at -1.5 to -3 m/s^2 or below -3 m/s^2, at least 1 s | T | count /90 | Std\* | WY-physical_metrics |
| 178 | Explosive accelerations, change of direction | SkillCorner metric suites added 2026 (named, definitions not public) | T | /90 | Prop (SkillCorner) | SC-PV, SC-PHYS |
| 179 | In / out of possession split | Any physical metric split by team phase (TIP, OTIP) | T, SEQ | m /30 min TIP/OTIP | Std\* | SC-PHYS |
| 180 | Off-ball runs (10 types) | Dropping off, coming short, pulling wide, pulling half-space, support, run ahead, overlap, underlap, run in behind, cross receiver; classified on speed, distance and threat, served or not | T | runs /90, % served, threat | Prop (SkillCorner) | SC-RUNS |
| 181 | Off-the-ball movement (event tag) | Significant movement into empty space showing readiness to receive (Wyscout manual tag) | E (non-ball tag) | count | Prop (Wyscout) | WY-off_the_ball |
| 182 | Receptions between / behind the lines | Receptions behind the opponent midfield or defensive line, optionally under pressure, and followed by a line break or distribution | T, E | count, map | Std\* (FIFA EFI) | FIFA-EFI |
| 183 | Average position | Mean x-y of a player's actions (event-based) or tracking positions | E or T | dot on pitch, formation plot | Std | PN, WY-metrics |
| 184 | Heat map / touch map | Density of a player's positions or touches over a pitch grid; FBref attacks left to right | E or T | map | Std | FB-POS |

## 8. Team and style

| # | Metric | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 185 | Possession % | FBref: share of passes attempted; Wyscout: share of pure in-play time in possession (dead time excluded) | E (or SEQ with timestamps) | % | Std\* | FB-POS, WY-ball_possession |
| 186 | Field tilt | Team's share of final-third passes (or touches) out of both teams' final-third totals | E2 | % | Std\* (public analytics) | FT |
| 187 | PPDA | Opponent passes / defensive actions in the pressing zone; Trainor (2014) and Wyscout use the opponent's final 60% (Wyscout counts fouls, interceptions, won defensive duels, sliding tackles); Opta uses passes outside the presser's defensive third and fouls, tackles, interceptions, challenges, blocked passes | E | ratio (lower = more pressing) | Std\* | WY-ppda, OA-DEF, SB-PPDA |
| 188 | Challenge intensity | Defensive actions (defensive duels, loose ball duels, interceptions, tackles) per minute of opponent possession | E, SEQ | per minute | Prop (Wyscout) | WY-challenge_intensity |
| 189 | High turnovers | Possessions starting in open play within 40 m of the opponent goal; also those ending in a shot or goal | E, SEQ | count, map | Std\* (Opta) | OA-DEF |
| 190 | Start distance | Average distance from own goal where a team's open-play sequences start (defensive height proxy) | E, SEQ | metres | Prop (Opta) | OA-DEF |
| 191 | Pressed sequences | Opponent open-play sequences starting in their defensive third with 3 or fewer passes and ending in their own half | E, SEQ | count | Prop (Opta) | OA-DEF |
| 192 | Direct attacks | Open-play sequences starting just inside own half, at least 50% of movement toward goal, ending in a shot or touch in the box | E2, SEQ | count | Prop (Opta) | OA-DEF |
| 193 | Build-up attacks | Open-play sequences of 10+ passes ending in a shot or a touch in the box | E, SEQ | count | Prop (Opta) | OA-DEF |
| 194 | Sequence metrics | Per sequence: time, passes, progress (m toward goal), length, speed, direct speed (progress / time), width, absolute width | E2, SEQ | averages, scatter | Prop (Opta) | OPTA-DEF, OA-DEF |
| 195 | Attacks, counterattacks, positional attacks | Wyscout attack = possession with at least one successful action in the final third; counterattack = quick switch after a turnover; positional = the rest | E, SEQ | count, % with shots | Prop (Wyscout) | WY-attack, WY-metrics |
| 196 | Average passes per possession / possession duration | Mean passes and seconds per open-play possession | E, SEQ | averages | Std | WY-metrics |
| 197 | Long pass share | % of a team's passes that are long | E2 | % | Std | WY-metrics |
| 198 | Average formation line | Mean x of all team events with the ball (own goal to opponent goal axis) | E | metres | Prop (Wyscout) | WY-metrics |
| 199 | Defensive line height | Distance from own goal line to the deepest outfield player; in and out of possession | T | metres over time | Std\* (FIFA EFI) | FIFA-DLH |
| 200 | Team length / width / shape | Distance between deepest and highest outfielders, lateral spread, block shape | T | metres, shape plot | Std\* | FIFA-DLH, FIFA-EFI |
| 201 | Ball recovery time | Time a team takes to regain possession after losing it | E, SEQ (or T) | seconds | Std\* (FIFA EFI) | FIFA-BRT |
| 202 | Phases of play | Ball-in-play time split into in- and out-of-possession phases (e.g. build-up, counter-attack, pressing blocks) | T | % of time | Std\* (FIFA EFI) | FIFA-PHASES, FIFA-PHYS |
| 203 | xG for / against / difference | Team xG, xGA and xGD (FBref totals include penalties) | E, M | table, rolling line | Std | FB-XG |
| 204 | Set-piece output | Corners or free kicks leading to a shot within 14 seconds; set-piece xG by type | E, Q, SEQ | count, % | Std\* | WY-metrics, OPTA-DEF |
| 205 | Pass networks | Nodes at players' average pass locations, edges weighted by completed passes between pairs, usually up to the first substitution | E2 | network on pitch | Std | PN |
| 206 | On-pitch goals / xG +/- and On-Off | Team goals or xG for minus against while a player is on; On-Off = on-pitch net per 90 minus off-pitch net per 90 | E, MIN | /90 | Std | FB-PT2 |
| 207 | Points per match | Average team points in matches the player appeared in | E | ratio | Std | FB-PT2 |

## 9. Context and adjustments

| # | Convention | Definition | Data | Presentation | Std | Source |
|---|---|---|---|---|---|---|
| 208 | Per 90 | Count / (minutes / 90); FBref "90s" = minutes divided by 90 | MIN | /90 | Std | FB-DEF, SB-RAD |
| 209 | Leader minimums | FBref rate leaders need 30 minutes per squad game; rate stats also need attempts (e.g. .395 shots, .5 take-ons, .97 aerials per squad game) | MIN | qualifier flag | Std\* | FB-ST, FB-POS, FB-MISC |
| 210 | Scouting-report minimums | FBref: 450 min for a report and 1,350 min for the comparison pool over the last 365 days; per-season reports 450 min (180 for UCL/UEL); StatsBomb publishes at 600+ min; Wyscout physical at 60+ active minutes | MIN | inclusion rule | Std\* | FB-SR, SB-CP, SB-XGC, WY-physical_metrics |
| 211 | Position peer groups | FBref uses six position sets (GK, CB, FB incl. wing-backs, MF, AM/W, FW) from minutes at position in Opta formation data | E (lineups, formations) | filter | Std\* | FB-SR |
| 212 | Percentile rank | FBref: mean of % of peers strictly below and % at or below; inverted where lower is better (goals against, turnovers) | per-90 table | 0-100, pizza chart, bars | Std | FB-SR |
| 213 | Rolling 365-day window and competition groups | Last 365 days, compared only within a competition group (Big 5 + UCL/UEL, next 14, women's top 9) | E, dates | report header | Std\* (FBref) | FB-SR |
| 214 | Radar boundaries | StatsBomb radar axes run from the bottom 5% to the top 5% of production at the position (Big 5 seasons); many axes are style markers, not quality | per-90 table | radar | Prop (StatsBomb) | SB-RAD |
| 215 | Possession adjustment | Scale defensive volume to 50% possession (StatsBomb sigmoid) or per 30 minutes of opponent possession (Wyscout); FBref reports are not adjusted | MIN, SEQ | PAdj columns | Std\* | SB-PADJ, WY-p_adj, FB-SR |
| 216 | Similarity search | FBref: up to 10 players with the smallest differences across the ~20 summary percentiles, all weighted equally | percentile table | ranked list, compare view | Std\* | FB-SR |
| 217 | Summary template (about 20 stats) | One fixed outfield template (npG, npxG, shots, assists, xAG, npxG+xAG, SCA, passes, pass %, prog. passes, prog. carries, take-ons, att-pen touches, prog. passes received, tackles, interceptions, blocks, clearances, aerials won) so layouts stay familiar | per-90 table | percentile bars | Std\* (FBref) | FB-SR |
| 218 | Position-specific report sets | Different headline stats per position (Wyscout reports: e.g. forwards add touches in box, received long passes, recoveries in final third) | per-90 table | rankings | Std\* | WY-player_reports, SB-RAD |
| 219 | Share of squad minutes | Player minutes / team minutes (availability, trust) | MIN | % | Std | FB-PT2 |
| 220 | Age at season start | FBref age as of 1 August (winter leagues) or 1 February (summer leagues) | dates | years | Std | FB-DEF |
| 221 | Age curves | Minutes-weighted curves put the peak at about 25-28; forwards peak earliest (about 25), centre-backs and goalkeepers later and decline slowly (CB curve flat until 31-32) | MIN, dates | curve, age-adjusted percentile | Std\* (research) | AGE |
| 222 | Per 100 passes / per shot / per touch | Efficiency normalisers for skill metrics (PAx per 100 passes, npxG per shot, shot touch %) | E | rate | Std | OA-XP, FB-ST, SB-RAD |

---

## Scouting presentation conventions

- **Per 90 first, totals second.** Rates are per 90 minutes; totals appear only next to minutes. Scouts read a rate next to
  its sample size (FBref prints "Based on 2866 minutes played" under every report). [FB-SR]
- **Percentiles against position peers**, not the whole league. FBref compares within six position sets and a competition
  group over the last 365 days; StatsBomb radars use position templates whose axes span the 5th to 95th percentile of the
  Big 5. A percentile always names its peer group and window. [FB-SR, SB-RAD]
- **Minimum minutes** keep tiny samples out of the comparison pool (FBref 1,350 min for the pool, 450 for a report;
  StatsBomb articles 600+). Players under the pool minimum still get a report but do not move the percentiles. [FB-SR, SB-CP]
- **Pizza charts and radars** for a single-player profile (one slice per metric, coloured by group: attacking,
  possession, defending); **percentile bars** in tables; **scatter plots** of two rates (npxG/90 vs xAG/90, progressive
  passes vs progressive carries) with the peer pool as grey dots for shortlisting; **pitch maps** (shots sized by xG,
  progressive passes as arrows, touch heat maps, defensive action maps) for the "how" behind the number.
- **Similarity search** from the same percentile vector: smallest distance, equal weights at FBref; commercial tools add
  weighting and filters (age, league, minutes, contract). [FB-SR]
- **Style vs quality.** StatsBomb notes many radar axes (especially for defenders) are stylistic markers; volume defending
  is shown possession-adjusted. [SB-RAD, SB-PADJ]
- **Name the provider.** Progressive passes, PPDA, sprint and xG differ by provider (see rows 28-30, 187, 172, 10);
  comparisons across providers are not valid.

## The ten metrics scouts lean on most

Chosen because they appear in FBref's fixed summary template and in the StatsBomb and Wyscout position reports
[FB-SR, SB-RAD, WY-player_reports], and because together they cover scoring, creating, progressing and defending:

1. **npxG per 90** (with npxG per shot): how many good chances a player gets.
2. **xAG / xA per 90**: the quality of chances a player creates.
3. **Shot-creating actions per 90**: creation volume beyond the final pass.
4. **Progressive passes per 90**: moving the ball up the pitch with the pass.
5. **Progressive carries per 90**: moving the ball up the pitch on the dribble.
6. **Progressive passes received per 90**: getting on the ball in advanced areas (forwards and wingers).
7. **Successful take-ons per 90 and take-on %**: beating a player.
8. **Touches in the attacking penalty area per 90**: presence in the box.
9. **Tackles + interceptions, possession-adjusted, with pressures and pressure regains**: defensive work rate.
10. **Aerial duel win %**: physical dominance (centre-backs, strikers).

Possession-value totals (**OBV, g+, VAEP, xT**) sit on top as the one-number summary, and **pass completion %** is
always read next to pass difficulty (xPass) or volume.

## Raw-data requirements in short

- **Event data with start and end x-y, outcome, body part and timestamps** covers rows 1-15, 17-62, 65-133 and 136-155,
  the whole FBref/Opta catalogue.
- **Possession segmentation** (which events form one team possession, how it started and ended) is needed for SCA/GCA,
  progressive actions (the "last six passes" rule), xGChain, high turnovers, sequences, PPDA zones and possession %.
- **Freeze frames** (positions of players at the shot) improve xG and enable GSAA%, GK positioning error, packing and line
  breaks without full tracking.
- **Tracking at 10-25 Hz** is required for every physical metric, off-ball runs, on-ball engagements, defensive line
  height, team shape and phases of play. Speed bands assume smoothed speed; efforts usually need a 1-second minimum.
- **Trained models** (xG, xGOT/PSxG, xPass, OBV, VAEP, g+, PV) need a large historical shot or action sample.

## Known but not verified in this pass

These are widely used but were not read from a primary source here; treat the names as pointers, not definitions:
Catapult PlayerLoad (accelerometer load), academic EPV and pitch-control models (Fernandez, Spearman), Second Spectrum's
and Genius Sports' tracking-derived metrics, StatsBomb 360 metrics (xPass 360), and Opta Vision tracking metrics.

## Sources

| Key | Source (read 2026-10-23) |
|---|---|
| FBREF-2026 | Awful Announcing, Sports Reference pulls advanced data: https://awfulannouncing.com/soccer/sports-reference-pulls-advanced-data-agreement-violation-dispute.html |
| FB-ST | FBref Premier League shooting table, tooltips (Wayback 2025-03-31): https://fbref.com/en/comps/9/shooting/Premier-League-Stats |
| FB-PA | FBref passing table (Wayback 2025-05-03): https://fbref.com/en/comps/9/passing/Premier-League-Stats |
| FB-PT | FBref pass types table (Wayback 2025-04-03): https://fbref.com/en/comps/9/passing_types/Premier-League-Stats |
| FB-GCA | FBref goal and shot creation table (Wayback 2025-05-04): https://fbref.com/en/comps/9/gca/Premier-League-Stats |
| FB-DEF | FBref defensive actions table (Wayback 2024-11-23): https://fbref.com/en/comps/9/defense/Premier-League-Stats |
| FB-POS | FBref possession table (Wayback 2025-05-04): https://fbref.com/en/comps/9/possession/Premier-League-Stats |
| FB-MISC | FBref miscellaneous table (Wayback 2025-06-17): https://fbref.com/en/comps/9/misc/Premier-League-Stats |
| FB-GK | FBref advanced goalkeeping table (Wayback 2025-05-06): https://fbref.com/en/comps/9/keepersadv/Premier-League-Stats |
| FB-PT2 | FBref playing time table (Wayback 2025-07-29): https://fbref.com/en/comps/9/playingtime/Premier-League-Stats |
| FB-XG | FBref, What is xG? (Wayback 2025-05-04): https://fbref.com/en/expected-goals-model-explained/ |
| FB-SR | FBref, Scouting Reports Explained (Wayback 2025-05-01): https://fbref.com/en/about/scouting-reports-explained ; example report https://fbref.com/en/players/bc7dc64d/scout/365_m1/Bukayo-Saka-Scouting-Report |
| OPTA-DEF | Stats Perform, Opta Event Definitions (Wayback 2024): https://www.statsperform.com/opta-event-definitions/ |
| OA-DEF | The Analyst, Opta football stats definitions: https://theanalyst.com/articles/opta-football-stats-definitions |
| OA-XGOT | The Analyst, What are expected goals on target (xGOT): https://theanalyst.com/articles/what-are-expected-goals-on-target-xgot/ ; Stats Perform, Enhancing xGOT: https://www.statsperform.com/insights/enhancing-expected-goals-on-target/ |
| OA-XP | The Analyst, Expected pass completion explained: https://theanalyst.com/articles/expected-pass-completion-explained |
| OA-PHYS | The Analyst, Premier League players distance run, sprints: https://theanalyst.com/articles/premier-league-players-distance-run-fastest-slowest-sprints-walking |
| SP-PV | Stats Perform, Introducing a Possession Value framework: https://www.statsperform.com/resource/introducing-a-possession-value-framework/ |
| SB-SPEC | StatsBomb Open Data Events specification v4.0.0 (PDF): https://github.com/statsbomb/open-data/blob/master/doc/Open%20Data%20Events%20v4.0.0.pdf |
| SB-OBV | Hudl StatsBomb, Introducing On-Ball Value (OBV): https://www.hudl.com/blog/introducing-on-ball-value-obv |
| SB-PV | Hudl StatsBomb, Possession value models explained: https://www.hudl.com/blog/possession-value-models-explained |
| SB-XGC | Hudl StatsBomb, Introducing xGChain and xGBuildup: https://www.hudl.com/blog/introducing-xgchain-and-xgbuildup |
| SB-RAD | StatsBomb, Understanding StatsBomb Radars: https://blogarchive.statsbomb.com/articles/soccer/understanding-statsbomb-radars/ |
| SB-PADJ | StatsBomb, Introducing possession-adjusted player stats: https://blogarchive.statsbomb.com/articles/soccer/introducing-possession-adjusted-player-stats/ |
| SB-PSXG | Hudl StatsBomb, A new way to measure keepers' shot stopping: post-shot expected goals: https://www.hudl.com/blog/a-new-way-to-measure-keepers-shot-stopping-post-shot-expected-goals |
| SB-CP | StatsBomb, How StatsBomb data helps measure counter-pressing: https://blogarchive.statsbomb.com/articles/soccer/how-statsbomb-data-helps-measure-counter-pressing/ |
| SB-PPDA | Colin Trainor, Defensive Metrics: Measuring the Intensity of a High Press (StatsBomb, 2014): https://statsbomb.com/?p=10118 (via search summary) ; Premier League explainer: https://www.premierleague.com/news/4250153 |
| WY-* | Wyscout glossary, entry per slug: https://dataglossary.wyscout.com/{slug}/ (e.g. progressive_pass, progressive_run, ppda, physical_metrics, p_adj, deep_competion, smart_pass, xa, xg, player_metrics, metrics, player_reports, wyscout_index) |
| KS-XT | Karun Singh, Introducing Expected Threat (xT): https://karun.in/blog/expected-threat.html |
| VAEP | Decroos et al., Actions Speak Louder Than Goals: https://arxiv.org/abs/1802.07127 ; socceraction VAEP docs: https://socceraction.readthedocs.io/en/latest/documentation/valuing_actions/vaep.html |
| ASA-G+ | American Soccer Analysis, What are Goals Added?: https://www.americansocceranalysis.com/what-are-goals-added |
| ASA-G+M | American Soccer Analysis, Goals Added: Deep Dive Methodology: https://www.americansocceranalysis.com/home/2020/5/4/goals-added-deep-dive-methodology |
| SC-PV | SkillCorner, Introducing Peak Velocity: https://www.skillcorner.com/articles/skillcorner-releases-new-peak-velocity-metric |
| SC-PHYS | SkillCorner Physical Data: https://skillcorner.com/products/football/physical-data |
| SC-RUNS | SkillCorner, Game Intelligence off-ball run types: https://skillcorner.com/blog/game-intelligence-off-ball-run-types |
| SC-OBE | SkillCorner Game Intelligence out-of-possession (via search summary): https://skillcorner.com/blog/gi-oop |
| FIFA-EFI | FIFA Training Centre, EFI metrics index: https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/efi-metrics/player-involvement.php |
| FIFA-LB | FIFA EFI, Line breaks: https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/efi-metrics/line-breaks.php |
| FIFA-DLH | FIFA EFI, Defensive line height and team length: https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/efi-metrics/defensive-line-height-and-team-length.php |
| FIFA-BRT | FIFA EFI, Ball recovery time: https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/efi-metrics/ball-recovery-time.php |
| FIFA-PHASES | FIFA EFI, Phases of play: https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/efi-metrics/phases-of-play.php |
| FIFA-PHYS | FIFA Qatar 2022 physical analysis, background and method: https://fifatrainingcentre.com/en/fwc2022/physical-analysis/background-and-method.php ; Setting the Benchmark Part 2 (Biology of Sport): https://termedia.pl/-Setting-the-Benchmark-Part-2-Contextualising-the-Physical-Demands-of-Teams-in-the-FIFA-World-Cup-Qatar-2022,78,51366,1,0.html |
| HSR-REV | High-speed running and sprinting in professional adult soccer, systematic review: https://pmc.ncbi.nlm.nih.gov/articles/PMC9968809/ |
| IMPECT | Packing explained (secondary): https://anfieldindex.com/25279/liverpool-analytics-packing-palace.html |
| FT | Field tilt (secondary): https://ladumaanalytics.substack.com/p/beyond-ball-possession-the-case-for ; https://www.sportmonks.com/glossary/key-data-points |
| PN | Soccermatics, Passing networks: https://soccermatics.readthedocs.io/en/latest/gallery/lesson1/plot_PassNetworks.html ; ASA, How to use passing networks: https://www.americansocceranalysis.com/home/2024/6/20/how-to-use-passing-networks-in-soccer |
| AGE | ESPN, soccer age curves: https://global.espn.com/football/story/_/id/37467220/soccer-age-curves-show-goalkeepers-central-defenders-peak-latest ; ISACE paper: https://www.ida.liu.se/~nikca89/papers/isace24.pdf |

Sources marked "via search summary" or "secondary" were read only through a search-result summary or a third-party
explainer, not the provider's own documentation.
