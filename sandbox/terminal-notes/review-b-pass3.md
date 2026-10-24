# Review B, round 3: the Scout terminal through a scout's eyes

I reviewed 4215002 on `ux/sandbox`. I read all of `terminal.js` and the CSS it relies on, then used the page on
127.0.0.1:8174 in the desktop app's browser pane, with real keys and clicks, at 1440x900 and 375x812. Part A's local app
on :8040 served the clips. I fixed nothing. My test workspace was cleared from localStorage afterwards, the viewport
reset, the tab closed and the server stopped.

**Verdict: not signed off.** Nothing must be fixed. Two things should be. All four of my round 2 findings are fixed:

- RANK puts the ranked column first. At 375, `RANK DF aerial win %` shows Aerial duels won % as the first metric column.
- The grid tip sits beside the cell. Real arrow keys at 1440 left the next rows readable.
- During CMP, RDR draws the focus as a dashed outline, with a legend entry and "+ add".
- Most commands bring their chart into view. From the top at 1440, RANK, CMP, RDR, FORM, SIM, SHOT, HEAT, SCAT and
  TEAM each left their chart or table 100% in view. The two gaps are below.

The rest still holds:

- Selecting a player repaints every panel in 20-35 ms.
- Enter on a screener cell played its clip from :8040 (readyState 4, currentTime moving), and focus stayed on the cell.
- Contrast: dim text is at least 5.5:1, and numbers on the strongest yellow shading are at least 5.1:1.
- There is no sideways scroll at 375 (scrollWidth 375).
- No hidden-rating key (RATINGS, GK_RATINGS, PHYSICAL, `attributes`) is anywhere in terminal.json. I walked all 328 keys.
- The console stayed empty.

## Should fix

1. **The keyboard route into the screener grid is about 35 Tab presses long.** The grid uses one Tab stop (good). But
   Alt+1 (F1) focuses the panel heading, and from there it takes 34 Tabs to reach the first cell:
   - 4 panel buttons
   - 5 position buttons
   - filter, Qualified, Value, Pctl, Add column and Default columns
   - Player, Club and Min, then a sort button and an × for each of the 8 columns

   From the command line it takes about 57. The only short way is undocumented: Alt+4 then Shift+Tab, which works only
   while CLIP follows SCRN in the layout. HELP says "In the screener: arrow keys, Home/End, Enter" but not how to get
   there. This matters because RANK, then arrowing down the ranking, is the core keyboard path. Fix: have F1/Alt+1 focus
   the grid's active cell (or each F-key focus its panel's main control), or make Enter on a panel heading move into its
   body. Either way, say it in HELP.

2. **Two commands can still leave their subject off screen.**
   - **At 375, the in-view check runs before the output line grows.** On a phone the output line is in the page flow.
     `showPanel` measures first, then `out()` writes a 3-4 line message and pushes the panel down. Seen twice:
     - Real typing at 375: `RANK DF aerial` → choose Aerial duels won % → Enter. The page stayed at scrollY 0 with the
       table top at 738 of 812 px. Only the header showed, and no ranked row.
     - Scripted from the top: `RANK GK save` left the table 64% "in view", with its first row at 736 px.

     Fix: write the output line before `showPanel`, or test the first rows rather than 60% of the table box.
   - **At 1440, a name (`TOURE <GO>`, the headline command) checks only `.tx-card`.** That is a 43 px strip at 774-817
     px. It passes, so nothing scrolls, and the scout sees the card at the bottom edge. The player's numbers ("Best vs
     forwards") and SIM stay below the fold. Fix: target the card plus the Best table, so the PLYR panel top goes under
     the bar.

## Nits (not blocking)

- **Command line labels.** The command line's accessible name is its label "CMD>", so a screen reader reads "CMD greater
  than, combobox". Give it `aria-label="Command line"`. The `<GO>` button reads as "less than GO greater than".
- **Toolbar role.** `#txKeys` has `role="toolbar"` but no arrow-key navigation (the 10 F-keys are 10 Tab stops). Drop
  the role, or add a roving tabindex.
- **Typing straight after Cmd+K.** On the terminal itself, Cmd+K focuses after 30 ms, and characters typed in that gap
  are lost. All 5 were lost in a scripted test. Focus at once when the section is already showing. Cmd+K also jumps from
  the Player view (Femi's own dashboard) into Maya's terminal.
- **The grid tip.** Arrowing right, the compact tip sits right of the cell and covers the next 2-3 columns of about 4
  rows. Better than round 2. Placing it above the header row while in the grid would hide nothing.
- **A small screener.** At 1440x900 the screener shows 9 of 24 rows (box height `100vh - 620px`), and its controls and
  caption take 155 px. This was deliberate, to keep CLIP on the first screen. On an XL panel the box could grow.
- **SHOT focus.** On the shot map, a focused shot and the playing shot look the same (both blue strokes).
- **Still open from earlier rounds:**
  - Tab runs top-level player and club suggestions at once.
  - Up then Down loses the draft you were typing.
  - `aria-label` on the noisy-mark span, which has no role.
  - Help is a non-modal dialog without a focus trap.
  - "SYNTHETIC DATA Synthetic data: …" says it twice.
  - "Qualified (100.5+ min)" shows a decimal.
  - The FW default column is noisy (Non-penalty goals ≈).
  - Panel buttons and chips under 24 px at 375.
  - Namesakes open by most minutes: `ustin` and `CMP toure ustinov` give Otis (DF), not Amari (FW).
  - CMP offers swaps only for the first ambiguous name.
  - The screener does not follow a selection across positions.
  - No units (km/h, m) in RANK lines and cells.
  - At 375 the command bar scrolls away after every command, so the next command needs a scroll back up.
