# Reviewer A, pass 3

Branch `ux/app-redesign` at 224727a (`git diff main...HEAD`: 10 commits). Checked against the brief,
docs/redesign/inventory.md, adaptation.md and safeguard.md, and against the five pass-2 findings (review-a-pass2.md S1-S3,
review-b-pass2.md S1-S2). No code was changed by this review.

Paths: `index.html`, `app.js`, `product.css` are in `src/regista/static/product/`. Line numbers are at 224727a.

## Verdict

**Signed off.** No blocker and no should_fix left. All five pass-2 findings are fixed and checked in the browser. Four
nits remain (N1 to N4). None of them blocks sign-off.

## What was run

- Full suite: `OMP_NUM_THREADS=4 python3 -m pytest -q` gave **605 passed**, 10 warnings, 199 s.
- Scope: `git diff main...HEAD --name-only` lists only `src/regista/static/` (me, player, product, scout, shared),
  `tests/test_product_page.py`, `tests/test_player_api.py` and `docs/redesign/`. The pass-2 commit 224727a touches only
  `app.js`, `index.html`, `product.css` and `docs/redesign/home.md`. Its diff adds no inline script, handler or style
  attribute. `#resultsStatus` and `#fullMatchNote` are set with `textContent`.
- Browser: local server `REGISTA_DOTENV= python3 -m uvicorn regista.api:app --port 8074`, stopped afterwards. Widths
  checked: 1440 x 900, 1280, 1101, 768 x 1024 and 375 x 812 (mobile preset). The only console error came from this
  reviewer's own iframe probe (frame-ancestors 'none', as designed). The pages logged none.

| page / state | 1440 | 375 | notes |
|---|---|---|---|
| Home landing | ok | ok | The tagline is verbatim. The prompts type in and out (placeholder caught at "Find me shots from outside the box this\|"). Tab filled "Find me shots from outside the box this season" and focus stayed in the box. Enter searched. "Data Search · Ask Microsoft Foundry" sits under the box. No pitch copy and no example buttons. |
| Results, Data Search | ok | ok | Nutmeg query: 38 moments in 15 matches. Shots query: 362 moments in 33 matches. The compact bar spans the top at 79 px and the grid starts at 263 px. The panel is hidden. Focus returns to `#rq`. `#resultsStatus` (role=status) holds the reply. scrollWidth equals the viewport width. |
| Results, Ask Microsoft Foundry ("now the replays") | ok | ok | At 1440 the bar spans the top (79 px) and the panel is on the right under it (144 px, x 1064, 360 wide). At 375 the order is bar 213 px, panel 327 px, grid 1045 px. The fallback is honest: "Foundry is not set up on this server, so Regista's rules wrote this reply." In the steps: "Answered by Regista's own rules, with no AI model (Foundry was asked for)." The technical line reads "answered by rules (Foundry is not configured on this deployment)". |
| Match view from a card (rl_r08_eas_cal, Elias Popescu) | ok | ok | `#matchSub` is gone and the timeline is shown. The four actions share one row: top 602 at 1440, 591 at 1280, 612 at 1101 (labels on two lines inside their buttons, row 447 of 447 px, no overflow) and 1191 at 768. The note "Watch the full match: the first view takes a few minutes." is under the row. "Match recap" is folded with its own switch. The playing card has `outline: none`, border rgb(38,44,58) and no shadow. At 375 the actions take two rows (adaptation I-098, a yes/no for Zaid). |
| Deep link `/?match=rl_r08_bro_fai&player=t_home_10&clip=cl_t_home_10_000018` | ok | ok | Opens the match view on clip 000018 (video src `.../clips/cl_t_home_10_000018.mp4`, "Preparing…" while it renders). The Scout link reads "See Kenan Nakamura's Scout profile" and points to /players/pl_bro_10. Download reel, Export moments (`moments.csv?player=t_home_10`) and Watch the full match are present. At 375 the empty panel comes first (213 px) and the stage starts at 745 px, which is safeguard D12. |
| /scout | ok | ok | Scout is current with background rgb(255,205,40). At 375 the nav is a row of tabs. Content is unchanged. scrollWidth 1440 / 375. |
| /players/pl_bro_10 | ok | ok | Scout is current. The profile's clip links are still `/?match=rl_r08_bro_fai&player=t_home_10&clip=…`. scrollWidth 1440 / 375. |
| /me | ok | ok | "Player profile" is current (`aria-current="page"`). The left panel is 220 px wide at 1440 and becomes a row of tabs at 375. |
| /studio | ok | ok | Unchanged: its own header ("Product →"), not in the diff, scrollWidth 375. |

## Pass-2 findings, verified

1. **A-S1 / B-S1 (results bar under the panel on narrow screens): fixed.** The bar and `#searchNote` now sit in
   `#resultsTop` (index.html:43-58), the first child of `.work`, spanning both columns (product.css:40,
   `.rtop { grid-column: 1 / -1 }`). At 1100 px and below, `.rtop { order: -2 }` (product.css:199) keeps them above the
   panel. Measured at 375 px with Foundry: bar 213, panel 327, grid 1045. `#resultsTop` is hidden outside the results
   (app.js:138), and the global `[hidden] { display: none !important }` wins over `display: flex`.
2. **A-S2 (stage actions wrap below 1440): fixed.** The button reads "Watch the full match" (app.js:324). The
   long-match wording moved to `#fullMatchNote` under the row (index.html:96), linked with `aria-describedby`, and
   hidden when the link is hidden (Cosmos DB). Above 760 px the row is `flex-wrap: nowrap` and a label wraps inside its
   button (product.css:105-108). The row was one row at 1440, 1280, 1101 and 768 and never overflowed. I-101's wording
   is kept: the note carries the same sentence.
3. **A-S3 (step count overstated): fixed.** `aggregate()` (app.js:708-717) counts distinct match ids and runs
   separately, and `stepCount()` (app.js:895-899) prints them. Seen: "librarian.search_clips 42 ms · 53 runs in 34
   matches" next to "34 matches searched in 573 ms". The follow-up showed "librarian.search_clips 27 ms · 34 matches".
4. **A-pass-2 brief item 4 (same as 1): fixed.** See 1.
5. **B-S2 (Data Search results not announced): fixed.** `#resultsStatus` (index.html:123, `role="status"`,
   `aria-live="polite"`, visually hidden) is filled by `announce()` (app.js:693-698) with the reply, the error, or "no
   matches". It is filled only while the panel, the other live region, is hidden, and it is cleared first so a repeated
   reply is read again. Seen with Data Search: "362 moments in 33 matches · any player · shot. Best: …". With Foundry it
   stayed empty, so the reply was not announced twice.

## Issues (nits only)

- **N1 (accessibility, carried from pass 2).** Opening a result re-renders the grid and focus falls to `<body>` (seen
  after a click: `document.activeElement` was BODY). The next Tab still reaches the stage. Moving focus to the match
  title or the stage would tell a keyboard user where they are.
- **N2 (docs, deliverable accuracy).** adaptation.md was not updated after pass 2. Two rows now misdescribe the page.
  I-145 (adaptation.md:181) still says the panel comes before the compact bar at 375 px. I-101 (adaptation.md:137) still
  quotes the button text "(the first view takes a few minutes)". home.md "Pass 2 fixes" is correct. Update those two
  rows before the map goes to Zaid. safeguard.md still lacks items for I-028 (tab titles "Regista" / "Regista Player"
  against the nav labels) and I-098 (stage actions take two rows on phones). adaptation.md marks both as needing a
  decision.
- **N3 (wording).** In "Details: step names and times" the time per step is the sum across the matches that ran
  parallel. `librarian.load_match 2.1 s · 34 matches` sits next to "34 matches searched in 573 ms" wall time. Both are
  true, but a reader can take 2.1 s as elapsed time. A word such as "2.1 s in all" would remove the doubt.
- **N4 (layout).** In the 360 px panel, and at 375 px, step names break mid-word: "conversation.ste / p" and
  "librarian.search_cl / ips". The rule is unchanged from main (`overflow-wrap: anywhere`, product.css:94). The longer
  count "53 runs in 34 matches" leaves less room for the name. Breaking at the dot, or putting the count on its own line,
  would read better.

## Inventory and decisions

Every decision in the brief is applied: the landing, the results bar with its switch, the panel only with Foundry,
search across every match merged best first, and the match view without the explainer, with the conversation in the
panel only, "How Regista answered" one line per answer, the folded recap with its own switch, the actions in one row and
no yellow outline. The navigator is applied on /, /me, /scout and /players/{id}. The inventory items I re-checked after
pass 2 are present: the timeline, sort and tag chips, the pickers, the Scout link, deep links, Play reel, Download reel,
Export moments, Watch the full match with its note, the footer, How it works, the Studio link, the live regions,
keyboard Tab fill and Enter, and the phone layouts. Pass 2 removed or hid nothing. The only wording move (I-101) keeps
its sentence.

## Disagreements with decisions

None that I would change. As in pass 2, for Zaid's awareness: with Data Search on the results there is no panel, so the
reply text and "How Regista answered" for that search can only be heard (now through `#resultsStatus`). They are not
visible until the switch moves to Foundry or a card is opened. This follows the decision and is listed so that it is a
conscious choice.
