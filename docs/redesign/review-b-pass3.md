# Review B, pass 3

Reviewer B, independent of reviewer A. Branch `ux/app-redesign` at 224727a (`git diff main...HEAD`, 10 commits), checked
against the brief, docs/redesign/inventory.md (I-001 to I-148), adaptation.md and safeguard.md. This review changed no
code.

**Verdict: signed off.** No blocker or should_fix item is left. The five pass-2 findings (review A's S1 to S3 and
review B's S1 and S2) are fixed and were checked in the browser. The nits and decision items listed below go to Zaid's
list.

## How it was checked

- Full suite: `OMP_NUM_THREADS=4 python3 -m pytest -q` gave **605 passed**, 10 warnings, 200 s.
- Scope: `git diff main...HEAD --stat` touches only `src/regista/static/` (me, player, product, scout, shared),
  `tests/test_product_page.py`, `tests/test_player_api.py` and `docs/redesign/`. The fix commit 224727a changes only
  product/app.js, index.html, product.css and docs/redesign/home.md. It adds no inline script or handler. New text
  reaches the page through `esc()` (`stepCount` in `howAnswered`) or `textContent` (`announce`, `#fullMatch`).
- Browser: I ran a local server with `REGISTA_DOTENV= python3 -m uvicorn regista.api:app --port 8075` (no .env, no
  Azure), stopped it afterwards, and used my own tab. Widths: 1440 x 900, 1280, 1101, 761 and 375 x 812 (mobile preset).
  The page never scrolled sideways (scrollWidth equals the viewport) at any width on any page I checked.

| page / state | 1440 | 375 | notes |
|---|---|---|---|
| Home landing | ok | ok | Logo, tagline as decided, prompts typing, "Data Search · Ask Microsoft Foundry" under the box, footer with How it works and Studio link. Tab fill confirmed through the keydown handler: "Show me take-ons in the final third". |
| Results, Data Search ("Find me all the nutmegs") | ok | ok | 38 moments in 15 matches. Bar at y 79, grid at y 144, panel hidden, focus on `#rq`. Sort and tag chips are there (All 38, Nutmeg 38, ...). The new status reads "38 moments in 15 matches · any player · nutmeg. Best: ...". |
| Results, Ask Microsoft Foundry ("now the replays") | ok | ok | 4 moments. At 1440 the panel is on the right (x 1064). At 375 the order is bar 213, panel 327, grid 924. The fallback is honest: "Foundry is not set up on this server, so Regista's rules wrote this reply."; the details say "answered by rules (Foundry is not configured on this deployment)". |
| Match view (deep link `/?match=rl_r08_bro_fai&player=t_home_10&clip=cl_t_home_10_000018`) | ok | ok | No `#matchSub`. Scout link "See Kenan Nakamura's Scout profile". Timeline. The playing card has border rgb(38,44,58), no shadow, no outline. "Match recap" is folded and opens with Instant/Foundry inside. A question asked here lands in the panel log, the way-out button works, and Back to results restores the bar, the heading and focus. |
| Bad link `/?match=nope_999`, offline search + Retry | ok | ok | The offline text shows in the grid and in the status, and Retry recovers 38 results. |
| /scout | ok | ok | Left panel with Scout current (rgb(255,205,40)). At 375 it becomes a row of tabs at y 59. Content unchanged. |
| /players/pl_bro_10 | ok | ok | Scout is current. 30 profile links of the form `/?match=&player=&clip=`. |
| /me | ok | ok | "Player profile" current. |
| /studio | ok | ok | Unchanged (its own navigation). |

## Pass-2 findings: verified

| # | finding | status | evidence |
|---|---|---|---|
| 1, 4 | Results on narrow screens put the panel above the compact bar | **fixed** | The bar and `#searchNote` moved into `#resultsTop` (index.html:43-57), which spans both columns (`.rtop`, product.css:40) with `order:-2` at <=1100 px (product.css:199). At 375 with Foundry: bar 213, panel 327, grid 924. At 1440 the bar is still at the top across both columns. `#resultsTop` is hidden in the match view and on the landing (app.js:138). |
| 2 | Stage actions wrap below 1440 | **fixed** | The button now reads "Watch the full match", and "Watch the full match: the first view takes a few minutes." is a muted note under the row (`#fullMatchNote`, linked with `aria-describedby`). At 761 px and up the row does not wrap (`flex-wrap: nowrap`), and labels wrap inside their buttons instead. All four tops were equal at 1440 (580), 1280 (541), 1101 (609, two-line labels) and 761 (842). At 375 they sit 2 + 2 (see N7). |
| 3 | Step count overstated ("53 matches") | **fixed** | `aggregate()` counts distinct match ids and keeps runs. Shown: "librarian.search_clips 42 ms · 53 runs in 34 matches", "librarian.load_match 1.2 s · 34 matches". |
| 5 | Data Search results not announced | **fixed** | `#resultsStatus` (index.html:123, `.sr`, `role="status"`, `aria-live="polite"`) is filled by `announce()` (app.js:693-698) only while the panel is hidden, so nothing is announced twice. It is set on success, on "no matches on this server" and on errors. |

## Remaining nits (not blocking; for Zaid's list)

- **N1. Prompt gap on focus (still open, from pass 2).** app.js:400-402: if the box gets focus in the ~400 ms between
  prompts, the placeholder sticks at an empty value or a partial prompt, and Tab moves on instead of filling.
- **N3. Focus order on narrow screens (still open).** At <=1100 px the panel is shown before the grid but comes after it
  in the DOM, so the keyboard reaches it after the whole grid. This goes with D12.
- **N4. Two Retry buttons for one failed search with Ask Microsoft Foundry (still open).** One is in the log and one in
  the grid. The log's Retry stays after a successful retry.
- **N5. Safeguard "needs a decision" list still lacks the pass-2 items.** I-028 (tab titles "Regista Player" and
  "Regista" against the nav labels "Player profile" and "Home"), I-148 (Home uses each match's POST /chat, not GET
  /search), I-055 (the follow-up examples now appear only in the panel hint). The safeguard covers I-098 only up to its
  pass-2 fix.
- **N7. Phones: stage actions in two rows of two at 375 px** (it was three rows before pass 2). At phone width, "one
  row" would mean shrinking four buttons below a usable tap size. I think two rows is right, but it departs from the
  wording of the decision, so it belongs on Zaid's list.
- **N8 (new). Step names break mid-word in the panel at 375 px.** "Details: step names and times" splits names such as
  "conversation.ste|p" and "librarian|.search_c|lips" inside the narrow `<code>` column. This is cosmetic and only shows
  once someone opens the details. Wrapping at the dot or letting the time drop to its own line would read better.

## Disagreements with decisions (not changed)

- **Cards "exactly as today" on cross-match results.** A card does not say which of the 34 matches it comes from, so
  the only way to find out is to open it (safeguard D7). A one-line match name on result cards seems worth departing
  from "exactly".
- **Search every match by calling each match's /chat.** That is 34 requests per question, about 23 s on a cold server
  (home.md). On the single-replica live app, a judge's first search will be slow. A server-side search across matches
  would be better, but it is outside this UI-only scope.
- **"Match recap" keeps Instant / Foundry** while every other switch says Data Search / Ask Microsoft Foundry. That puts
  two vocabularies for the same choice on one screen.
