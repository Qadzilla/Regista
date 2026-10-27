"""Warm for judging (regista.warm, regista.api._prerender with tour=True) and the Foundry limits for judging.

The plan picks the URLs the pages ask for, from the JSON they read: Femi Toure's Goal reel (profile-view.js goalReelIds),
the demo match's recap reel (app.js recapButtons), Hector Santos's take-ons (profile-view.js openStat) and the first cards
of one competition's newest match in the Clip view (app.js fillPlayers and the grid's best-first sort). The URLs are then
requested through the app in-process (asgi_get), so the cache keys are exactly the pages'.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from regista import api, warm

STATIC = Path(__file__).resolve().parents[1] / "src/regista/static"


def mom(match, clip, tags=("goal",), reason="on_ball_main", rnd=1, t=10.0):
    return {"match_id": match, "clip_id": clip, "tags": list(tags), "reason": reason, "round": rnd, "t": t,
            "video_url": f"/api/matches/{match}/clips/{clip}.mp4"}


def test_the_goal_reel_is_each_goal_on_the_ball_once_in_match_order():
    profile = {"rows": [
        {"profile": {"moments": [mom("rl_r06", "c3", rnd=6), mom("rl_r01", "c2", rnd=1, t=55), mom("rl_r01", "c1", rnd=1, t=5),
                                 mom("rl_r01", "c9", reason="replay_appearance", rnd=1), mom("rl_r02", "c5", tags=("shot",), rnd=2),
                                 mom("rl_r01", "c1", rnd=1, t=5)]}},
        {"profile": {"moments": [mom("cm_x", "c7", rnd=None), {**mom("rl_r03", "c8", rnd=3), "video_url": "https://evil/x.mp4"}]}}]}
    assert warm.goal_reel(profile) == ["/api/matches/rl_r01/clips/c1.mp4", "/api/matches/rl_r01/clips/c2.mp4",
                                       "/api/matches/rl_r06/clips/c3.mp4", "/api/matches/cm_x/clips/c7.mp4"]


def test_the_recap_reel_is_its_clips_then_the_joined_download():
    recap = {"reel": ["a", "b", "nov"], "clips": {"a": {"video_url": "/api/matches/m/clips/a.mp4"},
                                                  "b": {"video_url": "/api/matches/m/clips/b.mp4"}, "nov": {"video_url": None}}}
    assert warm.recap_reel(recap, "m") == ["/api/matches/m/clips/a.mp4", "/api/matches/m/clips/b.mp4", "/api/matches/m/reel.mp4?clips=a,b"]
    assert warm.recap_reel({"reel": [], "clips": {}}, "m") == []
    # app.js links the same joined reel: the reel's ids that have a video, in order, joined by commas
    assert "matchUrl(`/reel.mp4?clips=${ids.map(enc).join(',')}`)" in (STATIC / "product/app.js").read_text()


def test_evidence_is_the_numbers_moments_with_a_clip_from_the_busiest_competition():
    item = lambda m, c: {"match_id": m, "clip_id": c, "video_url": f"/api/matches/{m}/clips/{c}.mp4"}  # noqa: E731
    profile = {"rows": [
        {"sample": {"minutes": 40}, "profile": {"evidence": {"take_ons_won": {"items": [item("x", "c0")]}}}},
        {"sample": {"minutes": 85}, "profile": {"evidence": {"take_ons_won": {"items": [item("m", "c1"), {"match_id": "m", "clip_id": None},
                                                                                         item("m", "c2")]}}}}]}
    assert warm.evidence(profile, "take_ons_won") == ["/api/matches/m/clips/c1.mp4", "/api/matches/m/clips/c2.mp4"]
    assert warm.evidence({"rows": []}, "take_ons_won") == []


def test_the_clip_views_default_player_and_its_first_cards():
    info = {"players": [{"player_id": "t_away_02", "team_id": "t_away", "kit_number": 2},
                        {"player_id": "t_home_09", "team_id": "t_home", "kit_number": 9},
                        {"player_id": "t_home_04", "team_id": "t_home", "kit_number": 4}],
            "moment_counts": {"t_home_09": 7, "t_home_04": 7, "t_away_02": 3}}
    assert warm.default_player(info) == "t_home_04"   # most moments; a tie keeps team, then kit order (app.js fillPlayers)
    assert warm.default_player({"players": info["players"], "moment_counts": {}}) == "t_away_02"
    clips = [{"player_id": "t_home_04", "watchability": 0.2, "t": 5, "video_url": "/api/matches/m/clips/a.mp4"},
             {"player_id": "t_home_04", "label": {"watchability": 0.9}, "t": 9, "video_url": "/api/matches/m/clips/b.mp4"},
             {"player_id": "t_home_04", "watchability": 0.9, "t": 1, "video_url": "/api/matches/m/clips/c.mp4"},
             {"player_id": "t_away_02", "watchability": 1.0, "t": 1, "video_url": "/api/matches/m/clips/d.mp4"}]
    assert warm.grid_first(clips, "t_home_04", n=2) == ["/api/matches/m/clips/c.mp4", "/api/matches/m/clips/b.mp4"]


def test_download_reel_is_the_players_moments_best_first_at_most_twelve():
    clips = [{"id": f"c{i}", "player_id": "p", "watchability": i / 20, "t": i, "video_url": f"/api/matches/m/clips/c{i}.mp4"} for i in range(14)]
    clips.append({"id": "other", "player_id": "q", "watchability": 1.0, "t": 0, "video_url": "/api/matches/m/clips/other.mp4"})
    (url,) = warm.download_reel(clips, "m", "p")
    assert url == "/api/matches/m/reel.mp4?clips=" + ",".join(f"c{i}" for i in range(13, 1, -1))
    assert warm.download_reel(clips, "m", "nobody") == []
    assert "dl.href = matchUrl(`/reel.mp4?clips=${ids.map(enc).join(',')}`)" in (STATIC / "product/app.js").read_text()


def test_the_plan_reads_what_the_pages_read_and_skips_a_part_that_fails():
    calls, logged = [], []
    answers = {
        "/api/catalogue/players/pl_bro_09?include=profile&moments=0": {"rows": [{"profile": {"moments": [mom("rl_r01", "g1")]}}]},
        "/api/matches/syn_0294/recap?player=t_home_09&engine=rules": {"reel": ["r1"], "clips": {"r1": {"video_url": "/api/matches/syn_0294/clips/r1.mp4"}}},
        "/api/matches/syn_0294/clips": [{"id": "r1", "player_id": "t_home_09", "label": {"watchability": 0.4}, "t": 3,
                                         "video_url": "/api/matches/syn_0294/clips/r1.mp4"},
                                        {"id": "r2", "player_id": "t_home_09", "label": {"watchability": 0.8}, "t": 9,
                                         "video_url": "/api/matches/syn_0294/clips/r2.mp4"}],
        "/api/competitions/co_esp_u19": {"matches": [{"match_id": "cm_old", "date": "2026-09-05", "round": 1},
                                                     {"match_id": "cm_new", "date": "2026-10-17", "round": 3}]},
        "/api/matches/cm_new": {"players": [{"player_id": "t_home_02", "team_id": "t_home", "kit_number": 2}], "moment_counts": {"t_home_02": 1}},
        "/api/matches/cm_new/clips": [{"player_id": "t_home_02", "watchability": 0.5, "t": 1, "video_url": "/api/matches/cm_new/clips/k.mp4"}],
    }

    def get_json(path):
        calls.append(path)
        if path not in answers:
            raise RuntimeError(f"GET {path} answered 404")
        return answers[path]

    urls = warm.plan(get_json, log=logged.append)
    assert urls == ["/api/matches/rl_r01/clips/g1.mp4", "/api/matches/syn_0294/clips/r1.mp4", "/api/matches/syn_0294/reel.mp4?clips=r1",
                    "/api/matches/syn_0294/reel.mp4?clips=r2,r1", "/api/matches/cm_new/clips/k.mp4"]
    assert calls[3] == "/api/catalogue/players/pl_pnr_11?include=profile&moments=0" and len(logged) == 1 and "scout evidence" in logged[0]


def test_asgi_get_asks_the_app_itself():
    status, headers, body = asyncio.run(warm.asgi_get(api.app, "/api/health"))
    assert status == 200 and headers["content-type"].startswith("application/json") and json.loads(body)["ok"] is True
    status, _h, _b = asyncio.run(warm.asgi_get(api.app, "/api/matches/no_such_match/clips"))
    assert status == 404
    get_json, _get_video = warm.fetchers(api.app)
    assert get_json("/api/health")["ok"] is True
    with pytest.raises(RuntimeError):
        get_json("/api/matches/no_such_match")


def test_a_video_warmed_in_process_is_the_file_the_endpoint_serves(monkeypatch, tmp_path):
    sample = Path(__file__).resolve().parents[1] / "data/synthetic/sample"
    monkeypatch.setattr(api, "DATA_ROOT", sample)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path)
    rendered = []

    def fake_render_once(out, render):   # no ffmpeg: a stand-in file where the renderer would put it
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 64)
        rendered.append(out)
        return out

    monkeypatch.setattr(api, "_render_once", fake_render_once)
    _gj, get_video = warm.fetchers(api.app)
    status, ctype = get_video("/api/matches/syn_0294/clips/cl_t_home_09_000002.mp4")
    assert status == 200 and ctype == "video/mp4"
    assert rendered == [api._clip_cache_path("syn_0294", "cl_t_home_09_000002", 25.0, 1280)]   # the page's own cache key


def test_prerender_with_the_tour_counts_its_part(monkeypatch):
    monkeypatch.setattr(api, "PRERENDER_PROGRESS", dict(api.PRERENDER_PROGRESS))
    monkeypatch.setattr(api, "_render_clip_cached", lambda d, c, label, fps, width: Path("x.mp4"))
    asked = []

    def fake_fetchers(app):
        assert app is api.app
        return (lambda path: {}), (lambda url: asked.append(url) or ((200, "video/mp4") if "good" in url else (503, "application/json")))

    monkeypatch.setattr(warm, "fetchers", fake_fetchers)
    monkeypatch.setattr(warm, "plan", lambda get_json, log=print: ["/api/matches/m/clips/good1.mp4", "/api/matches/m/clips/bad.mp4",
                                                                    "/api/matches/m/clips/good2.mp4"])
    api._prerender(tour=True)
    p = api.PRERENDER_PROGRESS
    assert asked == ["/api/matches/m/clips/good1.mp4", "/api/matches/m/clips/bad.mp4", "/api/matches/m/clips/good2.mp4"]
    assert p["tour"] == {"planned": 3, "rendered": 2, "failed": 1} and p["running"] is False
    assert p["total"] == p["rendered"] + p["failed"] and p["failed"] == 1
    # without the flag (tests, the Studio's progress test) nothing beyond the featured player's clips is asked for
    asked.clear()
    api._prerender()
    assert asked == [] and api.PRERENDER_PROGRESS["tour"] is None


def test_the_startup_thread_warms_the_tour():
    src = Path(api.__file__).read_text()
    assert 'threading.Thread(target=_prerender, kwargs={"tour": True}, name="regista-prerender", daemon=True).start()' in src


@pytest.mark.slow
def test_the_plan_on_the_real_app_finds_every_part():
    get_json, _gv = warm.fetchers(api.app)
    urls = warm.plan(get_json, log=lambda m: pytest.fail(m))
    assert sum("/rl_r" in u for u in urls) == 5   # Femi Toure's five league goals
    assert any("/syn_0294/reel.mp4?clips=" in u for u in urls)
    assert any("/cm_eu19_" in u and "_t_home_11_" in u for u in urls)   # Hector Santos's take-ons
    assert all(u.startswith("/api/matches/") for u in urls)


# ---------------------------------------------------------------------------- Foundry limits for judging

def test_ask_limits_for_judging_are_the_defaults_and_each_env_overrides_its_own(monkeypatch):
    for var in ("REGISTA_ASK_PER_MIN", "REGISTA_ASK_PER_HOUR", "REGISTA_ASK_TOTAL_PER_HOUR", "REGISTA_ASK_TOTAL_PER_DAY", "REGISTA_ASK_CONCURRENT"):
        monkeypatch.delenv(var, raising=False)
    lim = api.AskLimiter.from_env()
    assert [cap for _w, cap, _v in lim.rules] == [5, 40, 120, 600] and lim.concurrent == 3
    monkeypatch.setenv("REGISTA_ASK_PER_MIN", "2")
    monkeypatch.setenv("REGISTA_ASK_CONCURRENT", "0")   # never below one at a time
    lim = api.AskLimiter.from_env()
    assert [cap for _w, cap, _v in lim.rules] == [2, 40, 120, 600] and lim.concurrent == 1
