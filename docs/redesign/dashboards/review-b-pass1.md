# Review B, round 1: fidelity and UX

Reviewer B compared each section with the sandbox, side by side, on the `ux/dashboards` branch at ebace2e. The app ran offline on port 8142 and the sandbox on port 8143, at 1440 px and 375 px. I also checked the panes at about 800 px, keyboard paths, labels and wording. I fixed nothing.

**Verdict: not signed off.** Five things should be fixed. Nothing must be fixed.

## What matches the sandbox

These match in structure, wording and behaviour:

- `/me` Overview, Matches & videos, Messages, Team and Settings.
- The shared profile page on `/players/{id}`, including the scout bar.
- Scout Overview, Shortlist board, Reports, Messages and Team.

I checked these working:

- Messages are shared between the two dashboards. A reply sent as Femi showed up in Maya's inbox, with clip cards that play.
- The scout bar's links work: Message, Write a report and Notes. Back returns to the profile.
- New report, Insert a moment, and cited moments that play.
- Compare numbers open their moments.
- The Scout agent (Data Search) works.
- Switch player, `?player=` kept in the panel links, and a goalkeeper's dashboard.
- Upload cards in all three states (working, waiting for you, done), with the moments and the recap. I faked the records in my own tab.

Layout and accessibility:

- The left panel is correct on Home, `/me`, `/scout` and `/players/{id}`. The current section is yellow and the parent link is plain text, with `aria-current` set correctly. On phones the sections are a second row of tabs.
- Nothing scrolls sideways at 375 px in any section.
- No controls are missing a name, and there are no console errors.
- The page tests pass (104).

## Should fix

1. **Find players is not the approved layout.**
   - The league table sits beside the cards, so at 1440 px there are 2 card columns instead of the sandbox's 4.
   - Today's five filters plus Reset replace the sandbox's three (Name or club, Position, Sort by).
   - Three pieces of text were added that the sandbox does not have:
     - a tagline;
     - the Synthetic badge sentence;
     - a paragraph explaining the engines ("…through Regista's player tools (MCP)…").
   - Keep the engine picker, which is needed. Bring the rest back to the sandbox's structure. The table could go under the cards or into Team.
   - Files: `static/scout/index.html`, `scout.css`.
2. **Compare is today's table, not the sandbox's.**
   - It has 28 rows with "94th percentile" and "0th percentile" under each number, and is about 1500 px tall.
   - The sandbox has eight headline rows: "Per 90 minutes this season. Pick a number to see the moments behind it."
   - "Nth percentile" breaks the plain-English rule ("Higher than 88% of the league's midfielders").
   - File: `scout.js`, the compare renderer.
3. **Two wording bugs on player cards.**
   - `shortPct` turns "Not above any of the league's midfielders" into "Not above any of midfielders" (`scout.js:83`).
   - In the Scout agent's answer, the card line reads "Take-ons won: 2.69 per 90 · 1st of 18". It does not say of whom, and Bruno Lindqvist (second overall) shows "1st of 18" because the rank is among midfielders. Say "1st of 18 midfielders" (`scout.js:470`).
4. **Extra caveats, and the two dashboards disagree.**
   - Scout Settings says "Password: Regista has no sign-in yet." Its Sign out says "Regista has no sign-in yet, so there is nothing to sign out of."
   - On `/me` the same rows are an Admin key row and a Sign out that forgets the key.
   - The brief allows one quiet line about browser storage and no other caveats. Drop the Scout Password row, or match `/me`, and give Scout's Sign out something real to do.
   - The sandbox has none of the "A synthetic player…" notes on the profile page (and so on My profile) or the badge on Find players; the footer already says it. Remove them, unless Zaid wants them kept.
5. **An id is shown in the upload steps.** The Saved row prints the worker's note "13 files saved as match pv_8807d7835c". The Is this you? row prints "2 answer(s) from the player". Show the note without the match id, and change "answer(s)" to "answers", as the answered line already does (`me.js`, `steps()` / `pipeline()`).

## Nits

- "Messages, notes and reports are kept in this browser only." also appears in Scout Reports. The brief asks for it in Messages and Settings only.
- The notes box says "private to you", but Scout Privacy defaults to "Fairhaven FC's scouts". The sandbox said "private to Fairhaven FC".
- Overview activity reads "Gino Mensah is on your shortlist: Offer". The sandbox style is "Farid Vargas moved to Trial".
- "← Back to Scout" on the profile page; the sandbox says "← Back".
- The Numbers introduction on the profile is longer than the sandbox's "This season, against the league's other forwards. Pick a number to see the moments behind it."
- The seeded Femi report quotes 11 matches, 1.78 goals per 90 and 5.92 shots per 90. Those numbers hold only while his friendly is in the profile. Offline the profile shows 10 matches, 1.80 and 5.09.
- A player with no conversations gets a tall empty Messages panel.
- Mute and Block change their label and set `aria-pressed` at the same time, so screen readers announce the state twice.
- The nav count reads "Messages 1" to screen readers. Add "unread" as hidden text.
- The extra line in Add a match ("an MP4 at 640x360, 10 frames a second…") is not in the sandbox.
