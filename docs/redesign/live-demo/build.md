# The live demo for judges: build report

Branch `feature/live-demo`, 2026-10-26/27. Not merged, not deployed. The live app is unchanged. Nothing was written to
the live app or to Azure; the only requests to the live app were GETs (health, the catalogue's totals, the processed
upload's record and its `/me` page, and one clip).

The job: judges may score from the live app alone, so it has to explain itself, show its best moments in order, play
them without waiting, and stay up until judging ends on 2026-11-10.

## What was built

| # | Item | Where |
|---|---|---|
| 1 | **`/demo`, the judges' page.** What Regista is in three sentences; the four paths (fans and creators, broadcasters, scouts, players), each a link into its live view; what this server runs right now, read from `/api/health` with Home's icons and flags (only what is running is listed); Fabric and GitHub Actions named as checked outside the app; the synthetic-data note; "Good to know" (read-only, Foundry limits, first-view renders, the Studio key); a big **Take the tour** button. Linked as **Demo** in the left views panel on every page, and from Home ("Take the tour" and "What is Regista?" under the search switch). | `src/regista/static/demo/{index.html,demo.js,demo.css}`, route `GET /demo` in `src/regista/api.py` |
| 2 | **The guided tour.** One card per page: "Step N of M", a title, one or two plain sentences, an optional suggested click, Back, Next (Finish on the last), Exit tour, and Hide (folds the card to a pill). Steps name a URL (the tour goes there) and highlight one element, by id or by a `data-tour` attribute only. The tour's place is in `Regista.store` (key `tour`, this browser only): it resumes after a page load, moves on when the visitor follows a suggested link onto the next step's page, says "Tour paused" anywhere else (with "Back to the tour"), and Exit forgets it. It never clicks, submits or fetches: a step may put words in a box (dispatching `input`, never sending), so a Foundry question is only asked by the visitor pressing Ask. Desktop: a 360 px card bottom right. Phones (<= 720 px): a strip along the bottom; the highlighted element is scrolled above it. | `src/regista/static/shared/{tour.js,tour.css}`, loaded last on `/`, `/demo`, `/scout`, `/me`, `/players/{id}` |
| 3a | **Warm for judging.** At startup (`REGISTA_PRERENDER=1`, already set in the Dockerfile), after the featured player's clips, every clip the tour and the storyboard play, one at a time, counted in `PRERENDER_PROGRESS` (`total` grows by the tour's part; `tour` = planned, rendered, failed). The URLs are not rebuilt by hand: `regista.warm.plan` reads the same JSON the pages read and picks URLs the way the pages do, then each URL is requested through the app in-process (`warm.asgi_get`, a plain GET into the ASGI app, no port, no key), so the cache keys are the pages' own. | `src/regista/warm.py`; `_prerender(tour=True)` and `_prerender_tour()` in `src/regista/api.py` |
| 3b | **Foundry limits for judging.** Defaults raised from 3 a minute / 20 an hour per visitor, 60 an hour / 300 a day for everyone, 2 at a time, to **5 / 40, 120 / 600, 3**. Every `REGISTA_ASK_*` variable still overrides its own. Ask, Chat, the Scout agent and the Foundry recap share this one limiter. | `ASK_DEFAULTS` in `src/regista/api.py`; `docs/architecture.md`, `CLAUDE.md` §4.1 updated |
| 3c | **Daily live check.** A GitHub Actions workflow, daily at 07:23 UTC and on demand, runs read-only checks of the live app until 2026-11-11 (after that it passes without a request). A failed run turns red and GitHub notifies the account that last changed the schedule. The probe is standard library only and runs as a script, with no install, no secret and no token. | `.github/workflows/live-check.yml`, `src/regista/live_check.py` |
| 4 | **Tests.** `GET /demo` classified public in `tests/test_access.py`; the new static files in the smoke test's `STATIC_FILES` (pyproject's package-data globs already cover `static/*/*.{html,js,css}`); the tour's steps; the warm-up plan and the in-process GETs; the probe. | `tests/test_tour.py` (16), `tests/test_warm.py` (11 + 1 slow), `tests/test_live_check.py` (16) |

### Two changes the tour needed

- **A Goal reel on profiles.** Storyboard beat 1 is "Femi Toure's Goal reel", but since the catalogue port (PR #40) the
  profile at `/players/pl_bro_09` has no Goal button: only "Play reel" (the best ten moments). Best moments now has a
  **Goal reel** button beside Play reel, shown when the player has a goal: every goal on the ball in the main view, each
  once, in match order, played clip by clip on the profile's stage ("Goal reel · clip 2 of 5"), for any catalogue player.
  For Femi Toure it plays his five league goals (rounds 1, 1, 6, 8, 10). `profile-view.js` `goalReelIds`.
- **Stable targets.** `data-tour` attributes on the elements steps point at: `goal-reel` and `stat-<key>` (profile tiles)
  in `profile-view.js`, `stage-actions` on Home's stage buttons, `co-uploads` on a competition page's "Uploaded matches"
  heading (`scout.js`), `agent-steps` on an upload's agent list (`me.js`). Nothing else on those pages changed.

## Every tour step

15 steps, in the storyboard's order (`docs/demo-storyboard.md`: hook, clip powerhouse, recap, video in, Microsoft and
agents, catalogue and Fabric, the four paths, close). "Fills" means the tour puts those words in the box; the visitor
presses the button.

| # | URL | Target | Caption (title, text, suggested click) |
|---|---|---|---|
| 1 | `/players/pl_bro_09` | `[data-tour="goal-reel"]` | **Every goal, found.** Femi Toure is the Regista League's top scorer: five league goals, none a penalty. Regista found every one in the footage. *Press Goal reel: each goal once, in match order.* |
| 2 | `/?match=syn_0294&player=t_home_09` | `#timelineWrap` | **Every moment of a match.** Regista watched this match and cut every moment Sami Castellanos is on the ball, plus every replay, highlight and close-up he appears in. Each mark on the timeline is one. *Click any mark to play it.* |
| 3 | `/?match=syn_0294&player=t_home_09` | `#askForm` | **Then you just ask.** Ask in plain words. Data Search answers with Regista's own rules, so no AI model is called. *Press Ask to find his nutmegs.* (fills `his nutmegs`) |
| 4 | `/?match=syn_0294&player=t_home_09` | `#askForm` | **Follow-ups keep the thread.** Regista remembers the question so far, so a follow-up narrows it: now only the replays of those nutmegs. *Press Ask.* (fills `now the replays`) |
| 5 | `/?match=syn_0294&player=t_home_09` | `#recap` | **Explained and recapped.** Every match gets a recap, told from the picked player's side. Each sentence is a link that plays the moment it describes. *Open Match recap, click a sentence, then try Play recap reel.* |
| 6 | `/me?player=pl_bro_09#matches` | `[data-tour="agent-steps"]` | **Video in.** Femi's footage of a friendly went through Azure Blob Storage and a queue to a Container Apps job, where Regista's vision agents ran in turn, each with its time. *Measured on Regista's own rendered footage.* |
| 7 | `/?match=syn_0294&player=t_home_09` | `#askForm` | **Microsoft Foundry and MCP.** Switch to Ask Microsoft Foundry: a Foundry agent (gpt-5-mini, on Microsoft Agent Framework) answers and may call tools. Under its reply, How Regista answered shows each step, and which server ran each tool: Regista's MCP server or the Azure MCP Server. *Pick Ask Microsoft Foundry, then press Ask. Foundry questions are limited to a few a minute per visitor.* (fills `every nutmeg in the library`) |
| 8 | `/scout#competitions` | `#coLine` | **A catalogue of uploaded footage.** Regista is also a catalogue of matches uploaded by players and teams below the professional level: 14 competitions in 10 countries. Every player, club and competition is invented; countries and levels are labels. *Next opens one competition.* |
| 9 | `/scout#competition/co_esp_u19` | `[data-tour="co-uploads"]` | **Checked in Microsoft Fabric.** Each upload says who filmed it and the camera they named. On 26 October 2026 a Microsoft Fabric notebook recomputed every catalogue number from the raw tables: 7,399 of 7,399 rows matched. Fabric runs in its own workspace, not in this app. *Watch in the Clip view opens a match's moments; the tour waits.* |
| 10 | `/?match=syn_0294&player=t_home_09` | `[data-tour="stage-actions"]` | **Fans, creators, broadcasters.** Fans and creators take moments away: Download reel joins them into one video, Export moments lists them with timecodes. Broadcasters get the recap and its reel as a replay package. *Try Download reel.* |
| 11 | `/scout#find` | `#scExamples` | **Scouts: fair comparisons.** Scouts ask in plain words. Players are compared only with players of their own level, age group and gender, and every percentile names its pool. *Press "Who are the best U19 dribblers up front?", then open Hector Santos.* |
| 12 | `/players/pl_pnr_11` | `[data-tour="stat-take_ons_won"]` | **Every number opens its moments.** Hector Santos is an invented U19 forward in Spain. Each number on his profile opens the moments it was counted from. *Press Take-ons won, then pick a moment to play it.* |
| 13 | `/scout#terminal` | `#txForm` | **The Scout terminal.** 127 metrics, each with its definition and source, in linked panels, with a search box that reads plain questions. *Press Search: Femi Toure comes first.* (fills `most goals in England`) |
| 14 | `/me?player=pl_bro_09#matches` | `#addBtn` | **Players build their profile.** A player uploads their own match here, answers "Is this you?" where Regista is unsure, and the match joins their profile. Uploading starts cloud work, so on this demo it needs the operator's key. |
| 15 | `/demo` | `#closeLinks` | **That's Regista.** Every touch, every replay, every player, found. Next: real footage from players and teams. The code, the tests and how each judging criterion is met are in the repository. |

What the steps were checked against (local app, this branch; the live app read-only where it matters):
- Step 1: Goal reel plays `rl_r01_eas_bro` 05:48 and 55:27, then rounds 6, 8 and 10 ("Goal reel · clip 2 of 5" seen).
- Steps 3 and 4: "his nutmegs" gives 3 moments; "now the replays" gives 1, "nutmeg · half-speed replay from high and wide".
- Step 6: the live app's `/me?player=pl_bro_09#matches` shows the processed upload `up_8807d7835c` with 9 agent rows
  (shots 17 s, identity 2 min 06 s). Locally there is no upload, so that step shows its card with nothing highlighted.
- Step 11: the chip, on Data Search, answers "Hector Santos ... 5.31 per 90, 97th percentile among 16 academy U19 men
  forwards"; following his link moved the tour to step 12 by itself.
- Step 13: "most goals in England" puts Femi Toure first in semi-pro men.
- Step 7 was not pressed: it would spend a Foundry call, and locally there is no Foundry. Its wording does not promise
  that both MCP servers appear on every answer; it says which server ran each tool.

## Warm for judging: what is rendered

`warm.plan` on this branch's data plans 25 URLs (after the featured player's clips):

1. Femi Toure's Goal reel: `/api/matches/rl_r01_eas_bro/clips/cl_t_away_09_000006.mp4`, `.../cl_t_away_09_000023.mp4`,
   `/api/matches/rl_r06_bro_eas/clips/cl_t_home_09_000011.mp4`, `/api/matches/rl_r08_bro_fai/clips/cl_t_home_09_000005.mp4`,
   `/api/matches/rl_r10_bro_ash/clips/cl_t_home_09_000011.mp4`.
2. The demo match's recap reel (Instant, Sami Castellanos's side): six `syn_0294` clips (already warm as the featured
   player's), then `/api/matches/syn_0294/reel.mp4?clips=cl_t_home_09_000002,...,cl_t_home_09_000010` (Download recap reel).
3. The demo match's Download reel: `/api/matches/syn_0294/reel.mp4?clips=` his 11 moments, best first, exactly the
   `href` the page sets (compared in the browser).
4. Hector Santos's take-ons won: the 4 of his 5 take-ons that have a clip of their own (`cm_eu19_02_pnr_sot` x2,
   `cm_eu19_03_pnr_pij` x2).
5. Liga Juvenil Levante Interior's newest uploaded match `cm_eu19_03_vdc_nvc`, opened from "Watch in the Clip view": its
   default player (`t_home_02`, most moments) and the first 8 cards of the grid, best first. Compared in the browser:
   the page's first 8 card videos are the same 8 URLs, in the same order.

Timing: a cold start on an empty cache rendered all 50 URLs (26 featured, 24 the tour's; the recap's clips repeat the
featured ones) in 74 s on Zaid's 10-core Mac, with 0 failures. The live replica has 1 CPU, so expect several minutes;
not measured there. A visitor during that time still gets any clip on demand, as today.

## Foundry limits: cost

`gpt-5-mini` list price is about $0.25 per million input tokens and $2 per million output tokens (check the Azure price
sheet for Global Standard). A Foundry answer with a tool call or two is roughly 10,000 input and 1,500 output tokens
across its model calls, about half a cent. These are estimates, not measured on this deployment.
- The everyone-caps bound the worst case. Before: 300 a day, about $1.65 a day. Now: 600 a day, about $3.30 a day.
- Over the 15 days of judging that is at most about $50, against about $25 before. It is reached only if someone hits
  the global cap every day.
- Real use by a handful of judges is a few dollars at most.
- The Studio's Overview shows Ask and Chat usage against the limits. If the credit runs low, set a lower
  `REGISTA_ASK_TOTAL_PER_DAY` with `infra/deploy-app.sh`, with no code change.

## The daily live check

`python src/regista/live_check.py [--url URL] [--services a,b] [--until YYYY-MM-DD]`. Checks:
- `/api/health`: 200, `ok`, and each service running (Foundry, Cosmos DB, AI Search, Azure MCP, tracing, Container
  Apps, Storage).
- `/`, `/demo`, `/scout`, `/me` and `/players/pl_bro_09` answer 200 with HTML.
- `/api/catalogue` totals: 14 competitions, 10 countries, 90 matches.
- One demo-match clip answers 200 with `video/mp4`. Only its first 4 KB is read.

Results:
- Against this branch's local server (`--services ""`): **9 of 9 passed**.
- Against the live app (GETs only): **8 of 9**. `/demo` is 404 until this branch is deployed. The live health check
  reported all seven services running.

Scheduled workflows run from the default branch only, so the daily check starts once this is merged into `main`.

## Checks

- `python3 -m pytest -q`: **1189 passed** (16 deselected). `python3 -m pytest -q -m slow`: **16 passed**.
- `node --check` on `tour.js` (in `tests/test_tour.py`).
- The tour, end to end, in the built-in browser against a local server (`REGISTA_DOTENV=`, port 8247).
  - At 1440 px, every step: the right page, the target highlighted, boxes filled, auto-advance from Find players to
    Hector Santos, and Finish clears the store.
  - At 375 px, every step: the target's box never overlaps the card. Each step's rectangle was measured; step 6 was
    measured against the live upload's agent list, 588 px tall, with 597 px free above the card.
  - At 375 px: Hide and reopen, "Tour paused" on an unrelated page, and Exit.
  - No console errors. No horizontal scroll at 375 px.
- Cold prerender with the tour on an empty cache: 50 of 50, no failures; warmed clips then answer in about 30 ms.
- Servers stopped and browser tabs closed afterwards.

## Open

- **README's judges' tour, the storyboard and the pitch are not edited** (Zaid is working on them). The README's
  two-minute tour still describes the old Home ("Make a reel of Sami Castellanos's best moments", "midfielders who win
  the ball back"). It could point at `/demo` and "Take the tour". The storyboard's rehearsal note still says Foundry
  allows 3 a minute and 20 an hour per visitor (now 5 and 40). Beat 1's Goal reel exists again, as a button on the profile.
- **Deploy and check live.** After merge and CI deploy:
  - run `python src/regista/live_check.py` (expect 9 of 9);
  - take the tour once on the live app at 1440 and 375 px (step 6 is the one only the live app can show);
  - watch the Studio's prerender count reach its total (about 50).
- The left panel's new link is labelled **Demo**; "For judges" or "Start here" are alternatives if Zaid prefers.
- Step 7 cannot be checked without spending a Foundry call on the live app. Rehearse it once before judging, as the
  storyboard already says.
