# The catalogue UI port: the Scout pages

Branch `ux/catalogue` (on top of PR #39; not merged, not pushed). Written 2026-10-26 by the Scout builder, following
`port-map.md` §2.1-2.6 and the backend in `backend.md`. This round ports Find players, the agent panel, Competitions and
one competition's page, the Overview, Team needs and the Shortlist with Compare from the approved sandbox
(`.claude/worktrees/sandbox-ref/sandbox/scout.js` and `index.html`, head e041bfd) into `/scout`. Everything shown is
synthetic: invented players, clubs and competitions; countries and levels are labels.

**Zaid's port decisions, as built here.**
- **Minutes:** the engine's minutes are untouched. Compare's moment list shows the engine's `minute` ("Round 1 · 6'").
- **Noisy marks:** a ≈ follows every number the engine marks noisy. That covers the card's pool line, the agent's rows,
  shortlist items, Team needs rows and Compare cells. A one-line legend under the list uses the engine's `noisy_words`.
- **League fixtures only:** every number on these pages comes from the catalogue endpoints, which count England's league
  fixtures only. Femi Toure shows 5 goals in 10 matches over 274 minutes. His goals per 90 are 1.64, at the 98th
  percentile among 33 semi-pro men forwards. Player-view uploads are named, never counted: on the competition page under
  "Uploaded through the Player view", and as "added a match" on the Overview (from `not_counted`).
- **The Scout agent uses its catalogue tools:** `POST /api/scout/ask` with `where: "catalogue"`, for both engines.
- **One ranking rule, the engine's:** the browser never sorts or ranks players. Order, places, boards, none yet and the
  "N of M have any" lines all come from `/api/catalogue/players` and `/api/catalogue/rank`.
- "None yet" for zeros. Pool lines read "98th percentile among 33 semi-pro men forwards". Small pools carry their reason.
  Round, never matchday.

## What each page does now

### Find players (`/scout#find`)
- **Where to look:** Whole catalogue and My level ("My level: semi-pro men"). Maya's level is a persona seed,
  `demo.SCOUTS.maya.level` in `shared/demo.js`; it is not served.
- **Filters:** Name or club, Country, Level, Age group, Gender, Competition, Position and Sort by, in the sandbox's order,
  plus "Also show players without enough minutes for a percentile".
  - The Competition list follows the other filters, grouped by country.
  - The filters live in the address (`?tier=semi_pro&…#find`), so a search can be shared or reloaded.
- **Sort options:** goals per 90 (the default), assists, shots, key passes, take-ons won, nutmegs, passes completed,
  tackles won, interceptions, recoveries, saves, and minutes played. Labels come from `/api/metrics`.
- **The list:** `GET /api/catalogue/players?…&sort=&metrics=<sort + the cards' numbers>&limit=24`.
  - One board when everyone is at one level ("Everyone here: semi-pro men", 24 cards, then "Show all N").
  - Otherwise one board per level (4 cards each, "Show all N"), or one per gender for one position across levels (pool
    mode). These are the engine's `boards`.
  - "Show all" pages the board through its `offset`, 200 rows at a time.
- **The status line:** the count with enough minutes, competitions and countries, the footage date, "N more without enough
  minutes" (a second request at `min_minutes=0`), the goalkeeper note, the career note, and "synthetic data, invented
  names".
- **The rule line:** the engine's mode in plain words. Across levels it adds the warning with "Why?".
- **Each board:** "20 of the 110 players on this list with enough minutes have any goals so far. The 90 with none are
  listed last, with no place number", from the board's `with_any` and `none_yet`.
- **Cards:** place (the engine's `rank`), shirt, name, position, club and the shortlist stage. Then competition, country
  and the level chip; three numbers per 90 with bars (none yet has an empty bar); the pool line of the sort stat with ≈
  and the small-pool flag and its reason; the sample ("10 matches · 274 minutes in Regista League") and "also plays in …".
  - The app's star (shortlist) stays on the card. In the sandbox the card was one link.
- **Goalkeepers:** with no position picked, a list sorted by a metric holds only the positions that metric is scored for.
  These come from the metrics engine's `positions` and are sent as `position=DF,MF,FW`.
  - A goals list leaves keepers out and says "goalkeepers left out of this sort (pick Goalkeeper to see them)". Saves
    lists only keepers ("only goalkeepers are ranked on this").
  - This differs from the sandbox in one place: the engine scores passes completed and recoveries for keepers, so those
    lists keep them. The sandbox left keepers out of every sort except saves and minutes.

### The agent panel (inside Find players)
- Placeholder "Ask about the catalogue's players". The examples are the sandbox's three questions: "Who are the best U19
  dribblers up front?", "Find me women forwards who score" and "Which amateur midfielders create the most chances?".
- The engine picker is Data Search or Foundry.
- **The answer shows:**
  - the reply, "Understood: …", and who answered with which tools;
  - Foundry's unchecked numbers (`checked`);
  - the cross-level warning with "Why?", when the tool returns one;
  - up to five rows: competition, country, the number with its pool line, small and noisy marks, minutes, and a link to
    the profile;
  - "The first 5 of 17";
  - the ≈ legend;
  - "How the Scout agent answered", which lists the steps (new plain names for `scout.catalogue_place`,
    `scout.search_catalogue_players` and `scout.get_catalogue_player`) and the search tool's arguments.
- The sandbox's "Example … the sandbox calls no AI model" labels are gone. The app shows what really ran.

### Competitions (`/scout#competitions`) and one competition (`/scout#competition/<id>`)
- **A new section.** Competitions sits between Find players and Terminal in the left panel and the phone tab row. It is
  also in `/players/{id}`'s panel, which repeats Scout's sections. `#competition/<id>` is an alias of the section, so
  Competitions stays marked.
- **The list:** the 14 competitions grouped by 10 countries, from `/api/catalogue`.
  - Each card: region, format, season, level chip, tier, age group and gender; clubs, players and uploaded matches;
    coverage and dates; cameras; and uploads by team accounts and by players.
  - "Your level" marks semi-pro men. The camera note is shown once.
- **A competition's page:** `GET /api/competitions/{id}`.
  - The header: country, region, labels, who can play, how many matches are uploaded (and that the season goes on after
    24 Oct 2026), and "Find players here", which opens Find players on that competition.
  - "How players here are compared": the level's pool sizes by position. Under 5 reads "too few for a percentile: it
    takes 5"; under 15 reads "small pool". This section also has the server's `sample.words` and the qualifying rule.
  - Uploaded matches: newest first, 8 shown then "Show all", each with uploader, camera and "Watch in the Clip view"
    (`clip_view`). "Uploaded through the Player view" lists `player_uploads`, not counted.
  - England's table (Fairhaven highlighted), or "Results: uploaded matches only, not a league table".
  - Squads: a club picker (Fairhaven first when present), each player with minutes, "not enough for a percentile" or
    "not in any uploaded match yet", and "also plays in …" for career players.

### Overview (`/scout#overview`)
- **Needs you:**
  - unread replies;
  - matches shortlisted players uploaded through the Player view (`not_counted`, "not in the catalogue's numbers");
  - draft reports;
  - "94 players fit what Fairhaven needs": the distinct players over every need's two engine queries, with her own
    club's players left out;
  - "7 matches uploaded this week, in 4 competitions, up to 24 Oct 2026", filtered by date from
    `/api/catalogue/matches`.
- **New footage in the catalogue:** the five newest uploads, each with uploader, camera and the Clip view link.
- **Shortlist tiles:** each name with its country and level ("Kevin Jung (Germany, semi-pro men)").
- **Recent activity:** from the store, newest first. A shortlisted player from beyond Maya's competition says where they
  play.

### Team needs (`/scout#team`)
- **The club line:** "Regista League, England · semi-pro men · Harbour Ground · 2nd in the table, 15 points from 10
  matches". It comes from the England competition page.
- **The squad:** by shirt number, with each player's league-fixture minutes.
- **Each need is the engine's answer:**
  - At your level: `/api/catalogue/rank?metric=&position=&tier=semi_pro&age_group=senior&gender=men&min_percentile=`,
    ranked by the stat per 90.
  - From below: `…&tier=amateur,college,academy&gender=men&rank_by=pool&min_percentile=`, ranked by each player's
    percentile in their own level.
  - Fairhaven's own players are left out. That is filtering, not ranking.
  - Each list shows 6, then "Show all N".
- **The form:** gains "Look at" (My level and below, or My level only). "Better than" reads "75% of their level's
  position". The seeds carry `where: 'below'`.

### Shortlist and Compare (`/scout#shortlist`)
- **Items:** each from `GET /api/catalogue/players/{id}?metrics=<the cards' numbers>&moments=0`, using the row with the
  most minutes.
  - Each item shows competition, country and level chip; the player's strongest lead number with its pool line, ≈ and
    small flag; the sample; and the note.
  - A player with no catalogue row cannot be compared.
- **New seeds**, with the sandbox's notes, each checked against the API by `tests/test_shared_dashboard.py`:
  - Kevin Jung (Germany, her level): a goal in 84 minutes, three uploaded matches;
  - Edson Jimenez (US college, plus amateur football in August): shots at the 97th percentile, 77 minutes;
  - Ruben Prieto (17, Spain U19): one goal in 55 minutes.
  - The five league seeds and their notes are unchanged; they were already checked against the league fixtures.
- **Compare:** `GET /api/catalogue/compare?ids=&metrics=`.
  - The rows are each position's lead numbers, plus goals, assists, key passes, take-ons won, tackles won, interceptions
    and recoveries.
  - The best marks are the server's (`best`). The note says why: one level, best value in yellow; several levels and one
    position, the highest percentile; several levels and positions, "Nothing is marked best".
  - Cells give the percentile and pool, or "None yet · 25 of 33 in the pool have none", plus the small pool and ≈.
  - Column heads give the full club name, country, level and minutes.
  - A number opens its moments: `?evidence=KEY&competition=`, paged with `evidence_offset` ("Show more"). The list
    scrolls into view, which fixes the sandbox's "opens below the fold".

## Backend added in this round (additive)

1. **Engine places on list rows.** Every row of `/api/catalogue/players` (and its boards' `top`) has `rank`, its place
   on its board.
   - `_places` and `_ranked_rows` were factored out of `_rank`, so the list and `/api/catalogue/rank` share one rule:
     ties share a place, and there is no place for none yet, too few minutes, or no percentile in pool mode.
   - `sort=minutes` places qualified rows by whole minutes. `sort=name` has no places.
2. **`position` takes a comma list** on `/api/catalogue/players` and `/api/catalogue/rank` (`DF,MF,FW`). Every other
   endpoint, the terminal's included, keeps one position (tested: `/api/terminal/rank?position=DF,FW` is a 422).

Both are documented in `docs/catalogue/build/api.md` and tested in `tests/test_catalogue_scout_pages.py`:
- the list's places equal `/rank`'s, row for row, for My level, England and forwards across levels;
- each board ranks from 1, with ties shared;
- Femi Toure is first on My level (98th among 33);
- the position list leaves keepers out, and "most goals in England" outfield still ranks 25;
- the minutes and name lists.

No route, static file or default changed, so `tests/test_access.py`, `pyproject` and `cloud/smoke.py STATIC_FILES` are
unchanged.

## Files

| File | What |
|---|---|
| `static/scout/scout.js` | Find players, the agent panel, Competitions and the competition page, Overview, Shortlist and Compare, and Team needs on the catalogue. Reports, Messages and Settings are kept, with the To/A report on lists now offering shortlisted catalogue players. |
| `static/scout/index.html` | The Competitions nav item and its two panels, the new Find players layout, the Overview's "New footage", the compare note, and the needs form's "Look at". The league table left Find players. |
| `static/scout/scout.css` | The sandbox's catalogue rules (`sc-scope`, boards, level chip, pool line, small flag, ≈, uploads, competition cards and page, squads, tables) on the app's tokens. The league-table rules were removed. |
| `static/shared/demo.js` | Maya's `level`, the three catalogue shortlist seeds, and `where` on the needs seeds. |
| `static/player/index.html` | One link: Competitions in the repeated Scout panel. |
| `catalogue_api.py` | The two additions above. |
| `docs/catalogue/build/api.md` | The two additions. |
| Tests | `tests/test_catalogue_scout_pages.py` (new, 6 tests). `test_scout_page.py` is rewritten for the catalogue layout (nine sections, the agent's `where`, endpoints, no browser ranking, compare's server marks, competitions, needs through `/rank`). `test_shared_dashboard.py` has the new seeds plus a claims test. `test_product_page.py` and `test_scout_terminal.py` gained Competitions in the panel. |

## Checks

- **Quick suite:** `python3 -m pytest -q` gave 1060 passed. **Slow suite:** `-m slow` gave 15 passed. Both ran on the
  Mac; Linux CI was not run, since nothing was pushed. No test passes a large input on a command line.
- `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched and green.
- `node --check` passes on `scout.js`. There is no `style=`, inline handler or inline script; every API value goes
  through `esc()`, and bar widths and the crest are set through `element.style`.
- **Local server and browser:** `REGISTA_DOTENV= uvicorn regista.api:app --port 8247` with the built-in browser, at 1440
  and 375 px.
  - There were no console errors.
  - `scrollWidth` was 375 on `#find`, `#competitions`, `#competition/co_eng_sp_men`, `#competition/co_nga_am_men`,
    `#overview`, `#team` and `#shortlist`, with no element past the edge outside a table's own scroll box.
  - The tab was closed, the viewport reset and the server stopped.
- **What held on screen:**
  - **My level:** "Everyone here: semi-pro men · 110 players". Femi Toure is 1st (1.64 goals per 90, 98th percentile
    among 33 semi-pro men forwards ≈, 10 matches, 274 minutes). After "Show all 110", all 110 cards matched
    `/api/catalogue/rank` row for row and place for place (20 ranked, 90 none yet, no place for any of them).
  - **Whole catalogue, goals:** nine level boards, 476 players with enough minutes, and "515 more without enough
    minutes".
  - **Forwards across levels:** pool mode with Men (123) and Women (17) boards. The top four are Femi Toure, Sergio
    Gallego, Edson Jimenez and Ruben Prieto. Olivia Webb has a small pool: "only 8 qualified semi-pro women forwards to
    compare with".
  - **The agent (Data Search):** "Find me women forwards who score" returned Olivia Webb first, the cross-level warning,
    5 rows with "SMALL POOL" and ≈, "The first 5 of 17", and 3 steps. With Foundry chosen, the local server (no Foundry
    configured) answers with the rules and says so: "Answered by Regista's rules (Foundry is not configured on this
    deployment)". The Foundry path itself is covered by the backend's stand-in tests; it was not run against Azure.
  - **Competitions:** 14 competitions, 10 countries, 66 clubs and 90 uploaded matches, with England's 30 uploads (15
    tripod, 8 broadcast, 5 drone, 2 phone; 19 by team accounts, 11 by players). On Weserland-Liga, Your level, pools of
    11 goalkeepers (small pool), 44, 33 and 33, 8 uploads newest first with Round N, and the results table. England's
    table puts Fairhaven 2nd with 15 points. "Find players here" opened Find players on the competition (60 players).
  - **Overview:** "94 players fit what Fairhaven needs" and "7 matches uploaded this week, in 4 competitions, up to 24 Oct
    2026"; the five newest uploads; and tiles with country and level.
  - **Team:** "A forward who scores" gives 21 fit: 7 at her level (Femi Toure first) and 14 from below (Sergio Gallego,
    Edson Jimenez, Ruben Prieto…).
  - **Compare** (Femi Toure, Kevin Jung, Ruben Prieto; two levels, one position): the highest-percentile marks as served,
    and "None yet · all 16 in the pool have none". Femi's 5 goals opened Round 1 6' and 56', Round 6 49', Round 8 6' and
    Round 10 8'; the first clip loaded (readyState 4).
- Nothing reached Azure or the live app, and no Fabric job ran.

## Not in this round, and open

1. **Reports and Messages (port map §2.7) were not ported here.** This task named Find players, Competitions, Overview,
   Team needs and Shortlist.
   - Femi's report and the messages keep their league-based seeds, which `test_shared_dashboard.py` checks against the
     league fixtures, so they are true.
   - A report on a catalogue player reads the league profile for its moments, so "Insert a moment" says it cannot load
     for a player outside the league. "Write a report" for any player should read `include=profile` (B3).
2. **Keepers on outfield sorts follow the engine:** passes completed and recoveries keep keepers, which the sandbox did
   not (above). If Zaid wants the sandbox's rule, it is one line (`scoredFor`).
3. **The count line's "N competitions in M countries"** counts the competitions the filters select, not only those with a
   row in the list. With a name search it is left out.
4. **Profile links** go to `/players/{id}` (the API's `profile_url`). Which row a career player's profile opens on is up
   to the profiles builder (§2.8).
5. **The Overview's "added a match" card** shows only when a shortlisted player has a done Player-view upload. Locally
   there is none, so it was not seen on screen. On the live app, Femi Toure's upload `up_8807d7835c` would show it.
6. "With every semi-pro men player in the same position" (competition page) is the sandbox's wording, kept as approved.
