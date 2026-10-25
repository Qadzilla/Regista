"""The Scout terminal: the Terminal section of /scout (static/scout/terminal.js, terminal-words.js and terminal.css),
ported from the sandbox design and its "intuitive" round. These tests pin what the page code must keep: the section in
the left panel, the Content Security Policy rules (no inline script, handlers or style attributes; data colours and widths
go through element.style), escaping, per-visitor saved layouts through Regista.store only (old ones still load), reads
only, no hidden ratings, the complete evidence behind every number, the four fixes the sandbox reviewers left open, the
stale-command guard, and the friendlier pieces: the search box that reads plain questions (every stat by any of its
names), plain panel names, the clips drawer, numbers with nothing behind them as plain text. Its behaviour in a browser
(1440 and 375 px) is checked by hand against a local offline run; see docs/redesign/terminal-friendly/build.md.
"""

from __future__ import annotations

import fnmatch
import json
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
def words() -> str:
    return (SCOUT / "terminal-words.js").read_text()


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
               'id="txGrid"', 'id="txTip"', 'id="txEx"', 'id="txNav"', 'id="txFoot"', 'id="txDrawer"', 'id="txDrawerH"', 'id="txDrawerBody"'):
        assert el in page, el
    # a search box (a labelled combobox) with a Search button; no CMD> prompt or <GO> left
    assert '<label class="sr" for="txIn">Search a player, club or stat</label>' in page and 'role="combobox"' in page
    assert 'placeholder="Search a player, club or stat…"' in page and '<button type="submit" class="tx-go">Search</button>' in page
    assert "CMD&gt;" not in page and "&lt;GO&gt;" not in page
    # the clips drawer: a labelled dialog with a Close button
    assert 'class="tx-drawer" id="txDrawer" role="dialog" aria-modal="false" aria-labelledby="txDrawerH" hidden' in page
    assert 'data-act="dclose" aria-label="Close clips"' in page
    assert '<link rel="stylesheet" href="/static/scout/terminal.css">' in page
    words_at = page.index('<script src="/static/scout/terminal-words.js" defer></script>')
    assert page.index("/static/scout/scout.js") < words_at < page.index('<script src="/static/scout/terminal.js" defer></script>')
    # the profile page repeats Scout's sections in its left panel
    assert 'data-section="terminal">Terminal</a>' in (STATIC / "player/index.html").read_text()


def test_the_image_ships_the_terminals_files():
    patterns = re.search(r'regista = \[(.*?)\]', (ROOT / "pyproject.toml").read_text()).group(1)
    globs = [g.strip().strip('"') for g in patterns.split(",")]
    for f in ("static/scout/terminal.js", "static/scout/terminal-words.js", "static/scout/terminal.css"):
        assert any(fnmatch.fnmatch(f, g) for g in globs), f"{f} is not package data"
    from tests.test_packaging import _excluded

    for f in ("terminal.js", "terminal-words.js", "terminal.css"):
        assert not _excluded(f"src/regista/static/scout/{f}"), f


def test_the_script_parses(js):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    for f in ("terminal.js", "terminal-words.js"):
        assert subprocess.run([node, "--check", str(SCOUT / f)], capture_output=True).returncode == 0, f


def test_the_csp_rules_hold(js, words, css):
    # no style attributes anywhere in the script's markup: shading, colours and widths are data attributes applied through
    # element.style after rendering
    assert "style=" not in js and "style=" not in words and "innerHTML" not in words
    for attr in ("data-bg", "data-c", "data-g", "data-w", "data-l", "data-fg"):
        assert attr in js
    assert "function styleUp(root)" in js and "el.style.background" in js and "el.style.setProperty('--c'" in js
    # no inline handlers in the markup it writes, no eval, no external origins
    assert not re.search(r"\son[a-z]+=", js), "inline event handler in terminal.js markup"
    assert "eval(" not in js and "new Function" not in js and "http://" not in js
    # the left panel's router hides every [data-panel] that is not the section on screen: the terminal's own panels must
    # use another attribute, or opening Find players would hide them for good
    assert "data-panel" not in js and 'data-txp="' in js and "dataset.txp" in js and "dataset.panel" not in js
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


def test_workspaces_and_history_stay_in_this_browser_through_the_shared_store(js, words):
    for src in (js, words):
        assert "localStorage" not in src and "sessionStorage" not in src and "indexedDB" not in src
    assert "R.store.get(STORE_KEY, null)" in js and "R.store.set(STORE_KEY, store)" in js and "STORE_KEY = 'terminal'" in js
    assert "R.store.persistent()" in js and "not saved: storage blocked" in js
    assert "R.store.watch(" in js
    # three workspaces with Reset, each checked before use (unknown players, metrics and panels dropped)
    assert "function resetWs()" in js and "function clean(s)" in js and "[0, 1, 2]" in js


def test_reset_this_demo_resets_the_terminal_in_the_same_tab(js):
    # Regista.demo.reset() clears the store, but the storage event only reaches other tabs: without this the terminal kept
    # its workspaces and history in memory and wrote them back on its next save (found by the safeguard pass).
    hook = re.search(r"\$\('stReset'\)[\s\S]{0,700}?\}\);", js)
    assert hook, "the terminal does not listen to Reset this demo"
    body = hook.group(0)
    assert "clearTimeout(saveT)" in body and "store = { cur: 0, ws: [null, null, null], hist: [] }" in body and "readStore()" in body
    # scout.js's own listener (demo.reset) must run first: it is registered by scout.js, which loads before terminal.js
    scout = (SCOUT / "scout.js").read_text()
    assert "demo.reset();" in scout and "the Terminal saved layouts" in scout
    # and what is playing stops: the drawer closes
    assert "forgetReel()" in body and "closeDrawer()" in _fn(js, "forgetReel")


def test_reset_this_demo_in_another_tab_resets_an_open_terminal(js):
    # Regista.store.reset() removes the key, so the other tab gets a storage event: readStore() must then start from the
    # defaults (and drop a pending save), not keep the old workspaces and history in memory and write them back on the
    # next click (review A, round 1).
    rs = _fn(js, "readStore")
    nothing = rs[rs.index("} else {"):]
    assert "clearTimeout(saveT)" in nothing and "store = { cur: 0, ws: [null, null, null], hist: [] }" in nothing
    assert nothing.index("store = {") < nothing.index("clean(store.ws[store.cur])")
    watch = js[js.index("R.store.watch("):js.index("const resetBtn")]
    assert "readStore()" in watch and "histAt = -1" in watch and "R.store.remove(STORE_KEY)" in watch


def test_cmp_without_a_player_says_how_to_use_it(js):
    # `CMP vs` or `CMP ,` resolves no players: the usage line, never a crash reading .q of nothing (review A, round 1)
    cmp = _fn(js, "cmdCmp")
    assert cmp.index("if (!rs.length)") < cmp.index("const bad") and "Compare needs two or three players: compare <player>" in cmp
    assert "rest ? `No player called" not in cmp


def test_the_heat_map_reads_the_league_only_grid(js):
    # every terminal number is league fixtures only; the profile's grid also counts claimed and uploaded matches
    assert "/heatmap`" in js and "heatOf(p.id, 'heat')" in _fn(js, "renderHeat")
    assert "R.api(`/api/players/${enc(pid)}`)" not in js
    assert "on-ball actions in league matches this season" in _fn(js, "renderHeat")


def test_the_terminal_only_reads(js, words):
    # the search-box reader makes no requests at all
    assert "R.api" not in words and "fetch(" not in words and "XMLHttpRequest" not in words
    assert "method:" not in js and "'POST'" not in js and "'PUT'" not in js and "'DELETE'" not in js
    assert "fetch(" not in js            # every request goes through Regista.api, a GET without a key
    used = set(re.findall(r"R\.api\(`?'?(/api/[a-z/]+)", js))
    allowed = {"/api/metrics", "/api/season", "/api/teams", "/api/terminal/screen", "/api/terminal/scatter", "/api/players/", "/api/teams/"}
    assert used and used <= allowed, used - allowed
    assert "auth: true" not in js and "X-Regista-Token" not in js


def test_the_hidden_ratings_never_appear(js, words):
    from regista.season.league import ATTRIBUTE_KEYS

    for k in ("attributes", *ATTRIBUTE_KEYS):
        # a property read (.finishing) or a key as a whole string ('finishing'): words in comments may repeat them
        for src in (js, words):
            assert not re.search(rf"\.{k}\b|['\"]{k}['\"]", src), k


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
    assert "goPanel(p.id)" in js and "goPanel(t.dataset.id, " in js
    # a ranking leaves the leader's ranked number as the table's active cell, and Help says how to get there
    assert "scrAct = rows.length ? { pid: rows[0].id, c: 1 } : null;" in _fn(js, "cmdRank")
    assert "(Players) goes straight into the players table" in js


def test_fix_4_commands_bring_their_subject_into_view_after_the_output_line(js):
    rank = _fn(js, "cmdRank")
    assert rank.index("out(`${cap1(posText(S.scr.pos))}") < rank.index("showPanel('scrn', true, scrollTable(m.key))")
    assert "trs[Math.min(2, trs.length - 1)]" in _fn(js, "scrollTable")   # the first rows of the ranking, not 60% of the box
    run = _fn(js, "run")
    # a name brings the card and the Best table into view; panel commands load first, write the line, then scroll
    assert "showPanel('plyr', true, '.tx-best')" in run
    for cmd_out, cmd_show in (("out('', '', esc(line)", "showPanel(PANEL_CMD[head]"),):
        assert run.index(cmd_out) < run.index(cmd_show)
    assert "class=\"tx-mt tx-best\"" in js


def test_fix_4_commands_wait_for_every_shown_panel_before_they_scroll(js):
    # On a phone the panels are stacked: one above the subject still "Loading…" grows when its data lands and would push
    # the subject below the fold after the scroll (review A, round 2: HEAT or SHOT as the first command for a player).
    settled = _fn(js, "panelsSettled")
    assert "c.panels" in settled and "visible" in settled and "colsPending" in settled and "nextFrame()" in settled
    assert "(c.panels || (c.panels = new Set())).add(panel)" in _fn(js, "want")
    run = _fn(js, "run")
    for show in ("showPanel(PANEL_CMD[head], true", "showPanel('plyr', true, '.tx-best')"):
        i = run.index(show)
        assert run.rfind("await panelsSettled();", 0, i) > run.rfind("select(p.id, true);", 0, i)
    for name, show in (("cmdCmp", "showPanel('radar')"), ("cmdScat", "showPanel('scat', true)"), ("team", "showPanel('team', true)")):
        body = _fn(js, name)
        assert body.index("await panelsSettled();") < body.index(show), name


def test_only_the_terminal_binds_cmd_k(js):
    assert "(e.metaKey || e.ctrlKey) && !e.altKey && String(e.key).toLowerCase() === 'k'" in js
    others = [p for p in STATIC.rglob("*.js") if p.name != "terminal.js" and re.search(r"metaKey|ctrlKey", p.read_text())]
    assert not others, others


def test_the_synthetic_data_is_said_once_and_numbers_say_where_they_come_from(js):
    # once, plainly, at the bottom of the section ("Synthetic data: invented players and clubs…", from the catalogue)
    foot = _fn(js, "paintFoot")
    assert "$('txFoot').innerHTML" in foot and "CAT.note" in foot and "Synthetic data" in foot
    assert "SYNTHETIC DATA" not in js and "Synthetic data" not in _fn(js, "paintMeta")
    # every metric's definition, rule and source on hover and focus; noisy marked as the engine marks it
    tip = _fn(js, "tipHtml")
    assert "m.definition" in tip and "m.rule" in tip and "CAT.sources" in tip and "m.noisy" in tip and "m.min_attempts" in tip
    assert "rel.noisy" in js and "aria-describedby" in js


def test_a_stale_command_drops_its_line_and_scroll(js):
    # Commands wait for the network: an older one finishing after a newer command, or after a player picked by hand, must
    # not replace the newer output line or scroll away from it (review B, round 3).
    assert "let gen = 0;" in js
    assert "if (!quiet) gen++;" in _fn(js, "select")  # a hand-picked player overrides a command still loading
    run = _fn(js, "run")
    assert "const g = ++gen;" in run
    for show in ("showPanel(PANEL_CMD[head], true", "showPanel('plyr', true, '.tx-best')"):
        i = run.index(show)
        assert run.rfind("if (g !== gen) return;", 0, i) > run.rfind("await panelsSettled();", 0, i)
    for name, show in (("cmdCmp", "showPanel('radar')"), ("cmdScat", "showPanel('scat', true)"), ("team", "showPanel('team', true)")):
        body = _fn(js, name)
        assert "const g = gen;" in body, name
        assert body.rfind("if (g !== gen) return;", 0, body.index(show)) > body.rfind("await panelsSettled();", 0, body.index(show)), name


# ---------------------------------------------------------------------- the friendlier terminal (the intuitive round)

WORDS_HARNESS = r"""
const fs = require('fs');
globalThis.window = globalThis;
eval(fs.readFileSync(process.argv[1], 'utf8'));
const L = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const players = L.players.map(p => ({ ...p, id: p.global_id }));
const TW = window.Regista.terminalWords;
const W = TW.create({ metrics: () => L.cat.metrics, defaults: () => L.cat.default_columns, clubs: () => L.season.clubs,
  players: () => players, byId: (id) => players.find(p => p.id === id), focus: () => players.find(p => p.id === 'pl_bro_09') });
const shape = (r) => ({ do: r.do, key: r.key || null, keys: r.keys || null, pos: r.pos || null, rest: r.rest || null,
  head: r.head || null, p: r.p ? r.p.id : null, club: r.club ? r.club.club_id : null, most: !!r.most, fewest: !!r.fewest, worst: !!r.worst });
const out = { short: Object.fromEntries(L.cat.metrics.map(m => [m.key, TW.shortLabel(m)])), loose: {}, q: {} };
for (const m of L.cat.metrics) out.loose[m.key] = [...new Set([m.key, m.label, TW.shortLabel(m)].map(TW.loose))];
for (const q of JSON.parse(process.argv[3])) out.q[q] = shape(W.interpret(q));
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def league(tmp_path_factory) -> Path:
    from regista import api

    c = TestClient(api.app)
    cat = c.get("/api/metrics").json()
    season = c.get("/api/season").json()
    players = c.get("/api/terminal/screen", params={"min_minutes": 0, "limit": 200, "metrics": "goals"}).json()["players"]
    f = tmp_path_factory.mktemp("terminal") / "league.json"
    f.write_text(json.dumps({"cat": cat, "season": season, "players": players}))
    return f


def interpret(league: Path, queries: list[str]) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    res = subprocess.run([node, "-e", WORDS_HARNESS, str(SCOUT / "terminal-words.js"), str(league), json.dumps(queries)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


QUESTION_FORMS = ["{}", "most {}", "the most {}", "who has the most {}", "who has the most {}?", "{} per 90", "most {} per 90",
                  "top {}", "top 5 {}", "highest {}", "best {}", "show me the most {}", "rank {}", "{} per 90 minutes", "{} p90",
                  "MOST {}", "highest {} per game", "which players have the most {}", "most {} in the league",
                  "fewest {}", "least {}", "lowest {}", "the fewest {}"]
# With a position or a club before or after the stat: (form, position, club).
PLACED_FORMS = [("forwards with the most {}", "FW", None), ("forwards most {}", "FW", None), ("most {} for forwards", "FW", None),
                ("midfielders with the fewest {}", "MF", None), ("most {} among defenders", "DF", None),
                ("most {} at Brookfield", None, "cl_brookfield"), ("Brookfield most {}", None, "cl_brookfield"),
                ("most {} for forwards at Brookfield", "FW", "cl_brookfield"), ("forwards with the most {} at Brookfield", "FW", "cl_brookfield"),
                # review round 2: "which <position> have the most <stat>"
                ("which forwards have the most {}", "FW", None), ("which midfielder has the fewest {}", "MF", None),
                ("what keepers have the most {}", "GK", None), ("which defenders have the most {} at Brookfield", "DF", "cl_brookfield")]


def test_every_stat_answers_by_key_label_and_short_label_in_plain_questions(league):
    # Zaid's fix for the sandbox reviewer's open finding: "most <stat>" and "<stat> per 90" worked for a short list of
    # stats only. Every catalogue metric, by its key, its label or its short column label, alone or in a question, now
    # ranks the players on that metric.
    from regista.season.metrics import CATALOGUE

    probe = interpret(league, [])
    queries, want = [], {}
    for key, m in CATALOGUE.items():
        for name in {key, m.label, probe["short"][key]}:
            for form in QUESTION_FORMS:
                q = form.format(name)
                queries.append(q)
                want[q] = key
    got = interpret(league, queries)["q"]
    bad = [f"{q} -> {got[q]}" for q in queries
           if not (got[q]["do"] == "rankKey" and got[q]["key"] == want[q]) and not (q.startswith("rank ") and got[q]["do"] == "rank")]
    assert not bad, f"{len(bad)} questions missed their stat, e.g. " + "; ".join(bad[:8])
    # "fewest", "least", "lowest" ask for the smallest numbers first; "most", "highest" for the biggest
    for q in queries:
        if q.split(" ")[0] in ("fewest", "least", "lowest") or q.startswith("the fewest "):
            assert got[q]["fewest"] and not got[q]["most"], q
        elif q.split(" ")[0].lower() in ("most", "highest"):
            assert got[q]["most"] and not got[q]["fewest"], q


def test_every_stat_answers_with_a_position_or_a_club_before_or_after_it(league):
    # Review round 1: "forwards with the most goals" answered Nothing found (the position was read off after the leading
    # superlatives, so "most" stayed), and stat names holding filler, position or club-like words ("Shots on target",
    # "Mid third pass %", "Passes from the defensive third") lost them to the filler filter or the club pattern.
    from regista.season.metrics import CATALOGUE

    probe = interpret(league, [])
    queries, want = [], {}
    for key, m in CATALOGUE.items():
        for name in {key, m.label, probe["short"][key]}:
            for form, pos, club in PLACED_FORMS:
                q = form.format(name)
                queries.append(q)
                want[q] = (key, pos, club)
    got = interpret(league, queries)["q"]
    bad = [f"{q} -> {got[q]}" for q in queries
           if (got[q]["do"], got[q]["key"], got[q]["pos"], got[q]["club"]) != ("rankKey", *want[q])]
    assert not bad, f"{len(bad)} of {len(queries)} questions missed, e.g. " + "; ".join(bad[:8])


def test_which_position_questions_and_their_verbs(league):
    # Review round 2: "which forwards have the most goals" answered Nothing found, as did "which strikers score the most";
    # "who wins the most tackles" did too. The position is kept, and a verb after it names the stat as after "who".
    cases = {
        "which forwards have the most goals": ("goals", "FW", None), "which forward has the most goals": ("goals", "FW", None),
        "what forwards have the most goals": ("goals", "FW", None), "which keepers have the best save %": ("save_pct", "GK", None),
        "which forwards score the most": ("goals", "FW", None), "which strikers score the most": ("goals", "FW", None),
        "which keepers concede the fewest": ("goals_conceded", "GK", None),
        "which defenders win the most tackles": ("tackles_won", "DF", None), "who wins the most tackles": ("tackles_won", None, None),
        "which players win the most tackles": ("tackles_won", None, None), "who wins the most aerial duels": ("aerial_duels_won", None, None),
        "which forwards win the most fouls": ("fouls_won", "FW", None), "what players have the most goals": ("goals", None, None),
        "which forwards have the most goals at Brookfield": ("goals", "FW", "cl_brookfield"),
    }
    got = interpret(league, list(cases) + ["which forwards have the fewest goals", "which forwards are the best", "which forwards", "what is xG"])["q"]
    bad = {q: got[q] for q, w in cases.items() if (got[q]["do"], got[q]["key"], got[q]["pos"], got[q]["club"]) != ("rankKey", *w)}
    assert not bad, bad
    assert got["which forwards score the most"]["most"]
    assert got["which forwards have the fewest goals"]["fewest"] and got["which forwards have the fewest goals"]["pos"] == "FW"
    # a position with nothing but "the best" (or nothing) left ranks that position on its first column
    assert got["which forwards are the best"]["do"] == "rankKey" and got["which forwards are the best"]["pos"] == "FW"
    assert got["which forwards"]["do"] == "rankKey" and got["which forwards"]["pos"] == "FW"
    # "what" without a position is not read as one
    assert got["what is xG"]["pos"] is None


def test_every_stats_names_are_its_own(league):
    # a name two stats share would find neither: every key, label and short label (in the loose form people type) is unique
    probe = interpret(league, [])
    owner: dict[str, str] = {}
    for key, names in probe["loose"].items():
        for n in names:
            assert owner.setdefault(n, key) == key, f"{n!r} names both {owner[n]} and {key}"


def test_short_labels_fit_the_radar(league):
    # radar axes show the short label in full (at most 18 characters) for every stat a radar can show
    from regista.season.metrics import DEFAULT_COLUMNS

    probe = interpret(league, [])
    radar = {k for cols in DEFAULT_COLUMNS.values() for k in cols}
    long = {k: probe["short"][k] for k in radar if len(probe["short"][k]) > 18}
    assert not long, long


def test_plain_questions_and_old_mnemonics_read_as_commands(league):
    q = interpret(league, [
        "who are the best finishers?", "best finishers", "top scorers", "forwards", "best defenders", "tackles",
        "Whitfield tackles", "Toure vs Ustinov", "who is better Toure or Ustinov", "compare Toure with Ustinov",
        "Toure goals", "Toure highlights", "Toure shots", "show me Toure", "best finishers at Brookfield", "most minutes",
        "shots", "shots Toure", "strikers like Toure", "who plays like Toure?", "similar to Toure", "touch map Toure",
        "RANK FW npxg", "CMP Toure Ustinov", "SCAT npxg xa FW", "SIM", "SHOT", "FORM", "HEAT", "RDR", "TEAM BRO", "HL Toure",
        "HELP", "BRO", "Toure", "xyzzy qq", "save %", "best save percentage"])["q"]
    assert q["who are the best finishers?"] == q["best finishers"] and q["best finishers"]["key"] == "np_goals" and q["best finishers"]["pos"] == "FW"
    assert q["top scorers"]["key"] == "goals"
    assert q["forwards"]["do"] == "rankKey" and q["forwards"]["pos"] == "FW"
    assert q["best defenders"]["key"] == "tkl_int_padj" and q["best defenders"]["pos"] == "DF"
    # a word several stats share offers the choices, for a player too
    assert q["tackles"]["do"] == "many" and "tackles_won" in q["tackles"]["keys"]
    assert q["Whitfield tackles"]["do"] == "many" and q["Whitfield tackles"]["p"]
    for k in ("Toure vs Ustinov", "who is better Toure or Ustinov", "compare Toure with Ustinov", "CMP Toure Ustinov"):
        assert q[k]["do"] == "cmp", k
    assert q["Toure goals"] == {**q["Toure goals"], "do": "stat", "key": "goals", "p": "pl_bro_09"}
    assert q["Toure highlights"]["do"] == "hlPlayer" and q["HL Toure"]["do"] == "hl"
    assert q["Toure shots"]["do"] == "panel" and q["Toure shots"]["head"] == "SHOT"
    assert q["show me Toure"]["do"] == "player" and q["Toure"]["do"] == "player"
    assert q["best finishers at Brookfield"]["club"] == "cl_brookfield"
    assert q["most minutes"]["do"] == "minutes"
    # "shots" alone is the stat; with a player it is the shot map; the mnemonic SHOT is always the panel
    assert q["shots"]["do"] == "rankKey" and q["shots"]["key"] == "shots"
    assert q["shots Toure"]["head"] == "SHOT" and q["SHOT"]["head"] == "SHOT"
    for k in ("strikers like Toure", "who plays like Toure?", "similar to Toure", "SIM"):
        assert q[k]["do"] == "panel" and q[k]["head"] == "SIM", k
    assert q["touch map Toure"]["head"] == "HEAT" and q["HEAT"]["head"] == "HEAT"
    assert q["RANK FW npxg"] == {**q["RANK FW npxg"], "do": "rank", "rest": "FW npxg"}
    assert q["SCAT npxg xa FW"]["do"] == "scat" and q["FORM"]["head"] == "FORM" and q["RDR"]["head"] == "RDR"
    assert q["TEAM BRO"]["do"] == "team" and q["BRO"]["do"] == "club" and q["HELP"]["do"] == "help"
    assert q["xyzzy qq"]["do"] == "none"
    assert q["save %"]["key"] == q["best save percentage"]["key"] == "save_pct"


def test_the_terminal_runs_the_readers_intents(js):
    run = _fn(js, "run")
    for intent in ("help", "rank", "rankKey", "minutes", "cmp", "scat", "team", "club", "hl", "hlPlayer", "hlFocus", "stat", "many", "panel", "player"):
        assert f"'{intent}'" in run, intent
    assert "const it = W.interpret(t);" in run
    # a goalkeepers' stat ranks the goalkeepers unless a position is named; a failed search keeps its text, selected
    assert "if (!pos && gkOnly(m)) pos = 'GK';" in _fn(js, "cmdRank")
    assert "inp.value = t; inp.select();" in run


def test_the_screen_and_scatter_say_how_many_moments_are_behind_each_number():
    from regista import api

    c = TestClient(api.app)
    scr = c.get("/api/terminal/screen", params={"min_minutes": 0, "limit": 200, "metrics": "goals,assists,distance"}).json()
    toure = next(p for p in scr["players"] if p["global_id"] == "pl_bro_09")
    for k in ("goals", "assists", "distance"):
        ev = c.get("/api/players/pl_bro_09/metrics", params={"evidence": k, "evidence_limit": 0}).json()["evidence"]
        assert toure["values"][k]["evidence_total"] == ev["total"] == ev["moments"], k
    assert toure["values"]["goals"]["evidence_total"] == 5 and toure["values"]["assists"]["evidence_total"] == 0
    sc = c.get("/api/terminal/scatter", params={"x": "goals", "y": "assists", "min_minutes": 0}).json()
    pt = next(p for p in sc["points"] if p["global_id"] == "pl_bro_09")
    assert pt["x_evidence_total"] == 5 and pt["y_evidence_total"] == 0


def test_numbers_with_nothing_behind_them_are_plain_text(js, css):
    # zero moments: no underline, no play mark, the status line says so instead of opening an empty drawer
    assert "const zeroC = (c) => evTotalC(c) === 0;" in js and "zcC(c)" in _fn(js, "renderScrn") and "zcC(c)" in _fn(js, "mrow")
    act = _fn(js, "act")
    ev = act[act.index("if (a === 'ev')"):act.index("if (a === 'fev')")]
    assert ev.index("t.classList.contains('z')") < ev.index("return openEvidence(")
    assert ".pf .tx .tx-n.z { text-decoration: none; cursor: default; }" in css and ".pf .tx .tx-n.z::before { display: none; }" in css
    # a clickable number says what it plays: "▶ 5 moments", from the API's evidence_total
    assert "evidence_total: evidence ? (evidence.moments ?? evidence.total) : null" in js and "click to play" in _fn(js, "tipHtml")


def test_plain_panel_names_and_their_shortcuts(js):
    titles = re.findall(r"\{ id: '(\w+)', title: '([^']+)'", js[js.index("const PANELS"):js.index("const DEFAULT_ORDER")])
    assert [t for _, t in titles] == ["Players", "Player", "Radar", "Clips", "Shots", "Touch map", "Form", "Scatter", "Team"]
    keys = _fn(js, "paintKeys")
    assert 'aria-keyshortcuts="Alt+${n}"' in keys and "go to it" in keys and "is hidden: show it" in keys and "Help</button>" in keys
    assert "F${n}" not in js and "<GO>" not in keys
    # Clips is a drawer, not a panel: never in the grid, opened and closed by its button, Alt+4 and Escape
    assert "DEFAULT_ORDER = ['scrn', 'plyr', 'radar', 'form', 'shot', 'heat', 'scat', 'team']" in js
    assert "if (id === 'clips') { if (drawerOpen()) closeDrawer(); else openDrawer(true); return; }" in _fn(js, "goPanel")
    assert "$('txDrawerH').focus(" in _fn(js, "openDrawer")
    close = _fn(js, "closeDrawer")
    assert "drawerFrom" in close and "back.sel" in close


def test_old_saved_layouts_still_load(js):
    # v2 (the first port: Clips in the grid) loads into v3: an untouched v2 default takes the new default, a changed one
    # keeps its order, sizes and hidden panels without Clips; players, comparison, columns and the rest carry over
    clean = _fn(js, "clean")
    assert "![2, VER].includes(s.v)" in clean and "V2_DEFAULT" in clean and "!def.drawer" in clean
    assert "const V2_DEFAULT = 'scrn:L,clips:S,plyr:S,radar:S,form:S,shot:S,heat:S,scat:S,team:XL';" in js
    assert "const VER = 3;" in js and "v: VER" in _fn(js, "defaults")


def test_the_header_selection_examples_and_profile_link(js):
    sel = _fn(js, "renderSel")
    assert "Selected:" in sel and "Compare with…" in sel and "to the comparison" in sel and "Comparing:" in sel
    ex = _fn(js, "paintExamples")
    assert "'Best finishers', 'rank forwards non-penalty goals'" in ex and "Compare ${lastName(f)} and ${lastName(rival)}" in ex and "Who plays like" in ex
    meta = _fn(js, "paintMeta")
    assert "Saved layouts:" in meta and "Reset layout" in meta and "small sample, read with care" in meta
    # every player's card opens their profile on this app
    assert '<a href="/players/${esc(enc(p.id))}">Open profile &rarr;</a>' in _fn(js, "renderPlyr")
    scrn = _fn(js, "renderScrn")
    assert "Regulars only (" in scrn and ">Percentile</button>" in scrn and "Columns (${cols.length})" in scrn and "values per 90 minutes" in scrn
    assert "shortLabel(m)" in scrn and 'data-row="${esc(p.id)}"' in scrn


def test_the_phone_row_and_the_wide_layout(js, css):
    assert "function paintNav()" in js and "function navCurrent(" in js and "function fitTall()" in js and "function fillRows()" in js
    assert ".pf .tx-mnav { display: none; }" in css and "position: sticky; top: var(--top-h, 52px)" in css
    # move, size and close show on hover and keyboard focus, always on touch screens
    assert ".pf .tx-panel:hover .tx-pbtns, .pf .tx-panel:focus-within .tx-pbtns { opacity: 1; }" in css
    assert "@media (hover: none) { .pf .tx-pbtns { opacity: 1; } }" in css


def test_a_ratios_count_is_the_moments_the_drawer_plays_each_event_once():
    # A ratio's evidence lists each event once per key (a pass, and again if completed): Toure's pass completion is 92 of
    # 124, 216 rows. The drawer merges them into 124 rows, so "play its N moments" must say 124, not 216 (safeguard).
    from regista import api

    c = TestClient(api.app)
    scr = c.get("/api/terminal/screen", params={"min_minutes": 0, "limit": 200, "metrics": "pass_pct,npxg_plus_xa"}).json()
    toure = next(p for p in scr["players"] if p["global_id"] == "pl_bro_09")
    for k in ("pass_pct", "npxg_plus_xa"):
        items, offset = [], 0
        while True:
            ev = c.get("/api/players/pl_bro_09/metrics", params={"evidence": k, "evidence_offset": offset}).json()["evidence"]
            items += ev["items"]
            offset += len(ev["items"])
            if not ev["items"] or offset >= ev["total"]:
                break
        merged = {(it["match_id"], it["event_id"] or f"t{it['t']}") for it in items}   # terminal.js mergeEvidence
        assert toure["values"][k]["evidence_total"] == ev["moments"] == len(merged), k
    pp = toure["values"]["pass_pct"]
    assert pp["evidence_total"] == pp["den"] == 124
    full = c.get("/api/players/pl_bro_09/metrics", params={"evidence_limit": 0}).json()["metrics"]["pass_pct"]["evidence"]
    assert full["moments"] == 124 and full["total"] == 216 and full["items"] == []
    sc = c.get("/api/terminal/scatter", params={"x": "pass_pct", "y": "goals", "min_minutes": 0}).json()
    assert next(p for p in sc["points"] if p["global_id"] == "pl_bro_09")["x_evidence_total"] == 124


def test_every_numbers_moment_count_is_the_drawers_row_count_for_every_player_and_metric():
    # Review round 1: one pass that creates two shots is two shot-creating actions, so a single key could list an event
    # twice; the screen counted rows (18), /metrics counted events (16) and the drawer listed every row (18). One rule now:
    # each event once, in the screen's and the scatter's evidence_total, in /metrics' moments and in the drawer's rows
    # (terminal.js mergeEvidence for every event metric; one row per match for a physical one).
    from regista import api
    from regista.season.metrics import CATALOGUE
    from regista.terminal_api import metrics as season_metrics

    c = TestClient(api.app)
    keys = list(CATALOGUE)
    screen: dict[str, dict[str, int]] = {}
    for i in range(0, len(keys), 16):
        chunk, offset = keys[i:i + 16], 0
        while True:
            page = c.get("/api/terminal/screen", params={"min_minutes": 0, "limit": 200, "offset": offset, "metrics": ",".join(chunk)}).json()
            for p in page["players"]:
                screen.setdefault(p["global_id"], {}).update({k: v["evidence_total"] for k, v in p["values"].items()})
            offset += len(page["players"])
            if not page["players"] or offset >= page["total"]:
                break
    sm = season_metrics()
    assert len(screen) == len(sm.players) and all(len(v) == len(keys) for v in screen.values())
    bad = []
    for gid, cells in screen.items():
        table = c.get(f"/api/players/{gid}/metrics", params={"evidence_limit": 0}).json()["metrics"]
        ps = sm.players[gid]
        for k in keys:
            ev = sm.evidence(ps, k)          # every item, as the drawer pages them in
            rows = len(ev["items"]) if ev["per_match"] else len({(it["match_id"], it["event_id"] or f"t{it['t']}") for it in ev["items"]})
            if not (cells[k] == table[k]["evidence"]["moments"] == rows):
                bad.append(f"{gid} {k}: screen {cells[k]}, /metrics {table[k]['evidence']['moments']}, drawer {rows}")
    assert not bad, f"{len(bad)} cells disagree, e.g. " + "; ".join(bad[:6])
    # Femi Toure's shot-creating actions: a pass that led to two shots is one moment, counted twice in the stat
    toure = sm.evidence(sm.players["pl_bro_09"], "sca")
    assert toure["total"] > toure["moments"] == screen["pl_bro_09"]["sca"]


def test_the_drawer_lists_each_event_once_for_one_key_too(js):
    reel = _fn(js, "evidenceReel")
    single = reel[reel.index("} else {", reel.index("(ev.keys || []).length > 1")):]
    assert "mergeEvidence(ev).map(" in single and "counts ${n} times" in single
    assert "return len({self._moment_id(e) for k in m.evidence_keys() for e in ps.evidence.get(k, [])})" in (
        Path(__file__).resolve().parents[1] / "src/regista/season/metrics.py").read_text()


def test_most_of_a_stat_where_lower_is_better_lists_the_most_first(league, js):
    # "most yellow cards" asks who has the most cards; it ranked the players with none first, as "best" would (safeguard).
    # "most", "highest" and the like list the biggest numbers first; "best", "top" and a bare stat keep the better way.
    q = interpret(league, ["most yellow cards", "who has the most yellow cards?", "highest goals conceded", "most fouls committed per 90",
                           "best goals conceded", "top yellow cards", "yellow cards", "most goals"])["q"]
    for k in ("most yellow cards", "who has the most yellow cards?", "highest goals conceded", "most fouls committed per 90", "most goals"):
        assert q[k]["do"] == "rankKey" and q[k]["most"], k
    for k in ("best goals conceded", "top yellow cards", "yellow cards"):
        assert q[k]["do"] == "rankKey" and not q[k]["most"], k
    assert "{ m: MK.get(it.key), pos: it.pos, most: it.most, fewest: it.fewest, worst: it.worst }" in _fn(js, "run")
    rank = _fn(js, "cmdRank")
    assert "const low = end === 'most' ? false : end === 'fewest' ? true : end === 'worst' ? !lowerBetter : lowerBetter;" in rank
    assert "S.scr.sort = { k: m.key, dir: low ? 1 : -1 };" in rank and "(most first; fewer is better)" in rank


def test_fewest_least_lowest_and_worst_rank_from_the_other_end(league, js):
    # Review round 1: "fewest yellow cards", "least fouls", "lowest xG", "fewest goals conceded", "who concedes the least"
    # and "worst finishers" answered Nothing found. "fewest", "least", "lowest" list the smallest numbers first, whichever
    # way the stat is better; "worst" reverses the stat's better way.
    q = interpret(league, ["fewest yellow cards", "least fouls", "lowest xG", "fewest goals conceded", "who concedes the least",
                           "who concedes the least goals?", "worst finishers", "the lowest pass completion", "forwards with the fewest goals",
                           "fewest goals at Brookfield", "worst goals conceded"])["q"]
    assert q["fewest yellow cards"] == {**q["fewest yellow cards"], "do": "rankKey", "key": "yellow_cards", "fewest": True, "most": False}
    assert q["least fouls"]["do"] == "rankKey" and q["least fouls"]["key"] == "fouls" and q["least fouls"]["fewest"]
    assert q["lowest xG"]["do"] == "rankKey" and q["lowest xG"]["key"] == "xg" and q["lowest xG"]["fewest"]
    for k in ("fewest goals conceded", "who concedes the least", "who concedes the least goals?"):
        assert q[k] == {**q[k], "do": "rankKey", "key": "goals_conceded", "fewest": True}, k
    assert q["worst finishers"] == {**q["worst finishers"], "do": "rankKey", "key": "np_goals", "pos": "FW", "worst": True}
    assert q["the lowest pass completion"]["key"] == "pass_pct" and q["the lowest pass completion"]["fewest"]
    assert q["forwards with the fewest goals"] == {**q["forwards with the fewest goals"], "key": "goals", "pos": "FW", "fewest": True}
    assert q["fewest goals at Brookfield"] == {**q["fewest goals at Brookfield"], "key": "goals", "club": "cl_brookfield", "fewest": True}
    assert q["worst goals conceded"]["worst"] and not q["worst goals conceded"]["fewest"]
    rank = _fn(js, "cmdRank")
    # fewest: smallest first; worst: the better way reversed (the most conceded first); the line says which end
    assert "end === 'fewest' ? true" in rank and "end === 'worst' ? !lowerBetter" in rank
    assert "' (worst first)'" in rank and "' (fewest first; more is better)'" in rank


def test_plural_verbs_and_best_roles_after_a_position(league):
    # Review round 3: "which forwards dribble the most" ranked Dribbled past (the opposite stat), plural verbs after a
    # position found nothing or the wrong stat, and "which forwards are the best finishers" found nothing.
    verbs = {"dribble": "take_ons_won", "shoot": "shots", "score": "goals", "assist": "assists", "head": "aerial_duels_won",
             "run": "distance", "press": "pressures", "carry": "progressive_carries", "pass": "progressive_passes"}
    qs = {}
    for v, key in verbs.items():
        qs[f"which forwards {v} the most"] = key
        qs[f"who {v}s the most" if not v.endswith(("ss", "sh")) else f"who {v}es the most"] = key
    qs["who carries the most"] = "progressive_carries"
    qs.update({"which forwards are the best finishers": "np_goals", "which forwards are the top scorers": "goals",
               "which midfielders are the best creators": "sca", "which forwards are the best dribblers": "take_ons_won",
               "which defenders are the best tacklers": "tkl_int_padj", "which forwards dribble the most": "take_ons_won"})
    qs.pop("who carrys the most", None)
    got = interpret(league, list(qs))["q"]
    bad = {q: (got[q]["do"], got[q]["key"]) for q, key in qs.items() if (got[q]["do"], got[q]["key"]) != ("rankKey", key)}
    assert not bad, bad
    assert got["which forwards are the best finishers"]["pos"] == "FW" and got["which midfielders are the best creators"]["pos"] == "MF"
