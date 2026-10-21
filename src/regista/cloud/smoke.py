"""Container smoke test: do the agent tools start inside the image, and did the image get the pages and the matches?
No Azure credentials and no network calls needed.

    python -m regista.cloud.smoke          # exit 0 when every check passes; prints one JSON line per check

CI runs this inside the freshly built image (.github/workflows/build-image.yml), because the Azure MCP Server is a
.NET binary whose runtime needs (ICU, OpenSSL) differ between a laptop and the slim Linux image. Listing tools is an
MCP handshake only: nothing is queried. The file checks catch a build that forgot package data (the Product and Studio
pages ship as ``regista/static``) or a ``.dockerignore`` that dropped a sample match.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from regista.cloud.config import CloudConfig


# What the two dashboards load, relative to regista/static, and the matches the image serves.
STATIC_FILES = ("product/index.html", "product/app.js", "product/timeline.js", "studio/index.html", "shared/regista.js",
                "shared/regista.css")
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
    for name, make, want in (("regista-mcp", lambda: regista, {"search_clips", "search_library"}),
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


def main() -> int:
    results = file_checks() + asyncio.run(checks())
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
