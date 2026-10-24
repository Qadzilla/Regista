# Review A, closing round 2: engineering

Reviewer A, closing round 2. I read `git diff main...HEAD` on `feature/terminal-engine`. The code is at b6f9cd7;
a1f6507 only adds review B's report. I read the earlier reviews and fixes first (`review-a-pass1/2`,
`review-a-final1`, `review-b-*`, `review-fixes-1/2`). Then I re-read what b6f9cd7 changed:
- generator 0.6.0 (`_tackler`, role-weighted pass targets, `cross_from`, the retuned tables);
- the code fingerprint in `build.py` and `reliability.py`;
- the role shapes and leader gaps in `report.py`;
- the `REALISM` changes in `metrics.py`;
- the re-recorded pins, `demo.js`, the storyboard and the contract docs.

I ran every check myself and fixed nothing.

**Not signed off.** Nothing must be fixed. Two things should be fixed:
- **Crosses** are aimed at whoever the build-up would pass to. Review B's first finding covers the same code from the
  football side.
- **The touch-interval text** that the API serves is wrong.

Everything closing round 1 asked of review A is done. I confirmed each item below.

## What I checked myself

- **Back-compat, independently of the branch's test.** I made detached worktrees at main (e3da71d) and at b6f9cd7^.
  One script ran against both main and HEAD, each importing its own `src`. It hashed events and tracks for:
  - every vision training spec (101-110), event-training spec (121-126), development spec (201-206) and fresh spec
    (301-303);
  - the `demo` and `realistic` profiles on seeds 5 and 900;
  - two Player-view friendly films (`friendly_kwargs`);
  - `derive_clips` (clips and labels) for every player of every committed sample.

  All 35 entries are identical. `tests/test_backcompat.py` passes too. The worktrees are removed.
- **Determinism.**
  - Three league fixtures (rounds 1, 5 and 10), events and tracks, give one hash under `PYTHONHASHSEED` 1 and 4242.
  - `_tackler` sorts its candidates by player id, so nothing depends on set order.
  - A cold build into an empty folder is byte-identical to the local `data/season/matches`: 90 of 90 files (events,
    clips and manifests of 30 fixtures).
  - So the committed `summaries.json`, `reliability.json` and demo claims come from current matches.
- **The code fingerprint (round 1's should-fix).**
  - **Done.** `code_fingerprint(BUILT_BY)` hashes generator, physical, camera, clips and playing time. It is cached
    per process and sits inside the match fingerprint. `reliability.league_fingerprint` hashes `GENERATED_BY`.
  - **Test.** The new test edits a copied generator and sees both fingerprints change.
  - **Docker.** In the image the package installs into site-packages, so `_SRC` (two levels up from `build.py`)
    resolves there and the hashed bytes are the same files. The image builds the season fresh.
- **Tests.**
  - `python3 -m pytest -q`: 757 passed, 11 deselected, in 5 min 12 s. It ran beside my other scripts, so the time is
    inflated.
  - `python3 -m pytest -q -m slow`: 11 passed in 2 min 46 s.
  - The slowest part A items in the fast suite:
    - module fixture setups that generate three league fixtures: 7.4 s and 6.4 s, under load;
    - the league renderer test: 6.0 s;
    - the demo's clip test: 5.2 s.

    Nothing new is slow. The slow suite is dominated by the reliability recomputation (67 s) and the six-season pool
    (65 s).
- **Report and audit.**
  - **`report --league`:**
    - event bands: 13 of 13;
    - league-mode bands: 10 of 11 (red cards: none in the committed season, a verdict only over six);
    - physical bands: 14 of 14; style bands: 4 of 4;
    - leaders: 13 of 14 (interceptions high), indicative on one season, as designed;
    - role shapes: all hold (indicative). The slow tests pass them over six seasons.
  - **`season.audit`:** Femi Toure is outright top scorer with 3. Six players have 2.
- **API, probed with TestClient on the local season.**
  - Every `demo.js` ranking claim re-recorded in b6f9cd7 holds:
    - Toure is 1st of 18 qualified forwards for goals and np goals per 90;
    - pl_ash_10 is 3rd of 18 midfielders for take-ons won;
    - pl_ash_09 is 2nd of 18 forwards for shots;
    - pl_dun_06 is 2nd of 18 midfielders for passes;
    - pl_eas_03 is 3rd of 24 defenders for key passes;
    - Toure won 4 of 18 take-ons.
  - The storyboard's rules-Scout claim holds: "midfielders who win the ball back" answers Bruno Lindqvist.
  - Validation is unchanged and holds: an unknown metric, `limit=0` and a bad id give 422 or 400; an unknown player or
    club gives 404.
- **Python 3.11.** I scanned b6f9cd7's added lines for 3.12-only f-string nesting. None found. (This machine has no
  3.11. The nightly slow workflow and the image use 3.11.)

## Closing round 1 findings, checked

| Finding | Verdict |
|---|---|
| Fingerprint blind to in-version generator changes | Fixed (above) |
| Role shapes contradict football | Fixed for passes, touches, tackles and fouls (the table in the report agrees). The full-back cross order passes for the wrong reason: should-fix 1 below and review B's finding 1 |
| Toure the only scoring threat | Fixed: the leader-gap and top-share bands are in place, each with its source, and pass over six seasons in the slow test |
| touches_in_box labelled checked | Fixed: marked not comparable, the leader band removed, and a test pins it |

## Should fix

### 1. A cross is aimed at whoever the build-up would pass to, so centre-backs and holding midfielders "receive" crosses 60 m away

**Where:** `src/regista/synth/generator.py`: `_league_pass` (L1746-1762), `_pick_pass_target` (L1453-1458) and
`cross_from` (L213).

**The mechanism.**
- `_league_pass` picks the target first, with `_pick_pass_target`. In his own 60% a passer weights centre-backs 3.0,
  the holding midfielder 1.8 and full-backs 1.5, against the striker's 0.3 (`receive_role`).
- Only then does it decide the kind. Any wide pass past `cross_from` becomes a cross (`cross_share` 1.0), and the aim
  is replaced by a spot in the box.
- So the cross keeps the build-up target as `related_player_id`, often a centre-back behind the crosser.
- On a completed cross that player runs toward the box while the ball flies, and the rest of the gap is `_place`d.
- On a contested cross, `aerial_probability(target, header, cross=True)` decides the duel as if he were there. Then
  `_place(winner, aim)` puts the winner into the opponents' box.

**Numbers.**
- **Distance at the moment of the cross.** I hooked `MatchSim._event` over 10 fixtures and measured the receiver's
  distance from where the cross comes down, as a median:

  | Receiver | Median distance |
  |---|---|
  | Centre-back | 60 m |
  | Full-back | 53 m |
  | Central midfielder | 42 m |
  | Holding midfielder | 40 m |
  | Striker | 23 m |

- **Who receives, six pooled seasons:**

  | Receiver | Intended crosses | Completed crosses |
  |---|---|---|
  | Centre-back | 467 | 100 |
  | Holding midfielder | 403 | 68 |
  | Full-back | 318 | 54 |
  | Striker | 574 | 121 |

  Centre-backs, holding midfielders and full-backs get 40% of completed crosses.
- **The committed season.** Holding midfielders receive the most completed crosses of any role (21, against strikers'
  18). Holding midfielders and centre-backs win 12 of the attacking side's 24 cross aerial duels; strikers win 4.
- **What 0.6.0 changed.** The flaw predates 0.6.0. I regenerated the season at b6f9cd7^:
  - Then, completed crosses went to centre-backs 8 times, full-backs 5 and holding midfielders 6, against strikers' 18.
  - 0.6.0 roughly doubles that, because it weights build-up targets toward the back line and lets full-backs cross
    from 42 m.
  - Position jumps (`relocated_per90_m`) went from 29 m to 45 m per player per 90.
- **The full-back cross order.** 380 of the 750 full-back crosses over six seasons start in his own half (42-52.5 m from
  his goal line). Without them full-backs make 0.195 of wingers' crosses, below the third that
  `fb_crosses_third_of_w` checks. So the role shape that `REALISM["crosses"]` cites passes on these balls. Review B
  reaches the same conclusion from the football side.

**What it affects.**
- `crosses`, `cross_pct` and `passes_received`;
- touches in the box and aerial duels for defenders;
- the shots that follow a cross;
- the physical diagnostic.

**Fix.**
- Decide first whether the pass is a cross. Then pick its target among teammates attacking the box (ahead of the ball
  and near the area, weighted to strikers, wingers and attacking midfielders).
- Measure `cross_from` from the opponent's goal line, so full-backs cross from the attacking third or on the overlap.
- Re-check `fb_crosses_third_of_w`. Add a role check or diagnostic for who receives completed crosses, and one for where
  crosses start.

### 2. The served definition of touches gives a touch interval the code does not use

**Where:**
- `src/regista/season/metrics.py`: L293 (the `touches` description), L555 (`REALISM["touches"]`) and L561
  (`REALISM["touches_in_box"]`);
- `src/regista/synth/report.py`: L111 (a comment).

**The problem.**
- **The text:** these say "one touch record per 1.7 s on the ball (generator 0.6.0; 1.8 s in 0.5.0)".
- **The code:** it uses `touch_every_s` 1.89 (1.82 in 0.5.0). `data/synthetic/README.md` says 1.89.
- **Neither is the real rate.** The generator writes `max(1, int(hold / 1.89))` records over a hold drawn from
  U(1, 4) s. That averages one record per 2.33 s on the ball. The committed season has 575 touch records per team per
  90; the note says "about 600", which is fine.
- **Where users see it:** `/api/metrics` and every terminal column description serve this text. The project's rule is
  that no metric goes out without a correct definition.

**Fix:** state the parameter, or better the measured rate, in one place and quote it everywhere.

## Nits

- **Leader gaps print as minutes.** `render_markdown` shows "leader_npxg_gap | 1.63 ratio (1.63 min)". At L673,
  `key.replace("_per90", "_minutes")` is a no-op for keys without `_per90`, so the ratio prints again as minutes.
- **`leader_{npxg,goals}_gap` returns 0.0 when the second-best value is 0.** It then reads "low" against a band whose
  floor is 1. This only happens on tiny samples.
- **`reliability.league_fingerprint` hashes the generator but not `season/metrics.py` or `playing_time.py`.**
  - A change to a metric's rule leaves the committed noisy flags looking current to the fast test.
  - The nightly slow test (`test_the_committed_reliability_reproduces`) catches it.
  - The stale reason still says "computed for another league file" when only the code changed.
- **`BUILT_BY` leaves out `schema.py`** (the `SCHEMA_VERSION` stamped on every record) and `build.py` (the manifest).
  Both change rarely.
- **The top-scorer guarantee is a maintenance cost, not a defect.**
  - Toure is outright top scorer in 4 of 12 regenerated seasons now. The test docstring says so; it was 10 of 12 at
    0.5.0.
  - The committed season's 3-2 lead rests on `touch_every_s` being re-picked by scanning, which reshuffles every draw.
    This is documented.
  - Any future league-mode change will need a new scan.
- **`_tackler` placement.**
  - A tackler up to 10 m away gets at most 1 s to close (`_reach(max_s=1.0)`); the rest is placed.
  - He is placed where the holder stood when the call began, though the holder moves meanwhile.
  - Both jumps are logged as `relocated_m`, as designed.
- **Carried from earlier rounds, unchanged:**
  - `last3_minus_season` skips the 15-minute floor;
  - the `rank` docstring is incomplete;
  - `build_all` sizes its pool with `os.cpu_count()`;
  - `materialise` still has a two-syscall window;
  - `rank`'s O(n^2) `rest`;
  - the whole-table evidence cap;
  - two meanings of "regular";
  - keepers get outfield percentiles;
  - `club=` matches only exactly;
  - `Body.s_prev` is not reset on `_place(stop=True)`;
  - `.gitignore` hides this folder;
  - the slow suite builds six seasons twice.
- **The `demo.js` ranking claims are still untested.** They were re-recorded by hand this round. I verified all five
  above, but a test asserting them would catch the next re-record.
- **Fabric:** the lakehouse still holds generator 0.5.0 data until it is re-synced. This is a deployment step.

## Numbers

| Check | Result |
|---|---|
| Fast suite | 757 passed, 11 deselected, 5 min 12 s (under load) |
| Slow suite | 11 passed, 2 min 46 s |
| Back-compat against main | 35 of 35 identical (vision 101-110, 121-126, 201-206, 301-303; demo/realistic x 2 seeds; 2 friendlies; derived clips of every committed sample) |
| Determinism | 1 hash across 2 `PYTHONHASHSEED` values; cold build = local folder, 90 of 90 files |
| Cold `build_all` | 17.5 s, run while the slow suite was going (about 6 s alone in round 1) |
| `report --league` / `season.audit` | 21 s / 18.5 s, both under load |
| Completed crosses to CB/DM/FB (6 seasons) | 222 of 551 (40%); 0.5.0, one season: 19 of 54 |
| Full-back crosses from his own half (6 seasons) | 380 of 750; without them FB/W = 0.195 (check needs 0.333) |
| relocated_per90_m | 29 m (0.5.0) to 45 m (0.6.0) |
