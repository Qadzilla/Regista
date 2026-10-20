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

## Services per pipeline stage (planned; nothing below runs yet)

| Stage | Component today | Azure target |
|---|---|---|
| Ingest | file read | Blob Storage for feeds; Azure Functions + Event Grid to trigger; Azure AI Video Indexer for scene cuts |
| Interpret | synthetic generator | Azure AI Vision (detection, OCR for kit numbers) and custom tracking models in Microsoft Foundry; event stream to Event Hubs → Fabric Eventstream → Lakehouse |
| Explain | `label_clips` | Foundry-hosted model behind the Label agent; evaluation with Foundry evals against human annotations |
| Render | `regista.render` | Azure Container Apps job workers (CPU), output to Blob; the service's on-demand render cache becomes Blob + CDN |
| Personalize | Librarian, viewer, API | Foundry agent + Agent Framework orchestration; Azure AI Search over labels; Azure AI Translator and Speech for languages; viewer on Container Apps |

## Demo deployment on Azure Container Apps (planned)

```
Container Apps environment
├── regista-api        image from Dockerfile; uvicorn regista.api:app; 1–3 replicas; ingress on :8000
│                      env REGISTA_DATA=/mnt/data/matches  REGISTA_CACHE=/mnt/data/clips
├── regista-render     Container Apps job: python -m regista.render / render.clips on queue messages
└── storage mount      Azure Files share for matches and the clip cache (Blob + CDN later)

Cosmos DB (serverless)   clip / label / match documents, partition key match_id
Azure AI Search          index over label.title, summary, explanation, tags
Microsoft Foundry        project with the Label model deployment and the Librarian agent
Agent Framework          orchestrator hosting the seven roles; MCP client to regista.mcp_server and Azure MCP Server
Fabric                   Eventstream + Lakehouse for event/possession/segment streams; notebooks for the realism report
```

The container already builds from the `Dockerfile` in the repo root and serves the viewer, the API, on-demand rendering, uploads, and the agent pipeline with no cloud dependency, so the Container Apps step is a deployment, not a rewrite.

## What is deliberately not here

- No real footage, anywhere. The vision layer is designed and its output contract is enforced, but no model has been trained; the generator stands in for it.
- No Azure resource exists yet. Every service above is marked planned until code runs against it.
- Face recognition is not the identification path. Kit number, team colour, and tracking continuity are, for both robustness and policy reasons.
