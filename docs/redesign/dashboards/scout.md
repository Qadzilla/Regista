# The Scout dashboard (/scout)

The approved sandbox Scout dashboard (Maya Lindqvist, chief scout, Fairhaven FC) ported into the real app. Nothing is
committed.

## Files

| File | What changed |
|---|---|
| `static/scout/index.html` | Rebuilt: seven section panels (`data-panel`), the left panel with Scout's sections, loads `dashboard.css`, `demo.js` and `profile-view.js` |
| `static/scout/scout.js` | Rebuilt around `Regista.sections` and `Regista.demo`; today's live parts kept (league, filters, cards, Scout agent, compare) |
| `static/scout/scout.css` | Only what `dashboard.css` does not cover: cards with a star, league table, agent options and trace, compare table, citations, phone rules |
| `tests/test_scout_page.py` | Updated for the new script list and nav; new tests for the sections, the store, the scout-bar links, clip keys, the CSP |

## The sections

| Section | Live from the API | Kept in this browser |
|---|---|---|
| **Overview** | Uploads by shortlisted players (their profiles' filmed matches), how many players fit the needs | Replies waiting, drafts to finish, stage tiles, recent activity (from messages, reports and the shortlist) |
| **Find players** | Scout agent (both engines, with "How the Scout agent answered": plain steps, then step names and times), filters (`/api/players`), cards, league table | Stars and stage badges |
| **Shortlist** | `/api/compare`; every number opens the moments behind it (the player's evidence, playing beside the list; ratios open their numerator) | Stages, notes, move-to, compare picks (2 or 3) |
| **Reports** | "Insert a moment" lists the player's best moments from `/api/players/{id}` | The seeded Femi report, drafts saved as you type, verdicts, cited moments that play |
| **Messages** | Clip cards play the API's clip videos | One conversation store with `/me`: Maya's replies reach Femi and his reach her |
| **Team** | Fairhaven's crest, table position, squad (`/api/season`), and each need's fitting players (headline per-90 percentile, other clubs only) | The needs (add, remove) |
| **Settings** | | Email, notifications, privacy, Reset this demo |

Scout-bar links from `/players/{id}` work on their own: `#messages/<id>` opens or starts the conversation,
`#shortlist/<id>` puts the player on the shortlist and in compare (and highlights them), `#reports/<id>` opens their
draft. The shortlist and reports links then drop the player from the address, so a reload does not repeat them.

"Messages, notes and reports are kept in this browser only." appears in Messages, Reports and Settings.

## Checked

- `python3 -m pytest -q`: 651 passed (the full suite, with the other builder's work in the same checkout at that moment).
- Offline app on port 8122 (`REGISTA_DOTENV=`), in the desktop app's browser at 800 px and 375 px: every section renders,
  no console errors, no sideways scroll at 375 px in any section. Asked "Forwards with the most goals" and "Who wins the
  most take-ons?" (Data Search), starred and unstarred, the scout-bar links for shortlist, reports and messages, compare
  of Hugo Delgado and Femi Toure with Femi's 6 goals playing, a draft on Amari Ustinov with a cited goal and a verdict,
  a scout message and a player reply through the shared store (count and Overview card updated), Reset this demo.
- Offline there is no Foundry: picking Foundry answers with the rules and says why. No uploaded friendly offline, so
  the "added a match" card does not show.

## Inventory (today's /scout)

Kept as they were: SC-01, SC-04, SC-07, SC-08, SC-09, SC-11, SC-14, SC-15, SC-16, SC-19, SC-20, SC-21, SC-23, SC-27,
SC-29, SC-30.

Changed:
- SC-02, SC-03: four scripts now (regista.js, demo.js, profile-view.js, scout.js); the panel shows Scout's seven sections.
- SC-05: the page title is "Find players" with the promise as its subtitle; the synthetic badge and sentence stay.
- SC-06: the league table moved into Find players (beside the cards from 1100 px, above them on narrower screens);
  Fairhaven's row is tinted and the picked club shows as pressed.
- SC-10: Instant is now called Data Search, as on Home; pill buttons.
- SC-12: the question box allows 200 characters, what the API accepts and what the error says (it allowed 300).
- SC-13: the answer adds the number it was about on each card and the trace of steps.
- SC-17, SC-18: same filters, Name first; the query keeps the `#find` hash.
- SC-22: the sandbox's card look (kit shirt, three rates with bars, the percentile said in words, stage badge); star and
  whole-card link kept.
- SC-24, SC-25, SC-26, SC-28: the shortlist is `Regista.demo` (the old key is merged in once); it is its own section with
  four stage columns; compare picks are ticked by the scout, no longer the first three automatically.

## Open questions (shared files I do not own)

- `tests/test_product_page.py`: add `"scout/index.html"` to `SECTIONS_REQUIRED`. The page passes that test already.
- `shared/demo.js`: `reset()` leaves the old `regista-scout-shortlist` key, so after a reset its players are merged
  back into the shortlist. Remove that key in `reset()` too.
- The rules engine does not hear "score": "Forwards who score the most" ranks by minutes. The example now asks
  "Forwards with the most goals".
