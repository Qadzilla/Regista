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
    assert "Ran in-process: no model, no MCP." in script
    assert "'regista-mcp'" in script and "'azure-mcp'" in script


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
