# Player, profile and Scout pages: inventory before the dashboards port

Taken on branch `ux/dashboards` at commit 33c49a5, before any code changed. This is the checklist for the port of the
sandbox's Player dashboard and Scout dashboard: every item must end up in the new pages, or be flagged and decided.

Paths: `me/…`, `player/…`, `scout/…`, `shared/…` are under `src/regista/static/`. Python files are under `src/regista/`.
"Goes to" names the new section: `/me#overview|#profile|#matches|#messages|#team|#settings`,
`/scout#overview|#find|#shortlist|#reports|#messages|#team|#settings`, the shared profile page (`/players/{id}`, and the
same renderer in `/me#profile`), or the left panel.

Ids: ME = today's `/me`; PL = today's `/players/{id}`; AM = `player/add-match.js`; SC = today's `/scout`; SH = shared
files and server rules; T = test assertions that bind the port.

## ME: today's Player view (/me)

| id | what | file:line | goes to |
|---|---|---|---|
| ME-01 | Title "Regista Player", meta description, favicon | me/index.html:6-8 | /me (title may follow the section) |
| ME-02 | Load order: shared/regista.css, me.css; shared/regista.js, me.js (defer). No inline script or handler | me/index.html:9-10, 100-101 | /me |
| ME-03 | Brand header `header.top`, sticky | me/index.html:13-15; me.css:12-14 | /me |
| ME-04 | Left panel with "Player profile" current | me/index.html:18 | left panel: Player profile + its 6 sections |
| ME-05 | Network banner (role=alert) with Retry. Texts: "Regista cannot be reached. Check the connection." (start, suggestions); "…; progress will update when it is back." (polling); "Regista could not load the league: …" | me/index.html:22; me.js:63-68, 76, 371, 578-579 | /me, every section |
| ME-06 | Intro: h1 "Your match, cut by Regista." and lede | me/index.html:24-27 | Overview header / Add a match intro (sandbox reuses the lede in the form) |
| ME-07 | "Synthetic" badge and note (players and footage are synthetic) | me/index.html:28-30 | decide: the brief says no other caveats; keep one synthetic line (footer) |
| ME-08 | Numbered steps 1-2-3 (stepno, aria-hidden) | me/index.html:34, 58, 85 | replaced by sections |
| ME-09 | Chosen player: shirt in kit colours (GK colour for keepers), name, "Club · Position · number N · X matches in Regista" | me/index.html:35-45; me.js:37-42, 109-111 | header of every /me section |
| ME-10 | "Profile" link to /players/{id} | me/index.html:42; me.js:112 | /me#profile (same renderer) plus "See your profile" links |
| ME-11 | "Change": back to the finder, hides steps 2-3, stops polling, focuses search | me/index.html:43; me.js:122-128 | Switch player control |
| ME-12 | Search form (role=search, sr label, maxlength 80): GET /api/players?q=&sort=name&limit=12. Notes: "The first 12 matching “q”:", "N matching “q”:", "No player matches “q”.", "Search failed: …"; empty query shows suggestions | me/index.html:47-51; me.js:80-86, 567 | Switch player control |
| ME-13 | Suggestions: six forwards by goals (GET /api/players?position=FW&sort=goals&limit=6), "Or pick one of the league’s forwards:" | me/index.html:52; me.js:71-78 | Switch player control |
| ME-14 | Result list (aria-live polite): button per player with mini shirt, name, "Club · Position · #N" | me/index.html:53; me.js:88-96; me.css:41-49 | Switch player control |
| ME-15 | Choosing: id checked against `^pl_[a-z0-9_]{1,40}$`, GET /api/players/{id}; failure "That player could not be loaded: …"; URL gets ?player= by replaceState; old upload cards cleared; uploads refreshed | me.js:98-120 | Switch player |
| ME-16 | Deep link `/me?player=pl_…` opens that player quietly; bad ids ignored; no param shows the finder | me.js:581-583 | keep ?player=; new default is Femi Toure (pl_bro_09); the hash names the section |
| ME-17 | Start: /api/health (write mode) and /api/season (clubs) together | me.js:572-580 | /me |
| ME-18 | "Your footage" hidden until a player is picked | me/index.html:57 | Matches & videos, Add a match |
| ME-19 | Footage note: synthetic film in the vision format (640x360, 10 fps, no captions), `python -m regista.player.film` | me/index.html:59-61 | decide: operator wording; at most a small hint |
| ME-20 | Operator note: only the operator can upload (admin key); anyone can watch progress | me/index.html:62-63 | Add a match |
| ME-21 | Write modes: read-only "This deployment is read-only: nothing can be uploaded here."; locked "This deployment has no admin key configured, so nothing can be uploaded here."; form hidden | me.js:139-144 | Add a match (and Is this you?) |
| ME-22 | Key in use: "Using the admin key from this tab." + "Forget it" (clears the key); mode `open` needs no key | me.js:146-150 | Add a match |
| ME-23 | Key prompt: password field (autocomplete off, aria-label "Admin key"), "Use this key", sessionStorage note; sets Regista.key; "Key kept for this tab. Pick the video and upload."; upload button disabled until a key exists | me.js:152-164 | Add a match |
| ME-24 | Video field: accept video/mp4,.mp4, required; label "up to N MB" with N from the uploads list's max_mb | me/index.html:66-67; me.js:365 | Add a match |
| ME-25 | "Against": league clubs except the player's own | me/index.html:68; me.js:131-134 | Add a match |
| ME-26 | "Your club played": At home (default) / Away, pill radios with focus ring | me/index.html:69-73; me.css:65-71 | Add a match (sandbox: "You played") |
| ME-27 | Checks before sending: "Pick the video first.", "The footage must be an MP4 file (.mp4).", "That video is N MB; the limit is M MB.", "Pick the club you played against." | me.js:194-197 | Add a match |
| ME-28 | Upload by XMLHttpRequest with progress: progressbar (aria-valuenow), "Uploading x of y MB…", then "Storing the video and queueing the vision job…" | me/index.html:76-79; me.js:174-189, 205-214 | Add a match |
| ME-29 | POST /api/player/uploads, multipart global_id, opponent_club_id, side, video, header X-Regista-Token | me.js:177-178, 199-203; player_api.py:313 | Add a match |
| ME-30 | Success: "Uploaded. The vision job is queued[ in Azure]: follow it below."; form reset; card added; poll in 300 ms; card scrolled into view | me.js:217-223 | Add a match → Your uploads |
| ME-31 | Failure: 401 clears key, asks again, "That key was not accepted. Paste it again."; 403 shows detail; else "The upload failed: …"; dropped connection message; button state restored | me.js:186, 224-231 | Add a match |
| ME-32 | Upload message line role=status aria-live | me/index.html:80 | Add a match |
| ME-33 | "Regista at work": one card per upload, subtitle "N uploads · K in progress, updating live" | me/index.html:83-88; me.js:350-356 | Your uploads |
| ME-34 | Empty: "No footage from this player yet. Upload a match above and follow every agent here." | me/index.html:89 | Your uploads (offline: no friendly, must read well) |
| ME-35 | Polling GET /api/player/uploads?global_id=: 2 s while any upload is queued/running, 15 s otherwise; paused while the tab is hidden, resumes at once on return; stale replies after a switch dropped; one request at a time | me.js:358-377, 391-394, 569 | Your uploads; Overview's Needs you should read the same data |
| ME-36 | Store kind (azure/local) remembered and changes copy | me.js:366, 310 | Your uploads |
| ME-37 | Card head: "Against X · home" / "At X · away"; weekday and time, size in MB, "synthetic footage"; status pill Queued / Working / Is this you? / Done / Failed, coloured | me.js:316-319, 338-342; me.css:91-96 | Your uploads |
| ME-38 | Live card glow while queued or running | me.js:337; me.css:87 | Your uploads |
| ME-39 | Agent pipeline: Queued, Shots, Identity, Is this you? (only when asked), Possession, Events, Writer, Clips (all intelligence roles), Done. States ok/running/ask/failed/skipped/pending with ✓ ✕ ? –; time per step (sum of ms); tooltip with what the agent does and its note; screen-reader state words | me.js:237-313 | Your uploads ("every agent step and time") |
| ME-40 | Inferred steps: running with no running stage lights the next one; failed with no failed stage marks the next; done marks all; needs_review marks all before the question | me.js:276-287 | Your uploads |
| ME-41 | "Now" line: "Waiting for a worker" (Azure: Blob Storage + Container Apps Job copy), "<Step> agent" + what it does, "Finished · The agents took X in all." | me.js:305-313 | Your uploads |
| ME-42 | Live clock on the working step, every second, from updated_at ("working m:ss") | me.js:380-389, 565 | Your uploads |
| ME-43 | Pulse on the working node; no animation under prefers-reduced-motion | me.css:107, 116-117 | Your uploads |
| ME-44 | Phones (≤760 px): pipeline becomes a column; upload form one column, full-width button | me.css:162-171 | Matches & videos |
| ME-45 | Failed job: "The job stopped: <error or no reason given>" (role=alert) | me.js:344-345 | Your uploads |
| ME-46 | Cards survive polls: only changed parts are rebuilt (signature), so a playing clip or half-given answers are not reset | me.js:321-348 | Your uploads, Is this you? |
| ME-47 | Newest upload first | me.js:350-353 | Your uploads |
| ME-48 | Questions: GET /api/player/uploads/{id}/questions when needs_review, reloaded only when updated_at changes; "The questions could not be loaded: …" | me.js:397-404; player_api.py:409 | Is this you? (per upload) |
| ME-49 | Heading "Is this you, <first name>?" or "Nothing to ask you", explanation with the count | me.js:433-436 | Is this you? |
| ME-50 | Question card: crop image (URL checked against the crops pattern), alt text with time, lazy, pixelated; else "No picture · m:ss" | me.js:441-446; me.css:128-129 | Is this you? |
| ME-51 | "Yes, me" / "No" toggles (aria-pressed, role=group with label), card border shows the answer, answers kept across redraws | me.js:447-456 | Is this you? |
| ME-52 | Meta: "Main camera" or the replay kind · time span · hint (named you but unsure / named someone / unnamed; % of kit-number reads; estimate %) | me.js:457-465 | Is this you? |
| ME-53 | "Send my answers" (or "Finish" with no items), "Skip: keep the agents’ calls"; "Answering needs the admin key: paste it in “Your footage” above."; "Answer at least one, or skip."; progress copy; "Thanks: N answers applied." / "Done."; 401 clears key; buttons re-enabled on error | me.js:408-431 | Is this you? |
| ME-54 | POST /api/player/uploads/{id}/answers {answers:[{item_id,is_me}]} with the key; card updated from the reply | me.js:420-423; player_api.py:515 | Is this you? |
| ME-55 | Results when done: GET links.clips, only the uploader's clips, best 6; "Your moments: N" + badge "Filmed by the player · cut from video"; best-first copy; none: "Regista found no moments of you on the ball in this footage. The match still counts in your profile."; load error | me.js:470-492 | Your uploads (done card); Overview best moment / activity |
| ME-56 | Moment card: cover button "Play: title" (▶, reason · time), video URL checked to start with /api/matches/, "Cutting the clip…", error "The clip could not be played. Try again."; title, "m:ss · reason · worth watching N%", up to 4 tags (no touch/on_ball_main) | me.js:538-561 | Your uploads; moment attachments in Messages |
| ME-57 | "Open the match on Home" (links.clip_view) and "See your updated profile" (links.profile), same-origin paths only | me.js:483, 490-492 | Your uploads |
| ME-58 | Match recap: "Writing your match recap…", GET /api/matches/{mid}/recap?player=; headline, paragraphs, each sentence a link to /?match&player&clip; "Written by Regista from the match events…"; "The recap could not be written: …" | me.js:493-536 | Your uploads (done card) |
| ME-59 | Recap reel: "Play your recap reel (N)" → "Cutting the reel… the first view takes a little while"; error "The reel could not be played. Try again."; reel URL checked | me.js:514-528 | Your uploads |
| ME-60 | "Read it on Home" to clip_view&recap=1 | me.js:535 | Your uploads |
| ME-61 | Footer: synthetic line; Home · Scout · Regista Studio | me/index.html:93-96 | /me footer |
| ME-62 | .sr, focus ring, no sideways scroll, sections labelled by their headings | me.css:4-7 | all |
| ME-63 | All API text through textContent/h(), never markup | me.js:16-28 | see T-15 |

## PL: today's player profile (/players/{id})

| id | what | file:line | goes to |
|---|---|---|---|
| PL-01 | Title "Player profile · Regista Scout", then "<name> · Regista Scout"; "No such player · Regista Scout" | player/index.html:6; player.js:93, 103 | shared profile page |
| PL-02 | Meta, favicon, shared css then player.css; regista.js, player.js, add-match.js (defer) | player/index.html:7-10, 119-121 | shared profile page |
| PL-03 | Left panel marks Scout current | player/index.html:18 | left panel: Scout + its sections |
| PL-04 | "← Back to Scout"; returns to the referring /scout URL with its filters when same-origin (needs referrer-policy same-origin) | player/index.html:22; player.js:396-399; api.py:118 | scout bar "Back" (sandbox #scBack); keep filters/section |
| PL-05 | "Loading the profile…" (role=status); after 3 s "…The league is built on first use, which can take about half a minute." | player/index.html:24; player.js:68-71 | shared renderer (both pages) |
| PL-06 | Error banner + Retry: "The profile could not be loaded (detail or HTTP n)." / "…Check your connection." | player/index.html:26; player.js:78-82, 401 | shared renderer |
| PL-07 | Missing: bad id "That is not a player id."; 404 "No player with this id has played in the Regista League."; "Find a player in Scout" link. Server answers 400 for malformed ids | player/index.html:28-32; player.js:67, 77, 92-98; season_api.py:81-84, 293-297 | shared profile page |
| PL-08 | Player id read from the last path segment | player.js:8 | shared profile page |
| PL-09 | Header: shirt in kit colours, h1 name, "#N · Position · ● Club" (club dot), "N appearances · M minutes" | player/index.html:35-42; player.js:117-129 | shared renderer (sandbox draws an SVG shirt) |
| PL-10 | Synthetic note: every number counted from the league's event streams and linked to its moments | player/index.html:43-44 | shared renderer (see T-07) |
| PL-11 | Summary: hidden when empty; string or {text, by, sources}; paragraphs; "Written by X"; Sources list linking to a clip, a time or a path, with "Round N, v Opp" | player/index.html:46; player.js:132-151 | shared renderer; the sandbox's cited sentences (play the moment / open the number) plus a fallback for the older shape |
| PL-12 | Best-moments reel: cover, "Play best moments", "The best six moments across the season, back to back." / "No moments to put in a reel yet." (disabled); GET /api/players/{id}/reel.mp4?n=6[&tag=] | player/index.html:48-61; player.js:155-184; season_api.py:143 | shared renderer (sandbox: strip of 8 + "Play reel" playing clips back to back) |
| PL-13 | Reel loading overlay "Putting the reel together (kind). The first time renders each moment…"; hides on canplay/playing; error "The reel could not be loaded. Try again, or pick another kind of moment below." | player.js:177-193, 407-410 | shared renderer |
| PL-14 | Kind-of-moment chips: "Best of everything" + goal, assist, nutmeg, take-on… that the player has; aria-pressed; deliberately no counts | player/index.html:60; player.js:12-13, 155-169, 403-406 | shared renderer (not in the sandbox: keep) |
| PL-15 | Numbers: "Across N matches, per 90 minutes."; "Every number links to the moment it came from. Pick one to see each event behind it." | player/index.html:63-68; player.js:204 | shared renderer |
| PL-16 | Headline stat buttons from headline_keys (saves only for, and first for, keepers): label, per-90, "N in total", percentile bar, "Nth percentile among forwards" / "Too few minutes to compare with other forwards" | player.js:196-216 | shared renderer tiles; wording "Higher than N% of the league's forwards" |
| PL-17 | Ratio tiles (pass accuracy, take-on success, shot accuracy): %, "a of b <stat>", open the numerator's evidence | player.js:217-224, 247-250 | shared renderer (sandbox shows ratios as text: keep them openable) |
| PL-18 | "Show every number" / "Hide the full table" (aria-expanded, aria-controls): two tables (Stat, Total, Per 90 min, Percentile; Rate, Share, From) with sr captions and a percentile note | player/index.html:70-71; player.js:226-243, 428-433 | shared renderer (not in the sandbox: keep) |
| PL-19 | Evidence: "<Stat>: N across M matches" (focusable), "None yet." / "The first k of N, in match order…" / "In match order…"; each event links to its clip ("Watch the moment") or time ("Open the match here"); Close; Escape; second click closes; aria-expanded on every opener; focus returns to the stat; re-shown after a reload | player/index.html:72-79; player.js:113, 252-283, 412-427 | shared renderer (sandbox plays the clip in place; still link to Home) |
| PL-20 | Touch map SVG (105x68, heat cells, markings, "Attack" arrow), role=img with a text description of the thirds; "N% own / middle / final third"; "No actions recorded yet." | player/index.html:82-89; player.js:286-329 | shared renderer (sandbox draws cells with inline styles: see SH-08) |
| PL-21 | Moments grid: "The best N across the season, best first." / "No labelled moments yet."; 9 at a time, "Show more" | player/index.html:91-98; player.js:332-341, 434 | shared renderer (not in the sandbox: keep) |
| PL-22 | Moment card: Play (aria-label), reason (replays in red), title, tag words, "Round N · v Opp" or "Filmed by the player" / "Claimed match", "Watch on Home" | player.js:343-359 | shared renderer |
| PL-23 | Playing a card: video in place, "Preparing this clip. The first view renders it…", "This clip could not be loaded.", focus on the video; same-origin URL only | player.js:361-374 | shared renderer |
| PL-24 | One video at a time: starting one pauses the others | player.js:423-425 | every page with video |
| PL-25 | Matches: league rounds first, then uploads and claims; badge "Filmed by the player · cut from video" / "Claimed" / "Round N"; date; "v/at Opp (home/away)"; score with W/D/L chip (sr Won/Lost/Drew); row link "Watch on Home"; separate "Recap" link (aria-label) to &recap=1; "No matches yet." | player/index.html:100-106; player.js:377-392 | shared renderer (sandbox lacks Recap and W/D/L: keep) |
| PL-26 | Deep links into Home: /?match&player&clip, /?match&t=, /?match&player, &recap=1 (exact strings are tested) | player.js:52-56 | shared renderer |
| PL-27 | window.RegistaPlayer {id, profile, onProfile, reload} and a `regista:profile` event after every load (add-match follows it) | player.js:27-32, 88-89 | shared renderer |
| PL-28 | Phones (≤760 px): header not sticky; match rows and evidence reflow | player.css:162-171 | shared renderer |
| PL-29 | Footer: synthetic line; Home · Scout | player/index.html:112-115 | shared profile page |
| PL-30 | .sr, focus ring, no sideways scroll; tables scroll inside their own box | player.css:3-6, 85 | shared renderer |
| PL-31 | Number formats: 1 decimal from 10, else 2; ordinals; dates en-GB "12 Oct" | player.js:35-62 | shared renderer |

## AM: "Add a match" on the profile (player/add-match.js)

| id | what | file:line | goes to |
|---|---|---|---|
| AM-01 | Fills only `<section id="addMatch">`; runs only on /players/pl_… paths | add-match.js:15-29 | shared profile page; decide whether /me#profile shows it (Matches & videos already has an upload) |
| AM-02 | "Add a match" heading and intro (the operator confirms the claim in the Studio) | add-match.js:75-78 | shared profile page |
| AM-03 | Status line (role=status, aria-live) coloured by tone | add-match.js:73, 79-80 | shared profile page |
| AM-04 | Loads player and health; "Cannot load this player: …" | add-match.js:97-102 | shared profile page |
| AM-05 | Read-only / locked messages | add-match.js:103-107 | shared profile page |
| AM-06 | Key prompt; the key slot `regista-key` in sessionStorage, shared with Regista.key and the Studio | add-match.js:18-23, 83-95 | shared profile page |
| AM-07 | GET /api/studio/session with the key: capabilities.jobs decides the video form; 401 clears the key, "That key was not accepted." | add-match.js:110-117 | shared profile page |
| AM-08 | "For Name (Club, number N)." | add-match.js:124 | shared profile page |
| AM-09 | events.jsonl (required), tracks.jsonl (optional), match id (checked, no ".."); POST /api/matches[?match_id=]; "Validating and running the Agent Framework workflow…"; "Match X added: the workflow ran / reported a problem (see the Studio)"; 401 handling | add-match.js:135-166 | shared profile page |
| AM-10 | "Or a match already added": local matches (not rl_), "Find me in this match" | add-match.js:168-177 | shared profile page |
| AM-11 | Operator machine only: video path, team sheet, new match id; POST /api/studio/jobs {kind:'vision-run'}; polls the job every 3 s with its status | add-match.js:179-219 | shared profile page |
| AM-12 | Elsewhere: "Have a video instead? Video processing runs on the operator’s machine, where the vision layer lives: …" + models hint (text is tested) | add-match.js:128-131 | shared profile page |
| AM-13 | "Which one is you in <match>?": team (starts on the team with the profile's number), kit number, "On this team sheet: Name (N) — your profile number is M", optional name (checked) and note, "That’s me", "Back"; "This match already knows who everyone is: it needs no claim."; POST /api/claims | add-match.js:222-275 | shared profile page |
| AM-14 | "Claim sent: pending." with "Watch the match", "Studio, Claims" (/studio#claims), "Add another match" | add-match.js:277-285 | shared profile page |
| AM-15 | Styles through el.style.cssText (CSSOM, allowed); player.css keeps its grids inside a phone's width | add-match.js:37, 72; player.css:173-178 | shared profile page (move to classes) |

## SC: today's Scout view (/scout)

| id | what | file:line | goes to |
|---|---|---|---|
| SC-01 | Title "Regista Scout", meta, favicon | scout/index.html:6-8 | /scout |
| SC-02 | shared css, scout.css; exactly regista.js then scout.js (tested) | scout/index.html:9-10, 141-142 | /scout (see T-11) |
| SC-03 | Left panel, Scout current | scout/index.html:18 | left panel: Scout + its 7 sections |
| SC-04 | Error banner + Retry (re-runs what failed); "Can't reach Regista right now. Check your connection and try again." or the server's detail | scout/index.html:22; scout.js:40-42, 80-87 | /scout, every section |
| SC-05 | Intro h1 "Every player in the league, every number backed by a moment.", lede, Synthetic badge (text tested) | scout/index.html:24-30 | Overview header / Find players; see T-10 |
| SC-06 | League table: "<league> <season>", "6 clubs · 10 rounds · 30 matches", columns # Club P W D L GD Pts with abbr titles, sr caption, kit swatch, +GD; "Loading the league…"; "The league is not available." | scout/index.html:32-49; scout.js:91-123 | Find players (or Overview); not in the sandbox's Scout: keep |
| SC-07 | Club in the table filters players to that club (again clears), aria-label "Show X players", syncs the select, scrolls to results | scout.js:125-132 | Find players |
| SC-08 | Phones (≤600 px): short club names, tighter table | scout.css:150-157 | Find players |
| SC-09 | Footer note replaced by the season's note | scout.js:111 | /scout footer |
| SC-10 | Scout agent: sr label, maxlength 300, example placeholder; engine radiogroup "Instant" (rules, default) / "Foundry"; hint explaining both | scout/index.html:51-65 | Find players (sandbox has no engine switch: keep it; labels "Data Search" / "Foundry" to match Home) |
| SC-11 | Ask: empty ignored; button disabled while asking; "Asking the Foundry Scout agent… (a few seconds)" / "Ranking the players…"; POST /api/scout/ask {q, engine} | scout.js:482-500; season_api.py:241 | Find players |
| SC-12 | Errors: 429 "Too many questions just now; try again in a minute."; 422 "Ask in under 200 characters." (field allows 300); else "Regista could not answer just now…" | scout.js:493-496 | Find players |
| SC-13 | Answer (aria-live): reply, "Understood: …", who answered ("Answered by Microsoft Foundry, using <tools>." / "Answered by Regista's rules (<why>)." / "Answered by Regista's rules."), "Numbers in this reply that no tool returned: …", then player cards with stars | scout/index.html:65; scout.js:455-472 | Find players (sandbox has example chips: add them) |
| SC-14 | window.RegistaScout.renderScoutAnswer | scout.js:473 | keep (tested name) |
| SC-15 | Compare panel: focusable heading, Close (focus back to Compare), explanation | scout/index.html:68-76; scout.js:449 | Shortlist |
| SC-16 | Compare: 2-3 picked → GET /api/compare?ids=; "Loading…"; error; header per player (shirt, profile link, club · position, minutes); per-90 rows with percentile under each, ratio rows; highest marked ▲ and sr "(highest)" when more than one value and top > 0; sr caption | scout.js:393-446; season_api.py:201 | Shortlist (sandbox: every number opens its moments, from profiles) |
| SC-17 | Filters: Position, Club, Name (250 ms debounce, 80 chars), Minimum minutes (0-10000, step 30, 300 ms debounce), Sort (Minutes played, Name, then stat catalogue in "Per 90 minutes" / "Share that worked"), Reset | scout/index.html:79-107; scout.js:136-201 | Find players (sandbox has Name, Position, Sort only: keep Club, Minimum minutes, Reset) |
| SC-18 | Filters in the URL (position, club, q, min_minutes, sort), read on load (checked against the options), written by replaceState to /scout?… | scout.js:148-172 | Find players; the query must survive next to the #find hash |
| SC-19 | GET /api/players?sort&limit=200&filters; stale replies dropped; aria-busy on the cards | scout.js:205-228; season_api.py:103 | Find players |
| SC-20 | Results: "N players, sorted by X per 90 minutes", plus "Cards do not show X; each player's profile does." | scout/index.html:123-127; scout.js:279-288 | Find players |
| SC-21 | Empty: "No players match these filters. Try a lower minimum or another position." | scout/index.html:129; scout.js:291-292 | Find players |
| SC-22 | Card: shirt (dark or light ink on the kit), name link covering the card, club · #N · position with swatch, minutes · matches, star (aria-pressed, add/remove label), "Per 90 minutes", 4 rates (sort first) with value, percentile (tooltip "Higher than N% of forwards in the league" / "Too few minutes…"), bar; ratios "of attempts"; best moment or "No labelled moments yet." | scout.js:231-277 | Find players; Shortlist; Team needs |
| SC-23 | paint(): colours and widths set by element.style from data-c / data-c2 / data-w | scout.js:65-76 | pattern for every new page |
| SC-24 | Shortlist in localStorage `regista-scout-shortlist` (ids checked); in memory when storage fails, with "This browser is not keeping the shortlist, so it lasts until you leave the page." | scout/index.html:115; scout.js:302-320 | Shortlist via Regista.store; migrate the old key once |
| SC-25 | Shortlist panel: "(N)", "Star a player to keep them here. Pick two or three to compare.", rows with compare checkbox (sr label, max 3, others disabled), shirt, profile link, club · position, × remove; focus kept after change/remove | scout/index.html:110-121; scout.js:348-389 | Shortlist (with stages) |
| SC-26 | Compare enabled from 2 picked; "Pick two or three to compare." / "Pick one more to compare." / "N picked."; first three picked on load and when added | scout.js:312, 330, 368-370 | Shortlist |
| SC-27 | Stars agree everywhere (list and agent answer) | scout.js:338-346, 475-480 | Find players, profile scout bar |
| SC-28 | Shortlist sticky beside the cards from 980 px; stacked on phones | scout.css:57-66 | Shortlist is its own section now |
| SC-29 | Footer: note; Home · Regista Studio | scout/index.html:134-137 | /scout footer |
| SC-30 | 16 px inputs (phones do not zoom), card focus ring, long names wrap | scout.css:50, 71, 99, 7 | all |

## SH: shared files and server rules

| id | what | file:line |
|---|---|---|
| SH-01 | One left panel markup on every page, Home / Player profile / Scout, one aria-current; /players/{id} marks Scout; current in yellow; a row of tabs at ≤720 px | shared/regista.css:22-49 |
| SH-02 | --top-h follows the header so the panel sticks under it | shared/regista.js:51-67; regista.css:34 |
| SH-03 | Regista.key: sessionStorage `regista-key`, sent only as X-Regista-Token | shared/regista.js:16-22 |
| SH-04 | Regista.api (JSON, FormData, auth), ApiError | shared/regista.js:24-40 |
| SH-05 | esc, reasonLabel, tagLabel, fmtTime | shared/regista.js:6-14, 49 |
| SH-06 | `[hidden]` always wins over layout | shared/regista.css:10 |
| SH-07 | CSP: script-src 'self'; style-src 'self' 'unsafe-inline'; media/img self + blob; connect-src self; referrer-policy same-origin | api.py:116-118 |
| SH-08 | Today player.js writes style="" into markup (club dot, percentile bar) and the sandbox does too (bars, heat cells). The brief forbids it: set them after rendering | player.js:126, 214; sandbox profile-view.js:107, 129 |
| SH-09 | Routes: /me (player_api.py:276), /scout (season_api.py:76), /players/{gid} with 400 on bad ids (season_api.py:81) | — |

## T: what the tests assert (keep, or change on purpose with the code)

| id | assertion | test |
|---|---|---|
| T-01 | The left panel is exactly `<a href="/">Home</a><a href="/me">Player profile</a><a href="/scout">Scout</a>` with one aria-current, on all four pages (header holds no nav; shell > nav, shell-main > main … footer) | test_product_page.py:143-160 |
| T-02 | Only three hrefs and one aria-current inside nav.views | test_player_api.py:329-334 |
| T-03 | `.views` styled only in shared/regista.css (not in me.css, scout.css, player.css, product.css); phone rule has flex-direction row and overflow-x auto; --top-h in both shared files | test_product_page.py:163-172 |
| T-04 | /players/{id} serves player/index.html byte for byte with the CSP; bad ids 400; unknown id serves the page with id="missing" and "No such player" | test_player_page.py:38-50 |
| T-05 | No inline scripts or handlers; scripts and links under /static/; every file loaded is served (add-match.js excepted) | test_player_page.py:53-69 |
| T-06 | player/index.html has nav with Scout current, "← Back to Scout", ids summary, addMatch, reelVideo, headline, touchMap, momentGrid, matchList, evidence; the add-match.js tag; "Every number links to the moment it came from"; "synthetic player from Regista's generated league"; `<section id="summary" … hidden></section>` | test_player_page.py:72-82 |
| T-07 | player.js has window.RegistaPlayer and regista:profile, never "AddMatch"/"addMatch" | test_player_page.py:85-88 |
| T-08 | player.js holds the four Home link templates, `/reel.mp4?n=${REEL_N}`, `&tag=${encodeURIComponent(tag)}`, `e.status === 404`, showMissing | test_player_page.py:91-96 |
| T-09 | player.js uses stat_labels; no "per90" or "_" in the page's visible text; no "per90" in any template string's visible text; `const { esc,`; no raw ${m.title}/${p.name}/${src.title}/${text}/${where(; every where( call escaped; node --check passes | test_player_page.py:99-123 |
| T-10 | /scout serves scout/index.html byte for byte; nav Scout current; "synthetic players and clubs from Regista's generated" in the page | test_scout_page.py:38-41, 63-64 |
| T-11 | /scout loads exactly ["/static/shared/regista.js", "/static/scout/scout.js"]; no inline script/handler; scout.css linked; files served | test_scout_page.py:44-60 |
| T-12 | ids scoutAsk, scoutAnswer, name scoutEngine; "function renderScoutAnswer(json)"; the exact call `R.api('/api/scout/ask', { method: 'POST', body: { q, engine } })`; "Answered by Microsoft Foundry" and "Answered by Regista's rules" | test_scout_page.py:67-72 |
| T-13 | scout.js names /api/season, /api/players?, /api/compare?ids=; `const esc = R.esc`; no "per90" in the page; "localStorage" and "try {" in scout.js | test_scout_page.py:75-81 |
| T-14 | /me (with ?player=) serves me/index.html byte for byte with the CSP; scripts under /static/ and served; no inline handlers; stylesheets served | test_player_api.py:308-320 |
| T-15 | me.js has no innerHTML, insertAdjacentHTML or eval; has X-Regista-Token; no "sessionStorage." | test_player_api.py:323-326 |
| T-16 | add-match.js: only getElementById('addMatch'), "if (!root) return;", no innerHTML, `const KEY = 'regista-key';`, sessionStorage, no localStorage, 'X-Regista-Token', no ?token=, the operator video text, the four endpoints; served as JavaScript | test_claims.py:252-265 |
| T-17 | Pages call the first view Home: '<a href="/">Home</a>' in me/, player/, scout/ index.html; ">Watch on Home<" in player.js; "'Open the match on Home'" and "'Read it on Home'" in me.js; never "in Clips" | test_product_page.py:383-390 |
| T-18 | Routes are classified public: GET /me, /scout, /players/{gid} and the read APIs; uploads, answers, claims, POST /api/matches need the admin key (a new route fails until classified) | test_access.py:17-60 |
| T-19 | Studio files must not mention localStorage (shared/regista.js is not in the checked set, studio.js is). shared/regista.js is also run in node with only `window = {}` (no document, no storage): Regista.store must not touch storage at load time | test_studio_page.py:189-219 |

## Where the port will collide (decide before building)

1. T-01/T-02 compare the nav's inner HTML exactly. The section links under Player profile and Scout break both tests
   unless they sit outside `<a>` siblings the regexes read, or the tests are updated with the new markup.
2. T-15 forbids innerHTML in me.js, while the sandbox renders with innerHTML + esc. Either build /me with h()/textContent
   or update the test to the esc() rule used elsewhere (T-09 style).
3. T-11 fixes /scout's scripts to two files. A shared profile renderer loaded on /scout means updating it.
4. T-06/T-04 need the profile page's ids and sentences; T-10/T-14 need the pages served byte for byte from their files
   (fine as long as the pages stay static files).
5. SH-08: today's style="" in player.js must go when it moves into the shared renderer.
6. AM-01: add-match.js only runs on /players/…; on /me#profile the brief wants the same page without the scout bar.
7. SC-24: existing visitors' shortlist sits under `regista-scout-shortlist`; carry it into `regista.demo.v1.` once.
8. ME-16: today /me with no player shows a picker; the brief opens Femi Toure. Switch player replaces the picker.
9. ME-07, SC-05, PL-10: the synthetic notes are tested (T-06, T-10). The brief allows no other caveats; keep one short
   line where the tests need it, or update the tests.

## Today's features the sandbox design does not show (keep them inside the design)

Profile page: kind-of-moment reel chips (PL-14), full number tables (PL-18), the moments grid with Show more (PL-21),
the Recap link and W/D/L per match (PL-25), loading/slow/missing/error states (PL-05 to PL-07), the referrer-aware Back
(PL-04), Add a match with claims (AM-*), ratio evidence (PL-17), summary sources in the older shape (PL-11).
Scout: league table and club filter (SC-06, SC-07), engine switch and answered-by/checked lines (SC-10, SC-13),
Club / Minimum minutes / Reset filters and the URL state (SC-17, SC-18), compare's highest marker and percentiles
(SC-16), storage-blocked note (SC-24). Player: key prompt and Forget it (ME-22, ME-23), write modes (ME-21), XHR upload
progress (ME-28), live clocks and inferred steps (ME-40, ME-42), skip answers (ME-53), recap and recap reel per upload
(ME-58, ME-59), footer link to the Studio (ME-61, SC-29).
