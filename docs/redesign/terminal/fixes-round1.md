# Scout terminal: fixes for review round 1

Branch `ux/terminal`. Three findings from review A, round 1. All three are fixed, and each has a test.

## 1. The heat map counted uploaded and claimed matches but called them "this season"

**Cause.** The heat map read the profile grid (`GET /api/players/{id}`). Season adds every confirmed claim and every
finished Player-view upload to that grid. Every other number in the Terminal comes from the metrics engine, which
counts league fixtures only.

**Fix.**
- `Season._aggregate` (src/regista/season/profiles.py) now copies each player's touch grid into `Season.league_grids`
  after the league fixtures and before any claim or upload is added. The cells and events are the same as the profile
  grid, and the profile grid itself is unchanged.
- There is a new read-only endpoint, `GET /api/players/{id}/heatmap` (src/regista/terminal_api.py). It validates the
  id (400 for a bad id, 404 for a player who has not played in the league) and returns the player card, the
  league-only `grid`, its `total`, a `scope` line, `pitch` and the synthetic note. It is public, like every other
  terminal read, and is listed in tests/test_access.py.
- `PITCH.heatmap_rule` now says the grid counts Regista League fixtures only, and that the profile page's grid also
  counts claimed and uploaded matches.
- terminal.js: `renderHeat()` and the `HEAT` command read `/heatmap` through a new `heatOf()`. The old
  `profileOf()` had no other callers and is removed. The caption now says "N on-ball actions in league matches this
  season".
- Docs updated: docs/scout-terminal/build/metrics.md, docs/redesign/terminal/build.md, docs/architecture.md and
  CLAUDE.md §2.9.

**Test.** `test_the_heat_map_counts_league_fixtures_only` (tests/test_metrics.py) builds a fake upload for Femi Toure:
one of his league fixtures copied as a non-league match, with him as the uploader. It checks that his profile gains
one appearance and more grid touches, and that `/heatmap` stays exactly the same. Without an upload, `/heatmap` equals
the profile grid. The input-validation and hidden-ratings tests now include `/heatmap`.

**Checked locally.** `/api/players/pl_bro_09/heatmap` returns 407 (no uploads offline). The panel caption reads
"407 on-ball actions in league matches this season (...)".

## 2. "Reset this demo" in another tab was undone by an open Terminal

**Cause.** When nothing was stored, `readStore()` kept the workspaces and history it already held in memory. The next
save then wrote them back to storage.

**Fix (terminal.js).**
- When nothing valid is stored, `readStore()` now clears a pending save (`clearTimeout(saveT)`) and sets
  `store = {cur: 0, ws: [null, null, null], hist: []}` before `clean()`.
- The `R.store.watch` handler also clears the history cursor and draft, the open reel, the scatter cursor and the
  screener's active cell, and stops the video, whenever the key is gone after the event.
- On a full clear (`key === null`), the handler drops the in-memory copy too (`R.store.remove`). Regista.store keeps
  its memory fallback in that case, so without this the old workspaces would come back.
- `saveT` is now declared with the other state at the top of the script.

**Test.** `test_reset_this_demo_in_another_tab_resets_an_open_terminal` (tests/test_scout_terminal.py), alongside the
existing same-tab test.

**Checked locally.** I ran `CMP Toure Ustinov` and `TEAM EAS`, then did what another tab's reset does: removed the key
and sent the `storage` event. After one click and a command, storage held `compare: []` and `hist: ["HELP"]`, so the
old compare list and history did not come back.

## 3. CMP with no player crashed and left the previous success line on screen

**Fix.** `cmdCmp()` now tests `!rs.length` first and shows the usage line. Only after that does it look for an
unknown name.

**Test.** `test_cmp_without_a_player_says_how_to_use_it`.

**Checked locally.** After a successful CMP, both `CMP vs` and `CMP ,` show "CMP needs two or three players: CMP
<player> <player> [<player>]." and the page reports no errors.

## Suite

- `python3 -m pytest -q`: 836 passed.
- `python3 -m pytest -q -m slow`: 13 passed.
- The live app and Azure were not touched. The local app ran with `REGISTA_DOTENV=` on 127.0.0.1:8765 and was
  stopped afterwards.
