"""The catalogue's MCP tool bodies (``regista.mcp_server``: ``list_competitions``, ``search_catalogue_players``,
``get_catalogue_player``) and the competition summary the API shares. Pure reads over the committed catalogue and
``CatalogueMetrics``; never a hidden rating or a level scale. Bad arguments come back as ``{"error": ...}`` so an agent
can correct itself.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from regista.catalogue import store
from regista.catalogue.metrics import ALL_WARNING, POOL_RULE, SYNTHETIC_NOTE, CatalogueMetrics
from regista.catalogue.taxonomy import AGE_GROUPS, GENDERS, TIERS, levels_public
from regista.season.metrics import CATALOGUE, DEFAULT_COLUMNS

Record = dict[str, Any]

LABEL_KEYS = ("competition_id", "name", "country", "region", "tier", "age_group", "gender", "format", "season", "coverage")
SCOPES = ("level", "competition", "all")
POSITIONS = ("GK", "DF", "MF", "FW")
MAX_LIMIT = 50


def comp_labels(e: Record) -> Record:
    return {k: e.get(k) for k in LABEL_KEYS}


def uploads_of(e: Record, comp: Record) -> list[Record]:
    """Each fixture's uploader and camera (England's from the index's overlay, the others' from their fixtures)."""
    if e["source"] == "league":
        return [e.get("uploads", {}).get(fx["match_id"], {}) for fx in comp["fixtures"]]
    return [{"uploader": fx.get("uploader"), "camera": fx.get("camera")} for fx in comp["fixtures"]]


def competition_summary(e: Record, comp: Record) -> Record:
    """A competition as a list shows it, from the committed files only (no match is built)."""
    ups = uploads_of(e, comp)
    gids = {p["global_id"] for c in comp["clubs"] for p in c.get("squad", [])}
    dates = [fx["date"] for fx in comp["fixtures"]]
    return {**comp_labels(e), "teams": len(comp["clubs"]), "players": len(gids), "uploaded_matches": len(comp["fixtures"]),
            "cameras": dict(Counter(u.get("camera") for u in ups if u.get("camera"))),
            "uploaders": dict(Counter((u.get("uploader") or {}).get("type") for u in ups if u.get("uploader"))),
            "dates": [min(dates), max(dates)] if dates else None,
            "api_url": f"/api/competitions/{e['competition_id']}"}


def _check(value: str | None, allowed: tuple[str, ...] | list[str], name: str) -> str | None:
    if value and value not in allowed:
        return f"unknown {name} {value!r}: one of {', '.join(allowed)}"
    return None


def filter_errors(tier=None, age_group=None, gender=None, position=None, scope=None) -> str | None:
    return (_check(tier, [k for k, _v in TIERS], "tier") or _check(age_group, [k for k, _v in AGE_GROUPS], "age_group")
            or _check(gender, [k for k, _v in GENDERS], "gender") or _check(position, POSITIONS, "position")
            or _check(scope, SCOPES, "scope"))


def entries_matching(index: Path | str | None, *, competition=None, country=None, tier=None, age_group=None,
                     gender=None) -> list[tuple[Record, Record]]:
    out = []
    for e in store.entries(index):
        if (competition and e["competition_id"] != competition) or (tier and e["tier"] != tier) or \
                (age_group and e["age_group"] != age_group) or (gender and e["gender"] != gender) or \
                (country and e["country"].lower() != country.lower()):
            continue
        out.append((e, store.competition(e["competition_id"], index)))
    return out


def list_competitions(index: Path | str | None = None, *, country: str | None = None, tier: str | None = None,
                      age_group: str | None = None, gender: str | None = None) -> Record:
    err = filter_errors(tier=tier, age_group=age_group, gender=gender)
    if err:
        return {"error": err}
    idx = store.load_index(index)
    rows = [competition_summary(e, c) for e, c in entries_matching(index, country=country, tier=tier, age_group=age_group,
                                                                    gender=gender)]
    return {"competitions": rows, "total": len(rows), "levels": levels_public(),
            "careers": [{k: car.get(k) for k in ("global_id", "name", "competitions", "story")} for car in idx.get("careers", [])],
            "note": SYNTHETIC_NOTE}


def search_players(cm: CatalogueMetrics, *, tier=None, age_group=None, gender=None, country=None, competition=None,
                   position=None, sort: str = "minutes", order: str = "desc", scope: str = "level", limit: int = 10,
                   min_minutes: float | None = None) -> Record:
    """Player-competition rows across the catalogue, filtered and ranked by any terminal metric (or minutes); each with the
    sorted metric's value, its percentile in ``scope`` and the pool it came from."""
    err = filter_errors(tier=tier, age_group=age_group, gender=gender, position=position, scope=scope)
    if err:
        return {"error": err}
    if competition and competition not in cm.metrics:
        return {"error": f"unknown competition {competition!r} (list_competitions lists them)"}
    if sort != "minutes" and sort not in CATALOGUE:
        return {"error": f"unknown sort {sort!r}: minutes or a Scout terminal metric key such as npxg, goals, take_ons_won"}
    if order not in ("asc", "desc"):
        return {"error": "order is asc or desc"}
    limit = max(1, min(int(limit), MAX_LIMIT))
    rows = cm.select(tier=tier, age_group=age_group, gender=gender, country=country, competition=competition,
                     position=position, min_minutes=min_minutes)
    if sort == "minutes":
        rows.sort(key=lambda r: ((-1 if order == "desc" else 1) * r[1].minutes, r[1].info["name"], r[0]))
    else:
        rows = cm.sort(rows, sort, order)
    out = []
    for cid, ps in rows[:limit]:
        gid = ps.info["global_id"]
        row = {"global_id": gid, "name": ps.info["name"], **cm.labels_of(cid), "club": ps.info["club"],
               "position": ps.info["position"], "role": ps.info.get("role"), "age": ps.info.get("age"),
               "minutes": round(ps.minutes, 1), "appearances": ps.appearances,
               "qualified": ps.minutes >= cm.metrics[cid].min_minutes, "career": len(cm.people.get(gid, [])) > 1}
        if sort != "minutes":
            c = cm.cell(cid, gid, sort, scope)
            row["stat"] = {"key": sort, "label": CATALOGUE[sort].label, "value": c["value"], "percentile": c["percentile"],
                           "noisy": c["noisy"], "pool": {k: c["pool"][k] for k in ("scope", "tier", "age_group", "gender",
                                                                                   "position", "size", "small", "reason")}}
        out.append(row)
    levels = {cm.level[cid] for cid, _ps in rows}
    return {"players": out, "total": len(rows), "sort": sort, "order": order, "scope": scope,
            "warning": ALL_WARNING if scope == "all" or len(levels) > 1 else None, "pool_rule": POOL_RULE,
            "note": SYNTHETIC_NOTE}


def find_player(cm: CatalogueMetrics, player: str) -> tuple[str | None, list[Record]]:
    """(global id, candidates): by global id, or by full name (case-insensitive), or by a unique surname."""
    p = (player or "").strip()
    if p in cm.people:
        return p, []
    low = p.lower()
    exact = [gid for gid, es in cm.people.items() if es[0][1]["name"].lower() == low]
    if len(exact) == 1:
        return exact[0], []
    hits = exact or [gid for gid, es in cm.people.items() if low and low in es[0][1]["name"].lower()]
    if len(hits) == 1:
        return hits[0], []
    return None, [{"global_id": gid, "name": cm.people[gid][0][1]["name"],
                   "competitions": [c for c, _p in cm.people[gid]]} for gid in sorted(hits)[:10]]


def get_player(cm: CatalogueMetrics, player: str, scope: str = "level") -> Record:
    err = filter_errors(scope=scope)
    if err:
        return {"error": err}
    gid, candidates = find_player(cm, player)
    if gid is None:
        return {"error": f"no single catalogue player matches {player!r}", "candidates": candidates}
    out = cm.player(gid, scope)
    out["default_metrics"] = {r["competition_id"]: list(DEFAULT_COLUMNS.get(r["position"], DEFAULT_COLUMNS[None]))
                              for r in out["rows"]}
    return out
