# Catalogue UI port: review A, pass 1 (engineering)

Branch `ux/catalogue` at bc4ae69, reviewed as `git diff feature/catalogue...HEAD` (60 files, +7874 / -1387). Lens:
API additions, back-compat, CSP and escaping, `Regista.store`, the upload backend, the Scout agent's tools, packaging and
smoke, tests and their speed, cold loads, and whether the live app's existing pages survive a deploy.

**Verdict: not signed off.** Nothing must be fixed. Four things should be fixed: three in the catalogue rules engine's
answers, one about how much data a cold Terminal load sends. Two smaller performance items are listed with them. Nothing
here blocks a deploy.

## How I checked

- **Suites (Mac):** quick suite 1077 passed in 274 s; `-m slow` 15 passed in 131 s. The slowest tests are the existing
  vision ones. No new test is in the top 25 except a few catalogue tests at 3-4 s.
- **Local server:** my own server on :8263 (`REGISTA_DOTENV=`, a scratch player store, a test token generated for this
  run), now stopped. Built-in browser at 1440 and 375 px. I reused one stale tab whose server was gone, then closed it.
- **Writes:** none to the live app, Azure or Fabric. The upload probes below ran against the scratch store only; every
  one was refused, so no record was written.

## What holds

- **Upload backend: validated and token-gated.**
  - Without a token: 401.
  - Player not in the competition: 422 ("no player 'pl_ads_01' in Liga Juvenil Levante Interior").
  - Opponent from another competition: 422.
  - Bad camera, a future date, a date before the season (taken from the competition's window), 2026-02-30, a malformed
    or unknown `competition_id`, `consent=no`: each gives a plain 422.
  - The Regista League's friendly form without `competition_id` behaves as before (404 for a club outside the league).
  - `UploadRecord`'s new fields have defaults, so old records still load (a test covers it).
  - `_keep_manifest` keeps the worker's title and labels after an answer and drops the machine paths (tested).
- **League profile untouched by catalogue uploads.** A finished catalogue-club upload enters `uploaded_matches()`.
  `Season._add_claimed` keeps only global ids already in the league (`if gid in acc`), so Femi Toure's league profile
  cannot pick up a Nigerian player's match.
- **Scout agent tools are public and read-only.** `SCOUT_TOOLS` adds only `list_competitions`,
  `search_catalogue_players` and `get_catalogue_player`. They reach the agent through `allowed_tools`, so it gets no
  Cosmos DB namespace and no `render_clip`. `where` is an optional field. `where: "mars"` gives 422; without `where`
  the answer is the league's, as before.
- **API additions validated.**
  - Comma lists on `tier` and `position` are bounded by regex. I probed lists across `/api/terminal/screen`,
    `/api/catalogue/matches`, `/api/competitions`, `/api/players`, `/api/season` and `/api/teams`: all 200, with the
    expected totals.
  - `min_percentile` is bounded to 0-100. `sort=name` together with `min_percentile` gives a plain 422.
  - `include` accepts only `profile`.
- **Back-compat.**
  - `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched and green.
  - No new route, so `tests/test_access.py` needs no change.
  - The generator, `season/pins.py` and `league.json` are unchanged.
  - The catalogue title change ("Round N: …") is picked up by `_labels_current`, so a stale folder rebuilds. The image
    builds the catalogue at `docker build` time anyway.
- **CSP and escaping.**
  - I listed every `${…}` added in the static files. The ones without `esc()` are built strings, and I followed their
    call sites: `poolLine`, `agentRow`, `momfilter`, the career story, the Answered-by line. Each ends in `esc()` or
    `textContent`.
  - No `style=` attributes, inline handlers or direct `localStorage`; per-visitor state goes through `Regista.store`.
  - `/players/{id}` cannot be framed (`frame-ancestors 'none'`).
- **Phone (375 px).** `scrollWidth` was 375 on:
  - Scout: terminal, overview, find, competitions, shortlist, team;
  - a Nigerian profile (`/players/pl_ads_01`);
  - every `/me` section, including `#matches/add`.
- **Unknown player.** `/players/pl_nope_99` says "No such player" in plain words. The Clip view on `cm_nam_02_irk_ads`
  names the competition, country, level, date, uploader and camera.
- **Packaging.** `terminal-place.js` is covered by package-data (`static/*/*.js`) and is in the smoke test's
  `STATIC_FILES`, along with `terminal-words.js`.
- **Hidden data.** The roster and manifest of a catalogue upload are built with `ratings=False`, and a test walks them
  for hidden keys.

## Should fix

1. **The catalogue rules engine gives the wrong reason for "none yet" on a named player**
   (`src/regista/catalogue/scout.py`, `_pool_line` and `player_card`).
   - "Sergio Cruz shots" answers: "non-penalty goals none yet, no percentile (not enough minutes)".
   - He has 49.9 minutes at CF Torrevalle, where 45 are needed. The real reason is "none yet", which the rest of the
     port words as "None yet · N of the M … have none".
   - `_pool_line` falls back to "not enough minutes" whenever the percentile is None.
2. **A named player's answer ignores the stat that was asked.** `answer_catalogue` calls `player_card(cm, named)`
   without `sort`, so the card and reply show the position's default metric. In the example above, `understood` even
   says it heard "shots", while the reply talks about non-penalty goals. The fix is to pass `metric_for(q["sort"], …)`.
3. **Broken sentences in catalogue rules answers** (`reply_for` and `answer_catalogue`).
   - Empty result: "No the women goalkeepers in Nigeria in the catalogue match that yet." The `who` string already
     starts with "the".
   - `tier=college` with `age_group=college` and no gender: "leads the college college players". The level words are
     a plain join when gender is missing.
   - An ascending ("fewest") answer still says "leads" (the "fewest yellow cards in college" question: "Andre Johnson …
     leads … for non-penalty xg: 0.00 per 90").
   - The same question's stat (yellow cards) is not understood and falls back to npxg. `understood` shows the fallback,
     but the reply does not say the stat was not understood.

   This engine answers whenever Foundry is not set up or is rate-limited, so judges can see these sentences.
4. **Cold Terminal load sends about 3 MB of uncompressed JSON.**
   - Measured in the browser on a cold page: 32 API calls, 2,967 KB.
   - `directory()` pages the whole catalogue: six calls of `/api/catalogue/players?sort=name&limit=200`, about
     250 KB each, about 1.3 KB per row (each page also repeats rules, pools and `samples`). It does this just to build
     the name index.
   - The opening screen adds another 394 KB.
   - The app sends no `Content-Encoding`. On the live app in France Central, that is seconds on a judge's first visit.
   - Fixes: a slim directory read (id, name, club, competition, minutes), or compressing JSON responses only. Do not
     compress MP4 range responses.

## Smaller performance items (fix with item 4 if convenient)

- **`player_uploads()` is not cached** (`src/regista/player_api.py`). It runs on every `/api/competitions/{id}` and,
  through `not_counted`, on every `/api/catalogue/players/{id}`.
  - With Blob storage that means one list of the `uploads` container plus one download per record, on every public
    profile and competition view.
  - On England's page it also calls `ensure_match` for every finished friendly.
  - `uploaded_matches()` already keeps a 30 s listing (`LIST_TTL_S`); the same cache would do.
- **`not_counted(gid)` builds the app's league season** (`season_api.season()`) even for a player who is not in
  England. The season is cached, but a profile in Spain then waits for the league build on a cold replica.

## Nits

- `POST /api/player/uploads` accepts England's id as `competition_id`. The record then says `kind: "match"` and the
  manifest carries catalogue labels with `counted: False`, but the header says it is a friendly and the league profile
  counts it. The UI never sends it (`me.js` leaves it out for England). The API could treat England's id as the
  friendly form.
- `include=profile` hard-codes `moments=40` and ignores the endpoint's `moments` parameter.
- `include=profile` writes each row's summary twice (`row["summary"]` and `profile["summary"]` both call
  `summary_row`).
- `summaries._num` uses `:g`, which would print a count of 1,000,000 or more as `1e+06`. That is harmless at today's
  sizes; `int()` where the value is whole would be safer.
- Find players' cards show "0.00 assists per 90" beside the headline stat. The pool lines say "None yet" for zeros, but
  these secondary numbers do not. This is a parity question for review B.
- Carried, not from this branch: a failed worker job shows the raw exception, including a temporary path, on `/me`.

## Not checked

- Linux CI (nothing was pushed).
- The Foundry engine with a real model: the tests use a stand-in.
- A full upload through the worker: the verifier ran one in the scratch store.
