# Live demo: fixes after review round 1

Branch `feature/live-demo`, on top of 3509409. This round fixes the 15 findings from `review-a-pass1.md` (the judge's
view) and `review-b-pass1.md` (engineering). Nothing was deployed. Nothing wrote to the live app or to Azure.

## What changed, finding by finding

| # | Finding | Fix |
|---|---|---|
| 1 | Step 1 said "Regista found every one in the footage" and named the "Regista League" without saying it is invented | It now says "Femi Toure is the top scorer in Regista's synthetic league: five goals, none a penalty. Here is every one, in match order." |
| 2 | Step 2 said "Regista watched this match" about `syn_0294` | It now says "This match comes from Regista's match generator. Regista cut every moment Sami Castellanos is on the ball…". Only the upload step mentions vision agents, and a test checks this. |
| 3 | The tour was too long: 15 steps over 10 page loads | Now 12 steps over 8 loads (/players, /, /me, /, /scout, /players, /scout, /demo). "Ask" and "Follow-up" are one step. "Fans" is folded into the recap step (recap, its reel, Download reel, Export moments). "Players" is folded into the upload step. Both duplicate trips (/me twice, / after Scout) are gone. |
| 4 | Step 14 highlighted "Add a match", which asks for the operator's key | The step is gone. The merged upload step highlights the agent list. Its action line points at the moments the agents found, just below the list. A test checks that no step targets `#addBtn`. |
| 5 | Step 9's title "Checked in Microsoft Fabric" did not match its highlight ("Uploaded matches") | The Fabric sentence moved onto the catalogue step, retitled "A catalogue, checked in Fabric". It starts "Not in this app:", then gives 7,399 of 7,399 and the date. The competition step is now "Who filmed each match", with the uploader and camera, and says the camera is only a label. |
| 6 | Step 6's act line "Measured on Regista's own rendered footage." was not an action | Dropped. The card makes no measurement claim, so nothing needs qualifying. The act line is now something to do. |
| 7 | /demo at 1440x900: the Microsoft tiles were below the fold | "Running on this server right now" now comes straight after the hero, above the four paths. I put in all eight live tiles (the eight the live health check reports): they start at y=561 and end at y=889, so all of them fit in the 900 px viewport. |
| 8 | /demo's hero overstated Foundry; "Indexes every labelled clip" | The hero now says "Agents on Microsoft Agent Framework label and explain each moment and write match recaps; Microsoft Foundry answers questions and can write the recap." The third sentence says "synthetic catalogue". The AI Search tile on /demo and on Home now reads "Indexes the library's labelled clips…". |
| 9 | The engine switch is kept only in memory: Back from the Foundry step could leave Foundry picked | Steps marked `"rules"` (moments, ask, recap) put the switch back on Data Search when the tour arrives on them. The tour dispatches the switch's own change event, so `setEngine` updates all three copies. It also puts the recap's switch back on Instant. Nothing is fetched or sent. Step 3 also says "With Data Search picked". In the browser: I picked Ask Microsoft Foundry on step 3, pressed Next, and the switch and hint went back to Data Search. |
| 10 | README, storyboard and pitch | README's judges' tour now starts at `/demo` and **Take the tour**, and lists what the 12 steps show. The storyboard's rehearsal gives the new limits (5 a minute, 40 an hour per visitor; 120 an hour and 300 a day overall). Its warm-up note says the app now warms the clips at startup. **Pitch: not changed here.** `feature/judge-docs` (9f5b5c0) already rewrote `docs/pitch.md` and its Links section opens on `/demo`, so an edit here would only conflict with it. |
| 11 | A double-click on Next skipped a step | `onCardClick` now ignores the second click of a double-click (`e.detail > 1`) and any Next, Back or resume within 400 ms of the last move. Leaving the page disables the card's buttons. In the browser at 1440: a double-click on step 1 (which changes page) landed on step 2, and a double-click on step 2 (same page) landed on step 3. |
| 12 | `_render_waiting` was changed from two threads without a lock | Its changes are now made under `_render_waiting_guard`, a `threading.Lock`, and the comment says why. A test runs 900 `_video` calls from six threads, each on its own loop, and the count returns to 0. |
| 13 | Load on the 1-CPU replica: `os.cpu_count()` reports the host's cores | New `regista.render.video.usable_cpus()`: the smallest of the machine's count, the CPU affinity, and the container's quota (cgroup v2 `cpu.max`, or v1 `cpu.cfs_quota_us`), rounded up. A render's default workers are now `usable_cpus() - 1` (1 at least, 8 at most). On Container Apps' 1.0 CPU, every render, the warm-up's included, runs in-process instead of forking a pool onto one CPU. The Studio's cache facts now show `usable_cpus` and the warm-up's `tour` progress. **Still to measure after the deploy** (see below). |
| 14 | The cost note left out that the subscription stops at its $100 credit | See "Foundry cost against the credit" below. The daily cap for everyone is **kept at 300**, not raised to 600. |
| 15 | The tour stopped waiting for its element after 20 s | `WAIT_MS` is now 60 s. It still polls every 250 ms, and only while the visitor is on that step. |

Nits also fixed:
- The last step shows only Finish, with no separate "Exit tour".
- "Nothing you click changes Regista" replaces "changes anything" on /demo.
- The live check now runs as `python -I`, so `src/regista` cannot shadow the standard library.
- The workflow's comment says GitHub emails whoever last changed the schedule, so Zaid should merge it himself.

## Foundry cost against the credit

- **The credit left cannot be read from here.** `az consumption usage list --subscription "Azure for Students"`
  (read-only) returns every resource with cost `None`. Sponsorship offers do not expose prices through that API. The
  balance shows on the Azure for Students page in the portal (or microsoftazuresponsors.com). Zaid should read it there.
- **Worst case at the old cap of 600 a day:** about $3.30 a day, so about $50 over the 15 days of judging. This is an
  estimate: about half a cent per answer at list price, not measured, and gpt-5-mini's reasoning tokens could make it
  higher. Add the base cost of about $10-15 through judging (CLAUDE.md §4.1) and whatever has been spent since
  2026-10-21. That puts the worst case at about $60-65 plus spending to date, against $100. If the credit runs out,
  Azure disables the subscription and the live demo goes down.
- **Decision: keep `REGISTA_ASK_TOTAL_PER_DAY` at 300** (about $25 worst case over judging). The margin is unknown, so
  the cap stays where it was before judging.
  - The per-visitor limits (5 a minute, 40 an hour), 120 an hour overall and 3 at a time are raised as planned.
  - A handful of judges will not reach 300 questions a day.
  - If Zaid reads a comfortable balance, `REGISTA_ASK_TOTAL_PER_DAY=600` through `infra/deploy-app.sh` raises it with
    no code change. A test checks the defaults and the override.

## How I checked

- **Tests:** `python3 -m pytest -q` (`REGISTA_DOTENV=`): **1195 passed**, 16 deselected. `-m slow`: **16 passed**.
  The first run caught `test_warm`'s defaults test, which still expected 600 a day; it now expects 300.
- **New tests:**
  - test_tour: the 12 steps and their beats; no vision claim outside the upload step; Fabric on the catalogue step,
    marked "Not in this app"; no step targets Add a match; the ruled steps and the switch code; the double-click guard
    and `WAIT_MS` ≥ 60 s; the step count on /demo matches the tour.
  - test_render: the cgroup v2 and v1 quotas, no quota, and no cgroup files; a 1-CPU render runs in-process.
  - test_hardening: the render queue count under threads; the Foundry defaults and their override.
  - test_studio: the new cache facts.
- **Local server:** `REGISTA_DOTENV= uvicorn regista.api:app` on 127.0.0.1:8240, with an empty cache folder.
  - **Built-in browser at 1440x900:** /demo (tiles above the fold, as measured above), then all 12 steps from Take
    the tour. Every step's element was highlighted except step 5: locally there is no upload for Femi, so the agent
    list does not exist. On the live app, `GET /api/player/uploads?global_id=pl_bro_09` shows `up_8807d7835c` done,
    with 10 stages and links.
  - **Built-in browser at 375x812:** /demo and steps 3, 4 and 7. The element sat under the header and the card along
    the bottom, with no horizontal scroll (scrollWidth 375).
  - Exit cleared the store key, the card and `tour-running`. No console errors.
  - The server log has no POST, PUT, PATCH or DELETE.
  - `python3 -I src/regista/live_check.py --url http://127.0.0.1:8240 --services ""`: 9 of 9 passed.
  - Tab closed, viewport reset, server stopped.

## Still open

- **After the deploy (Zaid's go-ahead), on the live app, read-only:**
  - Read the Studio's cache facts: `usable_cpus` should be 1, and note the prerender's `started_at` and `finished_at`.
  - Time `/api/health` and a page load while the warm-up runs.
  - Take the tour once at 1440 and 375 px.
  - Press Ask Microsoft Foundry once and check that "How Regista answered" names both MCP servers.
  - Don't deploy in the hours before judges are likely to look.
- **Read the Azure for Students balance** in the portal and decide whether to raise the daily cap.
- **Nits left as they were:**
  - Step 7's highlight is still the one-line count (`#coLine`): centring the tall competition list would push its
    heading off screen.
  - "Demo" in the left panel is not renamed.
  - The tour state never expires.
  - The card has no `aria-live`.
  - The live check's brand-markup match is unchanged.
  - The tour cannot cross pages where storage is blocked.
