# The catalogue: the API (phase 4)

Branch `feature/catalogue`, 2026-10-25. This is phase 4 of `docs/catalogue/build/design.md` (§8): the catalogue's 14
competitions served over HTTP and MCP. Everything here reads; nothing writes to the live app, Azure or Fabric. The
examples below are real responses on the committed catalogue, trimmed (`…` marks cut fields or list items).

## What changed

| File | Change |
|---|---|
| `src/regista/catalogue_api.py` (new) | The router with the new endpoints, the shared input checks (`where`, `scope_param`), the catalogue warm-up, and the catalogue-mode answers the existing endpoints call. |
| `src/regista/catalogue/tools.py` (new) | The three MCP tool bodies and the competition summary the API shares. |
| `src/regista/catalogue/profiles.py` | Additive: `use_minutes`, `scope_competitions`, `stat_pool`, `stat_cell`. These give a profile stat (the `/api/players` cards' headline) a percentile pooled by scope. |
| `src/regista/season_api.py` | Optional `competition=` on `/api/season`; optional catalogue filters, `scope`/`pool` and `offset` on `/api/players`; optional `include=career` on `/api/players/{id}`; a hint in the 404 for a catalogue player; `warm_catalogue()` after `warm_metrics()`. |
| `src/regista/terminal_api.py` | Optional catalogue parameters on every terminal endpoint (below). The two rule strings moved into constants (`FORM_RULE`, `SIMILAR_RULE`) with the same text. The 404s for catalogue players and clubs gain a hint. |
| `src/regista/api.py` | Includes the catalogue router. |
| `src/regista/mcp_server.py` | Three new tools. The existing six player and clip tools are unchanged. |
| `src/regista/cloud/foundry.py`, `cloud/smoke.py` | The new tools are counted as Regista MCP tools in traces. The image smoke test expects them in the Regista server's list. |
| `tests/test_catalogue_api.py` (new), `tests/test_access.py` | 27 tests. 11 rows added to the access table, all `public` (reads only). |
| `CLAUDE.md` §3.0 | One entry for `catalogue_api.py` and `tools.py`. (§2.11 is phase 5.) |

**Back-compat.**
- `tests/test_catalogue_backcompat.py` is unchanged and still passes: 21 HTTP and 4 MCP responses recorded on `main`,
  hash for hash.
- Without the new parameters, every existing endpoint gives `main`'s answer.
- The Scout agent's public tool list (`SCOUT_TOOLS`) is unchanged. Whether the Foundry Scout agent gets the catalogue
  tools is the UI round's decision (design.md §8.4).

## The rules every endpoint follows

**Scopes.** `scope` (alias `pool`) is one of three values. Giving both with different values is a 422.
- `level`: the same tier, age group, gender and position. This is the default on every catalogue answer.
- `competition`: one competition. For England this gives today's numbers exactly (tested cell by cell against
  `/api/terminal/screen` and the `/api/players` cards).
- `all`: every tier and age group of one gender. Genders never mix. Answers in this scope carry a `warning`.

**What every number carries.**
- `pool`: scope, tier, age_group, gender, position, size, small (under 15), min_size, competitions, and reason (why
  there is no percentile).
- `sample`: competition, minutes, appearances, qualifying minutes, competition matches, club matches.
- Rows from more than one level carry `warning: "rows from different levels: read each percentile against its own pool"`.

**When an existing endpoint answers from the catalogue.**
- Only when the caller passes `competition`, `country`, `tier` (or its alias `level`), `age_group`, `gender`, or
  `scope`/`pool`.
- Without a competition filter, the selection stays **England semi-pro men** (the Regista League). So
  `/api/terminal/screen?scope=level` lists England's players with level percentiles (the England and Germany pool).
- The new `/api/catalogue/*` endpoints read the whole catalogue by default.

**Validation.**
- Ids match `^co_…$`, `^pl_…$` and `^cl_…$`. A malformed id is a 400.
- An unknown competition is a 404 when it is in the path and a 422 when it is a filter.
- `tier`/`level`, `age_group`, `gender`, `camera` and `uploader_type` are enums. Contradictory `tier` and `level` give a
  422. So does `age_min` above `age_max`.
- Unknown metrics, `limit` above 200, a negative `offset`, and `evidence_offset` without `evidence` are refused.
- An unknown country is not an error: it returns an empty list.

**Paging.**
- `offset` with `limit` (at most 200) on `/api/catalogue/players`, `/api/competitions/{id}/players`,
  `/api/catalogue/rank`, `/api/catalogue/matches`, and `/api/players` in catalogue mode. `total` counts every row.
- `/api/players` without catalogue parameters: without `offset` the response is today's, exactly (`total` is the number
  of cards returned, as it always was). With `offset` (0 included) it pages, `total` counts every card the filters keep,
  and the response adds `offset` (review A, round 1).
- **Ranking across levels (review B, round 1).** A list whose rows come from more than one level (`/api/catalogue/rank`,
  the sort of `/api/catalogue/players`, the MCP tool `search_catalogue_players`, and the terminal endpoints with
  catalogue parameters) ranks each row by its percentile within its own pool, best first, then rows from pools that are
  not small, then more minutes, then the value. Rows without a percentile follow, unranked. Within one level the order
  is by value, as before. `rank_by=pool|value` forces either; the response says `rank_by` and `rank_rule`. Men and women
  are never ranked together: a list holding both has one board per gender (`boards`, each row's `board`; ranks
  restart at 1 on each board).

**Never served.**
- Hidden ratings (`attributes`, every rating key) and level scales (`skill_offset`, `stamina_offset`, `speed_mult`,
  `accel_mult`, `height_shift`, `style_offset`, `age_range`).
- Match seeds.
- A test walks 30 payloads (every new endpoint, and every optional-parameter variant) and the MCP results for these
  keys.

**Camera type is a label.** Every response that lists cameras carries `camera_note`. Every match is rendered with the
same broadcast-style view, and the vision layer is measured only on that render.

**Cost.**
- The catalogue's engines are built once per process: about 3.6 s with the 60 matches on disk.
- A fresh process (CI) first builds the 60 matches in one spawn pool.
- On the app, `warm_catalogue()` runs in the background after the league's metrics (`REGISTA_CATALOGUE_WARM`,
  default 1). `/api/catalogue` and `/api/competitions` read only the committed files, so they answer at once.

## New endpoints

### `GET /api/catalogue`

The catalogue: every competition with its labels and upload counts, the levels and which competitions share a pool,
the careers, and the totals. It reads the committed files only.

```
GET /api/catalogue
{"catalogue": "Regista catalogue", "season": "2026/27",
 "competitions": [{"competition_id": "co_ger_sp_men", "name": "Weserland-Liga", "country": "Germany", "region": "Lower Saxony",
   "tier": "semi_pro", "age_group": "senior", "gender": "men", "format": "11-a-side", "season": "2026/27", "coverage": "sparse",
   "teams": 6, "players": 108, "uploaded_matches": 8, "cameras": {"tripod": 2, "broadcast": 3, "drone": 1, "phone": 2},
   "uploaders": {"player": 3, "team": 5}, "dates": ["2026-08-08", "2027-01-23"], "api_url": "/api/competitions/co_ger_sp_men"}, …],
 "levels": {"tiers": […], "age_groups": […], "genders": […],
            "pools": [{"tier": "semi_pro", "age_group": "senior", "gender": "men", "competitions": ["co_eng_sp_men", "co_ger_sp_men"]}, …]},
 "careers": [{"global_id": "pl_sot_09", "name": "Sergio Cruz", "competitions": ["co_esp_u19", "co_esp_am_men"],
              "clubs": ["cl_sotoalto", "cl_torrevalle"], "story": "an academy striker stepping up …", "api_url": "/api/catalogue/players/pl_sot_09"}, …],
 "totals": {"competitions": 14, "countries": 10, "clubs": 66, "players": 1183, "matches": 90},
 "camera_note": "Camera type is a label of the upload: …", "warm": {"state": "idle", "error": null}, "synthetic": true, "note": "…"}
```

### `GET /api/competitions`

Filters: `country` (any case), `tier` or `level`, `age_group`, `gender`, `competition`. Each item is shaped like
`/api/catalogue`'s competitions.

```
GET /api/competitions?country=Spain
{"competitions": [{"competition_id": "co_esp_am_men", …}, {"competition_id": "co_esp_u19", …}], "total": 2,
 "filters": {"country": "Spain"}, "levels": {…}, "camera_note": "…", "synthetic": true, "note": "…"}
```

### `GET /api/competitions/{competition_id}`

One competition:
- its labels;
- its clubs with squads (public bio only; `career` lists a player's other competition);
- its uploaded matches, each with the uploader (team, or player with a name), the camera and a Clip view link;
- `results`, the sample, and the level's pool sizes.

England's `table` is the Regista League's table and its `results_note` is null. Every other competition has
`table: null` and `results` of its uploaded matches only.

```
GET /api/competitions/co_ger_sp_men
{"competition_id": "co_ger_sp_men", "name": "Weserland-Liga", "country": "Germany", "region": "Lower Saxony", "tier": "semi_pro",
 "age_group": "senior", "gender": "men", "format": "11-a-side", "season": "2026/27", "coverage": "sparse",
 "clubs": [{"club_id": "cl_hollenburg", "name": "SV Hollenburg", "short_name": "HBG", "city": "Hollenburg", "ground": "…", "kit": {…},
            "squad": [{"global_id": "pl_hbg_01", "name": "Igor Almeida", "kit_number": 1, "position": "GK", "role": "GK", "starter": true,
                       "age": 31, "date_of_birth": "1994-10-27", "height_cm": 190, "preferred_foot": "right", "nationality": "Brazil",
                       "career": null}, …]}, …],
 "matches": [{"match_id": "cm_gsp_01_hbg_hsb", "round": 1, "date": "2026-08-08", "home": "cl_hollenburg", "away": "cl_haselbrock",
              "score": {"t_home": 0, "t_away": 0}, "title": "Weserland-Liga, matchday 1: SV Hollenburg 0–0 Eintracht Haselbrock",
              "uploader": {"type": "player", "global_id": "pl_hsb_08", "club_id": "cl_haselbrock", "club": "Eintracht Haselbrock",
                           "name": "Kai Neumann"},
              "camera": "tripod", "clip_view": "/?match=cm_gsp_01_hbg_hsb", "home_name": "SV Hollenburg", "away_name": "Eintracht Haselbrock"}, …],
 "results": [{"club_id": "cl_lindenmoor", "club": "TuS Lindenmoor", "short_name": "LMR", "played": 4, "won": 1, "drawn": 3, "lost": 0,
              "goals_for": 1, "goals_against": 0}, …],
 "results_note": "uploaded matches only, not a league table", "table": null,
 "sample": {"matches_uploaded": 8, "club_matches": {"cl_erlenhorst": 3, …, "cl_vorstadt": 1}, "qualifying_minutes": 45.0,
            "note": "Per-90s and percentiles rest on the uploaded matches only."},
 "level_pool": {"scope": "level", "label": "semi_pro/senior/men", "competitions": ["co_eng_sp_men", "co_ger_sp_men"],
                "positions": {"GK": {"size": 11, "small": true, "under_min": false}, "DF": {"size": 44, …}, …}, …},
 "camera_note": "…", "warm": {…}, "synthetic": true, "note": "…"}
```

### `GET /api/competitions/{competition_id}/players`

One competition's players with metric columns (default: the position's core set). Percentiles are in `scope`, `level`
by default. The other parameters are those of the screen below, minus the competition filters. `min_minutes` defaults
to the competition's qualifying minutes.

```
GET /api/competitions/co_ger_sp_men/players?position=FW&metrics=npxg&limit=1
{"columns": [{"key": "npxg", …, "reliability": {…}, "realism": {"level": "semi_pro/senior/men", "kind": "reference", …}}],
 "scope": "level", "sort": "npxg", "total": 15, "offset": 0,
 "players": [{"global_id": "pl_mvs_11", "name": "Leon Lehmann", "club": "VfL Mövenstedt", "competition_id": "co_ger_sp_men",
              "minutes": 52.9, "qualified": true, "profile_url": null, "api_url": "/api/catalogue/players/pl_mvs_11", …,
              "values": {"npxg": {"value": 0.52, "percentile": 92, "qualified": true, "total": 0.305, "peers": 33, "noisy": true,
                                  "evidence_total": 3,
                                  "pool": {"scope": "level", "tier": "semi_pro", "age_group": "senior", "gender": "men", "position": "FW",
                                           "size": 33, "small": false, "min_size": 5,
                                           "competitions": ["co_eng_sp_men", "co_ger_sp_men"], "reason": null},
                                  "sample": {"competition_id": "co_ger_sp_men", "minutes": 52.9, "appearances": 2,
                                             "qualifying_minutes": 45.0, "competition_matches": 8, "club_matches": 2}}}}],
 "pools": […], "pool_rule": "…", "reliability_note": "…", "warning": null, …}
```

### `GET /api/catalogue/players`

The cross-country screen. There is one row per player and competition, so a career player has two.
- **Filters:** `tier`/`level`, `age_group`, `gender`, `country`, `competition`, `position`, `role`, `club`, `q`,
  `min_minutes`, `age_min`, `age_max`, `foot`.
- **`camera`:** players with an appearance in a match filmed on that camera type.
- **`career=true`:** only players in two competitions.
- **Also:** `metrics`, `sort`, `order`, `scope`, `limit` and `offset`.

```
GET /api/catalogue/players?tier=academy&age_group=U19&position=FW&metrics=np_goals&sort=np_goals&limit=1
{"scope": "level", "sort": "np_goals", "order": null, "total": 13, "offset": 0, "limit": 1,
 "competitions": ["co_esp_u19", "co_mar_u19"], "warning": null, "filters": {"tier": "academy", "age_group": "U19"},
 "players": [{"global_id": "pl_pij_09", "name": "Alejandro Perez", "competition": "Liga Juvenil Levante Interior", "country": "Spain",
              "club": "Atlético Pinarejo Juvenil", "age": 18, "minutes": 58.7, "career": false, …,
              "values": {"np_goals": {"value": 1.53, "percentile": 96, "peers": 13, "noisy": true,
                                      "pool": {"scope": "level", "tier": "academy", "age_group": "U19", "gender": "men", "position": "FW",
                                               "size": 13, "small": true, "min_size": 5, "competitions": ["co_esp_u19", "co_mar_u19"],
                                               "reason": null}, "sample": {…}}}}],
 "pools": [{"scope": "level", "label": "academy/U19/men", "competitions": ["co_esp_u19", "co_mar_u19"],
            "positions": {"GK": {"size": 5, "small": true, "under_min": false}, …, "FW": {"size": 13, "small": true, "under_min": false}}}],
 "pool_rule": "…", "reliability_note": "…", "camera_note": null, "synthetic": true, "note": "…"}
```

### `GET /api/catalogue/players/{global_id}`

One player across the catalogue:
- the public bio, the career (every competition, even with 0 minutes), and what adds up (no merged per-90);
- one row per competition, with the metrics (default: the position's core set) and their pools, the touch map, and
  that competition's rules summary;
- the best moments across competitions.

`evidence=KEY` returns one number's evidence instead. `competition=` picks the row (default: the row with the most
minutes), and `evidence_offset` pages through it.

```
GET /api/catalogue/players/pl_sot_09?metrics=np_goals&moments=1
{"global_id": "pl_sot_09", "name": "Sergio Cruz", "bio": {"age": 17, "height_cm": 188, "preferred_foot": "both", "nationality": "Spain"},
 "career": [{"competition_id": "co_esp_u19", …, "minutes": 42.2, "qualified": false},
            {"competition_id": "co_esp_am_men", "competition": "Regional Preferente Levante Interior", "club": "CF Torrevalle",
             "kit_number": 9, "role": "ST", "appearances": 2, "minutes": 50.4, "qualified": true, "first_match": "2026-10-24",
             "last_match": "2026-11-14", "matches": ["cm_eam_03_tvl_ams", "cm_eam_04_rsc_tvl"], …}],
 "career_story": "a juvenil striker who, while still eligible for the juvenil, also plays for the senior amateur club his academy side is affiliated with, in the same territorial federation (Valencian Community)",
 "overall": {"competitions": 2, "competitions_played": 2, "appearances": 4, "minutes": 92.6, "totals": {…},
             "note": "Counts and minutes are summed across competitions; per-90 rates and percentiles stay per competition, …"},
 "rows": [{"competition_id": "co_esp_u19", …},
          {"competition_id": "co_esp_am_men", "club": "CF Torrevalle", "position": "FW", "scope": "level", "sample": {…},
           "metrics": {"np_goals": {"value": 1.79, "percentile": 98, "peers": 27,
                                    "pool": {"tier": "amateur", "competitions": ["co_esp_am_men", "co_nga_am_men", "co_mex_am_men"], …}, …}},
           "touch_map": [[…], …],
           "summary": {"text": "Sergio Cruz is a pressing forward for CF Torrevalle: 39.28 pressures per 90, 2nd of the league's 9 forwards. …", …}}],
 "moments": [{"match_id": "cm_eam_03_tvl_ams", "clip_id": "cl_t_home_09_000014", "title": "Sergio Cruz (9): goal at 56'", "tags": ["shot", "goal"],
              "watchability": 1.0, "video_url": "/api/matches/cm_eam_03_tvl_ams/clips/cl_t_home_09_000014.mp4", "competition_id": "co_esp_am_men", …}],
 "profile_url": null, "summary_note": "…", "pool_rule": "…", "reliability_note": "…", "warning": null, "synthetic": true, "note": "…"}

GET /api/catalogue/players/pl_sot_09?evidence=shots&competition=co_esp_am_men&evidence_limit=1
{"global_id": "pl_sot_09", "competition_id": "co_esp_am_men", "value": 3.57, "percentile": 87, "pool": {…}, "sample": {…},
 "evidence": {"keys": ["shots"], "total": 2, "moments": 2, "offset": 0,
              "items": [{"metric": "shots", "match_id": "cm_eam_03_tvl_ams", "minute": 56, "clip_id": "cl_t_home_09_000014",
                         "video_url": "/api/matches/cm_eam_03_tvl_ams/clips/cl_t_home_09_000014.mp4",
                         "link": "/?match=cm_eam_03_tvl_ams&player=t_home_09&clip=cl_t_home_09_000014", …}]}, …}
```

### `GET /api/players/{global_id}/career`

Every competition the player is in, for any catalogue player (England's included), and what adds up.
`/api/players/{id}?include=career` adds the same block as `career` to the existing profile. Without the parameter the
profile is `main`'s, which is tested.

```
GET /api/players/pl_kbc_11/career
{"global_id": "pl_kbc_11", "name": "Edson Jimenez",
 "career": [{"competition_id": "co_usa_col_men", "club": "Kestrel Bay College", "kit_number": 11, "role": "W", "appearances": 3,
             "minutes": 87.9, "qualified": true, …},
            {"competition_id": "co_mex_am_men", "club": "Club Agave Azul", "kit_number": 7, "role": "W", "appearances": 2,
             "minutes": 58.3, "qualified": true, …}],
 "overall": {"competitions": 2, "competitions_played": 2, "appearances": 5, "minutes": 146.2, "totals": {…}, "note": "…"},
 "story": "a Mexican student-athlete who plays for an amateur side at home outside the college season",
 "api_url": "/api/catalogue/players/pl_kbc_11", "synthetic": true, "note": "…"}
```

### `GET /api/catalogue/rank`

One metric's leaderboard across the filtered catalogue: `metric`, plus the screen's filters, `scope`, `order`,
`rank_by`, `limit` and `offset`.
- Each row's percentile is read against its own pool. Across levels the board ranks by that percentile (`rank_by`
  pool), within one level by value; a selection with both genders has one board per gender.
- Value rank: ratios rank only rows with their competition's minimum attempts. Pool rank: only rows with a percentile.
  The rest are listed after, unranked.

```
GET /api/catalogue/rank?metric=np_goals&gender=men&position=FW&limit=3
{"metric": {…}, "scope": "level", "rank_by": "pool", "rank_rule": "…", "boards": null, "ranked": 108, "offset": 0, "limit": 3,
 "warning": "rows from different levels: read each percentile against its own pool. Raw event rates barely encode level …",
 "players": [{"rank": 1, "board": "men", "name": "Femi Toure", "competition": "Regista League", "value": 1.64, "percentile": 98,
              "pool": {"scope": "level", "tier": "semi_pro", "age_group": "senior", "size": 33, "small": false, …}, …},
             {"rank": 2, "board": "men", "name": "Sergio Cruz", "competition": "Regional Preferente Levante Interior",
              "value": 1.79, "percentile": 98, "pool": {"tier": "amateur", "age_group": "senior", "size": 27, …}, …},
             {"rank": 3, "board": "men", "name": "Ulises Perez", "competition": "Atlantic Collegiate Soccer Conference",
              "value": 3.25, "percentile": 97, "pool": {"tier": "college", "age_group": "college", "size": 18, …}, …}],
 "unranked": […], "competitions": [… 12 men's competitions], "pool_rule": "…", …}
```

Without `gender` the same request gives `"boards": [{"gender": "men", "ranked": 108}, {"gender": "women", "ranked": 20}]`:
the men's board first, then the women's, which starts again at rank 1 (Hannah Mitchell, Pennine Women's League).
`rank_by=value` gives the old raw-value order on each board.

### `GET /api/catalogue/compare`

`ids` names two or three players, with one row each. By default that is the row with the most minutes;
`competitions=co_x,co_y` picks rows in the order of `ids`. `same_pool` says whether every percentile comes from one
pool.

```
GET /api/catalogue/compare?ids=pl_bro_09,pl_sot_09&metrics=npxg
{"players": [{"name": "Femi Toure", "competition_id": "co_eng_sp_men", "values": {"npxg": {"value": 1.15, "percentile": 98, "pool": {"size": 33, …}, …}}, …},
             {"name": "Sergio Cruz", "competition_id": "co_esp_am_men", "values": {"npxg": {"value": 1.82, "percentile": 98, "pool": {"size": 27, …}, …}}, …}],
 "columns": […], "scope": "level", "same_pool": false,
 "warning": "different pools (level or position): read each percentile against its own pool", …}
```

### `GET /api/catalogue/matches`

Uploaded matches across the catalogue, in the index's competition order and then by date. Filters: `competition`,
`country`, `tier`/`level`, `age_group`, `gender`, `club` (an id), `camera`, `uploader_type`; plus `limit` and `offset`.

```
GET /api/catalogue/matches?uploader_type=player&tier=amateur&limit=1
{"matches": [{"match_id": "cm_eam_03_tvl_ams", "round": 3, "date": "2026-10-24", "score": {"t_home": 1, "t_away": 0},
              "title": "Regional Preferente Levante Interior, matchday 3: CF Torrevalle 1–0 Atlético Montesol",
              "uploader": {"type": "player", "global_id": "pl_tvl_04", "club_id": "cl_torrevalle", "club": "CF Torrevalle", "name": "Alvaro Munoz"},
              "camera": "phone", "clip_view": "/?match=cm_eam_03_tvl_ams", "competition_id": "co_esp_am_men", "country": "Spain",
              "tier": "amateur", …}],
 "total": 9, "offset": 0, "limit": 1, "filters": {"tier": "amateur", "uploader_type": "player"}, "camera_note": "…", …}
```

### `GET /api/catalogue/pools`

Pool sizes per scope and position: rows qualified on minutes, each under its own competition's rule. A metric's own
pool can be smaller (ratio attempts).

```
GET /api/catalogue/pools
{"scope": "level", "min_pool": 5, "small_pool": 15,
 "pools": [… , {"label": "academy/U17/men", "competitions": ["co_gha_u17"],
                "positions": {"GK": {"size": 2, "small": true, "under_min": true}, "DF": {"size": 8, "small": true, "under_min": false},
                              "MF": {"size": 6, …}, "FW": {"size": 5, …}}}], "pool_rule": "…", "warning": null, …}
```

## Optional parameters on existing endpoints

Every response keeps today's top-level keys. Each adds the fields described here.

| Endpoint | New parameters | What they do |
|---|---|---|
| `GET /api/season` | `competition` | That competition with the same keys. `table` is its uploaded matches' results; `table_note` says so. `rounds` lists matchdays with uploads, each match with uploader and camera. `percentiles` gains `scope` and `min_pool`. `competition` holds the labels. For England: today's response plus `competition` and `table_note: null`. |
| `GET /api/players` | `competition`, `country`, `tier`/`level`, `age_group`, `gender`, `scope`/`pool`, `offset` | Cards from each selected competition. Each headline percentile is in `scope` (level by default) with its `pool`. Cards gain competition labels, `career` and `api_url`. `total` counts every row. England's cards come from the app's own season (fixtures, confirmed claims, Player-view uploads), so they are today's cards; `basis` says so. |
| `GET /api/players/{id}` | `include=career` | Adds `career` (the career block). |
| `GET /api/metrics` | `competition`, `scope` | Each metric described in that competition: ratio minimums, the reliability table it reads, its realism check. Plus the catalogue `season` block. The xT grid outside England is England's. |
| `GET /api/terminal/screen`, `/rank`, `/scatter` | the five competition filters, `scope`/`pool` | Same keys. Cells and points carry `pool` and `sample` (scatter: `x_pool`, `y_pool`). `season` becomes the catalogue block: scope, competitions with their minimums and samples, the pool rule, the warning, and the competition's thresholds when there is one competition. |
| `GET /api/players/{id}/metrics`, `/form`, `/similar`, `/shots`, `/heatmap` | `competition`, `scope` | That catalogue row (default: the player's row with the most minutes), with pools in `scope`. `similar` with level or all scope uses the cross-level standardisation from engine.md. |
| `GET /api/teams` | the five competition filters | The selected competitions' clubs, each with `level_rank`, `level_of` and `level_mean`. |
| `GET /api/teams/{club_id}/style`, `/shots` | `competition` | A catalogue club in that competition (a 404 if it has no upload there). |

Examples:

```
GET /api/terminal/screen?country=Germany&position=FW&metrics=npxg&limit=1
{"columns": […], "sort": "npxg", "total": 15, "offset": 0,
 "players": [{… "values": {"npxg": {"value": 0.52, "percentile": 92, "peers": 33, "pool": {"competitions": ["co_eng_sp_men", "co_ger_sp_men"], …}, "sample": {…}}}}],
 "season": {"scope": "level", "competition_id": "co_ger_sp_men", "min_minutes": 45.0, "warning": null, "competitions": […], …}}

GET /api/season?competition=co_mar_u19
{"league": "Ligue Juniors Atlas Centre U19", "season": "2026/27", "clubs": […],
 "table": [{"club_id": "cl_nour_cedres", "club": "Nour Cèdres Juniors", "played": 3, "won": 1, "drawn": 2, "lost": 0, …}, …],
 "table_note": "uploaded matches only, not a league table", "rounds": [{"round": 1, …}, {"round": 5, …}, {"round": 6, …}],
 "percentiles": {"rule": "…", "min_minutes": 45.0, "scope": "competition", "min_pool": 5}, "noisy": ["key_passes", …], …}

GET /api/players?gender=women&position=FW&min_minutes=45&sort=goals&limit=1
{"players": [{"name": "Hannah Mitchell", "competition": "Pennine Women's League", "minutes": 60.2,
              "headline": {"goals": {"label": "Goals", "count": 1, "per90": 1.5, "percentile": 95,
                                     "pool": {"scope": "level", "tier": "semi_pro", "gender": "women", "position": "FW", "size": 11, "small": true, …}}, …}, …}],
 "total": 20, "offset": 0, "scope": "level", "competitions": ["co_eng_sp_women", "co_usa_col_women"],
 "warning": "rows from different levels: read each percentile against its own pool", …}

GET /api/players/pl_bro_09/similar?scope=all&n=2
{… "z_basis": "level", "warning": "rows from different levels: …",
 "similar": [{"name": "Ulises Perez", "competition": "Atlantic Collegiate Soccer Conference", "similarity": 0.897, "same_level": false, …},
             {"name": "Murilo Pereira", "competition": "Campeonato Serrano Sub-20", "similarity": 0.851, "same_level": false, …}]}

GET /api/teams/cl_hollenburg/style?competition=co_ger_sp_men
{"club": "SV Hollenburg", "values": {"possession_pct": {"value": 51.3, "rank": 3, "of": 6, "league_mean": 49.8, "level_rank": 4, "level_of": 12,
 "level_mean": 49.9, …}, …}, "sample": {"matches": 3, "small": false, "competition_matches": 8}, "competition_id": "co_ger_sp_men", …}
```

**Two decisions made here.**
- **Pooled percentiles for `/api/players` cards.** The cards' headline stats are the profile's own counts. They are not
  the terminal's metrics; for example, shots there include penalties. So their pooled percentile is computed the same
  way `Season` computes its own (`CatalogueProfiles.stat_cell`):
  - FBref's rule, not inverted, on per-90 rates;
  - rates use the unrounded minutes of the metrics engine (the same playing time; all 1,054 rows agree);
  - each row qualifies under its own competition's minutes;
  - at least 5 peers outside England's own competition scope.
  A test recomputes one college forward's goals percentile by hand.
- **`/api/competitions/{id}/players` defaults to scope `level`**, as every catalogue answer does (requirement 4). The
  design suggested `competition`. `scope=competition` gives that.

**404 hints.**
- `/api/players/pl_sot_09` and the terminal's player endpoints say "a catalogue player: GET /api/catalogue/players/pl_sot_09".
- `/api/teams/cl_hollenburg/style` says "a catalogue club: add competition=co_ger_sp_men".
- An id that is in no catalogue squad keeps today's detail. `pl_zzz_09` is in the back-compat snapshot and is tested.

## MCP tools (added; existing tools untouched)

| Tool | Arguments | Returns |
|---|---|---|
| `list_competitions` | country, tier, age_group, gender | the competition summaries, levels and careers |
| `search_catalogue_players` | tier, age_group, gender, country, competition, position, sort (minutes or any terminal metric), order, scope (level default), limit (at most 50), min_minutes, rank_by | one row per player and competition; the sorted metric's value, percentile, noisy flag and pool; a warning across levels; across levels ranked by percentile within each row's pool, genders on separate boards |
| `get_catalogue_player` | player (global id, full name, or a unique part of a name), scope | `CatalogueMetrics.player` (bio, career, overall, rows with pools), no evidence lists; candidates when the name is ambiguous |

Bad arguments return `{"error": …}` so an agent can correct itself. Example:

```
search_catalogue_players(gender="men", position="FW", sort="npxg", limit=2)
[{"global_id": "pl_mpu_09", "name": "Ulises Perez", "competition_id": "co_usa_col_men", "tier": "college", "minutes": 83.0, "career": false,
  "stat": {"key": "npxg", "label": "Non-penalty xG", "value": 2.61, "percentile": 97, "noisy": true,
           "pool": {"scope": "level", "tier": "college", "age_group": "college", "gender": "men", "position": "FW", "size": 18, "small": false, "reason": null}}, …},
 {"global_id": "pl_sot_09", "name": "Sergio Cruz", "competition_id": "co_esp_am_men", "tier": "amateur", "career": true,
  "stat": {"value": 1.82, "percentile": 98, "pool": {"tier": "amateur", "size": 27, …}, …}, …}]
get_catalogue_player("Olivia King") -> {"global_id": "pl_msa_07", "rows": [co_usa_col_women, co_eng_sp_women], …}
```

## Tests

`tests/test_catalogue_api.py` has 27 tests on the committed catalogue. They check:
- **The catalogue:** totals 14 / 10 / 66 / 1,183 / 90; five careers; the level pools.
- **Filters:** seven filter cases on `/api/competitions`, including case-insensitive country and an unknown country.
- **Competitions:** England's competition (its table equals `/api/season`'s; 30 uploads). Germany's (8 uploads, named
  uploaders, results only, careers in squads).
- **The screen:** pages through every row (the union equals `cm.select()`) with pools on every cell. Filters, sort and
  order; women only; careers only; camera; scope all.
- **Pools:** a competition's players default to the level pool. Morocco U19 in competition scope has no percentile and
  gives the reason; in its level pool it has percentiles.
- **One player:** a career player has two rows, two career entries, the overall sum, touch maps, summaries and moments.
  Paged evidence from `cm_` matches; refusals.
- **Careers:** `/career`, and `include=career` leaves the rest of the profile byte-equal.
- **Rank, compare, matches, pools:** rank paging and ties; compare in the same and in different pools; matches with
  every filter and paging; pool sizes.
- **England in competition scope:** the catalogue path equals today's screen cells and card percentiles.
- **Existing endpoints in catalogue mode:** each keeps today's keys; the scope/pool alias and the conflict between them.
- **A pooled card percentile** recomputed by hand.
- **404 hints** only for catalogue ids.
- **Bad inputs:** 14 kinds refused.
- **The Clip view:** a `cm_` match opens in it.
- **Privacy:** a walk of 30 payloads.
- **MCP tools:** listed and answering.

**Results on the Mac.**
- Quick suite (`python3 -m pytest -q`): **941 passed**, 14 deselected, in 4 min 11 s (914 before this phase).
  `tests/test_catalogue_backcompat.py` and `tests/test_access.py` pass.
- Slow suite (`python3 -m pytest -q -m slow`): **14 passed** in 1 min 54 s. The engine and generator are unchanged in
  this phase, apart from the additive profile methods.
- Linux CI runs on the PR.

## Open

- **Summary wording.** The rules summary of a sparse competition still says "of the league's 9 forwards", meaning the
  competition's players in its uploaded matches. `summary_note` says what the summaries rest on. Rewording
  `summaries.py` would change England's stored summaries' basis, so it is left for the UI round.
- **Profile links.** `profile_url` stays null for non-England players, because `/players/{id}` (the page) reads
  `/api/players/{id}`, which serves England only. Every catalogue row carries `api_url` instead. The UI round decides
  the page.
- **The Foundry Scout agent** still has only the three league tools (`SCOUT_TOOLS`). Giving it the catalogue tools is a
  decision for Zaid (design.md §8.4, §13).
- **Ranking across levels.** Resolved in review round 1: across levels the lists rank by percentile within each row's
  pool and keep genders on separate boards; raw-value ranking stays available with `rank_by=value`.
