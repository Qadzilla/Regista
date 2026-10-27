"""The judges' page (/demo) and the guided tour (static/shared/tour.js).

The tour's steps are plain data between markers in tour.js; these tests read them as JSON and check that every step's
URL is a page the app serves, that every element a step points at is in that page's HTML or is made by its scripts, that
the steps follow the demo video's beats, and that the tour only reads (it never clicks, submits or fetches for the
visitor, so a Microsoft Foundry question is only ever asked by the visitor pressing Ask). The tour's behaviour in a
browser (1440 and 375 px, every step, Hide, paused, Exit) is checked by hand: docs/redesign/live-demo/build.md.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "src/regista/static"
TOUR = STATIC / "shared/tour.js"

# A page's path -> the files that build it (its HTML, then the scripts it loads that can make a step's element).
PAGES = {
    "/": ["product/index.html", "product/app.js"],
    "/demo": ["demo/index.html", "demo/demo.js"],
    "/scout": ["scout/index.html", "scout/scout.js", "scout/terminal.js"],
    "/me": ["me/index.html", "me/me.js", "player/profile-view.js"],
    "/players/": ["player/index.html", "player/player.js", "player/profile-view.js"],
}
TOUR_PAGES = ["product/index.html", "demo/index.html", "scout/index.html", "me/index.html", "player/index.html"]

# The demo video's beats (docs/demo-storyboard.md), in order, as tour steps.
# Beat 7's paths are folded in where the tour already stands (fixes-1): fans, creators and broadcasters on the recap
# step (the recap, its reel, Download reel, Export moments), players on the upload step; scouts keep their own steps.
BEATS = ["hook",                                  # 1 the Goal reel
         "moments", "ask",                        # 2 every moment; "his nutmegs", then "now the replays"
         "recap",                                 # 3 explained and recapped (+ 7: fans, creators, broadcasters)
         "video-in",                              # 4 the processed upload, agent by agent (+ 7: players)
         "foundry",                               # 5 Ask Foundry and How Regista answered
         "catalogue",                             # 6 the catalogue, who filmed it, and the Fabric check (fixes-2: one step)
         "scout", "number", "terminal",           # 7 the scouts' path
         "close"]                                 # 8


def steps() -> list[dict]:
    text = TOUR.read_text()
    body = text[text.index("/* STEPS:BEGIN */"):text.index("/* STEPS:END */")]
    array = body[body.index("["):body.rindex("]") + 1]
    return json.loads(array)


def page_files(path: str) -> list[str]:
    return PAGES["/players/"] if path.startswith("/players/") else PAGES[path]


@pytest.fixture(scope="module")
def client() -> TestClient:
    from regista import api

    return TestClient(api.app)


def test_the_steps_follow_the_storyboard_beats_in_order():
    s = steps()
    assert [x["id"] for x in s] == BEATS
    for x in s:
        assert set(x) <= {"id", "url", "target", "above", "rules", "fill", "follows", "title", "text", "act"}, x["id"]
        assert x["title"] and x["text"] and len(x["title"]) <= 40, x["id"]
        assert len(x["text"]) <= 330 and len(x.get("act", "")) <= 120, x["id"]   # one or two plain sentences
        assert "_" not in x["text"] and "regista." not in x["text"].lower(), x["id"]   # no snake_case, no module names


def test_every_step_url_is_a_page_the_app_serves(client):
    for x in steps():
        u = urlsplit(x["url"])
        assert u.scheme == "" and u.netloc == "" and u.path.startswith("/"), x["url"]
        r = client.get(u.path, params=dict(parse_qsl(u.query)))
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), x["url"]
        assert "/static/shared/tour.js" in r.text and "/static/shared/tour.css" in r.text, x["url"]


def test_every_target_is_an_id_or_a_data_tour_attribute_that_its_page_has():
    headline_fw = re.search(r"FW: \[([^\]]+)\]", (STATIC / "player/profile-view.js").read_text()).group(1)
    for x in steps():
        files = "\n".join((STATIC / f).read_text() for f in page_files(urlsplit(x["url"]).path))
        t = x["target"]
        m_id = re.fullmatch(r"#([A-Za-z][\w-]*)", t)
        m_dt = re.fullmatch(r'\[data-tour="([a-z0-9_-]+)"\]', t)
        assert m_id or m_dt, f"{x['id']}: a target is #id or [data-tour=\"name\"], never a layout selector: {t}"
        if m_id:
            name = m_id.group(1)
            assert f'id="{name}"' in files, f"{x['id']}: no element with id {name} on {x['url']}"
        else:
            name = m_dt.group(1)
            if name.startswith("stat-"):   # a number's tile: data-tour="stat-${esc(k)}" for each headline stat
                assert 'data-tour="stat-${esc(k)}"' in files and f"'{name[5:]}'" in headline_fw, x["id"]
            else:
                assert f'data-tour="{name}"' in files or f"'data-tour': '{name}'" in files, f"{x['id']}: no {t} on {x['url']}"
        if "fill" in x:
            assert f'id="{x["fill"]["id"]}"' in files and x["fill"]["value"], x["id"]


def test_the_steps_say_what_the_live_app_shows():
    by = {x["id"]: x for x in steps()}
    assert by["hook"]["url"] == "/players/pl_bro_09" and "Goal reel" in by["hook"]["act"]
    assert by["ask"]["fill"]["value"] == "his nutmegs" and '"now the replays"' in by["ask"]["act"]
    assert by["moments"]["url"] == by["ask"]["url"] == by["recap"]["url"] == "/?match=syn_0294&player=t_home_09"
    assert by["video-in"]["url"].startswith("/me?player=pl_bro_09")
    assert "Azure MCP Server" in by["foundry"]["text"] and "Regista's MCP server" in by["foundry"]["text"]
    assert "press Ask" in by["foundry"]["act"]   # the visitor asks Foundry; the tour never does
    # fixes-2: the question asks beyond this match, so Foundry's tools have a reason to run, and the card says the
    # moments panel stays this match's; the chat's instructions send such a question to the library's search
    assert "other matches" in by["foundry"]["fill"]["value"] and "library" not in by["foundry"]["fill"]["value"]
    assert "the moments on the page stay this match's" in by["foundry"]["text"]
    from regista.cloud.foundry import CHAT_INSTRUCTIONS
    assert "search_index_query" in CHAT_INSTRUCTIONS and "When the user asks beyond this match" in CHAT_INSTRUCTIONS
    # Fabric is not in the app: its check is quoted as text, with its date, said first to be outside the app, on the
    # step whose title names it (fixes-1: not on the competition page, whose highlight is the uploads)
    cat = by["catalogue"]
    assert "Fabric" in cat["title"] and "Not in this app: " in cat["text"]
    assert "7,399 of 7,399" in cat["text"] and "26 October 2026" in cat["text"]
    # fixes-2: one step on the competition page, its highlight the competition's header (not a line the card repeats);
    # the 7,399 rows are 1,057 player-competition rows times 7 stats, so never "every catalogue number"
    assert cat["url"] == "/scout#competition/co_esp_u19" and cat["target"] == '[data-tour="co-head"]'
    assert "7,399 player numbers" in cat["text"] and "every catalogue number" not in cat["text"]
    assert "every catalogue number" not in (STATIC / "demo/index.html").read_text()
    # Only the upload step says Regista's vision agents watched footage: the league and the demo match come from the
    # generator (fixes-1), and nothing claims they were found in footage
    assert "synthetic league" in by["hook"]["text"] and "footage" not in by["hook"]["text"]
    assert "match generator" in by["moments"]["text"] and "watched" not in by["moments"]["text"]
    assert "vision agents" in by["video-in"]["text"] and "Azure Blob Storage" in by["video-in"]["text"]
    for x in steps():
        if x["id"] != "video-in":
            assert "vision" not in x["text"] and "watched" not in x["text"], x["id"]
    # An act line is something to do, never a caption
    assert all(not x["act"] or not x["act"].startswith("Measured") for x in steps())
    # No step points at a write: Add a match asks for the operator's key on the live app
    assert all(x["target"] != "#addBtn" for x in steps())
    assert "Who are the best U19 dribblers up front?" in by["scout"]["act"] and by["number"]["url"] == "/players/pl_pnr_11"
    assert by["terminal"]["fill"]["value"] == "most goals in England" and "Femi Toure" in by["terminal"]["act"]
    assert by["close"]["url"] == "/demo"
    for x in steps():
        assert "Copilot" not in x["text"] + x.get("act", "")


def test_the_tour_only_reads_and_keeps_its_place_in_the_visitor_store():
    js = TOUR.read_text()
    code = js[js.index("/* STEPS:END */"):]
    for never in ("fetch(", "R.api(", "requestSubmit", ".submit(", "XMLHttpRequest", "sendBeacon", "X-Regista-Token",
                  "localStorage", "sessionStorage", "eval(", ".style", "style=", "setAttribute('style'"):
        assert never not in code, never
    # It clicks nothing on the page: the only .click() would be a visitor's; it moves focus within its own card.
    assert ".click()" not in code
    assert "R.store.get(KEY" in code and "R.store.set(KEY" in code and "R.store.remove(KEY)" in code and "const KEY = 'tour'" in js
    assert "esc(step.title)" in code and "esc(step.text)" in code and "esc(step.act)" in code
    assert "[data-tour-start]" in code   # started by Home's and /demo's buttons
    assert "dispatchEvent(new Event('input'" in code   # a box is filled, never sent


def test_the_steps_that_say_data_search_put_the_switches_back_on_it():
    """Going Back from the Foundry step to a step that says no AI model is called must not leave Foundry picked."""
    s = steps()
    by = {x["id"]: x for x in s}
    ruled = [x["id"] for x in s if x.get("rules")]
    assert ruled == ["moments", "ask", "recap"]
    assert "With Data Search picked" in by["ask"]["text"] and not by["foundry"].get("rules")
    # every Clip view step before Foundry is ruled, so Back from Foundry lands on Data Search
    i = [x["id"] for x in s].index("foundry")
    assert all(x.get("rules") for x in s[:i] if x["url"].startswith("/?"))
    js = TOUR.read_text()
    fn = js[js.index("function rulesEngine()"):js.index("// Find the step's element")]
    assert 'input[name="fengine"][value="rules"]' in fn and "dispatchEvent(new Event('change'" in fn
    assert 'input[name="recapEngine"][value="rules"]' in fn and "fetch(" not in fn
    html = (STATIC / "product/index.html").read_text()
    assert 'name="fengine" value="rules"' in html and 'name="recapEngine" value="rules"' in html
    app = (STATIC / "product/app.js").read_text()
    assert "r.addEventListener('change', () => setEngine(r.value))" in app   # the change event is what sets all copies


def test_a_double_click_moves_one_step_and_a_slow_page_still_gets_its_highlight():
    js = TOUR.read_text()
    click = js[js.index("function onCardClick(e)"):js.index("document.addEventListener('click'")]
    assert "e.detail > 1" in click and "CLICK_GAP_MS" in click and "lastMove = now" in click
    assert "b.disabled = true" in js[js.index("function go(i)"):js.index("function exit()")]
    wait = int(re.search(r"const WAIT_MS = (\d+);", js).group(1))
    assert wait >= 60000   # the probe allows 120 s for a cold catalogue; a cold profile or competition page can take most of a minute


def test_the_demo_page_says_how_many_steps_the_tour_has():
    html = (STATIC / "demo/index.html").read_text()
    m = re.search(r"(\d+) short steps", html)
    assert m and int(m.group(1)) == len(steps())


def test_the_tour_script_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    res = subprocess.run([node, "--check", str(TOUR)], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr


@pytest.mark.parametrize("page_file", TOUR_PAGES)
def test_every_page_the_tour_visits_loads_it_last_with_no_inline_code(page_file):
    html = (STATIC / page_file).read_text()
    scripts = re.findall(r'<script src="([^"]+)"', html)
    assert scripts[0] == "/static/shared/regista.js" and scripts[-1] == "/static/shared/tour.js", page_file
    assert '<script src="/static/shared/tour.js" defer></script>' in html
    assert re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)[-1] == "/static/shared/tour.css"
    assert not re.search(r"<script>|\son[a-z]+=|\sstyle=", html), page_file


def test_phones_get_the_card_along_the_bottom_and_a_way_to_fold_it():
    css = (STATIC / "shared/tour.css").read_text()
    phone = css[css.index("@media (max-width: 720px)"):]
    assert ".tour { left: 8px; right: 8px; bottom: 8px;" in phone
    assert ".tour { position: fixed; right: 20px; bottom: 20px;" in css
    assert "prefers-reduced-motion: reduce" in css and ".tour-on" in css
    js = TOUR.read_text()
    assert "function reveal(el, step)" in js and "window.scrollBy" in js   # the element is brought above the card
    # phones: the element goes under the header (what it leads to shows above the strip), except where the answer
    # appears above it (the Ask box), and the pages' own scrolls stop above the strip
    assert "matchMedia('(max-width: 720px)')" in js and "!step.above" in js
    assert [x["id"] for x in steps() if x.get("above")] == ["ask", "foundry"]
    assert "scroll-padding-bottom" in phone
    assert "data-tour-act=\"min\"" in js and "data-tour-act=\"open\"" in js   # Hide folds the card to a pill


# ---------------------------------------------------------------------------- /demo

def test_the_demo_page_is_served_and_names_only_what_runs(client):
    r = client.get("/demo")
    assert r.status_code == 200 and "Take the tour" in r.text and "data-tour-start" in r.text
    html = (STATIC / "demo/index.html").read_text()
    assert r.text == html
    for p in ("/static/shared/regista.css", "/static/demo/demo.css", "/static/shared/tour.css", "/static/shared/regista.js",
              "/static/demo/demo.js", "/static/shared/tour.js"):
        assert client.get(p).status_code == 200, p
    # the four paths, each into its live view
    for who in ("Fans and creators", "Broadcasters", "Scouts", "Players"):
        assert who in html, who
    for href in re.findall(r'class="dm-path panel" href="([^"]+)"', html):
        u = urlsplit(href.replace("&amp;", "&"))
        assert client.get(u.path).status_code == 200, href
    assert len(re.findall(r'class="dm-path panel"', html)) == 4
    # what runs is read from /api/health, with Home's icons and flags; Fabric is named as checked outside the app
    js = (STATIC / "demo/demo.js").read_text()
    assert "R.api('/api/health')" in js and ".filter((s) => s[2])" in js
    home = (STATIC / "product/app.js").read_text()
    for icon, flag in (("foundry", "cloud.foundry"), ("mcp", "h.azure_mcp"), ("cosmos-db", "cloud.cosmos"), ("ai-search", "cloud.search"),
                       ("container-apps", "h.container_apps"), ("storage", "h.storage"), ("app-insights", "h.tracing")):
        assert f"['{icon}'," in js and flag in js and f"['{icon}'," in home, icon
        assert (STATIC / "product/icons" / f"{icon}.svg").is_file()
    assert "['agent-framework', 'Microsoft Agent Framework', true," in js
    assert "Checked outside this app" in html and "7,399 of 7,399" in html and "not in this app" in html
    assert "Synthetic data, by design" in html and "Copilot" not in html + js
    assert 'id="closeLinks"' in html and "https://github.com/Qadzilla/Regista" in html


def test_the_demo_page_has_no_inline_code_and_escapes_what_it_shows():
    html = (STATIC / "demo/index.html").read_text()
    js = (STATIC / "demo/demo.js").read_text()
    assert not re.search(r"<script>|\son[a-z]+=", html) and "style=" not in html + js
    assert "esc(name)" in js and "esc(what)" in js and "esc(icon)" in js
    assert "textContent" in js   # the catalogue's sentence is text, never markup


def test_home_offers_the_tour_and_the_judges_page():
    html = (STATIC / "product/index.html").read_text()
    landing = html[html.index('<section class="landing"'):html.index('<div class="work"')]
    assert "data-tour-start" in landing and 'href="/demo"' in landing
    assert landing.index('class="engine pill"') < landing.index("data-tour-start") < landing.index('id="stack"')


def test_the_goal_reel_plays_each_goal_once_in_match_order():
    js = (STATIC / "player/profile-view.js").read_text()
    assert 'data-r="goalreel" data-tour="goal-reel" hidden>Goal reel<' in js
    fn = js[js.index("function goalReelIds()"):js.index("function play(k, start = true, fallback = null)")]
    assert "includes('goal')" in fn and "m.reason === 'on_ball_main'" in fn and "CLIP_MP4.test" in fn
    assert "q('goalreel').hidden = !goalReelIds().length;" in js and "name: 'Goal reel'" in js


def test_only_a_followed_link_moves_the_tour_on_by_itself():
    """fixes-2: a second tab on the next step's page skipped the hook, and Back from the upload step jumped to Foundry.
    The tour moves on by itself only onto a step marked "follows" (Hector Santos, reached by a link from Find players),
    only on that page's own load, in a tab the visitor is looking at, and never on Back or Forward."""
    s = steps()
    assert [x["id"] for x in s if x.get("follows")] == ["number"]
    i = [x["id"] for x in s].index("number")
    assert "Hector Santos" in s[i - 1]["act"] and s[i - 1]["url"] != s[i]["url"]
    js = TOUR.read_text()
    code = js[js.index("/* STEPS:END */"):]
    fn = code[code.index("function render(arrived = false)"):code.index("const step = STEPS[s.i];")]
    assert "arrived && next && next.follows" in fn and "followedHere()" in fn and "save(s)" in fn
    assert fn.count("s.i += 1") == 1
    followed = code[code.index("function followedHere()"):code.index("function render(")]
    assert "document.visibilityState !== 'visible'" in followed and "'back_forward'" in followed
    # only the page's own first render may move it on: never another tab's change, a hash change or Back
    assert code.count("render(true)") == 1 and code.rstrip().endswith("render(true);\n})();")
    assert "R.store.watch((k) => { if (k === KEY || k === null) render(); });" in code
    assert "window.addEventListener('hashchange', () => render());" in code
    # a page restored from the back/forward cache draws its card again (go() left its buttons disabled)
    assert "window.addEventListener('pageshow', (e) => { if (e.persisted) render(); });" in code


def test_a_picked_moment_plays_where_a_phone_can_see_it():
    """fixes-2: on a phone the best-moments section is taller than the screen, so 'nearest' left the video above it."""
    js = (STATIC / "player/profile-view.js").read_text()
    start = js.index("function showStage(root)")
    fn = js[start:js.index("\n  }\n", start)]
    assert "matchMedia('(max-width: 720px)')" in fn and "'.pf-screen'" in fn and "block: narrow ? 'start' : 'nearest'" in fn
    assert "querySelector('.pf-best').scrollIntoView" not in js and js.count("showStage(el);") == 3
    assert ".pf-screen { scroll-margin-top: 12px; }" in (STATIC / "shared/dashboard.css").read_text()
