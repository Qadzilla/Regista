# Catalogue review round 2: fixes

Branch `feature/catalogue`. This round answers review A pass 2 (`review-a-pass2.md`) and review B pass 2
(`review-b-pass2.md`). No match, pin, rating or measurement moved:
- the England semi-pro men competition is byte-identical (its season pins hold);
- `generate()` without attributes is unchanged;
- every catalogue pin holds.

The changes are in ranking, payloads and the realism notes' wording.

Tests: 955 quick and 14 slow, all passing on macOS. Nothing here depends on the machine; the realism re-stamp reads
only committed JSON.

## Fixed

### 1. `order` meant opposite things in the two rank modes (review A #1)

**Problem.** In pool mode, `CatalogueMetrics.order_rows` applied `order` to the oriented percentile (high means good).
For a lower-is-better metric, `order=desc` therefore listed the fewest fouls first. In value mode it listed the most.

**Fix.** An explicit `order` is now the raw direction in both modes. In pool mode, the worst-first flag flips when
`higher_is_better` is False. Without `order`, the list stays best first. `RANK_RULE` and the endpoint docstrings say
so.

**Reproduced after the fix.** `/api/terminal/screen?metrics=fouls&sort=fouls&order=desc&position=MF&country=England`
now starts 4.84, 2.80, 2.37 (men's board).

**Test.** `test_order_is_the_raw_direction_in_both_rank_modes` uses fouls (per 90, lower is better) across England
semi-pro men and England U18. It covers:
- pool mode, with desc, asc and no order;
- value mode, on one level;
- `/api/terminal/screen` and `/api/catalogue/players`.

### 2. `/api/players` mixed levels and genders; the terminal hid the rank mode (review A #2)

**`/api/players`.** In catalogue mode, `players_payload` now follows `order_rows`' rule:
- **Across levels:** a per-90 stat or a ratio ranks by each card's percentile in `scope`, then pools that are not
  small, then more minutes, then the value. Cards without a percentile follow. The percentile comes from the new
  `CatalogueProfiles.sort_percentile`; ratios use the new `ratio_pool`.
- **Within one level, and for `minutes` or `name`:** cards rank by value.
- **Genders:** men's and women's cards always go on separate boards.
- **Response:** it adds `rank_by`, `rank_rule`, `boards` (each board's size and offset), and a `board` on each card.
- **Parameter:** `rank_by` is accepted.

**Reproduced after the fix.**
- `?country=England&sort=goals` starts with regulars at the 99th, 98th and 98th percentile (Femi Toure third, by
  minutes on a tie). The women's board starts at offset 166.
- `?tier=semi_pro&position=FW` starts with Femi Toure.

**Terminal endpoints.** In catalogue mode, `/api/terminal/screen` and `/rank` add `rank_by`, `rank_rule` and `boards`
to today's keys. They accept `rank_by`, which switches them to catalogue mode, as a catalogue filter does. These keys
are additive and appear in catalogue mode only. Responses without catalogue parameters keep their keys, which
`tests/test_catalogue_backcompat.py` pins.

**Tests.**
- `test_catalogue_cards_rank_within_pools_on_gender_boards`
- `test_terminal_catalogue_payloads_say_how_they_ranked`

### 3. The youth order notes claimed age steps their sources do not cover (review B #3)

**Problem.** [S8] covers U13-U18, and [S5, S6] cover U13-U17. The notes claimed more than that.

**Change.** This is wording and spans only. `realism.ORDERS` now separates what is sourced from what is assumed:

| Order | Levels | Basis | Sources |
|---|---|---|---|
| `youth_distance` | U17 < U18 | sourced | [S8] |
| `youth_distance_extension` | U18 < U19 < U20 < senior | assumed, no published band | none ([S8] covers U13-U18 only) |
| `youth_peak_speed_mean` | U17 < U18 < U19 < U20 < senior | assumed, no published band, **by construction** | none ([S5], [S6] cover U13-U17 only) |

The youth speed scales are interpolated between U17 and senior (`taxonomy.LEVELS`), so the peak-speed order tests the
build, not football. The served note says exactly that.

**How assumed orders are served.**
- They are measured the same way, and the note opens with "Assumed order, no published band".
- They are served in `realism.assumed_orders` with `basis`, `covers` and `by_construction`.
- They never make a metric's kind "order" and never set its verdict. U19 and U20 distance and every youth peak speed
  above U17 are now kind `none`.
- `level_kinds` lists them as `assumed_orders`.

**Re-stamping `data/catalogue/realism.json`.** It was re-stamped by the new `python -m regista.catalogue
recheck-realism`, which re-runs the band and order checks on the file's own stored aggregates (`levels`,
`per_season`) without regenerating any season. The measurement, fingerprint and method are unchanged:
- The bands and every unchanged order keep identical steps and verdicts.
- The U17 to U18 distance step passes (margin 179 m, noise +/- 75).
- The distance extension and the peak-speed order are not separated, as before.
- Sourced checks: two fail (U17 band, amateur pass completion) and one is not separated (women's ball losses,
  semi-pro).

**Carried into the reports.** `docs/catalogue/build/engine.md` (the level table and the verdicts table) has the change.
The phase 5 report does not exist yet; it should quote this split.

**Tests.**
- `test_youth_orders_claim_only_the_span_their_sources_cover`
- `test_the_committed_realism_verdicts_match_their_own_aggregates`: the committed verdicts equal `recheck` of
  themselves.

### 4. The women's board was hidden from cross-catalogue lists and the MCP tool (review B #4)

No data moved. The changes are in the new endpoints and the tool only.

**API.**
- `/api/catalogue/rank`: each entry in `boards` now has `ranked`, `offset` (where the board starts among the ranked
  rows) and `top` (its first rows, up to 5).
- `/api/catalogue/players`, `/api/competitions/{id}/players` and the terminal screen: each board has `rows`, `offset`
  and `top`.
- So the women's board is on every page. `offset=boards[1].offset` pages straight to it.

**MCP tool.** When a selection holds men and women, `search_catalogue_players` returns each board's top `limit` rows:
the men's, then the women's, each row with its `board`. It also returns `boards` (`gender`, `total`, `shown`) and a
`hint` to pass `gender` to read one board further.

**Test.** `test_a_mixed_gender_rank_shows_the_womens_board_on_its_first_page`: rank, screen and tool all show women on
the first page or call.

## Not fixed: Zaid's decisions (open from round 1, no change)

- **U17 match speeds (round 1 S1).** Ghana U17 outfielders' median peak match speed is about 30 km/h, and the served
  note says the band fails by 0.98 km/h. Two options:
  - retune the academy speed multipliers, which moves every youth pin and the level reliability table;
  - accept the failure in CLAUDE.md §2.11 (phase 5).

  Decide before any youth profile or youth leaderboard appears in the demo.
- **Levels differ in ratings and pace, not in most event rates (round 1 S2).** `ALL_WARNING` says so plainly. Two
  options:
  - build design.md §5.2's level-relative passing and retention effect, which moves every catalogue pin;
  - record the acceptance in phase 5, so the pitch never claims that levels differ in what a scout reads.

Both choices change the data or the project's stated scope, so they are Zaid's call. They are not made here.
