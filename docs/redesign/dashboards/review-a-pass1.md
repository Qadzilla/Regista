# Review A, round 1: correctness and safety

Branch `ux/dashboards` at ebace2e (`git diff main...HEAD`). I read the code and ran the pages on a local offline app
(`REGISTA_DOTENV= uvicorn regista.api:app --port 8141`). Nothing was sent to the live app or Azure.

**Verdict: signed off.** I found nothing that must or should be fixed. Five small nits are listed at the end.

## What I checked

**Tests.** The full suite passes: 654 passed.

**Writes to the server.** The only writes are the ones that existed before:
- the upload (XHR `POST /api/player/uploads` with `X-Regista-Token`);
- the answers (`auth: true`);
- add-match's three POSTs.

The Scout agent's `POST /api/scout/ask` is a read. The network log for every section showed only GETs and the ask. The
upload and answer code is the same as on `main`: 401 clears the key and asks again, and 403 shows the server's detail.

**Live data and errors.** I stubbed `fetch` in the page to fake errors:
- **Scout agent.** A 429 reads "Too many questions just now…". A network failure reads "Regista could not answer just
  now…". The Foundry engine offline falls back to "Answered by Regista's rules (Foundry is not configured…)".
- **Filters.** A network failure shows the banner, and Retry recovers.
- **Missing players.** `/players/pl_nobody_99` shows the missing state. `/me?player=pl_nobody_99` opens Femi with the
  Switch player note, and every link in the left panel keeps `?player=`.
- **Is this you?** With a faked needs_review upload, the steps and times, Needs you, and the questions all rendered.
  Markup in the question text and in `named_as` showed as plain text, and a 401 on answering was handled.
- **Compare.** Compare and its evidence are real. The evidence played
  `/api/matches/rl_r01_ash_fai/clips/cl_t_home_09_000020.mp4`, picked by match + clip id.

**Per-visitor store.**
- **Shared conversations.** Femi's reply, with an attached moment, reached Maya's thread in the same browser. Her
  unread count changed. Her reply came back to Femi.
- **Block.** Femi's Block hid his compose box and disabled Maya's.
- **Reset.** Reset on /scout cleared every `regista.demo.v1.` key, and the seeds came back.
- **Blocked storage.** This is covered by node tests. Every direct `localStorage` use outside `Regista.store` (the old
  shortlist key in demo.js) is inside try/catch. The browser-only line shows in Messages and Settings on both dashboards.

**esc() and the CSP.**
- Markup typed into a reply (`<img onerror>`) showed as text on both sides and did not run.
- Grep found no inline handlers or `style=""` in markup strings.
- Bars and crests are set through `element.style`.
- The console showed no CSP errors.

**Clip identity.** Messages, reports, the picker, evidence and compare all key a clip by `match_id|clip_id`
(`PV.key`, `demo.refKey`).

**Layout.** At 375 px, no section of /scout scrolls sideways. Home's left panel is still Home (yellow), Player profile
and Scout.

## Nits (no change needed to sign off)

1. **A thread is marked read on phones before it is opened.** `me.js` `readOpen()` marks the open conversation read
   when Messages is entered on a phone, while only the list is showing. `scout.js` guards this with `threadShown`.
2. **The player stays in the address on /scout.** `/scout#messages/<id>` keeps the player after it opens. Shortlist and
   Reports drop it with `settle()`. A reload is harmless: `startConversation` is idempotent.
3. **Seed times can be in the future.** Seeds at `ago(0, '09:15')` are later than the visitor's clock before 09:15,
   so "Today, 09:15" sorts above messages that are already past.
4. **A storage event redraws over typing.** On `/players/{id}`, any storage event from another tab redraws the scout
   bar and drops a note being typed. On /scout, it redraws a draft report and can lose up to 300 ms of typing.
5. **A full clear leaves stale memory.** `Regista.store.watch` does not clear its memory copy when another tab clears
   all storage (`key === null`), so a stale value can be read back after a full clear. Reset this demo removes keys one
   by one, so this does not happen through Reset.
