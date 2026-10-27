"""The daily live check (regista.live_check, .github/workflows/live-check.yml): read-only GETs with no key, every check
reported, a failure makes the run fail. ``fetch`` is injected, so nothing here reaches the network; one test runs the
probe against the app itself."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import live_check

REPO = Path(__file__).resolve().parents[1]
BASE = "https://example.test"
HEALTH = {"ok": True, "cloud": {"foundry": True, "model": "gpt-5-mini", "cosmos": True, "search": True}, "azure_mcp": True,
          "tracing": True, "container_apps": True, "storage": True}
PAGE = b"<!doctype html><p class=\"brand\">REGI<span>STA</span></p>"
CLIP = "/api/matches/syn_0294/clips/cl_t_home_09_000002.mp4"


def site(**over):
    """A fake live app: path -> (status, content type, body); over replaces answers."""
    answers = {"/api/health": (200, "application/json", json.dumps(HEALTH).encode()),
               "/api/catalogue": (200, "application/json", json.dumps({"totals": {"competitions": 14, "countries": 10, "clubs": 66,
                                                                                    "players": 1183, "matches": 90}}).encode()),
               f"/api/matches/syn_0294/clips?player=t_home_09": (200, "application/json", json.dumps([{"video_url": CLIP}]).encode()),
               CLIP: (200, "video/mp4", b"\x00\x00\x00\x18ftypmp42")}
    for p in live_check.PAGES:
        answers[p] = (200, "text/html; charset=utf-8", PAGE)
    answers.update(over)
    seen = []

    def fetch(url, timeout):
        assert url.startswith(BASE + "/")
        path = url[len(BASE):]
        seen.append(path)
        if path not in answers:
            return 404, "application/json", b'{"detail":"Not Found"}'
        a = answers[path]
        if isinstance(a, Exception):
            raise a
        return a

    fetch.seen = seen
    return fetch


def failed(results):
    return [r["check"] for r in results if not r["ok"]]


def test_a_healthy_app_passes_every_check_and_asks_only_reads():
    f = site()
    results = live_check.run(BASE, fetch=f)
    assert failed(results) == [] and len(results) == 2 + len(live_check.PAGES) + 2
    assert f.seen[0] == "/api/health" and f.seen[-1] == CLIP and set(live_check.PAGES) <= set(f.seen)
    assert {"/", "/demo", "/scout", "/me", "/players/pl_bro_09"} == set(live_check.PAGES)


@pytest.mark.parametrize("over, check", [
    ({"/api/health": (503, "application/json", b"{}")}, "health"),
    ({"/api/health": (200, "application/json", json.dumps({**HEALTH, "storage": False}).encode())}, "health services"),
    ({"/api/health": (200, "application/json", json.dumps({**HEALTH, "cloud": {**HEALTH["cloud"], "foundry": False}}).encode())}, "health services"),
    ({"/demo": (404, "application/json", b"{}")}, "page /demo"),
    ({"/scout": (200, "application/json", b"{}")}, "page /scout"),
    ({"/api/catalogue": (200, "application/json", json.dumps({"totals": {"competitions": 13, "countries": 10, "matches": 90}}).encode())},
     "catalogue totals"),
    ({CLIP: (503, "application/json", b"{}")}, "clip video"),
    ({CLIP: (200, "text/html", PAGE)}, "clip video"),
    ({"/api/matches/syn_0294/clips?player=t_home_09": (200, "application/json", b"[]")}, "clip video"),
    ({"/me": TimeoutError("timed out")}, "GET /me"),
])
def test_each_failure_is_reported_never_a_crash(over, check):
    assert check in failed(live_check.run(BASE, fetch=site(**over)))


def test_main_fails_loudly_and_stops_checking_after_judging(monkeypatch, capsys):
    monkeypatch.setattr(live_check, "run", lambda url, services: [{"check": "health", "ok": False, "detail": "HTTP 503"}])
    assert live_check.main(["--url", BASE]) == 1
    assert "FAIL  health: HTTP 503" in capsys.readouterr().out
    monkeypatch.setattr(live_check, "run", lambda url, services: [{"check": "health", "ok": True, "detail": "HTTP 200"}])
    assert live_check.main(["--url", BASE, "--services", ""]) == 0
    monkeypatch.setattr(live_check, "run", lambda *a, **k: pytest.fail("no request after judging"))
    assert live_check.main(["--until", "2000-01-01"]) == 0
    assert "Judging is over" in capsys.readouterr().out


def test_http_fetch_sends_a_plain_get_with_no_key(monkeypatch):
    sent = []

    class Answer:
        status = 200
        headers = {"content-type": "video/mp4"}

        def read(self, n=-1):
            return b"x" * (n if n > 0 else 10)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        sent.append(req)
        return Answer()

    monkeypatch.setattr(live_check.urllib.request, "urlopen", urlopen)
    status, ctype, body = live_check.http_fetch(BASE + CLIP, 5)
    assert status == 200 and ctype == "video/mp4" and len(body) == live_check.PEEK   # a video: only its first bytes
    req = sent[0]
    assert req.get_method() == "GET" and req.data is None
    assert {k.lower() for k in req.headers} <= {"user-agent", "accept-encoding"}   # no token, no cookie


def test_the_probe_passes_against_the_app_itself(monkeypatch, tmp_path):
    from regista import api

    monkeypatch.setattr(api, "DATA_ROOT", REPO / "data/synthetic/sample")
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)

    def fake_render_once(out, render):   # no ffmpeg in this test: a stand-in where the clip would be
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        return out

    monkeypatch.setattr(api, "_render_once", fake_render_once)
    c = TestClient(api.app)

    def fetch(url, timeout):
        r = c.get(url[len("http://testserver"):])
        return r.status_code, r.headers.get("content-type", ""), r.content

    results = live_check.run("http://testserver", fetch=fetch, services=(), catalogue={})   # the catalogue builds in its own tests
    assert failed(results) == [], results


def test_the_probe_is_standard_library_only_so_the_workflow_runs_it_as_a_script():
    tree = ast.parse((REPO / "src/regista/live_check.py").read_text())
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert mods <= {"__future__", "argparse", "datetime", "json", "sys", "urllib", "typing"}, mods


def test_the_workflow_checks_daily_until_judging_ends_with_no_secret():
    wf = (REPO / ".github/workflows/live-check.yml").read_text()
    assert "schedule:" in wf and "cron:" in wf and "workflow_dispatch:" in wf
    assert "permissions:\n  contents: read" in wf
    assert "python src/regista/live_check.py --until 2026-11-11" in wf
    assert "secrets." not in wf and "token" not in wf.lower() and "pip install" not in wf
    assert live_check.UNTIL == "2026-11-11" and live_check.LIVE_URL.startswith("https://regista-api.")
