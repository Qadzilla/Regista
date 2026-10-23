"""python -m regista.season.fabric: the Regista League in Microsoft Fabric, cross-checked by a Fabric notebook.

    python -m regista.season.fabric setup [--capacity ID] [--env .env]   # own trial capacity -> workspace + lakehouse
    python -m regista.season.fabric push                                  # season + uploads -> Delta tables in OneLake
    python -m regista.season.fabric check [--no-run] [--json OUT]         # notebook recomputes the leaders; compare

``setup`` writes REGISTA_FABRIC_WORKSPACE_ID and REGISTA_FABRIC_LAKEHOUSE_ID into the .env file (only those lines);
``push`` and ``check`` read them. Signs in with ``DefaultAzureCredential`` (``az login``). See regista.cloud.fabric.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from regista.cloud import fabric as fb

LEAGUE = "data/season/league.json"
ROOT = "data/season/matches"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.season.fabric", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env", default=None, help="the .env file to read and to write the ids into (default: $REGISTA_DOTENV or .env)")
    ap.add_argument("--league", default=LEAGUE)
    ap.add_argument("--root", default=ROOT, help="where the league's match folders are (generated when missing)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="find your own trial capacity; create or reuse the workspace and the lakehouse")
    s.add_argument("--capacity", default=None, help="a capacity id (still only one of your own trials)")
    s.add_argument("--workspace", default=fb.WORKSPACE_NAME)
    s.add_argument("--lakehouse", default=fb.LAKEHOUSE_NAME)
    p = sub.add_parser("push", help="write the season and the uploads as Delta tables (overwrites them)")
    p.add_argument("--no-uploads", action="store_true", help="skip the Player-view uploads table")
    c = sub.add_parser("check", help="run the Fabric notebook and compare its leaders with Regista's")
    c.add_argument("--no-run", action="store_true", help="compare the leaders_check already in OneLake")
    c.add_argument("--timeout", type=float, default=1800)
    c.add_argument("--json", default=None, help="also write the full comparison here")
    args = ap.parse_args(argv)

    env = Path(args.env or os.environ.get("REGISTA_DOTENV", ".env") or ".env")
    from regista.cloud.config import load_dotenv

    load_dotenv(env)
    try:
        if args.cmd == "setup":
            return _setup(args, env)
        ws, lh = os.environ.get(fb.ENV_WORKSPACE), os.environ.get(fb.ENV_LAKEHOUSE)
        if not (ws and lh):
            print(f"{fb.ENV_WORKSPACE} and {fb.ENV_LAKEHOUSE} are not set: run setup first", file=sys.stderr)
            return 2
        return _push(args, ws, lh) if args.cmd == "push" else _check(args, ws, lh)
    except fb.FabricError as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2


def _setup(args, env: Path) -> int:
    client = fb.FabricClient()
    s = fb.setup(client, capacity_id=args.capacity, workspace_name=args.workspace, lakehouse_name=args.lakehouse)
    print(f"signed in as {s.upn}")
    print(f"capacity   {s.capacity['displayName']} ({s.capacity['id']}, {s.capacity['sku']}, {s.capacity.get('region')})")
    print(f"workspace  {s.workspace['displayName']} {s.workspace['id']}" + (" (created)" if "workspace" in s.created else " (reused)"))
    print(f"lakehouse  {s.lakehouse['displayName']} {s.lakehouse['id']}" + (" (created)" if "lakehouse" in s.created else " (reused)"))
    fb.set_env_lines(env, {fb.ENV_WORKSPACE: s.workspace["id"], fb.ENV_LAKEHOUSE: s.lakehouse["id"]})
    print(f"wrote {fb.ENV_WORKSPACE} and {fb.ENV_LAKEHOUSE} to {env}")
    return 0


def _push(args, ws: str, lh: str) -> int:
    from regista.cloud.fabric_tables import season_tables, to_arrow, upload_rows
    from regista.season.league import load_league

    t0 = time.time()
    tables = season_tables(load_league(args.league), args.root)
    if not args.no_uploads:
        from regista.player.store import store_from_env

        store = store_from_env()
        tables["uploads"] = upload_rows(store)
        print(f"uploads from the {store.kind} store: {len(tables['uploads'])}")
    lake = fb.OneLake(ws, lh)
    for name, rows in tables.items():
        t = time.time()
        lake.write(name, to_arrow(name, rows))
        print(f"  {name:14} {len(rows):>7} rows  ({time.time() - t:.1f} s)")
    print(f"pushed {len(tables)} tables to {fb.table_uri(ws, lh, '')} in {time.time() - t0:.1f} s")
    return 0


def _check(args, ws: str, lh: str) -> int:
    from regista.cloud.fabric_notebook import definition

    client = fb.FabricClient()
    lake = fb.OneLake(ws, lh, tokens=client.tokens)
    if not args.no_run:
        lakehouse_name = next((x["displayName"] for x in client.lakehouses(ws) if x["id"] == lh), fb.LAKEHOUSE_NAME)
        nb_def = definition(ws, lh, lakehouse_name)
        nb = next((n for n in client.notebooks(ws) if n.get("displayName") == fb.NOTEBOOK_NAME), None)
        if nb:
            client.update_notebook(ws, nb["id"], nb_def)
            print(f"notebook {fb.NOTEBOOK_NAME} {nb['id']} (updated)")
        else:
            client.create_notebook(ws, fb.NOTEBOOK_NAME, nb_def, "Recomputes the Regista League leaders in Spark SQL.")
            nb = next(n for n in client.notebooks(ws) if n.get("displayName") == fb.NOTEBOOK_NAME)
            print(f"notebook {fb.NOTEBOOK_NAME} {nb['id']} (created)")
        t = time.time()
        job = client.wait_job(client.run_notebook(ws, nb["id"]), timeout_s=args.timeout, progress=print)
        print(f"notebook run {job.get('id')} {job.get('status')} in {time.time() - t:.0f} s")
        if job.get("status") != "Completed":
            print(json.dumps(job.get("failureReason"), indent=1), file=sys.stderr)
            return 1
    regista = lake.read("player_season").to_pylist()
    fabric = lake.read("leaders_check").to_pylist()
    result = fb.compare(regista, fabric)
    for line in fb.report_lines(result):
        print(line)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, default=str) + "\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
