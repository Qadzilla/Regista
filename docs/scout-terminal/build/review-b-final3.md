# Part A review B, closing round 3: football and data science

I reviewed `git diff main...HEAD` on `feature/terminal-engine` at 83484e2 (generator 0.7.0) on 2026-10-24. My lens was
football and data science. I read the earlier reviews and fix reports first, then checked the current code and data
myself. I changed no code. Everything here is synthetic: invented players in an invented league.

**Verdict: not signed off.** Round 2's fixes work. Crosses now start near the box and go to the players attacking it,
the back line steps up, and the served touch-record text matches the code. Every band and role-shape check passes over
six seasons. Nothing must be fixed. Three things should be:

- Headed shots and headed goals run at about half the Premier League's rate. The source is Opta's, cited below.
- Progressive passes are low in every role, not only for centre-backs, so the terminal's "checked" label and its
  centre-back-only note understate the gap.
- Wide players in the crossing zone still cross almost every time they pass.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 759 passed, 12 deselected (7 min 16 s) |
| `python3 -m pytest -q -m slow` | 12 passed (1 min 32 s) |
| `tests/test_backcompat.py` | 9 passed |
| `python3 -m regista.synth.report --league` | events 13/13, league mode 10/11 (penalties low, indicative), physical 14/14, style 4/4, leaders 12/14 (interceptions leader 3.08 and `top_npxg_share` 0.43 high, both indicative), role shapes 8/8 hold (indicative) |
| `python3 -m regista.synth.report --league --repeat 6` | every band in: 13/13, 11/11, 14/14, 4/4, 14/14; role shapes 8/8 hold |
| `python3 -m regista.season.audit` | Toure is outright top scorer: 3 goals (2 non-penalty), then three players with 2 |
| My own scripts | six pooled seasons from `audit.season_matches(seasons=6)` (180 matches, 120 team-90s), raw-event tallies and one `SeasonMetrics.from_streams`; `MatchSim._place` hooked over 12 fixtures to find where position jumps come from |

## Round 2 fixes: checked

| Fix | What I saw |
|---|---|
| Crosses decided first, aimed at the box | Over six seasons, open-play crosses: W 1,408, FB 750, everyone else 135. Median start, metres from the opponent's goal line: FB 35.4, W 30.4. Completed crosses go to ST 56%, W 33%, AM 6%, and CB/DM/FB 1.6% together. Open-play completion is 18.6% (Premier League 18.8-21.7%) |
| Full-back cross order | FB 3.4 against W 7.7 per 90 (corners included). Open play only, qualified players: FBs 2.1-4.3, wingers 4.4-7.5. The start condition (median within 40 m) is real and holds |
| Back line in possession | Over six seasons, progressive passes CB 2.1 and FB 3.3 against ST 1.4. Touches FB 57.5 against W 47.4. CB long passes 4.0, 93% of them forward (to W, FB, ST). CB long-pass completion is 59% |
| Touch-record text | `TOUCH_RECORDS` is derived from `touch_every_s` and the league `hold` range. I re-derived it by hand: 1.92 s with holds of U(1, 4) s gives E[records] = 1.053, so one record per 2.37 s on the ball. The served text says 2.4 s, which is right; nit 1 covers the docs |
| New shape checks | Each one names its source and says the floor or condition is ours. The checks pass on the values above |

## Should fix

### 1. Headed shots and goals run at about half the Premier League's rate

These are raw-event tallies over six pooled seasons (60.2 match-90s, both teams):

| | Regista 0.7.0 | Premier League |
|---|---|---|
| headed shots per match | **1.9** (114 of 1,510 shots, 7.5%) | 4.0 in 2023/24; 4.1 in early 2024/25 |
| headed goals per match | **0.20** (12 of 146 goals, 8.2%) | 0.53 in 2023/24 (203 goals); 0.36 in 2019/20, the lowest season the article gives |
| goals within 6 s of the scoring side's own cross | 9 of 146 (6.2%) | (no figure read) |

Source for the Premier League column: Opta Analyst, "We're Seeing Fewer Headed Goals in 2024-25", 15 Oct 2024
(theanalyst.com/articles/premier-league-fewer-headed-goals-2024-25). 0.53 headed goals against about 3.3 goals a match
puts headers near 16% of goals; that is our arithmetic.

**Why it happens.**
- A completed cross becomes an ordinary possession.
- `_reach` lets the receiver run up to 3 s more to the drop while play goes on and the ball waits there. Then comes a
  1-4 s spell on the ball, with touch records and the usual pass, take-on and shot weights. The shot weight is halved
  after a cross (`after_cross_shot` 0.5).
- Only a shot from that possession can be a header (60% of the time).
- So 0.7.0 aims crosses at the forwards, but the forwards rarely finish first time.

**Why it matters.**
- Synthetic data quality is scored, and the event mix is the deliverable.
- Target forwards and good headers of the ball (the `aerial` rating) turn their crosses into chances half as often as
  they would in football.
- No band covers this, so the report cannot catch it.

**What to do.** Give a cross that arrives a first-time finish branch: a header or volley on arrival, weighted by role
and by `aerial` or `finishing`. Then add a sourced band for headed shots and headed goals per match, from the Opta
Analyst figures above.

### 2. Progressive passes are low in every role, and "checked" rests on a ratio at the bottom of its band

| | Regista, six seasons | Premier League |
|---|---|---|
| league leader, per 90 | **5.56** (P. Petrov, AM); best DM 4.44, best CB 3.49 | the five most progressive passers of 2023/24 made 1,602 (FBref via Football365, the source of `prog_pass_carry_ratio`). That is 320 each in at most 3,420 minutes, so **at least 8.4 per 90** on average (our arithmetic) |
| team, per 90 | 27.5 per team | (no league total read; the reviewer's recollection of FBref squads is about 40-50, unsourced) |
| passes per carry | 1.38 (band 1.2-3.0) | the band's own source gives about 1.9 |
| role means | CB 2.11, ST 1.42, W 2.42, DM 3.02, FB 3.29, CM 3.32, AM 4.23 | holding midfielders are among the main progressive passers (reviewer's knowledge) |

- The leader sits at two thirds of a lower bound taken from the project's own source. A leader band at 0.75 V would
  fail.
- The engine's carries are not low: the top five carriers average 7.5 per 90, against at least 4.9 implied by the
  same article. So the ratio falls toward its floor because passes are short of the mark.
- Holding midfielders fell from 3.95 per 90 in 0.6.0 to 3.02 now. They are now below full-backs and central
  midfielders.
- Where a scout sees it:
  - `progressive_passes` is the first DF default column. It is also an MF default and in the similarity template.
  - `REALISM["progressive_passes"]` is `checked: True` with a "Likely low for centre-backs" note, and the README says
    the same.
  - The note is honest about centre-backs and silent about the rest. The split-half flag marks the metric noisy
    (r 0.25), which is shown, but noise does not explain a low level.

**What to do.**
- Either raise the level, with more vertical options for holding and central midfielders and centre-backs, and add a
  sourced leader band. FBref's per-90 top three would be the source, in the `LEADER_V` pattern.
- Or change the note to say progressive passes are likely low in every role: a league leader of about 5.6 per 90,
  against at least 8.4 for the Premier League's top five. Also make the label say the check covers the league ratio and
  the role order only.

### 3. In the crossing zone, wide players still almost always cross

Over six seasons, among passes from a wide channel within 40 m of the opponent's goal line:
- full-backs played 798 crosses and 61 other passes (**93% crosses**);
- wingers played 1,823 crosses and 603 other passes (75%).

`cross_choice` is 1.0 for both roles. So whenever a teammate is within 34 m of the goal line, a pass from there is a
cross. Round 2 asked for a cross to be "a choice among the full-back's options, not the label on every wide pass". 0.7.0
fixed where crosses start but kept them automatic, and the fix report lists the finding as fixed without saying so.

In football a wide player near the box also plays it inside, back, or as a cut-back. The cut-back is among the best
chance-creating passes, and it is absent here. Our view, unsourced, is that well under half of such passes are crosses.

Effects:
- Wide players' key passes and xA come only from crosses. The key-pass leader is 2.48 per 90, at the bottom of its band
  (2.27).
- Wingers' pass completion is 68.4%, the lowest outfield role by far.

**What to do.** Set `cross_choice` below 1 (0.1.0 used 0.7), and add a cut-back target from near the byline. Then
retune so `fb_crosses_third_of_w` still holds.

## Nits

1. **The touch interval is stated two ways.**
   - The served text, built by `TOUCH_RECORDS`, says one record per 2.4 s, which is correct.
   - `data/synthetic/README.md` (touch records), the `touch_every_s` comment in `generator.py` and the round-2 fix
     report say 2.3 s.
2. **Wingers and strikers play long passes backwards.**
   - Non-cross passes over 30 yards: 75% of wingers' and 88% of strikers' go backwards, mostly to full-backs and
     centre-backs.
   - The cause is `receive_role_attack` (CB 1.6, FB 1.8) together with the floor in the distance weight.
   - Result: strikers attempt 2.6 long passes per 90 at 70% completion, where the `cb_long_passes_floor` source gives
     Haaland 0.18.
3. **`relocated_m` does not name its largest in-play source.**
   - The definition lists a keeper's dive, set-piece spots and the reset after a goal.
   - Over 12 fixtures, most in-play jumps come from `_reach`: a receiver's or chaser's last gap. Jumps over 3 m have a
     median of about 5 m and a maximum of 19 m.
   - Aerial-duel winners placed under the ball come next: a median of 6-8 m when over 3 m, and a maximum of 16 m.
   - Both show as jumps in the 10 Hz tracks and in rendered video.
4. **Round 2's nits still stand.**
   - The gap rows print "1.69 ratio (1.69 min)".
   - The npxG gap and `top_npxg_share` compare with Premier League xG that includes penalties.
   - `cross_completion` is labelled open-play but counts corner deliveries (0.189 with corners, 0.186 without).
   - Central midfielders win more tackles than holding midfielders (4.03 against 3.79).
   - Attacking midfielders commit the most fouls (1.76).
   - Keepers complete about 56% of their passes.
   - DF percentiles pool centre-backs with full-backs.
   - Reliability uses rows that repeat the same starters six times.
5. **Margins are tight.**
   - Over six seasons, `leader_npxg_gap` is 1.69 against a 1.75 ceiling, and `top_npxg_share` is 0.385 against 0.40.
   - In the committed season Toure leads by one goal (3 to 2), and `top_npxg_share` is 0.43, high but indicative.
   - The fix report's "every one-season band is in" covers the league, physical and style tables, not the leaders.
6. **The Fabric copy is stale.** The lakehouse still holds the 0.6.0 season, as the fix report says. Re-sync it before
   any Fabric cross-check is claimed for 0.7.0.

## Numbers

Six pooled seasons, unless noted.

| | Value |
|---|---|
| Open-play crosses per team per 90 | 19.1; corner deliveries 4.3; corners 5.3 |
| Open-play cross completion by role | W 18.0%, FB 18.1% |
| Leaders (per 90) | npxG Toure 0.79, then Ibarra 0.47; np goals Toure 0.63, then Ibarra 0.54; key passes Nakamura 2.48; xA Whitfield 0.36; crosses Brennan 9.89; progressive carries Whitfield 10.07; tackles won Mensah (CM) 4.60; interceptions Lindqvist (DM) 2.23 |
| Pass completion by role | CB 81.6%, FB 81.5%, DM 88.4%, CM 86.6%, AM 84.9%, W 68.4%, ST 79.7%, GK 55.8% |
| Long-pass completion by role | CB 59%, FB 50%, W 41%, DM 71%, ST 70% |
| relocated_per90_m | 42 (diagnostic) |
| Shot outcomes | goal 136, saved 333, blocked 405, off target 624; np goals minus npxG -8.4 (within about one SD) |
