# Safeguard: everything removed, hidden, moved, merged or reworded

Branch `ux/app-redesign`, `git diff main...HEAD` at bb705b0 (5 commits: f69587c inventory, 6dd5001 navigator, 35c91ef
Home, 895e3af tests, bb705b0 notes). Checked against docs/redesign/inventory.md (I-001 to I-148, N-1 to N-11), the
brief, and the sandbox (`git show ux/sandbox:sandbox/index.html`, `sandbox.css`, `sandbox.js`). No code was changed
by the safeguard.

Verdicts: **DECIDED** (one of the brief's decisions, quoted), **KEPT** (still there and working, moved or restyled),
**RESTORE** (removed or hidden without a decision: must be put back), **NEEDS DECISION** (a judgement call for Zaid).

Line numbers are in the new files: `index.html`, `app.js`, `product.css` in `src/regista/static/product/`.

## Result

- **RESTORE: none.** Nothing was removed or hidden without a decision, and nothing outside scope changed.
- **NEEDS DECISION: 13 items**, listed in full at the end.
- Spot-checked in a browser (local server on port 8093, `REGISTA_DOTENV=` empty, stopped afterwards), 1440 px and
  375 px: landing (prompts typing, pickers, footer, nav with Home current); Data Search "Find me all the nutmegs"
  (38 moments, tag chips and sort shown, panel hidden); a card into the match view (URL `?match=&player=&clip=`, title,
  Scout link, timeline, stage, the four actions on one row at the same y, folded recap, Back to results, panel with the
  whole log, playing card with `aria-current` and no yellow border); the same deep link at 375 px (no sideways scroll,
  panel above the match); /scout at 375 px (tabs row, Scout current, no sideways scroll). Reviewers own the full browser pass.

## Scope

`git diff main...HEAD --name-only`: `src/regista/static/` (me, player, product, scout, shared), `tests/test_product_page.py`,
`tests/test_player_api.py`, `docs/redesign/`. No Python under `src/regista/` outside `static/`, no API, data, infra
or deploy change. **In scope.**

Test assertions removed or changed, each one following a decision:

| test | old assertion | why it changed | verdict |
|---|---|---|---|
| test_product_page.py `test_the_files_the_page_loads_are_served` | old h1 text served at / | h1 replaced by logo and tagline | DECIDED: "the large REGISTA logo, the tagline …" |
| test_product_page.py (was `test_example_chips_…`) | `const ASKS = [` present | chips removed; the `tagbar` assertion is kept | DECIDED: "No pitch copy, no example buttons." |
| test_product_page.py (was `test_the_views_switch_marks_clips_…`) | Clips current, order /, /scout, /me | nav labels and order | DECIDED: "Labels: Home (/), Player profile (/me), Scout (/scout)" |
| test_player_api.py `test_every_view_links_to_the_player_view` | order /, /scout, /me | same | DECIDED (same quote) |

The `'/search` absence test (test_product_page.py:44-49) is unchanged; Home uses each match's `/chat`.

## Navigation (item 2 of the brief)

| what changed | where | verdict |
|---|---|---|
| Views pill switch removed from every header (product, scout, player, me `index.html`) and moved into `<nav class="views">` in a left `.shell` panel | each page's index.html after `</header>`; shared/regista.css:22-49 | DECIDED: "the view links move to a left panel … with the REGISTA header" |
| Labels Clips / Scout / Player become Home / Player profile / Scout, order /, /me, /scout | same | DECIDED: "Labels: Home (/), Player profile (/me), Scout (/scout)" |
| /players/{id} marks Scout current | player/index.html:18 | DECIDED: "/players/{id} shows Scout as current" |
| Current view in yellow; row of tabs at <= 720 px | shared/regista.css:43, 45-49 | DECIDED: "current view in Regista yellow; a row of tabs on phones" |
| Per-page `.views` overrides deleted (scout.css old 14-17, player.css old 12-15) | scout/scout.css, player/player.css | DECIDED: navigation-only rules, replaced by the shared panel (inventory N-7) |
| Brand in the header | every page | KEPT |
| Clips header still holds the Match and Player pickers | index.html:13-17 | KEPT (I-010 to I-020) |
| New `trackHeader()` sets `--top-h` | shared/regista.js:51-67 | KEPT (addition; Studio test path guarded) |
| Studio header and its "Product →" link | studio/ | KEPT, unchanged (I-027, N-9) |
| Player and Scout content | me, player, scout pages | KEPT: only the nav markup and the nav CSS changed; content is the same, beside a 220 px panel on desktop |
| Footer links on /me, /scout, /players/{id} still say "Clips"; profile and /me link text "Open in Clips", "Open the match in Clips", "Read it in Clips"; Studio "the Product" | me/index.html:95, scout/index.html:136, player/index.html:114; player.js:356, 389; me.js:491, 535; studio.js:703, 1060 | **NEEDS DECISION** (D1) |

## Home: landing (item 1, first bullet)

| what changed | where | verdict |
|---|---|---|
| h1 "Every touch, every replay, every player, found in seconds." (I-046) | index.html:28 | DECIDED: "the large REGISTA logo, the tagline …" |
| Lede (I-047) | removed | DECIDED: "No pitch copy" |
| Example chips, `ASKS`, `renderExamples()` (I-048) | removed; `chipName()` kept for the way-out button (app.js) | DECIDED: "no example buttons" |
| Six prompts type in and out; Tab fills the one showing; still for reduced motion; an empty Search runs the prompt showing | app.js PROMPTS and `startPrompts()` | DECIDED (the brief's six prompts, verbatim) |
| Switch "Data Search · Ask Microsoft Foundry" under the box | index.html:35-38 | DECIDED |
| Landing no longer shows the featured match's title, timeline, stage, recap, moments grid on first load (I-049, I-050, I-078, I-090, I-114) | those now live in the match view | KEPT (moved): the featured match still loads in the background and is one picker change away; the match view holds all of it |
| Fatal states also on the landing (#landingNote) | index.html:39; app.js `fatal()` | KEPT (I-042) |
| Engine hint (I-058) not shown on the landing | it lives in the panel only | **NEEDS DECISION** (D2) |
| Meta description still the old line | index.html:7 | **NEEDS DECISION** (D3) |
| Match and Player pickers visible on the landing and results (the sandbox header has none) | index.html:15-16 | KEPT; placement is **NEEDS DECISION** (D4) |

## Home: results across every match (item 1, second and third bullets)

| what changed | where | verdict |
|---|---|---|
| Compact search bar with the switch; same grid, cards, sort, tag chips, Show more | index.html:45-59, 116-128 | DECIDED: "a compact search bar at the top with the switch; the clip grid and cards exactly as today" |
| Conversation panel only with Ask Microsoft Foundry; with Data Search the reply text, "How Regista answered", fallback line and engine hint are not visible on the results (checked in the browser) | app.js:149 `layoutPanel()` | DECIDED: "with Ask Microsoft Foundry, the conversation panel on the right". The log is kept and shows in full once a card opens or the switch moves to Foundry. The way-out button and Retry are also shown under the empty text (app.js `render()`) |
| Search calls every match's own `/chat` (library + league), merged best first | app.js:526 `searchEvery()` | DECIDED: "call the existing per-match search for every match … and merge, best first". Cost is in docs/redesign/home.md "Cost" |
| Cosmos-only matches are left out of the search, the note line says so | app.js `searchList()`, `searchNote()` | KEPT (they could never answer questions, I-045); still reachable from the picker |
| A name in the question keeps only matches where it named someone, and only that player's moments | app.js:511 `namesIn()`, 594-606 | **NEEDS DECISION** (D5): page-side filtering that hides some per-match answers |
| "Labelled by Microsoft Foundry" badge on results read for library matches only | app.js:714 `loadSearchDetails()` | **NEEDS DECISION** (D6) |
| Cards do not name their match | app.js `render()` (cards as before plus `data-mid`) | **NEEDS DECISION** (D7): the brief says "cards exactly as today" |
| A reel asked for on the results opens the best match and plays only that match's part; Download reel and Export moments exist only in the match view (per-match endpoints) | app.js:747 `reelFromSearch()` | **NEEDS DECISION** (D8) |
| Switching Data Search / Ask Microsoft Foundry on the results only changes the next question and shows or hides the panel; the sandbox re-ran the search on switch (sandbox.js:182) | app.js `setEngine()` | KEPT (nothing lost); a sandbox divergence, noted for the reviewers |
| How it works, realism report: "Show this match's numbers" on the landing or results reads the featured match loaded in the background, which is not on screen | app.js:1441 `toggleReport()` uses `state.match` | **NEEDS DECISION** (D9) |

## Home: the match view (item 1, fourth bullet)

| what changed | where | verdict |
|---|---|---|
| `#matchSub` (manifest subtitle, I-051) removed from markup and script | index.html:64-69; app.js `showMatchLine()` | DECIDED: "the match's explainer line removed" (inventory N-2: I-051 is the explainer) |
| Vision note (I-053) and Scout profile link (I-052) | index.html:66-68 | KEPT, under the title. Results cards can carry "Cut from video" with only the badge's tooltip to explain it (the note is in the match view) |
| One log, in the right panel; reply bubbles tagged with where they searched | index.html:132-146 | DECIDED: "the whole conversation in the right panel only" |
| "How Regista answered" summary line with engine and step count; plain steps and "Details: step names and times" on demand | app.js `howAnswered()` | DECIDED: "'How Regista answered' one line per answer, steps and timings on demand" |
| Log no longer cleared on a new match or player (I-060); Foundry `chat.history` now runs across matches (reset only on "start over", app.js:584, 994) | app.js:790 `newConversation()` | Log kept: DECIDED ("the whole conversation"). History carried into a new match's Foundry context: **NEEDS DECISION** (D10) |
| Ask box placeholder 'Ask for a moment: "his nutmegs", "now the replays", "second half"' and label "Ask for a moment" become "Ask about this match" / "Ask a follow-up across every match" | index.html:137-138; app.js:154-155 | DECIDED by the sandbox's panel ("Ask a follow-up", sandbox.js:111). The follow-up guidance remains in the engine hint ("Follow-ups build on what you asked; 'start over' clears it.") |
| Engine switch labels Instant / Foundry become Data Search / Ask Microsoft Foundry; the three switches are one choice | index.html:35-38, 52-55, 139-142; app.js `setEngine()` | DECIDED ("Data Search · Ask Microsoft Foundry") |
| Engine hint now starts "Data Search:" / "Ask Microsoft Foundry:" and adds "Questions here search this match / every match." | app.js:426 | KEPT (reworded to the new labels) |
| Recap: `<section>` "Recap" becomes `<details>` "Match recap" with the Instant / Foundry switch inside; written when first opened, not on every load | index.html:95-110; app.js `resetRecap()`, `openRecap()` | DECIDED: "the recap folded into an expandable 'Match recap' that keeps its own Instant/Foundry switch inside". Side effect: the recap's clips (I-112) join the timeline only once it is opened |
| `?recap=1` opens the fold, writes it and jumps to it below the sticky header | app.js:224-229, 1246-1251 | KEPT (I-035, N-10) |
| Stage actions moved out of `.info` into one row spanning the stage; smaller buttons; wrap on phones | index.html:85-90; product.css:101-102, 197 | DECIDED: "the stage's actions in one row" (checked: four at one y at 1440 px) |
| `.card.on` yellow border and shadow removed; class still toggled and `aria-current="true"` added | product.css (rule gone); app.js:1141 `markPlaying()` | DECIDED: "no yellow outline on the playing card" |
| "Back to results" button | index.html:63 | KEPT (addition) |
| "start over" in the match view returns to the player's moments, not to a landing | app.js:993 `restartQuery()` | KEPT: same reset as before (the old landing it re-showed held only the decided-away chips) |
| Opening a result shows that player's moments under the stage, not the question's results | app.js:758 `openResult()` | KEPT (as the sandbox: the clicked moment plus its player's moments; Back to results returns the search) |
| Browser Back: views switch with `replaceState`, so Back leaves Home from the match view | app.js `syncUrl()` | **NEEDS DECISION** (D11) |
| Phones and up to 1100 px: the panel sits above the match view (`order: -1`); on a profile deep link at 375 px the empty panel is first and the stage starts at about 745 px | product.css:189-193 | The order is the sandbox's (sandbox.css:135); **NEEDS DECISION** (D12) |

## Unchanged and checked present (KEPT)

Timeline (I-078 to I-089, timeline.js not touched); stage, overlays, now line, reel labels (I-090 to I-097, I-102,
I-103); Play reel, Download reel, Export moments, Watch the full match with the long-match note and `#t=` (I-098 to
I-101); recap by-line, citations, recap reel and download (I-107 to I-111, I-113); sort and tag chips with focus kept
(I-115 to I-117); cards, previews, badges, empty states, Show more (I-118 to I-129); footer "Built on", synthetic line,
How it works, Studio link (I-130 to I-134); How it works dialog and report (I-135 to I-140); keyboard (I-141 to I-143);
responsive rules (I-144 to I-146); deep links `?match=&player=&clip=&t=&recap=1`, LINK_ID checks, link fallback
(I-030 to I-036); errors, offline text, net banner with Retry, fatal and loading texts (I-040 to I-045). Every
user-facing string from these items was found in the new files.

## Needs a decision (for Zaid)

- **D1. "Clips" wording on other pages.** Footers on /me, /scout, /players/{id} link "Clips"; profiles say "Open in
  Clips", "Read it in Clips"; Studio says "the Product". Keep (the brief keeps Player and Scout content exactly as it is)
  or rename to "Home" for consistency with the nav.
- **D2. Engine hint on the landing.** The explanation of Data Search vs Ask Microsoft Foundry (and "Foundry is not
  set up on this server") shows only in the panel, so not on the landing nor on Data Search results. Keep it
  panel-only (matches "no pitch copy") or add a one-line hint under the landing switch.
- **D3. Meta description** (index.html:7) still "Every touch, every replay, every player, found in seconds." Keep, or
  change to the new tagline.
- **D4. Match and Player pickers on the landing and results.** Kept in the header (the sandbox has none); changing
  either jumps to the match view. Keep there, or move them into the match view's title line.
- **D5. One name, one player across matches.** When a question names a player, Home drops matches where the name did
  not resolve and other players' moments (the note line says so). Without it, "Femi Toure" also returned Femi Rahman
  and Milan Toure. Keep this page-side filter, or show every match's own answer unfiltered until a server-side
  cross-match search exists (out of scope here).
- **D6. Foundry badge on league results.** Not computed for league matches (about 430 KB of clips each; all are
  rules-labelled today, so nothing is lost now). Accept, or read every match's clips at that cost.
- **D7. Cards on the results do not say which match they are from.** The brief says cards exactly as today. Keep,
  or add the match name to each card.
- **D8. Reels, downloads and export across matches.** The reel and CSV endpoints take one match: a reel asked for on
  the results plays only the best match's part in its match view, and Download reel / Export moments exist only in
  the match view. Accept, or add results-level actions later (needs API work, out of scope).
- **D9. Realism report on Home.** "Show this match's numbers" on the landing or results reports on the featured match
  loaded behind the landing, which is not on screen. Keep, hide the toggle outside the match view, or say which match.
- **D10. Foundry history across matches.** The match view no longer clears the conversation history on a new match or
  player, so a Foundry reply in one match gets the earlier turns from other matches as context. Keep (one
  conversation), or reset the history (not the log) when the match changes, as before.
- **D11. Browser Back.** Views use `replaceState` (a test pins no `pushState`), so Back from the match view leaves the
  page instead of returning to the results. Keep (Back to results button only), or push a history entry per view.
- **D12. Panel above the match view on narrow screens.** As the sandbox; on a phone a profile's deep link opens with
  an empty "Ask for a moment to start." panel above the title and the clip below the fold. Keep, or place the panel
  after the stage on phones (or collapse it while empty).
- **D13. Prompt promise.** "Find me shots from outside the box this season" is read as "any player · shot" (no
  distance filter on the server). The prompt is Zaid's verbatim; keep, or swap it for one the search answers exactly.
