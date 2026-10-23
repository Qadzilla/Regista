"""Microsoft Fabric: capacity choice, setup, the lakehouse tables, the notebook definition, and the cross-check.

Everything runs against fakes: a fake HTTP transport for the Fabric and Power BI APIs, fake tokens, and a local folder
(or a recording fake) in place of OneLake. No test reaches Fabric or Azure."""

import base64
import json
from pathlib import Path

import pytest

from regista.cloud import fabric as fb
from regista.cloud.fabric_notebook import STAT_SQL, definition
from regista.cloud.fabric_tables import SCHEMAS, UPLOAD_STATS, player_season_rows, season_tables, to_arrow, upload_rows
from regista.player.store import LocalStore, UploadRecord, match_id_for
from regista.schema import iter_jsonl
from regista.season.build import materialise
from regista.season.league import new_league, people
from regista.season.profiles import STATS, Season

ME = "al-qadi.z@northeastern.edu"
MINE = "9c9f2c26-2a79-4b7f-b1c0-294a4bc697fc"
THEIRS = "f9a6f187-4d65-4c1f-879c-83e168987333"
PPU = "c9b63cc4-affa-4fec-8c11-8ef4880144df"


def jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")  # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


def fabric_caps():
    return [{"id": MINE, "displayName": "Trial-20261023T034958Z-x", "sku": "FTL64", "region": "Central US", "state": "Active"},
            {"id": PPU, "displayName": "Premium Per User - Reserved", "sku": "PP3", "state": "Active"},
            {"id": THEIRS, "displayName": "Trial-20260904T163223Z-y", "sku": "FTL64", "state": "Active"}]


def powerbi_caps():
    # as the Power BI API answers in this tenant: other people's trials show no admins and only the Assign right,
    # and ids can come back in upper case
    return [{"id": MINE, "admins": [ME], "capacityUserAccessRight": "Admin", "sku": "FTL64"},
            {"id": THEIRS, "admins": [], "capacityUserAccessRight": "Assign", "sku": "FTL64"},
            {"id": PPU.upper(), "admins": [ME], "capacityUserAccessRight": "Admin", "sku": "PP3"}]


# ---------------------------------------------------------------------------- capacity choice
def test_choose_capacity_picks_only_the_users_own_trial():
    assert fb.choose_capacity(fabric_caps(), powerbi_caps(), ME)["id"] == MINE
    assert fb.choose_capacity(fabric_caps(), powerbi_caps(), ME.upper())["id"] == MINE  # names compare without case


def test_choose_capacity_never_picks_someone_elses_trial():
    with pytest.raises(fb.NoOwnCapacity):
        fb.choose_capacity(fabric_caps(), powerbi_caps(), ME, capacity_id=THEIRS)
    with pytest.raises(fb.NoOwnCapacity):
        fb.choose_capacity(fabric_caps(), powerbi_caps(), ME, capacity_id=PPU)  # admin of it, but it is not a trial
    # the trial is not on yet: only other people's trials are visible
    pbi = [c for c in powerbi_caps() if c["id"] != MINE]
    with pytest.raises(fb.NoOwnCapacity, match="not on yet"):
        fb.choose_capacity(fabric_caps(), pbi, ME)
    # admin listed but without the Admin right, or someone else as admin: not the user's
    for change in ({"capacityUserAccessRight": "Assign"}, {"admins": ["someone.else@northeastern.edu"]}):
        pbi = [{**c, **change} if c["id"] == MINE else c for c in powerbi_caps()]
        with pytest.raises(fb.NoOwnCapacity):
            fb.choose_capacity(fabric_caps(), pbi, ME)


def test_choose_capacity_skips_a_paused_trial_and_asks_when_there_are_several():
    paused = [{**c, "state": "Inactive"} if c["id"] == MINE else c for c in fabric_caps()]
    with pytest.raises(fb.NoOwnCapacity):
        fb.choose_capacity(paused, powerbi_caps(), ME)
    second = "11111111-2222-3333-4444-555555555555"
    caps = fabric_caps() + [{"id": second, "displayName": "Trial-2", "sku": "FTL64", "state": "Active"}]
    pbi = powerbi_caps() + [{"id": second, "admins": [ME], "capacityUserAccessRight": "Admin"}]
    with pytest.raises(fb.FabricError, match="several"):
        fb.choose_capacity(caps, pbi, ME)
    assert fb.choose_capacity(caps, pbi, ME, capacity_id=second)["id"] == second


def test_upn_from_token():
    assert fb.upn_from_token(jwt({"upn": ME})) == ME
    assert fb.upn_from_token(jwt({"preferred_username": ME})) == ME
    with pytest.raises(fb.FabricError):
        fb.upn_from_token(jwt({"appid": "x"}))  # a service principal owns no trial


# ---------------------------------------------------------------------------- the REST client, faked
class FakeFabric:
    """Just enough of the Fabric and Power BI APIs: capacities, workspaces, lakehouses (created through a long-running
    operation), notebooks and job runs. Records every call."""

    def __init__(self, workspaces=None, pbi=None):
        self.calls = []
        self.workspaces = list(workspaces or [])
        self.pbi = pbi if pbi is not None else powerbi_caps()
        self.lakehouses: dict[str, list] = {}
        self.notebooks: dict[str, list] = {}
        self.ops: dict[str, dict] = {}
        self.jobs: dict[str, list] = {}

    def __call__(self, method, url, headers, body):
        assert headers["Authorization"].startswith("Bearer ")
        data = json.loads(body) if body else None
        self.calls.append((method, url, data))
        path = url.split("api.fabric.microsoft.com/v1", 1)[-1]
        if url.startswith(fb.POWERBI_API):
            assert headers["Authorization"] == "Bearer pbi-token"
            return self._ok({"value": self.pbi})
        if method == "GET" and path == "/capacities":
            return self._ok({"value": fabric_caps()})
        if method == "GET" and path == "/workspaces":
            return self._ok({"value": self.workspaces})
        if method == "POST" and path == "/workspaces":
            ws = {"id": f"ws-{len(self.workspaces)}", "type": "Workspace", **data}
            self.workspaces.append(ws)
            return fb.Response(201, {}, json.dumps(ws).encode())
        parts = path.split("?")[0].strip("/").split("/")
        if parts[0] == "operations":
            op = self.ops[parts[1]]
            if len(parts) == 3:
                return self._ok(op["result"])
            op["polls"] += 1
            return self._ok({"status": "Succeeded" if op["polls"] > 1 else "Running"})
        ws = parts[1]
        if parts[2] == "lakehouses" and method == "GET":
            return self._ok({"value": self.lakehouses.get(ws, [])})
        if parts[2] == "lakehouses" and method == "POST":
            lh = {"id": f"lh-{ws}", "displayName": data["displayName"], "type": "Lakehouse"}
            self.lakehouses.setdefault(ws, []).append(lh)
            self.ops["op1"] = {"polls": 0, "result": lh}
            return fb.Response(202, {"location": f"{fb.FABRIC_API}/operations/op1", "retry-after": "1"}, b"")
        if parts[2] == "notebooks" and method == "GET":
            return self._ok({"value": self.notebooks.get(ws, [])})
        if parts[2] == "notebooks" and method == "POST" and len(parts) == 3:
            nb = {"id": "nb-1", "displayName": data["displayName"], "definition": data["definition"]}
            self.notebooks.setdefault(ws, []).append(nb)
            return fb.Response(201, {}, json.dumps({"id": "nb-1", "displayName": data["displayName"]}).encode())
        if parts[2] == "notebooks" and parts[-1] == "updateDefinition":
            next(n for n in self.notebooks[ws] if n["id"] == parts[3])["definition"] = data["definition"]
            return fb.Response(200, {}, b"")
        if parts[2] == "items" and parts[4] == "jobs" and method == "POST":
            assert "jobType=RunNotebook" in url
            self.jobs["job-1"] = ["NotStarted", "InProgress", "Completed"]
            return fb.Response(202, {"location": f"{fb.FABRIC_API}/workspaces/{ws}/items/{parts[3]}/jobs/instances/job-1"}, b"")
        if parts[2] == "items" and parts[4] == "jobs" and method == "GET":
            states = self.jobs[parts[6]]
            status = states.pop(0) if len(states) > 1 else states[0]
            return self._ok({"id": parts[6], "status": status})
        raise AssertionError(f"unexpected {method} {url}")

    @staticmethod
    def _ok(body):
        return fb.Response(200, {}, json.dumps(body).encode())


def client_for(fake):
    tokens = {fb.FABRIC_SCOPE: jwt({"upn": ME}), fb.POWERBI_SCOPE: "pbi-token", fb.STORAGE_SCOPE: "storage-token"}
    return fb.FabricClient(tokens=tokens.__getitem__, transport=fake, sleep=lambda s: None, poll_s=0)


def test_setup_creates_the_workspace_on_the_users_own_capacity_and_the_lakehouse():
    fake = FakeFabric(workspaces=[{"id": "other", "displayName": "Off Campus Housing", "type": "Workspace", "capacityId": THEIRS}])
    s = fb.setup(client_for(fake))
    assert s.upn == ME and s.capacity["id"] == MINE and s.created == ["workspace", "lakehouse"]
    posts = [(u, d) for m, u, d in fake.calls if m == "POST"]
    assert posts[0][1]["displayName"] == "Regista" and posts[0][1]["capacityId"] == MINE
    assert s.lakehouse["displayName"] == "regista_league" and s.lakehouse["id"] == f"lh-{s.workspace['id']}"
    # nothing was sent to anyone else's workspace or capacity
    assert not any("other" in u or (d and THEIRS in json.dumps(d)) for _m, u, d in fake.calls)


def test_setup_reuses_what_is_there():
    fake = FakeFabric(workspaces=[{"id": "ws-r", "displayName": "Regista", "type": "Workspace", "capacityId": MINE.upper()}])
    fake.lakehouses["ws-r"] = [{"id": "lh-r", "displayName": "regista_league"}]
    s = fb.setup(client_for(fake))
    assert (s.workspace["id"], s.lakehouse["id"], s.created) == ("ws-r", "lh-r", [])
    assert not [c for c in fake.calls if c[0] == "POST"]


def test_setup_never_touches_a_regista_workspace_on_another_capacity():
    fake = FakeFabric(workspaces=[{"id": "ws-x", "displayName": "Regista", "type": "Workspace", "capacityId": THEIRS}])
    with pytest.raises(fb.FabricError, match="not touching it"):
        fb.setup(client_for(fake))
    assert not [c for c in fake.calls if c[0] == "POST"]


def test_setup_stops_when_the_trial_is_not_on():
    fake = FakeFabric(pbi=[c for c in powerbi_caps() if c["id"] != MINE])
    with pytest.raises(fb.NoOwnCapacity):
        fb.setup(client_for(fake))
    assert not [c for c in fake.calls if c[0] == "POST"]


def test_notebook_create_update_and_run():
    fake = FakeFabric()
    c = client_for(fake)
    d1 = definition("ws-1", "lh-1", "regista_league")
    c.create_notebook("ws-1", fb.NOTEBOOK_NAME, d1)
    c.update_notebook("ws-1", "nb-1", definition("ws-1", "lh-1", "regista_league", ["goals"]))
    assert fake.notebooks["ws-1"][0]["definition"] != d1
    seen = []
    job = c.wait_job(c.run_notebook("ws-1", "nb-1"), progress=seen.append)
    assert job["status"] == "Completed" and seen == ["notebook run: NotStarted", "notebook run: InProgress",
                                                     "notebook run: Completed"]


def test_429_waits_and_retries():
    waits, answers = [], [fb.Response(429, {"retry-after": "3"}, b""), fb.Response(200, {}, b'{"value": []}')]
    c = fb.FabricClient(tokens=lambda s: "t", transport=lambda *a: answers.pop(0), sleep=waits.append)
    assert c.workspaces() == [] and waits == [3.0]


def test_errors_say_what_failed():
    c = fb.FabricClient(tokens=lambda s: "t", transport=lambda *a: fb.Response(403, {}, b'{"errorCode":"Forbidden"}'))
    with pytest.raises(fb.FabricError, match="403"):
        c.workspaces()


# ---------------------------------------------------------------------------- .env
def test_set_env_lines_edits_only_those_lines(tmp_path):
    env = tmp_path / ".env"
    original = "# comment\nA=1\nREGISTA_FABRIC_WORKSPACE_ID=old\nB='x=y'\nREGISTA_FABRIC_WORKSPACE_ID=dupe\nC=3"
    env.write_text(original)
    fb.set_env_lines(env, {fb.ENV_WORKSPACE: "ws-new", fb.ENV_LAKEHOUSE: "lh-new"})
    assert env.read_text() == "# comment\nA=1\nREGISTA_FABRIC_WORKSPACE_ID=ws-new\nB='x=y'\nC=3\nREGISTA_FABRIC_LAKEHOUSE_ID=lh-new\n"
    fb.set_env_lines(env, {fb.ENV_LAKEHOUSE: "lh-2"})
    assert env.read_text().count("REGISTA_FABRIC_LAKEHOUSE_ID") == 1 and "lh-2" in env.read_text()
    fb.set_env_lines(tmp_path / "new.env", {fb.ENV_WORKSPACE: "w"})
    assert (tmp_path / "new.env").read_text() == "REGISTA_FABRIC_WORKSPACE_ID=w\n"


# ---------------------------------------------------------------------------- tables
@pytest.fixture(scope="module")
def small():
    league = new_league(2026)
    return {**league, "fixtures": league["fixtures"][:3]}


@pytest.fixture(scope="module")
def tables(small, tmp_path_factory):
    root = tmp_path_factory.mktemp("fabric_season")
    season = Season.build(small, root)
    return small, root, season, season_tables(small, root, season)


def test_tables_have_their_schema_and_sizes(tables):
    small, root, _season, t = tables
    assert set(t) == set(SCHEMAS) - {"uploads"}
    for name, rows in t.items():
        assert rows and all(set(r) == set(SCHEMAS[name]) for r in rows), name
        arrow = to_arrow(name, rows)
        assert arrow.column_names == list(SCHEMAS[name]) and arrow.num_rows == len(rows)
    assert len(t["clubs"]) == 6 and len(t["players"]) == 108 and len(t["matches"]) == 3
    assert len(t["lineups"]) == 3 * 36 and len(t["player_season"]) == 108 * len(STATS)
    n_events = sum(1 for fx in small["fixtures"] for r in iter_jsonl(root / fx["match_id"] / "events.jsonl") if r["type"] == "event")
    assert len(t["events"]) == n_events
    assert len(t["clips"]) == len(t["labels"]) and {lb["clip_id"] for lb in t["labels"]} == {c["clip_id"] for c in t["clips"]}


def test_every_row_carries_the_global_player_id(tables):
    small, _root, _season, t = tables
    who = people(small)
    assert {r["global_id"] for r in t["players"]} == set(who)
    for name in ("lineups", "clips", "labels", "player_season"):
        assert all(r["global_id"] in who for r in t[name]), name
    on_ball = [e for e in t["events"] if e["player_id"]]
    assert on_ball and all(e["global_id"] in who for e in on_ball)
    assert all(e["global_id"] is None for e in t["events"] if not e["player_id"])
    for r in t["lineups"]:  # a per-match id and its global id belong to the same club and kit number
        p = who[r["global_id"]]
        assert (p["club_id"], p["kit_number"]) == (r["club_id"], r["kit_number"])
    for e in on_ball:
        assert who[e["global_id"]]["club_id"] == e["club_id"]


def test_player_season_is_what_the_profiles_show(tables):
    _small, _root, season, t = tables
    rows = {(r["global_id"], r["stat"]): r for r in t["player_season"]}
    for gid, p in season.profiles.items():
        for key in STATS:
            r = rows[(gid, key)]
            assert (r["appearances"], r["minutes"], r["count"], r["per90"], r["percentile"]) == (
                p["appearances"], p["minutes"], p["counts"][key], p["per90"][key], p["percentiles"].get(key))
    assert player_season_rows(season) == t["player_season"]


def test_matches_rows_give_the_minutes_the_profiles_count(tables):
    small, _root, season, t = tables
    played = {m["match_id"]: m["played_s"] for m in t["matches"]}
    for gid, p in season.profiles.items():
        if p["appearances"]:
            assert p["minutes"] == round(sum(played[m["match_id"]] for m in p["matches"]) / 60.0, 1)
    goals = {m["match_id"]: m["home_goals"] + m["away_goals"] for m in t["matches"]}
    for mid, n in goals.items():
        assert n == sum(1 for e in t["events"] if e["match_id"] == mid and e["event_type"] == "goal")


def test_uploads_table_reads_the_store(small, tables, tmp_path):
    _small, root, _season, _t = tables
    fx = small["fixtures"][0]
    store = LocalStore(tmp_path / "player")
    header = next(iter_jsonl(materialise(small, fx, root) / "events.jsonl"))
    me = next(p for p in header["players"] if p["starter"] and p["position"] == "FW")
    done = UploadRecord(upload_id="up_done000001", global_id=me["global_player_id"], club_id=fx["home"],
                        opponent_club_id=fx["away"], side="home", kit_number=me["kit_number"], status="done",
                        match_id=match_id_for("up_done000001"), stages=[{"role": "shots"}, {"role": "identity"}])
    queued = UploadRecord(upload_id="up_wait000002", global_id="pl_ash_10", club_id=fx["home"], opponent_club_id=fx["away"],
                          side="home", kit_number=10)
    store.put_record(done)
    store.put_record(queued)
    store.put_match(done.match_id, root / fx["match_id"])
    rows = {r["upload_id"]: r for r in upload_rows(store)}
    assert set(rows) == {"up_done000001", "up_wait000002"}
    assert all(set(r) == set(SCHEMAS["uploads"]) for r in rows.values())
    d, q = rows["up_done000001"], rows["up_wait000002"]
    assert d["status"] == "done" and d["stages"] == 2 and d["minutes"] > 29
    stream = list(iter_jsonl(root / fx["match_id"] / "events.jsonl"))
    for key in UPLOAD_STATS:
        assert d[key] == sum(1 for e in stream if e["type"] == "event" and e.get("player_id") == me["player_id"] and STATS[key][1](e))
    assert q["minutes"] is None and q["goals"] is None
    assert to_arrow("uploads", list(rows.values())).num_rows == 2


# ---------------------------------------------------------------------------- OneLake
def test_onelake_paths_tokens_and_overwrite():
    written = []
    lake = fb.OneLake("ws-1", "lh-1", tokens={fb.STORAGE_SCOPE: "st"}.__getitem__,
                      writer=lambda uri, data, opts: written.append((uri, data, opts)))
    lake.write("events", "rows")
    uri, data, opts = written[0]
    assert uri == "abfss://ws-1@onelake.dfs.fabric.microsoft.com/lh-1/Tables/events"
    assert opts == {"bearer_token": "st", "use_fabric_endpoint": "true"}


def test_a_repush_replaces_the_table(tmp_path):
    pytest.importorskip("deltalake")
    rows = [{"global_id": "pl_ash_09", "name": "A", "club_id": "cl_ashby", "kit_number": 9, "position": "FW", "starter": True}]
    uri = str(tmp_path / "players")
    fb._delta_write(uri, to_arrow("players", rows * 3), {})
    fb._delta_write(uri, to_arrow("players", rows), {})
    back = fb._delta_read(uri, {})
    assert back.num_rows == 1 and back.column_names == list(SCHEMAS["players"])


# ---------------------------------------------------------------------------- the notebook
def test_notebook_definition_points_at_the_lakehouse_and_covers_every_checked_stat():
    d = definition("ws-1", "lh-1", "regista_league")
    assert d["format"] == "ipynb" and d["parts"][0]["path"] == "notebook-content.ipynb"
    nb = json.loads(base64.b64decode(d["parts"][0]["payload"]))
    assert nb["metadata"]["dependencies"]["lakehouse"] == {
        "default_lakehouse": "lh-1", "default_lakehouse_name": "regista_league", "default_lakehouse_workspace_id": "ws-1"}
    code = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "abfss://ws-1@onelake.dfs.fabric.microsoft.com/lh-1/Tables" in code and "leaders_check" in code
    assert set(STAT_SQL) == set(fb.CHECK_STATS) and set(fb.CHECK_STATS) <= set(STATS)
    for stat in fb.CHECK_STATS:
        assert f"AS {stat}" in code
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), "cell", "exec")  # every cell is valid Python


# ---------------------------------------------------------------------------- the comparison
def row(gid, stat, count=1, per90=0.3, pct=50, minutes=300.0, apps=10):
    return {"global_id": gid, "stat": stat, "appearances": apps, "minutes": minutes, "count": count, "per90": per90,
            "percentile": pct}


def test_compare_agrees_within_rounding():
    regista = [row("pl_a", "goals"), row("pl_a", "shots", pct=None), row("pl_b", "goals", 0, 0.0, 0)]
    fabric = [row("pl_a", "goals", per90=0.305 - 1e-12, minutes=300.04), row("pl_a", "shots", pct=None),
              row("pl_b", "goals", 0, 0.0, 0), row("pl_a", "nutmegs")]  # a stat not checked is ignored
    r = fb.compare(regista, fabric, stats=["goals", "shots"])
    assert r["ok"] and (r["players"], r["checked"], r["matched"]) == (2, 3, 3)
    assert fb.report_lines(r)[-1] == "result: Fabric agrees with Regista"


def test_compare_reports_every_difference():
    regista = [row("pl_a", "goals"), row("pl_b", "goals"), row("pl_c", "goals")]
    fabric = [row("pl_a", "goals", count=2, per90=0.6), row("pl_b", "goals", pct=None), row("pl_d", "goals")]
    r = fb.compare(regista, fabric, stats=["goals"])
    assert not r["ok"] and r["matched"] == 0 and r["checked"] == 2
    assert {(d["global_id"], d["field"]) for d in r["differences"]} == {("pl_a", "count"), ("pl_a", "per90"), ("pl_b", "percentile")}
    assert r["only_regista"] == [("pl_c", "goals")] and r["only_fabric"] == [("pl_d", "goals")]
    lines = fb.report_lines(r)
    assert lines[-1] == "result: MISMATCH" and any("pl_a goals count: Regista 1, Fabric 2" in x for x in lines)


def test_the_season_compared_with_itself_matches(tables):
    _small, _root, _season, t = tables
    r = fb.compare(t["player_season"], [dict(x) for x in t["player_season"]])
    assert r["ok"] and r["players"] == 108 and r["checked"] == 108 * len(fb.CHECK_STATS)


def test_cli_needs_setup_first(monkeypatch, capsys, tmp_path):
    from regista.season import fabric as cli

    monkeypatch.delenv(fb.ENV_WORKSPACE, raising=False)
    monkeypatch.delenv(fb.ENV_LAKEHOUSE, raising=False)
    assert cli.main(["--env", str(tmp_path / "none.env"), "push"]) == 2
    assert "run setup first" in capsys.readouterr().err
