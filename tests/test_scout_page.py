"""The Scout page (/scout): served by the app, loading only same-origin scripts and no inline script (the CSP allows
``script-src 'self'`` only), with the hooks other Scout sessions build on.

The page's behaviour in a browser (desktop and 375 px) is checked by hand against a local run; see the PR that
introduced it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SCOUT = Path(__file__).resolve().parents[1] / "src/regista/static/scout"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from regista import api

    return TestClient(api.app)


@pytest.fixture(scope="module")
def page(client) -> str:
    r = client.get("/scout")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    return r.text


@pytest.fixture(scope="module")
def script() -> str:
    return (SCOUT / "scout.js").read_text()


def test_scout_serves_the_page_not_the_placeholder(page):
    assert page == (SCOUT / "index.html").read_text()
    assert "This page is being built" not in page
    assert '<nav class="views"' in page and 'href="/scout" aria-current="page"' in page and 'href="/"' in page


def test_the_page_loads_only_same_origin_scripts_and_no_inline_script(page):
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", page, flags=re.S)
    assert scripts, "the page loads its scripts"
    for attrs, body in scripts:
        src = re.search(r'\bsrc="([^"]+)"', attrs)
        assert src, f"inline script: {body[:60]!r}"
        assert body.strip() == ""
        assert src.group(1).startswith("/") and not src.group(1).startswith("//"), src.group(1)
    assert not re.search(r"\son[a-z]+\s*=", page), "inline event handler"
    srcs = [re.search(r'src="([^"]+)"', a).group(1) for a, _ in scripts]
    assert srcs == ["/static/shared/regista.js", "/static/scout/scout.js"]


def test_the_files_the_page_loads_are_served(client, page):
    for path in re.findall(r'(?:src|href)="(/static/[^"]+)"', page):
        assert client.get(path).status_code == 200, path
    assert "/static/scout/scout.css" in page


def test_the_page_says_its_players_are_synthetic(page):
    assert "synthetic players and clubs from Regista's generated" in page


def test_the_scout_agent_is_wired(page, script):
    assert 'id="scoutAsk"' in page and 'id="scoutAnswer"' in page and 'name="scoutEngine"' in page
    assert "coming in this build" not in page + script
    assert "function renderScoutAnswer(json)" in script and "R.api('/api/scout/ask', { method: 'POST', body: { q, engine } })" in script
    # who answered is always said, and a Foundry fallback to the rules shows its reason
    assert "Answered by Microsoft Foundry" in script and "Answered by Regista's rules" in script


def test_numbers_come_from_the_api_and_text_is_escaped(script):
    for endpoint in ("/api/season", "/api/players?", "/api/compare?ids="):
        assert endpoint in script
    assert "const esc = R.esc" in script
    # No raw stat keys in what people read: labels come from the API's stat catalogue.
    assert "per90" not in (SCOUT / "index.html").read_text()
    assert "localStorage" in script and "try {" in script
