# The catalogue: design (before any code)

Branch `feature/catalogue`, cut from `main` at c349c3d. Written 2026-10-25 for the builders of the data and engine round.
Nothing in this document runs yet; every "will" below is a plan.

**Zaid's decision.** Regista becomes a **catalogue of uploaded footage** for recruitment below the professional line.
Players and teams upload matches, and scouts find and compare players across countries and levels. The data stays
synthetic (CLAUDE.md §1.5 and the hackathon scope): invented people, invented clubs, invented competition names. Real
countries, regions and levels are classification labels only.

---

## 0. Decisions at a glance

| # | Decision | Why (short) |
|---|---|---|
| D1 | `data/season/league.json` is **not touched**: no new keys, same bytes. The catalogue is a new folder, `data/catalogue/`: one index file `catalogue.json` and one league-shaped file per new competition, `competitions/<competition_id>.json`. The England semi-pro men entry in the index **points at** `league.json` and adds its catalogue labels (country, level, uploader, camera) as an overlay. | Every pin, fingerprint, reliability stamp, summary basis, Fabric table, film roster and test that reads `league.json` keeps working with no edit. A league-shaped competition file works with today's `generate_kwargs`, `materialise`, `Season.build` and `SeasonMetrics.from_streams` as they are. |
| D2 | One **absolute rating scale** across the catalogue. Its reference (offset 0) is the existing league, now labelled England semi-pro men. Each level has a skill offset, physical multipliers, a height shift and an age range (§4.3). | The generator's skill z is absolute (`SKILL_CENTRE`), so ratings scaled by level make levels genuinely differ, and a player whose career spans two competitions keeps one set of ratings. |
| D3 | **One small generator change**: an optional per-team `style_offset` that re-centres team style (`TEAM_STYLE`) on the competition. Without the key nothing changes, byte for byte. The version string stays `0.7.1`. | Without it, every side at a low level hits the style clamp (−2.5), so every side in the competition plays the same way. Skill z stays absolute everywhere else. |
| D4 | Matches are built on demand and cached like the league's: `data/catalogue/matches/<match_id>/` (git-ignored, docker-ignored, built into the image). There are **60 new uploaded matches** with ids `cm_<code>_<nn>_<home>_<away>`. Every one is pinned (`regista.catalogue.pins.CATALOGUE_PINS`). | The same pattern as today's season (§2.5): deterministic, generated in about 1.3 s each, checked on Linux in CI and inside the image. |
| D5 | **Two engines side by side.** The existing league engine (`Season`, `SeasonMetrics` over `league.json`) keeps serving every existing endpoint unchanged. A new `CatalogueMetrics` holds one `SeasonMetrics` per competition and **re-pools** player-competition rows by (tier, age group, gender, position). | Requirement 3: the England competition's numbers on existing endpoints must not move. In the catalogue, Germany semi-pro men joins England's pool, so England players' level-scope percentiles legitimately differ. Every number says which pool it came from. |
| D6 | Scopes: `level` (default: same tier, age group, gender and position), `competition`, and `all` (every tier and age group, **same gender**). A percentile needs at least 5 peers. A pool under 15 is flagged `small`. | Requirement 4. FBref does not draw percentiles from tiny pools. Today England's goalkeeper pool is 6 (save% 4), so the flag is honest there too. |
| D7 | xT for every non-England competition uses **the grid fitted on the England season** (a fixed reference model). England keeps its own fitted grid, as today. | A 3-8 match competition cannot fit a 12 × 8 xT grid. Fitting once on a large set and applying it elsewhere is how Karun Singh's xT is used. |
| D8 | New data goes out through new endpoints (`/api/catalogue…`, `/api/competitions/{id}`), plus an optional `competition=` on `/api/season`, `/api/players` and the terminal endpoints. Without that parameter, every existing response is what it is today. | Requirement 3. |
| D9 | Realism: Premier League bands apply **at most** to senior semi-pro and college (as an upper reference). Youth, amateur and women's levels get a sourced band where one was read (one: U17 peak match speed), sourced **order checks** across levels, or "no published band". | Requirement 5. Section 10 has the table. |

---

## 1. What exists today, and what each caller does after this round

The callers below come from a grep of `league.json`, `regista.season` and `load_league` across `src/`, `tests/`,
`Dockerfile`, `infra/` and `static/` (the `.claude/worktrees/` copies are ignored).

| Caller | Reads | After this round |
|---|---|---|
| `season/league.py` (`new_league`, `assign_attributes`, `people`, `generate_kwargs`, `player_attributes`) | `league.json` | **Unchanged.** The catalogue's definition code imports its constants (`ROLE_MEANS`, `ROLE_SPEED`, `ROLE_HEIGHT`, `STANDOUTS`, `_round_robin`) and calls `generate_kwargs` on competition files. |
| `season/build.py` (`materialise`, `build_all`, `ensure_tracks`, `fingerprint`) | league dict + fixture | One additive change: optional `manifest_extra` and `title_fn` arguments to `materialise` (default None gives today's manifest). The England fingerprint is unchanged: `build.py` is not in `BUILT_BY`. |
| `season/pins.py` | built England folders | **Unchanged.** New pins live in `catalogue/pins.py`. |
| `season/profiles.py` (`Season`, `load_season`, `refresh`) | `league.json` + claims + uploads | Unchanged for England. `Season.build` is reused per competition for moments, touch maps and match lists. One additive argument: `min_minutes_floor` (default 0). |
| `season/metrics.py` (`SeasonMetrics`, `load_metrics`, `build_season`) | `league.json` | Unchanged for England. Additive optional arguments on `from_streams`: `xt=` (a fitted `XTModel`; default None fits one, as today), `min_minutes_floor=0.0` and `min_pool=2`. |
| `season/reliability.py`, `audit.py` | `league.json` + generator source | Unchanged code. **`reliability.json` must be re-stamped** after the generator edit (D3): its fingerprint includes `generator.py`'s source. Same numbers, new stamp (§5.3). |
| `season/summaries.py` + `summaries.json` | the league Season | Unchanged (`basis` does not include code). Catalogue players get rules summaries; Foundry summaries for them are not run in this round. |
| `season/scout.py` + `mcp_server.py` (`search_players`, `get_profile`, `compare_players`) | the league Season | Unchanged. New MCP tools are added beside them (§8.4). |
| `season/claims.py`, `claims_api.py`, `player_api.py`, `player/film.py` (`roster_for`), `player/worker.py` | `league.json` | Unchanged. Claims, uploads and the Player view stay England-only in this round. |
| `season/fabric.py`, `cloud/fabric_tables.py`, `cloud/fabric_notebook.py` | `league.json` | Unchanged (no Fabric job here). A catalogue push is **planned**, not built. |
| `season_api.py` (`/api/season`, `/api/players…`, `/api/compare`, `/api/scout/ask`) | `load_season(SEASON_LEAGUE…)` | Unchanged by default. Optional `competition=` on `/api/season` and `/api/players` (§8.2). |
| `terminal_api.py` (`/api/metrics`, `/api/terminal/*`, `/api/players/{id}/{metrics,form,similar,shots,heatmap}`, `/api/teams…`) | `load_metrics(SEASON_LEAGUE…)` | Unchanged by default. Optional `competition=` (§8.2). |
| `api.py` (`SEASON_LEAGUE`, `SEASON_ROOT`, `_season_match_dir`, `_is_season_match`, warm-up) | `league.json` | `_season_match_dir` and `_is_season_match` also resolve `cm_…` ids through the catalogue. New `CATALOGUE`/`CATALOGUE_ROOT` env settings. The catalogue warms after the metrics. `list_matches` is unchanged (it lists `DATA_ROOT` only). |
| `cloud/smoke.py` (`season_checks`) | built England folders | Adds `catalogue_checks`: catalogue pins inside the image, plus the new MCP tools in the Regista MCP tool list. |
| `Dockerfile` | copies `league.json`, `summaries.json`, `reliability.json`; builds the season | Also copies `data/catalogue/` (index + competition files) and runs `python -m regista.catalogue build`. |
| `static/*` (`shared/demo.js`, `scout/scout.js`, `scout/terminal.js`, `player/*`, `me/me.js`, `product/app.js`) | existing endpoints | **Unchanged** (the UI round comes later). The seeds in `demo.js` still quote England, which is still what the endpoints serve. |
| `synth/report.py` | league streams | Unchanged for `--league`. New `--catalogue` mode (§10). |
| Tests (`test_backcompat`, `test_league_mode`, `test_attributes`, `test_season`, `test_metrics`, `test_reliability`, `test_scout_*`, `test_fabric`, `test_player_*`, `test_smoke`, `test_packaging`, `test_recap`, `test_detmath`) | as above | All must pass unchanged, apart from the expected-tools list in the MCP and smoke tests, which gains the new tools. |

---

## 2. Data model

### 2.1 Levels taxonomy

A competition is classified on four axes. Pools are keyed on three of them: `(tier, age_group, gender)`.

| Axis | Values | Notes |
|---|---|---|
| `tier` | `semi_pro`, `amateur`, `college`, `academy` | `professional` is **not used** (below the professional line, by decision). Labels: "Semi-pro", "Amateur", "College / university", "Academy / youth". |
| `age_group` | `senior`, `college`, `U20`, `U19`, `U18`, `U17` | "college" is its own age group (18-23 student-athletes). An age group means under N on 1 August 2026 (the season start, `AGE_ON`). |
| `gender` | `men`, `women` | Display layers may say "boys" for male youth. Default pools never mix genders, and neither does `scope=all` (the physical scales differ by design, §4.3). |
| `format` | `11-a-side` | Every competition. |

These pools exist in the catalogue. Pool sizes are what to expect; the builders measure the real ones.

| Pool (tier / age group / gender) | Competitions | Outfield peers per position (approx.) |
|---|---|---|
| semi_pro / senior / men | England semi-pro men (30 matches), Germany semi-pro men (8) | 30-40 |
| semi_pro / senior / women | England semi-pro women (5) | 8-15, often `small` |
| amateur / senior / men | Spain regional amateur, Nigeria regional amateur, Mexico amateur (13 together) | 15-30 |
| college / college / men | USA college men (6), Japan university men (4) | 15-25 |
| college / college / women | USA college women (5) | 8-15 |
| academy / U20 / men | Brazil state U20 (4) | 5-12 |
| academy / U19 / men | Spain U19, Morocco U19 (8 together) | 10-20 |
| academy / U18 / men | England U18 academy (4) | 5-12 |
| academy / U17 / men | Ghana U17 academy (3) | 5-10 |

### 2.2 The 14 competitions

Every competition plays the 2026/27 season, 11-a-side, with squads of 18 in the fixed 4-3-3 numbering (`ROLE_OF_KIT`)
and **two halves of 15 minutes**, like the league. Thirty generated minutes stand in for a match; per-90 rates
normalise it, and every metric's thresholds already scale to it (`thresholds`, `qualifying_minutes`). Youth halves are
not modelled shorter: every competition gets the same synthetic compression, and the docs say so.

Names are invented. Regions are real place labels. The ids are the contract; builders may polish the display names but
must keep them invented and check that no name is a real club or league they know of.

| competition_id | code | Name (invented) | Country | Region (label) | Tier | Age | Gender | Teams | Uploaded matches | Coverage |
|---|---|---|---|---|---|---|---|---|---|---|
| `co_eng_sp_men` | (`rl`) | Regista League (**existing**) | England | Northern England | semi_pro | senior | men | 6 | 30 | full (double round robin) |
| `co_eng_sp_women` | `ewo` | Pennine Women's League | England | Yorkshire | semi_pro | senior | women | 5 | 5 | sparse |
| `co_eng_u18` | `eu18` | Shires Academy League U18 | England | West Midlands | academy | U18 | men | 4 | 4 | sparse |
| `co_usa_col_men` | `ucm` | Atlantic Collegiate Soccer Conference | USA | New England | college | college | men | 6 | 6 | sparse |
| `co_usa_col_women` | `ucw` | Pacific Coast Collegiate Conference | USA | California | college | college | women | 5 | 5 | sparse |
| `co_esp_am_men` | `eam` | Regional Preferente Levante Interior | Spain | Valencian Community | amateur | senior | men | 5 | 5 | sparse |
| `co_esp_u19` | `eu19` | Liga Juvenil Levante Interior | Spain | Valencian Community | academy | U19 | men | 5 | 5 | sparse |
| `co_ger_sp_men` | `gsp` | Weserland-Liga | Germany | Lower Saxony | semi_pro | senior | men | 6 | 8 | sparse |
| `co_bra_u20` | `bu20` | Campeonato Serrano Sub-20 | Brazil | Minas Gerais | academy | U20 | men | 4 | 4 | sparse |
| `co_nga_am_men` | `nam` | Ogun Riverside Amateur League | Nigeria | Ogun State | amateur | senior | men | 4 | 4 | sparse |
| `co_gha_u17` | `gu17` | Ashanti Colts Academy League U17 | Ghana | Ashanti | academy | U17 | men | 4 | 3 | sparse |
| `co_jpn_uni_men` | `jum` | Minato Bay University League | Japan | Kanagawa | college | college | men | 4 | 4 | sparse |
| `co_mex_am_men` | `mam` | Liga Amateur del Valle Alto | Mexico | Jalisco | amateur | senior | men | 4 | 4 | sparse |
| `co_mar_u19` | `mu19` | Ligue Juniors Atlas Centre U19 | Morocco | Fès-Meknès | academy | U19 | men | 4 | 3 | sparse |

Totals: 60 new matches (8+6+5+5+5+5+4+4+4+4+4+3+3), 60 new clubs, 1,080 new squad slots holding 1,075 new people (five
career players fill two slots each, §2.4), plus the existing 6 clubs, 108 players and 30 matches.

### 2.3 Clubs and people

- **Clubs**: `{club_id: "cl_<slug>", name, short_name (3-4 letters, unique across the catalogue; the six league codes
  ash/bro/cal/dun/eas/fai are reserved), city (invented town), ground, kit: {primary, secondary, gk}, squad: [...]}`.
  Kits are distinct within a competition by the league's rule (primaries far apart; keeper colours distinct from every
  primary and from each other), because the renderer and the vision layer need two clearly different team colours.
- **Squad entry**, in the same shape as `league.json`: `{global_id: "pl_<short>_<kit>", name, kit_number, position, starter,
  role, date_of_birth, height_cm, preferred_foot, nationality, attributes: {...hidden...}}`. A career player keeps the
  `global_id` of his first club and takes the destination club's kit number in its squad (§2.4).
- **Names** come from new per-country, per-gender pools (`regista/catalogue/names.py`): common given names and surnames,
  combined at random, so the people are invented. Tests check that no full name repeats in the catalogue and that none
  equals a league name.
- **Nationality** draws a mostly home-country distribution per competition (for example USA college about 75% USA plus
  international students; England about 80% England plus a mix). These are labels, like the league's.

### 2.4 Careers (a player in two competitions)

Five people. One person has one set of hidden ratings and one bio, shared by both squad entries. The destination slot
must have the same role (`ROLE_OF_KIT`) as the source slot.

| # | Source (first club) | Destination | Story | Same role? |
|---|---|---|---|---|
| 1 | Spain U19 academy (a striker) | Spain regional amateur men | An academy player stepping up to the senior amateur side (the "filial" pattern) | ST to ST |
| 2 | Spain U19 academy (a central midfielder) | Spain regional amateur men | Same | CM to CM |
| 3 | USA college women (an English winger) | England semi-pro women | A student-athlete who plays for her home club outside the college season | W to W |
| 4 | USA college men (a German centre-back) | Germany semi-pro men | Same pattern | CB to CB |
| 5 | USA college men (a Mexican forward) | Mexico amateur men | Same pattern | ST or W |

Rules the generator of the definition enforces, with a test for each:
- Both of the person's clubs have at least one uploaded match where he is on the team sheet, and he has minutes in
  both competitions (choose a starter slot in the destination, or retry the coverage draw deterministically).
- He never plays two matches on the same date.
- Same gender. Age is consistent: a U19 player is 17-18 and still eligible to play senior amateur football.
- The England semi-pro men competition takes no career player: its squads are frozen (requirement 1).

### 2.5 Matches: uploader and camera

A competition file's `fixtures` lists **only its uploaded matches**. Each is chosen from that competition's double
round robin (`_round_robin`, the league's function). It keeps the league's fixture fields (`match_id`, `round`, `date`,
`home`, `away`, `seed`) and adds:

```json
{"match_id": "cm_gsp_03_hbg_vor", "round": 3, "date": "2026-09-12", "home": "cl_hollenburg", "away": "cl_vorstadt",
 "seed": 20280803,
 "uploader": {"type": "team", "club_id": "cl_hollenburg"},
 "camera": "tripod"}
```

Or, for a player upload, `"uploader": {"type": "player", "global_id": "pl_vor_10", "club_id": "cl_vorstadt"}`. The
uploader is a member of either squad who played in that match.

- `camera`: one of `tripod`, `phone`, `drone`, `broadcast`. Draw weights by tier: semi-pro tripod .50, broadcast .25,
  phone .15, drone .10; college broadcast .55, tripod .35, drone .10; amateur phone .55, tripod .35, drone .10;
  academy tripod .55, drone .20, phone .15, broadcast .10.
- `uploader.type`: team-account probability by tier: semi-pro .70, college .80, amateur .40, academy .75. Otherwise a
  player uploads.
- **Camera type is a label.** Regista renders every match with the same broadcast-style view, and the vision layer is
  measured only on that render. The docs and the API note say so. Nothing claims that phone or drone footage is
  processed differently.
- **Coverage draw**: every club appears in at least one uploaded match. Otherwise uploads are chosen at random from
  the round robin, with dates in a plausible window for that country's calendar, kept inside 1 August 2026 to
  31 May 2027 under the "2026/27" label.
- **England semi-pro men** get uploader and camera for all 30 fixtures through the overlay in `catalogue.json`
  (§3.2). `league.json` is untouched.

---

## 3. Where it lives

### 3.1 Choice: a new `data/catalogue/` folder, with the league kept as one competition by reference

```
data/catalogue/
  catalogue.json                     index: taxonomy, competitions (order, labels, file or source), England overlay
  competitions/co_eng_sp_women.json  league-shaped: league, season, seed, generator, attributes, level, clubs, fixtures
  competitions/co_eng_u18.json
  ...                                13 files
  matches/                           built on demand (git-ignored, docker-ignored); one folder per cm_ match
```

**Why not grow `league.json` into the catalogue?** Its bytes are the input of `reliability.league_fingerprint` (its
`clubs`, `fixtures` and `generator`), `load_season`'s cache key (mtime), `summaries_path()`, `fabric_tables`,
`film.roster_for`, `tests/test_season.py::test_the_committed_league_is_what_new_league_writes`,
`tests/test_backcompat.py` (it reads fixture 0 and the squads), and the Dockerfile. Changing the file risks every one of
them, and most of the gain would go into selectors that every caller then needs. Kept apart, the frozen competition is
frozen by construction: a test pins `league.json`'s SHA-256 to its value on `main`.

**Why league-shaped competition files?** Every engine function takes a "league" dict (`clubs` with `squad`, `fixtures`,
`generator`, `league`, `season`). A competition file in that shape passes straight into `generate_kwargs`,
`materialise`, `build_all`, `ensure_tracks`, `Season.build`, `SeasonMetrics.from_streams`, `people`, `club_by_id` and
`bio`, with no change. The only new keys are additive: `competition` (labels), `level` (the scale used, §4.3) and the
fixtures' `uploader` and `camera`.

### 3.2 `catalogue.json` (index)

```json
{"catalogue": "Regista catalogue", "season": "2026/27", "seed": 2027, "version": 1,
 "note": "Synthetic: invented players, clubs and competition names. Countries, regions and levels are classification labels.",
 "levels": {"tiers": [...], "age_groups": [...], "genders": [...]},
 "competitions": [
   {"competition_id": "co_eng_sp_men", "code": "rl", "name": "Regista League", "country": "England",
    "region": "Northern England", "tier": "semi_pro", "age_group": "senior", "gender": "men", "format": "11-a-side",
    "season": "2026/27", "source": "league", "path": "data/season/league.json", "coverage": "full",
    "uploads": {"rl_r01_ash_fai": {"uploader": {"type": "team", "club_id": "cl_ashby"}, "camera": "tripod"}, "...": {}}},
   {"competition_id": "co_eng_sp_women", "code": "ewo", "name": "Pennine Women's League", "country": "England",
    "region": "Yorkshire", "tier": "semi_pro", "age_group": "senior", "gender": "women", "format": "11-a-side",
    "season": "2026/27", "source": "catalogue", "path": "data/catalogue/competitions/co_eng_sp_women.json",
    "coverage": "sparse"}
 ],
 "careers": [{"global_id": "pl_xxx_09", "competitions": ["co_esp_u19", "co_esp_am_men"]}]}
```

Paths are relative to the repo root and resolved against the index file's parent's parent's parent, the same way
`summaries_path()` is resolved next to the league. The resolver also honours `REGISTA_SEASON` for the England entry,
so tests and the Docker image (`/app/data/season/league.json`) keep pointing at the same file.

### 3.3 A competition file

The same top-level keys as `league.json`, plus these:

```json
{"league": "Weserland-Liga", "season": "2026/27", "seed": 202708,
 "competition": {"competition_id": "co_ger_sp_men", "code": "gsp", "country": "Germany", "region": "Lower Saxony",
                 "tier": "semi_pro", "age_group": "senior", "gender": "men", "format": "11-a-side"},
 "generator": {"name": "regista-synth", "version": "0.7.1", "profile": "league", "minutes": 15.0, "periods": 2, "track_hz": 1.0},
 "attributes": {"version": 1, "seed": 203708003, "age_on": "2026-08-01", "hidden": true, "scales": "docs/catalogue/build/design.md#43",
                "note": "Synthetic players. Ratings drive the generator and are never shown."},
 "level": {"key": "semi_pro/senior/men", "skill_offset": 0, "style_offset": 0},
 "clubs": [...], "fixtures": [...]}
```

`level` is the definition's own record of the scale it used: offsets and multipliers, read back by tests and by
`generate_kwargs_catalogue` for `style_offset`. It is never served (§8.5).

### 3.4 Code layout (new package `regista.catalogue`)

```
src/regista/catalogue/__init__.py
src/regista/catalogue/taxonomy.py    tiers, age groups, genders, LEVELS (scales per pool key, with sources), pool keys
src/regista/catalogue/names.py       per-country, per-gender name pools; club name parts
src/regista/catalogue/define.py      new_catalogue(seed): competitions, clubs, squads, attributes, careers, coverage,
                                     uploader/camera, England overlay; save/load; deterministic (detmath.Random streams)
src/regista/catalogue/store.py       load_catalogue_cached, competitions(), competition(id) -> (league-shaped dict, root),
                                     resolve_match(match_id) -> (competition, fixture, root), people across the catalogue
src/regista/catalogue/build.py       build_catalogue(cat, workers): one process pool over every stale fixture; materialise
                                     with the catalogue manifest
src/regista/catalogue/pins.py        CATALOGUE_PINS {match_id: 16 hex}, drift(cat)
src/regista/catalogue/metrics.py     CatalogueMetrics: per-competition SeasonMetrics, pooled percentiles, scopes, cells
src/regista/catalogue/profiles.py    per-competition Season (moments, touch maps, match lists), catalogue player view
src/regista/catalogue/__main__.py    python -m regista.catalogue {define|build|check|players|levels}
src/regista/catalogue_api.py         /api/catalogue…, /api/competitions/{id}… (router included in api.py)
```

Environment settings (in `api.py`, next to `SEASON_*`): `REGISTA_CATALOGUE` (default `data/catalogue/catalogue.json`),
`REGISTA_CATALOGUE_ROOT` (default `data/catalogue/matches`) and `REGISTA_CATALOGUE_WARM` (default `1`). England matches
keep `SEASON_ROOT`.

---

## 4. How the catalogue is defined (generated once, committed)

`python -m regista.catalogue define` writes `catalogue.json` and the 13 competition files. A quick test regenerates
them in memory and compares them, byte for byte, with the committed files (the pattern of
`test_the_committed_league_is_what_new_league_writes`).

### 4.1 Seeds and random streams

All definition streams are `regista.detmath.Random` (its `gauss` gives the same bits on macOS and Linux;
`random.Random.gauss` goes through libm). Each competition has its own streams, so adding or retuning one competition
never moves another.

| Stream | Seed |
|---|---|
| catalogue seed | `CATALOGUE_SEED = 2027` |
| competition k (k = 1..13 in the table order of §2.2, England excluded) | `comp_seed = 202700 + k` |
| names and clubs | `Random(comp_seed)` |
| attributes | `Random(comp_seed * 1000 + 3)` (cf. the league's `ATTRIBUTE_SEED_OFFSET`) |
| coverage (which fixtures are uploaded, dates) | `Random(comp_seed * 1000 + 7)` |
| uploader and camera | `Random(comp_seed * 1000 + 11)` |
| England overlay (uploader and camera of the 30 fixtures) | `Random(CATALOGUE_SEED * 1000 + 1)` |
| careers (which people, which slots) | `Random(CATALOGUE_SEED * 1000 + 13)` |
| match seed n (1-based within competition k) | `comp_seed * 100 + n` (20270101..20271308; never equal to a league seed 20270..20362, a sample seed or a vision seed; a test checks every seed in the catalogue is unique) |
| realism measurement seasons (§10) | `match seed + 50_000_000 * (repeat + 1)` |

Build order: competitions are defined in the order of §2.2, except that every career's source comes before its
destination (Spain U19 before Spain amateur; USA college men before Germany and Mexico; USA college women before
England women). The career stream picks the people once every source exists. In a destination squad the career slot is
**drawn like any other slot** (so no other player's draws shift) and then overwritten by the career person.

### 4.2 Attributes per person

This is the league's `_person_attributes` with a level applied. The draw order is fixed and documented in `define.py`:

1. `quality = gauss(±STARTER_EDGE/2, 1)` as in the league.
2. Age from the level's age range (triangular with a mode: §4.3). Date of birth is counted back from `AGE_ON`.
3. Height: `gauss(ROLE_HEIGHT[role].mean + level.height_shift, sd)`, clamped to the level's height range.
4. Ratings: `ROLE_MEANS[role] + level.skill_offset` (stamina also gets `level.stamina_offset`), spread as the league
   does (`RATING_SD`, `QUALITY_SHARE`), plus the league's height and age adjustments. Clamped to
   `1..NATURAL_CAP + level.skill_offset`.
5. Top speed: `gauss(ROLE_SPEED[role].mean * level.speed_mult, sd * level.speed_mult)` with the league's height and age
   terms, clamped to `SPEED_RANGE * level.speed_mult`. Acceleration: the league's formula, then `* level.accel_mult`,
   clamped to `ACCEL_RANGE * level.accel_mult`.
6. Bio: foot as the league; nationality from the competition's distribution.
7. Standouts: the league's `STANDOUTS` pairs, lifted within **each competition** (`STANDOUT_LIFT`, capped at
   `STANDOUT_CAP + level.skill_offset`), so every competition has players worth finding. No "star" is set outside
   England: Femi Toure stays the one rigged-by-ratings star (§2.10).

### 4.3 Level scales

The reference is the existing league (England semi-pro men). Its scales are the league module's constants, which were
tuned against Premier League bands: §10 says how far that can be claimed.

| Pool key | skill offset | stamina offset | top speed × | accel × | height shift (cm) | age range (mode) |
|---|---|---|---|---|---|---|
| semi_pro / senior / men | 0 | 0 | 1.00 | 1.00 | 0 | 17-35 (26; GK/CB 28) |
| college / college / men | −3 | 0 | 0.99 | 0.99 | 0 | 18-23 (20) |
| amateur / senior / men | −8 | −4 | 0.97 | 0.97 | 0 | 18-38 (27) |
| academy / U20 / men | −4 | 0 | 0.97 | 0.97 | 0 | 17-19 (18) |
| academy / U19 / men | −5 | 0 | 0.96 | 0.96 | −1 | 16-18 (17) |
| academy / U18 / men | −6 | 0 | 0.95 | 0.95 | −2 | 16-17 (16) |
| academy / U17 / men | −9 | −2 | 0.92 | 0.92 | −3 | 15-16 (16) |
| semi_pro / senior / women | −3 | −3 | 0.83 | 0.90 | −12 | 17-35 (25) |
| college / college / women | −4 | −3 | 0.82 | 0.90 | −12 | 18-23 (20) |

Where each number comes from, honestly:

- **Top speed, U17 men, × 0.92: sourced.** Highly trained U17 players reached a maximal sprinting speed of about
  30.7 km/h (U13 about 25.2) in a study of peak match running speed in U13-U17 players [S6]. The league's mean outfield
  top speed is 33.4 km/h (measured on `league.json`, 96 outfielders); 30.7 / 33.4 ≈ 0.92. Peak **match** speed in U17 was 26.8 ± 1.9 km/h [S5]; that
  is the band in §10.
- **Top speed, U18-U20, × 0.95 / 0.96 / 0.97: interpolated.** Regista's assumption between the sourced U17 figure and
  seniors. The direction is sourced: sprint qualities rise with age and maturation [S7], and match running output
  rises with age, U13 to U18 [S8].
- **Top speed, women, × 0.82-0.83: sourced.** High-level American female players' mean peak sprint speed was
  27.3 ± 1.4 km/h, with maxima above 30 [S3]. 27.3 / 33.4 ≈ 0.82, and the scaled outfield range (24.4-31.0 km/h)
  contains the reported maxima. The acceleration multiplier (0.90) is **Regista's assumption**: no published band was
  read.
- **Stamina, women, −3: direction sourced.** Only the women showed a second-half drop in distance at selected speeds
  in the UEFA Champions League comparison [S1], and every physical variable fell between halves in women's
  internationals [S2]. The size is Regista's.
- **Skill offset, women, −3/−4: direction sourced.** At UEFA Champions League level women completed fewer passes and
  lost the ball more often, with no difference in touches, possession time or duels won [S1]. The size is Regista's.
  Default pools never compare across genders.
- **Skill offsets for college, amateur and academy: Regista's definition of the levels.** No published source can put
  a number on "an amateur is N rating points below a semi-pro". The directions are sourced where possible: amateurs
  completed fewer passes and sprinted less than professionals in small-sided games [S10]; higher-standard players
  sprint more in Norway's three standards [S9]. The offsets are stated as assumptions in the docs and in this table.
- **Amateur top speed × 0.97, college × 0.99, amateur stamina −4: Regista's assumptions.** No published band was read.
  In the Norwegian study high-speed running was similar across standards, while sprinting was higher at the top [S9].
- **Heights: Regista's assumptions.** No football height band was read for women or youth.

**What the offsets do in the generator** (skill z is absolute, so these are the model's effects, measured in §10
rather than assumed). For amateur men (z ≈ −1.14) the weights in `LEAGUE` give roughly: shots from inside 16 m
× 0.81 (`shot_drive`), carries × 0.71 (`carry_drive`), take-on attempts × 0.81 (`take_on_drive`), nutmegs and skills
× 0.75 (`flourish`), through balls × 0.71 (`through_vision`), fouls × 1.26 (`foul_discipline`), dispossessions
× 1.08 (`lose_*`), pass completion about −0.09 log-odds (passer 0.22 against defender 0.14), and goals per shot about
+0.11 log-odds (keeper 0.16 against finisher 0.06). Head-to-head outcomes (take-on success, aerial duels) cancel
between two sides of the same level. The realism report shows each of these by level. Where the sources give a
direction (women and amateurs complete fewer passes and lose the ball more), it is an order check.

---

## 5. The generator change (the only one)

### 5.1 What

`TEAM_STYLE` re-centred per competition. In `_team_style`, the centre becomes `centre + team.style_offset`, where
`style_offset` is an optional team-spec key (a float), copied by `_team_specs` and held on `Team`. When the key is
absent or 0, the old expression runs unchanged (a branch, not an added `+ 0.0`).

`regista.catalogue.store.generate_kwargs_catalogue(comp, fixture)` calls `regista.season.league.generate_kwargs` and
then sets `teams[i]["style_offset"] = comp["level"]["skill_offset"]` when it is non-zero (the style ratings are the
skill ratings, so the offset is the same). England's kwargs never carry the key.

### 5.2 Why only this

- Style is relative by definition: "keeps the ball more than the other sides". With an absolute centre, every amateur
  and U17 side sits at the clamp (−2.5 for both `keep` and `press`), so all sides in a competition play alike, and
  possession and PPDA collapse to one value.
- Everything else stays absolute (D2), so levels differ through the ratings. A volume re-centring (shots, carries and
  take-ons relative to the competition, outcomes absolute) was considered and **is not built**. It is the fallback if
  the §10 measurement shows a level's volumes outside anything in football (for example shots per 90 far below every
  source). That would be a decision for Zaid, with numbers in hand.

### 5.3 Byte identity, versions, and what must be re-stamped

- No `style_offset`, no change: `tests/test_backcompat.py` (no attributes) and `SEASON_PINS` (league mode, England)
  must pass untouched.
- **Do not bump `LEAGUE_GENERATOR_VERSION`.** It is written into every league stream's header, so a bump moves all 30
  England pins. The change is inert without the new key; the comment block at the top of `generator.py` records it as
  "catalogue: optional style_offset (inert without it)".
- Editing `generator.py` changes `code_fingerprint(BUILT_BY)`. So every England folder rebuilds once, to the same
  bytes (the pins check this), and `reliability.league_fingerprint` changes, so **`reliability.json` reads as stale**.
  Re-stamp it with `python -m regista.season.reliability` (6 seasons, slow). The numbers must come out identical: the
  builder diffs everything except the fingerprint and says so in the phase report. Otherwise `/api/metrics`'s
  `season.reliability.stale` would change, a response change.

---

## 6. Building and caching the matches

- `regista.catalogue.build.build_catalogue(cat, workers=None)`: collect every stale fixture of every non-England
  competition, then **one** spawn-context process pool, as `build_all` does (the `if __name__ == "__main__"` rule
  applies), then `materialise` each in place. England stays `regista.season.build.build_all` on `SEASON_ROOT`.
- **Manifest** of a catalogue match: today's keys, plus `"collection": "catalogue"`, `competition_id`, `competition`,
  `country`, `tier`, `age_group`, `gender`, `uploader` and `camera`. The title is "Weserland-Liga, matchday 3:
  Hollenburg 2–1 Vorstadt". The subtitle names the competition and says the match is a synthetic uploaded match.
  Implemented through `materialise(..., manifest_extra=..., title_fn=...)`; the defaults give today's manifest
  exactly.
- **Fingerprint**: today's `fingerprint(league, fixture)`. It already covers the kwargs (squads, ratings,
  `style_offset`) and the code source.
- **Cost**: 60 matches × about 1.3 s ≈ 80 s on one core, about 10 s on 10 cores. About 1.2 MB of events and clips per
  match without tracks (≈ 70 MB). Tracks (15 MB) only when a video is asked for (`ensure_tracks`).
- **Docker**: `COPY data/catalogue/catalogue.json data/catalogue/competitions ./data/catalogue/…`, then
  `RUN python -m regista.catalogue build` after the season build, so a fresh revision starts warm. `.dockerignore` and
  `.gitignore` add `data/catalogue/matches/`. `tests/test_packaging.py` gains a guard that the catalogue files are not
  docker-ignored.
- **The Clip view**: `api._season_match_dir(match_id)`: `rl_…` as today; `cm_…` goes through
  `catalogue.store.resolve_match`, then `ensure_tracks(comp, fx, CATALOGUE_ROOT)`. `_is_season_match` does the same
  without building. So `/api/matches/cm_…/clips`, `.mp4`, `/recap` and the rest work for catalogue matches. They are
  not added to `list_matches` (which lists `DATA_ROOT` only), so the Product's match list is unchanged.
- **Warm-up**: after `warm_metrics`, `warm_catalogue()` builds the catalogue and its metrics in the background
  (`REGISTA_CATALOGUE_WARM`, default 1). The new endpoints report `warm` like `/api/season`.

---

## 7. The engine: pools within level

### 7.1 Structure

```
CatalogueMetrics
  competitions: {competition_id: SeasonMetrics}   # England: the same object load_metrics returns (identical numbers)
  rows: {(competition_id, global_id): PlayerSeason}  # player-competition rows (a career player has two)
  pools: {(scope_key, metric, position): sorted rank values}
```

- **England**: `load_metrics(SEASON_LEAGUE, SEASON_ROOT)` as today: its own fitted xT, its rules, its numbers.
- **Every other competition**: `SeasonMetrics.from_streams(comp, streams, xt=england.xt, min_minutes_floor=45.0,
  min_pool=5)` (new optional arguments; defaults reproduce today's behaviour exactly).
- **Profiles side**: `Season.build(comp, root, min_minutes_floor=45.0)` per competition for moments, touch grids,
  match lists and the results of uploaded matches. No claims or uploads outside England in this round.

### 7.2 Qualifying minutes and ratio minimums (per competition)

- `min_minutes(comp) = max(45.0, qualifying_minutes(max club minutes in comp))`. England: max(45, 100.5) = 100.5, the
  same as today. A club with one uploaded match (about 30 minutes) leaves its players unqualified: that is honest, as
  there is not enough footage. The 45-minute floor (one and a half synthetic matches) is Regista's rule and is stated
  in every response's pool rule.
- Ratio minimums: `thresholds(max club minutes in comp)` as today, per competition.
- A row qualifies for a metric under its **own competition's** rule. A level pool is the union of qualified rows from
  its competitions.

### 7.3 Percentiles

- `fbref_percentile` over the pool's `rank_value`s, inverted where lower is better: the same rule as today.
- `MIN_POOL = 5`: a smaller pool gives `percentile: null` with `pool.reason: "fewer than 5 qualified peers"`.
  `SMALL_POOL = 15`: `pool.small: true`.
- Scope keys:
  - `level`: `(tier, age_group, gender)` and the row's position. **This is the default** on catalogue endpoints.
  - `competition`: `competition_id` and position. For England this is today's percentile, exactly.
  - `all`: `gender` and position. Every tier and age group within one gender, on request only. Responses add a
    `warning` that levels differ.
- Positions are the league's GK, DF, MF and FW. `role` (FB, CB, …) stays a filter, not a pool, because the pools are
  already small.

### 7.4 What every number carries

```json
{"value": 0.42, "percentile": 71, "qualified": true, "total": 3.0, "noisy": false, "evidence_total": 3,
 "pool": {"scope": "level", "tier": "semi_pro", "age_group": "senior", "gender": "men", "position": "FW", "size": 31,
          "small": false, "min_size": 5, "competitions": ["co_eng_sp_men", "co_ger_sp_men"], "reason": null},
 "sample": {"minutes": 274.0, "appearances": 10, "qualifying_minutes": 100.5, "competition_id": "co_eng_sp_men"}}
```

- `noisy`: the England split-half table (`reliability.json`) applied to every competition, labelled
  `"reliability": "measured on England semi-pro men (one season of ten 30-minute matches a club); sparser competitions are noisier still"`.
  A per-competition reliability is not computed: 3-8 matches cannot be split in halves meaningfully.
- Evidence: `SeasonMetrics.evidence` per row, unchanged. Links open the Clip view at the `cm_…` match.

### 7.5 Careers in the engine

A career player has one row per competition. The catalogue player view lists both rows, each with its own pools.
There is **no merged per-90 across levels**: rates from two levels would mix pools. The career block states minutes per
competition and links both.

### 7.6 Hidden ratings

`CatalogueMetrics` and every new view read only the event streams, the physical records and the public bio (`bio()`,
`people()` without `attributes`), as the league engine does.

---

## 8. Endpoints

### 8.1 Unchanged

Every existing endpoint, called as today (no new parameter), returns the same JSON as on `main`, apart from
non-deterministic fields (`warm`, timings). A snapshot test records hashes on `main` before any code change (§11).
This covers `/api/season`, `/api/players`, `/api/players/{id}`, `/moments`, `/reel.mp4`, `/api/compare`,
`/api/scout/ask` (rules), `/api/metrics`, `/api/terminal/{screen,rank,scatter}`,
`/api/players/{id}/{metrics,form,similar,shots,heatmap}`, `/api/teams`, `/api/teams/{id}/{style,shots}`, the MCP tools
`search_players`, `get_profile` and `compare_players`, and Fabric `push`/`check`.

For a non-England player id, `/api/players/{gid}` keeps answering 404. Its message gains a hint (the detail text
changes, the shape does not): "a catalogue player: GET /api/catalogue/players/{gid}".

### 8.2 Optional parameters on existing endpoints

- `/api/season?competition=co_…`: the same keys for that competition (`league` is its name). For a sparse
  competition, `table` holds the results of uploaded matches only, and `table_note` says "uploaded matches only, not a
  league table". `rounds` lists matchdays that have uploads. `sample` is that competition's.
- `/api/players?competition=co_…`: cards from that competition's `Season`, percentiles in competition scope.
- Terminal endpoints `?competition=co_…`: that competition's `SeasonMetrics` (competition scope, the 45-minute floor,
  `MIN_POOL` 5), in today's shapes. Optional `scope=level|all` adds `pool` to each cell, and `season` gains `scope`.
  Without parameters: England, unchanged.

### 8.3 New endpoints (`catalogue_api.py`, all GET, public, read-only)

**`GET /api/catalogue`**: the catalogue.
```json
{"catalogue": "Regista catalogue", "season": "2026/27",
 "competitions": [{"competition_id": "co_ger_sp_men", "name": "Weserland-Liga", "country": "Germany", "region": "Lower Saxony",
                   "tier": "semi_pro", "age_group": "senior", "gender": "men", "format": "11-a-side", "season": "2026/27",
                   "teams": 6, "players": 108, "uploaded_matches": 8, "coverage": "sparse",
                   "cameras": {"tripod": 4, "broadcast": 2, "phone": 1, "drone": 1}, "uploaders": {"team": 6, "player": 2}}],
 "levels": {"tiers": [{"key": "semi_pro", "label": "Semi-pro"}], "age_groups": [...], "genders": [...],
            "pools": [{"tier": "semi_pro", "age_group": "senior", "gender": "men", "competitions": ["co_eng_sp_men", "co_ger_sp_men"]}]},
 "careers": [{"global_id": "pl_…", "name": "…", "competitions": ["co_esp_u19", "co_esp_am_men"]}],
 "totals": {"competitions": 14, "countries": 10, "clubs": 66, "players": 1183, "matches": 90},
 "warm": {"state": "ready", "error": null}, "synthetic": true, "note": "…"}
```

**`GET /api/competitions/{competition_id}`**: one competition (`competition_id` matches `^co_[a-z0-9_]{1,40}$`).
```json
{"competition_id": "...", "name": "...", "country": "...", "region": "...", "tier": "...", "age_group": "...", "gender": "...",
 "format": "11-a-side", "season": "2026/27", "coverage": "sparse",
 "clubs": [{"club_id": "...", "name": "...", "short_name": "...", "city": "...", "kit": {...}, "ground": "...",
            "squad": [{"global_id": "...", "name": "...", "kit_number": 9, "position": "FW", "starter": true, "age": 19,
                       "date_of_birth": "...", "height_cm": 181, "preferred_foot": "right", "nationality": "Germany",
                       "career": ["co_usa_col_men"]}]}],
 "matches": [{"match_id": "cm_gsp_03_hbg_vor", "round": 3, "date": "...", "home": "...", "away": "...", "home_name": "...",
              "away_name": "...", "score": {"t_home": 2, "t_away": 1}, "title": "...", "camera": "tripod",
              "uploader": {"type": "player", "global_id": "...", "name": "...", "club_id": "..."}, "clip_view": "/?match=cm_…"}],
 "results": [{"club_id": "...", "played": 3, "won": 2, "drawn": 0, "lost": 1, "goals_for": 5, "goals_against": 3}],
 "results_note": "uploaded matches only, not a league table",
 "table": null,
 "sample": {"matches_uploaded": 8, "club_matches": {"cl_…": 3}, "qualifying_minutes": 45.0, "note": "..."},
 "synthetic": true, "note": "..."}
```
For England, `table` is `Season.table` (today's) and `results_note` is null.

**`GET /api/competitions/{competition_id}/players`**: that competition's cards, with metric columns (like `screen`,
competition scope by default, `scope=level|all` accepted).

**`GET /api/catalogue/players`**: the cross-country screen. Filters: `tier`, `age_group`, `gender`, `country`,
`competition`, `position`, `role`, `q`, `min_minutes`, `age_min`, `age_max`, `foot`, `camera` (players seen on that
camera type), `career` (true: only players in two competitions). Plus `metrics`, `sort`, `order`, `scope`
(default `level`), `limit`, `offset`. Each row is a player-competition row.
```json
{"columns": [{"key": "npxg", "...": "describe()"}], "scope": "level", "sort": "npxg", "total": 412, "offset": 0,
 "players": [{"global_id": "...", "name": "...", "competition_id": "...", "competition": "...", "country": "...",
              "tier": "...", "age_group": "...", "gender": "...", "club_id": "...", "club": "...", "position": "FW",
              "role": "ST", "age": 19, "nationality": "...", "minutes": 88.0, "appearances": 3, "qualified": true,
              "career": false, "profile_url": "/players/pl_…",
              "values": {"npxg": {"value": 0.61, "percentile": 88, "pool": {"...": "..."}, "sample": {"...": "..."}}}}],
 "pools": [{"scope": "level", "tier": "...", "age_group": "...", "gender": "...", "position": "FW", "size": 12, "small": true}],
 "pool_rule": "FBref's percentile among qualified peers of the same tier, age group, gender and position …",
 "synthetic": true, "note": "..."}
```

**`GET /api/catalogue/players/{gid}`**: the player across the catalogue.
```json
{"global_id": "...", "name": "...", "bio": {"age": 18, "height_cm": 179, "preferred_foot": "left", "nationality": "Spain"},
 "career": [{"competition_id": "co_esp_u19", "competition": "...", "country": "Spain", "tier": "academy", "age_group": "U19",
             "gender": "men", "club_id": "...", "club": "...", "kit_number": 9, "position": "FW", "role": "ST",
             "appearances": 3, "minutes": 84.0, "first_match": "...", "last_match": "..."}],
 "rows": [{"competition_id": "...", "scope": "level", "metrics": {"goals": {"value": 0.0, "percentile": null, "pool": {"...": "..."}}}}],
 "moments": [{"match_id": "cm_…", "clip_id": "...", "title": "...", "watchability": 0.8, "video_url": "..."}],
 "summary": {"text": "...", "sentences": [], "model": "rules"},
 "synthetic": true, "note": "..."}
```
Query parameters: `scope` (default `level`), `metrics` (default: the position's `DEFAULT_COLUMNS`), `evidence=KEY`
with `competition=` (one metric's evidence, paged as in `/api/players/{id}/metrics`).

**`GET /api/catalogue/rank?metric=KEY&…filters…&scope=`**: one metric's leaderboard, ranked within the filter. Every
row carries its own pool. With mixed levels, the response adds `"warning": "rows from different levels: read each percentile against its own pool"`.

**`GET /api/catalogue/compare?ids=pl_a,pl_b[,pl_c][&competitions=co_x,co_y,…]&scope=`**: two or three players, each on
one row (by default the row with the most minutes; `competitions` picks rows in the order of `ids`). Response:
`{"players": [...rows with values...], "same_pool": bool, "warning": "…" | null}`.

**`GET /api/catalogue/matches?competition=&camera=&uploader_type=&country=&tier=`**: uploaded matches across the
catalogue, each as in `/api/competitions/{id}`'s `matches`.

### 8.4 MCP tools (added, existing ones untouched)

- `list_competitions()`: the `/api/catalogue` competitions and pools.
- `search_catalogue_players(tier, age_group, gender, country, competition, position, sort, scope, limit)`.
- `get_catalogue_player(player)`: by global id or name, without evidence lists.

They read `REGISTA_CATALOGUE` / `REGISTA_CATALOGUE_ROOT`. Whether the public Foundry Scout agent gets them
(`SCOUT_TOOLS`) is a decision for the UI round: not in this round. `tests/test_mcp.py`, `test_scout_agent.py` and
`cloud/smoke.py` expect them in the Regista server's list.

### 8.5 Never served

Hidden `attributes` (every rating key), the competition files' `level` block (offsets and multipliers relate to the
hidden ratings), and seeds of individual matches beyond what `manifest.generator` already shows today. One test walks
every new endpoint's JSON (and the optional-parameter variants) for any key in `ATTRIBUTE_KEYS`, `skill_offset`,
`speed_mult`, `accel_mult` or `stamina_offset`. It extends `test_ratings_never_appear_in_public_json`.

---

## 9. Back-compat and the pins: how each guarantee is kept and checked

| Guarantee | How it is kept | Checked by |
|---|---|---|
| `league.json` byte-identical | never written; the catalogue overlays it | new test: SHA-256 of `data/season/league.json` equals its `main` value (recorded in the test) |
| England's 30 fixtures | kwargs unchanged (no `style_offset`), generator inert without the key, version string unchanged | `SEASON_PINS` (`test_league_mode.py::test_the_committed_season_is_pinned` on Linux CI; `smoke.season_checks` in the image) |
| England names, ratings, bios; Femi Toure 5 league goals, two clear | `league.json` untouched | existing `test_attributes`, `test_league_mode::test_femi_toure_is_the_leagues_top_scorer` |
| `generate()` without attributes | inert change | `tests/test_backcompat.py` unchanged |
| New matches deterministic across platforms | league mode uses `detmath`; definition streams use `detmath.Random` | `CATALOGUE_PINS` for all 60 matches, in CI on Linux and in `smoke.catalogue_checks` |
| Existing endpoint responses | separate engines; optional parameters only | snapshot test (§11), recorded on `main` before the first change |
| `reliability.json` not stale | re-stamped after the generator edit, numbers identical | existing `test_reliability` fingerprint test, plus the builder's diff in the phase report |
| `summaries.json` still valid | `basis` unchanged for England | existing tests (`summary_for` returns the stored one) |
| Fabric unchanged | not touched | `tests/test_fabric.py` |

---

## 10. Realism plan per level

`python -m regista.synth.report --catalogue [--repeat 3] [--out docs/catalogue/realism.md]` measures each pool on
**measurement seasons**: the competition's full double round robin regenerated `repeat` times with measurement seeds
(§4.1). It never uses the sparse committed sample, which is too small for a verdict. It reports each level against the
kinds of checks below. A slow test runs it and asserts the verdict lines.

Kinds of check:
- **band**: a published band read for this level → pass/fail.
- **reference**: a band from a higher level shown beside the number, **no verdict** (an upper reference).
- **order**: a sourced direction between levels, checked on the pooled measurements (pass/fail).
- **none**: "no published band": the number is shown, nothing is claimed.

| Level | Event rates | Physical | Notes |
|---|---|---|---|
| semi_pro / senior / men, England | the existing `--league` report, unchanged: Premier League bands, now labelled "Premier League bands, an upper reference for semi-pro football: the generator was tuned to them" | same | No semi-pro band was read. The PL is the only source, and the claim is capped at "tuned to PL bands". |
| semi_pro / senior / men, Germany | PL bands as **reference** (same rating scale as England, so expect them to hold); verdicts not claimed for semi-pro | PL / World Cup bands as reference | |
| college / college / men | PL bands as reference | NCAA Division I: about 9,367 m per match [S4], reference only (NCAA's re-entry substitutions make it per match, not per 90) | |
| college / college / women | none | women's references: total distance per 90 9.5-11.0 km from positional means in women's internationals [S2]; teams 103.3 ± 4.4 km per match at the 2023 Women's World Cup [S11]; season top speed within 24.4-31.0 km/h [S3] | All are elite references (upper), no verdict |
| semi_pro / senior / women | none | as college women | |
| amateur / senior / men | none | none | order: sprint distance per 90 below semi-pro [S9]; pass completion below semi-pro [S10] |
| academy / U20, U19, U18 | none | none | order: peak speed mean and distance per 90 rise U17 < U18 < U19 < U20 < senior [S5, S6, S8] |
| academy / U17 / men | none | **band**: mean peak match speed of outfielders (the engine's `peak_speed_mean`) in 24.9-28.7 km/h, 26.8 ± 1.9 [S5] | the one sourced band below senior level: highly trained academy players, which fits an academy U17 |
| women vs men (any tier) | order: pass completion lower, dispossessions higher in women's pools [S1] | order: distance at ≥ 20 km/h per 90 lower in women's pools [S1, S2]; second-half drop in high-intensity distance [S1] | |

The physical metrics keep **one definition everywhere**: FIFA's men's zones, ≥ 20 and ≥ 25 km/h. Women's tournaments
use 19 and 23 km/h [S11], so women's sprint counts here are on the men's thresholds and are not compared with
women's-threshold figures. Total distance and top speed do not depend on thresholds and are the ones referenced.

If a level misses its band or order check, the builder reports it with the numbers and does not retune silently. A
retune is a design change for review (a level's offsets, or the §5.2 fallback).

---

## 11. Test plan

All tests set `REGISTA_DOTENV=""` (tests/conftest.py already does), never reach Azure, and never write to the live app.
Linux CI rules: no long command-line arguments (feed JSON through files or stdin: the 128 KB failure), spawn-context
process pools only behind `__main__`, no reliance on macOS-only paths, and every float that decides an outcome goes
through `detmath`.

**Before the first code change (phase 0):** record the snapshot on `main`'s code in this branch. Hash the canonical JSON
(`sort_keys`, with `warm` and timing fields removed) of: `/api/season`, `/api/players` (default and
`sort=goals&position=FW`), `/api/players/pl_bro_09`, `/api/players/pl_bro_09/moments`, `/api/compare?ids=pl_bro_09,pl_ash_09`,
`/api/scout/ask` (rules, "who scored the most goals"), `/api/metrics`, `/api/terminal/screen` (default and `position=FW`),
`/api/terminal/rank?metric=npxg`, `/api/terminal/scatter?x=npxg&y=xa`,
`/api/players/pl_bro_09/{metrics,form,similar,shots,heatmap}`, `/api/teams`, `/api/teams/cl_brookfield/style`, and the
MCP tools' outputs for the same questions. Store them in `tests/data/catalogue_backcompat.json`, keyed by call.

Quick suite (`python3 -m pytest -q`):

1. `test_catalogue_backcompat.py`: `league.json` SHA-256; the snapshot hashes; `SEASON_PINS` unchanged; non-England
   gid on `/api/players/{gid}` still 404.
2. `test_catalogue_define.py`: the committed catalogue is what `new_catalogue()` writes (byte-equal); 14 competitions
   with the §2.2 labels; no `professional` tier; 4-6 teams; 18 per squad in 4-3-3 numbering; every seed unique; ids
   match the patterns; short names unique; names unique and none equals a league name; kit distinctness per
   competition; ages inside each level's range; ratings and physical inside each level's clamps; England absent from
   competition files.
3. `test_catalogue_levels.py`: on the committed definitions, level means order as designed (women's mean top speed
   below men's of the same tier; U17 < U18 < U19 < U20 < senior; amateur skill mean below semi-pro); standouts per
   competition; no star outside England.
4. `test_catalogue_careers.py`: five careers, same gid, same bio and ratings in both squads, same role, same gender;
   minutes in both competitions; no two matches on one date.
5. `test_catalogue_coverage.py`: 60 uploads; 3-8 per competition; every club appears at least once; uploader is a
   squad member who played, or one of the two clubs; camera in the four values; England overlay covers all 30 fixtures.
6. `test_catalogue_build.py`: a catalogue match validates against the schema (0.2.0, league mode); its manifest has the
   catalogue keys; rebuild is deterministic; tracks equal a fresh `generate`; `style_offset` reaches team style
   (possession spread within an amateur competition is wider than with the key removed, measured on one match pair);
   a team spec without the key generates exactly what it did.
7. `test_catalogue_pins.py`: all 60 `CATALOGUE_PINS` (session-scoped build in a temp root; parallel). If it takes over
   about 60 s on CI, a one-match-per-tier subset stays quick and the full set moves to `-m slow` (and the smoke test
   in the image still checks all 60).
8. `test_catalogue_metrics.py`: England's competition-scope cells equal `load_metrics`' for every metric and player;
   a level pool is the union of its competitions' qualified rows; `MIN_POOL` gives null with a reason; `small` below
   15; `scope=all` keeps gender; percentiles by FBref's rule (a hand-computed pool); career rows separate; the
   45-minute floor; non-England xT is England's grid; every cell has `pool` and `sample`.
9. `test_catalogue_api.py`: shapes of every §8.3 endpoint; filters; 400 for bad ids; 404 for unknown competitions and
   players; optional `competition=` on `/api/season`, `/api/players` and terminal endpoints returns today's keys; a
   `cm_` match opens in `/api/matches/{id}/clips` and its recap.
10. `test_catalogue_privacy.py`: no hidden rating key, `level` block or scale key in any new or optional-parameter
    response (walks the JSON).
11. `test_mcp.py` / `test_scout_agent.py` / `test_smoke.py`: the new tools listed and answering; the existing three
    unchanged.
12. `test_packaging.py`: catalogue files shipped, `data/catalogue/matches/` ignored.

Slow suite (`python3 -m pytest -q -m slow`, run because the generator changes):

13. `reliability.json` recomputed equals the committed numbers (existing slow test, with the new fingerprint).
14. `--catalogue` realism report: the U17 band, every order check, and the England `--league` verdicts unchanged.
15. The full 60-match pin set, if moved here by item 7.

---

## 12. Phases for the builders (commit each; reports in `docs/catalogue/build/`)

Every commit message ends with a blank line, then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The
`docs/catalogue/build/` folder matches `.gitignore`'s `build/`, so reports are added with `git add -f`.

| Phase | Work | Done when | Report |
|---|---|---|---|
| 0 | Record the back-compat snapshot on unchanged code | `tests/data/catalogue_backcompat.json` committed; test green | `phase0-snapshot.md` |
| 1 | `taxonomy.py`, `names.py`, `define.py`, `store.py`; write `data/catalogue/`; tests 2-5 and the `league.json` hash | committed files regenerate byte-equal; quick suite green | `phase1-data.md` (competitions, sizes, careers, coverage tables) |
| 2 | Generator `style_offset`; `generate_kwargs_catalogue`; `build.py` (`manifest_extra`); `catalogue/build.py`; pins recorded; `api._season_match_dir` for `cm_`; Dockerfile, ignores, smoke; **re-stamp `reliability.json`** (diff: numbers identical) | tests 1, 6, 7, 12 green; `SEASON_PINS` and back-compat untouched; slow test 13 green | `phase2-build.md` (timings, pins, the reliability diff) |
| 3 | `SeasonMetrics`/`Season` optional arguments; `catalogue/metrics.py`, `catalogue/profiles.py` | test 8 green; England equality holds | `phase3-engine.md` (pool sizes per level and position, small pools) |
| 4 | `catalogue_api.py`; optional `competition=`/`scope=`; MCP tools; warm-up | tests 9-11 green; snapshot unchanged | `phase4-api.md` (endpoint list with one real response each, trimmed) |
| 5 | `report.py --catalogue`; `docs/catalogue/realism.md`; `data/synthetic/README.md` "Catalogue"; CLAUDE.md §2.11 and §3.0 lines; full quick and slow suites | both suites green on the Mac; CI green on Linux | `phase5-realism.md` (every check, pass or fail, with numbers) |

Then the PR (not merged until Zaid says so).

---

## 13. Risks and open questions

- **Volumes at low levels** (§4.3): absolute skill z means fewer carries, take-ons and through balls at amateur and
  U17 level. If §10 shows a level outside anything football produces, the §5.2 fallback is Zaid's call.
- **Small pools**: sparse competitions make many single-competition pools `small`, and goalkeeper pools often
  fall under 5 (null percentiles). That is honest, and the UI round must show it well.
- **Re-stamping `reliability.json`** takes a slow run (six seasons). Budget for it in phase 2.
- **Name collisions with real clubs or leagues**: invented names can still collide by accident. The builders check
  the display names and keep the ids stable if a name changes.
- **Docker build time** grows by the catalogue build (about 10-80 s depending on the build machine's cores).
- **Camera type is a label only** (§2.5); the pitch must not imply that phone or drone footage was processed.
- Open for Zaid (not blocking): whether the public Scout agent gets the catalogue tools in this round, and whether the
  Player view's uploads may come from catalogue clubs (today England only).

---

## 14. Sources

Read 2026-10-25 (abstracts and publisher or repository pages; full texts not read unless stated). The builders quote
only what these say and keep the citation with the number.

- [S1] Bradley PS, Dellal A, Mohr M, Castellano J, Wilkie A. Gender differences in match performance characteristics of
  soccer players competing in the UEFA Champions League. *Hum Mov Sci* 2014;33:159-171.
  https://pubmed.ncbi.nlm.nih.gov/24139663/ : men covered more total distance (ES 0.5), and the gap grew at higher
  speeds; only women showed a second-half drop at selected speeds; women lost the ball more often and completed fewer
  passes (ES 0.5-0.9); no difference in touches, possession time or duels won.
- [S2] Datson N, Drust B, Weston M, Jarman IH, Lisboa PJ, Gregson W. Match physical performance of elite female soccer
  players during international competition. *J Strength Cond Res* 2017;31(9):2379-2387. doi:10.1519/JSC.0000000000001575.
  https://eprints.chi.ac.uk/id/eprint/3511/ : central midfielders about 10,985 m total, central defenders about
  9,489 m; physical output fell between halves at every position.
- [S3] Vescovi JD. Sprint speed characteristics of high-level American female soccer players: Female Athletes in Motion
  (FAiM) study. 2012. https://lida.sport-iat.de/dfb/Record/4026390 : mean peak speed 27.3 ± 1.4 km/h (sprint test),
  maxima above 30.0 km/h.
- [S4] Match demands of National Collegiate Athletic Association Division I men's soccer. *J Strength Cond Res* 2018.
  https://lida.sport-iat.de/ta/Record/4050577 : about 9,367 m per match (18 players, 24 matches). The author list was
  not confirmed in the abstract read: cite it by title.
- [S5] Peak match speed and maximal sprinting speed in young soccer players: effect of age and playing position. *Int J
  Sports Physiol Perform* 2015;10(7):888-896 : peak match speed 23.4 ± 1.8 km/h (U13) and 26.8 ± 1.9 km/h (U17),
  180 male youth players. The author list was not confirmed in the result read: verify it before quoting authors.
- [S6] Age-related differences in peak match running speed in highly-trained young soccer players.
  https://lida.sport-iat.de/ta/Record/4029276 : maximal sprinting speed about 25.2 km/h (U13) to 30.7 km/h (U17);
  faster players reached higher match speeds.
- [S7] Mendez-Villanueva A, et al. Age-related differences in acceleration, maximum running speed, and repeated-sprint
  performance in young soccer players. *J Sports Sci* 2011;29(5):477-484. doi:10.1080/02640414.2010.536248 : the
  oldest group was fastest; the differences were explained by maturation.
- [S8] Buchheit M, Mendez-Villanueva A, Simpson BM, Bourdon PC. Match running performance and fitness in youth soccer.
  *Int J Sports Med* 2010;31(11):818-825 : match running output rose with age (U13-U18) and varied by position.
- [S9] Match running performance on three different competitive standards in Norwegian soccer.
  https://lida.sport-iat.de/ta/Record/4059033 : level-1 professionals sprinted 61% and 51% more than level-2
  professionals and level-4 amateurs; high-speed running was similar across levels.
- [S10] Professional vs amateur players in small-sided games (amateurs: less sprinting and high-intensity running,
  lower pass success, higher perceived effort), as summarised in https://pmc.ncbi.nlm.nih.gov/articles/PMC6815094.
  A training format, not full matches: used for direction only. Confirm the exact paper before quoting it.
- [S11] FIFA Training Centre, FIFA Women's World Cup 2023 physical analysis, part 2: setting physical benchmarks across
  teams.
  https://www.fifatrainingcentre.com/en/game/tournaments/fifa-womens-world-cup/2023/post-tournament-analysis/physical-analysis/part-2-setting-physical-benchmarks-across-teams.php
  : teams 103.3 ± 4.4 km per match; 6.7 ± 0.6 km above 19.0 km/h; 1.9 ± 0.3 km above 23.0 km/h (women's zones).

The Premier League and World Cup bands already in `regista.synth.report` keep their own cited sources and are used
for England as today, and as references only for Germany semi-pro and college men (§10).
