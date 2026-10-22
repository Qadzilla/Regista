"""Player profiles across the season, aggregated from the league's event streams and clips.

A profile is keyed on the global player id and holds: appearances and minutes, counts and per-90 rates for the stats a
scout reads (passing, chance creation, shooting, dribbling, defending), the league percentile of each rate among
players in the same position, a touch map oriented so the player's team attacks left to right, the player's best
moments across matches, and for every stat the events it was counted from, with the clip each event sits in
("verified by Regista": a number you can watch). Nothing here calls a model; the Foundry summary is the Profile
agent's job (planned in the Scout view work).
"""

from __future__ import annotations

import json
import threading
from bisect import bisect_left
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from regista.schema import iter_jsonl
from regista.season.build import materialise
from regista.season.league import club_by_id, load_league, people
from regista.synth.generator import PITCH_L, PITCH_W

Record = dict[str, Any]

# stat key -> (label people read, what counts). Each test gets one event and returns True when it counts.
STATS: dict[str, tuple[str, Any]] = {
    "touches": ("Touches", lambda e: e["event_type"] == "touch"),
    "passes": ("Passes", lambda e: e["event_type"] == "pass"),
    "passes_completed": ("Passes completed", lambda e: e["event_type"] == "pass" and e.get("outcome") == "success"),
    "forward_passes": ("Forward passes", lambda e: e["event_type"] == "pass" and "forward" in e.get("qualifiers", [])),
    "key_passes": ("Key passes", lambda e: e["event_type"] in ("pass", "cross") and "key_pass" in e.get("qualifiers", [])),
    "assists": ("Assists", lambda e: e["event_type"] == "assist"),
    "crosses": ("Crosses", lambda e: e["event_type"] == "cross"),
    "crosses_completed": ("Crosses completed", lambda e: e["event_type"] == "cross" and e.get("outcome") == "success"),
    "carries": ("Carries", lambda e: e["event_type"] == "carry"),
    "take_ons": ("Take-ons", lambda e: e["event_type"] == "take_on"),
    "take_ons_won": ("Take-ons won", lambda e: e["event_type"] == "take_on" and e.get("outcome") == "success"),
    "nutmegs": ("Nutmegs", lambda e: e["event_type"] == "nutmeg"),
    "shots": ("Shots", lambda e: e["event_type"] == "shot"),
    "shots_on_target": ("Shots on target", lambda e: e["event_type"] == "shot" and
                        bool({"goal", "saved"} & set(e.get("qualifiers", [])))),
    "goals": ("Goals", lambda e: e["event_type"] == "goal"),
    "tackles_won": ("Tackles won", lambda e: e["event_type"] == "tackle" and e.get("outcome") == "success"),
    "interceptions": ("Interceptions", lambda e: e["event_type"] == "interception"),
    "recoveries": ("Ball recoveries", lambda e: e["event_type"] == "recovery"),
    "clearances": ("Clearances", lambda e: e["event_type"] == "clearance"),
    "pressures": ("Pressures", lambda e: e["event_type"] == "pressure"),
    "saves": ("Saves", lambda e: e["event_type"] == "save"),
    "fouls_won": ("Fouls won", lambda e: e["event_type"] == "foul_won"),
}
# Shown on profiles and scout cards, in this order; the rest are in the full table.
HEADLINE = ["goals", "assists", "shots", "key_passes", "take_ons_won", "nutmegs", "passes_completed", "tackles_won",
            "interceptions", "recoveries", "saves"]
RATIOS = {"pass_accuracy": ("Pass accuracy", "passes_completed", "passes"),
          "take_on_success": ("Take-on success", "take_ons_won", "take_ons"),
          "shot_accuracy": ("Shots on target", "shots_on_target", "shots")}
GRID_X, GRID_Y = 12, 8
MOMENTS_KEPT = 40
MAX_EVIDENCE = 60


@dataclass
class Season:
    league: Record
    root: Path
    profiles: dict[str, Record] = field(default_factory=dict)
    matches: list[Record] = field(default_factory=list)
    table: list[Record] = field(default_factory=list)

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, league: Record, root: Path | str) -> Season:
        s = cls(league, Path(root))
        s._aggregate()
        return s

    def _aggregate(self) -> None:
        clubs = club_by_id(self.league)
        who = people(self.league)
        acc: dict[str, Record] = {gid: _empty(p) for gid, p in who.items()}
        table = {cid: {"club_id": cid, "club": c["name"], "short_name": c["short_name"], "kit": c["kit"], "played": 0, "won": 0,
                       "drawn": 0, "lost": 0, "goals_for": 0, "goals_against": 0, "points": 0} for cid, c in clubs.items()}
        for fx in self.league["fixtures"]:
            d = materialise(self.league, fx, self.root)
            stream = list(iter_jsonl(d / "events.jsonl"))
            header = stream[0]
            score = header.get("score", {})
            minutes = sum(p["t_end"] - p["t"] for p in header.get("periods", [])) / 60.0
            ltr = {p["period"]: p["left_to_right_team_id"] for p in header.get("periods", [])}
            local_to_global = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
            team_club = {t["team_id"]: t.get("club_id") for t in header["teams"]}
            opp = {header["home_team_id"]: fx["away"], header["away_team_id"]: fx["home"]}
            self._table_row(table, fx, score)
            self.matches.append({"match_id": fx["match_id"], "round": fx["round"], "date": fx["date"], "home": fx["home"],
                                 "away": fx["away"], "score": score, "title": _manifest_title(d)})
            clip_of_event, moments = _clips_and_moments(d, local_to_global)
            for p in header["players"]:
                gid = p.get("global_player_id")
                if gid and p["starter"] and gid in acc:
                    a = acc[gid]
                    a["appearances"] += 1
                    a["minutes"] += minutes
                    a["matches"].append({"match_id": fx["match_id"], "round": fx["round"], "date": fx["date"],
                                         "player_id": p["player_id"], "club_id": team_club[p["team_id"]],
                                         "opponent": clubs[opp[p["team_id"]]]["name"],
                                         "home": p["team_id"] == header["home_team_id"],
                                         "score": f"{score.get('t_home', 0)}–{score.get('t_away', 0)}"})
            for rec in stream:
                if rec["type"] != "event" or not rec.get("player_id"):
                    continue
                gid = local_to_global.get(rec["player_id"])
                if not gid or gid not in acc:
                    continue
                a = acc[gid]
                for key, (_label, test) in STATS.items():
                    if test(rec):
                        a["counts"][key] += 1
                        if len(a["evidence"][key]) < MAX_EVIDENCE:
                            a["evidence"][key].append({"match_id": fx["match_id"], "player_id": rec["player_id"], "event_id": rec["id"], "t": rec["t"],
                                                       "clip_id": clip_of_event.get((rec["player_id"], rec["id"]))})
                pt = rec.get("pitch")
                if pt and rec["event_type"] in ("touch", "pass", "cross", "carry", "take_on", "shot", "tackle", "interception",
                                                "recovery", "clearance"):
                    period = (rec.get("clock") or {}).get("period", 1)
                    team_ltr = ltr.get(period, header["home_team_id"]) == rec["team_id"]
                    x, y = (pt["x"], pt["y"]) if team_ltr else (PITCH_L - pt["x"], PITCH_W - pt["y"])
                    gx = min(GRID_X - 1, max(0, int(x / PITCH_L * GRID_X)))
                    gy = min(GRID_Y - 1, max(0, int(y / PITCH_W * GRID_Y)))
                    a["grid"][gy][gx] += 1
            for gid, ms in moments.items():
                if gid in acc:
                    acc[gid]["moments"] += ms
        for gid, a in acc.items():
            self.profiles[gid] = _finish(a)
        _percentiles(self.profiles)
        self.table = sorted(table.values(), key=lambda r: (-r["points"], -(r["goals_for"] - r["goals_against"]), -r["goals_for"], r["club"]))
        for i, r in enumerate(self.table, start=1):
            r["position"] = i
            r["goal_difference"] = r["goals_for"] - r["goals_against"]

    @staticmethod
    def _table_row(table: dict[str, Record], fx: Record, score: dict[str, int]) -> None:
        h, a = table[fx["home"]], table[fx["away"]]
        gh, ga = score.get("t_home", 0), score.get("t_away", 0)
        for row, gf, gc in ((h, gh, ga), (a, ga, gh)):
            row["played"] += 1
            row["goals_for"] += gf
            row["goals_against"] += gc
            if gf > gc:
                row["won"] += 1
                row["points"] += 3
            elif gf == gc:
                row["drawn"] += 1
                row["points"] += 1
            else:
                row["lost"] += 1

    # ------------------------------------------------------------------ queries
    def player(self, gid: str) -> Record | None:
        return self.profiles.get(gid)

    def players(self, *, position: str | None = None, club: str | None = None, min_minutes: float = 0.0, q: str | None = None,
                sort: str = "minutes", limit: int = 200) -> list[Record]:
        """Profile cards (no evidence, moments or grid), filtered and sorted. ``sort`` is a stat key (per 90), a ratio
        key, or "minutes" / "name"; highest first except "name"."""
        rows = [p for p in self.profiles.values() if p["appearances"] > 0]
        if position:
            rows = [p for p in rows if p["position"] == position.upper()]
        if club:
            c = club.lower()
            rows = [p for p in rows if c in (p["club_id"].lower(), p["club"].lower(), p["short_name"].lower())]
        if min_minutes:
            rows = [p for p in rows if p["minutes"] >= min_minutes]
        if q:
            words = q.lower().split()
            rows = [p for p in rows if all(w in p["name"].lower() or w in p["club"].lower() for w in words)]
        rows.sort(key=lambda p: _sort_key(p, sort))
        return [card(p) for p in rows[:limit]]


def _sort_key(p: Record, sort: str) -> Any:
    if sort == "name":
        return p["name"]
    if sort == "minutes":
        return (-p["minutes"], p["name"])
    if sort in p["per90"]:
        return (-p["per90"][sort], p["name"])
    if sort in p["ratios"]:
        return (-(p["ratios"][sort] or 0.0), p["name"])
    raise ValueError(f"unknown sort {sort!r}")


def card(p: Record) -> Record:
    """What a scout list shows: who, where, how much, and the headline rates."""
    keep = ("global_id", "name", "club_id", "club", "short_name", "kit", "kit_number", "position", "appearances", "minutes")
    return {**{k: p[k] for k in keep}, "headline": {k: {"label": STATS[k][0], "count": p["counts"][k], "per90": p["per90"][k],
                                                        "percentile": p["percentiles"].get(k)} for k in HEADLINE},
            "ratios": p["ratios"], "best_moment": p["moments"][0] if p["moments"] else None}


def _empty(person: Record) -> Record:
    return {"global_id": person["global_id"], "name": person["name"], "kit_number": person["kit_number"],
            "position": person["position"], "starter": person["starter"], "club_id": person["club_id"], "club": person["club"],
            "short_name": person["short_name"], "kit": person["kit"],
            "appearances": 0, "minutes": 0.0, "matches": [], "counts": {k: 0 for k in STATS},
            "evidence": {k: [] for k in STATS}, "grid": [[0] * GRID_X for _ in range(GRID_Y)], "moments": []}


def _finish(a: Record) -> Record:
    m = a["minutes"]
    a["minutes"] = round(m, 1)
    a["per90"] = {k: round(v * 90.0 / m, 2) if m else 0.0 for k, v in a["counts"].items()}
    a["ratios"] = {k: (round(a["counts"][num] / a["counts"][den], 3) if a["counts"][den] else None) for k, (_l, num, den) in RATIOS.items()}
    a["stat_labels"] = {k: lbl for k, (lbl, _t) in STATS.items()} | {k: lbl for k, (lbl, _n, _d) in RATIOS.items()}
    a["moments"].sort(key=lambda r: (-r["watchability"], r["round"], r["t"]))
    a["moments"] = a["moments"][:MOMENTS_KEPT]
    a["percentiles"] = {}
    return a


def _percentiles(profiles: dict[str, Record]) -> None:
    """Each per-90 rate's percentile (0-100) among players in the same position with at least 40% of the most minutes."""
    by_pos: dict[str, list[Record]] = {}
    most = max((p["minutes"] for p in profiles.values()), default=0.0)
    for p in profiles.values():
        if p["appearances"] and p["minutes"] >= 0.4 * most:
            by_pos.setdefault(p["position"], []).append(p)
    for group in by_pos.values():
        for key in STATS:
            values = sorted(p["per90"][key] for p in group)
            for p in group:
                below = bisect_left(values, p["per90"][key])
                p["percentiles"][key] = round(100.0 * below / max(1, len(values) - 1)) if len(values) > 1 else None


def _manifest_title(d: Path) -> str | None:
    m = d / "manifest.json"
    return json.loads(m.read_text()).get("title") if m.exists() else None


def _clips_and_moments(d: Path, local_to_global: dict[str, str | None]) -> tuple[dict[tuple[str, str], str], dict[str, list[Record]]]:
    """(player id, event id) -> that player's on-ball clip the event sits in, and global id -> the player's labelled
    moments in this match. Keyed by player too: another player's clip of the same possession is not this one's evidence."""
    clips, labels = {}, {}
    p = d / "clips.jsonl"
    if p.exists():
        for r in iter_jsonl(p):
            (clips.__setitem__(r["id"], r) if r["type"] == "clip" else labels.__setitem__(r["clip_id"], r))
    clip_of_event: dict[tuple[str, str], str] = {}
    moments: dict[str, list[Record]] = {}
    match_id = d.name
    round_no = json.loads((d / "manifest.json").read_text()).get("round") if (d / "manifest.json").exists() else None
    for cid, c in clips.items():
        for eid in c.get("event_ids", []):
            if c["reason"] == "on_ball_main":
                clip_of_event.setdefault((c["player_id"], eid), cid)
        gid = local_to_global.get(c["player_id"])
        lb = labels.get(cid)
        if gid and lb:
            moments.setdefault(gid, []).append({
                "match_id": match_id, "round": round_no, "clip_id": cid, "player_id": c["player_id"], "t": c["t"], "t_end": c["t_end"],
                "reason": c["reason"],
                "title": lb["title"], "tags": [t for t in lb["tags"] if t not in ("touch", "on_ball_main")],
                "watchability": lb["watchability"], "video_url": f"/api/matches/{match_id}/clips/{cid}.mp4"})
    return clip_of_event, moments


# ---------------------------------------------------------------------------- one season per process
_cache: dict[tuple[str, str], Season] = {}
_cache_lock = threading.Lock()


def load_season(league_path: Path | str, root: Path | str) -> Season:
    """The season for this league file and match folder, built once per process (rebuilt if the league file changes)."""
    league_path, root = Path(league_path), Path(root)
    key = (str(league_path.resolve()), str(league_path.stat().st_mtime_ns))
    with _cache_lock:
        s = _cache.get(key)
        if s is None:
            s = Season.build(load_league(league_path), root)
            _cache.clear()
            _cache[key] = s
        return s
