# Touchline — Project Source of Truth

> **Every touch. Every replay. Every player. Found instantly.**
>
> Touchline is an AI system that watches a full 90-minute football broadcast, learns to recognise every player, cuts every moment a chosen player is on the ball (plus every replay and highlight they appear in), labels those moments, and lets you find them through a chatbot: *"find me Pogba doing a nutmeg."*

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

Turn **synthetic, football-realistic** event data (passes, shots, tackles, possession changes, pressure events, match metadata) into explainable match intelligence, real-time narratives, and automated recaps for studio, broadcast, or streaming, personalised per fan. Expected pipeline: **Ingest → Interpret → Explain → Render → Personalize**. "Auto-eventing from a video feed" and "player identification" are explicitly listed as suggested features, which is exactly what Touchline does. A metrics-only or personalisation-only project is considered incomplete.

### 1.5 ⚠️ Data and footage constraint (read before every demo decision)

- The organisers provide **no footage and no dataset**. Section 4.7 of the rules: projects must use synthetic, football-realistic data, and you warrant you hold the rights to any footage you use. The demo video may not contain third-party copyrighted material without permission.
- **How Touchline stays compliant:** raw broadcast footage we have access to is used **privately** for development and model training. The system's **output is a synthetic event dataset** (touch events, player positions, replay markers, clip labels) which is what we submit, publish, and build the demo on. For the public demo, use footage we have rights to (our own recordings, openly licensed clips, or a synthetic/rendered match) and never commit raw broadcast video to this repo.
- "Optimised synthetic data creation" is scored under Technological Implementation, so the event dataset Touchline generates is a first-class deliverable, not a by-product.

---

## 2. What Touchline is

### 2.1 Purpose

Content creation and ease of finding significant moments and clips. Highlight reels and edits are everywhere and are the craze; Touchline makes that process easier. It also serves scouting: a scout can find **every moment a player is on the ball** across a full match, or a season, in seconds.

### 2.2 Input

A raw, full 90-minute game as delivered on broadcast servers (the main broadcast feed with replays and highlights cut in by the director). That is what we have access to.

### 2.3 Workflow (the general first thought)

1. **Train the model on raw broadcast footage** for spatial and facial recognition, player behaviour, and position on and off the ball at all times.
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

## 3. How Touchline maps to the hackathon pipeline and hero tech

This is the initial mapping. Change it as we learn what is practical in the time available.

| Pipeline stage | What Touchline does | Hero technology (initial pick) |
|---|---|---|
| **Ingest** | Pull the broadcast feed, split into frames/segments, detect scene cuts (main view vs replay) | Azure Blob Storage, Azure Functions / Event Grid, Azure AI Video Indexer |
| **Interpret** | Detect and track players, recognise identity (face, kit number, gait), detect ball possession, emit a **synthetic event stream** | Azure AI Vision, custom models hosted in **Microsoft Foundry**, Cosmos DB or Fabric for the event store |
| **Explain** | Label each clip (nutmeg, dribble, shot...), score "worth watching", explain why | Foundry models + **Microsoft Agent Framework** labelling agent, RL-with-human feedback loop |
| **Render** | Cut clips with timecodes, produce machine-readable overlays and reels | Azure Container Apps / AKS workers, FFmpeg, Azure Media handling |
| **Personalize** | Chatbot: natural-language search over labelled clips, per-player reels, multi-language | Foundry Agent + **Azure MCP** tools, Azure AI Speech/Translator, web UI |

### 3.1 Multi-agent design (target category)

Distinct agent roles with shared state and handoffs, so the system does something a single agent could not:

- **Ingest Agent** — segments the feed, flags replays and highlights.
- **Identity Agent** — finds and tracks the chosen player in every frame.
- **Possession Agent** — decides when the tracked player is on the ball.
- **Clip Agent** — cuts and stores clips per the rules in 2.3 step 4.
- **Label Agent** — names the event and scores watchability; asks the human when unsure (RL loop).
- **Librarian Agent** — chatbot interface; translates "Pogba nutmeg" into a query over the clip index and returns clips.

Orchestrated with Microsoft Agent Framework; tools exposed via MCP; failure recovery via retries and dead-letter queues.

---

## 4. Working agreements for Claude

- Keep this file current. When the idea changes, edit section 2; when the stack changes, edit section 3.
- Never commit raw broadcast video, large model weights, or secrets. `.gitignore` covers the common cases; keep it that way.
- Name the hero technology in commit messages and docs when a change uses one. Judges read the repo.
- Use GitHub Copilot Agent Mode where sensible and keep evidence of it (it is a named hero tech).
- Keep the README demo-ready: a judge should be able to understand and run the project from it.
- The demo video is under 2 minutes. Design features so they demo well in that window.

## 5. Open questions

- Which player-identification approach is feasible in 8 days: face recognition, kit number OCR, tracking + manual seed, or a combination?
- Which footage do we have rights to use in the public demo?
- Do we host the chatbot UI as a web app on Azure Container Apps, or keep it simpler for the demo?
- Team: solo or up to 4?
