# The catalogue UI port: the backend (B1-B15, B17)

Branch `ux/catalogue` (on top of PR #39, `feature/catalogue`; not merged, not pushed). Written 2026-10-26 by the backend
builder, following `port-map.md` §3. Everything here is additive: no existing endpoint changed its shape or its
defaults, `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched and green, England semi-pro
men is byte-identical (`league.json`, the season pins) and every catalogue pin holds. Nothing reached Azure or the live
app; no Fabric job ran.

**Zaid's port decisions, as built.** The engine's minutes are untouched (no change to `match_minute`, `clock_at` or
clip titles; evidence carries the engine's `minute`). The noisy marks stay (`noisy` on every cell; Femi Toure's
non-penalty goals are still noisy). Catalogue pages count England's league fixtures only: Femi Toure has 5 goals in 10
matches over 274.3 minutes there, and his Player-view friendly is named (`not_counted`), never counted. The Foundry
Scout agent holds the catalogue tools. Player-view uploads may come from catalogue clubs. One ranking rule, the
engine's; "none yet" for zeros; pool lines in words; Round, never matchday.

Commits: `fa0a5d5` (B1), `2e21827` (B2-B12, B15), `e655867` (B14), `d64bc5f` (B17), the answers' manifest fix
(found by the B15 run), then this report.

## Every new or changed endpoint and field

"New" means a field or parameter that did not exist; nothing was renamed or removed except where marked *changed*
(only inside PR #39's own endpoints, which no snapshot covers).

### `GET /api/catalogue`

| Field | What |
|---|---|
| `clubs[]` | new: all 66 clubs, `{club_id, name, short_name, competition_id, kit}` (the Terminal's team picker) |
| `count_metrics[]` | new: the 70 metric keys that read "none yet" at 0 (B5) |
| `none_yet_rule` | new: the rule in one paragraph |
| `noisy_words` | new: what ≈ means, in plain words (B7) |
| `levels.pools[]` | new keys `key` ("semi_pro/senior/men"), `words` ("semi-pro men"), `label` ("Semi-pro, senior, men") |

`as_of` and `as_of_note` were already there. The committed `catalogue.json` keeps its plain `levels` shape (the words
are added by the API only, `levels_public(words=True)`).

### `GET /api/competitions`

`levels.pools[]` gains `key`, `words`, `label`. `tier` (and its alias `level`) takes a comma list:
`tier=amateur,college,academy`; one value is still valid; an unknown value in the list is a 422.

### `GET /api/competitions/{id}`

| Field | What |
|---|---|
| `clubs[].uploaded_matches` | new: the club's uploaded matches in this competition |
| `clubs[].squad[].appearances`, `minutes`, `played`, `qualified` | new: playing time in this competition's matches (England: the league fixtures) |
| `sample.words` | new: the sample in plain words, e.g. "Only uploaded matches count here: 8 so far, 1 to 3 for each club, of about 30 minutes. A regular's season here is about 87 minutes; a percentile needs 45 minutes. Per 90s rest on the 8 uploaded matches." England: "Every league match is uploaded: 30 matches, 10 for each club, …" |
| `player_uploads[]` | new: finished Player-view uploads of this competition's clubs (England's: the league friendlies too), named and never counted: `{upload_id, match_id, competition_id, global_id, name, club_id, club, opponent_club_id, opponent, side, date, camera, uploader {type, global_id, name}, title, source: "upload", kind: "friendly"\|"match", clip_view, counted: false, note}`, newest first |
| `player_uploads_note`, `noisy_words` | new |
| `matches[].title` | *changed*: "Round N: Home h–a Away" (B1) |

### `GET /api/catalogue/players` (and `GET /api/competitions/{id}/players`)

New parameters on `/api/catalogue/players`:
- `min_percentile` (0-100): keeps rows whose percentile in their own pool (`scope`) is at least it; none yet never
  qualifies. Only with a metric sort.
- `sort=minutes`: minutes played, most first (`order=asc` fewest), one board per level, `rank_by: "value"`.
- `sort=name`: alphabetical (`order=desc` reverses), one list, no boards, `rank_by: "name"`.
- `tier` comma lists (as everywhere).

New response fields: `with_any`, `none_yet` (the sorted count: rows with any / with none; null when the sort is not a
count), `samples` (`{competition_id: sample with words}`), `min_percentile`, `none_yet_rule`, `noisy_words`.

Each row (card): `profile_url` is now `/players/{gid}` for every catalogue row (*changed*: was null outside England),
new `also_in` (the player's other competition ids). Each cell: new `none_yet` (bool), `zeros` (`{none, of}` when none
yet, else null), `pool.words`. Each board: new `with_any`, `none_yet`.

Ordering: a count at 0 is listed after the ranked rows of its board (B5).

### `GET /api/catalogue/players/{gid}`

New parameter `include=profile`.

| Field | What |
|---|---|
| `rows[].profile` | new with `include=profile` (B3), see below |
| `rows[].also_in` | new |
| `rows[].not_counted[]` | new: this player's matches in this competition the catalogue names and never counts: `{match_id, competition_id, date, opponent, source: "upload"\|"claim", kind, title, camera, clip_view}` |
| `rows[].basis` | new: one sentence, e.g. "These numbers count the Regista League fixtures only (10 matches). Femi Toure's friendly v Calder Town, uploaded through the Player view, is not counted here." |
| `rows[].sample.words` | new |
| `rows[].summary` | *changed*: worded for the competition (B4), plus `engine` ("rules" or "foundry") |
| `not_counted[]` | new: all of the player's named, uncounted matches |
| `basis` | *changed*: always `FIXTURES_BASIS` (was `ENGLAND_BASIS` or null) |
| `profile_url` | *changed*: always `/players/{gid}` |
| `summary_note` | *changed* text |
| England rows' `touch_map`, `summary`, `moments` | *changed*: the league fixtures only (B2) |

`rows[].profile` (B3), in the requested `scope` (level by default):
- `scope`, `appearances`, `minutes`, `qualifying_minutes`, `qualified`, `counts`, `per90`;
- `stats[key]` for every profile stat: `{label, count, per90, percentile, pool (with words), reason, noisy,
  none_yet: {none, of} | null, evidence_total}`;
- `ratios[key]` for pass_accuracy, take_on_success, shot_accuracy, aerial_win: the metrics engine's `pass_pct`,
  `take_on_pct`, `shot_on_target_pct`, `aerial_win_pct`: `{metric, label, unit: "%", value, num, den, percentile, pool,
  reason, noisy, evidence_total}`;
- `evidence[stat]`: `{total, items: [{match_id, clip_id, t, minute, video_url}]}`, at most 10 items, the true total;
- `matches[]`: `{match_id, round, date, opponent, home, score, source, uploader (named), camera, clip_view}`, newest
  first;
- `grid`, `moments` (40, each with `competition_id`), `summary`, `passes_note`, `none_yet_rule`.

Rules inside the profile:
- **Passes and passes completed** are the metrics engine's cells (crosses included, labelled "(crosses included)"), and
  `counts`/`per90` carry the same numbers, so the profile and the Terminal say one number. Every ratio equals its
  `METRIC_OF` metric, value and denominator (tested).
- **Goalkeepers' outfield numbers: the metrics engine decides.** A stat has a percentile for a position only when its
  terminal metric is scored for that position; otherwise none, reason "not ranked for goalkeepers" (or "for
  forwards": a forward's saves). `forward_passes` (no terminal metric) keeps the profile engine's percentile for
  outfield players and none for goalkeepers. Saves, passes, recoveries and touches keep keepers' percentiles.
- **None yet**: a count where more is better at 0, for a position it is ranked for: no percentile, `{none, of}` from
  its pool. Offsides and aerial duels lost are never none yet. A stat not ranked for the position shows its reason
  instead.

### `GET /api/catalogue/rank`

New parameter `min_percentile`; `tier` comma lists. New fields: `with_any`, `none_yet` (over every row of the
selection, ranked or not), `min_percentile`, `none_yet_rule`; boards gain `with_any`, `none_yet`; cells gain
`none_yet`, `zeros`, `pool.words`. A count at 0 has no place and is listed in `unranked` (B5). "Most goals in England":
25 ranked, 116 none yet.

### `GET /api/catalogue/compare`

New: `best` (`{metric: [global_id…]}`), `best_rule` (`{metric: {by: "value"|"percentile"|null, reason}}`) and
`best_rules` (the rule in words). One level: the best value as shown (ties share; lower is better where the metric says
so). Several levels, one position: the best percentile. Several levels and positions: no mark. Never a style marker, a
row without a value or percentile, or none yet (B10).

### `GET /api/catalogue/matches`

`title` *changed* to "Round N: …" (B1). Otherwise unchanged.

### Existing endpoints in catalogue mode (only with a catalogue parameter; defaults untouched)

- `/api/terminal/screen`, `/rank`, `/scatter`: cells gain `none_yet`, `zeros`, `pool.words`; boards gain `with_any`,
  `none_yet`; `season.sample.words` and `season.competitions[].sample.words`; ranking follows none yet.
- `/api/players/{gid}/metrics`, `/form`: cells as above. `/similar` (catalogue mode): rows gain `profile_url` and
  `shared_strengths_words` (plain words: "getting good scoring chances", "actions that lead to a shot"; any other metric
  reads as its label, lower case) (B11). `/heatmap?competition=`: the fixtures-only basis (the grid was already the
  league fixtures' grid).
- `/api/players` (catalogue mode): `profile_url` for every card; boards carry `with_any`/`none_yet` (null: these cards
  rank profile stats); headline pools gain `words`. **Basis unchanged**: England's cards here still come from the
  app's season (PR #39's rule, `ENGLAND_BASIS`), as the port map says.

### `POST /api/scout/ask`

New optional body field `where: "league" | "catalogue"` (default: the league; a missing or `"league"` value gives the
league answer, the `scout_ask_rules` snapshot is unchanged). With `where: "catalogue"` (B14):
- the rules engine reads the place words (`regista.catalogue.place`, a Python port of `terminal-place.js`: country,
  level, age group, gender, competition, "my level", "whole catalogue", "young"), then the stat and position from the
  league parser (stat keys mapped to terminal metrics; no stat: the position's first default column), then calls
  `search_catalogue_players` (or `get_catalogue_player` for a player named in full);
- the answer has the league shape plus `where`, `warning`, `result_total`, `with_any`, `none_yet`; `query.args` are the
  tool's arguments; cards are catalogue rows: `{global_id, name, club, position, competition_id, competition, country,
  tier, age_group, gender, level_words, minutes, appearances, qualified, career, board, stat {key, label, value,
  percentile, noisy, none_yet, zeros, pool (with words)}, small, profile_url, api_url}`;
- the Foundry engine gets a hint that the question is about the catalogue; its catalogue calls are run again here for
  the cards and every number in its reply is checked against them (`checked`).

The league parser learned two phrases: "up front" (forwards) and "create the most chances" (key passes).

### `POST /api/player/uploads` and the upload records (B15)

New multipart fields `competition_id`, `date` (YYYY-MM-DD), `camera` (tripod, phone, drone, broadcast), `consent`
(yes/true/on/1); `max_fields` 8 → 12. With a `competition_id` the date, the camera and `consent=yes` are all required,
the player must be in that competition's squad and the opponent one of its clubs (not the player's own). The date must
be on or after the competition's season start and not in the future. Without a `competition_id` today's league form
works as before (the new fields are optional and checked when given). Every refusal is a plain 422.

`UploadRecord` gains `competition_id` (None: the league's friendly form, as every old record), `camera`, `date_played`,
`uploader_type` ("player"), `consent` (False); old records load with these defaults. `GET /api/player/uploads[/{id}]`
shows the new fields and, for a catalogue upload, `competition: {competition_id, name, country, tier, age_group,
gender}`; `player` and `opponent` are looked up in the upload's competition.

The worker builds the roster from the upload's competition (`roster_for(..., competition_id=, date=)`, always without
ratings) and the manifest adds `competition_id`, `country`, `region`, `tier`, `age_group`, `gender`, `camera`,
`uploader {type, global_id, club_id}`, `counted: false` and the date played; the title stays "<name>'s match: H v A".
`python -m regista.player.film` gains `--competition` and `--date`.

Joining: the upload is named on its competition page (`player_uploads`) and in the player's catalogue rows
(`not_counted`), and counted nowhere: the catalogue counts each competition's own matches; the league's season already
skips upload rows whose global id is not a league player (`Season._add_claimed` keeps only league ids; tested).
`uploaded_matches()` rows carry `competition_id`.

### MCP tools and the Foundry Scout agent

- `search_catalogue_players`: `tier` comma lists; rows gain `profile_url`, `stat.none_yet`, `stat.zeros`,
  `stat.pool.words`; the answer gains `with_any`, `none_yet`, `none_yet_rule`; boards gain the counts; none yet is
  listed after the ranked rows. `list_competitions`: level words. `get_catalogue_player`: cells as above.
- `cloud/foundry.py`: `SCOUT_TOOLS` adds `list_competitions`, `search_catalogue_players`, `get_catalogue_player`
  (public, read-only; never the Cosmos DB tools or `render_clip`, tested); `SCOUT_INSTRUCTIONS` add the catalogue's
  rules (level pools by default, say the pool and its size, warn across levels, never mix men and women, "none yet"
  for a 0 count, noisy means small sample, quote only tool numbers).
- `season_api._scout_foundry`: the MCP child's env adds absolute `REGISTA_CATALOGUE` and `REGISTA_CATALOGUE_ROOT`.

### No new routes

`include=profile` and `where` are parameters on existing routes, so `tests/test_access.py` needs no new row; no new
static file, so `pyproject` and `cloud/smoke.py STATIC_FILES` are unchanged. B16 (one search over every match) was not
built: it waits for the Clip view builder's measurement (port map §2.11).

## Code

| File | What |
|---|---|
| `season/metrics.py` | `COUNT_METRICS` (70 keys; outside `Metric.public()`) |
| `catalogue/metrics.py` | `none_yet`, `zeros`, `pool_words`, `sample_words`, `any_of`, `count_split`, board counts, none yet in `sort` and `percentile`, `PLAIN` + `strength_words`, `NONE_YET_RULE`, `NOISY_WORDS`, cards with `also_in` and `profile_url` |
| `catalogue/profiles.py` | `fixtures_only()` (England on the league fixtures, other seasons shared), `FIXTURES_BASIS`, pool words on `stat_cell` |
| `catalogue/page.py` | new: `profile_row`, `summary_row`, `wording_for` (B3, B4) |
| `catalogue/place.py` | new: the place words (Python port of `terminal-place.js`) |
| `catalogue/scout.py` | new: the Scout agent's rules engine on the catalogue, catalogue cards, Foundry calls run again |
| `catalogue/taxonomy.py` | `level_words`, `level_label`, `POSITION_WORDS`, `levels_public(words=)` |
| `catalogue/tools.py` | tier lists, none yet and words in `search_players` |
| `catalogue/build.py` | Round titles (B1) |
| `catalogue/define.py` | plain career stories (B17) |
| `catalogue_api.py` | every endpoint change above; `catalogue_profiles(basis=)`, `not_counted`, `basis_sentence`, `compare_best` |
| `season/summaries.py` | `Wording`; `summary_for(..., wording=, stored=)`; default text byte-identical |
| `season/scout.py` | catalogue calls in `from_foundry`; two parser phrases |
| `season_api.py` | `where` on `/api/scout/ask`; catalogue env for Foundry |
| `cloud/foundry.py` | `SCOUT_TOOLS`, `SCOUT_INSTRUCTIONS` |
| `player/{store,film,worker}.py`, `player_api.py` | catalogue-club uploads (B15), `player_uploads` |

Tests: `tests/test_catalogue_port.py` (new, 72 tests: every item above, the sandbox's place-word checks on the Python
port, the three sandbox agent questions against the tool, the Foundry stand-in, hidden-key walks of every new payload,
the upload form's refusals, a done catalogue upload named and never counted). PR #39 tests updated where they expected
the old behaviour: zeros ranked (England competition-scope cells now differ only by none yet), `profile_url: null`
outside England, the board key set, the "matchday" titles, the old career stories.

## B17: stories and examples

The two Spanish juveniles' stories now read "17 and still plays for UD Sotoalto's under-19 side; he also plays for CF
Torrevalle, the senior amateur club it is linked to, in the same region" (and Navalcastro / Riuseca at 18), filled in
from the person's age and clubs. `catalogue.json` was regenerated: only those two strings changed, every competition
file is byte-identical, `python -m regista.catalogue define --check` and `check` pass. `docs/catalogue/build/api.md`'s
stale examples were refreshed from the current data (Sergio Cruz now has no non-penalty goal yet in either competition,
a good none-yet example; Edson Jimenez 76.7 + 30.1 minutes; Round titles).

## B15 measurement: one local end-to-end run

Local only, `LocalStore` in a scratch folder, a test token, no Azure, models `models/vision_v4` (the models trained
without captions and name labels, which match the footage format):

1. `film(cl_adire_stars, cl_riverbank, home, seed=4101, minutes=3, competition_id=co_nga_am_men, date=2026-10-17)`:
   Adire Stars FC v Riverbank Warriors FC (Ogun Riverside Amateur League, Nigeria, amateur men), 3.4 minutes of
   640x360, 10 fps footage, rendered in 4 s. These kits (two clubs never seen in training) are the first catalogue
   kits the vision layer has met.
2. `POST /api/player/uploads` through `TestClient` with `competition_id`, `date`, `camera=tripod`, `consent=yes`: 201,
   the record carries the four fields.
3. `python -m regista.player.worker --once --models models/vision_v4`: 60 s (shots 8 s: 7 camera shots; identity
   48 s: 135 of 145 player tracks named from kit numbers; possession 0.6 s; events 0.6 s: 59 events; writer 2 s),
   status `needs_review` with 1 question about the uploader. The manifest names the competition, tier, camera, date,
   uploader and `counted: false`; title "Adebayo Nwosu's match: Adire Stars FC v Riverbank Warriors FC".
4. Clips for the uploader (pl_ads_09, #9) against the film's ground truth (`regista.vision.pipeline.compare_clips`, IoU
   0.5):

   | | true | vision | matched | recall | precision |
   |---|---|---|---|---|---|
   | Before the answer | 5 | 4 | 3 | 0.60 | 0.75 |
   | After the answer | 5 | 5 | 4 | **0.80** | **0.80** |

   On the ball in the main view: recall 0.75 → 1.00, precision 0.75 → 0.80. The one highlight appearance is missed
   both times. The answer ("is this you?" for track tr_20) was simulated from ground truth
   (`regista.vision.review.simulated_answers`: yes) and sent through `POST /answers`, which recomputed the match.
   For scale: the league's fresh matches score clip recall 0.75, precision 0.94 (docs/vision.md, v4); one 3-minute
   match is a single data point, not a measurement of the vision layer on catalogue kits.
5. After the answer: status `done`; the upload is named on `GET /api/competitions/co_nga_am_men` (`player_uploads`)
   and in the player's catalogue row (`not_counted`; basis "… Adebayo Nwosu's match v Riverbank Warriors FC, uploaded
   through the Player view, is not counted here."); his row still counts 2 matches; `GET /api/players/pl_ads_09` is a
   404 (he is not a league player, so the league's season never counts it).

**A bug this run found, fixed:** applying the answers recomputed the match through the vision pipeline, which wrote
its own manifest over the worker's: the title, uploader, competition labels and camera were lost, and the local video
path and `out_dir` were pushed back to the store. League uploads take the same path, so the live demo upload (answered on
2026-10-22) probably lost its title then; that was not checked on the live app (read-only checks only). `player_api._keep_manifest` now restores the worker's manifest
with the recomputed counts and no machine paths; `tests/test_player_api.py` checks it.

## Checks

- `python3 -m pytest -q`: 1052 passed, 15 deselected (Mac, on the final code; 980 before this round).
- `python3 -m pytest -q -m slow`: 15 passed.
- Linux CI was not run here (nothing is pushed). Nothing new passes big inputs on a command line.
- `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py`: untouched, green (the snapshot of every existing
  endpoint without parameters, the three league MCP tools, `league.json`'s hash).
- `python -m regista.catalogue check`: every catalogue match is its pin (after the Round titles rebuilt the 60 folders).
  `python -m regista.catalogue define --check`: the committed catalogue is what the definition writes.
- A local server (`REGISTA_DOTENV= uvicorn regista.api:app --port 8231`, then stopped): `/api/catalogue` 66 clubs and
  70 count metrics; Femi Toure's catalogue profile 10 matches, 274.3 minutes, 5 goals, non-penalty goals at the 98th
  percentile among 33 semi-pro men forwards, noisy; "U19 midfielders in Spain" through the Scout agent: 11 players.
- The port map's numbers: Femi Toure 98th of 33 (level), 97th of 18 (competition), 96th of 123 (all); "most goals in
  England" 25 ranked, 116 none yet; Sergio Cruz 2 and 2 matches (career strip); "U19 midfielders in Spain" 11.
- Hidden-key walks of every new payload (ratings, level scales including `execution`, seeds): none.
- No browser checks: this round changes no page (the UI builders check theirs at 1440 and 375 px).

## Open, for the UI builders and Zaid

1. **None yet on cells is position-blind; on profiles it is not.** A keeper with no goals is "none yet" in a ranking
   cell (so "most goals in England" lists 25 ranked and 116 none yet, keepers included, as the port map counted); the
   profile shows the keeper's goals as "not ranked for goalkeepers" instead. Both follow the engine's flags.
2. **xG, npxG and xA at 0 stay ranked** (not counts). Zaid's call (port map §6.1).
3. **England's stored summaries** are rules-v0, not Foundry, so catalogue rows show the rules summary in the
   competition's wording; a Foundry summary would show only while its numbers hold on the fixtures (§6.3).
4. **`/api/players` in catalogue mode** keeps the app's basis for England (claims and uploads counted), as PR #39
   decided and the map keeps. The catalogue pages read `/api/catalogue/players/{gid}`.
5. **B16** waits for the Clip view's measurement.
6. **Live app after deploy:** catalogue match folders rebuild once for the new titles (the image builds them); the
   upload date check uses the server's date.
7. CLAUDE.md §2.11 and §3.0 (the three new modules) are for the port's landing, as the map says.
