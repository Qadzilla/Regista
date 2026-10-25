# Scout terminal port: independent review A, round 3

I reviewed branch `ux/terminal` at 260fcc3, which holds round 2's fix. I read `git diff main...HEAD` and the round-2
fix diff (ba94c07..260fcc3). My lens was correctness, safety and honesty.

How I checked:

- The app ran offline on 127.0.0.1:8183 with `REGISTA_DOTENV=`.
- I drove /scout#terminal in headless Chromium (Playwright) under the page's real Content Security Policy, at
  1440 x 1000 and at 375 x 812, with reduced motion so every scroll is instant. I did not use the shared browser pane.
- I compared what the page showed with the API's answers.
- Nothing went to the live app or Azure. I fixed nothing; this file is the only change.

**Verdict: signed off.** Round 2's must-fix is fixed and holds up on players that earlier rounds did not test. Every
number I checked matches the API. Nothing must or should be fixed. The nits are below.

## Round 2's finding: fixed

**Finding:** HEAT and SHOT, run as the first command for a player at 375 px, left the chart off screen.

**What I checked:** a fresh page for each command, so nothing was cached. I read the subject's position every 100 ms for
3 s. All the players were new to the reviews:

| Command (first on a fresh page, 375 x 812) | Subject top to bottom (px) | On screen |
|---|---|---|
| `HEAT Farid Vargas` | 121–338 | 100% |
| `HEAT Ivan Santos` | 121–337 | 100% |
| `SHOT Benji Tanaka` | 121–481 | 100% |
| `SHOT Sami Ibarra` | 121–481 | 100% |
| `FORM Jonah Okafor` | 83–283 | 100% |
| `RDR Femi Rahman` | 105–394 | 100% |
| `SIM Leon Toure` (player card) | 8–737 | 100% |
| `TEAM DUN` (the panel is taller than the screen) | 8–1373 | the top is in view |
| `CMP Sami Ibarra, Kenan Kowalski` | 104–393 | 100% |
| `SCAT tackles_won interceptions DF` | 144–394 | 100% |
| `Haruki Vargas` (card's numbers) | 243–422 | 100% |
| `RANK GK saves` (table body) | 706–851 | leader row in view |

- `scrollWidth` stayed at 375 on every run. There were no page errors.
- **Two commands typed 150 ms apart:** `HEAT` then `TEAM`, `SHOT` then `HEAT`, `FORM` then `RDR`, each at 375 px and at
  1440 px. The second command always won: its output line showed, its subject was in view and its player was in focus.
  So the longer wait that `panelsSettled()` adds does not let a stale command scroll away from a newer one.

**Code:**
- `panelsSettled()` is bounded at 6 s.
- A failed request leaves the wait state, so it cannot block the loop.
- `team()` is now async, and its three callers return its promise from inside the async `run()`.
- The new test pins the order: `selectReady`, then `panelsSettled`, then `showPanel`.

## Numbers checked against the API: 21 checks, more than 120 numbers, all match

I chose players and clubs that rounds 1 and 2 did not use: an attacking midfielder, a central midfielder, two
goalkeepers, a winger, Fairhaven and Dunmore.

| # | Panel | Terminal shows | API / engine |
|---|---|---|---|
| 1 | Ready line | 102 players, 127 metrics, 30 matches | screen total, `/api/metrics`, `/api/season` |
| 2 | PLYR, Noel Oliveira | 26, 184 cm, Right, England, 279 min, 10 apps; best: prog. passes received 2.58 (92), take-ons 4.52 (92), assists 0.32 (86), carries into final third 2.58 (86), take-ons won 1.61 (86), high accelerations 69.1 (86) | `/metrics`: 278.8 min and the same values and percentiles |
| 3 | SIM, Oliveira | Delgado 0.37, Petrov 0.32, Nakamura 0.30, Rahman 0.29, Adeyemi 0.22 | `/similar` 0.369, 0.324, 0.298, 0.286, 0.224 |
| 4 | RDR, Oliveira (MF template) | 0.31/69, 0.97/64, 3.23/69, 3.55/69, 2.26/75, 81.8%/8, 1.86/8, 2.58/58 | `/metrics` (npxg_plus_xa … pressure_regains) |
| 5 | SHOT, Oliveira | Shots 1.29 (4 tot), Goals 0.32 (1), npxG 0.17 (0.54 tot), npxG/shot 0.135, on target 0.32 (1); "4 non-penalty, 0 penalty" | `/shots`: 4 shots, 1 goal, 0 penalties; xG 0.024 + 0.443 + 0.041 + 0.032 = 0.54; 4 × 90 / 278.8 = 1.29 |
| 6 | SHOT list | R1 at ASH 49' 0.02 off target; R2 v DUN 3' 0.44 goal; R4 v EAS 1' 0.04; R5 v CAL 15' 0.03 | `/shots` minutes, xG, outcomes and rounds |
| 7 | HEAT, Oliveira | 389 on-ball actions; Touches 54.23 (168 tot), prog. passes received 2.58 (8 tot) | `/heatmap` total 389; touches evidence total 168; 168 × 90 / 278.8 = 54.23 |
| 8 | FORM bars, Oliveira, npxG + xA | 0.10, 1.32, 0.99, 0.12, 0.11, 0.15, 0.11, 0.00, 0.00, 0.00; season 0.31 | `/form` values and season equal |
| 9 | FORM consistency | mean 0.29, SD 0.47, CV 1.613, L3−S −0.31; pass completion 82.5%, 14.3, 0.174, −1.9 | `/form` mean, sd, cv, last3_minus_season |
| 10 | FORM bar R3 → clips | "1 in this match", key pass at 60' | evidence for npxg_plus_xa: one R3 item (key_passes, 60'); 0.99 × 30 / 90 = the 0.33 xA |
| 11 | RDR, Emeka Dubois → Pass completion | "87.7% · 121 of 138 · 64th pctl", 138 rows (✓/✗) | 259 evidence items = 138 distinct passes, 121 completed: complete, no cap |
| 12 | FORM, Dubois, Pass completion, bar R2 | "16 in this match", 16 rows | R2 evidence: 30 items, 16 distinct events, 14 completed |
| 13 | Playback | first R2 moment: `rl_r02_eas_ash/clips/cl_t_home_08_000005.mp4` | readyState 4, playing (currentTime 5.0 s), no error |
| 14 | PLYR, Emeka Castellanos (GK) | pass completion 60.0%, goals conceded 0.90, saves 2.69, save % 75.0%, clean sheet % 70.0% | `/metrics`: 18/30, 3 total, 9 total, 9/12, 7/10, each 75th |
| 15 | TEAM FAI header | 2nd · 15 pts · 5:4 | `/api/season` table: position 2, 15 points, 5 for, 4 against |
| 16 | TEAM FAI style (19 rows) | e.g. possession 48.5% 5/6 (lg 50.0%), field tilt 44.4% 4/6, PPDA 11.5 5/6, xG for 0.85 5/6, xG against 1.36 4/6, shots against 14.34 5/6, set-piece xG 0.01 6/6, pressures 168.22 4/6 | `/style` values, ranks and league means, all 19 |
| 17 | TEAM FAI xG against reel | 48 moments, "4.54 xG", each shot with taker, minute, outcome | `/teams/cl_fairhaven/shots?side=against`: 48 shots, 4.54 xG, 4 goals (= table's 4 against) |
| 18 | RANK DF clearances | 24 defenders; top Gino Yilmaz 4.02 | `/rank`: ranked 24, #1 Gino Yilmaz 4.02 |
| 19 | CMP Oliveira, Hugo Delgado | Delgado: 0.08/31, 0.64/53, 1.61/42, 3.53/64, 4.18/92, 85.2%/36, 3.17/25, 3.53/81 | `/metrics` for pl_ash_10 |
| 20 | SCAT key_passes × sca MF | 18 players | `/scatter`: 30 points, 18 qualified (the default view shows qualified players) |
| 21 | RANK FW distance → leader's cell | Gino Reyes 10030 m per 90, 32581.3 in total, 97th; 10 per-match rows marked "no clip" | the 10 per-match values add up to 32581; 32581.3 × 90 / 10030 = 292.3 min |

**Radar with a missing percentile:**
- Noel Brennan has no save-% percentile: he is under the attempts minimum.
- `RDR Noel Brennan` draws 5 wedges and leaves Save % empty, never at the 0th, and the caption says so.
- `CMP Haruki Vargas, Noel Brennan` shows "–" for both in the table, and the caption explains the gap.

## Full evidence

- `/api/players/{id}/metrics?evidence=KEY` pages with `evidence_offset`. I paged the season's largest list
  (pl_eas_06 pass_pct, 347 items) in pages of 37: the pages joined together equal the one-call list exactly.
- `evidenceOf()` in `terminal.js` reads pages until `offset >= total`. The clips panel showed every moment in every
  list I opened (138, 48, 16, 10 and 1). There is no cap and no "first N".
- Input checks:
  - `evidence_offset` without `evidence=` gives 422.
  - Offsets past the end give an empty page, with the total kept.
  - A bad id gives 400, an unknown player 404, a bad `side` 422.
  - `test_metrics.py` covers all of these, plus shots against the engine, a club's shots adding up to its numbers, the
    heat map counting league fixtures only, screen paging, and no hidden ratings in the new reads.

## Rules

- **CSP:** the header is `script-src 'self'`; Playwright's string evaluation was blocked by it, which proves it was on.
  `terminal.js` and the Terminal markup have no `style=`, inline handlers or inline scripts. There were no page or CSP
  errors in any run.
- **esc():**
  - Every API value I traced into `innerHTML` goes through `esc()`: names in the radar, compare table, form-bar labels,
    clip titles and subtitles, `waitHtml`, and the alternative-name buttons.
  - The template strings that are not escaped are written with `textContent` (`out()`) or escaped where they are used.
  - The safeguard's payload test covered 25 places.
- **Storage:** only `Regista.store`. `terminal.js` has no `localStorage`, `sessionStorage` or `fetch(`.
- **Read only:** every request in every run was a GET.
- **No hidden ratings:** none in `terminal.js`, `terminal_api.py` or the new engine fields. The guard test includes the
  new endpoints.
- **No ids shown to people:** the panels show names, clubs, rounds and minutes.
- **The inventory:** the safeguard checked all 91 items. My runs touched Terminal only and found no regressions.
- **Tests:**
  - `python3 -m pytest -q` gave 837 passed and 13 deselected.
  - `python3 -m pytest -q -m slow` gave 13 passed. The engine is in the diff, so I ran it.

## Nits (none blocks sign-off)

1. **A physical number's clips panel shows its note twice.** "Physical numbers come from the 10 Hz motion record…"
   appears in the panel's header (`reel.note`) and again in the empty video area (`stopVideo('nolink')` falls back to
   the same note). "Play all" also shows for a list where no row has a clip.
2. **A physical total has no unit.** The subtitle reads "10030 m per 90 · 32581.3 in total". The total could say
   "32,581 m". This is part of the open "physical values show no unit" item.
3. **The README's API line** (`/api/players/{id}/metrics|form|similar|shots`) leaves out `/heatmap`.
   docs/architecture.md lists it.
4. **The second page of evidence is never fetched in this season.** No list has more than 500 items (the largest is
   347), so the client's next-page loop never runs. The API's paging is tested and the client loop is simple, so this
   is only a note.
5. **Open from earlier rounds, unchanged:**
   - an ambiguous name opens the player with the most minutes
   - clubs tied on a team metric get the engine's rank
   - Ctrl+K on a Mac is taken in text fields
   - Help has no focus trap
   - per-90 FORM bars read like counts ("Passes 27.00")
