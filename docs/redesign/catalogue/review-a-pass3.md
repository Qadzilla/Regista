# Catalogue UI port: review A, pass 3 (engineering)

Branch `ux/catalogue` at dfa4aff (fixes round 2), reviewed as `git diff feature/catalogue...HEAD` (71 files,
+9550 / -1393). Most attention went to what round 2 changed:
- `catalogue/scout.py`, `catalogue/tools.py`, `CatalogueMetrics.placed` and `ranked_first`;
- the Foundry and MCP tool descriptions;
- the agent cards in `scout.js` and `profile-view.js`.

Lens: API additions, back-compat, CSP and escaping, `Regista.store`, the upload backend, the agent's tools, packaging
and smoke, tests and their speed, cold loads, and the live app's existing pages after a deploy.

**Verdict: signed off.** Nothing must be fixed and nothing should be fixed. Round 2's three fixes hold. What is left
are carried smaller items and nits, none of which blocks a merge or a deploy.

## How I checked

- **Test suites (Mac):**
  - quick suite: 1,120 passed in 296 s;
  - `-m slow`: 15 passed in 170 s.

  The slowest quick tests are still the vision ones (20 s at most). The slowest catalogue test takes 4.9 s, and round
  2's `test_catalogue_fixes2.py` is not in the top 25.
- **Local server:** my own server on :8288, with `REGISTA_DOTENV=`, a copy of `data/player` as the player store, a
  scratch feedback folder, and a test token generated for this run. All of them are in the scratchpad's `rva3/`
  folder. The server is now stopped.
- **Browser:** the built-in browser at 1440 and 375 px, in one tab of my own, closed afterwards. Ports 8040 and 8060
  were left alone.
- **Writes:** none to the live app, Azure or Fabric. I made no upload, not even locally.

## Round 2, checked

- **Minutes questions,** asked of the rules engine through the API:
  - "who plays the most minutes in Spain" reads "One list per level … Amateur men: Andres Vidal …, 90 minutes, shared
    with 3 others. Academy U19 men: … 91 minutes". The answer has no percentile warning.
  - "Femi Toure minutes" reads "274 minutes in 10 appearances" (league fixtures only, as decided).
  - "who played the fewest minutes in England" gives each level's lowest. I checked them against
    `/api/catalogue/players?sort=minutes&order=asc`: 234.5, 45.3 and 48.6 minutes. Every one of those rows is
    qualified, so the ranked-only filter hides nobody here.
- **Longer catalogue names win:**
  - "most touches in the box" ranks `touches_in_box`;
  - "which defenders win the most aerial duels" ranks `aerial_duels_won`;
  - "who wins the most take-ons" ranks `take_ons_won`.

  The `heard` line names the metric used, and the parser's own line is dropped when the catalogue's wins.
- **Replies shaped by the ranking rule:**
  - "Find me women forwards who score" now opens "17 women forwards from several levels, ranked by each player's
    percentile …". Each Next row carries its pool line.
  - Lists with both genders say "one list per gender".
  - Value-mode lists across levels say "One list per level" and give each level's first ranked row. "Leads" appears
    only on one-level lists.
- **Unranked rows never lead:**
  - "best keepers at my level" names Emeka Castellanos (75%). The card reads "save % 75.0%", and unqualified Lennart
    Vogel (100%, 90 minutes) comes fifth.
  - "least accurate passers in Japan" names Genki Yamada.
  - "who has the most nutmegs in Ghana" and "most goals in Morocco under 19" both say no one has any yet.
  - Every row carries `ranked`. `search_players` keeps the boards grouped and each board's order stable: `group_boards`
    is a stable sort, and `with_any` / `none_yet` are unchanged.
- **Engineering of the change:**
  - `catalogue_api._ranked_rows` now delegates to `CatalogueMetrics.placed`, so the rank endpoint and the tool share
    one rule.
  - `resolve_stat` maps through `SORT_OF` exactly as `metric_for` did, so no position mapping was lost.
  - Regexes are built from metric phrases only, with the user's text matched, never compiled.
  - A rules answer takes 0.03-0.06 s.
- **The agent's tools:** `SCOUT_TOOLS` is unchanged since pass 2 and public only: no Cosmos DB namespace and no
  `render_clip`. The new instruction text adds rules and no tools.
- **API validation,** probed with curl:
  - an unknown metric, an out-of-range `limit` or `offset`, a bad tier, a bad player id, an unknown competition, a bad
    `scope` and a `<script>` global id all get plain 4xx answers;
  - a question over 200 characters gets 422;
  - an upload without the token gets 401.
- **Phone and console:**
  - `scrollWidth` was 375 at 375 px on every Scout section (overview, find, competitions, shortlist, reports, messages,
    team, settings, terminal), on Sergio Cruz's profile, on every `/me` section and on the Clip view
    (`cm_nam_02_irk_ads`);
  - the agent's cross-level answer also fits at 375;
  - no console errors.
- **Back-compat:**
  - These files have an empty diff against `feature/catalogue`: `tests/test_backcompat.py`,
    `tests/test_catalogue_backcompat.py`, `season/pins.py`, `league.json` and `synth/`.
  - The added static lines have no `style=`, no inline handlers and no inline scripts.
  - The smoke test's `STATIC_FILES` includes `terminal-words.js` and `terminal-place.js`.
- **Upload backend:** I read it again against pass 1.
  - Catalogue fields are all required with a `competition_id`, and optional and still checked without one.
  - England's id resolves to the league in the API, `roster_for` and `film`.
  - Old records load with the new defaults.
  - `catalogue_labels` adds nothing for league friendlies, so their manifests are unchanged.
  - The `--work` mkdir fix is in.

## Smaller items (carried, not blocking)

- **`player_uploads()` is still uncached** (`src/regista/player_api.py`).
  - Each public competition page, catalogue profile (through `not_counted`) and `/api/player/uploads` read lists the
    store and reads every `record.json`.
  - With the live app's handful of records this costs tens of milliseconds.
  - `uploaded_matches()`'s 30 s listing (`LIST_TTL_S`) could serve it.
- **A failed worker job shows the raw exception, with a temporary path, on `/me`.** This is the Player view's existing
  format, not this branch's. Catalogue clubs' uploads now reach it too, so a plain sentence (detail kept in the log) is
  worth doing.
- **Gzip runs on the event loop,** about 15 ms per MB. That is fine at today's sizes. Move it to the threadpool if
  whole-catalogue Terminal payloads (about 6 MB) become common.

## Nits

- **"who has the best save percentage"** ranks saves per 90, not Save %. The league parser hears "save", and "save
  percentage" is not a catalogue phrase (the label is "Save %"). The understood line says so, so it is honest but
  weaker. "save percentage" could be added as a phrase for `save_pct`.
- **"lowest first" in pool mode can read as lowest percentile first.** "fewest fouls by forwards in England" says
  "ranked by each player's percentile … in their own pool, lowest first", then lists 94th, 81st, 69th. The fouls are
  lowest first; the percentiles run highest first. "fewest fouls first" would be unambiguous.
- **"leads" on a tie:** "Emeka Castellanos … leads … 75% … Next: Leon Oliveira 75%". The minutes reply already names
  ties; the stat reply could do the same.
- **`agentNumber` in `scout.js`** leaves a trailing space when a ratio metric has no unit. It is invisible in the page.
- **Carried:**
  - rules replies print metres as "12120.00 per 90" ("who covers the most distance in Spain");
  - `_JSONGzip` matches "gzip" anywhere in `Accept-Encoding`, so `gzip;q=0` still gets gzip;
  - no test pins an MP4 range request under gzip;
  - `me.js`'s `clean()` is dead code.

## Not checked

- Linux CI, since nothing was pushed.
- The Foundry engine with a real model.
- A full worker upload: the verifier ran one in a scratch store, and round 2 did not touch the worker.
