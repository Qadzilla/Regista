# Refresh 2: everything that quotes the league, after the determinism fix and Femi Toure's edge (2026-10-24)

Branch `feature/terminal-engine` on top of 2ef14e3 (PR #36, part A). The season is generator 0.7.1 (the same bits on
Linux and macOS) with league attributes version 2 (Femi Toure: finishing 99, dribbling 72). Everything here is
synthetic. Commands ran offline with `REGISTA_DOTENV=`, except the Fabric push and check (Zaid's own workspace
"Regista", lakehouse `regista_league`; nothing else in the tenant was touched). Nothing was written to the live app or to
Azure. The `push` read the Player-view upload list from the Azure store, read-only.

## The facts everything was checked against (re-run here)

| Fact | Value | How |
|---|---|---|
| Femi Toure, league only | 10 appearances, 274.3 min, 5 goals (0 penalties), 19 shots, 9 on target, 14 take-ons with 1 won | `load_season(api.SEASON_LEAGUE, api.SEASON_ROOT, [], [])` |
| Femi Toure, with his uploaded friendly `pv_8807d7835c` | 11 appearances, 277.5 min, 5 goals, 22 shots, 11 on target, 14 take-ons with 1 won; the same five goal clips | the same, `uploaded=` the local copy of the done upload |
| Top scorers | Toure 5; Amari Ustinov 3, Leon Whitfield 3; Haruki Adeyemi 2, Milan Brennan 2 | `python3 -m regista.season.audit` |
| His goals (match, clip) | `rl_r01_eas_bro` `cl_t_away_09_000006` (6') and `cl_t_away_09_000023` (56'); `rl_r06_bro_eas` `cl_t_home_09_000011` (49'); `rl_r08_bro_fai` `cl_t_home_09_000005` (6'); `rl_r10_bro_ash` `cl_t_home_09_000011` (8') | `profile["evidence"]["goals"]`, both ways |
| The 56' goal | cross, first touch, a 6.1 m carry (`dribble`), then a shot with `header` from 4.4 m | the match's `events.jsonl` |
| Ranks (per 90, pool 100.5 min) | Toure 1st of 18 forwards for goals and for shots on target (also in total); Delgado (`pl_ash_10`) 4th of 18 midfielders for take-ons won; Ustinov (`pl_ash_09`) 2nd of 18 forwards for shots; Vargas (`pl_dun_06`) 3rd of 18 midfielders for passes; Mensah (`pl_eas_03`) 9th of 24 defenders for key passes | the seed test's rank rule, league only and with the friendly: identical |
| Goal-tagged moments | 20, of which 5 on the ball in the main view | `profile["moments"]` |
| His Goal reel | **42.24 s**, 1280x720, 25 fps | `GET /api/players/pl_bro_09/reel.mp4?tag=goal&reason=on_ball_main&order=match` through `TestClient` with an empty cache, measured with ffmpeg |
| Scout "midfielders who win the ball back" | Sami Okafor (Calder Town) 12.82 per 90 (42 in 294.8 min); next Amari Haddad 11.58 | `scout.answer_rules` |
| Scout "forwards with the most take-ons" | Haruki Fontaine (Eastwick United) 2.5 per 90 (8 in 288.2 min) | `scout.answer_rules` (the Foundry agent's example answer says 288 minutes) |
| Scout "forwards who score" | Femi Toure 1.64 per 90 (5 in 274.3 min); next Ustinov 1.04, L. Whitfield 1.03 | `scout.answer_rules` |
| Corners | 107; first event after (touches and pressure skipped): taker's cross 62, carry 21, pass 10, take-on 6, throw-in 5, period end 3 | review-a-final3's rule; the same rule gives 70 of 115 on the season before the star's ratings (rebuilt from 391ff3c's `league.json`) |
| Headed shots | 17, of which 7 within 3 s of the header's own carry | shots with qualifier `header`; the same rule gives 7 of 14 on the season before his ratings (the review's 0.7.0 count was 8 of 14) |

## The dashboard seeds (`src/regista/static/shared/demo.js`)

The previous job (femi-edge) had already rewritten them. Checked here independently, with and without his friendly:

- every clip reference exists by match and clip id, with the same title, `t`, round, reason and video URL;
- the five Summary clips are exactly his five league goals (four matches), the Strengths and sent clips hold his goal
  event, the two Concerns clips hold his failed take-ons;
- every count and rank in Maya's messages, notes and report holds both ways (table above). The claims are league
  counts ("five league goals", "one of his fourteen take-ons in league matches") and ranks among the league's regular
  forwards; his friendly adds shots, shots on target and 3.2 minutes but no goal and no take-on, so nothing flips;
- no goal is called a header.

No change was needed. `tests/test_shared_dashboard.py` (9 tests) passes.

## The realism report (`docs/realism-report.md`)

Regenerated all three runs and compared them with the committed file:

- `python3 -m regista.synth.report --league`: every table row and every line is in the committed report (only the
  heading differs).
- `--profile realistic --seeds 21 22 23 24 25 26 27 28 --minutes 30`: identical rows.
- `--league --repeat 6` (180 matches, 5,422.09 minutes): 13/13, 11/11, 14/14, 4/4, 14/14, role shapes 8/8 hold, as the
  summary table says.

No change was needed.

## What was stale, and fixed

| Where | Said | Now |
|---|---|---|
| `data/synthetic/README.md`, corners | the taker's cross 70 times in 115, carry 18, pass 8, take-on 8, shot 1, throw-in 5, period end 5 (true before the star's ratings) | 62 in 107, carry 21, pass 10, take-on 6, throw-in 5, period end 3 (70 of 115 before); still 45 corners where nobody attacks the box |
| `data/synthetic/README.md`, six-season figures | keepers save about 70%, 43% of unblocked shots on target, take-ons 37%, keepers' long passes 47% | 68%, 44%, 36%, 48% (`--repeat 6`: save_pct 0.681, shot_accuracy_ex_blocks 0.438, take_on_success 0.363, gk_long_pass_share 0.481; before the ratings 0.702, 0.428, 0.369, 0.48) |
| `data/synthetic/README.md`, role shapes over six seasons | touches DM 65, ST 47, W 47; crosses W 7.7; progressive passes ST 1.4; long passes CB 4.0, ST 2.6; tackles won ST 0.8, FB 1.8, DM 3.8; fouls won ST 1.4; 95% of crosses received (strikers 56%) | DM 64, ST 48, W 48; W 7.9; ST 1.5; CB 3.9, ST 2.5; ST 0.9, FB 1.6, DM 3.9; ST 1.7; 94% (strikers 53%). Every order still holds |
| `CLAUDE.md` §4.2 | corners 70 of 115 with 0.7.1; "8 of 14 headed shots come after the header's own carry" (the review's 0.7.0 figure); "Fabric still holds the 0.7.0 season"; 797 tests; part A "not merged" | 62 of 107 (70 of 115 before the ratings); 7 of 17 within 3 s (8 of 14 the review's 0.7.0 count); the fourth Fabric run; 798 plus 13 slow; part A **merge-ready**; the round 6 corner-goal sentence replaced (that goal no longer exists: the round 1 goal at 56' is the one staged as carry then header) |
| `README.md` | "763 tests"; Fabric "holds the 0.7.0 season until it is pushed and checked again" | 798; pushed again and 756 of 756 |
| `docs/criteria.md` | "763 tests"; Fabric pending | 798; pushed and checked, 756 of 756 |
| `docs/architecture.md` | "league mode, generator 0.7.0"; Fabric "Pending" | 0.7.1; the fourth run with its row counts |
| `docs/demo-storyboard.md` | beat 5's 756 of 756 "after the notebook took Regista's percentile rule" (the 0.7.0 season); "Re-sync Fabric" to do; the Fabric shot "on the 0.7.0 season: re-sync first" | 756 of 756 on the season this branch serves; the re-sync marked done with its rows |

## Searches for the previous numbers, and verdicts

```bash
git grep -nE "three goals|3 goals|one a penalty|2 each|Petrov|0\.90|0\.56|0\.67|2\.14|20 shots|299\.8|7 take-ons|23\.6|13\.97|Haddad|2\.47|2\.46|Fontaine|Delgado|797|798|796|761|760|756|0\.7\.0|top scorer" -- . ':!docs/scout-terminal/build' ...
git grep -niE "three league goals|outside the box|from distance|round 5|r02goal|r05goal|r06goal47|r06takeon|ten take-ons|third among midfielders|sixth among|Ustinov|Whitfield|Okafor|42\.2|in four" ...
git grep -nE "of 115|of 111|headed shots|70%|37%|56%|95% of|43%|47% of" ...
```

Every remaining hit is one of:

- **True now** (checked above): the seeds; Femi's 5 goals, 274 minutes, 1.64 and 1.15 per 90, npxG 3.51, the 42.2 s
  reel, Sami Okafor's 12.82, Haruki Fontaine's 2.5 (8 in 288 minutes), the realism report's rows (6.23, 1.15, 1.64,
  2.95 at 274 minutes), "20 goal moments, of which 5".
- **Dated history, worded as such**: the storyboard's "With generator 0.7.0 (checked 2026-10-24) the reel is his three
  league goals ... 23.6 s"; CLAUDE.md's earlier status entries (657, 620, 618, 410 tests); the Fabric first to third
  runs (756, 328 of 756); `tests/test_league_mode.py`'s docstring (5 of 12 with 0.7.0, 11 of 24 with version 2); the
  generator's comments on why `touch_every_s` is 1.92 (a 0.7.0 choice).
- **Not a league number**: names in the generator's surname pool, recap and test fixtures (Brennan, Whitfield, Fontaine
  in other matches); `@media (max-width: 760px)`; detmath constants; `tests/test_fabric.py`'s `checked == 756` (108
  players x 7 stats, a fake Fabric); vision metrics; `scout.py`'s example prompt "compare Amari Ustinov and Hugo Fontaine"
  (both are league players).

## Microsoft Fabric

`az` signed in as Zaid's account (subscription "Azure for Students"). Then:

```bash
REGISTA_DOTENV= python3 -m regista.season.fabric push
REGISTA_DOTENV= python3 -m regista.season.fabric check --json <scratch>/fabric-check.json
```

- **push** (28.0 s): clubs 6, players 108, matches 30, lineups 1,080, events 33,758, clips 10,661, labels 10,661,
  player_season 3,024, uploads 1 rows (uploads read from the Azure store: 1).
- **check**: notebook `regista_leaders_check` run `9f3d8a7c-…` completed in 52 s; 108 players x 7 stats (goals,
  assists, shots, key_passes, take_ons_won, tackles_won, interceptions): **756 of 756 match**, no differences, nothing
  only in Regista or only in Fabric. Femi Toure's five goals are among the matched rows.

## Checks

- `python3 -m pytest -q`: **798 passed**, 13 deselected; `python3 -m pytest -q -m slow`: **13 passed** (Mac, Python 3.13).
- `tests/test_backcompat.py` and `tests/test_shared_dashboard.py`: 18 passed.
- `python3 -m regista.synth.report --league` (and `--repeat 6`, and the realistic profile): as above.
- `python3 -m regista.season.audit`: Femi Toure first with 5 (non-penalty 5, npxG 3.51, 19 shots).
- CI on Linux (Python 3.11), commit d670d90: green. Push run https://github.com/Qadzilla/Regista/actions/runs/40135431517
  (797 passed, 1 skipped; the image's smoke test printed `{"check": "season-pins", "ok": true, ..., "differs": {}}`)
  and PR run https://github.com/Qadzilla/Regista/actions/runs/40135433252.

## Open

- Merging PR #36 and deploying are not this job's. After the deploy, re-check storyboard beats 1, 5 and 7 on the live
  app, read-only: five goals and a 42.2 s reel, the realism verdicts, Sami Okafor.
- The open findings of review closing round 3 (corners, headed shots, progressive passes, `cross_choice`) remain, with
  their counts now recomputed for this season.
- The committed season is a favourable draw (femi-edge.md): any generator change re-draws Brookfield's matches, and
  every number above moves with it.
