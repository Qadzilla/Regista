# Catalogue UI port: independent verification

Branch `ux/catalogue` (cut from `feature/catalogue` = PR #39), 2026-10-26. I checked the four build rounds (backend
0787597, Scout 39bce59, profiles and Player view 8b4ee97, Terminal and Clip view 8db521d) without relying on their
reports. I used my own local server, the built-in browser at 1440 and 375 px, the sandbox at :8060 opened side by side
in the same tab, and the API. Fixes are in commit 8013023. Nothing was pushed or merged, and nothing reached Azure, the
live app or Fabric.

**Setup.**
- Server: `REGISTA_DOTENV= uvicorn regista.api:app --port 8271`, with a scratch player store, a scratch feedback folder
  and an admin token generated for this run (kept in a scratch file, never printed). The server is now stopped.
- Femi Toure's demo friendly in the scratch store: the friendly's match folder (`pv_8807d7835c`, from
  `data/player/matches`) plus a hand-written `done` upload record. This lets "named, not counted" be seen offline.
- The reference servers on :8040 and :8060 were left running. My browser tab is closed and the viewport is reset.

## Flows walked

| Flow | 1440 | 375 | What I saw |
|---|---|---|---|
| Find players: U19 midfielders in Spain | yes | yes | 11 ranked, 11 more without enough minutes. Izan Marquez is 1st (1.50 per 90, "97th percentile among 17 academy U19 men midfielders") and Mohamed Bouzid 2nd. The other nine read "None yet · 15 of the 17 … have none". Words and numbers are identical to the sandbox, apart from the app's ≈ marks. The order matches `/api/catalogue/rank` (with_any 2, none_yet 9). |
| My level | yes | yes | Semi-pro men, 33 forwards. Femi Toure is 1st (1.64, "98th percentile among 33 semi-pro men forwards"), then Kevin Jung (95th) and Emre Scholz. |
| Sergio Cruz's profile, career, scope toggle | yes | yes | The career strip has both clubs (2 matches · 47 min and 2 matches · 50 min, as `/api/players/pl_sot_09/career` gives 46.5 and 49.9). "Show these numbers" switches the summary, numbers and scout bar to the Juvenil row. Level / Competition / All levels re-ask the API: shots 97th of 16 → 95th of 10 → 63rd of 123, as the API gives. "All levels" shows the rough-guide warning. |
| Nigerian competition page | yes | yes | The Ogun Riverside Amateur League page: 4 uploads with uploader and camera, "Uploaded matches only, not a league table", and squads with minutes. The results table equals `/api/competitions/co_nga_am_men` row for row. Layout and words match the sandbox, except for the sample paragraph (the engine's B7 words, which replace the sandbox's `plainSample` as the port map says). |
| Clip view: one of its matches, clip playing | yes | yes | `/?match=cm_nam_02_irk_ads`: the match line names the competition, country, level, date, uploader and camera. Clip `cl_t_home_06_000018.mp4` played (readyState 4, no error). |
| Terminal: "most goals in England" | yes | yes | Femi Toure is first, 98th · pool 33, 1.64. The rows are identical to the sandbox's for the same search. |
| Terminal: "U19 midfielders in Spain" | yes | yes | 11 rows, Izan Martinez first (97th · pool 17). Identical to the sandbox. |
| /me: Switch player to a catalogue player | yes | yes | Switch player lists 1,052 players. Picking Adebayo Chukwu (pl_irk_05, Iroko Lions FC) switches the header, Overview (2 matches, 60 min, interceptions 89th of 41 amateur men defenders), Matches & videos and Team. |
| Catalogue upload flow, up to the write | yes | yes | Step 1 picks the competition, opponent, side and date. Step 2 takes the video, camera and the required consent box. The admin key is asked for. |
| One local upload (scratch store only) | n/a | n/a | Via the API with the test token. No token gave 401. Missing consent gave 422 ("tick the box …"). Missing date gave 422. The full form gave 201 (`up_37f1356258`, competition, camera, date and consent stored). Then `worker --once` ran with `models/vision_v4` in 44 s: needs_review, 29 clips (1 the player's), 6 questions about him. /me showed every agent step and the "Is this you?" questions. I stopped before answering, which is a write. |
| Scout agent, rules engine, catalogue question | yes | n/a | "Which amateur midfielders create the most chances?": Luis Gomez first, 1.74 key passes per 90, 98th of 33. It says how it understood the question and is "Answered by Regista's rules". The rows are the sandbox's. Over the API, three more catalogue questions answered as expected (U19 MF Spain, women forwards, goals in Nigeria). |
| Also compared with the sandbox | yes | n/a | Overview, Team needs ("A forward who scores · 21 fit", identical lists at your level and from below). |

## Numbers against the API

- **Five percentiles with pools.** Each matches between page and API:
  - Femi's goals, 98th of 33 semi-pro men forwards;
  - Femi's shots, 98th of 33;
  - Femi's key passes, 89th of 33;
  - Sergio's shots, 60th of 31 amateur men forwards (level) and 63rd of 123 men forwards at every level (all);
  - Izan Marquez's goals, 97th of 17 academy U19 men midfielders.
  
  Femi's goals, shots and key passes also equal `/api/players/pl_bro_09/metrics` (the Terminal's engine).
- **A competition table.** England: Brookfield 17 points, Fairhaven 2nd with 15 (the Team page says "2nd in the table,
  15 points from 10 matches"). Nigeria's uploaded-match results are as above.
- **A career.** Sergio Cruz: UD Sotoalto Juvenil (2, 46.5) and CF Torrevalle (2, 49.9), with the career story.
- **Femi Toure, league fixtures only on catalogue pages.**
  - Catalogue profile: 10 matches, 274.3 minutes, 5 goals, 1.64 per 90, noisy.
  - Sample line: "These numbers count the Regista League fixtures only (10 matches). Femi Toure's friendly v Calder
    Town, uploaded through the Player view, is not counted here."
  - `/api/competitions/co_eng_sp_men` lists the friendly in `player_uploads` with `counted: false`.
  - /me Overview: 10 matches and 5 goals.
  - The Scout Overview card: "Femi Toure added a match … (not in the catalogue's numbers)".
  - The league endpoint `/api/players/pl_bro_09` counts it (11 appearances), as PR #39's basis keeps it.

## Rules

- **CSP header** on `/scout`: `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, plus
  `X-Frame-Options: DENY` and `nosniff`. There were no console errors on any page I opened. A probe confirmed the
  console reader works.
- **Changed static files (18):**
  - No `style=` attributes, inline handlers or inline scripts.
  - Styles are set only through CSSOM (`el.style.x`), with colours checked against a hex pattern first.
  - A scan of every added `${…}` inside HTML templates found only `esc()`-wrapped values, numbers, generated ids or
    fixed words. The unescaped ones (`r.competition`, `they`) go to `textContent`.
- **Width at 375 px:** `scrollWidth` was 375 on every Scout section (overview, find, competitions, two competition
  pages, shortlist, reports, messages, team, settings, terminal), both profiles with a scope switch, every /me section
  including the add form and Switch player, the Clip view match, and Home results.
- **Hidden keys:** none in 53 payloads. I walked every new or changed read with the tests' hidden set (attribute keys,
  offsets, `level_scale`, `seed`, `age_range`, `level` as a non-label), plus `ratings`/`hidden`:
  - `/api/catalogue`, the pools, matches, players (three filter sets), rank (two), compare and career;
  - three `include=profile` profiles and two similar lists;
  - all 14 competitions and their player lists;
  - the uploads, the terminal screen, teams and the season;
  - three `where: "catalogue"` answers from `/api/scout/ask`.
- **Back-compat:** `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched and green. No route
  was added in this branch. `terminal-place.js` is covered by package-data (`static/*/*.js`) and is in the smoke test's
  `STATIC_FILES`.
- **SEASON_PINS:** untouched. The generator, `season/pins.py` and `league.json` are unchanged on this branch; only the
  two career-story strings in `catalogue.json` changed. So England semi-pro men stays byte-identical.
- **Linux CI:** the node harnesses pass file paths as arguments and the questions on stdin. No large command-line
  argument.

## Suites

- Quick suite at 8db521d: **1074 passed**.
- Slow suite (`-m slow`): **15 passed**.
- After my fixes (8013023): quick suite **1077 passed** (1074 plus the 3 new tests). The touched files plus both
  back-compat files passed first on their own (83).

## Fixed (commit 8013023)

1. **The profile's sample line spoke for the competition, not the player.**
   - What it showed: Sergio Cruz's numbers block read "Only uploaded matches count here: 5 so far … Per 90s rest on the
     5 uploaded matches. These numbers count …'s uploaded matches only (2 matches)." That is two different counts in
     one line, and his own minutes were missing.
   - What it shows now, as the sandbox words it: "2 matches · 50 minutes in Regional Preferente Levante Interior.
     CF Torrevalle played 2 of the competition's 5 uploaded matches. A percentile needs 45 minutes here."
   - The basis sentence is added only when it names something: England (league fixtures only, the friendly not
     counted) or a row with uncounted uploads.
   - The competition's own sample words stay on its page.
   - A test pins it.
2. **"5 Sept" next to "24 Oct".** The /me activity feed, profile dates and upload days asked the browser for an en-GB
   short month, which Chromium spells "Sept". They now use the same fixed month names as the rest of the app. A test
   keeps `month: 'short'` out of the dashboards' scripts.
3. **`worker --work <new folder>` failed every upload.** The cause was a FileNotFoundError from the temporary
   directory; it was found by the local upload run. The worker now creates the folder. A test checks it and fails
   without the fix.

## Open (not fixed; listed for the next round or Zaid)

1. **Worker failures show a machine path to the player.** The failed-job text on /me ends with the raw exception,
   including a temp path ("FileNotFoundError: … '/private/tmp/…'"). This is the worker's existing error format, from
   the Player view PR. A plain sentence, with the detail kept in the log, would be better.
2. **Minutes past the match length.** "dribble at 58'" and "shot at 50'" appear in 2 x 15-minute matches. This is
   Zaid's decision (the engine's minutes stay as they are), recorded here only because it shows on every catalogue
   page.
3. **Small wording differences from the sandbox, all minor:**
   - the competition page's sample paragraph is the engine's B7 words, and its camera note is longer;
   - the agent rows show no kit number;
   - the sort option reads "Shots per 90", not "Shots (incl. penalties) per 90";
   - the Overview card says "cut by Regista" without "on the live app".
4. **Sandbox cosmetics carried over unchanged:** "Any of these 1" as the Competition filter's first option, and the
   pool lines in small pools ("97th of 16" can read like a rank). Zaid's call in the sandbox notes.
5. **Cross-level lists read oddly by value.** "Best women forwards" lists Olivia Webb (1.10 per 90, 94th of 8, a small
   pool) before Kaitlyn Stewart (1.53) and Paige Allen (1.30). The order is right under the one ranking rule
   (percentile within each player's own level); the answer says the rows come from more than one level.
6. **Carried from the builders and confirmed, not re-tested in depth:**
   - the first Home search on a fresh process is slow (catalogue matches build on first use);
   - whole-catalogue Terminal payloads are large (about 6.4 MB);
   - Reports cannot insert moments for a catalogue-only player;
   - the vision layer on catalogue kits is measured on single matches only (this run: 1 clip of the player's, 6
     identity questions, not scored against truth).
7. **Side effects, scratch only:** my worker run picked up a stale queued message left in the session's scratch store by
   an earlier builder (`up_985965981e`) and marked it failed. It lives in the scratch store only; the repo's `data/`
   is untouched.
