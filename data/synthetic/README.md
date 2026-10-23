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
| Versioning | `schema_version` is semver; the current version is **0.1.1** (`regista.schema.SCHEMA_VERSION`). Additive fields bump the patch. Renames and enum changes bump the minor and must update both schemas, the generator, and `tests/`. |

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

`event_type` values: `touch`, `pass`, `cross`, `carry`, `dribble`, `take_on`, `nutmeg`, `skill_move`, `shot`, `goal`, `assist`, `save`, `block`, `header`, `tackle`, `interception`, `clearance`, `recovery`, `pressure`, `foul`, `foul_won`, `offside`, `card_yellow`, `card_red`, `substitution`, `kick_off`, `throw_in`, `corner`, `free_kick`, `goal_kick`, `penalty`, `possession_change`, `period_start`, `period_end`, `injury_stoppage`, `var_review`.

**From footage (`source: vision`).** The vision layer's `events_vision` agent (`regista.vision.events`) writes a subset: `pass` and `cross` (success, or fail with an `interception` by the opponent), `shot` (with `qualifiers` `goal`, `saved`, `off_target` or `unknown`), `save`, `goal`, `tackle`, `carry` (with `t_end` and `metrics.carry_distance_m`), and `take_on` (a `nutmeg` record beside it, and the `nutmeg` qualifier on the take-on, when the ball went through the defender). `confidence` is the classifier's probability. Clocks are omitted; `pitch` is the ball or player position the vision layer measured. A nutmeg in footage is defined by geometry: the ball passes through the defender's position while the carrier goes round him.

**Identity answers (`annotation`, from `regista.vision.review`).** `target_type` `track` with `correction` `{"player_id": <id or null>, "answer": <id, not_a_player, or unknown>}`, or `target_type` `appearance` with `correction` `{"players": [...]}` for a replay; `verdict` is `confirm`, `correct`, or `reject`; `context` holds the question id, the question, the identity agent's call, its confidence, and the candidates shown. Simulated answers used for measurement carry `source: synthetic` and `simulates: human`.

**How the generator stages one-on-ones.** The generator records each take-on the way a camera would see it: the defender stands goal-side in the carrier's path; for a nutmeg the ball goes straight through him while the carrier goes round; for a plain take-on carrier and ball go round together; a failed take-on has him step across 1 m in front. This changes only the recorded `track` positions around those moments, never the events, possessions, or any random draw (a test pins the committed sample).

`metrics` keys: `pass_distance_m`, `pass_difficulty` (0–1), `shot_distance_m`, `shot_speed_kmh`, `ball_speed_kmh`, `xg`, `sprint_speed_kmh`, `carry_distance_m`.

The hackathon brief names passes, shots, tackles, possession changes, pressure events, and match metadata. All are first-class here.

### `annotation` — the human-in-the-loop record

A person's feedback on any record: `target_id`, `target_type`, `verdict` (`confirm`, `reject`, `correct`), `correction` (partial fields to overwrite), `note`, `annotator`, `annotated_at`, and, since 0.1.1, `context`. Annotations are appended, never applied in place, so a training loop can replay them and the audit trail survives.

`context` (optional, added in 0.1.1) is a snapshot of what the reviewer saw: `match_id`, `clip_id`, `player_id`, `reason`, `duration_s`, `tags`, `title`, `model`, `watchability`, `prior_watchability`. It lets `regista.feedback` retrain the watchability model from verdicts alone, without regenerating the match.

Real annotations have `source: human`. They are written by `regista.feedback.record_verdict` when someone answers a review: the viewer's Keep/Drop buttons, the `--review` terminal prompt of `python3 -m regista.agents`, or the API (`POST /api/matches/{id}/review`, `POST /api/matches/{id}/clips/{clip_id}/verdict`). A verdict on a clip targets its `label`; keep is `confirm`, drop is `reject`, and a corrected score or tags is `correct`, with `correction.keep` and any corrected `watchability` or `tags`. Real verdicts are stored in `data/feedback/annotations.jsonl` (or `$REGISTA_FEEDBACK_DIR`), and the API service also keeps them in Cosmos DB. **The generator emits placeholders** with `source: synthetic` and `simulates: human` so consumers can see the shape; no person has reviewed synthetic data, and placeholders are never used for training.

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

**For the generator.** `regista.season.league.player_attributes(league)` gives `{global_id: ratings}`; the role is on
each squad entry. Matches generated without ratings (every committed sample, the vision seeds, the demo and realistic
profiles) must stay byte-identical: tests/test_backcompat.py pins their hashes from `main`.

## Azure mapping

What runs today (see `docs/architecture.md`): with `--cloud`, and on uploads to the live app, the Persist agent upserts `match`, `clip`, and `label` records into Cosmos DB (database `regista`, containers `matches`, `clips`, `labels`, partition `match_id`), and the indexer role writes every labelled clip into the Azure AI Search index `regista-clips`. The API service keeps human `annotation` records and the learned watchability model in the Cosmos DB container `annotations`. The rest of the event stream (`camera_segment`, `possession`, `event`, `appearance`, `track`) is not stored in Azure.

Planned, not implemented:

| Record | Where it would land |
|---|---|
| `camera_segment`, `possession`, `event`, `appearance`, `annotation` | Event Hubs → Fabric Eventstream → Lakehouse table per type; also Cosmos DB (partition `match_id`) for the chatbot's low-latency lookups |
| `track` | Blob Storage as JSONL/Parquet, loaded to Fabric on demand |
