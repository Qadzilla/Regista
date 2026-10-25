# Review B, round 1: the Terminal port, through a scout's eyes

I reviewed `ux/terminal` at 7faffb9 (`git diff main...HEAD`). My lens was:

- fidelity to the approved sandbox;
- keyboard-only use, focus, screen-reader labels and contrast;
- 1440 and 375 px with no sideways scroll;
- consistency with the rest of `/scout`.

How I checked:

- I read all of `terminal.js` and diffed `terminal.css` and the markup against the sandbox reference
  (`.claude/worktrees/sandbox-ref/sandbox`).
- I ran the app offline on 127.0.0.1:8184 (`REGISTA_DOTENV=`) and served the sandbox on :8185, side by side in my own
  browser tabs, using real key presses where keys mattered.
- I fixed nothing. Afterwards I cleared my test workspace, reset both viewports, closed both tabs and stopped both
  servers. Nothing touched the live app or Azure.

**Verdict: signed off.** Nothing must or should be fixed. Six nits follow.

## Fidelity to the sandbox

- **Same look.** At 1440x900 the two pages match panel for panel:
  - the command bar, the F-key row, the synthetic strip, workspaces and the focus/CMP bar;
  - the screener with the clips beside it, then PLYR, RDR and FORM.
- **Same styles.** `terminal.css` is the sandbox's rules re-scoped from `#scout .tx` to `.pf .tx`. The sticky offset
  now follows `--top-h`.
- **The markup** is the sandbox's, with the reviewers' label fixes ("Command line", "Go"). The `role="toolbar"` that had
  no arrow keys is gone. The `.sr` "Terminal" h1 matches the sandbox; the other sections show a visible title.
- **Commands.** The same command table and the same nine panels, in the same F-key order.
- **RANK** still puts the ranked column first and prepends it to the columns, as in the sandbox.
- **Two visible changes, both correct:**
  - "Qualified (101+ min)" no longer has a decimal.
  - "Ready: 102 players" (the sandbox said 108). The 6 unplayed squad players are not API rows, and TEAM lists them
    separately at 0′.

## Keyboard only, end to end

All of these used real key presses at 1440 unless noted.

- **Cmd+K** from the page puts focus in the line, and typing lands there.
- **The screener route (fix 3):**
  - `RANK DF aerial win` then Enter gave "RANK DF · Aerial duels won %: 24 defenders; top Caio Sorensen 100.0%. Alt+1
    enters the table."
  - Alt+1 put focus on the leader's ranked number (tabindex 0). The compact tip showed "(9 of 9) · 98th pctl vs
    defenders".
  - Down moved a row. Enter opened all 9 moments in CLIP, and focus stayed on the cell.
  - Enter on the F1 button does the same as Alt+1.
  - Command line to grid is now 1 key. Plain Tab is still about 52 stops, but Alt+1, F1, the RANK line, the screener
    caption and HELP all name the short route.
- **HELP.** Enter focuses the dialog heading, Tab reaches "Close help", and Escape closes it with focus back in the
  command line ("Help closed.").
- **FORM bar.** Enter on round 7's bar kept focus on the bar. CLIP said "0 in this match" and "No
  moments behind this number in this match" (fix 1's wording).
- **Focus rings.** The CSS gives every button, input, select and `[tabindex]` in `.tx` a 2 px amber focus ring; I saw it on the cells and the help heading.
- **Panel headings** take focus only from the F-keys and Alt+digit (tabindex -1), so they add no Tab stops.

## Subjects in view (fix 4)

- **At 1440:** I scripted 10 commands from the top of the page. Each one's subject ended fully below the sticky bar
  and above 900 px:
  - TOURE ("Best vs" table at 433-577)
  - RANK (third row at 532-556)
  - FORM, CMP, SHOT, TEAM, SCAT and HEAT
  - SIM (609-875)
  - RDR
- **At 375:** TOURE, FORM, CMP, SHOT, TEAM, SCAT, SIM and HEAT all ended in view.
  - `RANK GK save` is ambiguous on purpose and offers three choices instead.
  - `scrollWidth` was 375. Wide tables scroll inside their panels.
  - The hidden pane does not run smooth scrolling, so these runs replaced it with instant scrolling, as the safeguard
    did.

## Radar (fix 2), looked at

`CMP Femi Toure, Otis Nakamura, Jonah Eriksen` draws:

- one polygon for Toure;
- one broken polyline for Nakamura, with no point at the centre;
- no outline for Eriksen, with the note "Jonah Eriksen has no outline: goalkeepers are not scored on the FW template.
  The table has the values." The caption explains the gaps.

## Contrast and labels

Contrast on the panel backgrounds:

- Dim text (`#8a93a6`), at 10.5-12.5 px, measures 5.5:1 to 6.4:1. This covers captions, F-key subtitles, ranks, ×
  buttons, workspace buttons and panel context.
- Axis labels measure 16.9:1.

Labels for screen readers:

- **Command line:** combobox "Command line", listbox "Suggestions" and `aria-activedescendant`.
- **Output line:** a polite status.
- **Panels:** regions named by their headings.
- **Screener number cells:** they read the player, the metric, the value, the percentile (or why there is none) and
  "Open its moments".
- **Noisy metrics:** the noisy mark reads ", noisy".

## Consistency with /scout and the left panel

- Terminal sits after Find players in both left panels (`/scout` and `/players/{id}`), with `aria-current`.
- At 375 the section row scrolls so Terminal shows.
- Leaving the section pauses the clip and hides the tip.
- No other `/scout` script binds keys (only `profile-view.js`'s Escape in its own evidence box), so the Terminal's keys
  clash with nothing.
- The tests touching this branch passed: `tests/test_scout_terminal.py`, `test_scout_page.py`, `test_metrics.py` and
  `test_access.py`, 113 in all.

## Nits (not blocking)

1. **Alt+1 while a RANK column is still loading.** In my first run I pressed Alt+1 straight after Enter, during "loading
   the column…". Focus went to the old active cell, and Down moved it to the next row (Elias Bakker).
   - Then the column landed: `finish()` moved the active cell to the leader, and the repaint kept focus on Bakker with
     `tabindex="-1"`.
   - Arrow keys still work from there, and a second Alt+1 lands on the leader. But for a moment the focused cell is not
     the grid's Tab stop.
   - Possible fix: move focus along with `scrAct` in `finish()` when focus is in the grid.
2. **Names on generic divs.** `#txKeys` ("Panels") and `#txSel` ("Selected players") carry `aria-label` on plain divs,
   which screen readers ignore. Now that the toolbar role is gone, `role="group"` would make both names count.
3. **Unnamed tables.** The tables (screener, Best vs, compare, consistency, team style) have no caption or
   `aria-label`. Their panel regions are named, so this is minor.
4. **A stale tooltip after a resize.** A tip open when the viewport shrinks stays at its old fixed position, off screen
   (seen going from 1440 to 375 with focus on a grid cell). It causes no page scroll. Hiding the tip on `resize` would
   tidy this.
5. **Still open from the sandbox reviews:**
   - Help is a non-modal dialog without a focus trap.
   - A focused shot and the playing shot look the same on the shot map.
   - At 375 the command bar scrolls away.
   - Many buttons are under 24 px at 375.
   - Namesakes open by most minutes, so `CMP toure ustinov` and `RDR USTINOV` give Otis (DF), not Amari (FW).
   - Physical values show no units.
6. **Ctrl+K on a Mac.** I agree with the safeguard's open question. Cmd/Ctrl+K as specified takes Ctrl+K from every
   `/scout` text field, and on a Mac that is "delete to end of line". Taking only Cmd+K on a Mac would keep it. This is
   Zaid's call.
