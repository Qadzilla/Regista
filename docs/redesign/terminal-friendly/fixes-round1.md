# Fixes for review round 1 (friendlier Scout terminal)

Three findings came in. All three are fixed, and the full suite passes (855 tests).

## 1. "▶ N moments" was wrong for shot-creating actions

**Cause.** A single pass can create two shots, so `ps.evidence['sca']` can list the same event twice. For a metric with one key, `evidence_total` counted rows. `evidence()['moments']` counted distinct events, and the drawer listed every row.

**Fix.** There is now one rule: each event is counted once, everywhere.
- `SeasonMetrics.evidence_total` (`src/regista/season/metrics.py`) no longer has a single-key fast path. It always counts distinct `(match, event)` pairs, so the screen and the scatter agree with `/metrics` `moments`.
- In `src/regista/static/scout/terminal.js`, the drawer's single-key branch of `evidenceReel` now merges rows with `mergeEvidence`, the same way the multi-key branch already did. When an event counts more than once, its row shows the summed value and says "counts N times".

**Checked in the browser.** For Femi Toure's shot-creating actions:
- the cell tooltip says "Play its 16 moments"
- the drawer has 16 rows, and two of them say "Live-ball pass · counts 2 times"
- the status line says "16 moments"

**Tests.**
- `test_every_numbers_moment_count_is_the_drawers_row_count_for_every_player_and_metric` covers all 297 players and all 127 metrics. It checks that the screen's `evidence_total`, `/metrics` `moments` and the drawer's merged row count are equal.
- `test_the_drawer_lists_each_event_once_for_one_key_too`

## 2. "most <stat>" with a position, a club or filler words

**Fix.** `natural()` in `src/regista/static/scout/terminal-words.js` now works in this order:
1. Phrases such as "in the league" or "this season" are removed from the end first.
2. It tries the exact stat name, removing leading superlatives one word at a time.
3. If that fails, it tries the exact stat name with a position before it ("forwards with the most X", "forwards most X") or after it ("most X for forwards", "most X among defenders"). The stat's own words are tried as a whole before any word is taken as a position.
4. Club matching tries the last "at/for/from/in" first. It uses a lookahead, so "goals for at Brookfield" works. After the club is found, it tries the exact name again, with or without a position.
5. The final word-match fallback also drops superlatives found anywhere in the question.

**Tests.**
- `QUESTION_FORMS` has gained "X per 90 minutes", "X p90", "MOST X", "highest X per game", "which players have the most X", "most X in the league", and the fewest/least/lowest forms.
- `test_every_stat_answers_with_a_position_or_a_club_before_or_after_it` runs 9 position and club forms over every key, label and short label (2673 questions). It checks the stat, the position and the club.

## 3. "fewest / least / lowest / worst <stat>"

**Fix.**
- The reader returns `fewest: true` for fewest, least, lowest and smallest, and `worst: true` for worst, weakest, poorest and bottom. The first such word in the question wins.
- "who concedes the least" works through a new `concedes` verb, which maps to `goals_conceded`.
- `cmdRank` sorts by the requested end:
  - most: biggest first
  - fewest: smallest first
  - worst: the stat's better way reversed
- The status line names the order: "(worst first)", "(fewest first; more is better)", "(lowest first: lower is better)" or "(most first; fewer is better)".

**Tests.** `test_fewest_least_lowest_and_worst_rank_from_the_other_end`. Checked in the browser with "fewest yellow cards", "who concedes the least", "worst finishers", "forwards with the most goals" and "most passes from the defensive third at Brookfield".
