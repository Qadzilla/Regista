# Clips page and shared navigation: inventory before the redesign

Taken on branch `ux/app-redesign` at commit 1ebceaa, before any code changed. This is the checklist for the
builders, the adaptation map, the safeguard and the reviewers: every item must end up somewhere in the new layout,
or be one of the removals Zaid decided, or be flagged.

Path conventions: `index.html`, `app.js`, `timeline.js`, `product.css` are in `src/regista/static/product/`;
`regista.css`, `regista.js` are in `src/regista/static/shared/`; other static files are named from
`src/regista/static/`. Python files are named from `src/regista/`. Endpoints are relative to the app root; `{id}` is a
match id. "Decided" marks the items Zaid's brief changes or removes; everything else must be kept.

## The table

| id | area | what | file:line | endpoint |
|---|---|---|---|---|
| I-001 | Page shell | Page title "Regista"; meta description "Every touch, every replay, every player, found in seconds."; favicon | index.html:6-8 | GET / (api.py:574); GET /static/product/favicon.svg |
| I-002 | Page shell | Load order: shared/regista.css, product.css, shared/regista.js, timeline.js (defer), app.js (defer). No inline scripts, handlers or style attributes (CSP header) | index.html:9-10, 166-168; api.py:118 | GET /static/... |
| I-003 | Shared tokens | Colour tokens --bg, --panel, --line, --text, --muted, --accent (#ffcd28, Regista yellow), --replay, --ok, --warn, --bad, --highlight, --closeup; --radius, --gap; base font; `[hidden]` always wins over layout | regista.css:3-11 | none |
| I-004 | Shared tokens | Base elements: links in accent, select/input/textarea, button (yellow), button.alt (outline), button:disabled, .muted, .panel | regista.css:12-18 | none |
| I-005 | Shared JS | window.Regista: esc() (all innerHTML escaping), reasonLabel/tagLabel (plain-word labels for reasons and tags), Studio key in sessionStorage (not used by Clips), api() JSON helper, ApiError, authedObjectUrl, fmtTime (m:ss) | regista.js:6-51 | none |
| I-006 | Header | Header bar `header.top`: panel background, bottom border, sticky at the top (z-index 5), wraps | index.html:13; product.css:8-10 | none |
| I-007 | Header / nav | Brand wordmark "REGI" + "STA" in accent | index.html:14; regista.css:19-20 | none |
| I-008 | Nav (Clips page) | Views switch `<nav class="views" aria-label="Views">`: Clips (/) with aria-current="page", Scout (/scout), Player (/me). Decided: becomes left panel, labels Home / Player profile / Scout | index.html:15 | GET /, /scout (season_api.py:76), /me (player_api.py:276) |
| I-009 | Nav (shared style) | Views switch style: pill group; current link on --line background (used as is by the Clips page and /me) | regista.css:22-27 | none |
| I-010 | Match picker | "Match" label + select#match; change loads the match then syncs the URL | index.html:16; app.js:155-156, 999 | GET /api/matches (api.py:592) |
| I-011 | Match picker | Featured match first (server `featured` flag, else the match with video and the most clips), then the others as listed | app.js:154-156, 200-205 | GET /api/matches |
| I-012 | Match picker | League optgroup (label from league + season, default "Regista League 2026/27"); options = title or "Round N: Home v Away"; loaded after first paint, not awaited; silent when there is no league | app.js:157, 171-190 | GET /api/season (season_api.py:87) |
| I-013 | Match picker | A linked match not yet listed gets its own option (rl_ ids go into the league group) | app.js:193-197 | none |
| I-014 | Match picker | Match names: title, else "Home 2–1 Away", else "A match"; "(from Cosmos DB)" suffix for Cosmos matches; never the id | app.js:41-47 | none |
| I-015 | Match picker | Disabled while a match loads; on failure goes back to the match still shown (page never mixes two matches) | app.js:217-231 | GET /api/matches/{id}, GET /api/matches/{id}/clips |
| I-016 | Player picker | "Player" label + select#player; change picks the player | index.html:17; app.js:1000 | none |
| I-017 | Player picker | Option text "Name · kit · team · N moments"; optgroups "Players with moments" (most first) and "No moments in this match"; default = linked player, else most moments, else first | app.js:264-277 | moment_counts from GET /api/matches/{id} (api.py:627) |
| I-018 | Player picker | Any player can be picked: the server derives moments for a player with none cut yet; "Finding the moments…" while loading | app.js:280-302, 290 | GET /api/matches/{id}/clips?player={pid} (api.py:696) |
| I-019 | Player picker | A failed switch reverts the picker and shows the error banner with Retry | app.js:293-297 | as I-018 |
| I-020 | Header layout | Picker label style (small uppercase); picks flex 1 1 260px, max 480px | product.css:11-13 | none |
| I-021 | Nav (Scout /scout) | Header: brand + views nav (Clips /, Scout / current, Player /me), multi-line markup | scout/index.html:13-20 | GET /scout (season_api.py:76) |
| I-022 | Nav (Scout /scout) | Own header and nav styles: sticky .top (no wrap); .views override with current link on accent yellow, #111 text; header not sticky at ≤600 px | scout/scout.css:10-17, 154-155 | none |
| I-023 | Nav (profile /players/{id}) | Header: brand + views nav (Clips, Scout current, Player). Decided: Scout shows as current | player/index.html:13-16 | GET /players/{gid} (season_api.py:81) |
| I-024 | Nav (profile /players/{id}) | Own header and nav styles: sticky wrapping .top; .views override (6 px radius, current on --line); header not sticky at ≤760 px | player/player.css:9-15, 166-167 | none |
| I-025 | Nav (Player /me) | Header: brand + views nav (Clips, Scout, Player current). Decided: label becomes "Player profile" | me/index.html:13-16 | GET /me (player_api.py:276) |
| I-026 | Nav (Player /me) | Own header style: sticky wrapping .top; uses the shared .views style; no phone rule for the header (stays sticky at 375 px) | me/me.css:12-14 | none |
| I-027 | Nav (Studio /studio) | Studio header "REGISTA STUDIO", "the control room", link "Product →" to /, role badge. Not part of the views nav today; the brief names only Home, Player profile, Scout | studio/index.html:11-16; studio/studio.css:8-9 | GET /studio |
| I-028 | Nav (page titles) | Tab titles: "Regista" (/), "Regista Scout" (/scout), "Player profile · Regista Scout" (/players/{id}), "Regista Player" (/me) | index.html:6; scout/index.html:6; player/index.html:6; me/index.html:6 | none |
| I-029 | Cross-page wording | Other pages name the Clips view in link text: "Open in Clips" (profile), "Open the match in Clips", "Read it in Clips" (/me), "see it in the Product", "the Product" (Studio) | player/player.js:356, 389; me/me.js:491, 535; studio/studio.js:703, 1060 | none |
| I-030 | Deep links | readLink(): ?match=, ?player=, ?clip=, ?t= (finite, ≥ 0), ?recap=1; ids checked by LINK_ID regex and '..' rejected | app.js:105-112 | none |
| I-031 | Deep links | clip= alone selects its player (clip ids are cl_{player}_{6 digits}) | app.js:113, 159 | none |
| I-032 | Deep links | A linked match loads quietly; if it fails, the featured match opens and the bad link is cleared from the address bar | app.js:159-165, 226 | GET /api/matches/{id}, /clips |
| I-033 | Deep links | openLinked(): clip= selects and plays it; t= picks the nearest moment (switching player if needed) and sets the full-match link to #t= | app.js:128-137 | GET /api/matches/{id}/video.mp4#t= |
| I-034 | Deep links | A linked clip autoplays; if the browser refuses, it retries muted | app.js:738 | none |
| I-035 | Deep links | recap=1 (the profiles' "Recap" link): once the recap is written the page jumps to it, below the sticky header | app.js:158, 759, 784-789 | none |
| I-036 | URL sync | syncUrl(): replaceState (never pushState) with match, player and the picked clip; called after link open, player pick, reply naming a player, select, match change | app.js:117-124, 161, 301, 537, 701, 999 | none |
| I-037 | Deep-link producers | Profile page builds /?match&player&clip, /?match&t, /?match&player, &recap=1 links | player/player.js:52-56, 142-143, 262, 356, 384 | none |
| I-038 | Deep-link producers | /me builds /?match&player&clip links and uses links.clip_view (+ &recap=1); the server writes clip_view as /?match=&player= | me/me.js:483-535; player_api.py:261 | GET /api/me... (server side) |
| I-039 | Deep-link producers | Add-match flow links to c.links.match ("Watch the match") | player/add-match.js:282 | none |
| I-040 | Errors | Network error banner #netError (role="alert"), text + Retry button; hidden on success | index.html:21; app.js:93-99; product.css:162-164 | retries the failed call |
| I-041 | Errors | Offline text "Can't reach Regista right now. Check your connection and try again." (fetch failed, not an HTTP error) | app.js:35-37 | none |
| I-042 | Errors | Fatal states in the results area, stage hidden: "Regista could not list its matches: …", "There are no matches on this server yet.", "This match could not be loaded: …" | app.js:147-148, 152, 164, 207-211, 229 | GET /api/matches, /api/matches/{id} |
| I-043 | Errors | Switching to a match that fails: "That match could not be loaded: …" with Retry | app.js:228 | GET /api/matches/{id} |
| I-044 | Loading | "Loading the match…" on first load; "Finding the moments…" on player switch | app.js:219, 290 | none |
| I-045 | Read-only (Cosmos) | Match read from Cosmos DB without its event stream: ask input and button disabled; hint "This match is read from Cosmos DB without its event stream, so it cannot answer questions here. Its moments are below."; full match link hidden; examples disabled; recap hidden; cards and stage say "Read from Cosmos DB. The labels and timings are stored there; this server does not hold the match's video." | app.js:242, 247-250, 281, 367-368, 374, 621, 730, 764 | none |
| I-046 | Landing | h1 "Every touch, every replay, every player, found in seconds." Decided: replaced by the large logo and the tagline "Every moment. Every highlight. Every player. Found in seconds." | index.html:23-24; product.css:17-18 | none |
| I-047 | Landing | Lede "Regista watched this match and cut every moment each player had the ball, plus every replay and highlight they appear in. Ask for any moment." Decided: removed (no pitch copy) | index.html:25-26; product.css:155 | none |
| I-048 | Landing | Example question chips (#examples, role="group" "Try a question"): up to three, built from the picked player's own tags (ASKS table, chipName() disambiguation); a click fills the box and sends; disabled for Cosmos. Decided: removed (no example buttons) | index.html:27; app.js:329-369; product.css:19-22 | POST /api/matches/{id}/chat on click |
| I-049 | Landing | Landing shown at start, on a new match or player, and after "start over"; hidden on send | app.js:317, 322-325, 398, 576 | none |
| I-050 | Match line | Match title h2#matchTitle (match name rules I-014) | index.html:31; app.js:254-255 | GET /api/matches, /api/matches/{id} |
| I-051 | Match line | Match subtitle #matchSub from the manifest (e.g. "Three minutes from Regista's match generator, packed on purpose: …"; league: "… round N: thirty generated minutes, every starter's moments cut and labelled."), hidden when none. Probably "the match's explainer line" the brief removes: see note N-2 | index.html:32; app.js:256-258; season/build.py:83 | GET /api/matches, /api/matches/{id} |
| I-052 | Match line | Scout profile link "See {name}'s Scout profile" → /players/{global id}, only for league players (pl_ id), set as text | index.html:33; app.js:583-590; product.css:159-160 | GET /players/{gid} |
| I-053 | Match line / badge | Vision note: "Cut from video" badge + "on a moment means the vision layer found it in the pictures: who had the ball, what happened and who is in each replay."; shown only for origin = vision | index.html:34-35; app.js:259; product.css:158, 161 | origin from GET /api/matches/{id} |
| I-054 | Conversation | Conversation log #log (aria-live="polite"), hidden until the first message; max 360 px tall, scrolls, auto-scrolls to the newest | index.html:39; app.js:383-393; product.css:35 | none |
| I-055 | Ask box | Form #askForm: hidden label "Ask for a moment", input#q type=search, maxlength 300, autocomplete off, placeholder 'Ask for a moment: "his nutmegs", "now the replays", "second half"', 16 px (no phone zoom); Enter submits | index.html:40-42; app.js:997; product.css:25-26 | POST /api/matches/{id}/chat |
| I-056 | Ask box | Engine switch, radiogroup "Who answers": Instant (rules, default) / Foundry; keyboard focus ring on the selected segment | index.html:43-46; product.css:27-32 | engine field of /chat |
| I-057 | Ask box | Ask button #go; disabled while a reply is pending and for Cosmos matches | index.html:47; app.js:397, 428 | none |
| I-058 | Ask box | Engine hint #engineHint: Instant text ("…with no AI model. Follow-ups build on what you asked; "start over" clears it."), Foundry text ("…a Microsoft Foundry model writes the reply and may call its tools. Takes a few seconds."), Foundry-not-set-up text; updates on engine change and when health arrives | index.html:49; app.js:373-381, 928, 998 | GET /api/health |
| I-059 | Conversation | send(): POST {message, state, history, engine}; the server keeps nothing, the page sends the state back; input cleared; focus returns to the input | app.js:395-432 | POST /api/matches/{id}/chat (api.py:1196) |
| I-060 | Conversation | Conversation seeded from the picked player (so "his" works); reset on new match or player (log cleared) | app.js:26, 308-320 | none |
| I-061 | Conversation | Your message bubble (.msg.me, right) | app.js:399; product.css:36-37 | none |
| I-062 | Conversation | Waiting line: "Searching…" or "Searching, then asking Microsoft Foundry to write the reply…" | app.js:401; product.css:40 | none |
| I-063 | Conversation | Reply bubble (.msg.bot, yellow left rule) with the reply text | app.js:409; product.css:38 | none |
| I-064 | Conversation | Fallback line when Foundry was asked but rules answered: "Foundry is not set up on this server / Foundry took too long / Foundry could not answer this time, so Regista's rules wrote this reply." | app.js:458-464; product.css:166 | answered_by from /chat |
| I-065 | How Regista answered | Collapsible "How Regista answered" under each reply; scrolls into view when opened | app.js:390-391, 482 | none |
| I-066 | How Regista answered | Plain steps: "Read the match", "Understood: …", "Found N of M moments", "Checked what else the same player has", "Cleared the question", "Handed the question to the Foundry Librarian agent", "Microsoft Foundry (model) chose what to look up / wrote the reply", tool steps ("Searched this match's moments", "Searched the clip library with Azure AI Search", "Read the library in Azure Cosmos DB", "Listed the matches", "… through the Azure MCP Server / through Regista's MCP server") | app.js:491-523 | trace, tools_used from /chat |
| I-067 | How Regista answered | "Answered by Regista's own rules, with no AI model" or "Answered by Microsoft Foundry (model)", plus "(Foundry was asked for)" | app.js:481, 484 | answered_by |
| I-068 | How Regista answered | Nested "Details: step names and times": each step's kind, exact name, server (Regista MCP server / Azure MCP Server) and time (ms / s); or tool chips when there is no trace; "Engine X · answered by Y" | app.js:470-480, 485-486; product.css:44-56, 176-182 | trace from /chat |
| I-069 | Conversation errors | Error reply (.msg.bot.err): offline text, 429 detail (rate limit), 404 "This match is not on this server any more. Pick another match.", else "Regista could not answer: …"; Retry button for offline and 5xx | app.js:416-426; product.css:39, 165 | POST /chat |
| I-070 | Conversation | Way-out button on an empty reply: the server's suggestion (label + message + cleared state), else "Show all of {name}'s moments" (sends "start over", then the name); placed above the trace | app.js:437-455; product.css:165 | POST /chat |
| I-071 | Conversation | Reply sets the sort: match order (state.order "time" or wording) or best first | app.js:403, 411-412 | state.order from /chat |
| I-072 | Conversation | applyReply(): results replace the grid ("more" appends new ones); tag filter cleared; reel ids kept; a reply naming one player switches the player picker, Scout link, URL and loads their clips | app.js:525-539 | GET /clips?player= |
| I-073 | Results heading | After a reply: "N moments · {understood}" | app.js:540 | none |
| I-074 | Empty state | After a reply with nothing: "Nothing for {understood}. Filters from earlier questions still apply: use the button in the reply, or say "start over"." or "Nothing matched that question. Try a player's surname, a kit number, or an action like "nutmeg" or "shot"." | app.js:543-546 | none |
| I-075 | Reels | A reply that is a reel, or a message saying reel / montage / compilation, plays the reel straight away | app.js:547-549 | none |
| I-076 | Conversation | "In match order": the page fetches the remaining pages itself (POST /chat "more", Instant engine, up to 10 pages) without adding lines to the log | app.js:415, 555-570 | POST /api/matches/{id}/chat |
| I-077 | Conversation | "Start over" (reset intent): the log stays, the query and results reset, the landing comes back | app.js:526, 574-578 | none |
| I-078 | Timeline | Section "The match, kick-off to full time" (#timelineWrap, #timeline); hidden when there is no data or drawing fails | index.html:52-54; app.js:677-694; product.css:58 | none |
| I-079 | Timeline | Drawn from the match duration, periods, every clip the page knows, key moments, the current results (highlight) and the selected clip | app.js:682-690 | GET /api/matches/{id} (duration_s, periods, key_moments), /clips |
| I-080 | Timeline | Lanes per clip kind, fixed order: On the ball (yellow), Replay (red), Highlight (blue), Closeup (purple), Other; legend dot + name per lane; short names under 480 px | timeline.js:24-31, 67-73, 112-116; product.css:207-211 | none |
| I-081 | Timeline | Periods shaded, labelled "1st half", "2nd half", "Period N" when wide enough | timeline.js:98-102; product.css:201 | none |
| I-082 | Timeline | Time axis: grid lines and tick labels (30 s to 30 min steps), "KO" and "FT" | timeline.js:48-52, 104-110 | none |
| I-083 | Timeline | Clip markers: clips outside the results dimmed and drawn underneath; hover un-dims; selected clip ringed | timeline.js:118-137; product.css:212-219 | none |
| I-084 | Timeline | Goals: dashed line through the lanes and a ball on top with a tooltip (label, time); goal labels in the strip's aria-description | timeline.js:139-149; product.css:205-206 | key_moments |
| I-085 | Timeline | Tooltip under the strip on hover or focus: clip title, time range and kind; kept inside the strip | timeline.js:151-171; product.css:220-224 | none |
| I-086 | Timeline | Keyboard: one tab stop; arrows, Home, End move between clips in match order; Enter or Space plays; Escape hides the tip; focus kept across redraws | timeline.js:173-212 | none |
| I-087 | Timeline | Click (or Enter) on a marker plays that clip on the stage | timeline.js:189-195; app.js:689 | none |
| I-088 | Timeline | Accessible summary "Match timeline, m:ss: N clips, M in the current results. Arrow keys move between clips, Enter plays one."; each marker labelled with title, kind, times, "in the results" | timeline.js:89-90, 128-130 | none |
| I-089 | Timeline | Redraws itself when its width changes (ResizeObserver) | timeline.js:215-228 | none |
| I-090 | Stage | Stage section "Now playing" (#stage): video with controls, playsinline, 16:9 black screen | index.html:56-58; product.css:60-62 | none |
| I-091 | Stage | Clip video = the clip's video_url, rendered on first request; preload auto when playing, else metadata | app.js:733-738 | GET /api/matches/{id}/clips/{clip_id}.mp4 (api.py:760) |
| I-092 | Stage | No-video overlay: "No moments to play here yet.", the Cosmos text, "This clip could not be loaded. Try again in a moment." | index.html:59; app.js:716-717, 727-731, 747-752 | none |
| I-093 | Stage | Loading overlay "Preparing this clip. The first view renders it, which takes a few seconds." while the video loads or waits | index.html:60; app.js:742-753; product.css:63-64 | none |
| I-094 | Stage | "Now" line (yellow uppercase): "Kind · m:ss–m:ss", or during a reel "Reel · clip i of n" / "Recap reel · clip i of n" | index.html:63; app.js:722, 913; product.css:67 | none |
| I-095 | Stage | Title (default "Pick a moment"; "Nothing to play yet" when empty) | index.html:64; app.js:718, 723 | none |
| I-096 | Stage | Tags of the playing clip (football tags only) | index.html:65; app.js:724 | none |
| I-097 | Stage | Why line: the label's explanation; for Foundry labels its summary; "Scored …" explanations dropped | index.html:66; app.js:56-70, 725 | label from /clips or /chat |
| I-098 | Stage actions | Play reel button: "Play reel (n)" when more than one; disabled when nothing to play; plays the last reel reply or the visible results in order, max 12, then scrolls to the stage | index.html:68; app.js:864-870, 906-909, 1003 | none |
| I-099 | Stage actions | Download reel link: fetched by the page with "Preparing reel…", saved under the server's filename; errors "Can't reach Regista. Try again." / "The reel could not be made. Try again." for 3 s; aria-disabled when empty | index.html:69; app.js:866-872, 881-903, 1005 | GET /api/matches/{id}/reel.mp4?clips=… (api.py:818) |
| I-100 | Stage actions | Export moments (CSV download): the visible clips after a question or a tag filter, else all of the player's moments; aria-disabled when empty | index.html:70; app.js:873-876 | GET /api/matches/{id}/moments.csv?clips=… or ?player= (api.py:847) |
| I-101 | Stage actions | "Watch the full match" (new tab); "(the first view takes a few minutes)" for matches over 10 minutes; hidden for Cosmos; starts at t= from a link | index.html:71; app.js:135, 241-245 | GET /api/matches/{id}/video.mp4 (api.py:767) |
| I-102 | Stage | Reel playback: next clip when one ends; any manual pick stops the reel | app.js:905-915, 1004, 699 | none |
| I-103 | Stage | Picking a moment selects it, plays it, syncs the URL, marks its card and scrolls the stage into view | app.js:697-704 | none |
| I-104 | Stage | Disabled link style (aria-disabled), .btn / .btn.alt / .btn.ghost | product.css:69-73 | none |
| I-105 | Recap | Recap panel #recap, heading "Recap"; hidden for Cosmos matches or with no player. Decided: folds into an expandable "Match recap" in the match view | index.html:76-78; app.js:762-768; product.css:75-77 | none |
| I-106 | Recap | Recap engine switch, radiogroup "Who writes the recap": Instant / Foundry; back to Instant on every new match or player; a change rewrites the recap. Decided: stays inside the folded recap | index.html:79-82; app.js:313, 760, 765, 1006 | engine= of /recap |
| I-107 | Recap | "This match, told from {name}'s side." | index.html:84; app.js:769 | none |
| I-108 | Recap | Waiting text "Writing the recap…" / "Asking Microsoft Foundry to write the recap. This can take half a minute…"; error "The recap could not be written: …" or offline text | app.js:770, 776-779 | GET /api/matches/{id}/recap?player=&engine= (api.py:1281) |
| I-109 | Recap | Headline and paragraphs; each sentence that cites a moment is a link (?match&player&clip, opens in a new tab too) that plays it on the stage and highlights itself; aria-live | index.html:85; app.js:792-805, 842-850; product.css:78-82 | GET /recap |
| I-110 | Recap | By-line: Instant ("written by Regista's own rules … Pick a sentence to play its moment."), Foundry ("Written by Microsoft Foundry (model) from the match's facts[, written earlier and kept]. Regista checked every sentence: N kept, M left out …"), or the fallback reason (not set up / busy / took too long / could not write it) | index.html:86; app.js:808-821; product.css:84 | answered_by, checked, cached from /recap |
| I-111 | Recap | "Play recap reel (n)" and "Download recap reel"; disabled when the recap cites no playable clip | index.html:87-90; app.js:823-830, 852-859, 1007 | GET /api/matches/{id}/reel.mp4?clips=… |
| I-112 | Recap | The recap's clips (another player's goal, say) join the page's clips, so the stage and the timeline show them | app.js:833-840 | none |
| I-113 | Recap | Only the latest request draws (a match or player change meanwhile wins) | app.js:766, 777, 781 | none |
| I-114 | Results | Results heading h2#resultsHead: "Moments", or "N moments · {name}, {team}" for the player's moments | index.html:95; app.js:598-600 | none |
| I-115 | Sort | Sort group "Sort": Best first / Match order (aria-pressed); best first = watchability then time | index.html:96-99; app.js:84-86, 919-922, 1001; product.css:89-91 | none |
| I-116 | Tag chips | Tag bar (#tagbar, role="group" "Filter the moments by tag"): "All N" plus one chip per football tag with its count, most first; filters the grid, timeline highlight, reel and export; focus kept on the chip; hidden with fewer than two results | index.html:101; app.js:643-658; product.css:167-171 | none |
| I-117 | Tag chips | Bookkeeping tags (…_appearance, …_against, on_ball_main, touch, possession_change, kick_off, period_start, period_end) never shown or offered | app.js:49-51 | none |
| I-118 | Grid | Clip grid #grid: auto-fill columns, min 270 px (one column on phones) | index.html:102; app.js:610-640; product.css:93 | none |
| I-119 | Card | Card = button with aria-label "Play {title}"; click plays it on the stage | app.js:619, 631 | none |
| I-120 | Card | Preview video: loads only when the card nears the viewport (IntersectionObserver, 200 px margin, preload none → metadata); "Preparing…" until the first frame; "Could not load the preview" on error | app.js:620, 632-637, 667-674; product.css:172-174 | GET /api/matches/{id}/clips/{clip_id}.mp4 |
| I-121 | Card | No-video card text for Cosmos matches | app.js:621; product.css:99-100 | none |
| I-122 | Card | Reason line "Kind · m:ss" (replays in a lighter red for contrast) | app.js:623; product.css:103-104 | none |
| I-123 | Card | Title | app.js:624; product.css:102 | none |
| I-124 | Card | Watchability bar, tooltip "How worth watching, from 0 to 1: 0.xx" | app.js:625, 630; product.css:106-107 | none |
| I-125 | Card | Football tags | app.js:626; product.css:108-109 | none |
| I-126 | Badges | "Labelled by Microsoft Foundry" (tooltip names the model) for foundry: labels; "Cut from video" (tooltip "Cut from video by Regista's vision layer, run offline") for vision matches | app.js:660-665; product.css:110-112 | label.model, origin |
| I-127 | Card | Playing card marked .on: yellow border and yellow shadow. Decided: no yellow outline on the playing card in the match view | app.js:702, 726; product.css:97 | none |
| I-128 | Empty state | Player with no moments: "{name} never had the ball in the main camera and is in no replay or highlight, so Regista cut no moments for this player. Pick someone from "Players with moments"."; "Pick a player." | index.html:103; app.js:601-602, 608; product.css:114 | none |
| I-129 | Results | "Show more (N more)" after a question with more matches than shown; sends "more" | index.html:104; app.js:613-615, 1002; product.css:115 | POST /api/matches/{id}/chat |
| I-130 | Footer | "Built on …" naming only what health reports running (Microsoft Foundry (model), Microsoft Agent Framework, Azure MCP Server, Azure Cosmos DB, Azure AI Search, Application Insights) | index.html:109; app.js:924-933 | GET /api/health (api.py:579) |
| I-131 | Footer | "Rendered from synthetic match data; no real footage." | index.html:110 | none |
| I-132 | Footer | "How it works" button | index.html:111; app.js:1010 | none |
| I-133 | Footer | "Regista Studio" link to /studio | index.html:111 | GET /studio |
| I-134 | Footer | Footer style: centred, muted, 12.5 px | product.css:117-118 | none |
| I-135 | How it works | Dialog drawer from the right, modal; title "How it works"; Close button; backdrop click closes; Escape closes; focus returns to the button | index.html:114-118; app.js:1010-1013; product.css:120-126 | none |
| I-136 | How it works | "Two layers": Vision layer (private, runs offline) and Intelligence layer (this app), plus the event-list note | index.html:120-135; product.css:128-129 | none |
| I-137 | How it works | "The agent workflow": Ingest; Validator and Possession in parallel; Clip; Label; Review; Recap; Persist; Indexer (only where Azure AI Search is configured); Librarian | index.html:137-152; product.css:130-135 | none |
| I-138 | How it works | "Azure on this deployment": ticked list (Microsoft Foundry, Azure Cosmos DB, Azure AI Search, Azure MCP Server, Application Insights) with on / not configured and what each does; "Checking…"; "Health is not available right now." | index.html:154-155; app.js:926, 934-943; product.css:136-141 | GET /api/health |
| I-139 | How it works | "How real is the data?" paragraph | index.html:157-160 | none |
| I-140 | How it works | Realism report toggle "Show this match's numbers next to Premier League ranges" (aria-expanded); loads once per match, Markdown rendered safely (headings, bold, tables, in band / high / low verdicts), match id replaced by "this match"; "Loading the report…", "The realism report is not available for this match."; reset on match change | index.html:161-163; app.js:246, 946-994, 1009; product.css:185-194 | GET /api/matches/{id}/report (api.py:887) |
| I-141 | Keyboard | :focus-visible yellow outline everywhere; .sr visually hidden labels | product.css:3-4 | none |
| I-142 | Keyboard | Engine radios usable by keyboard (visually hidden inputs, focus ring on the segment) for both switches | product.css:27-32 | none |
| I-143 | Keyboard | Focus returns to the ask input after a reply; tag chip keeps focus after filtering; dialog returns focus; timeline keyboard (I-086) | app.js:429, 656, 1013 | none |
| I-144 | Responsive | No sideways scroll (body overflow-x hidden), text-size-adjust 100%; main max 1200 px, 16 px padding, column gap | product.css:5-6, 15 | none |
| I-145 | Responsive | ≤760 px: stage one column; pickers full width; engine switch full width with equal halves; header not sticky; Ask button keeps its size; workflow pair one column | product.css:143-152 | none |
| I-146 | Responsive | Timeline short lane names and narrow gutter under 480 px | timeline.js:72-73, 115 | none |
| I-147 | Data model | Every clip the page knows (state.all): the match's clips, each looked-at player's moments, reply results and recap clips; feeds the timeline and the stage | app.js:14-25, 74-82, 235-236, 833-840 | GET /clips, /clips?player=, /chat, /recap |
| I-148 | Endpoints not used today | GET /api/matches/{id}/search (q, limit ≤ 50; returns results with video_url) and POST /api/matches/{id}/ask exist but the page does not call them; a test forbids "'/search" in the page | api.py:731, 1120; tests/test_product_page.py:44-49 | GET /api/matches/{id}/search |

## Notes for the builders, the safeguard and the reviewers

- N-1. CLAUDE.md §2.8 is not on `ux/sandbox` (its CLAUDE.md stops at §2.7) nor on this branch; the sandbox folder
  (`sandbox/index.html`, `sandbox.css`, `sandbox.js`, 91-line index) is the only record of the decided layout.
- N-2. "The match's explainer line removed": the sandbox match view has a title, timeline, stage, actions, recap and
  conversation, and no line under the title. The candidates on the Clips page are I-051 (the manifest subtitle, most
  likely), I-053 (the vision note, which explains the "Cut from video" badge) and I-058 (the engine hint). Only I-051
  reads as an explainer of the match; I-053 and I-058 need a decision before anything removes them.
- N-3. Search across every match: the brief says "call the existing per-match search for every match". The page
  uses only POST /chat today (I-059); GET /api/matches/{id}/search exists (I-148) and is not called, and
  tests/test_product_page.py:47-49 asserts "'/search" and "/search?" are absent. Whichever endpoint is used, that test
  and the "Note the cost in the PR" item follow from it. /chat with the Foundry engine costs a model call per match.
- N-4. Removing the example chips (I-048, decided) breaks tests/test_product_page.py:73-75 ("const ASKS = [").
- N-5. Replacing the h1 (I-046, decided) breaks tests/test_product_page.py:39 (asserts the old h1 text served at /).
- N-6. The nav change (I-008, I-021, I-023, I-025) breaks tests/test_product_page.py:119-125 (expects
  `<a href="/" aria-current="page">Clips</a>`, link order /, /scout, /me, and `.views` only in shared/regista.css),
  tests/test_scout_page.py:41 and tests/test_player_page.py:73 (both look for `<nav class="views"` and
  `href="/scout" aria-current="page"`). The brief's order is Home, Player profile, Scout (/, /me, /scout).
- N-7. Three pages restyle `.views` themselves (I-022 scout.css, I-024 player.css; /me uses the shared one), with
  different current-link colours: Scout already shows the current view in yellow. A shared left panel must override or
  remove these per-page rules; those CSS lines are navigation, not page content.
- N-8. Cross-page link text still says "Clips" or "the Product" (I-029). The brief keeps Player and Scout content
  exactly as it is, so renaming that text needs a decision.
- N-9. The Studio (I-027) has its own header and is not in the brief's nav list; it is reached from the footer link
  (I-133). Leaving it as is keeps it unchanged.
- N-10. Profiles deep-link into / with ?match, ?player, ?clip, ?t and ?recap=1 (I-037, I-038, I-039). After the
  redesign these links must open the match view (not the Home landing), with ?recap=1 opening the folded "Match recap".
- N-11. Today the conversation, the recap, the stage and the grid are all for one match; the decided Home searches
  every match. Per-match items that need a home in the match view: match and player pickers (I-010 to I-019),
  Scout profile link (I-052), vision note (I-053), timeline (I-078 to I-089), stage and its actions (I-090 to I-104),
  recap (I-105 to I-113), the player's moments list with sort and tag chips (I-114 to I-129), the realism report
  (I-140, which reads "this match").
