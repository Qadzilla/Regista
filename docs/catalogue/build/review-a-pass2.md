# Catalogue: independent review A, round 2 (engineering)

Reviewed `git diff main...HEAD` on `feature/catalogue` at e5ca6ae (the round 1 fixes). My lens is engineering: the data
model, generation and caching, determinism and pins, back-compat, whether the existing app still works, API validation,
response shapes and paging, cold-build performance, and the tests and their speed. I fixed nothing. Every probe ran
offline against a local `TestClient` with `REGISTA_DOTENV=`. Nothing touched the live app, Azure or Fabric.

**Verdict: not signed off.** Nothing must be fixed. Two things should be fixed, both small API-semantics gaps left by
the round 1 ranking fix (S3). The rest are nits.

## My round 1 findings: both fixed

1. **England's catalogue cards now count claims and uploads.** `catalogue_profiles()` calls
   `cp.use_england(season_api.season())`.
   - `season()` is cached by `load_season`, so the England pools are rebuilt only when that object changes, under the
     profiles lock.
   - `_minutes` uses the profile's own minutes whenever the metrics engine counted a different set of matches.
   - `basis` and `career.profile_only_matches` say which numbers are league-only. `profile_only_matches` reads the
     profile's own `source` values (`claim`, `upload`), so it is right.
   - The new test with a fake upload pins this behaviour.
2. **`/api/players` paging is fixed.**
   - Without `offset` the response is today's. `?limit=5` gives `total` 5 and no `offset` key.
   - With `offset` (0 included), `total` counts every card: `offset=0` gives 102, `offset=100` gives 2 cards with
     `total` 102, and `offset=200` gives 0 cards.
   - Catalogue mode agrees: `competition=co_eng_sp_men&offset=10` gives `total` 102.

## What I checked, and what held

- **Pins under Python 3.11's float summation (CI's interpreter).** I swapped `builtins.sum` for 3.11's naive summation
  and regenerated into an empty folder:
  - the first fixture of each of the 12 unchanged new competitions;
  - all 5 re-recorded Spain U19 fixtures, whose header now carries the new name;
  - the 12 include the first Ghana U17 and England U18 fixtures, two competitions whose dates of birth moved.

  17 of 17 match `CATALOGUE_PINS` (21 s). This supports the claim that dates of birth never reach the stream, and it
  removes the most likely Linux-only cause of drift. It is still not real Linux CI.
- **The realism file is wired in.**
  - `data/catalogue/realism.json` is part of `load_catalogue_metrics`'s cache key, through its mtime.
  - The Dockerfile copies it, and `test_packaging` guards it.
  - `cloud.smoke` fails the image if the file is stale or any verdict is missing.
  - Its fingerprint is the reliability one, so a stale file serves "not measured" and never a wrong verdict.
- **Sample-aware `noisy` (Spearman-Brown).**
  - `r <= 0` returns r unchanged, and zero minutes returns None, so there is no division by zero.
  - England's competition scope keeps today's flag exactly.
  - Sparse competitions in competition scope now get the adjustment too (before, they read the level flag). That is an
    improvement.
- **The cross-level board.** `order_rows` groups rows into boards with a stable sort after ranking.
  - `_rank` restarts `place` on each board, and offset paging walks the combined list.
  - `/api/terminal/rank?metric=np_goals&position=FW&tier=semi_pro` ranks Femi Toure first (1.64, 98th percentile), and
    the women's board starts again at 1.
  - Season totals (`yellow_cards`) always rank by value, as documented.
- **Validation.**
  - `rank_by` is a `Literal` on the API, so a bad value gives 422.
  - The MCP tool returns `{"error": ...}` for `rank_by="luck"`.
  - `rank_mode` raises `ValueError` for a bad value if called directly.
- **Test speed.** The catalogue test files plus `test_packaging` and `test_backcompat`, matches already built:
  103 passed in 21 s. The slowest test takes 4.1 s. Nothing slow has crept into the quick suite. The re-measure is
  marked `slow`.

## Should fix

1. **`order` means opposite things in the two rank modes for lower-is-better metrics.**
   Where: `CatalogueMetrics.order_rows` in `catalogue/metrics.py`, which sets `worst_first = order == "asc"` against an
   oriented percentile. `sort` reads `order="desc"` as "biggest raw value first".
   - In value mode (one level), `order=desc` puts the largest numbers first. `/api/catalogue/rank?metric=fouls&position=MF&competition=co_ger_sp_men&order=desc`
     starts 4.98, 4.15, 2.46.
   - In pool mode (more than one level), `order=desc` puts the best percentile first, and for a lower-is-better metric
     that means the smallest numbers. The same request without `competition` starts 0.0, 0.0, 0.0. With `order=asc`,
     pool mode puts the largest first.
   - The friendly terminal sends `order=desc` for "most fouls" or "most yellow cards"
     (`terminal-words.js`: "most" ranks the biggest numbers first even where lower is better). Once the UI round adds
     catalogue parameters, "most fouls" across England's three levels would list the players with zero fouls first.
     `/api/terminal/screen?metrics=fouls&sort=fouls&order=desc&position=MF&country=England` does that today: 0.0, then
     0.31, then 0.62.
   - The 10 per-90 metrics where lower is better are affected, among them `ball_losses`, `fouls`, `dribbled_past`,
     `offsides` and `aerial_duels_lost`.
   - No test covers `order` in pool mode.
   - Fix: give an explicit `order` the raw direction in both modes. In pool mode, flip `worst_first` when
     `higher_is_better is False`; with no `order`, keep "best first". Add a test with one lower-is-better per-90 metric
     across two levels.

2. **Two lists still mix levels and genders, or rank by percentile without saying so. The S3 fix was not applied
   everywhere.**
   - **`/api/players` in catalogue mode** (`catalogue_api.players_payload`) still sorts every selected competition's
     cards together by the raw per-90 value (`_sort_key`).
     - `/api/players?country=England&sort=goals` gives Milan Whitfield (40.6 min), Haruki Petrov (43.0), Femi Toure,
       then Hannah Mitchell (women's league), Owen Toure, two more women, then an U18 boy.
     - `tier=semi_pro&position=FW` puts Kevin Jung (Germany, 23.6 min) first and Hannah Mitchell among the men.
     - That breaks the design's "genders never mix" and the new `RANK_RULE`, while the same filters on
       `/api/catalogue/players` give separate boards ranked by pool.
   - **The terminal endpoints in catalogue mode** (`screen_payload`, `rank_payload`) now rank across levels by
     percentile with gender boards, as the fix report says. But:
     - they drop `rank_by`, `rank_rule` and `boards` from the response;
     - they accept no `rank_by` parameter (`&rank_by=value` is silently ignored);
     - their docstrings still say "sorted by `sort` … best first".
     A client sees rows out of value order, and rank 1 twice, with nothing at the top level to explain it. Each row's
     `board` key is the only hint.
   - Fix:
     - `players_payload`: use `order_rows`'s rule. Group by gender, and across levels sort by the scope's percentile of
       the sort stat, or at least by gender board. Serve `rank_by` and `boards`.
     - Terminal catalogue payloads: add `rank_by`, `boards` and `rank_rule`. These are additive keys in catalogue mode
       only, so back-compat holds. Accept `rank_by` and update the docstrings.

## Nits

- `catalogue_fingerprint` hashes every competition's whole `competition` block, which includes its name, region and
  `eligibility` label. A wording-only edit to a label therefore makes `reliability.json` and `realism.json` stale, and
  each needs a 5-minute re-measure. The smoke test catches a forgotten re-measure at image build, so this is friction,
  not a silent bug. Hashing only the fields that reach the generator would avoid it.
- The fix report says the five Spain U19 pins changed only in the header name. I confirmed they hold under 3.11's
  summation. The pins docstring now carries a one-line history ("re-recorded in review round 1"). It belongs in the
  commit log, not the module.
- In `_rank`'s pool mode, ties are equal on (percentile, value), while the order also uses pool size and minutes. Two
  rows with the same percentile and value share a rank even when one comes from a small pool. That is defensible, but
  `RANK_RULE` could say that ties share a rank.
- Carried over from round 1, unchanged and still nits:
  - `build_catalogue` swallows pool exceptions without logging them.
  - `materialise_match` deletes a stale folder outside the lock.
  - An unknown `country` gives an empty 200.
  - `/api/teams` ignores `scope`.
  - `/api/catalogue/matches` waits for the full metrics engine.
  - `store.repo_root` assumes the index's location.

## Outside this lens (noted, not judged)

These belong to Zaid and to the realism review:
- The U17 peak-speed band fails, and amateur pass completion fails.
- The levels barely differ in event data.
- Women's own speed zones are not computed.
- The phase 5 realism report and CLAUDE.md §2.11 are not written.
- Linux CI has not run on this branch yet. The PR will be the first Linux run of the 60 catalogue pins.
