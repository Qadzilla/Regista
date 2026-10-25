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
- ``match_recap(match_dir, player_id)``         the match recap (rules engine): headline, paragraphs whose every sentence
                                                cites a clip or an event, and the recap reel; from a player's side if given
- ``search_players(position, club, q, sort, order, limit, min_minutes)``
                                                the Regista League's players filtered and ranked by any stat per 90
- ``get_profile(player)``                       one player's season (by global id or name), without the evidence lists
- ``compare_players(players)``                  two or three players side by side
- ``list_competitions(country, tier, age_group, gender)``
                                                the catalogue's 14 synthetic competitions (countries and levels below the
                                                professional line), their uploads, levels and careers
- ``search_catalogue_players(tier, age_group, gender, country, competition, position, sort, order, scope, limit, min_minutes)``
                                                players across the catalogue ranked by a Scout terminal metric, each
                                                percentile with the pool it came from (same level by default)
- ``get_catalogue_player(player, scope)``       one player across the catalogue: career, a row per competition with pools

The player tools read the league named by REGISTA_SEASON / REGISTA_SEASON_ROOT (default data/season/…); the catalogue
tools also read REGISTA_CATALOGUE / REGISTA_CATALOGUE_ROOT (default data/catalogue/…).

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
        "to produce a video, match_recap for a written recap of a match (or of one player's match). Paths are "
        "match directories containing events.jsonl (and clips.jsonl). For the "
        "synthetic Regista League's players across the season use search_players, get_profile and compare_players; for the "
        "catalogue of 14 synthetic competitions across countries and levels use list_competitions, "
        "search_catalogue_players and get_catalogue_player (percentiles within the same level by default)."
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
def search_library(query: str, top: int = 10) -> dict[str, Any]:
    """Search every indexed match at once through Azure AI Search, e.g. "every nutmeg by the home 9" or
    "most watchable replays". Returns ranked clips with match, player, title, tags, watchability, minute.
    Needs REGISTA_SEARCH_ENDPOINT; for one match's files use search_clips instead."""
    from regista.cloud.search import search_library as _search_library

    return _search_library(query, top=top)


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


@server.tool()
def match_recap(match_dir: str, player_id: str | None = None) -> dict[str, Any]:
    """A short written recap of one match: a headline and three or four short paragraphs (the score, the goals with
    scorer, assister and minute, the best chances and saves, who stood out), every sentence citing the clip or event it
    comes from, plus a reel of the recap's best clips. With player_id (a per-match id like t_home_09) it is told from
    that player's side: their part in the goals, their best moments, the replays they appear in."""
    from regista.recap import recap

    out = recap(match_dir, player_id=player_id or None)
    out.pop("trace", None)
    return out


# ---------------------------------------------------------------------------- the Regista League's players (Scout view)

def _season():
    import os

    from regista.season.profiles import load_season

    return load_season(os.environ.get("REGISTA_SEASON", "data/season/league.json"),
                       os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))


def _player_tool_docs() -> str:
    from regista.season.profiles import RATIOS
    from regista.season.scout import sort_keys

    ratios = list(RATIOS)
    return ("Search the synthetic Regista League's players (6 clubs, 10 rounds) and rank them. position: GK, DF, MF or FW "
            "(wingers and strikers are FW). club: name or short name. q: words of a player's name. sort: one of "
            + ", ".join(sort_keys()) + " (stats are per 90; " + ", ".join(ratios[:-1]) + " and " + ratios[-1] + " are ratios). "
            "order: desc (most first) or asc. min_minutes: leave empty for the default (the qualifying minutes when ranking: a third of a club's minutes). "
            "Returns each player's global_id, club, minutes, the sorted stat with its count and rank among the same position, "
            "and their headline rates per 90.")


@server.tool(description=_player_tool_docs())
def search_players(position: str | None = None, club: str | None = None, q: str | None = None, sort: str = "minutes",
                   order: str = "desc", limit: int = 10, min_minutes: float | None = None) -> dict[str, Any]:
    from regista.season.scout import search_players as _search_players

    return _search_players(_season(), position=position, club=club, q=q, sort=sort, order=order, limit=limit, min_minutes=min_minutes)


@server.tool()
def get_profile(player: str) -> dict[str, Any]:
    """One Regista League player's season, by global id (pl_ash_09) or full name: appearances, minutes, every stat per
    90 (or ratio) with its count, percentile and rank among the same position, best moments, matches, and the
    profile summary. Without the per-event evidence lists."""
    from regista.season.scout import get_profile as _get_profile

    return _get_profile(_season(), player)


@server.tool()
def compare_players(players: list[str]) -> dict[str, Any]:
    """Two or three Regista League players side by side (global ids or full names): every stat per 90 and ratio,
    with counts, percentiles and ranks among their positions."""
    from regista.season.scout import compare_players as _compare_players

    return _compare_players(_season(), players)


# ---------------------------------------------------------------------------- the catalogue (14 competitions)

def _catalogue():
    from regista.catalogue.metrics import load_catalogue_metrics

    return load_catalogue_metrics()   # REGISTA_CATALOGUE, REGISTA_CATALOGUE_ROOT, REGISTA_SEASON, REGISTA_SEASON_ROOT


@server.tool()
def list_competitions(country: str | None = None, tier: str | None = None, age_group: str | None = None,
                      gender: str | None = None) -> dict[str, Any]:
    """The catalogue's synthetic competitions (invented names; countries and levels are labels): each with country,
    region, tier (semi_pro, amateur, college, academy), age_group (senior, college, U20, U19, U18, U17), gender (men,
    women), teams, players, uploaded matches, cameras and uploaders; plus the levels (which competitions share a
    percentile pool) and the careers (players in two competitions). Filters are optional."""
    from regista.catalogue.tools import list_competitions as _list

    return _list(None, country=country, tier=tier, age_group=age_group, gender=gender)


@server.tool()
def search_catalogue_players(tier: str | None = None, age_group: str | None = None, gender: str | None = None,
                             country: str | None = None, competition: str | None = None, position: str | None = None,
                             sort: str = "minutes", order: str = "desc", scope: str = "level", limit: int = 10,
                             min_minutes: float | None = None) -> dict[str, Any]:
    """Players across the catalogue's competitions, one row per player and competition. Filters: tier, age_group, gender,
    country, competition (an id from list_competitions), position (GK, DF, MF, FW). sort: minutes or a Scout terminal
    metric key (npxg, np_goals, xa, sca, take_ons_won, progressive_passes, tackles_won, interceptions, pass_pct, ...).
    scope: level (default: peers of the same tier, age group, gender and position), competition, or all (every level of
    one gender; levels differ, so read each percentile against its pool). min_minutes: empty for each competition's
    qualifying minutes. Returns the sorted metric with its value, percentile, noisy flag and pool (size, small, reason)."""
    from regista.catalogue.tools import search_players

    return search_players(_catalogue(), tier=tier, age_group=age_group, gender=gender, country=country,
                          competition=competition, position=position, sort=sort, order=order, scope=scope, limit=limit,
                          min_minutes=min_minutes)


@server.tool()
def get_catalogue_player(player: str, scope: str = "level") -> dict[str, Any]:
    """One catalogue player by global id (pl_sot_09) or full name: public bio, the career (every competition, club and
    minutes), what adds up across competitions (no merged per-90), and per competition the position's core metrics with
    percentiles in ``scope`` and their pools. Without the per-event evidence lists."""
    from regista.catalogue.tools import get_player

    return get_player(_catalogue(), player, scope)


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
