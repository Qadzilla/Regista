# Review B, round 1: the Scout terminal through a scout's eyes

Reviewed at 39a15c2 on `ux/sandbox`. I read `terminal.js`, `terminal.css`, the Terminal markup in `index.html` and the
builder's and checker's notes. I used the page served on 127.0.0.1:8174 in the desktop app's browser pane, with real
keys and clicks, at 1440x900 and 375x812. Part A's local app on :8040 was serving clips. Nothing was fixed.

**Verdict: not signed off.** Two problems must be fixed and five should be. The command line itself is strong: the
mnemonics, `<GO>`, autocomplete in every slot, history and Cmd+K from another section all work with real keys. So do
roving focus in the screener and percentile shading on dense tabular numbers. A repaint takes about 33 ms.

## Must fix

1. **Keyboard focus falls to `<body>` after most controls repaint.** `paint()` keeps focus only for elements that
   have a `data-fid` and still exist after the repaint. `renderSel()` and `paintMeta()` keep none. I reproduced each
   of these with a real Enter or Space, and each time `document.activeElement` became `BODY`:
   - a similar player in PLYR (the `sim-<id>` button disappears once that player becomes the focus);
   - `+ add <name>` in the selection strip;
   - the workspace buttons WS 1, 2 and 3;
   - the screener's position filter (ALL, GK, DF, MF, FW);
   - TEAM's club switcher.

   The code shows the same gap for Reset, the CMP chip name, its × and Clear, Value/Pctl, Default columns, a column's ×,
   the radar's template switch and the scatter's position filter. None of these has a `data-fid`, or the element is
   removed. A keyboard-only scout must tab back from the top of the page after every one of them, so keyboard use
   does not work end to end.

2. **At 1440x900, Regista's edge plays off screen.** In the default layout the screener fills the first viewport
   (panel at 285 to 823 px). CLIP's header starts at 831 px, and the video sits at 927 to 1136 px. A real click on a
   screener number started the clip (readyState 4, playing) but left `scrollY` at 0, so nothing could be seen.
   `openReel` only scrolls when the panel's *top* is below `innerHeight - 60`, and here 831 < 840. It should test
   whether the video is visible. Better still, a default layout could put CLIP beside the screener (see should fix 1).

## Should fix

1. **The default workspace is 2,792 px tall: about three screens at 1440x900.** Only one panel (SCRN) is in the first
   viewport. PLYR, RDR and CLIP start at 831 px, SHOT, HEAT and FORM at 1533 px, and SCAT and TEAM at 2065 px.
   Selecting a player "updates the linked panels", but none of them is visible when it happens, so linking does not
   *feel* linked. A Bloomberg-grade first screen would show the screener (M, shorter) beside PLYR or RDR and CLIP.
2. **The Terminal section has no `h1`.** Every other Scout section has one (Maya Lindqvist, Find players, Shortlist,
   Reports and so on). In Terminal the first heading is a panel `h2`, "F1 SCRN Screener". Screen-reader users who
   navigate by heading find no section title. A visually hidden `<h1>Terminal</h1>` would fix it and match the rest
   of the sandbox.
3. **The F-keys use `aria-pressed`, but pressing one never un-presses it.** `fkey` always shows the panel and focuses
   it, so a screen reader announces a toggle that does not toggle. Either make F-keys toggle the panel (Bloomberg
   style) or drop `aria-pressed` and put "hidden" in the label.
4. **Contrast below 4.5:1 on controls and labels:**
   - a hidden panel's F-key: `opacity: .6` on the dim colour gives 2.9:1;
   - the command-line placeholder (`#5f6779` on `#090b10`): 3.5:1;
   - the FORM chart's opponent labels (`.tx-axl.dim`): 3.3:1;
   - the pizza's black value text on style-marker wedges (opacity .45): 2.6 to 2.9:1. The values are repeated in
     the table below.
5. **Chart text is too small to read.** FORM's axis and value labels render at 8.0 px at 1440, smaller at 375, and
   the radar's axis labels at 9.4 px. The dense tables use 11 to 12.5 px, which reads well; the charts should be at
   least 10 px.

## Nits

- **The add-column select may add columns while you arrow through it.** On Windows Chrome, arrow keys on a closed
  `<select>` fire `change`, so each Down may add a column. I did not test this; macOS fires `change` only on close.
- **Tab runs some suggestions at once.** Accepting a top-level player or club suggestion with Tab runs it. Bloomberg
  users expect Tab to complete and Enter (`<GO>`) to run.
- **Up-arrow history drops what you were typing.** Coming back down with Down leaves an empty line instead of the draft.
- **`aria-label` on generic elements is not reliably announced.** This covers the noisy mark `≈` (a span) and the
  "Selected players" strip (a div). Use visually hidden text for the noisy mark and `role="group"` for the strip.
- **The keyboard tooltip covers the screener's next rows.** It opens below each cell as you arrow down.
- **Help is a `role="dialog"` that neither traps focus nor closes when focus leaves it.**
- **The size and move buttons do nothing useful on phones.** At 375 px every panel spans full width, so S, M and L
  look the same.
- **Touch targets are small at 375.** Some are 16 to 22 px tall (shared-strength chips, ×, panel buttons), under the
  24 px minimum.
- **"SYNTHETIC DATA Synthetic data: …" says it twice in one line.** "SYNTHETIC DATA Invented players and clubs…"
  reads cleaner.
- **The qualified label reads "Qualified (100.5+ min)".** A minutes threshold reads better as an integer.
- **The default FW sort column, non-penalty goals, is itself marked noisy (r −0.02).** A scout's first screen opens
  sorted on a number the page says cannot separate players.
- **Alt+1 to Alt+9 can collide with browser tab switching on Linux.**
- **The checker's open items still apply:** the namesake choice, swaps for the first ambiguous name only, the screener
  not following a selection across positions, and units missing in RANK output and cells.

## What works well (checked, not assumed)

- **Cmd+K:** from `#scout/shortlist` it routed to the Terminal and focused the input.
- **Autocomplete:** `cmp tou` offered the seven Toures, Tab took the first, and `ustinov` offered four Ustinovs.
  Enter ran it, and the output line offered the other namesakes as one-click swaps.
- **Screener keyboard:** one tab stop with roving focus and arrow keys; percentile shading; sort with `aria-sort`;
  cell labels with name, metric, value and percentile. White on the strongest shading is 4.6:1.
- **Tooltips:** hovering shows the definition, rule, source, unit, the noisy r and the player's value; focus on value
  buttons and headers shows the same through `aria-describedby`.
- **Phone:** at 375 there is no sideways page scroll (scrollWidth 375), and the screener scrolls inside its panel.
- **Hidden ratings:** `terminal.json` has no rating keys (a key walk found only metric keys such as
  `accelerations_high` and `skill_moves`).
- **Focus rings:** amber `:focus-visible` rings on buttons, inputs and selects; SVG shots and form bars show focus
  strokes.

Housekeeping: the 8174 server is stopped. My tab is closed and its `regista.terminal*` localStorage keys are removed.
Another agent navigated my first tab (tab-25) to :8173 and kept using it, so I left that tab open.
