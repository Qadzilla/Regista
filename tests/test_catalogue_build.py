"""The catalogue's matches (docs/catalogue/build/design.md §5, §6 and §11, items 6, 7 and 12): regenerated from the
competition files into league-mode match folders with the catalogue's manifest, the same bits on every platform
(``regista.catalogue.pins``, checked on Linux in CI and inside the image), team style re-centred per competition by the
generator's one inert change (``style_offset``), and reachable through the Clip view's endpoints by their ``cm_`` ids.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.catalogue import store
from regista.catalogue.build import _labels_current, build_catalogue, ensure_tracks, materialise_match
from regista.catalogue.pins import CATALOGUE_PINS, drift
from regista.schema import SCHEMA_VERSION, clips_validator, events_validator, iter_jsonl
from regista.season.league import generate_kwargs, load_league
from regista.season.playing_time import played_seconds
from regista.synth.generator import LEAGUE_GENERATOR_VERSION, MatchSim, generate

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"   # git-ignored: built here once, like the league's data/season/matches


@pytest.fixture(scope="module")
def comps():
    return store.new_competitions(INDEX)


@pytest.fixture(scope="module")
def built(comps):
    """Every catalogue match, built as the server builds it (one pool of spawned processes; current folders are kept)."""
    build_catalogue(comps, MATCHES)
    return MATCHES


def _fx(comps, cid, i=0):
    comp = next(c for c in comps if c["competition"]["competition_id"] == cid)
    return comp, comp["fixtures"][i]


def test_every_catalogue_match_is_pinned_and_the_same_on_every_platform(comps, built):
    """Recorded on macOS (regista.catalogue.pins); on CI this runs on Linux, where the live app builds the catalogue."""
    assert set(CATALOGUE_PINS) == {f["match_id"] for c in comps for f in c["fixtures"]} and len(CATALOGUE_PINS) == 60
    moved = drift(comps, built)
    assert not moved, f"{len(moved)} of {len(CATALOGUE_PINS)} catalogue matches generated differently here: {sorted(moved)}"


def test_catalogue_manifests_carry_the_competition_uploader_and_camera(comps, built):
    for comp in comps:
        labels = comp["competition"]
        for fx in comp["fixtures"]:
            m = json.loads((built / fx["match_id"] / "manifest.json").read_text())
            assert m["collection"] == "catalogue" and m["competition"] == comp["league"] == m["league"]
            assert {k: m[k] for k in ("competition_id", "country", "region", "tier", "age_group", "gender")} == \
                {k: labels[k] for k in ("competition_id", "country", "region", "tier", "age_group", "gender")}
            assert m["uploader"] == fx["uploader"] and m["camera"] == fx["camera"]
            assert m["title"].startswith(f"Round {fx['round']}: ") and "matchday" not in m["title"] + m["subtitle"]
            assert "synthetic uploaded match" in m["subtitle"] and "camera type is a label" in m["subtitle"]
            assert m["generator"]["seed"] == fx["seed"] and m["generator"]["version"] == LEAGUE_GENERATOR_VERSION


@pytest.mark.parametrize("cid", ["co_eng_sp_women", "co_usa_col_men", "co_nga_am_men", "co_gha_u17"])
def test_a_catalogue_match_validates_as_league_mode(comps, built, cid):
    comp, fx = _fx(comps, cid)
    ev, cl = events_validator(), clips_validator()
    stream = list(iter_jsonl(built / fx["match_id"] / "events.jsonl"))
    bad = [(r.get("id"), ev.errors(r)) for r in stream if not ev.is_valid(r)]
    assert not bad, bad[:3]
    assert {r["schema_version"] for r in stream} == {SCHEMA_VERSION}
    assert any(r["type"] == "physical" for r in stream)
    clips = list(iter_jsonl(built / fx["match_id"] / "clips.jsonl"))
    assert clips and all(cl.is_valid(r) for r in clips)
    squad = {p["global_id"] for c in comp["clubs"] if c["club_id"] in (fx["home"], fx["away"]) for p in c["squad"]}
    header = next(r for r in stream if r["type"] == "match")
    assert {p["global_player_id"] for p in header["players"]} == squad


def test_career_players_have_minutes_in_both_competitions(comps, built):
    index = store.load_index(INDEX)
    by_id = {c["competition"]["competition_id"]: c for c in comps}
    for car in index["careers"]:
        for cid, club in zip(car["competitions"], car["clubs"]):
            secs = 0.0
            for fx in by_id[cid]["fixtures"]:
                if club not in (fx["home"], fx["away"]):
                    continue
                stream = list(iter_jsonl(built / fx["match_id"] / "events.jsonl"))
                header = next(r for r in stream if r["type"] == "match")
                pid = next(p["player_id"] for p in header["players"] if p.get("global_player_id") == car["global_id"])
                secs += played_seconds(stream).get(pid, 0.0)
            assert secs > 0, (car["global_id"], cid)


def test_style_offset_recentres_team_style_and_is_inert_without_it(comps):
    comp, fx = _fx(comps, "co_esp_am_men")
    kw = generate_kwargs(comp, fx)
    assert all(t["style_offset"] == comp["level"]["style_offset"] for t in kw["teams"])
    with_key = MatchSim(**{**kw, "minutes": 0.1})
    plain = copy.deepcopy(kw)
    for t in plain["teams"]:
        del t["style_offset"]
    without = MatchSim(**{**plain, "minutes": 0.1})
    # without the re-centring every amateur side sits at the clamp: all sides would keep the ball alike
    assert all(t.style["keep"] == -2.5 for t in (without.home, without.away))
    assert all(-2.5 < t.style["keep"] < 2.5 for t in (with_key.home, with_key.away))
    assert with_key.home.style["keep"] != with_key.away.style["keep"]
    # the Regista League's arguments never carry the key (league.json has no level), so its pins hold
    league = load_league(ROOT / "data" / "season" / "league.json")
    assert all("style_offset" not in t for t in generate_kwargs(league, league["fixtures"][0])["teams"])
    assert all("style_offset" not in t for t in generate_kwargs(comp, fx, ratings=False)["teams"])


def test_changed_labels_rebuild_the_folder_and_tracks_match_a_fresh_generate(comps, built, tmp_path):
    comp, fx = _fx(comps, "co_mar_u19")
    shutil.copytree(built / fx["match_id"], tmp_path / fx["match_id"])
    assert _labels_current(comp, fx, tmp_path)
    other = copy.deepcopy(fx)
    other["camera"] = "drone" if fx["camera"] != "drone" else "phone"
    assert not _labels_current(comp, other, tmp_path)
    d = ensure_tracks(comp, fx, tmp_path)
    fresh = generate(**generate_kwargs(comp, fx))
    lines = (d / "tracks.jsonl").read_text().splitlines()
    assert len(lines) == len(fresh.tracks) and json.loads(lines[0]) == fresh.tracks[0] and json.loads(lines[-1]) == fresh.tracks[-1]
    assert hashlib.sha256((d / "events.jsonl").read_bytes()).hexdigest()[:16] == CATALOGUE_PINS[fx["match_id"]]
    m = materialise_match(comp, other, tmp_path)   # the new camera label: rebuilt, same events
    assert json.loads((m / "manifest.json").read_text())["camera"] == other["camera"]
    assert hashlib.sha256((m / "events.jsonl").read_bytes()).hexdigest()[:16] == CATALOGUE_PINS[fx["match_id"]]


def test_a_catalogue_match_opens_in_the_clip_view_endpoints(comps, built, tmp_path, monkeypatch):
    from regista import api

    comp, fx = _fx(comps, "co_jpn_uni_men")
    shutil.copytree(built / fx["match_id"], tmp_path / fx["match_id"])
    monkeypatch.setattr(api, "CATALOGUE", INDEX)
    monkeypatch.setattr(api, "CATALOGUE_ROOT", tmp_path)
    c = TestClient(api.app)
    m = c.get(f"/api/matches/{fx['match_id']}").json()
    assert m["title"].startswith(f"Round {fx['round']}: ") and "matchday" not in m["subtitle"] and m["clip_count"] > 0
    clips = c.get(f"/api/matches/{fx['match_id']}/clips").json()
    assert clips and isinstance(clips, (list, dict))
    assert c.get(f"/api/matches/{fx['match_id']}/recap").status_code == 200
    assert c.get("/api/matches/cm_nope_01_aaa_bbb").status_code == 404
    assert api._is_season_match(fx["match_id"]) and not api._is_season_match("cm_nope_01_aaa_bbb")
    assert fx["match_id"] not in {x["match_id"] for x in c.get("/api/matches").json()}   # the Product's list is unchanged


def test_the_image_check_passes_on_the_built_catalogue_and_names_a_match_that_differs(comps, built, tmp_path):
    from regista.cloud.smoke import catalogue_checks

    [ok] = catalogue_checks(INDEX, built)
    assert ok["ok"] and ok["differs"] == {}
    comp, fx = _fx(comps, "co_ger_sp_men")
    shutil.copytree(built / fx["match_id"], tmp_path / fx["match_id"])
    with open(tmp_path / fx["match_id"] / "events.jsonl", "a") as f:
        f.write("\n")
    [bad] = catalogue_checks(INDEX, tmp_path)
    assert not bad["ok"] and bad["differs"][fx["match_id"]] != "missing"
    assert sum(v == "missing" for v in bad["differs"].values()) == 59


def test_a_stale_folder_is_removed_under_the_match_lock_and_a_failed_pool_is_logged(comps, built, tmp_path, monkeypatch,
                                                                                  caplog):
    """Review A round 3 nits: materialise_match removes a folder with stale labels only while holding the lock its build
    takes (so it never deletes a folder another thread is writing), and build_catalogue logs a process pool that fails
    before it builds the matches here, one by one."""
    import concurrent.futures
    import logging

    from regista.catalogue import build as cbuild
    from regista.season import build as season_build

    comp, fx = _fx(comps, "co_gha_u17")
    shutil.copytree(built / fx["match_id"], tmp_path / fx["match_id"])
    other = copy.deepcopy(fx)
    other["camera"] = "drone" if fx["camera"] != "drone" else "phone"
    held = []
    real_rmtree = cbuild.shutil.rmtree

    def rmtree(path, *a, **kw):
        held.append(season_build.match_lock(fx["match_id"]).locked())
        return real_rmtree(path, *a, **kw)

    monkeypatch.setattr(cbuild.shutil, "rmtree", rmtree)
    materialise_match(comp, other, tmp_path)
    assert held and held[0] is True
    monkeypatch.setattr(cbuild.shutil, "rmtree", real_rmtree)

    class Broken:
        def __init__(self, *a, **kw):
            raise OSError("no worker processes here")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", Broken)
    one = copy.deepcopy(comp)
    one["fixtures"] = [copy.deepcopy(f) for f in comp["fixtures"][:2]]
    for f in one["fixtures"]:
        f["camera"] = next(c for c in ("tripod", "phone", "drone", "broadcast")
                           if c not in (f["camera"], other["camera"]))   # stale labels: both need a rebuild
        if not (tmp_path / f["match_id"]).exists():
            shutil.copytree(built / f["match_id"], tmp_path / f["match_id"])
    with caplog.at_level(logging.WARNING, logger="regista.catalogue.build"):
        paths = build_catalogue([one], tmp_path, workers=2)
    assert len(paths) == 2 and "process pool failed" in caplog.text
    assert all(json.loads((p / "manifest.json").read_text())["camera"] == f["camera"] for p, f in zip(paths, one["fixtures"]))
