# Review B, pass 2

Reviewer B, independent of reviewer A. Branch `ux/app-redesign` at 6aa20af (`git diff main...HEAD`), checked against the
brief, docs/redesign/inventory.md (I-001 to I-148), adaptation.md and safeguard.md. No code was changed by this review.

**Verdict: not signed off.** Two should_fix items (S1, S2). No blocker.

## How it was checked

- Full suite: `OMP_NUM_THREADS=4 python3 -m pytest -q`: **605 passed**, 10 warnings, 195 s (595 before this work; the new
  tests are in tests/test_product_page.py).
- Scope: `git diff main...HEAD --stat` touches only `src/regista/static/` (me, player, product, scout, shared),
  `tests/test_product_page.py`, `tests/test_player_api.py` and `docs/redesign/`. No Python, API, data, infra or deploy
  change. No inline script, handler or `style=` attribute in any page or in app.js innerHTML (grep). Text that reaches
  innerHTML goes through `esc()` (read searchEvery, howAnswered, searchNote, render, recap).
- Browser: local server `REGISTA_DOTENV= python3 -m uvicorn regista.api:app --port 8075` (no .env, no Azure, so Foundry
  is "not set up"), own browser tab, at 1440 x 900, 1110 x 800 and 375 x 812. Pages: Home landing; results with Data
  Search ("Find me all the nutmegs": 38 moments, 15 matches; "shots": 362, Show more 188 -> 321 cards); results with Ask
  Microsoft Foundry (panel on the right, follow-up "now the replays" -> 4); a card into the match view; a question
  and "Match recap" there; Back to results; "start over" back to the landing; deep link
  `/?match=rl_r08_bro_fai&player=t_home_10&clip=cl_t_home_10_000018&recap=1`; a bad link `/?match=nope_999`; a network
  failure (fetch rejected in the page) on a search, then Retry; `/scout`, `/players/pl_bro_10`, `/me`, `/studio`.
  Scroll width equals the viewport on every page at every width. Console: no errors from the pages.

## Decisions: applied?

| decision | result | evidence |
|---|---|---|
| Landing: large logo, tagline, search box, six prompts typing, Tab fills, still for reduced motion, switch under the box, no pitch copy, no example buttons | applied | index.html:27-40; app.js:381-413; prompts verbatim; Tab filled "Show me take-ons in the final third" and "Find me all the nutmegs"; no `.lede`, `#examples`, `ASKS` |
| Results: compact bar on top with the switch; grid and cards as today; Foundry panel on the right | applied at desktop; **not at <= 1100 px** (S1) | index.html:45-59; app.js:148-159 |
| Search covers every match, merged best first, cost noted | applied | app.js:483-494, 526-681 (each match's POST /chat, Instant engine, 6 in flight); home.md "Cost (for the PR)" |
| Match view: explainer line removed | applied | `#matchSub` gone (index.html:64-69; app.js:330-333) |
| Whole conversation in the right panel; "How Regista answered" one line, steps and timings on demand | applied | index.html:132-146; app.js:877-900; seen "How Regista answered · Data Search, no AI model · 3 steps", steps, then "Details: step names and times" |
| "Match recap" folded, with its own Instant/Foundry switch inside | applied | index.html:95-110; recap written on open; `recap=1` opened it at 71 px (header 63 + 8) |
| Stage actions in one row | applied at 1440 (all four at y 602); wraps to 2 rows at 1110 and 3 at 375 (N7) | index.html:87-92; product.css:101-102 |
| No yellow outline on the playing card | applied | playing card border rgb(38,44,58), no shadow, `aria-current="true"` |
| Left panel on every page, current in yellow, tabs on phones, REGISTA header, Home / Player profile / Scout, /players/{id} shows Scout | applied | shared/regista.css:22-49; current bg rgb(255,205,40) on /, /me, /scout, /players/pl_bro_10; row of tabs at 375; /studio unchanged |
| Player and Scout content unchanged | applied | diffs of me/player/scout are nav markup and nav CSS only |

## Inventory spot checks (beyond the adaptation map)

All present and working in the browser: pickers (I-010 to I-019) in the header on every Home view; timeline with
periods, goals, lanes, keyboard stop (I-078 to I-089; "Match timeline, 30:38: 412 clips, 8 in the current results");
sort and tag chips (I-115, I-116); Scout profile link (I-052, "See Kenan Nakamura's Scout profile" -> /players/pl_bro_10);
badges (I-126); deep links with clip and recap (I-030 to I-036; clip autoplayed, picker set, URL kept); Play reel (12),
Download reel and Export moments hrefs, Watch the full match with the long-match note (I-098 to I-101); recap by-line,
citations and "Play recap reel (4)" (I-107 to I-111); errors with Retry (I-040, I-069; offline text in the grid and in
the log, Retry recovered 38 results); loading progress "Searching every match… n of N"; empty and way-out (I-074, I-070);
footer, How it works, Studio link (I-130 to I-135); Foundry fallback line reads honestly: "Foundry is not set up on this
server, so Regista's rules wrote this reply." and the panel hint "…so Regista's rules will write the reply. The moments
found are the same."

## Findings

### Should fix

**S1. Results on narrow screens: the conversation panel sits above the compact search bar.** product.css:189-193 puts
`.convo` first (`order: -1`) in `.work`, but the bar (`.rbar`) is inside `.work-main`, so the panel comes before the bar.
At 375 px with Ask Microsoft Foundry: panel top 213 px, bar 732 px, grid 1141 px. The brief says "a compact search bar
at the top with the switch", and the sandbox keeps the bar on top and puts the panel between the bar and the grid
(sandbox.css:100: `.rbar` is outside `.rbody`; `.foundry { order: -1 }` inside `.rbody`). The match view's order is the
sandbox's (sandbox.css:135) and is D12 in the safeguard; the results' is not. Fix: on <= 1100 px keep the bar (and
`#searchNote`) above the panel, e.g. move them out of `#resultsView` to the top of `.work` spanning both columns, or let
the panel follow the bar in the narrow layout. Also gives one "Who answers" switch next to the bar first, not two
stacked further down.

**S2. Data Search results are not announced to screen readers.** The only live region for answers is `#log`
(index.html:134, `aria-live="polite"`), inside `#convo`, which is hidden on the results with Data Search
(app.js:149-150). Before, every reply was announced through the log (I-054). Now a Data Search question changes the
grid and the heading silently; focus stays in the bar. Fix: a polite status for the result set (e.g. `role="status"`
or `aria-live="polite"` on `#resultsHead`, or a visually hidden status line set to "38 moments · any player · nutmeg").

### Nits

- **N1. Prompt gap on focus.** app.js:397-401: focusing the empty box while the typing is between prompts (shown is
  empty, about 400 ms of each cycle) freezes the placeholder at "|" and Tab moves on instead of filling (reproduced:
  Tab went to `#homeGo`). Focus mid-word freezes a partial prompt ("Find me all "), though Tab fills the whole one. Use
  `PROMPTS[typing.p]` on focus when `typing.shown` is empty or partial.
- **N2. Sticky panel under the header at the end of the page.** At 1440 after a follow-up with 4 results, scrolled to
  the end: panel top 40.7 px, header bottom 62.5 px, so "Conversation" is cut. Ordinary sticky-at-container-end
  behaviour (product.css `.convo` sticky inside `.work`); cosmetic.
- **N3. Focus order on narrow screens.** With the panel shown first visually (`order: -1`), it is last in the DOM, so
  keyboard focus reaches it after the whole grid (WCAG 2.4.3). Goes with D12 and S1.
- **N4. Two Retry buttons for one failed search.** app.js:570 adds Retry to the log and app.js:573 / 1038 adds one under
  the empty text. After the grid's Retry succeeds, the log's stale Retry stays and re-runs the search if clicked.
- **N5. Safeguard list misses some UNCLEAR items from the adaptation map.** Not in D1-D13: I-028 (tab title "Regista
  Player" on /me vs the nav's "Player profile"; / is "Regista" though the nav says Home); I-098 (actions wrap to 2 rows at
  1110 px and 3 at 375 px); I-148 (Home uses each match's POST /chat, not GET /search: whether that is "the existing
  per-match search"); I-145 results order on narrow (S1); I-055 (the old placeholder's follow-up examples now live only
  in the panel hint). They should reach Zaid's list.

## Disagreements with decisions (not changed)

- **Cards "exactly as today" on cross-match results.** A card such as "Zane Weber (11): nutmeg at 9'" no longer says
  which of 34 matches it is from; the only way to find out is to open it. A one-line match name on result cards (D7)
  seems worth the departure from "exactly".
- **Search every match by calling each match's /chat.** 34 requests per question; home.md measures about 23 s on a cold
  server (league streams regenerated on first use). On the live single-replica app a judge's first search will be the
  slow one. A server-side cross-match search would be better; out of this UI-only scope.
- **"Match recap" keeps Instant / Foundry** while every other switch now says Data Search / Ask Microsoft Foundry: two
  vocabularies for the same choice on one screen.
