"""The dashboards' shared pieces: the per-visitor store (Regista.store in shared/regista.js), the seeds and helpers both
dashboards use (Regista.demo in shared/demo.js), the left panel's sections helper and the shared dashboard styles.

The store and the seeds run for real in node (skipped without node), with a stand-in localStorage that works, and one
that throws as a private window's can: the pages must work either way, and nothing touches storage at load.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[1] / "src/regista/static/shared"

STORAGE = """
let reads = 0;
function makeStorage(broken) {
  const data = new Map();
  return {
    get length() { if (broken) throw new Error('blocked'); return data.size; },
    key(i) { if (broken) throw new Error('blocked'); return [...data.keys()][i] ?? null; },
    getItem(k) { reads++; if (broken) throw new Error('blocked'); return data.has(k) ? data.get(k) : null; },
    setItem(k, v) { if (broken) throw new Error('blocked'); data.set(k, String(v)); },
    removeItem(k) { if (broken) throw new Error('blocked'); data.delete(k); },
    _data: data,
  };
}
"""


def run(body: str, broken: bool = False, preset: dict | None = None) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = (STORAGE + f"globalThis.localStorage = makeStorage({'true' if broken else 'false'});\n"
          + "".join(f"localStorage._data.set({json.dumps(k)}, {json.dumps(v)});\n" for k, v in (preset or {}).items())
          + "const window = globalThis; const readsBefore = reads;\n"
          + (SHARED / "regista.js").read_text() + "\n" + (SHARED / "demo.js").read_text() + "\n"
          + "const loadReads = reads - readsBefore;\nconst R = window.Regista, D = R.demo;\n"
          + "const out = (() => {\n" + body + "\n})();\nconsole.log(JSON.stringify(out));\n")
    res = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_loading_the_scripts_reads_no_storage_and_the_store_round_trips():
    out = run("""
      const before = loadReads;
      const fresh = R.store.get('x', { a: 1 });
      fresh.a = 2;                                        // a copy: the fallback is not changed
      const again = R.store.get('x', { a: 1 });
      const kept = R.store.set('x', { b: [1, 2] });
      return { before, again, kept, back: R.store.get('x', null), raw: localStorage._data.get('regista.demo.v1.x'),
               persistent: R.store.persistent() };
    """)
    assert out["before"] == 0
    assert out["again"] == {"a": 1} and out["kept"] is True and out["back"] == {"b": [1, 2]}
    assert out["raw"] == '{"b":[1,2]}' and out["persistent"] is True


def test_blocked_storage_falls_back_to_memory_and_the_seeds():
    out = run("""
      const seeded = D.conversations().length;
      const c = D.forPlayer('pl_bro_09').find(x => x.scout === 'maya');
      D.send(c.id, 'player', 'Thursday works.');
      D.setStage('pl_bro_09', 'Trial');
      return { seeded, last: D.conversation(c.id).msgs.slice(-1)[0].text, stage: D.shortlist().pl_bro_09.stage,
               kept: R.store.set('y', 1), persistent: R.store.persistent() };
    """, broken=True)
    assert out["seeded"] == 5 and out["last"] == "Thursday works." and out["stage"] == "Trial"
    assert out["kept"] is False and out["persistent"] is False


def test_one_conversation_store_for_both_sides():
    out = run("""
      const femi = D.forPlayer('pl_bro_09');
      const maya = D.forScout('maya');
      const before = { player: D.unread('player', 'pl_bro_09'), scout: D.unread('scout', 'maya') };
      const thread = femi.find(c => c.scout === 'maya');
      D.markRead(thread.id, 'player');
      D.send(thread.id, 'player', 'Thursday at ten works for me.', [femi[0].msgs[1]?.clips?.[0] || thread.msgs[1].clips[0]]);
      const seen = D.forScout('maya')[0];
      const after = { player: D.unread('player', 'pl_bro_09'), scout: D.unread('scout', 'maya') };
      D.setBlocked(thread.id, true);
      const refused = D.send(thread.id, 'scout', 'Hello?');
      const started = D.startConversation('maya', 'pl_ash_10', 'Hugo Delgado');
      const same = D.startConversation('maya', 'pl_ash_10');
      return { femi: femi.map(c => c.scout), maya: maya.map(c => c.player), before, after, top: seen.player,
               last: seen.msgs.slice(-1)[0], refused, started: started.id, same: same.id, empty: started.msgs.length,
               when: D.whenText(seen.msgs[0].at).length > 0 };
    """)
    assert sorted(out["femi"]) == ["maya", "priya", "tomas"]
    assert sorted(out["maya"]) == ["pl_bro_09", "pl_dun_06", "pl_eas_03"]
    assert out["before"] == {"player": 2, "scout": 1}
    assert out["after"] == {"player": 1, "scout": 2}       # Femi read Maya's; his reply is unread in her inbox
    assert out["top"] == "pl_bro_09" and out["last"]["from"] == "player"
    clip = out["last"]["clips"][0]
    assert clip["match_id"] == "rl_r07_bro_cal" and clip["clip_id"] == "cl_t_home_09_000005"
    assert clip["video_url"] == "/api/matches/rl_r07_bro_cal/clips/cl_t_home_09_000005.mp4"
    assert out["refused"] is None and out["started"] == out["same"] == "cv_maya_ash_10" and out["empty"] == 0
    assert out["when"] is True


def test_shortlist_compare_reports_needs_and_reset():
    out = run("""
      const seeded = D.shortlist();
      D.setNote('pl_cal_09', 'Quick feet.');                // a note adds a player as Watching
      D.setStage('pl_ash_09', '');                          // off the list
      const picks = ['pl_bro_09', 'pl_ash_10', 'pl_dun_06', 'pl_eas_03'].map(g => D.toggleCompare(g));
      const draft = D.draftReport('pl_ash_10', 'Hugo Delgado, midfielder, Ashby Athletic');
      const again = D.draftReport('pl_ash_10');
      const mid = { list: D.shortlist(), compare: D.compare(), reports: D.reports().map(r => [r.gid, r.draft]), same: draft.id === again.id };
      D.reset();
      return { seeded, mid, after: { list: Object.keys(D.shortlist()), compare: D.compare(), reports: D.reports().length,
               needs: D.needs().map(n => [n.pos, n.stat, n.pct]), settings: Object.keys(D.settings('scout')) },
               stages: D.STAGES, verdicts: D.VERDICTS, note: D.NOTE };
    """)
    assert {g: v["stage"] for g, v in out["seeded"].items()} == {
        "pl_bro_09": "Contacted", "pl_ash_10": "Watching", "pl_ash_09": "Watching", "pl_dun_06": "Trial", "pl_eas_03": "Offer"}
    mid = out["mid"]
    assert mid["list"]["pl_cal_09"]["stage"] == "Watching" and mid["list"]["pl_cal_09"]["note"] == "Quick feet."
    assert "pl_ash_09" not in mid["list"]
    assert mid["compare"] == ["pl_bro_09", "pl_ash_10", "pl_dun_06"]   # at most three
    assert mid["reports"][0] == ["pl_ash_10", True] and ["pl_bro_09", False] in mid["reports"] and mid["same"]
    after = out["after"]
    assert after["list"] == ["pl_bro_09", "pl_ash_10", "pl_ash_09", "pl_dun_06", "pl_eas_03"] and after["compare"] == []
    assert after["reports"] == 1 and after["needs"] == [["FW", "goals", 75], ["MF", "recoveries", 75], ["DF", "interceptions", 75]]
    assert "notify" in after["settings"]
    assert out["stages"] == ["Watching", "Contacted", "Trial", "Offer"] and out["verdicts"] == ["Sign", "Keep watching", "Pass"]
    assert out["note"] == "Messages, notes and reports are kept in this browser only."


def test_the_old_scout_shortlist_joins_the_new_one_once():
    out = run("return { list: D.shortlist(), stored: localStorage._data.has('regista.demo.v1.shortlist') };",
              preset={"regista-scout-shortlist": json.dumps([{"global_id": "pl_cal_07", "name": "x"}, {"global_id": "BAD"}])})
    assert out["list"]["pl_cal_07"]["stage"] == "Watching" and "BAD" not in out["list"] and out["stored"] is True
    assert out["list"]["pl_bro_09"]["stage"] == "Contacted"


def test_reset_also_forgets_the_old_scout_shortlist():
    # Otherwise the old key's players would be merged back into the restored seeds on the next read.
    out = run("D.shortlist(); D.reset(); return { list: Object.keys(D.shortlist()), old: localStorage._data.has('regista-scout-shortlist') };",
              preset={"regista-scout-shortlist": json.dumps([{"global_id": "pl_cal_07"}])})
    assert "pl_cal_07" not in out["list"] and out["old"] is False


def test_seeded_moments_are_femi_tourés_real_clips():
    # The seeds' clips must exist in the league as generated from data/season/league.json (clip ids repeat across
    # matches, so each is checked by match and clip id).
    out = run("return D.seeds().reports[0].sections.flatMap(s => s.cites).concat(D.seeds().conversations[0].msgs[1].clips);")
    from regista.season.profiles import load_season
    from regista import api

    p = load_season(api.SEASON_LEAGUE, api.SEASON_ROOT, [], []).player("pl_bro_09")
    have = {(m["match_id"], m["clip_id"]): m for m in p["moments"]}
    for ref in out:
        m = have.get((ref["match_id"], ref["clip_id"]))
        assert m is not None, ref
        assert m["title"] == ref["title"] and m["video_url"] == ref["video_url"]


def test_the_sections_helper_and_the_shared_styles():
    js = (SHARED / "regista.js").read_text()
    assert "window.Regista = { esc, reasonLabel, tagLabel, key, api, ApiError, authedObjectUrl, fmtTime, store, sections };" in js
    assert "const PREFIX = 'regista.demo.v1.';" in js
    css = (SHARED / "dashboard.css").read_text()
    assert ".views" not in css and "style=" not in css
    for rule in (".pf {", ".pf-head", ".pf-tile", ".pf-pitchsvg", ".mx {", ".st-toggle", ".tm-squad", ".sc-stage", ".sc-bar", ".ov-need"):
        assert rule in css, rule
    demo = (SHARED / "demo.js").read_text()
    assert "fetch(" not in demo and "R.api" not in demo  # nothing per visitor is sent to the server
