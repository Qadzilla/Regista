# Catalogue UI port: review A, pass 2 (engineering)

Branch `ux/catalogue` at 2522180 (fixes round 1), reviewed as `git diff feature/catalogue...HEAD` (66 files,
+8766 / -1388), with most attention on what round 1 changed. Lens: API additions, back-compat, CSP and escaping,
`Regista.store`, the upload backend, the Scout agent's tools, packaging and smoke, tests and their speed, cold loads, and
whether the live app's existing pages survive a deploy.

**Verdict: not signed off.** Nothing must be fixed, and nothing here blocks a deploy. One thing should be fixed: a rules
answer that contradicts itself, which round 1's new "no stat" note introduced. The pass-1 items round 1 took on are fixed
and hold up under my checks.

## How I checked

- **Test suites (Mac):** the quick suite passed 1,095 in 289 s, and `-m slow` passed 15 in 145 s. The slowest tests
  are still the existing vision ones. The only catalogue tests in the top 25 take 3-5 s.
- **Local server:** I ran my own server on :8279 with `REGISTA_DOTENV=`, a copy of `data/player` as the player store
  and a test token generated for this run. It is now stopped. I used the built-in browser at 1440 and 375 px in a tab of
  my own, which I closed afterwards.
- **Writes:** none to the live app, Azure or Fabric.
- **Shared scratch folder:** I reused common file names there (`player/`, `token`, `server.log`, `quick.log`,
  `slow.log`), so earlier agents' copies were replaced. The `player/` I replaced was the verifier's finished scratch
  store. The other live server (:8263) uses its own `rb2/` folder and was not affected. The repo's `data/` is
  untouched.

## Round 1, checked

- **The directory read, `GET /api/catalogue/directory`:**
  - It is public and listed in `tests/test_access.py`.
  - It has no parameters to validate.
  - It sends the cards without cells, pools or samples. The hidden-key payload test covers it.
  - It takes about 17 ms warm. Its body is 642 KB, or 55 KB gzipped.
- **The cold Terminal load,** measured in the browser: 27 API calls, 234 KB on the wire and 2,255 KB decoded, as round
  1 reports. A name search ("Izan Marquez") then finds the player and opens his card at 375 px.
- **The `_JSONGzip` middleware** compresses only status-200 JSON bodies of at least 1 KB that arrive whole. I checked
  with curl that everything else passes through untouched:
  - an MP4 range request still answers 206 with `video/mp4`, a `content-range` and no encoding;
  - HTML, scripts, CSV, 400s and 404s are not compressed;
  - HEAD answers carry a correct gzip `content-length`;
  - the security headers are still on every answer (`_Hardening` is the outer layer).

  On the cost: compressing the largest page this app serves (1.25 MB, `/api/catalogue/players?limit=200`) adds about
  15 ms on the event loop.
- **One shot count:**
  - Pavel Petrov's profile (1440 px) reads "Shots on target (penalties excluded)" and "33.3% of shots on target,
    penalties excluded (1 of 3)", matching Find players.
  - `/me` My profile now comes from the catalogue API, with no "(incl. penalties)" left on screen.
  - The league's `/api/players/{id}` is unchanged, and the back-compat tests are green.
- **The moment clock:** Pavel Petrov's cards read "ON THE BALL · ROUND 4 · 48:28", and the highlight reads "FT". Sergio
  Cruz's profile at 375 px reads the same way. Titles and `match_minute` are unchanged.
  - `clock_of` reads `SeasonMetrics.match_clock`, which the constructor always builds. Nothing loads metrics from a
    pickle, so no stale object can lack it.
- **The rules answers:** I asked 26 catalogue questions. "Sergio Cruz" now gives the none-yet reason, "Sergio Cruz
  shots" answers with shots, there is no "No the …" and no "college college", "fewest fouls" reads "has the fewest …",
  and "most yellow cards" ranks by yellow cards.
- **Phone (375 px):** `scrollWidth` was 375 on:
  - Sergio Cruz's profile;
  - the Terminal, before and after a search;
  - `/me` Overview, Matches, Team and Messages;
  - the Clip view on `cm_nam_02_irk_ads`, where a clip played (readyState 4).

  No page logged a console error.
- **Back-compat:**
  - `tests/test_backcompat.py`, `tests/test_catalogue_backcompat.py`, `season/pins.py`, `league.json` and the
    generator have an empty diff against `feature/catalogue`.
  - The smoke test's `STATIC_FILES` includes `terminal-place.js`.
  - The new tests pass the node harnesses their data on stdin, with no large command-line arguments.
- **Unchanged since pass 1:** the upload backend's validation and token gate, and the Scout agent's public-only tools
  (`SCOUT_TOOLS`).

## Should fix

1. **The rules answer to a minutes question contradicts itself** (`src/regista/catalogue/scout.py`: `stat_asked`,
   `default_note`, `metric_for`).
   - "who plays the most minutes in Spain" answers: understood "(heard “most minutes” → minutes)", then the reply ends
     "I did not find a stat I know in the question, so this ranks by Non-penalty xG". "who played the most minutes
     among U19 players" does the same.
   - The cause: `stat_asked` and `metric_for` treat "minutes" as no stat, so `defaulted` is set even though the parser
     heard one.
   - Before round 1 the answer silently ranked by npxG. Now it says something false.
   - Fix it either way:
     - rank by minutes (`/api/catalogue/players` already sorts by `minutes`);
     - or word the note for this case ("Minutes are not a ranked stat here, so this ranks by …").
   - A related weakness: the catalogue phrase match runs only when the league parser finds nothing. So "who has the
     most touches in the box" ranks all touches, and "who wins the most aerial duels" ranks aerial duels rather than
     aerial duels won. Both say so in "understood", so these are honest, just weaker.

## Smaller items (fix with the above if convenient)

- **Carried from pass 1, not fixed:** `player_uploads()` is still uncached (`src/regista/player_api.py`).
  - Each public `/api/competitions/{id}`, `/api/catalogue/players/{id}` (through `not_counted`) and `/api/player/uploads`
    read lists the Blob `uploads` container (videos included) and downloads every `record.json`. A profile load makes
    three such reads.
  - With a few records on the live app this costs tens of milliseconds, not seconds.
  - `uploaded_matches()`'s 30 s listing (`LIST_TTL_S`) would serve it.
- **Gzip runs on the event loop.** It costs about 15 ms per MB here and a little more on the container. It is fine at
  today's sizes. If whole-catalogue Terminal payloads (about 6 MB) become common, compress in the threadpool.

## Nits

- `_JSONGzip` checks only for "gzip" in `Accept-Encoding`, so `gzip;q=0` would still get gzip. No browser sends that.
- No test covers an MP4 range request under gzip (I checked it by hand). One line in
  `test_json_answers_are_gzipped_and_video_and_pages_are_not` would pin it.
- `me.js` line 151 still has a `clean()` that strips "(incl. penalties)". The catalogue labels no longer contain those
  words, so it is dead code; `profile-view.js`'s `clean()` is now an identity function.
- Rules replies print metres as "12120.00 per 90" ("who covers the most distance in Spain"), with no unit and two
  decimals.
- A Foundry summary stored for a league player would still be served on England's catalogue page and could quote the
  profile engine's shots, which include penalties. Today every stored summary is `rules-v0`, so none is served there.
- Carried: a failed worker job shows the raw exception, including a temporary path, on `/me`.

## Not checked

- Linux CI (nothing was pushed).
- The Foundry engine with a real model.
- A full worker upload: the verifier ran one in a scratch store in the last round, and round 1 did not touch the
  worker.
