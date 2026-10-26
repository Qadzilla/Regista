"""The Regista League as tables for a Fabric lakehouse: one list of rows per table, with a fixed column schema.

    clubs           one row per club
    players         one row per squad member, keyed on the global player id (pl_ash_09)
    matches         one row per fixture: round, date, clubs, score, seed, and played_s (the periods' length in seconds)
    lineups         one row per player per match: per-match id (t_home_09), global id, club, starter
    events          every event of every league match, with the global id of its player (and of the related player)
    clips, labels   every starter's clips and their labels, with global ids
    player_season   Regista's own profile numbers (``regista.season.profiles``), one row per (player, stat): appearances,
                    minutes, count, per-90 rate, percentile within the position. League fixtures only.
    uploads         Player-view uploads from the store (``regista.player.store``): who, which clubs, status, and for a
                    finished one the uploader's minutes and headline counts in that match
    catalogue_*     the catalogue (14 competitions, 90 matches) and Regista's numbers for its check: built by
                    ``regista.cloud.fabric_catalogue`` with their schemas here (``CATALOGUE_TABLES``), under their own
                    names so the league's tables above stay exactly as they are

Rows are plain dicts so tests can read them; ``to_arrow`` turns a table into a pyarrow Table with its schema.
"""

from __future__ import annotations

import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from regista.schema import iter_jsonl
from regista.season.build import materialise
from regista.season.league import people
from regista.season.playing_time import played_seconds
from regista.season.profiles import STATS, Season

Record = dict[str, Any]

# column -> type: string, int, double, bool, date, timestamp, list<string>
SCHEMAS: dict[str, dict[str, str]] = {
    "clubs": {"club_id": "string", "name": "string", "short_name": "string", "ground": "string",
              "kit_primary": "string", "kit_secondary": "string", "kit_gk": "string"},
    "players": {"global_id": "string", "name": "string", "club_id": "string", "kit_number": "int", "position": "string",
                "starter": "bool"},
    "matches": {"match_id": "string", "round": "int", "date": "date", "home_club_id": "string", "away_club_id": "string",
                "home_goals": "int", "away_goals": "int", "seed": "int", "periods": "int", "played_s": "double",
                "video_duration_s": "double", "title": "string"},
    "lineups": {"match_id": "string", "player_id": "string", "global_id": "string", "team_id": "string", "club_id": "string",
                "kit_number": "int", "position": "string", "starter": "bool", "played_s": "double"},
    "events": {"match_id": "string", "event_id": "string", "t": "double", "period": "int", "minute": "int", "second": "int",
               "event_type": "string", "outcome": "string", "player_id": "string", "global_id": "string", "team_id": "string",
               "club_id": "string", "related_player_id": "string", "related_global_id": "string", "possession_id": "string",
               "segment_id": "string", "under_pressure": "bool", "x": "double", "y": "double", "end_x": "double",
               "end_y": "double", "body_part": "string", "qualifiers": "list<string>", "confidence": "double"},
    "clips": {"match_id": "string", "clip_id": "string", "player_id": "string", "global_id": "string", "t": "double",
              "t_end": "double", "keyframe_t": "double", "reason": "string", "event_ids": "list<string>",
              "segment_ids": "list<string>"},
    "labels": {"match_id": "string", "label_id": "string", "clip_id": "string", "player_id": "string", "global_id": "string",
               "title": "string", "summary": "string", "explanation": "string", "tags": "list<string>",
               "watchability": "double", "prior_watchability": "double", "model": "string"},
    "player_season": {"global_id": "string", "name": "string", "club_id": "string", "position": "string",
                      "appearances": "int", "minutes": "double", "stat": "string", "label": "string", "count": "int",
                      "per90": "double", "percentile": "int"},
    "uploads": {"upload_id": "string", "global_id": "string", "club_id": "string", "opponent_club_id": "string",
                "side": "string", "kit_number": "int", "status": "string", "source": "string", "match_id": "string",
                "created_at": "timestamp", "updated_at": "timestamp", "stages": "int", "error": "string",
                "minutes": "double", "goals": "int", "assists": "int", "shots": "int", "key_passes": "int",
                "take_ons_won": "int", "tackles_won": "int", "interceptions": "int"},
    # ---- the catalogue (14 competitions, 90 matches), built by regista.cloud.fabric_catalogue; distinct names, so the
    # league's tables above and their check stay exactly as they are. Public facts only: never the hidden ratings, the
    # level scales, the generator's execution or the seeds.
    "catalogue_competitions": {"competition_id": "string", "code": "string", "name": "string", "country": "string",
                               "region": "string", "tier": "string", "tier_label": "string", "age_group": "string",
                               "age_group_label": "string", "gender": "string", "gender_label": "string", "level": "string",
                               "level_label": "string", "format": "string", "season": "string", "eligibility": "string",
                               "teams": "int", "uploaded_matches": "int", "coverage": "string", "source": "string",
                               "as_of": "date"},
    "catalogue_clubs": {"competition_id": "string", "club_id": "string", "name": "string", "short_name": "string",
                        "city": "string", "ground": "string", "kit_primary": "string", "kit_secondary": "string",
                        "kit_gk": "string"},
    "catalogue_players": {"competition_id": "string", "global_id": "string", "name": "string", "club_id": "string",
                          "kit_number": "int", "position": "string", "role": "string", "starter": "bool", "age": "int",
                          "date_of_birth": "date", "height_cm": "int", "preferred_foot": "string", "nationality": "string",
                          "career": "bool"},
    "catalogue_matches": {"match_id": "string", "competition_id": "string", "round": "int", "date": "date",
                          "home_club_id": "string", "away_club_id": "string", "home_goals": "int", "away_goals": "int",
                          "periods": "int", "played_s": "double", "video_duration_s": "double", "title": "string",
                          "uploader_type": "string", "uploader_club_id": "string", "uploader_global_id": "string",
                          "camera": "string"},
    "catalogue_lineups": {"match_id": "string", "competition_id": "string", "player_id": "string", "global_id": "string",
                          "team_id": "string", "club_id": "string", "kit_number": "int", "position": "string",
                          "starter": "bool", "played_s": "double"},
    "catalogue_events": {"match_id": "string", "competition_id": "string", "seq": "int", "event_id": "string", "t": "double",
                         "period": "int", "minute": "int", "second": "int", "event_type": "string", "outcome": "string",
                         "player_id": "string", "global_id": "string", "team_id": "string", "club_id": "string",
                         "related_player_id": "string", "related_global_id": "string", "possession_id": "string",
                         "segment_id": "string", "under_pressure": "bool", "x": "double", "y": "double", "end_x": "double",
                         "end_y": "double", "body_part": "string", "qualifiers": "list<string>", "confidence": "double"},
    "catalogue_possessions": {"match_id": "string", "competition_id": "string", "seq": "int", "possession_id": "string",
                              "t": "double", "t_end": "double", "player_id": "string", "global_id": "string",
                              "team_id": "string", "club_id": "string", "gained_by": "string", "lost_by": "string",
                              "touches": "int", "under_pressure": "bool"},
    "catalogue_player_season": {"competition_id": "string", "global_id": "string", "name": "string", "club_id": "string",
                                "position": "string", "tier": "string", "age_group": "string", "gender": "string",
                                "appearances": "int", "minutes": "double", "qualifying_minutes": "double", "stat": "string",
                                "label": "string", "count": "int", "per90": "double", "qualified": "bool",
                                "percentile": "int", "pool_size": "int", "pool_words": "string", "noisy": "bool"},
}
LEAGUE_TABLES = ("clubs", "players", "matches", "lineups", "events", "clips", "labels", "player_season", "uploads")
CATALOGUE_TABLES = tuple(k for k in SCHEMAS if k.startswith("catalogue_"))
UPLOAD_STATS = ["goals", "assists", "shots", "key_passes", "take_ons_won", "tackles_won", "interceptions"]


def season_tables(league: Record, root: Path | str, season: Season | None = None) -> dict[str, list[Record]]:
    """Every league table: the league definition, each fixture's match folder (generated when missing) and the season's
    profiles (built here from the league fixtures alone unless ``season`` is given)."""
    root = Path(root)
    who = people(league)
    tables: dict[str, list[Record]] = {k: [] for k in ("clubs", "players", "matches", "lineups", "events", "clips", "labels")}
    for c in league["clubs"]:
        tables["clubs"].append({"club_id": c["club_id"], "name": c["name"], "short_name": c["short_name"], "ground": c.get("ground"),
                                "kit_primary": c["kit"]["primary"], "kit_secondary": c["kit"]["secondary"], "kit_gk": c["kit"]["gk"]})
        for p in c["squad"]:
            tables["players"].append({"global_id": p["global_id"], "name": p["name"], "club_id": c["club_id"],
                                      "kit_number": p["kit_number"], "position": p["position"], "starter": p["starter"]})
    for fx in league["fixtures"]:
        d = materialise(league, fx, root)
        _match_rows(tables, d, fx, who)
    season = season or Season.build(league, root)
    tables["player_season"] = player_season_rows(season)
    return tables


def _match_rows(tables: dict[str, list[Record]], d: Path, fx: Record, who: dict[str, Record]) -> None:
    stream = list(iter_jsonl(d / "events.jsonl"))
    header = stream[0]
    score = header.get("score", {})
    team_club = {t["team_id"]: t.get("club_id") for t in header["teams"]}
    gid_of = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
    periods = header.get("periods", [])
    manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
    tables["matches"].append({
        "match_id": fx["match_id"], "round": fx["round"], "date": dt.date.fromisoformat(fx["date"]),
        "home_club_id": fx["home"], "away_club_id": fx["away"], "home_goals": score.get(header["home_team_id"], 0),
        "away_goals": score.get(header["away_team_id"], 0), "seed": fx["seed"], "periods": len(periods),
        # the same sum, in the same order, that a profile's minutes come from
        "played_s": sum(p["t_end"] - p["t"] for p in periods),
        "video_duration_s": (header.get("video") or {}).get("duration_s"), "title": manifest.get("title")})
    on_pitch = played_seconds(stream)  # the seconds a profile's minutes come from (substitutions and red cards cut them)
    for p in header["players"]:
        tables["lineups"].append({"match_id": fx["match_id"], "player_id": p["player_id"], "global_id": gid_of[p["player_id"]],
                                  "team_id": p["team_id"], "club_id": team_club.get(p["team_id"]), "kit_number": p["kit_number"],
                                  "position": p["position"], "starter": bool(p["starter"]),
                                  "played_s": float(on_pitch.get(p["player_id"], 0.0))})
    for e in stream:
        if e["type"] != "event":
            continue
        clock, pt, end = e.get("clock") or {}, e.get("pitch") or {}, e.get("pitch_end") or {}
        tables["events"].append({
            "match_id": fx["match_id"], "event_id": e["id"], "t": e["t"], "period": clock.get("period"),
            "minute": clock.get("minute"), "second": clock.get("second"), "event_type": e["event_type"],
            "outcome": e.get("outcome"), "player_id": e.get("player_id"), "global_id": gid_of.get(e.get("player_id")),
            "team_id": e.get("team_id"), "club_id": team_club.get(e.get("team_id")),
            "related_player_id": e.get("related_player_id"), "related_global_id": gid_of.get(e.get("related_player_id")),
            "possession_id": e.get("possession_id"), "segment_id": e.get("segment_id"),
            "under_pressure": bool(e.get("under_pressure")), "x": pt.get("x"), "y": pt.get("y"), "end_x": end.get("x"),
            "end_y": end.get("y"), "body_part": e.get("body_part"), "qualifiers": list(e.get("qualifiers") or []),
            "confidence": e.get("confidence")})
    if (d / "clips.jsonl").exists():
        for r in iter_jsonl(d / "clips.jsonl"):
            if r["type"] == "clip":
                tables["clips"].append({"match_id": fx["match_id"], "clip_id": r["id"], "player_id": r["player_id"],
                                        "global_id": gid_of.get(r["player_id"]), "t": r["t"], "t_end": r["t_end"],
                                        "keyframe_t": r.get("keyframe_t"), "reason": r["reason"],
                                        "event_ids": list(r.get("event_ids") or []), "segment_ids": list(r.get("segment_ids") or [])})
            elif r["type"] == "label":
                tables["labels"].append({"match_id": fx["match_id"], "label_id": r["id"], "clip_id": r["clip_id"],
                                         "player_id": r["player_id"], "global_id": gid_of.get(r["player_id"]),
                                         "title": r.get("title"), "summary": r.get("summary"), "explanation": r.get("explanation"),
                                         "tags": list(r.get("tags") or []), "watchability": r.get("watchability"),
                                         "prior_watchability": r.get("prior_watchability"), "model": r.get("model")})


def player_season_rows(season: Season) -> list[Record]:
    """Regista's numbers, exactly as a profile shows them: one row per player and stat."""
    rows = []
    for gid in sorted(season.profiles):
        p = season.profiles[gid]
        for key, (label, _test) in STATS.items():
            rows.append({"global_id": gid, "name": p["name"], "club_id": p["club_id"], "position": p["position"],
                         "appearances": p["appearances"], "minutes": p["minutes"], "stat": key, "label": label,
                         "count": p["counts"][key], "per90": p["per90"][key], "percentile": p["percentiles"].get(key)})
    return rows


def upload_rows(store: Any, fetch: Callable[[str, Path], int] | None = None) -> list[Record]:
    """One row per Player-view upload in the store. A finished upload's match is fetched (``store.get_match``) and the
    uploader's minutes and headline counts in it are added; the uploader is found by global id on the team sheet,
    else by their side and kit number, as the profiles find them."""
    fetch = fetch or store.get_match
    rows = []
    for rec in store.list_records():
        row = {"upload_id": rec.upload_id, "global_id": rec.global_id, "club_id": rec.club_id,
               "opponent_club_id": rec.opponent_club_id, "side": rec.side, "kit_number": rec.kit_number, "status": rec.status,
               "source": rec.source, "match_id": rec.match_id, "created_at": _ts(rec.created_at), "updated_at": _ts(rec.updated_at),
               "stages": len(rec.stages or []), "error": rec.error, "minutes": None, **{k: None for k in UPLOAD_STATS}}
        if rec.status == "done" and rec.match_id:
            with tempfile.TemporaryDirectory() as tmp:
                d = Path(tmp) / rec.match_id
                if fetch(rec.match_id, d) and (d / "events.jsonl").exists():
                    row.update(_uploader_numbers(d, rec))
        rows.append(row)
    return rows


def _uploader_numbers(d: Path, rec: Any) -> Record:
    stream = list(iter_jsonl(d / "events.jsonl"))
    header = stream[0]
    pid = next((p["player_id"] for p in header.get("players", []) if p.get("global_player_id") == rec.global_id), None)
    if pid is None:
        team = header.get(f"{rec.side}_team_id")
        pid = next((p["player_id"] for p in header.get("players", [])
                    if p["team_id"] == team and p["kit_number"] == rec.kit_number), None)
    if pid is None:
        return {}
    out: Record = {"minutes": round(sum(p["t_end"] - p["t"] for p in header.get("periods", [])) / 60.0, 1)}
    for key in UPLOAD_STATS:
        test = STATS[key][1]
        out[key] = sum(1 for e in stream if e["type"] == "event" and e.get("player_id") == pid and test(e))
    return out


def _ts(t: float | None) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(t, tz=dt.timezone.utc) if t else None


def to_arrow(table: str, rows: list[Record]) -> Any:
    """The rows as a pyarrow Table with the table's schema (columns in schema order; missing values are nulls)."""
    import pyarrow as pa

    types = {"string": pa.string(), "int": pa.int64(), "double": pa.float64(), "bool": pa.bool_(), "date": pa.date32(),
             "timestamp": pa.timestamp("us", tz="UTC"), "list<string>": pa.list_(pa.string())}
    schema = pa.schema([(name, types[kind]) for name, kind in SCHEMAS[table].items()])
    cols = {name: [r.get(name) for r in rows] for name in schema.names}
    return pa.Table.from_pydict(cols, schema=schema)
