# How Regista meets the judging criteria

Each criterion of the Inside the Game hackathon (five, 20% each), what Regista does for it, and where a judge can check.
"Live" means the app at https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io serves it today.
Everything named here runs; what is planned is listed as planned. (Replaces `docs/gap-analysis.md`, kept in git history.)

## 1. Technological implementation

| Hero technology | How Regista uses it | Check |
|---|---|---|
| **Microsoft Foundry** (`gpt-5-mini`) | Labels clips; answers as the Librarian (Ask Foundry, Chat), the Scout agent, the match recap, the Profile agent's summaries; every Foundry answer falls back to rules and says so | live: Foundry engine on `/`, `/scout`, the Recap panel; `src/regista/cloud/foundry.py` |
| **Microsoft Agent Framework** | Two workflows: intelligence (ingest → validator and possession → clip → label → review → recap → persist → indexer, with Azure → profiles → librarian) and vision (shots → identity → is-this-you → possession → events → writer) | `src/regista/agents/workflow.py`, `src/regista/vision/agents.py`, `docs/workflow.md` |
| **Azure MCP** | Microsoft's Azure MCP Server runs inside the container beside Regista's own MCP server (10 tools); the Foundry Librarian calls both | live: Ask Foundry lists `search_index_query`; `python -m regista.mcp_server --list-tools` |
| **Azure Apps and AI services** | Container Apps (the app, one replica) and an event-driven **Container Apps Job** (vision, KEDA queue scaler); Blob Storage and a Storage queue; Application Insights with Foundry tracing | `infra/`, `docs/architecture.md` ("Deployment", "The views") |
| **Azure databases** | Cosmos DB serverless (matches, clips, labels, human annotations); Azure AI Search index `regista-clips` | `src/regista/cloud/` |
| **Microsoft Fabric** | The season and the Player-view uploads in a Fabric lakehouse (9 Delta tables in OneLake); a Fabric notebook recomputes the league leaders, and Regista checks they match its own. 756 of 756 rows matched on 2026-10-23. After the league was regenerated (2026-10-24), the check first matched 328 of 756 (the notebook still ranked percentiles by the old rule); with the notebook on Regista's rule, 756 of 756 matched again that day. Generator 0.7.1 (2026-10-24, the same season on Linux and macOS) regenerated the season since; the lakehouse holds the 0.7.0 season until it is pushed and checked again. `tests/test_fabric.py` applies the notebook's rule offline and compares it with the profiles | `python -m regista.season.fabric check`; `docs/architecture.md` ("Microsoft Fabric") |
| **GitHub CLI** | Provisioning sets the deploy variables with `gh`; CI on GitHub Actions deploys with a federated identity (no stored secret) | `infra/provision.sh`, `.github/workflows/build-image.yml` |
| GitHub Copilot Agent Mode, GitHub SDK | **Not used.** Regista is built with Claude Code; nothing claims otherwise | – |

**Code quality.** 763 tests (`python3 -m pytest -q`), run with the image build and an in-image smoke test on every push,
plus 13 slow ones (`python3 -m pytest -q -m slow`: whole seasons regenerated) in a nightly workflow;
a schema-validated contract between the layers (`data/synthetic/README.md`); one-command provisioning (`infra/SETUP.md`);
keyless Azure (Entra ID roles, shared-key login off on Cosmos DB, Search and Storage).

**Synthetic data quality.** The generator's realistic profile sits inside Premier League per-90 bands
(`docs/realism-report.md`); a 2D broadcast renderer with director cuts and replays gives exact ground truth; the Regista
League is a full synthetic season with fixed squads, generated in league mode. Hidden player ratings drive outcomes and
are never served by any API, MCP tool or page. Schema 0.2.0 adds substitutions, penalties, aerial duels, red cards and
offsides, and every player moves at 10 Hz within their own pace (`regista.synth.physical`). On the committed season all 13
event bands and all 14 physical bands hold; over six pooled seasons every band holds, the league-mode, leader and team
bands included (`python3 -m regista.synth.report --league [--repeat 6]`). Split-half reliability is measured
(`python3 -m regista.season.audit`), and noisy stats are flagged as such. The vision layer is measured against that truth on matches it never
saw (`docs/vision.md`: fresh matches with the v4 models, clips 0.75 recall / 0.94 precision; a full 90-minute match, all 5 goals).

**The Scout terminal's engine** (part A, built on `feature/terminal-engine`, not yet deployed; its screens are next):
127 player metrics and 19 team-style metrics, each with its definition, rule and source (FBref, Opta, StatsBomb,
Wyscout; xT fitted on the season), percentiles among position peers (FBref's rule), and the events and clip behind every
number. Served read-only by `regista.terminal_api` (`/api/metrics`, `/api/terminal/screen|rank|scatter`,
`/api/players/{id}/metrics|form|similar`, `/api/teams`). Check: `tests/test_metrics.py`, `docs/scout-terminal/build/`.

## 2. Agentic design and innovation

- **Distinct roles with shared state and handoffs**: the two workflows above, typed handoffs, fan-out and fan-in,
  retries, dead-letter routing, checkpoints (`tests/test_workflow.py`).
- **People in the loop**: the workflow pauses (`request_info`) for clips the Label agent is unsure about and for
  "is this you?" identity questions; answers become annotations and retrain the watchability model and the kit-number
  reader.
- **Agents across the cloud**: an upload on `/me` is handed from the app to a Container Apps Job through a queue; the
  vision workflow runs there and hands the match back; the Profile agent adds it to the player's profile.
- **Grounded answers**: the Scout agent and the recap check that every number in a Foundry answer came from a tool or
  the facts; every recap sentence cites its moment; every answer shows its trace (agent, model call, each tool call).
- Not used: A2A.

## 3. Real-world impact

Content creators, scouts, broadcasters and fans each get a view: Clips (any moment, reels, CSV export), Scout (every
player across a season, verified stats, compare, shortlist), Player (a player's own footage becomes a profile), Studio
(operating it). Production-shaped: CI/CD to Azure, keyless, token-gated writes, bounded public rendering, a read-only key
for reviewers, tracing.

## 4. UX and presentation

- Four views with one header switch, plain football words (no ids, no "per 90" jargon in fans' views), phone width
  (375 px) checked, keyboard access, every answer explained.
- The demo video (under two minutes) follows `docs/demo-storyboard.md`.

## 5. Adherence to category

Entered for **Best Multi-Agent System**: distinct agent roles (ingest, validator, possession, clip, label, review,
recap, persist, indexer, profile, librarian; vision: shots, identity, possession, events, writer; the Scout agent),
shared state, handoffs across a queue to a cloud job, failure recovery (retries, dead letters, rules fallbacks), all on
Microsoft Agent Framework.

## Planned, not built

Azure AI Vision and Video Indexer for the vision layer; Azure AI Speech and Translator (the app is English only, by
decision); a Fabric data agent; the Scout terminal's screens (part B: to be built in the sandbox, then ported into Scout as a
Terminal section); real broadcast footage (the vision layer is trained and measured on rendered footage).
