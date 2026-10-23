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

- **Event stream** (vision layer out): `match`, `camera_segment`, `track`, `appearance`, `possession`, `event`, `annotation`.
- **Clip stream** (intelligence layer out): `clip`, `label`.

Not a pixel of footage crosses it. The synthetic generator produces the same stream from nothing, which is what the demo and the tests run on. The realistic profile sits inside Premier League per-90 bands (`docs/realism-report.md`); the demo profile packs a 3-minute sample with action.

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

**The Profile agent's summaries** (`src/regista/season/summaries.py`): two or three sentences per player (what kind of player, what else stands out, the best moment), each sentence listing the facts it rests on (`S…` a stat with its rank among the position, `M…` a moment with its clip, `P1` the season). `python -m regista.season summarise` writes them with rules; with `--cloud` a Foundry model writes them from the same numbered facts, and an answer is refused (one retry, then the rules summary) when a sentence cites nothing, cites a fact that does not exist, uses a number its cited facts do not hold, or uses a gendered pronoun. The committed `data/season/summaries.json` records each summary's `model` and a fingerprint of the numbers it was written from; `GET /api/players/{id}` serves the stored summary only while the profile still has those numbers and otherwise writes the rules one on the spot (`model: "rules-v0 (live)"`).

## Two dashboards

Live since 2026-10-22 (plan: `docs/plan-two-dashboards.md`). One FastAPI app serves both, with the same code locally and on Azure.

- **The Product (`/`, `src/regista/static/product/`)**, open to everyone: a match and player picker that opens on the featured match (`"featured": true` in its `manifest.json`), one ask box with the Instant / Foundry switch (both through `/chat`), the "How Regista answered" panel under every reply, a timeline of the whole match (`timeline.js`; periods and goals from `GET /api/matches/{id}`), the stage with Play reel, Download reel (`/reel.mp4`, up to 12 clips, rendered once and cached) and Export moments (`/moments.csv`), a Best first / Match order switch, plain-English labels and badges ("Labelled by Microsoft Foundry", "Cut from video"), and How it works.
- **The Studio (`/studio`, `src/regista/studio_api.py`, `src/regista/studio/`)**, behind a key: Overview, Review queue, Who's who, Training, Runs, Jobs (local only) and Console. `capabilities` says what a deployment can do, so on the live app the local-only parts say so instead of failing. `python3 -m regista.studio status` prints the overview from a local app or the live one.

**Who may do what** (`src/regista/access.py`; `tests/test_access.py` walks every route, so a new route fails until it is classified):

| Routes | No key | View key | Admin key |
|---|---|---|---|
| The Product: `/`, health, matches, clips, clip and match video, reel, moments, report, search, `/ask`, `/chat`; the `/studio` page itself (no data in it) | ✔ | ✔ | ✔ |
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

Any MCP host can drive Regista with these. The Foundry Librarian attaches this server, and beside it Microsoft's Azure MCP Server (`azmcp`, from the `msmcp-azure` package), started read-only with only the Cosmos DB namespace, plus the Search namespace when Search is configured; the tools allowed are `cosmos_database_container_item_query`, `cosmos_list`, and `search_index_query` (`src/regista/cloud/foundry.py`). Calls to the Cosmos DB query tool have been seen from local CLI runs. Inside the container (public Ask Foundry, AI Search namespace only), `search_index_query` was verified on 2026-10-21 (revision `regista-api--d1021183822`); the Cosmos DB tools are not offered there by design.

## Services per pipeline stage

**Running** marks what code calls in Azure today; everything else is planned.

| Stage | Running today | Planned next |
|---|---|---|
| Ingest | file read of `events.jsonl`; API upload on Container Apps (**running**) | Blob Storage for feeds; Functions + Event Grid triggers; AI Video Indexer for scene cuts |
| Interpret | vision layer v0 (`regista.vision`, local): shot, identity, and possession agents as a second Agent Framework workflow, trained and measured only on Regista's own rendered broadcast (`docs/vision.md`); the synthetic generator for the public demo | Azure AI Vision kit-number OCR (a stub backend raises `NotImplementedError` today); models hosted in Foundry; Event Hubs → Fabric Eventstream → Lakehouse |
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

**What the live app serves.** The Product and the Studio described above, with the four sample matches in the image, and the library in Cosmos DB and Azure AI Search, with tracing. The vision layer runs only from the repository (README, "What's live"). The matches in the image with everything (`syn_0141`, `syn_0142`, `syn_0294`, `vis_0201`), plus every match Cosmos DB holds (`source: cosmos` in `/api/matches`): teams, players, clips and labels read back from Cosmos, skipping the stale pre-0.1.1 documents. Uploaded matches are written to the container's local disk and lose their event stream on a restart or new revision, so their video, search, and verdicts are unavailable from then on (the API answers 409 and says why). `/api/health` names what the deployment runs (`librarian`, `azure_mcp`, `tracing`), and the page's footer shows it. Agent Framework spans start with the app whenever the Application Insights connection string is set.

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
  within the position. Counts, appearances and percentiles must be equal; minutes and per-90 rates may differ only by
  rounding (Python and Spark round halves differently).

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

## What is deliberately not here

- No real footage, anywhere. The vision layer v0 is trained and measured only on Regista's own rendered broadcast; its evaluation matches were used during development, so they are a development set, not a held-out test. `docs/vision.md` has the numbers and what changes for real footage.
- Running in Azure: Microsoft Foundry, Agent Framework (on Foundry), Cosmos DB, Azure AI Search, Application Insights with Foundry tracing, Container Apps, and Container Registry; Microsoft Fabric (a lakehouse and a notebook, from the CLI; section above). Azure AI Vision, Video Indexer, Speech, Translator, Blob Storage, Functions, and Event Hubs are planned until code runs against them. GitHub Copilot is not used.
- Face recognition is not the identification path. Kit number, team colour, and tracking continuity are, for both robustness and policy reasons.
