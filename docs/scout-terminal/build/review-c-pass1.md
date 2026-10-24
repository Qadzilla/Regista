# Review C, round 1: the refresh (part C)

Independent review of part C on `feature/terminal-engine` at 38deb43: commits 462a47f (demo.js seeds), 543acee (docs and
demo) and 38deb43 (stale-number check). The review covers the seeds in `src/regista/static/shared/demo.js`,
`docs/demo-storyboard.md`, `docs/realism-report.md`, README, `docs/criteria.md`, `docs/architecture.md`, CLAUDE.md, the
Fabric re-sync result and the stale-number check (`stale-check.md`). Everything ran offline with `REGISTA_DOTENV=`
exported. The only requests to the live app were two read-only GETs, used to compare it with the branch. Nothing was
written to the live app, Azure or Fabric, and no file other than this one was changed.

**Verdict: not signed off.** One thing must be fixed and four should be. The seeds' numbers, the realism report, the
Scout examples and the test counts are all true for the new league (checked below). What fails:

- the Fabric cross-check, which this branch broke;
- a false sentence in the contract doc;
- a storyboard that says to record against the live app, where these numbers are not yet true;
- open closing-round-3 findings missing from CLAUDE.md's "Left" list;
- the demo showcasing a header that the generator stages as a ground carry followed by a header.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 761 passed, 12 deselected (235 s) |
| `python3 -m pytest -q -m slow` | 12 passed (95 s) |
| `git diff --stat main..HEAD -- data/synthetic/sample models` | empty: the committed samples are byte-identical to `main` (`tests/test_backcompat.py` passes in the suite) |
| `python3 -m regista.synth.report --league --out <scratch>` | every table row also appears in the committed `docs/realism-report.md` (`comm -23` on the sorted rows is empty); 13/13, 10/11, 14/14, 4/4, 12/14 |
| Season facts (`load_season(api.SEASON_LEAGUE, api.SEASON_ROOT, [], [])`) | Femi Toure: 10 appearances, 299.8 min, 3 goals (1 penalty), 20 shots, 9 on target, 7 take-ons with 1 won. Next best scorers have 2. Pool 100.5 min, 18 qualifying FW, 18 MF, 24 DF |
| Ranks behind the shortlist notes (sorted by per 90 among qualifying players, values printed to check for ties) | Femi FW goals 1st (0.901 vs 0.666); FW shots on target 1st (2.70 vs 1.84; 9 in total vs 6, also 1st among all forwards, whatever their minutes); Hugo Delgado MF take-ons won 3rd (1.638; 2nd 2.108, 4th 1.472); Amari Ustinov FW shots 3rd (3.997; 2nd 4.597, 4th 3.39); Farid Vargas MF passes 2nd (59.43; 1st 60.41, 3rd 57.15); Gino Mensah DF key passes 5th (0.651; 6th 0.625). No ties |
| Goal events | r02 `ev_000699`: qualifier `penalty`, 11 m. r05 `ev_000506`: shot from x 25.7 m, y 38.2 (outside the 16.5 m box), 26.07 m. r06 `ev_000589`: `body_part` head, 9.6 m, corner by t_home_07 at 1000.5 s, cross at 1003.5 s |
| Scout examples | Amari Haddad MF recoveries 13.97 per 90 (45 in 290.0 min); Haruki Fontaine FW take-ons won 2.47 (8 in 292.0) |
| `python3 -m regista.season.metrics --rank goals --position FW`, `--player pl_bro_09`; `python3 -m regista.season.audit` | run as documented; Femi first for goals (0.9, pct 97); the audit lists him first among top scorers |
| Round 6 goal clip, rendered offline (`TestClient` GET `/api/matches/rl_r06_bro_eas/clips/cl_t_home_09_000012.mp4`, 5.48 s) | contact sheet checked; tag line reads "carry, dribble, shot, goal, header" (see should-fix 4) |
| Live app, read-only GET `/api/players/pl_bro_09` | 11 appearances, 303.9 min, **6 goals** (main's league); the friendly's one moment is a shot, not a goal |
| `src/regista/cloud/fabric_notebook.py` | `LEADERS_SQL` uses a 40% pool (L72), `RANK()-1` over `(n-1)` (L77, L82) and per-90 rounded to 2 decimals (L58). The Fabric job's diagnosis is accurate. No test checks the SQL's rule against `profiles._percentiles` |

## Must fix

### 1. The Fabric cross-check fails, and this branch broke it

**Where:** `src/regista/cloud/fabric_notebook.py` `LEADERS_SQL` (L34-L82).

The notebook matched 756 of 756 rows on `main` (2026-10-23). After commit 253c2e9 changed
`profiles._percentiles`, it matches 328 of 756. The new rule is FBref's average of strictly-below and at-or-below, with
a third-of-club-minutes pool (100.5) and unrounded rates. `LEADERS_SQL` still ranks with `(RANK()-1)/(n-1)`, a pool of
40% of the top player's minutes, and per-90 rounded to 2 decimals.

The docs record this honestly as pending (README, criteria, architecture, storyboard, CLAUDE.md §4.2). Even so,
Microsoft Fabric is one of the named hero technologies, and its only evidence of correctness is now a failing check. The
fix is known and small:

- the pool: `appearances > 0 AND minutes_raw >= ROUND(max club minutes / 3, 1)`;
- the rank value: `ROUND(n * 90 / minutes_raw, 6)`;
- the percentile: `BROUND(50 * (strictly_below + at_or_below) / n, 0)` where n > 1.

Then:

- add a test that applies the SQL's rule to the season tables offline (Python) and compares the result with
  `Season.build`'s percentiles, so the two cannot drift apart again;
- run `REGISTA_DOTENV= python3 -m regista.season.fabric check`;
- replace "328 of 756 ... fix pending" in the five docs with the new result.

## Should fix

### 1. The storyboard says to record on the live app, but beats 1, 5 and 7 are true only after this branch is deployed

**Where:** `docs/demo-storyboard.md` L4, L16 ("Record against https://regista-api..."), beats 1, 5 and 7, and "To build
before recording".

The table says "all live unless noted". Beat 1 promises "his three league goals ... the reel runs 23.6 s". Beat 5
shows "14 of 14 physical measures at 10 Hz". Beat 7 names Amari Haddad at 13.97 per 90. All three hold only for the
league on this branch.

The live app serves `main`'s league. A read-only GET today gives Femi Toure 6 goals in 303.9 minutes, and main's
storyboard named Kenan Nakamura for beat 7. The storyboard notes the merge only for the terminal's engine (L24-25).

Add "merge and deploy `feature/terminal-engine`, then re-check beats 1, 5 and 7 on the live app" to "To build before
recording". Also note under the table that these beats depend on that deploy.

### 2. The contract doc says a corner is always a cross; in the committed season 45 of 111 are not

**Where:** `data/synthetic/README.md` L218: "A corner from the flag is always a cross."

Over the committed season, the first event after each corner, skipping touch and pressure:

| What follows the corner | Count |
|---|---|
| cross by the taker | 66 |
| carry | 18 |
| pass | 9 |
| take-on | 7 |
| shot | 1 |
| period end | 5 |
| throw-in | 5 |

review-a-final3 should-fix 1 named this sentence. The stale check edited the same file (L196) but left this line.
Either correct the sentence to what 0.7.0 does, or fix `_corner`/`_set_piece` so that someone attacks the box, which is
review-a-final3's fix.

### 3. CLAUDE.md §4.2 leaves the open closing-round-3 findings out of "Left"

**Where:** CLAUDE.md §4.2 "As of 2026-10-24" ("after two review rounds and three closing rounds ... Left: that fix,
part B, ...").

Closing round 3 was not signed off. Its open should-fixes:

- review-a-final3 1: nobody attacks the box at corners;
- review-b-final3 1: headed shots and goals at about half the Premier League rate;
- review-b-final3 2: progressive passes low in every role;
- review-b-final3 3: wide players in the crossing zone almost always cross.

No commit addresses them, and CLAUDE.md, the source of truth, does not say whether they are deferred or accepted. List
them under "Left", or record the decision to accept them for the submission.

### 4. The demo showcases a "header from a corner" that the generator stages as a 4 m dribble and then a header

**Where:**

- `demo.js` (Tomas's message "Your header from a corner"; the report's Strengths "in the air", citing `r06goal47`);
- `docs/demo-storyboard.md` beat 1 ("a header from a corner");
- `CLAUDE.md` §2.10.

The round 6 goal's events:

1. the corner, 1000.5 s;
2. the cross to t_home_09, 1003.5 s;
3. Femi's first touch;
4. a `carry` with qualifier `dribble`, 4.0 m along the ground, 1006.1-1007.6 s;
5. the shot with `body_part: head`.

The rendered clip's tag line reads "carry, dribble, shot, goal, header". Across the committed season, 8 of the 14
headed shots come after the header's own carry within 3 s. This is the mechanism behind review-b-final3 1 (a completed
cross becomes an ordinary possession). Part C put it in front of a viewer in a scout's message and possibly in the
hook. A football-literate judge will read "dribble ... header" as wrong. Either give crosses a first-time finish branch
(review-b-final3's fix), or stop citing this goal as a header from a corner until that branch exists.

## Nits

- `tests/test_shared_dashboard.py::test_seeded_claims_hold_in_the_league` proves "struck from outside the box" with
  `shot_distance_m > 18`. That does not prove outside the box: a shot from inside the area can be up to 26.05 m from the
  goal. It holds here because the shot is from x 25.7 m. Check the distance from the goal line (`pitch.x`, or
  `105 - x`, depending on direction) > 16.5 instead.
- CLAUDE.md L555 "Built and working: event-stream contract (schema 0.1.1)" is stale beside §3's schema 0.2.0.
- `docs/architecture.md` (Fabric second run): "which ranking on `minutes_raw` avoids" states as fact something that
  has not run. Say "should avoid" until the fixed SQL has been checked.
- Storyboard beat 5's voiceover, "with the truth for every frame, in Microsoft Fabric", reads as if the frame-level
  truth is in Fabric. The lakehouse holds clubs, players, matches, lineups, events, clips, labels, player_season and
  uploads: no tracks and no physical records.
- There are two meanings of "regular": the percentile pool is a third of a club's minutes (100.5), while the physical
  bands use 40% of the most minutes anyone played (`report.py` L166). Both are documented, but a reader comparing the
  realism report with Scout may trip.
- Femi's shots differ by engine: the profile counts 20 shots and 9 on target (6.0 and 2.7 per 90, penalties included),
  while `regista.season.metrics` gives 5.7 and 2.4 per 90 (FBref's rule, penalty kicks excluded). The demo.js claims
  hold under both, but the profile and the terminal will show different numbers for the same label.
- `src/regista/synth/generator.py` L144's "every one-season band" comment is still open (stale-check's decision, fine
  to fold into the next generator change; generator changes are due anyway for should-fixes 2 and 4).

## Confirmed true (no action)

- **demo.js** (pinned by the new tests): every seed claim; every cited clip (match, clip id, title, t, round, reason)
  exists and holds the goal or failed take-on its text names; the round 5 goal is from outside the box and the round 6
  goal is headed after a corner.
- **Storyboard:** "12 goal moments now, of which 3" and the 23.6 s reel (stale-check's measurement; not re-rendered
  here).
- **Docs:** README, criteria, architecture and CLAUDE.md agree with the code on:
  - 28 per-90 stats and 4 ratios; the 100.5 pool;
  - 127 and 19 metrics; 2 x 15-minute matches;
  - 761 tests plus 12 slow, and the nightly `slow-tests.yml` (cron `17 4 * * *`);
  - the hidden ratings' names in `league.json`.
- **Realism report:** its rows match a fresh `--league` run.
- **Fabric:** the job's figures (push row counts; 328 of 756) are recorded consistently in all five docs.
