# Catalogue review A, closing round 3: engineering

Branch `feature/catalogue` at ebe3f4e, reviewed against `main` (`git diff main...HEAD`, 34 commits). This round looks
mainly at what changed since closing round 2: fixes-close2.md (commits bece496 and ebe3f4e). I read those changes on top
of everything after review round 3 (fixes-3.md, levels.md, docs.md, verify-2.md, fixes-close1.md). My lens is
engineering:
- determinism and pins;
- back-compat and the existing app;
- API shapes and validation;
- the ranking rule on every surface;
- the generator change staying inert for England;
- tests and how long they take;
- whether the docs match the code.

I fixed nothing. This file is the only change in this round.

**Verdict: signed off.** Nothing must be fixed and nothing should be fixed. The nits below are optional. The decisions
listed for Zaid are not defects.

## What changed since closing round 2

The changes are wording only: `design.md` §10 (the realism table and the [S15] entry), one sentence in
`data/synthetic/README.md`, and one in `fixes-close1.md`. No code, data, pins or tests changed (`git diff d485add..HEAD`
touches only those three files and the report). Both of closing round 2's findings are closed:

- **design.md's table now agrees with the served checks** (`realism.ORDERS`):
  - The amateur sprint order is marked assumed, citing [S9] and [S15] against it. Served:
    `amateur_sprint_distance`, `basis: assumed`, `sources: []`, with `contrary` naming S9 and S15.
  - Amateur pass completion and ball losses are "a direction extended from [S10]". Served: `sources: ['S10']`, and the
    label says the build extends it.
  - The women's ≥ 20 km/h order cites [S1] only. Served: `women_hi_distance_*`, `sources: ['S1']`.
  - The pass gap cites [S1, S12]. Served with `gap: [5.0, 11.0]` and `calibrated: true`.
  - The academy row splits the steps the same way the build does. U17 < U18 distance is sourced [S8]
    (`youth_distance`). Distance from U18 up to senior is assumed (`youth_distance_extension`). Peak speed from U17 to
    senior is assumed (`youth_peak_speed_mean`), with `by_construction: true`, which matches the row's "holds by
    construction".
  - The line above the table says the served checks supersede it.
  - [S15] in the design's source list matches `realism.SOURCES["S15"]`: authors, year, journal and DOI.
- **The heavy-touch denominator** now reads "on the 60 catalogue matches". 60 is the number of fixtures in the 13
  competition files.

## What I checked, and what holds

**England is untouched** (all re-run by me, not taken from the verifier)
- `data/season/league.json` has SHA-256 04dbb30f…0b1a34 on both this branch and `main`.
- `git diff main...HEAD` is empty for `season/pins.py` and `tests/test_backcompat.py`.
- `tests/test_catalogue_backcompat.py` and `tests/data/catalogue_backcompat.json` were last touched in ab3bb02, where
  they were recorded on main's code.
- I rebuilt the 30 England fixtures into an empty folder (7.1 s), and `season.pins.drift` returned `{}`.
- From the raw `events.jsonl`, with roster ids mapped to global ids, Femi Toure (pl_bro_09) has 5 goals:
  - round 1 at 5' and 55';
  - round 6 at 48';
  - round 8 at 5';
  - round 10 at 7'.

  None carries the penalty qualifier. The next best are pl_bro_11 and pl_ash_09 with 3 each, so he is two clear. The
  season's only `penalty` event is pl_dun_10's (round 4).

**Catalogue determinism**
- I rebuilt the 60 catalogue matches into an empty folder with `build_catalogue` (spawned pool, 13.8 s), and
  `catalogue.pins.drift` returned `{}`.
- The pin test (`test_every_catalogue_match_is_pinned_and_the_same_on_every_platform`) is in the quick suite, not marked
  slow. The image workflow runs it on Linux, and the smoke test re-checks the pins inside the image. So the CLAUDE.md
  sentence "Linux CI runs them on the PR" is accurate, though it has not happened yet (see Decisions).
- Matches are found only through the competition files (`store.new_competitions`, `resolve_match`), never by listing
  `data/catalogue/matches/`. The image also leaves that folder out (`.dockerignore`) and builds it fresh. So the 29 stale
  local folders cannot be served or counted.

**API shapes, validation, ranking and privacy** (TestClient against my fresh builds, `REGISTA_DOTENV=`)
- **Validation.** 15 malformed requests get 422 or 404 as they should:
  - `rank_by=x`, `order=up`, an unknown metric, `limit=0`, `offset=-1` and `scope=world` on `/api/catalogue/rank`;
  - `tier=pro` and a country with `<` on `/api/catalogue/players`;
  - unknown competition or player ids: 404;
  - a bad `scope` or `competition` on `/api/terminal/rank` and `/api/players`;
  - a single id on `/api/catalogue/compare`;
  - a malformed competition id on `/api/metrics`.
- **Ranking.**
  - `/api/catalogue/rank?metric=goals&country=England` gives one board per level (semi-pro men, U18, semi-pro women),
    with Femi Toure first (1.64, then Ustinov 1.04 and Whitfield 1.03).
  - `gender=women` gives two level boards.
  - `position=FW&scope=all` ranks by pool, one board per gender. The cross-level warning is served.
  - `yellow_cards&tier=amateur` is a single level: ranked by value, fewest first.
  - `/api/terminal/rank?metric=goals` without `scope` keeps its existing shape: no `rank_by` or `boards` keys, and the
    league's own `season` block. With `scope=all` it adds them and keeps England's 66 rows, as documented.
- **Privacy.** 50 payloads contain none of the rating, level-scale, execution, style-offset or seed keys, and none of the
  73 competition and fixture seed values. The 50 cover every catalogue route, each competition's detail, players and
  `/api/metrics?competition=`, compare, career, rank with `scope=all`, and the terminal screen with `scope=all`.

**Reports match the code**
- `python -m regista.synth.report --catalogue` prints the committed `docs/catalogue/realism.md` exactly, apart from
  print's trailing newline.
- The counts agree in CLAUDE.md §2.11 and §4.2, the data README, criteria.md and realism.md:
  - 10 of 10 sourced checks pass (1 band and 9 orders, 3 of them confirming a calibration);
  - of 7 assumed orders, 6 hold and distance U18 < U19 fails.
- Outside the build records, I found no stale "11 of 11", "ten sourced", "5 hold", "89 catalogue" or "979 quick".

**Tests** (Mac, `REGISTA_DOTENV=`; times inflated because my two rebuilds ran at the same time)
- Quick suite: **980 passed**, 15 deselected, 5 min 3 s.
- Slow suite: **15 passed**, 3 min 48 s.
- This matches CLAUDE.md's "980 quick tests and 15 slow". Closing round 2 measured 4 min 24 s and 2 min 8 s on an idle
  machine, and nothing has changed since that would move them.

## Nits (not needed for sign-off)

- **`search_catalogue_players`' documented signature leaves out `rank_by`.** The function takes it
  (`mcp_server.py` line 232, explained in its docstring). The module docstring's tool list (line 24) and
  `docs/architecture.md`'s MCP table (line 206) both omit it. The verifier found the architecture.md gap; the module
  docstring has the same gap.
- **A single-board answer has `boards: null`.** `/api/catalogue/rank` with one level (for example `tier=amateur`) and
  `/api/terminal/rank?scope=all` restricted to England return `"boards": null`, and each row's `board` is the gender.
  verify-2 described this as `boards []`. Either is workable, but one documented value (always a list) would be simpler
  for a client. Boards also come in competition order, not level order (verifier's nit).
- **Served calibration notes end in "(taxonomy.LEVELS)"**, a Python path in a scout-facing string. Carried from closing
  round 2.
- **design.md's academy row is headed "U20, U19, U18"** but now also states the U17 < U18 step. That is accurate, just
  outside its heading.
- **levels.md has two hand-written figures the committed file contradicts**, and fixes-3.md's review nits remain. These
  are build records, carried from earlier rounds.

## Decisions for Zaid (not defects)

- The 29 stale, git-ignored folders in `data/catalogue/matches/` (dated 2026-10-31 to 2027-05-22) are harmless: nothing
  lists that folder, and the image does not ship it. Deleting them is tidy but optional.
- Linux has not yet run the 60 catalogue pins, which were recorded on macOS. The quick suite includes the pin test, so
  the PR's image workflow will run it, and the in-image smoke test checks the pins again.
- Realism judgements carried from review B: amateur pass completion and ball losses rest on an extension of S10; the U17
  band is a spread across players; the distance U18 < U19 assumed order fails. Each is stated in the served notes and in
  realism.md.
