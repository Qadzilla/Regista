"""The Product page (/): one ask box through /chat, the stage, the grid, How it works; nothing from the Studio.

Static checks on the page and its script, plus the files it loads being served. The page's behaviour in a browser
(desktop and 375 px, both engines) is checked by hand; see the PR that introduced it.
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
    assert "Every touch, every replay, every player, found in seconds." in c.get("/").text
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


def test_example_chips_and_tag_filters_come_from_the_moments_themselves(script, page):
    assert "const ASKS = [" in script and "tags.has(tag)" in script
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


def test_the_footer_names_only_what_health_reports(script):
    start = script.index("const on = [")
    built = script[start:script.index("$('builtOn')", start)]
    for service, flag in (("Microsoft Foundry", "h.cloud.foundry"), ("Azure MCP Server", "h.azure_mcp"), ("Azure Cosmos DB", "h.cloud.cosmos"),
                          ("Azure AI Search", "h.cloud.search"), ("Application Insights", "h.tracing")):
        assert re.search(re.escape(flag) + r" \? `?'?" + re.escape(service), built), service
    assert "Container Apps" not in built  # health does not report hosting, so the footer does not claim it
    assert "Copilot" not in script


def test_grid_videos_load_lazily(script):
    assert "IntersectionObserver" in script and 'preload="none"' in script


# ---------------------------------------------------------------------------- the Clip view beside the Scout view

def test_the_views_switch_marks_clips_as_current_and_is_styled_once_for_every_page(page):
    nav = re.search(r'<nav class="views" aria-label="Views">(.*?)</nav>', page).group(1)
    assert re.findall(r'<a href="([^"]+)"', nav) == ["/", "/scout"]
    assert '<a href="/" aria-current="page">Clips</a>' in nav and ">Scout</a>" in nav
    shared = (PRODUCT.parent / "shared/regista.css").read_text()
    assert ".views {" in shared and '.views a[aria-current="page"]' in shared
    assert ".views" not in (PRODUCT / "product.css").read_text()  # one rule, shared by the Scout and profile pages


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
    assert "history.replaceState(null, '', location.pathname)" in init  # ... with the bad link cleared from the address
    assert "if (quiet && !previous) return false;" in script  # and says nothing about it
    linked = script[script.index("async function openLinked("):script.index("// ------------------------------------------------------------------ loading")]
    assert "state.all.has(link.clip)" in linked and "select(link.clip, true, true)" in linked
    assert "/video.mp4')}#t=${Math.round(link.t)}" in linked  # t= starts the full match there and picks the nearest moment
    assert "v.muted = true" in script  # browsers only autoplay a linked clip muted


def test_the_url_follows_the_match_player_and_moment_with_replace_state(script):
    sync = script[script.index("function syncUrl()"):script.index("// The moment a link asked for")]
    assert "history.replaceState(null, '', url)" in sync and "pushState" not in script
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
    assert {x["player_id"] for x in clips} == {p["player_id"] for p in m["players"] if p["starter"]}  # every starter: the player picker works
    one = clips[0]
    assert c.get(f"/api/matches/{mid}/moments.csv", params={"player": one["player_id"]}).status_code == 200
    assert c.get("/api/matches/rl_r99_nob_ody").status_code == 404  # an unknown league id: the page falls back


def test_matches_outside_the_league_have_no_global_ids():
    from regista import api

    m = TestClient(api.app).get("/api/matches/syn_0294").json()
    assert not any(p.get("global_player_id") for p in m["players"])
