# Stale-number check after the league was regenerated (2026-10-24)

An independent check, branch `feature/terminal-engine` on top of 543acee. I searched the whole repository for numbers and
claims about the old league and the old Femi Toure: `src/`, `docs/`, `README.md`, `CLAUDE.md`, `tests/` and
`data/synthetic/README.md`. The reports in `docs/scout-terminal/build/` were left out because they are history. For each
hit, the verdict is still true (proved by running the code), stale (fixed here), or history (a dated record that was true
when written). Everything ran offline with `REGISTA_DOTENV=` exported. Nothing was written to the live app, Azure or Fabric.

## Searches

```bash
P='6 goals|six goals|1\.78|1\.8 per 90|11 matches|10 matches|304 minutes|303\.9|301 minutes|300\.7|756|5\.92|2\.07|88%|20 shots|17 shots|24 goal moments|8-minute|8 minutes|0\.2 s|Kenan Nakamura|17\.96|top scorer|top-scorer'
grep -rnE "$P" src docs README.md CLAUDE.md tests data/synthetic/README.md | grep -v '^docs/scout-terminal/build/'
grep -rnE "Femi|Toure|pl_bro_09" ...                     # every claim about the star
grep -rnE "thirty-minute|30-minute|22 per-90|three ratios|Kenan|Haddad|13\.97|595 tests|760 tests|0\.76 recall" ...
grep -rnE "(generator 0\.[3-6]|0\.[3-6]\.0:)" ...         # claims tied to an older generator version
grep -rnoE "<number> (of N|goals|matches|minutes|per 90|...)" src/regista/static   # prose numbers in the pages
```

None of `1.78`, `1.8 per 90`, `304 minutes`, `303.9`, `300.7`, `5.92`, `17 shots`, `24 goal moments` as a current claim,
`8-minute`, `8 minutes`, `0.2 s` or `17.96` occurs outside history. `Kenan Nakamura` occurs only in `docs/redesign/` review
records. The remaining hits follow.

## The facts the checks rest on (re-run here)

| Fact | Value now | Command |
|---|---|---|
| Femi Toure | 10 appearances, 299.8 min, 3 goals (1 a penalty), 20 shots, 9 on target, 7 take-ons with 1 won; goals per 90 0.90 | `load_season("data/season/league.json", "data/season/matches").player("pl_bro_09")` |
| Top scorers | Femi Toure 3; Kenan Petrov, Milan Brennan, Amari Ustinov 2 | same season, and `python3 -m regista.season.audit` ("Femi Toure ... goals 3 (non-penalty 2, npxG 2.14, 19 shots)") |
| Forwards who qualify | 18 (pool 100.5 minutes) | `scout.search_players(s, position="FW", ...)["matched"]`, `min_minutes` 100.5 |
| His goal moments | 12 tagged goal among his moments, of which 3 are on the ball in the main view | `p["moments"]` filtered by tag `goal` and `reason` |
| His Goal reel | 23.60 s, 1280x720 | `GET /api/players/pl_bro_09/reel.mp4?tag=goal&reason=on_ball_main&order=match` through `TestClient`, then measured with ffmpeg |
| Scout "midfielders who win the ball back" | Amari Haddad (Ashby Athletic) 13.97 per 90 (45 in 290 minutes) | `scout.answer_rules(s, "midfielders who win the ball back")` |
| Scout "forwards with the most take-ons" | Haruki Fontaine (Eastwick United) 2.47 per 90 (8 in 292 minutes) | `scout.answer_rules(s, "forwards with the most take-ons")` |
| Realism, one season | event rates 13 of 13, league mode 10 of 11 (penalties low, indicative), physical 14 of 14, team style 4 of 4, leaders 12 of 14 (indicative), role shapes 8 hold | `python3 -m regista.synth.report --league` (the committed `docs/realism-report.md` has the same rows; only its headings differ) |
| Realism, six pooled seasons | 13/13, 11/11, 14/14, 4/4, 14/14; take-on success 0.371 | `python3 -m regista.synth.report --league --repeat 6` |
| Realistic profile | 13 of 13 | `python3 -m regista.synth.report --profile realistic --seeds 21 22 23 24 25 26 27 28 --minutes 30` |
| Catalogues | 28 per-90 stats and 4 ratios; 127 player metrics in 8 groups; 19 team metrics | `season_api.stat_catalogue()`, `metrics.CATALOGUE`, `metrics.TEAM_CATALOGUE` |
| Touch records | 561.6 per team per 90 in the committed season | count of `touch` events in `data/season/matches/rl_*` / 60 team-matches x 3 |
| Match length | 2 x 15 minutes (`league.json` generator `minutes: 15.0, periods: 2`) | `data/season/league.json` |
| Generation time | 1.18 s median of five for fixture 0 here (CLAUDE.md says about 1.3 s: same order, kept) | `audit._stream(generate_kwargs(...))`, timed |
| Toure outright top scorer over 12 regenerated seasons | 5 of 12 (seasons 0, 3, 6, 7, 8); a season's top scorer has 3 to 6 goals | `season_matches(league, seasons=12)` then `top_scorers` per season |

## Every hit and its verdict

### Fixed (stale)

| Where | What it said | Verdict and fix |
|---|---|---|
| `src/regista/cloud/foundry.py:483` (the Foundry Scout agent's instructions) | example answer "Amari Ustinov (Ashby Athletic) wins the most take-ons among forwards, 3.29 per 90 (11 in 301 minutes)" | **Stale.** Ustinov now has 1 take-on won. A model can repeat the example, so it now uses the rules Scout's current answer: "Haruki Fontaine (Eastwick United) ..., 2.47 per 90 (8 in 292 minutes)". A new test, `test_the_scout_agents_example_answer_holds_in_the_committed_league` (`tests/test_scout_agent.py`), checks the example against `search_players` on the committed league, so the next regeneration cannot leave it stale. |
| `src/regista/mcp_server.py:163` (the `search_players` tool description, flagged by the docs job) | "pass_accuracy, take_on_success and shot_accuracy are ratios" | **Stale:** `aerial_win` is the fourth ratio. The list is now built from `profiles.RATIOS`, so it reads "pass_accuracy, take_on_success, shot_accuracy and aerial_win are ratios" and follows the code from now on. |
| `tests/test_league_mode.py:581` (docstring of the slow npxG test) | "generator 0.6.0: he is the outright top scorer in 4 of 12 regenerated seasons ...; a season's top scorer has three or four goals" | **Stale for the current generator.** With 0.7.0 it is 5 of 12, and a season's top scorer has 3 to 6 goals (the 12-season run above). Now reads "generator 0.7.0: ... 5 of 12 ...; three to six goals; 4 of 12 with 0.6.0". |
| `data/synthetic/README.md:196` | "the committed season has the star as its outright top scorer and every one-season band in" | **Imprecise.** On one season penalties read low and the leaders 12 of 14, both marked indicative. Now reads "every band one season can judge in (penalties and the individual leaders are judged over six pooled seasons)". |
| `docs/scout-terminal/regista-data.md:1-12, 43, 48, 166, 273` | an audit of `main` at 9b00972: every starter about 301 minutes and plays every minute, 3 ratios, a 40% pool, "CLAUDE.md §2.5 says 8 minutes, which is stale" | **A snapshot, true of that commit, misleading now.** The body is kept as research history, with a note added under its header: league mode added substitutions (most minutes now 301.6), 28 per-90 stats and 4 ratios, FBref's rule with the 100.5-minute pool, §2.5 now says 2 x 15 minutes, and where the current figures are. |
| `tests/test_league_mode.py:30` (comment) | "penalties and red cards are rare (about 0.07 and 0.03 a 30-minute match)" | **Stale for red cards.** Six pooled seasons give 0.2 penalties and 0.17 red cards per 90 (`--repeat 6`), so about 0.07 and 0.06 per 30-minute match. The comment now says so. "One penalty and two red cards" in the committed season still holds: one season reads 0.1 and 0.2 per 90 over about ten full matches. |
| `README.md:153`, `CLAUDE.md:505`, `docs/criteria.md:20` | "760 tests" | **Stale after this commit's new test:** now 761 (`python3 -m pytest -q`: 761 passed, 12 deselected). |

### Not fixed: needs a product or code decision outside this job

| Where | What | Why it is left |
|---|---|---|
| `src/regista/synth/generator.py:144` (a comment on `touch_every_s`) | "every one-season band in", the same imprecision as the README line fixed above | `generator.py` is in `season.build.BUILT_BY` and `GENERATED_BY`. Editing even a comment changes `code_fingerprint`, which marks `data/season/reliability.json` stale and rebuilds every match folder. The README now carries the precise wording. Fix the comment in the next real generator change. |
| `src/regista/cloud/fabric_notebook.py` `LEADERS_SQL` | The Fabric cross-check matches 328 of 756 rows, because the notebook still ranks percentiles the old way | This is a code change, and it can be proved only by running the notebook in Fabric, which this job may not do. `docs/architecture.md:273-283`, `docs/criteria.md:16`, `README.md:119`, `CLAUDE.md:507-510` and `docs/demo-storyboard.md:39,56-62` all state this correctly as pending. |

### Still true (proved by the commands above)

| Where | Claim | Proof |
|---|---|---|
| `src/regista/static/shared/demo.js:82,108,120` | "Three league goals, more than anyone else in the league"; "top scorer ..., the most per 90 among the league's regular forwards"; "the most per 90 of its 18 regular forwards" | 3 goals vs 2, goals-per-90 rank 1 of 18 qualifying forwards; pinned by `test_seeded_claims_hold_in_the_league` |
| `demo.js:62-70` clip refs | his goals in rounds 2 (50'), 5 (15') and 6 (47'), and take-ons in rounds 6 (3') and 9 (2') | `tests/test_league_mode.py::test_every_clip_the_demo_cites_exists_and_shows_what_its_title_says` (passes) |
| `docs/demo-storyboard.md:35` (beat 1) | three league goals, the most in the league, rounds 2/5/6, a 23.6 s reel | season facts, and the reel rendered and measured: 23.60 s |
| `docs/demo-storyboard.md:39` (beat 5) | one season 13 of 13 event rates and 14 of 14 physical; six pooled seasons every band | `regista.synth.report --league` and `--repeat 6` |
| `docs/demo-storyboard.md:41` (beat 7) | Amari Haddad 13.97 per 90, 45 in 290 minutes | `answer_rules` |
| `docs/demo-storyboard.md:49-55` | "24 goal moments for Toure then, of which 6 on the ball; 12 now, of which 3"; "six goals and 44 s before player ratings"; reel 23.6 s at 1280 wide | 12 and 3 counted from his moments, the same list that `/api/players/{id}/moments?tag=goal` returns; "24/6" and "six goals, 44 s" are labelled as the past; the reel was measured |
| `docs/demo-storyboard.md:38` (beat 4) | shots 17 s, identity 2 min 6 s | the Azure job run of 2026-10-22 (CLAUDE.md §4.1), with no league numbers in it |
| `CLAUDE.md:248, 374, 505` | top scorer with 3 league goals (one a penalty, rounds 2, 5, 6); the audit lists Femi first; 13/13, 14/14, 10/11, 12/14; reel 23.6 s | season facts, `regista.season.audit`, report runs, reel measured |
| `CLAUDE.md:138-148` (§2.5 data bullet) | 30 matches of 2 x 15 minutes; a regular about 300 minutes; about 1.3 s a match; 5.9 s cold on 10 cores | `league.json`; most minutes 301.6; 1.18 s measured here (same order, so kept); the cold build was not re-timed |
| `README.md:66-80` | 30 matches of two 15-minute halves, squads of 18, 28 per-90 stats and four ratios, a 100.5-minute pool, 127 and 19 metrics, 13 of 13 and 14 of 14, every band over six seasons | `stat_catalogue()`, `search_players` `min_minutes`, `CATALOGUE`, report runs |
| `src/regista/static/product/index.html:218-219` | realistic setting, eight 30-minute matches, all 13 measures in range | `--profile realistic --seeds 21..28 --minutes 30`: 13 of 13 |
| `data/synthetic/README.md:190, 194` | take-ons succeed about 37% over six seasons; about 560 touch records per team per 90 | 0.371 pooled; 561.6 counted |
| `src/regista/synth/report.py:70,194,641,706`, `season/metrics.py`, `season/league.py:25`, `season/build.py:5`, `season/reliability.py:17`, `static/product/app.js:354` | league matches last 30 minutes; a season is 30 thirty-minute matches | `league.json` (15-minute halves, 2 periods, 30 fixtures) |
| `docs/architecture.md:123`, `README.md:136` | the audit prints the top scorers | `python3 -m regista.season.audit` |
| `docs/architecture.md:269-283`, `docs/criteria.md:16`, `README.md:119`, `CLAUDE.md:507-510`, `docs/demo-storyboard.md:39,56-62` | "756 of 756 on 2026-10-23"; "328 of 756 on 2026-10-24"; 108 players x 7 stats; 462 rows with a percentile | dated records of the Fabric runs; 756 = 108 x 7 still holds; the 2026-10-24 numbers are the Fabric job's notebook run |
| `src/regista/static/scout/scout.js:741`, `docs/redesign/dashboards/review-b-pass1.md:46` | "Higher than 88% of the league's midfielders" | an example of wording in a code comment, not a league number |
| `src/regista/static/player/profile-view.js:308` ("Goal 16"), `static/product/app.js:935` ("53 runs in 34 matches"), `season/summaries.py:185` ("assist at 13'"), `season/scout.py:379` (example question) | illustrative strings in comments and docstrings | not presented as league facts |
| `README.md:62` | the live upload had 5 moments and joined Femi Toure's profile | the live record of 2026-10-22 (pv_8807d7835c), unrelated to the regenerated league |

### History (dated records, left as they are)

| Where | Old numbers it quotes |
|---|---|
| `CLAUDE.md:518` (entry "Earlier, 2026-10-23 (evening)") | "Femi's 11 matches with his friendly". This was true then on the live app, and is still 10 league matches + 1 friendly. |
| `CLAUDE.md:536-538` (the "Earlier, 2026-10-23" and "2026-10-22" entries) | 756 of 756, 595 and 551 tests |
| `docs/architecture.md:265-270` ("First run, 2026-10-23") | the old season's Fabric row counts |
| `docs/redesign/dashboards/review-b-pass1.md:65`, `review-b-pass2.md:52`, `review-a-pass2.md:76`, `safeguard.md:82-84`, `scout.md:39` | 11 matches, 1.78 and 5.92 per 90, "Six goals in eleven games", Femi's 6 goals |
| `docs/redesign/review-a-pass2.md:32`, `review-a-pass3.md:31`, `review-b-pass2.md:44`, `review-b-pass3.md:27` | the Scout link to Kenan Nakamura on an old deep link |
| `docs/redesign/home.md:200` | "21 moments in 10 matches" (a sample reply in a build record) |
| `docs/vision.md:215` | "0.60 / 0.33 -> 1.00 / 1.00" (a vision result; a grep false positive on `0.33`/`1.00`, unrelated to the league) |
| `docs/scout-terminal/industry-metrics.md:293,299,400` | FBref's 30-minutes-per-squad-game rule and a VAEP paper id: external facts, not the league |

## Tests

- `python3 -m pytest -q`: **761 passed**, 12 deselected (231 s). One new test pins the Foundry example answer.
- `python3 -m pytest -q -m slow`: **12 passed** (97 s). The only slow-suite edit is a docstring.
- Back-compat: no generator, schema, sample or vision file changed. `generator.py` was edited and then reverted, to keep
  `code_fingerprint`.
