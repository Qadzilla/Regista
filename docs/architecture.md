# Regista architecture

Regista turns a football broadcast into a searchable library of one player's moments. It is built as two layers with one contract between them, so the half that touches footage stays private and the half that judges see runs on data we generate ourselves.

```
            PRIVATE VISION LAYER                      │                PUBLIC INTELLIGENCE LAYER
                                                      │
  broadcast feed ──▶ Ingest ──▶ Interpret ────────────┼──▶ Explain ──▶ Render ──▶ Personalize
  (we have access,   segment    detect, track,        │     label,      cut clips,   Librarian,
   not a licence)    replays    identify (kit number, │     score,      reels,       viewer, API,
                                team colour,          │     explain     broadcast    MCP tools
                                continuity), emit     │
                                the EVENT STREAM ─────┤  ◀── synthetic generator feeds the same stream
                                                      │      (demo profile for reels, realistic for stats)
                                                 the boundary:
                                     src/regista/schemas/*.schema.json   
```

## The contract

Everything crossing the boundary is JSON Lines validated by two JSON Schemas (`data/synthetic/README.md` documents them record by record):

- **Event stream** (vision layer out): `match`, `camera_segment`, `track`, `appearance`, `possession`, `event`, `annotation`,
  and, from the generator in league mode only, `physical`.

Schema 0.2.0 (since 2026-10-23) adds the league's events `substitution`, `penalty`, `aerial_duel`, `card_red` and
`offside`, through balls as a pass qualifier, and the record type `physical`: each player's 10 Hz motion summarised as
distance, the FIFA speed zones, sprints, top speed, accelerations and decelerations. Streams without them stay 0.1.1:
every committed sample, the vision layer's output, and Who's who answers, verdicts and claims (`LEGACY_SCHEMA_VERSION`).
`tests/test_backcompat.py` checks that output without ratings is byte-identical to `main`.
- **Clip stream** (intelligence layer out): `clip`, `label`.

Not a pixel of footage crosses it. The synthetic generator produces the same stream from nothing, which is what the demo and the tests run on. It has three profiles. The realistic profile sits inside Premier League per-90 bands. The league profile (league mode, generator 0.7.1) adds player ratings and 10 Hz motion, and is checked against event, league-mode, physical, team-style, leader and role-shape bands (`docs/realism-report.md`). The demo profile packs a 3-minute sample with action.

## The agents

The pipeline is a Microsoft Agent Framework workflow (`src/regista/agents/workflow.py`), the default engine of `python3 -m regista.agents`. Ingest fans out to Validator and Possession, which fan back in at Clip; then Label, Review, Persist, Indexer (only when `REGISTA_SEARCH_ENDPOINT` is set), Librarian, and a finish step. Every role, and the review step, has an edge to a `dead_letter` executor. The graph is in `docs/workflow.md`. The original hand-written orchestrator is kept as a reference implementation (`--engine orchestrator`).

These are the roles from the product design (CLAUDE.md §3.1). Identity is not among them: it belongs to the vision layer (`src/regista/vision`, see below), and for the public demo the generator plays it.

| Role | Inputs → outputs | Local (default) | With `--cloud` (and on uploads to the live app) |
|---|---|---|---|
| **Ingest** | `match_dir` → `stream`, `index`, `match` | reads and indexes `events.jsonl` | same |
| **Validator** | `match_dir` → `validation` | JSON Schema validation, blocks on invalid events | same |
| **Possession** | `index`, `player_ids` → `on_ball` | on-ball windows per player with their camera segment | same |
| **Clip** | `index`, `player_ids`, `on_ball` → `clips` | the clip rule (`regista.clips`) | same |
| **Label** | `index`, `clips` → `labels` | tags, titles, explanation, watchability: the model learned from human verdicts (`regista.feedback`) when one has been trained, else the `rules-v0` table; flags clips it is unsure about | `FoundryLabelAgent`: `gpt-5-mini` on Microsoft Foundry through Agent Framework, with the learned model or `rules-v0` as the prior and the fallback |
| **Review** | `labels` → verdicts, `review_log` | with `--review` (or `review=true` on upload) the workflow pauses with `request_info` on flagged clips; verdicts are stored as human `annotation` records and retrain the watchability model; checkpointed, so a paused review resumes after a restart | same; in the API service, verdicts and the learned model are also kept in Cosmos DB `annotations` so they survive restarts |
| **Recap** | `match_dir`, `index`, `clips`, `labels` → `recap` | writes `recap.json`: headline, short paragraphs whose every sentence cites a clip or an event, a reel of the recap's best clips (`regista.recap`, rules) | `FoundryRecapAgent`: `gpt-5-mini` writes it from the same facts; sentences that cite nothing, use a number the facts do not hold, or use jargon are dropped; the rules recap is the fallback |
| **Persist** | `match_dir`, `clips`, `labels` → `clips_path` | writes `clips.jsonl` | `CosmosPersistAgent`: also upserts to Cosmos DB (`matches`, `clips`, `labels`, partition `match_id`) |
| **Indexer** | `match`, `clips`, `labels` → `search_index` | not in the graph | `SearchIndexAgent`: every labelled clip into the Azure AI Search index `regista-clips` |
| **Librarian** | `clips_path`, `queries` → `answers` | rule-based parser and ranking (`regista.librarian`) | `FoundryLibrarianAgent`: `gpt-5-mini` calling Regista's MCP server and, when `azmcp` is installed, Microsoft's Azure MCP Server; falls back to the rule-based answer on error |

What the workflow guarantees, and `tests/test_workflow.py` checks: typed handoffs (a failing role sends a `DeadLetter` message that only the `dead_letter` executor accepts), fan-out and fan-in, shared state under one key per value, retries on retryable errors, remaining roles recorded as skipped after a failure, the human-in-the-loop pause and resume, checkpointing, a per-attempt `trace.jsonl`, and a `dead_letter.jsonl` with the failing agent's inputs. The trace format is the same as the reference orchestrator's.

**Chat** (`POST /api/matches/{id}/chat`, `regista.conversation`; on the live app, Foundry engine verified there on 2026-10-21) keeps a conversation: each message is parsed and merged into the query built so far (a named player replaces the player, "he" and "his" keep it; new tags, angles and minutes replace the old unless the message says "also"; "everything", "whole match" and "start over" clear), and every reply says how the conversation is understood. The search and the merged query are deterministic; with the Foundry engine a Foundry model writes the reply from the conversation and the results, with the same public tools and limits as Ask Foundry, and the rule-based reply stands if it fails. The server keeps nothing between turns: the merged query and the last 12 turns travel with each request and are checked again. "Make that a reel" returns the current results, best first, which the page plays back to back. Every Chat and Ask Foundry answer carries a `trace` of what ran, in order (`{name, kind: step|agent|model|tool, server: regista-mcp|azure-mcp|null, ms}`): the rules engine lists its in-process steps, and the Foundry engine adds the agent, model and tool spans that Agent Framework's OpenTelemetry instrumentation recorded for that request, collected in-process whether or not Application Insights is configured (when none were recorded, the tools called are listed without timings and `trace_note` says so).

**Ask Foundry** (`POST /api/matches/{id}/ask`, one question, no conversation) and the Foundry engine of Chat run the Foundry Librarian, open to everyone and limited for cost and safety:
- questions of at most 200 characters;
- per visitor 3 a minute and 20 an hour; for everyone 60 an hour and 300 a day; two at a time (`REGISTA_ASK_*` to change); Ask and Chat share one limiter, and the Instant engine is not limited;
- public tools only: Regista's `search_clips`, `search_library` and `list_matches` (no rendering), and the Azure MCP Server's AI Search namespace. A crafted question cannot reach Cosmos DB, where the `annotations` container holds reviewers' verdicts and notes. The CLI keeps the Cosmos DB tools.

Uploads still pass no questions to the Librarian.

**The Scout agent** (`POST /api/scout/ask`, `src/regista/season/scout.py`; the Scout view) answers questions about the Regista League's players: "a winger with the most take-ons", "midfielders who win the ball back", "the best finisher". The rules engine always reads the question first, into filters and a sort (roles map to positions, winger and striker are FW; phrases map to stats; "fewest" reverses; "top 3" limits), runs the `search_players` tool, writes the reply from its numbers, and says in `understood` what it heard. With the Foundry engine (the default when Foundry is configured) a `gpt-5-mini` agent on Microsoft Foundry, through Agent Framework, then calls Regista's MCP server, limited to the three read-only player tools, and answers with the names and numbers they returned. The cards come from running its last player tool call again in-process, `understood` names that call, and `checked` lists any number in its reply that no tool result holds. It shares Ask Foundry's limiter and timeout; over the limits, on a timeout or an error, the rules answer stands and `answered_by` says why. The answer carries the same `trace`.

**The match recap** (`GET /api/matches/{id}/recap?player=&engine=`, `src/regista/recap.py`; CLAUDE.md §2.7): a headline and three or four short paragraphs, told from one player's side when a player is given, and a reel of its 4 to 6 best clips. One set of facts is read from the event stream and the labelled clips (the score; goals with scorer, assister and minute; the best chances that did not go in and who saved them; who stood out; for a player, their part in the goals, their best moments and the replays they appear in), each fact with a ref (`G1`, `C1`, `S1`, `M1`, `P1`, `R1`) that resolves to real clips and events. The rules engine writes sentences from them; with the Foundry engine a `gpt-5-mini` agent (Agent Framework, no tools) writes JSON sentences that list their refs, and Regista keeps only the sentences that cite a known ref, use only numbers the facts hold (the Scout agent's check) and contain no jargon or ids; `checked` lists what was left out and why. Every sentence's `cites` are `{t, clip_id?, event_id?}`; the Clip view plays the cited clip on the stage. Foundry recaps share Ask Foundry's limiter and timeout (over them: the rules recap, never a 429) and are cached on the replica per (match, player) for as long as the facts they were written from hold. The Recap step in the workflow writes `recap.json` after the review, before persist.

**The Profile agent's summaries** (`src/regista/season/summaries.py`): two or three sentences per player (what kind of player, what else stands out, the best moment), each sentence listing the facts it rests on (`S…` a stat with its rank among the position, `M…` a moment with its clip, `P1` the season). `python -m regista.season summarise` writes them with rules; with `--cloud` a Foundry model writes them from the same numbered facts, and an answer is refused (one retry, then the rules summary) when a sentence cites nothing, cites a fact that does not exist, uses a number its cited facts do not hold, or uses a gendered pronoun. The committed `data/season/summaries.json` records each summary's `model` and a fingerprint of the numbers it was written from; `GET /api/players/{id}` serves the stored summary only while the profile still has those numbers and otherwise writes the rules one on the spot (`model: "rules-v0 (live)"`).

## The views

Four views, one FastAPI app, the same code locally and on Azure (all live since 2026-10-22):

| View | Route | For | Built on |
|---|---|---|---|
| **Clips** (the Product) | `/` | creators, broadcasters, fans: ask for any moment | the Librarian, Chat, the match recap |
| **Scout** | `/scout`, `/players/{id}` | scouts: find a player across the season | the Regista League, profiles, the Scout and Profile agents |
| **Player** | `/me` | a player: upload my footage, check it's me, publish | Blob storage, a Storage queue, a Container Apps Job running the vision workflow |
| **Studio** | `/studio` | the operator | review, Who's who, training, claims, runs |

**Scout data: the Regista League** (`src/regista/season/`, CLAUDE.md §2.5). Six synthetic clubs with fixed squads, a
double round robin of 30 matches of two 15-minute halves. Only `data/season/league.json` is committed; matches regenerate
from it deterministically (built into the image at `docker build` time, tracks only when video needs them). A match takes
about 1.3 s to generate in league mode, and a cold season about 6 s in parallel on 10 cores (37 s on one;
`regista.season.build.build_all`). Every roster entry carries a global player id (`pl_bro_09`), so profiles aggregate
across matches: per-90 rates, percentiles by position (FBref's rule, among players with at least a third of a club's
minutes), a touch map, best moments, and for every stat the events and clips it was counted from. Every player also has
a public bio (age, height, foot, nationality) and hidden ratings (finishing, passing, vision, dribbling, defending,
aerial, stamina, keeper skills, top speed, acceleration). The generator reads the ratings. They are in the committed
`league.json`, but no API, MCP tool or page serves them: `people()` drops them, and `tests/test_attributes.py` and
`tests/test_metrics.py` check every public payload. Scouts judge players by what they do.

**The Scout terminal's engine** (part A, built on `feature/terminal-engine`, not yet deployed; the terminal's screens are
part B). Three pieces:

- **League mode** (`regista.synth.generator`, `LEAGUE_GENERATOR_VERSION` 0.7.1): the ratings move the probabilities of
  every action, and roles shape who makes which numbers (centre-backs pass and win headers, wingers cross and carry,
  strikers shoot).
  League matches take exp, log, sin, cos, hypot and Gaussians from `regista.detmath` (fdlibm ports on IEEE arithmetic)
  instead of libm, so the server (Linux) builds the same season as a Mac; `regista.season.pins` pins all 30 fixtures,
  checked in CI and by the image's smoke test (`docs/scout-terminal/build/determinism.md`).
- **Physical motion** (`regista.synth.physical`): all 22 players move at 10 Hz within their own `top_speed_kmh` and
  `acceleration_ms2`, tiring with stamina. Each match writes one `physical` record per player. `DEFINITIONS` gives each
  measure's definition and source.
- **Metrics** (`regista.season.metrics`): 127 player metrics in eight groups (shooting, creation, passes, carrying,
  defence, goalkeeping, physical, value) and 19 team-style metrics, each with a definition, a rule (FBref, Opta,
  StatsBomb, Wyscout) and sources. xT is fitted on the season. The engine gives per-90s, percentiles among position
  peers, the events and clip behind every number, form, similar players (cosine on standardised per-90s) and team style
  (possession, field tilt, PPDA, directness, set-piece xG). `regista.season.reliability` marks metrics whose split-half
  reliability is below 0.3 as noisy (`data/season/reliability.json`). A regular plays about 300 minutes a season, so
  every response states the sample.

`regista.terminal_api` serves it read-only and open, like the rest of Scout:

| Route | What |
|---|---|
| `GET /api/metrics` | the catalogue: every metric's definition, rule, sources, unit, kind, direction and positions; groups; the season's thresholds; the fitted xT grid |
| `GET /api/terminal/screen` | players with chosen metric columns; filters position, role, club, minutes, age, foot, name; sort by any metric |
| `GET /api/terminal/rank` | one metric's leaderboard (rank, value, percentile, how many events back it) |
| `GET /api/terminal/scatter` | two metrics per player, plus the pool's medians |
| `GET /api/players/{id}/metrics`, `/form`, `/similar`, `/shots`, `/heatmap` | every metric for one player with percentiles and evidence (paged with `evidence_offset`, so every moment can be read); per-match values and consistency; the most similar players in the same position; every shot with its location and clip; the touch grid from league fixtures only |
| `GET /api/teams`, `/api/teams/{club_id}/style`, `/api/teams/{club_id}/shots` | every club's style metrics; one club's with ranks; every shot by or against the club |

`python3 -m regista.season.metrics --rank KEY | --player ID` prints the same from the command line;
`python3 -m regista.season.audit` prints split-half reliability and the top scorers; `python3 -m regista.synth.report
--league [--repeat N]` checks the season against the bands. Build reports, independent verification and review rounds:
`docs/scout-terminal/build/`.

**The catalogue** (merged with PRs #39 and #40 and live since 2026-10-26 on revision `regista-api--d1026204656`;
CLAUDE.md §2.11, `docs/catalogue/build/design.md`). Regista as a library of uploaded footage below the professional
line: 14 synthetic competitions in 10 countries (tiers semi-pro, amateur, college, academy; senior, college and U17-U20
age groups; men and women), 66 clubs, 1,183 invented people, 90 matches. The Regista League is one of them, "England
semi-pro men", by reference: `league.json`, its pins and every existing endpoint's answer are unchanged
(`tests/test_catalogue_backcompat.py`). The other 13 are league-shaped files in `data/catalogue/` whose 60 uploaded
matches build on demand like the league's and are pinned (`regista.catalogue.pins`). Each level scales the hidden
ratings and sets an `execution` size the generator reads (inert when absent, so generator 0.7.1 and every existing
match are unchanged). Camera type and uploader are labels of each upload: every match is rendered the same way.

- **Engine** (`regista.catalogue.metrics`): one `SeasonMetrics` per competition, the same 127 metrics, percentiles
  re-pooled by level (same tier, age group, gender and position across countries; `scope=competition` or `all` on
  request), every number with its `pool` and `sample`; rankings compare percentiles only within a position and raw
  numbers only within a level. Reliability per level on six full regenerated seasons (`data/catalogue/reliability.json`).
- **API** (`regista.catalogue_api`, read-only and open): `/api/catalogue`, `/api/competitions[/{id}[/players]]`,
  `/api/catalogue/{players[/{id}],rank,compare,matches,pools}`, `/api/players/{id}/career`, and optional catalogue
  parameters on `/api/season`, `/api/players` and the terminal endpoints. Without them every response is `main`'s.
- **Realism per level** (`python3 -m regista.synth.report --catalogue`, `docs/catalogue/realism.md`): one sourced band
  (U17 peak match speed), sourced orders between levels, assumed orders shown but never counted, and "no published band"
  for event rates below the professional line. Premier League bands appear only as an upper reference.

**The Player view's cloud path** (`src/regista/player/`, `src/regista/player_api.py`, CLAUDE.md §2.6):

```
/me ──upload (admin token)──▶ Blob: uploads/{id}/video.mp4 + record.json
                         └──▶ Storage queue vision-jobs ──▶ Container Apps Job regista-vision (KEDA queue scaler,
                                                            one execution per message, the job's own identity)
                                                              │  models from Blob: models/vision/
                                                              │  vision workflow (Agent Framework): shots → identity →
                                                              │  is-this-you questions → possession → events → writer
                                                              ▼  clips for every starter, stage times into record.json
                              Blob: matches/pv_{id}/ ──▶ the app fetches it on first use: Clips, profile, "Is this you?"
```

The footage is synthetic (`regista.player.film`: a friendly between two league clubs in the vision layer's format), and
the roster is both clubs' league squads (`roster_for`), so the match it writes carries global ids and joins the
uploader's profile with no mapping. Keyless throughout: shared-key login is off on the storage account; the app holds
Storage Blob Data Contributor and Queue Data Message Sender, the job Blob and Queue Data Contributor and AcrPull.
Verified end to end in Azure on 2026-10-22: a 3-minute upload took 3 min 5 s and joined the player's profile.

The two original dashboards in detail (plan: `docs/plan-two-dashboards.md`):

- **The Product (`/`, `src/regista/static/product/`)**, open to everyone: a match and player picker that opens on the featured match (`"featured": true` in its `manifest.json`), one ask box with the Instant / Foundry switch (both through `/chat`), the "How Regista answered" panel under every reply, a timeline of the whole match (`timeline.js`; periods and goals from `GET /api/matches/{id}`), the stage with Play reel, Download reel (`/reel.mp4`, up to 12 clips, rendered once and cached) and Export moments (`/moments.csv`), a Best first / Match order switch, plain-English labels and badges ("Labelled by Microsoft Foundry", "Cut from video"), and How it works.
- **The Studio (`/studio`, `src/regista/studio_api.py`, `src/regista/studio/`)**, behind a key: Overview, Review queue, Who's who, Training, Runs, Jobs (local only) and Console. `capabilities` says what a deployment can do, so on the live app the local-only parts say so instead of failing. `python3 -m regista.studio status` prints the overview from a local app or the live one.

**Who may do what** (`src/regista/access.py`; `tests/test_access.py` walks every route, so a new route fails until it is classified):

| Routes | No key | View key | Admin key |
|---|---|---|---|
| The Product: `/`, health, matches, clips, clip and match video, reel, moments, report, search, `/ask`, `/chat`; Scout and the terminal's metrics (`/api/metrics`, `/api/terminal/*`, `/api/teams*`); the `/studio` page itself (no data in it) | ✔ | ✔ | ✔ |
| Studio reads: `/api/studio/*`, `GET /api/feedback`, `GET …/review`, `GET …/identity-review` and its crops | – | ✔ | ✔ |
| Writes: upload, verdicts, workflow review, Who's who answers, retraining, vision jobs | – | 403 | ✔ |

`REGISTA_ADMIN_TOKEN` and `REGISTA_STUDIO_VIEW_TOKEN` are Container Apps secrets on the live app and lines in `.env` locally; keys travel only in the `X-Regista-Token` header, never in a URL. With neither key set, a plain local run (development) is open, except that a write carrying another site's `Origin` is refused. It fails closed: with `REGISTA_READONLY=1` or `REGISTA_CLOUD` set and no key configured, the Studio answers 401 and writes are off, so a deployment that lost its key secret never falls open; `infra/deploy-app.sh` refuses to deploy without `REGISTA_ADMIN_TOKEN`. `REGISTA_READONLY=1` switches writes off whatever the key. Every response carries a strict Content-Security-Policy (`script-src 'self'`, `frame-ancestors 'none'`); both pages load only their own script files.

**Public renders are bounded.** The video endpoints accept only the sizes the pages use (25 fps, width 640 or 1280; anything else is 400). Renders run on their own small thread pool, so requests waiting for one never hold the threads the other endpoints use; at most `REGISTA_RENDER_QUEUE` (24) wait at once, more get 503 with `Retry-After`. The cache keeps at most `REGISTA_CACHE_MAX_MB` (1024 MB), evicting the least recently served files first, never one being rendered or served.

**The answer trace.** Every `/chat` and `/ask` answer carries `trace: [{name, kind, server, ms}]`, which the Product shows as "How Regista answered". The Instant engine lists its in-process steps (`librarian.load_match`, `conversation.step`, `librarian.search_clips`) and says that no model and no MCP server ran. The Foundry engine adds what Agent Framework's OpenTelemetry instrumentation recorded for that request, collected by an in-process span processor keyed by trace id: the agent (`regista-librarian-chat`), the model call (`gpt-5-mini`), and each tool call with its server (`search_clips` on Regista's MCP server, `search_index_query` on the Azure MCP Server). The same spans go to Application Insights when it is configured. When no spans were recorded, the tools are listed without timings and `trace_note` says so.

## MCP tools

`python -m regista.mcp_server` serves these over stdio (tested end to end with the MCP client):

| Tool | What it does |
|---|---|
| `search_clips(match_dir, query, limit)` | the Librarian over one match's files: parse, rank, explain |
| `search_library(query, top)` | search every indexed match at once through Azure AI Search (needs `REGISTA_SEARCH_ENDPOINT`) |
| `derive_clips(match_dir, player_id)` | the clip rule and labeller for one player |
| `validate_stream(path)` | schema validation of a match directory or one file |
| `render_clip(match_dir, clip_id, out_dir)` | cut one clip to MP4 with its title card |
| `list_matches(root)` | the matches available |
| `search_players(position, club, q, sort, order, limit, min_minutes)` | the Regista League's players filtered and ranked by any stat per 90 or ratio, each with its rank among the position |
| `get_profile(player)` | one player's season by global id or full name, without the per-event evidence lists |
| `compare_players(players)` | two or three players side by side |
| `match_recap(match_dir, player_id)` | the match recap (rules engine): headline, paragraphs with a citation on every sentence, the recap reel; from one player's side when given |
| `list_competitions(country, tier, age_group, gender)` | the catalogue's competitions with their uploads, levels and careers |
| `search_catalogue_players(tier, age_group, gender, country, competition, position, sort, order, scope, limit, min_minutes)` | players across the catalogue ranked by a terminal metric, each percentile with its pool (same level by default) |
| `get_catalogue_player(player, scope)` | one player across the catalogue: career and a row per competition with pools |

Any MCP host can drive Regista with these. The Foundry Librarian attaches this server, and beside it Microsoft's Azure MCP Server (`azmcp`, from the `msmcp-azure` package), started read-only with only the Cosmos DB namespace, plus the Search namespace when Search is configured; the tools allowed are `cosmos_database_container_item_query`, `cosmos_list`, and `search_index_query` (`src/regista/cloud/foundry.py`). Calls to the Cosmos DB query tool have been seen from local CLI runs. Inside the container (public Ask Foundry, AI Search namespace only), `search_index_query` was verified on 2026-10-21 (revision `regista-api--d1021183822`); the Cosmos DB tools are not offered there by design.

## Services per pipeline stage

**Running** marks what code calls in Azure today; everything else is planned.

| Stage | Running today | Planned next |
|---|---|---|
| Ingest | file read of `events.jsonl`; API upload on Container Apps; Player-view footage into **Blob Storage** and a **Storage queue** (**running**) | Functions + Event Grid triggers for broadcast feeds; AI Video Indexer for scene cuts |
| Interpret | vision layer v0 (`regista.vision`): shot, identity, possession and event agents as a second Agent Framework workflow, trained and measured only on Regista's own rendered broadcast (`docs/vision.md`); runs in an event-driven **Container Apps Job** for Player-view uploads (**running**) and locally; the synthetic generator for the public demo | Azure AI Vision kit-number OCR (a stub backend raises `NotImplementedError` today); models hosted in Foundry; Event Hubs → Fabric Eventstream → Lakehouse |
| Explain | `FoundryLabelAgent`: `gpt-5-mini` on **Microsoft Foundry** via **Agent Framework**, the learned watchability model or rules-v0 as prior and fallback (**running**) | Foundry evaluations against human annotations from the review tool |
| Render | `regista.render` inside the Container Apps service, on-demand with a local cache (**running**) | Container Apps jobs for batch renders; Blob + CDN for the cache |
| Review | `ReviewExecutor`: the workflow pauses with `request_info` on clips the Label agent is unsure about; verdicts become human annotations and retrain the watchability model (**running**) | Foundry evaluations scoring each labeller against the human verdicts |
| Persist | `CosmosPersistAgent`: **Cosmos DB** serverless, `matches` / `clips` / `labels` / `annotations` (**running**) | |
| Index | `SearchIndexAgent` (role `indexer`): every labelled clip into **Azure AI Search** `regista-clips` (**running**) | Vector search over clip summaries |
| Personalize | `FoundryLibrarianAgent` on Foundry calling two MCP servers: Regista's (search_clips, search_library) and Microsoft's **Azure MCP Server** (read-only Cosmos DB and Search queries), from the CLI with `--cloud --query` (**running**); the app and API on **Container Apps**, where anyone can ask the rule-based or the Foundry Librarian, rate-limited (**running**) | AI Translator and Speech for languages |
| Observe | Agent Framework OpenTelemetry → **Application Insights** → Foundry **Tracing** (**running**; spans from the live app verified on 2026-10-21 (revision `regista-api--d1021183822`), plus local CLI runs) | Alerts on dead letters |

## Deployment on Azure Container Apps (running)

```
subscription Azure for Students (Northeastern University directory), resource group regista-rg, France Central
(the subscription allows five European and Canadian regions; the group carries the directory's required tags)
├── regista-foundry-<id>   Microsoft Foundry resource, project "regista", deployment gpt-5-mini (GlobalStandard)
├── regista-cosmos-<id>    Cosmos DB serverless, key login off, database "regista",
│                          containers matches / clips / labels / annotations (partition /match_id)
├── regista-search-<id>    Azure AI Search, free tier, key login off, index regista-clips
├── regista-appi           Application Insights on the Log Analytics workspace, connected to the Foundry project for tracing
├── <registry>acr          Container Registry (Basic, no admin user); images pushed by GitHub Actions (federated identity)
├── regista-env            Container Apps environment (workload profiles mode) + Log Analytics workspace (0.1 GB/day cap)
└── regista-api            Container App: uvicorn regista.api:app on :8000, one replica (min = max = 1), external ingress,
                           system-assigned identity with AcrPull (it pulls its own image), Foundry User (project), Cosmos DB
                           data-contributor, and Search roles,
                           env FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL, REGISTA_COSMOS_ENDPOINT, REGISTA_SEARCH_ENDPOINT, REGISTA_CLOUD=1,
                           secrets admin-token (REGISTA_ADMIN_TOKEN), appi-connection (APPLICATIONINSIGHTS_CONNECTION_STRING),
                           and studio-view-token (REGISTA_STUDIO_VIEW_TOKEN)
```

Provision with `infra/provision.sh` (idempotent; creates the Foundry resource, project and deployment, Cosmos DB and its containers, AI Search, and the Container Apps environment and registry, and writes `.env`). It does not create Application Insights or connect it to the Foundry project; that was done by hand in the portal. Build the image by pushing to `main`, deploy with `infra/deploy-app.sh`. Free-trial subscriptions cannot run ACR Tasks, which is why the image builds on GitHub Actions rather than with `az containerapp up --source`.

**Auth.** The app and the CLI reach Foundry, Cosmos DB, and AI Search with Microsoft Entra ID (`DefaultAzureCredential`: `az login` on a laptop, the managed identity in Container Apps) through role assignments; the code uses no keys for them. Nothing else uses keys or passwords: key-based local auth is off on the Cosmos DB and AI Search accounts, the registry has no admin user (the app pulls with its own identity, AcrPull), and GitHub Actions signs in with a federated identity (OpenID Connect, trusted only for `main`) that may push images and update the resource group. Writes on the live app (uploads, verdicts, reviews, retraining) need the `X-Regista-Token` header, checked against a Container Apps secret; a second secret, the Studio view key, reads the Studio and writes nothing (table above). CI deploys change only the image, so the view key is set once with `infra/deploy-app.sh`. `.env` holds the endpoints plus `REGISTA_ADMIN_TOKEN` and `APPLICATIONINSIGHTS_CONNECTION_STRING`; it is git-ignored and docker-ignored.

**What the live app serves.** The Product and the Studio described above, with the four sample matches in the image, and the library in Cosmos DB and Azure AI Search, with tracing. The vision layer runs only from the repository (README, "What's live"). The matches in the image with everything (`syn_0141`, `syn_0142`, `syn_0294`, `vis_0201`), plus every match Cosmos DB holds (`source: cosmos` in `/api/matches`): teams, players, clips and labels read back from Cosmos, skipping the stale pre-0.1.1 documents. Uploaded matches are written to the container's local disk and lose their event stream on a restart or new revision, so their video, search, and verdicts are unavailable from then on (the API answers 409 and says why). `/api/health` names what the deployment runs (`librarian`, `azure_mcp`, `tracing`, `container_apps`, `storage`), and Home's "Running on" row shows it under the search: the official service icons, each beside its full name, only for what health reports. Agent Framework spans start with the app whenever the Application Insights connection string is set.

## Microsoft Fabric: the season in OneLake, cross-checked

The Regista League (30 matches, 108 players) and the Player view's uploads live in a **Fabric lakehouse** as Delta
tables, and a **Fabric notebook** recomputes the league leaders on its own so Regista can check its profiles against it.

```
Fabric trial capacity (Zaid's own; the tenant is Northeastern's and holds other people's trials, never used)
└── workspace "Regista"
    ├── lakehouse regista_league   OneLake: abfss://<workspace>@onelake.dfs.fabric.microsoft.com/<lakehouse>/Tables/
    │     clubs, players (global ids), matches (played_s), lineups (per-match id -> global id, starter),
    │     events (every league event with its player's global id), clips, labels,
    │     player_season (Regista's profile numbers: one row per player and stat), uploads (Player-view uploads),
    │     leaders_check (written by the notebook)
    └── notebook regista_leaders_check   Spark SQL over events, lineups, matches, players -> leaders_check
```

`python -m regista.season.fabric setup | push | check` (`src/regista/cloud/fabric.py`, `fabric_tables.py`,
`fabric_notebook.py`):

- **setup** lists capacities through the Fabric API and their admins through the Power BI API, and picks only an active
  trial capacity whose admins include the signed-in user and on which that user holds the Admin right
  (`choose_capacity`). It creates or reuses the workspace "Regista" on that capacity and the lakehouse in it. A
  "Regista" workspace on any other capacity is left alone. The ids go into `.env` (`REGISTA_FABRIC_WORKSPACE_ID`,
  `REGISTA_FABRIC_LAKEHOUSE_ID`).
- **push** writes the tables with delta-rs (`deltalake`) straight into OneLake, overwriting each one (data and
  schema), so a push can be repeated. Uploads are read from the Player view's store (Azure Blob Storage when
  `REGISTA_STORAGE_ACCOUNT` is set). For a finished upload, the uploader's minutes and headline counts are added.
- **check** creates or updates the notebook through the Items API (its definition is generated from
  `fabric_notebook.py`, so it lives in the repo) and runs it on demand through the Job Scheduler API. When the run ends
  it reads `leaders_check` back from OneLake and compares it, row by row, with `player_season`. The notebook re-derives
  goals, assists, shots, key passes, take-ons won, tackles won and interceptions from the event contract in SQL; it does
  not reuse Regista's Python. For each stat it computes appearances, minutes, count, per-90 rate and the percentile
  within the position. Counts, appearances and percentiles must be equal; minutes and per-90 rates may differ by one
  unit of their last digit at most (0.1 minutes, 0.01 per 90): Spark's ROUND takes a half up on the decimal form, Python's
  round takes the binary value half to even, so the two can disagree on a half (30.15 minutes: 30.2 against 30.1).

Keyless: `DefaultAzureCredential` with the Fabric API scope, the Power BI scope (capacity admins) and the storage scope
(OneLake). The notebook recreates `leaders_check` each run without deletion vectors, which Fabric turns on for new
tables and which delta-rs cannot read yet. Tests (`tests/test_fabric.py`) use a fake Fabric API and a local folder in
place of OneLake; they never reach Fabric.

**First run, 2026-10-23** (workspace `b45d50d0-…`, lakehouse `1926e0bf-…`, trial capacity FTL64 in Central US):
`push` wrote clubs 6, players 108, matches 30, lineups 1,080, events 55,890, clips 11,881, labels 11,881,
player_season 2,376 and uploads 1 rows in 31 s. `check` ran the notebook in 52 s, and its `leaders_check` agreed with
Regista on all 756 rows checked (108 players x 7 stats; 462 of them carry a percentile, the rest belong to players
below the minutes bar or on the bench). The first run failed before any comparison: `leaders_check` had deletion vectors
on. That was fixed in the notebook.

**Second run, 2026-10-24** (the season regenerated in league mode, generator 0.7.0): `push` wrote clubs 6, players 108,
matches 30, lineups 1,080, events 33,624, clips 10,620, labels 10,620, player_season 3,024 and uploads 1 rows in 23 s.
`check` ran the notebook in 42 s and matched **328 of 756** rows. Appearances, minutes, counts and per-90 rates agreed on
all 756. Every difference was in the percentile: Regista now uses FBref's rule (the average of the share of position
peers strictly below and the share at or below), ranks unrounded rates, and pools players with at least a third of a
club's minutes (100.5). The notebook's `LEADERS_SQL` still used `(RANK()-1)/(n-1)`, rates rounded to 2 decimals, and
40% of the top player's minutes.

**Third run, 2026-10-24** (same lakehouse, no new push): `LEADERS_SQL` now states Regista's rule. The pool is players
who appeared with unrounded minutes of at least `ROUND(max club minutes / 3, 1)`, a club's minutes being the sum of its
matches' `played_s / 60`. The rank value is the per-90 rate to 6 decimals. The percentile is
`BROUND(50 * (strictly_below + at_or_below) / n, 0)` when n > 1. `fabric_notebook.leaders_rule` applies the same rule
in Python to the same tables, and `tests/test_fabric.py` compares it with `Season.build` (three fixtures in the quick
suite, the whole committed season under `-m slow`). `REGISTA_DOTENV= python3 -m regista.season.fabric check` ran the
notebook in 52 s and matched **756 of 756** rows (462 with a percentile). The `player_season` table in OneLake was read
back and equals what this branch's `Season.build` gives. The row counts above are what `fabric_tables.season_tables`
builds offline from the same season.

**Fourth run, 2026-10-24** (the season the app serves: generator 0.7.1, the same bits on Linux and macOS, and the
star's league attributes version 2): `push` wrote clubs 6, players 108, matches 30, lineups 1,080, events 33,758, clips
10,661, labels 10,661, player_season 3,024 and uploads 1 rows in 28 s. `check` ran the notebook in 52 s and matched
**756 of 756** rows (108 players x 7 stats), Femi Toure's five goals among them.

### The catalogue in the same lakehouse (running)

**Status: Pushed and checked in Fabric on 2026-10-26: 8 tables (145,546 rows) in 17 s; notebook run 27d43e96 Completed in 83 s; 7,399 of 7,399 rows matched, and the league check re-run the same day matched 756 of 756 (`docs/catalogue/fabric.md`, "Real run").**

The catalogue (§2.11 of CLAUDE.md: 14 competitions in 10 countries, 90 uploaded matches) goes into the same lakehouse
under its own table names, so the league's tables, its notebook and its 756-row check stay exactly as they are:

```
lakehouse regista_league
  catalogue_competitions (14: level labels, as_of), catalogue_clubs (66), catalogue_players (1,188 squad entries,
  public bio only), catalogue_matches (90: round, date, score, played_s, uploader, camera), catalogue_lineups (3,240,
  played_s from substitutions and red cards), catalogue_events (102,904, with competition_id and seq),
  catalogue_possessions (30,645, with seq), catalogue_player_season (7,399: Regista's numbers, one row per
  player-competition row and stat), catalogue_leaders_check (written by the second notebook)
notebook regista_catalogue_check   Spark SQL over the six raw catalogue tables -> catalogue_leaders_check
```

- England semi-pro men is the Regista League's 30 fixtures (from `data/season/matches`), the matches the catalogue
  pages count; the Player view's friendlies are not in the catalogue tables.
- `catalogue_player_season` comes from the engine the catalogue pages use (`regista.catalogue.metrics`): appearances,
  minutes, count, per-90, whether the row qualifies, the percentile in the default **level pool** (same tier, age group,
  gender and position over every competition of that level) and that pool's size.
- The second notebook (`fabric_catalogue_notebook.py`) writes the catalogue's rules again in SQL: time on the pitch
  from the period, substitution and red-card events (it never reads the tables' `played_s`, which come from
  `regista.season.playing_time`, the engine's own rule; the league's notebook still sums `lineups.played_s`), each
  competition's qualifying minutes (England a third of the busiest club's minutes; elsewhere also at least 45), level pools, FBref's
  percentile, no percentile from fewer than 5 peers or for a count of 0. The catalogue engine's shots leave penalties
  out, its key passes are FBref's (the pass received at the start of the shooter's possession, read off
  `catalogue_possessions`), and a tackle without an outcome counts as won; the SQL follows the engine there, and the
  engine is unchanged.
- `catalogue_leaders_rule` is the same SQL in plain Python. `tests/test_fabric_catalogue.py` compares it with
  Regista's rows for every row (7,399 of 7,399 offline) and checks that a rule written differently (penalties in the
  shots, no 45-minute floor, pools per competition, men and women in one pool) is caught; small built streams pin the
  rules the committed data cannot tell apart (FBref's key pass against the league's qualifier, England without the
  floor, a tackle with no outcome won, time on the pitch), each against the engine's own answer.
- `python -m regista.season.fabric push --catalogue` writes the league's tables and then the catalogue's
  (`--catalogue-only`: only the catalogue's; plain `push` is unchanged); `check --catalogue` runs the second notebook
  and compares.

## What is deliberately not here

- No real footage, anywhere. The vision layer v0 is trained and measured only on Regista's own rendered broadcast; its evaluation matches were used during development, so they are a development set, not a held-out test. `docs/vision.md` has the numbers and what changes for real footage.
- Running in Azure: Microsoft Foundry, Agent Framework (on Foundry), Cosmos DB, Azure AI Search, Application Insights with Foundry tracing, Container Apps, and Container Registry; Microsoft Fabric (a lakehouse and a notebook, from the CLI; section above; the catalogue's tables and second notebook run there too). Since the Player view, Blob Storage, a Storage queue and a Container Apps Job run too. Azure AI Vision, Video Indexer, Speech, Translator, Functions, and Event Hubs are planned until code runs against them. GitHub Copilot is not used.
- Face recognition is not the identification path. Kit number, team colour, and tracking continuity are, for both robustness and policy reasons.
