"""Container smoke test: do the agent tools start inside the image, and did the image get the pages and the matches?
No Azure credentials and no network calls needed.

    python -m regista.cloud.smoke          # exit 0 when every check passes; prints one JSON line per check

CI runs this inside the freshly built image (.github/workflows/build-image.yml), because the Azure MCP Server is a
.NET binary whose runtime needs (ICU, OpenSSL) differ between a laptop and the slim Linux image. Listing tools is an
MCP handshake only: nothing is queried. The file checks catch a build that forgot package data (the Product and Studio
pages ship as ``regista/static``) or a ``.dockerignore`` that dropped a sample match. The season check compares the
league the image built with the committed pins, on the platform the live app runs on, and the catalogue check does
the same for the catalogue's uploaded matches (``regista.catalogue.pins``).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from regista.cloud.config import CloudConfig


# What the dashboards load (the Terminal included), relative to regista/static, and the matches the image serves.
STATIC_FILES = ("product/index.html", "product/app.js", "product/timeline.js", "product/icons/foundry.svg", "studio/index.html",
                "shared/regista.js", "shared/regista.css", "scout/index.html", "scout/scout.js", "scout/terminal.js",
                "scout/terminal.css", "scout/terminal-words.js", "scout/terminal-place.js")
SAMPLE_MATCHES = ("syn_0141", "syn_0142", "syn_0294", "vis_0201")
MATCH_FILES = ("events.jsonl", "clips.jsonl", "manifest.json")


def file_checks(static_root: Path | None = None, data_root: Path | None = None) -> list[dict]:
    """The packaged static files and the sample matches are where the app reads them (``REGISTA_DATA`` in the image)."""
    if static_root is None:
        import regista

        static_root = Path(regista.__file__).resolve().parent / "static"
    data_root = data_root or Path(os.environ.get("REGISTA_DATA", "data/synthetic/sample"))
    missing_static = [f for f in STATIC_FILES if not (static_root / f).is_file()]
    missing_data = [f"{m}/{f}" for m in SAMPLE_MATCHES for f in MATCH_FILES if not (data_root / m / f).is_file()]
    return [{"check": "static-files", "ok": not missing_static, "root": str(static_root), "missing": missing_static},
            {"check": "sample-matches", "ok": not missing_data, "root": str(data_root), "missing": missing_data}]


async def _list_tools(tool) -> list[str]:
    async with tool:
        return [f.name for f in tool.functions]


async def checks() -> list[dict]:
    from agent_framework import MCPStdioTool

    from regista.cloud.foundry import azure_mcp_tool, child_env

    out = []
    # Placeholder endpoints switch the namespaces on; the handshake never contacts them.
    cfg = CloudConfig(cosmos_endpoint="https://smoke.documents.azure.com:443/", search_endpoint="https://smoke.search.windows.net")
    regista = MCPStdioTool(name="regista", command=sys.executable, args=["-m", "regista.mcp_server"], env=child_env())
    for name, make, want in (("regista-mcp", lambda: regista, {"search_clips", "search_library", "list_competitions",
                                                                  "search_catalogue_players", "get_catalogue_player"}),
                             ("azure-mcp-public", lambda: azure_mcp_tool(cfg, ("search",)), {"search_index_query"}),
                             ("azure-mcp-cli", lambda: azure_mcp_tool(cfg), {"search_index_query", "cosmos_database_container_item_query"})):
        try:
            tool = make()
            if tool is None:
                raise RuntimeError(f"not available (azmcp on PATH: {shutil.which('azmcp')})")
            names = await asyncio.wait_for(_list_tools(tool), 120)
            missing = sorted(want - set(names))
            out.append({"check": name, "ok": not missing, "tools": sorted(names), "missing": missing})
        except Exception as exc:  # noqa: BLE001 - reported, then the exit code says it failed
            out.append({"check": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return out


def vision_checks() -> list[dict]:
    """The Container Apps Job runs the vision workflow from this same image: its libraries must import."""
    missing = []
    for mod in ("cv2", "sklearn", "scipy", "joblib", "azure.storage.blob", "azure.storage.queue"):
        try:
            __import__(mod)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            missing.append(f"{mod}: {type(exc).__name__}: {exc}")
    return [{"check": "vision-libraries", "ok": not missing, "missing": missing}]


def season_checks(league_path: Path | None = None, root: Path | None = None) -> list[dict]:
    """The Regista League the Dockerfile built inside the image is the committed season, bit for bit
    (``regista.season.pins``): league matches are generated on the server's platform, and libm's last bits once made
    Linux generate different matches than the Mac they were checked on (docs/scout-terminal/build/determinism.md)."""
    from regista.season.league import load_league
    from regista.season.pins import drift

    league_path = league_path or Path(os.environ.get("REGISTA_SEASON", "data/season/league.json"))
    root = root or Path(os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    try:
        moved = drift(load_league(league_path), root)
    except Exception as exc:  # noqa: BLE001 - reported, then the exit code says it failed
        return [{"check": "season-pins", "ok": False, "error": f"{type(exc).__name__}: {exc}"}]
    return [{"check": "season-pins", "ok": not moved, "root": str(root), "differs": moved}]


def catalogue_checks(index: Path | None = None, root: Path | None = None) -> list[dict]:
    """The catalogue's matches the Dockerfile built inside the image are the committed ones, bit for bit
    (``regista.catalogue.pins``), like the league's."""
    from regista.catalogue import store
    from regista.catalogue.pins import drift

    index = index or Path(os.environ.get("REGISTA_CATALOGUE", "data/catalogue/catalogue.json"))
    root = root or Path(os.environ.get("REGISTA_CATALOGUE_ROOT", "data/catalogue/matches"))
    try:
        moved = drift(store.new_competitions(index), root)
    except Exception as exc:  # noqa: BLE001 - reported, then the exit code says it failed
        return [{"check": "catalogue-pins", "ok": False, "error": f"{type(exc).__name__}: {exc}"}]
    return [{"check": "catalogue-pins", "ok": not moved, "root": str(root), "differs": moved}]


def catalogue_reliability_checks(index: Path | None = None) -> list[dict]:
    """The per-level reliability shipped with the image was measured for this catalogue and generator, so the engine
    marks noisy numbers (``regista.catalogue.reliability``); a stale or missing table would mark none."""
    from regista.catalogue import reliability as rel
    from regista.catalogue import store
    from regista.catalogue.taxonomy import ENGLAND_ID
    from regista.season.league import load_league

    index = index or Path(os.environ.get("REGISTA_CATALOGUE", "data/catalogue/catalogue.json"))
    try:
        league = load_league(store.competition_path(store.entry(ENGLAND_ID, index), index))
        data = rel.load(league, store.new_competitions(index), index.with_name(rel.FILE_NAME))
    except Exception as exc:  # noqa: BLE001 - reported, then the exit code says it failed
        return [{"check": "catalogue-reliability", "ok": False, "error": f"{type(exc).__name__}: {exc}"}]
    return [{"check": "catalogue-reliability", "ok": "stale" not in data, "levels": sorted(data.get("levels", {})),
             "stale": data.get("stale")}]


def catalogue_realism_checks(index: Path | None = None) -> list[dict]:
    """The realism verdicts shipped with the image were measured for this catalogue and generator, so a served check says
    pass, fail or not separated (``regista.catalogue.realism``); a stale or missing file would serve "not measured"."""
    from regista.catalogue import realism as rea
    from regista.catalogue import store
    from regista.catalogue.taxonomy import ENGLAND_ID
    from regista.season.league import load_league

    index = index or Path(os.environ.get("REGISTA_CATALOGUE", "data/catalogue/catalogue.json"))
    try:
        league = load_league(store.competition_path(store.entry(ENGLAND_ID, index), index))
        data = rea.load(index.with_name(rea.FILE_NAME), league, store.new_competitions(index))
    except Exception as exc:  # noqa: BLE001 - reported, then the exit code says it failed
        return [{"check": "catalogue-realism", "ok": False, "error": f"{type(exc).__name__}: {exc}"}]
    checks = data.get("bands", []) + data.get("orders", [])
    return [{"check": "catalogue-realism", "ok": "stale" not in data and bool(checks)
             and all(c.get("verdict") for c in checks), "checks": len(checks), "stale": data.get("stale")}]


def main() -> int:
    results = (file_checks() + vision_checks() + season_checks() + catalogue_checks() + catalogue_reliability_checks()
               + catalogue_realism_checks() + asyncio.run(checks()))
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
