# The catalogue UI port: independent review B, pass 3

Branch `ux/catalogue` at dfa4aff (fixes round 2). The diff reviewed is `git diff feature/catalogue...HEAD`. Written
2026-10-26.

**Lens:** product and data honesty.
- Does the app match the approved sandbox (words, layout, flows) at both widths?
- Do the numbers match the API, with their pool and sample?
- Is there one ranking rule?
- Are small pools, warnings and noisy marks visible?
- Is Femi Toure's basis stated?
- Is it demo-worthy and plain?

**How I checked.**
- My own server on port 8277, stopped when I was done. It ran with:
  - `REGISTA_DOTENV=` and `REGISTA_READONLY=1`;
  - a scratch feedback folder and clip cache;
  - a scratch Player store, holding a copy of `data/player/matches` and one `done` upload record for the demo friendly
    (`up_8807d7835c`, Femi Toure v Calder Town), so the "not counted" sentence could show.
- The built-in browser at 1440 and 375 px. I closed the tab afterwards.
- 41 questions to the Scout agent (`where: "catalogue"`, rules engine) over the API, and 15 asked on Find
  players (some of them the same questions).
- Checks against `/api/catalogue/rank` and `CatalogueMetrics.select`.
- I wrote nothing to the live app, Azure or Fabric, and changed no code.

**Verdict: not signed off.** Two findings should be fixed. Nothing must be fixed. All three round-2 fixes hold. Both
new findings are in the Scout agent:
- the first is in the minutes answers that round 2 added;
- the second is on the agent's cards, which do not use the `ranked` flag that round 2 added.

## Round 2: all three fixes hold

1. **Minutes questions no longer contradict themselves.**
   - "who plays the most minutes in Spain" reads "One list per level for the players in Spain, most minutes played first
     within the level. Amateur men: Andres Vidal (…), 90 minutes, shared with 3 others. Academy U19 men: Adrian Gonzalez
     (…), 91 minutes, shared with 3 others." The cards agree: four rows at 90, then 86.
   - "Femi Toure minutes" reads "274 minutes in 10 appearances".
   - No percentile warning is shown on a minutes answer.
   - The longer catalogue names win. "most touches in the box" ranks touches in the box. "which defenders win the most
     aerial duels" ranks aerial duels won. "who wins the most take-ons in Germany" ranks take-ons won.
2. **Across levels, the reply states the rule first.**
   - The Find players example chip "Find me women forwards who score" now reads "17 women forwards from several levels,
     ranked by each player's percentile for goals in their own pool. First: Olivia Webb (…), 1.10 per 90, 94th
     percentile among 8 semi-pro women forwards, a small pool; ≈ noisy … Next: Kaitlyn Stewart (1.53 per 90, 94th
     percentile among 9 college women forwards, a small pool; noisy) and Paige Allen (1.30 per 90, 83rd …)". This is the
     sandbox's shape.
   - "most sprints by defenders", "which defenders win the most aerial duels" and "who is the fastest winger" use the
     same shape, with "one list per gender".
   - "most goals in England", "who fouls the most" and "who has the most yellow cards" read "One list per level …",
     then each level's first ranked row with its pool line.
   - "leads" now appears only on one-level lists.
3. **Unranked rows never lead.**
   - "best keepers at my level" names Emeka Castellanos at 75%. This matches `/api/catalogue/rank` and the Terminal
     ("11, 4 ranked (7 below the minimum attempts, listed after)").
   - "least accurate passers in Japan" names Genki Yamada at 45%, 2nd percentile among 24 college men defenders.
   - "who has the most nutmegs in Ghana" reads "No one among the players in Ghana has any nutmegs yet (0 of 21)." So do
     "most goals in Morocco under 19" and "most nutmegs by goalkeepers" (per gender).
   - "best save % among women" says "no one ranked yet" for both levels. It does not name a leader.

**Also checked:**
- The agent's cards show ratios and totals in their own unit: "save % 75.0%", "pass completion 45.0%", "4 yellow
  cards".
- A none-yet cell with an empty pool reads "None yet".
- At 375 px, `scrollWidth` is 375 on Find players after three answers and on the Terminal.
- No console errors. A probe confirmed the console reader works.

## Should fix

### 1. "Fewest minutes" answers name the wrong player, because players without enough minutes are left out silently

**What happens.** `search_players` selects rows with the default minimum minutes, so only players with enough minutes
for a percentile are in the list. The round-2 minutes reply then states the extreme of that list as a plain fact about
everyone:

- **"who played the fewest minutes at my level":**
  - the reply: "Ole Friedrich (SV Hollenburg, Weserland-Liga, Germany) has played the fewest minutes among the semi-pro
    men players: 65 minutes in 3 appearances."
  - the data: the level has 198 player rows, and only 121 of them are in the list. Sani Adeleke (Weserland-Liga) has 1
    minute, and Felix Fuchs and Jonas Schwarz have about 4.
- **"who played the fewest minutes in Spain":**
  - the reply: "Amateur men: Izan Prieto (CD Riuseca, …), 45 minutes. Academy U19 men: Marcos Romero (…), 46 minutes."
  - the data: Andres Delgado has 1 minute in Izan Prieto's competition, and Marc Prieto has under 1 minute in the U19
    competition.
- Neither the reply nor the understood line ("fewest minutes played · top 5 · within each player's level") says that
  the list holds regulars only. Find players states it ("515 more without enough minutes").

"Most minutes" answers are not affected, because the players with the most minutes are always regulars.

**Fix.** Do one of these:
- For minutes questions, select every row (`min_minutes=0`). Minutes need no percentile, and the round-2 code already
  treats minutes as a total ranked by value.
- Or keep the regulars-only list and say so: "has played the fewest minutes among the 121 semi-pro men players with
  enough minutes for a percentile".

### 2. The agent's cards ignore `ranked`, so an unranked row sits under ranked ones with no mark

**What happens.** The reply now skips unranked rows, and `search_catalogue_players` lists them after the ranked rows,
with `ranked: false`. But `agentRow` in `static/scout/scout.js` never reads `ranked`. The card shows the value and the
pool's reason, and gives no word that the row has no place.

- **"best keepers at my level":** the fifth card reads "Lennart Vogel … save % 100.0% · No percentile: fewer than 5
  qualified peers · SMALL POOL · 90 minutes". It sits under two keepers at 50.0%, and nothing says why.
  - The true reason is in the API row (`ranked: false`, `qualified: true`): he has too few attempts.
  - The Terminal, on the same question, gives him "–" and says "7 below the minimum attempts, listed after".
  - The pool reason on the card ("fewer than 5 qualified peers") is true of all five keepers. It does not explain his
    position in the list.
- "best save % among women" shows the same thing on every card (100.0%, 80.0%, 50.0%, then outfield players with no
  value). The reply above does say "no one ranked yet".

**Why it matters.** The cards are the visual part of the answer. A 100% under a 50% reads as a ranking error, and the
port's rule is one ranking rule. Round 2 added the flag to the tool for exactly this. Only ratio questions with fewer
ranked rows than the limit show it today: keepers, and small or women's pools.

**Fix.** In `agentRow`, when `p.ranked === false`, replace the pool line with the Terminal's words, or add them after
it: "not ranked: too few attempts, listed after", or "None yet" for a count.

## Checked and matching

- **Femi Toure's profile** at `/players/pl_bro_09`, 1440 px, with the friendly's record in the store:
  - The sample line ends "These numbers count the Regista League fixtures only (10 matches). Femi Toure's friendly v
    Calder Town, uploaded through the Player view, is not counted here."
  - The Matches list ends with "Friendly v Calder Town · Uploaded through the Player view · Not counted in these
    numbers".
  - These read as round 2 reported: the tiles (5 goals ≈, 1.64 per 90, 98th percentile among 33 semi-pro men forwards;
    assists "None yet · 25 of the 33 …"; 19 shots (penalties excluded)), the four ratio rows with pools, the summary,
    and the moment clocks.
- **Find players** at 1440: the boards, place numbers and pool lines match the list endpoint, and ties share a place.
  Unranked rows have no number, and each board ends with its "N with none are listed last" footnote.
- **Terminal** at 375: "best save % at my level" gives "11, 4 ranked (7 below the minimum attempts, listed after). Top:
  Emeka Castellanos and Leon Oliveira, 75.0%, tied." This matches `/api/catalogue/rank`.
- **Example chips:**
  - "Who are the best U19 dribblers up front?" gives Hector Santos, 5.31 take-ons won per 90, 97th percentile among 16
    academy U19 men forwards, "8 of 16 have any so far".
  - "Which amateur midfielders create the most chances?" gives Luis Gomez, 1.74, 98th percentile among 33. This matches
    the verifier and the sandbox.
- **Tests:**
  - quick suite at dfa4aff: 1120 passed;
  - slow suite: 15 passed;
  - `tests/test_backcompat.py` and `tests/test_catalogue_backcompat.py` are untouched.

## Nits

1. **Ties read as a lead.** "best keepers at my level" says "Emeka Castellanos … leads … 75% … Next: Leon Oliveira
   75%", while the Terminal says "tied". "best take-on success in Germany" says "leads" over four more rows at 100%.
   The minutes reply already names ties ("shared with 3 others"). The stat reply could do the same.
2. **Units and case.**
   - "who has the highest top speed" reads "Haruki Fontaine …, 36.7, 98th percentile …", with no "km/h".
   - Cards and the understood line lowercase labels: "non-penalty xg per 90", "npxg + xa". The reply itself keeps
     "xG".
3. **Phrases the parser misses.** Each is stated honestly in the understood line.
   - "best save percentage" ranks saves per 90 ("save" → saves). Save % exists.
   - "best aerial duel win rate" ranks aerial duels contested.
   - "fastest" is not understood, so "who is the fastest winger" ranks non-penalty goals.
4. **Season totals.**
   - "who has the most yellow cards" says "4, no percentile (a season total: not ranked)" about the player it lists
     first.
   - Its cards carry a SMALL POOL badge (the pool size is 0).
   - The answer shows the cross-level percentile warning on a list with no percentiles.
   - "no percentile (a season total)" would read better.
5. **A shared place with different percentiles.** On Find players, Emre Scholz and Amari Ustinov are both 3rd at 1.04
   goals per 90, but 92nd and 89th. Places tie on the rounded value, and percentiles use the unrounded one (1.039 against
   1.036). This is the API's rule (`_places`).
6. **A named career player's minutes answer gives one row.** "Sergio Cruz minutes" reads "CF Torrevalle … 50 minutes
   in 2 appearances". His Juvenil row (about 47 minutes) is not mentioned. The reply does name the club, so it is
   honest.
7. **Still open from earlier rounds**, all Zaid's call or already listed:
   - minutes past the match length ("goal at 56'" next to the clock "55:27");
   - the competition page's B7 sample words;
   - "Any of these 1";
   - the raw worker error text on /me;
   - the engine marking keepers' nutmegs as none yet.
