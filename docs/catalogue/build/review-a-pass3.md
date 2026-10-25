# Catalogue review A, round 3: engineering

Branch `feature/catalogue` at bb99e4e, reviewed against `main` (`git diff main...HEAD`). Lens: the data model,
generation and caching, determinism and pins, back-compat, the existing app, API validation and shapes, paging, cold-build
performance, and tests and their speed. Nothing was fixed in this round; this file is the only change.

**Verdict: signed off.** Nothing must be fixed and nothing should be fixed under this lens. What is left is nits, plus
the items that are Zaid's decisions (listed at the end, not judged here).

## My round 2 findings: both fixed

1. **`order` in the two rank modes.** In pool mode, `CatalogueMetrics.order_rows` now flips worst-first for
   lower-is-better metrics, so `desc` means the largest raw numbers first in both modes. I checked the logic for all
   four cases (higher or lower is better, asc or desc) and reproduced it:
   - `/api/catalogue/rank?metric=fouls&position=MF&order=desc` across levels starts 4.98, 5.97, 3.83, 4.84, at
     percentiles 2, 2, 3, 5. These are the lowest oriented percentiles, which is the raw direction.
   - Without `order`, the same request starts 0.0 at percentile 94: best first.

   `test_order_is_the_raw_direction_in_both_rank_modes` covers rank, the terminal screen and the catalogue screen.
2. **`/api/players` and the terminal's rank mode.** In catalogue mode, `players_payload` now ranks cards from more than
   one level by each card's percentile in scope (`CatalogueProfiles.sort_percentile`, `ratio_pool`), puts men and women
   on separate boards, and serves `rank_by`, `rank_rule`, `boards` and each card's `board`.
   - `?country=England&sort=goals` gives the women's board at offset 166. `rank_by=value` restores the raw order
     (Milan Whitfield at 40.6 minutes first), on boards.
   - The terminal's catalogue payloads add `rank_by`, `rank_rule` and `boards`. `rank_by=value` on
     `/api/terminal/rank` is honoured.
   - Profile stats and ratios are all higher-is-better and their pooled percentiles are raw (not oriented), so pool
     mode and value mode agree on direction there.
   - An invalid `rank_by` gives a 422, and an unknown `sort` still gives a 422.

The other round 2 fixes, checked under this lens:
- **Gender boards with offset and top rows.** These are on `/api/catalogue/rank`, `/api/catalogue/players`, the
  competition screen, and the terminal screen and rank. The MCP tool `search_catalogue_players` with `limit=2` returns
  two men, then two women (Hannah Mitchell first), with `boards` [{men, 108, 2}, {women, 20, 2}] and a hint.
  - An offset past the end (500) gives an empty page but still the boards' top rows.
- **`recheck-realism`.** It reads only committed JSON and keeps the fingerprint. A test pins that the committed
  verdicts equal a recheck of themselves.

## Checks run

- **Quick suite:** 955 passed, 14 deselected, 4 min 15 s on macOS. No catalogue test is among the ten slowest; the
  slowest catalogue test is 4.1 s. The four catalogue and back-compat files run in 14.6 s (77 tests).
- **Back-compat:** `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` pass. Every new key appears
  only in catalogue mode or when the caller passes `rank_by`, which is a new parameter.
- **Offline probes** through `TestClient` with `REGISTA_DOTENV=`: 22 requests across `/api/players`,
  `/api/catalogue/{rank,players}` and `/api/terminal/{screen,rank}`, plus two direct calls to the MCP tool's function.
  - The first request (a cold catalogue load) took 4.0 s. Every later one took 0.01 s or less, pool mode across every
    competition included.
- **Determinism:** I found no unordered directory or set iteration that feeds output in `regista.catalogue`. The sets
  in `define.py` are membership only.
- I did not rebuild the pins. The verifier did this twice before round 1 (drift {} both times), and rounds 2 and 3
  changed no generator, definition or seed.

## Nits (no action needed for sign-off)

- **Ranking mixes positions when no position filter is set.** Each row is ranked by its percentile among its own
  position. So `/api/players?country=England&sort=goals` starts with Otis Nakamura (0.31 goals per 90, near the top
  among defenders), with Femi Toure (1.64) third. This follows `RANK_RULE`, and `/api/catalogue/rank` without
  `position` behaves the same way.
  - The fix report describes this list as "regulars at the 99th, 98th and 98th percentile", which is true but hides
    the mix of positions.
  - `RANK_RULE` could say that rows of different positions compare on their own position's percentile. The UI round
    should default to one position.
- **Ratio pools in `/api/players` have no minimum attempts.** A ratio's pooled percentile counts any qualified card
  with one attempt. Jonas Hoffmann (19 of 19 passes in 60 minutes) tops semi-pro forwards' pass accuracy. Value mode
  already behaved this way on main, so this is not a regression. The terminal's ratio metrics do apply
  `min_attempts`.
- **Board shapes differ between surfaces:**
  - the MCP tool: `{gender, total, shown}`
  - `/api/catalogue/rank` and terminal rank: `{gender, ranked, offset, top}`
  - the screens: `{gender, rows, offset, top}`
  - `/api/players`: `{gender, rows, offset}`, with no `top`. A reader can still page there with `offset`.

  One shape would be easier for the UI round.
- **Pool ties share a rank on (percentile, value)**, while the order also uses pool size and minutes (carried from
  round 2).
- **Carried from rounds 1 and 2, unchanged:**
  - `catalogue_fingerprint` hashes label wording.
  - `build_catalogue` swallows pool exceptions without logging them.
  - `materialise_match` deletes a stale folder outside the lock.
  - An unknown `country` gives an empty 200.
  - `/api/teams` ignores `scope`.
  - `/api/catalogue/matches` waits for the full metrics engine.
  - `store.repo_root` assumes the index's location.
  - The pins docstring carries a history line.

## Outside this lens (noted, not judged)

- **Linux CI has not run on this branch.** The PR will be the first Linux run of the 60 catalogue pins (recorded on
  macOS), of the level reliability slow test and of the new API tests. Nothing found here is machine-specific, but only
  CI proves it.
- **Zaid's decisions, left open in `fixes-2.md`:** the U17 peak-speed band fails (29.68 km/h against 24.9-28.7); levels
  differ in ratings and pace, not in most event rates (amateur pass completion is above semi-pro men's).
- **Phase 5 is not written:** the realism report, CLAUDE.md §2.11 and the data README's Catalogue section. Source
  entries S4, S6 and S9 still lack authors or year.
