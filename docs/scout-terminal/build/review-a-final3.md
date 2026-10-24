# Review A, closing round 3: engineering

Reviewer A, closing round 3. I read `git diff main...HEAD` on `feature/terminal-engine` at 83484e2, which is generator
0.7.0 plus the closing round 2 fixes. I read the earlier reviews and fixes first (`review-a-pass1/2`,
`review-a-final1/2`, `review-b-*`, `review-fixes-1/2`), then went through 83484e2 line by line:
- `_league_pass`, `_pick_cross_target`, `long_ball_role` and `carry_role` in the generator;
- `push_role`, `width_pull` and the striker's `box_push` in `_move_league`;
- `TOUCH_RECORDS` and the `REALISM` changes in `season/metrics.py`;
- the new role shapes and cross diagnostics in `synth/report.py`;
- the re-recorded pins, `demo.js`, the storyboard and `data/synthetic/README.md`.

I ran every check myself and fixed nothing.

**Not signed off.** Nothing must be fixed. One thing should be fixed: **at corners nobody attacks the box.** Generator
0.7.0 now turns some corners into 50-83 m passes back toward halfway, and the contract doc says a corner is always a
cross. Everything closing round 2 asked of review A is done (checked below).

## What I checked myself

- **Back-compat, independently of the branch's test.** I made a detached worktree at main (e3da71d). One script ran
  against main and against HEAD, each importing its own `src` (asserted). It hashed events and tracks for:
  - every vision training seed (101-110), event-training seed (111-140), development seed (201-206) and fresh seed
    (301-303);
  - the `demo` and `realistic` profiles on seeds 5 and 900;
  - two Player-view friendlies (`friendly_kwargs`, from each side's own league file);
  - `derive_clips` for every player of the four committed samples.

  All **59 of 59** are identical. `git diff main...HEAD -- data/synthetic/sample` is empty, and `tests/test_backcompat.py`
  passes. Every 0.7.0 change is behind `self.league`, `_move_league` or `_league_pass`. The worktree is removed.
- **Determinism.** A cold `build_all` into an empty folder under `PYTHONHASHSEED=4242` gives the same files as the local
  `data/season/matches`, byte for byte (`diff -rq`, tracks aside). `_pick_cross_target` sorts its candidates by player id.
- **Tests.**
  - `python3 -m pytest -q`: 759 passed, 12 deselected, in 7 min 16 s. Another agent's pytest ran alongside, so the time
    is inflated. The slowest part A items in the fast suite are module setups of three league fixtures (4.9 s), the
    demo-clip test (4.3 s) and the league renderer test (3.2 s). Nothing new is slow.
  - `python3 -m pytest -q -m slow`: 12 passed in 3 min 19 s. The reliability recompute takes 81 s and the six-season pool
    75 s.
- **Report and audit on the committed season** (12 s and 8 s):
  - event bands: 13 of 13;
  - league-mode bands: 10 of 11 (penalties 0.10 per 90, indicative on one season);
  - physical and style bands: all in;
  - role shapes: all 8 hold;
  - leaders: 12 of 14 (interceptions 3.08 and top_npxg_share 0.43 are high, both indicative).
  - Femi Toure is outright top scorer with 3 (one a penalty). Ustinov, Brennan and Petrov have 2 each.
- **Contract numbers.**
  - The committed season has 11,233 touch records, which is **559 per team per 90** ("about 560": right).
  - Cross starts by role are all within 35.2 m. Strikers, wingers and the 10 receive 97% of completed crosses.
  - relocated_per90_m is 41.0.
- **The touch-record text.** `TOUCH_RECORDS` computes the integral correctly: 2.5 / 1.0533 = 2.37 s, served as "2.4 s".
  The new test samples the generator's own rule against it.
- **API, probed with TestClient on the local season.**
  - `/api/metrics` cold: 1.8 s. Reliability is not stale.
  - The `touches`, `crosses`, `progressive_passes`, `progressive_carries` and `long_passes` texts match the code.
  - Validation holds: an unknown metric, `limit=0`, an unknown metric in a list, or `age_min` above `age_max` gives 422;
    a bad id gives 400; an unknown player gives 404.
- **Every re-recorded `demo.js` and storyboard claim holds:**
  - Toure is 1st of 18 forwards for goals per 90; his three goal clips exist under the cited ids.
  - pl_ash_10 is 3rd of 18 midfielders for take-ons won.
  - pl_ash_09 is 3rd of 18 forwards for shots.
  - pl_dun_06 is 2nd of 18 midfielders for passes.
  - pl_eas_03 is 5th of 24 defenders for key passes.
  - Toure won 1 of 7 take-ons.
  - The rules Scout answers "midfielders who win the ball back" with Amari Haddad.
- **Python 3.11.** None of 83484e2's added lines nest f-string quotes.

## Closing round 2 findings, checked

| Finding | Verdict |
|---|---|
| Crosses aimed at the build-up target | Fixed: the cross is decided first and aimed among outfielders within 34 m of the goal line. Committed season: CB and CM get 2.8% of completed crosses, DM and FB none. But see the should-fix below: at the moment of the cross the area is almost always empty |
| Touch-interval text | Fixed in the served text, which is generated from the parameters and tested. README and the generator comment say 2.3 s (nit) |
| Full-backs' crosses from their own half | Fixed: the zone is measured from the opponent's goal line; FB median start 35.2 m |
| Defenders' progression and FB touches | Fixed as far as claimed: the three new sourced role shapes hold. The remaining gaps carry "likely" notes, as asked |

## Should fix

### 1. Nobody attacks the box at corners, so 0.7.0 turns some corners into long passes back toward halfway, and the contract doc says a corner is always a cross

**Where:**
- `src/regista/synth/generator.py`:
  - `_corner` (L1673) calls `_set_piece` with no `also` positions;
  - `_move_league` (L820 and its dead-ball branch) works out `att = self.last_team if live else None`;
  - `_league_pass` (L1793-1800) and `_pick_cross_target` (L1500);
- `data/synthetic/README.md` L217;
- the `cross_choice` comment (generator L226).

**Mechanism.**
- During the corner's dead ball (10-14 s) `live` is false. `_move_league` therefore sends every player to his base anchor
  as the shift relaxes to 0, with no `box_push`.
- The corner-taking side's strikers and wingers end up outside the area. Nobody else is sent there, because `_corner`
  passes no `also` positions.
- The taker then gets an ordinary spell on the ball: a hold of 1-4 s, then a carry, take-on, shot or pass.
- A pass from the flag is a cross only if `_pick_cross_target` finds a teammate within 34 m of the goal line. If it finds
  none, 0.7.0 plays an ordinary `_pick_pass_target` pass. In build-up that target is a centre-back, full-back or holding
  midfielder (`receive_role`).

**Numbers.**

What follows each of the committed season's 111 corners (first event after the corner that is not a touch or pressure):

| After the corner | Count |
|---|---|
| Cross | 66 |
| Carry from the flag | 18 |
| Ordinary pass from the flag | 9 |
| Take-on | 7 |
| Period end | 5 |
| Throw-in | 5 |
| Shot from the flag (30.9 m, xG 0.025, rl_r02_cal_bro) | 1 |

- The 9 ordinary passes travel 47-83 m and end 34-70 m up the pitch. They go to 5 full-backs, 2 holding midfielders, a
  winger and a striker. 6 are completed, so they count as completed long passes.
- Before 0.7.0 every pass from the flag was a cross, albeit at the wrong man. These backward passes are new in 0.7.0.

I hooked `_pick_cross_target` over 12 fixtures. A "decision" is one call, that is, one wide pass inside the zone:

| | Decisions | Teammates within 34 m (median) | Nobody within 34 m | Nobody in the penalty area | Receiver's distance from the drop (median) |
|---|---|---|---|---|---|
| Corners | 40 | 1 | 15% | 95% | 24 m |
| Open play | 185 | 1 | 25% (becomes an ordinary pass) | 91% | 22 m |

The receiver makes up the gap through `_reach`: the ball waits in the box for up to 3 s while he runs. The leftover
placement is small (median 0.6 m, p90 7.8 m per cross).

**What it affects.**
- **The contract.** README L217 says "A corner from the flag is always a cross", but only 66 of 111 corners are followed
  by one. The generator comment says the same. README L214 and generator L230 say the target is "a teammate attacking it
  (they run onto it while it is in the air)", but at 91-95% of crosses there is no teammate in the area.
- **Statistics.**
  - `crosses` and `cross_pct` (corner crosses are in both);
  - corners' share of shots, and set-piece aerial duels: the defenders in the box contest against someone arriving from
    about 20 m;
  - the long passes and pass completion of full-backs and holding midfielders (the backward corner passes);
  - a shot taken from the corner flag.

**Fix.**
- In league mode, give `_corner` `also` positions for the attacking side, so a few players (centre-backs, the striker, the
  far winger, the 10) stand in the area. Do the same for the nearest defenders.
- Make the taker's first action a delivery: a cross, or an explicit short corner, never a shot from the flag.
- Correct README L214/L217 and the generator comments to match.
- Add a fast test that corners are followed by a cross with several attackers in the area. Add a report diagnostic for
  attackers in the area when a cross is struck.
- Open play may need a later run toward the box, but the corner is the concrete defect.

## Nits

- **The touch interval is still quoted two ways.** README L193-194, the `touch_every_s` comment (generator L139) and
  83484e2's message say "one record per 2.3 s". The served `TOUCH_RECORDS` says 2.4 s, and exactly it is 2.37 s.
  README is the contract doc; quote `TOUCH_RECORDS` or say 2.4.
- **"Every one-season band in"** (round 2's result) covers the event and league-mode bands only. On the committed season
  the leader bands for interceptions (3.08 against a 2.96 ceiling) and top_npxg_share (0.43 against 0.40) are high. Both
  are indicative by design, and over six pooled seasons they pass (top share 0.385, leader npxG gap 1.69 against 1.75).
- **`cross_choice` is 1.0 for every role.** It draws a random number that always passes. Meanwhile a winger in a wide
  channel inside 39 m never plays an ordinary pass while anyone is within 34 m of the goal line.
- **The new start-position checks hold by construction.**
  - Full-backs' cross zone is 40 m, which equals `FB_CROSS_START_MAX_M`.
  - The slow test's `max(cross_start_m_by_role) <= 40` cannot fail while `cross_zone_m` stays at 40 or below.
  - Both guard the parameters rather than measure behaviour. Say so in their docstrings.
- **Offside on crosses.** 17 of 462 crosses (3.7%) are flagged offside through `offside_long`, because the cross target
  is now often the furthest man forward. That is plausible, but it is not documented or tested.
- **Carried from earlier rounds, unchanged:**
  - leader gaps print as minutes in `render_markdown`;
  - `leader_*_gap` returns 0.0 when the second-best value is 0;
  - `reliability.league_fingerprint` hashes neither `metrics.py` nor `playing_time.py`;
  - `BUILT_BY` leaves out `schema.py` and `build.py`;
  - `last3_minus_season` skips the 15-minute floor;
  - the `rank` docstring is incomplete, and `rank` has an O(n^2) `rest`;
  - `build_all` sizes its pool with `os.cpu_count()`;
  - `materialise` still has a two-syscall window;
  - the whole-table evidence cap;
  - two meanings of "regular";
  - keepers get outfield percentiles;
  - `club=` matches only exactly;
  - `Body.s_prev` is not reset on `_place(stop=True)`;
  - `.gitignore` hides this folder;
  - the slow suite builds six seasons twice.
- **The `demo.js` ranking claims are still untested.** All of them hold today (above). The next re-record should be
  caught by a test, not by hand.
- **Fabric** still holds the 0.6.0 season until it is re-synced (a deployment step; this job did not ask for one).

## Numbers

| Check | Result |
|---|---|
| Fast suite | 759 passed, 12 deselected, 7 min 16 s (alongside another agent's pytest) |
| Slow suite | 12 passed, 3 min 19 s |
| Back-compat against main | 59 of 59 identical (vision 101-140, 201-206, 301-303; demo/realistic x 2 seeds; 2 friendlies; clips of 4 samples) |
| Determinism | cold build under PYTHONHASHSEED=4242 = local folder (`diff -rq`) |
| Cold `build_all` | 15.6 s (under load) |
| `report --league` / `season.audit` | 12 s / 8 s |
| Corners followed by a cross (committed season) | 66 of 111; 9 become 47-83 m passes back toward halfway |
| Crosses with nobody in the penalty area at the strike (12 fixtures) | corners 95%, open play 91%; receiver median 22-24 m from the drop |
| Touch records per team per 90 | 559 (served "about 560"); per record 2.37 s (served 2.4, README 2.3) |
