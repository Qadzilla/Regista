# Part A review B, round 1: football and data science

I reviewed `git diff main...HEAD` on `feature/terminal-engine` at 643d0a4 on 2026-10-23. My lens was whether a scout would believe the
numbers and whether each metric follows the rule it cites. I changed no code. All figures come from the committed season
(30 fixtures of 30 minutes) through `regista.season.metrics.load_metrics`, with my own scripts in the scratchpad. Everything
here is synthetic.

**Verdict: not signed off.** Most of the engine is good work:
- **Definitions.** Progressive passes and carries, key passes, SCA/GCA, PAdj, PPDA, save %, per 90 and the FBref percentile
  rank follow the wording in `industry-metrics.md`, and every metric names its rule and its source.
- **Possession adjustment.** It is sane: a player sees about 31 minutes of opponent possession per 90 on the pitch (0.345 per
  minute), so PAdj comes to about 0.97 times the per-90 value, as in real football.
- **What stops sign-off.** League totals are in band, but the spread between individual players is not. A scout looks at the
  leaders first, and the leaders are where it breaks.

## Must fix

### 1. The league's leaders are 1.5 to 3 times the best real players, and no band checks them

Every event band tests a league or team total. Only the physical bands test individuals (lowest and highest regular, the
fastest player). For events, nothing checks the top of the distribution.

| Metric per 90 (qualified) | Regista leader | Roughly the best real PL player |
|---|---|---|
| shots | Ustinov 12.2, Toure 11.3 | about 4-5 |
| npxG | Ustinov 1.51, Toure 1.41 | about 0.8-0.9 |
| non-penalty goals | Toure 2.90 | about 1.0 |
| key passes | Nakamura 8.2 | about 3.5 |
| xA | Nakamura 1.30 | about 0.4-0.5 |
| SCA | Nakamura 11.5 | about 7 |
| progressive carries | P. Petrov 26.9 | about 8-10 |
| touches in the box | Ustinov 20.1 | about 10-12 |
| tackles + interceptions | Valente 11.1 | about 6 |
| interceptions | Yilmaz 7.2 | about 3 |
| crosses | Reyes 10.6 | about 6-7 |

- **Why.** Shot volume is concentrated. Only 8 players in the league took 10 or more shots all season. Toure takes 50% of
  Brookfield's shots and 51% of its npxG; Ustinov takes 59% and 66% of Ashby's. Real top strikers take about 20-25% of their
  team's shots and about 30-40% of its xG.
- **Finishing is too strong.** Toure scores 9 non-penalty goals from 4.37 npxG, twice his xG. Elite finishers beat xG by about
  10-25% over a long run. The finishing weight (0.45 logit per z, with Toure at z = 2.6) makes "goals minus xG" a signal about
  ten times stronger than in real football.
- **What to do.** Add individual bands with sources (top qualified player per 90 for shots, npxG, key passes, xA, SCA,
  progressive carries, touches in the box, Tkl+Int) and a band for the top striker's share of team shots. Then retune player
  selection so the leaders sit near real maxima. The verifier flagged Toure's 3.2 goals per 90, but the problem covers every
  leaderboard, and the leaderboards are what a scout reads.
- **Toure can stay top scorer.** He needs a realistic edge, not an absurd one. With about 10 full matches in a season, he
  could also lead on non-penalty goals minus xG, or across the pooled seasons.

### 2. Centre-backs barely contest aerial duels

Aerial duels per player over the season, for qualified players (mean, max):

| Role | ST | DM | AM | CM | FB | W | CB | GK |
|---|---|---|---|---|---|---|---|---|
| mean | 14.2 | 12.0 | 9.7 | 7.5 | 7.3 | 7.1 | **2.9** | 0 |
| max | 18 | 17 | 12 | 9 | 11 | 13 | 6 | 0 |

- **Real football is the other way round.** Centre-backs contest the most headers (about 4-6 per 90).
- **Why this happens.** In `synth/generator.py` around line 1576, a duel happens only on a pass that would otherwise be
  completed, against the outfielder nearest the landing spot. Clearances, headers from crosses that defenders win first, and
  goal kicks contested by centre-backs are not modelled the way the shape needs.
- **Consequences:**
  - The centre-backs' top `aerial` rating (81) never shows.
  - Split-half reliability for aerial duels won is about 0, as the verifier found.
  - The 10-duel minimum leaves exactly one defender with an aerial win %. Yet "Aerial win %" is one of the scouts' core ten
    and a default DF column (`DEFAULT_COLUMNS["DF"]`). It is blank for every centre-back, and seven of the twelve show 100%
    on 1-6 duels.

## Should fix

1. **There are more progressive carries than progressive passes, and carries make up 92% of xT added.**
   - The league has 60.5 progressive carries per team per 90 against 35.8 progressive passes.
   - In FBref's Opta-era Premier League data, carries run at roughly half the passes.
   - Carries average 11.3 m, of which 10.7 m is forward, so nearly every carry is progressive.
   - "xT added" therefore mostly measures carrying. Retune carry direction in league mode, and add a sourced band for the
     ratio of progressive passes to progressive carries.
2. **Cross completion is 47%.** Opta's typical figure is about 22-25%. Wingers' "crosses completed" and "cross completion"
   percentiles sit on a skill rate twice the real one. Add a band and lower `cross_delivery`.
3. **Save % counts penalties in shots on target faced** (`sot_faced`, "penalties included").
   - This is inconsistent with the engine's own `shots_on_target`, which excludes penalties as FBref does.
   - I believe FBref's Save% tooltip says it does not include penalty kicks; its GK table lists PKatt, PKA and PKsv
     separately. I could not load FBref to confirm (403).
   - Either way, exclude penalties from SoTA, GA-for-Save% and Save%, or label the difference.
4. **The ratio minimums are scaled one way and the minutes another.**
   - Qualifying minutes are scaled to 30-minute matches: a third of club minutes, 100.6.
   - The FBref "per squad game" attempt minimums are multiplied by 10 matches without that scaling. FBref's rate is per
     90-minute game, so 4 shots, 5 take-ons, 10 aerial duels and 7 challenges is three times FBref's rate per minute.
   - The rule label ("FBref: .395 shots per squad game, times 10 matches") reads as FBref's rule when it is not equivalent.
     This is what leaves aerial win % nearly empty for defenders.
   - Scale by club minutes / 90 (1.3, 1.7, 3.2 and 2.1, so 2, 2, 4 and 3 after rounding up), or keep the stricter values
     and label them as Regista's.
5. **The profile and the terminal give different percentiles for the same stat** (verifier finding, confirmed in
   `scout.py` against `fbref_percentile`). For Toure, key passes show "higher than 6%" on one page and the 8th percentile
   on the other. Two numbers for one stat on two pages undermine trust. Use one rule.
6. **Two physical bands compare a league mean against the range of individual players.**
   - Walking share is banded 0.54-0.78 and jogging share 0.15-0.35. Those are the Premier League's lowest and highest
     individuals, not the range a mean should fall in.
   - The league mean (walking 0.60, jogging 0.33) passes while sitting at the individual extremes: the average Regista
     player jogs like the PL's top jogger.
   - Band the mean against a mean, or band the lowest and highest individuals against the lowest and highest.
7. **Centre-backs run too little** (verifier finding, confirmed in the physical report).
   - Every regular centre-back runs 7.75-8.45 km per 90, below the Premier League's lowest regular (8.5 km).
   - They cover 300 m at 20 km/h and above, against 500-800 m.
   - The lowest-regular band passes only on Regista's own 7.5 km floor.
8. **High accelerations outnumber high decelerations by about 3 to 1** (68 against 21 per 90).
   - The match-demands literature (for example Harper, Carling and Kiely's 2019 systematic review) finds high-intensity
     decelerations at least as frequent as accelerations.
   - Both metrics are in the catalogue and get percentiles. Fix the braking model, or mark both metrics as unbanded and
     unrealistic.
9. **No PPDA band.** The metrics report says no citable league norm exists. The Analyst publishes Premier League team
   PPDA every season (roughly 8-9 for the hardest-pressing teams to about 16-17 for the most passive). Regista's 13.3-19.2
   is at or beyond the passive end. Rule 4 asks for a band wherever a Premier League norm exists. The same applies to
   possession and field tilt.

## Nits

- **Keepers.** There are 6 in the pool, so their percentiles move in steps of about 17. The API returns `peers`; part B
  should show it next to every percentile, and perhaps hide percentiles under about 10 peers.
- **The `xa` label.** It reads "xA (xG assisted)" and cites "FBref xAG / Wyscout xA". On FBref, "xA" is a different,
  pass-based column. Calling it "xAG" on screen would avoid confusing anyone who knows FBref.
- **Big chances.** At xG 0.30 or more, the league has 1.15 per team per 90, below Opta's typical rate (about 2). The label
  is honest; a lower threshold would track Opta better.
- **Demo seed note.** Maya's note "Finishes early and low across the keeper" cannot be backed by the data, which has no
  shot height. It is a fictional scout's note, but the rest of the seeds cite stats.
- **Penalty conversion** is 3 of 3 in the committed season (19 of 22 pooled, 0.86, against the PL's about 0.78). This is
  noise, but it deserves a diagnostic band.
- **Strikers' relocation.** They log 79 m per 90 of `relocated_m`, four to six times other roles (verifier). This is worth
  a look in `_place` for strikers.

## How I checked

- **Code.** I read the catalogue, the thresholds, the percentile, PAdj and value code in `season/metrics.py`, and the
  aerial-duel and pass code in `synth/generator.py`. I compared every definition with `industry-metrics.md` (rows 46, 74,
  104, 127, 187, 208 and 212).
- **Data.** From the built season I computed:
  - the top 5 per 90 for 27 metrics;
  - shot and npxG shares of team totals;
  - aerial duels by role;
  - G against xG by finishing rating;
  - PAdj against per-90 values;
  - opponent possession per minute played.
- **Sources.** One web check, of FBref's Save% wording, was blocked (403). Where I give a real-player comparison
  ("roughly the best PL player"), it is my own football knowledge, so treat it as an order of magnitude to be replaced by
  sourced bands. It is not a citation.
