# Live demo: fixes after review round 2

Branch `feature/live-demo`, on top of 1d373a7. This round fixes the seven findings from `review-a-pass2.md` and
`review-b-pass2.md`. Nothing was deployed. Nothing wrote to the live app or to Azure. The live app was not read this
round.

## What changed, finding by finding

| # | Finding | Fix |
|---|---|---|
| 1 | A second tab on the next step's page moved the tour on, so the judge lost the hook | `render()` moves the tour on by itself only on the page's own first render (`render(true)`, once, at the end of the script), only in a visible tab (`document.visibilityState`), and never after Back or Forward. Another tab's change (`R.store.watch`), a hash change, popstate and a restored page all call `render()` with no advance. So a tab in the background never writes the tour's place. |
| 2 | On a phone, picking a moment on a profile played the video off screen | New `showStage(root)` in `profile-view.js` replaces the three `.pf-best` scrolls (both renderers). At 720 px and below it scrolls `.pf-screen` (the video) into view with `block: 'start'`. Wider screens keep `.pf-best` with `'nearest'`. `.pf-screen` gets the same 12 px `scroll-margin-top` as the profile's sections on phones. |
| 3 | Step 6 (Foundry and MCP) may not show the trace it promises | See "Step 6" below: the question, the card and the chat's instructions changed. **Not checked on the live app**, because that needs a deploy and a Foundry call. |
| 4 | Steps 7 and 8 repeated the page, and "every catalogue number" overstated Fabric | They are now one step, "A catalogue, checked in Fabric", on `/scout#competition/co_esp_u19`. It highlights the competition's header (new `data-tour="co-head"`), so the card no longer repeats a highlighted line. The camera sentence is gone, and the act line says "Below: who filmed each match." The card says Fabric "recomputed its 7,399 player numbers from the raw tables; 7,399 of 7,399 matched". /demo now says "recomputed the catalogue's 7,399 player numbers from the raw tables (7,399 of 7,399 matched) and the league's 756 (756 of 756)". **11 steps.** That is still 8 page loads, not the review's 7: the two steps it merged were both on `/scout`, joined by a hash change, so merging them saves no load. |
| 5 | Step 4's card was too long for a phone | It is now two short sentences, "Each match gets a recap told from his side, and each sentence plays its moment. Its reel is a broadcaster's replay package.", and the act line "Open Match recap, then click a sentence." At 375x812 the card is 195 px tall, down from 253. With the recap open, Play recap reel shows above the card. |
| 6 | Back could restore a dead card from the back/forward cache | `window.addEventListener('pageshow', (e) => { if (e.persisted) render(); })`. `render()` rebuilds the card, so its buttons work again. |
| 7 | The browser's Back from step 5 jumped the tour forward to step 6 | Only a step marked `"follows": true` can move the tour on by itself. That is step 9 (Hector Santos), the one step a link leads to (his name, from Find players). The navigation also has to be a followed link (not `back_forward`, see #1). Steps 2-4 and 6 share one URL, but none of them is marked, so Back onto that URL leaves the tour where it was. |

### Step 6 (Foundry and MCP)

- **The review's fallback would not have helped.** It suggested moving the step to Home's search box, where the
  Azure MCP Server had been verified through `/ask`. But no page calls `/ask` any more. Home's search with Ask
  Microsoft Foundry posts to the same `/api/matches/{id}/chat` as the match view (app.js line 753), with the same
  `CHAT_INSTRUCTIONS`. So the step stays on the match view.
- **The question now reaches beyond the match.** The box gets "his nutmegs here, and any in other matches?", not "every
  nutmeg in the library". The moments panel shows this match's nutmegs, which is the "here" half. The card now says
  so: "the moments on the page stay this match's".
- **The chat's instructions now ask for a search.** `CHAT_INSTRUCTIONS` (cloud/foundry.py) used to say only "You may
  call your tools…". Now, when a question reaches beyond the match (other matches, every match, the library), they
  tell the agent to search before replying:
  - `search_index_query` on the Azure AI Search index `regista-clips` (Azure MCP Server), if it holds that tool;
  - otherwise `search_library` (Regista's MCP server).
- **The card claims less.** The agent "writes the reply and can search other matches with its tools". How Regista
  answered "lists each tool it called and its server: Regista's MCP server or the Azure MCP Server". It no longer
  says both servers will appear.
- **The model still chooses its tools.** This makes the Azure MCP Server likely, not certain. The storyboard's
  rehearsal note now says this:
  - ask the tour's question;
  - if only Regista's MCP server appears after a few tries, cut beat 5's shot to that server and change the "two MCP
    servers" line.
- README's tour list says the same ("each tool it called, with the MCP server that ran it").

### The jump back to step 2 that could not be reproduced

I could not reproduce it either. At 1440 px I opened the recap on step 4 and clicked a sentence, and the URL gained
`clip=`. The store stayed at `{"i":3}`.

My best guess is the same cause as #1. Only a write can move the tour back to step 2, and before this fix a background
tab's `render()` could write the tour's place. Now nothing writes it except the visitor's own presses and a "follows"
arrival in the visible tab.

## How I checked

- **Tests.** `python3 -m pytest -q` (`REGISTA_DOTENV=`): **1197 passed**, 16 deselected. `-m slow`: **16 passed**.
- **New and changed tests** (tests/test_tour.py):
  - 11 steps, in the storyboard's beats.
  - The catalogue step's URL, its `co-head` target and the "7,399 player numbers" wording, with no "every catalogue
    number" on the step or on /demo.
  - Step 6's question reaches beyond the match, the card says the moments stay this match's, and `CHAT_INSTRUCTIONS`
    names `search_index_query`.
  - Only `number` is marked `follows`, and the step before it names Hector Santos.
  - The advance needs `arrived`, `next.follows` and `followedHere()`, which checks visibility and `back_forward`.
  - `render(true)` appears once. The watch and hashchange call `render()`. The `pageshow` handler is there.
  - `showStage` scrolls `.pf-screen` with `'start'` on phones, and no `.pf-best` scroll is left.
  - /demo says 11 steps (the existing test).
- **Local server:** `REGISTA_DOTENV= uvicorn regista.api:app --host 127.0.0.1 --port 8240`, with the built-in browser.
  - **#1:** a second tab was open on `/?match=syn_0294&player=t_home_09` while I pressed Take the tour on /demo. The
    tour opened `/players/pl_bro_09` on "Step 1 of 11", with the store at `{"i":0}` and the Goal reel highlighted.
  - **#7:** I went Next from step 4 to step 5 (`/me?player=pl_bro_09#matches`), then pressed the browser's Back.
    - The navigation type was `back_forward` and the store stayed `{"i":4}`.
    - The card said "Tour paused · Step 5 of 11", with its buttons enabled.
    - The Ask box stayed empty, so step 6's question was not filled.
  - **#6:** the built-in pane reloads rather than restoring a page from the back/forward cache, so I simulated one.
    With the card's buttons disabled, I dispatched `pageshow` with `persisted: true`, and the buttons came back
    enabled.
  - **Follows:** on step 8 I pressed the chip "Who are the best U19 dribblers up front?" (Data Search), then Hector
    Santos's name. His profile loaded with navigation type `navigate`, the tour moved to "Step 9 of 11", and Take-ons
    won was highlighted.
  - **#2 at 375x812:** I pressed Take-ons won and picked "take-on at 48'". scrollY went to 1361, the video sat at
    y 12-184 and played, and the card's top was at 609. Before the fix, the video ended up at y -795 to -623.
  - **At 1440x900:** steps 1-11 in turn.
    - Each target was highlighted except step 5's agent list. There is no upload for Femi locally, as in round 1.
    - On step 7, the competition header sat at y 110-289 and the card started at y 593.
  - **At 375x812:**
    - Step 4: card 195 px tall, the recap under the header.
    - Step 7: card 234 px tall, the header at y 12-359, the card's top at 550.
    - Steps 8, 10 and 11 highlighted their elements.
    - No horizontal scroll (scrollWidth 375).
  - **Exit** on step 11 cleared the store key, the card and `tour-running`. The console showed no errors.
  - **Requests.** The server log has no PUT, PATCH or DELETE. It has four POSTs, all read-only queries:
    - three to `/api/matches/syn_0294/chat` with the rules engine, my own curl checks of how Data Search reads step 6's
      question;
    - one to `/api/scout/ask`, the chip, with Data Search.
  - Afterwards I reset the viewport, closed my tabs (the two I opened, not the other sessions' tabs) and stopped the
    server.

## Still open

- **After the deploy (Zaid's go-ahead), on the live app:**
  - Press Ask Microsoft Foundry on step 6 once and read which servers How Regista answered lists. If the Azure MCP
    Server never appears, follow the storyboard's rehearsal note.
  - Take the tour once at 1440 and 375 px, including step 5's agent list, which exists only on the live app.
  - Also the items left from round 1: the Studio's cache facts (`usable_cpus` 1, prerender times) and the Azure for
    Students balance before raising the daily Foundry cap.
- **The back/forward cache restore** (#6) was simulated, not seen in a real browser. Check it once in Chrome or Safari:
  Next on step 1, then the browser's Back.
- **`docs/pitch.md` is unchanged**, as in round 1 (`feature/judge-docs` owns it). Its line "recompute every number:
  756 of 756 and 7,399 of 7,399 rows match" has the same overstatement as finding #4. Fix it there.
