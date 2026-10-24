"""Player profiles across the season, aggregated from the league's event streams and clips.

A profile is keyed on the global player id and holds: appearances and minutes, counts and per-90 rates for the stats a
scout reads (passing, chance creation, shooting, dribbling, defending), the league percentile of each rate among
players in the same position, a touch map oriented so the player's team attacks left to right, the player's best
moments across matches, and for every stat the events it was counted from, with the clip each event sits in
("verified by Regista": a number you can watch). Nothing here calls a model; the Foundry summary is the Profile
agent's job (planned in the Scout view work).

Besides the league's fixtures, a profile counts the matches of its confirmed claims (``regista.season.claims``): an
uploaded match in which the Studio confirmed that a player is this league player. Only the claimed player counts there,
under their global id; such matches have ``source: claim`` (and the ``claim_id``) in the profile's match list, league
fixtures ``source: league``. The league table counts fixtures only.

It also counts the Player view's finished uploads (``regista.player_api.uploaded_matches``): footage a player filmed,
cut by the vision workflow. Their team sheet already carries global ids, so no mapping is needed; only the uploader
counts there, with ``source: upload`` (and the ``upload_id``) in the match list.
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
from regista.season.league import bio, club_by_id, load_league, people
from regista.season.playing_time import played_seconds
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
    # Schema 0.2.0 (the league's generator since ratings; real footage has none of these yet):
    "aerial_duels_won": ("Aerial duels won", lambda e: e["event_type"] == "aerial_duel"),
    "aerial_duels_lost": ("Aerial duels lost", lambda e: e["event_type"] == "aerial_duel"),   # counted for related_player_id
    "through_balls": ("Through balls", lambda e: e["event_type"] == "pass" and "through_ball" in e.get("qualifiers", [])),
    "offsides": ("Offsides", lambda e: e["event_type"] == "offside"),
    "penalties_won": ("Penalties won", lambda e: e["event_type"] == "foul_won" and "penalty_won" in e.get("qualifiers", [])),
    "penalty_goals": ("Penalty goals", lambda e: e["event_type"] == "goal" and "penalty" in e.get("qualifiers", [])),
}
# Stats credited to the event's related_player_id (the other side of a contest), not its player_id.
RELATED_STATS = {"aerial_duels_lost"}
# Shown on profiles and scout cards, in this order; the rest are in the full table.
HEADLINE = ["goals", "assists", "shots", "key_passes", "take_ons_won", "nutmegs", "passes_completed", "tackles_won",
            "interceptions", "recoveries", "saves"]
RATIOS = {"pass_accuracy": ("Pass accuracy", "passes_completed", "passes"),
          "take_on_success": ("Take-on success", "take_ons_won", "take_ons"),
          "shot_accuracy": ("Shots on target", "shots_on_target", "shots"),
          "aerial_win": ("Aerial duels won %", "aerial_duels_won", "aerial_duels")}
# Counts made from other counts (not events), kept beside them so ratios and rates can use them.
DERIVED_COUNTS = {"aerial_duels": ("Aerial duels", ("aerial_duels_won", "aerial_duels_lost"))}
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
    extra: list[Record] = field(default_factory=list)    # confirmed claims' matches: {match_id, match_dir, players, claims}
    claimed: list[Record] = field(default_factory=list)  # the claimed matches that were counted, for the API and the trace
    uploads: list[Record] = field(default_factory=list)  # Player-view uploads: {match_id, match_dir, players, claims}
    uploaded: list[Record] = field(default_factory=list)  # the uploaded matches that were counted

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, league: Record, root: Path | str, claimed: list[Record] | None = None,
              uploaded: list[Record] | None = None) -> Season:
        """The season from the league's fixtures, plus the matches of ``claimed`` (``regista.season.claims.claimed_matches``:
        one row per confirmed claim) and of ``uploaded`` (``regista.player_api.uploaded_matches``: one row per finished
        Player-view upload)."""
        s = cls(league, Path(root), extra=_group_claims(claimed or []),
                uploads=_group_claims([{**u, "claim_id": u["upload_id"]} for u in uploaded or []]))
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
            local_to_global = {p["player_id"]: p.get("global_player_id") for p in header["players"]}
            team_club = {t["team_id"]: t.get("club_id") for t in header["teams"]}
            opp = {header["home_team_id"]: clubs[fx["away"]]["name"], header["away_team_id"]: clubs[fx["home"]]["name"]}
            self._table_row(table, fx, score)
            self.matches.append({"match_id": fx["match_id"], "round": fx["round"], "date": fx["date"], "home": fx["home"],
                                 "away": fx["away"], "score": score, "title": _manifest_title(d)})
            _add_match(acc, d, stream, local_to_global, round_no=fx["round"], date=fx["date"],
                       entry=lambda p: {"club_id": team_club[p["team_id"]], "opponent": opp[p["team_id"]], "source": "league"},
                       counts=lambda p, played=set(played_seconds(stream)): p["player_id"] in played)
        for e in self.extra:
            self._add_claimed(acc, e)
        for e in self.uploads:
            self._add_claimed(acc, e, source="upload")
        for gid, a in acc.items():
            self.profiles[gid] = _finish(a)
        _percentiles(self.profiles)
        self.table = sorted(table.values(), key=lambda r: (-r["points"], -(r["goals_for"] - r["goals_against"]), -r["goals_for"], r["club"]))
        for i, r in enumerate(self.table, start=1):
            r["position"] = i
            r["goal_difference"] = r["goals_for"] - r["goals_against"]

    def _add_claimed(self, acc: dict[str, Record], e: Record, source: str = "claim") -> None:
        """A confirmed claim's match: only the claimed players count, their per-match ids mapped to their global ids.
        The league table is untouched (the match is not a league fixture). A claimed player is counted for the whole
        match: the vision layer's team sheet says who was on the pitch, not when they came on. ``source="upload"``: a
        Player-view upload, the same way, its uploader in ``players`` and the upload id where a claim id would be."""
        d = Path(e["match_dir"])
        stream = list(iter_jsonl(d / "events.jsonl"))
        header = stream[0]
        local_to_global = {pid: gid for pid, gid in e["players"].items() if gid in acc}
        if not local_to_global:
            return
        teams = {t["team_id"]: t for t in header.get("teams", [])}
        other = {header.get("home_team_id"): header.get("away_team_id"), header.get("away_team_id"): header.get("home_team_id")}
        date = (header.get("meta") or {}).get("date")
        manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
        counted = {"match_id": e["match_id"], "players": local_to_global, "date": date, "title": manifest.get("title"),
                   "score": header.get("score", {})}
        if source == "upload":
            self.uploaded.append({**counted, "uploads": e["claims"]})
        else:
            self.claimed.append({**counted, "claims": e["claims"]})
        ref = "upload_id" if source == "upload" else "claim_id"

        def entry(p: Record) -> Record:
            gid = local_to_global[p["player_id"]]
            return {"club_id": acc[gid]["club_id"], "opponent": teams.get(other.get(p["team_id"]), {}).get("name"),
                    "team": teams.get(p["team_id"], {}).get("name"), "source": source, ref: e["claims"].get(p["player_id"])}

        _add_match(acc, d, stream, local_to_global, round_no=None, date=date, entry=entry,
                   counts=lambda p: p["player_id"] in local_to_global, derive_for=list(local_to_global))

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


def _group_claims(claimed: list[Record]) -> list[Record]:
    """One row per claimed match: {match_id, match_dir, players: {player_id: global_id}, claims: {player_id: claim_id}}."""
    by: dict[str, Record] = {}
    for c in claimed:
        m = by.setdefault(c["match_id"], {"match_id": c["match_id"], "match_dir": c["match_dir"], "players": {}, "claims": {}})
        if c["player_id"] not in m["players"] and c["global_id"] not in m["players"].values():
            m["players"][c["player_id"]] = c["global_id"]
            m["claims"][c["player_id"]] = c["claim_id"]
    return [by[k] for k in sorted(by)]


TOUCH_MAP_EVENTS = ("touch", "pass", "cross", "carry", "take_on", "shot", "tackle", "interception", "recovery", "clearance")


def _add_match(acc: dict[str, Record], d: Path, stream: list[Record], local_to_global: dict[str, str | None], *,
               round_no: int | None, date: str | None, entry: Any, counts: Any, derive_for: list[str] | None = None) -> None:
    """Add one match to the accumulators: appearances and minutes (players ``counts`` accepts), stat counts with their
    evidence, the touch map, and the labelled moments. ``entry`` gives the per-match row's club and opponent."""
    header = stream[0]
    match_id = d.name  # the folder is the match id the API serves (an upload may be stored under a new one)
    score = header.get("score", {})
    minutes = sum(p["t_end"] - p["t"] for p in header.get("periods", [])) / 60.0
    on_pitch = played_seconds(stream)
    ltr = {p["period"]: p.get("left_to_right_team_id") for p in header.get("periods", [])}
    clip_of_event, moments = _clips_and_moments(d, local_to_global, stream=stream, round_no=round_no, derive_for=derive_for)
    for p in header["players"]:
        gid = local_to_global.get(p["player_id"])
        if gid and gid in acc and counts(p):
            a = acc[gid]
            a["appearances"] += 1
            # time on the pitch: substitutions and red cards (schema 0.2.0) cut it; a stream without them, or a
            # claimed player the team sheet does not start, counts the whole match as before
            a["minutes"] += on_pitch[p["player_id"]] / 60.0 if p["player_id"] in on_pitch else minutes
            a["matches"].append({"match_id": match_id, "round": round_no, "date": date, "player_id": p["player_id"],
                                 **entry(p), "home": p["team_id"] == header.get("home_team_id"),
                                 # a vision match whose header has no score (nothing counted the goals) shows none
                                 "score": f"{score.get('t_home', 0)}–{score.get('t_away', 0)}" if score else None})
    for rec in stream:
        if rec["type"] != "event":
            continue
        other = local_to_global.get(rec.get("related_player_id") or "")
        if other and other in acc:
            for key in RELATED_STATS:
                if STATS[key][1](rec):
                    _count(acc[other], key, rec, match_id, rec["related_player_id"], clip_of_event)
        if not rec.get("player_id"):
            continue
        gid = local_to_global.get(rec["player_id"])
        if not gid or gid not in acc:
            continue
        a = acc[gid]
        for key, (_label, test) in STATS.items():
            if key in RELATED_STATS:
                continue
            if test(rec):
                a["counts"][key] += 1
                if len(a["evidence"][key]) < MAX_EVIDENCE:
                    a["evidence"][key].append({"match_id": match_id, "player_id": rec["player_id"], "event_id": rec["id"], "t": rec["t"],
                                               "clip_id": clip_of_event.get((rec["player_id"], rec["id"]))})
        pt = rec.get("pitch")
        if pt and rec["event_type"] in TOUCH_MAP_EVENTS:
            period = (rec.get("clock") or {}).get("period", 1)
            team_ltr = (ltr.get(period) or header.get("home_team_id")) == rec["team_id"]
            x, y = (pt["x"], pt["y"]) if team_ltr else (PITCH_L - pt["x"], PITCH_W - pt["y"])
            gx = min(GRID_X - 1, max(0, int(x / PITCH_L * GRID_X)))
            gy = min(GRID_Y - 1, max(0, int(y / PITCH_W * GRID_Y)))
            a["grid"][gy][gx] += 1
    for gid, ms in moments.items():
        if gid in acc:
            acc[gid]["moments"] += ms


def _count(a: Record, key: str, rec: Record, match_id: str, player_id: str, clip_of_event: dict[tuple[str, str], str]) -> None:
    a["counts"][key] += 1
    if len(a["evidence"][key]) < MAX_EVIDENCE:
        a["evidence"][key].append({"match_id": match_id, "player_id": player_id, "event_id": rec["id"], "t": rec["t"],
                                   "clip_id": clip_of_event.get((player_id, rec["id"]))})


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


CARD_BIO = ("age", "height_cm", "preferred_foot", "nationality")  # the public bio on a card (never the hidden ratings)


def card(p: Record) -> Record:
    """What a scout list shows: who, where, how much, and the headline rates."""
    keep = ("global_id", "name", "club_id", "club", "short_name", "kit", "kit_number", "position", "appearances", "minutes",
            *CARD_BIO)
    return {**{k: p[k] for k in keep}, "headline": {k: {"label": STATS[k][0], "count": p["counts"][k], "per90": p["per90"][k],
                                                        "percentile": p["percentiles"].get(k)} for k in HEADLINE},
            "ratios": p["ratios"], "best_moment": p["moments"][0] if p["moments"] else None}


def _empty(person: Record) -> Record:
    return {"global_id": person["global_id"], "name": person["name"], "kit_number": person["kit_number"],
            "position": person["position"], "starter": person["starter"], "club_id": person["club_id"], "club": person["club"],
            "short_name": person["short_name"], "kit": person["kit"], **bio(person),
            "appearances": 0, "minutes": 0.0, "matches": [], "counts": {k: 0 for k in STATS},
            "evidence": {k: [] for k in STATS}, "grid": [[0] * GRID_X for _ in range(GRID_Y)], "moments": []}


def _finish(a: Record) -> Record:
    for key, (_label, parts) in DERIVED_COUNTS.items():
        a["counts"][key] = sum(a["counts"][k] for k in parts)
    m = a["minutes"]
    a["minutes"] = round(m, 1)
    a["per90"] = {k: round(v * 90.0 / m, 2) if m else 0.0 for k, v in a["counts"].items()}
    a["ratios"] = {k: (round(a["counts"][num] / a["counts"][den], 3) if a["counts"][den] else None) for k, (_l, num, den) in RATIOS.items()}
    a["stat_labels"] = {k: lbl for k, (lbl, _t) in STATS.items()} | {k: lbl for k, (lbl, _n, _d) in RATIOS.items()} \
        | {k: lbl for k, (lbl, _p) in DERIVED_COUNTS.items()}
    # A claimed match has no round: it sorts after the league's rounds at equal watchability.
    a["moments"].sort(key=lambda r: (-r["watchability"], r["round"] is None, r["round"] or 0, r["t"]))
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


def _clips_and_moments(d: Path, local_to_global: dict[str, str | None], *, stream: list[Record] | None = None,
                       round_no: int | None = None, derive_for: list[str] | None = None,
                       ) -> tuple[dict[tuple[str, str], str], dict[str, list[Record]]]:
    """(player id, event id) -> that player's on-ball clip the event sits in, and global id -> the player's labelled
    moments in this match. Keyed by player too: another player's clip of the same possession is not this one's evidence.
    Players in ``derive_for`` who have no clips on disk (a claimed player in an upload cut for someone else) get theirs
    cut now by the clip rule, as GET /clips?player= does."""
    clips, labels = {}, {}
    p = d / "clips.jsonl"
    if p.exists():
        for r in iter_jsonl(p):
            (clips.__setitem__(r["id"], r) if r["type"] == "clip" else labels.__setitem__(r["clip_id"], r))
    missing = [pid for pid in (derive_for or []) if pid not in {c["player_id"] for c in clips.values()}]
    if missing:
        from regista.clips import derive_clips

        for pid in missing:
            try:
                new_clips, new_labels = derive_clips(stream if stream is not None else list(iter_jsonl(d / "events.jsonl")), pid)
            except ValueError:
                continue
            clips.update({c["id"]: c for c in new_clips})
            labels.update({lb["clip_id"]: lb for lb in new_labels})
    clip_of_event: dict[tuple[str, str], str] = {}
    moments: dict[str, list[Record]] = {}
    match_id = d.name
    if round_no is None and (d / "manifest.json").exists():
        round_no = json.loads((d / "manifest.json").read_text()).get("round")
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


def load_season(league_path: Path | str, root: Path | str, claimed: list[Record] | None = None,
                uploaded: list[Record] | None = None) -> Season:
    """The season for this league file, match folder, confirmed claims (``regista.season.claims.claimed_matches``) and
    finished Player-view uploads (``regista.player_api.uploaded_matches``), built once per process: rebuilt when the
    league file changes, a claim is confirmed or withdrawn, or an upload finishes (or its match changes)."""
    from regista.season.claims import fingerprint

    league_path, root = Path(league_path), Path(root)
    claimed, uploaded = list(claimed or []), list(uploaded or [])
    key = (str(league_path.resolve()), str(league_path.stat().st_mtime_ns), fingerprint(claimed), fingerprint(uploaded))
    with _cache_lock:
        s = _cache.get(key)
        if s is None:
            s = Season.build(load_league(league_path), root, claimed, uploaded)
            _cache.clear()
            _cache[key] = s
        return s


def invalidate() -> None:
    """Forget the built season, so the next read rebuilds it (the Profile agent calls this when it refreshes)."""
    with _cache_lock:
        _cache.clear()


def refresh(league_path: Path | str, root: Path | str, claimed: list[Record], global_ids: list[str],
            uploaded: list[Record] | None = None) -> Record:
    """Rebuild the season now (league fixtures, confirmed claims, finished uploads) and say what each of ``global_ids``
    looks like afterwards: the Profile agent's job when a match with global ids or confirmed claims goes through the
    workflow."""
    league_path = Path(league_path)
    if not league_path.exists():
        return {"skipped": f"no league at {league_path}", "profiles": []}
    invalidate()
    s = load_season(league_path, root, claimed, uploaded)
    out = []
    for gid in dict.fromkeys(global_ids):
        p = s.player(gid)
        if p is None:
            out.append({"global_id": gid, "known": False})
            continue
        out.append({"global_id": gid, "known": True, "name": p["name"], "appearances": p["appearances"], "minutes": p["minutes"],
                    "claimed_matches": [m["match_id"] for m in p["matches"] if m.get("source") == "claim"],
                    "uploaded_matches": [m["match_id"] for m in p["matches"] if m.get("source") == "upload"]})
    return {"profiles": out, "league_matches": len(s.matches), "claimed_matches": len(s.claimed), "uploaded_matches": len(s.uploaded)}
