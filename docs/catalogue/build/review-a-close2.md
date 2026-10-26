# Catalogue review A, closing round 2: engineering

Branch `feature/catalogue` at 9ec46c5, reviewed against `main` (`git diff main...HEAD`). This round looks mainly at what
changed since closing round 1: fixes-close1.md (commits da3a404 and 51aaa45), on top of what changed after review round
3 (fixes-3.md, levels.md, docs.md, verify-2.md). My lens is engineering:
- determinism and pins;
- back-compat and the existing app;
- API shapes and validation;
- the ranking rule on every surface;
- the generator change staying inert for England;
- tests and how long they take;
- whether the docs match the code.

I fixed nothing. This file is the only change in this round.

**Verdict: not signed off.** One item should be fixed. It is a two-row wording fix in the design record: two
misattributed sources that verify-2 and the closing fixes corrected everywhere else. Nothing must be fixed. The code,
data, pins, endpoints and tests hold up under this lens. Everything else is a nit, or a decision for Zaid that I list
but do not judge.

## Should fix

### S1. design.md's realism table still cites [S9] and [S2] for orders those sources do not support

- **Where:** `docs/catalogue/build/design.md` §10, the "Kinds of check" table:
  - about line 688, amateur row: "order: sprint distance per 90 below semi-pro **[S9]**";
  - about line 691, women vs men row: "order: distance at ≥ 20 km/h per 90 lower in women's pools **[S1, S2]**".
- **What is wrong:** these are the two misattributions verify-2 found and fixed in `realism.py`:
  - [S9]'s full text finds no difference in sprinting between second-tier professionals and fourth-tier amateurs. The
    closing fixes went further and made `amateur_sprint_distance` an assumed order, with [S9] and [S15] served as
    evidence *against* it.
  - [S2] has no men, so it cannot support a women-vs-men order. The served order cites [S1] only.

  The same document was already corrected for [S9] about 320 lines earlier (line 366: "corrected 2026-10-25,
  verify-2.md"). So design.md now says both things about [S9]. The table also lists the U18 to U20 steps as sourced
  orders "[S5, S6, S8]". The build serves them as assumed orders beyond each source's span: [S5] and [S6] stop at U17,
  [S8] at U18.
- **Why it matters here:** design.md is the catalogue's design, the file CLAUDE.md §2.11 points to. verify-2 treated it
  as a document to keep correct: it fixed S11's figure and the ± values there. A judge who checks a citation in this table
  finds the source saying the opposite. That goes against the project's honest-claims rule, even in a plan written
  before any code.
- **Fix (wording only; nothing regenerates):**
  - In the amateur row, write "order: pass completion and ball losses below semi-pro, direction extended from [S10];
    sprint distance below semi-pro is an assumed order, against [S9] and [S15]".
  - In the women vs men row, cite [S1] only for the ≥ 20 km/h order.
  - In the academy row, mark U18 to senior (distance) and U17 to senior (peak speed) as assumed beyond the sources'
    spans.
  - Alternatively, put one line above the table: "superseded by `docs/catalogue/realism.md`; see verify-2.md and
    fixes-close1.md". It should still not keep a citation its own source contradicts.

## What I checked, and what holds

**England is untouched**
- `data/season/league.json` has SHA-256 04dbb30f…0b1a34, the same bytes as `main`.
- `git diff main...HEAD` is empty for `season/pins.py` and `tests/test_backcompat.py`.
- `tests/test_catalogue_backcompat.py` and `tests/data/catalogue_backcompat.json` were last touched in ab3bb02, where
  they were recorded on main's code.
- Since levels.md, the closing fixes touched neither `generator.py` nor `catalogue/pins.py`. In `data/catalogue/` they
  touched only `realism.json`, which is re-stamped and holds no match data. So the verifier's rebuild (pin drift `{}`
  for England and the 60 catalogue matches, Femi Toure 5 league goals, none a penalty, two clear) still stands.
- I did not repeat the rebuild.

**The closing fixes are wording and served fields only**
- Every realism measurement is the same as before:
  - `recheck(realism.json) == realism.json` holds byte for byte as a dict, `method` included. The method is now
    re-stated by `method_text()` with `SE_CONDITIONAL`.
  - `catalogue_drift` is `[]`.
  - `catalogue_fingerprint` hashes competition labels, not realism wording, so it did not move. Neither did the
    loader's staleness check.
- `python -m regista.synth.report --catalogue` prints exactly the committed `docs/catalogue/realism.md`, apart from
  print's trailing newline.
- The new keys (`calibrated`, `calibration`, `extends`, `contrary`) appear only on catalogue realism payloads:
  - `/api/metrics?competition=co_gha_u17` serves them.
  - `/api/metrics` with no competition, which is England's existing response, does not, and its shape is unchanged.
  - `calibrated` is `null` on assumed orders.
  - The calibration text names a scale in words, never its value. The privacy tests check payload keys, and none of the
    new keys is a rating or scale key.
- I read the served notes on five competition and metric pairs:
  - Spain amateur `sprint_distance` is now kind `none`, carrying the assumed order and "Against it: [S9] … [S15]".
  - The Ghana U17 band says "Calibrated to this source … cannot fail short of a bug".
  - The England women's pass gap and the Spain amateur pass order say "the build extends" and "as the build extends it".
  - The Ghana U17 distance order says "Scaled in the source's direction … as reported", inside [S8]'s own span.
  - No served note says "the source reports that amateurs" or "… that women". A test pins this over every competition.
  - The fail and not-separated wording never says "as reported".
- The counts agree everywhere I looked:
  - 10 sourced checks (1 band, 9 orders), all pass: 3 calibrated, 7 scaled, 8 orders extended.
  - 7 assumed orders: 6 hold, 1 fails (running distance U18 < U19).
  - Places checked: `realism.md`, CLAUDE.md §2.11 and §4.2, the data README's "Realism per level" and criteria.md.
    `test_catalogue_report.py` pins the summary.
  - Searching `src`, `docs`, `data`, `tests`, README and CLAUDE.md, outside the build records, finds no stale "11 of 11",
    "ten sourced" or "5 hold".
- The heavy-touch bullet in the data README matches `MatchSim._heavy_touch`: first touch of a received pass,
  `exec_touch` × execution, doubled under pressure within 3.5 m, capped at 0.3, and the four records in order. No schema
  change was needed.

**Code paths unchanged since closing round 1.** The ranking rule (`choose_mode`, `board_by`, `group_boards`, one board
shape on all six surfaces), validation (422s), `materialise_match` under the match lock, packaging, the smoke test and
the CI paths are as I reviewed them in closing round 1. No commit since then touches them. The verifier's six-surface
ranking walk and app walk (`/`, `/me`, `/scout`, `/scout#terminal`, `/players/pl_bro_09`, no console errors) stand.

**Tests** (Mac, `REGISTA_DOTENV=`)
- Quick suite: 980 passed, 15 deselected, 4 min 24 s. That is one more than closing round 1: the new
  `test_sourced_checks_say_how_the_build_relates_to_them`.
- Slow suite: 15 passed, 2 min 8 s.
- The catalogue test files alone: 122 passed in 31 s. The slowest is still
  `test_execution_lowers_pass_completion_and_adds_heavy_touches` at 5.3 s. The new test adds no measurable time: it reads
  the committed file.
- CLAUDE.md's "980 quick tests and 15 slow" is correct.

## Nits (not needed for sign-off)

- **Served notes name internal code.** Every `calibration` string ends in "(taxonomy.LEVELS)". A scout reading a
  realism note gets a Python path. "the level scales" would say the same thing. No value is exposed.
- **The amateur pass and ball-loss notes say the extension twice.** The `extends` parenthesis ("[S10] compares
  fourth-division French amateurs … extends its direction to amateur against semi-pro men") is followed by the label's
  own parenthesis ("direction from [S10]: amateurs against internationals … extended by the build to semi-pros"). The
  women's notes have the same doubling for the 8-point gap. Either one alone would do.
- **The realism.md headline hardcodes which checks are calibrated** ("the U17 band and the two women's pass gaps") and
  the extension examples in `render_catalogue`. The numbers beside them are computed. If the calibrated set changes, the
  sentence goes stale without warning. The pinned summary counts in `test_catalogue_report.py` would catch most changes.
- **`catalogue_summary`'s `scaled` counts passing, uncalibrated checks only**, and the headline calls them "the other
  N". The two agree only while every sourced check passes.
- **Carried from closing round 1, unchanged:**
  - the MCP tool's hint ("pass position, gender or competition to read one board further"): with level boards, only
    `competition` gives one board;
  - architecture.md's MCP table leaves out `rank_by` (line 206);
  - the MCP tool's `order` defaults to `"desc"`, so the served `rank_rule`'s "without order, best first" never applies
    there;
  - `--repeat 0` with `--league` becomes one season;
  - boards come in competition order, not level order;
  - an unknown `country` gives an empty 200;
  - `/api/teams` ignores `scope`;
  - `/api/catalogue/matches` waits for the full metrics engine;
  - `store.repo_root` assumes where the index is;
  - pool ties share a rank;
  - levels.md's hand-written figures, which the committed file contradicts.

## Outside this lens, or Zaid's call (not judged)

- **Linux CI has not run this branch.** It has not run the 60 catalogue pins (52 re-recorded on macOS in levels.md), the
  level tests or the report tests. Nothing new reads libm or the clock, and the closing fixes touched no generator code.
  Still, the PR's CI is the first proof, and it should be green before merge.
- **Extrapolations, now stated in the served notes:** [S10] (amateurs against internationals, small-sided games) stands
  in for amateur against semi-pro, and [S1] and [S12] (elite women and men) for semi-pro and college. The U17 band is the
  spread across players used as a band for a mean.
- **Which orders are sourced, which are assumed and how they are sized:**
  - The assumed amateur sprint order holds in the simulation even though the full-match evidence goes against it. The
    order is shown as an assumption, with that evidence.
  - The assumed order running distance U18 < U19 fails.
  - Execution sizes other than the women's are assumptions.
