# Review B, pass 2: is the ported terminal intuitive, and does it match the sandbox?

Synthetic data: the players and clubs are invented. They belong to the Regista League, which Regista generates.

**Scope.** This pass reviews branch `ux/terminal-friendly` at 5d4b068, the round 1 fixes (`git diff main...HEAD`).

**How I ran it.** I ran the app offline with `REGISTA_DOTENV= uvicorn regista.api:app --host 127.0.0.1 --port 8204` and tested it in my own browser tab at 1440x900 and 375x812. I started from an empty store.

**Cleanup.** I changed no code. Afterwards:
- the server is stopped
- the viewport is reset
- this origin's storage is cleared
- my tab is closed
- the server log shows no POST, PUT, PATCH or DELETE

`python3 -m pytest -q`: 855 passed, 13 deselected.

**Verdict: not signed off. Nothing must be fixed. One thing should be fixed.**

## The round 1 fixes, checked in the browser

| Round 1 finding | Result |
|---|---|
| "▶ N moments" wrong for shot-creating actions | Fixed. Toure's sca cell says "Play its 16 moments". The drawer lists 16 rows, two of them "Live-ball pass · counts 2 times", and the status line says "16 moments". The drawer's header, "5.91 actions per 90 · 18 in total", is consistent with this, because the "counts 2 times" rows account for the difference. |
| "most <stat>" with a position or a club | Fixed for the forms tested. These all worked: "forwards with the most goals", "who are the forwards with the most goals", "most shots on target for midfielders", "fewest fouls among defenders", "most passes from the defensive third at Brookfield", "top 5 xG at Calder", "most goals per 90 for forwards at Brookfield", "who has the most interceptions among defenders", "most goals in the league", "who has the most xG at Brookfield" and "goalkeepers with the fewest goals conceded". |
| "fewest / least / lowest / worst <stat>" | Fixed. "fewest yellow cards", "least fouls", "lowest xG", "least goals", "fewest goals conceded", "who concedes the least", "worst finishers", "worst passers" and "bottom 5 xG" each rank from the right end. The status line names the order. |

## The scout's journey, again

1. At 1440, I typed "who are the best finishers?" and pressed Enter.
2. The answer was "Forwards ranked by Non-penalty goals: 18. Top: Femi Toure, 1.64 per 90".
3. The 1.64 opens a drawer of 5 moments, and the clip plays.
4. With the keyboard: Alt+1, then → (see the nits), then Enter opens the drawer and moves focus to its heading. Escape closes it and puts focus back on 1.64.

At 375, "forwards with the most goals" followed by a tap on 1.64 opens the bottom sheet (the lower 521 px) with focus inside. `scrollWidth` is 375, so nothing scrolls sideways, and there are no console errors.

## Should fix

### S1. "which <position> have the most <stat>" answers "Nothing found"

**Where.** `src/regista/static/scout/terminal-words.js`, the `OPEN` regex. It accepts "which player(s)" but no position after "which" or "what".

"which players have the most interceptions" works. Change "players" to a position and every stat fails. These all answered "Nothing found":
- which forwards have the most goals
- which forward has the most goals
- which midfielders have the most assists
- which defenders have the most interceptions
- which defenders have the most tackles won
- which keeper has the most saves
- what defenders have the most interceptions
- which strikers score the most
- which defenders win the most tackles

**Why it matters.** A scout who has never seen Bloomberg is likely to ask exactly this. It is the position form of Zaid's "most <stat>" request, and round 1 added the other position forms ("forwards with the most X", "most X for forwards") but not this one. The sandbox has the same gap (same `OPEN`), so this is not a fidelity regression. It is an unfinished part of the "most <stat> for every metric" fix.

**Suggested fix.**
- Let `OPEN` read `(which|what)\s+<position word>\s+(are|is|have|has|had)?`, setting `who` so the verb mapping works ("which strikers score the most"), and keep the position for the ranking.
- Or read only "which"/"what", and let `exactWithPos` find the position that now comes first.
- Add these forms to `test_every_stat_answers_with_a_position_or_a_club_before_or_after_it`.

## Nits (none blocks a sign-off)

- **Alt+1 lands on the player's name, not the number the question asked about.** After "who are the best finishers?", Alt+1 focuses "Femi Toure" (column 0), so Enter re-selects him. It takes one → to reach 1.64. The sandbox and main do the same (`scrAct … c: 0`). Pass 1's "Alt+1 then Enter opens the drawer" only held after an earlier click had moved the stop. If a ranking command set `scrAct` to its stat's column, a keyboard user would go from the question to the moments in two keys.
- **"least minutes" answers "Players by minutes played … Most: Otis Ustinov, 302 minutes"**, so the fewest is ignored for minutes.
- **The status wording varies by phrasing.** "lowest xG" says "(fewest first; more is better)" and "fewest yellow cards" says "(lowest first: lower is better)". The punctuation also differs: "most first; fewer is better" against "lowest first: lower is better". This was carried over from pass 1.
- **"most pass completion %" still offers 9 stats.** "highest pass completion" and "pass %" work. Carried over from pass 1.
- **The table keeps the columns from every question.** After about 30 questions it showed Interceptions, Fouls, Goals conceded and Save % beside "best finishers". This is a known sandbox nit, and the Columns menu and "Default columns" handle it.
- **The other pass 1 nits still stand:** "Enter plays them" in the mouse tooltip; team-number counts only in the tooltip; the form chart's x labels touching at 1440; no caption on the table; two cut-off texts at 375; and "best young players".
