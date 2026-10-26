# Catalogue review B, closing round 2: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at 9ec46c5 (`git diff main...HEAD`). I focused on what changed after
closing round 1: fixes-close1.md, with commits da3a404 (the heavy-touch records in the data contract) and 51aaa45 (the
realism wording, S-1 and S-2). I fixed nothing.

**Not signed off.** I found one should-fix item and no must-fix items. It is a single wrong count in the data contract,
fixed by changing one word. Nothing regenerates and England is untouched.

## How I checked

Everything ran offline with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric.
- I read the diffs of da3a404 and 51aaa45, plus `realism.py`, `docs/catalogue/realism.md`, CLAUDE.md §2.11 and §4.2,
  `data/synthetic/README.md` (Catalogue, Heavy touches, Realism per level) and `docs/criteria.md`.
- I printed the served notes with `realism.realism(key, competition_id)` for nine pairs:
  - Spain amateur men: `pass_pct`, `sprint_distance`, `ball_losses`;
  - Ghana U17: `peak_speed_mean`;
  - England semi-pro women: `pass_pct`;
  - US college women: `hi_distance`;
  - England U18: `distance`;
  - Japan university men: `ball_losses`, `pass_pct`.
- I listed `data/catalogue/realism.json`'s bands and orders with their basis, verdict, `calibrated` and `extends`.
- I regenerated the report with `python -m regista.synth.report --catalogue`. It equals the committed realism.md except
  for stdout's trailing newline.
- I ran `tests/test_catalogue_report.py` and the new
  `test_sourced_checks_say_how_the_build_relates_to_them` (15 passed).
- I checked [S15] against its Europe PMC record. It was added after verify-2, so no one had checked it yet. It is
  correct as cited: Djaoui, Chamari, Owen, Dellal, J Strength Cond Res 2017;31(6):1509-1517. The abstract compares
  first-division French professionals with fourth-division elite amateurs and finds no difference in match maximal
  sprinting speed by level, which is what the served `contrary` text says.
- I counted heavy touches in the local `data/catalogue/matches` against the competition files.
- I searched the repo for stale counts ("11 of 11", "ten sourced", "6 assumed" and similar). None is left outside
  `docs/catalogue/build/` and the unrelated league reports.
- I did not repeat the verifier's work: England's pins, Femi Toure's goals, the rebuilds, both suites, the privacy walk
  and the source checks. I accept those results.

## What closing round 1 achieved

| Close 1 | Status | What I checked |
|---|---|---|
| Review A: heavy touches missing from the contract | **Fixed** | The README bullet matches the generator (`exec_touch` 0.022 per unit of e, x2 under pressure within 3.5 m, capped at 0.3, `_heavy_touch` at generator.py:1512). It covers the four records in order, how they differ from a failed touch that goes `out_of_play`, and that a teammate's recovery still counts as a ball loss. 157 of 597 heavy touches go to the receiver's own side: I get the same numbers, but the match count stated beside them is wrong (S-1 below). |
| B S-1: [S10] served as reporting orders about semi-pros | **Fixed** | `amateur_sprint_distance` is now an assumed order. Its served note says what [S10] covers and gives the evidence against it ([S9], [S15]). The amateur pass and ball-loss notes now read "the source reports a direction between other levels, which the build extends (...)" and end "as the build extends it". The same treatment covers the six women's orders ([S1], [S12] are elite). Only `youth_distance`, inside [S8]'s own U13-U18 span, still reads "as reported", which is correct. |
| B S-2: calibration targets counted as evidence | **Fixed** | Three checks are served `calibrated: true`: the U17 band ("it cannot fail short of a bug") and the two women's pass gaps. The other seven are served "scaled in the source's direction". The headline is split: 10 of 10, of which 3 confirm a calibration and 7 follow from level scales, "none independently validates football below the professional line". The Method now says the standard errors are conditional on the drawn squads. No scale value is served, only words. |

The counts agree everywhere they are quoted: CLAUDE.md §2.11 and §4.2, the data README, criteria.md and realism.md.
They are 10 sourced checks (1 band, 9 orders), all passing, and 7 assumed orders, of which 6 hold and running distance
U18 < U19 fails. The README also says plainly that the amateur sprint order "holds but goes against the full-match
studies [S9, S15]".

The realism story is now one I would put in front of a judge or a recruitment analyst:
- every sourced check says what the source compared;
- every check says whether the build was set from it or only in its direction;
- the one band below the professional line is flagged as a calibration;
- the only failure is shown, not tuned away.

## Should fix

### S-1. The data contract says "89 built catalogue matches"; the catalogue has 60

- **Where:** the "Heavy touches" bullet in `data/synthetic/README.md`, which reads "on 89 built catalogue matches
  (2026-10-25) 157 of 597 heavy touches (26%) were recovered by the receiver's own side". fixes-close1.md §1 says the
  same.
- **What happened:** the local, git-ignored `data/catalogue/matches/` holds 89 folders.
  - 60 are the catalogue's current uploads.
  - 29 are leftovers from before the S-A date fix (fixes-3). Their ids are no longer in any competition file, and their
    dates run from 2026-10-31 to 2027-05-22, after the catalogue's as-of date.
  - Those 29 were built before `execution` existed and contain no heavy touches. All 597 heavy touches and all 157
    same-side recoveries come from the 60 current matches.

  So the ratio is right, but the denominator is not.
- **Why it matters:** the README is the contract, and judges read it. Everywhere else it says "60 uploaded matches
  (3-8 each)". Someone who reads "89 built catalogue matches" next to that will wonder whether the catalogue holds
  matches it does not declare, or matches after its as-of date.
- **Fix (one word):** "on the 60 catalogue matches". Nothing regenerates. You could also delete the 29 stale local
  folders (nit 2).

## Nits

1. **The amateur notes say the same thing twice.** The served note for `amateur_pass_pct` and `amateur_ball_losses`
   opens with the `extends` sentence ("[S10] compares fourth-division French amateurs with international players in
   small-sided games ...; the build extends its direction ..."). The label then repeats it in brackets ("direction from
   [S10]: amateurs against internationals, small-sided games; extended by the build to semi-pros"). Shortening either
   one would make the most-read amateur note about a third shorter. The women's labels do not repeat it.
2. **Stale local match folders.** The 29 future-dated folders above are not served:
   - `resolve_match` goes through the competition files;
   - the Docker image ignores the folder and builds its own;
   - the pins check by definition.

   They did mislead the count in S-1, though. `python -m regista.catalogue build` could warn about folders it does not
   own, or a one-off clean-up could remove them.
3. **The amateur sprint assumption runs against the evidence.** The build gives amateurs 11% less sprint distance than
   semi-pros (208 against 233 m per 90, 16 SE) and a lower mean peak match speed (30.68 against 31.46 km/h). Yet [S9]
   finds no sprinting difference between the second and fourth tiers, and [S15] finds no match maximal-speed difference
   between Ligue 1 and the fourth division. This is now served honestly as an assumption with the contrary evidence, so
   nothing is overstated, and rankings never compare levels. Whether amateur speed and stamina should come back towards
   semi-pro is a modelling choice for a later round (Zaid's call). Changing it would regenerate the catalogue.
4. **The women's ball-loss "scaled" sentence is slightly loose.** It reads "the women's technical execution was set in
   this direction". More precisely, that execution was sized to [S12]'s 8-point pass gap, and the ball-loss rise is a
   by-product. This is true either way and needs no change.
5. **Carried from closing round 1, unchanged and not in scope:**
   - U19 is the lowest-shooting level (10.37 team shots per 90) and scores less than U18;
   - the youth speed curve's biggest step is U20 to senior;
   - `taxonomy` still calls the women's speed multiplier "sourced [S3]" (a sprint-test ratio);
   - the career stories do not say "as a registered amateur" for the semi-pro student-athletes;
   - rows from short samples sit at the top of some boards;
   - levels.md's two hand-written figures disagree with the committed file;
   - [S7] is missing from `realism.SOURCES` (a source string that is never served);
   - boards come in competition order, not level order;
   - architecture.md's MCP table omits `rank_by`;
   - Linux CI has not yet run the 60 catalogue pins or the report tests.

## What is good

- The served realism notes are now exact about their evidence:
  - "the source reports" appears only where the source studied those levels ([S8], U17 to U18);
  - "the build extends" appears everywhere else;
  - the one assumed order that goes against published evidence names that evidence.
- Calibration is said where it applies, including "it cannot fail short of a bug" on the U17 band, the most quotable
  check. The headline says none of it independently validates football below the professional line. This is the same
  standard the report already applied to England's Premier League tuning.
- The conditional standard errors are stated in the method that is written into the committed file and the report, so
  "37.9 SE" can no longer be read as evidence about football.
- The heavy-touch contract bullet is precise enough to tell a miscontrol from a ball out of play, and it matches the
  generator.
- [S15] is real and cited exactly. Every count in CLAUDE.md, the data README, criteria.md and realism.md matches the
  committed file. England, the pins and both back-compat tests are untouched.
