# Safeguard check: the two dashboards in the real app

The last step after the builders. I checked the port against the inventory (`inventory.md`) and the rules, applied the
builders' requests on shared files, and ran the full suite. **654 tests pass.**

## Builders' requests I applied

- **Scouts see the player's My details.** `player/player.js` now applies the player's own edits from `/me#team` (name,
  position, number, foot, height, "About you") to `/players/{id}` in the same browser, and redraws when another tab
  changes them.
- **The shared renderer has a slot for foot, height and "About you".** `view.identity(name, position, kit, { foot,
  height, bio })` in `player/profile-view.js` fills it with textContent. `/me` uses it instead of adding its own div into
  the renderer. The styles moved from `me.css` to `dashboard.css`.
- **Reset this demo also forgets the old Scout shortlist key** (`regista-scout-shortlist`) in `shared/demo.js`.
  Without this, its players came back after every reset.
- **`scout/index.html` added to `SECTIONS_REQUIRED`** in `tests/test_product_page.py`.
- **The Scout rules engine understands "score".** "Forwards who score the most" used to rank by minutes. It now ranks
  by goals, and the parser test covers it (`regista/season/scout.py`).

New tests: reset forgets the old key (`test_shared_dashboard.py`), and the details reach the profile page
(`test_player_page.py`). I updated `test_me_page.py` to the new `identity()` call.

## The inventory, item by item

I read every item against the new code and ran the pages on a local offline app (port 8131, no `.env`) at 1280 px
and 375 px. Every section of `/me`, `/scout`, `/players/pl_bro_09` and Home rendered. Nothing scrolled sideways, and
the console showed no errors.

- **/me (ME-01 to ME-63):** all present. The items the design changed are the ones the builder listed in `me.md`:
  sections replace steps 1-3, the badge is dropped, and the finder became Switch player.
  - Upload, polling, steps and clock, questions, answers, results and recap code are today's.
  - Admin-key prompt, 401 and 403 handling, the read-only and locked states: kept.
  - Opens on Femi Toure, and `?player=` still works.
- **/players/{id} (PL-01 to PL-31, AM-01 to AM-15):** all present in the shared renderer.
  - Summary, reel with per-kind chips, "Show every number", evidence (Escape, focus return, kept on reload).
  - Touch map, moments nine at a time, matches with W/D/L and Recap.
  - Back to Scout with its filters; the missing state.
  - `add-match.js` behaves as before, with its inline styles moved to classes.
- **/scout (SC-01 to SC-30):** all present, with the changes listed in `scout.md`.
  - The league table moved into Find players.
  - The engine switch reads Data Search / Foundry.
  - The question box is limited to 200 characters, which now matches the API.
  - The shortlist has stages.
- **Shared and tests (SH-01 to SH-09, T-01 to T-19):** kept, or updated on purpose. Home's left panel is still the
  three links with Home in yellow.

**Restored:** nothing was missing. The builders kept every item or changed it on purpose, and each change is listed
in their reports.

Checked in the browser:
- A reply sent from Femi's Messages reached Maya's inbox: her count went to 2 and an Overview card appeared.
- The Scout agent answered, compare worked, and a number in compare opened its moments.
- My details showed on My profile and on `/players/pl_bro_09`, with markup in "About you" shown as plain text.
- Reset this demo cleared the browser's store.

## Rules checked

- **CSP:**
  - No inline scripts or `on…=` handlers in any page's markup or HTML strings.
  - No `style=""` in markup. Widths and colours are set through `element.style` after drawing.
- **esc():** every API or store value that reaches `innerHTML` in scout.js, player.js and profile-view.js goes through
  `esc()`. me.js builds with `h()` and textContent only, with no innerHTML.
- **Storage:**
  - Every localStorage and sessionStorage access is in try/catch (`Regista.store`, `Regista.key`, demo.js's old-key
    read and remove).
  - Loading the scripts reads no storage (tested in node).
  - With storage blocked, the pages fall back to the seeds in memory (tested).
- **Left panel:**
  - `/me` shows Player profile's six sections.
  - `/scout` and `/players/{id}` show Scout's seven sections.
  - Home is unchanged.
  - On phones the sections form a second row of tabs.
- **Writes to the server:** only the ones that existed before:
  - the upload (`POST /api/player/uploads`) and its answers, both with `X-Regista-Token`;
  - add-match's match upload, Studio job and claim, all with the key;
  - the Scout agent's question (`POST /api/scout/ask`, a read).
  - Messages, shortlist, notes, reports, needs, My details and settings stay in this browser. No new routes.
- Nothing was sent to the live app or Azure.

## Needs Zaid's decision

1. **Seed wording "Six goals in eleven games"** (Maya's first message, and "6 goals in 11 matches" in the seeded
   report). It is right on the live app, where the uploaded friendly makes 11 matches. On a fresh or offline app Femi
   has 10 matches, so it reads one high. Options: keep it, or reword to "Six goals this season".
2. **Design additions beyond the sandbox** (Scout builder):
   - New report opens an "A report on" picker.
   - Saved reports can be edited and deleted.
   - Cited moments in a draft can be removed (×).
   - Squad names link to profiles.
   - Settings "Change" edits the stored email.

   All of these work, but they are not in the approved design.
3. **Lines about having no sign-in on Scout Settings.** The Password row reads "Regista has no sign-in yet." and Sign out
   says there is nothing to sign out of. This follows the sandbox, but the brief asked for no caveats besides the
   browser-only line. On /me the same rows were turned into a working Admin key row and a Sign out that forgets the key.
4. **The browser-only line appears three times on /scout** (Messages, Reports, Settings). The brief named Messages and
   Settings. It fits Reports, but it is one line more than asked.
5. **Player settings are one set for the whole Player side, not one per player.** Toggles on `/me` are shared by every
   player picked in the same browser; only the email is per player. Making them per player needs `demo.settings` to
   take a player id.
