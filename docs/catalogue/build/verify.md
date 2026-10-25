# The catalogue: independent verification (after phase 4)

Branch `feature/catalogue` at c7d90a3, 2026-10-25, on Zaid's Mac (macOS arm64, Python 3.13). I did not rely on the
phase reports. Each claim below was checked by rebuilding the data, recomputing numbers from the raw event streams, or
running the app. Nothing was pushed or merged. Nothing was sent to the live app, Azure or Fabric. Tests ran with
`REGISTA_DOTENV=` (empty, so `.env` is never loaded).

## Verdict

| Check | Result |
|---|---|
| England semi-pro men unchanged; Femi Toure has 5 goals | **Pass** |
| Back-compat (`test_backcompat`, catalogue snapshot) | **Pass** |
| Every new match is pinned and builds the same twice | **Pass** (60 of 60) |
| Pools within level, recomputed by hand | **Pass** (12 of 12 cells, 6 players, 5 levels) |
| Careers | **Pass** (5 of 5) |
| No hidden rating in any API or MCP payload | **Pass** (396 GET payloads, 9 MCP results) |
| Current app works offline | **Pass** |
| Quick and slow suites | **Pass** (941 quick, 14 slow) |
| Realism per level | **Honest in its claims; two checks fail.** The report document is not written yet (phase 5). |

## 1. England semi-pro men and Femi Toure

- `data/season/league.json` has SHA-256 `04dbb30f…0b1a34`, the same on this branch and on `main`.
- I rebuilt all 30 fixtures from `league.json` into an empty folder (`regista.season.build.build_all`, 10 workers,
  6.5 s). `regista.season.pins.drift` returned `{}`: every fixture matches its SEASON_PIN.
- I counted Femi Toure's goals in the rebuilt streams myself: Brookfield's 9 shirt has `goal` events in rounds 1, 1, 6,
  8 and 10, so 5 goals. No penalty event belongs to him.
- On the same rebuild, his shots per 90 are 6.23, the figure CLAUDE.md quotes.
- The generator diff against `main` is the inert `style_offset` only. It does nothing unless a team spec carries the
  key. `generate_kwargs` adds the key only when a competition file has a `level.style_offset`, and `league.json` has
  none.

## 2. Back-compat

- `tests/test_backcompat.py` passes. That test checks that `generate()` without attributes is byte-identical to main.
- `tests/test_catalogue_backcompat.py` passes. It holds 21 HTTP and 4 MCP responses recorded on main's code.
- I re-ran both after my one edit (§9), together with the catalogue metrics and API tests: 65 passed.

## 3. Catalogue matches: pins and determinism

- 60 fixtures with 60 unique ids. The set equals the keys of `CATALOGUE_PINS`.
- I built all 60 twice into empty scratch folders:
  - 10 processes: 12.6 s.
  - 1 process: 78.4 s.
- `regista.catalogue.pins.drift` was `{}` for both builds.
- The two builds have identical files: all 180, SHA-256 compared file by file.
- They are also identical to the folders already in `data/catalogue/matches/`.
- Uploads are sparse as specified: 3 to 8 per competition. Germany has 8, and Ghana U17 and Morocco U19 have 3 each.
- Every new match has an uploader (a club of the match, or a player of one side) and a camera. Every player uploader
  started the match they uploaded.
- Every squad has 18 players with unique kit numbers.
- Ages at 1 August 2026 fit the age groups:

  | Age group | Ages |
  |---|---|
  | U17 | 15-16 |
  | U18 | 16-17 |
  | U19 | 16-18 |
  | U20 | 17-19 |
  | college | 18-23 |

- The mean hidden skill of outfield players falls with level, as designed: England 63.2, Germany 62.4, college men
  60.3, U17 54.1, amateur men 54.9-55.2.
- Mean top speed is 27.6-27.7 km/h for women and 31.1 km/h for U17, against about 33 for senior men.
- Not checked here: Linux. The 60 pins were recorded on macOS and have not run on Linux CI yet. The PR is their first
  Linux run.

## 4. Pools within level, recomputed by hand

I wrote a separate script that does not import `regista.catalogue.metrics`. For every competition it reads the raw
`events.jsonl`. Minutes come from `regista.season.playing_time` (existing code on main). Then it applies the rule
itself:

1. Count shots (penalties excluded, as in FBref's Sh) and successful tackles.
2. A row qualifies with at least a third of the busiest club's minutes. Outside England the minimum is at least 45.
3. Pool qualified rows of the same tier, age group, gender and position.
4. Apply FBref's percentile (mean of the share strictly below and the share at or below).

I compared the result with `/api/catalogue/players/{id}`:

| Competition (level) | Player | Metric | Mine (value, pool, pct) | API | |
|---|---|---|---|---|---|
| Germany (semi-pro men) | Fabian Meyer | shots | 3.452, 33, 80 | 3.45, 33, 80 | match |
| Germany (semi-pro men) | Fabian Meyer | tackles won | 0.0, 33, 14 | 0.0, 33, 14 | match |
| Spain amateur (amateur men) | Sergio Cruz | shots | 3.571, 27, 87 | 3.57, 27, 87 | match |
| Spain amateur (amateur men) | Sergio Cruz | tackles won | 3.571, 27, 94 | 3.57, 27, 94 | match |
| Ghana U17 (U17) | Richard Kusi (DF) | shots | 0.0, 8, 38 | 0.0, 8, 38 | match |
| Ghana U17 (U17) | Richard Kusi (DF) | tackles won | 1.634, 8, 81 | 1.63, 8, 81 | match |
| England women (semi-pro women) | Olivia King | shots | 0.0, 11, 18 | 0.0, 11, 18 | match |
| England women (semi-pro women) | Olivia King | tackles won | 0.0, 11, 23 | 0.0, 11, 23 | match |
| England men (semi-pro men) | Femi Toure | shots | 6.235, 33, 98 | 6.23, 33, 98 | match |
| England men (semi-pro men) | Femi Toure | tackles won | 0.656, 33, 32 | 0.66, 33, 32 | match |

- Sergio Cruz in Spain U19 (42.2 minutes, under the 45-minute minimum) is correctly not qualified and gets no
  percentile in either script.
- Every cell carries its pool: scope, tier, age group, gender, position, size, `small` (size under 15), `min_size` and
  competitions. It also carries its sample: minutes, qualifying minutes, matches.
- The U17 and women's pools above are flagged `small`.
- Scope `all` keeps genders apart and carries the warning.

## 5. Careers

The index lists 5 careers. From the competition files and raw streams:

- Each career player is in exactly one squad in each of his two competitions, and in no other squad. Exactly these 5
  global ids appear in two competitions; all 1,183 people are otherwise unique.
- Name, date of birth, nationality, height and foot are identical in both squads. The hidden ratings are identical too:
  one person on one absolute scale.
- The minutes I computed from the streams equal the API's career rows:

  | Player | First competition | Second competition |
  |---|---|---|
  | Sergio Cruz | Spain U19, 42.2 min | Spain amateur, 50.4 min |
  | Alberto Navarro | Spain U19, 56.8 min | Spain amateur, 30.1 min |
  | Olivia King | USA college women, 81.2 min | England women, 51.7 min |
  | Finn Schmidt | USA college men, 21.1 min | Germany, 60.2 min |
  | Edson Jimenez | USA college men, 87.9 min | Mexico amateur, 58.3 min |

- No career player has two matches on the same date.
- The `overall` block sums minutes, appearances and counts. It does not give a merged per-90 rate.
- Ages fit the stories. Sergio Cruz is 17 and Alberto Navarro was born in January 2008, so both are juvenil-eligible
  in 2026/27. The college players are 19-21.

## 6. Hidden ratings

- **HTTP.** I called every GET `/api` route the app serves. Path parameters used England, catalogue and career ids; I
  skipped video, crop and upload/job routes, which need ids that do not exist offline. Each route was called with six
  parameter variants: none, `competition`, `scope=all`, `scope=level`, `tier=academy` and `include=career`.
  - I walked every JSON payload, 396 in all.
  - I looked for every rating key (`finishing`, `passing`, `vision`, `dribbling`, `defending`, `aerial`, `stamina`,
    `top_speed_kmh`, `acceleration_ms2`, `shot_stopping`, `handling`, `distribution`, `attributes`).
  - I looked for every level-scale key (`skill_offset`, `stamina_offset`, `speed_mult`, `accel_mult`, `height_shift`,
    `style_offset`, `age_range`, `scales`, `age_on`, `hidden`).
  - I looked for `seed` and for any match seed value.
  - **0 hits.**
- **MCP.** I called the three new tools with filters, all scopes, a name lookup, an unknown id and a bad scope: 9
  results, **0 hits**. Bad input comes back as `{"error": …}`.

## 7. The current app, offline

I ran `REGISTA_DOTENV= uvicorn regista.api:app` from this branch on port 8040, using the repo's `regista-offline`
launch entry rather than 8211 so that no tracked file was edited. It was a fresh process: an old server on that port
was stopped first.

- **Pages.** `/`, `/me`, `/scout`, `/scout#terminal` and `/players/pl_bro_09` load with no console errors, and the
  server log has no errors.
  - The terminal says "102 players, 127 stats, 30 matches", which is England only, as before.
  - Femi Toure tops non-penalty goals at 1.64.
  - "who has the most tackles won" ranks tackles won through `/api/terminal/screen`.
  - `/api/terminal/rank?metric=np_goals&position=FW` answers with Femi first.
- **Catalogue endpoint.** `/api/catalogue` answers on the same server.

## 8. Realism per level

**What exists.** `regista.catalogue.realism` gives each metric at each level one kind of check:

- a published band: pass or fail;
- a sourced order between levels: pass or fail;
- an upper reference: no verdict;
- `none`: "no published band at this level: the number is shown, nothing is claimed".

**What I checked:**

- **Premier League bands stay where allowed.** They appear only for senior semi-pro men and college men. A scan of all
  127 metrics across 14 competitions found none elsewhere.
- **Kinds per level, out of 127 metrics.**

  | Level | band | order | reference | none |
  |---|---|---|---|---|
  | U17 | 1 | 1 | 0 | 125 |
  | Amateur | 0 | 2 | 0 | 125 |
  | Semi-pro women | 0 | 3 | 2 | 122 |

  The other youth levels have no band and no reference.
- **Re-measurement.** I re-ran the measurement into the scratchpad (`python -m regista.catalogue reliability --out …
  --aggregates …`): 1,524 matches in 290 s. The resulting `reliability.json` is **byte-identical** to the committed
  `data/catalogue/reliability.json`.
- **Verdicts on the measurement seasons.** 1 of 1 band fails; 9 of 10 orders pass.

  | Check | Values | Verdict |
  |---|---|---|
  | U17 mean peak match speed, band 24.9-28.7 km/h [S5] | 29.68 | **fail** |
  | Amateurs complete fewer passes than semi-pro men [S10] | 81.38% vs 80.53% | **fail** |
  | Amateurs sprint less [S9] | 209 vs 233 m per 90 | pass |
  | Peak speed rises with age, U17 to senior | 29.68 < 30.26 < 30.57 < 30.63 < 31.46 | pass |
  | Distance rises with age, U17 to senior | 9,855 < 10,034 < 10,040 < 10,122 < 10,365 m | pass |
  | Women complete fewer passes, semi-pro and college | 79.68 vs 80.53; 79.18 vs 81.04 | pass |
  | Women lose the ball more, semi-pro | 12.73 vs 12.68 per 90 | pass by 0.05 per 90: no real difference |
  | Women lose the ball more, college | 13.12 vs 12.18 | pass |
  | Women cover less distance at 20 km/h or more, semi-pro and college | 825 vs 1,040; 817 vs 985 m | pass |

- **The one band's source.** S5 exists: Al Haddad et al., IJSPP 2015;10(7):888-896, on 180 U13-U17 players. A later
  review cites it for a U17 peak match speed of 26.8 km/h. I could not see the paper's own table, so the ± 1.9 is
  unchecked.
- **How the band is built.** The band is mean ± one SD of individual players, applied to the level's mean. That is a
  generous window for a mean, and the value still lies outside it.
- **Source details.** S4, S6 and S9 have no authors or year in `SOURCES`, and no source carries a URL or DOI. Phase 5
  should complete them in `docs/catalogue/realism.md`.
- **Still missing.** The realism report itself (`report.py --catalogue` and `docs/catalogue/realism.md`) is phase 5 and
  is not written. The checks run in code, as above.

## 9. Fixed here

- **The written qualifying rule was wrong.** `POOL_RULE`, served as `pool_rule` and `percentile_rule` in catalogue
  responses, said a row qualifies with "a third of its club's minutes". The code (`SeasonMetrics.min_minutes`) uses a
  third of the competition's *busiest* club's minutes.
  - This makes no difference in England, where every club plays 10 matches.
  - In sparse competitions the 45-minute floor always applies: the busiest club has at most 4 uploads, about 40
    minutes.
  - The wording now says "a third of the minutes of the competition's busiest club". engine.md's rule line says the
    same.
  - No test pins the string, and no back-compat response contains it.

## 10. Open, not fixed (Zaid's call or a later phase)

1. **Linux CI has not run on this branch.** The PR is the first Linux run of the 60 catalogue pins, the level
   reliability table (its slow test) and the new API tests.
2. **Two realism checks fail** (§8): U17 peak match speed (29.68 against at most 28.7) and amateur pass completion
   above semi-pro men's.
   - The pass-completion levels hardly separate anywhere: 79.2-81.4% at every measured level.
   - Women losing the ball more at semi-pro level passes by only 0.05 per 90.
   - A retune changes generator or level scales, so every catalogue pin, the level reliability table and the reported
     numbers move. England stays untouched only if `generator.py` is not edited, or if the edit stays inert for
     `league.json`.
3. **Phase 5 is not built:**
   - `report.py --catalogue` and `docs/catalogue/realism.md`, with full source citations (authors, year, DOI or URL for
     S1-S11; S7 is unused).
   - CLAUDE.md §2.11.
   - The data README's Catalogue section.
4. **An unqualified row's pool gives no reason.** It has `percentile: null` with `pool.reason: null`. `qualified: false`
   and `sample.minutes` against `sample.qualifying_minutes` explain it, but a UI should say "under N minutes". The
   reason is pool-level by design, so this belongs in the UI round.
5. **Players at clubs with one uploaded match never qualify** (30 minutes is under the 45-minute floor). Morocco U19
   has three such clubs. This is honest and flagged, but the UI should explain it.
6. **Carried over from the phase reports, unchanged:**
   - Names were not web-checked against real clubs.
   - `profile_url` is null for non-England players.
   - The Foundry Scout agent does not have the catalogue tools.
   - Ranking across levels is by raw value.
   - Sparse competitions' rules summaries say "of the league's N forwards".
