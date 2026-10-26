"""The Regista catalogue as tables for the Fabric lakehouse, next to the league's (``regista.cloud.fabric_tables``).

14 competitions in 10 countries, 90 uploaded matches: England semi-pro men is the Regista League itself (its 30 league
fixtures, from ``data/season/matches``, exactly the matches the catalogue pages count; the Player view's friendlies are
not catalogue matches), and the other 13 competitions add 60 uploaded matches (``data/catalogue/matches``). Every table
is named ``catalogue_*``, so the league's tables and their check stay exactly as they are.

    catalogue_competitions   one row per competition: country, region, level labels (tier, age group, gender), the
                             season and ``as_of`` (the catalogue holds matches already played by then)
    catalogue_clubs          one row per club and competition
    catalogue_players        one row per squad entry (competition, global id): the public bio only (age, date of birth,
                             height, foot, nationality, role); ``career`` when the person is in two competitions' squads
    catalogue_matches        one row per uploaded match: competition, round, date, score, played_s (the periods' length),
                             who uploaded it (a team account or a player who started) and the camera type (a label only)
    catalogue_lineups        one row per player per match, with played_s from substitutions and red cards
    catalogue_events         every event of every match, with ``competition_id`` and ``seq`` (its place in the stream)
    catalogue_possessions    every possession record, with ``seq``: a key pass is read off the possession a shot came from
    catalogue_player_season  Regista's own numbers for the check, from the engine the catalogue pages use
                             (``regista.catalogue.metrics.CatalogueMetrics``): one row per player-competition row, per
                             checked stat, with appearances, minutes, count, per-90, the percentile in the default level
                             pool (``scope=level``) and that pool's size

Never written: the hidden ratings, the competition files' ``level`` block (scales and ``execution``), the generator
block, the attributes block and any seed. ``tests/test_fabric_catalogue.py`` checks every table for them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from regista.cloud.fabric import CATALOGUE_CHECK_STATS
from regista.schema import iter_jsonl
from regista.season.league import age_on, people
from regista.season.playing_time import played_seconds

Record = dict[str, Any]

PLAYER_KEYS = ("global_id", "name", "club_id", "kit_number", "position", "role", "starter", "age", "date_of_birth",
               "height_cm", "preferred_foot", "nationality", "career")


def catalogue_tables(cm: Any = None, *, index_path: Path | str | None = None, root: Path | str | None = None,
                     league_path: Path | str | None = None, season_root: Path | str | None = None,
                     stats: list[str] | None = None) -> dict[str, list[Record]]:
    """Every catalogue table. ``cm``: a built ``CatalogueMetrics`` (default: ``load_catalogue_metrics`` with these
    paths, which builds any missing match folder first, in a process pool: a calling script needs a ``__main__``
    guard)."""
    from regista.catalogue import store
    from regista.catalogue.build import materialise_match
    from regista.catalogue.taxonomy import AS_OF, ENGLAND_ID, level_label
    from regista.season import build as season_build

    if cm is None:
        from regista.catalogue.metrics import load_catalogue_metrics

        cm = load_catalogue_metrics(index_path, root, league_path, season_root)
    root = Path(root) if root else store.matches_root()
    season_root = Path(season_root or os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    names = _label_names()
    as_of = dt.date.fromisoformat(cm.index.get("as_of") or AS_OF)
    entries = {e["competition_id"]: e for e in cm.index["competitions"]}
    t: dict[str, list[Record]] = {k: [] for k in ("catalogue_competitions", "catalogue_clubs", "catalogue_players",
                                                   "catalogue_matches", "catalogue_lineups", "catalogue_events",
                                                   "catalogue_possessions")}
    squads = {gid: len(rows) for gid, rows in cm.people.items()}
    for cid in cm.order:
        e, comp = entries[cid], cm.comps[cid]
        level = f"{e['tier']}/{e['age_group']}/{e['gender']}"
        t["catalogue_competitions"].append({
            "competition_id": cid, "code": e.get("code"), "name": e["name"], "country": e["country"], "region": e.get("region"),
            "tier": e["tier"], "tier_label": names[e["tier"]], "age_group": e["age_group"],
            "age_group_label": names[e["age_group"]], "gender": e["gender"], "gender_label": names[e["gender"]],
            "level": level, "level_label": level_label(level), "format": e.get("format"), "season": e.get("season"),
            "eligibility": e.get("eligibility"), "teams": e.get("teams"), "uploaded_matches": e.get("uploaded_matches"),
            "coverage": e.get("coverage"), "source": e["source"], "as_of": as_of})
        for c in comp["clubs"]:
            kit = c.get("kit") or {}
            t["catalogue_clubs"].append({"competition_id": cid, "club_id": c["club_id"], "name": c["name"],
                                         "short_name": c.get("short_name"), "city": c.get("city"), "ground": c.get("ground"),
                                         "kit_primary": kit.get("primary"), "kit_secondary": kit.get("secondary"),
                                         "kit_gk": kit.get("gk")})
        for gid, p in people(comp).items():
            dob = p.get("date_of_birth")
            row = {"global_id": gid, "name": p["name"], "club_id": p["club_id"], "kit_number": p["kit_number"],
                   "position": p["position"], "role": p.get("role"), "starter": bool(p.get("starter")),
                   "age": age_on(dob) if dob else None, "date_of_birth": dt.date.fromisoformat(dob) if dob else None,
                   "height_cm": p.get("height_cm"), "preferred_foot": p.get("preferred_foot"),
                   "nationality": p.get("nationality"), "career": squads.get(gid, 0) > 1}
            t["catalogue_players"].append({"competition_id": cid, **{k: row[k] for k in PLAYER_KEYS}})
        for fx in comp["fixtures"]:
            if cid == ENGLAND_ID:   # the league's own fixtures and folders, as the catalogue pages count them
                d = season_build.materialise(comp, fx, season_root)
            else:
                d = materialise_match(comp, fx, root)
            _match_rows(t, cid, fx, d, cm.uploads.get(fx["match_id"]) or {})
    t["catalogue_player_season"] = catalogue_player_season_rows(cm, stats)
    return t


def _label_names() -> dict[str, str]:
    from regista.catalogue.taxonomy import AGE_GROUPS, GENDERS, TIERS

    return dict(TIERS) | dict(AGE_GROUPS) | dict(GENDERS)


def _match_rows(t: dict[str, list[Record]], cid: str, fx: Record, d: Path, upload: Record) -> None:
    stream = list(iter_jsonl(d / "events.jsonl"))
    header = stream[0]
    score = header.get("score", {})
    team_club = {x["team_id"]: x.get("club_id") for x in header["teams"]}
    gid_of = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
    periods = header.get("periods", [])
    manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
    up = upload.get("uploader") or {}
    t["catalogue_matches"].append({
        "match_id": fx["match_id"], "competition_id": cid, "round": fx["round"], "date": dt.date.fromisoformat(fx["date"]),
        "home_club_id": fx["home"], "away_club_id": fx["away"], "home_goals": score.get(header["home_team_id"], 0),
        "away_goals": score.get(header["away_team_id"], 0), "periods": len(periods),
        "played_s": sum(p["t_end"] - p["t"] for p in periods),   # the sum, in the order, the engine's club minutes use
        "video_duration_s": (header.get("video") or {}).get("duration_s"), "title": manifest.get("title"),
        "uploader_type": up.get("type"), "uploader_club_id": up.get("club_id"), "uploader_global_id": up.get("global_id"),
        "camera": upload.get("camera")})
    on_pitch = played_seconds(stream)
    for p in header["players"]:
        t["catalogue_lineups"].append({"match_id": fx["match_id"], "competition_id": cid, "player_id": p["player_id"],
                                       "global_id": gid_of[p["player_id"]], "team_id": p["team_id"],
                                       "club_id": team_club.get(p["team_id"]), "kit_number": p["kit_number"],
                                       "position": p["position"], "starter": bool(p["starter"]),
                                       "played_s": float(on_pitch.get(p["player_id"], 0.0))})
    for seq, e in enumerate(stream):
        if e["type"] == "possession":
            t["catalogue_possessions"].append({
                "match_id": fx["match_id"], "competition_id": cid, "seq": seq, "possession_id": e["id"], "t": e["t"],
                "t_end": e.get("t_end"), "player_id": e.get("player_id"), "global_id": gid_of.get(e.get("player_id")),
                "team_id": e.get("team_id"), "club_id": team_club.get(e.get("team_id")), "gained_by": e.get("gained_by"),
                "lost_by": e.get("lost_by"), "touches": e.get("touches"), "under_pressure": bool(e.get("under_pressure"))})
        if e["type"] != "event":
            continue
        clock, pt, end = e.get("clock") or {}, e.get("pitch") or {}, e.get("pitch_end") or {}
        t["catalogue_events"].append({
            "match_id": fx["match_id"], "competition_id": cid, "seq": seq, "event_id": e["id"], "t": e["t"],
            "period": clock.get("period"), "minute": clock.get("minute"), "second": clock.get("second"),
            "event_type": e["event_type"], "outcome": e.get("outcome"), "player_id": e.get("player_id"),
            "global_id": gid_of.get(e.get("player_id")), "team_id": e.get("team_id"),
            "club_id": team_club.get(e.get("team_id")), "related_player_id": e.get("related_player_id"),
            "related_global_id": gid_of.get(e.get("related_player_id")), "possession_id": e.get("possession_id"),
            "segment_id": e.get("segment_id"), "under_pressure": bool(e.get("under_pressure")), "x": pt.get("x"),
            "y": pt.get("y"), "end_x": end.get("x"), "end_y": end.get("y"), "body_part": e.get("body_part"),
            "qualifiers": list(e.get("qualifiers") or []), "confidence": e.get("confidence")})


def catalogue_player_season_rows(cm: Any, stats: list[str] | None = None) -> list[Record]:
    """Regista's numbers as the catalogue pages show them, one row per player-competition row (every player who appeared
    in a competition's uploaded matches) and checked stat: the competition engine's appearances, minutes, count and per-90
    (``cell``), and the percentile and pool of the default scope, ``level`` (same tier, age group, gender and position
    over every competition of that level; ``CatalogueMetrics.percentile`` and ``pool``)."""
    from regista.season.metrics import CATALOGUE

    stats = stats or CATALOGUE_CHECK_STATS
    rows = []
    for cid in cm.order:
        sm = cm.metrics[cid]
        lab = cm.labels[cid]
        for gid in sorted(sm.players):
            ps = sm.players[gid]
            pos = ps.info["position"]
            for key in stats:
                m = CATALOGUE[key]
                pool = cm.pool(cid, key, pos, "level")
                v = ps.values.get(key)
                rows.append({"competition_id": cid, "global_id": gid, "name": ps.info["name"], "club_id": ps.info["club_id"],
                             "position": pos, "tier": lab["tier"], "age_group": lab["age_group"], "gender": lab["gender"],
                             "appearances": ps.appearances, "minutes": round(ps.minutes, 1),
                             "qualifying_minutes": round(sm.min_minutes, 1), "stat": key, "label": m.label,
                             "count": int(round(ps.totals.get(key, 0.0))),
                             "per90": None if v is None else round(v, m.digits), "qualified": sm.qualified(ps, m),
                             "percentile": cm.percentile(cid, ps, key, "level"), "pool_size": pool["size"],
                             "pool_words": pool["words"], "noisy": cm.noisy(cid, key, "level", ps.minutes)})
    return rows
