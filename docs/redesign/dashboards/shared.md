# Shared pieces for the two dashboards

What was built for the /me and /scout builders to use, and how to use it. Nothing is committed yet. 633 tests pass.

## Files

| File | What it is |
|---|---|
| `static/player/profile-view.js` | The shared profile renderer: `Regista.profileView.render(root, profile, options)` |
| `static/player/index.html`, `player.js`, `player.css` | /players/{id} rebuilt on the renderer, with the scout bar on top |
| `static/player/add-match.js` | Unchanged behaviour; inline styles moved to classes (`am-stack`, `am-field`, `am-row`, `am-status`) |
| `static/shared/regista.js` | Adds `Regista.store` (per-visitor storage) and `Regista.sections` (left-panel sections) |
| `static/shared/demo.js` | The seeds and helpers both dashboards use: `Regista.demo` |
| `static/shared/regista.css` | Left-panel sections: indented links, yellow current section, phone second row |
| `static/shared/dashboard.css` | The sandbox's dashboard look, shared: `.pf`, panels, profile, Overview, messages, team, settings, scout pieces |
| `season_api.py` | `/api/season` clubs now carry `squad` (global_id, name, kit_number, position, starter) from league.json |
| `tests/test_shared_dashboard.py` (new), `test_player_page.py`, `test_product_page.py`, `test_player_api.py`, `test_season.py` | Updated and new tests |

## Load order on a dashboard page

```html
<link rel="stylesheet" href="/static/shared/regista.css">
<link rel="stylesheet" href="/static/shared/dashboard.css">
<link rel="stylesheet" href="/static/me/me.css">            <!-- or scout.css -->
...
<script src="/static/shared/regista.js"></script>
<script src="/static/shared/demo.js"></script>
<script src="/static/player/profile-view.js" defer></script>   <!-- /me only (My profile) -->
<script src="/static/me/me.js" defer></script>
```

Put `class="pf"` on `<main>` (or a wrapper) so the dashboard styles apply. A `.pf` inside a `.pf` adds no extra padding.

## Left panel

Markup for /me (for /scout use `/scout`, `Scout sections` and its seven sections):

```html
<nav class="views" aria-label="Views"><a href="/">Home</a><a href="/me" class="parent" aria-current="page">Player profile</a><div class="subviews" role="group" aria-label="Player profile sections"><a href="/me#overview" data-section="overview">Overview</a><a href="/me#profile" data-section="profile">My profile</a><a href="/me#matches" data-section="matches">Matches &amp; videos</a><a href="/me#messages" data-section="messages">Messages <span class="count" data-count="messages"></span></a><a href="/me#team" data-section="team">Team</a><a href="/me#settings" data-section="settings">Settings</a></div><a href="/scout">Scout</a></nav>
```

- Sections: /me `overview, profile, matches, messages, team, settings`; /scout `overview, find, shortlist, reports, messages, team, settings`.
- The subviews div sits right after the parent link. The parent link gets `class="parent"`. The current section gets `aria-current="true"`; the JS sets it.
- `const nav = Regista.sections({ fallback: 'overview', onChange(section, rest) { ... } })` reads the hash (`#messages/pl_bro_09` gives section `messages`, rest `['pl_bro_09']`). It marks the link, shows elements with `data-panel="<section>"` and hides the others, and calls `onChange` now and on every hash change. It returns `section()`, `rest()`, `go(section, ...rest)` and `count(section, n)`, which fills the `data-count` badge.
- Home's nav is unchanged. Tests: `tests/test_product_page.py` (`SECTIONS`, `SECTIONS_REQUIRED`). **Add `"me/index.html"` / `"scout/index.html"` to `SECTIONS_REQUIRED` once your page has its sections.**

## Shared profile renderer

```js
const view = Regista.profileView.render(rootElement, profile /* GET /api/players/{id} */, {
  bar: (slot, profile) => {},   // optional: fills a sticky slot above the header (the scout bar). Omit on /me.
  synthetic: true,              // false hides the one-line synthetic note
  stat: 'goals',                // optional: open this number's evidence at once (pass view.state().stat on a re-render)
});
view.pause(); view.identity(name, position, kitNumber); view.openStat(key); view.state(); // { stat, reelTag }
```

It draws the header (kit shirt), the summary (each sentence cites a number or a moment; older summary shapes still work), and best moments. Moments play in the stage; Play reel and the per-kind chips play the server reel `reel.mp4?n=6&tag=`. It also draws the numbers (tiles, ratios, "Show every number", evidence that plays), where they play, all moments (nine at a time), and the matches with W/D/L and Recap. It renders into a fresh child, so calling it again on the same root is safe. Error, retry and missing states belong to the page; see `player.js` for the pattern. Helpers on `Regista.profileView`: `key(m)` ("match_id|clip_id"), `short`, `roundName`, `pctText(p, pos)`, `vsLineFor(P)`, `best(P, n)`, `shirtSvg(kit, num, position, size)`, `paint(el)` (sets `data-w` widths), `clipHref`, `timeHref`, `matchHref`, `recapHref`, `reelUrl`, `POS`, `GROUP`, `HEADLINE`.

On /me#profile: `Regista.profileView.render(el, profile, {})`. Put the line "This is what scouts see when they open your profile." above it. To show My details edits, call `view.identity(d.name, d.position, d.kit_number)`. `add-match.js` runs only on /players/pl_…; /me has its own Add a match.

## Per-visitor store

`Regista.store.get(key, fallback)`, `set(key, value)`, `remove(key)`, `reset()`, `persistent()`, `watch(fn)`. The store uses the prefix `regista.demo.v1.`. Every access is guarded: with storage blocked, values live in memory and the seeds still show. Nothing touches storage at load.

Store keys (all managed by `Regista.demo`; prefer its functions): `conversations`, `shortlist`, `compare`, `reports`, `needs`, `details`, `settings.player`, `settings.scout`. The old Scout key `regista-scout-shortlist` is merged into `shortlist` (as Watching) on first read.

## Regista.demo (shared/demo.js)

- Constants: `NOTE` ("Messages, notes and reports are kept in this browser only."), `SCOUT` ('maya'), `PLAYER` ('pl_bro_09'), `SCOUTS` (maya, tomas, priya: name, initials, role, club, club_id, verified), `STAGES`, `VERDICTS`, `COMPARE_MAX` (3).
- Conversations (ONE store for both sides): `forPlayer(gid)`, `forScout(id = SCOUT)`, `conversation(id)`, `startConversation(scoutId, gid, playerName)` (idempotent), `send(id, 'player'|'scout', text, clips)`, `markRead(id, side)`, `setMuted(id, bool)`, `setBlocked(id, bool)`, `unread(side, who)`. A conversation looks like `{ id, scout, player, player_name, unread: { player, scout }, muted, blocked, msgs: [{ from, at, text, clips }] }`. `at` is epoch ms; show it with `whenText(at)` ("Today, 09:15", "21 Oct, 18:02") or `whenText(at, true)`. A blocked thread takes nothing from the scout.
- Clips in messages and reports are moment references: `ref(moment, match)` gives `{ match_id, clip_id, title, reason, round, opponent, t, video_url }`, and `refKey(r)` gives "match_id|clip_id". Play `video_url` as given.
- Shortlist: `shortlist()` returns `{ gid: { stage, note, at } }`. Also `setStage(gid, stage | '')`, `setNote(gid, note)` (adds as Watching), `onShortlist(gid)`, `compare()`, `setCompare(list)`, `toggleCompare(gid)`.
- Reports: `reports()`, `draftReport(gid, title)` (the open draft, or a new one with Summary, Strengths, Concerns), `saveReport(r)`, `dropReport(id)`, `saveReports(list)`. A report looks like `{ id, gid, author, at, verdict, draft, title, sections: [{ name, text, cites: [refs] }] }`.
- `needs()` / `saveNeeds(list)` (`{ id, title, pos, stat, pct }`); `details(gid)` / `saveDetails(gid, d)`; `settings('player'|'scout')` / `saveSettings(side, obj)`; `reset()` ("Reset this demo"); `seeds()`.

Seeds copied from the sandbox: Femi's three conversations (Maya, Tomás, Priya), Maya's three (Femi, Gino Mensah, Farid Vargas; the Femi thread is the same thread), the five-player shortlist with notes, the Femi report (Sign; five cited moments, four goals and a nutmeg, checked against the league by a test), and Fairhaven's three needs. Seed times are relative to today.

## Links from the scout bar (/players/{id})

| Button | Writes first | Goes to | /scout should |
|---|---|---|---|
| Stage select | `setStage` | stays | show the new stage |
| Message | `startConversation('maya', gid, name)` | `/scout#messages/<gid>` | open that conversation (create it if missing) |
| Compare | adds to shortlist as Watching if absent, then to `compare` | `/scout#shortlist/<gid>` | show the shortlist with gid ticked; compare at two or more |
| Notes | `setNote` (Save note) | stays | show the note |
| Write a report | `draftReport(gid, "Name, position, Club")` | `/scout#reports/<gid>` | open that player's draft |

Treat the hash as enough on its own: create whatever is missing, so a pasted link works too. The back link returns with `history.back()` when Scout sent the visitor, otherwise to `/scout#find`. Player cards should link to `/players/<gid>`.

## Checked

- In a browser against a local offline app (port 8071, no .env), at desktop and 375 px: Femi Toure, a goalkeeper (Jonah Eriksen), a missing player. Checked that evidence plays, the reel loads, the scout bar writes to the store, a player's reply shows up in Maya's inbox, reset works, there is no sideways scroll and there are no console errors. Home's panel looks the same.
- Not checked: the Foundry summary on the live app (offline used the stored summary), an uploaded friendly in the renderer (offline has none; the code handles `source: 'upload'`).
