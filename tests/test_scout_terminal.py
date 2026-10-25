"""The Scout terminal: the Terminal section of /scout (static/scout/terminal.js and terminal.css), ported from the sandbox
design. These tests pin what the page code must keep: the section in the left panel, the Content Security Policy rules
(no inline script, handlers or style attributes; data colours and widths go through element.style), escaping, per-visitor
workspaces through Regista.store only, reads only, no hidden ratings, the complete evidence behind every number, and the
four fixes the sandbox reviewers left open. Its behaviour in a browser (1440 and 375 px) is checked by hand against a
local offline run; see docs/redesign/terminal/build.md.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/regista/static"
SCOUT = STATIC / "scout"


@pytest.fixture(scope="module")
def page() -> str:
    from regista import api

    r = TestClient(api.app).get("/scout")
    assert r.status_code == 200
    return r.text


@pytest.fixture(scope="module")
def js() -> str:
    return (SCOUT / "terminal.js").read_text()


@pytest.fixture(scope="module")
def css() -> str:
    return (SCOUT / "terminal.css").read_text()


def _fn(js: str, name: str) -> str:
    """The source of one top-level function in terminal.js (up to the next function at the same indent)."""
    start = js.index(f"function {name}(")
    nxt = re.search(r"\n  (?:async )?function |\n  const [A-Za-z_]+ = ", js[start + 10:])
    return js[start:start + 10 + (nxt.start() if nxt else len(js))]


def test_the_terminal_is_a_section_of_scout_with_its_own_files(page):
    nav = re.search(r'<div class="subviews" role="group" aria-label="Scout sections">(.*?)</div>', page, flags=re.S).group(1)
    assert '<a href="/scout#find" data-section="find">Find players</a><a href="/scout#terminal" data-section="terminal">Terminal</a>' in nav
    assert '<div class="pv" data-panel="terminal" hidden>' in page
    for el in ('id="txForm"', 'id="txIn"', 'id="txAc"', 'id="txOut"', 'id="txKeys"', 'id="txHelp"', 'id="txMeta"', 'id="txSel"',
               'id="txGrid"', 'id="txTip"'):
        assert el in page, el
    # the command line is a labelled combobox; Enter is <GO>
    assert 'role="combobox" aria-label="Command line"' in page and 'aria-label="Go">&lt;GO&gt;</button>' in page
    assert '<link rel="stylesheet" href="/static/scout/terminal.css">' in page
    assert page.index("/static/scout/scout.js") < page.index('<script src="/static/scout/terminal.js" defer></script>')
    # the profile page repeats Scout's sections in its left panel
    assert 'data-section="terminal">Terminal</a>' in (STATIC / "player/index.html").read_text()


def test_the_image_ships_the_terminals_files():
    patterns = re.search(r'regista = \[(.*?)\]', (ROOT / "pyproject.toml").read_text()).group(1)
    globs = [g.strip().strip('"') for g in patterns.split(",")]
    for f in ("static/scout/terminal.js", "static/scout/terminal.css"):
        assert any(fnmatch.fnmatch(f, g) for g in globs), f"{f} is not package data"
    from tests.test_packaging import _excluded

    assert not _excluded("src/regista/static/scout/terminal.js") and not _excluded("src/regista/static/scout/terminal.css")


def test_the_script_parses(js):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    assert subprocess.run([node, "--check", str(SCOUT / "terminal.js")], capture_output=True).returncode == 0


def test_the_csp_rules_hold(js, css):
    # no style attributes anywhere in the script's markup: shading, colours and widths are data attributes applied through
    # element.style after rendering
    assert "style=" not in js
    for attr in ("data-bg", "data-c", "data-g", "data-w", "data-l", "data-fg"):
        assert attr in js
    assert "function styleUp(root)" in js and "el.style.background" in js and "el.style.setProperty('--c'" in js
    # no inline handlers in the markup it writes, no eval, no external origins
    assert not re.search(r"\son[a-z]+=", js), "inline event handler in terminal.js markup"
    assert "eval(" not in js and "new Function" not in js and "http://" not in js
    # the left panel's router hides every [data-panel] that is not the section on screen: the terminal's own panels must
    # use another attribute, or opening Find players would hide them for good
    assert "data-panel" not in js and 'data-txp="' in js
    assert ".views" not in css and "#scout" not in css


def test_every_api_value_is_escaped_before_it_reaches_the_page(js):
    assert "const esc = R.esc;" in js
    assert "String(v ?? '').replace(" not in js            # no private escaper: the shared one also escapes the backtick
    # the values people and the API name: never interpolated into markup unescaped. Calls that escape what they are given
    # (esc, runBtn, the shared shirt) are cut out first; what is left of a line that writes markup must not name them.
    def strip_calls(text: str, names: tuple[str, ...]) -> str:
        out, i = [], 0
        pat = re.compile(r"\b(?:%s)\(" % "|".join(names))
        while True:
            m = pat.search(text, i)
            if not m:
                return "".join(out) + text[i:]
            out.append(text[i:m.start()])
            depth, j = 1, m.end()
            while j < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[j], 0)
                j += 1
            i = j
    rest = strip_calls(js, ("esc", "runBtn", "shirt", "out"))
    for line in rest.splitlines():
        if "<" not in line:
            continue
        m = re.search(r"\$\{[a-z]{1,3}\.(name|club|label|definition|rule|nationality|title|note|short_name|when|val)\}", line)
        assert not m, f"unescaped {m.group(0)} in: {line.strip()[:120]}"
    # video urls play only when they are the API's own relative paths
    assert "VIDEO.test(String(it.video))" in js


def test_workspaces_and_history_stay_in_this_browser_through_the_shared_store(js):
    assert "localStorage" not in js and "sessionStorage" not in js and "indexedDB" not in js
    assert "R.store.get(STORE_KEY, null)" in js and "R.store.set(STORE_KEY, store)" in js and "STORE_KEY = 'terminal'" in js
    assert "R.store.persistent()" in js and "not saved: storage blocked" in js
    assert "R.store.watch(" in js
    # three workspaces with Reset, each checked before use (unknown players, metrics and panels dropped)
    assert "function resetWs()" in js and "function clean(s)" in js and "[0, 1, 2]" in js


def test_the_terminal_only_reads(js):
    assert "method:" not in js and "'POST'" not in js and "'PUT'" not in js and "'DELETE'" not in js
    assert "fetch(" not in js            # every request goes through Regista.api, a GET without a key
    used = set(re.findall(r"R\.api\(`?'?(/api/[a-z/]+)", js))
    allowed = {"/api/metrics", "/api/season", "/api/teams", "/api/terminal/screen", "/api/terminal/scatter", "/api/players/", "/api/teams/"}
    assert used and used <= allowed, used - allowed
    assert "auth: true" not in js and "X-Regista-Token" not in js


def test_the_hidden_ratings_never_appear(js):
    from regista.season.league import ATTRIBUTE_KEYS

    for k in ("attributes", *ATTRIBUTE_KEYS):
        # a property read (.finishing) or a key as a whole string ('finishing'): words in comments may repeat them
        assert not re.search(rf"\.{k}\b|['\"]{k}['\"]", js), k


def test_evidence_is_complete_paged_through_the_api(js):
    # Zaid's decision: every moment behind a number, not the sandbox's first 10; the API pages it (500 a page) and the
    # terminal reads page after page until it has them all; no cap is shown to people
    ev = _fn(js, "evidenceReel") + js[js.index("const evidenceOf"):js.index("const settle")]
    assert "evidence_offset=${offset}" in ev and "offset >= ev.total" in ev and "out.complete" in ev
    assert "First " not in js and "exported" not in js and "on the app" not in js and "evidence_limit=10" not in js
    assert "EVIDENCE_PAGE = 500" in js


def test_fix_1_a_form_bar_counts_every_moment_of_its_match(js):
    # the bar's match filters the whole list (every page), so "N in this match" is the match's full count
    reel = _fn(js, "evidenceReel")
    assert "r.items.filter(it => it.match_id === match)" in reel and "past the first" not in reel
    assert "in this match" in _fn(js, "renderClips")
    assert "openEvidence(S.focus, formKey(p), t.dataset.mid)" in js


def test_fix_2_the_radar_never_draws_a_missing_percentile_as_the_0th(js):
    radar = _fn(js, "renderRadar")
    assert "pc == null ? 0 : pc" not in radar and "pc == null ? null" in radar
    out = _fn(js, "outline")
    assert "polyline" in out and "pts.every(Boolean)" in out
    # a focus player with no percentile on the template is not drawn, and the note says why
    assert "is not drawn:" in radar and "has no outline:" in radar and "are not scored on the" in radar


def test_fix_3_alt_1_goes_straight_into_the_screeners_table(js):
    assert "if (id === 'scrn' && focusGrid()) return;" in _fn(js, "goPanel")
    assert "goPanel(p.id)" in js and "goPanel(t.dataset.id)" in js
    # RANK leaves the leader's ranked number as the table's active cell, and HELP says how to get there
    assert "scrAct = rows.length ? { pid: rows[0].id, c: 1 } : null;" in _fn(js, "cmdRank")
    assert "(F1) goes straight into the screener's table" in js


def test_fix_4_commands_bring_their_subject_into_view_after_the_output_line(js):
    rank = _fn(js, "cmdRank")
    assert rank.index("out(`RANK") < rank.index("showPanel('scrn', true, target)")
    assert "trs[Math.min(2, trs.length - 1)]" in rank          # the first rows of the ranking, not 60% of the box
    run = _fn(js, "run")
    # a name brings the card and the Best table into view; panel commands load first, write the line, then scroll
    assert "showPanel('plyr', true, '.tx-best')" in run
    for cmd_out, cmd_show in (("out('', '', esc(line)", "showPanel(PANEL_CMD[head]"),):
        assert run.index(cmd_out) < run.index(cmd_show)
    assert "class=\"tx-mt tx-best\"" in js


def test_only_the_terminal_binds_cmd_k(js):
    assert "(e.metaKey || e.ctrlKey) && !e.altKey && String(e.key).toLowerCase() === 'k'" in js
    others = [p for p in STATIC.rglob("*.js") if p.name != "terminal.js" and re.search(r"metaKey|ctrlKey", p.read_text())]
    assert not others, others


def test_the_synthetic_data_is_said_once_and_numbers_say_where_they_come_from(js):
    assert js.count("SYNTHETIC DATA") == 1
    # every metric's definition, rule and source on hover and focus; noisy marked as the engine marks it
    tip = _fn(js, "tipHtml")
    assert "m.definition" in tip and "m.rule" in tip and "CAT.sources" in tip and "m.noisy" in tip and "m.min_attempts" in tip
    assert "rel.noisy" in js and "aria-describedby" in js
