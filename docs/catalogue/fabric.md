# The catalogue in Microsoft Fabric

**Status (2026-10-26): built and tested offline on `feature/catalogue-fabric`. Not yet pushed to Fabric; the notebook has
not yet run there.** Every number below comes from the code run offline on the committed catalogue. The lead fills in
the real push and run (section "Real run", at the end).

The league already lives in the Fabric lakehouse `regista_league` (CLAUDE.md §2.7, `docs/architecture.md` "Microsoft
Fabric"): Delta tables in OneLake, and a Spark SQL notebook that recomputes the leaders from the raw tables so Regista
can compare them with its own numbers (756 of 756 rows on 2026-10-24). This adds the catalogue (CLAUDE.md §2.11: 14
competitions in 10 countries, 90 uploaded matches, levels, pools within a level) to the same lakehouse, with its own
independent check, in the same way.

## What is built

| Piece | Where |
|---|---|
| The catalogue's tables (rows as plain dicts, schemas in `SCHEMAS`, `to_arrow`) | `src/regista/cloud/fabric_catalogue.py`, `src/regista/cloud/fabric_tables.py` (`CATALOGUE_TABLES`) |
| The second notebook (Spark SQL) and its Python twin `catalogue_leaders_rule` | `src/regista/cloud/fabric_catalogue_notebook.py` |
| `compare` and `report_lines` for both checks (rows keyed on competition when they carry one) | `src/regista/cloud/fabric.py` |
| CLI: `push --catalogue`, `push --catalogue-only`, `check --catalogue` | `src/regista/season/fabric.py` |
| Tests (no test reaches Fabric, OneLake or Azure) | `tests/test_fabric_catalogue.py` (18 tests); `tests/test_fabric.py` unchanged apart from naming the league's tables |

The league's tables, its notebook (`regista_leaders_check`), `leaders_check` and its 756-row check are unchanged: the
catalogue's tables are all named `catalogue_*`, its notebook is a second notebook (`regista_catalogue_check`) that reads
and writes only `catalogue_*` tables, and plain `push` and `check` do exactly what they did before.

### The tables

| Table | Rows (offline) | What |
|---|---:|---|
| `catalogue_competitions` | 14 | country, region, tier, age group, gender (keys and labels), `level` (`tier/age_group/gender`), format, season, eligibility, coverage, `source` (`league` for England), `as_of` 2026-10-24 |
| `catalogue_clubs` | 66 | one per club and competition (6 league clubs + 60) |
| `catalogue_players` | 1,188 | one per squad entry (competition, global id): name, club, kit number, position, role, starter, and the public bio only (age, date of birth, height, foot, nationality); `career` on the 10 entries of the 5 people in two squads |
| `catalogue_matches` | 90 | competition, round, date, score, periods, `played_s`, title, uploader (type `team` 59 / `player` 31, club, player), camera (tripod 39, drone 19, broadcast 18, phone 14; a label only) |
| `catalogue_lineups` | 3,240 | one per player per match; `played_s` from substitutions and red cards (`regista.season.playing_time`) |
| `catalogue_events` | 102,904 | every event, with `competition_id` and `seq` (its place in the stream) |
| `catalogue_possessions` | 30,645 | every possession record, with `seq` (key passes are read off them) |
| `catalogue_player_season` | 7,399 | Regista's numbers for the check: 1,057 player-competition rows x 7 stats |
| `catalogue_leaders_check` | (7,399) | written by the notebook |

Never written: the hidden ratings, the competition files' `level` block (scales and `execution`), the generator block,
the attributes block and every seed (the league's own `matches` table keeps its seed column, as before). A test checks
every catalogue table's columns against those names.

**England semi-pro men comes from the league fixtures.** Its 30 rows in `catalogue_matches` are the Regista League's
fixtures, read from the league's own folders (`data/season/matches`), exactly the matches the catalogue pages count
(Zaid's port decision: league fixtures only). The Player view's friendlies (`pv_…`) are not catalogue matches, so they
are in no catalogue table; they stay in the league's `uploads` table. England's uploader and camera come from the
index's overlay. England's events are therefore in the lakehouse twice, once in `events` and once in
`catalogue_events`, so each check reads only its own tables.

### Regista's numbers: `catalogue_player_season`

From the engine the catalogue pages use, `regista.catalogue.metrics.CatalogueMetrics`: one row per player-competition
row (every player who appeared in a competition's uploaded matches; a career player has one row per competition) and
stat, with appearances, minutes (0.1), count, per-90 (2 decimals), `qualified`, the percentile in the default **level**
pool (`scope=level`), that pool's size, its words ("semi-pro men forwards"), the competition's qualifying minutes and
the row's noisy flag. A test checks these rows against `CatalogueMetrics.cell(..., "level")`. Femi Toure's goals row:
5 goals, 1.64 per 90, the 98th percentile among 33 semi-pro men forwards.

### The stats, and where the catalogue engine differs from the league check

The same seven stats as the league check (`CHECK_STATS`): goals, assists, shots, key passes, take-ons won, tackles won,
interceptions. All seven are per-90 counts where more is better, ranked for outfield players only (a keeper's pool size
is 0), and in `COUNT_METRICS`, so the catalogue's "none yet" applies (no percentile at 0). The league check follows the
profiles (`regista.season.profiles`); the catalogue pages use the Terminal's engine (`regista.season.metrics`), which
defines three of them differently. The SQL follows the engine; the engine is not changed.

| Stat | League check (profiles) | Catalogue engine, and the SQL |
|---|---|---|
| shots | every `shot` | `shot` without the `penalty` qualifier (FBref Sh) |
| key passes | a pass or cross with the `key_pass` qualifier | FBref's: for each non-penalty shot whose possession was gained by `pass_received`, the last successful pass or cross by a teammate to the shooter between the previous possession record and the shot's own (by `seq`) |
| tackles won | `tackle` with outcome `success` | `tackle` with outcome `success` or none |
| goals, assists, take-ons won, interceptions | the same tests | the same tests |

On the committed catalogue the two key-pass rules agree player by player (395 key passes), and every tackle carries
`success`, so only shots differ in the data: 5 penalty shots.

### The second notebook: `regista_catalogue_check`

Reads `catalogue_competitions`, `catalogue_players`, `catalogue_matches`, `catalogue_lineups`, `catalogue_events` and
`catalogue_possessions`, and writes the catalogue's rules again in Spark SQL:

- **appearances**: a starter, or a player who came on (a substitution's `related_player_id`), in a squad of that
  competition; **minutes**: the sum of those lineups' `played_s / 60`. Events count only for a player who appeared in
  that match, for the competition of the match (a career player's two rows stay apart).
- **qualifying minutes, per competition** (`CatalogueMetrics`): a third of the busiest club's minutes, rounded to 0.1
  (a club's minutes: the sum of its matches' `played_s / 60`); England (`source = 'league'`) keeps exactly that, every
  other competition needs at least 45. Offline: England 100.5, every other competition 45.
- **level pools**: the qualified rows of one position over every competition of the same tier, age group and gender,
  each row qualified under its own competition's rule (England and Germany semi-pro men share one pool).
- **percentile**: FBref's, `BROUND(50 * (strictly below + at or below) / n, 0)` on the unrounded rate (6 decimals); none
  when the pool has fewer than 5 rows or the count is 0 (the row stays in its pool).

It writes one row per competition, player and stat to `catalogue_leaders_check`, rebuilt each run without deletion
vectors (as the league's notebook does), and shows the top three per level for goals.

### The Python twin and the tests

`catalogue_leaders_rule` is the same SQL, view by view, in plain Python over the same tables; it imports nothing from
`regista.catalogue` or `regista.season`. `tests/test_fabric_catalogue.py`:

- the tables: schemas, sizes (14 competitions, 10 countries, 90 matches, events, possessions and lineups equal to the
  streams), England = the 30 league fixtures, no Player-view friendly, no hidden name in any column, every row's
  competition and global id;
- `catalogue_player_season` equals what the catalogue pages show (`CatalogueMetrics.cell`, level scope);
- the twin reproduces **7,399 of 7,399** rows offline (counts, appearances, minutes, per-90, qualified, pool size and
  percentile), and some England percentiles differ from the competition's own (the level pool is in effect);
- the check is sharp: penalties in the shots, no 45-minute floor, pools per competition, or men and women in one pool
  each make it fail;
- a pool of 4 gives no percentile, a count of 0 gives none, keepers have pool size 0;
- the stats mean what the engine means (per-90, higher is better, count metrics, outfield positions);
- the notebook reads only `catalogue_*` tables, writes `catalogue_leaders_check`, compiles cell by cell and states its
  rule; the league's notebook does not mention the catalogue;
- `compare` keeps a career's two rows apart and names the competition in each difference;
- the CLI: `push --catalogue-only` writes only the 8 catalogue tables, `push --catalogue` the league's and the
  catalogue's, plain `push` only the league's; `check --catalogue` creates and runs `regista_catalogue_check` and
  compares, and a changed number fails it.

What the data does not exercise: England's third (100.5) is above the 45-minute floor, so England's own case changes no
number here; and no level pool of these stats is under 5 rows (the smallest is 5: academy U17 men forwards), so the
minimum pool removes no percentile in the real data. The twin's tests exercise both.

## Run steps (for the lead)

From the repository root on a machine signed in with `az login` as al-qadi.z@northeastern.edu, with
`REGISTA_FABRIC_WORKSPACE_ID` and `REGISTA_FABRIC_LAKEHOUSE_ID` in `.env` (written by `setup` on 2026-10-23):

```bash
# 1. the league check first, unchanged (expect 756 of 756)
python3 -m regista.season.fabric check

# 2. push the catalogue's 8 tables (the league's tables untouched)
python3 -m regista.season.fabric push --catalogue-only
#    or league + uploads + catalogue in one go: python3 -m regista.season.fabric push --catalogue

# 3. create and run regista_catalogue_check, then compare
python3 -m regista.season.fabric check --catalogue --json docs/catalogue/fabric-check.json
```

Success: step 2 prints `catalogue_competitions 14`, `catalogue_clubs 66`, `catalogue_players 1188`,
`catalogue_matches 90`, `catalogue_lineups 3240`, `catalogue_events 102904`, `catalogue_possessions 30645`,
`catalogue_player_season 7399` and `pushed 8 tables`; step 3 prints the notebook's table counts, `7399 rows in
catalogue_leaders_check`, `checked 1057 player-competition rows in 14 competitions x 7 stats (...): 7399 of 7399 match`
and `result: Fabric agrees with Regista`, and exits 0.

## Real run

Not yet run. To fill in: date, workspace and lakehouse, push row counts and time, notebook run id and time, the check's
line (`N of 7,399`), and any difference.
