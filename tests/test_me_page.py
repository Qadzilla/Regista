"""The Player dashboard (/me): six sections under Player profile in the left panel, drawn by me.js on top of the shared
pieces (shared/regista.js, shared/demo.js, player/profile-view.js, shared/dashboard.css).

Static checks on the page and its script: the sections and their panels, the scripts and styles it loads and in which
order, the CSP rules (no inline script, handler or style), what stays live (uploads, "Is this you?", the profile) and what
stays in this browser (messages, My details, settings through Regista.demo, never storage directly). The page's behaviour
in a browser (desktop and 375 px, offline) is checked by hand against a local run; see docs/redesign/dashboards/me.md.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parents[1] / "src/regista/static"
ME = STATIC / "me"
SECTIONS = ["overview", "profile", "matches", "messages", "team", "settings"]


@pytest.fixture(scope="module")
def page() -> str:
    return (ME / "index.html").read_text()


@pytest.fixture(scope="module")
def script() -> str:
    return (ME / "me.js").read_text()


@pytest.fixture(scope="module")
def client() -> TestClient:
    from regista import api

    return TestClient(api.app)


def test_the_page_loads_the_shared_pieces_in_order(page):
    scripts = re.findall(r'<script src="([^"]+)"', page)
    assert scripts == ["/static/shared/regista.js", "/static/shared/demo.js", "/static/player/profile-view.js", "/static/me/me.js"]
    assert '<script src="/static/player/profile-view.js" defer></script>' in page and '<script src="/static/me/me.js" defer></script>' in page
    styles = re.findall(r'<link rel="stylesheet" href="([^"]+)"', page)
    assert styles == ["/static/shared/regista.css", "/static/shared/dashboard.css", "/static/me/me.css"]
    assert '<main class="pf" id="main">' in page  # the dashboard look applies


def test_me_and_its_section_addresses_serve_the_page(client, page):
    for params in ({}, {"player": "pl_bro_09"}, {"player": "not-a-player"}):
        r = client.get("/me", params=params)
        assert r.status_code == 200 and r.text == page
        assert "script-src 'self'" in r.headers["content-security-policy"]


def test_every_section_in_the_left_panel_has_its_panel(page):
    nav = re.search(r'<div class="subviews" role="group" aria-label="Player profile sections">(.*?)</div>', page, flags=re.S).group(1)
    assert re.findall(r'data-section="([a-z]+)"', nav) == SECTIONS
    assert 'aria-current="true"' not in nav  # me.js marks the section on screen (Regista.sections)
    assert '<span class="count" data-count="messages"></span>' in nav
    panels = re.findall(r'<div class="pv" data-panel="([a-z]+)" hidden>', page)
    assert panels == SECTIONS


def test_no_inline_script_handler_or_style(page, script):
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", page), "no inline script"
    assert not re.search(r"\son[a-z]+=", page), "no inline event handlers"
    assert "style=" not in page and "style=" not in script  # colours and widths are set on elements (element.style)
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script and "eval(" not in script


def test_the_live_parts_use_the_real_api(script):
    for endpoint in ("/api/health", "/api/season", "/api/players/${enc(gid)}", "/api/players?q=", "/api/players?position=FW&sort=goals",
                     "/api/player/uploads?global_id=", "/api/player/uploads/${enc(u.rec.upload_id)}/questions",
                     "/api/player/uploads/${enc(u.rec.upload_id)}/answers", "'/api/player/uploads'", "/recap?player="):
        assert endpoint in script, endpoint
    assert "x.setRequestHeader('X-Regista-Token', R.key.get())" in script  # uploads send the admin key
    assert "{ method: 'POST', body: { answers }, auth: true }" in script     # answers too
    assert "sessionStorage." not in script                                   # shared/regista.js keeps the key
    # Polling: 2 s while an agent works, 15 s otherwise, paused while the tab is hidden.
    assert "const POLL_MS = 2000;" in script and "const IDLE_MS = 15000;" in script and "document.hidden" in script


def test_the_profile_is_the_shared_page_without_the_scout_bar(page, script):
    assert "This is what scouts see when they open your profile." in page
    assert "PV.render($('meProfile'), S.P, { stat: keep.stat })" in script and "bar:" not in script
    assert "S.view.identity(d.name, d.position, d.kit_number, d)" in script  # My details (with foot, height, bio) on My profile


def test_the_default_player_and_the_player_in_the_address(script):
    assert "new URLSearchParams(location.search).get('player')" in script
    assert "GID_RE.test(wanted) ? wanted : demo.PLAYER" in script
    assert "url.searchParams.set('player', gid)" in script
    # The left panel's links keep the player the address names.
    assert "a.setAttribute('href', `/me${search}${a.dataset.section ? `#${a.dataset.section}` : ''}`)" in script


def test_per_visitor_content_goes_through_regista_demo_only(script):
    assert "localStorage" not in script and "R.store.get" not in script and "R.store.set" not in script
    for call in ("demo.forPlayer(S.gid)", "demo.send(c.id, 'player', text, S.draft)", "demo.markRead(c.id, 'player')",
                 "demo.setMuted(c.id, !c.muted)", "demo.setBlocked(c.id, !c.blocked)", "demo.saveDetails(S.gid,",
                 "demo.saveSettings('player', st)", "demo.reset()", "demo.unread('player', S.gid)", "R.store.watch("):
        assert call in script, call
    assert script.count("demo.NOTE") == 2  # one quiet line in Messages and one in Settings
    assert "Reset this demo" in (ME / "index.html").read_text()


def test_moments_are_known_by_match_and_clip(script):
    assert "demo.ref(m, match)" in script and "demo.refKey(" in script and "PV.key(m)" in script
    assert "clip_id ===" not in script  # never a clip id alone
    assert "startsWith('/api/matches/')" in script  # videos play from the API's relative urls only


def test_no_pitch_or_event_wording(page, script):
    for text in (page, script):
        assert "hackathon" not in text.lower() and "judge" not in text.lower() and "sandbox" not in text.lower()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_script_parses():
    subprocess.run(["node", "--check", str(ME / "me.js")], check=True)
