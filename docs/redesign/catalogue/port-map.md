# The catalogue UI port: the map (before code)

Branch `ux/catalogue`, cut from `feature/catalogue` (PR #39, not merged). Written 2026-10-26. This is the plan for
porting the catalogue UI that Zaid approved in the sandbox into the real app. It lists, for each sandbox piece, the app
files it goes into, the API calls it uses and the gaps in the API. Then it lists the backend work and the checks.
Nothing here is built yet. Everything shown in the app stays synthetic: the people, clubs and competitions are invented,
and countries and levels are only labels.

**Sources read for this map.**
- The sandbox at `.claude/worktrees/sandbox-ref/sandbox/`, head e041bfd (review A pass 5's should-fix is fixed there).
- Its notes in `sandbox/catalogue-notes/`: export, check, the three build reports, fixes rounds 1-4, reviews passes 1-5.
- The engine and API on this branch: `catalogue_api.py`, `season_api.py`, `terminal_api.py`, `player_api.py`,
  `api.py`, `mcp_server.py`, `cloud/foundry.py`, `season/scout.py`, `season/summaries.py`, `catalogue/*`,
  `player/{film,store,worker}.py`, and `docs/catalogue/build/api.md`.
- The app's current `static/{scout,me,player,product,shared}`.
- Probes run in-process with `REGISTA_DOTENV=` and `TestClient`, reads only. For example: `/api/catalogue/rank` ranks
  116 England zeros on goals (rank 18, the 38th percentile), and a catalogue summary says "the best of the league's 18
  forwards … 2.3 per 90".

## 1. Rules for every builder

### Zaid's decisions for this port

- **Minutes.** Keep the engine's minutes. Do not change `match_minute`, `clock_at` or clip titles. Moment cards show
  the match clock the video draws (period 2 from 45:00), worked out from `/api/matches/{id}` `periods`.
- **Noisy marks.** Keep the ≈ mark wherever the engine says a number is noisy, Femi Toure's goals included.
- **League fixtures only on catalogue pages.** A catalogue page counts the league fixtures only, so Femi Toure has 5
  goals in 10 matches over 274.3 minutes. His Player-view friendly is named on the page and not counted.
- **Catalogue-club uploads** (also the user's own request).
  - Player-view uploads may come from catalogue clubs. The backend for this is built in this port.
  - A processed upload is named on its competition page and in the player's career, but **not counted** in that
    competition's numbers. The harness task said the match "joins" its competition page and the career. The user's
    rule wins over that, so "joins" means "listed there", never "counted there".
- **Scout agent.** The Foundry Scout agent gets the catalogue tools.
- **Everything else as the sandbox shows after its last fix round:**
  - One ranking rule, the engine's: `/api/catalogue/rank`, or an endpoint's own ordering. The browser never ranks.
  - "None yet" for zeros.
  - Pool lines read "98th percentile among 33 semi-pro men forwards".
  - Small pools are flagged with their reasons.
  - Rounds are called Round, never matchday.
  - The sandbox builders' four picks:
    - the default sort is goals per 90, one list per level;
    - minutes played is ranked one list per level;
    - "From below" means every men's level below semi-pro, with no age cap;
    - per-visitor state goes through `Regista.store`. In the sandbox it stayed in memory; in the app it uses the
      store, as §2.9 says.

### Hard rules

These come from the task and CLAUDE.md.

- **CSP and escaping.** No inline scripts, handlers or style attributes. The sandbox's `terminal.js` still has 14
  `style=` attributes; convert them to DOM writes, as the live terminal already does. Every API value goes through
  `esc()` or `textContent`.
- **Per-visitor state** only through `Regista.store`. The Terminal's layouts move to v4, and v3 still loads.
- **Phones.** At 375 px there is no horizontal scroll.
- **Plain words** everywhere.
- **Never served:** hidden ratings, level scales (`execution` included) and seeds.
- **Synthetic data is labelled.**
- **Existing endpoints keep their shapes and defaults.** `tests/test_backcompat.py` and
  `tests/test_catalogue_backcompat.py` stay green and are never edited. The snapshot covers these, each called
  without parameters:
  - `/api/season`, `/api/players`, `/api/players/pl_bro_09` (summary included), `…/moments`, `/api/compare`;
  - `POST /api/scout/ask {q: "who scored the most goals", engine: rules}`;
  - `/api/metrics`, `/api/terminal/{screen,rank,scatter}`;
  - the player's `metrics`, `form`, `similar`, `shots` and `heatmap`;
  - `/api/teams`, the team's `style` and `shots`;
  - the three league MCP tools.

  So any new field goes into catalogue-mode answers or the PR #39 endpoints, **never into `Metric.public()`**, which
  `/api/metrics` and the default terminal columns print.
- **England semi-pro men stay byte-identical** (`league.json`, `SEASON_PINS`). Femi Toure keeps 5 league goals, none a
  penalty, two clear.
- **Files and routes.**
  - New static files are covered by the pyproject glob `static/*/*.js`. Add them by name to
    `cloud/smoke.py STATIC_FILES`.
  - New routes go in `tests/test_access.py`.
- **Tests never load `.env`** (`REGISTA_DOTENV=`).
- **Nothing reaches Azure or the live app,** and no Fabric job runs. Uploads are tested on `LocalStore` only.
- **Both suites pass,** on Linux CI too: `python3 -m pytest -q` and `-m slow`. Node harnesses read big inputs on
  stdin, never as one command-line argument (Linux's 128 KB limit).
- **Do not copy `sandbox/catalogue/*.json`** (74.5 MB) into the app. The app reads the API. The sandbox's offline
  helpers (`align_catalogue.py`, `SBCat.byValue`, `SBCat.places`, `zeroLine`, `plainSample`, the summary regexes)
  are behaviour the server must own (§3).

## 2. The map, piece by piece

All paths are under `src/regista/` unless noted. "Gap" names the backend item in §3 that the piece needs.

### 2.1 Scout: Find players (`/scout#find`)

| | |
|---|---|
| Sandbox | `scout.js` (find, `boardsFor`, cards, place filters), `index.html` (`#scout/find`), `sandbox.css` |
| App files | `static/scout/scout.js` (the find section), `static/scout/index.html`, `static/scout/scout.css`, `static/shared/regista.js` (a `poolLine` helper) |
| Filters | Country, Level, Age group and Gender options from `GET /api/catalogue` (`levels`, `competitions`, `totals`). The Competition options come from `GET /api/competitions?country=&tier=&age_group=&gender=`, so the list never offers a competition the list would leave empty. "My level" sets semi-pro, senior, men (Maya's level is a persona seed in `shared/demo.js`, not served). |
| List | `GET /api/catalogue/players?q=&country=&tier=&age_group=&gender=&competition=&position=&sort=goals&metrics=<sort>,<2 more>&limit=24&offset=` gives `boards`, `rank_by`, `rank_rule`, `warning`, and cards with `values[k].{value,percentile,pool,sample,noisy,evidence_total}`. "Show all N" pages a board through its `offset`. "Add the others" passes `min_minutes=0`. By default the list holds only qualified rows, and the page says so. |
| Cards | Name, position and club; competition, country and a level chip; three numbers with bars; the pool line of the sort stat; the small-pool flag with its reason; the sample ("10 matches · 274 minutes in Regista League"); "also plays in …"; and the shortlist stage from `Regista.store`. |
| Gaps | B5 (none yet: no place, listed after, and each board's "N of M have any" line), B6 (pool words), B9 (`sort=minutes`), B12 (`also_in`, `profile_url` for every player) |

### 2.2 Scout: Competitions (`/scout#competitions`) and one competition (`/scout#competition/<id>`)

| | |
|---|---|
| Sandbox | `scout.js` (competitions, `competitionPage`), `index.html` (`#scout/competitions`), `sandbox.js` (`SBClip.open`) |
| App files | `static/scout/scout.js`, `static/scout/index.html` (a new nav item, Competitions, between Find players and Terminal, in the left panel and in the phone tab row), `static/scout/scout.css` |
| List | `GET /api/catalogue`. It gives 14 competitions grouped by 10 countries, with region, format, season, level chip, tier, age group, gender, clubs, players, uploaded matches, coverage ("every league match uploaded so far" or "some matches uploaded"), dates, cameras and uploaders. Mark "Your level". Show `camera_note` once. |
| Page | `GET /api/competitions/{id}` gives the labels, `level_pool`, `sample`, the matches with their named uploader and camera, `results`/`results_note` or England's `table`, and the clubs with squads. The page shows: |
| | • **Header:** who can play, and the as-of line (`AS_OF_NOTE`). |
| | • **"How players here are compared":** pool sizes by position. A pool under its minimum reads "too few for a percentile: it takes 5"; a small pool is marked. |
| | • **Uploaded matches:** newest first, 8 shown, then "Show all". Each opens "Watch in the Clip view" (`clip_view` plus `&player=`). |
| | • **Table:** England's table, or "Results, uploaded matches only, not a league table". |
| | • **Squads:** a club picker. Each player row has minutes and "not enough for a percentile" or "not in any uploaded match yet". |
| | • **"Find players here":** opens `#find` with the competition. |
| | • **Player-view uploads:** listed here and not counted. |
| Gaps | B1 (Round titles), B7 (sample in plain words), B8 (squads with playing time, player uploads), B15 (uploads that join the page) |

### 2.3 Scout: Overview (`/scout#overview`)

| | |
|---|---|
| Sandbox | `scout.js` (overview), `catalogue-data.js` (`dayKey`, `dayWords`, `newestFirst`) |
| App files | `static/scout/scout.js`, `static/scout/index.html`, `static/shared/regista.js` (the date helpers, shared with `/me`) |
| Needs you | "N players fit what Fairhaven needs". This is the sum of `ranked` over each need's two engine queries (§2.4), with `limit=1`. "N matches uploaded this week, in M competitions, up to 24 Oct 2026" comes from `GET /api/catalogue/matches?limit=200` (90 rows), filtered by date in the browser. Filtering a list is fine; ranking it is not. |
| Panels | **New footage in the catalogue:** the 5 newest uploads from the same list, each with uploader and camera, opening the Clip view. **Shortlist tiles:** each player's country and level, from the cards. **Recent activity:** from the store, newest first, one date shape ("Today", "22 Oct"). |
| Gaps | B9 (`min_percentile` and a tier list), so a need's count is the engine's |

### 2.4 Scout: Team needs (`/scout#team`)

| | |
|---|---|
| Sandbox | `scout.js` (team, `fits()`) |
| App files | `static/scout/scout.js`, `static/shared/demo.js` (the needs seeds) |
| API | **At your level:** `GET /api/catalogue/rank?metric=<need.stat>&position=<pos>&tier=semi_pro&age_group=senior&gender=men&min_percentile=<need.pct>` (ranked by value). **From below:** `…&tier=amateur,college,academy&gender=men&rank_by=pool&min_percentile=<pct>`. A new need can be "My level only" or "My level and below". |
| Club line | The England table in `GET /api/competitions/co_eng_sp_men`: 2nd, 15 points from 10 matches. The squad with minutes comes from B8, or from `/api/catalogue/players?club=cl_fairhaven&min_minutes=0`. |
| Seeds | A need's `stat` must be a terminal metric key (`goals`, `interceptions`, …), as `demo.js` uses today. Women's pools are never mixed in: Fairhaven is a men's club. A player with none of the stat never fits (B5). |
| Gaps | B9, B5 |

### 2.5 Scout: Shortlist and Compare (`/scout#shortlist`)

| | |
|---|---|
| Sandbox | `scout.js` (shortlist, compare, evidence drawer) |
| App files | `static/scout/scout.js`, `static/shared/demo.js` (the seeds) |
| Seeds | Add Kevin Jung (Germany, her level), Edson Jimenez (a US college career player) and Ruben Prieto (Spain, academy U19), with notes that are true on the current data (the sandbox texts). Femi's note keeps "5 goals, two clear". `tests/test_shared_dashboard.py` then checks the new seeds' claims against the catalogue API, as it does for the league. |
| Items | Each item's strongest number, with its pool line and sample, comes from `GET /api/catalogue/players/{gid}?metrics=<the position's core set>&moments=0`, the row with the most minutes. |
| Compare | `GET /api/catalogue/compare?ids=a,b[,c]&competitions=…&metrics=…`. It gives `same_pool` and `warning`, and B10's `best` marks. A number opens its moments with `GET /api/catalogue/players/{gid}?evidence=KEY&competition=` (paged with `evidence_offset`). Column heads show full club names. A zero reads "None yet · N of M in the pool have none" and is never marked best. |
| Gaps | B10 (best marks owned by the server), B5 |

### 2.6 Scout: the agent panel (inside Find players)

| | |
|---|---|
| Sandbox | `scout.js` (the agent panel, from `boards.json` `agent_tool_examples`) |
| App files | `static/scout/scout.js` (`renderScoutAnswer`), `static/scout/index.html` (placeholder "Ask about the catalogue's players") |
| API | `POST /api/scout/ask {q, engine, where: "catalogue"}`. **The sandbox's "Example … the sandbox calls no AI model" labels go.** The app shows the real `answered_by`, `tools_used`, `trace` and `checked`. Cards show competition, country, value, pool line, small and noisy marks, minutes and a profile link. The cross-level warning appears when the tool returns one. |
| Gaps | B14 (catalogue tools, the `where` switch, a rules path for catalogue questions), B5 (the tool's none yet) |

### 2.7 Scout: Reports and Messages

| | |
|---|---|
| App files | `static/scout/scout.js`, `static/me/me.js`, `static/shared/demo.js` |
| Seeds | Port the sandbox's rewritten seeds. **Femi's report:** 5 goals in 10 matches, none a penalty; 1.64 per 90, at the 98th percentile among 33 semi-pro men forwards. Every number keeps its pool. Use one decimal where the profile's ratio rows do (47.4%, 7.1%; review A pass 4's nit). **Messages:** Olivia King's thread, and Tomás's "round 10". Clips are catalogue clips by match and clip id. "Write a report" works for any player with minutes and reads the profile endpoint (B3). |
| Store | One shared conversation store, so both sides see one thread (§2.9, unchanged). |

### 2.8 Profiles: `/players/{id}` for every catalogue player, with the career strip and the scope toggle

| | |
|---|---|
| Sandbox | `catalogue-profile.js` (`CP.render`, both audiences), `scout.js` `openPlayer` |
| App files | **New `static/player/catalogue-profile.js`**: one renderer for both audiences, a port of `CP.render`, which uses `Regista.profileView`'s helpers. `static/player/player.js` reads the catalogue endpoints, keeps the scout bar, and keeps `window.RegistaPlayer`. `static/player/index.html`, `static/shared/dashboard.css` (the `cp-*` rules). `profile-view.js` stays: `scout.js` and `terminal.js` use its helpers, and `tests/test_product_page.py` reads it. Its old Season-shape `render` may stay unused this round. |
| Route | `GET /players/{gid}` is unchanged (it already serves the page for any well-formed id). The page now reads `GET /api/catalogue/players/{gid}?include=profile&scope=<level\|competition\|all>&competition=<row>&moments=40`, `GET /api/players/{gid}/similar?competition=&scope=`, and the metrics evidence with `?evidence=KEY`. `GET /api/players/{gid}` stays as it is, for back-compat and the Studio. |
| Header | Name, position, club, kit number, age, height, foot and nationality. Then competition, country and a level chip, "also plays in …", and "Synthetic player · invented name". **The sticky scout bar follows the selected row.** That fixes check.md open point 5. |
| Career strip | Built from `career`, `career_story` and `overall`. Each card has matches and minutes, "Enough minutes for percentiles", "30 of the 45 needed" or "No minutes in an uploaded match yet", and the date range. Clicking a card switches the row. |
| Numbers | **Scope toggle:** Level (the default), Competition or All levels; All always shows `warning`. **Pool line:** "Compared with the 33 semi-pro men forwards with enough minutes, from Regista League (England) and Weserland-Liga (Germany)". **Sample line.** For England it adds that only the league fixtures are counted, and names Femi's friendly as not counted. **Six headline tiles:** count, per 90, bar and pool line, plus the small or none-yet flags with reasons, the ≈ mark, and the moments behind the number. **Ratios.** **"Every number in this competition"** (folded). **Best moments** across competitions, with competition chips and Play reel. **Where they play:** the touch map. **Similar players.** **Matches:** newest first, with uploader, camera and "Watch in the Clip view". |
| Add a match | `add-match.js` calls `/api/players/{gid}` and claims count only in the league's Season. Show it on England players' profiles only. Catalogue players add a match through `/me` (B15). Say so on the page in one line. |
| Gaps | B2 (England counts fixtures only), B3 (the profile shape), B4 (summary wording), B5, B6, B11 (similar players' reasons in plain words), B12, B15 (uploads named in the career) |

### 2.9 Player view (`/me`): Switch player and the catalogue upload flow

| | |
|---|---|
| Sandbox | `profile.js` (rewritten), `index.html` (the player bar, picker, add form), `catalogue-data.js` (`SBMsg`) |
| App files | `static/me/me.js`, `static/me/index.html`, `static/me/me.css` |
| Bar and Switch player | "Femi Toure · Brookfield Rovers · Regista League, England · semi-pro men". Switch player searches `GET /api/catalogue/players?q=&competition=&min_minutes=0&sort=minutes&limit=40` (players who have played, Femi first). Each entry shows shirt, position, club, competition, level chip, and "plays in two competitions". `?player=pl_…` opens any catalogue player. An unknown id opens Femi and says so. |
| Overview | The profile endpoint (level scope) gives "Your season" with three lead numbers and their pool lines. **Best moment.** **Recent activity:** newest first, and a match is listed once. A club upload that is one of the player's matches folds into the match row, as e041bfd does. **Needs you:** unread messages, Femi's real upload, "Add a match you filmed" and "Is this you?". |
| My profile | `catalogue-profile.js` in the player audience ("you", no Scout links). |
| Matches & videos | **Your uploads:** `/api/player/uploads?global_id=`. Femi's real upload keeps its steps and timings, labelled "on Azure Container Apps (the live app)". **In the catalogue:** `GET /api/catalogue/matches?club=<club>` gives matches the player uploaded, or that their club's team account uploaded of a match they played, with the camera label. Then "Is this you?" and All your matches. |
| Team | `GET /api/competitions/{id}` gives the club (crest, city, ground) and its squad with minutes (B8). England shows `table`; the others show "Results so far · uploaded matches only, not a league table". A career player picks between their two clubs. **My details** stay editable on the page only (store). |
| Upload flow | Two steps. **1. The match:** the player's competition (one, or two for a career player), Against (that competition's clubs), home or away, and the date played. **2. The footage:** the video file, required. "Filmed on" Tripod, Phone, Drone or Broadcast camera, with `camera_note`. The consent box "Everyone I filmed agreed to be filmed and shown", required. It posts `POST /api/player/uploads` (multipart, admin key) with `competition_id`, `opponent_club_id`, `side`, `date`, `camera` and `consent`. Progress shows the real stages, and no timings are claimed for anything else. A refusal shows the server's plain message. |
| Gaps | B3, B8, B9 (`sort=minutes`), B15 |

### 2.10 Terminal on the catalogue (`/scout#terminal`): place words, level boards, Pool column, compare warning

| | |
|---|---|
| Sandbox | `terminal.js` (Where menu, scope, boards, Pool column, card, compare, scatter, team picker), `terminal-place.js` (pure), `tools/test_terminal_place.js` (80 checks) |
| App files | `static/scout/terminal.js`; **keep the live `terminal-words.js` parser** (review A pass 5: the sandbox's `natural()` misses "most xG" and similar questions). **New `static/scout/terminal-place.js`**, the sandbox file fed from `GET /api/catalogue` instead of `index.json`. `static/scout/terminal.css`; `static/scout/index.html` loads place before words. `tests/test_scout_terminal.py` gets a node harness for place words, reading stdin, with the sandbox's 80 checks. |
| Table | `GET /api/catalogue/players?<where>&scope=&metrics=<≤16>&sort=&min_minutes=0&limit=200&offset=` pages the rows (1,057 at most), as `COLS_PER_CALL` does today. **Order, places, boards and none yet come from `GET /api/catalogue/rank?metric=<sorted>&<where>&scope=&limit=200&offset=`**, so the browser never ranks. Row ids are `<gid>~<cid>` for career players' second rows, so old links keep their global id. |
| Panels | **Card:** `/api/players/{gid}/metrics?competition=&scope=` (the sample, "Also plays in…", "Best among" with its pool). **Drawer:** `…/metrics?evidence=KEY&competition=&evidence_offset=`. **Form, shots, heat map, similar:** `/api/players/{gid}/{form,shots,heatmap,similar}?competition=&scope=`. **Scatter:** `/api/terminal/scatter?x=&y=&tier=&age_group=&gender=`, one level at a time. **Compare and radar:** `/api/catalogue/compare`, with its `warning` shown on the radar and in the status line. **Team picker:** all 66 clubs from `/api/catalogue` `clubs` (B8), then `/api/teams/{club}/style?competition=` (outside England: "uploaded matches only", small sample). |
| Filters | **Where:** Country, Level, Age group, Gender, Competition. **My level** and **Whole catalogue**. **Percentiles within** Level, Competition or All levels (All always warns). A **Pool column** for the sorted stat. A **Level column**; on phones, the level shows under the name. |
| Layouts | v4 in `Regista.store`, which adds filters and scope. v3 opens on My level. |
| Phone fix | `terminal.css` line 23 (`.pf .tx-top`) and line 383 (720 px query): add `z-index: auto`. Then check at 375 px, scrolling 150-380 px. Also fix the Pool column sliding under the sticky name after a ranking scrolls the table. |
| Gaps | B5 (none yet in rank, boards and cells), B6, B8 (`clubs`) |

### 2.11 Clip view (`/`): the picker and search over catalogue matches

| | |
|---|---|
| Sandbox | `sandbox.js` (`matchHead`, picker groups, results grouped by competition, the Competition filter, the card and upload lines, `SBClip.open`) |
| App files | `static/product/app.js`, `static/product/index.html`, `static/product/product.css` |
| Matches | **`/api/matches` is unchanged.** A new `loadCatalogue()` (like `loadSeason()`, never awaited for the first paint) reads `GET /api/catalogue/matches?limit=200` (90 rows, England's 30 included; drop duplicates against `/api/season`). It adds one optgroup per competition, grouped by country, each entry "Round N · Home s–s Away · date · camera · upload type". `?match=cm_…` already opens (tested). |
| Match line | Under the title: competition, country, level, date, the uploader ("uploaded by the X team account" or "uploaded by Leon Valente, a player at Ashby Athletic") and the camera label. It is joined client-side from the catalogue list, so `/api/matches/{id}` keeps its shape. The heading uses `title` as it is once B1 lands. |
| Search | Fan out `POST /api/matches/{id}/chat` (rules) over every match, as today, now about 124 matches. Results are grouped by competition (8 each, "Show all N"), with a Competition filter. Cards read "Round 1 · Eastwick United 0–2 Brookfield Rovers · Regista League", plus an upload line and the match clock from `periods`. **Measure** on the local app (warm): if a search takes more than 8 s at 6 in flight, add B16. |
| Small | Player picker: "1 moment", not "1 moments". The prompt "take-ons in the final third" is only partly understood (the search ignores "final third"). Show what the search understood, as the sandbox does, or replace the prompt (Zaid's call, §6). |
| Gaps | B1, B16 (only if the measurement asks for it) |

## 3. Backend work

Each item lists what to build, where, and how to test it. B-numbers are referenced above. **Build these first.** The UI
builders can work in parallel against the contracts below.

### B1. Match titles say Round

- **Change:**
  - `catalogue/build.py`: `title()` becomes `"Round {n}: {home} {h}–{a} {away}"`, the league's form. The subtitle reads
    "…, round {n}: …".
  - `_labels_current()` checks the new prefix. Then each built folder is stale once and rebuilds.
  - Update `tests/test_catalogue_build.py` lines 64 and 146, and `catalogue_api.season_payload`'s docstring.
- **Check:**
  - The title lives only in `manifest.json` (`season/build.py` line 119), so `CATALOGUE_PINS` must not move.
  - Run `python -m regista.catalogue check`, plus the catalogue build test and the image smoke test's pins.

### B2. England counts league fixtures only on catalogue pages

- **The problem.** `catalogue_api.catalogue_profiles()` calls `cp.use_england(season())`. That is the app's season:
  fixtures, confirmed claims and Player-view uploads. On the live app it would count Femi's friendly (6 goals, 11
  matches, 303.9 min).
- **Change:**
  - Add a second cached instance, `catalogue_profiles(basis="fixtures")`, which skips `use_england`. Every read for
    catalogue pages uses it: `/api/catalogue/players/{gid}` (`touch_map`, `summary`, `moments`, and B3), the competition
    page, `/api/players/{gid}/heatmap?competition=`, and the profile seeds.
  - `/api/players` in catalogue mode keeps `ENGLAND_BASIS` as it is (PR #39's test).
- **Add** `not_counted` to each England row of `/api/catalogue/players/{gid}`. It lists that player's claimed or
  uploaded matches (`match_id`, `date`, `opponent`, `source`, `title`). Replace `basis` with one plain sentence: "These
  numbers count the Regista League fixtures only (10 matches). His friendly v Calder Town, uploaded through the Player
  view, is not counted here."
- **Test:** with a done `LocalStore` upload for pl_bro_09, the catalogue profile still has 5 goals, 10 matches and
  274.3 min, and `not_counted` names the upload, while `/api/players/pl_bro_09` counts it (today's behaviour).

### B3. A catalogue profile in the profile page's shape

- **Endpoint:** `include=profile` on `GET /api/catalogue/players/{gid}`. It is an additive parameter, so no new route.
- **Each row gains `profile`,** in the requested `scope`, on the B2 basis:
  - `appearances`, `minutes`, `counts`, `per90`;
  - `matches[]`: `match_id`, round, date, opponent, home, score, uploader (named), camera, `clip_view`;
  - `stats[key]`: `{count, per90, percentile, pool (with words), reason, noisy, none_yet: {none, of} | null,
    evidence_total}`;
  - `ratios[key]`: `{value, num, den, percentile, pool, reason, noisy}`;
  - `evidence[stat]`: `{total, items: [{match_id, clip_id, t, minute, video_url}]}`, at most 10, with the true total;
  - `grid`, `moments` (40), `summary` (B4).
- **Passing numbers come from the metrics engine.** `passes`, `passes_completed` and `pass_accuracy` read its cells
  (`passes`, `passes_completed`, `pass_pct`: crosses included, labelled so), and so do the other ratios that `METRIC_OF`
  maps. Add a test that each profile ratio equals its `METRIC_OF` metric's value and denominator (review B pass 2).
- **Goalkeepers' outfield numbers: the metrics engine decides.**
  - A profile stat has a percentile for a position only when its terminal metric (`METRIC_OF`, or the same key) is
    scored for that position (`CATALOGUE[k].positions`). Otherwise there is none, with the reason "not ranked for
    goalkeepers".
  - Stats with no terminal metric (`forward_passes`) keep the profile engine's percentile for outfield players and
    get none for goalkeepers.
  - **Why this engine:**
    - It is Zaid's one ranking rule. The Terminal, `/api/catalogue/*`, Compare and the MCP tools already give no
      percentile there. A profile saying "50th among 11 goalkeepers" for interceptions would contradict the Terminal
      for the same player.
    - Goalkeeper pools are small (11 semi-pro men, 2 in Ghana U17), and outfield counts are mostly 0. So those
      percentiles are tie values, not information.
    - Saves, passes, recoveries and touches are scored for goalkeepers, so they keep their percentiles.
- **None yet** follows B5's flag. Lower-is-better counts (offsides, aerial duels lost) never read "none yet". At 0 they
  show "0" with the engine's percentile or reason, so the profile has no second rule (review B pass 5).
- **The scope toggle** refetches with `scope=`. The client caches each scope.

### B4. Summary wording for catalogue rows

- **Change:** add a wording hook to `season/summaries.py`. Its default is today's text, so `/api/players/{gid}`'s
  summary stays byte-identical (snapshot `player_star`). The catalogue path passes the competition's words:
  - **Full coverage:** "the Regista League's 18 forwards".
  - **Sparse:** "the 12 forwards with enough minutes in <competition>'s uploaded matches".
  - **A row without enough minutes:** no rank clause and no "also ranks" sentence. Instead: "not ranked: 30 minutes,
    under the 45 needed".
  - **Numbers:** rates with two decimals ("2.30 per 90"), percentages with one ("91.6%"). The pass sentence comes from
    `pass_pct` (B3).
  - **"Round N"** stays; it is the competition's own round number. The word "matchday" never appears.
- **England:**
  - A catalogue row may show the stored Foundry summary only if `summary_for` validates it against the
    fixtures-basis profile. Say "Foundry" when it is one.
  - Otherwise it shows the rules summary with these words.
  - Update `summary_note`.

### B5. "None yet" and an explicit count flag

- **The flag.** Add `COUNT_METRICS` in `season/metrics.py`, a frozenset that is **not** in `Metric.public()` (the
  snapshot). A count is a per-90 or total metric whose unit is a count, not m, km/h, xG, xT or %, and whose key has
  neither `_diff` nor `_minus_`. That is the sandbox's 70 metrics.
- **The rule.** A count where higher is better, at exactly 0, is "none yet":
  - **Cells** (catalogue mode only): `none_yet: true`, `percentile: null`, and `zeros: {none, of}` in that scope.
  - **Ranking:** no place; the row is listed after the ranked rows. This applies to `/api/catalogue/rank`,
    `/api/catalogue/players`, the terminal endpoints in catalogue mode, Compare's `best`, and the MCP tool
    `search_catalogue_players`.
  - **Boards:** each board gains `with_any` and `none_yet` counts, so a list can end with "17 of the 66 players on
    this list have any goals so far."
- **Where it shows.** `/api/catalogue` lists `count_metrics`. The profile (B3) and Find players use the same flag.
- **xG, npxG and xA at 0 stay ranked** (they are measures; this matches the sandbox and the API). Zaid can still change
  that (§6).
- **Update the PR #39 tests** whose expectations rank zeros (rank paging and ties).

### B6. Pool words

- **Change:**
  - Every catalogue pool object gains `words`:
    - level: "semi-pro men forwards";
    - competition: "forwards in Regista League";
    - all: "men forwards at every level".
  - `levels.pools[]` in `/api/catalogue` and `/api/competitions` gain `words` and `label` (the export's `level_words`
    and `level_label`).
- **The client** builds the line with one helper, `Regista.poolLine(cell)` in `shared/regista.js`: "98th percentile
  among 33 semi-pro men forwards". The All scope adds `warning`. A small pool adds its reason; a pool under its minimum
  says "too few for a percentile: it takes 5".

### B7. The sample in plain words

`sample.words` on each competition (the competition page, `/api/catalogue/players` `pools`, terminal `season`), for
example "a regular's season here is about 59 minutes" and "per 90s rest on the 8 uploaded matches". Also one plain line
for what ≈ means. This replaces the sandbox's `plainSample` and its code-reference stripping.

### B8. Squads with playing time, clubs, and Player-view uploads

- **`/api/competitions/{id}`:**
  - squad entries gain `appearances`, `minutes`, `qualified` and `played`;
  - clubs gain `uploaded_matches`;
  - the page gains `player_uploads` (B15). Each is a done `pv_` match whose manifest names this competition: title,
    date, uploader, and "uploaded through the Player view; not counted in this competition's numbers".
- **`/api/catalogue`** gains:
  - `clubs` (66: `club_id`, name, `short_name`, `competition_id`, kit), for the Terminal's team picker;
  - `count_metrics` (B5);
  - `as_of` and `as_of_note`.

### B9. Team needs owned by the engine

- **`tier` takes a comma list** (`amateur,college,academy`). A single value is still valid. It applies to every `Where`
  filter and the MCP tool.
- **`min_percentile`** goes on `/api/catalogue/rank` and `/api/catalogue/players`. "Fits" is then the engine's: the
  percentile in the row's own pool is at or above it, and the row is not "none yet".
- **`sort=minutes` and `sort=name` on `/api/catalogue/players`.** Today they are refused (422, "unknown metric
  'minutes'", probed). Find players' "Minutes played" sort and Switch player both need them. Minutes rank one board per
  level by value, which is the sandbox pick Zaid approved; name is alphabetical, with no places.

### B10. Compare's "best" from the server

`/api/catalogue/compare` gains, per metric, `best: [global_id…]` and `best_rule`:
- **One level:** the best raw value. Ties on the shown value share the mark.
- **Several levels, one position:** the best percentile.
- **Several levels and positions:** no mark, and the reason why.
- **Never** a "none yet" row.

### B11. Similar players' reasons in plain words

- Add a plain phrase per metric (`PLAIN`, in the catalogue module), the sandbox's list: "getting good scoring chances",
  "actions that lead to a shot", and so on.
- Serve `shared_strengths_words` in catalogue-mode `similar` only. The default `similar` answer is in the snapshot.

### B12. Links for every catalogue player

- `profile_url` becomes `/players/{gid}` for every catalogue row:
  - in `CatalogueMetrics.card` (drop the `None` for non-England rows);
  - in `/api/players` catalogue-mode cards;
  - in `/api/catalogue/players/{gid}` and in similar rows.
- Cards gain `also_in` (the other competition ids) for career players.

### B13. `/players/{gid}` serves catalogue players

- The route is unchanged. The page reads B3; a `pl_` id that is in no squad shows the page's "missing" state.
- **Check** that `tests/test_player_page.py` and `test_me_page.py` pages still load.
- No new route.

### B14. The Scout agent on the catalogue

- **`cloud/foundry.py`:**
  - `SCOUT_TOOLS` adds `list_competitions`, `search_catalogue_players` and `get_catalogue_player`;
  - `SCOUT_INSTRUCTIONS` add the catalogue's rules: percentiles within level by default; say the pool and its size;
    warn across levels; never put men and women together; say "none yet" for 0 on a count; invented names; quote only
    tool numbers.
- **`season_api._scout_foundry`:** the MCP child's env adds absolute `REGISTA_CATALOGUE` and `REGISTA_CATALOGUE_ROOT`.
- **`season/scout.py`:**
  - `PLAYER_TOOLS`, `run_tool` and `from_foundry` handle the catalogue tools. The cards are catalogue rows: competition,
    country, value, pool, small, noisy, minutes, `profile_url`.
  - `unverified_numbers` checks the reply against those results.
- **`/api/scout/ask`:**
  - The body gains an optional `where: "catalogue"`. The default stays the league, so the `scout_ask_rules` snapshot is
    unchanged.
  - With `where: "catalogue"`, the rules engine parses place words server-side, then calls
    `catalogue.tools.search_players`. The place words are a small Python port of `terminal-place.js`'s vocabulary,
    built from the catalogue index: countries, tiers, age groups, gender, competition words, "my level" and "whole
    catalogue". The metric and position come from `answer_rules`' parser.
- **Tests:**
  - the stand-in Foundry answerer, as in `tests/test_scout_agent.py`;
  - the three sandbox questions ("Who are the best U19 forwards?", "Find me women forwards who score", "Which amateur
    midfielders create the most chances?") give the same rows as `search_catalogue_players`;
  - a test that `where` is ignored by the league snapshot.
- The image smoke test already expects the catalogue tools in the Regista MCP server's list.

### B15. Uploads from catalogue clubs

- **`player/film.py`:**
  - `friendly_kwargs`, `roster_for` and `film` take `competition_id` (default `None`, which means the Regista League).
    With an id, they load `catalogue.store.competition(cid)`, which is league-shaped.
  - The CLI gets `--competition`.
  - Keep `ratings=False`. Nothing from `attributes` or level scales may enter the roster header or the manifest; add a
    test that walks both for the hidden keys.
- **`player/store.py`, `UploadRecord`:** add `competition_id: str | None = None` (`None` covers today's records),
  `camera: str | None = None`, `date_played: str | None = None`, `uploader_type: str = "player"` and
  `consent: bool = False`. `from_json` already ignores unknown keys, so old records load.
- **`player_api.py`:**
  - `create_upload` reads `competition_id`, `camera` (tripod, phone, drone or broadcast), `date` and `consent`; raise
    `max_fields` from 8 to 12.
  - It validates:
    - the player is in that competition's squad (`_person` becomes catalogue-aware);
    - the opponent is a club of that competition and not the player's own;
    - the date is ISO, on or after the season's start and not after today;
    - with a `competition_id`, the video, the date, the camera and `consent=yes` are all required. Today's league
      form keeps working.
  - Refusals are plain 422 messages.
  - `_view` adds the new fields (additive).
- **`player/worker.py`:** pass `rec.competition_id` to `roster_for`. The manifest adds the competition labels, camera,
  uploader `{type: player, global_id}` and date. The title stays "<name>'s match: H v A".
- **Profiles:**
  - Check that `Season._aggregate` (England) skips upload rows whose global id is not a league player; filter in
    `uploaded_matches` if it does not.
  - `uploaded_matches` rows carry `competition_id`.
- **Joining:** B8's `player_uploads`, and B2's `not_counted` in the career and profile. They are named and **never
  counted**. The catalogue engine reads fixtures only, which is Zaid's rule.
- **Measure:**
  - The vision layer has been measured only on rendered league matches, never on catalogue kits (women's and youth
    clubs' colours).
  - Run one local end-to-end on `LocalStore`: `film --competition co_nga_am_men …`, upload through `TestClient` with a
    test token, `worker --once`, answer the questions. Record clip recall and precision against the film's truth in
    the build report.
  - No Azure.

### B16. Optional: one search over every match

Build this only if §2.11's measurement asks for it. `POST /api/catalogue/search {message, states}` runs the rules
`/chat` turn over every match in a thread pool. It returns each match's output (results, understood, state) in one
answer, grouped by competition. The answer is the same as the fan-out, in one request, and follow-ups keep each match's
state. It is a new route, so it needs a row in `tests/test_access.py` (public: reads only).

### B17. Small fixes

- **Plain career stories** for pl_sot_09 and pl_nvc_08 (the sandbox's `STORIES`). Change them in
  `catalogue/define.py` `CAREERS`, regenerate `data/catalogue/catalogue.json`, and check that no pin moved and
  `tests/test_catalogue_define.py` passes.
- **Refresh the stale examples in `docs/catalogue/build/api.md`:**
  - Sergio Cruz's 1.79 at the 98th percentile among 27, and his 58.3 minutes;
  - Edson Jimenez's minutes;
  - the "matchday" titles.

## 4. Not ported

These are deliberately left behind.

- **The sandbox's minute rewrites:** none. The engine's minutes stand.
- **Browser-side ranking:** `SBCat.byValue` and `SBCat.places`, Find players' `boardsFor`, Team needs' `fits()`, and
  the Terminal's own sort. They all become API calls.
- **The sandbox's summary regex rewrites, `zeroLine`, `plainSample`, and the `align_catalogue.py` passing fix.** They
  become B3, B4, B5 and B7.
- **"Sandbox: nothing was uploaded" and "Example … calls no AI model" labels.** The app does the real thing, labelled
  with what really ran.
- **The sandbox's stale `matches.json`, `results.json`, `scout.json` and `profile.json`.** The app reads the current
  season from the API.
- **Load-size work for the sandbox's JSON files.** It does not apply.

## 5. Order, split and checks

**Order.**
1. **Backend first,** one builder: B1-B15, then B17, plus their tests. Commit by item.
2. **Then four UI builders in parallel** against §3's contracts:
   - (a) Scout: §2.1-2.7;
   - (b) profiles and the Player view: §2.8-2.9;
   - (c) the Terminal: §2.10;
   - (d) the Clip view: §2.11, then B16 if measured.
3. **Then a check** and two independent reviews, as in the sandbox rounds.

**Each builder checks:**
- **Their own server:** `REGISTA_DOTENV= uvicorn regista.api:app --host 127.0.0.1 --port <8211-8299>`, in the
  background. Kill it when done. Never use port 8040 or 8060.
- **The built-in browser** at 1440 and 375 px:
  - no console errors;
  - `scrollWidth` 375 on every route touched;
  - close the tabs and reset the viewport afterwards.
- **These numbers hold on screen:**
  - Femi Toure: 5 goals, 10 matches, 274.3 min; non-penalty goals 1.64 per 90 at the 98th percentile among 33
    semi-pro men forwards (97th among 18 in his competition, 96th among 123 at every level); the friendly named, not
    counted;
  - Sergio Cruz's career strip (2 and 2 matches);
  - "U19 midfielders in Spain" gives 11 players;
  - "most goals in England" gives 25 ranked (116 none yet);
  - the table matches `/api/catalogue/rank` row for row.
- **Both suites,** quick and slow.
- **`node --check`** on new JavaScript, and the stdin node harnesses.
- **No `style=`, inline handler or script** in the diff.
- **Every value** goes through `esc()` or `textContent`.

**Reports** go in `docs/redesign/catalogue/`: `build-backend.md`, `build-scout.md`, `build-profiles.md`,
`build-terminal.md`, `build-clips.md`, then `check.md` and the reviews.

**CLAUDE.md** gets a §2.11 update when the port lands, plus its §3.0 entries for any new files.

## 6. Still Zaid's call

None of these block the port.

1. **xG, npxG and xA at exactly 0:** ranked, as now and in the API, or "none yet"? B5 keeps them ranked.
2. **The Home prompt "take-ons in the final third":** the search does not read "final third". Label what was
   understood, or replace the prompt.
3. **England's stored Foundry summaries** on catalogue profiles: show one only when it still validates against the
   fixtures-only numbers (B4's plan), or always use the rules summary there.
4. **"Add a match" on catalogue profiles:** this map keeps it for England players and sends catalogue players to `/me`.
5. **Date of birth** is served in `/api/competitions/{id}` squads. It is public synthetic bio. The sandbox showed age
   only, and so will the port.
6. **The vision layer on catalogue kits:** B15 measures it once, locally. If it is poor, the build report says so
   plainly, and the upload flow stays labelled.
