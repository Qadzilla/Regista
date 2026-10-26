# Catalogue review B, closing round 3: football, data science and product

Branch `feature/catalogue`, 2026-10-25, reviewed at ebe3f4e (`git diff main...HEAD`). I focused on what changed since
review round 3 (fixes-3.md, levels.md, docs.md, verify-2.md and the closing rounds after them), and most closely on
closing fixes round 2: bece496 and ebe3f4e. I fixed nothing. This file is the only change in this round.

**Signed off.** I found no must-fix and no should-fix items. Everything left is a nit, or a modelling decision for
Zaid that is already served honestly.

## How I checked

Everything ran offline with `REGISTA_DOTENV=`. Nothing was sent to the live app, Azure or Fabric.
- **The closing round 2 fixes.** I read the diffs of bece496 and ebe3f4e against design.md §10, `realism.ORDERS` and
  `docs/catalogue/realism.md`. I also searched design.md, the data README, criteria.md, architecture.md, README and
  CLAUDE.md for any remaining [S9], [S2] or [S10] citation that claims more than its source.
- **The realism report.** `python -m regista.synth.report --catalogue` printed the committed `docs/catalogue/realism.md`
  (only stdout's trailing newline differs). I recomputed the measured match count from the competition files: 254 per
  season, times 6, is the stated 1,524.
- **One source, rechecked.** I read [S8]'s abstract record on Europe PMC (doi:10.1055/s-0030-1262838). Earlier rounds
  had confirmed that it exists but had not checked what it says.
- **Ages and dates, from the committed competition files.** I checked every squad's dates of birth against its age
  group, its competition's `eligibility` string and the `age_range` rule ("under N on 1 August 2026"). I also checked
  every competition's fixture window against `as_of`.
- **Rankings.** Through FastAPI's TestClient I queried `/api/catalogue/rank` for academy goals, women's tackles won and a
  single-country query, and `/api/competitions/{id}` for two competitions.
- **England.** `git diff main` shows no change to `data/season/league.json`, `season/pins.py` or
  `tests/test_backcompat.py`. `tests/test_catalogue_backcompat.py` and its data were last touched in ab3bb02, where they
  were recorded on main's code.
- **Tests.** Quick suite and slow suite, results below.
- **Accepted, not repeated.** The verifier's rebuilds and pin drift, Femi Toure's goals, the privacy walk and the app
  walk. No commit since then touches the generator, the pins, the engine or the API.

## What closing round 2 achieved

| Close 2 finding | Status | What I checked |
|---|---|---|
| Review A S1 / B: design.md §10 still cited [S9] and [S2] for orders they do not support | **Fixed** | The amateur row now has pass completion and ball losses as "a direction extended from [S10] ..., not reported at these levels". The sprint order is an **assumed order**, against [S9] and [S15], which matches `amateur_sprint_distance` (`basis: assumed`, `contrary`). The women vs men row cites [S1] only for the ≥ 20 km/h order and [S1, S12] for the pass gap, as served. It marks the second-half drop "not checked", which matches `NOT_CHECKED`. The academy row keeps U17 < U18 as sourced [S8] and marks every step past each source's span as assumed. Peak speed is marked "holds by construction", as `youth_peak_speed_mean` serves it. A line above the table says the served checks supersede it. [S15] is in design.md's source list with the same citation realism.md serves. design.md lines 359-369 now agree with the table. No [S9], [S2] or [S10] citation in the docs claims more than its source. |
| Review B S-1: the data contract said "89 built catalogue matches" | **Fixed** | The README reads "on the 60 catalogue matches", and fixes-close1.md §1 carries the dated correction. That matches the competition files: 60 uploaded fixtures, plus England's 30, which have no `execution`. |

The counts are the same everywhere they are quoted:
- 10 sourced checks (1 band, 9 orders), all pass: 3 calibrated, 7 scaled, 8 orders extended;
- 7 assumed orders: 6 hold, and running distance U18 < U19 fails.

They appear in realism.md, CLAUDE.md §2.11 and §4.2, the data README's "Realism per level" and criteria.md.

## The lens, end to end

**Believable levels.**

Pass completion runs:
- men: semi-pro 80.5, college 77.2, amateur 72.1;
- youth: U20 77.5 down to U17 69.4;
- women: about 8 points below men of the same tier.

Ball losses mirror pass completion. Fouls and tackles won rise down the levels. Speeds:
- U17 match peaks sit on [S5]'s mean;
- women's match peaks (26.8 km/h) sit below the elite World Cup reference of 28.0-29.4 km/h [S14];
- women's total distance (10.1-10.2 km per 90) sits inside the elite positional range of 9.5-11.0 km.

Directness is limited to what can be measured: fewer passes per 90 at amateur level, an assumed order. realism.md says
"no source was found" for long-ball share, rather than inventing a band.

Each served check says how the build relates to it (calibrated, scaled or extended). The headline says none of it
independently validates football below the professional line. The only failure is shown, not tuned away.

**Sources say what is claimed.**
- [S8]'s abstract (Buchheit et al. 2010, 77 highly trained U13-U18 players, total distance and very-high-intensity
  activity) says match running performance increased with age. That supports the served label, "match running distance
  per 90 rises with age through U13-U18". See nit 1 on the single step.
- [S9] and [S15] are now cited only as evidence against the amateur sprint assumption, which is what their findings
  support.

**Honest dates.**
- `as_of` is 2026-10-24, and every competition's fixtures end on or before it:
  - the latest are Japan university, Spain amateur, Morocco U19 and Nigeria amateur, all on 10-24;
  - the earliest window opens on 08-08 (Germany semi-pro, Brazil U20).
- Every youth squad fits its own eligibility rule and the `age_range` rule:
  - Brazil U20's oldest player was born 2006-08-17, so he is under 20 on 1 August 2026;
  - England U18 players are 16.0-17.9 (born on or after 1 September 2008);
  - Spain's juvenil players were born 2008-2010;
  - Ghana U17 players are 15.1-16.6.
- College squads are 18.2-23.8.
- Career dates fit their stories (checked by the verifier, and consistent with the fixture windows above).

**Rankings a scout would trust.**
- Raw numbers are compared only within a level, and there is one board per level.
- A cross-level answer carries a warning that a raw number from one level is not a better or worse player than the same
  number from another.
- Every row carries its pool, its sample (minutes, appearances, club matches) and a noisy flag.

The short-sample problem remains (nit 2), but it is labelled on every row.

**Recruitment below the professional line.** The catalogue covers what a lower-league recruiter actually searches:
- semi-pro, amateur, college and U17-U20 academies;
- men and women, never pooled together;
- five careers that cross competitions without merging per-90 numbers;
- uploader and camera labels;
- camera type stated as a label only.

**Nothing overstated.**
- CLAUDE.md §2.11 and §4.2, the data README and criteria.md mark the catalogue "not merged, not deployed".
- They quote the realism counts with the calibration caveat.
- They state that the 60 pins were recorded on macOS, with Linux CI to follow on the PR.

## Nits (not needed for sign-off)

1. **[S8]'s trend is checked as one step.** The abstract reports an increasing trend over U13-U18 for total distance and
   very-high-intensity activity together. It gives no result for U17 against U18, nor for distance per minute alone.
   The served check tests only the U17 < U18 step (+172.8 m, 3.6 SE). That is a fair reading of a trend, and the label
   says "through U13-U18 (the catalogue's step: U17 < U18)". Adding "the abstract reports a trend, not each step" would
   make it exact.
2. **Short samples lead every board** (carried). Each academy goals board opens on one goal in 50-60 minutes from 2
   appearances: for example Tyler Webb, England U18, 1.81 per 90 in 49.6 minutes. Women's tackles won opens on 6 in
   48.6 minutes. Every row is flagged `noisy` with its sample, so nothing is hidden. Still, the UI round should demote or
   visibly mark rows under 90 minutes. With 3-8 uploads of 30 minutes per competition, few players reach 90.
3. **Season labels on calendar-year competitions.** `/api/competitions/co_bra_u20` serves `season: "2026/27"` beside its
   own eligibility text, "a 2026 Sub-20 competition". Japan's university league also runs on the calendar year but is
   labelled 2026/27. Both are invented competitions and every date is inside the as-of window, so nothing is false. A
   per-competition season label ("2026") would match the calendar each eligibility rule already names.
4. **Carried from earlier rounds, unchanged:**
   - levels.md's "12 sourced checks (1 band, 11 orders)" and "142.0 m, 4.4" contradict the committed file, and there is
     no pointer to realism.md;
   - `taxonomy`'s women's speed source still reads "sourced [S3]", a sprint-test ratio (never served);
   - [S7] is missing from `realism.SOURCES`;
   - the student-athlete stories do not say "as a registered amateur";
   - U19 is the lowest-shooting level and scores less than U18;
   - the youth speed curve's largest step is U20 to senior;
   - boards come in competition order, not level order;
   - a single-level answer returns `boards: []`;
   - pool ties share a rank;
   - architecture.md's MCP table omits `rank_by`;
   - the 29 stale, git-ignored pre-date-fix folders remain in `data/catalogue/matches/` (not served).

## Zaid's call, or outside this lens (not judged)

- **The amateur sprint assumption** runs against [S9] and [S15]: amateurs get 208 m against semi-pros' 233 m per 90 at
  25 km/h or more. It is served as an assumption, with that evidence. Moving amateur speed and stamina back towards
  semi-pro is a modelling choice and would regenerate the catalogue.
- **Execution sizes** other than the women's are assumptions. The failing assumed order (distance U18 < U19) stands as
  shown.
- **Linux CI** has not yet run the 60 catalogue pins or the report tests. The PR's CI is their first run and should be
  green before merge.

## Tests

Run on the Mac with `REGISTA_DOTENV=` at ebe3f4e:
- Quick suite: 980 passed, 15 deselected. I ran it twice, once alone (6 min 45 s) and once beside the slow suite
  (5 min 0 s).
- Slow suite: 15 passed, 980 deselected (3 min 45 s, run beside the quick suite).

CLAUDE.md's "980 quick tests and 15 slow" is correct. `tests/test_backcompat.py` and
`tests/test_catalogue_backcompat.py` pass inside the quick suite, untouched.
