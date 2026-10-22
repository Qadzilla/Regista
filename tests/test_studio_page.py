"""The Studio page (/studio): static checks on the page and its script, plus the files it loads being served.

The Studio renders reviewers' notes, model output, uploaded rosters and job logs, so the main checks are about markup:
every template literal that holds HTML must be built with the ``html`` tag (which escapes every value through
Regista.esc), and ``put()`` is the only place innerHTML is written. The key stays in sessionStorage and the request
header. The page's behaviour in a browser (view key and admin key, 768 px) is checked by hand; see the PR that
introduced it.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "src/regista/static/studio"
SHARED = ROOT / "src/regista/static/shared"


@pytest.fixture(scope="module")
def page() -> str:
    return (STUDIO / "index.html").read_text()


@pytest.fixture(scope="module")
def script() -> str:
    return (STUDIO / "studio.js").read_text()


# ------------------------------------------------------------------------------------------------ a small JS scanner

def template_literals(src: str) -> list[tuple[str, str]]:
    """Every template literal in ``src`` as (tag, static text), nested ones included. Skips comments, strings and regex
    literals so a backtick or quote inside them is not mistaken for code."""
    out: list[tuple[str, str]] = []

    def code(i: int, stop_at_brace: bool) -> int:
        depth = 0
        prev = ""  # last significant character, to tell a regex literal from a division
        while i < len(src):
            c = src[i]
            if src.startswith("//", i):
                i = src.find("\n", i)
                i = len(src) if i < 0 else i
                continue
            if src.startswith("/*", i):
                i = src.index("*/", i) + 2
                continue
            if c in "'\"":
                i = string(i, c)
                prev = c
                continue
            if c == "`":
                # the tag is the identifier right before the backtick; with a space between, it counts as untagged
                m = re.search(r"[A-Za-z_$][\w$]*$", src[max(0, i - 40):i])
                i = template(i, m.group(0) if m else "")
                prev = "`"
                continue
            if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^"):
                i = regex(i)
                prev = "/"
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if stop_at_brace and depth == 0:
                    return i + 1
                depth -= 1
            if not c.isspace():
                prev = c if not (c.isalnum() or c in "_$") else "a"
            i += 1
        return i

    def string(i: int, q: str) -> int:
        i += 1
        while src[i] != q:
            i += 2 if src[i] == "\\" else 1
        return i + 1

    def regex(i: int) -> int:
        i += 1
        in_class = False
        while True:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                i += 1
                while i < len(src) and src[i].isalpha():
                    i += 1
                return i
            i += 1

    def template(i: int, tag: str) -> int:
        i += 1
        text = []
        while src[i] != "`":
            if src[i] == "\\":
                text.append(src[i:i + 2])
                i += 2
            elif src.startswith("${", i):
                i = code(i + 2, True)
            else:
                text.append(src[i])
                i += 1
        out.append((tag, "".join(text)))
        return i + 1

    code(0, False)
    return out


def test_the_scanner_finds_tags_and_skips_regexes():
    src = "const a = /`[\"']/g; const b = html`<b>${x ? html`<i>${y}</i>` : `plain`}</b>`; // `<x>`\nconst c = `<p>${z}</p>`;"
    assert template_literals(src) == [("html", "<i></i>"), ("", "plain"), ("html", "<b></b>"), ("", "<p></p>")]


# ------------------------------------------------------------------------------------------------ the page

def test_the_page_loads_the_shared_helpers_then_its_own_files(page):
    order = [page.index(s) for s in ("/static/shared/regista.css", "/static/studio/studio.css", "/static/shared/regista.js",
                                     "/static/studio/studio.js")]
    assert order == sorted(order)
    assert "<script>" not in page  # no inline script: everything is in studio.js


def test_every_tab_has_a_link_a_view_and_a_loader(page, script):
    tabs = ["overview", "review", "whos-who", "training", "runs", "jobs", "console"]
    for tab in tabs:
        assert f'href="#{tab}" data-tab="{tab}"' in page, tab
        assert f'data-view="{tab}"' in page, tab
    loaders = re.search(r"const TABS = \{([^}]*)\}", script).group(1)
    assert sorted(re.findall(r"'?([a-z-]+)'?:", loaders)) == sorted(tabs)


def test_the_overview_links_land_on_a_tab():
    """The to-do links the Studio API writes (/studio#runs/<id>, #review/<id>, #whos-who/<id>, #training) are routes here."""
    facts = (ROOT / "src/regista/studio/facts.py").read_text()
    script = (STUDIO / "studio.js").read_text()
    links = set(re.findall(r'/studio#([a-z-]+)', facts))
    assert links == {"runs", "review", "whos-who", "training"}
    for tab in links:
        assert re.search(rf"\b'?{tab}'?: load", script), tab


def test_the_files_the_page_loads_are_served():
    from regista import api

    c = TestClient(api.app)
    assert "Regista Studio" in c.get("/studio").text
    for path in ("/static/studio/studio.css", "/static/studio/studio.js", "/static/shared/regista.js"):
        assert c.get(path).status_code == 200, path


# ------------------------------------------------------------------------------------------------ escaping

def test_every_html_template_is_built_with_the_escaping_tag(script):
    found = template_literals(script)
    assert len(found) > 100  # the scanner saw the whole file
    untagged = [text for tag, text in found if tag != "html" and re.search(r"<[A-Za-z/!]", text)]
    assert untagged == [], untagged[:3]
    assert {tag for tag, _ in found} <= {"", "html"}


def test_the_tag_escapes_every_value_and_put_is_the_only_way_in(script):
    # html`` escapes anything that is not already an html`` fragment, through the shared esc().
    assert "const { esc, api, key } = R;" in script
    assert "const show = (v) => (v instanceof Safe ? v.s : Array.isArray(v) ? v.map(show).join('') : esc(v));" in script
    assert script.count("new Safe(") == 1
    # put() is the only writer of markup, and it refuses plain strings.
    assert script.count("innerHTML") == 2  # the comment above and put() itself
    assert "if (!(frag instanceof Safe)) throw new TypeError" in script
    for sink in ("outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "srcdoc", "javascript:"):
        assert sink not in script, sink
    # inline handlers would need values in attributes as code: every handler is attached in the script.
    assert not re.search(r"\son[a-z]+=\"", script)


def test_the_escaping_tag_escapes_hostile_values():
    """Run the real html``/esc pair in node (skipped without node)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    shared = (SHARED / "regista.js").read_text()
    script = (STUDIO / "studio.js").read_text()
    block = script[script.index("class Safe"):script.index("const NOTHING")]
    js = ("const window = {};\n" + shared + "\nconst { esc } = window.Regista;\n" + block + """
const evil = '<img src=x onerror=alert(1)>"\\'`&';
const out = html`<a title="${evil}">${evil}${[evil, html`<b>${evil}</b>`]}</a>`;
let refused = false;
try { put({}, '<b>raw</b>'); } catch (e) { refused = true; }
const ok = !out.s.includes('<img') && !out.s.includes('"\\'') && out.s.includes('<b>&lt;img') && refused
  && html`${null}${undefined}`.s === '';
console.log(ok ? 'OK' : 'FAIL ' + out.s);
""")
    res = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert res.stdout.strip() == "OK", res.stdout + res.stderr


# ------------------------------------------------------------------------------------------------ the key

def test_the_key_stays_in_session_storage_and_the_header(page, script):
    files = page + script + (STUDIO / "studio.css").read_text()
    assert "localStorage" not in files
    assert "sessionStorage" not in script  # only through Regista.key (shared/regista.js)
    # the key's value is read only by Regista.api and authedObjectUrl, into the header; here only "is there one?"
    assert re.findall(r"key\.get\([^)]*\).{2}", script) == ["key.get() ?"]
    assert "X-Regista-Token" not in script
    for needle in ("token=", "key=", "Token=", "?k="):
        assert needle not in files, needle
    # Studio reads go through the shared helper with auth; crops through authedObjectUrl, never a plain <img src>.
    assert "api(path, { auth: true })" in script and "R.authedObjectUrl(path)" in script
    assert 'type="password"' in page and 'autocomplete="off"' in page


def test_the_console_sends_no_key(script):
    """The console calls the public endpoints exactly as a visitor would: no key header."""
    console = script[script.index("$('coForm').onsubmit"):script.index("function renderTrace")]
    assert "fetch(path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}" in console
    assert "auth" not in console


# ------------------------------------------------------------------------------------------------ writes and jobs

def test_every_write_control_is_gated_on_the_admin_key(page, script):
    assert "const canWrite = () => S.caps.writes !== 'read-only' && (S.role === 'admin' || S.role === 'open');" in script
    assert "Needs the admin key: the view key can read but not write." in script
    # Keep, Drop, resume a paused review, save Who's who answers, retrain, start a job: each rendered with ${w()}.
    for control in ('data-v="keep"${w()}', 'data-v="drop"${w()}', 'data-act="resume"${w()}', 'id="trRetrain"${w()}'):
        assert control in script, control
    # Who's who: the save button, the candidates and the "someone else" list need the admin key and the identity result
    assert "const canAnswer = (mid) => canWrite() && !S.noIdentity.has(mid);" in script
    for control in ('id="wwSave"${off}', 'data-pid="${c.player_id}"${off}', 'data-pid="unknown"${off}', '<select aria-label="Another player"${off}>'):
        assert control in script, control
    assert "j.running ? html` disabled" in script and ": w();" in script  # job forms
    assert 'id="upGo" type="submit" data-write' in page                    # the static upload button
    writes = re.findall(r"write\(`([^`]+)`", script) + re.findall(r"write\('([^']+)'", script)
    assert sorted(set(writes)) == sorted({"/api/matches/${enc(card.dataset.match)}/clips/${enc(card.dataset.clip)}/verdict",
                                          "/api/matches/${enc(box.dataset.match)}/review",
                                          "/api/matches/${enc(mid)}/identity-review", "/api/feedback/train",
                                          "/api/studio/jobs"})


def test_fresh_evaluations_carry_a_warning_and_a_confirmation(script):
    assert "scored with frozen models only and never tuned on" in script
    assert "if (args.set === 'fresh' && !confirm(" in script


def test_polling_intervals(script):
    assert "setTimeout(r, 2000)" in script and "out.status === 'running'" in script   # job log every 2 s while running
    assert "}, 30000);" in script and "document.visibilityState === 'visible'" in script  # overview every 30 s while visible
    assert "/log?offset=${offset}" in script


# ------------------------------------------------------------------------------------------------ the K4 fixes (audits J1, J3)

def test_keep_and_drop_reach_every_clip(page, script):
    """J1 #1: the review queue has an All clips view (flagged first), so the 8 verdicts a retrain needs are reachable."""
    assert '<select id="rvView"><option value="flagged">Flagged unsure</option><option value="all">All clips</option></select>' in page
    assert "r.cl.value.filter((c) => (everyClip || c.review) && (showDecided || !c.verdict)).sort(reviewOrder)" in script
    assert "(!!a.verdict - !!b.verdict) || (!!b.review - !!a.review)" in script  # undecided first, flagged first among them
    assert "const MIN_VERDICTS = 8;" in script and 'id="rvProgress"' in page
    assert script.count("data-view-all") >= 4  # queue, progress line, Training, a finished job


def test_whos_who_reloads_after_an_answer_and_is_read_only_without_the_identity_result(script):
    save = script[script.index("$('wwBody').addEventListener('click'"):script.index("$('wwBody').addEventListener('change'")]
    assert "S.whosDone = { mid, out };" in save and "loadWhos(mid)" in save  # J1 #6: the list reloads, count drops
    assert "S.noIdentity.add(S.whos.mid);" in save                         # a 409 makes it read-only for the session
    assert "if (r.identity_result === false) S.noIdentity.add(r.match_id);" in script  # known up front from /api/studio/runs
    assert "Read-only here: answers need the vision layer's identity result, which stays on the machine that ran it." in script


def test_words(page, script):
    """J3 N8, N9, S13, S14: plurals, where keys come from, an empty Runs tab, and what counts against the limits."""
    assert set(re.findall(r"(\w+)\(s\)", script)) <= {"constructor", "chip"}, "say 1 answer / 3 answers, not answer(s)"
    assert "Zaid shares the view key with judges in the submission" in page
    assert "No workflow runs on this server yet: uploads and jobs appear here" in script
    assert "Each of those requests still counts against these limits." in script and "not counted" not in script


def test_upload_defaults_to_the_most_active_player(script):
    upload = script[script.index("async function setUploadFile"):script.index("$('upEvents').onchange")]
    assert "r.type === 'possession' || r.type === 'event'" in upload and "players.find((p) => p.starter)" in upload


def test_jobs_show_long_args_shortened_and_offer_cut_clips_after_a_vision_run(script, page):
    assert 'class="mono small args" title="${JSON.stringify(x.args || {})}">${argsShort(x.args)}' in script
    steps = script[script.index("async function nextSteps"):script.index("// ---", script.index("async function nextSteps"))]
    assert "job.kind === 'vision-run'" in steps and "kind: 'cut-clips'" in steps and "#whos-who/${enc(mid)}" in steps
