# Review C, round 2: the refresh (part C)

Independent review of part C on `feature/terminal-engine` at c7a960b, the round 1 fixes on top of 462a47f, 543acee and
38deb43. It covers the seeds in `src/regista/static/shared/demo.js`, `docs/demo-storyboard.md`,
`docs/realism-report.md`, README, `docs/criteria.md`, `docs/architecture.md`, CLAUDE.md, the Fabric result and the
stale-number check. Everything ran with `REGISTA_DOTENV=` exported. Nothing was written to the live app, Azure or
Fabric: the Fabric checks below are reads from OneLake (`check --no-run` and a script that only reads tables). No file
other than this one was changed.

**Verdict: not signed off.** Nothing must be fixed. One thing should be: `docs/criteria.md` still says 12 slow tests,
and there are 13. All five round 1 findings are fixed or honestly documented, and I re-checked the Fabric fix against
OneLake myself. The nits below don't block.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 763 passed, 13 deselected (233 s) |
| `python3 -m pytest -q -m slow` | 13 passed (98 s), including `test_the_notebooks_rule_reproduces_the_whole_committed_season` |
| `git diff --stat main..HEAD -- data/synthetic/sample models` | empty: the committed samples are byte-identical to `main` |
| `REGISTA_DOTENV= python3 -m regista.season.fabric check --no-run` (reads only, no notebook run) | "756 of 756 match ... Fabric agrees with Regista" |
| Read-only script: OneLake `leaders_check` and `player_season` vs this branch's `Season.build` + `season_tables` | `player_season` 756/756; `leaders_check` 756/756; `leaders_rule()` vs build 756/756; 462 rows carry a percentile; pool 100.5. `leaders_check.computed_at` is 2026-10-24 11:28:52 UTC, before the fix commit (11:39 UTC), so it is the run the docs describe |
| `LEADERS_SQL` read against `profiles`/`metrics` | pool = appeared and `minutes_raw >= ROUND(max club minutes / 3, 1)`, where club minutes are the sum of `played_s/60`; rank value is per-90 to 6 decimals; FBref percentile `BROUND(50*(below+at_or_below)/n)` when n > 1. The old 40% / `(n-1)` rule is gone, and a test pins it |
| Season facts (`load_season`) | Femi Toure: 10 appearances, 299.8 min, 3 goals, 20 shots, 9 on target, 7 take-ons with 1 won. These are the numbers the seeds and the storyboard quote |
| Corners in the committed season (first event after each corner, skipping touch and pressure) | 111 corners: the taker's cross 66, carry 18, pass 9, take-on 7, period end 5, throw-in 5, shot 1. `data/synthetic/README.md` quotes exactly these counts |
| `git show main:docs/demo-storyboard.md` | main's beat 7 names Kenan Nakamura, as the new deploy note says |
| `grep` for "header", "in the air", "328 of 756", "761", "12 slow", "40%" across README, CLAUDE.md, criteria, architecture, storyboard, demo.js | see should-fix 1 and the nits. The "40%" hits left are the dated second run in architecture.md and the physical-band definition in the realism report, and both are correct |

## Round 1 findings

| Round 1 finding | Status |
|---|---|
| Must fix 1: the Fabric cross-check fails | **Fixed.** I confirmed it independently from OneLake (above). `tests/test_fabric.py` now checks the SQL's rule offline: three fixtures in the quick suite, the whole season under `-m slow`, plus a text pin. README, criteria, architecture (new "Third run"), storyboard and CLAUDE.md record 756 of 756 with dates |
| Should fix 1: storyboard beats 1, 5 and 7 depend on a deploy | **Fixed.** There is a note under the shot table, and "Merge and deploy ..., then re-check beats 1, 5 and 7" is in "To build before recording" |
| Should fix 2: "a corner is always a cross" | **Fixed in the contract doc.** The measured counts are given, and I reproduced them. The generator comments still say it (nit 2, held back because of the code fingerprint) |
| Should fix 3: closing round 3's open findings missing from CLAUDE.md | **Fixed.** §4.2 says closing round 3 was not signed off. It lists all four findings as open and Zaid's call, and puts "those findings (fix or accept)" under Left |
| Should fix 4: the "header from a corner" | **Fixed by the documentation route.** demo.js, the storyboard and the test no longer claim it. The Strengths line now cites the round 5 and round 2 goals, and their clip refs exist (tests pass) |

## Must fix

None.

## Should fix

### 1. `docs/criteria.md` says 12 slow tests; there are 13

**Where:** `docs/criteria.md` L21: "plus 12 slow ones (`python3 -m pytest -q -m slow` ...)".

The fix commit updated L20 to 763 but left L21. README L153 and CLAUDE.md §4.2 say 13, which is correct:
`pytest --collect-only -q -m slow` gives 13/776, and the run above passed 13. This is the judges' criteria page, and the
job asks for every number to be true. Change it to 13.

## Nits

1. `data/synthetic/README.md` (the corner paragraph) says "nobody attacks the box at 45 corners". That gives one cause
   to all 45, which the counts don't support:
   - 26 of the 45 are the taker's own carry, take-on or shot, chosen before any cross target is looked for;
   - only the 9 ordinary passes show an empty box;
   - review-a-final3 measured nobody in the penalty area at 95% of corner decisions, crosses included.

   Better: "the taker crosses at 66; at the 9 passes from the flag nobody was within reach, so he played an ordinary
   pass".
2. Generator comments L226 ("A corner is always a cross") and L1797 ("always from the corner flag") are still stale. This
   is known and recorded: editing `generator.py` changes the code fingerprint. Fix them with the next generator change.
3. Storyboard beat 5's voiceover, "with the truth for every frame, cross-checked in Microsoft Fabric", still suggests
   that the frame-level truth is in Fabric (round 1 nit). The lakehouse holds no tracks or physical records.
   Suggestion: "... down to every sprint. Its league leaders are cross-checked in Microsoft Fabric."
4. CLAUDE.md L565 "event-stream contract (schema 0.1.1)" is still stale beside §3's 0.2.0 (round 1 nit).
5. `tests/test_shared_dashboard.py` still tests "outside the box" with `shot_distance_m > 18` (round 1 nit). Use the
   distance from the goal line > 16.5 instead.
6. The demo.js Strengths line, "Scores from distance and from the penalty spot", generalises from one goal each. It is
   true as written, but "Has scored from distance and from the penalty spot" is more exact.
7. `docs/criteria.md` says the slow tests run "in a nightly workflow". `.github/workflows/slow-tests.yml` exists only on
   this branch, and scheduled workflows run from the default branch, so this holds only after the merge. That is in
   line with the README's "not yet merged", but worth knowing.
