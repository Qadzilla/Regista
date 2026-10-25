# The catalogue: data and build (phases 0, 1 and 2)

Branch `feature/catalogue`, 2026-10-25. This covers the back-compat snapshot (phase 0), the catalogue's definition
(phase 1) and building every match with pins (phase 2) of `docs/catalogue/build/design.md`. The engine (phase 3), the
API (phase 4) and the realism report (phase 5) come next. Nothing here writes to the live app, Azure or Fabric.

## What exists now

- **14 competitions in 10 countries.** England semi-pro men is the existing Regista League. `data/season/league.json`
  is byte-identical to `main` (SHA-256 `04dbb30f…0b1a34`, pinned by `tests/test_catalogue_backcompat.py`). The other 13
  are new, invented and committed in `data/catalogue/`: `catalogue.json` (the index) and 13 league-shaped competition
  files, 652 KB in all.
- **60 new clubs and 1,075 new people** (1,080 squad slots; five careers fill two slots each). Every person has a public
  bio and hidden ratings scaled to their level, age group and gender.
- **60 sparse uploaded matches** (3-8 per competition), each with an uploader (a team account, or a starter of one of
  the two sides) and a camera type. England's 30 fixtures get uploader and camera through an overlay in the index.
- **Every match is built deterministically and pinned.** `regista.catalogue.pins.CATALOGUE_PINS` holds 60 hashes,
  recorded on macOS. CI checks them on Linux, and the image checks them through `smoke.catalogue_checks`. The 30
  England pins (`SEASON_PINS`) are untouched and still pass.

Run it with `python -m regista.catalogue define --check`, `python -m regista.catalogue check` (builds, then compares
with the pins) and `python -m regista.catalogue competitions`.

## The competitions

| Competition (invented name, id) | Country | Region (label) | Tier / age / gender | Teams | People | Uploads | Dates of the uploads | Cameras | Uploaders team/player |
|---|---|---|---|---|---|---|---|---|---|
| Regista League (`co_eng_sp_men`, existing) | England | Northern England | semi_pro / senior / men | 6 | 108 | 30 (full) | 2026-08-15 to 2026-10-17 | broadcast 8, drone 5, phone 2, tripod 15 | 19/11 |
| Pennine Women's League (`co_eng_sp_women`) | England | Yorkshire | semi_pro / senior / women | 5 | 90 | 5 | 2026-08-16 to 2026-10-11 | drone 2, phone 1, tripod 2 | 4/1 |
| Shires Academy League U18 (`co_eng_u18`) | England | West Midlands | academy / U18 / men | 4 | 72 | 4 | 2026-08-29 to 2026-10-10 | phone 1, tripod 3 | 4/0 |
| Atlantic Collegiate Soccer Conference (`co_usa_col_men`) | USA | New England | college / college / men | 6 | 108 | 6 | 2026-08-29 to 2026-10-17 | broadcast 2, drone 2, tripod 2 | 5/1 |
| Pacific Coast Collegiate Conference (`co_usa_col_women`) | USA | California | college / college / women | 5 | 90 | 5 | 2026-08-22 to 2026-10-17 | broadcast 2, drone 2, tripod 1 | 4/1 |
| Regional Preferente Levante Interior (`co_esp_am_men`) | Spain | Valencian Community | amateur / senior / men | 5 | 90 | 5 | 2026-09-12 to 2026-10-24 | phone 4, tripod 1 | 1/4 |
| Liga Juvenil Levante Interior (`co_esp_u19`) | Spain | Valencian Community | academy / U19 / men | 5 | 90 | 5 | 2026-09-05 to 2026-10-17 | drone 1, tripod 4 | 4/1 |
| Weserland-Liga (`co_ger_sp_men`) | Germany | Lower Saxony | semi_pro / senior / men | 6 | 108 | 8 | 2026-08-08 to 2026-10-10 | broadcast 3, drone 1, phone 2, tripod 2 | 5/3 |
| Campeonato Serrano Sub-20 (`co_bra_u20`) | Brazil | Minas Gerais | academy / U20 / men | 4 | 72 | 4 | 2026-08-08 to 2026-10-10 | drone 2, phone 1, tripod 1 | 3/1 |
| Ogun Riverside Amateur League (`co_nga_am_men`) | Nigeria | Ogun State | amateur / senior / men | 4 | 72 | 4 | 2026-09-05 to 2026-10-24 | drone 1, phone 2, tripod 1 | 1/3 |
| Ashanti Colts Academy League U17 (`co_gha_u17`) | Ghana | Ashanti | academy / U17 / men | 4 | 72 | 3 | 2026-09-05 to 2026-10-17 | tripod 3 | 2/1 |
| Minato Bay University League (`co_jpn_uni_men`) | Japan | Kanagawa | college / college / men | 4 | 72 | 4 | 2026-08-29 to 2026-10-24 | broadcast 3, tripod 1 | 3/1 |
| Liga Amateur del Valle Alto (`co_mex_am_men`) | Mexico | Jalisco | amateur / senior / men | 4 | 72 | 4 | 2026-08-15 to 2026-10-17 | drone 1, phone 1, tripod 2 | 2/2 |
| Ligue Juniors Atlas Centre U19 (`co_mar_u19`) | Morocco | Fès-Meknès | academy / U19 / men | 4 | 72 | 3 | 2026-09-12 to 2026-10-24 | drone 2, tripod 1 | 2/1 |

Totals: 14 competitions, 10 countries, 66 clubs, 1,183 people (108 + 1,075), 90 matches (30 + 60). The "People" column
counts each competition's squads, so a career player appears in both of his competitions.

Every club appears in at least one uploaded match. Uploads were drawn from each competition's double round robin; with
an odd number of clubs, each round has a bye. Rounds are spread in whole weeks across each competition's season window
(US college in the autumn, for example). The catalogue is dated 2026-10-24 (`taxonomy.AS_OF`, served as `as_of`): a
library of footage holds only matches already played, so uploads are drawn only from rounds played by then, and every
competition that started in August or September contributes its opening rounds (fixes-3.md, review B round 3 S-A). Camera weights and team-upload rates by tier are design.md §2.5's. Camera type
is a label only: every match is rendered the same way, and each manifest's subtitle says so.

## Levels: what the scales produced

These are the scales of design.md §4.3, applied as written. Means are over each pool's people (outfielders for speed
and ratings) in the committed definition.

| Pool (tier / age / gender) | Competitions | Outfield top speed (km/h) | Mean of the 7 skills (outfield) | Stamina | Age | Height (cm) |
|---|---|---|---|---|---|---|
| semi_pro / senior / men | England, Germany | 33.3 | 62.8 | 73.0 | 26.2 | 181 |
| college / college / men | USA, Japan | 33.2 | 60.2 | 70.0 | 20.6 | 182 |
| amateur / senior / men | Spain, Nigeria, Mexico | 32.6 | 55.1 | 61.1 | 28.0 | 182 |
| academy / U20 / men | Brazil | 32.5 | 58.8 | 68.6 | 18.2 | 182 |
| academy / U19 / men | Spain, Morocco | 32.2 | 57.7 | 68.4 | 17.2 | 181 |
| academy / U18 / men | England | 31.9 | 56.9 | 68.3 | 16.5 | 179 |
| academy / U17 / men | Ghana | 31.1 | 54.1 | 63.8 | 15.8 | 178 |
| semi_pro / senior / women | England | 27.7 | 59.3 | 67.1 | 25.5 | 170 |
| college / college / women | USA | 27.6 | 57.3 | 65.3 | 20.5 | 169 |

Tests hold the designed order: women's top speed is more than 4 km/h below men's in the same tier; U17 < U18 < U19 <
U20 < senior in top speed; amateur < college < semi-pro in skill. They also check that every age, height, rating and
physical value sits inside its level's clamps. Each competition has its own standouts (the league's `STANDOUTS` pairs,
lifted within the competition), and no one outside England is a star. Femi Toure (`pl_bro_09`) is still the only
finishing 99.

How each scale is sourced (sourced, direction only, or Regista's assumption) is recorded in
`regista.catalogue.taxonomy.LEVELS[...].source` and design.md §4.3. The scales are hidden like the ratings: a test
checks that the index carries no rating or scale key.

## Careers

Five people play in two competitions. Each has one global id, one bio and one set of ratings in both squads, plays the
same role in both and starts in both. Each has minutes in uploaded matches of both competitions (checked on the built
matches) and never plays two matches on one date.

| Person (global id) | From | To | Role | Story |
|---|---|---|---|---|
| Sergio Cruz (`pl_sot_09`) | UD Sotoalto Juvenil, Spain U19 | CF Torrevalle, Spain amateur | ST | academy striker stepping up to a senior amateur side |
| Alberto Navarro (`pl_nvc_08`) | CF Navalcastro Juvenil, Spain U19 | CD Riuseca, Spain amateur | CM | the same |
| Olivia King (`pl_msa_07`) | Mesa Alta College, USA college women | Oxenridge Women, England semi-pro women | W | English student-athlete who played her home club's opening match in August, before the college season |
| Finn Schmidt (`pl_sms_04`) | Saltmarsh State, USA college men | VfL Mövenstedt, Germany semi-pro | CB | German student-athlete who played for a home side in August, before the college season |
| Edson Jimenez (`pl_kbc_11`) | Kestrel Bay College, USA college men | Club Agave Azul, Mexico amateur | W | Mexican student-athlete, the same pattern |

The England semi-pro men competition takes no career player, because its squads are frozen.

## Determinism, seeds and pins

- Every definition draw comes from `regista.detmath.Random` streams, one set per competition: names and clubs
  `Random(comp_seed)`, attributes `+3`, coverage `+7`, uploader and camera `+11` (×1000). The England overlay uses
  `Random(2027001)` and careers `Random(2027013)`. Here `comp_seed = 202700 + k`. Match n of competition k has seed
  `comp_seed × 100 + n` (20270101 to 20271303). All 90 match seeds in the catalogue are unique, which a test checks.
- **Pins:** `CATALOGUE_PINS`, 60 entries (the first 16 hex digits of each `events.jsonl`), recorded on macOS arm64 with
  Python 3.13. A cold build on one core and a cold build on 10 cores gave identical folders (`diff -r`). Linux
  agreement is checked by CI (`tests/test_catalogue_build.py`) and inside the image (`smoke.catalogue_checks`). It has
  **not been run on Linux yet**: that happens on the PR's CI.
- **England untouched:** all 30 `SEASON_PINS` still pass, `tests/test_backcompat.py` passes unchanged, and so does the
  back-compat snapshot below.

## Build time (cold) and size

| Run (Zaid's 10-core Mac, generator 0.7.1) | Time |
|---|---|
| 60 catalogue matches, cold, 10 processes (`python -m regista.catalogue build`) | **12.6 s** (12.7 s wall) |
| 60 catalogue matches, cold, one process (`--workers 1`) | **78.8 s** (1.31 s a match) |
| warm (every folder current) | 0.2 s |
| one match (Ghana U17, matchday 2), cold | 1.29 s |

The folders take 68 MB without tracks (about 1.1 MB a match). Tracks are written only when a video is requested
(`ensure_tracks`), as for the league. The Docker image now builds the catalogue at `docker build` time, after the season,
so a fresh revision starts warm.

## Code changes outside the new package (all additive)

| Change | Why | Effect on what exists |
|---|---|---|
| `synth/generator.py`: optional team-spec key `style_offset` (`{"keep": x, "press": y}`) re-centres `TEAM_STYLE` | Without it every amateur and U17 side sits at the style clamp (−2.5), so all sides play alike. A test shows the clamp without the key and distinct, unclamped styles with it | Inert without the key: a branch, not `+ 0.0`. `LEAGUE_GENERATOR_VERSION` stays 0.7.1. |
| `season/league.py` `generate_kwargs`: adds `style_offset` to both teams when the file has a `level.style_offset` | One place, so `fingerprint`, `materialise` and `ensure_tracks` all see it. This replaces the design's separate `generate_kwargs_catalogue` | `league.json` has no `level` key, so England's arguments are unchanged (tested) |
| `season/build.py` `materialise`/`ensure_tracks`: optional `manifest_extra`, `title_fn` | the catalogue manifest | Defaults give today's manifest exactly |
| `api.py`: `CATALOGUE`, `CATALOGUE_ROOT`; `_is_season_match`/`_season_match_dir` resolve `cm_…` ids | `/api/matches/cm_…`, `/clips`, `/recap` and video work for catalogue matches | `rl_…` unchanged; `/api/matches` (the Product's list) unchanged (tested) |
| `cloud/smoke.py`: `catalogue_checks` | pins inside the image | adds one check line |
| `Dockerfile`, `.gitignore`, `.dockerignore`, CI path filter | ship `data/catalogue/`, build it, ignore `data/catalogue/matches/` | `tests/test_packaging.py` guards it |
| `data/season/reliability.json`: re-stamped | its fingerprint includes `generator.py`'s source | **Only `league_fingerprint` changed** (`5fceb20c3903f148` to `a91152377b0055b4`). All 127 metrics' numbers are identical: the six-season recomputation was diffed line by line in 38 s on 10 cores. |

Two deviations from the design, both recorded in code: (1) `style_offset` is a per-key dict, not one float. `press`
averages defending and stamina, and stamina also carries the level's `stamina_offset`, so `press` is offset by
`skill + stamina/2`. With one float, every amateur side would sit 1.7 z below the centre in press. (2) A person's
nationality is drawn with the name (names stream), so the name comes from that nationality's pool.

## Phase 0: the back-compat snapshot

Before any code change, `tests/catalogue_snapshot.py` recorded the canonical JSON hashes of 21 HTTP calls and 4 MCP
calls on `main`'s code into `tests/data/catalogue_backcompat.json`. The HTTP calls cover `/api/season`, `/api/players`
(two ways), the star's profile and moments, `/api/compare`, the rules Scout answer, `/api/metrics`, the terminal's
screen, rank and scatter, the star's metrics, form, similar, shots and heatmap, the teams, Brookfield's style and shots,
and an unknown player's 404. The MCP calls are `search_players` (two ways), `get_profile` and `compare_players`. The
only fields dropped are `warm` and timings (`ms` and the like). After the generator edit the snapshot failed, as
expected: `reliability.json` read as stale, so `reliability` became null in 9 responses. After the re-stamp it passes
again. Every existing response is what it is on `main`.

## Tests

- New, quick suite: `test_catalogue_backcompat.py` (2), `test_catalogue_define.py` (16), `test_catalogue_build.py`
  (11), plus a catalogue check in `test_packaging.py`.
- **Quick suite: 887 passed** (857 before this round), 13 deselected, in 4 min 20 s on the Mac.
  `test_catalogue_build.py` builds all 60 matches into `data/catalogue/matches/` once, as the league's pin test does
  for its 30. On a 4-core CI runner that is about 20-25 s.
- Slow suite (`-m slow`, run because the generator changed): **13 passed** in 1 min 36 s, including the reliability recomputation (equal to the re-stamped table), six pooled seasons in every band, and Femi Toure leading the league in npxG.

## Indicative numbers from the uploaded sample (not a realism verdict)

Per 30-minute match on the committed matches. 3-8 matches per competition is far too few for a verdict. Phase 5
measures each level on regenerated full round robins (design.md §10).

| Competition | Matches | Goals | Shots | Passes | Pass completion | Take-ons | Tackles | Fouls |
|---|---|---|---|---|---|---|---|---|
| Regista League (England semi-pro men) | 30 | 1.00 | 8.0 | 280 | 0.84 | 14.4 | 13.7 | 7.2 |
| Pennine Women's League | 5 | 0.60 | 6.0 | 294 | 0.82 | 12.2 | 17.6 | 8.0 |
| Shires Academy League U18 | 4 | 0.50 | 7.2 | 288 | 0.83 | 11.0 | 18.0 | 7.8 |
| Atlantic Collegiate Soccer Conference | 6 | 1.50 | 10.8 | 279 | 0.85 | 10.2 | 11.2 | 6.7 |
| Pacific Coast Collegiate Conference | 5 | 0.20 | 5.0 | 287 | 0.81 | 13.0 | 14.0 | 10.2 |
| Regional Preferente Levante Interior | 5 | 0.80 | 5.8 | 288 | 0.84 | 10.4 | 15.2 | 9.2 |
| Liga Juvenil Levante Interior | 5 | 1.00 | 7.2 | 282 | 0.81 | 11.6 | 15.8 | 8.4 |
| Weserland-Liga | 8 | 0.38 | 8.5 | 285 | 0.81 | 12.8 | 16.8 | 8.2 |
| Campeonato Serrano Sub-20 | 4 | 0.75 | 7.5 | 293 | 0.86 | 11.5 | 12.0 | 7.5 |
| Ogun Riverside Amateur League | 4 | 1.00 | 9.8 | 286 | 0.85 | 9.2 | 11.5 | 6.2 |
| Ashanti Colts Academy League U17 | 3 | 1.00 | 6.3 | 283 | 0.83 | 11.0 | 11.0 | 7.3 |
| Minato Bay University League | 4 | 0.75 | 4.5 | 288 | 0.81 | 15.0 | 16.5 | 6.8 |
| Liga Amateur del Valle Alto | 4 | 0.25 | 5.5 | 282 | 0.81 | 10.8 | 15.5 | 8.5 |
| Ligue Juniors Atlas Centre U19 | 3 | 0.33 | 8.3 | 286 | 0.83 | 12.0 | 13.0 | 7.3 |

One thing to watch in phase 5: on this sample, pass completion does not separate the levels (0.81-0.86 everywhere).
Design.md §4.3 predicted this. The passer's skill and the marker's skill both drop with the level, so most of it
cancels in a match between two sides of the same level; what is left is about −0.09 log-odds for amateurs. The sources
say amateurs and women complete fewer passes [S1, S10], so the phase 5 order check may fail. Per the design, that
would be reported with its numbers and not retuned silently.

## Open

- **Linux CI not yet run** on the 60 catalogue pins: it runs on the PR.
- **Name collisions:** every club, town, ground and competition name was invented and chosen to avoid real clubs and
  leagues I know of. It has not been checked against a search engine. Hollenburg, for example, is a village name in
  Austria, though no club of that name is known. People's names are random pairs of common given names and surnames,
  as in the league, so any match with a real person is a coincidence of common names.
- **Possible level separation gap** in pass completion and dispossessions (above). Phase 5 decides with full
  round-robin numbers.
- Uploader and camera are not in a match's fingerprint, so `regista.catalogue.build` compares the manifest's labels and
  rebuilds a folder whose labels changed. This is tested.
