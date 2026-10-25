# Scout terminal: fixes for review round 2

Branch `ux/terminal`. Review A, round 2 (docs/redesign/terminal/review-a-pass2.md) had one finding. It is fixed and has a
test. Review B, round 2 signed off with nits only.

## At 375 px, HEAT or SHOT run first for a player left the chart off screen

**Cause.** As the reviewer found: a panel command waited only for the data of its own panel (and the player's numbers)
before it scrolled. At phone width the panels are stacked. Form sits above Shot, and Form and Shot sit above Heat. Those
panels only start loading when the player is selected. Their data arrived after the scroll, each "Loading…" line became
a chart 400 to 500 px taller, and the chart the command was about got pushed below the fold.

**Fix (src/regista/static/scout/terminal.js).**
- `want()` now records which panels asked for each request (`c.panels`).
- New `panelsSettled(ms = 6000)` waits two frames, so repaints already asked for get drawn and can start their own
  requests. It then waits for every request still loading that a shown panel asked for, plus the screener's pending
  columns while the screener is shown, and repeats until nothing is left. It gives up after 6 s, so a slow or failed
  request cannot block a command. The frame wait falls back to a 100 ms timer, because a hidden page gets no animation
  frames.
- Each command that scrolls to its subject now calls `await panelsSettled()` after selecting the player and before it
  writes its output line and scrolls. That covers the panel commands (SIM, SHOT, FORM, HEAT, RDR, PLYR), a bare player
  name, CMP, SCAT and TEAM (`team()` is now async). RANK already waits for its column, and the screener is the first
  panel, so RANK is unchanged.
- The output line still comes before the scroll, as fix 4 requires.

**Test.** `test_fix_4_commands_wait_for_every_shown_panel_before_they_scroll` (tests/test_scout_terminal.py). It checks
that `want()` records the panels, that `panelsSettled` waits on the shown panels' requests, the screener's columns and
the frames, and that every scrolling command awaits it after `selectReady` and before its `showPanel`.

**Checked in a browser** (local app with `REGISTA_DOTENV=`, port 8765). Each command ran as the first command on a fresh
page load, so nothing was cached. Scrolling was instant (reduced motion). The browser pane was hidden, so the harness
swapped animation frames for 16 ms timers before the Terminal loaded. I read the subject's position for 2 s after the
command finished. Viewport 375 x 812:

| Command (first for that player) | Chart top to bottom (px) | On screen |
|---|---|---|
| HEAT Bruno Lindqvist | 121–337 | 100% |
| HEAT Otis Nakamura | 121–337 | 100% |
| HEAT Gino Yilmaz | 121–337 | 100% |
| HEAT Amari Ustinov | 121–337 | 100% |
| SHOT Amari Ustinov | 121–481 | 100% (before the fix: 590–950, 62%, as the reviewer measured) |
| SHOT Bruno Lindqvist | 121–481 | 100% |
| FORM Bruno Lindqvist | 83–283 | 100% |
| SIM Otis Nakamura (player card) | 40–787 | 100% |
| RDR Gino Yilmaz | 102–391 | 100% |
| CMP Lindqvist Ustinov (radar) | 103–391 | 100% |
| SCAT npxg xa FW | 142–392 | 100% |
| TEAM EAS | 107–774 | 100% |
| Gino Yilmaz (card) | 40–768 | 100% |

`scrollWidth` stayed 375 throughout. At 1440 x 900, HEAT Bruno Lindqvist (298–544), SHOT Amari Ustinov (321–681) and
TEAM CAL (308–784) were all wholly in view. No console errors.

To show the harness catches the bug, I swapped the previous terminal.js back in for one run: SHOT Amari Ustinov landed at
590–950 (62% visible), the same as the reviewer's numbers. Then I put the fix back.

**Not seen in the app:** with the pane hidden, the browser gives the page no animation frames. Panels stay "Loading…"
until the page is visible again, which is how browsers treat background tabs. The harness worked around this by
swapping frames for timers before the Terminal loaded. Visible pages are not affected.

**Suite.** `python3 -m pytest -q`: 837 passed, 13 deselected. I did not touch the engine, so I did not run `-m slow`.
