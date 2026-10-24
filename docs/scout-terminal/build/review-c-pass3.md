# Review C, round 3: the refresh (part C)

This is an independent review of part C on `feature/terminal-engine` at 0d8a029, which is the round 2 fix on top of
462a47f, 543acee, 38deb43 and c7a960b. It covers:

- the seeds in `src/regista/static/shared/demo.js`;
- `docs/demo-storyboard.md` and `docs/realism-report.md`;
- README, `docs/criteria.md`, `docs/architecture.md` and CLAUDE.md;
- the Fabric result and the stale-number check.

Everything ran with `REGISTA_DOTENV=` exported. Nothing was written to the live app, Azure or Fabric. The Fabric checks
below only read from OneLake (`check --no-run`, plus a script that reads tables). No file other than this one was
changed.

**Verdict: signed off.** Nothing must or should be fixed. Round 2's one should-fix is fixed: the criteria page says 13
slow tests. I re-derived every number this review covers from the code and the committed league, and each one holds.
That includes the Fabric cross-check: I read it back from OneLake myself and got 756 of 756. The Fabric result handed to
this round (328 of 756, `all_match: false`) is from before round 1's fix to `LEADERS_SQL`. The docs record it as a dated
step, followed by the 756 of 756 run.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 763 passed, 13 deselected (234 s) |
| `python3 -m pytest -q -m slow` | 13 passed (98 s) |
| `git diff --stat main..HEAD -- data/synthetic/sample models` | empty: the committed samples are byte-identical to `main` |
| `python3 -m regista.synth.report --league` | 13/13, 10/11, 14/14, 4/4, 12/14 (indicative). Every table row is in the committed report (`comm -23` on sorted rows is empty) |
| `... --league --repeat 6` | 13/13, 11/11, 14/14, 4/4, 14/14. 180 matches, 5,423.32 minutes, take-on success 0.371, all as the verdict table says |
| `... --profile realistic --seeds 21-28 --minutes 30` | 13/13. Every row is in the committed report |
| Season facts (`load_season(api.SEASON_LEAGUE, api.SEASON_ROOT, [], [])`) | Femi Toure: 10 appearances, 299.8 min, 3 goals (1 a penalty), 20 shots, 9 on target, 7 take-ons with 1 won. The next best scorers have 2. Pool: 100.5 min |
| Shortlist ranks (qualifying players by per 90) | FW goals: Femi 1st of 18. FW shots on target: Femi 1st (2.70; 9 in total against 6 for the next forward). MF take-ons won: Hugo Delgado 3rd (1.638). FW shots: Amari Ustinov 3rd (3.997). MF passes: Farid Vargas 2nd (59.43). DF key passes: Gino Mensah 5th of 24 (0.651, ahead of 0.625). Each matches the seed note |
| `scout.answer_rules` | "midfielders who win the ball back": Amari Haddad, 13.97 per 90 (45 in 290 minutes), as in storyboard beat 7. "forwards who beat their man": Haruki Fontaine, 2.47 (8 in 292), as in the Foundry Scout example |
| Goal reel, rendered offline (`TestClient` GET `/api/players/pl_bro_09/reel.mp4?tag=goal&reason=on_ball_main&order=match`, scratch cache) | 23.60 s, 1280x720. He has 12 goal moments, 3 of them on the ball, as the storyboard says |
| `build_all` into empty scratch roots | 6.0 s in parallel (10 cores), 37.1 s with one worker (1.24 s a match). CLAUDE.md and the architecture page claim 5.9 s / 37 s and about 1.3 s |
| Catalogues | `profiles.STATS` 28; `RATIOS` 4 (pass_accuracy, take_on_success, shot_accuracy, aerial_win); `metrics.CATALOGUE` 127 in 8 `GROUPS`; `TEAM_CATALOGUE` 19; `reliability.NOISE_R` 0.3; Regista MCP lists 10 tools |
| `python3 -m regista.season.metrics --rank goals --position FW`, `python3 -m regista.season.audit` | Both run as documented. Femi is first for goals per 90 (0.9) and first among the top scorers |
| `REGISTA_DOTENV= python3 -m regista.season.fabric check --no-run` (reads only) | "756 of 756 match ... Fabric agrees with Regista". My first attempt hung with no output and was stopped. The retry finished at once |
| Read-only script: OneLake `player_season` and `leaders_check` against this branch's `player_season_rows(Season)` | `player_season` 3,024 rows, 756/756. `leaders_check` 756/756, 462 rows with a percentile, `computed_at` 2026-10-24 11:28:52 UTC. These are the figures the architecture page's third run gives |
| `grep` for stale numbers in current docs and code (6 goals, Kenan Nakamura, 0.6.0, 8-minute matches, 301 minutes, 760-762 tests, 12 slow, three ratios, 0.2 s, Ustinov's 3.29, "header from a corner", "in the air") | The remaining hits are dated history or version notes and are correct as written: the storyboard's deploy note, the reel's history, and the contract doc's per-version notes |

## Round 2 findings

| Round 2 finding | Status |
|---|---|
| Should fix 1: `docs/criteria.md` says 12 slow tests | **Fixed** (0d8a029). Criteria, README and CLAUDE.md all say 763 tests plus 13 slow ones, which matches the runs above |

## Must fix

None.

## Should fix

None.

## Nits (carried over from round 2, still open, none blocking)

1. In `data/synthetic/README.md`, the corner paragraph says "nobody attacks the box at 45 corners". That gives one cause
   to all 45. In fact, 26 of them are the taker's own carry, take-on or shot.
2. Generator comments L144 ("every one-season band"), L226 ("A corner is always a cross") and L1797 ("always from the
   corner flag") are stale. They are held back on purpose, because editing `generator.py` changes the code fingerprint.
   Fix them with the next generator change.
3. The voiceover for storyboard beat 5, "with the truth for every frame, cross-checked in Microsoft Fabric", suggests
   the frame-level truth is in Fabric. Fabric cross-checks the league leaders.
4. CLAUDE.md L565, "event-stream contract (schema 0.1.1)", is stale beside §3's 0.2.0.
5. `tests/test_shared_dashboard.py` proves "outside the box" with `shot_distance_m > 18`. Checking the distance from the
   goal line against 16.5 would be exact.
6. The demo.js Strengths line, "Scores from distance and from the penalty spot", rests on one goal of each kind. "Has
   scored ..." would be more exact.
7. `docs/criteria.md` says the slow tests run nightly. That is true only once `.github/workflows/slow-tests.yml` reaches
   the default branch, because scheduled workflows run from there.
