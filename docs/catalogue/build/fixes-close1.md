# Catalogue fixes, closing round 1

Branch `feature/catalogue`, 2026-10-25. Three findings from the closing review round 1 (review-a-close1.md should-fix
#1, review-b-close1.md S-1 and S-2). All three are fixed. Nothing was regenerated: every measured value, margin,
standard error and verdict in `data/catalogue/realism.json` is unchanged (checked field by field against the previous
commit), and so are the catalogue fingerprint, `data/season/league.json`, `SEASON_PINS` and the generator.

Commits: da3a404 (heavy-touch records), 51aaa45 (realism wording).

## 1. The data contract now describes heavy touches (review A)

`data/synthetic/README.md`, Catalogue section, after "Hidden scales": a new **Heavy touches** bullet. It says:
- when one happens: catalogue sides with `execution` only, on the first touch of a received pass, with probability
  `exec_touch` x e (0.022 per unit of e), twice that with a marker within 3.5 m, capped at 0.3;
- the four records, in order:
  1. a `touch`, `outcome: fail`, qualifiers `first_touch` and `heavy_touch`;
  2. the possession ending `lost_by: dispossessed`, with no tackle;
  3. a `recovery` by whoever else is nearest, of either side;
  4. a possession `gained_by: rebound` (same side) or `loose_ball` (other side);
- how it differs from the old failed touch (`out_of_play`), that it follows the failed take-on's loose-ball convention,
  and that a teammate's recovery still counts as a ball loss.

I checked the record pattern on the 60 catalogue matches (corrected 2026-10-25, fixes-close2.md: the local folder held 89, of which 29 were stale pre-date-fix builds with no heavy touches; all 597 come from the 60 current matches): every heavy touch is followed by a recovery
and a possession with the stated `gained_by`, and every one ends the receiver's possession as `dispossessed`. 157 of
597 (26%) were recovered by the receiver's own side. The review counted 25 of 98 on six matches. No schema change was
needed: qualifiers are free tags.

## 2. S-1: the notes no longer say [S10] reports orders about semi-pros

`src/regista/catalogue/realism.py`:
- **`amateur_sprint_distance` is now an assumed order.** `covers` names [S10]'s span (fourth-division amateurs against
  internationals, in small-sided games). A new `contrary` field gives the evidence against it: [S9] (no difference in
  sprinting between second-tier professionals and fourth-tier amateurs in full matches) and [S15]. [S15] is Djaoui L,
  Chamari K, Owen AL, Dellal A, "Maximal sprinting speed of elite soccer players during training and matches", J
  Strength Cond Res 2017;31(6):1509-1517, doi:10.1519/JSC.0000000000001642. It is now in `SOURCES`; before, it was cited
  only in levels.md. The served note reads "Assumed order, no published band ([S10] covers ... only): ... Against it:
  ...".
- **`amateur_pass_pct` and `amateur_ball_losses` stay sourced, and both say what is sourced.** Their labels read
  "(direction from [S10]: amateurs against internationals, small-sided games; extended by the build to semi-pros)".
  A new `extends` field holds the full sentence.
- **New template wording.** When an order has `extends`, the note reads "Order check [S10]: the source reports a
  direction between other levels, which the build extends (...)". It ends "as the build extends it", not "as reported".
- **The women's six orders also carry `extends`.** I went beyond the finding here, applying the same rule. [S1] and
  [S12] compare elite women and men, not semi-pro or college players, so the build extends their direction, and for the
  pass gaps their size too. Every sourced order except `youth_distance` is now worded as extended. `youth_distance`
  sits inside [S8]'s own U13-U18 span.
- **Served payloads.** `realism()`, `order_checks()` and `band_checks()` serve `extends`, `contrary`, `calibrated` and
  `calibration`. These are new keys on catalogue payloads only. No existing endpoint changes shape. No hidden rating or
  level scale value is served: the calibration text names the scale in words, never its value.

**Counts:** 10 sourced checks (1 band, 9 orders), all pass. 7 assumed orders: 6 hold, 1 fails (running distance
U18 < U19). They are updated in `docs/catalogue/realism.md` (regenerated), CLAUDE.md §2.11 and §4.2,
`data/synthetic/README.md` ("Realism per level") and `docs/criteria.md`. `python -m regista.catalogue recheck-realism`
re-stamped the committed file on its own stored aggregates.

## 3. S-2: calibration targets are no longer counted as independent evidence

- **Every sourced check now carries `calibrated` and `calibration`.**
  - Calibrated, because a level scale was set from the same source's number: the U17 band [S5] and the two women's pass
    gaps [S12]. Their notes say "Calibrated to this source: ... the check confirms the build follows its source", and
    the U17 note adds that it cannot fail short of a bug.
  - Scaled in the source's direction: the other seven. These are the amateur pass and ball-loss orders (the amateur
    execution was sized by the build in this direction), the women's ball losses and high-intensity distance, and the
    U17 < U18 distance step.
  - Assumed orders carry `calibrated: null`.
- **The headline is split.** realism.md, via `report.catalogue_summary`, now counts `calibrated`, `scaled` and
  `extended`. It reads: "Sourced checks: 10 of 10 pass ... Of those that pass, 3 confirm a calibration ... and the other
  7 follow from level scales set in the source's direction; none independently validates football below the
  professional line. 8 of the 9 sourced orders extend a direction the source reports between other levels ...".
- **More detail in realism.md.** Under "Kinds of check", a new "calibrated / scaled" entry. Under the band table, a
  "Calibrated" line. Under the sourced orders, a "How the build relates to each sourced order" list. The Sources column
  marks each order extended, calibrated or scaled.
- **The standard errors are now stated as conditional.** `realism.SE_CONDITIONAL` is appended to the method text
  (`method_text()`, used by `compute` and by `recheck`), and it appears in realism.md's Method section. It says the
  standard errors are conditional on each competition's drawn squads: every measurement season regenerates the same
  people, so many standard errors reflect the chosen scales, not football.
- **Docs.** The same split is in the data README, criteria.md and CLAUDE.md.

## Tests

- New: `test_sourced_checks_say_how_the_build_relates_to_them` (tests/test_catalogue_metrics.py). It covers the sprint
  order as assumed with [S9] and [S15] against it, S15 in the sources, `calibrated` and `calibration` on every sourced
  check, `extends` on the S10 and women's orders, the summary counts (10/10, 1 band, 3 calibrated, 7 scaled; 7 assumed,
  6 hold, 1 fails), the conditional-SE sentence in the method, and that no served note says "the source reports that
  amateurs" or "... that women".
- Updated: the amateur note now expects "as the build extends it" (test_catalogue_metrics.py), and the summary counts
  (test_catalogue_report.py).
- Untouched and green: tests/test_backcompat.py and tests/test_catalogue_backcompat.py.
- Quick suite: 980 passed (4 min 21 s). Slow suite: 15 passed (2 min 8 s). Both on the Mac.

## Not fixed

Nothing. The review's nits (U19 shooting, the youth speed curve's shape, the women's speed basis, career realism, short
samples at the top of boards) were not in this round's list and are unchanged.
