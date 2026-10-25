# Catalogue review B, round 1: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at 823d5f3 (`git diff main...HEAD`). I fixed nothing. **Not signed
off:** 2 must-fix and 8 should-fix findings below.

I checked the work offline, with nothing sent to the live app or Azure:
- read the taxonomy, definition, engine, realism and API code, the competition files and the phase reports;
- queried the API through FastAPI's TestClient (`REGISTA_DOTENV=`);
- read the committed match folders and `data/catalogue/reliability.json`.

The verifier already confirmed the England pins, Femi Toure's 5 goals, the pools' arithmetic and the test suites. I did
not repeat those checks.

## What is good

- The structure suits recruitment below the professional line:
  - four tiers with no professional tier, six age groups, two genders and 14 competitions in 10 countries;
  - uploaders and camera types, with the camera clearly marked as a label;
  - every number carries its pool (scope, tier, age, gender, position, size, `small`, competitions) and its sample.
- `all` scope keeps genders apart. Similar players across levels are standardised within each player's own level, which
  is the right choice.
- No career row merges per-90s across levels.
- Local detail is believable: Ghana's "Colts" football, the Spanish *juvenil*, German semi-pro naming, and each
  country's calendar window.
- The scales are honestly labelled `sourced`, `direction` or `assumption`. Heights (men about 181 cm, women about
  170 cm), distances per 90 and the women-to-men speed gap are in sensible ranges.
- Hidden ratings and level scales are never served. The verifier walked 396 payloads.

## Must fix

### M1. Served realism notes state two failed checks, and one hollow pass, as facts

- **Where:** `src/regista/catalogue/realism.py` `realism()`, served as `metric.realism` by `/api/catalogue/rank`,
  `/api/competitions/{id}/players` and the terminal endpoints with `competition=`.
- **What is served:**
  - `/api/catalogue/rank?metric=peak_speed_mean&competition=co_gha_u17` returns `kind: "band"` with the note "mean peak
    match speed of U17 outfielders within 26.8 +/- 1.9 km/h". There is no verdict. The measured level value is
    **29.68 km/h**, which fails the band (engine.md).
  - `pass_pct` in `co_esp_am_men` is served with the note "amateurs complete fewer passes than semi-pros". The data
    says the opposite: 81.38% against 80.53%.
  - "Women lose the ball more often than men (semi-pro)" is served as a passed order on a 0.05-per-90 margin (12.73
    against 12.68), which is noise.
- **Why it must be fixed:** a reader takes each note as a property of the numbers shown. That breaks non-negotiable 5:
  nothing may be claimed that the data does not support.
- **Fix:** serve the committed verdicts with the value and the margin, for example "checked against 24.9-28.7 km/h
  [S5]: measured 29.68, fails". They could be stored beside `reliability.json`, since `band_checks` and `order_checks`
  already produce them. Alternatively, word the note as what was checked, not what is true. Mark margins inside noise
  as "not separated". Phase 5 must not quote these labels as findings.

### M2. Olivia King's career story contradicts her own fixtures

- **Where:** `define.py` `CAREERS[2]`, served as `career_story` by `/api/players/pl_msa_07/career` and
  `/api/catalogue/players/pl_msa_07`.
- **The contradiction:** the story says she plays for Oxenridge Women "outside the college season". Her matches are:
  - Mesa Alta College, California: 2026-08-22, 2026-09-12 and 2026-10-03;
  - Oxenridge Women, Yorkshire: **2026-09-06**, between two college matches. Her other Oxenridge match, 2026-11-29,
    does fit the story.
- `_career_dates` only prevents two matches on the same date. It does not stop alternating weekends on two
  continents.
- **Fix, either:**
  - reword the story (cheap, no pins move); or
  - move the destination fixtures of the college-to-home careers outside the US season (after mid-November, or
    January to July). Fixture dates are in `events.jsonl`, so the moved matches get new pins.

## Should fix

### S1. U17 speeds are implausible for 15 and 16 year olds

- **The numbers:** U17 outfielders' match peak speeds (Ghana) have a median of **30.2 km/h** and a maximum of
  **34.4 km/h**. The level mean is 29.68 km/h against the sourced 24.9-28.7.
- A 16-year-old at 34.4 km/h is at the top end of elite senior football. Any scout watching youth football would
  notice.
- **Cause (engine.md):** the × 0.92 multiplier comes from a sprint-test maximum (30.7 km/h, S6), but generated players
  reach 94-97% of capacity in a match. The same research line (S5 and S6, both from highly trained academy cohorts)
  puts the match peak at about 0.87 of the test maximum.
- **Fix:** lower the youth speed multipliers, or lower the share of capacity youth reach in a match. Either moves the
  catalogue pins and the level reliability table. This is Zaid's call, but it should be decided before the demo shows a
  youth profile. If it is accepted as it is, M1 still applies.

### S2. The levels barely differ in event data

- The ratings differ by level. But both sides of a match scale together, so most outcome rates cancel out
  (engine.md's level aggregates):
  - pass completion is 79.0-81.4% at every level, with amateurs above semi-pro men;
  - ball losses are 12.1-13.4 per 90 everywhere;
  - U20 scores the fewest goals (0.79 per team per 90) and amateurs score as many as semi-pros (1.21 against 1.20).
- Real football runs the other way: pass completion falls clearly below the professional line, and youth and amateur
  matches tend to be higher scoring, not lower.
- Only the physical metrics separate the levels, and those are modest.
- So the claim that "levels genuinely differ" holds for the hidden ratings and for pace. It does not hold for most of
  what a scout reads.
- **Fix, either:**
  - add a level-relative passing and retention effect (design.md §5.2, which moves pins; Zaid's call); or
  - state this plainly in phase 5's report, and say in the `all`-scope warning that raw event rates do not encode
    level.

### S3. The default cross-catalogue leaderboard mixes levels and genders and rewards tiny samples

- **Where:** `/api/catalogue/rank`, the `sort` of `/api/catalogue/players`, and the MCP tool
  `search_catalogue_players`.
- **Example:** `/api/catalogue/rank?metric=np_goals&position=FW` with no filters ranks by raw per-90 value:

  | Rank | Player | Competition | Minutes |
  |---|---|---|---|
  | 1 | Ulises Perez | USA college men | 83 |
  | 2 | Mason Nelson | USA college men | 83 |
  | 3 | Sergio Cruz | Spain amateur | 50 |
  | 4 | Richard Amoah | Ghana U17 (pool of 5) | 52 |
  | 5 | Femi Toure | England semi-pro men | 274 |
  | 9 | Hannah Mitchell | England semi-pro women | 60 |

- The board ranks a women's player among men. That contradicts the design's "genders never mix". A Scout agent asked
  for "the best young striker" gets this list.
- **Fix:** with no level filter, rank by percentile within each row's own pool, with the value as a tie-break. Apply
  a gender filter by default, or split the board by gender. Keep raw-value ranking as an explicit option.

### S4. The `noisy` flag ignores the row's own sample size

- The level tables were measured on half-seasons with a median of 85-142 minutes. Sparse rows have 45-60 minutes.
- At every level, 13-24 metrics have a split-half r between 0.3 and 0.5. Rows at 45-60 minutes are served
  `noisy: false` for these metrics, although adjusting r to their sample would put most of them below 0.3.
- **Example:** r = 0.45 measured at 142 minutes, applied to 60 minutes, gives 0.26.
- **Fix:** adjust r with Spearman-Brown to the row's minutes: r_k = k·r / (1 + (k−1)·r), with
  k = minutes / `median_half_minutes`. Flag the row when r_k < 0.3. This is pure engine code; nothing regenerates.

### S5. The Spanish careers are not possible under Spanish registration rules

- Sergio Cruz (and, in the same way, Alberto Navarro) plays for UD Sotoalto Juvenil in Castile and León on
  2026-09-05 and 2026-11-28. He plays for CF Torrevalle in the Valencian Community on 2026-10-24 and 2026-11-14.
- That is two different clubs, in regions hundreds of kilometres apart, in alternating weeks of one season.
- A Spanish player holds one federation licence a season. A *juvenil* steps up to his own club's senior side, or to
  an affiliated one, in the same territorial federation.
- **Fix, either:**
  - make the senior amateur club the juvenil's own or an affiliated senior side, in one region (relabel the regions or
    choose other clubs); or
  - tell it as a mid-season move with no interleaving.

### S6. Youth birth dates break the countries' age cut-offs

- Ages are drawn as of 1 August 2026, so the U17 and U19 squads hold players born before those countries' calendar-year
  cut-offs:

  | Competition | Cut-off (calendar year) | Players born too early |
  |---|---|---|
  | Ghana U17 | born 2010 or later | 21 of 72 (born 2009) |
  | Spain U19 (juvenil 2026/27) | born 2008-2010 | 16 of 90 (born 2007) |
  | Morocco U19 | born 2008 or later | 7 of 72 (born 2007) |

- England U18 has 4 players born in August 2008, before the 1 September school-year cut-off. Brazil U20 is clean.
- **Fix, either:**
  - state the cut-off rule in the labels and taxonomy ("ages on 1 August 2026"); this is cheap; or
  - draw each person's date of birth within the country's rule; this moves pins.

### S7. "Semi-pro" England plays at Premier League physical levels, and the note understates it

- England's peak speeds reach 36.7 km/h (Germany's 36.8), with a level mean of 31.46 km/h.
- The served note calls the Premier League bands an "upper reference". But the league was tuned to sit inside them.
  So the "semi-pro" reference level, and the absolute scale of every level anchored to it, is Premier League level.
- **Fix:** reword the note to say that absolute values on every level sit on a scale calibrated to Premier League
  rates and likely overstate real semi-pro football, so they should be read within pools. This is wording only. England
  stays byte-identical.

### S8. Women's sprint metrics use the men's 25 km/h threshold, with no flag on the number

| Competition | Median sprints per 90 |
|---|---|
| England semi-pro women | 3.3 |
| USA college women | 1.5 |
| England semi-pro men | 11.8 |

- Many women players have zero sprints, so their percentiles rank mostly zeros. The threshold caveat appears only in
  design.md §10.
- **Fix:** add a per-cell or per-metric note in women's pools, for example "men's FIFA zones; women's tournaments use
  19 and 23 km/h". Better still, compute women's zones for women's pools, which never mix with men's.

## Nits

- **Women's speed multiplier:** semi-pro women use × 0.83, but the cited derivation is 27.3 / 33.4 = 0.82. Their mean
  capacity (27.7 km/h) is also above the S3 high-level mean (27.3). Make the derivation match, or say why semi-pro gets
  0.83.
- **Sources to complete:**
  - S5 is very likely Al Haddad, Simpson, Buchheit, Di Salvo and Mendez-Villanueva (IJSPP 2015);
  - S4 is likely Curtis et al. (JSCR 2018);
  - S9 is likely Sæterbakken et al. (Sports Med Int Open 2019).

  Verify each before quoting authors. S5 and S6 may come from the same research group, so "two different studies"
  needs checking. S7 is cited in `taxonomy.LEVELS` but missing from `realism.SOURCES`.
- **Missing diacritics:** names drop them (Muller, Schroder, Kruger, Jimenez, Perez, Joao), while club names keep
  theirs (VfL Mövenstedt). Müller, Schröder, Jiménez and João would read more authentically.
- **NCAA format:** NCAA conferences play a single round robin plus non-conference games. A double round robin labelled
  "conference" is not how US college soccer works. Either relabel it, or accept it as a synthetic simplification and
  say so.
- **Calendar-year seasons:** Brazil's state youth championships and Japan's university league run within a calendar
  year. The "2026/27" label fits Europe and Africa; for Brazil and Japan, say "2026".
- **Real tier name:** "Regional Preferente" is a real Valencian tier name. It is fine as a level label, but this
  competition name is not wholly invented, unlike the others.
- **Hidden players in discovery:** `/api/competitions/{id}/players` defaults to qualifying minutes, so Morocco U19
  lists 11 of its 72 players (one club). For a catalogue of uploads, the UI round should list everyone who has footage
  and keep qualification for percentiles only.
- **Goalkeepers in outfield rankings:** an outfield metric's raw rank lists goalkeepers with `pool.size: 0`. For
  example, `rank?metric=distance&order=asc` lists keepers first.
- **Under-18 contact:** for the UI round, Messages with U17 and U18 players should go through the club or a guardian.
  This is a product touch for the recruitment story.
- **Possible sourced goals check:** public league tables give a goals-per-match figure for youth and amateur
  football. It would be an easy sourced check for S2's goal rates.

## Summary

The data model, the pools and the honesty plumbing are sound, and the catalogue reads as a recruitment product below
the professional line. Before sign-off:
- **Must fix:** the served realism notes (M1) and Olivia King's story (M2).
- **Should fix:**
  - youth speed (S1) and level separation (S2) need a decision from Zaid: retune, or state them plainly;
  - the default leaderboard (S3) and the sample-aware noisy flag (S4) are engine and API changes that regenerate
    nothing;
  - the careers (S5), the age cut-offs (S6) and the two notes (S7, S8) are believability and labelling fixes.
