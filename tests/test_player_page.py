"""The player profile page (/players/{global_id}): served for any well-formed id, same-origin scripts only, and the
slots other Scout work fills (the Foundry summary, Add a match) present without depending on them.

Static checks on the page and its script, plus the routes. The page's behaviour in a browser (desktop and 375 px) is
checked by hand against a local run; see the PR that introduced it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PLAYER = Path(__file__).resolve().parents[1] / "src/regista/static/player"


@pytest.fixture(scope="module")
def page() -> str:
    return (PLAYER / "index.html").read_text()


@pytest.fixture(scope="module")
def script() -> str:
    return (PLAYER / "player.js").read_text()


@pytest.fixture(scope="module")
def client() -> TestClient:
    from regista import api

    return TestClient(api.app)


def test_the_page_serves_for_a_player_with_the_csp(client, page):
    r = client.get("/players/pl_ash_09")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.text == page
    assert "script-src 'self'" in r.headers["content-security-policy"]


def test_a_bad_id_gets_400_and_an_unknown_one_still_serves_the_page(client):
    for bad in ("NOT-AN-ID", "pl_", "pl_Ash_09", "x" * 50, "pl_ash_09.json"):
        assert client.get(f"/players/{bad}").status_code == 400, bad
    # The page asks the API, which answers 404 for players not in the league; the page then says "No such player".
    r = client.get("/players/pl_nobody_99")
    assert r.status_code == 200 and 'id="missing"' in r.text and "No such player" in r.text


def test_scripts_are_same_origin_files_and_none_is_inline(page):
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", page, flags=re.S)
    assert scripts
    for attrs, body in scripts:
        assert body.strip() == "", "no inline script: the CSP allows only script-src 'self'"
        src = re.search(r'src="([^"]+)"', attrs).group(1)
        assert src.startswith("/static/") and not src.startswith("//"), src
    assert not re.search(r"\son[a-z]+=", page), "no inline event handlers"
    for href in re.findall(r'<link[^>]+href="([^"]+)"', page):
        assert href.startswith("/static/"), href


def test_the_files_the_page_loads_are_served(client, page):
    for path in re.findall(r'(?:src|href)="(/static/[^"]+)"', page):
        if path.endswith("add-match.js"):
            continue  # owned by the add-a-match work; the page works without it
        assert client.get(path).status_code == 200, path


def test_the_page_has_its_sections_and_the_slots_others_fill(page):
    assert '<nav class="views"' in page and 'href="/"' in page and 'href="/scout" aria-current="page"' in page
    assert ">← Back to Scout<" in page
    for section in ('id="summary"', 'id="addMatch"', 'id="reelVideo"', 'id="headline"', 'id="touchMap"', 'id="momentGrid"',
                    'id="matchList"', 'id="evidence"'):
        assert section in page, section
    assert '<script src="/static/player/add-match.js" defer></script>' in page
    assert "Every number links to the moment it came from" in page
    assert "synthetic player from Regista's generated league" in page
    # The summary slot shows nothing until a summary exists: no placeholder sentence.
    assert re.search(r'<section id="summary"[^>]*hidden></section>', page)


def test_the_script_does_not_depend_on_add_match(script):
    # add-match.js may be missing (404): nothing in player.js calls into it; it may follow the profile instead.
    assert "window.RegistaPlayer" in script and "regista:profile" in script
    assert "AddMatch" not in script and "addMatch" not in script


def test_links_into_the_clip_view_and_the_reel(script):
    assert "/?match=${encodeURIComponent(matchId)}&player=${encodeURIComponent(playerId)}&clip=${encodeURIComponent(clipId)}" in script
    assert "/?match=${encodeURIComponent(matchId)}&t=" in script
    assert "/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}" in script
    assert "/reel.mp4?n=${REEL_N}" in script and "&tag=${encodeURIComponent(tag)}" in script
    assert "e.status === 404" in script and "showMissing" in script


def test_words_people_read(page, script):
    # Labels come from the API's stat_labels; no raw keys or "per90" reach the page.
    assert "stat_labels" in script
    text = re.sub(r"<[^>]+>", " ", page)
    assert "per90" not in text and "_" not in text
    for shown in re.findall(r"`([^`]*)`", script):
        visible = re.sub(r"\$\{[^}]*\}|<[^>]+>", " ", shown)
        assert "per90" not in visible, shown


def test_text_from_the_api_is_escaped(script):
    # Every innerHTML assignment builds from esc()'d values; titles and names also go through textContent.
    assert "const { esc," in script
    for raw in ("${m.title}", "${p.name}", "${src.title}", "${text}", "${where("):
        assert raw not in script, raw
    calls = re.findall(r"(.{4})where\(", script)  # where() returns plain text: every call is escaped
    assert calls and all(c == "esc(" for c in calls), calls


def test_the_script_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    res = subprocess.run([node, "--check", str(PLAYER / "player.js")], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
