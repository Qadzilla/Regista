# Regista — Project Source of Truth

> **Name:** *Regista* (Italian: "director"). In football, the regista is the deep-lying playmaker who sees the whole pitch and directs every move. In cinema, the regista is the film director. Regista directs every touch.

> **Regista directs every touch.** Every touch. Every replay. Every player. Found instantly.
>
> Regista is an AI system that watches a full 90-minute football broadcast, learns to recognise every player, cuts every moment a chosen player is on the ball (plus every replay and highlight they appear in), labels those moments, and lets you find them through a chatbot: *"find me Pogba doing a nutmeg."*

This file is the heart and soul of the project. It is the first general thought, not the final idea; we will improve it over time. Update it whenever the idea, the architecture, or the hackathon strategy changes. Claude reads this at the start of every session.

---

## 1. The hackathon we are competing in

**Inside the Game: Developer Hackathon** — Microsoft × Premier League, October 2026.

| Milestone | Deadline (Pacific Time) |
|---|---|
| Registration closes | **October 20, 2026, 12:00 PM** |
| Submissions close | **October 27, 2026, 11:59 PM** |
| Judging | October 27 – November 10, 2026 |
| Winners announced | By November 20, 2026 |

- Rules: https://github.com/microsoft/insidethegamehackathon/blob/main/OFFICIAL%20RULES.md
- Skilling playlists: https://aka.ms/aisn/hack
- Platform (registration + submission, Microsoft sign-in): https://aka.ms/insidethegame
- Reactor session (on demand): "Build AI-powered soccer insights apps with AKS and ACA" — https://developer.microsoft.com/en-us/reactor/events/27536/

### 1.1 Judging criteria — these are truth

Stage One is pass/fail: the project must fit the theme and use the required Microsoft technologies. Stage Two scores five criteria at **20% each**. Ties are broken by the highest score on the **first** criterion, then the next, so order matters.

1. **Technological Implementation** — use of the named "hero technologies" plus clean, documented code and synthetic data quality.
2. **Agentic Design and Innovation** — agent orchestration, MCP integration, multi-agent collaboration.
3. **Real-World Impact** — production-deployable, meaningful for broadcasters and fans.
4. **UX and Presentation** — intuitive UI, a balanced frontend and backend, and a demo video that sells it.
5. **Adherence to Category** — matches the category you enter.

**Hero technologies named in the rules:** Microsoft Foundry, Microsoft Agent Framework, Azure MCP, GitHub Copilot Agent Mode, Microsoft Fabric, GitHub SDK, GitHub CLI, Azure Apps and AI Services, Azure databases. Every architectural decision should be able to point at one of these.

### 1.2 Prizes and categories

A project can win **one Grand Prize and one Category Prize**.

| Prize | Cash per team member | What judges look for |
|---|---|---|
| Grand Prize, 1st | $4,000 + Premier League match ticket | Best overall, innovative use of the Microsoft AI platform stack |
| Grand Prize, 2nd | $2,500 + match ticket | Runner-up on the same basis |
| Best Use of Microsoft Foundry | $1,500 | Foundry for development, orchestration, management of AI solutions |
| Best Enterprise Solution | $1,500 | Production readiness, reliability, transparency, controls |
| Best Multi-Agent System | $1,500 | GitHub Copilot / Agent Framework / A2A; distinct agent roles, shared state, handoffs, failure recovery |
| Best Azure Cloud Native Integration | $1,500 | AKS, Container Apps, Functions, Logic Apps, event-driven architecture |

**Target category (initial pick):** Best Multi-Agent System, because the workflow below naturally decomposes into specialist agents. Revisit once the architecture settles.

### 1.3 Submission deliverables (hard requirements)

- **Public GitHub repo** (this one; it can stay private while we build, must be public before submitting).
- **Demo video under 2 minutes**, hosted on YouTube or Vimeo, showing the project running. Judges may score from the video alone.
- **Pitch** that names which Microsoft and Azure technologies were used, what it does, and what problem it solves.
- **Working demo or test build** judges can reach, with credentials if needed, free until judging ends.
- All materials in English. Teams of up to 4. Project must be new work since September 29, 2026.

### 1.4 The challenge, in the organisers' words

Turn **synthetic, football-realistic** event data (passes, shots, tackles, possession changes, pressure events, match metadata) into explainable match intelligence, real-time narratives, and automated recaps for studio, broadcast, or streaming, personalised per fan. Expected pipeline: **Ingest → Interpret → Explain → Render → Personalize**. "Auto-eventing from a video feed" and "player identification" are explicitly listed as suggested features, which is exactly what Regista does. A metrics-only or personalisation-only project is considered incomplete.

### 1.5 ⚠️ Data and footage constraint (read before every demo decision)

- The organisers provide **no footage and no dataset**. Section 4.7 of the rules: projects must use synthetic, football-realistic data, and you warrant you hold the rights to any footage you use. The demo video may not contain third-party copyrighted material without permission, and judges may score from the video alone. The Premier League helps judge and is the rights holder for Premier League broadcasts, so its feed must never appear in the submission without a written licence.
- "Optimised synthetic data creation" is scored under Technological Implementation, so the event dataset Regista generates is a first-class deliverable, not a by-product.

#### Decision: two layers, and the boundary between them is what we submit

1. **Vision layer — private.** Video in, events out: player tracks, possession, camera-cut and replay markers. Trained and tuned on the broadcast footage we have access to, privately. Nothing from this layer is published except code and metrics. Raw footage never enters this repo, the demo video, or any judge-facing artifact.
2. **Intelligence layer — public.** Events in; clips, labels, and chatbot out. Runs on the synthetic event stream the vision layer emits. The rules describe exactly this pipeline, so the event dataset becomes a headline deliverable.

#### Demo and public-repo footage: options, best first

1. **Build a synthetic match renderer.** Even a simple 2D or Unity-style render of players with kit numbers, a ball, and a director-style feed with cuts and replays. Perfect ground truth for free (easier training) and the strongest answer to the synthetic-data criterion.
2. **Record our own match.** Phone on a tripod at a pickup, college, or local game. Full rights, real footage, great demo moment. Get consent from any player we identify.
3. **Creative Commons clips** from Wikimedia Commons or Pexels for short demo segments. Check the exact licence on each clip.
4. **Pitch-diagram visualisation.** Render tracking output as dots on a pitch, Opta style, with no original pixels. Derived from footage so not zero risk, but far safer than frames, and it demos the intelligence layer well.
5. **Ask the organisers.** Post on the Innovation Studio platform asking whether licensed clips will be provided or whether Premier League footage may appear in demos. Costs nothing; the answer settles this.

**Decided 2026-10-20: we record our own match.** Professional broadcast footage cannot reasonably or legally be obtained, so the real footage is a game between Zaid and friends, filmed by us, with every player's written consent covering recording, training models on it, and showing it publicly (demo video, judges, live app). Anyone who does not consent stays off the pitch. The raw video stays local and out of the repo; clips may appear in the demo because we own them and the players agreed. Identity stays kit-number-first: numbered bibs, two clearly different team colours.

**Avoid:** football video-game footage (publisher copyright) and research datasets such as SoccerNet as demo material (research-only licences; a cash-prize hackathon likely falls outside them).

#### Decision: identification is kit-number-first, not face-first

Azure AI Face identification is a Limited Access service that Microsoft gates and restricts, and biometric identification of real people raises GDPR and similar issues. Microsoft judges will notice. The primary identity signal is **kit number + team colours + tracking continuity**, which is also more robust because faces are tiny in wide broadcast shots and numbers are not. Face recognition, if used at all, is an optional, local, non-Azure boost and never the primary path.

---

## 2. What Regista is

### 2.1 Purpose

Content creation and ease of finding significant moments and clips. Highlight reels and edits are everywhere and are the craze; Regista makes that process easier. It also serves scouting: a scout can find **every moment a player is on the ball** across a full match, or a season, in seconds.

### 2.2 Input

A raw, full 90-minute game as delivered on broadcast servers (the main broadcast feed with replays and highlights cut in by the director). That is what we have access to.

### 2.3 Workflow (the general first thought)

1. **Train the model on raw broadcast footage** (privately, vision layer) for spatial recognition, player identity via kit number + team colours + tracking continuity, player behaviour, and position on and off the ball at all times. Face recognition is optional and local only (see 1.5).
2. **Identify player moments**: every touch, every highlight, every replay.
3. **Perfect the identification through reinforcement learning with Zaid** in the loop (human feedback on detections).
4. **Pick one player and cut every clip** where that player is:
   - in the **main view and on the ball**, and
   - in **any replay or highlight** (camera angles that are not the main view), whether on or off the ball.
   - Main-view, off-the-ball footage is **excluded**, otherwise the output would be the whole game.
5. **Train the model to label clips and judge which are worth having or watching** (nutmeg, dribble, key pass, shot, tackle, skill move, goal, assist, etc.).
6. **Train the model over and over again** on the growing labelled corpus.
7. **Build a chatbot** that finds clips of specific labelled events: *"find me Pogba doing a nutmeg."*

### 2.4 Users

- **Content creators and editors** making highlight reels and edits.
- **Scouts and analysts** who need every on-ball moment of a player.
- **Broadcasters and studios** needing instant replay packages per player.
- **Fans** who want a personalised reel of their favourite player.

---

## 3. How Regista maps to the hackathon pipeline and hero tech

This is the initial mapping. Change it as we learn what is practical in the time available.

**Layer boundary:** Ingest and Interpret form the **private vision layer**; Explain, Render, and Personalize form the **public intelligence layer**. The contract between them is the synthetic event stream, **defined in `data/synthetic/README.md` and enforced by the JSON Schemas in `src/regista/schemas/`** (schema version 0.1.1: adds `annotation.context`, `label.prior_watchability`, `label.review`). A synthetic match generator (`python -m regista.synth`) feeds the same contract for the public demo, and `regista.clips.derive_clips` is the reference implementation of the clip rule on top of it.

### 3.0 Code layout and how to run it

```
src/regista/schema.py        load + validate JSONL streams by record type
src/regista/synth/           synthetic match generator (possessions, passes, shots, director cuts, replays)
src/regista/clips.py         clip rule + first labeller (watchability, tags, explanation)
src/regista/validate.py      CLI validator
src/regista/librarian.py     the Librarian: plain-English clip search (player, tags, minutes, replays), no cloud
src/regista/mcp_server.py    MCP server exposing search_clips, search_library, derive_clips, validate_stream, render_clip, list_matches
src/regista/synth/report.py  synthetic realism report: per-90 rates vs Premier League bands; generator profiles demo/realistic
src/regista/api.py           FastAPI service: viewer at /, matches, clips with filters, search, on-demand MP4, upload → pipeline
src/regista/static/viewer.html the clip viewer (player header, tag chips, watchability-sorted grid, Search + Ask Foundry, stack footer)
Dockerfile                   python:3.11-slim + fonts-dejavu; uvicorn regista.api:app on :8000 (built by GitHub Actions; no docker here)
docs/architecture.md         two layers, the workflow roles local vs cloud, MCP tools, Azure per stage (running vs planned), auth
docs/demo-storyboard.md      shot-by-shot plan for the sub-2-minute video, voiceover, what is named on screen
src/regista/cloud/           Azure wiring: config (.env), FoundryLabelAgent + FoundryLibrarianAgent (Agent Framework,
                             Regista MCP server as the Librarian's tool), CosmosPersistAgent; agents_for() swaps them in
infra/provision.sh           az CLI provisioning: Foundry resource + project + model, Cosmos DB serverless, AI Search, Container Apps
                             env + registry; writes .env (Application Insights was created and connected by hand)
infra/deploy-app.sh          deploy a pinned image to Container Apps, secrets, managed-identity roles; waits for a ready revision
src/regista/agents/          the roles (roles.py), the Microsoft Agent Framework workflow that runs them (workflow.py: fan-out/
                             fan-in, typed handoffs, dead-letter routing, retries, request_info review, checkpoints), the original
                             orchestrator kept as a reference (orchestrator.py), CLI (python -m regista.agents, --review, --graph)
src/regista/feedback.py      learning from people: human verdicts as annotations, needs_review(), the watchability model retrained
                             from verdicts (logistic regression, JSON), evaluate(); real verdicts live in data/feedback/
src/regista/cloud/search.py  Azure AI Search index regista-clips; SearchIndexAgent ("indexer" role); search_library()
src/regista/cloud/telemetry.py  Agent Framework OpenTelemetry → Application Insights → Foundry Tracing
src/regista/cloud/smoke.py   container smoke test: Regista MCP and Azure MCP list their tools inside the image (CI)
src/regista/vision/          the private vision layer v0: shots (camera_segment), identity (calibration, detection, team, kit
                             number, tracking → track/appearance), possession_vision, vision_writer; an Agent Framework vision
                             workflow; trained and measured on Regista's rendered broadcast (docs/vision.md has the numbers)
docs/vision.md               what each vision agent does, measured accuracy, and what changes for real broadcast footage
docs/gap-analysis.md         where Regista stood against the judging criteria on 2026-10-20 and the fixes, in order
docs/workflow.md             the workflow graph (Mermaid, generated by --graph)
src/regista/camera.py        the main-camera model shared by generator and renderer (what is in frame)
src/regista/render/          2D broadcast renderer: scene.py (interpolation, captions, score, clock),
                             draw.py (pitch, players, replays, closeups, crowd, end card, HUD), video.py
                             (parallel MP4 parts + ffmpeg concat), clips.py (per-clip videos, best-first reel)
data/synthetic/README.md     the contract, record by record
src/regista/schemas/        regista-events.schema.json, regista-clips.schema.json (package data)
data/synthetic/sample/       committed sample match (seed 294: home #9 scores, nutmegs a defender, replays, closeup, highlights)
tests/test_synthetic.py      schema + generator + clip rule must agree
```

```bash
pip install -e ".[dev,vision]"     # full local suite and pipeline; ".[dev,vision,cloud]" for Azure
python3 -m pytest -q
python3 -m regista.synth --minutes 3 --seed 294 --track-hz 1 --player t_home_09 --out data/synthetic/sample
python3 -m regista.synth --seed 77 --minutes 45 --periods 2 --profile realistic --home "Eastbury Rovers,EAS,#00A650" --away "Westfield Town,WES,#6A0DAD" --out docs/demo/seeds --report
python3 -m regista.validate data/synthetic/sample/syn_0294
python3 -m regista.render data/synthetic/sample/syn_0294 --out docs/demo/syn_0294.mp4 --frames-dir docs/demo/syn_0294_frames
python3 -m regista.render.clips data/synthetic/sample/syn_0294 --player t_home_09 --out docs/demo/clips_t_home_09
python3 -m regista.librarian data/synthetic/sample/syn_0294 "find me Castellanos doing a nutmeg"
python3 -m regista.mcp_server --list-tools        # or without the flag: stdio MCP server for any MCP host
python3 -m regista.synth.report data/synthetic/sample/syn_0294
python3 -m regista.synth.report --profile realistic --seeds 21 22 23 --minutes 30
python3 -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
uvicorn regista.api:app          # viewer at http://localhost:8000, OpenAPI at /docs
az login && ./infra/provision.sh # Azure: writes .env; then add --cloud to regista.agents (Foundry + Cosmos)
python3 -m regista.vision data && python3 -m regista.vision train --models models/vision    # vision: render data, train
python3 -m regista.vision run VIDEO --roster MATCH_DIR --out OUT --workflow                 # video in, event stream out
python3 -m regista.vision evaluate --set fresh --models models/vision                    # score frozen models on fresh matches
docker build -t regista . && docker run -p 8000:8000 regista
```

`docs/demo/` is git-ignored rendered output. The renderer uses the ffmpeg bundled in the `imageio-ffmpeg` pip package, so no system install is needed; without it, output falls back to GIF.

Rule of thumb when extending: change the schema, the generator, the clip rule, and the tests together, then bump `schema_version`.

| Pipeline stage | What Regista does | Hero technology (initial pick) |
|---|---|---|
| **Ingest** | Pull the broadcast feed, split into frames/segments, detect scene cuts (main view vs replay) | Azure Blob Storage, Azure Functions / Event Grid, Azure AI Video Indexer |
| **Interpret** | Detect and track players, recognise identity (kit number OCR + team colours + tracking continuity), detect ball possession, emit the **synthetic event stream** that crosses the private/public boundary | Azure AI Vision (OCR, object detection), custom models hosted in **Microsoft Foundry**, Cosmos DB or Fabric for the event store |
| **Explain** | Label each clip (nutmeg, dribble, shot...), score "worth watching", explain why | Foundry models + **Microsoft Agent Framework** labelling agent, RL-with-human feedback loop |
| **Render** | Cut clips with timecodes, produce machine-readable overlays and reels | Azure Container Apps / AKS workers, FFmpeg, Azure Media handling |
| **Personalize** | Chatbot: natural-language search over labelled clips, per-player reels, multi-language | Foundry Agent + **Azure MCP** tools, Azure AI Speech/Translator, web UI |

### 3.1 Multi-agent design (target category)

Distinct agent roles with shared state and handoffs, so the system does something a single agent could not:

- **Ingest Agent** — segments the feed, flags replays and highlights.
- **Identity Agent** — finds and tracks the chosen player in every frame using kit number, team colours, and tracking continuity.
- **Possession Agent** — decides when the tracked player is on the ball.
- **Clip Agent** — cuts and stores clips per the rules in 2.3 step 4.
- **Label Agent** — names the event and scores watchability; asks the human when unsure (RL loop).
- **Librarian Agent** — chatbot interface; translates "Pogba nutmeg" into a query over the clip index and returns clips.

**Vision (2026-10-20):** the Identity role now exists as a vision agent (`regista.vision`), alongside Shot and Possession agents, wired as a second Agent Framework workflow whose output directory is the intelligence workflow's input. Trained and measured only on rendered footage so far: seeds 201-206 are a development set (tuned against), seeds 301-303 are fresh matches scored once with frozen models (clip recall 0.76, precision 0.94). Never tune against 301-303; make a new fresh set instead. Tested at 640x360, 10 fps only; the shot model fails at 720p and degrades at 25 fps. Real broadcast footage is next (see docs/vision.md, last section). Trained models live in `models/vision/` (git-ignored).

**Status (2026-10-20, later):** the pipeline runs as a Microsoft Agent Framework workflow (`regista.agents.workflow`) with a human-in-the-loop review step, an optional Azure AI Search indexer role, and the Foundry Librarian calling two MCP servers (Regista's and Microsoft's Azure MCP Server). See docs/gap-analysis.md. Earlier: the Label and Librarian roles run on Microsoft Foundry (`gpt-5-mini`) through Microsoft Agent Framework, the Librarian calling Regista's MCP server as its tool, and the Persist role writes to Cosmos DB; `python3 -m regista.agents … --cloud` uses them, and uploads on the live app use the Foundry Label agent (uploads pass no questions, so the Foundry Librarian and Azure MCP run only from the CLI with `--query`). Previously: a local, rule-based v0 of this pipeline exists in `src/regista/agents/` (roles Ingest, Validator, Possession, Clip, Label, Persist, Librarian; the Identity role belongs to the private vision layer and is played by the generator for the demo). It has distinct roles with declared inputs and outputs, shared state handed along, retries, a per-attempt trace, and a dead-letter file; downstream agents are skipped, not crashed, when an upstream one fails. The Microsoft Agent Framework version keeps the same roles, state keys, and trace, swapping the rule-based Label and Librarian agents for Foundry-backed ones once Azure exists. Tools are exposed today through `regista.mcp_server` (local MCP, stdio).

---

## 4. Working agreements for Claude

- Keep this file current. When the idea changes, edit section 2; when the stack changes, edit section 3.
- Never commit raw broadcast video, large model weights, or secrets. `.gitignore` covers the common cases; keep it that way.
- Name a hero technology in commit messages and docs only when the change actually uses it. Never list a service as part of the architecture until code runs against it; mark it "planned" until then. Judges read the repo and will check.
- Do not claim GitHub Copilot Agent Mode (or any tool) in the pitch unless it was genuinely used and the evidence exists.
- Keep the README demo-ready: a judge should be able to understand and run the project from it.
- The demo video is under 2 minutes. Design features so they demo well in that window.

## 4.1 Azure (live since 2026-10-20)

- Subscription: Azure free trial on Zaid's account ($200 credit, 30 days, ends about **2026-11-19**). The rules require the demo to stay reachable free of charge until judging ends **2026-11-10**, so the trial covers judging with about a week to spare. Do not upgrade to pay-as-you-go without asking Zaid.
- Resource group `regista-rg`, East US: Foundry resource + project `regista` + `gpt-5-mini` deployment; Container Apps env `regista-env` + app `regista-api`; Container Registry (Basic). **Cosmos DB is in East US 2** because East US had no capacity.
- The free trial blocks ACR Tasks, so `az containerapp up --source` and `az acr build` fail. The image builds on GitHub Actions (`.github/workflows/build-image.yml`, secrets ACR_LOGIN_SERVER/USERNAME/PASSWORD) and deploys with `infra/deploy-app.sh` (pin `IMAGE=...:<sha>`).
- Auth: the app and the CLI reach Foundry, Cosmos DB and AI Search with Entra ID (`DefaultAzureCredential` / managed identity, role assignments); the code uses no keys. Not keyless everywhere: the Container App pulls its image with the registry admin credential (a Container Apps secret), GitHub Actions pushes with the admin login, and key-based local auth is still enabled on Cosmos DB and AI Search (unused). Say this honestly in docs; never write "keyless everywhere".
- `.env` holds the endpoints plus `REGISTA_ADMIN_TOKEN` and `APPLICATIONINSIGHTS_CONNECTION_STRING`; it is git-ignored and docker-ignored.
- Also in `regista-rg`: Azure AI Search `regista-search-a7fbe6` (**free tier, South Central US**: free tier is not offered in East US); Application Insights `regista-appi` on the existing Log Analytics workspace (daily cap 0.1 GB), connected to the Foundry project for tracing; Cosmos DB container `annotations` for human verdicts and the learned model.
- Tests never load `.env` (`REGISTA_DOTENV=""` in tests/conftest.py) and never reach Azure; a guard test enforces it. Each test gets its own feedback folder.
- **Ask Foundry is open but limited** (`REGISTA_ASK_PER_MIN` 3, `REGISTA_ASK_PER_HOUR` 20 per visitor; `REGISTA_ASK_TOTAL_PER_HOUR` 60, `REGISTA_ASK_TOTAL_PER_DAY` 300; `REGISTA_ASK_CONCURRENT` 2). Its tools are public-only by design: never give the public Librarian the Cosmos DB namespace (annotations hold reviewers' notes) or `render_clip`.
- **Writes on the live app need a token.** Uploads, verdicts, reviews and retraining require the `X-Regista-Token` header matching `REGISTA_ADMIN_TOKEN` (in `.env`, deployed as a Container Apps secret). The viewer asks for it once. Reads stay open for judges. `REGISTA_READONLY=1` switches writes off entirely.
- **Never send a request that writes to the live app as a test.** Probe with requests that cannot write (no token, or an invalid body) and check Cosmos afterwards. On 2026-10-20 two test verdicts reached Cosmos while an old revision was still serving; they were identified by timestamp and deleted.
- **A deploy is done only when the new revision is the latest ready one.** `deploy-app.sh` waits for that and prints logs on failure. Traffic weight alone is not proof.
- The image workflow runs the full test suite, builds the image, and runs `python -m regista.cloud.smoke` inside it (Regista MCP and Azure MCP must list their tools); any failure stops the push. Pull requests get the same checks and push nothing. It rebuilds on changes to `src/`, `tests/`, `data/synthetic/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`; `tests/test_packaging.py` guards `.dockerignore` against dropping package files. `infra/provision.sh` can be re-run: it keeps the existing write token and App Insights connection string in `.env` and reuses the resource group's registry; `deploy-app.sh` no longer duplicates the Cosmos role assignment (the app identity has 7 duplicates from earlier deploys, harmless).
- Cosmos DB still holds 16 clip and 16 label documents from before ids became player-scoped (`cl_000001` / `lb_000001` style): 11 of each for `syn_0294` and 5 of each for `syn_0141`. They are stale duplicates; delete them only with Zaid's go-ahead.
- Tear down after judging: `./infra/provision.sh --destroy`.

## 4.2 Where we are and what's next (update at the end of every work session)

**As of 2026-10-20, evening.** `main` is at the latest pushed commit; CI (tests, then image build) is green; the live app runs image 285ba93 (no app-facing change since, so no redeploy was needed). 158 tests pass.

**Built and working:** event-stream contract (schema 0.1.1) and synthetic generator; 2D broadcast renderer; clip rule and labeller; Librarian (rule-based locally, Foundry with `--cloud`); Regista MCP server; the Agent Framework workflow with human review, retries, dead letters and checkpoints; learning from verdicts (watchability model); Cosmos DB, AI Search, Foundry tracing; token-gated FastAPI app on Container Apps; vision layer v0 on rendered footage (fresh-match clip recall 0.76, precision 0.94; docs/vision.md).

**Audited 2026-10-20** by independent agents; every finding was fixed or is listed below. The full record is in commits 6d1a870 and d1de317.

**Waiting on Zaid:**
- Footage: our own consenting match (§1.5), recording planned for about 2026-10-23. Bring: video files, the team sheet (name, number, team), notes of key moments. Then: label, retrain the shot model on that format, run vision end to end, cut the demo.
- Go-ahead to delete 16 stale clip + 16 label docs in Cosmos (old-style ids).
- Go-ahead to harden auth: registry pull by managed identity (AcrPull) and local auth off on Cosmos DB and AI Search.
- First real Keep/Drop verdicts in the viewer.

**Next build work, in order (not blocked on footage):**
1. Make the hero tech visible on the live app: **built on branch `claude/live-hero-tech` (PR open, not deployed; deploy only on Zaid's approval).** Matches from Cosmos (stale ids filtered), Ask Foundry (`POST /api/matches/{id}/ask`, public read-only tools, rate-limited), health/footer naming the stack, tracing at app start, azmcp ICU fix + CI smoke test inside the image. After deploy: one Ask from the live app, then confirm spans from the container in App Insights and that `search_index_query` ran there; only then call it verified in docs.
2. Event spotting in the vision layer (passes, shots, tackles, nutmegs), so vision-derived clips get labels, not only reasons.
3. Vision for real footage: frame sampling inside ffmpeg with gap-normalised motion features, a person detector instead of discs, a real homography; designed now, trained when the footage arrives.
4. Demo video (docs/demo-storyboard.md needs a rewrite around the real match), pitch text, make the repo public before 2026-10-27.

## 5. Open questions

- **Decided 2026-10-19 (unsupervised run):** the renderer uses the ffmpeg bundled in the `imageio-ffmpeg` wheel (pip, no system install); the featured sample player is the home 9 (seed 294) because a goal by the 10 is a one-in-eighty event in the simulator; the generator keeps a `demo` profile for dense 3-minute samples and a `realistic` profile for statistics; placeholder annotations are `source: synthetic` + `simulates: human`, never claimed as real review; the FastAPI service is the deployable unit and the Dockerfile is unbuilt on this machine (no docker).
- **Resolved 2026-10-20: footage rights.** No professional footage; we record our own consenting match (see §1.5). Still open: when it is recorded, where it lives locally, and its format.
- **Organiser answer.** Have we asked on the Innovation Studio platform whether licensed clips will be provided or Premier League footage may appear in demos?
- **Demo footage pick.** The 2D renderer now produces broadcast-style video from the synthetic stream (`python -m regista.render`), which is footage we own outright. Still open: whether to add our own recorded match or CC clips on top for realism.
- **Resolved 2026-10-20: hosting.** The FastAPI service + viewer is live on Azure Container Apps (`regista-api`, one replica), see §4.1. It serves only the committed sample match; uploads live on local disk and do not survive a restart.
- Team: solo or up to 4?
