# Fixes for review round 2

One finding: a closed "More filters" kept its Club or Minimum minutes filter on with nothing on screen saying so.

Fixed in `src/regista/static/scout/scout.js`, all three ways the reviewer listed:

- **The link counts hidden filters.** Closed, it reads "More filters (1)" or "(2)" while Club or Minimum minutes is on;
  it updates on every filter change and on Reset.
- **The results line names them.** "11 players at Fairhaven FC, sorted by minutes played"; with a minimum,
  "... with at least 300 minutes ...".
- **The empty state suggests only what is on.** "No players match these filters. Try a club other than Fairhaven FC
  or a minimum below 5000 minutes." It no longer says "Try a lower minimum" when no minimum is set.

Checked offline on port 8143: Fairhaven from the league table (11 cards, line names the club), Fewer filters (link
shows "(1)"), minimum 5000 (link "(2)", the empty state above), Reset (link and line back to plain). A test pins it
(`tests/test_scout_page.py`). Full suite: 657 passed.
