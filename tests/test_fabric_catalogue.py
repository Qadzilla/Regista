"""Microsoft Fabric, the catalogue: its tables, Regista's numbers for the check, the second notebook, the notebook's rule
in plain Python, and the CLI's catalogue options.

Every test reads the committed catalogue and the Regista League as the app builds them (``data/catalogue/matches`` and
``data/season/matches``, git-ignored, built once). OneLake and the Fabric API are fakes: no test reaches Fabric or Azure.
"""

from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path

import pytest

from regista.catalogue.metrics import load_catalogue_metrics
from regista.catalogue.taxonomy import ENGLAND_ID
from regista.cloud import fabric as fb
from regista.cloud import fabric_catalogue_notebook as nb
from regista.cloud.fabric_catalogue import catalogue_player_season_rows, catalogue_tables
from regista.cloud.fabric_tables import CATALOGUE_TABLES, LEAGUE_TABLES, SCHEMAS, to_arrow
from regista.schema import iter_jsonl
from regista.season.league import ATTRIBUTE_KEYS, load_league
from regista.season.metrics import CATALOGUE, COUNT_METRICS

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
MATCHES = ROOT / "data" / "catalogue" / "matches"
LEAGUE = ROOT / "data" / "season" / "league.json"
SEASON_ROOT = ROOT / "data" / "season" / "matches"
STAR = "pl_bro_09"
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes", "skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift",
                                "execution", "style_offset", "level_scale", "age_range", "seed", "generator"}


@pytest.fixture(scope="module")
def cm():
    return load_catalogue_metrics(INDEX, MATCHES, LEAGUE, SEASON_ROOT)


@pytest.fixture(scope="module")
def tables(cm):
    return catalogue_tables(cm, root=MATCHES, season_root=SEASON_ROOT)


def _folder(cid, match_id):
    return (SEASON_ROOT if cid == ENGLAND_ID else MATCHES) / match_id


# ---------------------------------------------------------------------------- the tables
def test_the_catalogue_tables_have_their_schema_and_sizes(cm, tables):
    assert set(tables) == set(CATALOGUE_TABLES) and not set(CATALOGUE_TABLES) & set(LEAGUE_TABLES)
    for name, rows in tables.items():
        assert rows and all(set(r) == set(SCHEMAS[name]) for r in rows), name
        arrow = to_arrow(name, rows)
        assert arrow.column_names == list(SCHEMAS[name]) and arrow.num_rows == len(rows)
    comps = [cm.comps[cid] for cid in cm.order]
    assert len(tables["catalogue_competitions"]) == 14 and len({c["country"] for c in tables["catalogue_competitions"]}) == 10
    assert len(tables["catalogue_matches"]) == 90 == sum(len(c["fixtures"]) for c in comps)
    assert len(tables["catalogue_clubs"]) == sum(len(c["clubs"]) for c in comps)
    assert len(tables["catalogue_players"]) == sum(len(club["squad"]) for c in comps for club in c["clubs"])
    n_events = n_poss = n_lineups = 0
    for m in tables["catalogue_matches"]:
        stream = list(iter_jsonl(_folder(m["competition_id"], m["match_id"]) / "events.jsonl"))
        n_events += sum(1 for r in stream if r["type"] == "event")
        n_poss += sum(1 for r in stream if r["type"] == "possession")
        n_lineups += len(stream[0]["players"])
    assert (len(tables["catalogue_events"]), len(tables["catalogue_possessions"]), len(tables["catalogue_lineups"])) == (
        n_events, n_poss, n_lineups)
    # one row per player-competition row the engine has (every player who appeared), per checked stat
    assert len(tables["catalogue_player_season"]) == len(fb.CATALOGUE_CHECK_STATS) * sum(len(cm.metrics[c].players) for c in cm.order)


def test_england_semi_pro_men_is_the_league_fixtures(tables):
    """England's rows come from the Regista League's 30 fixtures, the matches the catalogue pages count: no Player-view
    friendly, the same folders as the league's own tables, the uploader and camera from the index's overlay."""
    league = load_league(LEAGUE)
    eng = [m for m in tables["catalogue_matches"] if m["competition_id"] == ENGLAND_ID]
    assert [m["match_id"] for m in eng] == [fx["match_id"] for fx in league["fixtures"]]
    assert not any(m["match_id"].startswith("pv_") for m in tables["catalogue_matches"])
    assert all(m["uploader_type"] in ("team", "player") and m["camera"] for m in tables["catalogue_matches"])
    overlay = json.loads(INDEX.read_text())["competitions"][0]
    assert overlay["competition_id"] == ENGLAND_ID
    for m in eng:
        u = overlay["uploads"][m["match_id"]]
        assert (m["uploader_type"], m["uploader_club_id"], m["camera"]) == (u["uploader"]["type"], u["uploader"]["club_id"], u["camera"])
    n = sum(1 for fx in league["fixtures"] for r in iter_jsonl(SEASON_ROOT / fx["match_id"] / "events.jsonl") if r["type"] == "event")
    assert sum(1 for e in tables["catalogue_events"] if e["competition_id"] == ENGLAND_ID) == n
    goals = Counter(e["global_id"] for e in tables["catalogue_events"]
                    if e["event_type"] == "goal" and e["competition_id"] == ENGLAND_ID)
    assert goals[STAR] == 5 and all(v <= 3 for g, v in goals.items() if g != STAR)   # Femi Toure, two clear


def test_no_hidden_rating_scale_or_seed_reaches_a_table(tables):
    for name, rows in tables.items():
        assert not set(SCHEMAS[name]) & HIDDEN, name
    comp = tables["catalogue_competitions"]
    assert all(c["level"] == f"{c['tier']}/{c['age_group']}/{c['gender']}" for c in comp)
    assert {c["source"] for c in comp} == {"league", "catalogue"} and all(str(c["as_of"]) == "2026-10-24" for c in comp)
    on_file = json.loads((ROOT / "data" / "catalogue" / "competitions" / "co_gha_u17.json").read_text())
    blob = json.dumps({n: tables[n] for n in ("catalogue_competitions", "catalogue_clubs", "catalogue_players")}, default=str)
    assert f'"execution": {on_file["level"]["execution"]}' not in blob and "speed_mult" not in blob


def test_every_row_carries_its_competition_and_global_id(tables):
    squad = {(p["competition_id"], p["global_id"]) for p in tables["catalogue_players"]}
    match_comp = {m["match_id"]: m["competition_id"] for m in tables["catalogue_matches"]}
    for name in ("catalogue_lineups", "catalogue_events", "catalogue_possessions"):
        for r in tables[name]:
            assert r["competition_id"] == match_comp[r["match_id"]], name
            if r.get("player_id"):
                assert (r["competition_id"], r["global_id"]) in squad, name
    careers = {p["global_id"] for p in tables["catalogue_players"] if p["career"]}
    assert len(careers) == 5 and all(sum(1 for c, g in squad if g == gid) == 2 for gid in careers)
    for m in tables["catalogue_matches"]:   # seq is each record's place in its stream
        assert m["played_s"] > 0
    seqs = [e["seq"] for e in tables["catalogue_events"] if e["match_id"] == tables["catalogue_matches"][0]["match_id"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


# ---------------------------------------------------------------------------- Regista's numbers
def test_player_season_is_what_the_catalogue_pages_show(cm, tables):
    rows = tables["catalogue_player_season"]
    assert catalogue_player_season_rows(cm) == rows
    for r in rows[::7]:
        c = cm.cell(r["competition_id"], r["global_id"], r["stat"], "level")
        assert (r["per90"], r["percentile"], r["pool_size"], r["qualified"], r["pool_words"]) == (
            c["value"], c["percentile"], c["peers"], c["qualified"], c["pool"]["words"])
        assert r["count"] == round(c["total"]) and r["minutes"] == c["sample"]["minutes"]
    star = {r["stat"]: r for r in rows if r["global_id"] == STAR}
    assert star["goals"]["count"] == 5 and star["goals"]["pool_words"] == "semi-pro men forwards"
    assert star["goals"]["percentile"] is not None


# ---------------------------------------------------------------------------- the notebook's rule, offline
def test_the_notebooks_rule_reproduces_the_catalogue_offline(cm, tables):
    """The second notebook's SQL rule, applied in plain Python to the tables Fabric reads, gives every number the
    catalogue pages show: counts, minutes, per-90, qualified, the level pool's size and the percentile, for every row."""
    regista = tables["catalogue_player_season"]
    r = fb.compare(regista, nb.catalogue_leaders_rule(tables), fb.CATALOGUE_CHECK_STATS)
    assert r["ok"], fb.report_lines(r)
    assert r["checked"] == len(regista) and r["competitions"] == 14
    pct = [x["percentile"] for x in regista]
    assert any(p is None for p in pct) and any(p is not None for p in pct)
    # the level pool is not the competition pool: England and Germany semi-pro men share one
    eng = cm.metrics[ENGLAND_ID]
    assert any(x["percentile"] != eng.players[x["global_id"]].percentiles.get(x["stat"])
               for x in regista if x["competition_id"] == ENGLAND_ID and x["percentile"] is not None)


@pytest.mark.parametrize("change", ["shots_with_penalties", "no_floor", "competition_pools", "genders_mixed"])
def test_the_check_is_sharp(tables, monkeypatch, change):
    """A rule written differently is caught: the league check's shots (penalties in), no 45-minute floor, pools per
    competition, or men and women in one pool."""
    if change == "shots_with_penalties":
        monkeypatch.setitem(nb.EVENT_TESTS, "shots", lambda e: e["event_type"] == "shot")
    elif change == "no_floor":
        monkeypatch.setattr(nb, "FLOOR_MINUTES", 0.0)
    t = dict(tables)
    if change == "competition_pools":
        t["catalogue_competitions"] = [{**c, "tier": c["competition_id"]} for c in tables["catalogue_competitions"]]
    if change == "genders_mixed":
        t["catalogue_competitions"] = [{**c, "gender": "any"} for c in tables["catalogue_competitions"]]
    r = fb.compare(tables["catalogue_player_season"], nb.catalogue_leaders_rule(t), fb.CATALOGUE_CHECK_STATS)
    assert not r["ok"] and r["differences"]


def test_a_pool_under_five_gives_no_percentile_and_a_zero_count_none(tables):
    rows = nb.catalogue_leaders_rule(tables)
    assert all(x["percentile"] is None for x in rows if x["count"] == 0)
    assert all(x["pool_size"] == 0 and x["percentile"] is None for x in rows if x["position"] == "GK")
    smallest = min((x for x in rows if x["position"] != "GK"), key=lambda x: x["pool_size"])
    key = (smallest["tier"], smallest["age_group"], smallest["gender"], smallest["position"])
    members = [x for x in rows if (x["tier"], x["age_group"], x["gender"], x["position"]) == key and x["qualified"]
               and x["stat"] == smallest["stat"]]
    assert len(members) == smallest["pool_size"] >= nb.MIN_POOL
    gone = members[0]
    fewer = {**tables, "catalogue_lineups": [r for r in tables["catalogue_lineups"]
                                             if (r["competition_id"], r["global_id"]) != (gone["competition_id"], gone["global_id"])]}
    if smallest["pool_size"] == nb.MIN_POOL:
        after = [x for x in nb.catalogue_leaders_rule(fewer)
                 if (x["tier"], x["age_group"], x["gender"], x["position"]) == key]
        assert after and all(x["pool_size"] == nb.MIN_POOL - 1 and x["percentile"] is None for x in after)


def test_the_stats_mean_what_the_catalogue_engine_means():
    assert set(nb.STAT_SQL) | {nb.KEY_PASSES} == set(fb.CATALOGUE_CHECK_STATS) == set(nb.STAT_POSITIONS)
    assert fb.CATALOGUE_CHECK_STATS == fb.CHECK_STATS
    for key in fb.CATALOGUE_CHECK_STATS:
        m = CATALOGUE[key]
        # per-90 counts where more is better: no inverted percentile, and "none yet" (no percentile at 0) applies
        assert m.kind == "per90" and m.higher_is_better is True and key in COUNT_METRICS, key
        assert nb.STAT_POSITIONS[key] == m.positions, key
    assert "penalty" in nb.STAT_SQL["shots"] and "COALESCE(outcome, 'success')" in nb.STAT_SQL["tackles_won"]


def test_the_notebook_reads_only_the_catalogue_and_states_its_rule():
    d = nb.definition("ws-1", "lh-1", "regista_league")
    assert d["format"] == "ipynb" and d["parts"][0]["path"] == "notebook-content.ipynb"
    book = json.loads(base64.b64decode(d["parts"][0]["payload"]))
    assert book["metadata"]["dependencies"]["lakehouse"] == {
        "default_lakehouse": "lh-1", "default_lakehouse_name": "regista_league", "default_lakehouse_workspace_id": "ws-1"}
    code = "".join("".join(c["source"]) for c in book["cells"] if c["cell_type"] == "code")
    assert "abfss://ws-1@onelake.dfs.fabric.microsoft.com/lh-1/Tables" in code
    assert all(t.startswith("catalogue_") for t in nb.TABLES) and set(nb.TABLES) < set(CATALOGUE_TABLES)
    assert '{BASE}/catalogue_leaders_check' in code and '{BASE}/leaders_check' not in code
    for stat in fb.CATALOGUE_CHECK_STATS:
        assert f"'{stat}'" in code
    for cell in book["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "cell", "exec")
    sql = " ".join(" ".join(nb.statements() + [nb.LEADERS_SQL]).split())
    assert "GREATEST(ROUND(MAX(m.club_min) / 3.0D, 1), 45.0D)" in sql and "c.source = 'league'" in sql
    assert "PARTITION BY tier, age_group, gender, position, stat ORDER BY rank_value" in sql
    assert "r.n >= 5 AND f.count > 0" in sql
    assert "BROUND(CAST(r.below + r.at_or_below AS DOUBLE) * 50.0D / r.n, 0)" in sql
    assert "p.gained_by = 'pass_received'" in sql and "e.seq > COALESCE(p.prev_seq, -1)" in sql


def test_the_league_notebook_is_unchanged():
    from regista.cloud.fabric_notebook import definition as league_definition

    book = json.loads(base64.b64decode(league_definition("ws-1", "lh-1", "regista_league")["parts"][0]["payload"]))
    code = "".join("".join(c["source"]) for c in book["cells"] if c["cell_type"] == "code")
    assert "catalogue" not in code and '{BASE}/leaders_check' in code
    assert fb.NOTEBOOK_NAME == "regista_leaders_check" != fb.CATALOGUE_NOTEBOOK_NAME


# ---------------------------------------------------------------------------- the comparison, keyed on competition
def _row(cid, gid, stat="goals", **kw):
    return {"competition_id": cid, "global_id": gid, "stat": stat, "appearances": 3, "minutes": 90.0, "count": 1,
            "per90": 1.0, "percentile": 50, "qualified": True, "pool_size": 12, **kw}


def test_compare_keeps_a_careers_two_rows_apart():
    regista = [_row("co_esp_u19", "pl_sot_09"), _row("co_esp_am_men", "pl_sot_09", count=2, per90=2.0)]
    same = fb.compare(regista, [dict(x) for x in regista], ["goals"])
    assert same["ok"] and (same["players"], same["checked"], same["competitions"]) == (2, 2, 2)
    assert fb.report_lines(same)[0].startswith("checked 2 player-competition rows in 2 competitions x 1 stats")
    swapped = [dict(regista[0], count=2, per90=2.0), dict(regista[1], count=1, per90=1.0, pool_size=11, qualified=False)]
    r = fb.compare(regista, swapped, ["goals"])
    assert not r["ok"] and {(d["competition_id"], d["field"]) for d in r["differences"]} == {
        ("co_esp_u19", "count"), ("co_esp_u19", "per90"), ("co_esp_am_men", "count"), ("co_esp_am_men", "per90"),
        ("co_esp_am_men", "pool_size"), ("co_esp_am_men", "qualified")}
    assert any(x.startswith("  co_esp_u19 pl_sot_09 goals count: Regista 1, Fabric 2") for x in fb.report_lines(r))
    assert fb.compare([_row("a", "p", per90=None)], [_row("a", "p", per90=None)], ["goals"])["ok"]


# ---------------------------------------------------------------------------- the CLI
class FakeLake:
    written: dict = {}
    stored: dict = {}

    def __init__(self, ws, lh, tokens=None):
        self.ws, self.lh = ws, lh

    def write(self, name, data):
        FakeLake.written[name] = data

    def read(self, name):
        return to_arrow(name, FakeLake.stored[name]) if name in SCHEMAS else _Arrowish(FakeLake.stored[name])


class _Arrowish:
    def __init__(self, rows):
        self.rows = rows

    def to_pylist(self):
        return [dict(r) for r in self.rows]


class FakeClient:
    def __init__(self):
        self.tokens = lambda scope: "t"
        self.made: list = []
        self.ran: list = []

    def lakehouses(self, ws):
        return [{"id": "lh-1", "displayName": "regista_league"}]

    def notebooks(self, ws):
        return [{"id": "nb-c", "displayName": name} for name, _d in self.made]

    def create_notebook(self, ws, name, definition, description=""):
        self.made.append((name, definition))

    def update_notebook(self, ws, nb_id, definition):
        raise AssertionError("a new workspace has no notebook to update")

    def run_notebook(self, ws, nb_id):
        self.ran.append(nb_id)
        return "job-url"

    def wait_job(self, url, timeout_s=0, progress=None):
        return {"id": "job-1", "status": "Completed"}


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    from regista.season import fabric as cli

    monkeypatch.setenv(fb.ENV_WORKSPACE, "ws-1")
    monkeypatch.setenv(fb.ENV_LAKEHOUSE, "lh-1")
    monkeypatch.setattr(fb, "OneLake", FakeLake)
    FakeLake.written, FakeLake.stored = {}, {}
    return cli, ["--env", str(tmp_path / "none.env")]


def test_push_catalogue_only_writes_only_the_catalogue_tables(cli_env, monkeypatch, tables, capsys):
    import regista.cloud.fabric_catalogue as fc

    cli, env = cli_env
    seen = {}
    monkeypatch.setattr(fc, "catalogue_tables", lambda **kw: seen.update(kw) or tables)
    monkeypatch.setattr(cli, "_league_tables", lambda args: (_ for _ in ()).throw(AssertionError("league pushed")))
    assert cli.main([*env, "push", "--catalogue-only"]) == 0
    assert set(FakeLake.written) == set(CATALOGUE_TABLES)
    assert FakeLake.written["catalogue_events"].num_rows == len(tables["catalogue_events"])
    assert seen["league_path"] == cli.LEAGUE and seen["season_root"] == cli.ROOT
    assert "pushed 8 tables" in capsys.readouterr().out


def test_push_with_catalogue_writes_both_and_plain_push_only_the_league(cli_env, monkeypatch, tables):
    import regista.cloud.fabric_catalogue as fc

    cli, env = cli_env
    league = {"clubs": [{"club_id": "cl_a", "name": "A", "short_name": "A", "ground": None, "kit_primary": None,
                         "kit_secondary": None, "kit_gk": None}]}
    monkeypatch.setattr(fc, "catalogue_tables", lambda **kw: tables)
    monkeypatch.setattr(cli, "_league_tables", lambda args: dict(league))
    assert cli.main([*env, "push", "--catalogue"]) == 0
    assert set(FakeLake.written) == {"clubs", *CATALOGUE_TABLES}
    FakeLake.written = {}
    assert cli.main([*env, "push"]) == 0
    assert set(FakeLake.written) == {"clubs"}


def test_check_catalogue_runs_the_second_notebook_and_compares(cli_env, monkeypatch, tables, capsys):
    cli, env = cli_env
    client = FakeClient()
    monkeypatch.setattr(fb, "FabricClient", lambda: client)
    FakeLake.stored = {"catalogue_player_season": tables["catalogue_player_season"],
                       "catalogue_leaders_check": nb.catalogue_leaders_rule(tables)}
    assert cli.main([*env, "check", "--catalogue"]) == 0
    assert [name for name, _d in client.made] == [fb.CATALOGUE_NOTEBOOK_NAME] and client.ran == ["nb-c"]
    book = json.loads(base64.b64decode(client.made[0][1]["parts"][0]["payload"]))
    assert "catalogue_leaders_check" in "".join("".join(c["source"]) for c in book["cells"])
    out = capsys.readouterr().out
    assert f"{len(tables['catalogue_player_season'])} of {len(tables['catalogue_player_season'])} match" in out
    assert "result: Fabric agrees with Regista" in out
    # --no-run compares what is there; a changed number fails the check
    bad = [dict(x) for x in FakeLake.stored["catalogue_leaders_check"]]
    bad[0]["count"] += 1
    FakeLake.stored["catalogue_leaders_check"] = bad
    assert cli.main([*env, "check", "--catalogue", "--no-run"]) == 1
    assert "MISMATCH" in capsys.readouterr().out
