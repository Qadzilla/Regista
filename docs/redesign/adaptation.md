# Adaptation map: every inventory item and where it lives now

Adaptation agent, branch `ux/app-redesign` at bb705b0 (`git diff main...HEAD -- src/regista/static tests`). One row per
inventory id (docs/redesign/inventory.md). No code was changed.

Paths as in the inventory: `index.html`, `app.js`, `product.css`, `timeline.js` are in `src/regista/static/product/`;
`regista.css`, `regista.js` are in `src/regista/static/shared/`. Line numbers are in the files at bb705b0.

**Status:** FOUND = present, with where it is now · CHANGED-BY-DECISION = changed or removed as the brief decided (the
decision is quoted) · UNCLEAR = present but changed in a way the brief does not decide, or depends on a reading of the
brief; needs a look · MISSING = not found.

**Checked:** B = clicked through in a browser (local server, `REGISTA_DOTENV=` empty, port 8073; 1440 x 900 and 375 x 812);
C = read in the code only (the state cannot be produced locally: no Cosmos DB match, no network failure, no empty server).

Views on `/`: **landing** (logo, tagline, search box, switch), **results** (compact bar, moments section, panel only with
Ask Microsoft Foundry), **match** (back link, match line, timeline, stage, folded recap, moments section, panel on the
right). The moments section (index.html:116-128) is one element that `showView()` (app.js:133-146) moves under the results
or under the match.

## Counts

| status | count |
|---|---|
| FOUND | 115 |
| CHANGED-BY-DECISION | 21 |
| UNCLEAR | 12 |
| MISSING | 0 |
| total | 148 |

UNCLEAR: I-028, I-029, I-045, I-049, I-055, I-060, I-077, I-098, I-126, I-140, I-145, I-148.

## The map

| id | status | where it lives now (file:line; where on screen) | checked | note |
|---|---|---|---|---|
| I-001 | FOUND | index.html:6-8, unchanged | B | Meta description still says "Every touch, every replay, every player, found in seconds." (old h1), not the new tagline; home.md Q6. |
| I-002 | FOUND | index.html:9-10, 210-212; same order; no inline script, handler or style attribute in index.html. regista.js:59 sets `--top-h` through CSSOM (`style.setProperty`), which the CSP allows | B | No CSP errors in the console on /, /me, /scout, /players/{id}. |
| I-003 | FOUND | regista.css:3-10, unchanged | B | |
| I-004 | FOUND | regista.css:12-18, unchanged | B | |
| I-005 | FOUND | regista.js:6-49, 69; new `trackHeader()` regista.js:54-67 (navigator) | B | |
| I-006 | FOUND | index.html:13-17; product.css:8-10. Header now holds brand + Match + Player pickers, no nav | B | Sticky at 1440 (measured 63 px); static at <= 760 px (product.css:209). |
| I-007 | FOUND | index.html:14; regista.css:19-20; same on /me, /scout, /players/{id} | B | |
| I-008 | CHANGED-BY-DECISION | index.html:20, left panel `nav.views` inside `.shell`; Home (current, yellow), Player profile, Scout | B | "the view links move to a left panel (current view in Regista yellow; a row of tabs on phones) ... Labels: Home (/), Player profile (/me), Scout (/scout)". Current link bg measured rgb(255,205,40). |
| I-009 | CHANGED-BY-DECISION | regista.css:22-49 (panel, sticky below header at `--top-h`; row of tabs at <= 720 px) | B | Same decision as I-008. Old pill rules gone. |
| I-010 | FOUND | index.html:15 (header, every Home view); app.js:222, 1476 (change opens the match view, loads, syncs URL) | B | From the landing, a change now opens the match view (was: same page). See I-049. |
| I-011 | FOUND | app.js:220-222, 276-281 | B | Picker order seen: Demo match first, then 3 library matches. |
| I-012 | FOUND | app.js:223, 246-266 | B | Optgroup "Regista League 2026/27", 30 options. |
| I-013 | FOUND | app.js:269-273 | C | |
| I-014 | FOUND | app.js:65-71 | B | |
| I-015 | FOUND | app.js:293-307 | C | |
| I-016 | FOUND | index.html:16; app.js:1477 (change opens the match view, then picks) | B | |
| I-017 | FOUND | app.js:337-350 | B | Seen: "Sami Castellanos · 9 · Northbridge FC · 11 moments"; groups "Players with moments" 19 / "No moments in this match" 17. |
| I-018 | FOUND | app.js:353-358, 360-375 ("Finding the moments…" app.js:363) | B | Picked a player with no moments: server answered, empty text shown. |
| I-019 | FOUND | app.js:366-370 | C | |
| I-020 | FOUND | product.css:11-13, 205 | B | |
| I-021 | CHANGED-BY-DECISION | scout/index.html:18 (left panel, Scout current) | B | Decision as I-008. Labels/order Home, Player profile, Scout; row of tabs at 375. |
| I-022 | CHANGED-BY-DECISION | scout/scout.css:10-13 (header kept), 151 (header static <= 600 px kept); `.views` override removed, shared rule used | B | Decision as I-008. Header static at 375 (measured). |
| I-023 | CHANGED-BY-DECISION | player/index.html:18, Scout current | B | "/players/{id} shows Scout as current" (verified on /players/pl_fai_09). |
| I-024 | CHANGED-BY-DECISION | player/player.css:9-11, 163 (header rules kept); `.views` override removed | B | Decision as I-008. Header static at 375. |
| I-025 | CHANGED-BY-DECISION | me/index.html:18, "Player profile" current | B | Decision as I-008. |
| I-026 | FOUND | me/me.css:12-14, unchanged (header still sticky at 375) | B | On phones the tab row under it is static and scrolls away. |
| I-027 | FOUND | studio/index.html, studio.css unchanged; no `.shell`/`nav.views` on /studio | B | Studio's "Product →" link unchanged (N-9). |
| I-028 | UNCLEAR | Titles unchanged: "Regista" (/), "Regista Scout", "Regista Player" (/me), profile title set by player.js (seen "Yusuf Tanaka · Regista Scout") | B | Kept exactly, but /me's tab title "Regista Player" no longer matches the nav label "Player profile", and / is now "Home". Needs a decision whether titles follow the labels. |
| I-029 | UNCLEAR | Unchanged: player.js:356, 389; me.js:491, 535; studio.js:703, 1060; plus footers me/index.html:95 "Clips · Scout · Regista Studio", scout/index.html:136 "Clips · Regista Studio", player/index.html:114 "Clips · Scout" | B | Kept exactly (brief: Player/Scout content unchanged), but "Clips" now names no view: the nav says Home. Inventory N-8; needs a decision. |
| I-030 | FOUND | app.js:165-172 | B | |
| I-031 | FOUND | app.js:173, 227 | B | `?match=syn_0294&clip=cl_t_home_09_000004` picked player t_home_09 and played the clip. |
| I-032 | FOUND | app.js:225-240; a failed link lands on the landing, URL cleared | B | `?match=nope_999&player=x`: landing, URL `/`, no error banner, featured match loaded behind it. Was: the featured match opened; now Home opens (decision makes / Home). |
| I-033 | FOUND | app.js:192-201 | B | `?match=rl_r01_ash_fai&t=600`: nearest moment 9:57-10:03 played, player switched, full-match link `#t=600`. |
| I-034 | FOUND | app.js:1181 | B | Linked clip playing (paused=false). |
| I-035 | FOUND | app.js:224, 229, 1216-1220, 1246-1251; opens the folded "Match recap" and scrolls below the sticky header | B | 1440: recap top at 71 px = header 63 + 8. |
| I-036 | FOUND | app.js:177-188 (replaceState only; plain `/` on landing and results; `?match&player&clip` in the match view) | B | |
| I-037 | FOUND | player/player.js unchanged; links open the match view | B | Profile links `/?match=…&player=…&clip=…` seen; opening one shows the match view. |
| I-038 | FOUND | me/me.js unchanged; `recap=1` opens the folded recap | B (recap=1), C (me.js) | |
| I-039 | FOUND | player/add-match.js:282 unchanged | C | |
| I-040 | FOUND | index.html:24 (top of main, every view); app.js:121-127 | C | |
| I-041 | FOUND | app.js:58-59 | C | |
| I-042 | FOUND | app.js:214-215, 237, 283-288, 306: moments section and, new, `#landingNote` (index.html:39) on the landing | C | |
| I-043 | FOUND | app.js:305 | C | |
| I-044 | FOUND | app.js:296, 363; new "Searching every match… n of N" app.js:545-549 | B (search), C | "Loading the match…" goes into the moments section, which is not on screen on the landing (the landing loads the featured match in the background). |
| I-045 | UNCLEAR | app.js:60, 156-157, 319, 427, 460, 1052, 1173, 1211, 1224; Cosmos-only matches left out of Home's search, said in `#searchNote` (app.js:489, 706) | C | Kept in the match view. Not testable locally (no Cosmos match). The hint "…Its moments are below." now sits in the right panel on desktop, beside the moments, not above them. "Examples disabled" went with the examples (decided). Cosmos matches are not searchable from Home at all: a consequence of search-every-match, not stated in the brief. |
| I-046 | CHANGED-BY-DECISION | index.html:28-29 (logo h1 with sr "Regista", tagline); product.css:19-21 | B | "the large REGISTA logo, the tagline 'Every moment. Every highlight. Every player. Found in seconds.'" |
| I-047 | CHANGED-BY-DECISION | removed (no `.lede` in markup or CSS) | B | "No pitch copy". |
| I-048 | CHANGED-BY-DECISION | removed (no #examples, ASKS, renderExamples); `chipName()` kept for the way-out button (app.js:801-810) | B | "no example buttons". Replaced by the six typing prompts (app.js:381-413). |
| I-049 | UNCLEAR | Landing shown at start (app.js:233) and after "start over" on the results (app.js:581-590) | B | Was also shown on every new match or player; now a new match or player opens the match view instead, and "start over" asked in the match view stays there (home.md Q4, Q5). Follows from Home replacing the per-match landing, but not stated in the brief. |
| I-050 | FOUND | index.html:65 (match view, under "Back to results"); app.js:330-333 | B | |
| I-051 | CHANGED-BY-DECISION | removed (#matchSub gone from index.html and app.js) | B | "the match's explainer line removed" (inventory N-2 reads this as I-051). |
| I-052 | FOUND | index.html:66 (match view, under the title); app.js:1001-1008 | B | "See Yusuf Tanaka's Scout profile" → /players/pl_fai_09. |
| I-053 | FOUND | index.html:67-68 (match view, under the title); app.js:332 | B | Vision match vis_0201: note shown, cards carry "Cut from video". N-2: kept, not removed. |
| I-054 | CHANGED-BY-DECISION | index.html:132-135, the conversation panel (right; above the content at <= 1100 px); "Ask for a moment to start." until the first message (app.js:437-441) | B | "with Ask Microsoft Foundry, the conversation panel on the right"; "the whole conversation in the right panel only". On the results with Data Search the panel (and so the log) is hidden; the reply's facts show in the heading, and error / way-out also show in the grid area (app.js:573-574, 1038-1043). |
| I-055 | UNCLEAR | Three boxes: landing #q (index.html:32), results #rq (index.html:49), panel #fq (index.html:138); all type=search, maxlength 300, autocomplete off, >= 16 px | B | Placeholder 'Ask for a moment: "his nutmegs", "now the replays", "second half"' is gone: landing shows the typing prompts (decided), #rq "Search every match", #fq "Ask about this match" / "Ask a follow-up across every match" (app.js:154). The hints about follow-ups were not decided away. |
| I-056 | CHANGED-BY-DECISION | index.html:35-38 (landing), 52-55 (results bar), 139-142 (panel); one choice kept in step (app.js:420-424); focus ring product.css:33 | B | Labels now Data Search / Ask Microsoft Foundry: "'Data Search · Ask Microsoft Foundry' under the box". |
| I-057 | FOUND | index.html:143 (#go, panel); plus #homeGo (index.html:33), #barGo (index.html:50); app.js:457-461 | B | |
| I-058 | CHANGED-BY-DECISION | index.html:145 (panel, under the box); app.js:426-435 | B | Wording "Instant:" → "Data Search:" / "Ask Microsoft Foundry:" follows the relabel; adds "Questions here search every match / this match." Not on the landing ("No pitch copy"). |
| I-059 | FOUND | app.js:813-841 (match view); Home: app.js:526-681 (each match's /chat, Instant) | B | |
| I-060 | UNCLEAR | Seed app.js:785-787, 790-796 | B | Seeded from the picked player as before. But a new match or player no longer clears the log or `chat.history` (old newConversation cleared both): the log stays in the panel ("the whole conversation" supports that), and the Foundry history now carries across matches. The history part is not decided. |
| I-061 | FOUND | app.js:537, 816; product.css:77 | B | |
| I-062 | FOUND | app.js:818 (match view); Home: app.js:538 "Searching every match…" / "…then asking Microsoft Foundry…" | B | |
| I-063 | FOUND | app.js:643, 826; product.css:78; each reply tagged with where it searched (app.js:455, product.css:62) | B | |
| I-064 | FOUND | app.js:867-873 | B | "Foundry is not set up on this server, so Regista's rules wrote this reply." seen (Foundry not set up locally). |
| I-065 | CHANGED-BY-DECISION | app.js:877-900: summary "How Regista answered · {who} · N steps" | B | "'How Regista answered' one line per answer, steps and timings on demand". Scroll into view on open kept (app.js:449-450). |
| I-066 | CHANGED-BY-DECISION | app.js:903-942, inside the fold; Home adds "Read every match (N matches)" / "Found N moments in K matches" | B | Same decision. Seen: "Read the match", "Understood: …", "Found 3 of 11 moments". |
| I-067 | CHANGED-BY-DECISION | app.js:892-896, inside the fold (summary also names who answered) | B | Same decision. |
| I-068 | CHANGED-BY-DECISION | app.js:885-898, one click further; Home adds "· N matches" per step and "N matches searched in X" | B | Same decision ("timings on demand"). |
| I-069 | FOUND | app.js:463-477 (both match view and Home); Home all-failed also in the grid (app.js:567-577) | C | |
| I-070 | FOUND | app.js:846-864 (match view), 649-665 (Home; also under the empty text, app.js:1038-1043) | B | Seen: "Show all 11 moments of Sami Castellanos". |
| I-071 | FOUND | app.js:828-829 (match view), 617-620 (Home) | B | |
| I-072 | FOUND | app.js:944-969 | C | |
| I-073 | FOUND | app.js:959 (match view), 668 (Home) | B | "4 moments · any player · nutmeg · replays only". |
| I-074 | FOUND | app.js:962-965 (match view), 671-674 (Home, "…in any match") | B | |
| I-075 | FOUND | app.js:968 (match view); Home: app.js:678, 747-754 (plays the best match's part in its match view) | B | "make a reel" on results → match view "Reel · clip 1 of 8". Reel is one match's (home.md Q7). |
| I-076 | FOUND | app.js:974-989 (match view), 725-743 (Home) | B | |
| I-077 | UNCLEAR | Home: app.js:581-590 (log kept, landing back); match view: app.js:993-996 (back to the player's moments, log kept) | B | Was: landing came back. In the match view it no longer does (home.md Q5). |
| I-078 | FOUND | index.html:71-73 (match view, under the match line); app.js:1111-1128 | B | |
| I-079 | FOUND | app.js:1116-1124 | B | |
| I-080 | FOUND | timeline.js unchanged | B | Lanes On the ball, Replay, Highlight, Closeup. |
| I-081 | FOUND | timeline.js unchanged | B | "1st half", "2nd half" on a league match. |
| I-082 | FOUND | timeline.js unchanged | B | Ticks 5:00 … KO, FT. |
| I-083 | FOUND | timeline.js unchanged | B | |
| I-084 | FOUND | timeline.js unchanged | B | 2 goals on rl_r01_ash_fai. |
| I-085 | FOUND | timeline.js unchanged | C | |
| I-086 | FOUND | timeline.js unchanged | B | ArrowRight + Enter played a clip. |
| I-087 | FOUND | app.js:1123 | B | |
| I-088 | FOUND | timeline.js unchanged | B | "Match timeline, 3:22: 11 clips, 11 in the current results. …" |
| I-089 | FOUND | timeline.js unchanged | C | |
| I-090 | FOUND | index.html:75-80 (match view) | B | |
| I-091 | FOUND | app.js:1177-1181 | B | |
| I-092 | FOUND | index.html:78; app.js:1158-1175, 1190-1195 | B (empty), C | |
| I-093 | FOUND | index.html:79; app.js:1185-1196 | C | |
| I-094 | FOUND | index.html:82; app.js:1165, 1375 | B | "Replay · 0:36–0:44", "Reel · clip 1 of 3", "Recap reel · clip 1 of 6". |
| I-095 | FOUND | index.html:83; app.js:1161, 1166 | B | |
| I-096 | FOUND | index.html:84; app.js:1167 | B | |
| I-097 | FOUND | index.html:85; app.js:81-96, 1168 | B | |
| I-098 | UNCLEAR | index.html:88 in `.stage > .actions` (index.html:87-92), one row under the clip and its details; product.css:101-102; app.js:1328-1332, 1368-1371, 1484 | B | Decided "the stage's actions in one row": at 1440 all four share one row (same top, 575 px). At 375 they wrap onto three rows (product.css:197): one row is not kept on phones. Needs a yes/no. |
| I-099 | FOUND | index.html:89 (same row); app.js:1333-1334, 1343-1365, 1486 | B (href), C (download) | Download not clicked (would save a file). |
| I-100 | FOUND | index.html:90 (same row); app.js:1335-1338 | B | href `/moments.csv?player=t_home_09`. |
| I-101 | FOUND | index.html:91 (same row); app.js:199, 318-322 | B | League match: "(the first view takes a few minutes)". |
| I-102 | FOUND | app.js:1367-1377, 1485 | C | |
| I-103 | FOUND | app.js:1131-1146 | B | |
| I-104 | FOUND | product.css:112-115 | B | |
| I-105 | CHANGED-BY-DECISION | index.html:95-110, `<details>` "Match recap" (match view, under the stage); app.js:1203-1252, 1488 (written when first opened) | B | "the recap folded into an expandable 'Match recap'". Was written on every load; now on open. |
| I-106 | CHANGED-BY-DECISION | index.html:99-102 (inside the fold); app.js:1207-1213, 1487 | B | "keeps its own Instant/Foundry switch inside". |
| I-107 | FOUND | index.html:98; app.js:1230 | B | |
| I-108 | FOUND | app.js:1231, 1239 | B (wait text), C | |
| I-109 | FOUND | index.html:104; app.js:1254-1267, 1304-1312 | B | 6 cited sentences; a click played the moment and marked the sentence. |
| I-110 | FOUND | index.html:105; app.js:1270-1283 | B | |
| I-111 | FOUND | index.html:106-109; app.js:1285-1292, 1314-1321 | B | "Play recap reel (6)". |
| I-112 | FOUND | app.js:1295-1302 | C | |
| I-113 | FOUND | app.js:1209, 1226, 1238, 1243 | C | |
| I-114 | FOUND | index.html:118 (moments section, under the results or the match); app.js:1016-1018 | B | |
| I-115 | FOUND | index.html:119-122; app.js:112-114, 1381-1384, 1478 | B | Works on the merged set too. |
| I-116 | FOUND | index.html:124; app.js:1076-1092 | B | Chip filtered 38 → 3, focus kept on the chip. |
| I-117 | FOUND | app.js:74-75 | C | |
| I-118 | FOUND | index.html:125; product.css:138 | B | |
| I-119 | FOUND | app.js:1050, 1062-1064 (results: opens the match view; match view: plays) | B | Adds an invisible `data-mid`. |
| I-120 | FOUND | app.js:1051, 1065-1070, 1103-1108 | B | |
| I-121 | FOUND | app.js:1052 | C | |
| I-122 | FOUND | app.js:1054; product.css:147-148 | B | |
| I-123 | FOUND | app.js:1055 | B | |
| I-124 | FOUND | app.js:1056, 1061 | B | "How worth watching, from 0 to 1: 0.70". |
| I-125 | FOUND | app.js:1057 | B | |
| I-126 | UNCLEAR | app.js:1094-1099; on Home results from `loadSearchDetails()` app.js:714-721 | B | Both badges seen (Foundry on syn_0141; vision on vis_0201). On Home's results the Foundry badge is read only for library matches; a Foundry-labelled league clip would show no badge there (home.md Q3). |
| I-127 | CHANGED-BY-DECISION | No `.card.on` style; playing card gets `aria-current="true"` (app.js:1141-1146) | B | "no yellow outline on the playing card". Measured border rgb(38,44,58), no shadow. |
| I-128 | FOUND | index.html:126; app.js:1019-1020 | B | |
| I-129 | FOUND | index.html:127; app.js:1044-1046, 1479-1483 (results: "more" of the matches that have more) | B | Results: "Show more (9 more)" → 39, hidden. |
| I-130 | FOUND | index.html:151 (below every view); app.js:1392-1395 | B | |
| I-131 | FOUND | index.html:152 | B | |
| I-132 | FOUND | index.html:153; app.js:1492 | B | |
| I-133 | FOUND | index.html:153 | B | |
| I-134 | FOUND | product.css:162-163 | B | |
| I-135 | FOUND | index.html:158-162; app.js:1492-1495 | B | Close returns focus to "How it works". |
| I-136 | FOUND | index.html:164-179 | B | |
| I-137 | FOUND | index.html:181-196 | B | |
| I-138 | FOUND | index.html:198-199; app.js:1386-1406 | B | |
| I-139 | FOUND | index.html:201-204 | B | |
| I-140 | UNCLEAR | index.html:205-207; app.js:1410-1456; reset on match change app.js:323 | B | Works in the match view. On the landing and the results, "Show this match's numbers…" shows the report of the match loaded in the background (featured, or the last one opened), while no match is on screen. |
| I-141 | FOUND | product.css:3-4 | B | |
| I-142 | FOUND | product.css:33, 69, 72 (all four switches) | C | |
| I-143 | FOUND | app.js:838 (#fq after a match-view reply), 576/679 (#rq or #fq after a search), 1090 (chip), 1495 (dialog); new Tab fills the prompt (app.js:394-396) | B | Tab filled "Find me shots from outside the box this season". |
| I-144 | FOUND | product.css:5-6, 15 | B | `main` max-width 1200 → 1320 px (with the left panel). No sideways scroll at 375 on landing, results, match view (scrollWidth 375). |
| I-145 | UNCLEAR | product.css:189-193 (<= 1100 px: panel above the content, not sticky), 195-212 (<= 760 px) | B | At 375 with Ask Microsoft Foundry the conversation panel comes before the compact search bar (panel top 213 px, grid 1015 px), so the bar is not "at the top" of the results on phones; in the match view the panel sits above the match title and stage (home.md Q10). |
| I-146 | FOUND | timeline.js unchanged | B | "Ball, Replay, Highl., Close" at 375. |
| I-147 | FOUND | app.js:19-33 (match view); Home keeps its own set `search` (app.js:38-47) | C | |
| I-148 | UNCLEAR | GET /search and /ask still not called; Home calls each match's POST /chat (Instant) | C | The brief says "call the existing per-match search for every match"; GET /api/matches/{id}/search exists and is unused. Whether /chat counts as "the existing per-match search" needs a yes/no (inventory N-3). |

## Seen in the browser, beyond single items

- Desktop 1440 x 900: landing (logo, tagline, typing prompts, switch, footer), Data Search "Find me all the nutmegs" (38
  moments, 15 matches, panel hidden), switch to Ask Microsoft Foundry (panel on the right with the whole log), "now the
  replays" (4), a card into the match view (title, Scout link where league, timeline, stage, actions in one row, folded
  recap, moments), questions, way-out, reels, recap and citations, How it works and the realism report, pickers, deep
  links (`clip=`, `t=`, `recap=1`, a bad id), /me, /scout, /players/pl_fai_09, /studio.
- 375 x 812: landing, results with the panel, match view, /me, /scout, /players/pl_fai_09: nav as a row of tabs with the
  current view in yellow, no sideways scroll on any of them.
- Console: no errors from the pages (only the 404s of the deliberately bad link, and one CSP frame error from an iframe
  probe of mine).
- Not checked in a browser: Cosmos DB matches (I-045, I-121), network failures (I-040 to I-043, I-069 Retry), the reel
  download (I-099), an empty server (I-042).
