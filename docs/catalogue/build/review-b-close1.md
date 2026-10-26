# Catalogue review B, closing round 1: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at 179cd25 (`git diff main...HEAD`). I focused on what changed after
review round 3: fixes-3.md, levels.md, docs.md and verify-2.md. I fixed nothing.

**Not signed off.** I found two should-fix items and no must-fix items.

Both should-fix items are about wording and how checks are classified. Neither moves any data, pin or measurement, and
England is untouched. They are:
- **S-1.** The served notes say S10 "reports" orders against semi-pros, a level it never studied. One of those orders,
  sprint distance, is contradicted by the only full-match study cited beside it, yet it still counts as a sourced pass.
- **S-2.** "11 of 11 sourced checks pass" counts checks the build was tuned to pass as if they were independent
  evidence. The report already applies that caveat to England, but not here.

## How I checked

Everything ran offline with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric.
- I read the reports, the diffs to CLAUDE.md, `data/synthetic/README.md`, `docs/criteria.md` and `docs/architecture.md`,
  and the sources and notes in `realism.py` and `taxonomy.py`.
- I printed the served realism notes with `realism.realism(...)` for Spain amateur men (`pass_pct`, `sprint_distance`,
  `ball_losses`), Ghana U17 (`peak_speed_mean`) and England semi-pro women (`pass_pct`).
- I recomputed per-level means and standard errors from `realism.json`'s `per_season`.
- I queried `/api/catalogue/rank` through FastAPI's TestClient for academy forwards and women's forwards.
- I did not repeat the verifier's work: England's pins, Femi Toure's goals, the rebuilds, the suites, the privacy walk,
  and checking that each source exists. I accept those results.

## What the closing fixes achieved (review B round 3)

| Round 3 | Status | What I checked |
|---|---|---|
| S-A future dates | **Fixed** | `as_of` is 2026-10-24 and every upload falls on or before it (the verifier counted 90 of 90). Careers now play their home matches in August, before college. The term-time matches are gone. |
| S-B "most goals" put a defender first | **Fixed** | Raw numbers are compared only within a level and percentiles only within a position. "Most goals in England" opens on Femi Toure on all six surfaces. |
| S-C U17 speeds | **Fixed** | U17 mean peak match speed is 26.80 km/h, inside 24.9-28.7. The multiplier is now set from the match peak, not the sprint test, which is the right reading of [S5]. |
| S-D levels barely differ | **Fixed** | Pass completion now runs from 80.5 (semi-pro men) to 69.4 (U17), and ball losses from 12.7 to 18.5. Women sit 8.5 and 7.9 points below same-tier men. Every youth and tier order goes the football way. |

The levels now look like football. The order is right on pass completion, ball losses, fouls and tackles. Women's
high-intensity distance sits below men's, with the zone caveat served. Youth and amateur goals sit at or above senior
(Caicedo-Parada's direction), with U19 and U20 the exception (see nits). Directness is honestly limited to fewer passes
per 90 and earlier shots, and "no source for long-ball share" is said in the report. The open items left to Zaid in
round 3 were decided and built rather than waved through.

## Should fix

### S-1. S10 is served as reporting orders against semi-pros, and its sprint order contradicts its own note

- **Where:** `realism.ORDERS` entries `amateur_sprint_distance`, `amateur_pass_pct` and `amateur_ball_losses`, and the
  template in `realism._order_note`. Every sourced order is served as "Order check [Sx]: the source reports that
  <label>". The counts follow from this classification in `docs/catalogue/realism.md`, CLAUDE.md §2.11 and §4.2,
  `data/synthetic/README.md` ("Realism per level") and `docs/criteria.md`.
- **What a scout or judge reads on a Spain amateur player today:**
  - "Order check [S10]: the source reports that amateurs complete fewer passes than semi-pros. … as reported".
  - "Order check [S10]: the source reports that amateurs lose the ball more often than semi-pros. … as reported".
  - "Order check [S10]: the source reports that amateurs sprint less than semi-pros (…; in full matches [S9] found no
    difference between second-tier professionals and fourth-tier amateurs, only the top tier sprinted more). …
    as reported".
- **Why it is wrong:**
  - [S10] compares French fourth-division amateurs with **international** players, in **small-sided games**. It says
    nothing about semi-pros, so "the source reports that … semi-pros" and "as reported" attribute to it a claim it does
    not make.
  - For pass completion and ball losses the direction is a fair extrapolation, but it is an extrapolation.
  - For sprinting, the extrapolation is contradicted:
    - the only full-match study cited, [S9], finds no difference between the professional second tier and the amateur
      fourth tier;
    - Djaoui et al. 2017 (levels.md, context) find no difference in match maximal speed between Ligue 1 and
      fourth-division elite amateurs.

    A check whose served text says the best evidence points the other way cannot count as a sourced pass.
- **Fix (wording and classification only; nothing regenerates):**
  - Move `amateur_sprint_distance` to `basis: "assumed"`, with `covers` naming S10's span and S9's contrary finding.
  - For `amateur_pass_pct` and `amateur_ball_losses`, either:
    - say what was sourced in the label, for example "amateurs complete fewer passes than international players in
      small-sided games [S10]; the build extends the direction to semi-pros", with the verdict worded "as the build
      extends it"; or
    - move both to assumed as well.
  - Make the template say "the source reports a direction that the build extends" whenever the levels compared are not
    the source's own.
  - Then update the counts. With the sprint order moved: **10 sourced checks (1 band, 9 orders), all pass; 7 assumed
    orders, 6 hold, 1 fails.** These counts appear in realism.md, CLAUDE.md §2.11 and §4.2, the data README and
    criteria.md. Run `recheck-realism`; no measurement moves.

### S-2. The headline counts calibration targets as independent evidence

- **Where:** "Sourced checks: 11 of 11 pass" (realism.md); "11 of 11 sourced checks pass" (CLAUDE.md §2.11 and §4.2);
  "one sourced band … and ten sourced orders … (all pass)" (data README); "one sourced band and ten sourced orders
  between levels pass" (criteria.md).
- **What happened (levels.md and taxonomy.py say so themselves):**
  - **U17 band.** The U17 speed multiplier was set so that U17's mean peak match speed "lands on 26.8 km/h, the
    source's mean" (`taxonomy.LEVELS`, "speed" source). The band check then compares 26.80 with that same source's
    26.8 ± 1.9. It cannot fail, short of a bug.
  - **Women's pass gaps.** The women's `execution` sizes are "sourced gap [S1, S12]: 8 points". The two women's pass
    orders then check that the gap falls inside 5-11 around those 8 points.
  - **Amateur orders.** The amateur `execution` (2.65) was sized by hand to give "about 8 points below" semi-pro. The
    amateur pass and ball-loss orders check that direction.
  - **Separation.** "Every step beyond season-to-season noise" measures match randomness on one fixed set of squads:
    `measure` regenerates the same clubs, people and ratings each season. Steps of 20-38 standard errors are therefore
    a property of the scales chosen, not evidence about football.
- **Why it matters:**
  - The report applies this caveat to England in its opening lines: Premier League bands "are a tuning target there, not
    independent evidence".
  - The youth peak-speed order is honestly served "by construction".
  - The same standard is not applied to the U17 band or the women's gaps. These are the two most quotable "sourced"
    passes, and a judge reading "11 of 11 pass" will take them as validation.
- **Fix (wording only):**
  - Add a `calibrated` flag (or reuse `construction`) to the U17 band and the two women's pass gaps, and serve it:
    "calibrated to this source: the level scale was set from it, so this confirms the build follows its source".
  - Say the same for the amateur execution size on the amateur orders.
  - Split the headline. For example: "10 sourced checks pass: 3 confirm a calibration (the U17 band, the women's pass
    gaps), the other 7 follow from level scales set in the source's direction; none is independent validation of
    football below the professional line."
  - Put one sentence in realism.md's Method saying that the standard errors are conditional on each competition's drawn
    squads.

## Nits

1. **U19 is the lowest-shooting and lowest-scoring level.** U19 team shots are 10.37 per 90 against 12.13 for senior
   semi-pro men (5.9 SE) and 12.17 for U18. Goals fall from U18's 1.82 to U19's 1.05 (2.8 SE), while U20 scores 1.10
   and senior 1.20.
   - levels.md's open item 4 calls U19 and U20 "within noise", which is true against senior but not for the U18 to U19
     drop or for U19's shots.
   - The likely cause is the two U19 competitions' own style (U19 already had the fewest shots before execution, 9.84).
   - It runs against the youth-score-more direction in Caicedo-Parada et al. No check is claimed. Name it in levels.md or
     realism.md, or look at the Spain and Morocco U19 style offsets in the UI round.
2. **The youth speed curve has the wrong shape.** U17 to U20 rises in steps of about 0.9 km/h, then jumps 2.0 km/h from
   U20 to senior. Maturation curves flatten in the late teens ([S7]: the differences were explained by maturation), so
   the biggest step falling between 19-year-olds and seniors is the opposite of growth. Part of the jump is also a
   measurement mismatch: [S5]'s youth tracking against a Premier-League-calibrated senior. It is an assumed order and
   only ever compared within youth pools, so no ranking suffers. Say "linear between U17 and U20; the senior step mixes
   level and measurement" in the assumed order's note, or interpolate concavely in a later round.
3. **The women's speed basis contradicts the U17 fix.** levels.md fixed U17 because a sprint-test speed is not a match
   peak: the generator's players reach 94-97% of capacity in matches, where real players reach about 87% [S5]. The
   women's multiplier (0.82-0.83) is still a sprint-test ratio: [S3]'s 27.3 km/h over England's generator capacity of
   33.4. The result (26.8 km/h, below [S14]'s elite 28.0-29.4) is plausible, so nothing moves, but `taxonomy`'s
   "sourced [S3]" overstates the method. Word it "direction and rough size from [S3]; below the elite reference [S14]".
4. **Career realism.**
   - Olivia King plays her English home match on 2026-08-16, and her college plays from 08-22. NCAA women's preseason
     usually starts in early August, so "before she flew out" is tight.
   - Two of the three student-athletes play for **semi-pro** sides. Being paid by a club is an NCAA amateurism problem.
     "As a registered amateur" in the story would close both gaps.
5. **Short samples at the top of boards** (carried). Academy forwards' non-penalty goals board: the top five have
   50-60 minutes from 2 appearances each. They are marked noisy, but the UI round should demote or visibly flag
   sub-90-minute rows, as round 3 suggested.
6. **levels.md contradicts the committed file.** It says "12 sourced checks (1 band, 11 orders)" and youth distance
   "142.0 m, 4.4 SE". The committed file and realism.md give 11 (1 band, 10 orders) and 172.8 m, 3.6 SE. It is a
   phase record, but it is the report people will open for S-C and S-D. Add a one-line pointer to realism.md.
7. **A source missing from the served list.** `taxonomy._YOUTH_SPEED` cites [S7], which is in design.md §14 but not in
   `realism.SOURCES`. The string is never served, so this is only a gap in the list.
8. **Carried from earlier rounds:**
   - no `no_spread` flag on pools where every value is equal;
   - unqualified cells return `pool.reason: null`;
   - four clubs with one 30-minute upload can never qualify;
   - boards come in competition order rather than level order;
   - architecture.md's MCP table omits `rank_by`;
   - Linux CI has not yet run the 60 catalogue pins, the level tests or the report tests. The PR is their first run.

## What is good

- The level picture a scout reads is now football-shaped and sourced where a source exists:
  - women about 8 points below same-tier men in pass completion, inside [S12]'s gap;
  - amateurs and youth losing the ball more;
  - U17 match peaks on [S5]'s mean.
- `execution` is inert when absent and England's kwargs never carry it. The 8 Germany pins did not move, which proves
  it in the data.
- The realism report separates bands, orders, assumed orders, references and "none". It never puts a Premier League band
  on a level below the line except as an upper reference, and it lists what it could not check.
- The one assumed order that fails (distance U18 < U19) is shown and explained, not tuned away.
- Dates are honest: one as-of date, and careers that fit the calendars.
- Rankings are now ones a scout can trust: raw numbers only within a level, percentiles only within a position, and
  every board sized and labelled.
- CLAUDE.md §2.11, the data README, criteria.md and architecture.md mark the catalogue "not merged, not deployed"
  everywhere, and their counts match the data.
