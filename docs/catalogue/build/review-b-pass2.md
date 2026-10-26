# Catalogue review B, round 2: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at e5ca6ae (`git diff main...HEAD`, focusing on the round 1 fixes). I fixed
nothing.

**Not signed off.** The round 1 fixes hold up, but four should-fix items remain:
- two are new: youth order notes overstate their sources, and the women's board is hidden from default lists and from the
  MCP tool;
- two carry over from round 1 and wait on Zaid: the U17 speeds and how little the levels differ in event data.

There are no must-fix items.

I checked everything offline, with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric:
- read the fix diff (`1c5e483..e5ca6ae`), `fixes-1.md`, `realism.json`, the taxonomy, definition, metrics, API and MCP tool code;
- queried `/api/catalogue/rank`, `/api/catalogue/players` and `search_catalogue_players` through FastAPI's TestClient and
  in-process;
- recounted birth years and career fixture dates from the committed competition files and match streams;
- ran the back-compat and catalogue tests (89 passed). The verifier's checks were not repeated: the England pins, Femi
  Toure's 5 goals, the pool arithmetic and the full suites.

## Round 1 findings: what the fixes did

| Round 1 | Status | What I checked |
|---|---|---|
| M1 realism notes stated failed checks as facts | **Fixed** | The U17 note now reads "29.68 km/h: fails, 0.98 km/h above the band". Amateur pass completion is a fail. Women's ball losses (semi-pro) are "not separated" (0.05 against noise of +/- 0.24). Verdicts come from the committed `realism.json`, with values, margins and standard errors. The 2-standard-error rule is applied consistently, including U19 to U20 distance at 2.02 SE (pass). |
| M2 Olivia King's story | **Fixed** | Her fixtures: Mesa Alta 08-22, 09-12 and 10-03; Oxenridge 09-06 (its round 1) and 11-29. They fit the reworded story. |
| S1 U17 speeds | **Open, Zaid's call** | Not retuned. The served note is now honest (see S-C below). |
| S2 levels barely differ in event data | **Open, Zaid's call** | Not retuned. Now stated plainly in the mixed-level warning and in engine.md (see S-D below). |
| S3 mixed leaderboard | **Fixed, with a gap** | Rows rank by percentile within their own pool, and genders have separate boards. Femi Toure is first among men on np_goals (98th percentile, pool of 33). FBref's percentile caps small pools (at most 90 with 5 peers), which limits the tiny-sample effect. Gap: see S-B. |
| S4 noisy ignored the row's minutes | **Fixed** | `reliability_at` is Spearman-Brown, k = minutes / median half-season minutes, served as `r_at_minutes`. England's competition scope keeps its own table. The formula is correct. |
| S5 Spanish careers | **Fixed** | Both Spanish competitions are now in the Valencian Community. Sergio Cruz (17, born 2009) and Alberto Navarro (18, born 2008) are both juvenil-eligible. Sotoalto Juvenil and CF Torrevalle even share a kit. Only the five U19 pins moved. |
| S6 youth birth dates | **Fixed** | Birth years now: Ghana U17 2010-2011 (ages 15-16); Spain U19 2008-2010; Morocco U19 2008-2010; England U18 from 2008-09-15 to 2010-07-21 (inside 1 Sep 2008 to 31 Aug 2010); Brazil U20 2006-2009. Age only touches ratings after 29 to 30, so shifting youth birth dates leaves ratings consistent. The Feb 29 case is handled. |
| S7 Premier-League-calibrated scale | **Fixed** | Every level note says it. |
| S8 women's zones | **Note fixed** | `threshold_note` and `zone_note` are on the five zone metrics in women's cells. Computing women's own zones is still open (Zaid's call, moves the women's pins). |

## Should fix

### S-A. Youth order notes say the sources report age steps the sources do not cover

- **Where:** `src/regista/catalogue/realism.py`, the order checks `youth_peak_speed_mean` [S5, S6] and `youth_distance`
  [S8]. They are served in `metric.realism.note` for every academy and semi-pro men's level, for example
  `/api/catalogue/rank?metric=distance&competition=co_eng_u18`.
- **What is served:** "Order check [S8]: the source reports that match running distance per 90 rises with age: U17 <
  U18 < U19 < U20 < senior". The note for peak speed has the same wording.
- **What the sources cover:**
  - realism.py's own source entry says S8 covers U13-U18. design.md says S8's "running output rose with age
    (U13-U18)", and that S6 studied U13-U17 and S5 reports U13 and U17.
  - None of them can report the U18 to U19, U19 to U20 or U20 to senior steps. Those steps are the build's assumption,
    and the U17 to U18 peak-speed step is also outside S5 and S6.
  - The youth speed scales are also interpolated between U17 and senior (`taxonomy.LEVELS`, "interpolated between U17
    [S6] and senior"). The peak-speed order is therefore built in by construction. Its "pass" checks the build's own
    assumption, not the source.
- **Why it matters:** this is the same class as round 1's M1, a served note that claims more than its evidence.
  Non-negotiable 5 says nothing is claimed that does not run or is not sourced.
- **Fix (wording only, no pins move):**
  - split each order into its sourced span (U17 to U18 for distance [S8]) and an assumed extension, worded as such, for
    example "assumed to continue to senior (no published band)";
  - mark the peak-speed steps "by construction (interpolated scale)";
  - update the labels in `realism.json` (re-stamped) and the phase 5 report to match.

### S-B. The women's board is hidden from default lists and unreachable from the MCP tool

- **Where:**
  - `catalogue_api._rank` and the `/api/catalogue/players` sort: `CatalogueMetrics.order_rows` puts the boards one
    after the other, men first;
  - `catalogue/tools.py` `search_players`, served as the MCP tool `search_catalogue_players`: `rows[:limit]`, default
    10, `MAX_LIMIT` 50, no offset.
- **What happens:**
  - `/api/catalogue/rank?metric=np_goals&position=FW` returns 25 men, ranks 1 to 25. The women's board (20 rows)
    starts at offset 108.
  - `boards` gives only `{"gender", "ranked"}`, with no starting offset or top rows.
  - The MCP tool returns 10 men and `"boards": ["men", "women"]`. It gives no per-board count, and it has no offset, so
    the women's board can never be reached without `gender=women`. The same holds for `tackles_won` across all
    positions.
  - So the Scout agent asked "who is the best finisher in the catalogue?" sees men only. That undercuts a catalogue that
    covers two women's competitions and promises separate boards.
- **Fix (new endpoints and tool only, no data moves):**
  - return each board's top rows (`limit` per board), or give each board its `offset` and a `top` slice in `boards`;
  - in the MCP tool, return per-board rows, or at least the count of each board with a hint to pass `gender`;
  - add a test in which a mixed-gender rank surfaces women's rows on its first page or call.

### S-C. U17 match speeds are still implausible (round 1 S1; open, Zaid's decision)

- The note is honest now: "fails, 0.98 km/h above the band".
- The data has not changed: Ghana U17 outfielders run peak match speeds with a median of about 30 km/h and a maximum of
  34.4 km/h, and these are 15 and 16 year olds.
- Decide it before any youth profile or youth leaderboard appears in the demo. If it is accepted as it is, record that
  decision in CLAUDE.md §2.11 (phase 5).

### S-D. Levels differ in ratings and pace, not in most event rates (round 1 S2; open, Zaid's decision)

- The warning now says this plainly.
- The task's own wording was that ratings are scaled "so levels genuinely differ". That holds for the hidden ratings and
  physical capacity. It does not hold for pass completion, ball losses or goals: amateur pass completion is above
  semi-pro men's.
- Either build the level-relative passing and retention effect (design.md §5.2, which moves every catalogue pin), or
  record acceptance in phase 5, so the pitch never says levels differ in what a scout reads.

## Nits

- **Sources (phase 5):** S4, S6, S9, S10 and S11 still have no authors or year, and no entry in `realism.py` has a DOI
  or URL. design.md has one for S6, but the served `sources` do not. The ±1.9 of the U17 band is still unconfirmed.
- **S10** is a small-sided-games study. It is labelled "direction only", but it is still the evidence behind a
  match-level pass completion order. Say so in the phase 5 report.
- **Order verdicts and squad sampling:** the order verdicts measure match-to-match noise on fixed squads. Each women's
  level is one competition of 5 teams. A "pass" says these squads differ. It does not say a level would differ with
  different squads. One line in the phase 5 method would cover it.
- **Noisy rows at the top of boards:** on the cross-level boards nearly every top row is `noisy: true`, from uploads of
  50 to 90 minutes. Femi Toure at 274 minutes is the exception. Consider demoting noisy rows within equal percentiles,
  or make `r_at_minutes` prominent in the UI round.
- **Term time in careers:** Finn Schmidt plays in Germany on 2027-01-23, and Edson Jimenez plays in Mexico on
  2027-03-27. Both fall in US spring semester term time. The fall season has ended, so the stories hold, but a German
  lower league on 23 January also sits in the usual winter break. Reword, or accept.
- **Spanish affiliation:** it lives only in the story text. No club field records it. Sotoalto and Torrevalle share
  kit colours; Navalcastro and Riuseca do not. The UI cannot show the link.
- **Spanish place names:** the Spain U19 clubs (Valdecarro, Navalcastro, Pinarejo, Peñaroble) keep Castilian
  meseta-style names after the move to the Valencian Community. That is plausible for the Castilian-speaking interior,
  but the amateur league's clubs (Benialcor, Riuseca, Camp de l'Horta) read Valencian.
- **Unqualified cells:** these still return `pool.reason: null`, as the verifier noted. The UI round should say "under N
  minutes".

## What is good

- The realism block is now properly honest. Bands and orders carry values, margins, standard errors and pass, fail or
  "not separated". Notes say "the source reports … measured …", and verdicts come from a committed, fingerprinted
  file that the image smoke test checks.
- Ranking by percentile within each row's own pool, with genders apart and `rank_by=value` as an explicit option, is
  the right default for a cross-country, cross-level catalogue.
- The Spearman-Brown noisy flag is correct, and it really does flag short uploads.
- Birth-date eligibility is a public label that matches each country's convention, applied without moving a rating or
  a pin.
- England (the Regista League) is untouched. Its catalogue cards now count uploads and claims like today's cards, and
  `basis` / `profile_only_matches` explain the league-only metrics.
