# Review A, round 1: the friendlier terminal (ux/terminal-friendly)

Reviewer A, round 1. My lens: correctness and safety. I checked:

- every number still matches the API
- complete evidence and playback
- the stale-command guard
- the "most <stat>" parser for every metric
- saved-layout migration
- CSP and esc(), Regista.store only, no ratings, no writes
- the inventory, tests and the full suite

I read `git diff main...HEAD` (commits 81eb9fa and c512d03) and fixed nothing.

**Verdict: not signed off.** One must-fix and one should-fix.

## How I checked

- **Test suite:** `python3 -m pytest -q` gives 851 passed, 13 deselected.
- **The app:** ran offline on 127.0.0.1:8203 (`REGISTA_DOTENV=`). The browser pane was at its tab cap with other sessions'
  tabs, so I closed nothing. Instead I drove a headless Chromium (Playwright) at 1440 px. The harness used CSP bypass
  only so it could run its own waits. The page's own CSP header is unchanged.
- **Every number in the table against the API:** I compared the 144 table numbers on first load with `/api/terminal/screen`.
  - Every value matches its rounded API value.
  - Every zero is plain text exactly when `evidence_total` is 0.
- **API counts:** for all 102 players × 127 metrics (12,954 cells) I compared `SeasonMetrics.evidence_total` with
  `evidence(...)["moments"]`. I also compared Toure's screen `evidence_total` with his `/metrics` `moments` for every metric.
- **Evidence and playback:**
  - "Femi Toure pass completion" plays 124 rows. The label says 124 and the API's `moments` is 124.
  - "Femi Toure touches" plays 182, matching the API's 182/182.
- **Stale guard:**
  - "similar to Femi Toure" followed at once by "team Calder" ends on Calder's line.
  - "Femi Toure" followed at once by "rank forwards goals" ends on the ranking.
  - No older line overwrote a newer one.
- **Saved layouts:** a changed v2 layout (team XL first, Clips M, Player hidden, MF, Percentile, xA sort, cols goals+xa,
  layout 2 current) loads correctly:
  - Clips is dropped and Player stays hidden.
  - Order and sizes are kept.
  - The columns, the sort and current layout 2 are kept.
- **Rules:**
  - The only storage key written is `regista.demo.v1.terminal`.
  - Every request is a GET to 127.0.0.1:8203, and there are no console errors.
  - terminal-words.js has no innerHTML, no style=, no storage and no requests.
  - I traced every new innerHTML interpolation in terminal.js: it goes through `esc()` or is a constant.
  - No hidden-rating keys appear (the tests also check this).
- **Parser:** I ran `terminal-words.js` in node with the real catalogue (the test's harness), on the tested forms plus
  others: 297 names per form (key, label, short label for 127 metrics).

## Must fix

### 1. "▶ N moments" is wrong for shot-creating actions (single-key stats can repeat an event)

**Where:**
- `src/regista/season/metrics.py`: `SeasonMetrics.evidence_total`, its single-key fast path, and `evidence()`'s new `moments`
- `src/regista/static/scout/terminal.js`: `fullFn`, which uses `evidence.moments`; `evidenceReel`'s single-key branch, which does not merge rows

**What happens:** one pass can create two shots, so `ps.evidence["sca"]` can list the same event twice. The two counts
then disagree:

- `evidence_total` counts the rows for a single-key metric: 18 for Toure.
- `evidence()["moments"]` counts distinct events: 16.
- The drawer's single-key branch lists every row unmerged: 18. Two rows read "R1 at EAS 52' Live-ball pass" and two read
  "R3 at FAI 46' Live-ball pass".

**What the scout sees:**
- The players table first says "Play its 18 moments" (from the screen).
- Once the selected player's full metrics load, which happens at once for the focus player, the cell says "Play its 16
  moments" and the tooltip says "▶ 16 moments · click to play".
- A click plays "Playing Femi Toure · Shot-creating actions: 18 moments."

So the count changes depending on what has loaded, and then disagrees with the drawer. That is the mismatch the
safeguard set out to remove.

**How often:**
- Across the league, 12 player cells disagree, all on `sca`. Every other metric agrees.
- `/api/terminal/screen` and `/api/players/{id}/metrics` give different numbers for the same cell (18 against 16).
- The safeguard report says the old count "was true only for single-key stats"; it is not true for `sca`.

**Fix direction (not applied):** pick one rule and use it on both endpoints and in the drawer. Either:
- (a) `moments` and `evidence_total` count the rows the drawer will list (merge only when there are several keys), or
- (b) the drawer merges duplicate events for single-key metrics too, and `evidence_total` always counts distinct events.

Then add a test that compares, for every player and metric:
- screen `evidence_total`
- `/metrics` `moments`
- the number of rows the drawer would list

The current tests check only goals, assists, distance, pass_pct and npxg_plus_xa, so they missed this.

## Should fix

### 2. "most <stat>" breaks when a position comes first, and in some filtered questions

**Where:** `src/regista/static/scout/terminal-words.js`, `natural()`.

**What is fixed:** the forms the new test covers work for all 127 metrics:
- "most X", "the most X", "who has the most X(?)", "X per 90", "most X per 90", "top X", "top 5 X", "highest X",
  "best X", "show me the most X"
- also "X per 90 minutes", "X p90", "who has the highest X per 90", "MOST X", "highest X per game", "which players have
  the most X"

**What still fails** (results on 297 names per form):
- **A position before "most":**
  - "forwards with the most X": 297 of 297 fail, including "forwards with the most goals", which answers "Nothing found".
  - "forwards most X": 297 of 297 fail.
  - Cause: the position is taken out only after the leading superlatives are read off, so "most" stays in what is left
    and matches no stat.
- **A filter with a stat whose name holds a filler word:**
  - "most X for forwards" (15 fail), "most X at Brookfield" (12) and "most X in the league" (12) fail.
  - The affected stats have names with "on", "in", "from", "the", "mid": Shots on target, Mid third pass %, Passes from
    the defensive third and others.
  - Cause: the filler-word filter and `posOf('mid')` take those words out of the stat's own name. "most shots on target
    for forwards" offers 3 stats. " from " also matches the club pattern before the real " at Brookfield".
- **"fewest X", "least X", "lowest X":** "Nothing found" for every stat, including the lower-is-better ones the new
  "most" rule is about.

Zaid asked for "most <stat>" to work for every catalogue metric. The plain form does. These are its natural
variants, and they still fail for whole groups of metrics.

**Suggested approach:**
- Strip superlatives wherever they appear, not only at the start.
- Try the exact stat name before removing filler or position words.
- Read "fewest", "least" and "lowest" as the smallest numbers first.
- Extend `QUESTION_FORMS` in the test with a position form and a club form.

## Nits (not blocking)

- **Shared-strength chips and radar wedges:** they open the drawer even for a number with no moments (no `z` class there),
  showing "Nothing to play". This is graceful, but it is not the plain-text treatment the table gives.
- **Number click while a command loads:** a click on a number in another row selects that player without bumping `gen`.
  If a typed player command is still loading, it can later take the selection back. Main behaves the same, so this is
  not a regression. A row click does bump `gen`.
- **Old layouts in storage:** a migrated v2 layout stays stored as `v: 2` until the next change saves it. This is harmless,
  since `clean()` migrates on every read.
- **"most" for lower-is-better stats:** the semantics ("most yellow cards" lists the most first) are the safeguard's open
  decision for Zaid. The code, the status line "(most first; fewer is better)" and the tests agree with each other.

## Kept (confirmed)

- **Complete evidence:** paged until complete. Toure's touches play 182 rows; his pass completion plays 124, with ratio
  rows merged.
- **The four fixes:** each is pinned by a test, and I checked them in the code:
  - form bars filter the complete list by match
  - the radar breaks its outline at a missing percentile
  - Alt+1 goes into the table
  - commands write their line, then scroll
- **Stale guard:** `gen` is bumped by `run` and by `select`, and checked after each await in the panel, player, compare,
  scatter, team and rank paths.
- **Reset this demo:** clears the store, the history and the drawer (`forgetReel` closes it).
- **Rules:** the CSP is unchanged; nothing is written to the server; the only storage is through Regista.store; no ratings.
- **Packaging:** terminal-words.js is package data and is not excluded by `.dockerignore` (tested).
