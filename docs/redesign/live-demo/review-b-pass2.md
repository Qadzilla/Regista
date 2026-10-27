# Live demo: independent review B, round 2 (engineering)

Branch `feature/live-demo` at a000c99 compared with `main` (`git diff main...HEAD`, 43 files). Round 1's fixes are in
a000c99 (report `fixes-1.md`). The lens is the same as in round 1: CSP, escaping, `Regista.store`, writes, how the tour
holds up across pages, whether the prerender is correct and what it costs a 1-replica app, the probe workflow, tests,
packaging and smoke. No fixes were made; this file is the only change.

## What I ran

- `python3 -m pytest -q` (REGISTA_DOTENV empty): **1195 passed**, 16 deselected (5 min 4 s).
- My own server, `REGISTA_DOTENV= uvicorn regista.api:app` on 127.0.0.1:8287 with an empty cache.
  - Port 8263 was already taken by reviewer A's server, so my first tour click landed on A's origin. The two of us
    shared one `regista.demo.v1.tour` key in the same browser. I moved to 8287 at once.
  - The server log has 124 GETs and **no POST, PUT, PATCH or DELETE**.
- Built-in browser at 1440x900 and 375x812. No console errors. Viewport reset and tab closed afterwards.
  - Started the tour from /demo and went step 1 → 2 across pages, then used the browser's Back.
  - Step 10 at 375: the highlighted element sat at 12-181 px, with the card from 609 px. No sideways scroll (375 = 375).
  - Step 11 at 375: `#txForm` sat at 154-194 px, filled with "most goals in England" and not sent.
  - Exit cleared the store key, the card, `.tour-on` and `html.tour-running`.
- The probe, `python3 -I src/regista/live_check.py --url http://127.0.0.1:8287 --services ""`: **9 of 9**, exit 0.
  `--until 2026-10-27` says judging is over and exits 0 without sending a request.
- **Render load in-process vs in a process pool.** This is the question round 1 left open for the 1-CPU replica. A
  scratch script started the app in uvicorn twice, on an empty cache:
  - once as it is here, with the renderer's process pool;
  - once with `usable_cpus` patched to 1, so renders run in-process as they now will on the live replica.

  Each run rendered three cold clips of the demo match while polling `/api/matches` every 50 ms:

  | Mode | 3 clips | `/api/matches` idle | during the renders |
  |---|---|---|---|
  | process pool (8 workers) | 5.6 s | 1.1 ms | median 5.8 ms, p95 11.2 ms, max 13.9 ms |
  | in-process (1 CPU) | 5.3 s | 1.3 ms | median 5.6 ms, p95 7.3 ms, max 17.1 ms |

  So rendering in the server's own process does not hold the event loop up (the GIL is not the bottleneck), and for
  short clips it is no slower. This is a 10-core Mac: it isolates the GIL question, not the 1-CPU quota.

## Round 1 findings: checked

| Round 1 | Now |
|---|---|
| Double-click on Next skips a step | Fixed: `e.detail > 1` or within 400 ms is ignored, and leaving a page disables the card's buttons (see should-fix 1 for one side effect) |
| `_render_waiting` changed on two threads | Fixed: changed under `_render_waiting_guard`, with a threaded test |
| Load on the 1-CPU replica | Partly fixed: `usable_cpus()` reads the cgroup v2/v1 quota, and the Studio shows it. In-process renders measured as harmless above. The live warm-up time is still unmeasured until a deploy |
| Cost note vs the student credit | Fixed: the daily cap stays at 300, and the reason is in `ASK_DEFAULTS`' comment and in fixes-1.md |
| `WAIT_MS` 20 s | Fixed: 60 s |
| Nits: Studio drops `tour` progress; `python -I`; Back from Foundry leaves the engine on Foundry | All fixed (`rulesEngine()` on steps marked `rules`) |

`usable_cpus` parsing is right:
- cgroup v2 `cpu.max` of `max 100000` means no quota;
- `50000 100000` rounds up to 1;
- v1 `-1` means no quota.

Without a cgroup namespace it falls back to the host count, which the Studio's `usable_cpus` would show after a deploy.

## Confirmed good

- **CSP.** `/demo` sends the same strict policy (`script-src 'self'`), `X-Frame-Options: DENY` and `nosniff`. The new
  and changed HTML has no inline script, handler or `style=`. tour.js only adds and removes classes.
- **Escaping.** The card escapes every value with `esc()`. demo.js escapes the icon, name and description, and the
  catalogue line uses `textContent`.
- **Store.** One key, through `R.store` only. `load()` drops an index that is out of range.
- **No writes.** No fetch in tour.js. `fill` only replaces an empty box or one of the tour's own phrases. The warm-up and
  the probe send plain GETs with no key. The workflow has `contents: read` and no secrets.
- **Prerender.** One thread, one request at a time, through the app's own routes, so the cache keys match. A part that
  fails is logged and skipped. All renders go through `_render_once`, `_render_slots` and the per-file lock.
- **Probe workflow.** Daily at 07:23 UTC plus `workflow_dispatch`, `timeout-minutes: 15`, `python -I`, standard library
  only, ending with `--until 2026-11-11`.
- **Packaging and smoke.** The pyproject globs cover `demo/*` and `shared/tour.*`. All five new files are in smoke's
  `STATIC_FILES`. `GET /demo` is in `tests/test_access.py`.

## Findings

### Must fix

None.

### Should fix

1. **The browser's Back after a tour step can show a dead card (bfcache). Plausible; not reproduced in the pane.**
   - When a step leaves the page, `go()` disables every button on the card, then calls `location.assign`.
   - The pages have no unload handler and no `Cache-Control: no-store`, so Chrome, Safari and Firefox may keep them in
     the back/forward cache.
   - A judge who presses the browser's Back then gets the old page restored as it was. Its scripts do not run again,
     and no `popstate` or `storage` event arrives. The card shows the old step with Back, Next, Hide and Exit all
     disabled until a reload.
   - The built-in browser pane reloaded the page instead of restoring it (`navigation.type` back_forward, the script
     ran again), so this is reasoned from the code, not seen.
   - Fix: one line in tour.js, `window.addEventListener('pageshow', (e) => { if (e.persisted) render(); });`. The card
     is rebuilt from the store with live buttons.
2. **The browser's Back from step 5 jumps the tour forward to step 6.**
   - Reproduced on the local server. The store held `{"i":4}` (step 5, "Video in: players upload", on
     `/me?player=pl_bro_09#matches`), and I loaded `/?match=syn_0294&player=t_home_09`, the page the browser's Back
     returns to.
   - The tour moved itself to **step 6, "Microsoft Foundry and MCP"**, saved `{"i":5}` and filled the box with "every
     nutmeg in the library".
   - Cause: `render()` moves the tour on whenever the current step is not here and the next one is. Steps 4 and 6 share
     the Clip view's URL with step 5's neighbours. Nothing is sent and the engine stays on Data Search, so this costs
     nothing. But a judge going back sees the tour skip ahead, and Back on the card then lands on step 5 again.
   - Fix: allow the automatic move only where the tour suggests following a link (step 9, Hector Santos's link). Mark
     that step, for example `"follows": true` on step 10, or skip the move when the navigation type is `back_forward`.

### Nits

- On Home, the comment `<!-- Or open one match … -->` now sits above the new tour line instead of the match picker
  (`product/index.html`).
- demo.js's comment says "Only what health says is running is shown", but Microsoft Agent Framework is always listed
  (`true`), as on Home. That is true of the code, which always runs the workflows, but the comment overstates.
- The tour state is shared by every tab of one origin by design. Two tabs on the tour move each other's place. I hit
  this with reviewer A's tab on 8263. A judge with two tabs open would see "Tour paused" in the other one. This is fine.
- The probe runs once a day, so an outage during judging can last up to about 24 hours before the email. Every 6 hours
  (`23 */6 * * *`) costs a few minutes of Actions a day and narrows that window. GitHub may also delay scheduled runs.
- Still open from round 1, unchanged: tour state never expires; the card has no `aria-live`; with blocked storage the
  tour cannot cross pages; `live_check` matches the literal brand markup `REGI<span>STA</span>`; actions are pinned by
  tag, not by SHA.
- `REGISTA_RENDER_CONCURRENCY` above 1 is now riskier on the live replica. With one usable CPU every render runs
  in-process, and the in-process path keeps the scene in module globals (`video._init_worker`). Two concurrent
  in-process renders would draw each other's frames. The default (1) is safe, and no script sets it. A one-line warning
  next to the variable, or a lock in `render_video`'s in-process branch, would prevent a surprise.

## Not checkable here (after the deploy, read-only)

- The Studio's cache facts should show `usable_cpus: 1`.
- Note the prerender's `started_at` and `finished_at` and its tour part, and time a page load while it runs.
- Take the tour once at 1440 and 375 px, and press the browser's Back once after a step that changes page (finding 1).

## Sign-off

Signed off for engineering. Both should-fix items are small changes in tour.js and cost nothing to fix. Neither one
writes anything or spends a Foundry call. Round 1's five should-fix items are fixed, and the one left to check is the
warm-up time on the live replica, after the deploy.
