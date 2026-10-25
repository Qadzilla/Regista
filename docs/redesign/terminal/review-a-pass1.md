# Scout terminal port: independent review A, round 1

Branch `ux/terminal`, reviewed at 7faffb9 (build 2fc1ed4 plus the safeguard's fix). I looked at
`git diff main...HEAD`. Lens: correctness, safety and honesty.

How I checked:

- The app ran offline on 127.0.0.1:8183 with `REGISTA_DOTENV=`.
- I drove the page with a headless Chromium (Playwright) under the page's real Content Security Policy. I did not use
  the shared browser pane.
- I compared what the page shows against the API's answers and the engine.
- Nothing went to the live app or Azure. I fixed nothing; this file is the only change.

**Verdict: not signed off.** One must-fix and two should-fixes.

## Must fix

### 1. The heat map counts uploaded and claimed matches, but calls them "this season"

- **Where:** `terminal.js` `renderHeat()`. It reads `grid` from `GET /api/players/{id}`. `PITCH.heatmap_rule` in
  `terminal_api.py` names the same source.
- **The problem:** the profile's grid is built by `Season`. `Season` adds the touches from every confirmed claim and
  every finished Player-view upload (`profiles.py`: `_add_claimed` calls `_add_match`).
- **Why that is wrong here:**
  - Every other number in the Terminal comes from the metrics engine. The engine's scope is "Regista League fixtures
    (synthetic); claimed and uploaded matches count on profiles only" (`_season_meta`).
  - Yet the caption says "N on-ball actions this season". It sits under Touches, Touches in the box and Progressive
    passes received, and those three are league-only.
- **Reproduced:** I built the season with one fake upload for Femi Toure, using a league match folder as the upload:
  - Toure's grid went from 407 to 468 actions, and his profile from 10 to 11 appearances.
  - The engine still says 10 appearances and 182 touches.
  - Offline, no uploads exist, so the build and the safeguard saw 407 and could not notice.
- **Why it matters on the live app:** Toure (pl_bro_09) is the Terminal's default focus player. He has the finished
  demo upload up_8807d7835c (CLAUDE.md §4.1), so the first heat map a judge sees mixes in a non-league friendly.
- **Fix:** take the heat map from league matches only. Two ways:
  - add a small read-only `grid` (league only) to the terminal API, from the metrics engine or from `Season` restricted
    to `source == "league"`, with a test that an upload leaves it unchanged;
  - or say plainly that uploads are included. That would break the Terminal's single scope, so the first is better.

  Then correct the `heatmap_rule` text.

## Should fix

### 2. "Reset this demo" in another tab is undone by an open Terminal

- **Where:** `terminal.js`, the `R.store.watch` handler and `readStore()`.
- **The cause:** `Regista.store.reset()` removes each key. Another tab's `storage` event therefore fires with
  `k === 'terminal'`, and `readStore()` runs. But `readStore()` only replaces `store` when a saved value exists. With
  the key gone it keeps the old workspaces and history in memory.
- **Reproduced (two tabs in one browser context):**
  1. Tab A ran `CMP Femi Toure Amari Ustinov` and `TEAM EAS`.
  2. Tab B clicked Reset this demo in Settings.
  3. The key was gone, but tab A still showed both compared players.
  4. One club click in tab A wrote back the old workspace: compare `[pl_bro_09, pl_ash_09]` and the history
     `['CMP Femi Toure Amari Ustinov', 'TEAM EAS']`. The reset was undone.
- **Why it counts:** this is the cross-tab half of the bug the safeguard fixed for the same tab (SC-47). The comment
  above the handler says it already covers it ("or Reset this demo cleared them").
- **Fix:** when the stored value is missing, reset `store` to `{ cur: 0, ws: [null, null, null], hist: [] }` before
  `clean()`, and drop any pending save. Add a test like `test_reset_this_demo_resets_the_terminal_in_the_same_tab`.

### 3. `CMP` with no player crashes and leaves the previous success line on screen

- **Where:** `terminal.js` `cmdCmp()`.
- **The cause:** for `CMP vs` or `CMP ,`, `resolvePlayers` returns `[]`. `rest` is not empty, so
  `` out(rest ? `No player called "${bad.q}".` …) `` reads `.q` of `undefined`.
- **Reproduced:** two page errors, "Cannot read properties of undefined (reading 'q')". The output line still read
  "CMP Femi Toure · Otis Nakamura: radar and table vs each player's position peers." from the command before, so the
  failed command looked like it had worked.
- **Fix:** test `!rs.length` first and show the usage line. Add a test for it.

## Numbers checked against the API and the engine (all match unless noted)

| Panel | What I compared | Result |
|---|---|---|
| Ready line | 102 players, 127 metrics, 30 matches | matches `/api/terminal/screen` total, `/api/metrics`, `/api/season` |
| SCRN | Toure's 8 default FW cells: np goals 1.64, npxG 1.15, npxG/shot 0.185, xA 0.14, SCA 5.91, take-ons won 0.33, touches in box 9.19, prog. passes received 11.81; the order Toure, Ustinov, Whitfield, Brennan, Tanaka, Kowalski | match `/api/players/pl_bro_09/metrics` (digits too) and the npxg sort |
| PLYR | age 27, height 184 cm, foot Left, Ireland, 274 min, 10 apps; Best vs forwards (six at the 97th) | match the screen card and the metrics |
| SIM | Ustinov 0.63, Reyes 0.39, Whitfield 0.17, Ibarra 0.16, Brennan 0.14 | match `/similar` (0.627, 0.389, 0.175, 0.159, 0.140) |
| RDR | pizza percentiles 97, 97, 92, 53, 97, 8, 97, 92 | match the API's percentiles |
| RDR, CMP | Toure against Otis Nakamura (DF): one polygon and one broken outline, no centre point; Nakamura's two missing percentiles show "–" | correct (fix 2 holds) |
| SHOT | 19 shots, 0 penalties, Goals 5, npxG 3.513 total, 9 on target | `/shots` adds up to the engine's Shots, npxG and Shots on target; every shot has x ≥ 73, the distance agrees with x and y, and every shot has a video |
| HEAT | Touches 182, in the box 28, prog. passes received 36 | match. The 407 actions match the profile grid offline, but see must-fix 1 |
| CLIP | touches in box 28 rows, touches 182 rows, npxG per shot 19 rows ("3.51 of 19") | equal to the evidence totals; a clip `src` is set from the API |
| FORM | np goals bars give 2, 0, 0, 0, 0, 1, 0, 1, 0, 1 "in this match" (sum 5); pass completion bars give 14, 8, 14, 10, 16, 9, 9, 11, 14, 19 | equal to the per-match evidence counts (the `passes` key); fix 1 holds |
| RANK | `RANK DF aerial win %`: 24 defenders, top Caio Sorensen 100.0%; `RANK FW npxg`: 18, Toure 1.15 | match `/api/terminal/rank` (24 ranked, Sorensen 9 of 9) |
| TEAM | BRO 1st, 17 pts, 5-2-3, 10:7; possession 54.1% (1/6), PPDA 13.6 (2/6), xG for 2.51 (1/6), goals against 2.09 (6/6), set-piece xG 0.26, pressures 147.23 (6/6) | match `/api/season` and `/style` |
| TEAM reels | EAS xG against: 52 shots adding up to 6.27 (engine total 6.274); EAS goals for: 1; BRO against: 29 shots, 4.496; set pieces: 7 shots, 0.863 | match `/style` totals. For all six clubs, goals counted from `/shots` equal the league table, both for and against |
| Physical | Distance in R1: 3125 m, 30 min, "1 in this match" | matches the per-match evidence (3124.8) |

## Rules

- **API additions:**
  - All of them are read-only GETs and validated: bad ids give 400, unknown players and clubs 404, bad `side`, negative
    `offset` or `evidence_offset`, and `evidence_offset` without `evidence` give 422.
  - `tests/test_metrics.py` covers them: paging equals one unpaged read, shots add up to the engine's totals for a
    player and two clubs, set-piece takers, the input checks, and no hidden ratings.
  - `tests/test_access.py` lists both new routes as public.
  - The engine computes nothing new.
  - No evidence list in this league is longer than 500 (the longest is 347, Lindqvist's pass completion). So the
    terminal's paging loop never runs on real data. It is simple and correct, and the API's paging is tested.
- **CSP:** the header is `script-src 'self'`. There are no `style=`, inline handlers or inline scripts in
  `terminal.js` or the new markup. Under the real CSP the page logged no CSP or console errors (only the CMP crash in
  item 3).
- **esc():** I scanned every `${…}` in markup in `terminal.js`. Every API string goes through `esc`, `runBtn` or
  `out` (textContent). The values left unescaped are numbers made by the code (`Number()`, `Math.*`, `toFixed`, sums,
  lengths) or constants (`GROUP_COL`, `OUTCLASS`).
- **Storage:** `Regista.store` only. There is no `localStorage` in `terminal.js`.
- **Read only:** every request the page sent in every run was a GET.
- **No hidden ratings:** none in the new payloads (tested), and none read by the script.
- **Width:** at 375 px, after eight commands, `scrollWidth` was 375 and there was no sideways scroll. Ctrl+K typed
  from Overview landed in the command line. After `RANK FW npxg`, Alt+1 focused Toure's npxG cell (1.15), and Down
  moved to Ustinov's (0.77).
- **Tests:** `python3 -m pytest -q` gave 830 passed, 13 deselected; `-m slow` gave 13 passed.
  - The terminal's own tests (`tests/test_scout_terminal.py`) are mostly source-string pins, not behaviour tests.
  - They would not catch items 2 and 3. Behaviour tests for the new fixes would need a browser in CI, which the repo
    does not have. Accepted as is, but item 2's test should at least pin the empty-store branch.
- **The inventory** was checked in full by the safeguard. My runs touched the Terminal and Settings only and found no
  regressions there.

## Nits

- **Physical reels say their note twice.** It appears in the clip header and again as the video message: `openReel`
  calls `stopVideo('nolink')`, which shows `reel.note`. The sub-line shows the season total "28030.6 in total" with no
  unit, while the rows say "3125 m". This is the build's known units item.
- **HELP undercounts what opens per-match values.** It says only "team-style ratios" open one value per match. High
  turnovers and pressures (per-90 counts) do too. The team caption ("the others open one value per match") is the
  accurate one.
- **Source codes in HELP.** HELP lists source codes ("FB-XG") next to their titles. They are id-like strings shown to
  people. This is the approved sandbox design, so a nit only.
- **Namesakes.** `SHOT USTINOV` opens Otis Ustinov (DF, most minutes) rather than the forward Amari. The build leaves
  this open, and it offers the namesakes.
- **Ctrl+K on a Mac.** On a Mac, Ctrl+K in Reports or Messages text fields is taken by the Terminal; there it normally
  deletes to the end of the line. This is the safeguard's open decision: consider binding only Cmd+K when
  `navigator.platform` is a Mac.
