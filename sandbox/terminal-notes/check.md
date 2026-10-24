# Scout terminal: independent check (part B6)

Checked 2026-10-24 in a real browser (the desktop app's browser pane, my own tab). The sandbox was served on
127.0.0.1:8172 and the local app on part A's code ran at http://localhost:8040. Viewports were 1440x900 and 375x812,
and I reset the viewport afterwards. I removed my test workspace (`regista.terminal.v1`) from the browser, closed the
tab and stopped the server. Nothing went to Azure or the live app, and /Users/zaid/Desktop/Regista was not touched (it
is still on feature/terminal-engine).

## Fixed in this commit (sandbox/terminal.js)

1. **A literal `<GO>` failed for names.** "TOURE <GO>" typed as text gave "Not a player, club or command". The trailing
   `<GO>` is now stripped for every command, so the spec's example works when typed out.
2. **CMP lost the namesake alternatives when names had no commas.** "CMP Toure Ustinov" silently picked Femi Toure
   and Otis Ustinov and offered no swaps. Swaps now appear, and clicking one ("CMP Leon Toure, Otis Ustinov") runs.
3. **Suggestions after `RANK <pos>` ignored the typed position.** They used the focus player's position defaults (a
   defender's metrics after "RANK FW "). They now follow the typed position: GK gives Save %, Goals conceded and
   Saves; ALL gives the league-wide defaults.
4. **"1 goals" in SHOT output** now reads "1 goal".
5. **Closing help with its button left "Help is open. Escape closes it."** on the output line. It now says "Help closed.".
6. **Per-match physical evidence had no unit.** It showed "34.9" and now shows "34.9 km/h" (m for distances).

I re-ran every case above after the fix. No console errors.

## Checked and working

- **Commands, good and bad input.** I ran each one through the real form submit.
  - Names: TOURE, "femi toure", Amari Ustinov.
  - RANK: FW npxg, a metric label ("RANK DF aerial win %"), the word "forwards", a metric alone ("goals"); errors for a
    missing or unknown metric.
  - CMP: 2 and 3 players (space- and comma-separated); errors for one player, unknown names and empty input.
  - SCAT: with and without a position, two-word labels; errors for one metric or nonsense.
  - SIM, SHOT, FORM, HEAT, RDR, each with a name, with no name (uses the focus player) and with an unknown name.
  - TEAM: short name, full name, prefix ("brook"), bare TEAM, a bare "BRO", and an unknown club.
  - HELP opens and Escape closes it. An unknown command gives an error and blank input does nothing.
- **Autocomplete** for commands, players, clubs, metric keys and labels (noisy ones marked ≈) and positions, per
  argument slot. Up, Down and Enter work with real keystrokes. History (Up and Down) recalls past commands.
  Cmd+K and Ctrl+K jump to the Terminal from Home and Find players and focus the line, including on a fresh page load
  before terminal.json has loaded.
- **Linked selection.** Each of these set the focus: screener name, screener number, similar player, team squad
  list, radar legend, scatter dot. Player, radar, shot, form and team all followed. The screener marked compared rows,
  and the scatter labelled the focus and compared players.
- **Evidence and clips.**
  - Every number opened its moments in CLIP: screener cell, player-card best list, similar-player chip, radar table,
    shot map dot and header numbers, heat header numbers, form mean, scatter readout, team set-piece xG.
  - Other numbers have no clip and say so: team possession (per-match values), physical metrics (per-match), and form
    bars for a match with no moments.
  - Clips really play from http://localhost:8040: the video reached readyState 4 and its currentTime advanced. The
    network log shows `GET /api/matches/rl_r01_eas_bro/clips/cl_t_away_09_000002.mp4 → 206`, and the app answers
    200 video/mp4. The "all N on the local app" link returns 200 JSON.
  - Script check against the app: 117 sampled evidence moments from 15 players all fall inside their clip's
    `t`–`t_end`. 3 moments have no clip, as the export states.
- **Workspaces.** WS1 holds CMP, RANK MF, SCAT, a hidden panel, a resized panel and a moved panel. WS2 kept its own
  state. After a reload I got WS2 back, then WS1 back intact; Reset restores the defaults; history persisted.
  - With storage blocked (a throwaway page whose localStorage getter throws, deleted afterwards), the terminal works
    in memory and shows "not saved: storage blocked". Every other sandbox section also loaded with no errors.
- **Definitions.** Hovering with the real mouse shows a tooltip with the definition, rule, source, unit, noisy flag
  with r, and the player's value and percentile. Keyboard focus on value buttons sets `aria-describedby="txTip"`.
  Every metric label in every panel sits beside a focusable value button that carries the same metric.
  The screener grid works with arrow keys and Enter, keeping focus and the tooltip.
- **No hidden ratings.**
  - Text search of terminal.json: no attributes, shot_stopping, top_speed_kmh or acceleration_ms2. "finishing" and
    "dribbling" appear only in definition and group text.
  - A walk of every key in the file finds none of the rating keys, and no metric key or definition mentions a rating.
  - The terminal's DOM (help open) has none either.
- **Layout.** At 1440 and 375 the page scrollWidth equals the viewport. The only elements past the edge are the
  existing mobile sub-nav links, which scroll inside `.subnav`. The screener table scrolls inside its panel. At 375
  every panel stacks in one column and stays readable: radar with a 3-player table, clips, scatter, team style.
- **Rest of the sandbox.** Home, Player profile (overview and the other five sections), the other Scout sections and
  `#scout/player/pl_bro_09` render with no console errors. The clip video pauses when you leave the Terminal.

## Left as is (for Zaid or a later pass)

- **Ambiguous names open the namesake with the most minutes.** TOURE gives Femi (right), but USTINOV gives Otis (a
  full-back), BRENNAN gives Noel (a keeper) and OKAFOR gives Farid (a full-back). The alternatives are one click away.
  A rule that prefers the focus player's position, or forwards, would suit a scout better. This is a product call.
- **CMP offers swaps for the first ambiguous name only** ("Toure", not "Ustinov" as well).
- **Repeat commands keep the earlier filter.** SCAT without a position keeps the scatter's current position filter
  rather than ALL, and the output says which (e.g. "FW"). RANK without a position sets ALL. Consistent enough; worth
  a sentence in HELP.
- **The screener does not follow the selection across positions.** Selecting a goalkeeper from the team squad leaves
  it on FW, so no row is highlighted. The scatter says "The focus player is not on this chart".
- **Units on single figures.** RANK output and screener values show km/h and m without the unit (the header tooltip
  has it).
- **At 375 px the screener shows one metric column at a time** next to the sticky name and the Club/Pos/Min columns.
  It works by scrolling inside the panel, but hiding Club/Pos on phones would show more numbers.
- **From the export (already known):**
  - The evidence cap of 10 per number.
  - The "all N" link opens raw JSON in a new tab, because the app sends no CORS headers.
  - Clips need the local app at 8040 and render on their first request.
