# Catalogue UI port: fixes round 2

Branch `ux/catalogue` (on top of PR #39). Three findings from review round 2, all fixed. Tests: `tests/test_catalogue_fixes2.py`
(25 tests). The quick suite passed (1120), and so did the slow suite (15). Local browser check on a server I started
myself (port 8231, stopped afterwards), at 1440 and 375 px: no horizontal scroll and no console errors.

## 1. A minutes question contradicted itself: fixed

**Before:** asked "who plays the most minutes in Spain", the understood line said `“most minutes” → minutes`. The
reply then said it had found no stat and ranked by non-penalty xG. The cause: the league parser reads a rank with no
stat as "minutes", and `stat_asked` treated every "minutes" as no stat.

**Now:** `stat_asked` counts minutes as asked only when the parser *heard* them (a `→ minutes` line). The answer then
ranks by minutes through `search_catalogue_players(sort="minutes")`, the same ordering `/api/catalogue/players` uses:
by value, one list per level.
- Across levels: "One list per level for the players in Spain, most minutes played first within the level. Amateur men:
  Andres Vidal (…), 90 minutes, shared with 3 others. Academy U19 men: Adrian Gonzalez (…), 91 minutes, shared with 3
  others."
- One level: "<name> has played the most minutes among the …: N minutes in M appearances. Next: …"
- A named player: "Femi Toure (Brookfield Rovers, Regista League, England): 274 minutes in 10 appearances."
- The understood line reads "most minutes played · … · within each player's level". A minutes answer carries no
  percentile warning, because minutes have no percentile.
- Minutes are rounded as the pages round them (`whole`, which matches JavaScript's Math.round). Before, Python's
  round-half-to-even made the reply say "90" while the card said "91".
- A question with no stat still says what it ranks by ("best keepers at my level" ranks by Save %).
- The engine's minutes are unchanged (Zaid's decision).

**The weaker point is also fixed:** a catalogue metric named in longer words than the league parser's now wins.
- "most touches in the box" ranks `touches_in_box`; "most touches" still ranks `touches`.
- Every metric whose label ends in "won" is also matched by its verb: "which defenders win the most aerial duels" ranks
  `aerial_duels_won`, and "who wins the most take-ons" ranks `take_ons_won`.
- The understood line names the metric that was used (`“win the most aerial duels” → aerial duels won`).

## 2. Replies across levels said "leads" for a smaller number: fixed

`reply_for` now follows the ranking rule the tool used:
- **More than one level, one position (`rank_by` pool):** the sandbox's shape. "17 women forwards from several levels,
  ranked by each player's percentile for goals in their own pool. First: Olivia Webb (…), 1.10 per 90, 94th percentile
  among 8 semi-pro women forwards, a small pool; ≈ noisy over a sample this size. Next: Kaitlyn Stewart (1.53 per 90,
  94th percentile among 9 college women forwards, a small pool; noisy) and Paige Allen (1.30 per 90, 83rd percentile
  among 9 college women forwards, a small pool; noisy)."
  - When the list holds men and women, it adds "one list per gender", with "Men, first: …" and "Women, first: …".
  - An ascending list adds "lowest first".
- **More than one level and more than one position (value mode, one board per level):** "One list per level for the
  players in England, ranked by goals within the level: a raw number is only compared with players at the same level."
  Then each level's first ranked row with its pool line (three levels, then "N more levels are in the list").
- **One level:** "leads", or "has the fewest / lowest", as before.

The vague closing sentence is gone: the first sentence now states the rule. The page still shows the cross-level
warning box from `warning`.

## 3. Rules answers led with unranked rows: fixed

**The tool:**
- `search_players` (the `search_catalogue_players` MCP tool, which both the rules engine and the Foundry Scout agent
  call) now puts the rows that get a place first on each board. The rest follow in their order: rows below the minimum
  attempts, then none yet. This is how `/api/catalogue/rank` lists them.
- Each row carries `ranked` (true or false).
- The rule now lives in one place: `CatalogueMetrics.placed` and `ranked_first`. `catalogue_api._ranked_rows` uses it.
- The MCP tool's description and the Foundry Scout instructions say that a row with `ranked` false never leads, and that
  when no row is ranked, the answer says no one is ranked yet.

**Results:**
- "best keepers at my level": Emeka Castellanos, 75%. This matches `/api/catalogue/rank?metric=save_pct&tier=semi_pro&gender=men&position=GK`.
- "least accurate passers in Japan": Genki Yamada, 45%, 2nd percentile. Koki Abe (20%, too few attempts) no longer
  leads.
- "who has the most nutmegs in Ghana" now reads "No one among the players in Ghana has any nutmegs yet (0 of 21)."
  "most goals in Morocco under 19" reads the same way.
- A test checks the ranked rows' order against `/api/catalogue/rank` for four lists:
  - keepers' save %;
  - Japan's defenders' pass completion, ascending;
  - Germany's take-on success;
  - men forwards' non-penalty goals.

**Left as PR #39 serves them:** `/api/catalogue/players` and `/api/terminal/screen` keep their raw order, with `rank`
null on unranked rows. The Terminal page already reorders them, and existing endpoints keep their shapes.

## Found in the browser and fixed

- **Ratio and total numbers on the Scout agent's cards.** Cards wrote every number as "per 90" ("75.00 save % per 90").
  They now use the metric's own unit ("save % 75.0%", "pass completion 45.0%"). A minutes card shows minutes and
  appearances, with no leading " · ".
- **Empty none-yet pools.** A none-yet cell whose pool is empty read "all 0 academy U17 men goalkeepers have none".
  The cause: a goalkeeper on nutmegs, a metric not scored for keepers. Find players, the compare view and the shared
  profile now say "None yet" there, as the Terminal and the server's pool line already did.
- **Open, not changed here:** the engine (PR #39) marks a keeper's nutmegs as none yet with an empty pool, rather than
  "not ranked for this position". These rows count toward "0 of 21" in Ghana. This is an engine question, not a port
  one.

## Changed tests

`tests/test_catalogue_fixes1.py::test_rules_sentences_read_right` expected "leads the college players" and "has the
fewest fouls committed among the forwards". Both lists come from more than one level, so after finding 2 they read
"One list per level …" and "… in their own pool, lowest first". The test now checks those shapes, and checks the
one-level "has the fewest / lowest" wording with "at my level".
