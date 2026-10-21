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

**Chat** (`POST /api/matches/{id}/chat`, `regista.conversation`; on the live app, Foundry engine verified there on 2026-10-21) keeps a conversation: each message is parsed and merged into the query built so far (a named player replaces the player, "he" and "his" keep it; new tags, angles and minutes replace the old unless the message says "also"; "everything", "whole match" and "start over" clear), and every reply says how the conversation is understood. The search and the merged query are deterministic; with the Foundry engine a Foundry model writes the reply from the conversation and the results, with the same public tools and limits as Ask Foundry, and the rule-based reply stands if it fails. The server keeps nothing between turns: the merged query and the last 12 turns travel with each request and are checked again. "Make that a reel" returns the current results, best first, which the viewer plays back to back. Every Chat and Ask Foundry answer carries a `trace` of what ran, in order (`{name, kind: step|agent|model|tool, server: regista-mcp|azure-mcp|null, ms}`): the rules engine lists its in-process steps, and the Foundry engine adds the agent, model and tool spans that Agent Framework's OpenTelemetry instrumentation recorded for that request, collected in-process whether or not Application Insights is configured (when none were recorded, the tools called are listed without timings and `trace_note` says so).

On the live app the search box has two buttons beside the Chat panel. **Search** runs the rule-based Librarian. **Ask Foundry** (`POST /api/matches/{id}/ask`) runs the Foundry Librarian, open to everyone and limited for cost and safety:
- questions of at most 200 characters;
- per visitor 3 a minute and 20 an hour; for everyone 60 an hour and 300 a day; two at a time (`REGISTA_ASK_*` to change);
- public tools only: Regista's `search_clips`, `search_library` and `list_matches` (no rendering), and the Azure MCP Server's AI Search namespace. A crafted question cannot reach Cosmos DB, where the `annotations` container holds reviewers' verdicts and notes. The CLI keeps the Cosmos DB tools.

The answer shows which model answered and every tool it called. Uploads still pass no questions to the Librarian.

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
| Personalize | `FoundryLibrarianAgent` on Foundry calling two MCP servers: Regista's (search_clips, search_library) and Microsoft's **Azure MCP Server** (read-only Cosmos DB and Search queries), from the CLI with `--cloud --query` (**running**); viewer and API on **Container Apps**, where the open search box is the rule-based Librarian (**running**) | AI Translator and Speech for languages; questions to the Foundry Librarian from the viewer |
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
                           secrets admin-token (REGISTA_ADMIN_TOKEN) and appi-connection (APPLICATIONINSIGHTS_CONNECTION_STRING)
```

Provision with `infra/provision.sh` (idempotent; creates the Foundry resource, project and deployment, Cosmos DB and its containers, AI Search, and the Container Apps environment and registry, and writes `.env`). It does not create Application Insights or connect it to the Foundry project; that was done by hand in the portal. Build the image by pushing to `main`, deploy with `infra/deploy-app.sh`. Free-trial subscriptions cannot run ACR Tasks, which is why the image builds on GitHub Actions rather than with `az containerapp up --source`.

**Auth.** The app and the CLI reach Foundry, Cosmos DB, and AI Search with Microsoft Entra ID (`DefaultAzureCredential`: `az login` on a laptop, the managed identity in Container Apps) through role assignments; the code uses no keys for them. Nothing else uses keys or passwords: key-based local auth is off on the Cosmos DB and AI Search accounts, the registry has no admin user (the app pulls with its own identity, AcrPull), and GitHub Actions signs in with a federated identity (OpenID Connect, trusted only for `main`) that may push images and update the resource group. Writes on the live app (uploads, verdicts, reviews, retraining) need the `X-Regista-Token` header, checked against a Container Apps secret. `.env` holds the endpoints plus `REGISTA_ADMIN_TOKEN` and `APPLICATIONINSIGHTS_CONNECTION_STRING`; it is git-ignored and docker-ignored.

**What the live app serves.** Everything in the viewer: Search, Ask Foundry with both MCP servers, Chat, Who's who, and the library in Cosmos DB and Azure AI Search, with tracing. The vision layer runs only from the repository (README, "What's live"). The committed sample match (`syn_0294`) with everything, plus every match Cosmos DB holds (`source: cosmos` in `/api/matches`): teams, players, clips and labels read back from Cosmos, skipping the stale pre-0.1.1 documents. Uploaded matches are written to the container's local disk and lose their event stream on a restart or new revision, so their video, search, and verdicts are unavailable from then on (the API answers 409 and says why). `/api/health` names what the deployment runs (`librarian`, `azure_mcp`, `tracing`), and the viewer's footer shows it. Agent Framework spans start with the app whenever the Application Insights connection string is set.

## What is deliberately not here

- No real footage, anywhere. The vision layer v0 is trained and measured only on Regista's own rendered broadcast; its evaluation matches were used during development, so they are a development set, not a held-out test. `docs/vision.md` has the numbers and what changes for real footage.
- Running in Azure: Microsoft Foundry, Agent Framework (on Foundry), Cosmos DB, Azure AI Search, Application Insights with Foundry tracing, Container Apps, and Container Registry. Microsoft Fabric, Azure AI Vision, Video Indexer, Speech, Translator, Blob Storage, Functions, and Event Hubs are planned until code runs against them. GitHub Copilot is not used.
- Face recognition is not the identification path. Kit number, team colour, and tracking continuity are, for both robustness and policy reasons.
