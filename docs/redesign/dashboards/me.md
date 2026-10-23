# The Player dashboard (/me)

The approved sandbox design for Femi Toure's dashboard, now in the real app at `/me`. Nothing is committed.

## Files

| File | What changed |
|---|---|
| `src/regista/static/me/index.html` | Rewritten: the left panel with the six sections, a Switch player strip in the header, one panel per section |
| `src/regista/static/me/me.js` | Rewritten: the six sections, with today's upload, polling and "Is this you?" code kept |
| `src/regista/static/me/me.css` | Rewritten: only what `shared/dashboard.css` does not already style |
| `tests/test_me_page.py` | New: 13 static checks on the page and script |
| `tests/test_product_page.py` | One line: `"me/index.html"` added to `SECTIONS_REQUIRED` |

## What each section does

- **Overview** (`/me#overview`): the header (kit shirt, name, "Forward · Brookfield Rovers · Number 9", an Add a match button) and four parts:
  - **Needs you** cards, built from real data:
    - unread messages, linking to that scout's thread;
    - a question waiting from an upload;
    - the latest upload's state (ready, working, stopped), or "Add a match" when there is none;
    - "No Is this you? questions waiting".
  - **Your season**: matches and minutes, plus the first three headline numbers for the player's position. Each says what it was compared against ("Higher than 94% of the league's forwards").
  - **Your best moment**: a video, with a "Cutting the clip…" line while it renders.
  - **Recent activity**, newest first: messages, uploads and the club's last two results.
- **My profile** (`#profile`): the line "This is what scouts see when they open your profile." Under it, `Regista.profileView.render(el, profile, {})`, the same page `/players/{id}` shows, without the scout bar. My details edits show in its header. Foot, height and the "About you" line go under the header too.
- **Matches & videos** (`#matches`; `#matches/add` opens the form; `#matches/questions` scrolls to the questions):
  - **Add a match**, behind the button. It is today's real form:
    - the admin key prompt, and the read-only and locked messages;
    - the MP4, size and opponent checks;
    - the XHR upload with its progress bar;
    - 401 clears the key and asks again; 403 shows the reason.
  - **Your uploads**: one card per upload, polled every 2 s while an agent works and every 15 s otherwise, paused while the tab is hidden. Each card shows every agent step with its note and time, a live clock on the step that is working, a "now" line, and the failure reason. A finished card shows the player's moments, the links to Home, and the recap with its reel.
  - **Is this you?**: the real questions for each upload waiting on review, with Yes / No, Send my answers and Skip (`POST …/answers` with the key). Earlier answers are listed. "No questions waiting" when there are none.
  - **All your matches**, newest first, each with Open on Home.
- **Messages** (`#messages`, `#messages/<scout>`): the shared conversation store (`Regista.demo`). The player can:
  - reply;
  - attach their own best moments, which arrive as clip cards that play;
  - mute or block (a blocked thread hides the reply box, and the scout's sends are refused).

  The left panel's count is `demo.unread('player', gid)`. A reply from Femi appears in Maya's inbox in the same browser (checked through `demo.forScout('maya')`). Another tab's changes redraw the section (`Regista.store.watch`).
- **Team** (`#team`): **My details** (name, position, kit number, foot, height, about you), saved per visitor with `demo.saveDetails`. They show in the header strip, the Overview, My profile, the squad list and the page title. "Undo my edits" restores the league's details. Below that, the club: crest, league position, squad (from `/api/season` `squad`, "You" marked), results with W/D/L, and the league table.
- **Settings** (`#settings`): who can see and message the player, notifications, and footage consent, all saved per visitor. Also:
  - **Account**: an editable email and an Admin key row with "Forget it".
  - **Sign out**: forgets the admin key in this tab.
  - **Reset this demo**: runs `demo.reset()` and redraws every section.
- The quiet line "Messages, notes and reports are kept in this browser only." appears once in Messages and once in Settings.

## Player choice

- `/me` opens on Femi Toure (`demo.PLAYER`). `?player=pl_…` opens another player.
- A malformed id is ignored. A well-formed id the league does not know opens Femi, with Switch player open and a line saying so.
- Switch player (in the header) searches the league or offers the top six forwards by goals. It keeps the section in the hash and stops polling while it is open.
- The left panel's links are rewritten to keep `?player=`. A plain `/me#team` would otherwise reopen Femi.

## Checked

- `python3 -m pytest -q`: 651 passed.
- Browser, against a local offline app (port 8121, `REGISTA_DOTENV=`), at 800 px and 375 px:
  - every section renders, with no sideways scroll;
  - the only console error is the expected 404 when testing an unknown player id.
- Offline there are no uploads. To check the upload cards I replaced `fetch` in the page, for that browser check only, with three made-up records: one working, one waiting for review with two questions, one done that points at a league match. The working clock, the "your turn" line, the questions, and the moments with the recap all rendered.
- Also checked:
  - reply with an attached moment, then block and unblock;
  - My details flowing to every place it shows, and surviving a reload;
  - settings toggles and Reset;
  - switching to a goalkeeper (Jonah Eriksen);
  - an unknown id.
- Not checked: a real upload or real answers (both would write), the Azure copy of the "now" line, and a Foundry summary on My profile.

## Decisions worth knowing

- The upload steps use the sandbox's row layout and labels: Footage received, Camera shots, Who is who, Is this you?, On the ball, Events, Match written, Clips cut, Saved.
- Today's state logic is kept, with two fixes:
  - The worker's `download` and `publish` roles now light their rows. They were not mapped before.
  - The worker lists every step up front as `pending`. The old code counted those rows as done. They now stay "not yet".
- The questions moved out of the upload card into the sandbox's "Is this you?" panel. The card says "Your turn" and links there.
- The sandbox's Settings had a Password row and a Sign out that did nothing. There is no sign-in, so the Password row is now an Admin key row, and Sign out forgets the admin key: both do something real.
- `add-match.js` (the claims flow) still runs only on `/players/pl_…`. On /me, Add a match is the real upload form.
