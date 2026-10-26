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
    # time on the pitch comes from the events: the tables' played_s is never read
    assert "played_s" not in sql.replace("catalogue_lineups.played_s", "")
    assert "s.event_type = 'period_start'" in sql and "MIN_BY(t, seq) AS t_off" in sql and "event_type = 'card_red'" in sql


def test_the_league_notebook_is_unchanged():
    from regista.cloud.fabric_notebook import definition as league_definition

    book = json.loads(base64.b64decode(league_definition("ws-1", "lh-1", "regista_league")["parts"][0]["payload"]))
    code = "".join("".join(c["source"]) for c in book["cells"] if c["cell_type"] == "code")
    assert "catalogue" not in code and '{BASE}/leaders_check' in code
    assert fb.NOTEBOOK_NAME == "regista_leaders_check" != fb.CATALOGUE_NOTEBOOK_NAME


# ---------------------------------------------------------------------------- built cases: the rules the season cannot tell apart
# On the committed catalogue three of the rewritten rules give the same numbers as a plausible wrong one (the league's
# key-pass qualifier, the 45-minute floor applied to England as well, a tackle with no outcome counted as lost), so the
# check above would pass with either. These small streams tell them apart. Each goes through the real table builder
# (``fabric_catalogue._match_rows``), the twin reads the tables, and the engine (``regista.season.metrics.analyse_match``,
# ``qualifying_minutes``, ``regista.season.playing_time``) gives the expected answer from the stream.
A, B = "t_a", "t_b"
BUILT_PLAYERS = [("a1", A, "MF", True), ("a2", A, "MF", True), ("a3", A, "FW", True), ("a4", A, "DF", True),
                 ("a5", A, "FW", False), ("b1", B, "DF", True), ("b2", B, "DF", False)]


class _Built:
    """One built stream: header, period events around the records given, ids and stream order filled in."""

    def __init__(self, match_id, records, periods=((0.0, 900.0), (905.0, 1805.0))):
        self.match_id = match_id
        header = {"type": "match", "id": f"ma_{match_id}", "match_id": match_id, "home_team_id": A, "away_team_id": B,
                  "teams": [{"team_id": A, "club_id": "cl_a"}, {"team_id": B, "club_id": "cl_b"}],
                  "players": [{"player_id": pid, "team_id": team, "kit_number": i + 1, "position": pos, "starter": st,
                               "global_player_id": f"pl_{pid}"} for i, (pid, team, pos, st) in enumerate(BUILT_PLAYERS)],
                  "periods": [{"period": i + 1, "t": t0, "t_end": t1, "left_to_right_team_id": A if i % 2 == 0 else B}
                              for i, (t0, t1) in enumerate(periods)],
                  "score": {A: 0, B: 0}}
        body = [{"type": "event", "event_type": "period_start", "t": t0, "period": i + 1} for i, (t0, _t1) in enumerate(periods)]
        body += [{"type": "event", "event_type": "period_end", "t": t1, "period": i + 1} for i, (_t0, t1) in enumerate(periods)]
        body += [dict(r) for r in records]
        body.sort(key=lambda r: r["t"])   # stable: records at the same time keep the order given
        self.stream = [header]
        for i, r in enumerate(body, 1):
            period = r.pop("period", None) or (1 if r["t"] < periods[0][1] else 2)
            r.setdefault("id", f"{'po' if r['type'] == 'possession' else 'ev'}_{i:04d}")
            if r["type"] == "event":
                r.setdefault("outcome", "success")
                r.setdefault("qualifiers", [])
                r["clock"] = {"period": period, "minute": int(r["t"] // 60), "second": int(r["t"] % 60)}
            self.stream.append(r)

    def engine(self):
        from regista.season.metrics import analyse_match

        return analyse_match(self.stream)


def _ev(t, event_type, pid=None, team=None, **kw):
    return {"type": "event", "t": t, "event_type": event_type, "player_id": pid, "team_id": team, **kw}


def _poss(t, pid, team, gained_by, pid_id):
    return {"type": "possession", "id": pid_id, "t": t, "t_end": t + 0.5, "player_id": pid, "team_id": team,
            "gained_by": gained_by}


def _built_tables(tmp_path, comps):
    """comps: [(competition_id, source, [_Built, ...])]: the catalogue tables for them, made by the real table builder."""
    from regista.cloud.fabric_catalogue import _match_rows

    t = {"catalogue_competitions": [], "catalogue_players": [], "catalogue_matches": [], "catalogue_lineups": [],
         "catalogue_events": [], "catalogue_possessions": []}
    for cid, source, built in comps:
        t["catalogue_competitions"].append({"competition_id": cid, "source": source, "tier": "semi_pro",
                                            "age_group": "senior", "gender": "men"})
        t["catalogue_players"] += [{"competition_id": cid, "global_id": f"pl_{pid}", "position": pos}
                                   for pid, _team, pos, _st in BUILT_PLAYERS]
        for i, b in enumerate(built):
            d = tmp_path / cid / b.match_id
            d.mkdir(parents=True)
            (d / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in b.stream))
            fx = {"match_id": b.match_id, "round": i + 1, "date": "2026-10-01", "home": "cl_a", "away": "cl_b"}
            _match_rows(t, cid, fx, d, {})
    return t


def _twin(tables, stat):
    return {r["global_id"][3:]: r for r in nb.catalogue_leaders_rule(tables, [stat])}


def test_built_key_passes_are_fbrefs_not_the_league_qualifier(tmp_path):
    """The key pass is the last completed pass or cross, by a teammate, to the shooter, between the possession record
    before the shot's own and the shot's own; a penalty has none. The league's rule (a pass tagged ``key_pass``) gives
    another answer here, and so does a rule without the possession window."""
    b = _Built("bm_kp", [
        _poss(1.0, "b1", B, "kickoff", "po_b0"),
        _ev(2.0, "pass", "a1", A, related_player_id="a3", qualifiers=["key_pass"]),   # before P1: outside P2's window
        _poss(3.0, "a1", A, "interception", "po_p1"),
        _ev(3.5, "carry", "a1", A, possession_id="po_p1"),
        _poss(4.0, "a3", A, "pass_received", "po_p2"),
        _ev(4.5, "shot", "a3", A, possession_id="po_p2", qualifiers=["off_target"]),  # no key pass
        _poss(10.0, "b1", B, "tackle", "po_q"),
        _ev(11.0, "pass", "a1", A, related_player_id="a3"),
        _ev(12.0, "cross", "a2", A, related_player_id="a3"),                          # the last complete one: a2
        _ev(13.0, "pass", "a4", A, related_player_id="a3", outcome="fail"),
        _ev(13.5, "pass", "b1", B, related_player_id="a3"),
        _poss(14.0, "a3", A, "pass_received", "po_p3"),
        _ev(14.5, "shot", "a3", A, possession_id="po_p3", qualifiers=["saved"]),
        _ev(20.0, "pass", "a2", A, related_player_id="a3"),
        _poss(21.0, "a3", A, "pass_received", "po_p4"),
        _ev(21.5, "shot", "a3", A, possession_id="po_p4", qualifiers=["penalty", "goal"]),   # a penalty: none
    ])
    tables = _built_tables(tmp_path, [("co_built", "catalogue", [b])])
    twin = {g: r["count"] for g, r in _twin(tables, "key_passes").items()}
    engine = {pid: int(c.get("key_passes", 0)) for pid, c in b.engine().counts.items()}
    assert twin["a2"] == 1 and twin["a1"] == 0 and sum(twin.values()) == 1
    assert {g: n for g, n in twin.items() if n} == {g: n for g, n in engine.items() if n}
    league = Counter(e["player_id"] for e in tables["catalogue_events"]
                     if e["event_type"] in ("pass", "cross") and "key_pass" in e["qualifiers"])
    assert dict(league) == {"a1": 1}   # the league's rule credits a1, the catalogue's a2
    # without the window (any earlier pass to the shooter), a1's pass before P1 would be P2's shot's key pass
    ev, poss = tables["catalogue_events"], {p["possession_id"]: p for p in tables["catalogue_possessions"]}
    window_less = Counter()
    for shot in ev:
        if shot["event_type"] == "shot" and "penalty" not in shot["qualifiers"] and \
                poss[shot["possession_id"]]["gained_by"] == "pass_received":
            cands = [e for e in ev if e["seq"] < poss[shot["possession_id"]]["seq"] and e["event_type"] in ("pass", "cross")
                     and e["outcome"] == "success" and e["team_id"] == shot["team_id"] and e["related_player_id"] == "a3"]
            window_less[max(cands, key=lambda e: e["seq"])["player_id"]] += 1
    assert dict(window_less) == {"a1": 1, "a2": 1}


def test_built_tackle_without_an_outcome_is_won(tmp_path, monkeypatch):
    """The engine counts a tackle with no outcome as won (``r.get("outcome", "success")``); the schema requires an
    outcome, so only a stream outside it has one, and the table keeps it as null. The league's test (outcome =
    'success') drops it."""
    b = _Built("bm_tk", [_ev(5.0, "tackle", "a4", A), _ev(6.0, "tackle", "a4", A, outcome="success"),
                         _ev(7.0, "tackle", "a4", A, outcome="fail"), _ev(8.0, "tackle", "b1", B)])
    for r in b.stream:
        if r.get("event_type") == "tackle" and r["t"] in (5.0, 8.0):
            del r["outcome"]
    tables = _built_tables(tmp_path, [("co_built", "catalogue", [b])])
    assert sum(1 for e in tables["catalogue_events"] if e["event_type"] == "tackle" and e["outcome"] is None) == 2
    engine = b.engine().counts
    twin = _twin(tables, "tackles_won")
    assert (twin["a4"]["count"], twin["b1"]["count"]) == (int(engine["a4"]["tackles_won"]), int(engine["b1"]["tackles_won"])) == (2, 1)
    monkeypatch.setitem(nb.EVENT_TESTS, "tackles_won", lambda e: e["event_type"] == "tackle" and e["outcome"] == "success")
    drifted = _twin(tables, "tackles_won")
    assert (drifted["a4"]["count"], drifted["b1"]["count"]) == (1, 0)


def test_built_england_keeps_its_third_without_the_floor(tmp_path, monkeypatch):
    """England's qualifying minutes are a third of its busiest club's, with no 45-minute floor; elsewhere the floor
    applies. A busiest club with 120 minutes (two 60-minute matches) gives 40.0: a player with 42 minutes qualifies in
    England and not in another competition. On the committed season England sits at 100.5, so only this case shows it."""
    from regista.catalogue.metrics import FLOOR
    from regista.season.metrics import qualifying_minutes

    def matches(cid):   # a1 starts both: off at 42:00 in the first, at once in the second (42 minutes, 2 appearances)
        return [_Built(f"{cid}_1", [_ev(2520.0, "substitution", "a1", A, related_player_id="a5")],
                       periods=((0.0, 1800.0), (1800.0, 3600.0))),
                _Built(f"{cid}_2", [_ev(0.0, "substitution", "a1", A, related_player_id="a5")],
                       periods=((0.0, 1800.0), (1800.0, 3600.0)))]

    tables = _built_tables(tmp_path, [("co_eng", nb.ENGLAND_SOURCE, matches("co_eng")),
                                      ("co_elsewhere", "catalogue", matches("co_elsewhere"))])
    rows = {(r["competition_id"], r["global_id"]): r for r in nb.catalogue_leaders_rule(tables, ["goals"])}
    eng, other = rows[("co_eng", "pl_a1")], rows[("co_elsewhere", "pl_a1")]
    assert eng["minutes"] == other["minutes"] == 42.0
    assert eng["qualifying_minutes"] == qualifying_minutes(120.0) == 40.0 < FLOOR == nb.FLOOR_MINUTES
    assert other["qualifying_minutes"] == FLOOR
    assert eng["qualified"] and not other["qualified"]
    monkeypatch.setattr(nb, "ENGLAND_SOURCE", "nobody")   # the floor applied to England too
    assert not {(r["competition_id"], r["global_id"]): r
                for r in nb.catalogue_leaders_rule(tables, ["goals"])}[("co_eng", "pl_a1")]["qualified"]


def test_built_time_on_the_pitch_is_worked_out_from_the_events(tmp_path):
    """The notebook recomputes time on the pitch from period, substitution and card_red events, not from the tables'
    played_s: starters, a substitute, a red card, a substitute sent off, the first of two exits."""
    from regista.season.playing_time import played_seconds

    b = _Built("bm_on", [_ev(300.0, "card_red", "a2", A),
                         _ev(1000.0, "substitution", "a1", A, related_player_id="a5"),
                         _ev(1500.0, "card_red", "a5", A),
                         _ev(1200.0, "substitution", "b1", B, related_player_id="b2"),
                         _ev(1300.0, "card_red", "b1", B)])   # already off: the first exit counts
    tables = _built_tables(tmp_path, [("co_built", "catalogue", [b])])
    secs = {pid: s for (_mid, pid), (_c, _g, s) in nb.on_pitch(tables).items()}
    assert secs == played_seconds(b.stream)
    assert secs == {"a1": 995.0, "a2": 300.0, "a3": 1800.0, "a4": 1800.0, "a5": 500.0, "b1": 1195.0, "b2": 605.0}
    zeroed = {**tables, "catalogue_lineups": [{**r, "played_s": 0.0} for r in tables["catalogue_lineups"]],
              "catalogue_matches": [{**m, "played_s": 0.0} for m in tables["catalogue_matches"]]}
    assert nb.catalogue_leaders_rule(zeroed) == nb.catalogue_leaders_rule(tables)   # the tables' played_s is never read


def test_time_on_the_pitch_from_the_events_agrees_on_every_catalogue_match(tables):
    """On all 90 matches, the minutes the notebook works out from the events equal the playing-time rule's
    (catalogue_lineups.played_s, from regista.season.playing_time) for every lineup row that played, and each match's
    length equals catalogue_matches.played_s."""
    mine = nb.on_pitch(tables)
    theirs = {(r["match_id"], r["player_id"]): r["played_s"] for r in tables["catalogue_lineups"]}
    assert mine and all(theirs[k] == s for k, (_c, _g, s) in mine.items())
    assert all(s == 0.0 for k, s in theirs.items() if k not in mine)
    lengths = nb.match_lengths(tables["catalogue_events"])
    assert {m["match_id"]: m["played_s"] for m in tables["catalogue_matches"]} == lengths


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


def test_compare_allows_one_unit_of_rounding_and_no_more():
    """Spark rounds a half up on the decimal form, Python half-even on the binary value: 30.15 minutes is 30.1 in Python
    and 30.2 in Spark. One unit of the last digit passes; two units do not."""
    assert round(30.15, 1) == 30.1 and round(0.125, 2) == 0.12   # Spark's ROUND gives 30.2 and 0.13
    one = fb.compare([_row("a", "p", minutes=30.1, per90=0.12)], [_row("a", "p", minutes=30.2, per90=0.13)], ["goals"])
    assert one["ok"]
    two = fb.compare([_row("a", "p", minutes=30.1, per90=0.12)], [_row("a", "p", minutes=30.3, per90=0.14)], ["goals"])
    assert not two["ok"] and {d["field"] for d in two["differences"]} == {"minutes", "per90"}


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
