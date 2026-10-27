# Regista: the pitch

Written 2026-10-26 for the submission form. Everything named runs today on the live app or from this repository. The
evidence for each claim is in `docs/criteria.md`.

## In one line

**Regista directs every touch:** it watches a football match, cuts every moment each player is on the ball, plus every
replay and highlight they appear in, then labels, explains and recaps it. Its agents let anyone find any moment by
asking, and let scouts compare players across countries below the professional level.

## Short version (for a form field)

Regista is a multi-agent system on Microsoft Foundry and Microsoft Agent Framework. It turns match footage into every
moment of every player: cut, labelled, explained, recapped and searchable in plain English. It also runs a synthetic
catalogue of footage uploaded by players and teams below the professional line: 14 competitions in 10 countries, 90
matches. Scouts compare players within their own level, and every number opens the moment behind it. It runs on Azure
Container Apps, with Cosmos DB, AI Search, Blob Storage and queues, and a Container Apps Job for the vision agents. Two
MCP servers serve the agents: Regista's own and Microsoft's Azure MCP Server. Microsoft Fabric recomputes and verifies
Regista's numbers.

## The problem

Highlight reels, edits and scouting all start with the same slow job: someone watches a full match and writes down
where each player touched the ball. Broadcasters and creators need those moments in minutes, not hours. Below the
professional line it is worse:
- players and small clubs film their own matches;
- nobody logs them;
- scouts cannot compare a U19 winger in Spain with one in Morocco, because nobody has measured either.

## What Regista does

- **Every moment, found.** The vision agents find the players, follow the ball and spot passes, shots, take-ons and
  nutmegs. Identity is kit-number first: no faces. The intelligence agents then cut every on-ball moment and every
  replay or highlight a player appears in, label each moment, score how worth watching it is, and explain why.
- **Ask for it.** "Find me his nutmegs", "now the replays": a Foundry agent answers through two MCP servers, and every
  answer plays its clips. Match recaps can be told from any player's side, and every sentence plays the moment it
  describes.
- **Four paths, one engine.**
  - Fans and creators: reels and exports.
  - Broadcasters: recaps and replay packages.
  - Scouts: a Scout view and a terminal over 127 metrics, each with its definition and source.
  - Players: upload your own match and watch it join your profile.
- **Honest numbers.**
  - Percentiles compare players only within their level, age group and gender, and every number names its pool ("97th
    percentile among 16 academy U19 men forwards").
  - Small pools and noisy samples are flagged.
  - Every number opens the moments it was counted from.

## How it is built (Microsoft and Azure)

- **Microsoft Agent Framework:** two workflows of distinct agents with typed handoffs, retries, dead-letter routing,
  checkpoints and a human review step.
  - Vision: shots, identity, "is this you?", possession, events.
  - Intelligence: ingest, validation, clips, labels, review, recap, persistence, search indexing, profiles, the
    Librarian.
- **Microsoft Foundry** (`gpt-5-mini`): labels clips and answers as the Librarian, the Scout agent and the recap writer.
  The Scout agent's and the recap's Foundry answers are checked against the numbers their tools returned, and every
  Foundry answer falls back to rules, and says so, when Foundry is unavailable.
- **MCP:** Regista's own MCP server (clips, recaps, players, catalogue) and Microsoft's **Azure MCP Server**, both
  called by the Foundry agents from inside the container.
- **Azure Container Apps** serves the app. An event-driven **Container Apps Job** (KEDA queue scaler) runs the vision
  agents on uploads that come in through **Blob Storage** and a **Storage queue**.
- **Azure Cosmos DB** (serverless) holds matches, clips, labels and human verdicts. **Azure AI Search** indexes the
  clips. **Application Insights** with Foundry tracing traces every agent step.
- **Microsoft Fabric:** the league and the catalogue are Delta tables in a lakehouse. Two Spark notebooks rewrite
  Regista's rules in SQL and recompute every number: 756 of 756 and 7,399 of 7,399 rows match.
- **GitHub Actions** runs over 1,100 tests, builds the image, smoke-tests it and deploys with a federated identity, with
  no stored secret. The app reaches Foundry, Cosmos DB, AI Search, Storage and the registry with Entra ID roles,
  with key login switched off.

## Synthetic data, by design

The rules ask for synthetic, football-realistic data, so Regista generates its own. It produces a whole league season
and a catalogue of 13 more competitions, with substitutions, penalties, aerial duels, cards and offsides, and every
player moving at 10 Hz within their own pace. A 2D broadcast renderer with director cuts and replays gives exact ground
truth for the vision layer.
- The league holds Premier League per-90 and physical bands (`docs/realism-report.md`).
- Each catalogue level is checked only against what a published source supports (`docs/catalogue/realism.md`).
- Every person, club and competition is invented.
- The vision layer is measured on matches it never saw: clip recall 0.75, precision 0.94, on rendered footage.

## Category

**Best Multi-Agent System.** The agents have distinct roles, shared state and typed handoffs, recover from failure,
and include a human in the loop, across two Microsoft Agent Framework workflows plus Foundry agents with MCP tools.

## Links

- Live app: https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io (Clips `/`, Scout `/scout`,
  Player `/me`, Studio `/studio`)
- Repository: https://github.com/Qadzilla/Regista
- Demo video: (YouTube or Vimeo link, under 2 minutes)
- Studio view key: in the submission form only, never in the repository

Built with Claude Code. GitHub Copilot was not used.
