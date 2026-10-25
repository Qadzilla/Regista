# Catalogue: fixes after review round 1

Branch `feature/catalogue`, 2026-10-25. This round answers the twelve findings of review A
(`review-a-pass1.md`, engineering) and review B (`review-b-pass1.md`, football, data science and product). Everything was
checked offline: nothing was sent to the live app, Azure or Fabric. Tests run with `REGISTA_DOTENV=` (no `.env`).

**Non-negotiables held:**
- England semi-pro men (the Regista League) is byte-identical. `league.json` was not touched, the 30 season pins hold,
  and Femi Toure keeps his 5 league goals.
- `generate()` without attributes is unchanged, and the generator was not edited.
- Existing endpoints answer as before without the new parameters (`tests/test_catalogue_backcompat.py` passes).
- No hidden rating is served.

## What moved in the data

| File | Change | Why |
|---|---|---|
| `data/catalogue/catalogue.json`, the competition files | Spain U19 renamed **Liga Juvenil Levante Interior**, region **Valencian Community** (was Liga Juvenil Meseta Norte, Castile and León). Every competition has an `eligibility` label: the birth-date rule for youth competitions, `null` otherwise. 48 youth dates of birth moved forward one year (Ghana U17 21, Spain U19 16, Morocco U19 7, England U18 4, as the review counted). Three career stories reworded. | S5, S6, M2 |
| `src/regista/catalogue/pins.py` | The five Spain U19 pins were re-recorded. The competition's name is in each match header (`meta.competition`). Putting the old name back into a rebuilt stream gives the old pin exactly (checked for `cm_eu19_01_pij_sot`), so nothing else moved. The other 55 catalogue pins and all 30 league pins are unchanged. | S5 |
| `data/catalogue/reliability.json` | Re-measured (1,524 matches, 291 s). Every level's numbers are **identical** to before. Only the fingerprint moved, because the labels and dates of birth are part of it. | stamp |
| `data/catalogue/realism.json` (new) | The realism verdicts, committed. For each level: pooled aggregates and one aggregate per measurement season. For every band and order: values, margins, standard errors and verdicts. It is stamped with the same fingerprint and shipped in the image (`Dockerfile`, `cloud.smoke`). | M1 |

Dates of birth never reach the generator (`LEAGUE_FIELDS` is attributes, role, height and foot), and the move uses no
random draw. So no rating, no career pick and no match moved. A test asserts this.

## The findings

### Review A

1. **England's catalogue cards left out claims and uploads.** Fixed.
   - `catalogue_api.catalogue_profiles()` now serves England from the app's own season (`season_api.season()`:
     fixtures plus confirmed claims and finished Player-view uploads) through `CatalogueProfiles.use_england`.
   - So `/api/players?competition=co_eng_sp_men`, with or without `scope=competition`, gives today's cards. When an
     England row has more matches than the metrics engine counted, the pooled percentile uses the profile's own
     minutes.
   - The terminal metrics and career rows stay on the league's 30 fixtures, as the Scout terminal does. They say so in
     `basis`, which is set on the catalogue cards, the career block and the catalogue player.
   - `/api/players/{id}?include=career` adds `career.profile_only_matches`: the uploads and claims that the profile
     counts and the career rows do not.
   - New test: `test_englands_catalogue_cards_count_a_confirmed_upload_as_todays_cards_do`, with one fake upload.
2. **`/api/players` `total` in its default mode.** Fixed.
   - `offset` now defaults to none. Without it the response is today's, exactly.
   - With `offset` (0 included) the response pages: `total` counts every card the filters keep, and the response adds
     `offset`.
   - Documented in the docstring and in api.md. Test: `test_players_total_counts_every_card_when_paged`.

### Review B, must fix

- **M1. Realism notes stated failed checks as facts.** Fixed.
  - Each band and order keeps its `label`, now worded as what the source reports. It is served with the committed
    verdict, the value or values, and the margin.
  - The note reads, for example: "Band check [S5]: the source reports that … (band 24.9-28.7 km/h). Measured at this
    level (6 full regenerated seasons): 29.68 km/h: fails, 0.98 km/h above the band."
  - An order step now needs a margin of at least two standard errors of the season-to-season spread. Otherwise it is
    **not separated**, never a pass.
  - Committed verdicts:

    | Verdict | Checks |
    |---|---|
    | fail | U17 peak speed band; amateur pass completion |
    | not separated | women's ball losses, semi-pro (0.05 against noise of +/- 0.24); youth peak speed (U19 to U20 by 0.06 against +/- 0.09); youth distance (U18 to U19 by 6 m against +/- 60) |
    | pass | the other six |

  - `realism` also gains `verdict`, `zone_note` and `verdicts_from`. Without a current file every check says "Not
    measured on this catalogue".
- **M2. Olivia King's story.** Reworded, so no pins move: "an English student-athlete at a US college who is also
  registered with her home club in Yorkshire and plays for it when she is in England: its opening match in September and
  after the college season". Her fixtures fit it: Oxenridge's round 1 on 2026-09-06, then 2026-11-29. A new test
  checks every story against its fixtures, and the other two college careers' "outside the college season" against the
  source window.

### Review B, should fix

- **S1. U17 speeds.** **Not retuned (Zaid's call).** Lowering the youth speed multipliers, or the share of capacity youth
  reach in a match, moves the youth pins and the level reliability. The served U17 note now says "fails, 0.98 km/h above
  the band", so nothing claims otherwise. Decide before a youth profile is demoed.
- **S2. Levels barely differ in event data.** **Stated plainly, not retuned (Zaid's call).**
  - `ALL_WARNING`, also served as the mixed-level warning, now says that raw event rates barely encode level and that
    percentiles within pools are the comparison.
  - engine.md says plainly that the levels differ in ratings and pace, not in raw event rates.
  - A level-relative passing and retention effect (design.md §5.2) moves every catalogue pin.
- **S3. The default leaderboard mixed levels and genders.** Fixed.
  - Lists whose rows come from more than one level rank by percentile within each row's own pool. These are
    `/api/catalogue/rank`, the sort of `/api/catalogue/players`, `search_catalogue_players`, and the terminal endpoints
    with catalogue parameters.
  - Ties go, in order, to rows from pools that are not small, then to more minutes, then to the value. Rows without a
    percentile are listed after, unranked.
  - Men and women are on separate boards (`boards`, each row's `board`), and ranks restart at 1 on each board.
  - Within one level the order stays by value. `rank_by=value` keeps raw ranking as an explicit option, on the API and
    on the MCP tool.
  - The reviewer's example now ranks Femi Toure first among men (98th percentile in a pool of 33). Hannah Mitchell
    heads the women's board.
  - Tie-break: the reviewer suggested the value. I put pool size and minutes before it, because values from different
    levels are what this fix stops comparing, and the sample size was the second complaint.
- **S4. `noisy` ignored the row's minutes.** Fixed in engine code only; nothing regenerated.
  - The level's r is adjusted to the row's minutes with Spearman-Brown, k = minutes / median half-season minutes, and
    the row is noisy when r_k is below 0.3. It is served as `r_at_minutes`.
  - England's competition scope keeps today's flag.
  - A test recomputes the flag by hand for four metrics on every sparse row, and checks that some short rows are now
    flagged where the half-season flag was not.
- **S5. Spanish careers.** Fixed by relabelling. Both Spanish competitions are now in the Valencian Community, and the
  juvenil plays for the senior amateur club his academy side is affiliated with, in the same territorial federation.
  Five pins re-recorded, as above.
- **S6. Youth birth dates.** Fixed, both ways the reviewer offered.
  - The rule is a public label (`eligibility`, served by `/api/competitions`) and lives in `taxonomy.BIRTH_CUTOFFS`:

    | Competition | Rule |
    |---|---|
    | England U18 | born on or after 1 September 2008 |
    | Spain U19 | born 2008-2010 |
    | Brazil U20 | born 2006 or later |
    | Ghana U17 | born 2010 or later |
    | Morocco U19 | born 2008 or later |

  - Every date of birth is drawn inside its competition's rule (`define.within_cutoff`), with no pin moved.
  - The Brazil and Morocco rules follow the usual calendar-year convention. They are labels of invented competitions,
    not quotes of a federation's rulebook.
- **S7. "Semi-pro" on a Premier League scale.** Reworded. Every realism note and level note now says that absolute
  values sit on a Premier-League-calibrated scale, likely overstate real football below the professional line, and
  should be read within pools. England is unchanged.
- **S8. Women's sprint zones.** **The note is done; the better fix is not built (Zaid's call).**
  - Women's cells on the five zone metrics (`hsr_distance`, `hi_distance`, `sprint_distance`, `sprints`, `hi_efforts`)
    carry `threshold_note`, and their realism a `zone_note`: men's FIFA zones; women's tournaments use 19 and 23 km/h
    [S11].
  - The medians the review quoted check out: 3.3, 1.5 and 11.8 per 90 among qualified outfielders.
  - Computing women's own zones needs the generator's physical record to carry them, which moves the women's pins.

## Tests

- New or changed:
  - `test_catalogue_api.py`: England with an upload; `/api/players` paging; the cross-catalogue board by pool with
    gender boards; the screen's `rank_by`; the MCP tool's `rank_by` and boards.
  - `test_catalogue_metrics.py`: the sample-aware noisy flag; women's zone notes; committed realism verdicts (current,
    served, steps consistent with their noise); the realism smoke check; the slow test also re-measures the U17 band
    verdict.
  - `test_catalogue_define.py`: stories against fixtures and registration; birth cut-offs.
  - `test_packaging.py`: `realism.json` is in the image.
- Full quick suite on this Mac: **949 passed** (4 min 13 s). Slow suite: **14 passed** (1 min 53 s). Linux CI runs on the PR.
