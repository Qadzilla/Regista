# Review A, round 2: correctness and safety

Branch `ux/dashboards` at 77abbfd (`git diff main...HEAD`). I read the code and ran the pages on a local offline app
(`REGISTA_DOTENV= uvicorn regista.api:app --host 127.0.0.1 --port 8141`) at 1440 px and 375 px. Nothing was sent to the
live app or Azure.

**Verdict: not signed off.** One thing should be fixed: the new "More filters" panel can hide a filter that is still on.
Everything else checks out.

## Should fix

**A collapsed "More filters" keeps its filter on, and nothing on screen says so.**
Where: `src/regista/static/scout/scout.js`, `moreFilters()`, the `fMore` click handler and `renderCards()`.

What happens:
1. On /scout#find, pick Fairhaven FC in the league table. More filters opens and 11 cards show.
2. Click "Fewer filters". The Club select is hidden, but the club filter stays on.
3. The page still shows 11 cards, and the line above them reads "11 players, sorted by minutes played".

Nothing near the cards names the club. The only sign is the pressed row in the league table, which now sits below all the
cards. Minimum minutes behaves the same way. The empty state also says "Try a lower minimum" while that field is hidden.
Before the round 1 fix, the Club field was always visible, so this is new.

Any one of these would fix it:
- name the active hidden filters in the results line ("11 players at Fairhaven FC, sorted by minutes played");
- keep the panel open while Club or Minimum minutes is set;
- show a count on the link ("More filters (1)").

## Round 1 fixes, checked

- **Find players layout.** At 1440 px the cards fill 4 columns (4 × 266 px). The order is Ask the Scout agent, then the
  three filters, then the cards, then the league table under them. The tagline, the badge and the engine paragraph are
  gone, and the engine picker stays. Picking a club in the table opens More filters and sets `?club=`. Reset clears the
  filters and the address.
- **Compare.** Femi Toure (forward), Dunmore's 6 (midfielder) and Eastwick's 3 (defender) give 8 rows, all per 90, with the
  highest value marked. The hover text and screen-reader label use plain words ("Best of the league's forwards"), and no
  "percentile" text is left. A number opens its moments, and the first one played
  `/api/matches/rl_r02_cal_bro/clips/cl_t_away_09_000010.mp4`, picked by match + clip id.
- **Card wording.** Cards read "Not above any of the league's midfielders". The Scout agent's lines read "1st of 18
  forwards", "1st of 18 midfielders" and "joint 2nd of 18 forwards". The `score` wording change in `season/scout.py` is
  covered by a new test case.
- **Caveats and Settings.**
  - The Password row is gone from Scout Settings.
  - Scout's Sign out cleared a key I put into sessionStorage and said so.
  - The profile page and /me My profile have no synthetic note; the footer keeps the one line.
- **Upload steps.** I faked a done upload by stubbing `fetch` with the real `UploadRecord` shape and the worker's real
  notes. The steps read "13 files saved", "2 answers from the player (2 yes)" and "2 identity calls". No `pv_` or `up_`
  ids show, and no "(s)" is left, in Matches & videos, Needs you or Recent activity.

## Fresh look: also checked

- **Tests.** The full suite passes: 656 passed.
- **Server writes.** These are the only writes in the dashboard scripts, and all existed before:
  - the upload XHR;
  - the answers;
  - add-match's three POSTs.

  `/api/scout/ask` is a read. The network log after sending a message showed only GETs. `/api/season` now carries each
  club's squad, which is read-only league data and has a test.
- **Shared conversation store.**
  - Femi sent a reply from /me with an attached moment, and it reached Maya's thread on /scout. Her unread count went up.
  - The clip card played its own match + clip video.
  - The markup typed into the reply (`<img onerror>`) showed as text and did not run on either side.
- **Reset and storage.**
  - Reset on /scout removed every `regista.demo.v1.` key and brought the seeds back.
  - The seeded moments still exist in the regenerated league (5 of 5).
  - Blocked storage is covered by the node tests.
- **esc() and the CSP.** I found no `style=""`, inline handlers or inline scripts. add-match.js now uses classes, which
  exist in `player.css`. Every interpolation I found that is not wrapped in esc() is a fixed string, a number, or text
  set with `textContent`.
- **Layout.** At 375 px, no section of /me scrolls sideways. The section on screen is marked in the left panel, and
  /players/{id} marks Scout as the parent.

## Nits (no change needed)

1. Maya's first seeded message says "Six goals in eleven games". Offline, Femi has 10 matches; it is 11 only with the
   uploaded friendly on the live app. The wording comes from the sandbox.
2. Scout's Sign out says "this tab no longer holds the admin key" even when the tab held none.
3. Round 1's nits 1 to 5 are unchanged: marking a thread read on phones, the player staying in `/scout#messages/<id>`,
   seed times later than the clock, a storage event redrawing over typing, and a full clear leaving stale memory.
