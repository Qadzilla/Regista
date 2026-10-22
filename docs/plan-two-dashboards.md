# Plan: two dashboards, the Product and the Studio

Drafted 2026-10-21 with Zaid, for judging criterion 4 (User Experience and Presentation: an intuitive UX, the project's value made clear, a balanced frontend and backend), with criteria 2 and 3 in mind. **Status: built, audited and live since 2026-10-22** (PRs #4-#17 into `ux/two-dashboards`, audits J1-J3, fixes K1-K5, then PR #18 to `main`, deployed by CI). The Studio view key was set on the live app the same night with one `infra/deploy-app.sh` run.

## 1. The idea

Today one page, `viewer.html`, does two jobs: it is the product (find and watch a player's moments) and the back office (verdicts, retraining, review queues, Who's who). They get in each other's way: a judge sees "model not trained yet" and Keep/Drop buttons that ask for a token.

Split them:

| | **Regista** (the Product) | **Regista Studio** (the control room) |
|---|---|---|
| Who | Content creators, scouts, fans, judges | Zaid, Claude, and judges with a view-only key |
| Where | `/` on the live app | `/studio` on the live app and locally |
| Promise | Ask for a moment, get it, watch it, take it away | See everything Regista is doing, correct it, retrain it |
| Access | Open, as now (rate limits unchanged) | Read: view key or admin key. Write: admin key only |
| Feel | Clean, guided, one ask box | Dense, technical, every number and trace |

One FastAPI app serves both, and the same code runs locally and on Azure. The Studio shows what each place can do. Locally it also runs vision jobs: training, evaluation, and learning from Who's who answers. On the live app those sections say "local only", because the footage and vision models never go to the cloud (CLAUDE.md §1.5).

## 2. Decisions to confirm with Zaid

1. **Names and routes**: Product at `/`, Studio at `/studio`. The look comes later; this plan only fixes structure.
2. **Two keys.**
   - `REGISTA_ADMIN_TOKEN` (exists): everything.
   - New `REGISTA_STUDIO_VIEW_TOKEN`: the whole Studio, read-only. Judges get it in the submission. Claude uses it to read the live Studio, so it never needs the admin key to look.
   - Both are Container Apps secrets. Rotating either one locks out whoever holds the old value.
3. **Who's who (my recommendation):**
   - Answering stays in the Studio, because it is a reviewer's job.
   - The live app gets one demo vision match, the vision layer's output on a rendered development match, so the human-in-the-loop step exists online. Judges see its questions read-only with the view key, and Zaid can answer them with the admin key.
   - In the Product, clips from that match carry an honest badge: "cut from video by Regista's vision layer (run offline on rendered footage)", plus "identity confirmed by a reviewer" where an answer exists.
4. **Both personas, one product.** Creators want the best moments first and a reel to download. Scouts want every touch in match order and a list with timecodes. One switch, "Best first / Match order", plus one action each: **Download reel** for creators, **Export moments** (CSV) for scouts.
5. **"How Regista answered" is visible to everyone**, collapsed by default.
6. **Delivery**: build on an integration branch, `ux/two-dashboards`. The live app stays as it is until the whole thing passes an independent audit, then one merge to `main` deploys it. PR #3 (cold-start fix) merges to `main` first, because everything here builds on it.

## 3. Nothing is lost: where every feature goes

Every endpoint keeps its path and behaviour (the MCP server, tests, scripts and the storyboard depend on them). Three reviewer-only reads move behind the Studio keys. The local default does not change: with no token set, everything stays open.

| Today | Product | Studio | Access change |
|---|---|---|---|
| Match and player pickers | ✔ | ✔ (every match, every player) | – |
| Clip grid, video, tags, watchability, explanation | ✔ (plain-English labels) | ✔ (raw fields, ids, scores, prior vs model) | – |
| Tag chips | ✔ | ✔ | – |
| "needs your review" chip, per-clip "Regista is unsure" note | – | ✔ Review queue | – |
| Search (rules), Ask Foundry, Chat | one ask box (Instant / Foundry); `/search` and `/ask` endpoints kept | ✔ test console: send any query to any engine, see raw JSON | – |
| Play reel | ✔ plus **Download reel** (new) | ✔ | – |
| Keep / Drop verdicts | – | ✔ Review queue | still admin |
| "Learning from people" bar, Retrain | – | ✔ Training | `GET /api/feedback` → view key |
| Who's who panel | badge only | ✔ answer (admin), read (view) | `GET …/identity-review` and crops → view key |
| Workflow review (`GET/POST …/review`): API only today | – | ✔ new UI | `GET …/review` → view key |
| Upload `events.jsonl`: API and script only today | – | ✔ new UI (drag and drop) | still admin |
| Realism report (`…/report`) | linked from "How it works" | ✔ | – |
| Health and stack footer | "Built on" strip + "How it works" | ✔ full health, tool lists | – |
| Broadcast video (`…/video.mp4`) | ✔ "Watch the full match" | ✔ | – |
| Vision run, evaluate, train, learn-from-reviews (CLI only) | – | ✔ Jobs, **local only** | admin |

The public clips endpoint also stops including verdict annotator names. Those stay in the Studio's own endpoint.

## 4. The Product (`/`)

Top to bottom, desktop and phone.

1. **Header**: logo, match picker, player picker ("Sami Castellanos · 9 · Northbridge FC"). Nothing else.
2. **Landing strip**, shown until the first question: one line, "Every touch, every replay, every player, found in seconds." Under it, three example chips that run in the ask box:
   - "Find me Castellanos doing a nutmeg"
   - "Every touch by number 9, in match order"
   - "Make a reel of his best moments"
3. **The ask box** (one input):
   - The engine switch, **Instant** (rules) or **Foundry**. Both go through `/chat`, so follow-ups always keep context.
   - The conversation log sits above the results.
   - Each reply drives the grid, the timeline and the stage, so there is one result set on screen at a time.
   - **"How Regista answered"** (collapsible, under every reply):
     - how the question was understood (player, actions, angles, minutes);
     - the steps in order, each with its time: for example `conversation.step` 2 ms, `Librarian.search_clips` 8 ms, and for Foundry `invoke_agent regista-librarian-chat` 3.1 s, then `execute_tool search_clips` (Regista MCP) 40 ms and `execute_tool search_index_query` (Azure MCP Server → Azure AI Search) 210 ms;
     - which model wrote the reply.
     The Instant path says honestly that it ran in-process with no model and no MCP.
4. **Timeline strip**: the match from kick-off to full time, with periods and goals marked. Each clip is a marker coloured by kind: on the ball, replay, highlight, closeup. Hover shows the title; click plays it on the stage. The current result set is highlighted and the rest dimmed.
5. **The stage**: one large player showing the selected clip or the reel, with its title, tags, and a sentence on why it was cut. Buttons: **Play reel**, **Download reel** (MP4), **Export moments** (CSV: time, end, kind, tags, title, watchability).
6. **Grid**:
   - Thumbnails, loaded lazily (PR #3).
   - Sort with **Best first / Match order**.
   - Plain labels: "On the ball", "Replay", "Highlight", "Closeup" and "Nutmeg", never `on_ball_main`.
   - Badges: "Labelled by Microsoft Foundry" when a label's model is `foundry:*`, "Cut from video" for vision matches.
7. **How it works**, a drawer from the footer:
   - the two layers;
   - the agent workflow graph (generated with `--graph`);
   - which Azure service does what, with a live tick from `/api/health`;
   - the realism report link.
8. **Footer**: "Built on Microsoft Foundry · Agent Framework · Azure MCP Server · Cosmos DB · AI Search · Container Apps · Application Insights", taken from health, so it names only what is running.

**Library matches get video back.** Their event streams are added to the image (regenerated from seeds 141 and 142). Their Foundry labels are exported read-only from Cosmos DB into their `clips.jsonl`, so the image and Cosmos DB agree and the cards keep Foundry's wording. The "no video" card stays for a genuinely Cosmos-only match, worded as information, not failure.

**Explanations in plain English**: the rules labeller's sentence becomes, for example, "A goal, the biggest moment there is, after a carry, a dribble, a take-on and a nutmeg. Cut because he had the ball in the main camera." Same score, same fields, no schema change. The committed sample's `clips.jsonl` is regenerated and the tests updated with it.

## 5. The Studio (`/studio`)

It asks for a key once and keeps it in `sessionStorage` (cleared when the tab closes). The key never goes in a URL, and the page shows which key is in use ("view" or "admin"). Sections, as tabs:

1. **Overview** (`GET /api/studio/overview`, one call):
   - a **to-do list** for Zaid: open workflow reviews, unanswered Who's who questions, clips flagged unsure, matches whose pipeline failed, a stale model;
   - health (Foundry, Cosmos DB, Search, Azure MCP, tracing), the deployed image and revision, and prerender progress;
   - usage: Ask and Chat calls against their limits, this hour and today;
   - data: documents per Cosmos DB container and documents in the Search index.
2. **Review queue**: flagged clips with video, label, model score vs prior, and Keep/Drop. Above it, any paused workflow review with its questions, answered here (`POST …/review`).
3. **Who's who**: today's panel, moved here, for any vision match. The view key sees the questions and crops; the admin key can answer.
4. **Training**:
   - the watchability model: verdict counts, agreement per scorer (from `/api/feedback`), the model's coefficients and version, **Retrain**, and a history of retrains;
   - **vision models (local only)**: the frozen models' fingerprints and measured numbers (from `evaluate` JSON output), plus **Learn from Who's who answers** (the reader fine-tune) as a job.
5. **Runs**:
   - every match with its pipeline run: per-agent status, attempts and timings from `agents/trace.jsonl`, dead letters, labels by model;
   - **Upload a match** by drag and drop (`POST /api/matches`) and watch its run.
6. **Jobs (local only)**: start `vision run`, `evaluate`, `train-events`, `learn-from-reviews`; one at a time, with logs streamed and results kept. On the live app this tab says why it is local only.
7. **Console**: send any question to `/search`, `/ask` or `/chat` with any engine, and see the raw JSON and the trace.

**For Claude**: `python3 -m regista.studio status` prints the overview from a local app or the live one, reading `REGISTA_STUDIO_VIEW_TOKEN` from `.env`. CLAUDE.md gains one line: check the Studio overview at the start of a session.

## 6. Backend changes

- `src/regista/studio_api.py`: a FastAPI router mounted by `api.py`, so Studio work does not collide with Product work in one file. It holds `/studio`, `/api/studio/overview`, `/api/studio/runs`, `/api/studio/runs/{id}`, `/api/studio/data`, `/api/studio/usage`, `/api/studio/cache`, `/api/studio/capabilities`, and `/api/studio/jobs` (local only).
- Auth (`api.py`): `require_studio_reader` accepts the view or admin key; `require_writer` stays admin-only. The access table in §3 is enforced and pinned by one test that walks every route.
- Answer traces:
  - `/chat` and `/ask` responses gain `trace: [{name, kind: agent|tool|model|step, server, ms}]`. For Foundry it is collected from the Agent Framework OpenTelemetry spans of that request (an in-process span processor keyed by trace id), so the timings are real. If spans are unavailable, the tool order without timings stands.
  - Each tool name is mapped to its MCP server (Regista or Azure MCP Server).
- `GET /api/matches/{id}` gains `periods` and `key_moments` (goals with minute and scorer) for the timeline.
- `GET /api/matches/{id}/reel.mp4?clips=…` (new): the reel rendered through `_render_once` (PR #3), with a cap on clip count.
- `GET /api/matches/{id}/moments.csv?player=…` (new).
- `/api/studio/usage`: counters read from the existing rate limiter (no new storage).
- Jobs runner (local only): one background process at a time, logs under `data/studio/jobs/`, never available when `REGISTA_CLOUD=1`.

## 7. The work, broken into agents

Each package is one agent (a Claude Code session in its own worktree, on a branch off `ux/two-dashboards`), with the files it owns, what it needs first, and when it is done. No two packages in the same phase write the same files.

**Phase 0: Foundations** (one agent; everything else waits for it)

| Agent | Owns | Done when |
|---|---|---|
| **P0 Foundations** | `api.py` auth and routing, new `studio_api.py` skeleton, `static/` split into `product/`, `studio/`, `shared/` (CSS tokens, `api()` helper, escaping, label names), `Dockerfile` env, `tests/test_access.py` | `/` serves today's viewer unchanged, `/studio` serves a stub; view and admin keys work; the access table test passes for every route; full suite green |

**Phase 1: built in parallel** (seven agents)

| Agent | Owns | Needs | Done when |
|---|---|---|---|
| **A Product UI** | `static/product/*` | P0 | header, landing strip, one ask box, stage, grid with sort and plain labels, badges, How it works drawer; works at 375 px; nothing from §3's Product column missing |
| **B Answer trace** | `conversation.py`, `cloud/foundry.py`, `cloud/telemetry.py`, chat/ask handlers | P0 | `trace` in `/chat` and `/ask` for both engines; tested with the fake Foundry model; Instant path says in-process |
| **C Timeline and exports** | match endpoint additions, `reel.mp4`, `moments.csv`, `static/product/timeline.js` | P0 | timeline component plus endpoints, tested; reel goes through `_render_once` |
| **D Library with video** | `data/synthetic/sample/syn_0141`, `syn_0142`, a read-only export script | P0 | streams regenerated from seeds; clip ids match Cosmos DB exactly; Foundry labels exported; prerender covers them; image size checked |
| **E Vision demo match** | `data/synthetic/sample/vis_…`, Who's who badge data | P0 | one rendered dev match run through the vision layer, outputs and crops packaged (size checked); its questions served; product badge honest |
| **F Plain-English labeller** | `clips.py` explanation text, sample `clips.jsonl`, tests | – | new sentences, same scores and schema; sample regenerated; suite green |
| **H Studio API** | `studio_api.py` endpoints, `regista/studio/__main__.py` CLI, jobs runner | P0 | every endpoint in §6 for the Studio, tested; the jobs runner refuses on cloud; `status` CLI works against local and live |

**Phase 2** (two agents)

| Agent | Owns | Needs | Done when |
|---|---|---|---|
| **G Studio UI** | `static/studio/*` | H, B | all seven tabs; view key sees everything and can change nothing; admin key can do every write the old viewer could, plus upload and workflow review |
| **I Wiring and docs** | glue between A, B and C in the product, README "What's live", `docs/architecture.md`, CLAUDE.md, storyboard beats 5–7 (the one ask box and the "How Regista answered" panel replace the Ask Foundry button and the lower third) | A, B, C | everything connected; docs name only what runs |

**Phase 3: audit** (independent agents that did not build anything)

| Agent | Checks |
|---|---|
| **J1 Function parity** | every row of §3 works, locally and in a deploy of the integration branch to a local container |
| **J2 Security** | the view key cannot write anywhere; no token in URLs, logs or HTML; the public Librarian's tool set is unchanged (no Cosmos DB, no render); annotator names no longer public |
| **J3 Browser** | Product and Studio at desktop and 375 px, keyboard, empty and error states, cold cache |

I check every finding myself before reporting it to you. Then one PR, `ux/two-dashboards` → `main`, which deploys it. After the deploy I check the live app read-only, and with the view key for the Studio.

**Order in time**:
- PR #3 first.
- P0 the same day.
- Phase 1 runs in parallel once P0 is in.
- Phase 2 as soon as its inputs land.
- The audit, then the merge.
- The demo video is recorded on the merged app (the storyboard is updated by I).

## 8. Risks and how the plan handles them

| Risk | Handling |
|---|---|
| A feature quietly disappears | §3 is a checklist; J1 walks it; endpoints keep their paths |
| A view key that can write | One auth dependency per access level; a test walks every route with no key, the view key and the admin key |
| Merge conflicts from parallel agents | Each Phase 1 agent owns separate files; `studio_api.py` and the `static/` split exist before they start |
| The live app breaks mid-week | Nothing reaches `main` until the audit passes |
| The image grows too large | D and E check sizes (about 1.5 MB per generated match; vision outputs trimmed) |
| Foundry span timings unavailable in some runs | The trace falls back to tool order without timings and says so |
| The Studio claims too much on the live app | Capabilities endpoint; local-only sections say so instead of failing |
