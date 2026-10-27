# Live demo: independent review A, round 2 (a judge's first visit)

Branch `feature/live-demo` at a000c99 (`git diff main...HEAD`). I looked at it as a judge who has never seen Regista:
- Is the tour clear, short, plainly worded and impressive?
- Does /demo make the product and the Microsoft stack obvious in 30 seconds?
- Does it work on a phone?
- Does it claim anything that does not run?

I did not fix anything. Nothing was written to the live app or to Azure. On the live app I sent one GET:
`/api/player/uploads?global_id=pl_bro_09`.

**Verdict: signed off, with five should-fix items.** All 15 round-1 findings are fixed. The tour is now honest: no
"found in the footage", only the upload step names vision agents, and Fabric is marked "Not in this app". The tour is
12 steps over 8 page loads and follows the storyboard's order. /demo puts the Microsoft tiles straight after the hero.
None of the items below blocks a deploy. Items 1 and 2 are small code fixes. Item 3 needs one Foundry press on the
live app after the deploy.

## How I checked

- **Local server.** My own server (`REGISTA_DOTENV= uvicorn regista.api:app`, 127.0.0.1:8263) and the built-in browser.
- **Desktop, 1440x900.** I took the whole tour from /demo's Take the tour and did each suggested action:
  - Goal reel.
  - "his nutmegs" gave 3 moments, then "now the replays" gave 1.
  - Opened the recap: 6 sentences, and Play recap reel (6).
  - The U19 dribblers chip put Hector Santos first; following his link moved the tour to step 10 by itself.
  - Take-ons won listed 5 moments, and one played.
  - The terminal's "most goals in England" put Femi Toure first.
  - Finish and Exit cleared `regista.demo.v1.tour`.
- **Phone, 375x812.** I took the whole tour again from Home's Take the tour.
  - The card sits along the bottom. No step's element was under the card when the step opened.
  - No sideways scroll (scrollWidth 375 on /demo, Home and every step).
- **Locally, step 5 has nothing to highlight.** Femi has no upload on a local server. On the live app he has one,
  `up_8807d7835c`, status done.
- **Writes and errors.** The server log shows only GETs, plus the POSTs I pressed myself: 4 `/chat` with Data Search,
  2 `/api/scout/ask`. No console errors.
- **Tests and checks:**
  - `tests/test_tour.py`, `test_warm.py`, `test_live_check.py` and `test_access.py`: 72 passed.
  - `node --check tour.js` passes.
  - The new files have no inline style, handler or script.
  - `git merge-tree` of this branch with `feature/judge-docs` (the pitch) is clean.
- **Clean-up.** Tabs closed, viewport reset, server stopped.

## Should fix

1. **A second tab on the next step's page moves the tour on, so a judge can lose the hook.**
   - **Reproduced.** I opened `/?match=syn_0294&player=t_home_09` in a second tab. That is exactly /demo's "Open
     Clips" link, and the URL of steps 2, 3, 4 and 6. Then I pressed Take the tour in the first tab.
   - **Result.** The first tab opened `/players/pl_bro_09` with "Tour paused · Step 2 of 12" instead of step 1.
     The store read `{"i":1}`. "Back to the tour" then goes to step 2, so the Goal reel hook is never shown.
   - **Cause.** `R.store.watch` re-renders the background tab. `render()` then advances the tour whenever that tab's
     page is the next step's page (the "followed the suggested link" rule).
   - **Fix (one line in `tour.js` `render()`).** Advance only when `document.visibilityState === 'visible'`, or only on
     the page's own load, never from the store watch.
   - I also saw one unexplained jump back to step 2 when I opened the recap at 1440 px. There was no second tab of mine
     open then. I could not reproduce it in three tries. It may be a stale tab of this origin in the shared browser
     profile.

2. **On a phone, step 10's "pick a moment to play it" plays the clip off screen.**
   - **Measured at 375x812, tour running.** I pressed Take-ons won, then picked "take-on at 48'". The page settled at
     scrollY 2169 with the video at y = -795 to -623, playing where the judge cannot see it. What shows is the moment
     list under the video.
   - **The tour is not the cause.** With the tour exited, the same pick scrolled the video off screen as well.
   - **Cause.** `profile-view.js` scrolls `.pf-best` into view with `block: 'nearest'`. On a phone that section (video
     plus a long moment list) is taller than the screen, so the browser lines up its bottom, not the video.
   - **Desktop is fine.** At 1440 the video ends up at y 237-601.
   - **Fix.** Scroll the video (`.pf-screen`) into view with `block: 'start'` on narrow screens. That covers lines 316,
     341 and 813 of `profile-view.js`.
   - The tour asks for this click, so a judge on a phone presses it and sees nothing play.

3. **Step 6 (Foundry and MCP) promises a trace the match chat may not produce. Check it on the live app.**
   - **What the card says.** "How Regista answered shows ... which server ran each tool: Regista's MCP server or the
     Azure MCP Server". The storyboard (beat 5) expects both servers.
   - **What the code says.** Step 6 asks in the match view's chat, whose `CHAT_INSTRUCTIONS` make tools optional: "You
     may call your tools for detail the note lacks (search_library for other matches)". So one press may show only
     Regista's MCP server, or no tool at all.
   - **Where the Azure MCP call was verified.** `search_index_query` through the Azure MCP Server was checked through
     `/ask`, which is Home's search box with Ask Microsoft Foundry (CLAUDE.md §4.1).
   - **The panel also disagrees with the question.** The moments panel shows this match's 3 nutmegs while the question
     says "every nutmeg in the library".
   - **What to do.**
     - After the deploy, press Ask Microsoft Foundry on step 6 once, and read which servers appear.
     - If the Azure MCP Server does not appear, point step 6 at Home's search box with Ask Microsoft Foundry and the
       same question.
     - Or keep the step and stop expecting both servers in the storyboard.

4. **Steps 7 and 8 are the weakest stretch, and step 7 overstates Fabric a little.**
   - **They repeat the page.**
     - Step 7's card repeats the line it highlights: "14 competitions in 10 countries", word for word.
     - Step 8's camera sentence repeats the note printed right under the highlighted "Uploaded matches" heading.
   - **They cover little ground.** Two page loads for metadata, between the Foundry step and the scouting steps.
   - **Merge them into one step:** the catalogue, who filmed it, and the Fabric line. That makes 11 steps over 7 loads.
     The test that keeps /demo's "12 short steps" equal to the tour's length will catch the number.
   - **"Recomputed every catalogue number" says too much.** The 7,399 rows are 1,057 player-competition rows times 7
     stats (storyboard, beat 6). Say "recomputed the catalogue's 7,399 player numbers from the raw tables; all 7,399
     matched". The same wording is on /demo ("every catalogue number").

5. **Step 4's card is too long for a phone.**
   - **Size.** About 50 words, the longest card. At 375 px it is 253 px tall, almost a third of the screen.
   - **Effect.** After a recap sentence plays (the page scrolls up to the video), Play recap reel is far below, under
     the card.
   - **Suggested text:** "Every match gets a recap told from the picked player's side; each sentence plays its
     moment, and the recap has its own reel. Download reel and Export moments take them away."

## Nits

- **Step 1 says "in match order" twice**, once in the text and once in the action line.
- **Step 5 says "He answered 'Is this you?'".** The two answers were given with the operator's token after checking the
  film's ground truth (CLAUDE.md §4.1). "'Is this you?' was answered where they were unsure" is exact.
- **The close says less than the tour.** "Every touch, every replay, every player, found." Naming what the judge just
  saw (clips, recaps, uploads, Foundry, the catalogue, the scout tools) before "Next: real footage" would land better.
- **The paths are below the fold at 1440x900.** With the live app's eight tiles, the four paths start at about y 925.
  This is the trade-off for putting the stack first, which round 1 asked for. A compact path row is optional.
- **The card covers the right column on desktop.** At 1440 it sits over the Clip view's right column (the Ask box once
  the conversation grows) and over the terminal's player card. Hide is there, so I would leave it.
- **Order of merging.** The pitch on `feature/judge-docs` says "start at `/demo`", and /demo exists only once this
  branch is deployed. Deploy this branch before submitting the pitch. The two branches merge cleanly.

## Still to check on the live app after the deploy (carried from round 1)

- **Step 5's agent list.** It exists only once this branch is deployed (`data-tour="agent-steps"`).
  - On an 812 px phone it fits above the card (588 px).
  - On shorter phones the card covers its last rows.
- **Step 6.** One Foundry press, as in item 3.
- **The warm-up on the 1-CPU replica.** The Studio should show `usable_cpus` 1. Note the prerender's start and finish
  times, and how pages respond while it runs.
- **The Azure for Students credit,** before raising `REGISTA_ASK_TOTAL_PER_DAY` above 300.
- **The repository and criteria links** on /demo and in the last step work only once the repository is public.
