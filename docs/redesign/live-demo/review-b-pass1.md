# Live demo: independent review B, round 1 (engineering)

Branch `feature/live-demo` at 7e28ecc compared with `main` (`git diff main...HEAD`, 31 files). The review looked at CSP,
escaping, `Regista.store`, writes, how the tour holds up across pages, whether the prerender is correct and what it costs
a 1-replica app, the probe workflow, tests, packaging and smoke. No fixes were made; this file is the only change.

## What I ran

- `python3 -m pytest -q`: **1189 passed**, 16 deselected (4 min 53 s). I did not re-run the slow suite. The diff touches
  nothing it covers (the generator and the season), and the verifier reports 16 passed.
- My own server: `REGISTA_DOTENV= REGISTA_PRERENDER=1 REGISTA_CACHE=<empty scratch folder>`, on 127.0.0.1:8271.
  - The warm-up finished in 84 s on this 10-core Mac: 51 of 51 rendered, 0 failed, 45 files, 37 MB. The Studio fact
    `cache.prerender` reports this.
  - During the warm-up, `/api/health` answered in 4-11 ms, and a clip that was not being warmed answered at once.
  - The server log has **no POST, PUT, PATCH or DELETE** after the whole session.
- Browser at 1440x900 and 375x812 (tab closed afterwards, viewport reset):
  - I started the tour from /demo and tried double-clicking Next, the paused card, a hash step on the same page
    (`#competitions` to `#competition/co_esp_u19`), Exit, and horizontal scroll on /demo (375 = 375).
  - No console errors.
  - Exit clears `regista.demo.v1.tour`, the card, `.tour-on` and `html.tour-running`.
- `curl -I /demo`: the strict CSP (`script-src 'self'`), `X-Frame-Options: DENY` and `nosniff` are all present.
- **The probe against the live app** (GETs only, `python3 src/regista/live_check.py`): 8 of 9 passed. The one failure is
  `/demo` (404), as expected, because the branch is not deployed. Health and all 7 services, the four existing pages,
  the catalogue totals (14 / 10 / 90) and a clip as video/mp4 all pass against the real app. So the health shape
  `_service()` reads (`cloud.foundry|cosmos|search`, plus top-level `azure_mcp`, `tracing`, `container_apps` and
  `storage`) matches production.

## Confirmed good

- **CSP.**
  - The new HTML has no inline script, no `on*=` handler and no `style=`. tour.js, tour.css, demo.js and demo.css are
    all external. The tour highlights with a class (`.tour-on`) and never touches `.style`. A test guards each of these.
  - Every page that loads the tour loads `regista.js` first and `tour.js` last, with `defer`.
- **Escaping.** Every value the tour card shows goes through `esc()`: the title, text, act and step count. demo.js
  escapes the icon, name and description (`cloud.model` included), and the catalogue sentence is set with `textContent`.
  The new `data-tour="stat-${esc(k)}"` in profile-view.js is escaped too.
- **Regista.store only.**
  - The tour keeps one key, `tour`, through `R.store.get`, `set` and `remove`. It never calls `localStorage` directly.
  - "Reset this demo" clears it with the rest of the prefix.
  - `load()` throws away an out-of-range index, so a stored state from an older step list cannot break a page.
- **No writes.**
  - The tour never fetches or submits. It fills a box only when the box is empty or holds one of the tour's own phrases,
    so it never overwrites what the visitor typed.
  - It sends an `input` event. On the terminal that only opens suggestions (`terminal.js` 2588); on Home it does
    nothing.
  - The warm-up sends plain in-process GETs with no key.
  - The probe sends plain GETs with no key and no cookie.
  - The workflow has `permissions: contents: read` and uses no secrets.
- **Prerender correctness.**
  - `warm.plan` reads the pages' own JSON, so the cache keys match what the pages ask for. The verifier showed this on
    an empty cache, and my run reproduced the same count of 51.
  - One planned part that fails is logged and skipped; it does not stop the rest.
  - `_render_once`'s per-file lock means a judge asking for a clip the warm-up is rendering waits for that one render
    and never renders it twice.
  - Warm GETs go through the app's two middlewares. Neither counts usage, and with no `Accept-Encoding` header the JSON
    comes back without gzip, so `json.loads` works.
- **Foundry limits.** There is one shared `AskLimiter` (`api._ask_limiter`) for Ask, Chat, the Scout agent and Foundry
  recaps, so the global caps really are global. No `REGISTA_ASK_*` is set in `infra/*.sh` or the Dockerfile, so the new
  defaults will take effect on deploy unless someone set one by hand on the Container App.
- **Probe and workflow.**
  - It runs daily at 07:23 UTC and on `workflow_dispatch`.
  - `--until 2026-11-11` passes without sending a request from that day on.
  - It uses the standard library only.
  - Worst-case run time is about 12 minutes (7 x 60 s, 120 s for the catalogue, 180 s for the clip), inside the
    15-minute timeout.
  - A network failure counts as a failed check, never a crash, and the exit code is 1 when anything fails.
- **Packaging and smoke.** The `pyproject` globs (`static/*/*.js|css|html`) cover `demo/` and `shared/tour.*`. The new
  files are in smoke's `STATIC_FILES`. `GET /demo` is in `tests/test_access.py`.

## Findings

### Must fix

None.

### Should fix

1. **A double-click on Next (or Back) skips a step.**
   - Reproduced on step 1: two clicks on the same Next button stored `{"i": 2}`, and the tour opened step 3, "Then you
     just ask", skipping step 2, "Every moment of a match".
   - Cause: `go()` reads `load()` again on the second click, after the first click has already saved `i + 1` and
     started `location.assign`. On a same-page step the card is re-rendered, so the second click lands on the new Next
     button.
   - Judges double-click buttons. Possible fixes: disable the bar's buttons once one is pressed, or carry the index the
     card was rendered for in the button (`data-tour-from`) and ignore clicks whose index is out of date.
2. **`_render_waiting` is no longer touched on one event loop only.**
   - The comment in `api.py` says "touched only on the event loop". The warm-up now calls `_video()` from its own
     thread, which runs its own loop through `asyncio.run` per request. So `_render_waiting["n"] += 1` and `-= 1` can
     run on two threads at once.
   - `+=` on a dict item is not atomic. A lost decrement leaves the counter one higher for good. After
     `REGISTA_RENDER_QUEUE` (24) such losses, every cold render would answer 503.
   - The window is small, because the warm-up sends one request at a time. Fix: guard it with a `threading.Lock`, or
     fix the comment and accept the risk knowingly.
3. **Load on the live replica is not measured, and the report should say what judges see meanwhile.**
   - The warm-up took 84 s here with the renderer's process pool (`video.py`: `workers = min(8, os.cpu_count() - 1)`).
   - The live app has 1.0 CPU and 2 GiB. Inside the container, `os.cpu_count()` reports the host's cores, not the
     quota, so each render may fork several processes onto one CPU.
   - The tour adds new renders to the featured player's. In my run, 19 of the 45 cached files exist only because of the
     tour: 17 clips from league and catalogue matches, and 2 joined reels. Expect several minutes of a busy CPU after
     every deploy, overlapping the season and catalogue warm-ups that the plan's catalogue GETs also start.
   - After the deploy: read the Studio's `prerender` started and finished times, and time `/api/health` and a page load
     during the warm-up. If it hurts, cap the renderer's workers at the cgroup quota for the warm-up thread. Either way,
     do not deploy in the hours before a judge is likely to look.
4. **The cost note leaves out what happens at the credit limit.**
   - build.md bounds Foundry at about $3.30 a day, at most about $50 over judging. CLAUDE.md §4.1 says the Azure for
     Students subscription "stops at the credit: no card" ($100). If spending reaches the credit, Azure disables the
     subscription and the live app goes down during judging.
   - The report should state the credit left today (Cost Management, read-only) and the worst case against it:
     $50 of Foundry, plus the base cost of about $10-15, plus whatever is already spent. If the margin is thin, keep
     `REGISTA_ASK_TOTAL_PER_DAY` at 300.
5. **The tour stops waiting for its element after 20 seconds (`WAIT_MS`).**
   - On a cold live revision, the profile, the competition page or the agent list can take longer than that: the
     catalogue builds on first use, and the probe allows 120 s for it.
   - When the wait runs out, the step shows its card but never highlights or scrolls. The judge sees a card pointing at
     nothing.
   - Fix: wait longer (60 s), or use a `MutationObserver` until the element appears. The warm-up now builds the
     catalogue at startup, which narrows this, but only after it has run.

### Nits

- If storage is blocked (some private windows), `Regista.store` keeps the tour in memory only, so the card disappears
  after the first navigation. It degrades quietly, but the tour cannot cross pages there. A hint on /demo, or carrying
  the step in a query parameter, would cover it.
- Tour state never expires. A judge who returns a day later sees "Tour paused · Step N" on every page until pressing
  Exit. Consider saving a timestamp and dropping the state after a few hours.
- The Studio does not show the tour's part of the warm-up. `studio/facts.py` copies only `running`, `total`, `rendered`,
  `failed`, `started_at` and `finished_at`, and drops `PRERENDER_PROGRESS["tour"]`, even though the docstring says it is
  "for the Studio". The totals already include it, so this is cosmetic.
- The workflow runs `python src/regista/live_check.py`, which puts `src/regista` first on `sys.path`. No file there
  shadows the standard library today, but a future `email.py` or `http/` would break the probe silently.
  `python -I src/regista/live_check.py` (on 3.11, `-I` implies `-P`) removes the risk.
- `actions/checkout@v4` and `setup-python@v5` are pinned by tag, not by SHA. That is acceptable for a read-only job with
  no secrets.
- The card is `role="dialog"` but does not receive focus when a step opens, and has no `aria-live`. A screen reader is
  not told the step changed after a same-page Next. `aria-live="polite"` on the card would do.
- Going Back from Foundry (step 7) to "Then you just ask" (step 3) leaves the engine switch on Ask Microsoft Foundry,
  while step 3 says Data Search answers. Pressing Ask then spends a Foundry call. The switch is visible, so this is
  minor. The tour could say "with Data Search selected".
- The page check in `live_check` looks for the literal `REGI<span>STA</span>`. It is fine today, but it will break on
  any brand-markup change.
- `/demo`'s line "nothing you click changes anything": I agree with the verifier that "nothing you click changes
  Regista" is more exact (§2.9 per-visitor state).

## Sign-off

Signed off for engineering, with the five should-fix items above. None of them blocks a merge. Items 1 and 2 are small
code changes. Item 3 is a check to run on the live app after the deploy. Item 4 is a sentence and a look at the credit
balance. Item 5 is a one-line change.
