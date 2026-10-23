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

### What's live

**Live app: https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io**. Every push to `main` that passes the tests, the image build and the in-image smoke test deploys itself.

> **Two dashboards, live since 2026-10-22:** the Product at `/` and Regista Studio at `/studio` (plan: `docs/plan-two-dashboards.md`). Judges get the Studio's view-only key with the submission; it opens the whole Studio and changes nothing.

> **Scout view, live since 2026-10-22:** `/scout` and `/players/{id}`, beside the Clip view (CLAUDE.md §2.5). Verified on revision `regista-api--d1022062451`: league, profiles, cross-match reels, deep links, the Scout agent on Instant and on Foundry (it called `search_players` through Regista's MCP server; every number in its reply came from the tool), claims refused without a key.

> **Player view, live since 2026-10-22:** `/me` (CLAUDE.md §2.6), on revision `regista-api--d1022150227`. Verified: an upload processed end to end in Azure, read back on the live app (5 moments, joined Femi Toure's profile); uploads refused without the admin token.

**Regista Player (`/me`): a player uploads their own footage.** Pick a (synthetic) player, upload a match video, and watch Regista's vision agents work on it live: shots, identity, possession, events, then clips. Answer "Is this you?" where Regista is unsure, and the match joins the player's Scout profile.
- **Event-driven in Azure, keyless:** the app stores the video in **Azure Blob Storage** and queues a message on an **Azure Storage Queue**; an **Azure Container Apps Job** (KEDA queue scaler, signing in with its managed identity) starts one execution per upload, runs the vision workflow (**Microsoft Agent Framework**) with models from a private Blob container, and writes the match back. A 3-minute upload takes about 3 minutes.
- **Synthetic footage:** `python -m regista.player.film` renders a friendly between two league clubs in the vision layer's format; both squads carry their global player ids, so the match joins profiles with no mapping. Uploads need the admin token.

**Regista Scout (`/scout`, `/players/{id}`), open to everyone.** Every player in the **Regista League**, a synthetic season (6 clubs, 30 thirty-minute matches, fixed squads), searchable like a scout would:
- **League table, filters and sort** by any of 22 per-90 stats or three ratios, with percentiles among players in the same position; **shortlist** and **compare** two or three players side by side.
- **Ask the Scout agent** ("midfielders who win the ball back"): **Instant** rules, or a **Microsoft Foundry** agent through Regista's MCP player tools (`search_players`, `get_profile`, `compare_players`), rate-limited like Ask Foundry, and it says how it understood the question.
- **Player profiles:** a summary written by Foundry with its sources, a best-of reel across matches, every stat linked to the events and clips it was counted from, a touch map, moments and matches. Each moment opens in the Clip view at that clip (`/?match=…&player=…&clip=…`), and the Clip view links back to the profile.
- **Add a match and claims:** a player adds a match (the vision layer's output) and says which player is them; the claim waits in the Studio's **Claims** tab for the operator, and a confirmed claim joins the profile through the workflow's Profile agent step. Video processing runs on the operator's machine (cloud video processing is planned). No real players' profiles: synthetic players only.

One app serves two dashboards, locally and on Azure:

**Regista, the Product (`/`), open to everyone.** For creators, scouts and fans: ask for a moment, watch it, take it away.
- It opens on the featured match (`syn_0294`: Sami Castellanos's nutmeg and goal) with a match picker and a player picker.
- **One ask box** with an engine switch: **Instant** (the rule-based Librarian, in-process, no model) or **Foundry** (the same search, then `gpt-5-mini` on Microsoft Foundry writes the reply through Agent Framework and may call its tools; rate-limited). Both go through the conversational Librarian, so follow-ups keep their context ("now the replays", "what about Ibarra?", "make that a reel").
- **How Regista answered**, under every reply: how the question was understood, which engine and model answered, and every step in order with its time. For Foundry these are the Agent Framework spans of that request: the agent, the model call, and each tool call with its MCP server (Regista's MCP server or Microsoft's Azure MCP Server → Azure AI Search).
- **A timeline** of the match from kick-off to full time, with periods, goals and every clip marked by kind; the current answer is highlighted, and a click plays the clip.
- **The stage**: the clip with its title, tags and a plain-English sentence on why it was cut; **Play reel**, **Download reel** (MP4) and **Export moments** (CSV with timecodes). **Best first / Match order** switches between a creator's and a scout's view.
- **The match recap**, told from the picked player's side: a headline and a few short paragraphs (the result, their part in the goals, their best moments, the replays they are in), every sentence a link that plays its moment on the stage, and **Play recap reel**. **Instant** (Regista's rules) or **Foundry** (`gpt-5-mini` writes it from the same facts; Regista keeps only sentences that cite a moment and use the match's own numbers, and says what it left out). Profiles link each match's recap, and `/me` shows "Your match recap" after an upload. Built, not yet deployed.
- Badges say where a moment came from: **Labelled by Microsoft Foundry** (the library matches) and **Cut from video** (the vision demo match).
- **How it works**: the two layers, the agent workflow, which Azure service does what on this deployment (from `/api/health`), and the realism report.

**Regista Studio (`/studio`), the control room, behind a key.** The view key sees everything and changes nothing; the admin key can also review, upload and retrain. Judges get a view key in the submission; it is never in this repository. Tabs: Overview (a to-do list, health, image and revision, Ask and Chat usage against their limits, Cosmos DB and Search document counts, render cache), Review queue, Who's who, Training, Runs, Jobs and Console. The Studio API and the keys are in the branch; the page is being finished.
- **On the live app**, with the view key: everything above read-only, including the demo vision match's Who's who questions and crops. Answering them needs the identity result, which stays on the machine that ran the vision layer, so the live app refuses (409) and says why. Runs show no pipeline traces for the shipped matches (their `agents/` folders are not in the image), and Jobs says it is local only.
- **Locally**: everything, plus answering Who's who on matches a local vision run produced and the vision jobs (run, evaluate, train, learn from Who's who answers), because the footage and the vision models never leave the machine.

**The library: four matches, all with video.** `syn_0294`, the featured sample (rules labeller); `syn_0141` and `syn_0142`, uploaded through the token-gated cloud workflow, labelled by Foundry, stored in Cosmos DB and indexed in Azure AI Search, with their event streams regenerated from their seeds and Foundry's labels exported read-only from Cosmos DB (`infra/export-library.py`, which checks every clip against the clip rule); and `vis_0201`, the vision layer's output on one of Regista's rendered development matches, run offline (in the image only, not in Cosmos DB or Search). Tracing goes to Application Insights.

**Run from this repository, not on the live app:** the vision layer (video in, event stream out, including event spotting and the full 90-minute run), because it needs footage and trained models that stay private. The demo video shows it running.

**Running in Azure** (subscription Azure for Students, resource group `regista-rg`, France Central; set up on 2026-10-21 with `infra/provision.sh` and `infra/deploy-app.sh`, verified the same day on revision `regista-api--d1021183822`):

| Technology | What it does in Regista |
|---|---|
| **Microsoft Agent Framework** | The whole pipeline is an Agent Framework workflow (`regista.agents.workflow`): ingest fans out to validator and possession, fans in at clip, then label, review, persist, indexer (when Search is configured), librarian. Typed handoffs, shared state, retries, dead-letter routing, checkpointing, and a human-in-the-loop pause (`request_info`). Diagram: `docs/workflow.md` |
| **Microsoft Foundry** (project `regista`, `gpt-5-mini` deployment) | The Label agent titles, tags, scores, and explains every clip; the Librarian agent answers questions and reports the tools it used. Sample output: `docs/evidence/foundry-labels-syn_0294.jsonl` (recorded before schema 0.1.1, so it carries the old `cl_000001`-style ids and `schema_version` 0.1.0) |
| **MCP, two servers** | Regista's own (`regista.mcp_server`: search_clips, search_library, derive_clips, validate_stream, render_clip, list_matches) and Microsoft's **Azure MCP Server** (`azmcp`, read-only, Cosmos DB and Azure AI Search namespaces). The Foundry Librarian calls both: from the CLI with `--cloud --query` (Cosmos DB and Search tools), and from the app (the Foundry engine of the ask box, `POST /api/matches/{id}/chat`, and `POST /api/matches/{id}/ask`), where it holds only read-only public tools: Regista's search tools and the Azure MCP Server's AI Search namespace. Both servers start inside the container image, checked by a CI smoke test on every build. Verified on the live app on 2026-10-21 (revision `regista-api--d1021183822`): an Ask Foundry question called `search_index_query` through the Azure MCP Server inside the container. The image smoke test also checks that the dashboards' static files and the four sample matches are in the image |
| **Azure AI Search** (free tier, index `regista-clips`) | The indexer role writes every labelled clip; `search_library` answers questions across every match |
| **Azure Cosmos DB** (serverless, `matches` / `clips` / `labels` / `annotations`) | The Persist agent upserts every match, clip, and label; human verdicts and the learned model live in `annotations` |
| **Application Insights + Foundry tracing** | Agent Framework's OpenTelemetry spans for every agent, model call, tool call, and workflow step, on the Foundry project's Tracing page. Spans come from the live app as well as local runs: verified on 2026-10-21 (revision `regista-api--d1021183822`): Ask, Chat and two uploads traced from the container (managed identity, `invoke_agent regista-librarian`, `invoke_agent regista-librarian-chat`, `chat gpt-5-mini`, `execute_tool search_index_query`, Cosmos DB writes) |
| **Azure Container Apps** (one replica) | Serves the app and its API (the Product and the Studio). Token-gated uploads run the cloud workflow (Foundry labelling, Cosmos DB, Search indexing) under the app's managed identity. Uploaded matches live on local disk, which a restart wipes, so the app also lists every match Cosmos DB holds and serves its clips and labels from there (no video without the event stream). Foundry questions are open to everyone and rate-limited |
| **Azure Container Registry + GitHub Actions** | `build-image.yml` runs the tests, builds the image and smoke-tests the agent tools inside it on every push; on `main` it pushes the image and deploys it, signing in to Azure with a federated identity (OpenID Connect: no password or key stored in GitHub), and the run waits until the new revision is the ready one |
| **Microsoft Entra ID** | The app and the CLI reach Foundry, Cosmos DB, and AI Search through role assignments (`DefaultAzureCredential`: `az login` locally, managed identity in Container Apps); the code uses no keys for them, and key login is switched off on Cosmos DB and AI Search. The Container App pulls its image with its own identity (AcrPull; the registry has no admin user), and GitHub Actions deploys with a federated identity. The secrets that remain are the admin key (writes), the Studio view key (set once with `infra/deploy-app.sh`, since CI deploys change only the image) and the Application Insights connection string, all Container Apps secrets |

**The vision layer (private, v0).** `python3 -m regista.vision run VIDEO --roster MATCH_DIR --out OUT --workflow` watches a broadcast video and writes the same event stream: shot segmentation and classification, player and ball detection, team and kit-number identity, tracking, possession, and **event spotting** (passes, shots, saves, goals, tackles, interceptions, carries, take-ons, nutmegs), as a second Agent Framework workflow. Clips cut from video therefore carry event tags, so "find me X doing a nutmeg" works on footage, not only on generated data. It is trained and measured only on Regista's own rendered broadcast, where the generator gives exact ground truth. The first evaluation matches were used during development, so they are reported as a development set. Three fresh matches with new clubs and kit colours far from every training kit were scored with frozen models only, on footage without the renderer's on-screen captions, name labels or ring on the ball holder: from video alone, the clips it cuts for all 22 starters recover 75% of the true clips at 94% precision, with 99.0% of named players named correctly. Events from video on the same matches: passes 1.00 precision / 0.76 recall, shots 0.80 / 0.80, the one goal found and 3 of 4 saves; nutmegs 0.67 / 0.67 (4 of 6), take-ons 0.82 / 0.50 and tackles (recall 0.44) are the weak spots. Two leaks were found and fixed along the way, and the write-up says so: an earlier shot model had been reading the captions to recognise replays, and the renderer still drew the ball holder's name and a ring on vision footage (the models did not lean on them, apart from the event spotter, which was retrained; the Who's who crops had printed the answer). **Who's who:** where the identity agent is unsure, it asks a person (a paused Agent Framework run, the Who's who panel when the app runs locally, or the terminal), with a crop and its top candidates; answers correct identity, recompute the match, and fine-tune the kit-number reader. With 12 simulated answers per development match, clip recall rose from 0.76 to 0.83 and precision from 0.92 to 0.95. **Full length:** on a fresh 90-minute match scored once with frozen models, the whole pipeline ran in about a third of real time, found all 5 goals, passes at 0.97 / 0.90 and shots at 0.91 / 0.78, and cut clips for all 22 starters at 0.86 recall / 0.94 precision. All numbers are in `docs/vision.md`; they come from easy synthetic footage and say nothing yet about real broadcasts, and the same document lists what changes for real footage.

**Learning from people.** When the Label agent is unsure (its rules prior and the model disagree, or a score sits on the keep/drop line) the workflow pauses and asks. Verdicts come from Keep/Drop in the app (the Studio's review queue), the `--review` terminal prompt, or the review API, and are stored as human annotations. A watchability model is retrained from them and becomes the Label agent's prior. This is learning from human feedback, not reinforcement learning.

**Planned, not wired:** Microsoft Fabric (needs a work or school tenant), Azure AI Vision and Video Indexer for the private vision layer, Azure AI Speech and Translator. GitHub Copilot Agent Mode is not used; the project is built with Claude Code.

## Quickstart

```bash
pip install -e ".[dev,vision]"          # the full local suite and pipeline; add ,cloud for Azure: ".[dev,vision,cloud]"
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

**The service** (`regista.api`, FastAPI) serves the Product at `/` and the Studio at `/studio` (`regista.studio_api`), lists matches, filters clips by player, tag, reason, and watchability, runs the Librarian at `/api/matches/{id}/search?q=`, renders any clip, a reel of up to 12 clips (`/reel.mp4`) or the whole broadcast to MP4 on demand with a cache, exports moments as CSV (`/moments.csv`), serves the realism report, and accepts an uploaded `events.jsonl` which it validates and pushes through the agent pipeline. Its review endpoints (`GET`/`POST /api/matches/{id}/review`, `POST /api/matches/{id}/clips/{clip_id}/verdict`, `/api/feedback`, `POST /api/feedback/train`) take human verdicts and retrain the watchability model. The `Dockerfile` packages it for Azure Container Apps. **The agent pipeline** is a Microsoft Agent Framework workflow: Ingest, Validator and Possession in parallel, Clip, Label, Review, Persist, Indexer (when Search is configured), and Librarian, over shared state with typed handoffs, retries, a per-attempt trace, a dead-letter executor, a human-in-the-loop pause, and checkpoints. Locally the Label and Librarian agents are rule-based (Label uses the model learned from verdicts when one exists); with `--cloud` they run on Foundry `gpt-5-mini`. `--engine orchestrator` runs the original hand-written orchestrator, kept as a reference. **The Librarian** answers plain-English questions over a match's labelled clips: player by name (typos tolerated), kit number, team, or position word; actions by football vocabulary ("meg", "strike", "beats his man"); minute windows; "replays of"; "top 3". It prints how it understood the query and an explanation per result. **The MCP server** exposes the Librarian (`search_clips`), cross-match search through Azure AI Search (`search_library`), the clip rule, the validator, the clip renderer, and the match list as tools over stdio, so any MCP host can drive Regista. **The realism report** compares a generated match with Premier League per-90 bands; the generator's `realistic` profile is tuned to sit inside them, the `demo` profile deliberately packs a 3-minute sample with action.

The renderer turns the event and track streams into a broadcast-style 1280x720 MP4: a perspective pitch with kit-coloured numbered players, a camera that follows the ball, replays at the director's slow-motion speed with a REPLAY badge and a different framing per angle, player closeups, crowd shots, a highlights package, a live scoreboard and clock, and timed captions for goals, shots, nutmegs, skill moves, fouls, and saves. The clip cutter writes one video per clip plus a best-first reel with title cards. A 3-minute match renders in about 15 seconds on an 8-core Mac. Nothing in the output comes from real footage.

The generator also does two halves (`--periods 2`), custom clubs (`--home "Name,SHORT,#hex"`), and a `realistic` profile for statistics. It writes `events.jsonl` (match header, camera segments, possessions, events, appearances, human annotations), `tracks.jsonl` (sampled positions), and `clips.jsonl` (the clip rule applied to one player, with labels and watchability scores). The contract is documented in [data/synthetic/README.md](data/synthetic/README.md).

## Status

As of 2026-10-21. Runs locally with no cloud dependency: the event-stream contract (schema 0.1.1, validated), a synthetic generator with a demo profile and a realistic profile that sits inside Premier League per-90 bands, the clip rule and labeller, a 2D broadcast renderer and clip cutter, the Librarian, an MCP server, the Agent Framework workflow with human review and a watchability model learned from verdicts, the FastAPI service with the Product and the Studio, and the vision layer v0 on rendered footage. In Azure: Foundry labelling and Q&A through Agent Framework (the Librarian using Microsoft's Azure MCP Server beside Regista's own), Cosmos DB, AI Search, Application Insights tracing, and the service on Container Apps (see the table above; `python3 -m regista.agents … --cloud` runs the cloud pipeline locally against the same resources). See `docs/architecture.md` for how each piece maps to Azure, `docs/gap-analysis.md` for what changed against the judging criteria, and `docs/demo-storyboard.md` for the video plan. Not yet: the vision layer on real broadcast footage, the Azure AI Vision OCR backend, real human verdicts from Zaid to train the watchability model on, and the demo video itself.

## Licence

MIT. No broadcast footage is included in this repository.
