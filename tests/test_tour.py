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
BEATS = ["hook",                                  # 1 the Goal reel
         "moments", "ask", "follow-up",           # 2 every moment; "his nutmegs", then "now the replays"
         "recap",                                 # 3 explained and recapped
         "video-in",                              # 4 the processed upload, agent by agent
         "foundry",                               # 5 Ask Foundry and How Regista answered
         "catalogue", "competition",              # 6 the catalogue, and the Fabric check
         "fans", "scout", "number", "terminal", "players",   # 7 the paths
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
        assert set(x) <= {"id", "url", "target", "above", "fill", "title", "text", "act"}, x["id"]
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
    assert by["ask"]["fill"]["value"] == "his nutmegs" and by["follow-up"]["fill"]["value"] == "now the replays"
    assert by["moments"]["url"] == by["ask"]["url"] == by["recap"]["url"] == "/?match=syn_0294&player=t_home_09"
    assert by["video-in"]["url"].startswith("/me?player=pl_bro_09")
    assert "Azure MCP Server" in by["foundry"]["text"] and "Regista's MCP server" in by["foundry"]["text"]
    assert "press Ask" in by["foundry"]["act"]   # the visitor asks Foundry; the tour never does
    # Fabric is not in the app: its check is quoted as text, with its date, and says where it runs
    assert "7,399 of 7,399" in by["competition"]["text"] and "26 October 2026" in by["competition"]["text"]
    assert "not in this app" in by["competition"]["text"]
    assert by["competition"]["url"] == "/scout#competition/co_esp_u19"
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
    assert [x["id"] for x in steps() if x.get("above")] == ["ask", "follow-up", "foundry"]
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
