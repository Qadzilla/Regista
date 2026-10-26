# Catalogue: independent review A, round 1 (engineering)

Reviewed `git diff main...HEAD` on `feature/catalogue` at 823d5f3 (phases 0-4 plus the verification commit). My lens is
engineering: the data model, generation and caching, determinism and pins, back-compat, whether the existing app still
works, API validation, response shapes and paging, cold-build performance, and the tests and their speed. I fixed nothing.

**Verdict: not signed off.** Nothing must be fixed. Two things should be fixed, both small; the rest are nits.

## What I checked, and what held

- **Generator back-compat.** The only change to the generator is the optional team-spec key `style_offset`. It does
  nothing when the key is absent, and `generate_kwargs` adds it only when the competition file has a `level` block
  (`league.json` has none). `season/build.py` gains keyword-only `manifest_extra` and `title_fn`; without them the
  manifest is the league's, as before.
- **`data/season/reliability.json`.** Only its `league_fingerprint` stamp moved, because that fingerprint hashes
  `generator.py`'s source. The values are untouched. For the same reason every England match folder rebuilds once
  (`BUILT_BY` covers `generator.py`). The image builds them in at `docker build` time anyway.
- **Pins on Linux and Python 3.11 (CI's interpreter).** Linux CI has not run yet. libm differences are already handled
  by `regista.detmath`. The other difference between this Mac (Python 3.13) and CI (3.11) is `sum()` over floats: 3.12
  and later add Neumaier compensation, 3.11 adds naively. I swapped `builtins.sum` for 3.11's naive summation, then:
  - generated the first fixture of every one of the 13 new competitions into an empty folder: 13 of 13 match
    `CATALOGUE_PINS`;
  - ran `test_catalogue_backcompat`, `test_catalogue_build`, `test_catalogue_metrics` and `test_catalogue_api`:
    67 passed, so the back-compat response hashes (recorded on 3.13) also hold under 3.11's summation.
  - Neither run is real Linux CI, but together they remove the most likely Linux-only failure.
- **Response shapes.** For 15 existing endpoints I diffed the default response against the same endpoint with a
  catalogue parameter (`competition=co_ger_sp_men`, or `scope=level` on player endpoints). Every catalogue response has
  every key of today's, at the top level, in `players[0]`/`points[0]`/`teams[0]` and in a cell, and only adds keys.
  - No static page sends `scope`, `pool`, `level`, `tier`, `gender`, `country`, `age_group` or `competition`, so the
    current UI can never switch into catalogue mode by accident.
- **Validation.** I sent 38 edge requests (unknown competition, club or metric; a bad scope; tier against level; age_min
  above age_max; duplicate compare ids; a competition count that does not match the ids; evidence_offset without
  evidence; a player in a competition he did not play in; `cm_nope`). Every answer was a 4xx or a correct 200. No 500.
  The MCP tools return `{"error": ...}` for a bad scope.
- **Ids.** No club id repeats across the 14 competitions. The only global ids in two squads are the 5 career players.
- **Cold engine cost.** One process, matches already on disk, from cold: England season 0.5 s, England metrics 0.8 s,
  catalogue metrics (13 competitions) 1.6 s, catalogue profiles 1.5 s. Peak RSS 307 MB, well inside the app's 2 GiB.
  The England `SeasonMetrics` inside the catalogue is the same object the terminal serves.
- **Image.** `.dockerignore` and `.gitignore` both exclude `data/catalogue/matches/`. The Dockerfile copies the
  definition and reliability files, builds the 60 matches at `docker build`, and `cloud.smoke` checks their pins and the
  reliability stamp inside the image. The built matches add about 50 MB to the image (events and clips; tracks are
  written on demand).
- **Test speed.** The five catalogue test files, with matches already built: 83 passed in 20.7 s. The slowest single
  test takes 4.7 s. The reliability recompute is correctly marked `slow`. On a cold CI runner, the first catalogue test
  module builds all 60 matches in a process pool (about 20-30 s on 4 cores). It sits in the quick suite on purpose, so
  Linux checks the pins, the same as the league's pins test.

## Should fix

1. **In catalogue mode, England reads league fixtures only, while today's profile cards also count claims and uploads.**
   Where: `catalogue/profiles.py` `build_catalogue_profiles`, which builds
   `Season.build(load_league(league_path), season_root)`. That is not `season_api.season()`, which passes
   `claimed_matches(...)` and `uploaded_matches()`.
   - On the live app Femi Toure has a finished Player-view upload, so today's `/api/players` card counts 11
     appearances.
   - `/api/players?competition=co_eng_sp_men` (or `scope=competition`) would give a different card for him: 10
     appearances, and different minutes, per-90s and percentiles.
   - `/api/players/pl_bro_09?include=career` puts both in one response: the profile says 11 appearances, the `career`
     block (from `CatalogueMetrics`, league only) says 10.
   - `test_england_in_competition_scope_is_todays_screen_and_cards` passes only because tests have no uploads or
     claims.
   - This is fine for the terminal endpoints, which have always been league only.
   - Fix: either build the catalogue's England `Season` from `season_api.season()`, or state "league fixtures only" in
     the catalogue-mode response and the docstring. Then add a test with one confirmed upload that pins the chosen
     behaviour.

2. **`/api/players` gains `offset`, but in its default mode `total` is the page length, not the total.**
   Where: `season_api.py` `list_players`. It calls `rows = s.players(..., limit=offset + limit)[offset:]`, then
   `total = len(rows)`.
   - `/api/players?offset=10&limit=5` returns `total: 5`. The same request with `competition=co_eng_sp_men` returns
     `total: 102`.
   - So one endpoint now has two meanings of `total`, and a client paging the default mode cannot tell how many pages
     there are.
   - Without `offset` the response is unchanged (back-compat holds).
   - Fix: either leave `offset` off the default mode, or compute `total` over every filtered row when `offset` is given,
     and document it either way.

## Nits

- `build_catalogue` catches every pool failure (`except Exception: pass`) and rebuilds the whole stale set one by one.
  A real generator error in a worker only shows up later, on the serial path, and a broken pool quietly turns a
  12-second build into about 80 seconds. Logging the exception would help.
- `materialise_match` deletes a folder whose labels are stale (`shutil.rmtree`) outside the per-fixture lock. A clip
  being served from that folder at that moment could fail. Folders only go stale on a definition change, so this is
  rare.
- An unknown `country` silently returns an empty selection (200), while an unknown `competition` gives 422. Checking
  country against the index would be consistent.
- `/api/teams?scope=level` ignores `scope` and returns today's response; `/api/teams` switches mode on the filters only.
  The docstring could say so.
- `season_payload` serves `percentiles.rule = PERCENTILE_RULE` ("a third of a club's minutes"), but sparse competitions
  also use the 45-minute floor and a minimum pool of 5. The numbers beside it (`min_minutes`, `min_pool`) are right;
  only the sentence is incomplete.
- `/api/catalogue/matches` and `/api/competitions/{id}` build the full catalogue metrics just to list uploads. On a cold
  replica they wait for the whole engine; the match list itself needs only the profiles.
- `catalogue_profiles` builds a second England `Season` (the duplicate in should-fix 1). It costs little memory today,
  but it is a second copy to keep in step.
- `store.repo_root` assumes the index sits at `<root>/data/catalogue/catalogue.json`. An index copied anywhere else
  resolves competition paths wrongly. Fine for the app and the tests as they are.

## Outside this lens (noted, not judged)

The two failing realism checks (U17 peak speed; amateur pass completion above semi-pro men's), the phase 5 report,
CLAUDE.md §2.11, and the missing source details (S4, S6, S9) are listed by the verifier and belong to the realism and
claims review.
