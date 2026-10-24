"""Honest numbers on a small season (review round 2): the sample size is stated, metrics a season cannot yet separate are
marked noisy (split-half reliability, ``regista.season.reliability``), and every metric says how far its league-wide level
is checked against the Premier League (``regista.season.metrics.REALISM``)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista.season import reliability
from regista.season.league import load_league, new_league, save_league
from regista.season.metrics import CATALOGUE, DEFAULT_COLUMNS, REALISM, build_season, realism
from regista.synth.generator import LEAGUE_GENERATOR_VERSION
from regista.synth.report import INDIVIDUAL_NORMS, LEAGUE_NORMS, NORMS, PHYSICAL_NORMS, ROLE_SHAPES, STYLE_NORMS

ROOT = Path(__file__).resolve().parents[1]
LEAGUE_PATH = ROOT / "data" / "season" / "league.json"
STAR = "pl_bro_09"
BANDS = set(NORMS) | set(LEAGUE_NORMS) | set(INDIVIDUAL_NORMS) | set(PHYSICAL_NORMS) | set(STYLE_NORMS) \
    | {f"shape_{k}" for k in ROLE_SHAPES}


# ---------------------------------------------------------------------------- the committed table

def test_the_committed_reliability_is_current_and_covers_every_metric():
    data = json.loads(LEAGUE_PATH.with_name("reliability.json").read_text())
    league = load_league(LEAGUE_PATH)
    assert data["generator_version"] == LEAGUE_GENERATOR_VERSION, "re-run python -m regista.season.reliability"
    assert data["league_fingerprint"] == reliability.league_fingerprint(league), "re-run python -m regista.season.reliability"
    assert set(data["metrics"]) == set(CATALOGUE)
    assert data["seasons"] >= 3 and data["noise_r"] == reliability.NOISE_R == 0.3 and data["synthetic"] is True
    for key, v in data["metrics"].items():
        if v["r"] is not None:
            assert v["noisy"] is (v["r"] < 0.3), key
            assert v["season_r"] == (pytest.approx(2 * v["r"] / (1 + v["r"]), abs=0.002) if v["r"] > 0 else 0.0), key
    loaded = reliability.load(LEAGUE_PATH, league)
    assert loaded["metrics"] and "stale" not in loaded
    # the passing volume a role repeats; aerial duels won were near 0 within a role in round 2's review
    assert data["metrics"]["passes"]["noisy"] is False


def test_a_missing_or_stale_table_marks_nothing(tmp_path):
    league = new_league(2026)
    path = save_league(league, tmp_path / "league.json")
    assert reliability.load(path, league) == {"metrics": {}, "stale": "no reliability.json beside the league file"}
    (tmp_path / "reliability.json").write_text(json.dumps({"generator_version": "0.0.1", "metrics": {"shots": {"noisy": True}}}))
    assert reliability.load(path, league)["metrics"] == {}
    (tmp_path / "reliability.json").write_text(json.dumps({"generator_version": LEAGUE_GENERATOR_VERSION,
                                                           "league_fingerprint": "another", "metrics": {"shots": {}}}))
    assert "another league" in reliability.load(path, league)["stale"]


def test_split_half_r_is_centred_on_each_role():
    # two roles at different levels: without centring the levels alone would correlate; within each role the halves
    # repeat exactly
    rows = [("0:CB", 1.0 + i, 1.0 + i) for i in range(5)] + [("0:ST", 10.0 + i, 10.0 + i) for i in range(5)]
    r, n = reliability._centred_r(rows)
    assert n == 10 and r == pytest.approx(1.0)
    noise = [("0:CB", 1.0, 2.0), ("0:CB", 2.0, 1.0), ("0:CB", 3.0, 3.0), ("0:ST", 10.0, 11.0), ("0:ST", 11.0, 10.0),
             ("0:ST", 12.0, 12.0), ("0:CB", 1.5, 1.5), ("0:ST", 10.5, 10.5)]
    r, _n = reliability._centred_r(noise)
    assert r < 0.6
    assert reliability._centred_r(rows[:3]) == (None, 3)


# ---------------------------------------------------------------------------- realism labels

def test_every_metric_says_how_far_its_level_is_checked():
    for m in CATALOGUE.values():
        r = m.public()["realism"]
        assert set(r) == {"checked", "bands", "note"} and r["note"], m.key
        assert all(b in BANDS for b in r["bands"]), (m.key, r["bands"])
        assert r["checked"] is bool(r["bands"]), m.key
    assert set(REALISM) <= set(CATALOGUE) | {"ppda", "possession_pct", "field_tilt_pct"}
    # the metrics the reviewers found off or not comparable say so
    for key in ("passes_into_box", "pressure_regain_pct", "medium_pass_pct", "long_pass_pct", "touches", "touches_in_box",
                "clean_sheets",
                "clean_sheet_pct", "gk_avg_pass_length", "xt_added"):
        assert realism(key)["checked"] is False and realism(key)["note"].split(":")[0] in (
            "unchecked", "unchecked, likely low", "not comparable"), key
    for key in ("save_pct", "shot_on_target_pct", "gk_launch_pct", "take_on_pct", "cross_pct", "pass_pct"):
        assert realism(key)["checked"] is True, key
    # review closing round 1: the metrics whose league level was checked but whose roles were not now name a role shape
    for key, shape in (("passes", "passes_cb_dm_over_st"), ("crosses", "fb_crosses_third_of_w"),
                       ("tackles_won", "st_tackles_below_fb_cb_dm"), ("fouls_won", "fouls_won_w_st_over_cb")):
        assert f"shape_{shape}" in realism(key)["bands"], key


def test_clean_sheets_and_touches_say_what_they_count():
    assert "30-min" in CATALOGUE["clean_sheets"].label and "30-min" in CATALOGUE["clean_sheet_pct"].label
    assert "30-minute" in CATALOGUE["clean_sheet_pct"].definition
    assert "clean_sheets" not in DEFAULT_COLUMNS["GK"] and "clean_sheet_pct" not in DEFAULT_COLUMNS["GK"]
    assert CATALOGUE["touches"].rule.startswith("Regista") and "twice" in CATALOGUE["touches"].definition


# ---------------------------------------------------------------------------- the API states the sample and the noise

@pytest.fixture(scope="module")
def small(tmp_path_factory):
    league = new_league(2026)
    small = {**league, "fixtures": league["fixtures"][:3]}
    root = tmp_path_factory.mktemp("rel_season")
    build_season(small, root)
    return small, root


@pytest.fixture
def client(small, monkeypatch, tmp_path):
    from regista import api
    from regista.season import metrics, profiles

    league, root = small
    path = save_league(league, tmp_path / "league.json")
    table = {k: {"r": 0.1 if k == "pressures" else 0.8, "season_r": 0.5, "n": 40, "noisy": k == "pressures"} for k in CATALOGUE}
    (tmp_path / "reliability.json").write_text(json.dumps({
        "generator_version": LEAGUE_GENERATOR_VERSION, "league_fingerprint": reliability.league_fingerprint(league),
        "seasons": 3, "noise_r": 0.3, "method": "test", "synthetic": True, "metrics": table}))
    monkeypatch.setattr(api, "SEASON_LEAGUE", path)
    monkeypatch.setattr(api, "SEASON_ROOT", root)
    monkeypatch.setattr(api, "CACHE_ROOT", tmp_path / "cache")
    metrics.invalidate()
    profiles.invalidate()
    yield TestClient(api.app)
    metrics.invalidate()
    profiles.invalidate()


def test_the_terminal_states_the_sample_and_marks_noisy_metrics(client):
    cat = client.get("/api/metrics").json()
    sample = cat["season"]["sample"]
    assert sample["matches_per_club"] == 1 and sample["match_minutes"] == pytest.approx(30.0, abs=1.0)
    assert "Small sample" in sample["note"] and sample["median_full_matches"] <= 1.0
    assert cat["season"]["reliability"]["noisy"] == ["pressures"] and cat["season"]["reliability"]["stale"] is None
    by_key = {m["key"]: m for m in cat["metrics"]}
    assert by_key["pressures"]["reliability"]["noisy"] is True and by_key["passes"]["reliability"]["noisy"] is False
    assert all("realism" in m for m in cat["metrics"])
    scr = client.get("/api/terminal/screen", params={"metrics": "pressures,passes", "min_minutes": 0}).json()
    assert scr["season"]["sample"]["note"]
    cells = scr["players"][0]["values"]
    assert cells["pressures"]["noisy"] is True and cells["passes"]["noisy"] is False
    assert [c["reliability"]["noisy"] for c in scr["columns"]] == [True, False]


def test_profiles_state_the_sample_and_mark_noisy_stats(client):
    p = client.get(f"/api/players/{STAR}").json()
    assert "Small sample" in p["sample"]["note"] and p["synthetic"] is True
    assert "pressures" in p["noisy"] and "passes" not in p["noisy"]
    assert p["stat_labels"]["shots"] == "Shots (incl. penalties)"
    assert p["stat_labels"]["shot_accuracy"] == "Shots on target % (incl. penalties)"
    season = client.get("/api/season").json()
    assert season["sample"]["matches_per_club"] == 1 and "pressures" in season["noisy"]


@pytest.mark.slow
def test_the_committed_reliability_reproduces():
    """The table is deterministic (same league, same seeds): recomputing it gives the committed file."""
    data = json.loads(LEAGUE_PATH.with_name("reliability.json").read_text())
    again = json.loads(json.dumps(reliability.compute(load_league(LEAGUE_PATH), data["seasons"]), sort_keys=True))
    assert again == data
