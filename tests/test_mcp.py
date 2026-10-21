"""The MCP server must expose the Librarian and the clip rule to any MCP host, for real, over stdio."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from regista.clips import derive_clips
from regista.synth import generate

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def match_dir(tmp_path_factory):
    r = generate(seed=294, minutes=3.0, track_hz=1.0)
    d = tmp_path_factory.mktemp("mcp") / r.match["match_id"]
    d.mkdir()
    (d / "events.jsonl").write_text("\n".join(json.dumps(x) for x in r.stream) + "\n")
    (d / "tracks.jsonl").write_text("\n".join(json.dumps(x) for x in r.tracks) + "\n")
    clips, labels = derive_clips(r.stream, "t_home_09")
    (d / "clips.jsonl").write_text("\n".join(json.dumps(x) for x in clips + labels) + "\n")
    (d / "manifest.json").write_text(json.dumps({"score": r.score, "clips_for": "t_home_09", "video_duration_s": r.match["video"]["duration_s"]}))
    return d


async def _with_client(fn):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=["-m", "regista.mcp_server"], cwd=str(REPO))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _run(fn):
    return asyncio.run(_with_client(fn))


def _payload(result):
    """FastMCP returns structured content when available, else JSON text."""
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    return json.loads(text)


def test_tools_are_listed():
    async def go(session):
        tools = await session.list_tools()
        return {t.name: t.description for t in tools.tools}

    tools = _run(go)
    assert {"search_clips", "derive_clips", "validate_stream", "render_clip", "list_matches"} <= set(tools)
    assert "nutmeg" in tools["search_clips"].lower() or "natural-language" in tools["search_clips"].lower()


def test_search_clips_over_mcp(match_dir):
    surname = next(p["name"].split()[-1] for p in json.loads((match_dir / "events.jsonl").read_text().splitlines()[0])["players"] if p["player_id"] == "t_home_09")

    async def go(session):
        res = await session.call_tool("search_clips", {"match_dir": str(match_dir), "query": f"find me {surname} doing a nutmeg"})
        return _payload(res)

    out = _run(go)
    assert out["parsed"]["player_id"] == "t_home_09"
    assert out["results"] and all("nutmeg" in r["tags"] for r in out["results"])
    assert all("Cut because" in r["explanation"] for r in out["results"])


def test_derive_and_validate_over_mcp(match_dir):
    async def go(session):
        derived = _payload(await session.call_tool("derive_clips", {"match_dir": str(match_dir), "player_id": "t_home_09"}))
        valid = _payload(await session.call_tool("validate_stream", {"path": str(match_dir)}))
        matches = _payload(await session.call_tool("list_matches", {"root": str(match_dir.parent)}))
        return derived, valid, matches

    derived, valid, matches = _run(go)
    assert derived["count"] == len(derived["clips"]) > 0
    assert valid["valid"] is True and set(valid["problem_counts"]) == {"events.jsonl", "tracks.jsonl", "clips.jsonl"}
    assert matches and matches[0]["match_id"] == match_dir.name
