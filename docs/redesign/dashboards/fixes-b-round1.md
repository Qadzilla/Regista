# Fixes for review B, round 1

All five findings are fixed. The full suite passes (656 tests). I checked the pages offline on port 8157, at 1440 px and 375 px.

## 1. Find players follows the sandbox layout

- The order is now the sandbox's: Ask the Scout agent, then the filters and cards, then the league table under the cards. At 1440 px the cards fill 4 columns, as in the sandbox.
- Three filters show, as in the sandbox: Name or club, Position (first option "Any"), and Sort by. The API's `q` already matches names and clubs.
- Club, Minimum minutes and Reset sit behind a "More filters" link. That keeps SC-17 from the inventory without showing it by default. The panel opens by itself when the URL sets `club` or `min_minutes`, or when a club in the table is picked. The URL state (SC-18) and the table's club filter (SC-06, SC-07) still work.
- The tagline, the Synthetic badge sentence and the engine explanation are gone. The engine picker (Data Search / Foundry) stays.

## 2. Compare is the sandbox's compact table

- It has the sandbox's rows: each player's position-leading rates, then goals, assists, key passes, take-ons won, tackles won, interceptions and recoveries. That makes 8 rows for a forward and a midfielder.
- Every value is per 90, under the line "Per 90 minutes this season. Pick a number to see the moments behind it."
- "Nth percentile" is gone. Each number's hover text and screen-reader label say "Higher than N% of the league's midfielders".
- The highest value is still marked, and the moments still open on click.

## 3. Card wording

- Cards, Team needs and shortlist items now use the house sentence unchanged, for example "Not above any of the league's midfielders".
- The Scout agent's card line says among whom: "1st of 18 midfielders", or "joint 2nd of 18 forwards" for a tie. The rank comes from `rank_in_position`.

## 4. Caveats and Settings

- Scout Settings: the Password row is gone. Sign out now does what it does on /me: it forgets the admin key this tab holds and says so.
- The synthetic note is gone from the shared profile page, and so from /me My profile too. Its `options.synthetic` switch is gone as well. Each page keeps the one synthetic line in its footer.
- The tests that pinned the old notes now check the footer line, and check that the notes are gone.

## 5. Upload steps in plain words

- A new `plain()` in me.js cleans every worker note before it is shown, in the step rows, the Needs-you card and the answered list.
- It drops match ids: "13 files saved as match pv_…" becomes "13 files saved".
- It fixes the "(s)" plurals: "2 answers", "1 answer", "2 identity calls".
- A node test pins both behaviours.
