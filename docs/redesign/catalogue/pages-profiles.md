# The catalogue UI port: profiles and the Player view

Branch `ux/catalogue` (on top of PR #39; not merged, not pushed). Written 2026-10-26 by the profiles builder, following
`port-map.md` §2.8-2.9 and the backend in `backend.md`. This round ports the sandbox's catalogue profile
(`sandbox/catalogue-profile.js`) and Player view (`sandbox/profile.js`) into `/players/{id}` and `/me`, on the real API.
Everything shown is synthetic: invented players, clubs and competitions; countries and levels are labels.

**Zaid's port decisions, as built here.**
- **Minutes:** the engine's minutes are untouched. The moments behind a number show the engine's `minute`, the same
  minute the clip titles use ("goal at 6'", "Round 1 · Eastwick United 0–2 Brookfield Rovers · 6'").
- **Noisy marks:** a ≈ follows every number the engine marks noisy (tiles, ratios, the full table, the Overview), with
  one line saying what it means. Femi Toure's goals keep theirs.
- **League fixtures only on catalogue pages:** both pages read `/api/catalogue/players/{id}?include=profile`, so Femi
  Toure shows 5 goals in 10 matches over 274 minutes, and the sample line ends "These numbers count the Regista League
  fixtures only (10 matches)." A Player-view upload or a confirmed claim is named (the row's `basis` sentence, a "Not
  counted in these numbers" row under Matches, "not counted in your numbers" in All your matches), never counted.
- **Catalogue-club uploads** go through the new backend (competition, date, camera, consent; admin key for writes as
  today). A Regista League player's upload stays the league's friendly form (no `competition_id`), so nothing changes
  for the league or the live demo upload.
- One ranking rule, the engine's: the renderer never sorts players or numbers. Its only `sort` calls pick a player's
  row with the most minutes, order moments by the engine's watchability, and put matches newest first.
- "None yet" for zeros, pool lines "98th percentile among 33 semi-pro men forwards", small pools with their reason,
  Round (never matchday).

## The profile: `/players/{id}` for every catalogue player

**One renderer for both audiences.** `static/player/profile-view.js` gains `Regista.profileView.catalogue(root, P,
{ cat, audience, bar, comp, onSelect, stat })`, a port of the sandbox's `CP.render`. `/players/{id}` uses it with the
scout bar (audience `scout`); `/me#profile` uses it without (audience `player`: "you", similar players not linked). The
older league renderer `render` stays in the file (nothing calls it now; its helpers are used by Scout and the Terminal).
The touch map moved into a shared helper, `pitchMarkup(grid)`, which both use.

**What it reads.**
- `GET /api/catalogue/players/{id}?include=profile&moments=0`, level scope, plus `GET /api/catalogue` (competitions,
  level pools and their words, club kits, the ≈ words). The scope toggle asks again with `&scope=competition|all`,
  once per scope.
- `GET /api/players/{id}/similar?competition=&scope=&n=5`, per competition and scope.
- "Show more" under a number: `GET /api/catalogue/players/{id}?evidence=KEY&competition=&evidence_limit=N`, the
  engine's evidence list, used only when its count equals the profile's.

**What it shows**, in the sandbox's order:
- **Header:** shirt in the club's kit, name, position, club, number; age, height, foot, nationality; competition,
  country, level chip and "also plays in …"; "Synthetic player · invented name". My details from `/me#team` still
  show on top (name, position, number, foot, height, bio), on both pages.
- **Career strip:** every competition, even with no minutes: country, region, season, club, number, position, matches,
  minutes, "Enough minutes for percentiles" / "Not enough minutes for percentiles: 30 of the 45 needed" / "No minutes in
  an uploaded match yet", and the dates. A career player gets the story and the summed line; clicking a card switches
  the summary, numbers, touch map and similar players to that competition.
- **Summary:** the engine's sentences (B4 wording), each opening its number or playing its moment; "Written by Regista"
  or "Written by Microsoft Foundry, checked against the numbers" from the row's `engine`.
- **Best moments** across competitions, with competition chips for a career player and Play reel (the best ten, one
  after another, in the page).
- **Numbers in <competition>:** the Level / Competition / All levels toggle; the pool line ("Compared with the 33
  semi-pro men forwards with enough minutes, from Regista League (England) and Weserland-Liga (Germany)."); All levels
  adds the plain warning with the engine's reason behind "Why?"; the sample line (`sample.words` + `basis`); the ≈ line;
  six headline tiles per position (count, per 90, bar, pool line, small-pool flag); the four ratios from the metrics
  engine ("74.2% of passes completed, crosses included (92 of 124)"); the moments behind a number; "Every number in this
  competition", folded.
- **Where they play** (the touch map) and **Similar players** (club, competition, country, level chip, "both strong on
  …" from `shared_strengths_words`).
- **Matches:** newest first, grouped by competition for a career player, with the uploader in words, the camera label
  and "Watch in the Clip view" (the API's `clip_view`, on this player); then the matches named and not counted.

**The scout bar** (shortlist stage, Message, Compare, Notes, Write a report) now follows the competition on screen: the
renderer calls it again when Career switches rows, so Sergio Cruz's bar reads "Forward · UD Sotoalto Juvenil · Liga
Juvenil Levante Interior" after switching (check.md open point 5). Its buttons read the latest row.

**Add a match** stays the Regista League's (add-match.js: events + tracks or a local video, then a claim the Studio
confirms). `player.js` shows it only for league players and tells add-match.js through `RegistaPlayer.inLeague`, so it
asks nothing of `/api/players/{id}` for anyone else (no 404s). Everyone else gets one line: "<name> plays in
<competition>: matches are added from the player's own dashboard. Open it in Player profile" (`/me?player=…#matches/add`).
Its wording now says a confirmed claim is named on this profile, not counted in its numbers.

## The Player view: `/me`

- **The bar** at the top of every section: shirt, "Femi Toure (the default player) · Brookfield Rovers · Regista
  League, England · semi-pro men", Switch player. It moved from the header into the page so it fits at 375 px.
- **Switch player:** Name or club, and Competition (grouped by country). It lists players who have played in an
  uploaded match, from `GET /api/catalogue/players?min_minutes=0&sort=name&limit=40` (alphabetical, no places), one
  entry per player, Femi first when nothing is searched: "1,052 players who have played in an uploaded match; the first
  40 by name shown, search to narrow it. Synthetic data, invented names." Each entry: shirt, name, position, club,
  number, competition, country, level chip, "plays in two competitions". `?player=pl_…` opens anyone in the catalogue;
  an unknown id opens Femi and says "No player with that id is in the catalogue."
- **Overview:** the header with the where line; Needs you (unread messages, the latest upload's state, "Add a match you
  filmed", "Is this you?"); Your season (where the player has the most minutes: matches, minutes and three lead numbers
  with their level pool lines, small pools and ≈; a career player is told the other competition is on My profile); the
  best moment across competitions; Recent activity, newest first, a match listed once (a club upload folds into the
  match line: "Round 1: San Aurelio State 0–0 Mesa Alta College · uploaded by the Mesa Alta College team account").
- **My profile:** the shared renderer, player audience.
- **Matches & videos:**
  - **Add a match**, two steps. 1. The match: Competition (the player's own; two for a career player), Against (that
    competition's clubs, from `/api/competitions/{id}`), home or away, Date played (no later than today). 2. The
    footage: the video (required), Filmed on (Tripod, Phone, Drone, Broadcast camera) with the catalogue's camera note,
    and "Everyone I filmed agreed to be filmed and shown" (required). Outside England a line says the vision agents were
    measured on Regista League matches and have been run on one test match of other kits. It posts
    `POST /api/player/uploads` with the admin key as today; a refusal shows the server's words ("The upload was refused:
    the season started on 2026-09-05: a match before it is not this season's").
  - **Your uploads:** every agent step and its time, as before; the card adds the competition, the day played and the
    camera. A catalogue upload is titled "Match v …", a league one "Friendly v …". The finished card says the match is
    listed on the profile and not counted in the catalogue's numbers. When a finished upload is not yet named on the
    profile, the page reads the profile again once.
  - **In the catalogue:** matches the player uploaded, or their club's team account uploaded of a match they played
    (`GET /api/catalogue/matches?club=` for each club in their career), with uploader and camera.
  - "Is this you?" and **All your matches** (newest first, each opening in the Clip view; named-not-counted first).
- **Messages:** unchanged (one store with Scout), now attaching moments from any competition.
- **Team:** My details (this browser only), then the club in its competition from `/api/competitions/{id}`: crest,
  city and ground, table position or uploaded matches, the squad with minutes ("no minutes yet"), Results or "Uploaded
  matches", and England's league table or "Results so far" with "Uploaded matches only, not a league table". A career
  player picks between their clubs; at the second club they keep that club's number and position.
- **Settings:** unchanged.

## Files

| File | What |
|---|---|
| `static/player/profile-view.js` | `catalogue()` (the catalogue profile, both audiences), `pitchMarkup()`, `statPoolLine()`, `longDate()`; the league `render` kept |
| `static/player/player.js` | reads the catalogue profile; scout bar follows the row; Add a match only for league players; `RegistaPlayer.inLeague` |
| `static/player/add-match.js` | waits for `inLeague`; wording: a confirmed claim is named here, not counted |
| `static/player/index.html` | the line for non-league players; missing text |
| `static/me/me.js`, `index.html`, `me.css` | the bar, Switch player across the catalogue, Overview, the upload form, catalogue uploads, Team on the competition page |
| `static/shared/dashboard.css` | the `cp-*` rules (career, scope toggle, pool lines, ≈, small pools, ratios, matches) |
| `tests/test_player_page.py`, `tests/test_me_page.py` | updated for the catalogue reads; new checks: the endpoints, no browser ranking, the words, the upload form's fields and consent, Switch player |

No new static file, route or endpoint, so `pyproject`, `cloud/smoke.py STATIC_FILES` and `tests/test_access.py` are
unchanged. No backend change.

## Checks

- **Quick suite:** `python3 -m pytest -q`: 1064 passed. **Slow suite:** `-m slow`: 15 passed. Both on the Mac. Linux CI was not run (nothing
  pushed). `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` untouched and green. No test passes a big
  input on a command line.
- `node --check` passes on the four scripts. No `style=`, inline handler or script in the diff; me.js still builds every
  node with `textContent` (no `innerHTML`); the renderer escapes every API value with `esc()`; bar widths and the crest
  are set through `element.style`.
- **Local server** (`REGISTA_DOTENV= uvicorn regista.api:app --port 8253`, a scratch `REGISTA_PLAYER_DIR`; later with
  writes open, no key) and the built-in browser at 1440 and 375 px. `scrollWidth` equalled the viewport on every route
  touched: the profiles of Femi Toure, Sergio Cruz, Bernard Frimpong and a squad member with no minutes; every `/me`
  section for Femi, Olivia King and Sergio Cruz, the open Switch player and the add form. No console messages on fresh
  loads of `/players/pl_bro_09` (scope toggles, a tile, the reel), every `/me` section for Sergio Cruz with a career
  switch, and `/scout#find`. (Errors seen earlier came from my own probes: an iframe the CSP refused, a server restart,
  and the deliberate 422 refusal.) The tab was closed, the viewport reset and the server stopped.
- **Numbers on screen:**
  - Femi Toure: 5 goals, 10 matches, 274 minutes; goals 1.64 per 90, "98th percentile among 33 semi-pro men forwards",
    "97th percentile among 18 forwards in Regista League", "96th percentile among 123 men forwards at every level"; ≈ on
    goals; his five goals behind the tile at 6', 56', 49', 6', 8' (Rounds 1, 1, 6, 8, 10); the round 1 goal played
    (readyState 4); passes "the first 10 of 124", Show more gave 30; Add a match shown (league player).
  - Sergio Cruz: career strip 2 and 2 matches (47 and 50 minutes), the story, the switch to Liga Juvenil (bar,
    numbers, summary and similar players follow); "None yet · 15 of the 16 academy U19 men forwards have none".
  - Bernard Frimpong (Ghana U17 keeper): "No percentile: only 2 qualified academy U17 men goalkeepers to compare with
    (it takes 5)"; outfield numbers "not ranked for goalkeepers"; no Add a match, the line to his dashboard instead.
  - Kwame Nkansah (in a squad, no minutes): his career card and "has not played in an uploaded match yet".
  - Olivia King on `/me`: Pacific Coast Collegiate Conference as her main competition, Team on Mesa Alta College with
    "Results so far · Uploaded matches only", Oxenridge Women under the second chip.
- **Uploads, local store only:**
  - Through the page (Femi, writes open locally): the form refused without a date, a video and consent, then queued a
    friendly v Calder Town with the date and camera on the record and no `competition_id`. For Sergio Cruz's U19 side a
    June date gave the server's refusal word for word.
  - End to end for a catalogue club: `python -m regista.player.film --competition co_usa_col_women` (Mesa Alta College v
    Coralline University, 3 minutes), uploaded to the local server with competition, date, camera and consent, then
    `python -m regista.player.worker --once --models models/vision_v4` (60 s; 129 of 136 tracks named). The page showed
    every step with its time, "Match v Coralline University", her one moment and the recap; the profile then named it
    ("… Olivia King's match v Coralline University, uploaded through the Player view, is not counted here.") and still
    counted 3 matches; the competition page lists it under `player_uploads`.
  - Her clips against the film's truth, before any answer (one question, none about her): recall 0.33, precision 1.00
    (3 true clips, 1 found: the close-up; neither on-ball moment). With B15's Nigerian match this is a second single
    match on catalogue kits, not a measurement; the form's line saying so stays.
- Nothing reached Azure or the live app; no Fabric job ran.

## Open

1. **The engine's summary says "with 1 appearances"** for a row with one match (Finn Schmidt). It is the summary writer's
   text (backend), not the page's.
2. **Reports and Messages on Scout** still read the league profile for moments (pages-scout open item 1): "Write a report"
   from a catalogue player's profile opens Reports, whose "Insert a moment" cannot load outside the league.
3. **The league renderer `render`** in profile-view.js is now unused by the pages; it stays because its helpers and tests
   share the file. It can go in a clean-up.
4. **My details** apply at the player's main club; at a second club Team shows that club's own number and position.
5. **The vision layer on catalogue kits:** two single matches so far (B15's 0.60/0.75 before answers; this one 0.33/1.00).
   Worth a proper fresh set before the demo shows a catalogue-club upload.
