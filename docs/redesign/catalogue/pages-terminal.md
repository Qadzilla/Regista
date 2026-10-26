# The catalogue UI port: the Terminal and the Clip view

Branch `ux/catalogue` (on top of PR #39, `feature/catalogue`). Written 2026-10-26 by the Terminal and Clip view builder,
following `port-map.md` §2.10 and §2.11. Nothing was pushed, merged or deployed. Nothing reached Azure or the live app,
and no Fabric job ran. Everything shown is synthetic: invented players, clubs and competitions; countries and levels are
labels.

## Zaid's decisions, as built

- **Minutes:** the engine's minutes are untouched. Cards and the stage show the match clock the clip's scoreboard draws
  (period 2 from 45:00, as `render/scene.py clock_at` does), worked out from the match's `periods`. Titles keep the
  engine's minute.
- **Noisy marks:** kept. ≈ follows each row's own level (the engine's `noisy` on the cell); menus use the selected
  player's level once their numbers are in, else the league's flag.
- **League fixtures only:** every Terminal number for England comes from the catalogue endpoints, which count the
  Regista League fixtures only. Femi Toure: 5 goals, 10 matches, 274 minutes; non-penalty goals 1.64 per 90 at the 98th
  percentile among 33 semi-pro men forwards (97th among 18 in his competition, 96th among 123 at every level).
- **One ranking rule, the engine's.** The browser computes no place. See "The table" below.
- **"None yet"** for a count at 0, **pool lines** in the engine's words, **small pools** flagged, **Round** never
  matchday.

## The Terminal (`/scout#terminal`)

### Files

- `static/scout/terminal-place.js` (new): the sandbox's place words, ported as `Regista.terminalPlace` (pure, no DOM,
  no network). Its vocabulary is built from `/api/catalogue` and the players' directory, not from an exported index.
- `static/scout/terminal.js`: the Terminal on the catalogue.
- `static/scout/terminal.css`: the where bar, list headers, the Percentile column, small and none-yet marks. The phone
  fix from fixes-round4 is in: `.pf .tx-top { position: static; z-index: auto; }` in the 720 px query.
- `static/scout/index.html`: loads `terminal-place.js` before `terminal-words.js`.
- `terminal-words.js` is unchanged. Review A pass 5 said to keep the live parser; I did, and it reads every existing
  question as before.
- `cloud/smoke.py STATIC_FILES` now lists `scout/terminal-words.js` and `scout/terminal-place.js`. The pyproject glob
  already covers them.

### Data

- **Rows:** one per player and competition, 1,057 in all.
  - A player with one competition keeps their global id as the row id, so old links and layouts still work.
  - A career player's rows are `<gid>~<competition>`.
- **The directory:** `GET /api/catalogue/players?min_minutes=0&sort=name&metrics=goals` gives the names, playing time
  and row ids. It is loaded once, in 6 pages of 200 (about 1.3 MB).
- **Cells:** held per percentile scope (`level`, `competition`, `all`), so switching scope asks the engine again rather
  than mixing pools.
- **A player's panels** read the existing endpoints with `competition=` and `scope=`:
  - `/api/players/{gid}/metrics`, and its evidence pages for the drawer;
  - `/form`, `/similar`, `/shots`, `/heatmap`.
- **Compare:** `/api/catalogue/compare` gives the warning and the `best` marks.
- **Scatter:** `/api/terminal/scatter`, one level at a time.
- **Team:**
  - `/api/teams` for the Regista League's clubs;
  - for a catalogue club, `/api/teams/{club}/style?competition=`, `/api/teams?competition=` (the bar ranges) and
    `/api/competitions/{id}` (the record and the squad's minutes);
  - team shots use `/api/teams/{club}/shots?competition=`.
- **Matches:** from `/api/season` plus `/api/catalogue/matches`, 90 in all.

### The table (the engine ranks, the browser does not)

The table asks `GET /api/catalogue/players` for the filters, scope, position, sort and order. Regulars only means the
engine's own qualifying minutes per competition; everyone means `min_minutes=0`.
- The first 16 columns come in the same call; more columns come in further calls with the same filters. Every call is
  paged in 200s.
- The order, each row's `rank` and its `board` (one list per level, or one per gender when one position spans levels)
  are the engine's. They follow the same rule as `/api/catalogue/rank`.
- The browser does only two things:
  - it lists the rows the engine gave no place after the placed ones, in the engine's order, as `/api/catalogue/rank`
    lists `players` then `unranked`;
  - for a club sort, it puts the engine's names list in club order. That is an order, not a ranking.
- The sandbox's `valueCmp`, `poolCmp`, `ranksOf`, `rankable` and the old `screenRanks` are gone. A test checks this.

Checked in the browser against the API, row by row (place and player):

| Search | Table | `/api/catalogue/rank` |
|---|---|---|
| most goals in England | 25 placed, 116 none yet, 3 lists (semi-pro men · your level, academy U18 men, semi-pro women) | 25 ranked, 116 unranked: same rows, same places |
| women forwards | 17: 5 placed, 12 none yet; one list "Women · 17 forwards from 2 levels", by percentile in own pool | same |
| best dribblers in academy | 159 in 4 lists; 43 placed, 116 none yet | same |

### Place words, as the sandbox shows them

- **Where menu:** Country, Level, Age group, Gender, Competition. Each list narrows to what the others allow.
- **Buttons:** **My level** (Fairhaven FC's level, semi-pro men, read from the catalogue's clubs) and **Whole catalogue**.
- **Percentiles within:** Level, Competition or All levels. All levels shows the engine's warning above the table.
- **Typed place questions** set the filters, and what is left goes to the usual reader. A player's or club's exact name
  always wins.
- **Inside commands:** place words work in `rank` and `plot`.
- **Suggestions** include Place items. **Help** has a "place or level" row. **Examples** add the five place questions.
- **Status line:** when filters carry over from an earlier search, it says so; at the scout's own level it says how to
  see every level.

Measured in the browser on the local app:

| Search | Result |
|---|---|
| U19 midfielders in Spain | 11, led by Izan Martinez (97th percentile among 17 academy U19 men midfielders) |
| most goals in England | 3 lists, 141 players, 25 ranked (116 none yet); Femi Toure first, 1.64 per 90 |
| women forwards | 17, one list by percentile in own pool; Olivia Webb (94th among 8, small) and Kaitlyn Stewart (94th among 9, small) |
| players in Nigeria | 41, led by Yusuf Okafor (98th among 33) and Adebayo Nwosu (95th among 31) |
| my level forwards | 33; Femi Toure 1.64, 98th percentile among 33 semi-pro men forwards |
| best dribblers in academy | 4 lists, 159 players |
| Weserland strikers | 15 in Weserland-Liga, 2 ranked (13 none yet) |
| best young defenders in Ghana | academy defenders in Ghana; the line says "young" was read as the academy levels |
| U21 forwards | "The catalogue has no U21 competition", with its age groups |

### Panels

- **Player card:** competition, country, level chip and "your level". The sample (appearances of the club's uploaded
  matches, minutes against what a regular needs). "Also plays in …" opens the other competition's row, with the career
  story. "Best among <pool words>" with "pool N" and the small flag.
- **Similar players:** in the scope shown; a similar player's level and country appear when they differ.
- **Radar and compare:**
  - each player is labelled with their level, and every value shows its percentile and pool;
  - when levels, genders or positions differ, a warning says how to read the comparison;
  - the engine's ★ best marks show in the table.
  - Example: "Compare Femi Toure and Sergio Cruz" warns: different levels (semi-pro men and amateur men).
- **Scatter:** one level at a time. When the filters cover several levels it shows the selected player's level (or the
  first) and says so.
- **Team:** a club picker for all 66 clubs, grouped by country and competition.
  - Catalogue clubs show rank in the competition and in the level, the competition's average, and the record from
    uploaded matches "only, not a league table".
  - A small-sample warning appears where the engine flags one.
  - Shot numbers play every shot; the others list one value per uploaded match.
  - Checked: CF Torrevalle (2 uploaded matches, small sample, ranks out of 5 and out of 13).
- **Touch map, shots and form** follow the row's competition.
- **The clips drawer:** a catalogue clip played. Sergio Cruz's shot, `cm_eam_02_fta_tvl`, reached readyState 4.

### Saved layouts

- Saved layouts are now version 4 in `Regista.store`, adding the filters and the scope.
- Versions 3 and 2 still load and open on My level.
- A player saved by global id who now has two rows takes their first row.
- Checked in the browser with a stored v3 layout (Sergio Cruz focused, MF columns): it opened on "Where: semi-pro men",
  with Sergio Cruz selected. I then removed the layout.

### Every existing question

I ran these in the browser and each answered as before, now with the competition in the line: Toure, rank forwards
non-penalty goals, RANK FW npxg, CMP TOURE USTINOV, SCAT npxg xa FW, SIM Toure, SHOT, FORM, HEAT, RDR, TEAM BRO,
HL Toure (25 moments: 5 goals, 13 other shots, 5 chances made, 2 interceptions), who has the most xG?, most yellow cards
(most first), Toure goals (5 moments), best finishers at Brookfield, most minutes, help, and an unknown word. Without
place words, a question keeps the table's current filters; by default that is the scout's level.

## The Clip view (`/`)

- **`/api/matches` is unchanged.** A new `loadCatalogue()` reads `/api/catalogue` and `/api/catalogue/matches` (paged).
  Like `loadSeason()`, it is never awaited for the first paint.
- **Match picker:**
  - one group per competition, grouped by country: "England · Regista League (semi-pro men)";
  - the league's group keeps `/api/season`'s matches, now in the same words;
  - entries read "Round N · Home s–s Away · date · camera · uploaded by a player / a team account";
  - 94 matches in all: the 4 sample matches and the 90 uploaded ones.
- **Home** gains "Or open a match", the same list. It opens the match view as a new history entry.
- **Match line under the title:** competition · country · level · date · the uploader ("uploaded by the Oxenridge Women
  team account" or "uploaded by Leon Valente, a player at Ashby Athletic") · "filmed on a drone (the uploader's label)".
  It is joined from the catalogue list. The heading is the match's own title ("Round 1: …").
- **Search:**
  - Home still sends one rules `/chat` per match, 6 in flight, now over 94 matches.
  - Results are grouped by competition in the catalogue's order, with the sample matches last as "Other matches". Each
    group shows the best 8 with "Show all N".
  - A Competition filter (grouped by country, with counts) narrows the grid.
  - Each card reads "Round 1 · Ashby Athletic 1–1 Fairhaven FC · Regista League", then the date, camera and uploader,
    then the match clock.
- **Measurement (B16):**
  - **Warm local app:** a whole search took **2.2 s** ("Find me every assist, best first": 42 moments in 10
    competitions). That is under the 8 s line, so B16 was not built.
  - **Cold:** the first search on a fresh process took **128 s**, because each catalogue match builds on its first
    `/chat`. See the open items.
- **Checked:**
  - "Find me all the nutmegs": 71 moments.
  - The Competition filter kept Weserland-Liga only.
  - Show all opened 24 Regista League assists.
  - A Pennine Women's League card opened its match with the match line and "On the ball · 58:45–58:51". Its clip
    played (readyState 4).

## Checks

- **Browser** (built-in browser, my own server at 127.0.0.1:8231, `REGISTA_DOTENV=`):
  - pages checked at 1440 and 375 px: the Terminal (table, where bar, lists, card, radar with the cross-level warning,
    team panel for a catalogue club, drawer), Home (landing with the picker, grouped results, filter, match view);
  - no console errors;
  - `scrollWidth` was 375 at 375 px on the Terminal, the Home landing and the results;
  - at 375 px the Terminal's search block computes `z-index: auto` and stays under the phone panel row when scrolled.
  - Cleanup: I removed my test layout from localStorage and closed the tab, and the viewport is back to desktop. The
    server is stopped.
- **Tests:**
  - `tests/test_scout_terminal.py`: 46 pass. Six tests are new:
    - the place words on the API's catalogue (25 sandbox cases plus 38 existing questions that must hold no place word);
    - parity between `terminal-place.js` and the Python port `regista.catalogue.place` on the same questions;
    - packaging and load order;
    - "the engine ranks, the browser never does";
    - the where bar, pools, none yet and lists;
    - the table's query against `/api/catalogue/rank`, row for row (25 placed, 116 none yet, Femi first, 1.64 at the
      98th among 33 semi-pro men forwards).
  - `tests/test_product_page.py`: 61 pass, 4 of them new.
- **Pins updated where the approved design changed them,** each to the new behaviour:
  - layouts v3 to v4;
  - the read-only endpoint list gains the catalogue reads;
  - the footer wording;
  - "Regulars only" without the league's minutes, now per competition;
  - the profile link uses the global id;
  - the runner is split into `run` and `runIntent`;
  - the rank status line goes through `rankText`;
  - the touch map follows the competition.
  - `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched.
  - `tests/test_scout_page.py`: its script-order pin now includes `terminal-place.js`.
- **Both suites on the Mac:**
  - quick: 1,074 pass, 15 deselected (one failure in the first run, the script-order pin above, fixed and re-run);
  - slow: 15 pass.
  - The node harnesses read their questions on stdin, as Linux CI needs.
- No new route, so `tests/test_access.py` needs no new row. No `style=` attribute, inline handler or script was added;
  every API value goes through `esc()` or `textContent`.

## Open items

1. **The first Home search on a fresh process is slow.** It took 128 s locally: each catalogue match builds on its first
   `/chat`. Later searches take about 2 s. A fresh live revision would show this to the first visitor. Two options:
   - warm the catalogue matches' chat state at startup, as `warm_catalogue()` does for the engines;
   - or build B16 with a warm-up.
   This is Zaid's call; I did neither.
2. **The table's payloads are large for the whole catalogue.** Each cell carries its pool and sample, so 1,057 rows with
   8 columns is about 6.4 MB. My level is about 0.3 MB per position. An opt-in compact cell shape on
   `/api/catalogue/players` would cut this; I added no backend.
3. **"best young defenders in Ghana"** now ranks defenders on what defenders are judged by (tackles and interceptions,
   possession-adjusted), as "best defenders" does everywhere. The sandbox ranked them on progressive passes.
