# Part A review B, closing round 2: football and data science

I reviewed `git diff main...HEAD` on `feature/terminal-engine` at b6f9cd7 on 2026-10-24. My lens was football and data
science. I read the earlier reviews and fix reports first, then checked the current code and data myself. I changed no
code. Everything here is synthetic: invented players in an invented league.

**Verdict: not signed off.** Round 1's fixes hold, and every band and role-shape check passes over six seasons. But one
of the new checks passes only because the generator labels a full-back's passes from his own half as crosses. A second
group of role shapes, defenders' progression and full-backs' share of the ball, still contradicts football, and nothing
checks it.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 757 passed, 11 deselected (5 min 12 s); includes `tests/test_backcompat.py` |
| `python3 -m pytest -q -m slow` | 11 passed (2 min 46 s) |
| `python3 -m regista.synth.report --league` | events 13/13, league mode 10/11 (red cards 0, indicative), physical 14/14, style 4/4, leaders 13/14 (interceptions leader high, indicative), role shapes 5/5 holding (indicative) |
| `python3 -m regista.synth.report --league --repeat 6` | everything in band: 13/13, 11/11, 14/14, 4/4, 14/14; role shapes 5/5 hold |
| `python3 -m regista.season.audit` | Toure is outright top scorer: 3 goals, then seven players with 2 |
| Six pooled seasons, my own scripts | `audit.season_matches(seasons=6)` into raw-event tallies and one `SeasonMetrics.from_streams`; 180 matches |

## Round 1 fixes: checked

| Fix | What I saw |
|---|---|
| Fingerprint covers the generator's code | Present in `build.py` and `reliability.py`, and the test passes. Review A's lens; I did not probe further |
| Role shapes | All five orders hold over six seasons and in the committed season. Passes per 90: CB 44, DM 56, ST 30. Tackles won: ST 1.09, DM 3.56. Fouls won: W 1.72, ST 1.55, CB 0.49 |
| Toure is no longer the only scoring threat | npxG per 90: 0.77 against 0.50 (gap 1.53). Goals per 90: 0.82 against 0.74. Over six seasons he scores 15 (4 penalties) to A. Ustinov's 13 (5 penalties). He takes 30.7% of Brookfield's npxG and scores 35.7% of its goals. Other forwards now score: Tanaka 0.55 non-penalty goals per 90, Brennan 0.47 |
| `touches_in_box` | Marked not comparable, with the reason given. Its leader band is gone |
| Labels | `REALISM` names each shape check, and the README describes 0.6.0 accurately except for the cross point below |

## Must fix

### 1. Full-backs' "crosses" are mostly passes from their own half, so the full-back cross check passes on mislabelled events

`_do_pass` in league mode: `cross_from = {"FB": 42.0, "W": 66.0}` and `cross_share` 1.0. So any pass a full-back makes
from a wide position more than 42 m from **his own** goal line becomes a cross aimed into the box, whoever the target
was. 42 m is about 10 m inside his own half. Over six pooled seasons:

| | Full-backs | Wingers |
|---|---|---|
| Open-play crosses | 750 | 1,897 |
| Median start, metres from the opponent's goal line | **52.6** (p10 33.0, p90 61.0) | 25.5 (p90 37.2) |
| Started more than 40 m out | **627 (84%)** | 10 (1%) |
| Started in his own half | **378 (50%)** | 10 |
| Median length | **49.9 m** | 33.7 m |
| Completed | 13.7% | 20.6% |

- **Every wide pass becomes a cross.** In wide positions past 42 m, full-backs made 749 crosses and 31 passes. A
  full-back on the touchline at halfway never plays it short down the line or back inside. He always hits a 50 m ball
  into the box.
- **By the terminal's own definition these are not crosses.** `crosses` reads "Balls from a wide area into the centre"
  (Opta). A 50 m ball from a full-back's own half is a long ball or a diagonal. An early cross starts around the edge of
  the final third, about 30-40 m from goal (reviewer's knowledge).
- **Without them the check fails.** Counting only crosses that start within 40 m of the opponent's goal line,
  full-backs make about 0.5 per 90 (123 crosses) against wingers' 7.9. That is far below the one-third order that
  `fb_crosses_third_of_w` checks.
- **Full-backs still create nothing.** Key passes per 90: FB 0.42, the lowest outfield role after CB. xA: FB 0.04.
  `LEADER_V`'s key-pass source names a full-back second (Robertson 3.19).
- **Other numbers inherit the error.** Full-backs' long passes (5.2 per 90) are mostly these crosses. That gives
  full-backs a long-pass completion of 33.9%, worse than any outfield role. Full-back pass completion is 80.6%, against
  86.7% on passes alone.
- **The labels overstate.** `REALISM["crosses"]` now names `shape_fb_crosses_third_of_w`. The README calls these
  "early and overlapping deliveries".

**What to do.** Measure the cross zone from the opponent's goal line: about the final 35-40 m, plus the overlap. Make
a cross a choice among the full-back's options, not the label on every wide pass, as `cross_share` 0.7 did in 0.1.0.
Then retune so full-backs reach the box often enough to hold the order. Give the shape check a start-position
condition, or add a diagnostic for cross start distance by role.

## Should fix

### 1. Defenders' progression and full-backs' share of the ball still contradict football, and the "checked" labels cover only the league total

Means per 90 for qualified players by kit role, from the terminal's engine over six pooled seasons:

| | CB | FB | DM | CM | AM | W | ST |
|---|---|---|---|---|---|---|---|
| progressive passes | **0.95** | **1.41** | 3.95 | 4.34 | 5.75 | 3.36 | 1.47 |
| progressive carries | **0.08** | **0.45** | 0.46 | 1.00 | 3.15 | 5.21 | 3.55 |
| long passes | **1.89** | 5.2 (crosses, above) | 1.93 | 2.49 | 1.93 | 9.40 | 2.17 |
| touches | 52.8 | **46.2** | 70.3 | 67.6 | 66.2 | 58.9 | 46.4 |
| passes | 44.1 | **37.7** | 56.2 | 52.8 | 49.3 | 41.6 | 30.2 |
| pass completion | 83.8% | 80.6% | 89.4% | 86.0% | 84.1% | 71.2% | 78.2% |

- **Defenders progress the ball least.** Centre-backs make fewer progressive passes than strikers (0.95 against 1.47).
  Centre-backs and full-backs are the two lowest outfield roles. Strikers make more progressive carries than attacking
  midfielders.
  - In the Premier League on FBref, centre-backs and full-backs are among the main progressive passers: about 3-6 per
    90 for regular starters, more for ball-playing defenders. Strikers make about 1-2.
  - Centre-backs play about 10-15% of their passes long (more than 30 yards).
  - These figures are my knowledge, unsourced.
- **The likely cause.** 63% of centre-back passes and 61% of full-back passes start in their own 40%, which FBref's
  progressive rule excludes. The back line sits deep in possession. Centre-backs also almost never go long (1.2% of
  their passes over 32 m).
- **Full-backs see too little of the ball.** They touch it and pass it less than wingers, and least of any outfield role
  except strikers. In the Premier League, full-backs touch the ball more than wingers (reviewer's knowledge).
- **Where a scout sees it.**
  - `progressive_passes` is the **first DF default column**, and it sits in the MF defaults and the similarity
    template.
  - Within DF, percentiles still rank full-backs against centre-backs on a scale about a quarter of the real one.
  - The all-positions view puts defenders at the bottom of progression.
- **The labels.** `REALISM["progressive_passes"]` is "checked" through `prog_pass_carry_ratio`, a league ratio. That
  is the same league-level-only claim round 1 found on passes and tackles.

**What to do.**
- Push the back line up in possession, or let centre-backs and full-backs pick forward and long targets more often.
- Add sourced shape checks in the `ROLE_SHAPES` pattern:
  - CB and FB progressive passes above ST
  - FB touches above W
  - CB long passes above a floor
- Until then, give `progressive_passes` and `progressive_carries` a role-level "likely off" note.

## Nits

1. **The gap rows print a ratio as minutes.** For `leader_npxg_gap` and `leader_goals_gap`, the report prints "1.53
   ratio (1.53 min)". `render_markdown` looks up `key.replace("_per90", "_minutes")`, which returns the gap key itself.
2. **The npxG gap's source is xG with penalties.** `leader_npxg_gap` calls "Haaland 1.04, Isak 0.81" npxG per 90, but
   `LEADER_V` says these are xG per 90 with penalties included.
   - Likewise, `top_npxg_share` compares Regista's npxG share with Premier League xG shares that include penalties.
     Haaland's non-penalty share is lower, about 31% by my arithmetic, and still inside the band.
3. **`cross_completion` includes corner deliveries.** The band cites open-play crosses (premierleague.com). The
   generator writes most corners as `cross` events: 577 of 712 corners, 20% of all crosses. Corner crosses complete at
   23%. Leaving them out gives about 18%, still in band.
4. **Some role orders are still off, though none is banded.**
   - Attacking midfielders commit the most fouls (2.17 per 90; CM 1.63, DM 1.07). Strikers led this last round.
   - Central midfielders win more tackles than holding midfielders (3.72 against 3.56).
   - Full-backs win fewer tackles than centre-backs (1.73 against 1.91).
   - Central midfielders shoot 2.09 times per 90, and one (K. Petrov) is third in the league for npxG per 90 (0.41).
     Real central midfielders shoot about 1-1.5 times (reviewer's knowledge).
5. **Keepers make about 12 passes per 90 at 56.6%.** This was nit 4 last round, and it is unchanged. `gk_pass_pct` is a
   GK default column. Its label says unchecked, which is honest. A "likely low" note would match the others.
6. **Two earlier nits still stand.**
   - The noisy flag measures luck within a kit role, but percentiles pool the whole position (DF mixes CB and FB).
   - Reliability is estimated from 360 rows that repeat the same 66 starters six times.

## Numbers

Six pooled seasons, unless noted.

| | Value |
|---|---|
| Toure | 1,652 min; 15 goals (11 non-penalty); npxG 14.1; 5.94 shots per 90 |
| Next best npxG per 90 | A. Ustinov 0.50, K. Petrov (CM) 0.41, Tanaka 0.40, Whitfield (W) 0.38 |
| Interceptions per 90 by role | CB 1.13, FB 0.77, DM 1.60, CM 1.17, W 0.42, ST 0.49 |
| Shots per 90 by role | CB 0.23, FB 0.45, DM 1.11, CM 2.09, AM 1.89, W 2.33, ST 3.21 |
| Offsides per 90 | ST 0.92, W 0.40 (league total in band) |
| Distance per 90 by role (km) | CM 10.9, DM 10.4, FB 10.1, W 9.5, AM 9.3, CB 9.1, ST 9.0 |
| Corners taken | W 601 of 712 |
