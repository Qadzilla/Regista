# Review B, pass 3: is the ported terminal intuitive, and does it match the sandbox?

Synthetic data: the players and clubs are invented. They belong to the Regista League, which Regista generates.

**Scope.** This pass reviews branch `ux/terminal-friendly` at 1f97175, which holds the round 2 fixes (`git diff main...HEAD`).

**How I ran it.**
- The app ran offline with `REGISTA_DOTENV= uvicorn regista.api:app --host 127.0.0.1 --port 8204`.
- I used my own browser tab at 1440x900 and 375x812, starting from an empty store.
- I also ran about 85 phrasings through `terminal-words.js` in node. I used the test suite's own harness (`WORDS_HARNESS`) with the real league.

**Cleanup.** I changed no code. Afterwards:
- the server is stopped
- the viewport is reset
- this origin's demo storage is cleared
- my tab is closed
- the server log shows no POST, PUT, PATCH or DELETE, and no 4xx or 5xx apart from `/favicon.ico`

`python3 -m pytest -q`: 856 passed, 13 deselected.

**Verdict: not signed off. Nothing must be fixed. Two things should be fixed.** Both are small parser gaps in the
round 2 position questions.

## The round 2 fix, checked

Every example both reviewers gave now ranks the right stat for the right position, in node:
- which forwards have the most goals
- which keeper has the most saves
- what defenders have the most interceptions
- which strikers score the most
- which defenders win the most tackles
- which goalkeepers have the best save %
- which keepers concede the fewest
- which midfielders create the most chances
- which forwards have the most goals at Calder

These also work:
- "who won the most tackles" and "which forwards win the most fouls" ("X won")
- "which forwards" alone, and "what is xG" (no position picked up)

In the browser at 375 px, "which defenders win the most tackles" answered "Defenders ranked by Tackles won: 24. Top:
Gino Yilmaz, 4.02 per 90", and `scrollWidth` stayed at 375.

## The scout's journey (1440)

1. I typed "who are the best finishers?" and pressed Enter. The answer was "Forwards ranked by Non-penalty goals: 18.
   Top: Femi Toure, 1.64 per 90."
2. Alt+1 put focus on the 1.64 button. Its name is "Femi Toure, Non-penalty goals 1.64 per 90, 97th percentile. Play
   its 5 moments".
3. Enter opened the Clips drawer (`role="dialog"`, labelled by its heading), moved focus to the heading "Clips", and
   loaded the first clip's MP4.
4. Escape closed the drawer and put focus back on 1.64.

The console showed no errors. All 15 changes still look as the safeguard and the earlier passes describe them.

## Should fix

### S1. "which <position> are the best <role>" answers "Nothing found"

**Where:** `src/regista/static/scout/terminal-words.js`, `natural()`. After `POS_OPEN`, the position goes back in front
of the rest.

**What happens.** The position plus the flagship question fails. "which forwards are the best finishers?" answers
"Nothing found for 'which forwards are the best finishers'" (seen in the browser). In node, these also answer none:
- which strikers are the best finishers
- which midfielders are the best passers
- which midfielders are the best dribblers
- which defenders are the best tacklers
- which forwards are the top scorers

The rewrite produces "forwards the best finishers", and the parser does not read that either. Close variants already
work:
- "who are the best finishers"
- "which players are the best finishers"
- "best finishers among forwards"
- "the best finishers for forwards"
- "which forwards are the best"

**Why it matters.** "Best finishers" is the first example chip, and this is its most natural position form. The round 2
fix introduced `POS_OPEN` for exactly this kind of question.

**Suggested fix.** When the words left after `POS_OPEN` resolve on their own to a stat or a role word ("the best
finishers"), put the position after them ("the best finishers forwards") or set it on the result directly. Add
"which forwards are the best {role}" for the role words, and "which forwards are the top scorers", to a test.

### S2. A plural verb after a position ranks the wrong stat or none: "which forwards dribble the most" ranks Dribbled past

**Where:** `terminal-words.js`, `VERB`. It holds third-person forms ("dribbles", "shoots", "tackles", "passes",
"presses", "carries", "heads", "saves", "runs", "fouls", "assists"). A few base forms are present ("score",
"create", "concede"), but most are not. After a plural subject ("which forwards …", "which players …"), the verb
comes in its base form. The fix-round-2b note says a verb after the position maps "as after who", but for most verbs
it does not.

**What happens.**
- "which forwards dribble the most" and "which players dribble the most" rank **Dribbled past** with "most first;
  fewer is better". The browser said: "Forwards ranked by Dribbled past (most first; fewer is better): 18. Top: Haruki
  Fontaine". That stat counts the times a player was beaten, the opposite of what was asked, and it is presented as a
  confident answer. "who dribbles the most" correctly ranks Take-ons won.
- "which forwards shoot the most", "which players shoot the most" and "which defenders head the most" answer
  Nothing found. ("who shoots the most" gives Shots.)
- These offer a choice of stats instead of the ranking the singular verb gives:
  - which defenders tackle the most
  - which players pass the most (37 stats)
  - which forwards press the most
  - which midfielders carry the most
  - which keepers save the most
  - which forwards run the most
  - which defenders foul the most
  - which forwards assist the most

**Suggested fix.** Add the base forms to `VERB`, with the same targets as the singular forms: dribble, shoot, tackle,
pass, press, carry, head, save, run, cover, foul, assist. Test "which forwards <base verb> the most" and "who <verb>s
the most" for every `VERB` entry, so they reach the same stat.

## Nits (none blocks a sign-off)

- A club inside the position phrase is not read. "which forwards at Calder have the most goals" and "which Calder
  forwards have the most goals" answer none. "which forwards have the most goals at Calder" works.
- "which defenders made the most interceptions" answers none ("made" is not read as "have").
  "which midfielders completed the most passes" offers 9 stats.
- "which forwards have more than 3 goals" answers none. Thresholds are not a terminal feature, but the line could
  point to the filters.
- Carried over from pass 2 and review A, round 2, still open:
  - "least minutes" ignores the end
  - the status wording and punctuation vary ("most first; fewer is better" against "lowest first: lower is better")
  - "most pass completion %" offers 9 stats
  - columns pile up across questions
  - "Enter plays them" appears in the mouse tooltip
  - "the most progressive carries in the league this season" answers none
  - "best young players"
  - the safeguard's open items (team counts load late, Cache-Control)

## Not done (per the task)

Nothing was pushed, no PR was opened, and nothing was merged.
