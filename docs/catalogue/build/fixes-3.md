# Catalogue fixes, round 3: dates, ranking across positions, review A's nits

Branch `feature/catalogue`, 2026-10-25. This round is step 1 of the closing round. It fixes review B round 3's S-A
and S-B and review A round 3's nits. Two commits:
- `d4075f1` (S-A, the data);
- `48d5a1a` (S-B and the nits, code only).

Everything ran offline with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric.

**The non-negotiables hold:**
- `data/season/league.json`, `SEASON_PINS`, `data/catalogue/reliability.json`, `data/catalogue/realism.json`,
  `tests/test_backcompat.py`, `tests/test_catalogue_backcompat.py` and `tests/data/` are byte-identical to `6183ff6`.
- Femi Toure still has 5 league goals, none a penalty (`python -m regista.season.audit`).
- Quick suite: 960 passed. Slow suite: 14 passed.
- `python -m regista.catalogue define --check`: the committed catalogue is what the definition writes.

## S-A. The catalogue is dated, and holds only matches already played

**Rule.** `taxonomy.AS_OF = "2026-10-24"` is one constant.
- It is written into `catalogue.json` as `as_of`.
- `/api/catalogue` serves it as `as_of`, with an `as_of_note`: every uploaded match is dated on or before it, and each
  season continues after it with no footage yet.
- `define._coverage` still shuffles the whole double round robin with the same coverage stream. It then drops the
  fixtures not played by `AS_OF` and draws the uploads from the rest, with the same two passes as before: first every
  club, then the remaining uploads.
- Because unplayed fixtures are dropped after the shuffle, a competition whose uploads were all played already keeps
  exactly the same fixtures. That holds for US college men, US college women and Japan: same match ids, seeds, dates
  and pins.
- A competition that cannot cover every club with its upload count by `AS_OF` raises an error. Before this round it
  could only fall short on the upload count.

**Season windows.** These are assumptions for invented competitions, with no source claimed. Rounds are still spread
in whole weeks over each window, so a later end date spreads them further apart.

| Competition | Window before | Window now | Rounds played by 2026-10-24 | Why |
|---|---|---|---|---|
| Pennine Women's League (England) | 2026-09-06 to 2027-05-02 | **2026-08-16** to 2027-05-02 | 1-3 (every 4 weeks) | an August start: Olivia King plays the opening match before the college season |
| Weserland-Liga (Germany) | 2026-08-08 to 2027-05-22 | 2026-08-08 to **2027-04-10** | 1-4 (every 3 weeks) | 8 uploads need enough played fixtures once Finn Schmidt's club is limited to August |
| Ogun Riverside Amateur League (Nigeria) | 2026-10-10 to 2027-05-15 | **2026-09-05** to 2027-05-15 | 1-2 | an October start left one round, 2 fixtures, too few for 4 uploads |
| Ashanti Colts Academy League U17 (Ghana) | 2026-09-19 to 2027-05-01 | **2026-09-05** to 2027-05-01 | 1-2 | the same: one round was played by the as-of date |
| Liga Amateur del Valle Alto (Mexico) | 2026-08-15 to 2027-05-22 | 2026-08-15 to **2026-12-12** | 1-4 (every 3 weeks) | an autumn tournament, as Mexican football splits its year; Edson Jimenez's club is limited to August |

- The other eight windows are unchanged.
- Every competition keeps its upload count, 60 in total, from 3 to 8 each. Every club still appears.
- Every season is still running on 2026-10-24 (each window ends after it), so the later rounds simply have no footage
  yet.
- England semi-pro men played its 10 rounds between 2026-08-15 and 2026-10-17, so it already fits.

**The uploads now** (from the updated table in catalogue.md):

| Competition | Uploads | Dates |
|---|---|---|
| England semi-pro women | 5 | 2026-08-16 to 2026-10-11 |
| England U18 | 4 | 2026-08-29 to 2026-10-10 |
| USA college men | 6 | 2026-08-29 to 2026-10-17 (unchanged) |
| USA college women | 5 | 2026-08-22 to 2026-10-17 (unchanged) |
| Spain amateur men | 5 | 2026-09-12 to 2026-10-24 |
| Spain U19 | 5 | 2026-09-05 to 2026-10-17 |
| Germany semi-pro men | 8 | 2026-08-08 to 2026-10-10 |
| Brazil U20 | 4 | 2026-08-08 to 2026-10-10 |
| Nigeria amateur men | 4 | 2026-09-05 to 2026-10-24 |
| Ghana U17 | 3 | 2026-09-05 to 2026-10-17 |
| Japan university men | 4 | 2026-08-29 to 2026-10-24 (unchanged) |
| Mexico amateur men | 4 | 2026-08-15 to 2026-10-17 |
| Morocco U19 | 3 | 2026-09-12 to 2026-10-24 |

The uploader and camera counts per competition came out the same, because that stream draws the same sequence per
fixture.

**Careers.** `CAREERS` gains a sixth field, when the person can play in the destination competition:
- `ANY`: the two Spanish juveniles. Their senior amateur matches fall on weekends other than their U19 matches.
- `BEFORE_SEASON`: the three student-athletes. They play only before the source competition's window opens.

`define.latest_dates` turns `BEFORE_SEASON` into a last upload date for that destination club: the day before the
college window opens. The coverage draw respects it. The same five people, global ids, clubs, bios and ratings come out
(the careers stream is unchanged). The story texts are rewritten:

| Person | Story now | Their destination uploads |
|---|---|---|
| Olivia King | "...registered with her home club in Yorkshire: she played its opening match in August, before she flew out for the college season" | Oxenridge's round 1, 2026-08-16 (college women open 2026-08-22) |
| Finn Schmidt | "...played for a semi-pro side at home in August, before the college season" | Mövenstedt's round 1, 2026-08-08 (college men open 2026-08-29) |
| Edson Jimenez | "...played for an amateur side at home in August, before the college season" | Agave Azul's round 1, 2026-08-15 |
| Sergio Cruz, Alberto Navarro | unchanged (Valencian Community, affiliated senior club) | Spain amateur 2026-10-03 and 10-24; their U19 dates are 09-05, 09-26 and 10-17 |

This removes the term-time matches review B carried from round 2 (2027-01-23 and 2027-03-27).

`_career_dates` still moves a clashing destination match to the next day. It moves it to the day before when the next
day would pass `AS_OF`. No clash occurs in the committed definition.

**Pins and the measurement.**
- 38 of the 60 catalogue pins moved and were re-recorded with `python -m regista.catalogue check`; drift is now `{}`.
  22 are unchanged: the three untouched competitions, plus matches whose fixture, seed and date came out the same.
- The pins docstring lost its history line (review A's nit) and now names the as-of date.
- England is untouched.
- **The measurement fingerprint did not move** (`ad54e036b2f4aa3d`, the same in `reliability.json` and
  `realism.json`). The fingerprint covers clubs, seeds, generator settings, labels and levels. Windows and uploads are
  not in it.
- The level measurement regenerates every competition's full round robin. A date reaches only the match header's
  `meta`, never a draw (`generator.MatchSim.meta`), so the measured values cannot change either.
- So there was no re-run of the level reliability and realism measurement. The slow suite's level recomputation still
  matches the committed table.

**Tests.**
- `test_the_catalogue_is_dated_and_holds_only_matches_already_played`: `AS_OF`, the index's `as_of`, every upload
  (England's included) on or before it, each on its round's date (±1 day for a career clash), and every season still
  running.
- The coverage test now checks each date is within its window and on or before `AS_OF`, not "before 2027-05-31".
- The story-vs-fixtures test now checks:
  - a college story says "before" and "August", and all its destination matches fall before the source window, in
    August;
  - "opening match" means round 1 only;
  - every `BEFORE_SEASON` career has a college story.
- `/api/catalogue` asserts `as_of`, each competition's last date and the 90 listed matches.

Three tests were rewritten because the data changed under them, not their intent:
- **Morocco's competition-scope pools.** Nour Cèdres now plays 2 of the 3 uploads, so its players qualify in
  competition scope and some pools reach 5. The test now checks that every pool under 5 has no percentile and gives a
  reason.
- **Sergio Cruz's evidence.** He no longer scores in Spain amateur, so the evidence test reads his shots.
- **Ghana's one-match club.** The small-sample team style test reads Rainforest, the club with one upload, instead of
  Cocoa Hill.

## S-B. Ranking across positions

**The rule** (`RANK_RULE`, applied by `CatalogueMetrics.choose_mode`, `board_by`, `group_boards` and `boards`):
percentiles are compared only within one position, and raw numbers only within one level.

| The list holds | Mode | Boards |
|---|---|---|
| one level | value | none |
| more than one level, one position (a position filter, or a list that holds one) | pool: each row's percentile in its own pool, then pools that are not small, then minutes, then the value | one per gender |
| more than one level, more than one position | value, within each level | one per level (men's levels first, in catalogue order) |
| `rank_by=value` | value, within each level | one per level |
| `rank_by=pool` with more than one position | pool | one per gender and position |
| a season total, minutes, name | value, within each level | one per level |

**The surfaces.** The rule applies on `/api/catalogue/rank`, `/api/catalogue/players` (and a competition's
`/players`), `/api/players` in catalogue mode, `/api/terminal/{screen,rank}` in catalogue mode, and the MCP tool
`search_catalogue_players`.
- Ranks restart at 1 on each board.
- Each row's `board` names the board it is ranked on: the gender when the list is one board.

**What `desc` means now.** `RANK_RULE`, the module docstring and every docstring on those surfaces say it plainly:
- In value mode, desc lists the largest numbers first, even where lower is better.
- In pool mode, desc lists the rows highest in their own pool in the raw direction first. Those are the largest numbers
  relative to each row's pool, not the largest numbers. For a lower-is-better metric, it lists the lowest oriented
  percentiles first.

**Reproduced, before and after.** `/api/terminal/rank?metric=goals&country=England`:
- Before: Otis Nakamura (DF, 1 goal, 99th percentile of defenders), Haruki Adeyemi (MF), then Femi Toure.
- Now: `rank_by: value`, three level boards.

| Board | Rows | Top rows |
|---|---|---|
| Semi-pro, senior, men | 66 | Femi Toure (FW, 1.64 per 90), Amari Ustinov (1.04), Leon Whitfield (1.03) |
| Academy / youth, under 18, men | 39 | starts at offset 66 |
| Semi-pro, senior, women | 33 | starts at offset 105 |

- With `position=FW` the list is pool mode again, with Femi Toure first.
- `/api/catalogue/rank?metric=fouls&position=MF&order=desc` across levels is unchanged: pool mode, the lowest oriented
  percentiles first, with men's and women's boards.

**Tests.**
- New: `test_most_goals_in_england_puts_the_top_scorer_first_on_every_surface`. It checks the six surfaces above, the
  MCP tool's hint and level boards, pool mode with a position, and that `rank_by=pool` across positions keeps one
  position per board.
- Updated to the rule:
  - `test_screen_filters_sort_and_order` and `test_terminal_catalogue_payloads_say_how_they_ranked`: `rank_by=value`
    across academy levels is sorted within each of the four level boards.
  - `test_catalogue_cards_rank_within_pools_on_gender_boards`: gender boards with a position; level boards across
    positions, opening on Femi Toure.

**Behaviour that changed beyond the bug:**
- `rank_by=value` across levels no longer gives one raw list. It gives one board per level.
- On the MCP tool, `sort=minutes` now reports `rank_by: "value"` and the rule (it reported null before).
- On `/api/players` in catalogue mode, a value-ordered per-90 or ratio sort lists the cards with their competition's
  qualifying minutes first, then the rest. Otherwise a substitute's goal in a few minutes topped the semi-pro men's
  board (`pl_fai_20` before Femi Toure).
- Every endpoint without catalogue parameters is unchanged. The back-compat snapshot passes untouched.

## Review A round 3 nits

1. **One board shape on every surface.** Every board is `{board, by, label, gender, level, position, size, offset,
   top}`, made by `CatalogueMetrics.boards`. `top` holds at most `BOARD_TOP` (5) rows, and `limit` when that is
   smaller.
   - The old per-surface keys are gone: `ranked`, `rows` and `total` became `size`, and `shown` went.
   - No back-compat test or snapshot used them (boards exist only in catalogue mode). Only this branch's own tests
     read them, and they were updated.
   - The MCP tool's `players` holds each board's top rows: up to `limit` each on two boards, up to 5 each on more.
     Without that, nine level boards times `limit` rows would flood an agent.
   - New test: `test_every_surface_serves_one_board_shape`, over seven lists.
2. **Minimum attempts on ratio pools in `/api/players`.**
   - `CatalogueProfiles.use_thresholds` takes each competition's ratio minimums from the metrics engine
     (`catalogue_profiles()` passes them).
   - `min_attempts(cid, ratio)` maps a profile ratio to its terminal metric's minimum: pass accuracy needs 10 passes;
     take-on success, shot accuracy and aerial win use FBref's per-squad-game rule scaled to the competition.
   - `ratio_pool` and `sort_percentile` leave out rows below it, so a forward with 19 of 19 passes in 60 minutes no
     longer tops the pass-accuracy pool.
   - New test: `test_ratio_pools_on_cards_need_the_minimum_attempts`.
3. **`build_catalogue` logs a failed pool.**
   - It writes a warning on logger `regista.catalogue.build`: "the process pool failed, building N matches here, one by
     one", with the traceback. Then it builds the matches as before.
   - Tested with a broken `ProcessPoolExecutor` and `caplog`.
4. **Stale folders are deleted inside the lock.**
   - `season.build.match_lock(match_id)` is the per-match lock that `materialise` and `ensure_tracks` already took,
     now named.
   - `catalogue.build.materialise_match` checks the labels again and removes a stale folder while holding it, so it
     never deletes a folder another thread is writing.
   - England's build behaves exactly as before.
   - Tested: the lock is held when the folder is removed.

Not fixed (left as review A listed them, outside this step's scope):
- `catalogue_fingerprint` hashes label wording;
- an unknown `country` gives an empty 200;
- `/api/teams` ignores `scope`;
- `/api/catalogue/matches` waits for the full metrics engine;
- `store.repo_root` assumes the index's location;
- pool ties share a rank on (percentile, value).

## Still open

- **S-C, U17 match speeds (Zaid's call):** 29.68 km/h against 24.9-28.7. The data is unchanged.
- **S-D, how little levels differ in event rates (Zaid's call):** unchanged. The level boards make it matter less in
  lists, because raw numbers no longer cross levels.
- **Review B nits, not in this step:**
  - pools without spread (`no_spread`);
  - short uploads tying long ones at the top of a percentile;
  - unqualified cells returning `pool.reason: null`;
  - clubs with one 30-minute upload that can never qualify. Ghana's Rainforest and Adinkra Stars, and Morocco's Jnane
    Vert and Najm Atlas, each have one upload now.
- **Phase 5** is not written: the realism report, CLAUDE.md §2.11 and the data README's Catalogue section. The
  source entries still lack authors or a year.
- **Older build reports describe the old shapes.** `api.md` and `engine.md` still describe gender-only boards and the
  old per-surface board keys. `design.md` still describes windows without the as-of date. They are records of their
  phases; this file and `RANK_RULE` supersede them, and phase 5 should fold this in.
- **Linux CI has not run this branch.** The 60 pins were re-recorded on macOS. The PR will be their first Linux run.
  The dates never reach a draw, and nothing new here is platform-specific.
