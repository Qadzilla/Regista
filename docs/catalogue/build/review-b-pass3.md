# Catalogue review B, round 3: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at bb99e4e (`git diff main...HEAD`, focusing on the round 2 fixes).
I fixed nothing.

**Not signed off.** Two new should-fix items, and the two round 1 items that wait on Zaid's decision are still open.
There are no must-fix items.
- New: 33 of the 60 uploaded catalogue matches are dated after today, so the catalogue holds footage of matches that
  have not been played yet.
- New: across levels, "most goals" ranks by each row's percentile within its position, so a defender with one goal
  comes out above Femi Toure's five. The rank rule's "desc lists the largest numbers first" is not true in that mode.
- Still open, Zaid's call: the U17 match speeds, and how little the levels differ in event data.

Everything was checked offline with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric.
- I read the fix diff (`bb99e4e`), `fixes-2.md`, `realism.json`, `realism.py`, `tools.py`, and the competition and
  match files.
- I queried `/api/catalogue`, `/api/catalogue/rank`, `/api/players` and `/api/terminal/{screen,rank}` through FastAPI's
  TestClient.
- I counted fixture dates, goals and shots from the committed competition files and match streams.
- I ran the back-compat, catalogue API and catalogue metrics tests: 77 passed.
- I did not repeat the verifier's checks (the England pins, Femi Toure's 5 goals, the pool arithmetic, the full
  suites). Linux CI has still not run on this branch.

## Round 2 findings: what the fixes did

| Round 2 | Status | What I checked |
|---|---|---|
| A #1 `order` meant opposite things in the two modes | **Fixed for lower-is-better metrics** | `/api/catalogue/rank?metric=fouls&position=MF&order=desc` across levels now starts 4.98, 5.97, 3.83, 4.84, the lowest percentiles first. With no order it lists the fewest fouls first (0.0 at the 94th percentile). See S-B below for higher-is-better metrics across positions. |
| A #2 `/api/players` mixed levels and genders | **Fixed** | The response carries `rank_by: pool`, `rank_rule`, and `boards` (men's 166 rows at offset 0, women's 82 at offset 166), plus each card's `board`. The terminal catalogue payloads carry `rank_by`, `rank_rule` and `boards`. |
| B #3 youth order notes overclaimed their sources | **Fixed** | `youth_distance` is now U17 < U18 only, sourced to [S8] (pass: margin 179 m, SE 37). `youth_distance_extension` and `youth_peak_speed_mean` are served as "Assumed order, no published band ([S8] covers U13-U18 only)". Peak speed adds "By construction: … tests the build, not football". Assumed orders never set `kind` or `verdict`: U19 distance and U18 peak speed are kind `none`. The served notes read correctly, and `recheck-realism` re-stamped the file without moving a measurement. |
| B #4 the women's board was hidden | **Fixed** | `/api/catalogue/rank?metric=np_goals&position=FW` gives `boards[1] = {women, ranked 20, offset 108, top: 5 rows}`. The MCP tool returns each board's top rows, with `total`/`shown` and a hint to pass `gender`. |
| B S-C U17 speeds | **Open, Zaid's call** | Unchanged: 29.68 km/h against a band of 24.9-28.7. The note says it fails. |
| B S-D levels barely differ in event rates | **Open, Zaid's call** | Unchanged. `ALL_WARNING` and engine.md say it plainly. |

## Should fix

### S-A. Most uploaded matches are dated in the future

- **Where:** `src/regista/catalogue/define.py` `round_dates` (rounds spread over `Competition.window`, default
  2026-08-15 to 2027-05-15) and the coverage draw. The dates are served in `/api/catalogue` (`dates`), on
  `/api/catalogue/matches`, and in every match record's `date`.
- **What is in the data:** 33 of the 60 uploaded catalogue fixtures are dated after 2026-10-25, today. That covers
  every upload in some competitions:

  | Competition | Upload dates |
  |---|---|
  | Ogun Riverside Amateur League | 2026-11-21 to 2027-03-27 |
  | Liga Amateur del Valle Alto | 2026-12-05 to 2027-05-22 |
  | Ashanti Colts Academy League U17 | 2026-10-31 to 2027-04-17 |

  Most others run into March or April 2027.
- **The England semi-pro men competition** played its 10 rounds between 2026-08-15 and 2026-10-17. Its season is over
  in the fiction, while the rest of the catalogue holds uploads from the next seven months.
- **Why it matters:**
  - Regista is now a catalogue of *uploaded footage*. Footage of a match cannot exist before the match is played.
  - Judging runs from 2026-10-27 to 2026-11-10, and the dates are visible in the competition list and the match lists.
  - Some career stories depend on these dates: Olivia King on 2026-11-29, Finn Schmidt on 2027-01-23, Edson Jimenez on
    2027-03-27.
- **Fix:** give the catalogue an "as of" date (for example 2026-10-24) and draw uploads only from rounds dated on or
  before it. Each country's calendar can stay honest: a competition that starts later in the season contributes its
  opening rounds, or its window moves. Re-record the catalogue pins and reword the career stories.
  - This moves the 60 catalogue pins and perhaps the measurement fingerprint. England is untouched.
  - If Zaid prefers not to move data, the alternative is to say so: label the catalogue as a full imagined 2026/27
    season, and keep dates out of anything a judge sees.

### S-B. Across levels, "most goals" ranks by percentile within each position: a one-goal defender tops it

- **Where:** `CatalogueMetrics.order_rows` in pool mode, used by:
  - `/api/catalogue/rank`;
  - `/api/players` in catalogue mode (`players_payload`, `sort_percentile`);
  - `/api/terminal/{screen,rank}` in catalogue mode;
  - the MCP tool `search_catalogue_players`.

  The wording at fault is in `RANK_RULE` and in the `search_players` docstring: "order (asc or desc) is the raw
  direction in both modes: desc lists the largest numbers first" and "desc: the largest numbers first".
- **Reproduced:**
  - `/api/terminal/rank?metric=goals&country=England` returns:
    1. Otis Nakamura, DF: 1 goal, 0.31 per 90, 99th percentile of 44 defenders;
    2. Haruki Adeyemi, MF: 2 goals, 0.65 per 90, 98th percentile;
    3. Femi Toure, FW: 5 goals, 1.64 per 90, 98th percentile.
  - `/api/terminal/screen?metrics=goals&sort=goals&order=desc&country=England` and
    `/api/players?country=England&sort=goals` return the same order.
  - Without the catalogue filter, `/api/terminal/rank?metric=goals` returns Femi Toure first. Adding a country filter
    makes the league's top scorer third behind a defender who scored once.
- **Why it matters:**
  - Percentile within position is a fair way to read a single row. It is not an answer to "who scores most".
  - The friendly terminal maps "most goals" to `order=desc` and promises the biggest numbers first. In pool mode, desc
    gives the highest percentiles first, and that is not the same thing once the list mixes positions, or mixes levels
    that hold different pool shapes.
  - For recruitment, a scout asking "most goals in England" or "most tackles across U19" sees positions interleaved by
    an arbitrary comparison.
- **Fix:** no data moves.
  - In pool mode, when the selection holds more than one position, keep positions apart as genders already are. Either
    use a board per position, or rank by percentile only when a position is given and otherwise fall back to the
    value within each level's board.
  - Reword `RANK_RULE` and the tool docstring: in pool mode, desc means the highest percentiles first, which are the
    largest numbers *relative to each row's pool*, not the largest numbers.
  - Add a test: a mixed-position, mixed-level `goals` rank must not put a defender above the competition's top scorer
    without saying it ranked within positions.

### S-C. U17 match speeds are still implausible (round 1 S1; open, Zaid's decision)

The data is unchanged. Ghana U17 outfielders, aged 15 and 16, have a mean peak match speed of 29.68 km/h against the
sourced band of 24.9-28.7 km/h. The served note says it fails.
- Either retune the academy speed multipliers, which moves the youth pins and the level reliability table.
- Or accept it in CLAUDE.md §2.11 (phase 5).

Decide before any youth profile or youth leaderboard appears in the demo.

### S-D. Levels differ in ratings and pace, not in most event rates (round 1 S2; open, Zaid's decision)

The data is unchanged:
- amateur pass completion is 81.38%, above semi-pro men's 80.53%;
- semi-pro women and men differ in ball losses by 0.05 per 90;
- goals per 30-minute match vary between competitions more by sample than by level (US college women 0.20, US college
  men 1.50, from 5 and 6 uploads).

Either build design.md §5.2's level-relative passing and retention effect, which moves every catalogue pin, or record
the acceptance in phase 5, so the pitch never says levels differ in what a scout reads.

## Nits

- **Pools without spread:** on `/api/catalogue/rank?metric=np_goals&position=FW`, the women's board's top 5 shows Hannah
  Mitchell (1.5 per 90, 95th), then four US college women forwards tied at 0.0 and the 50th percentile. All nine
  forwards in that pool scored no non-penalty goal: the competition has one goal in 5 uploads. A pool where every
  qualified value is equal carries no information. Flag it, for example `pool.no_spread: true`, or give no percentile.
  Its zeros otherwise outrank zeros in pools where somebody scored.
- **Short uploads at the top:** Sergio Cruz (50.4 minutes, 1 goal) ties Femi Toure (274 minutes, 5 goals) at the 98th
  percentile on np_goals. Both are `noisy`, and r_at_minutes is 0.024 against 0.188. This is carried from round 2:
  demote within equal percentiles, or make r_at_minutes prominent in the UI round.
- **Phase 5:** the realism report should quote the sourced/assumed split exactly as `realism.json` now serves it. Source
  entries S4, S6, S9, S10 and S11 still lack authors or a year, none has a DOI or URL, and the ±1.9 of the U17 band is
  still unconfirmed. S10 is a small-sided-games study behind a match-level order.
- **Carried from round 2:**
  - Term time in careers: Finn Schmidt plays on 2027-01-23 and Edson Jimenez on 2027-03-27. S-A's fix would remove
    both.
  - The Spanish affiliation is recorded only in story text.
  - Unqualified cells return `pool.reason: null`.
  - Clubs with one 30-minute upload can never qualify under the 45-minute floor (three Moroccan clubs).
- **Linux CI** has not run the 60 catalogue pins or the new API tests. The PR will be the first Linux run.

## What is good

- The youth realism notes now claim exactly their sources' span. "By construction" on the peak-speed order is the honest
  label. Assumed orders are measured, shown and never counted, and the committed verdicts re-derive from their own
  aggregates.
- No board hides behind another: every list says where the women's board starts and shows its top rows, and the MCP
  tool tells an agent how to read further.
- `order` for lower-is-better metrics now means the same thing in both modes, and every catalogue payload says how it
  ranked (`rank_by`, `rank_rule`, `boards`).
- The structure still serves recruitment below the professional line:
  - 14 competitions in 10 countries, with uploader and camera labels;
  - pools by tier, age group, gender and position, with sizes and small-pool flags;
  - careers kept as one row per competition.
- The England semi-pro men competition is untouched, and the default app answers as on main.
