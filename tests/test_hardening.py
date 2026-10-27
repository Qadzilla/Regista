"""Public render endpoints cannot stall the app or fill its disk, and the status CLI keeps its key to itself (audit J2)."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample"
CLIP = "cl_t_home_09_000002"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DATA_ROOT", SAMPLE)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    with TestClient(api.app) as c:
        yield c


@pytest.mark.parametrize("params", [{"width": 1905}, {"width": 320}, {"fps": 60}, {"fps": 24.5}, {"width": 640, "fps": 30}])
def test_only_the_sizes_the_pages_use_are_rendered(client, params):
    for path, more in ((f"/api/matches/syn_0294/clips/{CLIP}.mp4", {}), ("/api/matches/syn_0294/video.mp4", {}),
                       ("/api/matches/syn_0294/reel.mp4", {"clips": CLIP})):
        r = client.get(path, params={**params, **more})
        assert r.status_code == 400 and "width" in r.json()["detail"], (path, params)
    assert not api.CACHE_ROOT.exists(), "a refused size must not render anything"


def test_a_full_render_queue_answers_503_and_renders_nothing(client, monkeypatch):
    monkeypatch.setitem(api._render_waiting, "n", api.RENDER_QUEUE_MAX)
    r = client.get(f"/api/matches/syn_0294/clips/{CLIP}.mp4")
    assert r.status_code == 503 and r.headers["retry-after"] == "10"
    assert not api.CACHE_ROOT.exists()


def test_cached_videos_are_served_even_when_the_queue_is_full(client, monkeypatch):
    out = api._clip_cache_path("syn_0294", CLIP, 25.0, 1280)
    out.parent.mkdir(parents=True)
    out.write_bytes(b"cached video")
    monkeypatch.setitem(api._render_waiting, "n", api.RENDER_QUEUE_MAX)
    r = client.get(f"/api/matches/syn_0294/clips/{CLIP}.mp4")
    assert r.status_code == 200 and r.content == b"cached video" and not api._serving


def test_health_answers_while_renders_are_queued(client, monkeypatch):
    """Requests waiting for a render hold no thread of the pool every other endpoint uses (J2's repro stalled /api/health)."""
    import threading
    import time

    gate = threading.Event()

    def slow_job(d, clip, label, fps, width):
        def render(tmp):
            gate.wait(20)
            tmp.write_bytes(b"v")
            return {"path": str(tmp)}
        return api._clip_cache_path(d.name, clip["id"], fps, width), render

    monkeypatch.setattr(api, "_render_clip_job", slow_job)
    clips = [c["id"] for c in client.get("/api/matches/syn_0294/clips").json()][:12]
    results: list[int] = []
    threads = [threading.Thread(target=lambda cid=cid: results.append(client.get(f"/api/matches/syn_0294/clips/{cid}.mp4").status_code))
               for cid in clips * 4]
    for t in threads:
        t.start()
    time.sleep(0.5)
    started = time.monotonic()
    assert client.get("/api/health").status_code == 200
    assert time.monotonic() - started < 2.0
    gate.set()
    for t in threads:
        t.join(30)
    assert results.count(200) + results.count(503) == len(threads) and 200 in results


def _video(path: Path, size: int, age_s: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    t = path.stat().st_mtime - age_s
    os.utime(path, (t, t))
    return path


def test_the_cache_evicts_least_recently_served_first_never_a_file_in_use(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(api, "CACHE_MAX_BYTES", 2500)
    oldest = _video(tmp_path / "m1" / "a_25fps_1280.mp4", 1000, 400)
    served = _video(tmp_path / "m1" / "b_25fps_1280.mp4", 1000, 300)
    older = _video(tmp_path / "m2" / "c_25fps_1280.mp4", 1000, 200)
    partial = _video(tmp_path / "m2" / ".d_25fps_1280.1234abcd.part.mp4", 1000, 500)
    new = _video(tmp_path / "m2" / "e_25fps_1280.mp4", 1000, 0)
    monkeypatch.setitem(api._serving, served, 1)
    api._evict_cache(keep=new)
    assert not oldest.exists() and not older.exists()
    assert served.exists() and partial.exists() and new.exists()


def test_render_once_keeps_the_cache_within_its_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)
    monkeypatch.setattr(api, "CACHE_MAX_BYTES", 2500)

    def render(tmp):
        tmp.write_bytes(b"v" * 1000)
        return {"path": str(tmp)}

    for i in range(5):
        api._render_once(tmp_path / "m" / f"c{i}_25fps_1280.mp4", render)
    assert sorted(p.name for p in (tmp_path / "m").iterdir()) == ["c3_25fps_1280.mp4", "c4_25fps_1280.mp4"]


def test_deploy_refuses_without_the_admin_key():
    """The cloud app fails closed without a key, but a deploy must not silently drop it either."""
    text = (Path(__file__).resolve().parents[1] / "infra" / "deploy-app.sh").read_text()
    refusal = text.index('if [[ -z "${REGISTA_ADMIN_TOKEN:-}" ]]; then')
    assert "exit 1" in text[refusal:refusal + 300] and refusal < text.index("az containerapp")
    assert "warning: REGISTA_STUDIO_VIEW_TOKEN is not set" in text


# ---------------------------------------------------------------------------- the status CLI

@pytest.mark.parametrize("url, safe", [("https://regista.example", True), ("http://127.0.0.1:8000", True), ("http://localhost:8000", True),
                                       ("http://[::1]:8000", True), ("http://regista.example", False), ("ftp://127.0.0.1", False)])
def test_the_status_cli_sends_its_key_only_over_https_or_to_this_machine(url, safe):
    from regista.studio.__main__ import key_is_safe_to_send

    assert key_is_safe_to_send(url) is safe


def test_the_status_cli_key_never_follows_a_redirect(monkeypatch):
    from regista.studio import __main__ as cli

    seen = []

    class Done(Exception):
        pass

    def fake_urlopen(req, timeout):
        seen.append(req)
        raise Done

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(Done):
        cli.fetch_overview("https://regista.example", "the-key")
    req = seen[0]
    assert req.unredirected_hdrs.get("X-regista-token") == "the-key" and "X-regista-token" not in req.headers


def test_the_status_cli_drops_the_key_over_plain_http(monkeypatch, capsys):
    from regista.studio import __main__ as cli

    monkeypatch.setenv("REGISTA_DOTENV", "")
    monkeypatch.setenv("REGISTA_STUDIO_VIEW_TOKEN", "the-key")
    sent = []
    monkeypatch.setattr(cli, "fetch_overview", lambda url, key: sent.append(key) or (_ for _ in ()).throw(OSError("down")))
    assert cli.main(["status", "--url", "http://regista.example"]) == 2
    assert sent == [None] and "not sent" in capsys.readouterr().err


def test_the_render_queue_count_returns_to_zero_when_two_threads_render_at_once(monkeypatch):
    """The startup warm-up calls _video from its own thread and loop, beside the server's (fixes-1): the waiting count is
    changed under a lock, so no decrement is lost and cold renders never start answering 503 for good."""
    import asyncio
    import threading

    from fastapi import HTTPException

    monkeypatch.setattr(api, "_render_once", lambda out, render: out)   # renders nothing: _video then answers 503
    missing = api.CACHE_ROOT / "nowhere" / "never.mp4"

    def many():
        for _ in range(150):
            try:
                asyncio.run(api._video(missing, None))
            except HTTPException:
                pass

    threads = [threading.Thread(target=many) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert api._render_waiting["n"] == 0
    assert isinstance(api._render_waiting_guard, type(threading.Lock()))

