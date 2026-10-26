"""Catalogue UI port, fixes round 1 (docs/redesign/catalogue/fixes-round1.md).

- The Scout agent's rules answers on the catalogue: a named player's answer names the stat asked and the engine's real
  reason for no percentile ("none yet · 24 of the 31 … have none", never a guessed "not enough minutes"); the sentences
  read right (no "No the …", no "college college", "has the fewest" for an ascending list); a stat the league parser
  does not know is read from the Terminal's metric names, and an answer with no stat it knows says what it ranks by.
- The Terminal's name directory is one read (``/api/catalogue/directory``), and JSON answers are gzip-compressed (video,
  pages, scripts and range answers are not).
- Profiles: shots, shots on target and saves are the metrics engine's (penalty kicks left out, and the label says so),
  so the profile, Find players and the Terminal say one number; best moments carry the scoreboard's clock.

Reads the committed catalogue and the Regista League. Nothing reaches Azure or the live app.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from regista import api
from regista.catalogue.page import clock_text
from regista.render.scene import Scene

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
STAR, CRUZ, PETROV = "pl_bro_09", "pl_sot_09", "pl_dun_10"


@pytest.fixture(scope="module")
def client():
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(api, "SEASON_LEAGUE", LEAGUE)
        mp.setattr(api, "SEASON_ROOT", SEASON_ROOT)
        mp.setattr(api, "CATALOGUE", INDEX)
        mp.setattr(api, "CATALOGUE_ROOT", MATCHES)
        mp.setenv("REGISTA_SEASON", str(LEAGUE))
        mp.setenv("REGISTA_SEASON_ROOT", str(SEASON_ROOT))
        mp.setenv("REGISTA_CATALOGUE", str(INDEX))
        mp.setenv("REGISTA_CATALOGUE_ROOT", str(MATCHES))
        yield TestClient(api.app)


def ok(c, path, **params):
    r = c.get(path, params=params)
    assert r.status_code == 200, (path, r.text[:300])
    return r.json()


def ask(c, q):
    r = c.post("/api/scout/ask", json={"q": q, "where": "catalogue"})
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---------------------------------------------------------------------------- the Scout agent's rules answers

def test_a_named_player_answer_uses_the_stat_asked(client):
    out = ask(client, "Sergio Cruz shots")
    assert out["players"][0]["stat"]["key"] == "shots"
    assert out["reply"].startswith("Sergio Cruz (") and ": shots " in out["reply"]
    assert "non-penalty goals" not in out["reply"]
    assert "(incl. penalties)" not in out["understood"]   # the catalogue's shots leave penalties out


def test_a_named_player_with_none_yet_says_none_yet_not_minutes(client):
    out = ask(client, "Sergio Cruz")
    card = out["players"][0]
    assert card["stat"]["none_yet"] and card["qualified"]
    z = card["stat"]["zeros"]
    assert f"none yet · {z['none']} of the {z['of']} {card['stat']['pool']['words']} have none" in out["reply"]
    assert "not enough minutes" not in out["reply"] and "none yet, none yet" not in out["reply"]


def test_rules_sentences_read_right(client):
    empty = ask(client, "most goals by women goalkeepers in Nigeria")
    assert not empty["players"] and empty["reply"].startswith("No women goalkeepers in Nigeria")
    assert "No the" not in empty["reply"]
    college = ask(client, "best college players")
    # college men and women are two levels: one list per level (fixes round 2), so no "leads"
    assert "college college" not in college["reply"] and "One list per level for the college players" in college["reply"]
    fewest = ask(client, "fewest fouls by forwards at my level")
    assert fewest["query"]["sort"] == "fouls" and fewest["query"]["order"] == "asc"
    assert " has the fewest fouls committed among the semi-pro men forwards: " in fewest["reply"]
    assert " leads " not in fewest["reply"]
    low = ask(client, "fewest pass completion by midfielders at my level")
    assert " has the lowest pass completion among the semi-pro men midfielders: " in low["reply"]
    across = ask(client, "fewest fouls by forwards")   # several levels, one position: the pool rule, lowest first
    assert "in their own pool, lowest first" in across["reply"] and " leads " not in across["reply"]


def test_a_stat_the_league_parser_does_not_know_is_read_from_the_metric_names(client):
    out = ask(client, "most yellow cards")
    assert out["query"]["sort"] == "yellow_cards"
    assert "yellow cards" in out["reply"] and "“yellow cards” → yellow cards" in out["understood"]


def test_no_known_stat_says_what_it_ranks_by(client):
    out = ask(client, "most blah by forwards")
    assert out["query"]["sort"] == "np_goals"
    assert "I did not find a stat I know in the question, so this ranks by Non-penalty goals" in out["reply"]
    assert "defaulted" not in out["query"]
    named = ask(client, "most interceptions at my level")
    assert "I did not find" not in named["reply"]


# ---------------------------------------------------------------------------- the Terminal's directory and compression

def test_the_directory_is_every_row_once_without_cells(client):
    d = ok(client, "/api/catalogue/directory")
    screen = ok(client, "/api/catalogue/players", min_minutes=0, sort="name", limit=1)
    assert d["total"] == screen["total"] == len(d["players"])
    assert len({(r["global_id"], r["competition_id"]) for r in d["players"]}) == d["total"]
    assert all("values" not in r and "pool" not in r and "sample" not in r for r in d["players"])
    names = [r["name"] for r in d["players"]]
    assert names == sorted(names)
    assert set(d["qualifying_minutes"]) >= {r["competition_id"] for r in d["players"]}
    assert all(isinstance(v, float) and v > 0 for v in d["qualifying_minutes"].values())
    assert d["synthetic"] is True


def test_json_answers_are_gzipped_and_video_and_pages_are_not(client):
    raw = client.get("/api/catalogue/directory", headers={"Accept-Encoding": "gzip"})
    assert raw.headers["content-encoding"] == "gzip" and "Accept-Encoding" in raw.headers["vary"]
    assert int(raw.headers["content-length"]) < 120_000           # about 640 KB as plain JSON
    plain = client.get("/api/catalogue/directory", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert raw.json() == plain.json()
    with client.stream("GET", "/api/catalogue/directory", headers={"Accept-Encoding": "gzip"}) as r:
        body = b"".join(r.iter_raw())
    assert json.loads(gzip.decompress(body)) == plain.json()
    small = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in small.headers or len(small.content) >= 1024
    for path in ("/", "/scout", "/static/scout/terminal.js"):
        r = client.get(path, headers={"Accept-Encoding": "gzip"})
        assert r.status_code == 200 and "content-encoding" not in r.headers, path
        assert "content-security-policy" in r.headers


# ---------------------------------------------------------------------------- profiles: one shot count, the clock

def test_profile_shots_are_the_metrics_engines_with_penalties_left_out(client):
    p = ok(client, f"/api/catalogue/players/{PETROV}", include="profile")
    row = next(r for r in p["rows"] if r["competition_id"] == "co_eng_sp_men")
    stats, ratios = row["profile"]["stats"], row["profile"]["ratios"]
    screen = ok(client, "/api/catalogue/players", competition="co_eng_sp_men", q="Pavel Petrov", min_minutes=0,
                metrics="shots,shots_on_target")["players"][0]["values"]
    assert stats["shots"]["label"] == "Shots (penalties excluded)"
    assert stats["shots_on_target"]["label"] == "Shots on target (penalties excluded)"
    assert stats["shots"]["count"] == round(screen["shots"]["total"]) == ratios["shot_accuracy"]["den"]
    assert stats["shots_on_target"]["count"] == round(screen["shots_on_target"]["total"]) == ratios["shot_accuracy"]["num"]
    assert stats["shots"]["per90"] == screen["shots"]["value"]
    assert stats["shots"]["percentile"] == screen["shots"]["percentile"]
    assert "(incl. penalties)" not in json.dumps(row["profile"]["stats"])
    gk = ok(client, "/api/catalogue/players/pl_ash_01", include="profile")["rows"][0]["profile"]["stats"]
    assert gk["saves"]["label"] == "Saves (penalties excluded)"


def test_profile_moments_carry_the_scoreboard_clock(client):
    p = ok(client, f"/api/catalogue/players/{STAR}", include="profile")
    row = next(r for r in p["rows"] if r["competition_id"] == "co_eng_sp_men")
    moments = row["profile"]["moments"]
    assert moments and all(isinstance(m["clock"], str) for m in moments)
    first = next(m for m in moments if m["clip_id"] == "cl_t_away_09_000006")
    assert first["clock"] == "05:48" and first["title"].endswith("at 6'")   # the title keeps the engine's minute
    assert all("clock" in m for m in p["moments"])


@pytest.mark.parametrize("t", [0.0, 12.5, 899.9, 900.0, 905.0, 910.0, 1500.4, 1820.0, 1900.0])
def test_the_clock_is_the_renderers(t):
    periods = [{"period": 1, "t": 0.0, "t_end": 900.0}, {"period": 2, "t": 910.0, "t_end": 1810.0}]
    assert clock_text(periods, t) == Scene.clock_at(SimpleNamespace(match={"periods": periods}), t)
