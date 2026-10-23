# Home: landing, results across every match, the match view (item 1)

Builder: Home. Branch `ux/app-redesign`, on top of the navigator (6dd5001). Files changed: `src/regista/static/product/`
`index.html`, `app.js`, `product.css`, and `tests/test_product_page.py`. No Python, API, data, infra or deploy change.
Line numbers below are in the new files (`index.html`, `app.js`, `product.css` in `src/regista/static/product/`).

## What Home is now

Three views on the one page `/`, switched by `showView()` (app.js:133). Only the match view has a URL with a query.

| view | what is on it | where |
|---|---|---|
| landing | REGISTA logo (h1, the wordmark in the header's style, larger), tagline "Every moment. Every highlight. Every player. Found in seconds.", the search box (#q) with the six prompts typing in and out, the "Who answers" switch Data Search / Ask Microsoft Foundry under it. No pitch copy, no example buttons. | index.html:27-40; app.js:381-416 (prompts); product.css "Home's landing" |
| results | compact search bar (#rq) with the same switch beside it, a note line (#searchNote), the moments section (heading, sort, tag chips, grid, Show more) exactly as before; with Ask Microsoft Foundry the conversation panel on the right. | index.html:45-59; app.js:526-680 |
| match | Back to results, match title, Scout profile link, vision note, timeline, stage (video + details, then the four actions in one row), "Match recap" folded (its own Instant / Foundry switch inside), the moments section; the conversation panel on the right. | index.html:62-113; app.js:758-1000 |

The moments section (index.html:116-128) is one element that `showView()` moves under the results or under the match,
so every existing id (#resultsHead, #tagbar, #grid, #empty, #more, the sort buttons) stays unique and works in both.
The conversation panel (index.html:132-146) is one `aside`: log, follow-up box (#fq), a small switch, the engine hint.

### Typing prompts (landing)

The six prompts from the brief type into the empty box and back out (app.js:381-416, as the sandbox's `tick()`). They
pause while the box has focus or text, and while the landing is hidden. With `prefers-reduced-motion: reduce` the first
prompt shows still. Tab (without Shift) on an empty box fills in the prompt showing. Pressing Search with an empty box
searches the prompt showing (the sandbox did the same; this uses the whole prompt, not the half-typed text).

### Search across every match (Data Search)

`searchEvery()` (app.js:526) sends the question to every match's own `POST /api/matches/{id}/chat` with the Instant
engine (no model), each with that match's query so far, 6 requests at a time (`PARALLEL`, app.js:16), and merges the
results best first (watchability, then the match's place in the list, then time). The list (`searchList()`,
app.js:483) is the library's matches from `GET /api/matches` (featured first, picker order) and the league's from
`GET /api/season` (round order). A match with `source: cosmos` (no event stream, cannot answer questions today either)
is left out and the note line says how many.

- **Conversation state.** Each match keeps its own query state (`search.states`), sent back with the next message, so
  follow-ups ("now the replays", "second half", "start over") work as they did per match. The landing starts a fresh
  search (states cleared, log kept); the compact bar and the panel's box continue the conversation. "start over" brings
  the landing back and keeps the log (I-077).
- **One name, one player.** Each match reads a name on its own, so "Femi Toure" resolved to Femi Rahman or Milan Toure in
  matches Toure did not play, and to "any player" where nobody matched (seen locally). The page therefore keeps only
  matches where the question named someone when at least one did, and, when the question says a full name (else a
  surname) that some result has, only that player's moments (`namesIn()`, app.js:511). The note line says so. This is
  page logic on top of the per-match answers, not a server change; see open question Q1.
- **Show more** asks "more" of the matches that have more (app.js, `wire()` `$('more').onclick`). **Match order**
  orders by match (list order), then time. **Tag chips** and **sort** work on the merged set.
- **Badges.** For each match that found something the page reads `GET /api/matches/{id}` once (origin, for "Cut from
  video") and, for library matches only, `GET /api/matches/{id}/clips` (label models, for "Labelled by Microsoft
  Foundry") (`loadSearchDetails()`, app.js:714). League matches' clips are about 430 KB per match and are all labelled by
  Regista's rules (checked locally: 414 of 414 `rules-v0`), so they are not read; see Q3.
- **Reply in the log.** "N moments in K matches · {understood}. Best: {title}, {match}." Its "How Regista answered" adds
  each match's steps together (one line per step name, with the number of matches and their summed time) and gives the
  wall time of the whole search.

### Ask Microsoft Foundry

The grid is the same Data Search across every match. Then one `POST /chat` with `engine: foundry` goes to the match
holding the best result, with that match's query so far and the conversation history (app.js, in `searchEvery()`).
The reply bubble says plainly: "Microsoft Foundry wrote this from {match}, the match with the best result. The moments in
the grid come from every match." If Foundry is not set up or falls back, the merged reply stands with the existing
fallback line; a 429 or other error is shown as an error bubble with Retry where it was offered before. Q2.

### Opening a clip: the match view

A card on the results calls `openResult(mid, clipId)` (app.js:758): the match view opens, the match loads (or the player
switches when it is the same match), the clip plays on the stage, and the URL becomes `?match=&player=&clip=`
(replaceState, as before). Deep links (`?match=&player=&clip=&t=&recap=1`) open the match view directly; `recap=1` opens
the folded recap, writes it and scrolls to it (`openRecap()`, app.js:1216). A link that fails lands on the landing with
the link cleared (the featured match still loads quietly behind it, for the pickers).

Changes the brief decided, all in the match view:

- **Explainer line removed:** `#matchSub` (the manifest subtitle, I-051) is gone from the markup and the script.
- **Conversation in the right panel only:** one log, in the panel. "How Regista answered" is one line per answer
  (`How Regista answered · Data Search, no AI model · 3 steps`); the plain steps open on demand, and "Details: step names
  and times" one click further (app.js:877).
- **Recap folded** into `<details>` "Match recap" with its own Instant / Foundry switch inside (index.html:95-110). It is
  written when first opened for a match and player (Instant), not on every load; back to Instant on every new match or
  player as before.
- **Stage actions in one row:** the actions moved out of `.info` to span the stage under the clip and its details
  (product.css `.stage > .actions`); smaller buttons so the four fit on one row at desktop width; they wrap on phones.
- **No yellow outline on the playing card:** `.card.on` has no style now; the playing card gets `aria-current="true"`.

Questions asked in the match view (the panel's box, placeholder "Ask about this match") search that match exactly as the
old ask box did (`send()`, app.js:813): the reply drives that match's grid, timeline, stage, reels, way-out button,
"start over" (back to the player's moments) and "in match order". Each reply is tagged with where it searched ("Every
match" or the match's name).

## Cost (for the PR)

- Data Search: one `POST /api/matches/{id}/chat` per searchable match per question (34 here: 4 library + 30 league),
  Instant engine, no model. Measured locally: about 0.5 s for all 34 when warm; about 23 s the first time on a cold
  server, because each league match's event stream is regenerated on first use (about 3 s each). Plus, once per session
  per match that found something, `GET /api/matches/{id}` (about 7 KB, about 40 ms) and, for library matches, `GET
  /clips` (a few KB). "Show more" asks only the matches with more.
- Ask Microsoft Foundry: the same, plus exactly one Foundry call per question (one `/chat` with `engine: foundry`),
  under the existing Ask limits (3 per minute per visitor).
- Card previews: as before, a preview loads only when its card scrolls into view, but results now span many matches, so
  a cold server renders clips from several matches on the first search.

## Inventory: where each item lives now

Navigator items (I-006 to I-009, I-020 to I-028, I-035) are in docs/redesign/navigator.md. "kept" = unchanged in place.

| items | new place |
|---|---|
| I-001, I-002, I-003, I-004, I-005 | kept (meta description still says "Every touch, every replay, every player, found in seconds."; Q6) |
| I-010 to I-019 Match and Player pickers | kept in the header on every Home view; changing either opens the match view of that match / player (Q4) |
| I-029 cross-page wording | not touched (other pages) |
| I-030 to I-034, I-036 deep links, URL sync | kept; deep links open the match view; URL is `?match=&player=&clip=` in the match view, plain `/` on landing and results |
| I-037 to I-039 producers | unchanged pages; their links open the match view (`recap=1` opens the folded recap) |
| I-040, I-041 network error banner, offline text | kept, top of main on every view |
| I-042, I-043 fatal states | kept in the moments section; also shown on the landing (#landingNote) when there is no match to open |
| I-044 loading text | kept ("Loading the match…", "Finding the moments…"); new: "Searching every match… n of N" |
| I-045 Cosmos read-only | kept in the match view (panel box and Ask disabled, the same hint in the panel, full match hidden, no recap, no-video cards); Cosmos-only matches are left out of Home's search and the note says so |
| I-046 h1 | decided: replaced by the logo + tagline |
| I-047 lede | decided: removed |
| I-048 example chips | decided: removed (ASKS and renderExamples gone; chipName kept for the way-out button) |
| I-049 landing shown at start / after start over | landing at start and after "start over" on the results; in the match view "start over" returns to the player's moments (Q5) |
| I-050 match title | match view |
| I-051 match subtitle | decided ("explainer line"): removed |
| I-052 Scout profile link | match view, under the title |
| I-053 vision note | kept in the match view under the title (N-2: not removed) |
| I-054 log | the conversation panel; "Ask for a moment to start." until the first message |
| I-055 ask box | three boxes: landing #q (new search), results #rq (follow-up, every match), panel #fq (follow-up: every match on results, this match in the match view); all type=search, maxlength 300, 16 px or more |
| I-056 engine switch | relabelled Data Search / Ask Microsoft Foundry (decided); on the landing, the results bar and the panel, kept in step |
| I-057 Ask button | panel #go; also Search buttons #homeGo, #barGo; all disabled while a reply is pending |
| I-058 engine hint | kept in the panel, under the box (N-2: not removed); says whether questions there search every match or this match |
| I-059 to I-064 send, seed, bubbles, waiting line, reply, fallback line | kept (panel); seed from the picked player in the match view |
| I-065 to I-068 How Regista answered | decided form: one summary line per answer, plain steps and the step names and times on demand |
| I-069 error reply and Retry | kept (panel); on the results, when every match failed, the error and a Retry button also show in the grid area |
| I-070 way-out button | kept (panel); on the results also under the empty text |
| I-071 to I-077 sort from reply, applyReply, heading, empty text, reels, match order, start over | kept for the match view; the same for Home's search on the merged set (reel: Q7) |
| I-078 to I-089 timeline | match view, unchanged |
| I-090 to I-097 stage | match view, unchanged |
| I-098 to I-101 stage actions | match view, one row under the clip (decided) |
| I-102 to I-104 | match view, unchanged |
| I-105 to I-113 recap | folded "Match recap" (decided), switch inside, reels, citations, by-line unchanged |
| I-114 to I-129 results, sort, tag chips, grid, cards, badges, empty, Show more | one moments section, under the results or the match; cards unchanged (plus an invisible `data-mid`); I-127 decided (no yellow outline) |
| I-130 to I-134 footer | kept, below every view |
| I-135 to I-140 How it works and the realism report | kept (the report reads the match on screen in the match view) |
| I-141 to I-143 keyboard | kept; new: Tab fills a prompt; focus returns to the bar or panel box after a reply |
| I-144 to I-146 responsive | kept; new: at <= 1100 px the panel goes above the content and stops sticking (as the sandbox); at <= 760 px the results switch spans the width and the stage actions wrap |
| I-147 data model | kept for the match view; Home's search keeps its own set (`search`) |
| I-148 /search and /ask | still not called; Home uses each match's /chat |

## Checked in a browser (local server, REGISTA_DOTENV empty, port 8072)

1440 x 900 and 375 x 812: landing (prompts typing, Tab fills), Data Search "Find me all the nutmegs" (38 moments, 15
matches), Ask Microsoft Foundry (panel on the right; Foundry not set up locally, so the fallback line shows), "Show me
Femi Toure's goals, assists and shots" (39 moments, Femi Toure only, Show more 9, Match order, "now the replays" 13),
"Show me every header this season" (Foundry badges on the library's header clips), "start over" (landing back, log
kept), "make a reel of the nutmegs" (match view, "Reel · clip 1 of 3"), a card into the match view (clip plays, URL
`?match=&player=&clip=`), a question in the match view with How Regista answered opened, the folded recap opened,
`?recap=1`, a bad link (landing, link cleared), the Match picker from the landing (vision match: note and badges). No
sideways scroll at 375 px on landing, results or match view; no console errors.

## Open questions

- Q1. The name filter (one name, one player across matches) is page logic over each match's own reading of the name.
  A server-side search across matches would do this properly; the brief keeps Python out of scope.
- Q2. Ask Microsoft Foundry writes its reply from one match (the one with the best result): the `/chat` Foundry engine
  reads one match, and `/ask` reads one match or the search library. The panel says so on every Foundry reply.
- Q3. The "Labelled by Microsoft Foundry" badge on Home's results reads label models only for library matches; a league
  match labelled by Foundry in future would show no badge on the results (it would in its match view).
- Q4. The Match and Player pickers stay in the header on the landing and the results (kept where they were); they could
  move into the match view's title line. Needs a decision.
- Q5. "start over" asked in the match view resets to the player's moments there, not to the landing.
- Q6. The meta description (I-001) still says "Every touch, every replay, every player, found in seconds."; the new
  tagline is on the page only.
- Q7. A reel is one match's (the reel endpoint takes one match): a reel asked for on the results plays the best match's
  part of the results in that match's view. Download reel and Export moments are per match too, so they live in the
  match view only.
- Q8. The results cards do not say which match they are from (the brief keeps the cards exactly as they were).
- Q9. The browser Back button: views switch with replaceState (as before; a test pins no pushState), so Back leaves
  the page; "Back to results" is a button in the match view.
- Q10. On phones the conversation panel sits above the match view's stage (the sandbox's order); with a long
  conversation the clip is further down (the panel's log is capped at 360 px there).
- Q11. "Find me shots from outside the box this season" is read as "any player · shot" by the server's parser (no
  distance filter); the prompt promises more than the search does. Not a page change.

## Pass 2 fixes (review-a-pass2.md S1-S3, review-b-pass2.md S1-S2)

Checked on a local server (REGISTA_DOTENV empty, port 8071) at 1440, 1280, 1110 and 375 px; full suite 605 passed.

- Results bar on narrow screens (A-S1, B-S1). The compact bar and `#searchNote` moved out of `#resultsView` into
  `#resultsTop`, the first child of `.work`, spanning both columns (index.html, `.rtop` in product.css; shown with the
  results in `showView`, app.js). At <= 1100 px `.rtop { order: -2 }` keeps it above the panel. Measured at 375 px with
  Ask Microsoft Foundry: bar 213 px, panel 327 px, grid 1049 px. At 1440 px the bar spans the top and the panel sits on
  the right under it, as in the sandbox. DOM order is now bar, grid, panel (the panel was already last).
- Stage actions in one row (A-S2). The button says "Watch the full match"; on matches over 10 minutes a muted line under
  the row says "Watch the full match: the first view takes a few minutes." (`#fullMatchNote`, linked with
  aria-describedby; hidden with the link for Cosmos DB matches). Above 760 px the row no longer wraps: a label wraps
  inside its button where the stage is narrow. rl_r08_bro_fai: one row at 1440, 1280 (row 524 px of 626) and 1110 (labels
  on two lines). At 375 px the row still wraps, as before (adaptation I-098, a yes/no for Zaid).
- Step counts (A-S3). `aggregate()` counts distinct matches per step and the runs separately; the details now read
  "librarian.search_clips 38 ms · 53 runs in 34 matches" (and "· 34 matches" when each match ran it once).
- Data Search results announced (B-S2). `#resultsStatus` (visually hidden, role="status") in the results heading row is
  set to the reply ("21 moments in 10 matches · any player · header. Best: …"), the error, or "no matches", only while the
  conversation panel (the other live region) is hidden.
