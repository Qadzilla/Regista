# Regista demo video: storyboard (target 1:52, hard limit 2:00)

Rewritten 2026-10-21 around what runs today; beats 4-7 rewritten the same day for the two dashboards (the Product and Regista Studio, on `ux/two-dashboards`). Record beats 4-7 only after that branch is merged and deployed. Every shot shows something that actually runs: the live app on Azure, or the vision layer run from this repository on a laptop. Judges may score from this video alone, so nothing here is staged, mocked or claimed ahead of the code.

## Rules for this video

- **Footage.** Only footage we own: Regista's own rendered broadcast (`python3 -m regista.render`) and our own recorded match, filmed with every player's written consent (CLAUDE.md §1.5). Never Premier League or other broadcast footage, video-game footage, or SoccerNet clips. No club crests or league logos on screen.
- **Name only what runs.** On screen and in the voiceover, the Microsoft technologies named are exactly: Microsoft Foundry, Microsoft Agent Framework, Azure MCP Server, Azure Container Apps, Azure Cosmos DB, Azure AI Search, Application Insights, and GitHub Actions signing in to Azure with OpenID Connect. Not Fabric, AI Vision, Video Indexer, Speech, Translator, or GitHub Copilot (the project is built with Claude Code; Copilot is never claimed).
- **Live app read-only on camera.** Record against https://regista-api.kindfield-ba17f67b.francecentral.azurecontainerapps.io. No uploads, Keep/Drop verdicts or Who's who answers on the live app: they write, and they need the token, which must never appear on screen. The Studio view key never appears on screen either: paste it off camera. Who's who is answered on a local run (beat 4).
- **Numbers.** Only numbers from `docs/vision.md`, `docs/realism-report.md`, or measured on our own match, captioned with what they were measured on. Vision numbers come from rendered footage; say so.
- **Music.** None, or a track whose licence we can show. Judges may stop at 2:00; the cut ends at 1:52 to leave room.

## What runs where (checked 2026-10-21)

| Beat | Where it runs | Checked |
|---|---|---|
| Vision layer | Laptop, from this repository (models in `models/vision/`, never deployed) | docs/vision.md; models present on Zaid's Mac |
| Who's who, answered | Regista Studio on the laptop (`localhost:8000/studio`, no keys set locally, so it is open), match `vis_0201` from the local vision run: answering needs that run's identity result, which never leaves the laptop | `GET …/vis_0201/identity-review` lists the questions |
| Who's who on the live app | Read-only: the Studio with the view key shows `vis_0201`'s 3 questions and crops; answering there returns 409 and says why. Not filmed | |
| The Product: ask box, timeline, stage | Live app, revision deployed by CI from `main` after the merge | `GET /api/health`: `librarian: foundry:gpt-5-mini`, `azure_mcp: true`, `tracing: true`, Cosmos DB and Search on |
| Foundry labels | Live app, match `syn_0141`: its labels were written by `foundry:gpt-5-mini` through the cloud workflow, stored in Cosmos DB, and exported read-only into the image, so the cards carry the "Labelled by Microsoft Foundry" badge | `GET /api/matches/syn_0141/clips` |
| Ask box turns | Instant engine on `syn_0294`; replies below are the real output (`regista.conversation.chat_turn`, checked on 2026-10-21 against the branch) | run locally, same code as the live app |

## Assets to prepare

| Asset | How |
|---|---|
| Rendered broadcast for the hook | `python3 -m regista.render data/synthetic/sample/syn_0294 --out docs/demo/syn_0294.mp4` (1280x720, 25 fps; the nutmeg and goal are in the first minute) |
| Vision input video and team sheet | `python3 -m regista.vision data` renders the development matches without captions at 640x360, 10 fps, under `/tmp/regista_vision` (video in `video/`, team sheets in `matches/`). Use `syn_0201` |
| Vision run, recorded in a terminal | `python3 -m regista.vision run /tmp/regista_vision/video/syn_0201_640x360_10fps.mp4 --roster /tmp/regista_vision/matches/syn_0201 --out docs/demo/vis_0201 --match-id vis_0201 --workflow` (about 95 s; speed it up in the edit and label it; the trace table prints at the end, one row per agent). It also leaves the Who's who questions and crops in `docs/demo/vis_0201/review/`. Adding `--review` pauses the run at the terminal to ask them instead; leave it off for this take. Then `python3 -m regista.agents docs/demo/vis_0201 --player t_home_09` and `python3 -m regista.render.clips docs/demo/vis_0201 --player t_home_09 --out docs/demo/vis_0201_clips` |
| Local Studio for Who's who | `REGISTA_DATA=docs/demo uvicorn regista.api:app`, open http://localhost:8000/studio, tab Who's who, match `vis_0201`; it lists the questions the vision run left in `docs/demo/vis_0201/review/` (the directory name and `--match-id` must agree). Answering here writes only to the local folder. Check the Studio's Who's who tab answers before recording (the Studio page is the last piece built on the branch) |
| Live app, warmed | Open the Product (it opens on `syn_0294`) and play each Castellanos clip once before recording, so the on-demand renders are cached and the reel plays without waiting |
| Foundry rehearsal | One rehearsal question in the ask box with the engine on Foundry before recording (limits: 3 a minute, 20 an hour per visitor). Open "How Regista answered" and check the steps list both `search_clips` (Regista MCP server) and `search_index_query` (Azure MCP Server); rephrase if not |
| Proof shots | Azure portal, resource group `regista-rg` (Foundry, Cosmos DB, AI Search, Container Apps, Application Insights); Foundry project → Tracing (or Application Insights → Transaction search) showing `invoke_agent regista-librarian` with `execute_tool search_index_query`; GitHub → Actions, a green `build-image.yml` run on `main` |
| Our own match | See "Zaid's match" below |

Screen-record at 1920x1080, browser zoomed so text reads on a phone, dark terminal with a large font. Hide bookmarks, other tabs, notifications, and the subscription id in the portal.

## Shot list and voiceover

Timings assume about 125 spoken words a minute, slower than conversational pace, so typing and clicks have room. The words-per-second column is checked below.

| # | Time | On screen | Voiceover | Named on screen |
|---|---|---|---|---|
| 1 | 0:00–0:09 (9 s) | **If our match is ready:** our own footage, the best on-ball moment (a nutmeg or a goal), 4 s. **Otherwise:** the rendered broadcast, Castellanos (9) nutmegs a defender and scores, with the director's slow-motion replay. Title over the last 3 s: "REGISTA · every touch · every replay · every player". | "Editors and scouts lose hours scrubbing through match footage for one player's moments. Regista finds them in seconds." | Regista |
| 2 | 0:09–0:25 (16 s) | Split screen. Left: the vision input, Regista's rendered broadcast without captions, playing. Right: the terminal running `python3 -m regista.vision run … --workflow`; the trace prints shots, identity, identity_review, possession_vision, events_vision, vision_writer, each ok. Label in the corner: "real run, sped up ×6". Lower third for the last 5 s: "Fresh matches, frozen models: clips 76% recall, 94% precision · full 90 minutes: 5 of 5 goals · measured on Regista's rendered broadcast". | "It starts with video. An Agent Framework workflow splits the broadcast into shots, reads kit numbers and team colours, tracks every player, works out who has the ball, and spots passes, shots and nutmegs." | Microsoft Agent Framework (vision workflow, runs locally) |
| 3 | 0:25–0:37 (12 s) | **Our match slot.** Pick the version that is true on the lock date (see "Zaid's match"). **A:** our footage left, Regista's output right (the clips it cut for one player, or the event list), caption with numbers measured on our match. **B:** our footage, then only the stage that ran on it (for example the shot split as a timeline, or the Who's who crops), caption "Our own match, filmed with consent · [stage] runs on it; the rest is in progress". **C (fallback):** the 90-minute rendered run: the terminal's final summary and one clip from minute 80-something, caption "Full 90-minute match · 30.6 minutes on a laptop · 5 of 5 goals · clips 86% recall, 94% precision · rendered footage". | **A:** "This is our own match, filmed with every player's consent. Same pipeline, real footage: [one measured result, under ten words]." **B:** "This is our own match, filmed with every player's consent. [Stage] already runs on it; the rest of the pipeline is next." **C:** "A full ninety-minute match runs on a laptop in about half an hour: all five goals found, and 86 percent of every starter's clips." | **A/B:** "Our own match · every player consented". **C:** none |
| 4 | 0:37–0:47 (10 s) | Regista Studio running locally (`localhost` visible in the address bar, caption "running locally"), tab Who's who, match `vis_0201` (or our match, if its vision run left questions): a ringed crop, "Who is this player?", the top candidates. Click the right one and save: the match is recomputed. | "In the Studio, when it isn't sure who a player is, it asks. One answer corrects the whole match and teaches the kit-number reader." | Regista Studio · human in the loop (Agent Framework `request_info`) |
| 5 | 0:47–1:01 (14 s) | The live app (address bar shows `azurecontainerapps.io`). The Product opens on `syn_0294`: the stage plays Castellanos's goal, 4 s. The timeline under the ask box: kick-off to full time, the goal marked, every clip coloured by kind (on the ball, replay, highlight, closeup), his moments lit and the rest dimmed; hover a replay marker for its title, click the goal marker and it plays on the stage, 5 s. Switch the match picker to `syn_0141`: zoom on a card with the badge "Labelled by Microsoft Foundry" and its explanation ("Scored 0.56 because…"), 5 s. Lower third: "Labels written by Microsoft Foundry (gpt-5-mini) · stored in Azure Cosmos DB". | "The event stream feeds the live app on Azure Container Apps: every clip of a player, every replay he's in, on one timeline, labelled and explained by Microsoft Foundry." | Azure Container Apps, Microsoft Foundry, Azure Cosmos DB |
| 6 | 1:01–1:18 (17 s) | Back on `syn_0294`, the one ask box with the switch on **Instant**. Click the example chip "Find me Sami Castellanos doing a nutmeg", then type three follow-ups; each reply appears above the box, and the grid, the timeline and the stage follow it. 1. → "3 moments for Sami Castellanos (9) · nutmeg. Best: goal at 1'". 2. "now the replays" → "1 moment … nutmeg · replays only: nutmeg · half-speed replay from high and wide, at 1'", the replay on the stage. 3. "everything he did" → "11 moments for Sami Castellanos (9) · any moment". 4. "make that a reel" → "Here is a reel of the best 8 of 11 moments for Sami Castellanos (9) …, best first", and the stage starts it ("Reel · clip 1 of 8"); let 3 s play. Open "How Regista answered" under one reply for 2 s: "Ran in-process: no model, no MCP" and its three steps. Speed up the typing in the edit. | "Then just ask. Find me Castellanos doing a nutmeg. Now the replays. Everything he did. Make that a reel. Each follow-up builds on the last, and every reply says how it understood you." | The ask box (the conversational Librarian) |
| 7 | 1:18–1:34 (16 s) | Flip the switch to **Foundry** and ask the rehearsed library question in the same box (for example "Across every match in the library, who had shots on goal?"). Hold on the reply, then open "How Regista answered": "answered by foundry:gpt-5-mini" and the steps in order with their times: the agent `regista-librarian-chat`, the model `gpt-5-mini`, `search_clips` on Regista MCP server, `search_index_query` on Azure MCP Server. The panel replaces the old tool lower third; keep one small caption: "Azure MCP Server → Azure AI Search". Last 3 s: the Tracing view with the same spans (`invoke_agent regista-librarian-chat`, `execute_tool search_index_query`). | "Switch to Foundry: a Foundry model answers through Agent Framework, calling two MCP servers, Regista's own and Microsoft's Azure MCP Server, which searches every match in Azure AI Search. Every step is shown, with its time." | Microsoft Foundry, Microsoft Agent Framework, Azure MCP Server, Azure AI Search, Application Insights (tracing) |
| 8 | 1:34–1:46 (12 s) | Azure portal: `regista-rg` resource list, 4 s. Application Insights or Foundry Tracing: a workflow's spans, 3 s. GitHub Actions: the green run, steps test → build image → smoke test → push → deploy, with the `azure/login` step, 5 s. Lower third: "Every push to main: 209 tests, image build, in-image smoke test, deploy (OpenID Connect, no stored Azure credential)". | "Clips and labels live in Cosmos DB, every agent step is traced in Application Insights, and GitHub Actions tests and deploys every push, signing in through OpenID Connect." | Azure Cosmos DB, Application Insights, GitHub Actions with OpenID Connect |
| 9 | 1:46–1:52 (6 s) | End card: "REGISTA · every touch · every replay · every player". Below: github.com/Qadzilla/Regista and the live app URL. | "Regista. Every touch, every replay, every player. Found instantly." | Regista |

Before recording beat 8, check the test count in the run's log and change the caption if it is no longer 209. The repository has no GitHub Actions secrets (the old ACR_* ones were deleted on 2026-10-21), so the "no stored Azure credential" caption is exactly true; check `gh secret list` is still empty before recording.

## Timing check

| # | Seconds | Voiceover words | Words per second |
|---|---|---|---|
| 1 | 9 | 18 | 2.0 |
| 2 | 16 | 34 | 2.1 |
| 3 | 12 | 24 (C; A and B must stay at or under 26) | 2.0 |
| 4 | 10 | 24 | 2.4 |
| 5 | 14 | 29 | 2.1 |
| 6 | 17 | 33 | 1.9 |
| 7 | 16 | 36 | 2.3 |
| 8 | 12 | 28 | 2.3 |
| 9 | 6 | 9 | 1.5 |
| **Total** | **112 (1:52)** | **235** | **2.1 (126 a minute)** |

Calm narration runs about 2.5 words a second, so every beat has slack; beats 4, 7 and 8 are the tightest. If a take runs long, cut screen time from beat 6 (typing) first, never the end card. Exported length must read 1:55 or less.

## Zaid's match

**Footage arrives Saturday 2026-10-24. Lock date: Sunday 2026-10-25, evening.** Whatever runs on our footage by then decides version A, B or C of beat 3 (and whether beat 1 opens on our footage). After that, only editing.

- **A** needs the vision layer to cut clips from our footage, with a few numbers measured against Zaid's own labels of that match.
- **B** needs at least one stage running on it (the shot model retrained on its format, or identity questions with real crops). Show only that stage.
- **C** needs nothing new: the 90-minute rendered run already exists (`docs/vision.md`, "A full 90-minute match").

Never put our footage on screen with a caption that implies more ran on it than did.

### What Zaid needs to record (footage ready Saturday 2026-10-24)

1. **Consent first.** Written consent from every player before filming, covering recording, training models on the footage, and showing it publicly (demo video, judges, the live app). Anyone who does not consent stays off the pitch; keep bystanders out of frame.
2. **Kits.** Numbered bibs with large numbers on the back and, if possible, the front; two clearly different team colours, neither green nor close to grass; goalkeepers in a third colour. A ball that stands out from the grass.
3. **Camera.** A phone on a tripod, as high as possible (stand, bleachers, a balcony) at the halfway line, landscape. 1080p or 720p at a fixed 25 or 30 fps (turn off auto frame rate and HDR). Pan to follow the ball like a broadcast, or keep it wide and still; do not zoom digitally. A second phone behind one goal is a bonus: it gives us a replay angle.
4. **Length.** At least two halves of 15-20 minutes. No music playing nearby (copyrighted audio ends up in the video).
5. **Team sheet.** A CSV or note: name, number, team, kit colours, goalkeepers marked. This is the roster the vision run takes.
6. **Moment notes.** Minute and second of goals, nutmegs, skills, big saves, written on the day (or right after from the video). They become the labels we measure against and the clips we look for.
7. **Storage.** Raw video stays on the laptop, outside the repo (never committed, never uploaded to the live app). Share the files with this project's working folder by path when ready.

## Production notes

- Record beats 2, 3 (version C) and 4 first; they run locally and are repeatable. Record beats 5-7 on the live app last, after the `ux/two-dashboards` merge has deployed and after warming it.
- Beat 7 depends on the rate-limited Foundry engine: rehearse once, wait a minute, record. If a take fails or its steps list only `search_clips`, wait a minute and retry rather than editing the panel.
- Beat 6 uses the Instant engine for an instant, repeatable take; Foundry has its own beat. The Instant / Foundry switch sits beside the ask box.
- Recorded sizes: the renderer writes 1280x720; the vision input is 640x360, so upscale it in the edit and say nothing about its resolution.
- Keep a copy of the exact commands and app revision used on recording day in the submission notes, so judges can reproduce every shot.
