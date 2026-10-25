# Fix round 2 (B): "which <position> have the most <stat>"

Both round-2 reviewers found the same gap: `which forwards have the most goals`, `which strikers score the most`,
`which defenders win the most tackles` and the like answered Nothing found, while `which players have the most goals`
worked.

## Fix (src/regista/static/scout/terminal-words.js)

- `POS_OPEN`: `(which|what) <position word> (are|is|have|has|…)?` is read as an opening phrase. The position is kept
  and put back in front of the rest (`forwards the most goals`, `defenders the most tackles at Brookfield`), or after it
  when only "the best" is left (`which forwards are the best` reads as `the best forwards`). `who` is set, so a verb
  after the position names the stat as it does after "who" (`which strikers score the most` ranks forwards on goals).
  "which/what players" is everyone, with no position filter. "what" with no position after it is not read this way.
- `win/wins/won` after "who" or a position (`who wins the most tackles`, `which forwards win the most fouls`) reads as
  the stat "<stat> won" when one exists (Tackles won, Fouls won, Aerial duels won), else the stat itself. Before this
  `who wins the most tackles` answered Nothing found too.

Checked in the browser (127.0.0.1:8217/scout#terminal): `which defenders win the most tackles` gives
"Defenders ranked by Tackles won: 24".

`which defenders have the most tackles` gives a choice of three stats (Tackles won, Tkl + int, Tkl + int (adj.)), the
same as `who has the most tackles` and `defenders with the most tackles` already did: "tackles" alone names no single stat.

## Tests (tests/test_scout_terminal.py)

- `PLACED_FORMS` adds `which forwards have the most {}`, `which midfielder has the fewest {}`, `what keepers have the
  most {}` and `which defenders have the most {} at Brookfield`, checked for every catalogue metric by key, label and
  short label.
- `test_which_position_questions_and_their_verbs` covers the reviewers' examples, the verb forms, "which forwards"
  alone, and that "what is xG" picks up no position.

Full suite: 856 passed.
