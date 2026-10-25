# Scout terminal port: safeguard report

Branch `ux/terminal`, checked after the build commit 2fc1ed4. Everything ran offline on this machine: the app on
127.0.0.1:8182 with `REGISTA_DOTENV=`, in the desktop app's browser pane. Nothing touched the live app or Azure. Nothing
was pushed or merged.

## Result

- Every inventory item (SC-01 to SC-53, TD-01 to TD-38) is still there and works on the new `/scout`.
- One thing was broken by the port, and it is now fixed: **Reset this demo did not reset the Terminal in the same tab**.
  - `Regista.demo.reset()` cleared the browser store. The Terminal still held its workspaces and history in memory,
    and the storage event that would have told it only reaches other tabs.
  - So the next Terminal action wrote the old workspaces and the full history back. I reproduced this: the compare
    players and 18 history entries came back.
  - The fix: `terminal.js` now listens to the same button. It runs after scout.js's own listener, drops any pending
    save, forgets the workspaces and history it holds in memory, and redraws from the defaults.
  - Checked in the browser after the fix: comparison "none", history only the next command.
  - The Settings note now says the Terminal workspaces are reset too.
  - New test: `test_reset_this_demo_resets_the_terminal_in_the_same_tab`.
- Tests:
  - Before my change: `python3 -m pytest -q` gave 829 passed, 13 deselected.
  - After my change: 830 passed, 13 deselected (one new test), and `-m slow` 13 passed.

## Existing /scout features (SC items)

Checked at 1440 x 900 in the browser, each section opened through its hash:

| Items | What I checked | Result |
|---|---|---|
| SC-01, SC-03, SC-04 | Title "Regista Scout", CSP header `script-src 'self'`, left panel with 8 sections (Terminal after Find players), only the section's own panel showing | OK |
| SC-05, SC-11 to SC-14 | "Messages 1" count, Overview persona, Needs you cards, shortlist tiles | OK |
| SC-15, SC-16 | Scout agent, Data Search: "Forwards with the most goals" answered (Femi Toure 1.64 per 90). This POST is the page's only one | OK |
| SC-17, SC-18 | `?position=FW&sort=goals#find` loaded the filters (fPosition=FW, fSort=goals) | OK |
| SC-20, SC-22, SC-23 | 102 cards, the star toggles the shortlist and toggles back, 6 club buttons in the table | OK |
| SC-24 to SC-28 | `#shortlist/pl_bro_09` added the player to compare and dropped the id from the hash. The compare table appeared; a number opened its moments (Toure's 5 goals) | OK |
| SC-29 to SC-34 | `#reports/pl_bro_09` started a draft | OK |
| SC-36, SC-37 | `#messages/pl_bro_09` focused the composer | OK |
| SC-38 | "Messages, notes and reports are kept in this browser only." appears exactly twice | OK |
| SC-47 | Reset this demo | **Fixed** (above) |
| SC-49 | At 375 px: `scrollWidth` 375 in all 8 sections, header static, the sections in a scrolling row | OK |
| SC-51, SC-52 | scout.js changed only in its header comment and the reset note. No `style=` and no `localStorage` in it | OK |
| SC-53 | Only terminal.js binds Cmd/Ctrl+K (a test pins this) | OK |

Home (`/`), `/me` and `/players/pl_bro_09` load and render. The profile page's left panel lists Terminal. No console
error came from the pages; the only errors in the log came from my own test harness.

## Terminal against the sandbox reference

- **Commands:** the same command table as the sandbox (RANK, CMP, SCAT, SIM, SHOT, FORM, HEAT, RDR, TEAM, HELP) and the
  same nine panels in the same F-key order.
  - Every click action in the sandbox exists in the port. The port adds Retry and reload, which the sandbox did not
    need because its data was local.
  - Each command was run in the browser and gave its line: for example "RANK FW · Non-penalty xG: 18 forwards; top Femi
    Toure 1.15", "SHOT Femi Toure: 19 shots, 5 goals", and "TEAM BRO · Brookfield Rovers: team style…".
  - HELP opens and Escape closes it. An unknown word gives the error with examples.
- **Keys:** checked with real key presses.
  - Cmd+K from Overview opened the Terminal, and "team ash" typed straight after landed in the line.
  - Escape closed the suggestions. Enter ran the command, and Up brought it back.
- **Panels and workspaces:**
  - Hide, then the F-key brings the panel back.
  - Size S becomes M.
  - Workspace 2, then back to 1, kept that size. Reset put it back to S.
  - Everything is stored under `regista.demo.v1.terminal`; no other storage key was written.
- **Tooltips:** the definition, rule, source, unit and the noisy mark show on hover and on focus.
  - The focus tip was seen after a real Alt+1.
  - Focus events do not fire in a hidden pane, so the other focus checks used dispatched events.
- **Clips:**
  - A shot on the map loaded its clip (`readyState` 4, HTTP 200).
  - Brookfield xG against listed 29 opponent shots, adding up to 4.50.
  - Set-piece xG listed 7 shots with their takers, for example "Femi Toure · Goal".

### Zaid's decisions

- **Complete evidence:**
  - Toure's touches show all 182 moments; the API total is 182.
  - npxg shows 19 of 19.
  - The API pages correctly: `evidence_limit=100&evidence_offset=100` gave items 100 to 181, each with a `minute`.
  - Bad input is refused with 422: offset -1, limit 501, and side=sideways.
- **The four sandbox fixes:**
  1. **FORM bars:** all 10 of Toure's touches bars said "N in this match" equal to that match's distinct events in the
     full evidence list: 27, 15, 16, 18, 19, 11, 12, 19, 20, 25.
  2. **Radar:**
     - Toure against Otis Nakamura drew one polygon and one broken outline, with no vertex at the centre, and the
       caption explains the gap.
     - Toure against the keeper Jonah Eriksen drew no outline for Eriksen and said why: "goalkeepers are not scored on
       the FW template".
  3. **Keyboard route:** after `RANK FW npxg`, a real Alt+1 focused the leader's npxg cell. Down moved to Amari Ustinov
     (rank 2) with the tip showing.
  4. **In view at 375 px:** smooth scrolling was swapped for instant scrolling in the hidden pane. Ten commands were
     run: RANK DF aerial win %, TOURE, SIM, SHOT, FORM, HEAT, RDR, SCAT, TEAM and CMP. Each left its table or chart
     100% in view below the command bar, and `scrollWidth` stayed 375.

### App rules

- **CSP:** no `style=`, no inline handlers and no inline script in `terminal.js` or either `index.html`. Scripts are
  same-origin only.
- **esc():**
  - I wrapped `Regista.api` so that every name, label, note, club, title, definition, rule, body part and outcome came
    back with `<img src=x data-pwn=1>` appended.
  - Then I ran SIM, SHOT, FORM, HEAT, CMP and SCAT for players not yet loaded, opened evidence and played a shot.
  - The payload showed as text in 25 places, and no element was created.
- **Regista.store only:** no direct storage calls in terminal.js, and no storage keys outside the `regista.demo.v1.`
  prefix.
- **Read only:** the network log for the whole session shows only GET requests from the Terminal. The one POST was the
  Scout agent, which I ran on purpose for SC-16. The one HEAD was mine.
- **No ratings:** `rating`, `attributes` and `hidden` appear nowhere in the new endpoints' answers or in `/api/metrics`.

## Needs Zaid's decision

1. **Merge and deploy.** Whether to merge `ux/terminal` into `main`, which deploys through CI, is your call. Nothing is
   pushed.
2. **Ctrl+K on a Mac.** The spec asks for Cmd/Ctrl+K, so on `/scout` Ctrl+K is taken in every text field too. On a Mac,
   Ctrl+K normally deletes to the end of the line there (report text, message composer). Keep it, or take Ctrl+K only
   off the Mac?
3. **Left open by the build, unchanged here:**
   - An ambiguous name opens the player with the most minutes.
   - Clubs tied on team penalty xG get ranks 2 to 6. That ranking is the engine's.
   - Physical values in RANK lines and screener cells have no unit.
   - Help has no focus trap.

## Not checked

- A screen reader end to end, Safari and Firefox, and the live app.
- The panels redraw on `requestAnimationFrame`, so in a background tab a panel waiting for data stays on "Loading…"
  until the tab is shown. This is normal browser behaviour, and I worked around it in the hidden pane by running
  commands, which wait for their data.

## Final test run

- `python3 -m pytest -q`: 830 passed, 13 deselected.
- `python3 -m pytest -q -m slow`: 13 passed.
