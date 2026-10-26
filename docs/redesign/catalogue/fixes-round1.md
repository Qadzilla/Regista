# Catalogue UI port: fixes, round 1

Branch `ux/catalogue` (on PR #39's `feature/catalogue`; not pushed, not merged). Six findings from review A and review B
(pass 1). All six are fixed, and none is left open. Tests are in `tests/test_catalogue_fixes1.py` (18 tests).

## 1. Named player's "none yet" answer gave a false reason

`regista.catalogue.scout._pool_line` used to fall back to "not enough minutes" whenever a percentile was missing. It
now gives the engine's own reason, in this order:

- **None yet:** "none yet · 24 of the 31 amateur men forwards have none", from the cell's `zeros`, worded as the pages
  word it.
- **The pool's reason:** for example "a season total: not ranked", "not ranked for this position" or "fewer than N
  qualified peers".
- **Minutes:** a season total says it is ranked by value only. A row under its competition's qualifying minutes says
  "N minutes, under the minutes a regular needs in …".
- **A ratio:** "too few attempts".
- **Otherwise:** just "no percentile", with no guessed reason.

A new helper, `_stat_words`, stops a none-yet number from printing "none yet" twice.

Sergio Cruz asked without a stat now reads: "Sergio Cruz (CF Torrevalle, Regional Preferente Levante Interior, Spain):
non-penalty goals none yet · 24 of the 31 amateur men forwards have none."

## 2. Named-player answers ignored the stat that was asked

`answer_catalogue` now passes the asked stat to `player_card` as `metric_for(<stat>, <the player's position>)`. With no
stat, the card keeps the position's first default column, as before.

"Sergio Cruz shots" now reads: "… shots 1.80 per 90, 60th percentile among 31 amateur men forwards; ≈ noisy over a
sample this size." The Find players page in the browser shows the same.

The "heard" lines now name the catalogue's metric, not the league profile's stat: "“shots” → shots", not "→ shots (incl.
penalties)". The catalogue's shots leave penalties out.

## 3. Broken sentences in catalogue rules answers

- **Empty result:** `who` no longer starts with "the". It now reads "No women goalkeepers in Nigeria in the catalogue
  match that yet."
- **"college college":** a new helper, `level_phrase`, says each level word once, following `level_words`' rule. "best
  college players" now reads "leads the college players".
- **Ascending answers:** they no longer say "leads". A count reads "… has the fewest fouls committed among the
  forwards: …". A measure reads "… has the lowest pass completion among the midfielders: …". The "Understood" line uses
  the same word.
- **Unrecognised stats:**
  - When the league parser finds no stat, `catalogue_stat` reads the question against every Terminal metric's label
    and key, singular or plural, longest name first. "most yellow cards" now ranks `yellow_cards` and says so in
    "Understood".
  - When nothing matches at all, the reply says what it ranks by instead: "I did not find a stat I know in the
    question, so this ranks by Non-penalty goals (the forwards' first column); the Terminal's search knows every metric
    by name."
- **Labels in sentences:** they keep their abbreviations ("non-penalty xG", not "non-penalty xg").

## 4. A cold Terminal load sent about 3 MB of uncompressed JSON

There are two fixes:

- **The directory read:** a new route, `GET /api/catalogue/directory`, returns every player-competition row once, by
  name. It holds the cards with no metric cells, pools or samples, plus each competition's `qualifying_minutes`.
  `terminal.js` `directory()` now makes this one call instead of six pages of `/api/catalogue/players`. A row that is
  in the directory but not yet in the table still knows its competition's qualifying minutes (`QMIN` in `minMin`).
  - The route is listed in `tests/test_access.py` (public), the Terminal's read-only allow list, the hidden-key payload
    test, `catalogue_api`'s endpoint list and `docs/catalogue/build/api.md`.
- **Compression:** `_JSONGzip` in `regista.api` is a pure ASGI middleware that sits inside `_Hardening`. It gzips JSON
  answers only, and only:
  - status 200;
  - one whole body of at least 1 KB;
  - no `Content-Range` and no existing encoding;
  - for clients that accept gzip.

  It also adds `Vary: Accept-Encoding`. MP4 (range answers stay 206 and uncompressed, checked with curl), HTML, scripts
  and CSS pass through untouched, and the security headers still apply.

Measured in the browser on a cold `/scout#terminal`, 1440 px:

| | Before | After |
|---|---|---|
| API calls | 32 | 27 |
| Data sent | 2,967 KB | 234 KB (2,255 KB once decoded) |
| The name directory | 6 calls of about 250 KB each | 1 call, 56 KB (642 KB decoded) |

Existing endpoints keep their shapes and defaults.

## 5. Profiles showed two shot counts on one page

I took the second option the finding offered: one number everywhere.

- **The page's numbers:** `regista.catalogue.page.FROM_METRICS` now serves the metrics engine's cells for `shots`,
  `shots_on_target` and `saves`, as B3 already did for passes. Each label says what is left out:
  - "Shots (penalties excluded)"
  - "Shots on target (penalties excluded)"
  - "Saves (penalties excluded)"

  An outfield player's saves keep the "not ranked for …" reason.
- **The labels on screen:** `profile-view.js` `clean()` no longer strips labels, and `scout.js` drops its three
  `(incl. penalties)` strips. Any number that still includes penalties now says so on screen.
- **The ratio row:** it reads "of shots on target, penalties excluded".
- **The summary:** the rules summary on catalogue pages reads the same three numbers from the metrics engine (they are
  `Wording.overrides`, like pass completion). The summary, the tiles, the table, Find players, the Terminal and the
  agent now agree.

Pavel Petrov (`/players/pl_dun_10`), checked in the browser:

- **The table:** Shots (penalties excluded) 3, 1.06 per 90, 44th percentile; Shots on target (penalties excluded) 1.
- **The ratio row:** 33.3% (1 of 3).
- **Find players:** 1.06 per 90 at the 44th percentile, the same.

Femi Toure's 19 shots do not change (he has no penalties).

The league's own `/api/players/{id}` profile (the back-compat snapshot) is unchanged.

## 6. Best moments had lost the match clock

- **The API:** profile moments now carry `clock`, the time the clip video's scoreboard draws. It is worked out from the
  match's periods by `regista.catalogue.page.clock_text`, the same rule as the renderer's `Scene.clock_at`, and a test
  checks the two agree. The field is on `rows[].profile.moments` and on the top-level `moments` of
  `/api/catalogue/players/{gid}`.
- **Unchanged:** titles and `match_minute` (Zaid's decision).
- **The page:** `profile-view.js` shows the clock on the stage line and on each moment card: "ON THE BALL · ROUND 1 ·
  05:48" for Femi Toure's first goal, whose title still reads "goal at 6'". A highlight shown after full time reads
  "FT", as its video does.
- **The evidence lists behind a number keep the engine's minute,** as the port's pages-profiles decision says.

## Checks

- **Test suites:** `python3 -m pytest -q` and `python3 -m pytest -q -m slow` both pass (1,095 and 15).
  `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` pass and are unchanged. The other test edits:
  - `test_scout_terminal.py` allows the directory read;
  - `test_catalogue_port.py` adds the directory to its hidden-key payloads;
  - `test_access.py` lists the route.
- **In the browser,** on my own server (port 8231, stopped afterwards):
  - **1440 px:** Pavel Petrov's profile and table; the Terminal's cold load, a name search ("Sergio Cruz" finds both of
    his rows and opens his card); Find players asking "Sergio Cruz shots".
  - **375 px:** Pavel Petrov's and Femi Toure's profiles, the Terminal and the Clip view. There was no horizontal page
    scroll (the numbers table scrolls inside its own wrapper, as before) and no console errors.
- **Nothing reached Azure or the live app.**
