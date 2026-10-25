# Review A, round 3: the friendlier Scout terminal (ux/terminal-friendly)

Reviewer A, round 3. My lens is correctness and safety. I reviewed `git diff main...HEAD` at 1f97175. Round 2's fix changed only `terminal-words.js` and its tests, so I looked hardest at the new `POS_OPEN` and `WIN_W` reading.

How I tested:
- I ran about 100 phrasings through node, using the test harness and the API's own catalogue (127 metrics, 102 players).
- I ran the app offline on 127.0.0.1:8203 (`REGISTA_DOTENV=`) and checked in my own browser tab.

I changed no code. Afterwards:
- the server is stopped
- this origin's storage is cleared (it held only `regista.demo.v1.terminal`)
- the tab is closed

**Verdict: not signed off.** Nothing must be fixed. Two things should be fixed, both in the new "which <position> …" reading.

## What holds

- **Full suite:** `python3 -m pytest -q` gives 856 passed and 13 deselected.
- **Round 2's examples all work**, in node and in the browser:
  - `which forwards have the most goals`
  - `which strikers score the most`
  - `which defenders win the most tackles`, which gives "Defenders ranked by Tackles won: 24. Top: Gino Yilmaz, 4.02 per 90"
  - `who won the most fouls`
  - `which keepers have conceded the fewest goals`
  - `which forwards have the most goals at Calder`
  - `which mid has the most xA`
  - `what defender has the most interceptions`
- **"what is xG" still takes no position.**
- **Numbers match the API.** For that defenders answer, `/api/terminal/screen?position=DF&metrics=tackles_won&sort=tackles_won` returns the same top player and the same 24 regulars (36 with no minimum).
- **"most yellow cards"** still lists the most first ("… Noel Oliveira, 4").
- **Rules:** CSP header unchanged (`script-src 'self'`). The 1f97175 diff touches no markup and no `innerHTML`.
- **Read-only:** the server log shows 32 GETs, no POST, PUT, PATCH or DELETE, and no 4xx or 5xx.
- **Console:** no errors.
- **Unchanged since round 2,** and so not re-derived: complete evidence, the moments count, the four fixes, the stale guard, the saved-layout migration and `Regista.store` only. Their tests pass.

## Should fix

### 1. A plural verb after a position is not mapped, and "dribble" ranks the opposite stat

**Where:** `src/regista/static/scout/terminal-words.js`, `VERB` (and `SYN`), now reached through `POS_OPEN`.

**Detail:** round 2 sets `who` after "which <position>" so that "a verb after it names the stat as after who". With a plural position, the verb is plural. `VERB` has the base form only for score, create and concede; the other verbs are listed only with an s ("dribbles", "shoots", "tackles" and so on). So the singular question works and the plural one does not.

| Question | Answer now | The singular form gives |
|---|---|---|
| `which forwards dribble the most` | **Dribbled past** (checked in the browser: "Forwards ranked by Dribbled past (most first; fewer is better) … Haruki Fontaine") | `which forward dribbles the most` gives Take-ons won |
| `which players dribble the most` | **Dribbled past** | `who dribbles the most` gives Take-ons won |
| `which forwards shoot the most` | Nothing found | Shots |
| `which defenders head the most` | Nothing found | Aerial duels won |
| `which midfielders cover the most ground` | Nothing found | Distance |
| `which defenders tackle the most` | a choice of 5 stats | Tkl + int (adj.) |
| `which midfielders pass the most` | a choice of 37 stats | Progressive passes |
| `which keepers save the most` | a choice of 3 stats | Saves |
| `which midfielders run the most` | a choice of 2 stats (not distance) | Distance |

The press, carry, assist and foul forms also fall back to a choice of stats.

The dribble case is a confidently wrong answer: the scout asks for the best dribblers and gets the players dribbled past most often. It happens because "dribble" is not in `SYN` (dribblers, dribbler, dribbling and dribbles are), so `resolveMetric('dribble')` takes the one label that contains "dribble". The "which players dribble" form was already wrong before round 2. The position form makes it the natural phrasing.

The tests (`test_which_position_questions_and_their_verbs`) cover only score, concede and win, which are the verbs that already had base forms.

**Suggested fix:**
- Give every `VERB` entry its base form (dribble, shoot, tackle, pass, run, cover, press, save, carry, head, assist, foul), or strip a trailing s before the lookup.
- Add "dribble" to the dribblers `SYN`.
- Add a test that every `VERB` entry gives the same stat in "who <verb>s the most" and "which forwards <verb> the most".

### 2. "which <position> are the best <plural noun>" answers Nothing found

**Where:** `natural()`, the step that puts the position back in front of the rest.

**Detail:** each of these answers Nothing found (in the browser too, for the first):
- `which forwards are the best finishers`
- `which forwards are the top scorers`
- `which midfielders are the best creators`
- `which defenders are the best tacklers`
- `which forwards are the best dribblers`

Meanwhile `who are the best finishers`, `best finishers among forwards` and `the best finishers forwards` work. "Best finishers" is one of the three example chips, so this is a likely next question.

The cause: when anything is left after "the best", the position goes in front, which gives "forwards the best finishers". After that:
- `SUPER` is read only off the front, so "best" stays.
- The token filter removes "the" but not "best".
- `SYN` needs the whole word ("finishers").

The same gap exists without "which": `forwards best finishers` gives none.

**Suggested fix:** put the position after the leading superlatives ("the best forwards finishers", or append it: "the best finishers forwards", which already works). Alternatively, drop `SUPER` words in the token filter. Then add `which forwards are the best finishers` and `which midfielders are the top creators` to the test.

## Nits

- `which forwards at Brookfield have the most goals` and `which Brookfield forwards have the most goals` answer Nothing found. `which forwards have the most goals at Brookfield` works.
- `who has played the most minutes` and `which forwards have played the most minutes` answer Nothing found. `forwards with the most minutes` works.
- `which forwards play like Toure` and `which forwards are similar to Toure` answer Nothing found. `forwards like Toure` works.
- `who wins the most duels` offers 5 stats. That is reasonable, since no single stat is "duels won".
- Still open from earlier rounds:
  - the review A and B pass 2 nits (`… in the league this season`, `Toure most goals`, which club has the most, the CLAUDE.md §2.10 wording, "least minutes", status-line wording)
  - the safeguard's minor items (team counts before load, "Toure vs Ustinov" before similar players load, no Cache-Control)

## Not done (per the task)

Nothing was pushed, no PR was opened, and nothing was merged.
