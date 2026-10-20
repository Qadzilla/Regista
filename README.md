# Regista

**Regista directs every touch.** Every touch. Every replay. Every player. Found instantly.

*Regista* (Italian, "director"): the deep-lying playmaker who sees the whole pitch and directs every move, and the word for a film director. Both meanings are the product.

Regista is an AI system for the Microsoft × Premier League **Inside the Game: Developer Hackathon** (October 2026). It watches a full 90-minute football broadcast, learns to recognise players, cuts every moment a chosen player is on the ball plus every replay and highlight they appear in, labels those moments, and lets you find them through a chatbot:

> "Find me Pogba doing a nutmeg."

## Who it is for

- **Content creators** building highlight reels and edits.
- **Scouts and analysts** who need every on-ball moment of a player, instantly.
- **Broadcasters and studios** producing per-player replay packages.
- **Fans** who want a personalised reel of their favourite player.

## How it works

```
Broadcast feed ──▶ Ingest ──▶ Interpret ──▶ Explain ──▶ Render ──▶ Personalize
                   segment     track +       label +     cut        chatbot
                   replays     identify      score       clips      search
                               players       moments
```

The system emits a **synthetic, football-realistic event dataset** (touches, positions, replay markers, clip labels) and a searchable clip library. See [CLAUDE.md](CLAUDE.md) for the full project source of truth, hackathon criteria, and architecture.

## Microsoft and Azure technologies

**Running in Azure today** (resource group `regista-rg`, provisioned by `infra/provision.sh`):

| Technology | What it does in Regista |
|---|---|
| **Microsoft Agent Framework** | The whole pipeline is an Agent Framework workflow (`regista.agents.workflow`): ingest fans out to validator and possession, fans in at clip, then label, review, persist, indexer, librarian. Typed handoffs, shared state, retries, dead-letter routing, checkpointing, and a human-in-the-loop pause (`request_info`). Diagram: `docs/workflow.md` |
| **Microsoft Foundry** (project `regista`, `gpt-5-mini` deployment) | The Label agent titles, tags, scores, and explains every clip; the Librarian agent answers questions and reports the tools it used. Sample output: `docs/evidence/foundry-labels-syn_0294.jsonl` |
| **MCP, two servers** | Regista's own (`regista.mcp_server`: search_clips, search_library, derive_clips, validate_stream, render_clip, list_matches) and Microsoft's **Azure MCP Server** (read-only Cosmos DB and Azure AI Search tools). The Foundry Librarian calls both |
| **Azure AI Search** (free tier, index `regista-clips`) | The indexer role writes every labelled clip; `search_library` answers questions across every match |
| **Azure Cosmos DB** (serverless, `matches` / `clips` / `labels` / `annotations`) | The Persist agent upserts every match, clip, and label; human verdicts and the learned model live in `annotations` |
| **Application Insights + Foundry tracing** | Agent Framework's OpenTelemetry spans for every agent, model call, tool call, and workflow step, on the Foundry project's Tracing page |
| **Azure Container Apps** | Serves the viewer and API; uploads run the cloud workflow under the app's managed identity |
| **Azure Container Registry + GitHub Actions** | `build-image.yml` builds the image on every push to main |
| **Microsoft Entra ID** | Keyless auth everywhere: role assignments for the developer and the app; no keys in code or containers |

**Learning from people.** When the Label agent is unsure (its rules prior and the model disagree, or a score sits on the keep/drop line) the workflow pauses and asks. Verdicts come from the viewer's Keep/Drop buttons, the `--review` terminal prompt, or the review API, and are stored as human annotations. A watchability model is retrained from them and becomes the Label agent's prior. This is learning from human feedback, not reinforcement learning.

**Planned, not wired:** Microsoft Fabric (needs a work or school tenant), Azure AI Vision and Video Indexer for the private vision layer, Azure AI Speech and Translator. GitHub Copilot Agent Mode is not used; the project is built with Claude Code.

## Quickstart

```bash
pip install -e ".[dev]"
python3 -m pytest -q
python3 -m regista.synth --minutes 3 --seed 294 --player t_home_09 --out data/synthetic/sample
python3 -m regista.validate data/synthetic/sample/syn_0294
python3 -m regista.render data/synthetic/sample/syn_0294 --out docs/demo/syn_0294.mp4
python3 -m regista.render.clips data/synthetic/sample/syn_0294 --player t_home_09 --out docs/demo/clips_t_home_09
python3 -m regista.librarian data/synthetic/sample/syn_0294 "find me Castellanos doing a nutmeg"
python3 -m regista.mcp_server --list-tools
python3 -m regista.synth.report data/synthetic/sample/syn_0294
python3 -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
uvicorn regista.api:app                      # then open http://localhost:8000
docker build -t regista . && docker run -p 8000:8000 regista
```

**The service** (`regista.api`, FastAPI) serves the clip viewer at `/`, lists matches, filters clips by player, tag, reason, and watchability, runs the Librarian at `/api/matches/{id}/search?q=`, renders any clip or the whole broadcast to MP4 on demand with a cache, serves the realism report, and accepts an uploaded `events.jsonl` which it validates and pushes through the agent pipeline. The `Dockerfile` packages it for Azure Container Apps. **The agent pipeline** runs seven roles (Ingest, Validator, Possession, Clip, Label, Persist, Librarian) over shared state with declared handoffs, retries, a per-attempt trace, and a dead-letter file; it is rule-based v0 today, built so Foundry-backed agents slot into the same roles. **The Librarian** answers plain-English questions over a match's labelled clips: player by name (typos tolerated), kit number, team, or position word; actions by football vocabulary ("meg", "strike", "beats his man"); minute windows; "replays of"; "top 3". It prints how it understood the query and an explanation per result. **The MCP server** exposes the Librarian, the clip rule, the validator, and the clip renderer as tools over stdio, so any MCP host can drive Regista. **The realism report** compares a generated match with Premier League per-90 bands; the generator's `realistic` profile is tuned to sit inside them, the `demo` profile deliberately packs a 3-minute sample with action.

The renderer turns the event and track streams into a broadcast-style 1280x720 MP4: a perspective pitch with kit-coloured numbered players, a camera that follows the ball, replays at the director's slow-motion speed with a REPLAY badge and a different framing per angle, player closeups, crowd shots, a highlights package, a live scoreboard and clock, and timed captions for goals, shots, nutmegs, skill moves, fouls, and saves. The clip cutter writes one video per clip plus a best-first reel with title cards. A 3-minute match renders in about 15 seconds on an 8-core Mac. Nothing in the output comes from real footage.

The generator also does two halves (`--periods 2`), custom clubs (`--home "Name,SHORT,#hex"`), and a `realistic` profile for statistics. It writes `events.jsonl` (match header, camera segments, possessions, events, appearances, human annotations), `tracks.jsonl` (sampled positions), and `clips.jsonl` (the clip rule applied to one player, with labels and watchability scores). The contract is documented in [data/synthetic/README.md](data/synthetic/README.md).

## Status

Day 1. Everything below runs locally with no cloud dependency: the event-stream contract (schema-validated), a synthetic generator with a demo profile and a realistic profile that sits inside Premier League per-90 bands, the clip rule and labeller, a 2D broadcast renderer and clip cutter, the Librarian, an MCP server, and a v0 multi-agent pipeline with retries and dead letters. Also local: a FastAPI service with the clip viewer and a Dockerfile for it. See `docs/architecture.md` for how each piece maps to Azure and `docs/demo-storyboard.md` for the video plan. In Azure: Foundry labelling and Q&A through Agent Framework, Cosmos DB persistence, and the service on Container Apps (see the table above; `python3 -m regista.agents … --cloud` runs the cloud pipeline locally against the same resources). Not yet: the private vision layer, the demo video itself.

## Licence

MIT. No broadcast footage is included in this repository.
