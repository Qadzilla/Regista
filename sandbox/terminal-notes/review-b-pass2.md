# Review B, round 2: the Scout terminal through a scout's eyes

I reviewed b0d9027 on `ux/sandbox`. I read `terminal.js`, `terminal.css`, the Terminal markup and the round 1 fixes. Then I
used the page served on 127.0.0.1:8174 in the desktop app's browser pane, with real keys and clicks, at 1440x900 and
375x812. Part A's local app on :8040 served the clips. I fixed nothing.

**Verdict: not signed off.** Nothing must be fixed, but four things should be. All 13 round 1 findings are fixed, and I
re-checked the ones in my lens:

- Focus no longer falls to `<body>`. I tried real Enter or Space on WS 2 and WS 1, a similar player (focus goes to the
  PLYR heading), "+ add", a screener position, the radar template, a sort header and a PLYR run button.
- A clicked screener number plays in view at 1440. The video sat at 381-590 px with no scroll, played (readyState 4),
  and keyboard focus stayed on the cell.
- CLIP shares the first screen with the screener.
- The section has an h1, F-keys no longer claim `aria-pressed`, and chart text is at least 10 px.

The command line still feels right:

- Tab completes CMP's names without running the command, and Enter (`<GO>`) runs it.
- Arrow keys choose between namesakes.
- Focus stays in the command line after a command.
- Selecting a player repaints every panel in 26-43 ms.

There is no sideways scroll at 375 (scrollWidth 375). Clips play in view on a phone. No hidden-rating key appears
anywhere in terminal.json (I walked every key). The console stayed empty.

## Should fix

1. **Most commands open their panel mostly below the fold.** `showPanel` scrolls only when the panel's top is above the
   bar or below `innerHeight - 80`. That is the flaw round 1 fixed for CLIP, still present for every other panel. At
   1440x900 from the top of the page, after each command, this much of the target panel was in view:

   | Command | Panel top | Panel in view | What the scout sees |
   |---|---|---|---|
   | CMP | 743 px | 24% | the RDR header and legend, not the chart |
   | RDR | 718 px | 26% | the same |
   | FORM | 741 px | 29% | the same |
   | SIM | | 53% | about half the panel |

   SHOT, HEAT, SCAT and TEAM start far enough down that they do scroll, which is correct. Fix: test the panel's body or
   chart with `inView(…, 0.6)`, as openReel now does.

2. **RANK can sort by a column the scout cannot see.** RANK puts a new metric first, but leaves a metric that is already
   a column where it is, and never scrolls to it. At 1440, `RANK FW progressive_passes_received` sorts by a header at
   1069-1159 px, while the table's scroll box ends at 1017 px (scrollLeft 0). The rows come out in an order no visible
   column explains. At 375 only one metric column fits, so this happens almost every time. After `RANK FW npxg` the
   phone showed non-penalty goals reading 0.67, 0.60, 0.31, 0.00, 0.32. Fix: move the ranked column first, or scroll
   its header into view.

3. **In the screener, the keyboard tooltip covers the rows you arrow into.** Each arrow key moves focus to a cell and
   opens the full definition tooltip (about 340x170 px) right under it. It hides the next five or six rows and the
   neighbouring columns, which are exactly what a keyboard scout reads next. Escape hides it, but the next arrow brings
   it back. This was a nit in round 1. I raise it because keyboard use of the screener is the terminal's core path.
   Fix options:
   - In the grid, show the tooltip beside the cell, or above it when moving down.
   - Or show it only on a column header, or after a pause.
   - The value is already in the cell's aria-label, and aria-describedby can stay.

4. **While a comparison is on, RDR ignores the focus player and says nothing.** With 2 or 3 players in CMP, the radar
   draws only them (`players = S.compare.length >= 2 ? S.compare : [f]`). Selecting someone in the screener updates
   PLYR, FORM, SHOT, HEAT and TEAM, but the radar does not change. Its only hint is the panel's context text, "CMP". I
   saw this with Haruki Fontaine as the focus while the radar showed Toure and both Ustinovs. Fix: overlay the focus
   player as a dashed outline. Or add one line in the panel: "Comparing 3; Fontaine is not on the radar · + add".

## Nits (not blocking)

- Cmd+K on the terminal itself focuses the line after a 30 ms timeout. In a real-key test, the first characters typed
  straight after Cmd+K were lost. Focus at once when the section is already showing.
- Still open from round 1:
  - Tab runs top-level player and club suggestions at once.
  - Pressing Up then Down loses the draft you were typing.
  - `aria-label` on the noisy-mark span, and on the selection-strip div, which has no role.
  - Help is a dialog without a focus trap.
  - "SYNTHETIC DATA Synthetic data: …" says it twice.
  - "Qualified (100.5+ min)" shows a decimal.
  - The FW default sort is non-penalty goals, a metric marked noisy.
  - At 375, 367 of 392 visible controls are under 24 px tall. Most are dense table cells, but the panel buttons, × and
    chips are touch targets.
- Inputs use 15 px (command line) and 12.5 px (filter, selects), so iOS Safari zooms in on focus. The rest of the sandbox
  does the same (14-15 px inputs), so this is a sandbox-wide choice.
- Still open from the checker: namesakes open by most minutes (USTINOV opens Otis, a DF), CMP offers swaps only for the
  first ambiguous name, the screener does not follow a selection across positions, and RANK lines and cells show no
  units (km/h, m).
