# Review A, round 2: engineering

Reviewer A, round 2. I read `git diff main...HEAD` on `feature/terminal-engine` (up to 253c2e9), with most attention on
the round 1 fix commit. I fixed nothing. **Not signed off.** Nothing must be fixed. Four things should be fixed, and
all four are small.

## What I checked myself

- **Back-compat, independently.** I made a detached worktree at main (e3da71d) and ran the same script against both
  trees. The script hashed events and tracks for:
  - every vision development, fresh and first training spec;
  - the demo and realistic profiles on two other seeds;
  - the Player view's friendly film (each tree's own league.json);
  - `derive_clips` for every player of every committed sample.

  All 70 hashes are identical. The worktree is removed.
- **Tests.**
  - `python3 -m pytest -q`: 743 passed, 8 deselected, in 3 min 45 s.
  - `python3 -m pytest -q -m slow`: 8 passed in 37 s.
- **Realism report.** `python -m regista.synth.report --league` takes 6.8 s cold, in parallel. Event, league-mode,
  physical and style bands all pass. 5 of 11 leader bands read "high" for the committed season, as the fixer reported.
- **API, probed with TestClient on the built season.**
  - **Bad input:** unknown metric or group gives 422, a bad id 400, an unknown player or club 404, `age_min > age_max`
    422, and an empty key in `metrics=` 422.
  - **Evidence limits:** `evidence=KEY` returns up to 500 items (Toure's touches: 500 of 744). The table returns 10 per
    metric. `evidence_limit=0` returns none, for event and physical metrics alike.
  - **Speed:** warm queries take 1-40 ms.
- **The demo's claims, against the served season.**
  - Toure has 4 goals and is outright top scorer: next are Delgado and Ustinov on 3.
  - He has the most goals per 90 of 18 regular forwards. Ustinov is second.
  - pl_ash_10 leads midfielders in goals and take-ons won per 90.
  - All four demo clips are his goals, and their titles match.
  - The stored summaries are current: none of 102 falls back to a live rules summary.
- **One percentile rule.** For Toure, the profile and the terminal agree on goals (97), key passes (86), take-ons won
  (36), interceptions (53) and assists (28).

## Round 1 fixes, checked

| Fix | Verdict |
|---|---|
| `compute_metrics` no longer mutates records | Fixed. Side tables keyed by `id(r)`, and a test checks the stream stays byte-identical and valid |
| Cold build speed, CLAUDE.md note | Fixed. Process pool (spawn), and the season is baked into the Docker image. See should-fix 4 for a cross-process race |
| Part A goals unguarded in CI | Fixed. Nightly and manual `slow-tests.yml`, three league fixtures pinned, and demo.js clip ids checked in the fast suite. The schedule fires only once the workflow is on `main` |
| Profile vs terminal percentiles | Fixed for shared stats. "Shots" still differ (should-fix 2) |
| Save % and penalties | Fixed. `sot_faced` and `saves` leave penalties out, and a hand-made test covers it |
| Evidence limits | Fixed, as probed above |
| 23 s schema test | Fixed: 3.7 s (fixture setup) |
| Attempt minimums scaling | Fixed. Club minutes / 90, and each rule says so |
| Leaders, aerials, carries, crosses, CB running, accelerations, PPDA/possession | Retuned (generator 0.4.0) and banded with sources. All pooled bands pass in the slow tests. In the committed season, 5 leader bands are high (should-fix 3) |

## Should fix

1. **The contract docs are stale for generator 0.4.0.**
   - **Version:** `data/synthetic/README.md` "League mode" still says "generator version 0.2.0". The code and
     league.json say 0.4.0.
   - **Aerial duels:** the README says any cross or long ball a nearby defender can contest, the defender being the
     nearest. In 0.4.0 only forward long balls are contested, lost long balls are contested too, crosses land in the box
     and use a 16 m reach, and the defender is picked by role (`aerial_role`: centre-backs first).
   - **Missing from "How ratings move outcomes":**
     - team style (`TEAM_STYLE`: `keep` from passing and vision, `press` from defending and stamina);
     - shot propensity by role and distance (`shot_role`);
     - keepers in build-up (`gk_target`).
   - **CLAUDE.md §2.5:** it still describes the league as "30 matches of 8 minutes, generator profile `realistic`".
     They are 2 x 15 minutes, profile `league`.
   - **Vision stamp:** README and CLAUDE.md say streams without 0.2.0 content stay 0.1.1. But the vision layer stamps
     `SCHEMA_VERSION`, now 0.2.0 (`vision/pipeline.py:40`, `identity.py`, `shots.py`, `possession.py`, `events.py`).
     So a vision run, including the Player view's cloud worker, now writes 0.2.0 on streams that use nothing from
     0.2.0, and committed `vis_0201` (0.1.1) would not reproduce byte for byte. Either stamp the vision output
     `LEGACY_SCHEMA_VERSION`, or document the exception.
2. **The two "Shots" columns count different things under one label.** This is open issue 5 in `review-fixes-1.md`,
   still unfixed.
   - The profile's `shots` counts penalty kicks. The terminal's leaves them out, as FBref does.
   - The same player can show two numbers and two percentiles called "Shots".
   - The fix is one line: either relabel the profile's stat (for example "Shots (incl. penalties)"), or leave penalties
     out there too.
3. **The served season fails 5 of its own leader bands.** Rule 4 says the report's bands must pass for the league, and
   `python -m regista.synth.report --league` reports "high" for shots, key passes, xA, touches in the box and
   interceptions. These bands are the committed season's leaders against 1.5 x the Premier League's third best.
   - **What is tested:** the slow tests check leaders only over three pooled seasons.
   - **Why the pooled check is defensible:** a regular's season is about 300 minutes.
   - **What should change:** the report should say that pooled check is the rule. For example, apply
     `INDIVIDUAL_NORMS` only with `--repeat` of 3 or more, or label the single-season verdicts "indicative (one
     season)". Today, the command the rule names prints failures for the season every page shows.
4. **The process pool bypasses `materialise`'s per-match lock.**
   - **The race:** `warm_season` (profiles, then metrics) and a terminal request arriving during warm-up each call
     `build_all`. On a cold folder, both spawn pools that can generate the same fixture in two processes. The thread
     locks do not cross processes.
   - **The failure:** the second writer runs `shutil.rmtree(dest)` on the first writer's finished folder before its own
     `rename`. A reader in the server process, between those two steps, gets `FileNotFoundError`: a 500, or
     `WARM.state = failed`.
   - **Impact:** low, because the image is pre-built, so it bites only on a cold local run or a changed league.json.
   - **Cheap fix:** serialise `build_all` behind one module lock, or re-check `is_current` just before the `rmtree`
     and drop the temp folder if another writer won.

## Nits

- The test `test_the_profile_and_the_terminal_give_one_percentile_for_one_stat` skips any stat whose two values differ
  (`continue`). So it cannot catch the two pages counting a shared stat differently, which is the bug class it exists
  for. Assert the values are equal for the five shared stats.
- `/api/players/{id}/metrics?evidence_limit=500` returns about 2 MB for Toure (127 metrics x up to 500 items). It is
  bounded, but a public endpoint could cap the whole-table limit lower than the single-metric one.
- `rank?metric=save_pct&position=FW` returns 200 with every forward listed as unranked. A 422, or an empty list with a
  note that the metric is for keepers only, would be clearer.
- `rank` builds `rest` with `ps not in ranked`, which compares dataclasses field by field and is O(n^2). Use a set of
  global ids.
- `report.physical_metrics` calls a "regular" a player with 40% of the most minutes. The terminal uses a third of a
  club's minutes. Two meanings of "regular" in one branch.
- `Season.build` and `build_season` each parse all 30 `events.jsonl` files at warm-up. The parsed streams could be
  shared.
- `.gitignore`'s generic `build/` rule ignores `docs/scout-terminal/build/`, so each new report there needs
  `git add -f`.
- **For Zaid, not an engineering defect:** Toure being outright top scorer holds for the committed season only (4 of 12
  seasons). That season was chosen among global settings, not by rigging matches, and the fix report says so plainly.
  It needs his decision.

## Numbers

- **Fast suite:** 743 passed, 8 deselected, 225 s. The slowest tests are vision ones (up to 20 s). The slowest league
  test is fixture setup at 3.7 s.
- **Slow suite:** 8 passed, 37 s, on 10 cores.
- **Back-compat:** 70 hashes, all identical between main and the branch.
- **Cold league report:** 6.8 s (46 s of CPU).
- **API:** the warm terminal metrics build takes 1.0 s. Queries take 1-40 ms.
