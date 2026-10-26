# The catalogue: realism report and docs (phase 5)

Branch `feature/catalogue`, 2026-10-25, after levels.md. This is phase 5 of `docs/catalogue/build/design.md` (§10, §12):
the realism report per level, the data README's Catalogue section, CLAUDE.md §2.11 with the §3.0 and §4.2 lines, and
the catalogue's lines in `docs/architecture.md` and `docs/criteria.md`. Nothing here writes to the live app, Azure or
Fabric. No generator, data or pin changed.

## What was built

### `python -m regista.synth.report --catalogue`

- **What it reports.** Each of the nine levels against the checks a source supports. Kinds of check:
  - the sourced band (U17 mean peak match speed);
  - sourced orders between levels;
  - assumed orders (no published band): measured, shown, never counted;
  - references with no verdict: Premier League bands beside semi-pro and college men, and elite women's and NCAA figures;
  - "no published band" for event rates below the professional line.
- **The rest of the report.** A table of kinds per level and the level aggregates. A "Steps that do not pass" list,
  the speed-zone notes, what is not checked, the method, and every source with authors, year and DOI or URL.
- **Fast by default.** It reads the committed measurement `data/catalogue/realism.json` and re-runs the band and order
  checks on its stored aggregates (`realism.recheck`, in memory). No season is regenerated, and it runs in about 0.1 s.
  - It fails (exit 1) when the file is missing or stale (measured for another generator or catalogue fingerprint).
  - It also fails when the committed verdicts differ from what the checks' code computes on the same aggregates.
  - The report says which of these happened in its first lines.
- **`--regenerate`** measures the seasons again (`measure.measure`, then `realism.compute`).
  - `--level L` (repeatable) limits it to some levels; checks that need another level show "not measured".
  - `--repeat N` (default 6) and `--workers N` are passed through.
  - It compares the result with the committed file, level by level and season by season.
  - It **never writes** the committed file: that stays `python -m regista.catalogue reliability`'s job.
  - A run that measured nothing never claims agreement.
- **`--json`** prints the verdicts record with `summary` and `ok`. `--out PATH` writes the Markdown.
- **Argument checks.** `--level`, `--workers` and `--repeat` without `--regenerate` are refused (exit 2), as are an
  unknown level and `--catalogue` combined with a match directory, `--league` or `--profile`.
- **The `--league` report is unchanged.** `--repeat`'s default moved from `1` to `None` so the catalogue can default to
  six seasons; `--league` reads it as `args.repeat or 1`, and a test checks one season by default and six with
  `--repeat 6`.
- **Deterministic.** No dates or timings appear in the Markdown. `docs/catalogue/realism.md` is the report's own
  output, and a test checks it byte for byte.

### `docs/catalogue/realism.md`

Generated with `python -m regista.synth.report --catalogue --out docs/catalogue/realism.md`. It covers 6 regenerated
seasons of every competition's full double round robin, 1,524 matches, never the uploaded sample.

### Tests: `tests/test_catalogue_report.py`

14 quick tests and 1 slow test.

- A guard makes any generation fail, which proves the default report never regenerates.
- The verdict counts.
- Every level and check appears, with its verdict and in the right section (sourced or assumed).
- "none" for event rates at every level except semi-pro and college men.
- Every source id is listed.
- References carry no verdict, and S11 (a team's total per match) is never set against a per-90 number.
- The committed verdicts equal the checks' code.
- `realism.md` equals the report's output.
- No hidden rating or scale key appears in the JSON, and no scale key in the Markdown.
- 1,524 matches measured.
- Missing, stale (generator version) and out-of-step (a stricter `SEPARATION_SE`) measurements are each reported, and
  each fails.
- The command line, including the refused argument combinations.
- `--league` keeps one season by default.
- A regeneration that measured nothing claims no agreement.
- **Slow:** `--regenerate --level academy/U17/men` (Ghana, six full seasons, about 16 s on ten cores) equals the
  committed aggregates season by season. The U17 band passes, every order reads "not measured", and the committed file
  is untouched.

## Every check (from the committed measurement)

| Check | Kind | Verdict | Weakest step: margin (SE ratio) |
|---|---|---|---|
| U17 mean peak match speed in 24.9-28.7 km/h [S5] | band | pass (26.80) | 1.90 inside each edge |
| amateurs sprint less than semi-pros [S9] | sourced order | pass | +25.3 m (16.0) |
| amateurs complete fewer passes [S10] | sourced order | pass | +8.45 points (31.3) |
| amateurs lose the ball more [S10] | sourced order | pass | +4.81 (37.9) |
| running distance U17 < U18 [S8] | sourced order | pass | +172.8 m (3.6) |
| women's pass % below men's, semi-pro, gap 5-11 [S1, S12] | sourced order | pass | +8.53 (32.9) |
| women's pass % below men's, college, gap 5-11 [S1, S12] | sourced order | pass | +7.91 (22.9) |
| women lose the ball more, semi-pro [S1] | sourced order | pass | +4.66 (27.2) |
| women lose the ball more, college [S1] | sourced order | pass | +3.79 (20.6) |
| women's 20+ km/h distance below men's, semi-pro [S1, S2] | sourced order | pass | +192.8 m (18.1) |
| women's 20+ km/h distance below men's, college [S1, S2] | sourced order | pass | +171.7 m (15.6) |
| pass % amateur < college < semi-pro | assumed | pass | college to semi-pro +3.32 (12.1) |
| passes per 90 amateur < semi-pro | assumed | pass | +3.99 (24.8) |
| pass % U17 < U18 < U19 < U20 < senior | assumed | pass | U17 to U18 +2.34 (5.3) |
| ball losses U17 > U18 > U19 > U20 > senior | assumed | pass | U18 to U17 +1.06 (4.0) |
| peak speed U17 < ... < senior (by construction) | assumed | pass | U19 to U20 +0.92 (27.1) |
| distance U18 < U19 < U20 < senior | assumed | **fail** | U18 to U19 −76.7 m (−2.3) |

**Summary:** 11 of 11 sourced checks pass (1 band, 10 orders). Of 6 assumed orders, 5 hold and 1 fails.

Premier League references (no verdict): semi-pro men's pass completion 0.805, shots 24.3 and goals 2.41 per 90 for both
teams, distance 10.37 km, 20+ km/h 1,040 m, 25+ km/h 233 m, mean peak 31.46 km/h. All sit inside the bands the Regista
League was tuned to. College men's goals for both teams, 3.06 per 90, sit inside the 2.2-3.6 band too. These are shown
as references, never counted.

## Two corrections to levels.md

The report is generated from `data/catalogue/realism.json`, so where levels.md's hand-written figures differ, the file
is right.

1. **There are 11 sourced checks, not 12.** levels.md says "all 12 sourced checks (1 band, 11 orders)", but its own
   table lists 1 band and 10 sourced orders. All 11 pass.
2. **Running distance U17 < U18 is +172.8 m at 3.6 SE**, not "142.0 m, 4.4". The levels' aggregates give 10,127.6
   against 9,954.8. It is the weakest sourced check, and it still passes. levels.md's summary already said "the weakest
   at 3.6 standard errors".

levels.md is a dated build record, so it was not edited. CLAUDE.md, the data README and criteria.md quote the generated
numbers.

## Docs changed

- **`data/synthetic/README.md`:** a new "Catalogue" section before "Azure mapping". It covers:
  - the files, and England kept by reference;
  - competitions and levels: a table of the nine levels, their competitions and upload counts;
  - the hidden scales, with `execution` and `style_offset` inert when absent;
  - uploader and camera (camera a label only), and the as-of date 2026-10-24;
  - careers, pools (scopes, 5 peers for a percentile, small under 15, the 45-minute floor, England's xT grid, the rank
    rule, reliability) and realism per level.

  It also adds a `--catalogue` line to the commands at the top.
- **`CLAUDE.md`:**
  - **§2.11 "The catalogue (decided 2026-10-25)"** records Zaid's decisions:
    - recruitment below the professional line, from player and team uploads;
    - comparisons within level by default;
    - 14 competitions, with the Regista League kept as England semi-pro men;
    - synthetic data with invented names;
    - camera type is a label only.

    It also records what is built and what the UI round will do.
  - **§3.0:** the catalogue/metrics entry now names the committed verdicts and levels.md. A new entry for
    `synth/report.py --catalogue`, and two new commands.
  - **§4.2:** "As of 2026-10-25 (night)", with the previous entry renamed "Earlier, 2026-10-25 (evening)".
- **`docs/architecture.md`:** a "The catalogue" paragraph in The views (engine, API, realism per level), marked not
  merged and not deployed. The three catalogue MCP tools were added to the table, each marked not merged.
- **`docs/criteria.md`:** a catalogue paragraph under synthetic data quality, marked not merged and not deployed. The
  catalogue's pages and a Fabric push of it were added under "Planned, not built". The live counts (10 MCP tools, the
  test count) were left alone, because they describe the live app, which does not have the catalogue.

**Not claimed:**
- The branch has **not been pushed** and **no PR is open**: `gh pr list --head feature/catalogue` returns nothing, and
  the branch has no upstream. So the §4.2 line says "the branch is not pushed yet; the PR, merge and deploy wait for
  Zaid's go-ahead", not "PR open". Update that line when the PR exists.
- Nothing says the live app serves the catalogue.

## Invariants checked

- Unchanged since 8db3bee (`git diff --quiet`):
  - `data/season/` (`league.json`, `reliability.json`) and `data/catalogue/` (definition, `realism.json`,
    `reliability.json`);
  - `src/regista/season/pins.py` (`SEASON_PINS`);
  - `tests/test_backcompat.py`, `tests/test_catalogue_backcompat.py` and `tests/data`.
- `python -m regista.catalogue define --check` passes.
- Femi Toure's 5 league goals, none a penalty, are untouched: no generator or data change.
- No hidden rating or level scale appears in the report's JSON. No scale key appears in its Markdown (tested).

## Tests run

- Quick suite: **979 passed**, 15 deselected (4 min 21 s, macOS).
- Slow suite: **15 passed** (2 min 9 s), including the new U17 regeneration through the report.

## Open

1. **Distance U18 < U19 (assumed order) fails** by 76.7 m (2.3 SE), as levels.md reported. It needs a youth physical
   capacity in the motion model.
2. **Linux CI has not run** the 52 re-recorded catalogue pins or this report. The report's Markdown depends only on
   the committed JSON and fixed formatting, but CI is the check.
3. **PR not opened.** CLAUDE.md §4.2 says the branch is not pushed. Change it to "PR #N open" when it is.
4. **Older build records** (catalogue.md, api.md, engine.md) still quote the level scales and aggregates from before
   levels.md, as dated records. The current numbers live in `docs/catalogue/realism.md`, the data README and
   CLAUDE.md §2.11.
5. **criteria.md's general counts** ("798 tests", "13 slow", the Scout terminal "not yet deployed") were already out of
   date before this branch and describe `main`. They were left for the post-merge docs pass.
6. Carried from earlier steps: amateur peak speed against Djaoui et al. 2017; execution sizes other than the women's
   are assumptions; U19 and U20 goals slightly below the reference; the review nits listed in fixes-3.md.
