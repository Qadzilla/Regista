"""Microsoft Fabric: the Regista League in a OneLake lakehouse, and a Fabric notebook that recomputes the leaders.

Three steps, each run by ``python -m regista.season.fabric``:

- ``setup``: find the signed-in person's own Fabric trial capacity, then create (or reuse) the workspace "Regista" on it
  and the lakehouse ``regista_league`` inside it.
- ``push``: write the season as Delta tables into the lakehouse's ``Tables/`` folder in OneLake
  (``regista.cloud.fabric_tables`` builds them; every push overwrites them).
- ``check``: create or update the notebook ``regista_leaders_check`` (``regista.cloud.fabric_notebook``), run it on
  demand through the Job Scheduler API, wait, read the table ``leaders_check`` it wrote, and compare it with Regista's
  own ``player_season`` (``compare``).

Keyless: ``DefaultAzureCredential`` (``az login`` on a laptop) with the Fabric API scope for REST calls, the Power BI
scope for the one call that says who administers a capacity, and the storage scope for OneLake.

The tenant is a university's and holds other people's trial capacities, which the Fabric API lists too. ``choose_capacity``
only ever picks a trial capacity whose admins include the signed-in user and on which that user holds the Admin right;
an existing "Regista" workspace is reused only when it already sits on that capacity. Nothing else is created or changed.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

Record = dict[str, Any]

FABRIC_API = "https://api.fabric.microsoft.com/v1"
POWERBI_API = "https://api.powerbi.com/v1.0/myorg"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
STORAGE_SCOPE = "https://storage.azure.com/.default"
ONELAKE_HOST = "onelake.dfs.fabric.microsoft.com"

WORKSPACE_NAME = "Regista"
LAKEHOUSE_NAME = "regista_league"
NOTEBOOK_NAME = "regista_leaders_check"
ENV_WORKSPACE = "REGISTA_FABRIC_WORKSPACE_ID"
ENV_LAKEHOUSE = "REGISTA_FABRIC_LAKEHOUSE_ID"


class FabricError(RuntimeError):
    pass


class NoOwnCapacity(FabricError):
    """The signed-in user administers no active Fabric trial capacity (the trial is not on yet)."""


# ---------------------------------------------------------------------------- choosing a capacity
def is_trial(sku: str | None) -> bool:
    """Fabric trial capacities have SKUs FTL2 ... FTL64 ("FT" for Fabric trial)."""
    return bool(sku) and sku.upper().startswith("FT")


def choose_capacity(fabric_caps: list[Record], powerbi_caps: list[Record], upn: str, *, capacity_id: str | None = None) -> Record:
    """The one capacity Regista may use: an active Fabric trial the signed-in user (``upn``) administers.

    ``fabric_caps`` is the Fabric API's list (id, displayName, sku, state), ``powerbi_caps`` the Power BI API's, which
    adds ``admins`` and ``capacityUserAccessRight``. A capacity counts as the user's only when both say so: the user is
    among its admins and holds the Admin right. Other people's trials (listed with the Assign right and no visible admins),
    paid or Premium Per User capacities, and paused ones never qualify. ``capacity_id`` narrows the choice to that capacity,
    and still only if it is the user's own. Raises ``NoOwnCapacity`` when nothing qualifies, ``FabricError`` when several
    do and none was named."""
    me = upn.casefold()
    admin_of = {c["id"].lower(): c for c in powerbi_caps
                if me in {a.casefold() for a in c.get("admins") or []} and c.get("capacityUserAccessRight") == "Admin"}
    own = [c for c in fabric_caps if c["id"].lower() in admin_of and is_trial(c.get("sku")) and c.get("state") == "Active"]
    if capacity_id:
        own = [c for c in own if c["id"].lower() == capacity_id.lower()]
        if not own:
            raise NoOwnCapacity(f"capacity {capacity_id} is not an active Fabric trial that {upn} administers")
    if not own:
        raise NoOwnCapacity(f"{upn} administers no active Fabric trial capacity: the trial is not on yet "
                            f"({len(fabric_caps)} capacities visible, none of them {upn}'s)")
    if len(own) > 1:
        names = ", ".join(f"{c['displayName']} ({c['id']})" for c in own)
        raise FabricError(f"{upn} administers several trial capacities; name one with --capacity: {names}")
    return own[0]


def upn_from_token(token: str) -> str:
    """The signed-in user's name from an Entra ID access token's claims (read, not verified: it only names whose
    capacity to look for; Fabric itself checks the token)."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as e:
        raise FabricError("could not read the access token's claims") from e
    upn = claims.get("upn") or claims.get("unique_name") or claims.get("preferred_username")
    if not upn:
        raise FabricError("the access token names no user (a service principal cannot own a Fabric trial)")
    return upn


# ---------------------------------------------------------------------------- HTTP
@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body) if self.body else None


class Transport(Protocol):  # tests pass a fake; urllib otherwise
    def __call__(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> Response: ...


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> Response:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() or b"")


class TokenSource:
    """Entra ID tokens per scope from ``DefaultAzureCredential`` (or any object with ``get_token``), refreshed early."""

    def __init__(self, credential: Any = None):
        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential()
        self.credential = credential
        self._tokens: dict[str, tuple[str, float]] = {}

    def __call__(self, scope: str) -> str:
        tok = self._tokens.get(scope)
        if tok is None or tok[1] - time.time() < 300:
            t = self.credential.get_token(scope)
            tok = (t.token, float(t.expires_on))
            self._tokens[scope] = tok
        return tok[0]


class FabricClient:
    """The slice of the Fabric REST API Regista uses: capacities, workspaces, lakehouses, notebooks and job runs.
    Long-running operations (202 + Location) are followed to their result; 429s wait as Retry-After says."""

    def __init__(self, tokens: Callable[[str], str] | None = None, transport: Transport | None = None,
                 sleep: Callable[[float], None] = time.sleep, poll_s: float = 5.0):
        self.tokens = tokens or TokenSource()
        self.transport = transport or urllib_transport
        self.sleep = sleep
        self.poll_s = poll_s

    # -- plumbing
    def _send(self, method: str, url: str, body: Any = None, scope: str = FABRIC_SCOPE) -> Response:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"Bearer {self.tokens(scope)}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        for _ in range(8):
            r = self.transport(method, url, headers, data)
            if r.status != 429:
                return r
            self.sleep(float(r.headers.get("retry-after", "10")))
        return r

    def call(self, method: str, path: str, body: Any = None, *, scope: str = FABRIC_SCOPE, ok: tuple[int, ...] = (200, 201)) -> Any:
        url = path if path.startswith("https://") else f"{FABRIC_API}{path}"
        r = self._send(method, url, body, scope)
        if r.status == 202 and r.headers.get("location") and "/operations/" in r.headers["location"]:
            return self._follow(r)
        if r.status not in (*ok, 202):
            raise FabricError(f"{method} {path} -> {r.status}: {r.body[:400].decode(errors='replace')}")
        return r.json()

    def _follow(self, r: Response, timeout_s: float = 600) -> Any:
        """A long-running operation: poll it until it succeeds, then read its result (if it has one)."""
        loc = r.headers["location"]
        deadline = time.time() + timeout_s
        while True:
            self.sleep(float(r.headers.get("retry-after", self.poll_s)))
            r = self._send("GET", loc)
            state = (r.json() or {}).get("status") if r.status == 200 else None
            if state == "Succeeded":
                res = self._send("GET", loc.rstrip("/") + "/result")
                return res.json() if res.status == 200 else None
            if state in ("Failed", "Cancelled") or r.status >= 400:
                raise FabricError(f"operation {loc} {state or r.status}: {r.body[:400].decode(errors='replace')}")
            if time.time() > deadline:
                raise FabricError(f"operation {loc} still {state} after {timeout_s:.0f} s")

    def _list(self, path: str) -> list[Record]:
        out, url = [], f"{FABRIC_API}{path}"
        while url:
            page = self.call("GET", url) or {}
            out += page.get("value", [])
            url = page.get("continuationUri")
        return out

    # -- who and where
    def me(self) -> str:
        return upn_from_token(self.tokens(FABRIC_SCOPE))

    def capacities(self) -> list[Record]:
        return self._list("/capacities")

    def capacity_admins(self) -> list[Record]:
        return (self.call("GET", f"{POWERBI_API}/capacities", scope=POWERBI_SCOPE) or {}).get("value", [])

    def own_capacity(self, capacity_id: str | None = None) -> tuple[str, Record]:
        upn = self.me()
        return upn, choose_capacity(self.capacities(), self.capacity_admins(), upn, capacity_id=capacity_id)

    # -- workspace and items
    def workspaces(self) -> list[Record]:
        return self._list("/workspaces")

    def create_workspace(self, name: str, capacity_id: str, description: str = "") -> Record:
        return self.call("POST", "/workspaces", {"displayName": name, "capacityId": capacity_id, "description": description})

    def lakehouses(self, ws: str) -> list[Record]:
        return self._list(f"/workspaces/{ws}/lakehouses")

    def create_lakehouse(self, ws: str, name: str, description: str = "") -> Record:
        return self.call("POST", f"/workspaces/{ws}/lakehouses", {"displayName": name, "description": description})

    def notebooks(self, ws: str) -> list[Record]:
        return self._list(f"/workspaces/{ws}/notebooks")

    def create_notebook(self, ws: str, name: str, definition: Record, description: str = "") -> Record | None:
        return self.call("POST", f"/workspaces/{ws}/notebooks",
                         {"displayName": name, "description": description, "definition": definition})

    def update_notebook(self, ws: str, notebook_id: str, definition: Record) -> None:
        self.call("POST", f"/workspaces/{ws}/notebooks/{notebook_id}/updateDefinition", {"definition": definition})

    def run_notebook(self, ws: str, notebook_id: str) -> str:
        """Start the notebook now (Job Scheduler, RunNotebook); returns the job instance's URL."""
        url = f"{FABRIC_API}/workspaces/{ws}/items/{notebook_id}/jobs/instances?jobType=RunNotebook"
        r = self._send("POST", url, {})
        if r.status != 202 or not r.headers.get("location"):
            raise FabricError(f"starting the notebook -> {r.status}: {r.body[:400].decode(errors='replace')}")
        return r.headers["location"]

    def wait_job(self, job_url: str, timeout_s: float = 1800, progress: Callable[[str], None] | None = None) -> Record:
        """Poll a job instance until it ends; returns its last state (``status`` Completed, Failed, Cancelled or Deduped)."""
        deadline, last = time.time() + timeout_s, None
        while True:
            job = self.call("GET", job_url) or {}
            status = job.get("status")
            if progress and status != last:
                progress(f"notebook run: {status}")
                last = status
            if status in ("Completed", "Failed", "Cancelled", "Deduped"):
                return job
            if time.time() > deadline:
                raise FabricError(f"notebook run still {status} after {timeout_s:.0f} s")
            self.sleep(self.poll_s * 2)


# ---------------------------------------------------------------------------- setup
@dataclass
class Setup:
    upn: str
    capacity: Record
    workspace: Record
    lakehouse: Record
    created: list[str] = field(default_factory=list)


def setup(client: FabricClient, *, capacity_id: str | None = None, workspace_name: str = WORKSPACE_NAME,
          lakehouse_name: str = LAKEHOUSE_NAME) -> Setup:
    """The user's own trial capacity, the workspace on it and the lakehouse in it, created when missing.

    An existing workspace with this name is reused only if it is already on that capacity; one anywhere else (someone
    else's, or on another capacity) is never moved or changed, and setup stops instead."""
    upn, cap = client.own_capacity(capacity_id)
    created = []
    same = [w for w in client.workspaces() if w.get("displayName") == workspace_name and w.get("type") == "Workspace"]
    ws = next((w for w in same if (w.get("capacityId") or "").lower() == cap["id"].lower()), None)
    if ws is None and same:
        raise FabricError(f"a workspace named {workspace_name!r} exists ({same[0]['id']}) but not on {upn}'s trial capacity "
                          f"{cap['id']}; not touching it. Rename it or pass another --workspace name.")
    if ws is None:
        ws = client.create_workspace(workspace_name, cap["id"], "Regista: the Regista League season and Player-view uploads.")
        created.append("workspace")
    lh = next((x for x in client.lakehouses(ws["id"]) if x.get("displayName") == lakehouse_name), None)
    if lh is None:
        lh = client.create_lakehouse(ws["id"], lakehouse_name, "Regista League tables (Delta), written by regista.season.fabric push.")
        if not lh or "id" not in lh:  # a long-running create can end without a body: look it up
            lh = next(x for x in client.lakehouses(ws["id"]) if x.get("displayName") == lakehouse_name)
        created.append("lakehouse")
    return Setup(upn, cap, ws, lh, created)


def set_env_lines(path: Path | str, values: dict[str, str]) -> Path:
    """Set ``KEY=value`` for each of ``values`` in a .env file: replace those keys' lines, append missing ones, and leave
    every other line exactly as it was."""
    path = Path(path)
    lines = path.read_text().splitlines(keepends=True) if path.exists() else []
    todo = dict(values)
    out = []
    for line in lines:
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in values:
            if m.group(1) in todo:
                out.append(f"{m.group(1)}={todo.pop(m.group(1))}\n")
            continue  # a duplicate line for a key already written
        out.append(line)
    if todo:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out += [f"{k}={v}\n" for k, v in todo.items()]
    path.write_text("".join(out))
    return path


# ---------------------------------------------------------------------------- OneLake
def table_uri(workspace_id: str, lakehouse_id: str, table: str) -> str:
    return f"abfss://{workspace_id}@{ONELAKE_HOST}/{lakehouse_id}/Tables/{table}"


class OneLake:
    """Delta tables in a lakehouse's ``Tables/`` folder, written and read with delta-rs (``deltalake``) and a bearer
    token for OneLake. ``writer``/``reader`` are swapped for fakes in tests."""

    def __init__(self, workspace_id: str, lakehouse_id: str, tokens: Callable[[str], str] | None = None,
                 writer: Callable[..., None] | None = None, reader: Callable[..., Any] | None = None):
        self.workspace_id, self.lakehouse_id = workspace_id, lakehouse_id
        self.tokens = tokens or TokenSource()
        self.writer = writer or _delta_write
        self.reader = reader or _delta_read

    def options(self) -> dict[str, str]:
        return {"bearer_token": self.tokens(STORAGE_SCOPE), "use_fabric_endpoint": "true"}

    def uri(self, table: str) -> str:
        return table_uri(self.workspace_id, self.lakehouse_id, table)

    def write(self, table: str, data: Any) -> None:
        """Overwrite the table (data and schema): a re-push replaces it, never appends."""
        self.writer(self.uri(table), data, self.options())

    def read(self, table: str) -> Any:
        return self.reader(self.uri(table), self.options())


def _delta_write(uri: str, data: Any, options: dict[str, str]) -> None:
    from deltalake import write_deltalake

    write_deltalake(uri, data, mode="overwrite", schema_mode="overwrite", storage_options=options)


def _delta_read(uri: str, options: dict[str, str]) -> Any:
    from deltalake import DeltaTable

    return DeltaTable(uri, storage_options=options).to_pyarrow_table()


# ---------------------------------------------------------------------------- the cross-check
CHECK_STATS = ["goals", "assists", "shots", "key_passes", "take_ons_won", "tackles_won", "interceptions"]
PER90_TOLERANCE = 0.005 + 1e-9    # both sides round to 2 decimals; Python and Spark may round a half differently
MINUTES_TOLERANCE = 0.05 + 1e-9   # Regista keeps minutes to 0.1


def compare(regista: list[Record], fabric: list[Record], stats: list[str] | None = None) -> Record:
    """Regista's ``player_season`` rows against the notebook's ``leaders_check`` rows, both one row per (player, stat)
    with ``global_id, stat, appearances, minutes, count, per90, percentile``.

    Counts, appearances and percentiles must be equal; minutes and per-90 rates may differ by rounding only. Every
    player and stat Regista has must be on the Fabric side and the other way round."""
    stats = stats or CHECK_STATS
    mine = {(r["global_id"], r["stat"]): r for r in regista if r["stat"] in stats}
    theirs = {(r["global_id"], r["stat"]): r for r in fabric if r["stat"] in stats}
    diffs: list[Record] = []
    matched = 0
    for key in sorted(mine.keys() & theirs.keys()):
        a, b = mine[key], theirs[key]
        bad = [f for f, ok in (
            ("appearances", int(a["appearances"]) == int(b["appearances"])),
            ("minutes", abs(float(a["minutes"]) - float(b["minutes"])) <= MINUTES_TOLERANCE),
            ("count", int(a["count"]) == int(b["count"])),
            ("per90", abs(float(a["per90"]) - float(b["per90"])) <= PER90_TOLERANCE),
            ("percentile", _same_pct(a.get("percentile"), b.get("percentile"))),
        ) if not ok]
        if bad:
            diffs += [{"global_id": key[0], "stat": key[1], "field": f, "regista": a.get(f), "fabric": b.get(f)} for f in bad]
        else:
            matched += 1
    only_regista = sorted(mine.keys() - theirs.keys())
    only_fabric = sorted(theirs.keys() - mine.keys())
    players = {k[0] for k in mine} | {k[0] for k in theirs}
    return {"players": len(players), "stats": list(stats), "checked": len(mine.keys() & theirs.keys()), "matched": matched,
            "differences": diffs, "only_regista": only_regista, "only_fabric": only_fabric,
            "ok": not diffs and not only_regista and not only_fabric}


def _same_pct(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return int(round(float(a))) == int(round(float(b)))


def report_lines(result: Record) -> list[str]:
    out = [f"checked {result['players']} players x {len(result['stats'])} stats ({', '.join(result['stats'])}): "
           f"{result['matched']} of {result['checked']} match"]
    if result["only_regista"]:
        out.append(f"{len(result['only_regista'])} rows only in Regista, e.g. {result['only_regista'][:3]}")
    if result["only_fabric"]:
        out.append(f"{len(result['only_fabric'])} rows only in Fabric, e.g. {result['only_fabric'][:3]}")
    for d in result["differences"][:20]:
        out.append(f"  {d['global_id']} {d['stat']} {d['field']}: Regista {d['regista']}, Fabric {d['fabric']}")
    if len(result["differences"]) > 20:
        out.append(f"  ... and {len(result['differences']) - 20} more")
    out.append("result: " + ("Fabric agrees with Regista" if result["ok"] else "MISMATCH"))
    return out
