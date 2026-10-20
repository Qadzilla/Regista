"""Regista as an MCP server: the intelligence layer's tools for any MCP host.

    python -m regista.mcp_server                 # stdio transport (what Copilot Agent Mode, Claude, and
                                                 # Microsoft Agent Framework agents speak)
    python -m regista.mcp_server --list-tools    # print the tool catalogue and exit

Tools
-----
- ``search_clips(match_dir, query, limit)``     the Librarian: plain-English clip search with an explanation
- ``derive_clips(match_dir, player_id)``        the clip rule: every on-ball main-view moment plus every replay,
                                                highlight, and closeup appearance for one player
- ``validate_stream(path)``                     schema-validate a match directory or a single JSONL file
- ``render_clip(match_dir, clip_id, out_dir)``  cut one clip to MP4 with its title card
- ``list_matches(root)``                        the match directories available under a folder

Everything runs locally and deterministically; no model, no keys. A Foundry-hosted agent
calls these tools and reasons about the answers; it never re-implements them. The server
only touches files inside the directories it is given.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from regista.clips import derive_clips as _derive_clips
from regista.librarian import search_clips as _search_clips
from regista.schema import iter_jsonl, validate_jsonl, validate_match_dir

server = FastMCP(
    "regista",
    instructions=(
        "Regista finds every on-ball moment, replay, and highlight of a football player in a match and "
        "labels them. Use search_clips for natural-language questions like 'find me Castellanos doing a "
        "nutmeg'. Use derive_clips to list a player's clips, validate_stream to check data, render_clip "
        "to produce a video. Paths are match directories containing events.jsonl (and clips.jsonl)."
    ),
)


@server.tool()
def search_clips(match_dir: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Search a match's labelled clips with a natural-language query. Returns how the query was parsed,
    ranked results with titles, times, tags, watchability, and a plain-English explanation per clip."""
    return _search_clips(match_dir, query, limit)


@server.tool()
def derive_clips(match_dir: str, player_id: str) -> dict[str, Any]:
    """Apply the clip rule for one player: on-ball moments in the main camera plus every replay, highlight,
    and closeup they appear in. Returns clips and labels (same records as clips.jsonl)."""
    stream = list(iter_jsonl(Path(match_dir) / "events.jsonl"))
    clips, labels = _derive_clips(stream, player_id)
    return {"player_id": player_id, "clips": clips, "labels": labels, "count": len(clips)}


@server.tool()
def validate_stream(path: str) -> dict[str, Any]:
    """Validate a match directory (events.jsonl, tracks.jsonl, clips.jsonl) or one JSONL file against the
    Regista schemas. Returns per-file problem lists; empty lists mean valid."""
    p = Path(path)
    if p.is_dir():
        problems = validate_match_dir(p)
    else:
        problems = {p.name: validate_jsonl(p)}
    return {"path": str(p), "valid": not any(problems.values()), "problems": {k: v[:50] for k, v in problems.items()},
            "problem_counts": {k: len(v) for k, v in problems.items()}}


@server.tool()
def render_clip(match_dir: str, clip_id: str, out_dir: str, fps: float = 25.0, size: str = "1280x720") -> dict[str, Any]:
    """Render one clip (by clip id from derive_clips or search_clips) to an MP4 with its title card.
    Returns the file path and frame count."""
    from regista.render.clips import load_clips, render_clip as _render_clip
    from regista.render.draw import Style
    from regista.render.scene import Scene

    md = Path(match_dir)
    scene = Scene.load(md)
    w, h = (int(v) for v in size.lower().split("x"))
    player_id = None
    for r in iter_jsonl(md / "clips.jsonl") if (md / "clips.jsonl").exists() else []:
        if r["type"] == "clip" and r["id"] == clip_id:
            player_id = r["player_id"]
            break
    if player_id is None:
        raise ValueError(f"{clip_id} not found in {md / 'clips.jsonl'}; run derive_clips and write clips.jsonl first")
    clips, labels = load_clips(md, scene, player_id)
    clip = next(c for c in clips if c["id"] == clip_id)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return _render_clip(scene, clip, labels.get(clip_id), out / f"{clip_id}.mp4", fps, Style(w, h))


@server.tool()
def list_matches(root: str = "data/synthetic/sample") -> list[dict[str, Any]]:
    """List match directories under ``root`` with their manifest summaries."""
    out = []
    for d in sorted(Path(root).glob("*/")):
        if (d / "events.jsonl").exists():
            manifest = {}
            if (d / "manifest.json").exists():
                manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
            out.append({"match_dir": str(d), "match_id": d.name, "score": manifest.get("score"), "clips_for": manifest.get("clips_for"),
                        "video_duration_s": manifest.get("video_duration_s")})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Regista MCP server (stdio).")
    parser.add_argument("--list-tools", action="store_true")
    args = parser.parse_args(argv)
    if args.list_tools:
        import asyncio

        tools = asyncio.run(server.list_tools())
        for t in tools:
            print(f"{t.name}: {t.description.splitlines()[0] if t.description else ''}")
        return 0
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
