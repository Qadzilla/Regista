# The catalogue: independent verification 2 (after levels and phase 5)

Branch `feature/catalogue` at 76477ad, 2026-10-25, on Zaid's Mac (macOS arm64, Python 3.13). I did not rely on the
reports in fixes-3.md, levels.md and docs.md. Each claim below was checked by rebuilding the data into empty folders,
recomputing numbers from raw event streams, calling the app, or reading the cited papers. Nothing was pushed or merged.
Nothing was sent to the live app, Azure or Fabric. Tests ran with `REGISTA_DOTENV=` (empty, so `.env` is never loaded).

## Verdict

| Check | Result |
|---|---|
| England semi-pro men unchanged; Femi Toure has 5 goals, none a penalty, two clear | **Pass** |
| 60 catalogue matches built twice into empty folders: identical, equal to the pins | **Pass** |
| No uploaded match dated after the as-of date (2026-10-24) | **Pass** (90 of 90) |
| "Most goals in England" and other mixed-position lists, on every surface | **Pass** (6 surfaces) |
| Two level checks recomputed from raw streams | **Pass** (exact to the reported decimals) |
| Every source in realism.md and design.md exists and says what is claimed | **Exists: 14 of 14. Wording overclaimed in 4 places: fixed** (§6) |
| CLAUDE.md §2.11 and the docs claim nothing that does not run | **Pass** |
| The current app works offline | **Pass** |
| Privacy walk over the new payloads | **Pass** (336 GET payloads, 8 MCP results, 0 hits) |
| Quick and slow suites | **Pass** (979 quick, 15 slow, after my fixes) |

## 1. England semi-pro men and Femi Toure

- `data/season/league.json` has SHA-256 `04dbb30f…0b1a34`, the same as on `main`.
- `git diff main` shows no change to `src/regista/season/pins.py` or `tests/test_backcompat.py`.
  `tests/test_catalogue_backcompat.py` exists only on this branch (recorded on main's code in ab3bb02) and was not
  touched since.
- I rebuilt all 30 fixtures into an empty folder (`season.build.build_all`, 10 workers, 5.9 s).
  `season.pins.drift` returned `{}`.
- I counted goals from the raw `events.jsonl` myself, mapping each `player_id` to its `global_player_id` from the match
  header:
  - Femi Toure (`pl_bro_09`) scored 5 goals: round 1 at 5' and 55' (a header), round 6 at 48', round 8 at 5', and
    round 10 at 7'.
  - Next best: Leon Whitfield and Amari Ustinov with 3 each, so he is two clear.
  - The season has one `penalty` event (round 4, taken by `pl_dun_10`). None of Femi's goals follows a penalty.

## 2. Catalogue matches: determinism and pins

- I built all 60 into two empty folders: 10 processes (11.4 s), then 1 process (74.8 s).
- `catalogue.pins.drift` was `{}` for both builds.
- `diff -r` between the two builds: identical.
- Every file of both builds is also byte-identical to the folders in `data/catalogue/matches/`.
- `python -m regista.catalogue check` and `define --check` pass.
- Not checked here: Linux. The 60 pins were recorded on macOS. The PR's CI is their first Linux run.

## 3. The as-of date

- `catalogue.json` has `as_of: 2026-10-24`, and `/api/catalogue` serves it with its note.
- From the match headers of the 90 rebuilt streams (60 catalogue and 30 England), the latest date is 2026-10-24
  (Ogun Riverside Amateur League). None is later.
- Each competition's dates fit its window. For example: Germany 2026-08-08 to 10-10; England women 08-16 to 10-11;
  Ghana U17 09-05 to 10-17.
- **Careers.** I checked the minutes from the physical records:
  - Olivia King: England women on 08-16, then US college on 08-22, 09-12 and 10-03.
  - Finn Schmidt: Germany on 08-08, then US college on 10-17.
  - Edson Jimenez: Mexico on 08-15, then US college on 09-12, 10-10 and 10-17.
  - The two Spanish players alternate U19 and amateur matches, never two on one date.

## 4. Ranking across positions and levels

I called the offline app (`REGISTA_DOTENV= uvicorn regista.api:app`, the repo's `regista-offline` entry, port 8040).

- **"Most goals in England" puts Femi Toure first on all six surfaces:**
  - `/api/catalogue/rank`, `/api/catalogue/players`, `/api/terminal/rank`, `/api/terminal/screen`, `/api/players`
    (with `country=England`), and the MCP tool `search_catalogue_players`.
  - The semi-pro men's board reads Femi Toure 1.64, Amari Ustinov 1.04, Leon Whitfield 1.03.
  - The other boards are England U18 (43 rows) and England women (32 rows). fixes-3.md's 39 and 33 predate levels.md,
    which re-recorded the catalogue.
- **Other mixed lists:**
  - I checked goals, tackles won, passes completed, xG and yellow cards, each with `country=England`, `country=Spain`,
    `tier=academy` and `scope=all`.
  - Each list gives one board per level, sorted by value within the board. No board mixes levels or genders.
  - The leaders are sensible: forwards lead goals and xG, midfielders lead passes completed and tackles won.
  - A defender can lead a level on goals when the numbers say so (Freya Robinson, 1.71 per 90 in England women). That
    is a raw count within one level, which is what the rank rule allows.
- **Position filter.** `position=FW` across levels gives `rank_by: pool`, one board per gender, with Femi Toure first.
  `rank_by=pool` across positions gives one board per gender and position.
- **Yellow cards.** `metric=yellow_cards` lists the fewest first unless `order=desc`. That follows the endpoint's
  "best first" default, because lower is better for cards. With `order=desc`, Noel Oliveira (4 cards) is first. Cards
  are totals, so their percentile is null.
- **Scope only.** On existing endpoints, `scope=all` alone keeps England semi-pro men's rows. Only the percentile pool
  widens. This matches the documented default ("England semi-pro men unless a filter picks others"). The catalogue's
  own endpoints default to every competition.
- **Nits, not fixed:**
  - Boards come in competition order (semi-pro men, U18, college men, amateur, ...), not level order.
  - With one level, `boards` is `[]` and each row's `board` is the gender.

## 5. Two level checks recomputed from raw streams

I wrote `levels.py` in the scratchpad. It imports neither `regista.season.metrics` nor `measure`'s aggregates.

- **Streams.** It regenerates the measurement seasons from the documented seed rule: each competition's full double
  round robin, seed `comp_seed*100+n`, plus `50,000,000 x (repeat+1)`, 6 repeats. It generates them with `generate`
  and `season.league.generate_kwargs`: 336 matches in 61 s on 10 cores.
- **What it counts:**
  - Pass completion: outfield players' `pass` and `cross` events, completed when `outcome == "success"`.
  - Peak speed: `peak_speed_kmh` from outfielders' physical records with `played_s >= 600`.

| Level | Measure | Mine | realism.json / realism.md |
|---|---|---|---|
| Amateur men (Spain, Nigeria, Mexico) | pass completion | 72.08% (69,455 passes) | 72.08 |
| Academy U17 (Ghana) | mean peak match speed | 26.80 km/h (1,536 player-matches) | 26.80 |
| Amateur men | mean peak match speed | 30.68 | 30.68 |
| Academy U17 | pass completion | 69.36 | 69.36 |

- `python -m regista.synth.report --catalogue` printed exactly the committed `docs/catalogue/realism.md`. The only
  difference was stdout's trailing newline.

## 6. Sources

I looked up every DOI on Europe PMC: authors, title, journal, year, volume and pages. I read the abstracts. For S9 and
S12 I read the full text (open access). I read the FIFA Training Centre pages for S11 and S14 and the LIDA record for
S6.

**All 14 exist as cited.** Authors, year and pages match for S1-S8 and S10-S14. S9's author list matches; PubMed spells
the first author Sæterbakken.

**What each source says, against what was claimed:**

| Id | Claim checked | Verdict |
|---|---|---|
| S1 Bradley 2014 | women lost the ball more and completed fewer passes (ES 0.5-0.9); men covered more distance at higher speeds; only women dropped in the second half | matches |
| S2 Datson 2017 | central midfielders 10,985 m, central defenders 9,489 m; output fell between halves | matches, but it has no men: it was cited for two women-versus-men orders. **Fixed** |
| S3 Vescovi 2012 | mean peak sprint speed 27.3 ± 1.4 km/h; maxima above 30 | matches |
| S4 Curtis 2018 | 9,367 ± 2,149 m per match, 18 players, 24 matches | matches |
| S5 Al Haddad 2015 | U17 peak match speed 26.8 ± 1.9 km/h; 87.2% of maximal sprinting speed; 180 U13-U17 players | matches. The ± is the SD across players, while the label read as a mean's range. **Reworded** |
| S6 Al Haddad 2012 (ECSS) | maximal sprinting speed 25.2 (U13) to 30.7 km/h (U17) | matches |
| S7 Mendez-Villanueva 2011 | U18 > U16 > U14 in sprint qualities; the differences disappear after adjusting for maturity | matches (design.md only) |
| S8 Buchheit 2010 | match running rises with age, U13-U18; very high intensity above 16.1 km/h | matches |
| S9 Saeterbakken 2019 | "amateurs sprint less than semi-pros" | **does not support it.** The full text: Level 1 sprinted 61% and 51% more than Level 2 and Level 4, "with no difference between Level 2 and Level 4 (p=0.756)". **Fixed** |
| S10 Dellal 2011 | amateurs completed fewer passes, lost the ball more, and covered less sprinting and high-intensity running | matches. The comparison is 20 French fourth-division amateurs against 20 **international** players, in small-sided games. **Now said** |
| S11 Bradley 2024 (FIFA TC part 2) | "teams 103.3 ± 4.4 km per match" | the page text gives 103.3 km on average and a match-to-match CV of 3.9%. **No ± 4.4** (nor the ± 0.6 and ± 0.3 in design.md). **Fixed** |
| S12 Pappalardo 2021 | pass accuracy 0.76 ± 0.08 (women) against 0.84 ± 0.05 (men); recovery time 19.58 against 27.32 s | matches (Table 2) |
| S13 Bradley 2013 | pass completion and passes 4-39% higher in the Premier League; more high-intensity running lower down | matches |
| S14 Bradley 2024 (FIFA TC part 3) | top speeds 28.0-28.1 km/h for defensive and central midfielders, 29.1-29.4 for attacking, wide and forward roles; author Paul Bradley, 6 Feb 2024 | matches |

**Fixed (6a60518 and the report's commit):**

- **`realism.py`:**
  - `amateur_sprint_distance` now cites S10. Its label says what S10 compares and that S9 found no difference between
    second-tier professionals and fourth-tier amateurs.
  - The women's 20+ km/h orders now cite S1 only.
  - The S11 reference now reads "teams covered 103.3 km per match on average … (match-to-match variation 3.9%)".
  - The U17 band label says the ± 1.9 is the SD across the study's U17 players and that the band is wide for a level's
    mean.
  - S10's entry names the two groups compared.
- **The verdicts file.** `data/catalogue/realism.json` was rechecked on its stored aggregates
  (`python -m regista.catalogue recheck-realism`), and `docs/catalogue/realism.md` was regenerated.
  - No verdict, count or measured number moved: still 11 of 11 sourced checks pass, and 5 of 6 assumed orders hold.
  - The fingerprint is unchanged.
- **`design.md`:** the same corrections, dated.
  - §4.3 no longer says "higher-standard players sprint more in Norway's three standards".
  - §10's women's reference and §14's S11 and S9 lines no longer carry the unverified ± values.
  - S10's "confirm the exact paper" line is closed.
- **`taxonomy.py`:** the amateur skill offset's internal source said "direction [S9, S10]". S9 measures running, not
  skill, so it now says [S10]. The string is never served or written to the data files, and `define --check` still
  passes.

## 7. CLAUDE.md §2.11 and the docs

I checked each factual claim against the data or by running it.

- **Counts.** 14 competitions in 10 countries; 60 new clubs (66 with England); 1,075 new people (1,183 with the
  league's 108); 60 uploads, 3-8 each, every club covered; 5 careers. The README's uploads per level (38, 5, 13, 10, 5,
  4, 8, 4, 3) are correct, and so is its uploader shape (`type` team or player). Cameras: tripod 24, drone 14, phone 12,
  broadcast 10.
- **Three MCP tools.** `list_competitions`, `search_catalogue_players` and `get_catalogue_player` appear in
  `python -m regista.mcp_server --list-tools`.
- **API routes.** All the routes named in architecture.md exist, and `/api/season?competition=…` answers from the
  catalogue.
- **Commands.** These run and exit 0: `catalogue define --check`, `check`, `competitions`, `levels`, `player pl_bro_09
  --scope level`, and `synth.report --catalogue`. The report's `--regenerate --level` path is exercised by the slow
  test.
- **Status claims.**
  - "11 of 11 sourced checks, 5 of 6 assumed, distance U18 < U19 fails", "979 quick and 15 slow": confirmed.
  - "Not pushed, no PR": true.
  - Nothing claims the live app serves the catalogue.
- **Small mismatch, not fixed.** architecture.md's MCP table lists `search_catalogue_players` without its `rank_by`
  argument.

## 8. The current app, offline

`REGISTA_DOTENV= uvicorn regista.api:app` on port 8040, through the repo's `regista-offline` launch entry, in the
built-in browser.

- `/`, `/me` (Femi Toure: 10 matches, 274 minutes, 5 goals), `/scout`, `/scout#terminal` ("Ready: 102 players, 127
  stats, 30 matches", England only as before) and `/players/pl_bro_09` (1.64 goals per 90, "the best of the league's 18
  forwards") all load with no console errors.
- The server log has no errors. The only non-200s were my own 422s: `limit` over 200, and a wrong parameter name.
- The server was stopped and its tab closed afterwards.

## 9. Privacy walk

- **HTTP.** I listed every GET `/api` route from `/openapi.json`, skipping video, crop, upload and job routes. Path ids
  were `pl_bro_09`, the five career ids, `co_esp_u19`, `co_eng_sp_men`, `cl_brookfield` and `rl_r01_eas_bro`. Each
  route ran with six parameter variants: none, `competition`, `scope=all`, `tier=academy`, `country=USA&include=career`
  and `gender=women`. That gave 336 JSON payloads.
- **What I searched for:**
  - every rating key;
  - every level-scale key, `execution` included;
  - `hidden`, `seed` and `seeds`;
  - every committed match and competition seed value.
- **Result: 0 hits.**
- **MCP.** The three tools were called with filters, `scope=all`, a career id, a name, an unknown id and a bad scope.
  That gave 8 results and 0 hits. Bad input returns `{"error": …}`.
- **Names.** Bios carry age, height, foot and nationality only. All names are invented, as before.

## 10. Tests

- After my fixes: quick suite **979 passed**, 15 deselected (4 min 23 s); slow suite **15 passed** (2 min 9 s).
- The catalogue files ran again after the taxonomy edit: 121 passed.

## 11. Open, not fixed (Zaid's call or a later round)

1. **`amateur_sprint_distance` is still a sourced order**, now on S10 alone: amateurs against internationals, in
   small-sided games. The one full-match study (S9) finds no difference between second-tier professionals and
   fourth-tier amateurs, and Djaoui 2017 (levels.md) finds none in peak speed.
   - Downgrading it to an assumed order would be the stricter reading. It would make 10 of 10 sourced checks and
     6 of 7 assumed orders.
   - That changes the counts quoted in CLAUDE.md §2.11 and §4.2, the data README and criteria.md.
2. **S10's comparison group.** `amateur_pass_pct` and `amateur_ball_losses` rest on the same S10 comparison against
   international players, applied here to semi-pro men. The label names it now, but the step from "internationals" to
   "semi-pro" is an extrapolation.
3. **The U17 band** applies an SD across players around a level's mean. The label now says so, but as a check of a
   mean it is generous (noted in verify.md too).
4. **Linux CI** has run neither the 60 catalogue pins nor the report tests.
5. **Ranking display nits:** boards in competition order rather than level order; `boards: []` with one level.
6. **architecture.md's MCP table** omits `rank_by`.
7. **Carried from earlier reports, unchanged:**
   - levels.md's two hand-written figures (12 sourced checks, 142 m at 4.4 SE), recorded in docs.md.
   - The failing assumed order (distance U18 < U19).
   - Execution sizes other than the women's are assumptions.
   - The review nits listed in fixes-3.md.
