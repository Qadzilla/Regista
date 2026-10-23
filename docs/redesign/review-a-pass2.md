# Reviewer A, pass 2

Branch `ux/app-redesign` at 6aa20af (`git diff main...HEAD`: 7 commits). Checked against the brief, docs/redesign/inventory.md
(I-001 to I-148), adaptation.md and safeguard.md. No code was changed by this review.

Paths: `index.html`, `app.js`, `product.css` are in `src/regista/static/product/`; `regista.css`, `regista.js` in
`src/regista/static/shared/`. Line numbers are at 6aa20af.

## Verdict

**Not signed off.** No blocker; three should_fix items (S1 to S3) remain. Everything else in the brief is applied and every
inventory item I checked is present.

## What was run

- Full suite: `OMP_NUM_THREADS=4 python3 -m pytest -q` → **605 passed**, 10 warnings, 195 s (595 before this work; the 10 new
  tests are the redesign's). Changed test assertions each follow a decision (old h1, ASKS chips, nav labels and order); none
  was weakened otherwise. The `'/search` absence test is unchanged.
- Scope: `git diff main...HEAD --name-only` touches only `src/regista/static/` (me, player, product, scout, shared),
  `tests/test_product_page.py`, `tests/test_player_api.py` and `docs/redesign/`. No Python, API, data, infra or deploy file.
  No inline scripts, handlers or style attributes; text reaching innerHTML goes through `esc()` (checked `searchEvery`,
  `howAnswered`, `render`, `searchNote`, `progress`, `where`, the way-out buttons use textContent).
- Browser: local server `REGISTA_DOTENV= python3 -m uvicorn regista.api:app --port 8074` (health: Foundry, Cosmos, Search off;
  stopped afterwards), own tab, at 1440 x 900, 1366, 1280, 768 x 1024 and 375 x 812 (mobile preset).

| page / state | 1440 | 375 | notes |
|---|---|---|---|
| Home landing | ok | ok | Logo, tagline verbatim, prompts typing in and out, Tab filled "Find me all the nutmegs", "Data Search · Ask Microsoft Foundry" under the box, no pitch copy, no example buttons, footer. scrollWidth 375. |
| Results, Data Search ("Find me all the nutmegs") | ok | ok | 38 moments in 15 matches, compact bar + switch on top, tag chips, sort, no panel. Focus returns to the bar. |
| Results, Ask Microsoft Foundry ("now the replays") | ok | **S1** | Panel on the right with the whole log. Fallback reads honestly: "Foundry is not set up on this server, so Regista's rules wrote this reply." and the hint "Foundry is not set up on this server, so Regista's rules will write the reply. The moments found are the same." |
| Match view from a card | ok (**S2** at 1280/1366) | ok | No explainer line; timeline; stage; actions in one row at 1440; "Match recap" folded with Instant / Foundry inside (opened: written, citations, recap reel); conversation in the panel only, "How Regista answered · Data Search, no AI model · 4 steps" with steps and "Details: step names and times" on demand; playing card border rgb(38,44,58), no shadow, `aria-current="true"`. |
| Deep link `/?match=rl_r08_bro_fai&player=t_home_10&clip=cl_t_home_10_000018` | ok | ok | Match view, clip autoplays, Scout link "See Kenan Nakamura's Scout profile" → /players/pl_bro_10, "Watch the full match (the first view takes a few minutes)". Also `&recap=1` (fold opened, written, top 71 px), `?match=rl_r01_ash_fai&t=600` (9:57–10:03 played, full match `#t=600`), `?match=nope_1&player=x` (landing, URL cleared, no banner). |
| /scout | ok | ok | Left panel, Scout current in yellow; row of tabs at 375; content unchanged. scrollWidth 1440 / 768 / 375. |
| /players/pl_bro_10 | ok | ok | Scout current; profile links still `/?match=&player=&clip=` and open the match view. |
| /me | ok | ok | "Player profile" current. |
| /studio | ok | n/a | Unchanged (own header, no left panel). |

Also checked: Back to results restores the 21 header results and focuses the bar; "Femi Toure" prompt (39 moments, note
"Only Femi Toure: …", Show more (9 more) → 39, Match order); way-out button "Show all 11 moments of Sami Castellanos"; How it
works (services list, realism report, Close); keyboard Enter on a results card opens the match view; no sideways scroll at
375, 768, 1280, 1366 or 1440 on any page; no console errors from the pages.

## Issues

### S1 (should_fix, layout / decision not applied): on screens up to 1100 px the Foundry panel sits above the results' compact search bar

- Where: `index.html:42-147` (the `.rbar` is inside `.work-main`, beside `#convo` in `.work`); `product.css:189-193`
  (`.convo { order: -1 }` at <= 1100 px).
- What: at 375 px with Ask Microsoft Foundry, the panel (log, its own box and switch, hint) is first (top 213 px), the compact
  bar comes after it (711 px) and the grid starts at 1049 px. Two search boxes and two switches stack, and the bar is not
  "at the top" as decided. The sandbox keeps `.rbar` outside `.rbody`, so there the panel moves above the grid only
  (`sandbox.css:100`). The match view's order (panel above the match) does match the sandbox and is safeguard D12.
- Fix: keep the bar first on narrow screens, for example move `.rbar` and `#searchNote` out of `.work-main` to sit above
  `.work` in the results view (or give the bar `order: -2` in a layout where it shares the grid with the panel). Not in the
  safeguard's list (D12 covers the match view only).

### S2 (should_fix, decision not applied at common desktop widths): the stage's four actions take two rows on league matches below about 1440 px

- Where: `product.css:101-102` (`.stage > .actions`, `white-space: nowrap`); `app.js:322` (the long label
  "Watch the full match (the first view takes a few minutes)" on matches over 10 minutes, i.e. all 30 league matches).
- What: on `rl_r08_bro_fai` the four actions share one row at 1440 (top 580 for all), but at 1366 (555, 555, 555, 598) and
  1280 (541, 541, 541, 584) "Watch the full match …" wraps to a second row; the stage is 652 px wide beside the 220 px
  nav and the 360 px panel. Adaptation and safeguard checked one row only at 1440. 1280 and 1366 are the most common laptop
  widths, and the decision is "the stage's actions in one row".
- Fix (without losing I-101's wording): keep "Watch the full match" as the button text and move "(the first view takes a few
  minutes)" to a muted note right under the row (or the link's title plus a visible note), or let the row shrink its
  padding/font further before it wraps. Phones wrapping (375 px: two rows) is a separate yes/no already raised by
  adaptation I-098.

### S3 (should_fix, bug: wrong number shown): "Details: step names and times" says "53 matches" when 34 were searched

- Where: `app.js:690-699` (`aggregate()` adds `n += 1` per trace step) and `app.js:888` (shown as `· ${s.n} matches`).
- What: after "Find me all the nutmegs" the details read `librarian.search_clips 43 ms · 53 matches` while the same reply says
  "Read every match (34 matches)" and "34 matches searched in 623 ms". A match whose reply runs `search_clips` twice (the
  "Checked what else the same player has" step) is counted twice. It is the panel that explains how Regista answered, so it
  must not overstate.
- Fix: count distinct matches per step name (keep a Set of match ids in `aggregate()`), or label the count as runs
  ("53 runs in 34 matches").

### Nits

- N1 (accessibility): opening a result with the keyboard re-renders the grid, so focus falls to `<body>`
  (`app.js:758-779`, `render()` replaces `#grid`). The next Tab lands on the stage video, so it is usable, but moving focus
  to the stage or the match title would say where you are.
- N2 (safeguard completeness): adaptation flagged I-028 (tab titles "Regista" and "Regista Player" against the nav labels
  "Home" and "Player profile") as UNCLEAR, but safeguard.md has no decision item for it; D1 covers link text only. Add it to
  the needs-decision list. The same for S1's narrow-screen order on the results (adaptation I-145) and phone wrapping of the
  stage actions (adaptation I-098), which safeguard records as decided.
- N3: "Match order" on the results orders by match then time, and cards do not name their match (safeguard D7), so the
  grid reads 26:29, 7:42, 7:55 … with no visible break between matches. Covered by D7; noted because it is most visible here.

## Decisions checked as applied

Landing (logo, tagline, six prompts verbatim, Tab fill, reduced-motion still, switch under the box, no pitch copy or examples);
results (compact bar with switch, grid and cards as before, panel only with Foundry, every match searched through each
match's `/chat` with `PARALLEL = 6`, merged best first; cost written in home.md "Cost" for the PR); match view (no `#matchSub`,
conversation in the panel only, one-line "How Regista answered" with steps and times on demand, folded "Match recap" with its
own switch, actions in one row at 1440, no yellow outline); navigator on /, /me, /scout, /players/{id} (left panel, current
in yellow `rgb(255, 205, 40)`, row of tabs at <= 720 px, labels and order Home / Player profile / Scout, Scout current on
profiles); Player and Scout content unchanged (diff touches only nav markup and the removed `.views` overrides).

Inventory spot-checked present in the browser: I-007, I-010 to I-018, I-030 to I-036, I-050, I-052, I-054 to I-059, I-062 to
I-068, I-070 to I-074, I-078 to I-101, I-103, I-105 to I-111, I-114 to I-120, I-122 to I-125, I-127 to I-135, I-138, I-140,
I-143, I-144, I-146. Not reproducible locally (read in code only): Cosmos DB matches (I-045, I-121), network failures (I-040
to I-043, I-069 Retry), reel download (I-099), an empty server (I-042).

## Disagreements with decisions

None that I would change. One observation for Zaid: with Data Search on the results there is no panel, so the reply text
and "How Regista answered" for that search are not visible anywhere until the switch moves to Foundry or a card opens. This
follows the decision ("with Ask Microsoft Foundry, the conversation panel on the right") and is listed only so it is a
conscious choice.
