# The catalogue UI port: independent review B, pass 2

Branch `ux/catalogue` at 2522180 (fixes round 1). The diff reviewed is `git diff feature/catalogue...HEAD`. Written
2026-10-26.

**Lens:** product and data honesty.
- Does the app match the approved sandbox (words, layout, flows) at both widths?
- Do the numbers match the API, with their pool and sample?
- Is there one ranking rule?
- Are small pools, warnings and noisy marks visible?
- Is Femi Toure's basis stated?
- Is it demo-worthy and plain?

**How I checked.**
- My own server on port 8263: `REGISTA_DOTENV=`, `REGISTA_READONLY=1`, a scratch feedback folder and cache, the repo's
  `data/player` store (read only). I stopped it when I was done.
- The built-in browser at 1440 and 375 px, in one tab, switched between the app and the sandbox at :8060.
- curl reads against the same server, and 26 questions to the Scout agent (`where: "catalogue"`, rules engine).
- I wrote nothing to the live app, Azure or Fabric, and changed no code.

**Verdict: not signed off.** Two findings should be fixed. Nothing must be fixed. All six round-1 fixes hold. Both
new findings are in the Scout agent's rules answers (`regista.catalogue.scout`, new in this port). Judges see those
answers whenever Foundry is not set up or is rate-limited, and one of the three example questions on Find players shows
the first finding.

## Round 1: all six fixes hold

1. **A named player's "none yet" answer.** "Sergio Cruz" reads "non-penalty goals none yet · 24 of the 31 amateur men
   forwards have none". "Femi Toure assists" reads "none yet · 25 of the 33 …". Neither guesses a reason.
2. **A named player and the stat asked.** "Sergio Cruz shots" answers with shots: "1.80 per 90, 60th percentile among
   31 amateur men forwards; ≈ noisy". It hears "“shots” → shots".
3. **Broken sentences.**
   - The empty answer reads "No women goalkeepers in Nigeria in the catalogue match that yet."
   - "best college players" reads "leads the college players".
   - "fewest fouls by forwards in England" reads "has the fewest fouls committed among the forwards in England".
   - "most yellow cards" ranks yellow cards: "4, no percentile (a season total: not ranked)".
   - A question with no stat says what it ranks by.
4. **The cold Terminal.** `/api/catalogue/directory` is one gzipped read (55 KB on the wire), with no hidden keys.
   - The Terminal's name search finds both of Sergio Cruz's rows.
   - JSON answers carry `Content-Encoding: gzip` and `Vary`. HTML is not compressed, and a 404 passes through.
   - The CSP header is unchanged.
5. **One shot count.** Pavel Petrov's "Every number" table reads "Shots (penalties excluded) 3 · 1.06 · 44th" and
   "Shots on target (penalties excluded) 1". His ratio row reads "33.3% of shots on target, penalties excluded (1 of
   3)". Femi Toure's tile reads "19 Shots (penalties excluded)". These agree with Find players and the Terminal.
6. **The moment clock.**
   - Profile moment cards read "ON THE BALL · ROUND 1 · 05:48" for "goal at 6'", and "REPLAY · ROUND 1 · 05:59".
   - The same lines show on `/players/pl_bro_09` at 1440 and on `/me#profile` at 375.
   - Every moment of Sergio Cruz (55 across both rows) and Pavel Petrov (40) has a clock.
   - Highlights read "FT".

## Should fix

### 1. Across levels, rules answers say "leads" for a row with a smaller number than the next, and drop the sandbox's explanation

**What happens.** A list from more than one level that holds one position is ranked by each row's percentile in its
own pool. That is the engine's rule, and the rows are right. But the reply's first sentence says "leads … for <stat>:
<value>". The "Next:" rows show only their values, with no percentile. A reader sees a bigger number placed second.

- **Find players example chip "Find me women forwards who score"** (one of the three examples on the page):
  - app: "Olivia Webb (…) leads the women forwards for goals: 1.10 per 90, 94th percentile among 8 semi-pro women
    forwards, a small pool; ≈ noisy … Next: Kaitlyn Stewart 1.53 per 90 and Paige Allen 1.30 per 90. … These rows come
    from more than one level: read each percentile against its own pool."
  - sandbox (approved): "17 forwards from several levels, ranked by each player's percentile for non-penalty goals per
    90 in their own pool. First: Olivia Webb (…), 1.10 …, 94th percentile among 8 semi-pro women forwards. Next: Kaitlyn
    Stewart (1.53, 94th percentile among 9 college women forwards) and Paige Allen (1.30, 83rd percentile among 9 college
    women forwards)."
- **More cases:**
  - "most sprints by defenders": "Raul Rodriguez leads the defenders for sprints: 36.90 per 90 … Next: Timo Krause
    42.50 per 90 and Yuki Kato 44.30 per 90."
  - "which defenders win the most aerial duels": "Fabian Fuchs … 7.50 … Next: Victor Eze 7.88".
  - "who is the fastest winger": "Femi Toure leads the forwards for non-penalty goals: 1.64 … Next: Sergio Gallego
    2.99 per 90".

**Why it matters.** Under this lens, "leads … 1.10" next to "1.53" reads as an error. The one sentence that explains
the order comes last, in general words. The sandbox put the rule first and gave every "Next" row its pool. The verifier
listed the order as minor because the rows are right. The reply text is the problem, and it is a parity regression on a
demo chip.

**Fix.** In `reply_for`, when the result's `rank_by` is `pool` (or `warning` is set), use the sandbox's shape: "N
<position> from several levels, ranked by each player's percentile for <stat> in their own pool. First: … Next: <name>
(<value>, <pool line>) …". Keep "leads" for one-level lists only.

### 2. Rules answers lead with rows the ranking rule lists after, unranked

**What happens.** `tools.search_players` orders value-mode rows with `CatalogueMetrics.sort`. That sort ranks ratio rows
by raw value whether or not they have their competition's minimum attempts. `/api/catalogue/rank` and the Terminal's
screen list those rows after, unranked. The reply then says "leads" or "has the lowest" about a row that has no rank.

- **"best keepers at my level":**
  - agent: "Lennart Vogel (SC Erlenhorst, Weserland-Liga) leads the semi-pro men goalkeepers for save %: 100%, no
    percentile … Next: Tim Fuchs 100% and Tobias Klein 100%."
  - `/api/catalogue/rank?metric=save_pct&tier=semi_pro&gender=men&position=GK`: 4 ranked, Emeka Castellanos and Leon
    Oliveira first at 75%.
  - The Terminal ("best save % at my level") agrees with the rank endpoint: "11, 4 ranked (7 below the minimum attempts,
    listed after). Top: Emeka Castellanos and Leon Oliveira, 75.0%, tied." Lennart Vogel shows "–" below them.
- **"least accurate passers in Japan":**
  - agent: "Koki Abe … has the lowest pass completion among the players in Japan: 20%, no percentile".
  - rank endpoint: Genki Yamada (45%) is 1st, and Koki Abe is not ranked.
- **When every row is "none yet":**
  - "who has the most nutmegs in Ghana": "Bernard Fosu … leads the players in Ghana for nutmegs: none yet · all 5 academy
    U17 men forwards have none. Next: Bernard Frimpong none yet and Collins Fosu none yet. 0 of 21 have any so far."
  - "most goals in Morocco under 19": "Achraf Laaroussi leads the U19 players in Morocco for goals: none yet …".
  - The ranking rule lists none-yet rows with no place, so no one leads.

**Why it matters.** This breaks the port's "one ranking rule". The same question gets a different leader from the
agent than from the Terminal and the rank endpoint. The Foundry Scout agent calls the same `search_catalogue_players`
tool, so it sees the same order.

Note: `/api/catalogue/players` and `/api/terminal/screen` serve the same raw order (from PR #39), with `rank: null` on
those rows. The Terminal's page reorders them correctly. The agent is the one screen that shows the raw order as a
ranking.

**Fix.**
- Make `search_players` (or `CatalogueMetrics.sort` for ratios) put rows below their minimum attempts after the
  ranked rows, as `/api/catalogue/rank` does.
- In `reply_for`, when no row is ranked, say so: "No one among the … has a nutmeg yet (0 of 21)." Do not name a leader.

## Checked and matching

**Femi Toure's profile (1440) next to the sandbox.** These read word for word as the sandbox does: header, career,
summary, best moments, the six tiles with pools and ≈ marks, the four ratio rows, similar players, matches with
uploader and camera, and "Add a match".
- Differences: "(penalties excluded)" on shots, which is round 1's decision, and the clock on moment cards, which the
  app adds.
- The sample line ends "These numbers count the Regista League fixtures only (10 matches)."
- My store has no done upload record for the friendly, so the "not counted" sentence does not appear here. The API
  agrees: `not_counted` is [], and `/api/players/pl_bro_09` gives 10 appearances. The verifier's store did show it.

**Find players (1440).** Boards, pool lines, ≈ marks, the "Players from different levels" warning, Femi Toure 1.64
(98th of 33, 10 matches, 274 minutes) and "20 of the 110 … have any goals" all match the sandbox. The agent rows now show
a shirt on every row, so review B pass 1's nit 2 is gone.

**Terminal (1440).**
- Femi Toure's card states his sample: "10 appearances in 10 uploaded matches …; a regular needs 101".
- Unranked rows show "–", and the status line explains them.

**Phone (375).** `scrollWidth` is 375 on Pavel Petrov's profile (with the numbers table open) and on `/me#profile`.

**Tests.** The quick suite passes at 2522180: 1095 passed (I did not run the slow suite; the fix report gives 15 passed).

## Nits

1. **"players with the most minutes"** reads "Understood … (heard “most minutes” → minutes)", then ranks by non-penalty
   xG and says "I did not find a stat I know in the question". `search_players` can sort by minutes, so either rank by
   minutes or drop the "heard" line.
2. **"which defenders win the most aerial duels"** ranks aerial duels contested ("heard “aerial duels” → aerial
   duels"). The catalogue has `aerial_duels_won`, and "win" points at it.
3. **"fewest fouls … in England"** says "has the fewest" for one of several players tied at 0.00. "is among the players
   with none" would be exact.
4. **"who fouls the most"** reads "leads the players for fouls committed: 5.30 per 90, 2nd percentile". That is right,
   since fewer fouls is better, but it is hard to read. "(fewer is better)" after the percentile would help.
5. Still open from earlier rounds, all Zaid's call or already listed:
   - minutes past the match length in titles ("goal at 56'" in a 2 x 15 match, now next to the clock "55:27");
   - the competition page's B7 sample words;
   - "Any of these 1";
   - the raw worker error text on /me.
