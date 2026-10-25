# The catalogue: the engine (phase 3)

Branch `feature/catalogue`, 2026-10-25. This is phase 3 of `docs/catalogue/build/design.md`: the Scout terminal's
metrics engine running over all 14 competitions. It covers pools within a level, careers, similar players within and
across levels, team style per competition, and reliability and realism per level. The API (phase 4) and the full
realism report (phase 5) come next. Nothing here writes to the live app, Azure or Fabric.

## What exists now

| Module | What it does |
|---|---|
| `regista/catalogue/metrics.py` | `CatalogueMetrics`: one `SeasonMetrics` per competition, percentiles pooled by scope, cells with pool and sample, careers, similar players, team style, pool sizes. `load_catalogue_metrics()` builds it once per process. |
| `regista/catalogue/profiles.py` | `CatalogueProfiles`: one `Season` per competition, giving moments across competitions, touch maps, uploaded matches with uploader and camera, and results (England's table; elsewhere "uploaded matches only, not a league table"). |
| `regista/catalogue/measure.py` | Measurement seasons: each competition's full double round robin regenerated in memory with measurement seeds, cut in halves, and computed with the engine's rule for that competition. |
| `regista/catalogue/reliability.py` | Split-half reliability per level on those seasons, committed as `data/catalogue/reliability.json` with a fingerprint. |
| `regista/catalogue/realism.py` | Which check each metric gets at each level (band, order, reference or none), plus `band_checks` and `order_checks` over level aggregates. |
| `python -m regista.catalogue levels`, `player ID`, `reliability` | Pool sizes; one player across the catalogue; re-measuring every level. |

### Changes to existing code (additive; the defaults reproduce today exactly)

- `SeasonMetrics.from_streams(league, streams, *, xt=None, min_minutes_floor=0.0, min_pool=2)`:
  - `xt` values moves with a given grid instead of fitting one.
  - The floor lifts the qualifying minutes only when it is higher. This is a branch, so England keeps its exact float.
  - `min_pool` replaces the hard-coded `len(vals) < 2`.
- `Season.build(..., *, min_minutes_floor=0.0, min_pool=2)`, the same two rules on the profiles side. `_percentiles` takes `min_pool`, and `>= 2` equals the old `> 1`.
- `Dockerfile` ships `data/catalogue/reliability.json` (guarded in `tests/test_packaging.py`).
- `cloud/smoke.py` gains `catalogue_reliability_checks`, which checks inside the image that the shipped table is current.
- CLAUDE.md §3.0 gains lines for the new modules and commands. §2.11 is phase 5's.

The back-compat snapshot (`tests/test_catalogue_backcompat.py`: 21 HTTP and 4 MCP responses recorded on `main`) still
passes, and so do `SEASON_PINS`, `CATALOGUE_PINS` and `tests/test_backcompat.py`. No endpoint was added or changed.

## How the engine is built

- **England semi-pro men** is `load_metrics(league.json, data/season/matches)`: the very object the existing endpoints
  read, with its fitted xT, its 100.5 qualifying minutes and its percentile pools of 2 or more. A test asserts
  identity (`cm.metrics["co_eng_sp_men"] is load_metrics(...)`).
- **Every other competition** is built with `SeasonMetrics.from_streams(comp, streams, xt=england.xt, min_minutes_floor=45, min_pool=5)`
  (design.md D7 and §7.2):
  - 3-8 matches cannot fit a 12 × 8 xT grid, so these competitions use England's fitted grid as a fixed reference.
  - Qualifying minutes are `max(45, a third of the busiest club's minutes)`. Every sparse competition comes out at 45.
  - A club with one uploaded match leaves its players unqualified. There is not enough footage, and a test checks this.
- **Cost**: building the 13 sparse competitions' engines takes 1.4 s on Zaid's Mac, with the England engine already
  cached (0.8 s cold). The profiles side takes 1.8 s.

Qualified rows (minutes at or above the competition's minimum) per competition:

| Competition | Matches | Players who played | Qualified | Qualifying minutes |
|---|---|---|---|---|
| Regista League (England semi-pro men) | 30 | 102 | 66 | 100.5 |
| Pennine Women's League | 5 | 82 | 47 | 45 |
| Shires Academy League U18 | 4 | 64 | 22 | 45 |
| Atlantic Collegiate Soccer Conference | 6 | 94 | 33 | 45 |
| Pacific Coast Collegiate Conference | 5 | 80 | 31 | 45 |
| Regional Preferente Levante Interior | 5 | 80 | 32 | 45 |
| Liga Juvenil Meseta Norte | 5 | 80 | 41 | 45 |
| Weserland-Liga | 8 | 97 | 55 | 45 |
| Campeonato Serrano Sub-20 | 4 | 63 | 22 | 45 |
| Ogun Riverside Amateur League | 4 | 64 | 31 | 45 |
| Ashanti Colts Academy League U17 | 3 | 59 | 21 | 45 |
| Minato Bay University League | 4 | 63 | 31 | 45 |
| Liga Amateur del Valle Alto | 4 | 64 | 32 | 45 |
| Ligue Juniors Atlas Centre U19 | 3 | 62 | 11 | 45 |

## Pools within level

There are three scopes (design.md §7.3). A row qualifies under its own competition's rule, and a pool is the qualified
rows of one position in the scope:

- **`level`** (default): the same tier, age group and gender.
- **`competition`**: one competition. For England this is today's percentile, exactly.
- **`all`**: every tier and age group of one gender. Genders never mix, and responses in this scope carry a warning
  that levels differ.

The percentile rule is FBref's throughout, inverted where lower is better:
- Below 5 peers there is no percentile, and the cell gives the reason ("fewer than 5 qualified peers").
- Below 15 peers the pool is flagged `small`.
- England's own competition scope keeps the league's minimum of 2, so its numbers do not move.

Every cell carries the competition engine's own fields (`value`, `percentile`, `qualified`, `total` or `num`/`den`,
`peers`, `noisy`), plus `evidence_total`, `pool` (scope, tier, age group, gender, position, size, small, min_size,
competitions, reason) and `sample` (competition, minutes, appearances, qualifying minutes, competition and club
matches).

**Pool sizes per level and position** (rows qualified on minutes; a metric's own pool can be smaller because of ratio
attempts). `*` marks small (under 15); `!` marks under 5, where no percentile is given.

| Level pool | Competitions | GK | DF | MF | FW |
|---|---|---|---|---|---|
| semi_pro / senior / men | England, Germany | 11* | 44 | 33 | 33 |
| semi_pro / senior / women | England | 5* | 16 | 15 | 11* |
| college / college / men | USA, Japan | 6* | 24 | 16 | 18 |
| college / college / women | USA | 3! | 11* | 8* | 9* |
| amateur / senior / men | Spain, Nigeria, Mexico | 9* | 33 | 26 | 27 |
| academy / U20 / men | Brazil | 2! | 8* | 6* | 6* |
| academy / U19 / men | Spain, Morocco | 5* | 19 | 15 | 13* |
| academy / U18 / men | England | 2! | 8* | 6* | 6* |
| academy / U17 / men | Ghana | 2! | 8* | 6* | 5* |
| all / men | 12 competitions | 37 | 144 | 108 | 108 |
| all / women | 2 competitions | 8* | 27 | 23 | 20 |

Morocco U19 on its own qualifies 1 keeper, 4 defenders, 3 midfielders and 3 forwards, so every competition-scope
percentile there is null. The level pool with Spain U19 gives them percentiles. This is the case for pooling within
level.

Across all 127 metrics × positions (343 metric-position pools per level), the number of pools under 5 at level scope is:

| Pool | Under 5 |
|---|---|
| semi-pro men | 3 |
| college men | 16 |
| amateur men | 18 |
| U19 | 23 |
| semi-pro women | 25 |
| college women | 46 |
| U18 | 51 |
| U20 | 55 |
| U17 | 56 |

They are mostly keeper metrics.

## Femi Toure's percentiles with the new semi-pro men pool (England + Germany)

Femi Toure (`pl_bro_09`) in competition scope is exactly what the terminal shows today. The level-scope pool adds
Germany's qualified forwards: 33 instead of 18.
- He still leads the level's forwards in goals, non-penalty goals and npxG per 90:
  - non-penalty goals per 90: 1.64, then Amari Ustinov 1.04 (England) and Leon Whitfield 1.03 (England);
  - npxG per 90: 1.15, then Ustinov 0.77 and Leon Lehmann 0.52 (Weserland-Liga, Germany's best).
- His headline percentiles barely move (97 to 98).
- Where Germany's forwards are stronger, he slips: shot-creating actions 97 to 92, progressive passes received 92 to
  86, pass completion 75 to 65.
- Where they are weaker, he rises: xA 53 to 65, take-ons won 8 to 14, top speed 58 to 74.

| Metric (FW default columns, then more) | Value | Competition pct (pool) | Level pct (pool) | All men pct (pool) |
|---|---|---|---|---|
| Non-penalty goals | 1.64 | 97 (18) | 98 (33) | 96 (108) |
| Non-penalty xG | 1.15 | 97 (18) | 98 (33) | 97 (108) |
| npxG per shot | 0.185 | 92 (18) | 92 (31) | 87 (80) |
| xA | 0.14 | 53 (18) | 65 (33) | 65 (108) |
| Shot-creating actions | 5.91 | 97 (18) | 92 (33) | 90 (108) |
| Take-ons won | 0.33 | 8 (18) | 14 (33) | 37 (108) |
| Touches in the box | 9.19 | 97 (18) | 98 (33) | 96 (108) |
| Progressive passes received | 11.81 | 92 (18) | 86 (33) | 85 (108) |
| Goals | 1.64 | 97 (18) | 98 (33) | 96 (108) |
| Shots | 6.23 | 97 (18) | 98 (33) | 97 (108) |
| Top speed (season) | 35.0 km/h | 58 (18) | 74 (33) | 89 (108) |
| Distance covered | 9,198 m | 36 (18) | 35 (33) | 62 (108) |
| Pass completion | 74.2% | 75 (18) | 65 (33) | 60 (108) |

Across every England player and metric (6,310 cells that have a percentile in both scopes), the level pool moves a
percentile by:

| Measure | Points |
|---|---|
| median | 5 |
| mean | 5.7 |
| maximum | 34 |

Of those cells, 1,083 move by 10 or more and 129 by 20 or more.

Four England cells lose their percentile in level scope: keeper ratios whose competition pool is 2-4. The level's
minimum is 5, so the bigger pool is still too small. No cell gains one. The `all` scope ranks him against 108 forwards
from 12 men's competitions. His top speed rises to 89 there because youth and amateur forwards are slower by design,
which is why that scope warns.

## Careers

A career player has one row per competition, each read against its own level's pool. The career block lists every
squad he is in, in the career's order (where he came from first), even with 0 minutes. Each entry gives the
competition labels, season 2026/27, club, shirt, position and role, appearances, minutes, first and last match, and
the match ids.

`overall` sums what adds up: competitions, appearances, minutes, and the counts behind every per-90 metric. It gives
**no merged per-90 or percentile** (design.md §7.5), and says why.

Tests check five careers, two rows each, with minutes in both competitions. Each row's pools are its own level's,
the overall sums equal the rows' sums, and no player has two matches on one date.

| Person | Rows (competition: minutes) |
|---|---|
| Sergio Cruz (ST) | Spain U19: 42.2 (unqualified there); Spain amateur: 50.4 |
| Olivia King (W) | USA college women: 81.2; England semi-pro women: 51.7 |
| Alberto Navarro (CM), Finn Schmidt (CB), Edson Jimenez (W) | minutes in both (`python -m regista.catalogue player ID`) |

## Similar players within and across levels

Similarity is FBref's summary template (the keeper template for keepers): the cosine of standardised per-90 vectors
among qualified rows in the same position. The same person's other row is never his own match.

- **`competition`**: the competition engine's own `similar`. For England this equals the existing endpoint (tested).
- **`level`**: candidates from the whole level, standardised on the level's pool.
- **`all`**: candidates from every level of one gender, **each row standardised on its own level's pool**, so it finds
  players who stand out at their level the same way. Raw volumes, which differ between levels by design, are not
  compared. Each match says `same_level`, and the response warns.

For Femi Toure in `all` scope, the five closest are:

| Player | Competition | Similarity |
|---|---|---|
| Ulises Perez | USA college men | 0.897 |
| Murilo Pereira | Brazil U20 | 0.851 |
| Sergio Cruz | Spain amateur | 0.799 |
| Amari Ustinov | England | 0.743 |
| Kelvin Kyei | Ghana U17 | 0.683 |

All five share his non-penalty goals, npxG and shots strengths. In `level` scope the closest are Ustinov (0.743),
then Gino Reyes (England), Leon Whitfield (England), and Leon Lehmann and Fabian Meyer (Germany).

## Team style per competition

`team_style(competition, club)` is the competition engine's own (rank and mean among the competition's clubs with
uploaded matches; for England, exactly today's). It adds:
- `level_rank`, `level_of` and `level_mean` among every club of the level with uploads;
- the competition labels;
- `sample.small` when the club has fewer than 3 uploaded matches.

For example, Hollenburg's possession is 51.3%: 3rd of 6 in the Weserland-Liga and 4th of 12 semi-pro men's clubs. A
sparse competition's style rests on its uploads only, and the note says so.

## Reliability per level

`data/catalogue/reliability.json` applies the league's split-half method (`regista.season.reliability`) per level, on
**measurement seasons**:
- **What is regenerated**: every competition's full double round robin, 6 times (1,524 matches in all, never
  written).
- **Seeds**: base seed `comp_seed × 100 + n`, plus 50,000,000 × (season + 1). England keeps its fixtures' seeds plus
  the same offset. No measurement seed equals a committed one, which a test checks.
- **Halves**: each season is cut into its first and second half of rounds. In a double round robin each pair meets
  once in each half.
- **Rule**: each half is computed with the engine's rule for its competition.
- **Rows**: centred on the role's mean in that competition-season, then pooled over the level.
- **Cost**: 288 s on Zaid's 10-core Mac.
- **Stamp and checks**:
  - The file is stamped with the generator version and a fingerprint: England's league fingerprint, which covers the
    generator's source, plus every competition's clubs, ratings, seed, generator settings and level, the offset, the
    number of seasons and the method version.
  - A quick test checks the stamp, a slow test re-measures the U17 level bit for bit, and the image smoke test checks
    the shipped table is current.

| Level | Competitions | Matches | Median qualified minutes per half | Noisy | Not noisy | No estimate |
|---|---|---|---|---|---|---|
| semi_pro / senior / men | England, Germany | 360 | 142.1 | 83 | 34 | 10 |
| semi_pro / senior / women | England | 120 | 114.2 | 73 | 44 | 10 |
| college / college / men | USA, Japan | 252 | 129.1 | 77 | 40 | 10 |
| college / college / women | USA | 120 | 113.7 | 82 | 35 | 10 |
| amateur / senior / men | Spain, Nigeria, Mexico | 264 | 90.4 | 86 | 31 | 10 |
| academy / U20 / men | Brazil | 72 | 85.9 | 89 | 27 | 11 |
| academy / U19 / men | Spain, Morocco | 192 | 98.8 | 82 | 35 | 10 |
| academy / U18 / men | England | 72 | 87.4 | 93 | 20 | 14 |
| academy / U17 / men | Ghana | 72 | 85.4 | 87 | 29 | 11 |
| (England's own table, `data/season/reliability.json`) | England | 180 | about 150 | 78 | 39 | 10 |

Split-half r for a few metrics:

| Metric | England (own) | U17 | U18 | U19 | U20 | Amateur | College men | College women | Semi-pro men | Semi-pro women |
|---|---|---|---|---|---|---|---|---|---|---|
| npxG | 0.264 | 0.155 | 0.072 | 0.087 | 0.079 | 0.116 | 0.152 | −0.039 | 0.254 | 0.273 |
| Pass completion | 0.344 | 0.229 | 0.266 | 0.287 | 0.378 | 0.232 | 0.500 | 0.440 | 0.441 | 0.425 |
| Distance | 0.465 | 0.368 | 0.412 | 0.427 | 0.193 | 0.348 | 0.364 | 0.460 | 0.527 | 0.513 |
| Sprint distance | 0.489 | 0.777 | 0.563 | 0.630 | 0.571 | 0.524 | 0.477 | 0.789 | 0.581 | 0.818 |
| Peak speed (mean) | 0.819 | 0.772 | 0.745 | 0.755 | 0.787 | 0.771 | 0.745 | 0.863 | 0.836 | 0.841 |
| Interceptions | 0.019 | 0.015 | 0.012 | 0.031 | −0.064 | −0.012 | 0.028 | 0.012 | 0.069 | 0.043 |

How `noisy` is read:
- England in competition scope keeps the Regista League's table, as the existing endpoints read it.
- Every other number reads its row's level table. For Germany's own competition scope this is the semi-pro men level
  table, because no per-competition table exists.
- So an England number can be noisy in one scope and not the other. Of 127 metrics, the semi-pro men level table and
  England's own table disagree on 15 (for example shots, take-ons won, xG).

**What it cannot say.** The table measures half a *full* season of the level. Every sparse competition's uploads are
smaller than that (3-8 matches against 12-30 in the full round robin), so a metric marked noisy is noisier still on
the uploads, and one that is not marked may still be noisy there. A table on the uploads themselves is not computed,
because 3-8 matches cannot be split meaningfully. The engine's note (`RELIABILITY_NOTE`) and every metric's
`describe()` say which table a number reads.

## Realism per level (honest about which levels have bands)

`regista.catalogue.realism.realism(metric, competition)` gives each number's strongest check and everything behind it.
The kinds are design.md §10's:

| Level | Event rates | Physical | Order checks it takes part in |
|---|---|---|---|
| England semi-pro men | `reference`, **tuned**: the generator keeps the league inside these Premier League bands; no semi-pro band was read, so they are an upper reference | same | amateur sprinting and pass completion; women's pass completion, ball losses, distance at 20 km/h or more; youth speed and distance (England and Germany pooled as "senior") |
| Germany semi-pro men | `reference`: Premier League bands, no verdict | same | as above |
| College men | `reference`: Premier League bands, no verdict | plus NCAA Division I distance per match [S4], reference | women vs men (college) |
| College women, semi-pro women | `none`, apart from order checks | `reference`: elite women's distance [S2, S11] and sprint speed [S3] | pass completion lower, ball losses higher, distance at 20 km/h or more lower than men [S1, S2] |
| Amateur men | `none`, apart from order checks | `none`, apart from order checks | sprint distance below semi-pro [S9]; pass completion below semi-pro [S10] |
| U20, U19, U18 | `none` | `none`, apart from order checks | peak speed and distance rise U17 < U18 < U19 < U20 < senior [S5, S6, S8] |
| U17 | `none` | **`band`**: outfielders' mean peak match speed 24.9-28.7 km/h [S5] | as above |

Premier League bands never stand below senior semi-pro and college men (tested). The second-half drop in women's
high-intensity running [S1] is not checked, because the engine's metrics do not split halves (`NOT_CHECKED`).

### Preview of the checks on the measurement seasons (phase 5 owns the verdicts)

The same 1,524 measurement matches give level aggregates (`measure.level_aggregates`):
- per 90 rates per outfield player;
- pass completion over all outfield passes;
- the mean of outfielders' match top speeds, from matches with 10+ minutes.

`band_checks` and `order_checks` were run on them. Reproduce with
`python -m regista.catalogue reliability --aggregates PATH`. **Two checks fail.** As the design says, they are
reported here with their numbers and nothing was retuned.

| Check | Values (lowest level first) | Verdict |
|---|---|---|
| U17 band: mean peak match speed 24.9-28.7 km/h [S5] | **29.68** | **fail** (0.98 km/h above the top of the band) |
| Amateurs complete fewer passes than semi-pros [S10] | amateur **81.38%**, semi-pro men **80.53%** | **fail** (amateurs 0.85 points higher) |
| Amateurs sprint less than semi-pros [S9] | 209 m, 233 m per 90 | pass |
| Peak speed rises U17 < U18 < U19 < U20 < senior [S5, S6] | 29.68, 30.26, 30.57, 30.63, 31.46 km/h | pass |
| Distance per 90 rises with age [S8] | 9,855, 10,034, 10,040, 10,122, 10,365 m | pass (U18 to U19 by 6 m) |
| Women complete fewer passes, semi-pro [S1] | 79.68%, 80.53% | pass (0.85 points) |
| Women complete fewer passes, college [S1] | 79.18%, 81.04% | pass |
| Women lose the ball more, semi-pro [S1] | men 12.68, women 12.73 per 90 | pass (by 0.05: a coin flip, not a finding) |
| Women lose the ball more, college [S1] | men 12.18, women 13.12 per 90 | pass |
| Women cover less at 20 km/h or more, semi-pro [S1, S2] | 825 m, 1,040 m per 90 | pass |
| Women cover less at 20 km/h or more, college [S1, S2] | 817 m, 985 m per 90 | pass |

Why the two fail:

1. **U17 peak match speed.** The U17 top-speed multiplier (× 0.92) was taken from *maximal sprinting speed* (30.7 km/h
   [S6]). The generator's players reach about 94-97% of their top speed in a match. Real U17 players' *match* peaks sit
   well below their sprint-test maxima: 26.8 [S5] against 30.7 [S6], two different studies. So the scaled capacity is
   right for a sprint test and about 1-3 km/h high for match peaks. Senior men sit at 31.46, inside the Premier League
   band of 29-33. There are two fixes, and either is Zaid's call:
   - lower the youth speed multipliers;
   - make youth match peaks a smaller share of capacity.
2. **Amateur pass completion.** Phase 2 predicted this (catalogue.md). The passer's skill and the marker's skill drop
   together, so they cancel between two amateur sides. What is left (about −0.09 log-odds) is smaller than other
   effects at that level. Amateurs make fewer carries and take-ons, so more of their play is short, safe passes. The
   skill-offset size is Regista's assumption (taxonomy `LEVELS`), so a retune (a level-relative passing effect, or
   design.md §5.2's fallback) is a design change for Zaid.

Other aggregates, for context (team per 90):

| Level | Goals | Shots incl. penalties | Pass completion | Ball losses per 90 (outfield) |
|---|---|---|---|---|
| semi-pro men | 1.20 | 12.1 | 80.5% | 12.7 |
| semi-pro women | 1.22 | 11.1 | 79.7% | 12.7 |
| college men | 1.27 | 12.3 | 81.0% | 12.2 |
| college women | 0.95 | 9.7 | 79.2% | 13.1 |
| amateur men | 1.21 | 10.9 | 81.4% | 12.1 |
| U20 | 0.79 | 11.5 | 81.3% | 12.2 |
| U19 | 1.07 | 9.8 | 79.0% | 13.4 |
| U18 | 1.06 | 10.2 | 79.9% | 13.0 |
| U17 | 1.10 | 9.1 | 80.0% | 12.8 |

These pass completions count outfield passes as the engine's `pass_pct` defines them, so they read lower than the
indicative per-match table in catalogue.md, which counts differently. They are not bands.

## Hidden ratings

The engine reads the event streams, the physical records and the public bio only. `people()` drops `attributes`, and
no competition file's `level` block reaches a result. A test walks every engine result for every competition and
scope:
- `player`, `similar`, `team_style`, `describe`, `card` and `pool_sizes`;
- every career player with all 127 metrics.

It checks for any rating key (`ATTRIBUTE_KEYS`), `attributes`, or a scale key (`skill_offset`, `stamina_offset`,
`speed_mult`, `accel_mult`, `height_shift`, `style_offset`) and finds none.

## Tests

- New in `tests/test_catalogue_metrics.py`: 27 quick tests and 1 slow one.
  - **England unchanged.** England is the league engine itself. Its competition-scope cells equal today's for every
    player and all 127 metrics. Its competition-scope `similar` equals today's. The default arguments reproduce the
    league.
  - **Catalogue rules.** Every other competition follows them (England's xT, the 45-minute floor, pools of 5), and a
    club with one upload leaves its players unqualified.
  - **Pools.** A level pool is the union of its competitions' qualified rows. Percentiles follow FBref's rule by hand
    (including inverted ones). Small and too-small pools say so. `all` keeps gender and warns. A single-competition
    level gives the same numbers in both scopes. Every cell carries pool and sample.
  - **Evidence** opens `cm_` matches.
  - **Careers, similar players and team style**, as described above.
  - **Reliability.** The committed level table is current. `noisy` reads the right table.
  - **Realism** claims only what is checked. Band and order checks read aggregates.
  - **Privacy**: no hidden key anywhere.
  - **Pool sizes, filters and profiles.** Pool sizes cover every level, `select` filters, and the profiles give
    moments across competitions and upload-only results.
  - **Measurement seasons** are full round robins on unique seeds.
  - **Image smoke check**: the reliability table it checks is current.
  - **Slow**: re-measuring the U17 level reproduces the committed table bit for bit (16 s).
- `tests/test_packaging.py` gains the reliability file's guard.
- **Quick suite: 914 passed, 14 deselected** in 4 min 6 s (the full quick suite on the Mac, `python3 -m pytest -q`; 887 before this
  phase).
- **Slow suite: 14 passed** in 1 min 52 s (`python3 -m pytest -q -m slow`, the existing 13 and the new one).

## Open

- **Two realism checks fail on the preview**: the U17 peak match speed band and amateur pass completion (numbers
  above). Phase 5 runs the full report; any retune is Zaid's decision.
- **The per-level table is not yet checked on Linux.**
  - Its numbers come from league-mode generation (detmath) and the engine's arithmetic, the same as England's table,
    whose slow test passes on Linux CI.
  - The new slow test runs in the nightly slow workflow, which has not run on this branch.
  - The image smoke check confirms only that the shipped table is current, not that Linux re-measures it identically.
- **Small pools are the norm below semi-pro men**: four levels have keeper pools under 5, and most youth pools are
  small. This is honest, and the UI round must show `small` and `reason` well.
- **`all` scope's similarity compares players within their own level**, a design choice made here because the design
  did not specify it. A raw cross-level comparison would mostly pair players by level.
- **`card` returns `profile_url: null`** for non-England players, because the existing profile page serves England
  only. Phase 4 or the UI round links catalogue players.
- **Not built in this phase**: the endpoints and MCP tools (phase 4), `report.py --catalogue` and
  `docs/catalogue/realism.md` (phase 5), and catalogue Foundry summaries. Claims and Player-view uploads stay
  England-only.
