# Navigator: the views move to a left panel (item 2)

Builder: navigator. Branch `ux/app-redesign`. Scope: the views nav on Home (/), Player profile (/me), Scout (/scout) and
the profile (/players/{id}); the Studio keeps its own header and tabs (inventory I-027, N-9) and is unchanged.

## What changed, file by file

| file | change |
|---|---|
| shared/regista.css | The `.views` pill rules (old lines 22-27) are replaced by the left panel: `.shell` (220 px + content grid), `.shell-main`, `nav.views` (column, panel background, right border, sticky below the header), links muted, hover on --line, `:focus-visible` outline, current link `background: var(--accent); color: #111` (Regista yellow, as the sandbox's `.side`). At <= 720 px the panel becomes a row of tabs (row, pills, `overflow-x: auto`, not sticky). The comment holds the canonical markup. `--top-h` defaults to 52 px. |
| shared/regista.js | `trackHeader()`: sets `--top-h` to the height of `header.top` while it is sticky, 0 when the page lets it scroll away (Clips <= 760 px, Scout <= 600 px, profile <= 760 px), updated on resize. Skipped when there is no `document` (the Studio test runs this file in node). |
| product/index.html | The nav leaves the header (old line 15); the header keeps the brand and the Match and Player pickers. `<div class="shell">`, the nav, `<div class="shell-main">` wrap `main` and `footer`; the How it works `dialog` stays outside. |
| scout/index.html | Same move (old lines 15-19). Header keeps the brand. |
| player/index.html | Same move (old line 15). Scout is marked current. |
| me/index.html | Same move (old line 15). |
| scout/scout.css | Removed its `.views` override (old lines 14-17, navigation only); header comment updated. |
| player/player.css | Removed its `.views` override (old lines 12-15, navigation only). |
| tests/test_product_page.py | The Clips-switch test (old 119-125) is replaced by two: every page's header has the brand and no nav; exactly one `nav.views` per page with links Home (/), Player profile (/me), Scout (/scout) in that order and only the page's own view current (Scout on /players/{id}); nav before `shell-main` before `main`, footer inside the shell; the panel styled once in shared CSS, current in yellow, a row of tabs at <= 720 px, no page CSS restyles `.views`, `--top-h` in the CSS and the JS. |
| tests/test_player_api.py | `test_every_view_links_to_the_player_view` (served pages /, /scout, /players/{id}, /me): order now /, /me, /scout; labels Home, Player profile, Scout; exactly one aria-current. |

tests/test_scout_page.py:41 and tests/test_player_page.py:73 pass unchanged (they look for `<nav class="views"` and
Scout current, both still true).

## Inventory items checked

- I-006, I-020 (Clips header, pickers): header unchanged apart from the nav; pickers work (checked in the browser).
- I-007 brand: unchanged on every page.
- I-008, I-021, I-023, I-025: one nav per page, new labels and order, current view in yellow; /players/{id} marks Scout.
- I-009, I-022, I-024, I-026 (nav styles): one shared rule; the per-page overrides are gone. Each page's header rules
  (sticky, wrapping, phone rules) are untouched.
- I-027 Studio: unchanged; its page loads shared/regista.css but uses none of `.shell`, `.shell-main`, `.views`.
- I-028 tab titles: unchanged.
- I-035 recap jump below the sticky header (app.js:786-788): unaffected; the panel is beside the content, not above
  it, on desktop, and static on phones.

## Checked in the browser (local server, REGISTA_DOTENV empty, port 8071)

- 1400 px: /, /scout, /me, /players/pl_ash_09 show the panel with the right view in yellow; on / after scrolling,
  the panel stays at the header's bottom (header 62.5 px, `--top-h` 62.5 px).
- 740 px on /: header static, `--top-h` 0, panel sticks at the top; no horizontal scroll.
- 375 px: /, /scout, /me, /players/pl_ash_09 show a row of tabs under the header; page width 375 (no horizontal
  scroll).
- /studio: unchanged.

## Left for others / decisions

- Footer and cross-page links still say "Clips" (inventory N-8, I-029): page content, not the navigator; left as is.
- Home's own content (landing, results, match view) is the Home builder's; this change only wraps it in the shell.
