# Live demo: independent check

Checked 2026-10-27 on `feature/live-demo` at ee1201c (the build), then fixed in the commit that adds this file. Local
server only (`REGISTA_DOTENV= REGISTA_PRERENDER=1 uvicorn regista.api:app --port 8253`, an empty clip cache, a scratch
feedback folder); the live app was only read (GET: `/api/player/uploads?global_id=pl_bro_09` and the `/me` page).
Nothing was written to the live app or Azure. The server is stopped and the browser tab closed.

## Verdict

The tour works as a judge would take it, from Home and from /demo, at 1440 and 375 px. All 15 steps open the right
page and highlight their element. The card never covers the element when the step opens. Back, Next, Hide/reopen,
Paused / Back to the tour, Finish and Exit all work, and the tour picks up again after a reload. Nothing writes. There were no console
errors, and the pages break no CSP rule. Every clip the tour plays was already in the warm cache. The live check passes
locally and fails when the server is down or a page is missing. Both test suites pass.

I fixed one problem on phones (below). The remaining items are listed at the end.

## What was checked

**The tour, 1440 x 900, started from /demo.** For each step I measured the target's box against the card's box, checked
that the target was lit (`tour-on`) and fully on screen, that the search box was filled, and that the page had no
sideways scroll. Results for all 15 steps: found, lit, on screen, no overlap.

I also did what the cards ask a judge to do:
- Goal reel: plays Femi Toure's 5 goals in match order (r01 x2, r06, r08, r10).
- A timeline mark plays its clip. The page adds `clip=` to the URL, and the tour still counts it as the same page.
- Data Search: "his nutmegs" gives 3 moments, and "now the replays" gives 1, the half-speed nutmeg replay.
- Match recap: 6 sentences. Play recap reel plays 6 clips.
- Competitions, then Liga Juvenil: "Watch in the Clip view" pauses the tour ("The tour waits at ..."), and "Back to the
  tour" returns to step 9.
- U19 dribblers chip: Hector Santos comes first (5.31 per 90, 97th percentile among 16). Following his link moves the
  tour to step 12 by itself.
- Take-ons won lists 5 moments, and the first one plays.
- Terminal, "most goals in England": Femi Toure is first (1.64 per 90).
- Back from step 15 goes to step 14 on /me. Finish and Exit clear `regista.demo.v1.tour` and the highlight.
- A reload on step 14 shows step 14 again.

**The tour, 375 x 812 (mobile preset), started from Home.** I did the same measurements and actions. All 15 steps:
found, lit, no overlap when the step opens, no sideways scroll. Step 6 has no upload locally. On the live app, its agent
list (`ol.pf-steps`, 9 rows) is 588 px tall at 375 px. The tour puts it at 12-600 px, and the card's top is at 609 px,
so it fits with 2 px to spare on an 812 px screen (see Remaining).

**Writes.** In the server log, the only requests other than GET were the ones a judge presses:
`POST /api/matches/syn_0294/chat` (Data Search, read-only) and `POST /api/scout/ask` (the chip, Data Search). The tour
fills the boxes but never sends them. No Foundry call was made: there is no Foundry locally, and the tour never presses
Ask.

**CSP.** `/demo` sends the same policy as every other page (`script-src 'self'`, no inline scripts). `demo/index.html`,
`demo/demo.js`, `shared/tour.js` and the HTML the build changed have no inline scripts, `on*=` handlers or `style=`
attributes. demo.js and tour.js pass every value through `esc()`. The console showed no errors on any page.

**Warm cache (the prerender list against the pages' requests).** I started the server on an empty cache with
`REGISTA_PRERENDER=1`. The warm-up finished in 86 s with 51 of 51 rendered and 0 failed, leaving 45 files (some URLs repeat the featured
player's clips). Then I took the tour and did everything above. Results:
- These were all cache hits: Femi's 5 goal clips; the demo match's timeline clip and the 6 recap reel clips; the
  competition match's grid (`cm_eu19_03_vdc_nvc`, player `t_home_02`, the first 8 cards best first, exactly the warmed
  8); and Hector Santos's 4 take-on clips.
- The Download recap reel URL the page builds answered from cache in 0.016 s. The Download reel URL at step 10 (11
  clips, best first) answered in 0.009 s.
- No clip file was created after the warm-up finished (the newest file was created at 00:16:14; the warm-up ended at
  00:16:15).

So the warm-up uses the same cache keys as the pages.

**Live check (`src/regista/live_check.py`).**
- Against the local server with `--services ""`: 9 of 9 pass, exit 0.
- Against a closed port: 0 of 8 pass, each check FAILs with "no answer: Connection refused", exit 1.
- With a page `/no-such-page`: that check FAILs (HTTP 404) and the rest pass.
- With the default services against the local server (no Azure): "health services" FAILs and the run exits 1.
- `src/regista` has no file named like a standard-library module, so running the probe as a script cannot shadow one.

**Suites.**
- Before the fix: `python3 -m pytest -q` gave 1189 passed; `python3 -m pytest -q -m slow` gave 16 passed.
- After the fix: 1189 passed (the tour test gained assertions rather than new tests).

## Fixed (in this commit)

**On phones, what a step points at was hidden under the card.** The card fills the bottom quarter of a phone. The tour
put the element in the middle of the screen, so what the step leads to fell under the card:
- the Goal reel's video (step 1);
- the uploads below "Uploaded matches", with their uploader and camera, which step 9 talks about;
- the Scout agent's answer and Hector Santos's link (step 11);
- the Play recap reel button (step 5).

Two changes fix this:
- `tour.js` `reveal(el, step)`: on screens up to 720 px wide (the width where the card becomes a strip), the element
  goes just under the header, so what follows it shows between it and the card. The three Ask-box steps (`"above":
  true`: ask, follow-up, foundry) stay in the middle, because the conversation's answer appears above the Ask box.
- `tour.css`: on phones, while the tour runs, `html` gets `scroll-padding-bottom: 270px`, so the pages' own scrolls stop
  above the card. These are the moments list a number opens (`scrollIntoView` 'nearest') and the Goal reel's stage.
  Before, a number's 5 moments landed at 808-985 px, under the card (top at 609 px). After, they sit at 326-503 px.

Measured again at 375 px after the fix:
- step 1: the Goal reel button is at 12 px and the video at 109-281 px;
- step 9: the first two "Watch in the Clip view" buttons are on screen;
- step 11: the answer is on screen and Hector Santos's card starts at 469 px;
- step 5, recap opened: every sentence is on screen;
- the Ask steps are unchanged.

Desktop (1440 px) behaves as before; I rechecked steps 3 and 5 there. `tests/test_tour.py` now allows the step key
`above` and checks the phone placement and the scroll padding.

## Remaining (not fixed)

1. **Step 6 on short phones.** The live upload's agent list is 588 px tall. It fits above the card on an 812 px screen
   with 2 px to spare, but not on a 667 px phone (iPhone SE) or in a browser whose bars take more of the screen: the card
   covers the list's last rows. The judge can press Hide. A real fix would point at a shorter element, such as the
   list's first rows or the upload's header.
2. **Step 9 at 1440 px.** The card (bottom right) covers the "Watch in the Clip view" buttons of the 2nd to 4th
   uploads. The first upload's button, the newest, which is the one the warm-up prepared, is visible.
3. **After pressing Ask on a phone (steps 3, 4, 7)**, the conversation grows and pushes the Ask box down under the card.
   The answer itself stays visible above the box. It is the Ask box that ends up under the card, after the judge's own
   action.
4. **Not checkable locally:**
   - step 6's processed upload (it is only on the live app);
   - step 7's Foundry answer and "How Regista answered" (no Foundry locally; pressing Ask on the live app spends a
     Foundry call);
   - the warm-up's length on the live 1-CPU replica.

   After the deploy, take the tour once on the live app at 1440 and 375 px and press Ask Microsoft Foundry once.
5. **/demo's "nothing you click changes anything"** holds for the server: every write needs the operator's key. Some
   choices are remembered in the visitor's own browser, though: shortlist stages, notes and messages, which are §2.9's
   per-visitor demo data. Zaid may want "nothing you click changes Regista" instead.
6. **The repository links on /demo and step 15** point at https://github.com/Qadzilla/Regista. A judge can open them
   only once the repo is public, which is already on the submission list.
7. Carried over from build.md: the README tour, the storyboard (its rehearsal note still gives the old Foundry limits)
   and the pitch are not updated. The daily live check starts only once the branch is on `main`.
