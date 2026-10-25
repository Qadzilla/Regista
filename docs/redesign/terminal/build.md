# Scout terminal port: build report

Branch `ux/terminal`, cut from `main` after part A merged (1900d8a). The Scout terminal Zaid approved in the sandbox
(`sandbox/terminal.js`, `terminal.css` and the `#scout/terminal` markup) is now the **Terminal** section of `/scout`.
It runs on the real API instead of the sandbox's `terminal.json` export. Nothing was pushed, merged or deployed. Nothing
was sent to the live app or Azure. Every check below ran offline on this machine (`REGISTA_DOTENV=`, app on
127.0.0.1:8181).

## What a scout gets

- **Where it lives:** `/scout#terminal`, a new section right after Find players in the left panel (also in the
  profile page's copy of Scout's sections). Every other section of `/scout` works as before (inventory SC-01 to SC-53).
- **The command line:** Bloomberg-style mnemonics with `<GO>`.
  - The commands: `TOURE` (any name), `RANK <pos> <metric>`, `CMP a b [c]`, `SCAT x y [pos]`, `SIM`, `SHOT`, `FORM`,
    `HEAT`, `RDR`, `TEAM <club>` and `HELP`.
  - Autocomplete covers commands, players, clubs, metrics and positions.
  - Up arrow walks the history; Down brings back the line you were typing.
  - Cmd/Ctrl+K focuses the command line from any section of `/scout`, and the keys you type straight after it are
    kept.
- **Nine linked panels in one workspace:** screener, player, radar or pizza, clips, shot map, heat map, form, scatter
  and team style. Each can be hidden, moved or resized (S, M, L, XL).
  - Selecting a player anywhere updates the other panels.
  - Every number opens the moments behind it, and they play in the clips panel.
  - Tooltips give each metric's definition, rule, source, unit and direction, plus the noisy mark and the minimum
    attempts. They open on hover and on keyboard focus.
  - "SYNTHETIC DATA" appears once, with the sample note behind "Small sample".
- **Workspaces:** three of them (layout, focus and compare players, columns, sort, scatter axes, form metric, radar
  template) plus the history, kept in this browser through `Regista.store` (key `regista.demo.v1.terminal`).
  - Reset puts the current workspace back to its defaults. "Reset this demo" in Settings clears them all.
  - A blocked store says "not saved: storage blocked", and the terminal works from memory.
  - Changes made in another tab are read again.

## Zaid's two decisions

1. **The evidence is complete.** A number opens every moment behind it, not the sandbox's first 10.
   - `GET /api/players/{id}/metrics?evidence=KEY` now pages: `evidence_offset` plus pages of up to 500.
   - The terminal reads page after page until it has `total` items, then merges a ratio's or a sum's keys into one
     row per event.
   - Nothing on screen shows a cap. The sandbox's "First 10 of N" and "all N on the app" are gone.
   - Checked in the browser by forcing 40-item pages. Pass completion for Femi Toure took 6 calls (216 rows) and
     showed 124 events, equal to the ratio's 124 attempts.
2. **The four items the sandbox reviewers left open are fixed.**
   - **A FORM bar undercounting its match.** A bar filters the whole list (every page) by its match, so "N in this
     match" is that match's full count. Checked on all ten of Toure's non-penalty xG bars: 6, 1, 0, 1, 0, 1, 3, 1, 1
     and 5, each equal to the API's per-round count.
   - **The radar drawing a missing percentile as the 0th.**
     - A metric with no percentile is now a gap in the outline. The line breaks there, and a lone point between two
       gaps becomes a dot. It is never a point at the centre.
     - A compared or focus player with no percentile at all on the template is not drawn, and a note says why
       ("Jonah Eriksen is not drawn: goalkeepers are not scored on the FW template", "Milan Whitfield has no outline:
       under 101 minutes").
     - The caption explains the gaps.
     - Checked with Toure against Otis Nakamura (a defender with two missing percentiles): one polygon and one broken
       outline.
   - **About 35 Tab presses to reach the screener grid.**
     - F1 and Alt+1 now go straight to the grid's active cell.
     - After RANK, the active cell is the leader's ranked number, so `RANK FW npxg`, then Alt+1, then Down walks the
       ranking.
     - HELP and the screener caption say so.
     - Checked with real key presses: one Alt+1 reached the grid, and Down moved a row with its tip showing.
   - **Two commands leaving their subject off screen.**
     - Commands now load what their panel draws, write the output line, and only then measure and scroll.
     - RANK targets the first three rows of the ranking, not 60% of the table box.
     - A name targets the card plus the "Best vs" table.
     - Checked at 375 px from the top of the page: RANK DF aerial win %, TOURE, SIM, SHOT, FORM, HEAT, RDR, SCAT, TEAM
       and CMP. Each one's chart or table was 100% in view afterwards.
     - At 375 px the harness's background tab does not run smooth scrolling, so these runs replaced `scrollTo`'s
       smooth behaviour with an instant one. At 1440 px the real smooth scroll ran (CMP scrolled to 508 px).

## Smaller fixes carried over from the sandbox reviews

- **Command line and buttons:**
  - The command line's accessible name is "Command line" (it was "CMD>"), and `<GO>` reads "Go".
  - The F-key row is no longer an ARIA toolbar without arrow keys.
  - Tab takes a suggestion into the line without running it. Enter or a click runs it.
- **Labels and numbers:**
  - "Qualified (101+ min)" has no decimal.
  - The synthetic line no longer says "Synthetic data" twice.
  - The noisy mark is hidden from screen readers and replaced by the words ", noisy".
  - SIM says "No close match" when every similarity is under 0.50.
  - SHOT says that penalties are on the map but left out of Shots and npxG.
- **Opponents and help text:**
  - CLIP's match subtitle says "at" for away matches.
  - Team "against" reels name the opponent from the club's side ("R2 at EAS").
  - HELP no longer claims that every number opens clips. It says which numbers open one value per match, and which
    open nothing.

## API added (read-only, public, validated, tested, a row each in `tests/test_access.py`)

| Change | Why |
|---|---|
| `GET /api/players/{id}/shots` | SHOT: every shot (penalties too) with attacking-frame location and end point, xG, outcome, body part, penalty, football minute, round, opponent, clip |
| `GET /api/teams/{club_id}/shots?side=for\|against` | TEAM reels: every shot by or against the club, with who took it and its clip |
| `evidence_offset` on `/api/players/{id}/metrics?evidence=KEY`, `offset` in its answer | complete evidence (decision 1) |
| `minute` on every evidence item and on set-piece items | CLIP rows show the football minute (30-minute matches on a 90-minute clock) |
| set-piece evidence items carry the taker (`global_id`, `name`), `xg`, `outcome`, `clip_id`, `video_url` | the set-piece xG reel plays its shots |
| `digits` on every metric (player and team), `min_attempts` and `min_attempts_rule` on `describe()` | formatting and the tooltip's minimum attempts |
| `pitch` on `/api/metrics` (size, frame, touch grid, its events) | the heat map's caption |
| `offset` on `/api/terminal/screen` | the screener pages instead of trusting `limit=200` |

The engine computes no new values, so it gives the same numbers as before (`-m slow` passes). The changes are these:

- `MatchMetrics.shot_list` records each shot as it is counted.
- `SeasonMetrics` keeps each match's period table (`minute()`) and the league's shots (`player_shots`, `team_shots`).
- The new tests check that the shots add up to the engine's own totals. For Toure: non-penalty shots equal Shots,
  and their xG equals npxG. For each club: shots and xG, for and against.

What the API did not need: per-player heat-map cells come from the existing `/api/players/{id}` `grid`. The screener
fetches its columns 16 at a time (the endpoint's limit) and caches them per metric, so up to 40 columns work.

## Files

- `src/regista/static/scout/terminal.js` (new): the terminal. It is a plain script on `window.Regista` and adds
  nothing to it, so the pinned export line holds. It is loaded after `scout.js`.
- `src/regista/static/scout/terminal.css` (new): the sandbox's styles, scoped under `.pf .tx`.
- `src/regista/static/scout/index.html`: the section markup and the nav link. The terminal sits inside
  `<div class="pv" data-panel="terminal">`.
- `src/regista/static/player/index.html`: the nav link.
- `src/regista/season/metrics.py` and `src/regista/terminal_api.py`: the API above.
- `src/regista/cloud/smoke.py`: the image's smoke test checks that the Scout and Terminal files are packaged.
- **Docs:** `README.md`, `docs/architecture.md`, `docs/scout-terminal/build/metrics.md` and `CLAUDE.md` (§2.10 and
  §3.0).
- **Tests:**
  - `tests/test_scout_terminal.py` (new, 15 tests).
  - `tests/test_metrics.py`: 9 new tests, one of them parametrized over 8 bad inputs (16 cases in all).
  - Updated to add the Terminal section: `tests/test_scout_page.py`, `tests/test_product_page.py` and
    `tests/test_access.py`.

## App rules, and how each is held

| Rule | How |
|---|---|
| CSP: no inline script, handlers or `style=` | `terminal.js` contains no `style=` at all. Shading, colours, bar widths and range ticks are `data-bg`, `data-c`, `data-g`, `data-fg`, `data-w` and `data-l`, applied by `styleUp()` through `element.style` after each render. SVG colours are presentation attributes. A test pins all of this |
| `esc()` on every API value in `innerHTML` | `const esc = R.esc`. The test removes calls that escape what they are given (esc, runBtn, shirt) and fails on any name, club, label, definition, rule, title or note left raw in markup. In the browser, every API name, club, label, definition, rule and note was given `<img onerror=…>` appended: the payload rendered as text in every panel, clip list, tooltip and help, and no element was created |
| `Regista.store` only | No `localStorage`, `sessionStorage` or `indexedDB` in `terminal.js` (test) |
| Read-only | No POST, PUT or DELETE, no `fetch`, no key header. Every request is a `Regista.api` GET to the listed endpoints (test) |
| No hidden ratings | None in the new payloads (test). The script reads no rating key or `attributes` (test) |
| No ids shown to people | Output lines and panel captions use metric labels, not keys. Metric keys appear only where they are what you type (autocomplete detail, the tooltip's key, HELP's examples) |
| The router | `Regista.sections` hides every `[data-panel]` that is not the current section, so the terminal's own panels use `data-txp` (test) |

## Checks

- **Tests:**
  - `python3 -m pytest -q`: 829 passed, 13 deselected.
  - `python3 -m pytest -q -m slow`: 13 passed.
  - After the last JS changes, the 196 tests in the affected files passed again.
- **Browser, local app on :8181 (offline), 1440 x 900 and 375 x 812:**
  - No console messages at either width.
  - `scrollWidth` equals the viewport width at both, so there is no sideways page scroll. Wide tables scroll inside
    their panels.
  - Clips played from the API: a screener number (Toure npxG, 19 moments, `readyState` 4), a shot on the shot map,
    team xG against (29 opponent shots, adding up to 4.50 xG), goals for (10), set-piece xG (7 shots with their
    takers).
  - Possession opens ten match values, without a clip.
  - These commands were all run: RANK (including an ambiguous metric, which offers choices), CMP (including a keeper
    and an unqualified forward), SCAT with metric labels, SIM, SHOT, FORM, HEAT, RDR, TEAM, HELP and Escape, and an
    unknown word (which gives an error with examples).
  - Workspaces: switching, hiding a panel, Reset and Find players and back all held.
  - Cmd+K pressed from Overview with real keys opened the Terminal, and "rank mf key" typed straight after landed in
    the line and ran: "RANK MF · Key passes: 18 midfielders; top Pavel Petrov 2.12".
- **Not checked:** a screen reader end to end, Safari and Firefox, and the live app (not deployed).

## Open

- **Namesakes.** When a name is ambiguous, the player with the most minutes opens, as in the sandbox (`USTINOV`
  opens Otis). The namesakes are one click away.
- **Penalty xG ties.** Team penalty-xG ties are ranked 2 to 6 (a club with 0.00 reads "3/6"). That ranking is the
  engine's `team_style`, not the terminal's, and is unchanged.
- **Units.** Physical values in RANK lines and screener cells still carry no unit.
- **Help dialog.** Help is a non-modal dialog without a focus trap. Escape closes it and returns focus.
- **Deploy.** Merging and deploying are Zaid's call.
