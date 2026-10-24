# Regista synthetic event stream — the contract

This folder defines the **boundary between Regista's two layers** (see `CLAUDE.md` §1.5):

- The **private vision layer** reads video and writes this event stream.
- The **public intelligence layer** reads this event stream and writes clips, labels, and chatbot answers.

Nothing that crosses this boundary contains a pixel of footage. A synthetic match generator produces the same stream from no footage at all, which is what powers the public demo.

```
src/regista/schemas/               shipped inside the package, so any install can validate
├── regista-events.schema.json        vision-layer output (match, camera_segment, track, appearance, possession, event, annotation)
└── regista-clips.schema.json         intelligence-layer output (clip, label)

data/synthetic/
├── README.md                          this document
└── sample/<match_id>/
    ├── events.jsonl                   everything except tracks, sorted by t (match header first)
    ├── tracks.jsonl                   sampled positions, sorted by t (large; sampled at --track-hz)
    ├── clips.jsonl                    derived clips and labels for the chosen player
    └── manifest.json                  record counts, generator parameters, score
```

Generate and validate:

```bash
python -m regista.synth --minutes 3 --seed 294 --track-hz 1 --player t_home_09 --out data/synthetic/sample --report
python -m regista.validate data/synthetic/sample/syn_0294
python -m regista.synth.report --profile realistic --seeds 21 22 23 --minutes 30
python -m regista.synth.report --league --repeat 3      # the Regista League in league mode (players with ratings)
python -m regista.season.audit                          # split-half reliability within a role, and the scoring chart
```

`--periods 2` simulates two halves (`--minutes` is per half): the teams swap ends, the clock continues from 45', a `graphic` camera segment marks half time. `--home`/`--away` take `Name,SHORT,#primary[,#secondary[,#gk]]` so the demo can show different clubs. The generator has two profiles. `demo` (default) packs a short sample with shots, take-ons, and nutmegs so a 3-minute clip reel has content; its per-90 rates sit well above real football. `realistic` is tuned so that per-90 passes, completion, shots, xG per shot, tackles, interceptions, take-ons, nutmegs, fouls, corners, throw-ins, and possession length sit inside approximate Premier League bands (see `regista/synth/report.py` for the bands and their source). `report.md` next to a generated match states which bands it meets.

## Conventions

| Concern | Rule |
|---|---|
| Format | JSON Lines, one record per line, UTF-8. Streams cleanly into Azure Event Hubs, Fabric Eventstream, and Cosmos DB. |
| Envelope | Every record has `type`, `id`, `match_id`, `schema_version`, `source`, and (except `match`) `confidence`. |
| `id` | Unique within a match. Prefix by type: `ev_`, `po_`, `cs_`, `tr_`, `ap_`, `an_`, `cl_`, `lb_`. Since 0.1.1, clip and label ids include the player (`cl_t_home_09_000001`, `lb_t_home_09_000001`), because several players' clips share one `clips.jsonl` and one Cosmos DB partition. |
| `match_id` | Partition key everywhere (Cosmos DB, Fabric). |
| `source` | `vision` (from footage), `synthetic` (from the generator), `human` (a person's corrections), `derived` (intelligence layer). |
| `confidence` | 0–1. Vision and derived records carry real model confidence; synthetic records jitter it so downstream code never assumes 1.0. |
| Time `t` | Seconds from the start of the **video**, not the match clock. Broadcast feeds pause, replay, and cut; video time is the only axis that lines up with frames. `t_end` is exclusive. `frame` is optional and equals `round(t * video.fps)`. |
| `clock` | Match clock on events: `{period, minute, second}`. Derived from `match.periods`. |
| Pitch coordinates | Metres, absolute frame: `x` 0–105 along the length, `y` 0–68 along the width, origin at the corner to the main camera's left. Which team attacks toward `x = 105` is in `match.periods[].left_to_right_team_id`. Consumers flip when they need an attacking frame. |
| Image coordinates | `bbox` is `{x, y, w, h}` normalised 0–1 of the frame, top-left origin. |
| Versioning | `schema_version` is semver; the current version is **0.2.0** (`regista.schema.SCHEMA_VERSION`). Additive fields bump the patch. Renames and enum changes bump the minor and must update both schemas, the generator, and `tests/`. 0.2.0 added the event type `aerial_duel`, the possession `lost_by` value `offside` (see "League mode" below) and the record type `physical` (league mode only); every 0.1.x stream stays valid. The generator stamps a match **0.2.0** only in league mode; without player ratings it writes exactly what it wrote before, stamped **0.1.1** (`LEGACY_SCHEMA_VERSION`), so committed samples and the vision layer's seeds do not move a byte. The same rule holds outside the generator: the vision layer (`regista.vision`, including the Player view's cloud worker), Who's who answers, Keep/Drop verdicts and claims use nothing added in 0.2.0, so they stamp **0.1.1** too (committed `vis_0201` reproduces byte for byte). |

## Record types (vision layer → `regista-events.schema.json`)

### `match` — one per stream, always first

Teams, roster (with `kit_number`, `position`, `starter`), kit colours (hex), video metadata (`fps`, `width`, `height`, `duration_s`), `periods` (start/end in video time plus attacking direction), and `generator` provenance when synthetic.

**Seasons (optional, added 2026-10-22).** In a match from the Regista League (`regista.season`), each team also carries `club_id` (the club across matches) and each roster entry `global_player_id` (`pl_…`, the same person in every match). Per-match ids (`t_home_09`) are unchanged, so every other record and the clip rule work as before. Both fields are optional; streams without them are still valid 0.1.1.

### `camera_segment` — what the director is showing

| Field | Meaning |
|---|---|
| `kind` | `main` (live wide broadcast camera), `replay`, `highlight` (packaged montage), `closeup`, `crowd`, `bench`, `graphic`, `other` |
| `playback_speed` | 1.0 live; replays are typically 0.25–0.5 |
| `replay_of` | Event ids this segment replays |
| `replays_window` | The main-view `{t, t_end}` being reproduced, so a replay can be mapped back to live time |
| `angle` | Free text: `reverse`, `behind_goal`, `high_wide`, `touchline_cam` |

Segments are contiguous and non-overlapping and cover the whole video.

### `track` — a sampled position of a player, the ball, or a referee

`segment_id`, `object`, `track_id` (stable within a segment, even when identity is unknown), optional `player_id`/`team_id`, `pitch` (when the homography is available), `bbox`, and `identity` with its own `confidence` and `evidence` list (`kit_number`, `team_colour`, `continuity`, `lineup_prior`, `human`, `face_local`). The ball carries `speed_kmh`.

Tracks are the only high-volume type. They live in `tracks.jsonl` and are sampled at a configurable rate; everything else is event-driven.

### `appearance` — a player is in frame during a segment

A contiguous run of visibility for one player in one segment, with `on_ball` (any possession overlap) and `prominence` (0–1, how big and central). Appearances are what make the replay/highlight half of the clip rule cheap: the intelligence layer never touches tracks to answer "was the player in that replay?"

### `possession` — one player has the ball

`t`/`t_end`, `player_id`, `team_id`, `gained_by`, `lost_by`, `touches`, `pitch`/`pitch_end`, `under_pressure`. Possessions are the unit the clip rule cuts on for main-view footage.

### `event` — the football vocabulary

`event_type` (controlled list below), `player_id`, `team_id`, `related_player_id` (recipient, defender beaten, fouled player, assist provider), `possession_id`, `segment_id`, `pitch`/`pitch_end`, `outcome` (`success`, `fail`, `neutral`), `body_part`, `under_pressure`, `qualifiers` (free tags, snake_case), and `metrics`.

`event_type` values: `touch`, `pass`, `cross`, `carry`, `dribble`, `take_on`, `nutmeg`, `skill_move`, `shot`, `goal`, `assist`, `save`, `block`, `header`, `aerial_duel` (0.2.0), `tackle`, `interception`, `clearance`, `recovery`, `pressure`, `foul`, `foul_won`, `offside`, `card_yellow`, `card_red`, `substitution`, `kick_off`, `throw_in`, `corner`, `free_kick`, `goal_kick`, `penalty`, `possession_change`, `period_start`, `period_end`, `injury_stoppage`, `var_review`.

**From footage (`source: vision`).** The vision layer's `events_vision` agent (`regista.vision.events`) writes a subset: `pass` and `cross` (success, or fail with an `interception` by the opponent), `shot` (with `qualifiers` `goal`, `saved`, `off_target` or `unknown`), `save`, `goal`, `tackle`, `carry` (with `t_end` and `metrics.carry_distance_m`), and `take_on` (a `nutmeg` record beside it, and the `nutmeg` qualifier on the take-on, when the ball went through the defender). `confidence` is the classifier's probability. Clocks are omitted; `pitch` is the ball or player position the vision layer measured. A nutmeg in footage is defined by geometry: the ball passes through the defender's position while the carrier goes round him.

**Identity answers (`annotation`, from `regista.vision.review`).** `target_type` `track` with `correction` `{"player_id": <id or null>, "answer": <id, not_a_player, or unknown>}`, or `target_type` `appearance` with `correction` `{"players": [...]}` for a replay; `verdict` is `confirm`, `correct`, or `reject`; `context` holds the question id, the question, the identity agent's call, its confidence, and the candidates shown. Simulated answers used for measurement carry `source: synthetic` and `simulates: human`.

**How the generator stages one-on-ones.** The generator records each take-on the way a camera would see it: the defender stands goal-side in the carrier's path; for a nutmeg the ball goes straight through him while the carrier goes round; for a plain take-on carrier and ball go round together; a failed take-on has him step across 1 m in front. This changes only the recorded `track` positions around those moments, never the events, possessions, or any random draw (a test pins the committed sample).

`metrics` keys: `pass_distance_m`, `pass_difficulty` (0–1), `shot_distance_m`, `shot_speed_kmh`, `ball_speed_kmh`, `xg`, `sprint_speed_kmh`, `carry_distance_m`.

The hackathon brief names passes, shots, tackles, possession changes, pressure events, and match metadata. All are first-class here.

### `annotation` — the human-in-the-loop record

A person's feedback on any record: `target_id`, `target_type`, `verdict` (`confirm`, `reject`, `correct`), `correction` (partial fields to overwrite), `note`, `annotator`, `annotated_at`, and, since 0.1.1, `context`. Annotations are appended, never applied in place, so a training loop can replay them and the audit trail survives.

`context` (optional, added in 0.1.1) is a snapshot of what the reviewer saw: `match_id`, `clip_id`, `player_id`, `reason`, `duration_s`, `tags`, `title`, `model`, `watchability`, `prior_watchability`. It lets `regista.feedback` retrain the watchability model from verdicts alone, without regenerating the match.

Real annotations have `source: human`. They are written by `regista.feedback.record_verdict` when someone answers a review: the viewer's Keep/Drop buttons, the `--review` terminal prompt of `python3 -m regista.agents`, or the API (`POST /api/matches/{id}/review`, `POST /api/matches/{id}/clips/{clip_id}/verdict`). A verdict on a clip targets its `label`; keep is `confirm`, drop is `reject`, and a corrected score or tags is `correct`, with `correction.keep` and any corrected `watchability` or `tags`. Real verdicts are stored in `data/feedback/annotations.jsonl` (or `$REGISTA_FEEDBACK_DIR`), and the API service also keeps them in Cosmos DB. **The generator emits placeholders** with `source: synthetic` and `simulates: human` so consumers can see the shape; no person has reviewed synthetic data, and placeholders are never used for training.

### `physical` — a player's motion in one match (0.2.0, league mode only)

One per player who played, written by the generator in league mode after the match's other records (they close the
stream). The generator moves all 22 players on the pitch every 0.1 s (10 Hz), each within his own `top_speed_kmh` and
`acceleration_ms2` and tiring with his `stamina`; this record meters that motion exactly (synthetic: no tracking noise,
no smoothing). Fields: `t`/`t_end` (his spell), `player_id`, `team_id`, `played_s` (seconds on the pitch while the clock
ran, the same as `regista.season.playing_time`), `metrics`, `periods` (per period: `played_s`, `distance_m`,
`hi_distance_m`) and `method` (sample rate and thresholds).

| `metrics` key | Definition (source: `docs/scout-terminal/industry-metrics.md`) |
|---|---|
| `distance_m` | distance covered (#165) |
| `zone1_m` … `zone5_m` | FIFA speed zones: 0-6.9, 7.0-14.9, 15.0-19.9, 20.0-24.9, ≥ 25.0 km/h (#167, FIFA-PHYS) |
| `hi_distance_m` | high intensity, ≥ 20 km/h (zones 4 + 5) (#171) |
| `sprint_distance_m` | ≥ 25 km/h (zone 5) (#172) |
| `walking_s`, `jogging_s` | seconds below 6 km/h and at 6-15 km/h (The Analyst's bands, #168) |
| `hi_efforts`, `sprints` | runs at ≥ 20 / ≥ 25 km/h lasting at least 1 s (Wyscout, #171-172) |
| `peak_speed_kmh` | top speed in the match (#174) |
| `accelerations_medium`, `accelerations_high` | accelerations above 1.5 m/s² held for at least 1 s, peaking below / at or above 3 m/s² (#176, our reading of Wyscout's rule) |
| `decelerations_medium`, `decelerations_high` | the same for braking (#177) |
| `relocated_m` | not a football metric: position jumps the simulator made without motion (a keeper's dive to the ball, the last metres to a set-piece spot, the reset after a goal); never counted in any distance |

`regista.synth.physical.DEFINITIONS` holds the same definitions for anything that shows these numbers. The record says
`peak_speed_kmh`, never `top_speed_kmh`: that name belongs to the hidden rating, which is never served.

## Record types (intelligence layer → `regista-clips.schema.json`)

### `clip`

A time range for one player: `t`/`t_end`, `segment_ids`, `reason`, `event_ids`, `keyframe_t`, `pre_roll_s`/`post_roll_s`.

**The clip rule** (from `CLAUDE.md` §2.3 step 4), implemented in `regista.clips.derive_clips`:

1. `on_ball_main`: every possession by the player inside a `main` segment, padded by pre/post roll and clamped to that segment. Overlapping clips merge.
2. `replay_appearance`, `highlight_appearance`, `closeup_appearance`: every appearance by the player in a non-main segment, on or off the ball.
3. Main-view, off-the-ball appearances produce **no clip**. Otherwise the output would be the whole game.

### `label`

One per clip: `tags` (snake_case; event types and qualifiers plus the clip reason), `title`, `summary`, `explanation` (why it scored what it scored, in plain English), `watchability` (0–1), `language`, `model`. The chatbot searches over labels; the explanation is what makes a result defensible on air.

Added in 0.1.1, both optional:

| Field | Meaning |
|---|---|
| `prior_watchability` | The `rules-v0` score. When another scorer set `watchability` (the watchability model learned from human verdicts, or a Foundry model), the rules score is kept here; when rules-v0 alone scored the clip, the two are equal. |
| `review` | Why the Label agent wants a human to look at this clip, when it does: the prior and the model disagree by 0.30 or more, or `watchability` sits on the keep/drop boundary (0.40–0.60). Absent when the clip is not flagged. The workflow's review step pauses on these clips (`regista.feedback.needs_review`). |

### League mode (schema 0.2.0): what the generator emits when players have ratings

When both squads carry hidden ratings (`regista.season.league.generate_kwargs`, the Regista League's fixtures), the
generator runs in **league mode** (`regista.synth.generator`, generator version 0.7.1 (`LEAGUE_GENERATOR_VERSION`),
profile `league`; the stream is stamped schema 0.2.0). Since 0.7.1 league mode takes exp, log, sin, cos, hypot and its
Gaussians from `regista.detmath` instead of the platform's libm, so a league match is the same, bit for bit, on macOS and
on Linux (where the live app builds it; `regista.season.pins`, docs/scout-terminal/build/determinism.md). Outcomes then depend on the players involved, and these appear:

| Event | Fields | When |
|---|---|---|
| `substitution` | `player_id` the player coming **off**, `related_player_id` the player coming **on**, `team_id`, `pitch` where the player going off stood | 2-5 per team (mean 3.9, the Premier League's 2023-24 rate), at the first stoppage after a time drawn from 58-95% of the match (about the hour mark onward). Who comes off is weighted toward low stamina; a bench player of the same role, else the same line, comes on and takes his place in the shape. Keepers are not substituted. Not a moment: the clip rule never uses it |
| `penalty` | the taker (his team's best finisher on the pitch), `pitch` the spot, 11 m out | a foul whose victim is inside the box he attacks; the `foul` carries the qualifier `penalty_conceded` and the `foul_won` `penalty_won`. The kick is the next `shot`, in the taker's possession, with the qualifier `penalty` and `metrics.xg` 0.79 (FBref/Opta's penalty xG). Most contact in the box is not given: the defender wins the ball cleanly (a `tackle`) instead |
| `aerial_duel` | winner in `player_id` and `team_id`, loser in `related_player_id`, `pitch` where the ball came down, `outcome` success; qualifier `cross`, `long_ball` or `goal_kick` | a high ball a defender can reach: a cross (it comes down in the box, 6-14 m from the goal line; a defender within 16 m can come across, and 45% of crosses are contested in the air), a **forward** long ball (over 30 m and over 10 m forward, a launched keeper pass or a long goal kick included; a defender within 8.5 m; 60% of them are contested, 95% before generator 0.5.0), and a long ball that does **not** arrive (still contested 95% of the time when the target is near it). Balls played back or across stay low. The defender is picked among those in reach by role, centre-backs first (`LEAGUE["aerial_role"]`), then by `aerial` rating. One record per contest: aerial duels won are records where the player is `player_id`, lost where he is `related_player_id` (Opta and FBref count both sides). Height and `aerial` rating decide it, with an edge to the defender, larger on a cross. A cross won by the attacker counts as completed (Opta's rule) |
| `card_red` | the player sent off; qualifier `second_yellow` (after a second `card_yellow`) or `straight_red` | rare. The player leaves and his team plays on with ten. Keepers are not sent off (no substitute keeper is modelled) |
| `offside` | the attacker flagged, `related_player_id` the passer, `pitch` where his run started | a mistimed run on a through ball, or a forward pass to the furthest man forward. The pass is `fail` with the qualifier `offside`; the possession ends with `lost_by: offside`; an indirect `free_kick` (qualifier `indirect`) restarts for the defending side |

Also in league mode:

- **Through balls** are real: a forward pass to a runner in the attacking half is sometimes played into the space 6-12 m
  ahead of him (more often by passers with vision), qualifier `through_ball`. Before 0.2.0 the qualifier was coded but
  its condition never held.
- **Key passes count every shot.** The completed pass that started the shooter's possession is tagged `key_pass` for
  any shot (goal, saved, blocked or off target), not only goals and saves; a goal makes it the `assist`. Penalties have
  no key pass.
- **Body part** follows `preferred_foot`: 82% of passes and 80% of shots with the strong foot (95% for penalties),
  50/50 for two-footed players.
- **Saves** carry the qualifier `held` (the keeper keeps it) or `parried` (it runs loose for a rebound).
- **Goal kicks** are hit long half the time (qualifier `goal_kick` on the pass) to one of the three players furthest
  forward. **Keepers also launch long in open play** (0.5.0): about a third of their open-play passes go to the front
  three, less often for a better distributor and on a side of good passers (team style `keep`), so about 47% of keepers'
  passes travel 32 m or more, the Premier League's share (Opta Analyst).
- **Shot outcomes** (0.5.0): a shot that is not a goal is saved 25% of the time (a little more for good finishers), and
  of the rest 40% are blocked; so about 43% of unblocked shots are on target and keepers save about 70% (six seasons, 0.7.1),
  inside the Premier League's bands (`regista.synth.report`). Before 0.5.0, 60% of unblocked shots were on target.
- **Take-ons** succeed about 37% of the time (six seasons, 0.7.1) (the Premier League's 36.7%, Opta Analyst 2025/26); a failed take-on is a
  tackle, a foul, or (0.5.0) the ball running loose to whoever else is nearest.
- **Touch records** (0.5.0): one for every full 1.92 s of a spell on the ball, and at least one (`touch_every_s`; 1.82 in
  0.5.0, 1.89 in 0.6.0, one per 0.8 s before 0.5.0, about twice FBref's count). Spells last 1-4 s, so that averages one
  record per 2.3 s on the ball, about 560 per team per 90 in the committed season (`regista.season.metrics.TOUCH_RECORDS`
  states it for the terminal, from these parameters). The interval also reshuffles every random draw of a season; 0.7.0
  picked 1.92 from a scan of 1.80-2.00 so that the committed season has the star as its outright top scorer and every
  band one season can judge in (penalties and the individual leaders are judged over six pooled seasons), and six
  pooled seasons pass every band and role shape (both still true of 0.7.1's season).
- **xG** is still distance-based (`e^(-0.12·d)`, 0.02-0.85, as in 0.4.0-0.5.0; `0.95·e^(-0.12·d)` in 0.6.0, `1.1·e^(-0.12·d)` before),
  with headers at 0.40 and first-time shots from a cross at 0.45 of a shot from the same spot.
- **Roles shape the game** (0.6.0). Before, a pass looked for a teammate about 16 m away, tilted forward, and whoever
  was nearest the ball won it, so strikers passed and touched the ball more than anyone, full-backs hardly crossed,
  pressing strikers won as many tackles as holding midfielders, and wingers and strikers were fouled least. Now:
  - **who receives** is weighted by role (`receive_role`): in his own 60% a passer looks for centre-backs, the holding
    midfielder and full-backs, and for good passers (`receive_passing`); further forward (`receive_role_attack`) the
    ball is also recycled back through midfield;
  - **what the holder does** depends on his role (`pass_role`, `take_on_role`): forwards pass less and shoot, take
    players on and lose the ball more; centre-backs rarely take a man on;
  - **who wins the ball**: the nearest opponent presses, but the tackle (or the challenge on a take-on) goes to one of
    the opponents within 10 m by role (`tackle_role`: defenders and midfielders, rarely strikers), who closes the last
    metres; forwards pressing win it less often (`lose_role`);
  - **fouls**: a forward's challenge is more often a foul (`foul_role`), and forwards and wingers on the ball are fouled
    most (`fouled_role`);
  - **crosses** (0.7.0, review closing round 2): a wide player (more than 18 m from the middle) within 40 m of the
    opponent's goal line (a full-back, on the overlap), 39 m (a winger) or 35 m (anyone else) decides to cross first,
    then aims into the box at a teammate attacking it: an outfielder within 34 m of the goal line, by role (`cross_role`:
    wingers and the 10 at the back post and the edge of the box as well as the striker), nearness to where the ball comes
    down and finishing. With nobody there he plays an ordinary pass. A corner is **not** always a cross: the taker picks
    his first action like any holder, and only when he passes from the flag (where the crossing roll is skipped) and
    someone is attacking the box does it become a cross. In the committed season (generator 0.7.1) the first event after
    a corner, skipping touches and pressure, is the taker's cross 70 times in 115, a carry 18, a pass 8, a take-on 8, a
    shot 1, a throw-in 5 and the period's end 5: nobody attacks the box at 45 corners (an open finding of review closing
    round 3, CLAUDE.md §4.2). In 0.6.0
    the target was picked first (in build-up, mostly centre-backs) and any wide pass a full-back made more than 42 m from
    his **own** goal line became a cross into the box: half of full-backs' crosses were 50 m balls from their own half,
    and centre-backs a median 60 m away "received" crosses;
  - **the back line in possession** (0.7.0): centre-backs step up 12 m and full-backs push on 24 m beyond the team's
    shift (`push_role`), full-backs and wingers hold the width (`width_pull`), full-backs get more of the ball and wingers
    and strikers less, centre-backs hit some balls long to the front three (`long_ball_role`), and strikers and wide men
    carry into space less often (`carry_role`).
  Each order is checked by `regista.synth.report.ROLE_SHAPES` (pass/fail, each with its source): over six pooled
  seasons, per 90, passes CB 46 and DM 53 against ST 32; touches CB 54 and DM 65 against ST 47, FB 57 against W 47;
  crosses FB 3.4 against W 7.7, full-backs' open-play crosses starting a median 35 m from the opponent's goal line
  (wingers' 30 m); progressive passes CB 2.1 and FB 3.3 against ST 1.4; long passes CB 4.0 against ST 2.6; tackles won ST
  0.8 against FB 1.8, CB 2.0, DM 3.8; fouls won W 1.4 and ST 1.4 against CB 0.6. Strikers, wingers and the 10 receive
  95% of completed open-play crosses (strikers 56%), a diagnostic the report prints with where crosses start by role. The
  star's edge in chances is softened (`shot_drive` 0.19, `find_finisher` 0.13, `cross_finisher` 0.10): over six seasons
  his npxG per 90 is 1.7 times the next player's and he takes 39% of his club's npxG, both banded. Still off and labelled
  so in the terminal: centre-backs make about 2 progressive passes per 90 (a reviewer put Premier League regulars at
  3-6, unsourced) and almost no progressive carries.

**How ratings move outcomes.** A rating enters as a skill `z = (rating - centre) / 7`, where the centre is the rating of
the average league player who performs that action (`SKILL_CENTRE`, measured over league seasons: finishing 66, passing
68, defending 62, ...), added in log-odds with a weight in `LEAGUE`. So league-wide rates stay where the profile was tuned, and xG
stays the quality of the chance while finishing decides who beats it: goals minus xG is a real finishing signal.

| Outcome | Ratings involved |
|---|---|
| pass completion | passer's `passing` (and `vision` on a through ball), against the `defending` of the defender nearest where the ball comes down, and of the marker when under pressure |
| chance creation | `vision`: forward runners are picked more often, forward balls into the final third lead the receiver into space, through balls are tried more; in build-up teammates look for good `passing` (0.6.0), in the final third for good `finishing` |
| who shoots, from where (0.4.0) | each role has its own shot propensity in three distance bands (`LEAGUE["shot_role"]`: strikers from close in, midfielders and defenders from further out), and `finishing` pulls a player's shots closer in (`shot_drive`) |
| shot outcome | `finishing` (`aerial` for headers), strong or weak foot, against the keeper's `shot_stopping`; finishers hit the target a little more |
| team style (0.4.0) | `TEAM_STYLE` from each starting XI's ratings: `keep` (passing and vision) completes more passes and loses the ball less; `press` (defending and stamina) dispossesses more in the opponents' own 60% |
| keepers in build-up (0.4.0, 0.5.0) | a defender in his own half plays it back to the keeper more often (`gk_target`); the keeper launches long less with better `distribution` and on a side with more `keep` |
| save held or parried | keeper's `handling` |
| take-ons | `dribbling` against the defender's `defending`; good dribblers try more, and nutmeg and skill more |
| tackles, interceptions, fouls | `defending`: winning the ball from a carrier (since 0.6.0 the tackler is one of the opponents within 10 m, by role), reading a loose pass (the better of the two nearest defenders tends to get there), fouling less |
| aerial duels | `aerial` and height (per 10 cm), against the opponent's |
| who comes off | `stamina` |

**Motion (generator 0.3.0).** Every player on the pitch moves every 0.1 s within his own top speed (`top_speed_kmh`) and
acceleration (`acceleration_ms2`: full acceleration up to two thirds of top speed, tapering to nothing at it; unhurried
moves speed up gently). Off the ball he follows his shape position (which follows where the ball has been over the last
1.5 s), walking when near it and running when far; the nearest defender closes the holder down; attackers make runs
toward goal and the defender nearest the space follows them; after a turnover the side that lost the ball recovers;
receivers and chasers run to where the ball will be; at a dead ball everyone walks back and the set-piece taker walks to
the spot. Repeated sprints drain a reserve that slow running refills, and willingness and top speed fade over the match,
less for players with `stamina`. The ball stays at the carrier's feet. Each player's motion is summarised in a
`physical` record (above). Tracks are still sampled at `track_hz` from the same positions, for the renderer and the
vision layer.

**Clips and profiles.** Substitutions are not moments. An aerial duel tags the winner's clip `aerial_duel` when it falls
inside one. A penalty's taker gets the `penalty` set piece and the `penalty` shot in one possession clip. Profiles count
time on the pitch (`regista.season.playing_time`: substitutions and red cards cut a spell), credit substitutes with an
appearance, and add aerial duels won and lost (aerial win %), through balls, offsides, penalties won and penalty goals.

## League players: bio and hidden ratings

Added 2026-10-23 (attributes version 1). Every player in the Regista League (`data/season/league.json`, 6 clubs x 18) has
a public **bio** and hidden **ratings**. All of it is synthetic: invented people, no real player's name or biography.
`regista.season.league.assign_attributes` draws them from their own seeded stream (`random.Random(league seed + 1000003)`,
recorded under `attributes.seed` at the top of the file), so names and fixtures are the same as before attributes were
added, and `python -m regista.season new` writes the same file again.

**Role.** Each squad entry has `role`, the 4-3-3 slot behind its kit number (the formation never changes): `GK` 1, 13 ·
`FB` full-back 2, 3, 22 · `CB` centre-back 4, 5, 15 · `DM` holding midfielder 6, 16 · `CM` central midfielder 8, 14 ·
`AM` attacking midfielder 10 · `W` winger 7, 11, 17 · `ST` striker 9, 20 (`regista.season.league.ROLE_OF_KIT`).

**Bio (public: the API and pages show it).**

| Field | Scale |
|---|---|
| `date_of_birth` | ISO date. Age at season start (1 August 2026, FBref's convention for an August-May league) is 17-35; keepers and centre-backs a little older on average. The API shows `age` computed from it (`regista.season.league.age_on`) |
| `height_cm` | whole centimetres, 163-201; mean by role GK 190, CB 188, ST 183, DM 182, CM 179, FB 178, AM 176, W 175 (chosen to look plausible, not calibrated to a published source) |
| `preferred_foot` | `right`, `left` or `both`; about 75 / 20 / 5% overall, left-backs (3) and left wingers (11) more often left-footed |
| `nationality` | country name, a Premier League-like spread (about a quarter to a third English, then France, Spain, Brazil, Portugal, the Netherlands and others); weights in `NATIONALITIES` |

**Ratings (hidden: they drive the generator and are never served).** Under `attributes` on each squad entry. Scouts must
judge players from what they do, so `regista.season.league.people()` drops `attributes`, and no API, MCP tool or page
returns them (tests/test_attributes.py checks every public player endpoint and the player tools). They are readable in
this repository's league file, which is what makes the league regenerate exactly.

| Field | Who | Scale |
|---|---|---|
| `finishing`, `passing`, `vision` (chance creation), `dribbling`, `defending` (tackling and positioning), `aerial`, `stamina` | everyone | integer 1-99. Absolute across the league: a striker's finishing is about 75 on average, a centre-back's about 35 |
| `shot_stopping`, `handling`, `distribution` | goalkeepers only | integer 1-99 |
| `top_speed_kmh` | everyone | km/h, one decimal. Outfielders 29.4-37.4, goalkeepers 23.6-32.7: the Premier League 2024-25 range (slowest outfielder 29.4, fastest just over 37; keepers 23.6 to 32.7; Opta via The Analyst, `OA-PHYS` in docs/scout-terminal/industry-metrics.md) |
| `acceleration_ms2` | everyone | peak acceleration in m/s², two decimals. Outfielders 3.0-5.2, keepers 2.6-4.2; anchored on Wyscout's "high acceleration" threshold of 3 m/s² (industry-metrics row 176); the spread is our choice |

How they are drawn: each role has a mean per rating (`ROLE_MEANS`: centre-backs defend and win headers, wingers dribble
and are fastest, holding midfielders defend and pass, strikers finish, attacking midfielders see passes). A player's
rating is the role mean plus a spread of 7 points (SD), part shared quality (starters a little above the bench) and part
the rating's own draw; aerial follows height, stamina and top speed fade after 30. Drawn ratings stop at 95. Then one
standout per pair in `STANDOUTS` (the best starting keeper at shot stopping, centre-back at aerial and at defending,
full-back at stamina, holding midfielder at defending, central midfielder at passing, attacking midfielder at vision,
winger at dribbling, striker at aerial) is lifted 10 clear of the next best starter (at most 97), and **Femi Toure
(`pl_bro_09`) is the best finisher among forwards** (93; the next best forward has 85), decided by Zaid. No match is
rigged: what a rating does is the generator's business, and it applies to every player the same way.

**For the generator.** `regista.season.league.generate_kwargs` passes each squad entry's `attributes`, `role`,
`height_cm` and `preferred_foot`, which puts the generator in league mode (above). Matches generated without ratings
(every committed sample, the vision seeds, the demo and realistic profiles, the Player view's filmed friendlies, which
call `generate_kwargs(..., ratings=False)`) stay byte-identical: tests/test_backcompat.py pins their hashes from `main`.

## Azure mapping

What runs today (see `docs/architecture.md`): with `--cloud`, and on uploads to the live app, the Persist agent upserts `match`, `clip`, and `label` records into Cosmos DB (database `regista`, containers `matches`, `clips`, `labels`, partition `match_id`), and the indexer role writes every labelled clip into the Azure AI Search index `regista-clips`. The API service keeps human `annotation` records and the learned watchability model in the Cosmos DB container `annotations`. The rest of the event stream (`camera_segment`, `possession`, `event`, `appearance`, `track`) is not stored in Azure.

Planned, not implemented:

| Record | Where it would land |
|---|---|
| `camera_segment`, `possession`, `event`, `appearance`, `annotation` | Event Hubs → Fabric Eventstream → Lakehouse table per type; also Cosmos DB (partition `match_id`) for the chatbot's low-latency lookups |
| `track` | Blob Storage as JSONL/Parquet, loaded to Fabric on demand |
