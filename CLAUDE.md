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

### 2.5 Two views: Clips and Scout (decided 2026-10-22, part of the Oct 27 submission)

> One pipeline, two jobs: **Clips** finds any moment in a match; **Scout** turns every match a player is seen in into a
> verified profile scouts can search.

| Route | View | For |
|---|---|---|
| `/` | **Clip view** (the Product as built) | creators, broadcasters, fans: ask anything, get clips and reels; a header switch to Scout |
| `/scout` | **Scout view** | scouts: filter, ask the Scout agent, shortlist, compare players across the season |
| `/players/{id}` | **Player profile** | one player across every match: reel, per-90 stats, touch map, matches, Foundry summary, "Add a match" |
| `/studio` | **Studio** (as built) | the operator; adds a Claims tab ("that's me" confirmations) |

- **Data: the synthetic "Regista League".** 6 clubs, 10 rounds (double round robin), 30 matches of 2 x 15 minutes,
  generator profile `league` (league mode: hidden player ratings drive outcomes and roles shape who makes which numbers,
  generator 0.7.0; `regista.synth.report` checks league bands, leaders, the star's lead and role shapes, where crosses start and who receives them), fixed squads of 18
  with **global player ids** (`pl_…`) on every roster entry. A regular plays about 300 minutes a season, so the Scout
  terminal and profiles state the sample size and mark metrics whose split-half reliability is below 0.3 as noisy
  (`regista.season.reliability`, `data/season/reliability.json`). The league definition
  (`data/season/league.json`: clubs, squads, fixtures, seeds) is committed; matches regenerate deterministically from it
  and are not committed. Since league mode (player ratings, 10 Hz motion) a match takes about 1.3 s to generate (median
  of five, generator 0.7.0, measured 2026-10-24 on Zaid's 10-core Mac), so a cold season is built in parallel processes
  (`regista.season.build.build_all`: 5.9 s on 10 cores, 37 s on one); the Docker image builds the season in at
  `docker build` time, so a fresh revision starts warm.
- **Profiles** are aggregated from the event streams: appearances, minutes, counts and per-90 rates, a touch map (attack
  left to right), best moments across matches, and every stat links to the moments it came from ("verified by Regista").
  The **Profile agent** refreshes a profile when a match is added and has Foundry write a summary whose claims cite clips.
- **Scout agent** (Foundry) over new MCP tools `search_players`, `get_profile`, `compare_players`, plus the clip tools.
- **Add a match / claims:** on the live app a player adds a match as the vision layer's output (events + tracks, as
  uploads do today) and claims "that's me" (kit number + team); the claim is a human annotation confirmed in the Studio.
  On the operator's laptop the same flow accepts a video file and runs the vision layer locally first. Cloud video
  processing for this flow is **planned**; the Player view's uploads (§2.6) already run the vision layer in the cloud.
- **No real players' profiles for now.** Zaid's recorded match can appear in the Clip view (with consent) but gets no
  profiles. Profiles are synthetic players only.
- **Out of scope:** accounts and sign-in, footage-rights handling (post-hackathon), payments. Messaging exists only
  per visitor in the browser (§2.9). **Microsoft Fabric** is built (§2.7).

### 2.6 The third view: Player (decided 2026-10-22, part of the Oct 27 submission)

| Route | View | For |
|---|---|---|
| `/me` | **Player view** | a (synthetic) player uploads their own match footage, watches Regista's vision agents work on it, answers "is this you?", and the match joins their profile |

- **Footage is synthetic**: `python -m regista.player.film` renders a friendly between the player's club and another league
  club in the vision layer's format (640x360, 10 fps, no captions or name labels). Not real footage, by decision.
- **Processing runs in the cloud** (option A): the app stores the video in **Azure Blob Storage** and queues a message on an
  **Azure Storage Queue** (`vision-jobs`); an event-driven **Azure Container Apps Job** (KEDA queue scaler) runs the vision
  workflow with the models from a private Blob container, writes the match folder back to Blob, and the app serves it.
  `regista.player.store` is the contract (blob layout, queue message, `UploadRecord`); a local folder backend runs the
  same code in tests and offline. A laptop can run the same worker against the same queue as a fallback.
- **Identity is free**: the roster is both clubs' league squads (`roster_for`), so the vision match carries global ids and
  joins the profile with no mapping; "is this you?" is Who's who aimed at the player.
- **Writes need the admin token** (uploads, answers), like every write. Synthetic players only.

### 2.7 Match recaps and Microsoft Fabric (decided 2026-10-22, part of the Oct 27 submission)

- **Match recap** (the brief's "automated recaps, personalised per fan"): a short written recap of any match (headline
  plus 3-4 paragraphs; every sentence links to its moment in the Clip view) and a recap reel. Personalised by picking a
  player: the recap is told from their side. **English only.** Two engines as elsewhere: Instant (rules) and Foundry
  (rate-limited like Ask Foundry, rules fallback). A Recap step in the intelligence workflow; an MCP tool `match_recap`.
  Shown in the Clip view, on profiles, and on `/me` after an upload. No live commentary ticker (decided: less jargon).
- **Microsoft Fabric**: Zaid's Northeastern account can use Fabric (the tenant allows trials, checked 2026-10-22). A
  "Regista" workspace on his own trial capacity with a lakehouse `regista_league`; the season and Player-view uploads
  land in OneLake as Delta tables (keyless, Entra ID); a Fabric notebook recomputes the league leaders and percentiles
  and Regista checks they match its own. Only his own workspace is created or touched: the tenant is the university's.
  The Fabric data agent is not used (preview).
- `docs/criteria.md` replaces `docs/gap-analysis.md`: each judging criterion, its evidence and where to check it.

### 2.8 Positioning, pitch and demo (decided 2026-10-23)

**Regista is a clip powerhouse and a football data engine.** Video in: every touch, replay and highlight cut, labelled,
explained, recapped and searchable; plus a synthetic data engine (a whole season with exact ground truth). The four views
are the **paths** it serves, all live: fans and creators (Clips: search, reels, exports), broadcasters (recaps, replay
packages), scouts (Scout: profiles where every stat opens its moment), players (Player: upload your own match).

- **The pitch and the demo video follow this order:** (1) the clip powerhouse, (2) Microsoft, AI and agents shown
  working in the app, (3) the paths. The close says where it goes next.
- **Not a scouting-only product.** The brief names studio, broadcast and fans and calls metrics-only incomplete. The
  Bloomberg-style scouting terminal (workspaces, linked panels, ⌘K) serves the Scout path; its decisions are in §2.10.
  The demo shows only the part that is built (the engine and its API) and keeps the terminal's screens for "where it
  goes next" until they exist.
- `docs/demo-storyboard.md` is written to this structure (2026-10-23). UI/UX work continues in the sandbox
  (`ux/sandbox`); its small wins (yellow current view, centred nav, search-first Home) fold into the app later.

### 2.9 The Player and Scout dashboards (decided 2026-10-23)

Designed in the sandbox (`ux/sandbox`, `sandbox/`), ported by PR (branch `ux/dashboards`; reports in
`docs/redesign/dashboards/`).
- **One profile page, two audiences.** What a scout sees for a player (`/players/{id}`, with a scout bar: shortlist stage,
  Message, Compare, Notes, Write a report) is exactly the player's own "My profile"; one renderer,
  `static/player/profile-view.js`.
- **Player dashboard `/me`** (opens on Femi Toure, Switch player): Overview, My profile, Matches & videos (real uploads,
  agent steps, "Is this you?"), Messages, Team (my details; my club's squad, results, table), Settings.
- **Scout dashboard `/scout`** (as Maya Lindqvist, chief scout, Fairhaven FC, a synthetic persona): Overview, Find players
  (the real Scout agent, both engines), Shortlist (Watching, Contacted, Trial, Offer; compare), Reports (each point cites a
  moment), Messages (scouts start conversations; players reply, mute, block), Team (the club's needs, each listing the
  players who fit, computed live), Settings.
- **Live vs per visitor:** profiles, moments, numbers, uploads, the Scout agent, compare and claims are live. Messages,
  stages, notes, reports, needs, details and settings are kept **in the visitor's browser only** (`Regista.store`,
  prefix `regista.demo.v1.`, seeds in `static/shared/demo.js`, "Reset this demo" in Settings); one shared conversation
  store, so both sides see the same thread in one browser. Nothing of it reaches the server; no sign-in.
- The left panel shows a dashboard's sections under its parent link (second row of tabs on phones). `/api/season` lists
  each club's squad (read-only, from `league.json`).

### 2.10 The Scout terminal (decided 2026-10-23 and 2026-10-24)

Research first: `docs/scout-terminal/{industry-metrics,regista-data,catalogue}.md` (the industry's metrics, what
Regista's data can compute, the chosen catalogue). Build reports, verification and review rounds:
`docs/scout-terminal/build/`.
- **Part A, the engine (built on `feature/terminal-engine`, not yet merged or deployed):**
  - **Player attributes:** every league player has a public bio (date of birth, height, foot, nationality) and hidden
    ratings (1-99 skills, keeper skills, top speed, acceleration) in `data/season/league.json`. The generator reads them.
    No API, MCP tool or page serves them; tests check every public payload.
  - **League mode in the generator** (generator 0.7.0, schema 0.2.0): ratings drive outcomes and roles shape who makes
    which numbers. It adds substitutions, penalties, aerial duels, through balls, red cards and offsides. Output without
    ratings stays byte-identical to `main`.
  - **10 Hz physical motion** (`synth/physical.py`): every player within their own pace, tiring with stamina. Physical
    metrics are built for real from the motion (distance, speed zones, sprints, top speed, accelerations), not faked.
  - **The metrics engine** (`season/metrics.py`: 127 player and 19 team-style metrics, each with definition, rule and
    source) and **its API** (`terminal_api.py`). `regista.synth.report --league` checks the season against Premier
    League bands (`docs/realism-report.md`), and `regista.season.audit` measures split-half reliability.
- **Part B, the terminal's screens (next):** to be built first in the sandbox (`ux/sandbox`), then ported into Scout as a
  **Terminal** section. They are not shown as working until they run.
- **Femi Toure (pl_bro_09) stays the star:** the league's top scorer (3 league goals with generator 0.7.0, one a
  penalty, in rounds 2, 5 and 6), and the demo's hook. A test keeps him on top.
- **Honest numbers:** no metric without its definition and source; the sample size is stated (a regular plays about 300
  minutes a season); metrics whose split-half reliability is below 0.3 are marked noisy.

---

## 3. How Regista maps to the hackathon pipeline and hero tech

This is the initial mapping. Change it as we learn what is practical in the time available.

**Layer boundary:** Ingest and Interpret form the **private vision layer**; Explain, Render, and Personalize form the **public intelligence layer**. The contract between them is the synthetic event stream, **defined in `data/synthetic/README.md` and enforced by the JSON Schemas in `src/regista/schemas/`** (schema version 0.2.0 since 2026-10-23: the league's events `substitution`, `penalty`, `aerial_duel`, `card_red`, `offside`, and the record type `physical` (each player's 10 Hz motion summarised: distance, FIFA speed zones, sprints, top speed, accelerations), all from the generator in league mode only; streams without them, every committed sample and the vision layer's output
included, stay 0.1.1: `regista.vision`, Who's who answers, verdicts and claims stamp `LEGACY_SCHEMA_VERSION`). A synthetic match generator (`python -m regista.synth`) feeds the same contract for the public demo, and `regista.clips.derive_clips` is the reference implementation of the clip rule on top of it.

### 3.0 Code layout and how to run it

```
src/regista/schema.py        load + validate JSONL streams by record type
src/regista/synth/           synthetic match generator (possessions, passes, shots, director cuts, replays)
src/regista/clips.py         clip rule + first labeller (watchability, tags, explanation)
src/regista/validate.py      CLI validator
src/regista/librarian.py     the Librarian: plain-English clip search (player, tags, minutes, replays), no cloud
src/regista/conversation.py  the conversational Librarian (plan step 7): follow-ups merge into the query so far; chat_turn; /chat
src/regista/recap.py         the match recap (§2.7): facts with refs from the stream, rules or Foundry sentences each citing a clip or
                             event (Foundry's checked: refs, numbers, jargon), the recap reel; RecapAgent (workflow step, recap.json);
                             GET /api/matches/{id}/recap?player=&engine=; MCP tool match_recap; the Clip view's Recap panel
src/regista/mcp_server.py    MCP server exposing search_clips, search_library, derive_clips, validate_stream, render_clip, list_matches,
                             match_recap, and the player tools
src/regista/season/          the Regista League (Scout view data): league.py (6 clubs, squads with global player ids, double round
                             robin, seeds; committed as data/season/league.json), build.py (regenerates each match folder on demand,
                             tracks only when video needs them), profiles.py (per-90 rates, percentiles, touch map, moments, evidence)
src/regista/player/          the Player view: store.py (Blob + Queue or a local folder: uploads, jobs, matches, models), film.py
                             (synthetic footage of a friendly between league clubs; roster_for gives the vision team sheet)
src/regista/season_api.py    /scout, /players/{id}, /api/season, /api/players, /api/players/{id}[/moments|/reel.mp4], /api/compare
src/regista/season/metrics.py the Scout terminal's metrics engine: 127 player metrics + 19 team-style metrics from the league's
                             event streams and physical records (FBref/Opta/StatsBomb/Wyscout rules, xT fitted on the season),
                             per 90, percentiles vs position peers (FBref rule, qualifying minutes = a third of a club's), evidence
                             per number, form, similar players, team style; python -m regista.season.metrics [--rank K | --player ID]
src/regista/terminal_api.py  /api/metrics, /api/terminal/{screen,rank,scatter}, /api/players/{id}/{metrics,form,similar},
                             /api/teams[/{club_id}/style]: public reads, never the hidden ratings
src/regista/player_api.py    the Player view (/me): uploads to the store (admin), progress, "is this you?" answers through the
                             identity review, finished pv_ matches fetched from the store and served via _match_dir and profiles
src/regista/season/playing_time.py  time on the pitch from substitutions and red cards (profiles, build, Fabric lineups)
src/regista/season/audit.py  can a scout trust it: split-half reliability within a kit slot, the scoring chart (python -m regista.season.audit)
src/regista/season/reliability.py  split-half reliability per metric (data/season/reliability.json); below 0.3 is marked noisy
src/regista/season/claims.py "that's me": claims and Studio decisions as human annotations (claims.jsonl in the feedback folder,
                             Cosmos DB when configured); confirmed claims add their uploaded match to the claimed league player's profile
src/regista/claims_api.py    GET /api/claims [studio], POST /api/claims and /api/claims/{id}/decision [write]; a confirm runs the workflow
                             on the claimed match, whose profiles executor (the Profile agent, after persist) refreshes the profile
src/regista/static/player/add-match.js  "Add a match" on a profile: upload events + tracks (or, locally, a video through a vision-run
                             job), then "which one is you?" (team + kit number) as a claim; the Studio's Claims tab decides
src/regista/synth/physical.py league mode's motion meters: Body (a player's velocity, reserve, meters), the physical record's
                             metrics with definitions and sources (DEFINITIONS); the generator (since 0.3.0) moves all 22 at 10 Hz within each
                             player's top_speed_kmh / acceleration_ms2, tiring with stamina
src/regista/synth/report.py  synthetic realism report: per-90 rates vs Premier League bands; with --league [--repeat N] also league-mode,
                             physical, team-style, leader and role-shape bands (docs/realism-report.md); generator profiles
                             demo/realistic/league. League mode: hidden ratings drive outcomes (data/synthetic/README.md)
src/regista/api.py           FastAPI service: the Product at /, matches (featured flag, clip counts), clips with filters, search,
                             /ask, /chat (with the answer trace), on-demand MP4, reel.mp4, moments.csv, upload → pipeline
src/regista/access.py        who may do what: Product open, Studio behind the view or admin key, writes admin-only
src/regista/studio_api.py    Regista Studio (/studio): the control room's router; /api/studio/* behind the Studio keys
src/regista/static/          product/ (the Product at /: index.html, app.js, product.css, timeline.js), studio/ (the Studio),
                             shared/ (regista.css tokens, regista.js helpers)
src/regista/studio/          the Studio's facts (runs, to-do, data, cache), the local vision jobs runner, and the status CLI
                             (python3 -m regista.studio status [--url URL])
Dockerfile                   python:3.11-slim + fonts-dejavu; uvicorn regista.api:app on :8000 (built by GitHub Actions; no docker here)
docs/architecture.md         two layers, the workflow roles local vs cloud, MCP tools, Azure per stage (running vs planned), auth
docs/demo-storyboard.md      shot-by-shot plan for the sub-2-minute video, voiceover, what is named on screen
docs/plan-two-dashboards.md  the approved plan for the Product and the Studio, the access table, and the agents that built them
src/regista/cloud/           Azure wiring: config (.env), FoundryLabelAgent + FoundryLibrarianAgent (Agent Framework,
                             Regista MCP server as the Librarian's tool), CosmosPersistAgent; agents_for() swaps them in
infra/provision.sh           az CLI provisioning: Foundry resource + project + model, Cosmos DB serverless, AI Search, Container Apps
                             env + registry, App Insights + Foundry tracing, GitHub deploy identity; writes .env
infra/deploy-app.sh          first deploy and secret/setting changes: app identity (pulls its image itself), roles, secrets; waits
                             for a ready revision (infra/lib/aca.sh)
infra/ci-deploy.sh           GitHub Actions deploy (image only) after test, build and in-image smoke test; federated sign-in
infra/restore-library.sh     regenerate the library matches from their seeds and upload them through the live workflow
infra/export-library.py      read-only: library clips + Foundry labels from Cosmos DB into clips.jsonl, checked against the clip rule
infra/SETUP.md               runbook for a new Azure environment (accounts, sign-in checks, provision, deploy, verify)
src/regista/agents/          the roles (roles.py), the Microsoft Agent Framework workflow that runs them (workflow.py: fan-out/
                             fan-in, typed handoffs, dead-letter routing, retries, request_info review, checkpoints), the original
                             orchestrator kept as a reference (orchestrator.py), CLI (python -m regista.agents, --review, --graph)
src/regista/feedback.py      learning from people: human verdicts as annotations, needs_review(), the watchability model retrained
                             from verdicts (logistic regression, JSON), evaluate(); real verdicts live in data/feedback/
src/regista/cloud/search.py  Azure AI Search index regista-clips; SearchIndexAgent ("indexer" role); search_library()
src/regista/cloud/telemetry.py  Agent Framework OpenTelemetry → Application Insights → Foundry Tracing
src/regista/cloud/smoke.py   container smoke test (CI, inside the image): Regista MCP and Azure MCP list their tools; the dashboards'
                             static files and the four sample matches are packaged
src/regista/vision/          the private vision layer v0: shots (camera_segment), identity (calibration, detection, team, kit
                             number, tracking → track/appearance), possession_vision, vision_writer; an Agent Framework vision
                             workflow; trained and measured on Regista's rendered broadcast (docs/vision.md has the numbers)
src/regista/vision/review.py who's who (plan step 3): identity questions + crops, answers applied frame by frame, annotations,
                             terminal reviewer, learn_from_reviews (reader fine-tune); identity_review step in the vision workflow
src/regista/vision/events.py event spotting (events_vision role): pass, cross, shot, save, goal, tackle, interception, carry,
                             take-on, nutmeg from vision positions + possessions; geometric candidates + two trained classifiers
docs/vision.md               what each vision agent does, measured accuracy, and what changes for real broadcast footage
docs/criteria.md             each judging criterion: what Regista does for it and where to check (replaced gap-analysis.md)
docs/workflow.md             the workflow graph (Mermaid, generated by --graph)
src/regista/camera.py        the main-camera model shared by generator and renderer (what is in frame)
src/regista/render/          2D broadcast renderer: scene.py (interpolation, captions, score, clock),
                             draw.py (pitch, players, replays, closeups, crowd, end card, HUD), video.py
                             (parallel MP4 parts + ffmpeg concat), clips.py (per-clip videos, best-first reel)
data/synthetic/README.md     the contract, record by record
src/regista/schemas/        regista-events.schema.json, regista-clips.schema.json (package data)
data/synthetic/sample/       committed sample match syn_0294, "featured": true in its manifest, the Product opens on it (seed 294:
                             home #9 scores, nutmegs a defender, replays, closeup, highlights); library matches syn_0141/syn_0142
                             (seeds 141/142, Foundry labels from Cosmos DB); vis_0201, the vision layer's output on rendered dev
                             match syn_0201 (run offline; Who's who questions and crops in review/)
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
python3 -m regista.recap data/synthetic/sample/syn_0294 --player t_home_09 [--engine foundry]   # the match recap
python3 -m regista.mcp_server --list-tools        # or without the flag: stdio MCP server for any MCP host
python3 -m regista.synth.report data/synthetic/sample/syn_0294
python3 -m regista.season build && python3 -m regista.season table && python3 -m regista.season players --position FW --sort take_ons_won
python3 -m regista.synth.report --profile realistic --seeds 21 22 23 --minutes 30
python3 -m regista.synth.report --league [--repeat 6] [--out docs/realism-report.md]   # the league against every band (6 seasons pooled)
python3 -m regista.season.audit                                # split-half reliability, the top scorers (Femi Toure first)
python3 -m regista.season.metrics --rank goals --position FW   # the terminal's metrics engine; --player pl_bro_09 for one player
python3 -m pytest -q -m slow                                   # the slow tests (their own CI workflow)
python3 -m regista.agents data/synthetic/sample/syn_0294 --player t_home_09 --query "find me Castellanos doing a nutmeg"
uvicorn regista.api:app          # viewer at http://localhost:8000, OpenAPI at /docs
az login && ./infra/provision.sh # Azure: writes .env; then add --cloud to regista.agents (Foundry + Cosmos)
python3 -m regista.vision data && python3 -m regista.vision train --models models/vision    # vision: render data, train
python3 -m regista.vision run VIDEO --roster MATCH_DIR --out OUT --workflow                 # video in, event stream out
python3 -m regista.vision evaluate --set fresh --models models/vision                    # score frozen models on fresh matches
python3 -m regista.vision train-events && python3 -m regista.vision evaluate-events --set dev   # the event spotter
python3 -m regista.vision run VIDEO --roster MATCH_DIR --out OUT --workflow --review   # asks who's who at the terminal
python3 -m regista.vision learn-from-reviews OUT ...                         # fine-tune the reader on answered reviews
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

**Vision (2026-10-20):** the Identity role now exists as a vision agent (`regista.vision`), alongside Shot and Possession agents, wired as a second Agent Framework workflow whose output directory is the intelligence workflow's input. Trained and measured only on rendered footage so far: seeds 201-206 are a development set (tuned against), seeds 301-303 are fresh matches scored with frozen models only (v4, 2026-10-21: clip recall 0.75, precision 0.94). Never tune against 301-303; make a new fresh set instead. Tested at 640x360, 10 fps only; the shot model fails at 720p and degrades at 25 fps. **Vision footage is rendered without captions** (`captions=False`): the renderer's captions name the event, and the v2 shot model had learned to read them for replays (shot model v3 retrained without). **Nor with the holder's name label and ring** (`Style.labels`/`holder_ring`, off for vision via `vision_style`): they caused false detections and the event spotter had learned from them; v4 models (`models/vision_v4`, pass `--models`) are trained without them, `models/vision` keeps v3. **Event spotting** (`events_vision` role, `regista.vision.events`) on fresh matches (v4): passes 1.00/0.76, shots 0.80/0.80, take-ons 0.82/0.50, nutmegs 0.67/0.67 (precision/recall). The generator stages take-ons and nutmegs in the recorded tracks (`_duel`, `_apply_duels`) without changing any event; a test pins the committed sample. Real broadcast footage is next (see docs/vision.md, last section). Trained models live in `models/vision/` (git-ignored).

**Status (2026-10-20, later):** the pipeline runs as a Microsoft Agent Framework workflow (`regista.agents.workflow`) with a human-in-the-loop review step, an optional Azure AI Search indexer role, and the Foundry Librarian calling two MCP servers (Regista's and Microsoft's Azure MCP Server). See docs/gap-analysis.md. Earlier: the Label and Librarian roles run on Microsoft Foundry (`gpt-5-mini`) through Microsoft Agent Framework, the Librarian calling Regista's MCP server as its tool, and the Persist role writes to Cosmos DB; `python3 -m regista.agents … --cloud` uses them, and uploads on the live app use the Foundry Label agent (uploads pass no questions, so the Foundry Librarian and Azure MCP run only from the CLI with `--query`). Previously: a local, rule-based v0 of this pipeline exists in `src/regista/agents/` (roles Ingest, Validator, Possession, Clip, Label, Persist, Librarian; the Identity role belongs to the private vision layer and is played by the generator for the demo). It has distinct roles with declared inputs and outputs, shared state handed along, retries, a per-attempt trace, and a dead-letter file; downstream agents are skipped, not crashed, when an upstream one fails. The Microsoft Agent Framework version keeps the same roles, state keys, and trace, swapping the rule-based Label and Librarian agents for Foundry-backed ones once Azure exists. Tools are exposed today through `regista.mcp_server` (local MCP, stdio).

---

## 4. Working agreements for Claude

- Keep this file current. When the idea changes, edit section 2; when the stack changes, edit section 3.
- Never commit raw broadcast video, large model weights, or secrets. `.gitignore` covers the common cases; keep it that way.
- Name a hero technology in commit messages and docs only when the change actually uses it. Never list a service as part of the architecture until code runs against it; mark it "planned" until then. Judges read the repo and will check.
- Do not claim GitHub Copilot Agent Mode (or any tool) in the pitch unless it was genuinely used and the evidence exists.
- Keep the README demo-ready: a judge should be able to understand and run the project from it.
- The demo video is under 2 minutes. Design features so they demo well in that window.

## 4.1 Azure (live since 2026-10-20; second environment since 2026-10-21)

**Current environment (since 2026-10-21): Azure for Students.** Live app
https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io, revision `regista-api--d1021183822`
(image f01d587), then every push to `main` deploys itself through CI.
- Subscription "Azure for Students" (3f0ab090-…, $100 credit, expires 2027-10-21, stops at the credit: no card) in the
  **Northeastern University** directory; Zaid signs in as his member account al-qadi.z@northeastern.edu (Owner of the
  subscription, not a directory admin). The same directory holds **"SPS Shared Services"**, the university's
  subscription, which `az login` makes the default: never create or change anything there.
- Run the infra scripts with `SUBSCRIPTION="Azure for Students" LOCATION=francecentral RG_TAGS="Owner=al-qadi.z@northeastern.edu;Cost Center=Azure for Students;IaC managed=Qadzilla/Regista"`.
  A policy allows only francecentral, germanywestcentral, canadacentral, denmarkeast, belgiumcentral; resource groups
  must carry the tags Owner (email), Cost Center and IaC managed (resources inherit them).
- `regista-rg` in France Central: Foundry `regista-foundry-3f0ab0` (project `regista`, gpt-5-mini GlobalStandard, 10 of
  500 quota), Cosmos DB `regista-cosmos-3f0ab0` (serverless), AI Search `regista-search-3f0ab0` (free), Container Apps
  env `regista-env` (workload profiles mode: "express" environments cannot pull with the app's identity) + app
  `regista-api`, registry `registaacr3f0ab0`, Application Insights `regista-appi` on the env's workspace (0.1 GB/day).
- **Player view (since 2026-10-22):** storage account `registast3f0ab0` (shared-key login off, no public blobs) with
  containers `uploads`, `matches`, `models` (the trained vision models, private) and the queue `vision-jobs`; Container
  Apps Job `regista-vision` (event trigger, KEDA azure-queue scaler signing in with the job's system identity, 2 CPU /
  4 GiB, `python -m regista.player.worker --once`, roles AcrPull + Storage Blob/Queue Data Contributor), made by
  `infra/deploy-job.sh`; CI keeps its image in step with the app. Storage needed `Microsoft.Storage` registered (Azure
  says "SubscriptionNotFound" otherwise). `job update --args "-m"` fails (the CLI reads the dashes), so the command is
  set with `az resource update`.
- **Branch images:** ACR Tasks (`az acr build`) are blocked on this subscription too. Pushes to `feature/**` run the
  workflow's test and build and push `regista:branch-<sha>` (never `latest`) as the app registration
  `regista-github-build` (AcrPush on the registry only, federated for `refs/heads/feature/player-view`; variable
  `AZURE_BUILD_CLIENT_ID`). The deploy job runs on `main` only. Other feature branches test, build and smoke-test but
  push nothing (the build identity trusts only the branches listed in the workflow's PUSH condition; add a federated
  credential and the branch name there to push images for another branch). Use a branch image for the vision job with
  `IMAGE=…:branch-<sha> ./infra/deploy-job.sh`; the live app is untouched.
- **End to end in Azure, 2026-10-22** (branch image a6a8037, local app on the real storage, live app untouched): a
  3-minute synthetic film for Femi Toure (pl_bro_09) went upload → Blob → queue → job execution `regista-vision-2cvlj`
  (3 min 5 s: shots 17 s, identity 126 s) → needs_review with 2 questions; both answered yes (checked against the
  film's ground truth and the crops) → done; the match joined his profile (11 appearances). His moments: 4 of 5 found,
  4 of 5 correct. The first try failed at shots: the image had a newer scikit-learn than the models were pickled
  with; scikit-learn is now pinned to 1.7. The failed test upload up_6ae3bb64d6 was deleted from storage (2026-10-22); up_8807d7835c (done) stays as the demo upload.
- Keyless for real: key login off on Cosmos DB and Search; the registry has no admin user (the app pulls with AcrPull);
  GitHub Actions deploys as app registration `regista-github-deploy` (owned by Zaid; federated credentials for both
  GitHub subject formats, `main` only). The remaining secrets are the write token and the App Insights connection
  string (Container Apps secrets; values in `.env`).
- Verified 2026-10-21 (read-only except the library restore): health (Foundry, Cosmos DB, Search, Azure MCP, tracing),
  three matches (syn_0294, syn_0141, syn_0142; 141/142 uploaded through the token-gated workflow, Foundry-labelled,
  8 Search documents), Ask Foundry calling `search_index_query` in the container, a two-turn Foundry Chat, writes without
  the token refused (401), spans in Application Insights.
- Old `.env` (first environment) is at `~/.regista-old.env`; provision.sh refuses a `.env` written for another subscription.
- No budget alert (none set; the offer stops at its credit). Cost estimate: about $10-15 through judging.

**First environment (locked since 2026-10-21; do not link to it).** Its directory is locked: its only admin was a
personal account blocked by security defaults for command-line sign-in, then converted to an internal account whose
generated password was lost. Its app (https://regista-api.ambitioussand-4ee47ff4.eastus.azurecontainerapps.io, image
229f71f) keeps serving until its free trial ends (about 2026-11-19) and cannot be changed or deleted. Its notes, kept
for the record:

- Subscription: Azure free trial on Zaid's account ($200 credit, 30 days, ends about **2026-11-19**). The rules require the demo to stay reachable free of charge until judging ends **2026-11-10**, so the trial covers judging with about a week to spare. Do not upgrade to pay-as-you-go without asking Zaid.
- Resource group `regista-rg`, East US: Foundry resource + project `regista` + `gpt-5-mini` deployment; Container Apps env `regista-env` + app `regista-api`; Container Registry (Basic). **Cosmos DB is in East US 2** because East US had no capacity.
- The free trial blocks ACR Tasks, so `az containerapp up --source` and `az acr build` fail. The image builds on GitHub Actions (`.github/workflows/build-image.yml`, secrets ACR_LOGIN_SERVER/USERNAME/PASSWORD) and deploys with `infra/deploy-app.sh` (pin `IMAGE=...:<sha>`).
- Auth: the app and the CLI reach Foundry, Cosmos DB and AI Search with Entra ID (`DefaultAzureCredential` / managed identity, role assignments); the code uses no keys. Not keyless everywhere: the Container App pulls its image with the registry admin credential (a Container Apps secret), GitHub Actions pushes with the admin login, and key-based local auth is still enabled on Cosmos DB and AI Search (unused). Say this honestly in docs; never write "keyless everywhere".
- `.env` holds the endpoints plus `REGISTA_ADMIN_TOKEN` and `APPLICATIONINSIGHTS_CONNECTION_STRING`; it is git-ignored and docker-ignored.
- Also in `regista-rg`: Azure AI Search `regista-search-a7fbe6` (**free tier, South Central US**: free tier is not offered in East US); Application Insights `regista-appi` on the existing Log Analytics workspace (daily cap 0.1 GB), connected to the Foundry project for tracing; Cosmos DB container `annotations` for human verdicts and the learned model.
- **Clip videos render on first request** into the replica's disk cache, which every new revision starts empty. Each file renders once (other requests wait), into a temporary name renamed into place, at most `REGISTA_RENDER_CONCURRENCY` (1) at a time; the image sets `REGISTA_PRERENDER=1`, so the featured player's clips render in the background at startup, and the grid loads a video only when its card scrolls into view. Before this, a cold replica answered 503 to the grid (seen 2026-10-21).
- Tests never load `.env` (`REGISTA_DOTENV=""` in tests/conftest.py) and never reach Azure; a guard test enforces it. Each test gets its own feedback folder.
- **Ask Foundry is open but limited** (`REGISTA_ASK_PER_MIN` 3, `REGISTA_ASK_PER_HOUR` 20 per visitor; `REGISTA_ASK_TOTAL_PER_HOUR` 60, `REGISTA_ASK_TOTAL_PER_DAY` 300; `REGISTA_ASK_CONCURRENT` 2). Its tools are public-only by design: never give the public Librarian the Cosmos DB namespace (annotations hold reviewers' notes) or `render_clip`.
- **Writes on the live app need a token.** Uploads, verdicts, reviews and retraining require the `X-Regista-Token` header matching `REGISTA_ADMIN_TOKEN` (in `.env`, deployed as a Container Apps secret). The viewer asks for it once. Reads stay open for judges. `REGISTA_READONLY=1` switches writes off entirely.
- **Never send a request that writes to the live app as a test.** Probe with requests that cannot write (no token, or an invalid body) and check Cosmos afterwards. On 2026-10-20 two test verdicts reached Cosmos while an old revision was still serving; they were identified by timestamp and deleted.
- **A deploy is done only when the new revision is the latest ready one.** `deploy-app.sh` waits for that and prints logs on failure. Traffic weight alone is not proof. Every deploy creates a fresh revision (so changed secrets are read), and `.env` is parsed by `infra/lib/dotenv.sh`, never `source`d.
- The image workflow runs the full test suite, builds the image, and runs `python -m regista.cloud.smoke` inside it (Regista MCP and Azure MCP must list their tools); any failure stops the push. Pull requests get the same checks and push nothing. It rebuilds on changes to `src/`, `tests/`, `data/synthetic/`, `Dockerfile`, `.dockerignore`, `pyproject.toml`; `tests/test_packaging.py` guards `.dockerignore` against dropping package files. `infra/provision.sh` can be re-run: it keeps the existing write token and App Insights connection string in `.env` and reuses the resource group's registry; `deploy-app.sh` no longer duplicates the Cosmos role assignment (the app identity has 7 duplicates from earlier deploys, harmless).
- This environment's Cosmos DB still holds 16 clip and 16 label documents from before ids became player-scoped (`cl_000001` / `lb_000001` style). Zaid approved deleting them on 2026-10-21, but the directory is locked, so they stay until the trial ends. The new environment's Cosmos DB has none (checked 2026-10-21: 2 matches, 8 clips, 8 labels, 0 annotations, all player-scoped).
- Tear down after judging: `./infra/provision.sh --destroy`.

## 4.2 Where we are and what's next (update at the end of every work session)

**Start of every session:** run `python3 -m regista.studio status` (local app) and `python3 -m regista.studio status --url "$REGISTA_APP_URL"` (live) to see the Studio overview: to-do, health, usage, data, cache. It reads `REGISTA_STUDIO_VIEW_TOKEN` from `.env`; it never prints the key.

**As of 2026-10-24.** Part A of the Scout terminal (§2.10) is built on `feature/terminal-engine` (not merged, not
deployed): player attributes, league mode (generator 0.7.0, schema 0.2.0), 10 Hz physical motion, the metrics engine
(127 player, 19 team-style metrics) and its API, after two review rounds and three closing rounds
(`docs/scout-terminal/build/`). On the committed season: 13 of 13 event bands, 14 of 14 physical, 10 of 11 league-mode
(penalties low, indicative on one season), 12 of 14 leaders (indicative). Over six pooled seasons every band holds
(`docs/realism-report.md`). Femi Toure is the top scorer with 3 league goals; his Goal reel runs 23.6 s. 761 tests
plus 12 slow pass. The dashboards' seeds, the storyboard, README, criteria and architecture quote this league.
**Fabric:** the new season is pushed (events 33,624 rows, player_season 3,024), but the notebook's check matches only
328 of 756 rows. Its `LEADERS_SQL` (`src/regista/cloud/fabric_notebook.py`) still ranks percentiles the old way; it
needs FBref's rule and the third-of-club-minutes pool, then `REGISTA_DOTENV= python3 -m regista.season.fabric check`.
Left: that fix, part B (the terminal's screens, sandbox first, then ported into Scout as a Terminal section), merge
and deploy, Zaid's match, the video, the pitch, the public repo, submit by 2026-10-27.

**Earlier, 2026-10-23 (evening).** The Player and Scout dashboards are live (PR #34, merge c4a7b26, revision
`regista-api--d1023210106`; §2.9): `/me` (Femi Toure: Overview, My profile, Matches & videos, Messages, Team,
Settings), `/scout` (Maya Lindqvist, Fairhaven FC: Overview, Find players, Shortlist, Reports, Messages, Team, Settings),
and `/players/{id}` as the one shared profile with a scout bar. Messages, stages, notes, reports, needs and settings are
kept per visitor in the browser. The Scout agent now hears "score" (it ranked by minutes before). Checked live, read-only:
every section at 1440 and 375 px, Femi's 11 matches with his friendly, the Scout agent's answer, no console errors.
657 tests pass. Left: the hook's one-clip-per-goal reel, Zaid's match (Saturday), storyboard and video, pitch, public
repo, submit by 2026-10-27.

**Earlier, 2026-10-23 (late afternoon).** Home's "Running on" row is live (PR #33, merge 73853c4, revision
`regista-api--d1023164500`): the official icons of the eight services, icon first with the full name under it,
built from `/api/health` (which now also reports `container_apps` and `storage`); it replaced the footer's "Built on"
line. Icons: Azure Architecture Center V24, the MCP project's mark, the microsoft/agent-framework icon (Zaid's call on
Microsoft's icon terms, which name diagrams and documentation). Checked live: all eight tiles, no console errors. 620 tests pass.

**Earlier, 2026-10-23 (afternoon).** The redesigned Home (PR #32, merge 7afd88b) is live on revision
`regista-api--d1023155334`, deployed by CI: a left views panel on every page; Home is logo plus one search box across
every match (Data Search or Ask Microsoft Foundry); results grid with each card's match line; the match view (title line
with the Match and Player pickers, timeline, stage, folded recap); Back and Forward between landing, results and match.
Zaid's 13 decisions are in docs/redesign/decisions.md. Checked read-only on the live app: search, card line, match view,
Back and Forward, no console errors. The first search on a fresh revision takes about 25 s (league matches build on demand).
618 tests pass.

**Earlier, 2026-10-23.** `main` is at the latest pushed commit; CI is green. Live since PR #31 on revision `regista-api--d1023055523` (the vision job on the same image): the four views plus **match recaps** (rules and Foundry; verified on the live app for a sample, a league and an uploaded match, and one Foundry recap with all 6 sentences kept and no unchecked numbers). **Microsoft Fabric**: the season and uploads in the `regista_league` lakehouse on Zaid's trial (capacity 9c9f2c26…, until about 2026-12-22); the notebook cross-check matched 756 of 756 rows. Docs: README opens with the four views and a judges' tour; `docs/criteria.md`. 595 tests pass. Left: the demo video (storyboard to update for Scout, Player and recaps), the pitch, making the repo public, submitting.

**Earlier, 2026-10-22 (afternoon).** `main` is at the latest pushed commit; CI is green. Live: Clips (`/`), Studio (`/studio`), Scout (`/scout`, `/players/{id}`) and, since PR #28, the **Player view** (`/me`, §2.6) on revision `regista-api--d1022150227` (after CI's deploy, `deploy-app.sh` gave the app `REGISTA_STORAGE_ACCOUNT` and its storage roles); the vision job `regista-vision` runs main's image. Verified read-only on the live app: `/me`, the processed upload's match and profile, uploads refused without the token. 551 tests pass.

**Earlier, 2026-10-22 (morning).** `main` is at the latest pushed commit; CI (tests, image build, smoke test, push, deploy) is green. Live: the Clip view (`/`), the Studio (`/studio`) and, since PR #25, the **Scout view** (`/scout`, `/players/{id}`, §2.5) on revision `regista-api--d1022062451` (verified read-only, including one Foundry Scout answer that called `search_players`). 501 tests pass.

**Earlier, 2026-10-22 (early).** `main` is at a537d2c plus docs; CI (tests, image build, smoke test, push, deploy) is green; the
live app serves **the two dashboards** (PR #18, deployed by CI 2026-10-22 00:56-01:09 UTC): the Product at `/` and Regista Studio
at `/studio` (plan and the agents that built it: docs/plan-two-dashboards.md; PRs #4-#17 merged into `ux/two-dashboards`, then
#18 to `main`). 410 tests pass, on FastAPI 0.128 and on 0.141 as CI installs it. Checked on the live app after the deploy,
read-only: health (Foundry, Cosmos DB, Search, Azure MCP, tracing), four matches with video (syn_0294 featured, syn_0141,
syn_0142, vis_0201), both pages and their scripts, the CSP and frame headers, Studio reads and writes refused without a key,
render limits (width 999 gives 400), timeline fields, no console errors. **The Studio view key is live** (added to `.env` and
set by one `infra/deploy-app.sh` run on 2026-10-22, same image, revision `regista-api--d1022011224`); checked with it read-only:
role view, overview (to-do, Cosmos DB and Search counts, usage, prerender), Who's who (3 questions), feedback, and a write
attempt refused with 403.
Audits J1-J3 and fixes K1-K5 are recorded in the PRs; K5 found the renderer drew the ball holder's name and ring into vision
footage, removed them and retrained (models/vision_v4, local); fresh clips 0.75 / 0.94 (docs/vision.md).

**Built and working:** event-stream contract (schema 0.1.1) and synthetic generator; 2D broadcast renderer; clip rule and labeller; Librarian (rule-based locally, Foundry with `--cloud`); Regista MCP server; the Agent Framework workflow with human review, retries, dead letters and checkpoints; learning from verdicts (watchability model); Cosmos DB, AI Search, Foundry tracing; token-gated FastAPI app on Container Apps; vision layer v0 on rendered footage (fresh-match clip recall 0.75, precision 0.94 with v4; docs/vision.md).

**Audited 2026-10-20** by independent agents; every finding was fixed or is listed below. The full record is in commits 6d1a870 and d1de317.

**Waiting on Zaid:**
- Footage: our own consenting match (§1.5), ready **Saturday 2026-10-24** (Zaid, 2026-10-21). Bring: video files, the team sheet (name, number, team), notes of key moments. Then: label, retrain the shot model on that format, run vision end to end, cut the demo.
- First real Keep/Drop verdicts (the Studio's review queue, admin key).
- Give judges the Studio view key (`REGISTA_STUDIO_VIEW_TOKEN` in `.env`) in the submission form, never in the repo.

**Next build work, in order (not blocked on footage):**
1. ~~Make the hero tech visible on the live app~~ **Done and live 2026-10-20** (PR #1, image 229f71f, revision `regista-api--d1020232137`): Ask Foundry with public read-only tools, matches read back from Cosmos DB, health/footer naming the stack. Verified from the container: Foundry answered, `search_index_query` ran through the Azure MCP Server, spans reached App Insights. Container tracing had never worked before: deploy-app.sh cut the connection string at ';' (fixed in infra/lib/dotenv.sh).
2. ~~Event spotting in the vision layer~~ **Done 2026-10-20** (docs/vision.md "Event spotting"). Weak spots: nutmeg and take-on recall (limited by possession recall ~0.76 and naming), tackles recall 0.56.
3. ~~Identity corrections from Zaid (plan step 3)~~ **Done 2026-10-21** (docs/vision.md "Who's who"): questions + crops, workflow pause, viewer panel, terminal; answers fix the match (12 simulated answers per dev match: clips 0.76/0.92 -> 0.83/0.95) and fine-tune the reader (neutral-positive on rendered footage). Found: name_tracks leaves correct tracks unnamed when time spans merely overlap (same flaw fixed in review); worth fixing in naming itself, measured on dev only.
4. ~~A conversational Librarian (plan step 7)~~ **Done 2026-10-21**: `regista.conversation` + `POST /api/matches/{id}/chat` + the viewer's Chat panel with play-as-reel; rules engine checked in the browser. The Foundry engine is tested with a stand-in model only: the local Azure CLI token is blocked by security defaults (AADSTS530035) until Zaid runs `az login` again; verify it then, or on the live app after a deploy he approves.
5. ~~A 90-minute run~~ **Done 2026-10-21** (docs/vision.md "A full 90-minute match"): fresh match scored once: 0.34x real time, goals 5/5, clips 0.86/0.94. It exposed and fixed: interception vs recovery is not observable (spotter v2 spots "ball won"), early event timing, renderer memory (4.6 GB -> 225 MB); probing and sampling no longer decode whole videos.
6. ~~Azure~~ **Done 2026-10-21**: the first directory locked, a pay-as-you-go signup was refused, and the environment was
   rebuilt on Azure for Students (§4.1) with every feature live (Chat, Who's who, Ask Foundry, library) and CI deploys.
   Remaining: demo video, Zaid's recorded match, make the repo public, submit by 2026-10-27. The unused GitHub secrets
   ACR_LOGIN_SERVER/USERNAME/PASSWORD were deleted on 2026-10-21 (Zaid's go-ahead); the repo now has no Actions secrets.
3. Vision for real footage: frame sampling inside ffmpeg with gap-normalised motion features, a person detector instead of discs, a real homography; designed now, trained when the footage arrives.
4. Demo video (docs/demo-storyboard.md needs a rewrite around the real match), pitch text, make the repo public before 2026-10-27.

## 5. Open questions

- **Decided 2026-10-19 (unsupervised run):** the renderer uses the ffmpeg bundled in the `imageio-ffmpeg` wheel (pip, no system install); the featured sample player is the home 9 (seed 294) because a goal by the 10 is a one-in-eighty event in the simulator; the generator keeps a `demo` profile for dense 3-minute samples and a `realistic` profile for statistics; placeholder annotations are `source: synthetic` + `simulates: human`, never claimed as real review; the FastAPI service is the deployable unit and the Dockerfile is unbuilt on this machine (no docker).
- **Resolved 2026-10-20: footage rights.** No professional footage; we record our own consenting match (see §1.5). Still open: when it is recorded, where it lives locally, and its format.
- **Organiser answer.** Have we asked on the Innovation Studio platform whether licensed clips will be provided or Premier League footage may appear in demos?
- **Demo footage pick.** The 2D renderer now produces broadcast-style video from the synthetic stream (`python -m regista.render`), which is footage we own outright. Still open: whether to add our own recorded match or CC clips on top for realism.
- **Resolved 2026-10-20: hosting.** The FastAPI service + viewer is live on Azure Container Apps (`regista-api`, one replica), see §4.1. It serves only the committed sample match; uploads live on local disk and do not survive a restart.
- Team: solo or up to 4?
