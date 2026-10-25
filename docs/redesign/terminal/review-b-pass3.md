# Review B, round 3: the Terminal port after the round-2 fix

I reviewed `ux/terminal` at 260fcc3 (`git diff main...HEAD`). My lens was the same as in rounds 1 and 2:

- fidelity to the approved sandbox;
- keyboard-only use, focus and screen-reader labels;
- 1440 and 375 px with no sideways scroll;
- consistency with the rest of `/scout`.

This round looked mainly at the round-2 fix, `panelsSettled()` (commit 260fcc3), and at what it changed.

How I checked:

- I read the fix diff in `terminal.js` and the command runner around it (`run`, `team`, `cmdCmp`, `cmdScat`,
  `select`, `selectReady`, `out`, `showPanel`).
- I ran the app offline on 127.0.0.1:8184 (`REGISTA_DOTENV=`) in my own browser tab.
  - The pane was hidden, so the page got no animation frames. As in fixes-round2.md, I swapped
    `requestAnimationFrame` for 16 ms timers straight after load, and `window.scrollTo` for an instant scroll.
- I fixed nothing.
- Afterwards I removed my Terminal workspace, reset the viewport, closed my tab and stopped the servers.
- Nothing touched the live app or Azure.

**Verdict: not signed off.** One finding should be fixed. Nothing must be fixed.

## The round-2 fix works

At 375 x 812, each command ran first for its player:

| Command | Chart top to bottom (px) | Visible |
|---|---|---|
| HEAT Kenan Kowalski | 121–337 | yes |
| SHOT Yusuf Tanaka | 121–481 | yes |
| FORM Leon Whitfield | 82–282 | yes |
| RDR Pavel Petrov | 102–391 | yes |
| CMP Kowalski Tanaka (radar) | 102–391 | yes |
| TEAM FAI | 40 to the panel's end | yes |
| SIM Zane Weber (similar list) | 472–687 | yes |

- During HEAT, I sampled the chart's position every 250 ms for 2.5 s. It stayed at 121–337 throughout, so nothing
  pushed it down later.
- `scrollWidth` stayed at 375.
- At 1440 x 900, HEAT Haruki Zidane (298–544), SHOT Kenan Nakamura (321–681), TEAM DUN (240–834) and SCAT shots xa
  (342–592) were all wholly in view. `scrollWidth` was 1440.
- Real keys still work:
  - Cmd+K and typing land in the command line.
  - An ambiguous `RANK DF tackles` offers the three tackle metrics as buttons.
  - Alt+1 enters the screener grid on the leader's cell; Down moves to rank 2. The cell's name reads "Amari Ustinov,
    Shots 4.49, 92nd percentile. Open its moments".
- Suite: `python3 -m pytest -q` gave 837 passed, 13 deselected. The fix does not touch the engine, so I did not run
  `-m slow`.

## Should fix

### An older command finishes after a newer one: it replaces the newer output line and scrolls away

**Where:** `src/regista/static/scout/terminal.js`, the command runner.

- `run()` panel commands await `selectReady` and then `panelsSettled()`. So do a bare player name, `cmdCmp` and
  `cmdScat`, and `team()` (async since 260fcc3).
- After those awaits, each one calls `out(...)` and `showPanel(..., true)` unconditionally.
- Nothing checks whether a later command, or a click that selects a player, has happened in the meantime.

The sandbox read a local JSON file, so its commands finished at once. The port's commands wait for the network, and
round 2 made that wait longer: a cold player waits for every shown panel's data, bounded at 6 s.

**Reproduced (local server, so the window was only about 100–250 ms):**

1. **A newer command is undone.**
   - I ran `HEAT Caio Sorensen` (a player not loaded yet), then `RANK FW shots` 60 ms later.
   - At 114 ms the line read "RANK FW · Shots: 18 forwards; top Femi Toure 6.23. Alt+1 enters the table." and the page
     scrolled to the screener (y 493).
   - At 119 ms the stale HEAT replaced the line with "HEAT Caio Sorensen · Brookfield Rovers." and scrolled to the heat
     map (y 3675). The screener was 3194 px above the screen.
   - The person typed RANK last but ends up looking at a heat map. Its "Alt+1 enters the table" hint is gone.
2. **The output line names a different player from the panels.**
   - At 1440 px I ran `SHOT Sami Ibarra`, then clicked Gino Reyes in the screener 40 ms later.
   - The click selected Gino Reyes. FOCUS shows him, and the shot panel shows his numbers: "ASH · 14", 14 shots.
   - Then the stale SHOT wrote "SHOT Sami Ibarra: 6 shots, 0 goals. Each shot plays its clip." and scrolled to that
     panel.
   - The line is the `role="status"` live region, so a screen reader announces the wrong player as well.
3. A third run gave the same result: `HEAT Otis Nakamura`, then `RANK FW npxg` 30 ms later. RANK's line appeared at
   39 ms, and HEAT replaced it and scrolled at 47 ms.

**Why it matters for the demo:** on the live app every cold player means several requests over the network (card,
similar players, form, shots, heat map), so the window is longer than on localhost. Typing the next command while
"loading…" shows is exactly how a Bloomberg-style command line gets used. Clicking a run button in the output line,
or a screener cell, does the same.

**Suggested fix (small):**

- Keep a counter: `run()` and `select()` (and the click actions that select or scroll) increment it.
- After each await in a command (`selectReady`, `settle`, `panelsSettled`), compare the counter with the value the
  command started with. If it has changed, return without calling `out()` or `showPanel(…, true)`.
- Add a test beside `test_fix_4_commands_wait_for_every_shown_panel_before_they_scroll`, and check in the browser
  with the two sequences above.

## Nits (not blocking)

1. **TEAM shows no "loading…" line.** `team()` now waits for `panelsSettled()` before its first `out()`. For about
   100 ms (longer on a cold club over the network), the previous command's line stays on screen and seems to answer
   TEAM. The panel commands, names and SCAT say "loading…" first.
2. **Still open from rounds 1 and 2, unchanged:**
   - The heat map's svg label lacks "in league matches".
   - Alt+1 during a loading RANK column.
   - `#txKeys` and `#txSel` have no `role="group"`.
   - The tables have no caption.
   - A tooltip stays where it was after a resize.
   - Help has no focus trap.
   - A name shared by two players opens the one with the most minutes.
   - Physical values show no units.
   - Ctrl+K on a Mac is Zaid's call.
