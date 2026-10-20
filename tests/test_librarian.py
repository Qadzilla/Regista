"""The Librarian must understand football English, survive typos, and say when it finds nothing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from regista.clips import derive_clips
from regista.librarian import main as librarian_main, parse_query, search_clips
from regista.synth import generate

SEED = 294  # home #9 Castellanos: goal, nutmeg, replays, closeup


@pytest.fixture(scope="module")
def match_dir(tmp_path_factory):
    r = generate(seed=SEED, minutes=3.0, track_hz=1.0)
    d = tmp_path_factory.mktemp("match") / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    clips, labels = derive_clips(r.stream, "t_home_09")
    (d / "clips.jsonl").write_text("\n".join(json.dumps(x) for x in clips + labels) + "\n")
    return d


@pytest.fixture(scope="module")
def match(match_dir):
    return json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])


def _surname(match):
    return next(p["name"].split()[-1] for p in match["players"] if p["player_id"] == "t_home_09")


def test_name_and_tag(match_dir, match):
    out = search_clips(match_dir, f"find me {_surname(match)} doing a nutmeg")
    assert out["parsed"]["player_id"] == "t_home_09"
    assert out["parsed"]["tags"] == ["nutmeg"]
    assert out["results"] and all("nutmeg" in r["tags"] for r in out["results"])
    assert not out["relaxed"]


def test_kit_number_without_team_searches_both_nines(match_dir):
    out = search_clips(match_dir, "show me every goal by number 9")
    assert set(out["parsed"]["player_ids"]) == {"t_home_09", "t_away_09"}
    assert out["results"] and all("goal" in r["tags"] for r in out["results"])
    assert {r["player_id"] for r in out["results"]} == {"t_home_09"}


def test_misspelt_surname_is_corrected(match_dir, match):
    surname = _surname(match)
    typo = surname[:-2] + surname[-1]  # drop a letter
    out = search_clips(match_dir, f"{typo} nutmeg")
    assert out["parsed"]["player_id"] == "t_home_09"
    assert "taken as" in out["parsed"]["player_how"]
    assert out["results"]


def test_position_word_and_replay_reason(match_dir):
    out = search_clips(match_dir, "replays of the home striker's goal")
    assert out["parsed"]["player_id"] == "t_home_09"
    assert out["parsed"]["reasons"] == ["replay_appearance"]
    assert out["results"] and all(r["reason"] == "replay_appearance" and "goal" in r["tags"] for r in out["results"])


def test_team_and_minute_window(match_dir):
    out = search_clips(match_dir, "shots by Southgate in the first 2 minutes")
    assert out["parsed"]["team_id"] == "t_away"
    assert out["parsed"]["minutes"] == [1, 2]
    assert all(r["player_id"].startswith("t_away") and r["minute"] <= 2 for r in out["results"])


def test_no_results_explains_itself(match_dir, match):
    out = search_clips(match_dir, f"{_surname(match)} red card")
    assert out["results"] == []
    assert "No clips match" in out["message"] and "tagged" in out["message"]


def test_limit_phrase(match_dir):
    out = search_clips(match_dir, "top 2 moments of Northbridge")
    assert out["parsed"]["limit"] == 2 and len(out["results"]) == 2
    assert out["results"][0]["watchability"] >= out["results"][1]["watchability"]


def test_relaxed_match_is_flagged(match_dir, match):
    out = search_clips(match_dir, f"{_surname(match)} goal and a red card")
    assert out["relaxed"] and out["results"]
    assert "relaxed" in out["message"]


def test_cli_exit_codes(match_dir, match, capsys):
    assert librarian_main([str(match_dir), f"{_surname(match)} goal"]) == 0
    assert "understood:" in capsys.readouterr().out
    assert librarian_main([str(match_dir), "red cards"]) == 1  # a real tag that nothing carries


def test_parse_is_pure(match):
    p = parse_query("Top 3 nutmegs by the away keeper after the 60th minute", match)
    assert p["tags"] == ["nutmeg"] and p["limit"] == 3 and p["minutes"][0] == 60
    assert p["player_id"] == "t_away_01"
