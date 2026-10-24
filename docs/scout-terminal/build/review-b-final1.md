# Part A review B, closing round 1: football and data science

I reviewed `git diff main...HEAD` on `feature/terminal-engine` at bd33cc4 on 2026-10-24. My lens was football and data
science. I read the earlier reviews and fix reports first, then checked the current code and data myself. I changed no
code. Everything here is synthetic: invented players in an invented league.

**Verdict: not signed off.** Round 2's fixes hold, and every band passes over six seasons. The bands, though, check
league totals and the single leader. They never check which roles produce the numbers. Looked at by role, the league
contradicts football in ways a scout sees on the first sort.

## What I ran

| Check | Result |
|---|---|
| `python3 -m pytest -q` | 755 passed, 9 deselected (4 min 30 s) |
| `python3 -m pytest -q -m slow` | 9 passed (2 min 28 s) |
| `python3 -m regista.synth.report --league` | events 13/13, league mode 10/11 (penalties low, indicative), physical 14/14, style 4/4, leaders 8/12 (indicative) |
| `python3 -m regista.season.audit` | Toure top scorer with 4 goals; next is Brennan with 3 |
| `python3 -m regista.season.metrics` | diagnostics below |
| Six pooled seasons, my own script | `audit.season_matches(seasons=6)` into one `SeasonMetrics.from_streams` (66 starters, about 1,500-1,800 minutes each) |

`tests/test_backcompat.py` is part of the fast suite and passes.

## Round 2 fixes: checked

| Fix | What I saw |
|---|---|
| Shot accuracy and save % | 40.6% and 71.3% in the committed season; 42.8% and 70.3% over six. Both in band |
| Keepers' long passes | 46.3% of passes are 32 m or more (band 37-57%) |
| Take-on success | 43% (band 30-45%) |
| Leaders verdict only over six seasons | Holds. Single-season verdicts read "indicative", with minutes beside them |
| `sample` block and `noisy` flags | Present on the terminal cells and descriptions. `season_r` is computed with Spearman-Brown |
| `realism` on every metric | Present. The four "likely low" notes match the data: passes into the box 3.7 per team per 90, pressure regain 13.7%, medium and long completion as stated |
| Demo claims | Hold on the committed season (Toure 4 goals, the most shots on target per 90 of the 18 regular forwards, 2 of 12 take-ons won; pl_ash_09, pl_ash_10, pl_dun_06 and pl_eas_03 rank as stated) |
| Ratings drive outcomes | Over six seasons, within role, ratings track what they should: top speed and peak speed r 0.99, stamina and distance 0.75, dribbling and take-on % 0.66, defending and tackles won 0.64, passing and pass % 0.59, aerial and aerial win % 0.34 |

## Must fix

### 1. Role shapes contradict football, and no check looks at them

These are per-90 means of qualified players by kit role, over six pooled seasons. The committed season shows the same
pattern.

| Metric | Regista | Football |
|---|---|---|
| Passes attempted | **ST 62.6, W 56.2** most; CB 32.0, FB 35.1 fewest | centre-backs and holding midfielders make the most passes, strikers the fewest |
| Touches | **ST 84.6**, W 76.0; CB 41.4 | the same order as passes |
| Passes received | **ST 58.9**; CB 22.0 | |
| Crosses | **FB 0.31**, W 6.46. In the committed season, 12 full-backs made 9 crosses between them | full-backs are among the top crossers: the report's own crosses band names Doughty and Robertson |
| Tackles won | **ST 2.96**, about the same as DM 3.14, ahead of FB 2.17 and CB 1.45. Over six seasons, two strikers lead the league (H. Ustinov 4.05, A. Ustinov 3.93); in the committed season, three of the top four are strikers | strikers win the fewest tackles of any outfield role |
| Fouls committed | **ST 3.42**, the most of any role | forwards foul often, but at about half this rate |
| Fouls won | **W 0.89, ST 0.98**, the fewest of any outfield role; DM 1.61 the most | wingers and forwards draw the most fouls |
| Pass completion | CB 80.1%, below DM 85.6% and CM 84.2% | centre-backs complete the highest share |

**Why it matters.**
- **The first sort.** Sorting the terminal's all-positions view by passes or touches puts Toure top (75.7 passes and
  102 touches per 90 in the committed season), with only strikers and wingers in the top five.
- **Bands that pass for the wrong reason.**
  - The tackles-won leader band cites Palhinha, a holding midfielder, and passes because a striker fills it.
  - The crosses leader band cites two full-backs, and passes because wingers fill it.
  - The `passes` band is a two-team total, so it cannot see who makes the passes.
- **The labels.** `realism` marks `passes`, `tackles_won` and `crosses` as "checked". That is true only of the league
  level.

**Likely causes in `synth/generator.py`.**
- **Passes.** `_pick_pass_target` weights receivers by distance and a forward tilt, so forwards get the ball most and then
  pass most. This comes from the 0.1.0 design.
- **Crosses.** A cross needs a wide position in the final third, which full-backs rarely reach.
- **Tackles and fouls.** These go to the nearest marker of the player on the ball. Pressing forwards are the nearest
  marker in the opponent's build-up.

**What to do.**
- **Retune in league mode only.** The back-compat path stays untouched.
- **Add shape checks.** Use the `cb_aerial_won_rank` pattern, with sources, for:
  - passes and touches by role (CB or DM above ST)
  - crosses by full-backs (FB at least a third of W)
  - tackles won by strikers (ST below FB, CB and DM)
  - fouls won by wingers and forwards (W and ST above CB)

The real-football side of the table comes from my own football knowledge, except where it names the report's source.
Treat those entries as order-of-magnitude claims that need sourced bands, not as citations.

## Should fix

1. **Toure is the league's only scoring threat: the leader bands pass on one player.** Over six pooled seasons:

   | | Toure | Next best | Premier League 2023/24 (the report's own sources) |
   |---|---|---|---|
   | npxG per 90 | 1.11 | 0.47 (2.4 times lower) | Haaland 1.04, Isak 0.81 (1.3 times) |
   | Goals per 90 | 1.37 | 0.48 (2.9 times) | Haaland 0.95, Isak 0.84 (1.1 times) |
   | Shots per 90 | 6.0 | 3.74 | Nunez 4.75, Haaland 4.27 |
   | Goals over six seasons | 26 | 8 | |

   - **His share of Brookfield.** He scores 53% of the club's goals and takes 46% of its npxG. Round 1 put real top
     strikers at about 30-40% of team xG. His shot share, 29%, is the only share with a band.
   - **The rest of the league.** Without him, the best npxG per 90 (0.47) and goals per 90 (0.48) would fail the leader
     floors (0.61). The leader bands pass because of one designed outlier.
   - **What to do.** Add a band on the gap between the leader and the next player, or on the top three, using the
     rankings the report already cites. Also band the top scorer's share of club npxG. Then lift the other forwards, or
     soften Toure's edge, while keeping him top scorer.
   - **The committed season hides this.** It reads 4 goals against 3, and 1.0 npxG per 90 against 0.52.
2. **`touches_in_box` is labelled "checked", but it counts the same touch records that `touches` calls not comparable.**
   - **The data.** The league has 12.4 touches in the box per team per 90 (13.7 over six seasons). I recall FBref's
     Premier League team "Att Pen" touches at about 25 (my figure, unsourced).
   - **The leader band.** It fails low in the committed season (5.61 against a floor of 7.0). Over six seasons it passes
     by 0.84 (Toure 7.84; next best 5.64).
   - **Why.** Generator 0.5.0 halved the touch records (one per 1.82 s), and this metric shrank with them.
   - **Where it is used.** It sits in the FW default columns and in the similarity template.
   - **What to do.** Mark it "not comparable" like `touches`, or band it at team level with a read source.

## Nits

1. **The noisy flag and the percentile pool measure different things.**
   - **The flag.** It measures luck within a kit role, which is a correct statement.
   - **The pool.** Percentiles pool a whole position: DF mixes CB and FB, FW mixes W and ST.
   - **The effect.** A "noisy" metric's percentile can still be mostly role. Wingers against strikers on crosses, for
     example, give a stable ranking that says little about the player.
   - **What to do.** Say this on the flag, or offer role peers.
2. **"Not noisy" is claimed on small samples.**
   - **The rule.** `MIN_ROWS` is 8. `cross_pct` is marked reliable (r 0.41) from 18 rows, and its 95% interval runs from
     about -0.07 to 0.73.
   - **The rows are not independent.** The pooled n counts the same 66 starters six times, with the same ratings.
   - **What to do.** Raise the minimum, or mark these "not measured".
3. **7 of the 8 DF default columns are noisy, and so are 5 of the 8 FW defaults** (npxG per shot r -0.00, xA r 0.01).
   - Reliable alternatives exist: passes, pass %, progressive pass distance, long pass %, npxG, SCA, touches in the box.
4. **Keepers make about 13-14 passes per 90 at 57-59% completion.**
   - The generator's own comment says Premier League keepers make "about 30 passes a match".
   - `gk_pass_pct` is a GK default column. It is labelled unchecked, which is honest, but a "likely low" note would match
     the four others.
5. **Keepers cover 3.9 km per 90** (a diagnostic). I recall about 5-6 km for Premier League keepers (unsourced).
6. **The committed season has no penalties.** The verdict is marked indicative; across the band, no penalty in 903 minutes has a chance of about 2-25% (Poisson). Still,
   every penalty metric is zero in the season people see.
7. **Shot accuracy sits at the band's floor:** 40.6%, against 0.40. Six seasons give 42.8%, still below the Premier
   League's twenty-year 45.1%. In band, but on the low side.
8. **Strikers are caught offside 1.5-1.7 times per 90.** The league total is in band (5.08, ceiling 5.5); the striker
   share is high.

## Numbers

| | Committed season | Six seasons |
|---|---|---|
| Goals per 90 (both teams) | 2.29 | 2.62 |
| Save % | 71.3% | 70.3% |
| Key passes per non-penalty shot | 0.80 | 0.80 |
| SCA per team per 90 | 23.1 | 23.0 |
| Pressure regain rate | 13.7% | 13.6% |
| Share of xT added from carries | 69.7% | 66.2% |
| PPDA range | 10.4-12.8 | |
| Possession range | 45.1-53.7% | |

Full role table (six seasons, per 90, qualified players):

| | GK | CB | FB | DM | CM | AM | W | ST |
|---|---|---|---|---|---|---|---|---|
| passes | 12.9 | 32.0 | 35.1 | 40.9 | 42.1 | 47.9 | 56.2 | 62.6 |
| touches | 16.4 | 41.4 | 46.0 | 55.3 | 57.9 | 65.3 | 76.0 | 84.6 |
| pass % | 57.2 | 80.1 | 81.4 | 85.6 | 84.2 | 83.1 | 74.7 | 79.3 |
| crosses | 0 | 0.05 | 0.31 | 0.18 | 0.62 | 0.43 | 6.46 | 0.69 |
| tackles won | 0.01 | 1.45 | 2.17 | 3.14 | 2.71 | 1.88 | 1.48 | 2.96 |
| fouls | 0.02 | 0.29 | 0.67 | 0.99 | 1.07 | 1.82 | 1.64 | 3.42 |
| fouls won | 0.47 | 1.26 | 1.21 | 1.61 | 1.38 | 1.41 | 0.89 | 0.98 |
| aerial duels won | 0.01 | 3.28 | 1.28 | 0.59 | 0.27 | 0.28 | 0.53 | 1.51 |
| progressive passes | 0 | 1.19 | 2.13 | 3.38 | 5.35 | 7.63 | 5.28 | 3.12 |
| progressive carries | 0 | 0.19 | 0.62 | 0.48 | 0.86 | 2.76 | 5.98 | 5.84 |
| distance (km) | 3.92 | 9.37 | 10.37 | 10.60 | 11.02 | 9.47 | 9.65 | 9.06 |
| sprints | 0.1 | 5.2 | 14.1 | 5.1 | 7.1 | 6.4 | 14.1 | 9.2 |

Physical shapes are right: midfielders run furthest, and full-backs and wingers sprint most. So are aerials, with
centre-backs winning the most. The on-ball and defensive-action shapes are where it breaks.
