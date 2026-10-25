# Scout terminal port: independent review A, round 2

Branch `ux/terminal`, reviewed at e4c656c (round 1's fixes). I read `git diff main...HEAD` and the round-1 fix diff
(835a990..e4c656c). Lens: correctness, safety and honesty.

How I checked:

- The app ran offline on 127.0.0.1:8183 with `REGISTA_DOTENV=`.
- I drove /scout#terminal in a headless Chromium (Playwright) under the page's real Content Security Policy, at
  1440 x 1000 and at 375 x 812 (reduced motion, so every scroll is instant). I did not use the shared browser pane.
- I compared what the page showed against the API's answers.
- Nothing went to the live app or Azure. I fixed nothing; this file is the only change.

**Verdict: not signed off.** All three round-1 findings are fixed. One must-fix remains: one of Zaid's four required
fixes (a command's subject left off screen) still fails at 375 px.

## Must fix

### 1. At 375 px, HEAT (and partly SHOT) for a player not loaded yet still leaves the chart off screen

- **Where:** `terminal.js`. The `PANEL_CMD` branch of the command runner calls `selectReady()`, then
  `showPanel(..., true)`, which calls `scrollToShow()`.
- **Why it matters:** this is Zaid's port decision (2), item 4: "two commands can leave their subject off screen". The
  build and the safeguard report it fixed.
- **Reproduced (375 x 812, fresh page, reduced motion).** The numbers are the chart's top and bottom, read every
  100 ms for 3 s after Enter:

  | Command | Chart top–bottom | In view? |
  |---|---|---|
  | `HEAT Bruno Lindqvist` | 1021–1238 | no, wholly below the fold |
  | `HEAT Otis Nakamura` | 1021–1237 | no, wholly below the fold |
  | `HEAT Gino Yilmaz`, run cold | 1021–1238 | no |
  | `HEAT Gino Yilmaz`, after `SHOT Gino Yilmaz` | 121–338 | yes |
  | `HEAT Femi Toure`, already loaded | 121–337 | yes |
  | `SHOT Amari Ustinov` | 592–952 | the bottom 140 px are cut off (61% visible, just over the 0.6 test) |

  At 1440 px the same commands land in view: shot and heat share a row there.
- **Cause:** the command waits for its own panel's data, then scrolls. But at phone width the panels are stacked, and
  the panels above the subject start loading only once the player is selected: Form sits above Shot, and Form and Shot
  sit above Heat. Their data arrives just after the scroll. The Loading line becomes a chart about 400–500 px taller,
  and the subject is pushed below the fold. The safeguard's 10 commands probably ran with those panels already loaded
  (for example SHOT before HEAT for the same player), so they passed.
- **Fix (one way):**
  1. Before scrolling, wait for the data of every visible panel that sits above the subject (form, shots, heat), not
     only the subject's own.
  2. Or re-check `inViewFit` and scroll again once the repaint that `repaintSoon` triggers has landed.

  Then test with each panel's data not yet loaded: for example `HEAT <player>` as the first command for that player
  at 375 px.

## Round-1 findings: all fixed (checked in the browser and in the code)

| Finding | Check | Result |
|---|---|---|
| Heat map counted uploads as "this season" | `Season.league_grids` is copied after the league fixtures and before claims and uploads. `GET /api/players/{id}/heatmap` serves that copy and validates the id: a bad id gives 400, an unknown player 404. It is listed public in `test_access.py`. `test_the_heat_map_counts_league_fixtures_only` shows a fake upload adds an appearance and grid touches to the profile and leaves `/heatmap` unchanged. The caption says "in league matches this season". | fixed |
| Cross-tab Reset this demo undone | Tab A ran `CMP Femi Toure Amari Ustinov` and `TEAM EAS`. Tab B clicked Settings → Reset this demo. Tab A then showed "CMP none". One club click in tab A stored compare `[]`, club BRO and history `[]`, so nothing old came back. The same-tab reset also still works: after it, the store is empty and CMP shows none. | fixed |
| `CMP` with no player crashed | `CMP vs` and `CMP ,` show the usage line, with no page errors. | fixed |

## Numbers checked against the API (17 checks, more than 60 numbers, all match)

I chose different players from round 1 (a defender, a defensive midfielder, a second forward, another club), so this
sample is independent of the earlier one.

| # | Panel | Terminal shows | API |
|---|---|---|---|
| 1 | Ready line | 102 players, 127 metrics, 30 matches | screen total, `/api/metrics`, `/api/season` |
| 2 | PLYR, Caio Sorensen | age 24, 189 cm, Right, Ghana, 275 min, 10 apps | `/metrics` card: 24, 189, right, Ghana, 275.3, 10 |
| 3 | PLYR best | Prog. passing distance 469 (98), Passes into final third 5.23 (98), Skill moves 0.33 (98), Aerial duels lost 0.00 (98), Aerial win 100.0% (98), SCA 1.96 (94) | same values and percentiles |
| 4 | SIM, Sorensen | Whitfield 0.59, Ustinov 0.58, Oliveira 0.50, Rahman 0.29, Whitfield 0.19 | `/similar` 0.591, 0.585, 0.497, 0.286, 0.194 |
| 5 | RDR, Sorensen (DF template) | 69, 85, 73, 94, 60, 65, 98, 69; prog. passes 3.92, tkl+int padj 3.16, interceptions 0.98, clearances 2.62, blocks 0.65 | same |
| 6 | HEAT, Sorensen | Touches 60.16 (184 tot), in the box 0.00 (0), prog. passes received 0.33 (1); 406 on-ball actions | `/metrics`; `/heatmap` total 406 |
| 7 | CLIP, Lindqvist pass completion | "89.6% · 164 of 183 · 75th pctl", 183 rows (✓/✗), clip src set | 347 evidence items = 183 distinct events (complete, no cap) |
| 8 | FORM, Lindqvist passes | bars per 90: 27.00, 85.31, 41.72, 81.00, 60.00, 42.00, 65.35, 42.00, 71.29, 56.81 | per-match evidence 9, 20, 14, 27, 20, 14, 22, 14, 24, 19 over 30/21.1/30… minutes |
| 9 | FORM bar R3 | "14 in this match", 14 rows, R3 clip | 14 passes in rl_r03_cal_eas |
| 10 | SHOT, Amari Ustinov | 13 shots, 3 goals; Shots 4.49 (13 tot), npxG 0.77 (2.22 tot), npxG/shot 0.171, on target 1.73 (5 tot), 13 non-penalty | `/shots`: 13 shots, npxG 2.22, 3 goals, 0 penalties |
| 11 | SHOT clip | "13 shots, penalties included", 13 rows, mp4 src | the clip returns HTTP 200 video/mp4 |
| 12 | RANK MF progressive_passes | 18 midfielders; top Kenan Nakamura 7.23 | `/rank`: ranked 18, #1 pl_bro_10 7.23 |
| 13 | TEAM CAL header | 4th · 13 pts · 3-4-3 · 3:3 | `/api/season` table |
| 14 | TEAM CAL style | possession 49.8% 4/6, field tilt 39.2% 6/6, PPDA 14.3 1/6, passes per sequence 2.93 6/6, long-pass share 15.8% 1/6, xG for 0.81 6/6, xG against 1.16 1/6, goals against 0.90 1/6, set-piece xG 0.07 5/6, pressures 170.93 3/6, league averages | `/style` values, ranks and league means |
| 15 | TEAM CAL reels | (API side) shots against 40, xG 3.888, 3 goals; shots for 25, xG 2.725, 3 goals | equal to `/style` totals and the table's 3:3 |
| 16 | SCAT xa × sca MF | 18 midfielders; axis 0.00–0.45 and 0.06–4.51 | 18 qualified points; extents 0–0.42 and 0.30–4.27 plus the 6% padding |
| 17 | Keyboard route | after `RANK FW npxg`: Alt+1 focuses Toure's npxG 1.15, Down moves to Ustinov 0.77, Enter opens "0.77 xG per 90 · 2.22 in total · 92nd pctl · 13 moments" | `/metrics` |

## Rules

- **CSP:** the header is `script-src 'self'`. `terminal.js` and the new markup have no `style=`, inline handlers or
  inline scripts. No page errors or CSP errors in any run.
- **esc():** round 1's changes add only `esc(total)` and static text to markup.
- **Storage:** `Regista.store` only. No `localStorage` in `terminal.js`. The cross-tab path calls
  `R.store.remove`/`get`, never storage directly.
- **Read only:** every request in every run was a GET. A string pin in the tests guards the same.
- **No hidden ratings:** none in `terminal.js` or `terminal_api.py`. `/heatmap` is included in the hidden-ratings test.
- **Width:** 375 px gave `scrollWidth` 375 after 10 commands, so no sideways scroll.
- **Tests:** `python3 -m pytest -q` gave 836 passed, 13 deselected. `python3 -m pytest -q -m slow` gave 13 passed. The
  terminal's JS tests are still source-string pins. They would not catch must-fix 1, which only a browser shows.
- **The inventory:** the safeguard checked it in full. My runs touched Terminal and Settings only, and found no
  regressions.

## Nits

- **FORM bar labels for per-90 metrics.** The label reads "Passes 27.00" for a match with 9 passes. The caption says
  bars are per 90, but the bar's own label could say "27.00 per 90" so it does not read like a count.
- **Open from round 1, unchanged:** physical values have no unit in RANK lines and screener cells; ambiguous names open
  the player with the most minutes; Ctrl+K on a Mac is taken in text fields; source codes appear in HELP.
