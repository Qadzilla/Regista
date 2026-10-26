"""Catalogue UI port, fixes round 2 (docs/redesign/catalogue/fixes-round2.md).

- A minutes question ranks by minutes played (one list per level), and never says it found no stat.
- Across levels the rules reply follows the ranking rule it used: the rule first and each row with its own pool line
  (``rank_by`` pool), or one list per level (value mode, more than one position); "leads" only on one-level lists.
- ``search_catalogue_players`` lists the rows that get a place first on each board, as ``/api/catalogue/rank`` does
  (a ratio below its minimum attempts, or none yet, never leads), and a list where no one has any of a count says so.
- A catalogue metric named by longer words than the league parser's ("touches in the box", "win the most aerial
  duels") is the one ranked.

Reads the committed catalogue and the Regista League. Nothing reaches Azure or the live app.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from regista import api
from regista.catalogue.scout import whole

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
STAR = "pl_bro_09"


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
    r = c.post("/api/scout/ask", json={"q": q, "engine": "rules", "where": "catalogue"})
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---------------------------------------------------------------------------- minutes

@pytest.mark.parametrize("q", ["who plays the most minutes in Spain", "who played the most minutes among U19 players"])
def test_a_minutes_question_ranks_by_minutes(client, q):
    from regista import mcp_server

    out = ask(client, q)
    assert out["query"]["sort"] == "minutes" and "did not find a stat" not in out["reply"]
    assert "most minutes played" in out["understood"] and "non-penalty" not in out["understood"]
    assert out["warning"] is None   # minutes have no percentile to read against a pool
    args = {k: v for k, v in out["query"]["args"].items() if v is not None}
    tool = mcp_server.search_catalogue_players(**args)
    assert [c["global_id"] for c in out["players"]] == [p["global_id"] for p in tool["players"]]
    top = out["players"][0]
    assert top["stat"] is None and f"{whole(top['minutes']):,} minutes" in out["reply"]
    for board in {p["board"] for p in tool["players"]}:   # each board's first row has its board's most minutes
        mins = [p["minutes"] for p in tool["players"] if p["board"] == board]
        assert mins[0] == max(mins)


def test_a_named_player_minutes_answer(client):
    out = ask(client, "how many minutes has Femi Toure played")
    c = out["players"][0]
    assert c["global_id"] == STAR and out["reply"].endswith(f"{whole(c['minutes']):,} minutes in {c['appearances']} appearances.")


def test_no_stat_still_says_what_it_ranks_by(client):
    out = ask(client, "best keepers at my level")
    assert "I did not find a stat I know" in out["reply"] and out["query"]["sort"] == "save_pct"


# ---------------------------------------------------------------------------- the reply follows the ranking rule

@pytest.mark.parametrize("q", ["Find me women forwards who score", "most sprints by defenders",
                               "which defenders win the most aerial duels", "who is the fastest winger"])
def test_a_reply_across_levels_says_the_pool_rule_and_each_pool(client, q):
    out = ask(client, q)
    assert "leads" not in out["reply"]
    assert "from several levels, ranked by each player's percentile for" in out["reply"]
    nxt = out["reply"].split("Next: ", 1)[1]
    assert nxt.count("percentile among") >= 2   # each next row with its own pool line


def test_the_women_forwards_example_reads_like_the_sandbox(client):
    out = ask(client, "Find me women forwards who score")
    p = out["players"]
    assert out["reply"].startswith(f"{out['result_total']} women forwards from several levels, ranked by each player's "
                                   "percentile for goals in their own pool. First: " + p[0]["name"])
    assert f"Next: {p[1]['name']} (" in out["reply"] and f"among {p[1]['stat']['pool']['size']} " in out["reply"]


def test_one_list_per_level_when_levels_and_positions_mix(client):
    out = ask(client, "most goals in England")
    assert out["reply"].startswith("One list per level for the players in England, ranked by goals within the level")
    assert "leads" not in out["reply"] and "Semi-pro men: Femi Toure (" in out["reply"]


def test_one_level_keeps_leads(client):
    out = ask(client, "most interceptions at my level")
    assert " leads the semi-pro men players for interceptions: " in out["reply"]


# ---------------------------------------------------------------------------- unranked rows never lead

def _ranked_then_unranked(rows):
    boards: dict[str, list[bool]] = {}
    for r in rows:
        boards.setdefault(r["board"], []).append(r["ranked"])
    return all(flags == sorted(flags, reverse=True) for flags in boards.values())


@pytest.mark.parametrize("tool_args,rank_params", [
    ({"tier": "semi_pro", "age_group": "senior", "gender": "men", "position": "GK", "sort": "save_pct"},
     {"metric": "save_pct", "tier": "semi_pro", "age_group": "senior", "gender": "men", "position": "GK"}),
    ({"country": "Japan", "position": "DF", "sort": "pass_pct", "order": "asc"},
     {"metric": "pass_pct", "country": "Japan", "position": "DF", "order": "asc"}),
    ({"competition": "co_ger_sp_men", "sort": "take_on_pct"},
     {"metric": "take_on_pct", "competition": "co_ger_sp_men"}),
    ({"gender": "men", "position": "FW", "sort": "np_goals"}, {"metric": "np_goals", "gender": "men", "position": "FW"}),
])
def test_the_tool_lists_ranked_rows_first_in_the_rank_endpoints_order(client, tool_args, rank_params):
    from regista import mcp_server

    tool = mcp_server.search_catalogue_players(**tool_args, limit=50)
    assert _ranked_then_unranked(tool["players"])
    rank = ok(client, "/api/catalogue/rank", **rank_params, limit=50)
    ranked = [p["global_id"] for p in tool["players"] if p["ranked"]]
    assert ranked == [p["global_id"] for p in rank["players"]][:len(ranked)] and ranked


def test_best_keepers_at_my_level_names_the_rank_endpoints_leader(client):
    out = ask(client, "best keepers at my level")
    rank = ok(client, "/api/catalogue/rank", metric="save_pct", tier="semi_pro", age_group="senior", gender="men",
              position="GK")
    assert out["players"][0]["global_id"] == rank["players"][0]["global_id"]
    assert out["reply"].startswith(f"{rank['players'][0]['name']} (")


def test_least_accurate_passers_in_japan_lead_with_a_ranked_row(client):
    out = ask(client, "least accurate passers in Japan")
    assert out["players"][0]["ranked"] is True and _ranked_then_unranked(out["players"])
    assert "Koki Abe" not in out["reply"].split(".")[0]


@pytest.mark.parametrize("q,who,stat", [("who has the most nutmegs in Ghana", "players in Ghana", "nutmegs"),
                                        ("most goals in Morocco under 19", "U19 players in Morocco", "goals")])
def test_no_one_with_any_says_so(client, q, who, stat):
    out = ask(client, q)
    assert out["with_any"] == 0 and out["none_yet"]
    assert out["reply"] == f"No one among the {who} has any {stat} yet (0 of {out['none_yet']})."


# ---------------------------------------------------------------------------- the catalogue's own metric names

@pytest.mark.parametrize("q,key", [("most touches in the box", "touches_in_box"),
                                   ("which defenders win the most aerial duels", "aerial_duels_won"),
                                   ("who wins the most take-ons at my level", "take_ons_won"),
                                   ("most touches at my level", "touches"),
                                   ("Which amateur midfielders create the most chances?", "key_passes")])
def test_the_longer_catalogue_name_wins(client, q, key):
    out = ask(client, q)
    assert out["query"]["sort"] == key, out["understood"]


def test_whole_minutes_round_as_the_pages_do():
    assert (whole(90.5), whole(89.5), whole(90.4)) == (91, 90, 90)   # Math.round, not round half to even
