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

Seven roles run today in `src/regista/agents/` as a deterministic v0. They are the roles from the product design (CLAUDE.md §3.1), minus Identity, which lives in the vision layer and is played by the generator for the demo.

| Role | Inputs → outputs | Today (rule-based) | With Microsoft Agent Framework + Foundry |
|---|---|---|---|
| **Ingest** | `match_dir` → `stream`, `index`, `match` | reads and indexes `events.jsonl` | same; fed by Event Hubs / Fabric Eventstream instead of a file |
| **Validator** | `match_dir` → `validation` | JSON Schema validation, blocks on invalid events | same, as a tool the orchestrator calls first |
| **Possession** | `index`, `player_ids` → `on_ball` | on-ball windows per player with their camera segment | same |
| **Clip** | `index`, `player_ids`, `on_ball` → `clips` | the clip rule (`regista.clips.cut_clips`) | same rule; an LLM agent proposes extra cut points (pre-roll by context) |
| **Label** | `index`, `clips` → `labels` | tags, titles, watchability table, explanation (`rules-v0`) | Foundry model (gpt-4o class) labels and explains; the table becomes a prior; human annotations feed evaluation in Foundry |
| **Persist** | `match_dir`, `clips`, `labels` → `clips_path` | writes `clips.jsonl` | writes to Cosmos DB (partition `match_id`) and the AI Search index |
| **Librarian** | `clips_path`, `queries` → `answers` | deterministic parser + ranking (`regista.librarian`) | Foundry agent that calls the `search_clips` MCP tool and talks to the user; multilingual via Azure AI Translator |

What the orchestrator guarantees, and the tests prove: distinct roles with declared handoffs (`missing inputs` is a recorded skip, not a crash), shared state passed along, retries on retryable errors, a per-attempt `trace.jsonl`, and a `dead_letter.jsonl` with the failing agent's inputs. The Agent Framework version keeps the same role names, state keys, and trace format so dashboards and tests carry over.

## MCP tools

`python -m regista.mcp_server` serves these over stdio (tested end to end with the MCP client):

| Tool | What it does |
|---|---|
| `search_clips(match_dir, query, limit)` | the Librarian: parse, rank, explain |
| `derive_clips(match_dir, player_id)` | the clip rule and labeller for one player |
| `validate_stream(path)` | schema validation of a match directory or one file |
| `render_clip(match_dir, clip_id, out_dir)` | cut one clip to MP4 with its title card |
| `list_matches(root)` | the matches available |

Any MCP host can drive Regista with these: Copilot Agent Mode in VS Code, a Microsoft Agent Framework agent, or Claude. Azure MCP Server sits beside it for the Azure-side resources (Cosmos DB, Blob, Fabric) once they exist.

## Services per pipeline stage

**Running** marks what code calls in Azure today; everything else is planned.

| Stage | Running today | Planned next |
|---|---|---|
| Ingest | file read of `events.jsonl`; API upload on Container Apps (**running**) | Blob Storage for feeds; Functions + Event Grid triggers; AI Video Indexer for scene cuts |
| Interpret | synthetic generator (local) | AI Vision (detection, kit-number OCR) and tracking models in Foundry; Event Hubs → Fabric Eventstream → Lakehouse |
| Explain | `FoundryLabelAgent`: `gpt-5-mini` on **Microsoft Foundry** via **Agent Framework**, rules-v0 as prior and fallback (**running**) | Foundry evaluations against human annotations from the review tool |
| Render | `regista.render` inside the Container Apps service, on-demand with a local cache (**running**) | Container Apps jobs for batch renders; Blob + CDN for the cache |
| Review | `ReviewExecutor`: the workflow pauses with `request_info` on clips the Label agent is unsure about; verdicts become human annotations and retrain the watchability model (**running**) | Foundry evaluations scoring each labeller against the human verdicts |
| Persist | `CosmosPersistAgent`: **Cosmos DB** serverless, `matches` / `clips` / `labels` / `annotations` (**running**) | |
| Index | `SearchIndexAgent` (role `indexer`): every labelled clip into **Azure AI Search** `regista-clips` (**running**) | Vector search over clip summaries |
| Personalize | `FoundryLibrarianAgent` on Foundry calling two MCP servers: Regista's (search_clips, search_library) and Microsoft's **Azure MCP Server** (Cosmos DB and Search queries); viewer and API on **Container Apps** (**running**) | AI Translator and Speech for languages |
| Observe | Agent Framework OpenTelemetry → **Application Insights** → Foundry **Tracing** (**running**) | Alerts on dead letters |

## Deployment on Azure Container Apps (running)

```
resource group regista-rg (East US; Cosmos DB in East US 2, where capacity was available)
├── regista-foundry-<id>   Microsoft Foundry resource, project "regista", deployment gpt-5-mini (GlobalStandard)
├── regista-cosmos-<id>    Cosmos DB serverless, database "regista", containers matches/clips/labels (/match_id)
├── <registry>acr          Container Registry (Basic); images pushed by GitHub Actions build-image.yml
├── regista-env            Container Apps environment + Log Analytics workspace
└── regista-api            Container App: uvicorn regista.api:app on :8000, 1-2 replicas, external ingress,
                           system-assigned identity with Foundry User (project) and Cosmos data-contributor roles,
                           env FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL, REGISTA_COSMOS_ENDPOINT, REGISTA_CLOUD=1
```

Provision with `infra/provision.sh` (idempotent; writes `.env`), build the image by pushing to `main`, deploy with `infra/deploy-app.sh`. Free-trial subscriptions cannot run ACR Tasks, which is why the image builds on GitHub Actions rather than with `az containerapp up --source`.

## What is deliberately not here

- No real footage, anywhere. The vision layer is designed and its output contract is enforced, but no model has been trained; the generator stands in for it.
- Only Foundry, Agent Framework, Cosmos DB, Container Apps, and Container Registry are running. Every other service above is planned until code runs against it.
- Face recognition is not the identification path. Kit number, team colour, and tracking continuity are, for both robustness and policy reasons.
