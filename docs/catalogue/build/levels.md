# Levels that play like their level (review B, S-C and S-D)

Branch `feature/catalogue`, 2026-10-25, step 2 after fixes-3.md. Review B round 3 left two items open for a decision:
S-C (U17 match speeds above their sourced band) and S-D (levels barely differ in event data). The decision is to fix
both in this branch, which is unmerged, so the catalogue pins could move. England semi-pro men (the Regista League) does
not move.

## What changed, in short

- **S-C, speed.** The youth top-speed multipliers were taken from a sprint test, but the band is for match peaks. They
  are now set from U17's *match* peak speed [S5] and interpolated in match-peak terms up to senior. U17's mean peak
  match speed is now **26.80 km/h**, at the centre of the band 24.9-28.7. Before, it was 29.68 and failed by 0.98.
- **S-D, execution.** A new optional per-competition parameter, `execution`, lowers a side's technical execution
  against absolute football, not against the opponent. It covers pass completion, first touches on received passes and
  keeping the ball under a challenge. It is inert when absent: England's kwargs never carry it.
  - Pass completion now runs from **80.5%** (semi-pro men) to **69.4%** (U17) and **69.3%** (college women).
  - Ball losses per 90 now run from **12.7** to **18.5**.
  - Women complete **8.5** (semi-pro) and **7.9** (college) points fewer passes than same-tier men. The sourced gap is
    8 points [S12].
- **Verdicts.** All 12 sourced checks (1 band, 11 orders) pass, the weakest at 3.6 standard errors.
  - Of the 6 assumed orders (no published band), 5 pass.
  - One fails: running distance U18 < U19, which is beyond [S8]'s span. It is reported below with numbers.
- **What did not move.** England is untouched: `data/season/league.json`, `SEASON_PINS`, `LEAGUE_GENERATOR_VERSION`
  (0.7.1), the back-compat tests and `tests/data`. Femi Toure still has 5 league goals, none a penalty, two clear.
  `data/season/reliability.json` was re-stamped, and only its fingerprint changed.

## Sources read for this step

Read on 2026-10-25 (PubMed abstracts through E-utilities, and publisher pages). Only what an abstract or page states is
quoted. Sources [S1]-[S11] are design.md §14's. This step confirmed their authors and DOIs and added [S12]-[S14]. The
full entries are in `regista.catalogue.realism.SOURCES` and in design.md §14.

| Id | Source | What it gives this step |
|---|---|---|
| S5 | Al Haddad H, Simpson BM, Buchheit M, Di Salvo V, Mendez-Villanueva A. *Int J Sports Physiol Perform* 2015;10(7):888-896. doi:10.1123/ijspp.2014-0539 | U17 peak **match** speed 26.8 ± 1.9 km/h, which is **87.2 ± 5.7%** of maximal sprinting speed (U13: 23.4 km/h and 92.0%). This is the band and the reason for the retune. |
| S6 | Al Haddad H, Simpson BM, Buchheit M, Mendez-Villanueva A. ECSS Bruges 2012, abstract. https://lida.sport-iat.de/ta/Record/4029276 | Sprint-test maximum 30.7 ± 1.2 km/h at U17. The old multiplier was set from this, which explains the 1-3 km/h excess. |
| S12 | Pappalardo L, Rossi A, Natilli M, Cintia P. *PLoS One* 2021;16(8):e0255407. doi:10.1371/journal.pone.0255407 | Pass accuracy per team and match: **0.84 ± 0.05** at the 2018 men's World Cup against **0.76 ± 0.08** at the 2019 women's World Cup (Wyscout). Women's teams win the ball back sooner: recovery time 19.6 s against 27.3 s. |
| S1 | Bradley PS, Dellal A, Mohr M, Castellano J, Wilkie A. *Hum Mov Sci* 2014;33:159-171. doi:10.1016/j.humov.2013.07.024 | In the Champions League, women lost the ball more often and completed fewer passes (ES 0.5-0.9). There was no difference in touches, possession time or duels won. |
| S10 | Dellal A, Hill-Haas S, Lago-Penas C, Chamari K. *J Strength Cond Res* 2011;25(9):2371-2381. doi:10.1519/JSC.0b013e3181fb4296 | Fourth-division French amateurs against internationals, in small-sided games: amateurs completed a lower percentage of passes and lost more possessions. Direction only. |
| S13 | Bradley PS, Carling C, Gomez Diaz A, Hood P, Barnes C, Ade J, Boddy M, Krustrup P, Mohr M. *Hum Mov Sci* 2013;32(4):808-821. doi:10.1016/j.humov.2013.06.002 | Premier League against Championship and League 1: pass completion, forward and total passes, balls received and touches per possession were **4-39% higher** in the Premier League. The lower standards ran more at high intensity. |
| S14 | Bradley PS. FIFA Training Centre, Women's World Cup 2023 physical analysis, part 3, 2024 | Top speeds in games of **28.0-29.4 km/h** by position. An upper reference for women's match peaks. |
| (context) | Djaoui L, Chamari K, Owen AL, Dellal A. *J Strength Cond Res* 2017;31(6):1509-1517. doi:10.1519/JSC.0000000000001642 | Match maximal sprinting speed did **not** differ between French first-division professionals and fourth-division elite amateurs. Not a check; see the open items. |
| (context) | Caicedo-Parada S, Ortega-Toro E, Palao JM. *Int J Exerc Sci* 2025;18(3):575-590. doi:10.70252/KNPB8178 | World Cups 2003-2019, decisive matches only: goals per team per match were higher at U-17 (winners 2.78, losers 0.67) than U-20 (2.49, 0.52) and senior (2.20, 0.46). Youth tournaments score more, not fewer. Used to judge goals, not as a check. |

**What was looked for and not found.**
- No published pass completion or ball-loss figure by youth age group. Saward et al. (NTU) model the *frequency* of
  successful passes by age, which is position-specific. Hegedüs et al. 2025 report correlations only.
- No pass completion figure for amateur or semi-pro football in matches.
- No source for long-ball share by level.

So the youth passing order, the steps between the men's senior tiers, and every execution size except the women's are
**Regista's assumptions**. They are stated as such in the code (`taxonomy._EXEC*`) and in the served notes (assumed
orders, "no published band").

## S-C: speed set from match peaks

**Why it failed.** The generator's players reach about 94-97% of their top speed in a match. England: mean capacity
33.4 km/h against a mean match peak of 31.46. Real U17 players reach 87.2% of their sprint-test maximum in a match
[S5]. Taking U17's sprint-test 30.7 km/h [S6] as the generator's top speed therefore produced match peaks 1-3 km/h too
high.

**Fix.** The multipliers are now calibrated to match peaks, measured on six regenerated seasons:

| Level | top speed × before | after | mean peak match speed before | after | basis |
|---|---|---|---|---|---|
| U17 | 0.92 | **0.81** | 29.68 (band fail by 0.98) | **26.80** (band pass) | sourced band [S5]: 24.9-28.7 |
| U18 | 0.95 | **0.85** | 30.26 | **27.68** | interpolated (assumption) |
| U19 | 0.96 | **0.88** | 30.57 | **28.55** | interpolated (assumption) |
| U20 | 0.97 | **0.92** | 30.63 | **29.47** | interpolated (assumption) |
| senior semi-pro men | 1.00 | 1.00 | 31.46 | 31.46 | reference (unchanged) |

- The youth order U17 < U18 < U19 < U20 < senior now steps about 0.9 km/h each way, then 2.0 km/h to senior. Before,
  the U19 to U20 step was 0.06 and not separated. It holds **by construction** and is still served as an assumed order
  that tests the build, not football.
- **Acceleration multipliers are unchanged** (Regista's assumption, no band read).
- **Women's multipliers are unchanged.** The sources do not say they are wrong. Semi-pro and college women's match
  peaks (26.81 and 26.78 km/h) sit below elite women's game top speeds at the 2023 Women's World Cup (28.0-29.4 km/h
  [S14]). That reference is now served on `peak_speed_mean` in women's pools.
- **Youth sprint numbers fall a lot**, because youth peaks now sit near the 25 km/h sprint zone. U17 sprint distance
  went from 173 to 93 m per 90. Youth pools' five speed-zone metrics now carry a `threshold_note` (new
  `YOUTH_ZONE_NOTE`), as women's already did: youth studies use lower or individual thresholds (above 16.1 km/h in
  [S8]).

## S-D: technical execution by level

**Why levels did not differ.** Every rating moves an outcome through a skill z. A level's passers and markers carry the
same offset, so in head-to-head outcomes they cancel. Amateur pass completion (81.38%) came out above semi-pro men's
(80.53%), and semi-pro women and men differed by 0.05 ball losses per 90.

**The mechanism** (design.md §5.4, `generator.LEAGUE["exec_*"]`). A side whose team spec carries `execution` = e has
these effects, all absolute (they do not depend on the opponent's level):

| Effect | Weight | What it does |
|---|---|---|
| Pass completion | `exec_pass` 0.25 log-odds per unit | Every pass and cross arrives less often. |
| First touch | `exec_touch` 0.022 per unit, ×2 under pressure | A received pass is miscontrolled: a `touch` event with outcome fail and qualifiers `first_touch` and `heavy_touch`. The ball runs loose and the possession is lost as a dispossession; whoever is nearest picks it up (`recovery`). |
| Retention | `exec_lose` 0.12 log scale per unit | The holder is dispossessed more often when challenged. |
| Shooting | `exec_shot` 0.30 log scale per unit | The holder shoots sooner from where he stands. Without this term, shots fell 25-35% at the lowest levels, the opposite of the youth direction in Caicedo-Parada et al. |
| Goalkeeping | `exec_keeper` 0.20 log-odds per unit, on the defending side | The keeper and last defenders keep out fewer shots, so goals do not fall with the level. |

**Inert when absent.**
- `_team_specs` copies `execution` only when it is truthy, and every branch is guarded by `if team.execution`. No random
  draw is added without it.
- England's kwargs never carry it: `league.json` has no `level`, and `tests/test_catalogue_levels.py` checks all 30
  England fixtures.
- Germany semi-pro men is the reference level (execution 0). Its 8 pins did not move.
- `LEAGUE_GENERATOR_VERSION` stays 0.7.1. The generator's header comment records the key as "catalogue (not a version
  either: inert without it)".

**Sizes per level** (`taxonomy.LEVELS[...].execution`):

| Level | execution | Pass completion target | Basis |
|---|---|---|---|
| semi-pro men | 0 | 80.5 (reference) | the Regista League |
| college men | 1.4 | about 3 points below semi-pro men | assumption |
| amateur men | 2.65 | about 8 points below | assumption; direction [S10, S13] |
| U20 | 1.2 | rising with age, about 2-3 points a step | assumption |
| U19 | 1.3 | | assumption |
| U18 | 2.3 | | assumption |
| U17 | 3.0 | | assumption |
| semi-pro women | 2.3 | 8 points below semi-pro men | sourced gap [S12] |
| college women | 2.8 | 8 points below college men | sourced gap [S12] |

- U19's execution is close to U20's because U19's two competitions (Spain, Morocco) already completed about 1.5 points
  fewer passes than U18 before any execution effect. The sizes were set so the order is clear, not to a formula.
- The U17 and U18 sizes were widened once (2.6 to 3.0 and 2.1 to 2.3) after a full measurement. With the smaller sizes,
  the U17-U18 steps passed at 2.6 standard errors and the U17 to U18 ball-loss step was not separated (0.34, standard
  error 0.29).

**Directness.** No long-ball mechanism was built, because no source for long-ball share by level was found. "More
direct" shows only where it follows from the mechanism:
- fewer passes per 90 (39.4 amateur against 43.3 semi-pro, an assumed order covering [S13]'s direction);
- earlier shots (`exec_shot`).

## Before and after, per level

Measured on six regenerated seasons of every competition: the full double round robin, 1,524 matches. Per-90 rates are
per outfield player. Goals and shots are per team per 90, penalties included. Before is HEAD (b5ca0c2). After is this
step.

| Level | | Pass % | Ball losses /90 | Passes /90 | Shots /90 (team) | Goals /90 (team) | Peak match speed | Distance /90 | ≥20 km/h /90 | ≥25 km/h /90 | Tackles won /90 | Fouls /90 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semi-pro men | before | 80.53 | 12.68 | 43.34 | 12.13 | 1.20 | 31.46 | 10,365 | 1,040 | 233 | 2.21 | 1.06 |
| | after | 80.53 | 12.68 | 43.34 | 12.13 | 1.20 | 31.46 | 10,365 | 1,040 | 233 | 2.21 | 1.06 |
| college men | before | 81.04 | 12.18 | 43.31 | 12.26 | 1.27 | 31.28 | 10,180 | 985 | 222 | 1.95 | 1.16 |
| | after | **77.21** | **14.95** | 41.66 | 12.52 | 1.53 | 31.31 | 10,246 | 1,002 | 224 | 2.25 | 1.20 |
| amateur men | before | 81.38 | 12.06 | 43.60 | 10.86 | 1.21 | 30.76 | 9,904 | 926 | 209 | 1.98 | 1.29 |
| | after | **72.08** | **17.49** | 39.35 | 12.64 | 1.66 | 30.68 | 10,065 | 945 | 208 | 2.60 | 1.55 |
| U20 | before | 81.33 | 12.19 | 44.03 | 11.47 | 0.79 | 30.63 | 10,122 | 968 | 203 | 1.88 | 1.05 |
| | after | **77.50** | **14.68** | 41.92 | 12.21 | 1.10 | **29.47** | 10,155 | 953 | 177 | 2.20 | 1.19 |
| U19 | before | 78.98 | 13.40 | 42.84 | 9.84 | 1.07 | 30.57 | 10,040 | 944 | 204 | 2.43 | 1.33 |
| | after | **74.13** | **16.22** | 41.09 | 10.37 | 1.05 | **28.55** | 10,051 | 899 | 149 | 2.65 | 1.46 |
| U18 | before | 79.87 | 13.00 | 43.27 | 10.24 | 1.06 | 30.26 | 10,034 | 925 | 193 | 2.31 | 1.33 |
| | after | **71.70** | **17.41** | 38.88 | 12.17 | 1.82 | **27.68** | 10,128 | 893 | 125 | 2.83 | 1.58 |
| U17 | before | 80.04 | 12.78 | 43.20 | 9.11 | 1.10 | 29.68 | 9,855 | 883 | 173 | 2.25 | 1.45 |
| | after | **69.36** | **18.48** | 38.20 | 11.06 | 1.87 | **26.80** | 9,955 | 812 | 93 | 2.96 | 1.73 |
| semi-pro women | before | 79.68 | 12.73 | 42.63 | 11.13 | 1.22 | 26.85 | 10,038 | 825 | 94 | 2.11 | 1.27 |
| | after | **72.00** | **17.34** | 39.28 | 12.45 | 1.52 | 26.81 | 10,158 | 847 | 92 | 2.62 | 1.41 |
| college women | before | 79.18 | 13.12 | 42.94 | 9.69 | 0.95 | 26.71 | 9,921 | 817 | 85 | 2.25 | 1.36 |
| | after | **69.30** | **18.75** | 38.43 | 11.30 | 1.32 | 26.78 | 10,087 | 830 | 84 | 3.04 | 1.54 |

How to read it:
- **Semi-pro men are byte-identical**: England plus Germany, both at the reference. This is the inertness check in
  numbers.
- **Pass completion** now orders the levels the way football does: women below same-tier men, amateurs below college
  below semi-pro, and youth rising with age.
- **Ball losses** rise by 18-46% below the reference. For the women's levels (+37% semi-pro, +25% against college men)
  this is consistent with [S12]'s recovery times, where women's teams regain the ball about 1.4 times as often. That
  ratio is context, not a check.
- **Goals are at or above the reference** at every level except U19 and U20 (1.05 and 1.10 against 1.20). Goals per 90
  carry a season-to-season standard error of 0.06-0.25 at these levels, so those two are within noise. The youth goal
  order in Caicedo-Parada et al. (U-17 above U-20 above senior) holds for U17 against senior and U20; U20 against
  senior is inside the noise. It is not a check.
- **Shots** sit within 15% of the reference at every level: 10.4-12.6 against 12.1.
- **Tackles won and fouls rise** at lower levels. More ball is lost, so more ball is won back. No band is claimed.
- **High-intensity running** stays lower at amateur level (945 against 1,040 m per 90), as Norway's standards show for
  sprinting [S9]. [S13] found the reverse for high-intensity running within English professional football. That is a
  different span and is not checked.

## Every verdict (data/catalogue/realism.json, six seasons)

A step passes when its margin is at least 2 standard errors the way expected ("SE" is the margin over its standard
error). Sourced checks count. Assumed orders are measured and served but never counted.

| Check | Basis | Before | After | Weakest step: margin, SE ratio |
|---|---|---|---|---|
| U17 mean peak match speed in 24.9-28.7 [S5] | band | **fail** (29.68) | **pass** (26.80) | 1.90 inside the band from the top, 1.90 from the bottom |
| amateur sprint distance < semi-pro [S9] | sourced | pass | pass | 25.3 m, 16.0 |
| amateur pass % < semi-pro [S10] | sourced | **fail** (81.38 > 80.53) | **pass** | 8.45 points, 31.3 |
| amateur ball losses > semi-pro [S10] | sourced (new) | (not checked; was 12.06 < 12.68) | **pass** | 4.81 per 90, 37.9 |
| youth distance U17 < U18 [S8] | sourced | pass | pass | 142.0 m, 4.4 |
| women's pass % < men's, semi-pro, gap 5-11 [S1, S12] | sourced (gap new) | pass (gap 0.85: would fail the gap) | **pass**, gap 8.53 | 8.53 points, 32.9 |
| women's pass % < men's, college, gap 5-11 [S1, S12] | sourced (gap new) | pass (gap 1.86: would fail the gap) | **pass**, gap 7.91 | 7.91 points, 22.9 |
| women's ball losses > men's, semi-pro [S1] | sourced | **not separated** (0.05) | **pass** | 4.66, 27.2 |
| women's ball losses > men's, college [S1] | sourced | pass | pass | 3.80, 20.6 |
| women's ≥20 km/h < men's, semi-pro [S1, S2] | sourced | pass | pass | 192.8 m, 18.1 |
| women's ≥20 km/h < men's, college [S1, S2] | sourced | pass | pass | 171.7 m, 15.6 |
| pass % amateur < college < semi-pro | assumed (new) | (amateur 81.38 > college 81.04 > semi-pro 80.53: would fail) | pass | 3.32 points, 12.1 |
| passes per 90 amateur < semi-pro | assumed (new; covers [S13]) | (43.60 > 43.34: would fail) | pass | 3.99, 24.8 |
| pass % U17 < U18 < U19 < U20 < senior | assumed (new) | (would fail: U17 80.04 > U18 79.87 > U19 78.98) | pass | U17 to U18 2.34 points, 5.3 |
| ball losses U17 > U18 > U19 > U20 > senior | assumed (new) | (would fail) | pass | U18 to U17 1.07, 4.0 |
| peak speed U17 < U18 < U19 < U20 < senior | assumed, by construction | not separated | pass | U19 to U20 0.92 km/h, 27.1 |
| distance U18 < U19 < U20 < senior | assumed | not separated | **fail** | U18 to U19 −76.7 m, 2.3 |

The "would fail" entries for new checks apply each new check to HEAD's committed aggregates; HEAD never ran them.

**The one that does not pass: distance U18 < U19 (assumed, beyond [S8]).**
- U18 runs 10,128 m per 90 and U19 10,051, so the step goes the other way by 76.7 m against a noise band of ±65.6.
  Before this step the two were level (10,034 and 10,040).
- The execution effect adds running: more turnovers mean more loose balls, chases and recovery runs. U18's execution
  (2.3) is higher than U19's (1.3).
- A larger stamina deficit for U18 was tried (stamina offset −3, with U17 at −2). It barely moved distance (10,128 to
  10,116), because the generator's motion caps are absolute and stamina only shapes late-match fatigue. It was reverted,
  so no unexplained offset was left in.
- No source covers U18 to senior (that is why the order is assumed). Within professional football the lower standards
  run *more* at high intensity [S13], which is what the mechanism does here.
- So the verdict stands as measured and is served as "Assumed order, no published band … fails". Fixing it would take a
  youth-specific physical capacity in the motion model, for example a willingness-to-run cap by age. That is a
  generator change for a later round.

## Measurement, pins and stamps

- **Catalogue definition**: `python -m regista.catalogue define` rewrote all 13 competition files.
  - Youth speed and accel draws: the draw sequence is unchanged; only the multipliers moved the values.
  - Spain amateur men follows, through its two U19 career players.
  - Every file's `level` record now carries `execution` (Germany's is 0.0).
  - `catalogue.json` is unchanged. `define --check` passes.
- **Catalogue pins**: 52 of 60 moved and were re-recorded with `python -m regista.catalogue check`; drift is `{}`. The
  8 Germany pins did not move (execution 0). Recorded on macOS; Linux CI has not run them.
- **Level reliability and realism**: `python -m regista.catalogue reliability` (6 seasons, 1,524 matches, 284 s).
  - Catalogue fingerprint `ad54e036b2f4aa3d` → `3a2d69dde65217a6`.
  - Noisy metrics per level (of 127):
    - unchanged: semi-pro men 83;
    - fewer: college men 77 → 73, U17 87 → 83, semi-pro women 73 → 65, U19 82 → 81;
    - more: U20 89 → 99, U18 93 → 97, college women 82 → 87, amateur 86 → 87.
  - The slow suite's U17 recomputation reproduces the committed table and band verdict.
  - `recheck-realism` re-stamped one wording change, a coverage span, with no season regenerated.
- **League reliability**: the generator edit changed `code_fingerprint`. `python -m regista.season.reliability`
  re-stamped `data/season/reliability.json`, and the diff is one line, `league_fingerprint` `a91152377b0055b4` →
  `8d76ab2949e04f20`. Every number is identical.
- **Served notes.**
  - Each realism note now carries the new verdicts.
  - The women's pass orders say "inside the sourced gap of 5-11".
  - The cross-level warning (`ALL_WARNING`) no longer says raw rates "barely encode level". It now says raw numbers
    carry each level's own football, so a raw number from one level is not a better or worse player than the same
    number from another.
  - Youth zone metrics carry `YOUTH_ZONE_NOTE`.
- **Hidden.** `execution` is a hidden scale like `skill_offset`. It is in the competition files only, never in
  `catalogue.json` or any payload. The hidden-key tests (API, engine, index) now include it.

## Code and tests

- `src/regista/synth/generator.py`: `Team.execution`, `_team_specs`, the `exec_*` weights, `_heavy_touch`, and the guarded
  terms in `_play_possession`, `_league_pass` and `goal_probability`.
- `src/regista/season/league.py`: `generate_kwargs` copies `level.execution` to both team specs when non-zero.
- `src/regista/catalogue/taxonomy.py`: `Level.execution`, the new speed multipliers and the reworded source notes.
- `src/regista/catalogue/realism.py`:
  - full source entries (authors, year, DOI or URL) and the new [S12]-[S14];
  - the new orders;
  - `gap` on orders (a step must fall inside a sourced size);
  - the women's `peak_speed_mean` reference [S14];
  - `YOUTH_ZONE_NOTE` and `zone_note_for`.
- `src/regista/catalogue/metrics.py`: the threshold note by level, and the reworded `ALL_WARNING`.
- Tests:
  - `tests/test_catalogue_levels.py` (new): England's kwargs never carry execution; catalogue kwargs carry their
    level's; execution orders the levels; execution lowers pass completion by more than 4 points and adds heavy touches
    on the same fixtures.
  - `tests/test_catalogue_metrics.py`: the served verdicts (the U17 band, the amateur and women's orders pass, the gap
    is served), the gap logic on synthetic aggregates, and youth zone notes.
  - `execution` added to the hidden-key sets.

## Tests run

- Quick suite: 965 passed, 14 deselected (4 min 23 s, macOS), on the final tree.
- Slow suite: 14 passed (1 min 53 s), including the U17 level recomputation against the committed table.

## Open

1. **Distance U18 < U19 (assumed order) fails** by 76.7 m (2.3 SE). See above. It needs a youth physical capacity in
   the motion model.
2. **Amateur peak speed.** Djaoui et al. 2017 found no difference in match maximal speed between French first-division
   professionals and fourth-division elite amateurs. Regista's amateur level (× 0.97, an assumption) peaks 0.78 km/h
   below semi-pro men. The catalogue's amateur leagues sit below a French fourth division, so this was left. The source
   leans against the gap.
3. **Execution sizes other than the women's are assumptions.** No published pass completion exists for amateur, college
   or youth matches. The served notes say "no published band" for those orders.
4. **Goals.** U19 and U20 score slightly below the reference (1.05 and 1.10 against 1.20, within noise). The keeper term
   is one weight for every level. No goal band is claimed.
5. **Phase records.** catalogue.md, api.md and engine.md (other than a pointer) still show the old level scales and
   aggregates. Phase 5 should fold this report in, with fixes-3.md.
6. **Linux CI** has not run the 52 re-recorded pins.
