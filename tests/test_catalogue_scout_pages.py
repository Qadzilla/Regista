"""What the Scout pages on the catalogue need from the API (docs/redesign/catalogue/pages-scout.md).

- ``/api/catalogue/players`` rows carry the engine's ``rank`` (the place on their board), so Find players shows places
  without ranking in the browser: the same places, row for row, as ``/api/catalogue/rank``.
- ``position`` takes a comma list on ``/api/catalogue/players`` and ``/rank`` ("DF,MF,FW": the positions a metric is
  scored for), so a goals list with no position picked leaves goalkeepers out, as the metrics engine decides.
- The existing endpoints' defaults do not move (tests/test_backcompat.py and tests/test_catalogue_backcompat.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from regista import api

    return TestClient(api.app)


def ok(client: TestClient, path: str, **params) -> dict:
    r = client.get(path, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _list_rows(client: TestClient, **params) -> list[dict]:
    """Every row of /api/catalogue/players, page by page."""
    out, offset = [], 0
    while True:
        page = ok(client, "/api/catalogue/players", limit=200, offset=offset, **params)
        out += page["players"]
        offset += 200
        if offset >= page["total"]:
            return out


@pytest.mark.parametrize("params", [
    {"tier": "semi_pro", "age_group": "senior", "gender": "men", "position": "DF,MF,FW"},   # one level (My level)
    {"country": "England", "position": "DF,MF,FW"},                                          # one board per level
    {"position": "FW"},                                                                       # pool mode, per gender
])
def test_list_places_are_the_rank_endpoints(client, params):
    rows = _list_rows(client, sort="goals", metrics="goals", **params)
    rank = ok(client, "/api/catalogue/rank", metric="goals", limit=200, **params)
    placed = [(r["global_id"], r["competition_id"], r["rank"]) for r in rows if r["rank"] is not None]
    assert placed == [(r["global_id"], r["competition_id"], r["rank"]) for r in rank["players"]]
    assert len(placed) == rank["ranked"]
    # none yet (a count at 0) never has a place, and every row with a place has some
    for r in rows:
        cell = r["values"]["goals"]
        assert (r["rank"] is None) == (cell["none_yet"] or cell["percentile"] is None and rank["rank_by"] == "pool"
                                       or not r["qualified"])
    # each board ranks from 1, and rows showing the same number share a place
    by_board: dict[str, list] = {}
    for r in rows:
        if r["rank"] is not None:
            by_board.setdefault(r["board"], []).append(r)
    for board in by_board.values():
        assert board[0]["rank"] == 1
        for a, b in zip(board, board[1:]):
            same = a["values"]["goals"]["value"] == b["values"]["goals"]["value"] and (
                rank["rank_by"] != "pool" or a["values"]["goals"]["percentile"] == b["values"]["goals"]["percentile"])
            assert b["rank"] == (a["rank"] if same else board.index(b) + 1)


def test_femi_toure_is_first_on_my_level_and_the_list_counts_none_yet(client):
    out = ok(client, "/api/catalogue/players", sort="goals", metrics="goals", tier="semi_pro", age_group="senior",
             gender="men", position="DF,MF,FW", limit=3)
    top = out["players"][0]
    assert (top["name"], top["rank"], top["values"]["goals"]["percentile"]) == ("Femi Toure", 1, 98)
    assert top["values"]["goals"]["pool"]["words"] == "semi-pro men forwards" and top["values"]["goals"]["pool"]["size"] == 33
    assert out["with_any"] + out["none_yet"] == out["total"] and out["boards"] is None


def test_a_position_list_leaves_out_the_positions_it_does_not_name(client):
    every = ok(client, "/api/catalogue/players", sort="goals", country="England", limit=1)
    outfield = ok(client, "/api/catalogue/players", sort="goals", country="England", position="DF,MF,FW", limit=200)
    keepers = ok(client, "/api/catalogue/players", sort="goals", country="England", position="GK", limit=1)
    assert outfield["total"] + keepers["total"] == every["total"]
    assert all(r["position"] != "GK" for r in outfield["players"])
    rank = ok(client, "/api/catalogue/rank", metric="goals", country="England", position="DF,MF,FW", limit=200)
    assert rank["ranked"] == 25 and all(r["position"] != "GK" for r in rank["players"] + rank["unranked"])
    # a bad list is refused, a single position is as before
    assert client.get("/api/catalogue/players", params={"position": "FW,XX"}).status_code == 422
    assert client.get("/api/catalogue/rank", params={"metric": "goals", "position": "FW,"}).status_code == 422
    assert client.get("/api/terminal/rank", params={"metric": "goals", "position": "DF,FW"}).status_code == 422


def test_minutes_and_name_lists(client):
    mins = ok(client, "/api/catalogue/players", sort="minutes", tier="semi_pro", age_group="senior", gender="men", limit=200)
    ranked = [r for r in mins["players"] if r["rank"] is not None]
    assert ranked[0]["rank"] == 1 and all(r["qualified"] for r in ranked)
    assert [r["minutes"] for r in ranked] == sorted((r["minutes"] for r in ranked), reverse=True)
    names = ok(client, "/api/catalogue/players", sort="name", competition="co_ger_sp_men", limit=5)
    assert all(r["rank"] is None for r in names["players"])
