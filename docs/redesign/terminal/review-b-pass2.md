# Review B, round 2: the Terminal port after the round-1 fixes

I reviewed `ux/terminal` at e4c656c (`git diff main...HEAD`), with the same lens as round 1:

- fidelity to the approved sandbox;
- keyboard-only use, focus and screen-reader labels;
- 1440 and 375 px with no sideways scroll;
- consistency with the rest of `/scout`.

This round looked mainly at the three round-1 fixes (commit e4c656c) and at whether they broke anything.

How I checked:

- I read the fix diff in `terminal.js`, `terminal_api.py` and `season/profiles.py`, plus `Regista.store` in
  `shared/regista.js`.
- I ran the app offline on 127.0.0.1:8184 (`REGISTA_DOTENV=`) and the sandbox on :8185, in my own browser tabs. I used
  real key presses where keys mattered.
- I fixed nothing.
- Afterwards I removed my Terminal workspace, reset the viewport, closed my tabs and stopped both servers.
- Nothing touched the live app or Azure. The only "Reset this demo" click was in my own local tab.

**Verdict: signed off.** Nothing must or should be fixed. The nits are below.

## The three fixes, checked

### League-only heat map

- **The endpoint.** `GET /api/players/pl_bro_09/heatmap` returns 200 with the card, `grid`, `total` 407 and the scope
  "Regista League fixtures (synthetic)". There are no hidden ratings in its keys.
  - A malformed id gives 400 and an unknown player gives 404, the same as `/shots`.
- **The command.** `HEAT TOURE` (typed, then Enter) gives "HEAT Femi Toure · Brookfield Rovers.", the same line as the
  sandbox.
- **The caption** now reads "407 on-ball actions in league matches this season (…)". The rest of the panel is the
  sandbox's: the same svg, header context and stat buttons.
- **The code.** `Season.league_grids` is copied after the fixture loop and before `_add_claimed`, so claims and uploads
  cannot reach it. Every build path (`load_season`, `refresh`) goes through `_aggregate`, so the grid is always filled.
- **Test.** `test_the_heat_map_counts_league_fixtures_only` covers the upload case.

### Reset this demo in another tab

- **What I did:**
  - Tab A ran `CMP Toure Nakamura` and other commands.
  - Tab B (`/scout#settings`) pressed Reset this demo.
- **What tab A showed:**
  - Storage for `terminal` was `null`.
  - The CMP bar showed "CMP none".
  - Up arrow in the command line gave an empty line, so the history was gone too.
- **The handler.** On a full clear (`key === null`), dropping the in-memory copy is right. `Regista.store.get` falls
  back to `memory`, so without it the old workspaces would come back.

### CMP with no player

| Command | Output line |
|---|---|
| `CMP Toure Nakamura` | the success line |
| then `CMP vs` | "CMP needs two or three players: CMP <player> <player> [<player>]." |
| `CMP Toure zzzq` | "No player called "zzzq"." |

No console errors during the session.

## Regressions: none found

- **The keyboard route (fix 3):**
  - Cmd+K, then `RANK MF key passes`, then Enter gave "RANK MF · Key passes: 18 midfielders; top Pavel Petrov 2.12.
    Alt+1 enters the table."
  - Alt+1 focused the leader's cell. It is a button with tabindex 0 and the name "Pavel Petrov, Key passes 2.12, 97th
    percentile. Open its moments".
  - Down, then Enter, opened all 7 of Kenan Petrov's key-pass moments in CLIP, and focus stayed on his cell.
- **Subjects in view at 375 px (fix 4).** I ran 10 commands, each from the top of the page: TOURE, HEAT, SHOT, FORM,
  SIM, TEAM, SCAT, CMP, RDR and RANK.
  - Each one's chart or table ended on screen. RANK's ranked rows were already in view, so it did not scroll.
  - `scrollWidth` stayed at 375 throughout.
  - The hidden pane does not run smooth scrolling, so as in earlier rounds I swapped `window.scrollTo` for an instant
    scroll.
- **1440 px.** `scrollWidth` equals 1440, and the layout matches the sandbox as in round 1.
- **Suite.**
  - `python3 -m pytest -q`: 836 passed, 13 deselected.
  - `python3 -m pytest -q -m slow`: 13 passed. The fix touches the season engine, so I ran these.

## Nits (not blocking)

1. **The heat map's svg label** still says "Heat map: N on-ball actions, attacking left to right". The visible caption
   now says "in league matches"; the label could say it too.
2. **Still open from round 1.** None of these was in scope for round 1's fixes:
   - Alt+1 pressed while a RANK column is still loading leaves focus on a cell that is not the grid's Tab stop.
   - `#txKeys` and `#txSel` have `aria-label` without `role="group"`.
   - The tables have no caption or `aria-label`.
   - A stale tooltip stays at its old position after a resize.
   - Help has no focus trap.
   - Namesakes open by most minutes.
   - Physical values show no units.
3. **Ctrl+K on a Mac** is still Zaid's call, as the safeguard asked.
