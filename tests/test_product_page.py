"""Home (/): the landing search, results across every match through each match's /chat, the match view with the stage,
the folded recap and the conversation panel, How it works; nothing from the Studio.

Static checks on the page and its script, plus the files it loads being served. The page's behaviour in a browser
(desktop and 375 px, both engines) is checked by hand; see docs/redesign/home.md and the PR that introduced it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PRODUCT = Path(__file__).resolve().parents[1] / "src/regista/static/product"


@pytest.fixture(scope="module")
def page() -> str:
    return (PRODUCT / "index.html").read_text()


@pytest.fixture(scope="module")
def script() -> str:
    return (PRODUCT / "app.js").read_text()


def test_the_page_loads_the_shared_helpers_then_the_timeline_then_its_script(page):
    order = [page.index(s) for s in ("/static/shared/regista.css", "/static/product/product.css", "/static/shared/regista.js",
                                     "/static/product/timeline.js", "/static/product/app.js")]
    assert order == sorted(order)
    assert 'id="timeline"' in page  # agent C's timeline component renders here


def test_the_files_the_page_loads_are_served():
    from regista import api

    c = TestClient(api.app)
    html = c.get("/").text
    assert "Every moment. Every highlight. Every player. Found in seconds." in html  # the landing's tagline
    assert '<h1 class="logo" id="promise">' in html and "Every touch, every replay, every player" not in html.split("<body>")[1]
    for path in ("/static/shared/regista.css", "/static/shared/regista.js", "/static/product/product.css", "/static/product/app.js"):
        assert c.get(path).status_code == 200, path


def test_one_ask_box_through_chat(page, script):
    assert "matchUrl('/chat')" in script and "history: chat.history" in script and "engine: eng" in script
    assert 'value="rules"' in page and 'value="foundry"' in page and ">Instant<" in page and ">Foundry<" in page
    # The separate Search / Ask Foundry / Chat buttons are gone from the page (the endpoints stay for the Studio and MCP).
    for gone in ("'/search", "/search?", "/ask'", "/ask`", 'id="ask"', 'id="chatToggle"', ">Ask Foundry<"):
        assert gone not in page + script, gone


def test_how_regista_answered_shows_the_trace_or_the_tools_and_says_when_no_model_ran(script):
    assert "How Regista answered" in script
    assert "out.trace" in script and "out.tools_used" in script
    assert "Regista\\'s own rules, with no AI model" in script
    assert "'regista-mcp'" in script and "'azure-mcp'" in script


def test_how_regista_answered_is_plain_words_first_with_the_exact_steps_one_click_further(script):
    for plain in ("Read the match", "Understood: ", "moments`", "Microsoft Foundry (${step.name}) wrote the reply",
                  "Searched the clip library with Azure AI Search", "through the Azure MCP Server", "Details: step names and times"):
        assert plain in script, plain
    assert "so Regista's rules wrote this reply." in script  # Foundry asked for, rules answered: said in the reply itself


def test_any_player_can_be_picked_and_dead_ends_offer_a_way_out(script):
    assert "/clips?player=${enc(pid)}" in script and "moment_counts" in script and "Players with moments" in script
    assert "out.suggest" in script and "send(s.message, { withState: s.state" in script  # the server's clearing follow-up, when it has one
    assert "send('start over'" in script and "Show all of ${pl.name}'s moments" in script  # else the fallback
    assert "Can\\'t reach Regista right now." in script and "Retry" in script


def test_the_landing_has_typing_prompts_and_no_example_buttons_and_tag_filters_stay(script, page):
    # Decided: no pitch copy and no example buttons on the landing; six prompts type in and out of the box instead.
    assert "const ASKS = [" not in script and 'id="examples"' not in page and 'class="lede"' not in page
    # "Shots from outside the box" left the prompts: the search has no distance filter, so it answered "any shot".
    assert "outside the box" not in script
    for prompt in ("Find me the best saves this season", "Show me every header this season", "Find me all the nutmegs",
                   "Show me take-ons in the final third", "Find me every assist, best first", "Show me Femi Toure\\'s goals, assists and shots"):
        assert prompt in script, prompt
    assert "e.key === 'Tab'" in script and "q.value = PROMPTS[typing.p]" in script  # Tab fills the prompt showing
    assert "prefers-reduced-motion: reduce" in script  # still for people who prefer less motion
    landing = page[page.index('<section class="landing"'):page.index("</section>", page.index('<section class="landing"'))]
    assert landing.index('id="q"') < landing.index(">Data Search<") < landing.index(">Ask Microsoft Foundry<")  # the switch under the box
    assert 'id="tagbar"' in page and "renderTagBar" in script


def test_no_inline_scripts_handlers_or_styles_for_the_content_security_policy(page, script):
    assert not re.search(r"<script>|\son[a-z]+=", page)
    assert "style=" not in page + script
    assert "createElement('style')" not in (PRODUCT / "timeline.js").read_text()
    assert 'rel="icon"' in page and (PRODUCT / "favicon.svg").exists()


def test_studio_work_is_not_on_the_product(page, script):
    for studio in ("/verdict", "/feedback", "identity-review", "Keep", "Drop", "Retrain", "needs your review", "Who's who",
                   "X-Regista-Token", "auth: true"):
        assert studio not in page + script, studio


def test_labels_are_plain_words_and_badges_are_honest(script):
    assert "R.reasonLabel(" in script and "R.tagLabel(" in script
    assert "startsWith('foundry:')" in script and "Labelled by Microsoft Foundry" in script
    assert "origin === 'vision'" in script and "Cut from video" in script
    assert "Read from Cosmos DB." in script  # the no-video card, worded as information


def test_reel_and_moments_use_the_export_endpoints(page, script):
    assert "/reel.mp4?clips=" in script and "/moments.csv?" in script
    assert "Play reel" in page and "Download reel" in page and "Export moments" in page


def test_running_on_shows_only_what_health_reports(page, script):
    fn = script[script.index("function runningOn(h)"):script.index("// The realism report is Markdown")]
    for icon, service, flag in (("foundry", "Microsoft Foundry", "h.cloud.foundry"), ("mcp", "Azure MCP Server", "h.azure_mcp"),
                                ("cosmos-db", "Azure Cosmos DB", "h.cloud.cosmos"), ("ai-search", "Azure AI Search", "h.cloud.search"),
                                ("container-apps", "Azure Container Apps", "h.container_apps"), ("storage", "Azure Storage", "h.storage"),
                                ("app-insights", "Application Insights", "h.tracing")):
        assert f"['{icon}', '{service}', {flag}," in fn, service
        assert (PRODUCT / "icons" / f"{icon}.svg").is_file(), icon
    assert "['agent-framework', 'Microsoft Agent Framework', true," in fn  # the code itself: always there
    assert ".filter(t => t[2])" in fn and "$('stack').hidden = tiles.length < 2;" in fn
    # Icon first, the full service name under it (Microsoft's icon terms: the name always beside the icon)
    assert fn.index("<img src=\"/static/product/icons/${esc(icon)}.svg\" alt=\"\"") < fn.index("<span>${esc(name)}</span>")
    assert "$('howOpen').click()" in fn  # a tile opens How it works
    landing = page[page.index('<section class="landing"'):page.index('<div class="work"')]
    assert landing.index('class="engine pill"') < landing.index('id="stack"')  # under the search and its switch
    assert 'id="builtOn"' not in page and "builtOn" not in script  # it replaces the footer's "Built on" line
    for svg in (PRODUCT / "icons").glob("*.svg"):
        text = svg.read_text()
        assert "<script" not in text and "javascript:" not in text, svg.name


def test_grid_videos_load_lazily(script):
    assert "IntersectionObserver" in script and 'preload="none"' in script


# ---------------------------------------------------------------------------- the Clip view beside the Scout view

VIEWS = [("/", "Home"), ("/me", "Player profile"), ("/scout", "Scout")]
# A dashboard's sections, indented under its link in the left panel (shared/regista.css .subviews, shared/regista.js
# sections()); /players/{id} shows Scout's. Home has none. A page listed in SECTIONS_REQUIRED must have them.
SECTIONS = {"/me": ["overview", "profile", "matches", "messages", "team", "settings"],
            "/scout": ["overview", "find", "terminal", "shortlist", "reports", "messages", "team", "settings"]}
SECTIONS_REQUIRED = {"player/index.html", "me/index.html", "scout/index.html"}


@pytest.mark.parametrize("page_file, current", [("product/index.html", "/"), ("scout/index.html", "/scout"),
                                                ("player/index.html", "/scout"), ("me/index.html", "/me")])
def test_every_view_has_the_same_left_panel_with_its_own_view_current(page_file, current):
    html = (PRODUCT.parent / page_file).read_text()
    header = re.search(r'<header class="top">(.*?)</header>', html, flags=re.S).group(1)
    assert "<nav" not in header and '<p class="brand">REGI<span>STA</span></p>' in header  # the views left the header
    navs = re.findall(r'<nav class="views" aria-label="Views">(.*?)</nav>', html, flags=re.S)
    assert len(navs) == 1
    nav = navs[0]
    sub = re.search(r'<div class="subviews" role="group" aria-label="[^"]+ sections">(.*?)</div>', nav, flags=re.S)
    assert sub or page_file not in SECTIONS_REQUIRED, "the dashboard's sections are missing from the left panel"
    if current == "/":
        assert sub is None  # Home's panel is the three views, unchanged
    mark = ' class="parent" aria-current="page"' if sub else ' aria-current="page"'
    links = "".join(f'<a href="{h}"{mark if h == current else ""}>{t}</a>' for h, t in VIEWS)
    assert re.sub(r'<div class="subviews".*?</div>', "", nav, flags=re.S) == links
    if sub:
        # Right after the current view's link: one link per section, to that view's #section, at most one marked.
        assert nav.index(sub.group(0)) == nav.index(f'<a href="{current}"') + len(f'<a href="{current}"{mark}>') + len(dict(VIEWS)[current]) + len("</a>")
        found = re.findall(rf'<a href="{re.escape(current)}#([a-z]+)" data-section="([a-z]+)"', sub.group(1))
        assert [a for a, _b in found] == [b for _a, b in found] == SECTIONS[current]
        assert sub.group(1).count('aria-current="true"') <= 1 and 'aria-current="page"' not in sub.group(1)
    # The panel sits beside the page's content: shell > nav + shell-main > main ... footer
    shell = html[html.index('<div class="shell">'):]
    assert shell.index('<nav class="views"') < shell.index('<div class="shell-main">') < shell.index("<main")
    assert shell.index("</footer>") < shell.index("</div>\n</div>")


def test_the_profile_page_marks_find_players_under_scout():
    html = (PRODUCT.parent / "player/index.html").read_text()
    assert '<a href="/scout#find" data-section="find" aria-current="true">Find players</a>' in html
    assert '<span class="count" data-count="messages"></span>' in html


def test_the_left_panel_is_styled_once_for_every_page():
    shared = (PRODUCT.parent / "shared/regista.css").read_text()
    assert ".shell {" in shared and ".views {" in shared and "position: sticky" in shared
    assert '.views a[aria-current="page"] { background: var(--accent); color: #111; }' in shared  # Regista yellow
    phone = shared[shared.index("@media (max-width: 720px)"):]
    assert "flex-direction: row" in phone and "overflow-x: auto" in phone  # a row of tabs on phones
    for css in ("product/product.css", "scout/scout.css", "player/player.css", "me/me.css"):
        assert ".views" not in (PRODUCT.parent / css).read_text(), css  # one rule, shared by every view
    js = (PRODUCT.parent / "shared/regista.js").read_text()
    assert "--top-h" in js and "--top-h" in shared  # the panel sticks below headers of any height
    # A dashboard's sections: indented under the view, the one on screen in yellow, the view's own link steps back,
    # a second row of tabs on phones; styled here only (dashboard.css styles no part of the panel either).
    assert '.views .subviews a[aria-current="true"] { background: var(--accent); color: #111;' in shared
    assert '.views a.parent[aria-current="page"] { background: transparent; color: var(--text); }' in shared
    assert ".subviews { flex-basis: 100%; flex-direction: row; order: 1;" in phone
    assert ".views" not in (PRODUCT.parent / "shared/dashboard.css").read_text()
    assert "function sections(" in js and "aria-current', 'true'" in js and "hashchange" in js


def test_league_matches_join_the_picker_lazily_after_the_featured_match(script):
    init = script[script.index("async function init()"):script.index("async function loadSeason()")]
    assert "loadSeason();" in init and "await loadSeason" not in init  # the first paint never waits for the league
    assert init.index("[first, ...state.matches.filter(m => m !== first)]") < init.index("loadSeason();")
    season = script[script.index("async function loadSeason()"):script.index("function ensureOption(")]
    assert "R.api('/api/season')" in season and "createElement('optgroup')" in season and "'Regista League 2026/27'" in season
    assert "esc(m.match_id)" in season and "esc(m.title" in season
    assert "catch (e) { return; }" in season  # no league on the server: the picker keeps its matches, no error shown


def link_id_pattern(script: str) -> re.Pattern:
    return re.compile(re.search(r"const LINK_ID = /(.+)/;", script).group(1))


@pytest.mark.parametrize("value, ok", [
    ("rl_r01_eas_bro", True), ("syn_0294", True), ("t_away_09", True), ("cl_t_away_09_000003", True),
    ("../../etc", False), ("<b>", False), ("", False), ("-x", False), (".hidden", False), ("a" * 121, False),
    ("rl_r01 eas", False), ("a/b", False), ("a\"b", False),
])
def test_deep_link_ids_are_checked_before_they_are_used(script, value, ok):
    pattern = link_id_pattern(script)
    assert bool(pattern.fullmatch(value)) is ok and ("!v.includes('..')" in script)


def test_deep_links_open_a_match_player_and_moment_and_fall_back_quietly(script):
    read = script[script.index("function readLink()"):script.index("const playerOfClip")]
    for key in ("'match'", "'player'", "'clip'", "q.get('t')"):
        assert key in read, key
    assert "Number.isFinite(t) && t >= 0" in read
    assert "/^cl_(.+)_\\d{6}$/" in script  # a clip names its player, so clip= alone selects them
    init = script[script.index("async function init()"):script.index("async function loadSeason()")]
    assert "await loadMatch(link.match, { player: link.player || playerOfClip(link.clip), quiet: true })" in init
    assert "await loadMatch(first.match_id)" in init  # a link that fails lands on the featured match ...
    assert "history.replaceState({ view: 'landing' }, '', location.pathname)" in init  # ... with the bad link cleared from the address
    assert "if (quiet && !previous) return false;" in script  # and says nothing about it
    linked = script[script.index("async function openLinked("):script.index("// ------------------------------------------------------------------ loading")]
    assert "state.all.has(link.clip)" in linked and "select(link.clip, true, true)" in linked
    assert "/video.mp4')}#t=${Math.round(link.t)}" in linked  # t= starts the full match there and picks the nearest moment
    assert "v.muted = true" in script  # browsers only autoplay a linked clip muted


def test_the_url_follows_the_match_player_and_moment_with_replace_state(script):
    sync = script[script.index("function syncUrl()"):script.index("// Back and Forward")]
    assert "history.replaceState(entry, '', url)" in sync  # within a view the entry is replaced, never pushed
    assert "pushState" not in sync
    assert "Object.assign(entry, { match: state.match, player: state.player, clip: state.picked })" in sync  # for popstate
    assert "q.set('player', state.player)" in sync and "q.set('clip', state.picked)" in sync
    assert "if (await loadMatch($('match').value)) syncUrl();" in script
    pick = script[script.index("async function pickPlayer("):script.index("// ------------------------------------------------------------------ the conversation")]
    assert pick.index("state.picked = null;") < pick.index("syncUrl();")  # a new player: the old moment leaves the URL


def test_a_league_player_links_to_their_scout_profile(page, script):
    assert 'id="scoutLink"' in page and 'id="scoutLinkLine"' in page
    fn = script[script.index("function scoutLink()"):script.index("function showPlayerMoments()")]
    assert "global_player_id" in fn and "/^pl_[a-z0-9_]{1,40}$/" in fn and "`/players/${enc(gid)}`" in fn
    assert "textContent" in fn and "innerHTML" not in fn  # the name is set as text


@pytest.fixture(scope="module")
def season_client(tmp_path_factory):
    """The real league's clubs with its first fixture only: quick to build, opened through the normal match API."""
    from regista import api
    from regista.season.league import new_league, save_league

    league = new_league(2026)
    small = {**league, "fixtures": league["fixtures"][:1]}
    tmp = tmp_path_factory.mktemp("product_season")
    mp = pytest.MonkeyPatch()
    mp.setattr(api, "SEASON_LEAGUE", save_league(small, tmp / "league.json"))
    mp.setattr(api, "SEASON_ROOT", tmp / "matches")
    mp.setattr(api, "CACHE_ROOT", tmp / "cache")
    yield TestClient(api.app), small["fixtures"][0]["match_id"]
    mp.undo()


def test_what_the_page_reads_for_a_league_match_is_there(season_client):
    c, mid = season_client
    s = c.get("/api/season").json()
    listed = [m for r in s["rounds"] for m in r["matches"]]
    assert [m["match_id"] for m in listed] == [mid] and listed[0]["title"].startswith("Round 1: ")
    assert f"{s['league']} {s['season']}" == "Regista League 2026/27"  # the picker group's label
    m = c.get(f"/api/matches/{mid}").json()
    assert m["title"] == listed[0]["title"]
    assert all(re.fullmatch(r"pl_[a-z0-9_]{1,40}", p["global_player_id"]) for p in m["players"])
    clips = c.get(f"/api/matches/{mid}/clips").json()
    assert clips and all(re.fullmatch(r"cl_(.+)_\d{6}", x["id"]).group(1) == x["player_id"] for x in clips)
    # every starter (and every substitute who came on): the player picker works
    assert {p["player_id"] for p in m["players"] if p["starter"]} <= {x["player_id"] for x in clips} <= {p["player_id"] for p in m["players"]}
    one = clips[0]
    assert c.get(f"/api/matches/{mid}/moments.csv", params={"player": one["player_id"]}).status_code == 200
    assert c.get("/api/matches/rl_r99_nob_ody").status_code == 404  # an unknown league id: the page falls back


def test_matches_outside_the_league_have_no_global_ids():
    from regista import api

    m = TestClient(api.app).get("/api/matches/syn_0294").json()
    assert not any(p.get("global_player_id") for p in m["players"])


# ---------------------------------------------------------------------------- Home: results across every match

def test_search_covers_every_match_through_each_matchs_own_chat(script):
    every = script[script.index("async function searchEvery("):script.index("function resetSearch()")]
    assert "matchUrl('/chat', m.id)" in every and "engine: 'rules'" in every  # the existing per-match search, no model
    assert "pool(list, PARALLEL" in every and "const PARALLEL = 6;" in script  # a few requests at a time, not all at once
    listing = script[script.index("function searchList()"):script.index("const nameOf")]
    assert "state.matches" in listing and "state.season" in listing  # the library and the league
    assert "m.source === 'cosmos'" in listing  # a match without its event stream cannot answer: left out, and said
    assert "await seasonReady" in every  # the league's list is in before a search starts
    assert "sorted(search.results, { sort: 'best' })" in every  # merged best first
    assert "Searching every match…" in every  # a visible loading state with progress


def test_ask_microsoft_foundry_writes_one_reply_from_the_best_match_and_says_so(script):
    every = script[script.index("async function searchEvery("):script.index("function resetSearch()")]
    assert "matchUrl('/chat', topMid)" in every and "engine: 'foundry'" in every and "history: chat.history" in every
    assert every.count("engine: 'foundry'") == 1  # one model call per question, never one per match
    assert "the match with the best result" in every and "The moments in the grid come from every match." in every


def test_a_name_means_one_player_across_matches(script):
    fn = script[script.index("function namesIn("):script.index("const resolved")]
    assert "every(w => said.has(w))" in fn  # the full name first, then the surname
    assert "search.names.has(c.player)" in script and "where a name in the question meant another player" in script


def test_the_conversation_lives_in_the_right_panel(page, script):
    aside = page[page.index('<aside class="convo panel" id="convo"'):page.index("</aside>")]
    for part in ('id="log"', 'id="askForm"', 'id="fq"', 'id="engineHint"', ">Data Search<", ">Ask Microsoft Foundry<"):
        assert part in aside, part
    assert page.count('id="log"') == 1  # the whole conversation, in the panel only
    layout = script[script.index("function layoutPanel()"):script.index("// ------------------------------------------------------------------ links into the page")]
    assert "state.view === 'match' || (state.view === 'results' && engine() === 'foundry')" in layout
    assert "How Regista answered · ${short} · ${esc(plural(plain.length, 'step'))}" in script  # one line per answer
    assert "Details: step names and times" in script  # steps and timings on demand


def test_the_match_view_has_no_explainer_line_a_folded_recap_and_actions_in_one_row(page, script):
    assert 'id="matchSub"' not in page and "subtitle" not in script  # the match's explainer line is gone
    recap = page[page.index('<details class="recap panel" id="recap"'):page.index("</details>", page.index('id="recap"'))]
    assert '<summary id="recapHead">Match recap</summary>' in recap
    assert 'name="recapEngine" value="rules"' in recap and ">Instant<" in recap and ">Foundry<" in recap  # its own switch, inside
    stage = page[page.index('<section class="stage panel" id="stage"'):page.index("</section>", page.index('id="stage"'))]
    assert stage.index('<div class="info">') < stage.index("</div>\n          <div class=\"actions\">")  # actions under the clip, not in .info
    css = (PRODUCT / "product.css").read_text()
    assert ".stage > .actions { grid-column: 1 / -1;" in css
    assert ".card.on {" not in css  # no yellow outline on the playing card
    assert "openRecap()" in script and "recapView.wanted" in script  # recap=1 opens the folded recap


def test_cards_open_their_match_and_the_url_follows_only_the_match_view(script):
    assert "openResult(card.dataset.mid, card.dataset.id)" in script and 'data-mid="${esc(r.mid)}"' in script
    sync = script[script.index("function syncUrl()"):script.index("// Back and Forward")]
    assert "let url = location.pathname;" in sync and "if (state.view === 'match' && state.match)" in sync  # the landing and the results are plain /


# ---------------------------------------------------------------------------- decisions on PR #32 (Zaid, 2026-10-23)

def test_back_moves_between_the_landing_the_results_and_a_match(script):
    show = script[script.index("function showView("):script.index("function layoutPanel()")]
    assert "history.pushState({ view: v, from: state.view }, '', location.pathname)" in show and "v !== state.view" in show
    assert "showView('results', { push: true })" in script  # the first search from the landing
    open_ = script[script.index("async function openResult("):script.index("// ------------------------------------------------------------------ the match view's conversation")]
    assert "showView('match', { sync: false, push: true })" in open_  # a card opens its match as a new entry
    pop = script[script.index("async function onPopState("):script.index("// The moment a link asked for")]
    assert "loadMatch(s.match, { player: s.player, quiet: true })" in pop and "search.asked ? 'results' : 'landing'" in pop
    assert "window.addEventListener('popstate', onPopState)" in script
    assert "history.state?.from === 'results'" in script and "history.back()" in script  # Back to results is the browser's Back


def test_the_pickers_live_in_the_match_view_and_the_landing_is_logo_and_search(page):
    header = re.search(r'<header class="top">(.*?)</header>', page, flags=re.S).group(1)
    assert "<select" not in header and "pick" not in header
    match = page[page.index('<section class="matchline"'):page.index("</section>", page.index('<section class="matchline"'))]
    assert match.index('id="matchTitle"') < match.index('<select id="match">') < match.index('<select id="player">')
    css = (PRODUCT / "product.css").read_text()
    assert ".top .pick" not in css and ".titleline {" in css and ".pick select {" in css


def test_the_meta_description_is_the_tagline(page):
    assert '<meta name="description" content="Every moment. Every highlight. Every player. Found in seconds.">' in page
    assert "Every touch, every replay" not in page


def test_result_cards_say_which_match_they_come_from(script):
    line = script[script.index("function cardLine(m)"):script.index("// Runs fn over items")]
    assert "`Round ${m.round} · ${short(m.home, m.home_name)} v ${short(m.away, m.away_name)}`" in line
    assert "if (!m.home_name) return matchName(m);" in line  # a library match: its own name
    assert "state.clubs = new Map((s.clubs || []).map(c => [c.club_id, c.short_name]))" in script
    render = script[script.index("  function render(emptyHtml)"):script.index("const visionOf")]
    assert "s === search ? new Map(searchList().list.map(m => [m.id, m.card])) : null" in render  # results only
    assert '<span class="from">${esc(cards.get(r.mid) || \'\')}</span>' in render


def test_on_phones_the_panel_comes_right_after_the_clip_in_the_match_view(script):
    css = (PRODUCT / "product.css").read_text()
    narrow = css[css.index("@media (max-width: 1100px)"):css.index("@media (max-width: 760px)")]
    assert ".work.with-convo.in-match .work-main, .work.with-convo.in-match .matchview { display: contents; }" in narrow
    assert ".work.in-match .convo { order: 0; }" in narrow and ".work.in-match .matchview > .stage ~ * { order: 1; }" in narrow
    assert "$('work').classList.toggle('in-match', state.view === 'match')" in script


def test_the_realism_report_is_offered_only_in_the_match_view(page, script):
    assert '<p id="reportLine" hidden>' in page
    assert "$('reportLine').hidden = v !== 'match';" in script


@pytest.mark.parametrize("page_file, words", [("me/index.html", '<a href="/">Home</a>'), ("player/index.html", '<a href="/">Home</a>'),
                                              ("scout/index.html", '<a href="/">Home</a>'), ("player/profile-view.js", ">Watch on Home<"),
                                              ("me/me.js", "'Open the match on Home'"), ("me/me.js", "'Read it on Home'"),
                                              ("studio/studio.js", ">see it on Home<")])
def test_other_pages_call_the_first_view_home(page_file, words):
    text = (PRODUCT.parent / page_file).read_text()
    assert words in text and "in Clips" not in text and '<a href="/">Clips</a>' not in text and "the Product</a>" not in text
