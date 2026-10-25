# Review A, round 2: the friendlier Scout terminal (ux/terminal-friendly)

Reviewer A, round 2. My lens: correctness and safety. I reviewed `git diff main...HEAD` at 5d4b068 and ran the app offline on 127.0.0.1:8203 (`REGISTA_DOTENV=`), in my own browser tab at 1440 and 375 px. I changed no code. Afterwards I stopped the server and cleared this origin's demo storage.

**Verdict: not signed off.** One finding should be fixed, and it is small. All of round 1's fixes hold.

## What I checked, and it holds

- **Full suite:** `python3 -m pytest -q` gives 855 passed and 13 deselected.
- **Every number has one moment count.** `SeasonMetrics.evidence_total` counts distinct `(match, event)` for every event metric. `evidence()['moments']` uses the same `_moment_id`. The drawer's `mergeEvidence` merges on `match_id | event_id || 't'+t`, and `t` is rounded to 2 places on both sides, so its key is the same.
  - In the browser, Femi Toure's shot-creating actions read "5.91 actions per 90 · 18 in total", then "16 moments". The drawer has 16 rows, two of them say "counts 2 times", and the status line says "Playing … 16 moments".
  - The new test covers every player and metric (screen == /metrics == drawer rows).
- **Complete evidence:** paging through `evidence_offset` is unchanged.
- **The four fixes:** pinned by their tests.
- **Stale-command guard:** I fired a slow `plot … against …` and `similar to Calder`, then `most fouls`. The last line was the `most fouls` answer, and nothing older overwrote it.
- **The "most <stat>" parser and its other end:**
  - All key, label and short-label forms in `QUESTION_FORMS` and `PLACED_FORMS` pass.
  - I also ran about 70 extra phrasings through node with the real league. Among those that work:
    - `most goals per 90 for forwards`, `top 10 forwards by xG`, `midfielders with most xA`, `goalkeepers with the best save %`
    - `highest xG per 90 in midfield`, `most assists by a defender`, `most aerial duels won by defenders at Calder`
    - `who has the fewest fouls at Calder`, `who scores the least`, `lowest pass completion for defenders`
    - `most shots on target percent`, `most goals for at Brookfield`, `xG per 90 at Calder`, `forwards xG per 90`
  - No stat label, club name or player name contains an "end" word (most, least, worst and so on), so reading `end` off the whole question cannot misfire on a name.
  - In the browser:
    - "most yellow cards" gives "(most first; fewer is better) … Noel Oliveira, 4".
    - "fewest yellow cards" gives "(lowest first: lower is better)", with 41 players tied on 0.
    - "worst finishers" gives "(worst first)".
- **Saved layouts:** `clean()` accepts v2 and v3. An untouched v2 default (`V2_DEFAULT` matches main's `DEFAULT_ORDER` and sizes) takes the v3 default. A changed v2 layout keeps its order, sizes and hidden panels, and drops Clips (a drawer now). Everything else in it carries over.
- **Rules:**
  - No `style="`, inline handlers or `<script>` in `index.html`, `terminal.js` or `terminal-words.js`.
  - Storage goes only through `R.store` (`regista.demo.v1.terminal`). There is no localStorage or sessionStorage access.
  - Every request goes through `R.api` as a GET. The server log shows only GETs, with no 4xx or 5xx.
  - No rating keys appear, and the console shows no errors.
- **Phone, 375 px:** no sideways scroll (scrollWidth 375), and the sticky panel row shows.
- **API docstrings:** they describe `evidence_total` and `moments` correctly.

## Should fix

### 1. "which <position> have the most <stat>" answers "Nothing found"

**Where:** `src/regista/static/scout/terminal-words.js`, the `OPEN` regex and `natural()`.

**Detail:** `OPEN` reads "which players (have|has|are|is)" as an opener, but not "which" or "what" followed by a position word. Each of these answers Nothing found, both in node and in the browser on 8203:
- `which forwards have the most goals`
- `which forward has the most goals`
- `which midfielder has the most xA`
- `which defenders have the most tackles`
- `which keepers have the best save %`
- `which forwards have the fewest goals`
- `which forwards score the most`
- `what forwards have the most goals`

The round's own fix accepts the variants: `which players have the most goals`, `who are the forwards with the most goals` and `forwards with the most goals` all work. The "which <position>" form is the most natural way a scout asks the round-1 finding's question, so the position-question fix is incomplete.

**Suggested fix:**
- Let `OPEN` take `(which|what) <position word> (have|has|are|is)?`, keeping the position (or put the position word back at the front of what is left), and set `who` so a following verb ("score", "tackle") maps through `VERB`.
- Add `which forwards have the most {}`, `which midfielder has the fewest {}` and `which defenders have the most {} at Brookfield` to `PLACED_FORMS`.

## Nits

- `the most progressive carries in the league this season` answers Nothing found. `LEAGUE_W` removes only one trailing phrase. `… in the league` and `… this season` each work alone.
- `Toure most goals` gives none. `Toure goals` works.
- `which club has the most goals` gives none. Ranking clubs is not a terminal feature, but the question could point to Team.
- The CLAUDE.md §2.10 bullet still describes only "most"/"highest". It does not mention fewest, least or lowest (smallest first), worst (the better way reversed), or the position and club forms added in round 1.
- Still open from the safeguard:
  - Team numbers have no count until the club loads.
  - "Toure vs Ustinov" picks Hugo before Toure's similar players load.
  - Static files have no Cache-Control.
  - The sandbox nits listed in `build.md`.

## Not done (per the task)

Nothing was pushed, no PR was opened, and nothing was merged.
