# Part A verification, round 2 (independent)

Checked on 2026-10-24 against `feature/terminal-engine` at 66fa5d7 (PR #36), before the fix below. I re-ran every check
myself and did not rely on the builders' reports (determinism.md, femi-edge.md, refresh-2.md). Everything here is
synthetic: the Regista League's players, clubs and matches are generated.

**Verdict: PR #36 is ready to merge.**
- **CI:** green on Linux.
- **Tests:** they pass on the Mac.
- **Back-compat:** 54 generator cases are byte-identical to `main`.
- **Realism:** six pooled seasons sit in every band.
- **Femi Toure:** clearly the league's top scorer, and the per-90 leader for goals, non-penalty goals and npxG. This
  holds in a season built from scratch, which is the season the server builds.
- **Fabric:** holds that same season, and its cross-check matches 756 of 756.

I fixed one small display bug, which two earlier reviews had already reported. The rest is listed under "Open" below.
None of it blocks the merge.

## 1. CI

`gh pr checks 36` at 66fa5d7:

| Job | Result | Time |
|---|---|---|
| test | pass | 11m52s |
| build | pass | 1m29s |
| deploy | skipping | PRs do not deploy |

- **PR status:** mergeable, merge state CLEAN.
- **Last push run** (d670d90, run 40135431517): 797 passed, 1 skipped, 13 deselected.
- **Inside the image:** the smoke test printed `{"check": "season-pins", "ok": true, "differs": {}}`.
- **66fa5d7 itself** changed only a report, so it had no push run.

## 2. Tests on this Mac (Python 3.13.9)

- `python3 -m pytest -q`: **798 passed**, 13 deselected (4 min 40 s).
- `python3 -m pytest -q -m slow`: **13 passed** (1 min 44 s).
- After my fix, the three affected files (`test_league_mode.py`, `test_synthetic.py`, `test_reliability.py`): 74 passed.

## 3. Back-compat: no ratings means no change

I did not rely on `tests/test_backcompat.py`'s recorded hashes alone.
- **Method:** I made a detached worktree of `main` (e3da71d) in the scratchpad and ran the same script against each
  tree's `src`. I confirmed that the `main` import really came from the worktree: it has no `regista.detmath`.
- **Cases (54):**
  - every vision spec: training 101-140, development 201-206, fresh 301-303;
  - the three committed samples (seeds 294, 141, 142, `demo` profile);
  - the 45-minute two-period seed 77 under both `demo` and `realistic`.
- **Result:** the SHA-256 of `events.jsonl` and `tracks.jsonl` is identical in all 54 cases.
- **Committed files:** `git diff main -- data/synthetic/sample` is empty, so the committed sample files are untouched.

## 4. Realism (`python3 -m regista.synth.report --league`, and `--repeat 6`)

| Section | One season | Six seasons pooled |
|---|---|---|
| Event rates | 13 of 13 | 13 of 13 |
| League mode | 10 of 11 (penalties low, 0.1 per 90; indicative) | 11 of 11 |
| Physical (10 Hz) | 14 of 14 | 14 of 14 |
| Team style | 4 of 4 | 4 of 4 |
| Individual leaders | 12 of 14 (shots leader 6.23 against a ceiling of 6.18; top npxG share 0.46 against 0.40; indicative) | 14 of 14 |
| Role shapes | 8 of 8 hold (indicative) | 8 of 8 hold |

These match the committed `docs/realism-report.md` and the reports, apart from the edge case in Open item 1.

**Six-season values for Femi:**
- npxG leader 0.74 per 90, with a lead of 1.56 (band up to 1.75);
- goals leader 1.18 per 90, with a lead of 1.88 (band up to 2.0);
- top npxG share 0.337.

## 5. Femi Toure in the season the server generates

**How I built it.** I built all 30 fixtures from scratch into an empty folder in the scratchpad (68.5 s). That is what
`regista.season.build` does on a fresh server; the Mac's cached `data/season/matches` was not used. `pins.drift()` on
that folder returned `{}`: every fixture's `events.jsonl` matches the pins recorded for the season. CI built the same
season on Linux and also found no drift, in the test job (`test_the_whole_committed_season_is_the_same_on_every_platform`)
and inside the image (`season-pins`). So the Mac and Linux generate the same season, and the numbers below are what users
will see.

**Results on that build, using the terminal's engine (`build_season`) and its qualifying pool of 100.5 minutes:**

| Per 90, qualified | 1st | 2nd | 3rd | Lead |
|---|---|---|---|---|
| Goals | Femi Toure 1.64 (5 in 274.3 min) | Amari Ustinov 1.04 | Leon Whitfield 1.03 | 1.58x |
| Non-penalty goals | Femi Toure 1.64 (no penalties) | Ustinov 1.04 | L. Whitfield 1.03 | 1.58x |
| npxG | Femi Toure 1.15 (3.51) | Ustinov 0.77 | Emeka Dubois 0.53 | 1.50x |

- **Season totals:** Toure 5, Ustinov 3, L. Whitfield 3, then two players on 2. He is two clear, and
  `python3 -m regista.season.audit` lists him first.
- **Non-qualifiers:** some sit higher per 90 on tiny minutes, for example Milan Whitfield at 2.22 from one goal in
  40.6 minutes. They are outside the pool, as on FBref.
- **CI checks this too:** `test_femi_tourés_edge_in_the_terminal` is in the quick suite, so CI asserts the same lead on
  Linux on every push.

## 6. Do players still differ within roles? (`python3 -m regista.season.audit`)

**One season, rounds 1-5 against 6-10, within kit slot (66 starters):**
- **Clearly above 0:** carries 0.66, peak speed 0.77, sprint distance 0.56, shots 0.52, distance 0.52 and passes
  completed 0.45.
- **Weak or none:** goals 0.20, interceptions 0.17, key passes 0.05, tackles -0.01, take-ons -0.04, aerials -0.15 and
  crosses -0.33.

**Six pooled seasons (`data/season/reliability.json`):** 78 of 127 metrics are marked noisy (r below 0.3). Examples:
goals 0.07, npxg 0.26, interceptions 0.02, recoveries 0.07 and take-ons 0.09. The volume and physical metrics separate
players: passes 0.39, touches 0.38, sprints 0.37, carries 0.61 and peak speed 0.90.

- **History.** Every committed version of `reliability.json` looks like this: noisy counts 81 at 0.5.0, 70 at 0.6.0,
  74 at 0.7.0, 76 at 0.7.1, and 78 after the star's ratings. So this is not a regression from the last three jobs.
- **Docs are honest about it.** The terminal and profiles mark noisy metrics, and CLAUDE.md, criteria, architecture and
  README describe it that way.
- **`verify.md` is out of date here.** Its section 4 table (2026-10-23, at 93290f4: goals 0.47, interceptions 0.76) was
  measured on an older generator and no longer describes the league. It is a dated record, not a current claim.
- **Answer:** yes for volume, carrying and physical stats; mostly no for event counts within a role. Open item 2.

## 7. Spot-check: 10 quoted numbers against the fresh build

| # | Where | Claim | Found |
|---|---|---|---|
| 1 | `demo.js` report | "five league goals in four matches", none a penalty | 5 goals, in r01 (x2), r06, r08 and r10; no penalty goals |
| 2 | `demo.js` report | "the most per 90 of its 18 regular forwards" | 18 qualified FW; he leads with 1.64 |
| 3 | `demo.js` report | most shots on target of the league's forwards, total and per 90 | 9, and 2.95 per 90; next is 6 (L. Whitfield 2.05 per 90, Reyes) |
| 4 | `demo.js` report | "four of his five goals from inside 12 metres" | 5.6, 4.4, 11.4 and 8.1 m; the r06 goal is from 15.9 m |
| 5 | `demo.js` report | "Won one of his fourteen take-ons" | 14 attempted, 1 won |
| 6 | `demo.js` shortlist | Delgado (pl_ash_10) is "fourth among midfielders for take-ons won per 90" | 4th: 1.607, just behind Oliveira's 1.614 |
| 7 | storyboard beat 1 | goals at 6' and 56' (r01), 49' (r06), 6' (r08), 8' (r10); 56' is a header | clock minutes 5, 55, 48, 5 and 7 (so 6', 56', 49', 6', 8'); the r01 56' goal is `body_part: head` |
| 8 | storyboard beat 7 | Sami Okafor 12.82 recoveries per 90, 42 in 294.8 min, top midfielder | exactly that; Amari Haddad is 2nd with 11.58 |
| 9 | Scout example answer | Haruki Fontaine 2.5 take-ons won per 90, 8 in 288.2 min | exactly that (Ivan Whitfield is 2nd with 2.48) |
| 10 | `data/synthetic/README.md` | six seasons: about 44% of unblocked shots on target, keepers save about 68%, take-ons succeed about 36% | `--repeat 6`: 0.438, 0.681 and 0.363 |

All ten hold. I did not re-render the Goal reel (42.2 s); refresh-2.md rendered it at 42.24 s.

## 8. Microsoft Fabric (read-only)

- **Cross-check:** `python3 -m regista.season.fabric check --no-run` reads the tables already in OneLake and runs no
  notebook. It reported 108 players x 7 stats, **756 of 756 match**.
- **Is it the season the server builds?** I read three tables from the lakehouse and compared them with
  `season_tables()` on my from-scratch build:
  - `player_season`: 3,024 of 3,024 rows identical.
  - `clips`: 10,661 of 10,661 identical.
  - `events`: 33,758 rows on both sides. 38 rows differ only in how a whole coordinate is typed (`"x": 1.0` from
    Arrow, `1` locally). The values are the same.
- **Writes:** I wrote nothing to Fabric, Azure or the live app.

## 9. Fixed here

**Leader-gap rows printed a ratio as minutes.**
- **Symptom:** `render_markdown` showed "leader_npxg_gap | 1.5 ratio (1.5 min)".
- **Cause:** it looked up `key.replace("_per90", "_minutes")`, which returns the gap key itself.
- **History:** review-b-final2 and review-b-final3 had both reported this, and it was still open.
- **Fix:** minutes are now shown only for `_per90` leader rows. The test asserts that both gap rows carry no minutes
  and that a per-90 row still does.
- **Docs:** `docs/realism-report.md` updated. Its two rows now match the regenerated output exactly.
- **Files:** `src/regista/synth/report.py`, `tests/test_league_mode.py`, `docs/realism-report.md`.
- **Commit and CI:** ad3c726, green on Linux.
  - Push run https://github.com/Qadzilla/Regista/actions/runs/40138559323: test and build pass, 797 passed and
    1 skipped. The smoke test inside the image printed `season-pins` ok with `differs: {}`.
  - PR run https://github.com/Qadzilla/Regista/actions/runs/40138561975: success.

## Open (none blocks the merge)

1. **The goals-leader verdict uses a rounded value.** `leader_goals_per90` is 5 x 90 / 274.3 = 1.6405, rounded to
   1.64 before the comparison. The ceiling is 2 x 0.82 = 1.64, so one season reports "in band" when the unrounded
   value is just above it. Strictly, the one-season leaders would be 11 of 14, not 12 of 14. This is indicative only,
   since one season is not a verdict, and six seasons give 1.18. I did not change the rule: every metric in the report
   rounds this way, and changing it would move quoted figures in several docs. It is your call.
2. **Event counts barely separate players in the same role** (section 6). Most of them are noisy even over six seasons,
   and the terminal says so. If the Scout story leans on "players differ", lead with volume, carrying and physical
   stats, which do separate players.
3. **The committed season is a favourable draw for Femi,** as femi-edge.md says (all three leads in 8 of 24 seasons).
   Any generator change re-draws Brookfield's matches, which means redoing the pins, the seeds, the quoted numbers and
   the Fabric push.
4. **Review closing round 3's findings are still open:** corners (62 of 107 followed by the taker's cross), headed shots
   (7 of 17 within 3 s of the header's own carry), progressive passes, and `cross_choice`. Femi's 56' goal is one of
   those headed shots, and the storyboard already says not to call it a header.
5. **After you merge and CI deploys,** check storyboard beats 1, 5 and 7 on the live app without writing anything: five
   goals and a 42.2 s reel, the realism verdicts, and Sami Okafor.
