"""The Scout terminal's engine over the whole catalogue: the same 127 player metrics and 19 team-style metrics, with every
percentile drawn from a pool of peers at the same level (design.md §7).

**Structure.** One ``SeasonMetrics`` per competition (``competitions``), then pools across them:

- England semi-pro men is the Regista League's own ``SeasonMetrics``, the very object ``load_metrics`` returns to the
  existing endpoints: its fitted xT, its qualifying minutes (a third of a club's minutes), its numbers.
- Every other competition is ``SeasonMetrics.from_streams(comp, streams, xt=england.xt, min_minutes_floor=45,
  min_pool=5)``: England's fitted xT grid (3-8 matches cannot fit one; a fixed reference grid is how xT is used
  elsewhere), qualifying minutes of at least 45 (one and a half synthetic matches: a club with one uploaded match leaves
  its players unqualified, as there is not enough footage), and no percentile from fewer than 5 peers.

A player-competition row is one ``PlayerSeason`` in one competition. A career player (two competitions) has two rows and
no merged per-90: rates from two levels would mix pools. His career block sums what can be summed (minutes, appearances,
counts) and says so.

**Pools and scopes.** A row qualifies for a metric under its own competition's rule (minutes, ratio attempts). A pool is
the qualified rows of one position in a scope:

- ``level`` (the default): the same tier, age group and gender. England and Germany semi-pro men share a pool, so an
  England player's level percentile can differ from his competition percentile, legitimately; every number says which
  pool it came from.
- ``competition``: one competition. For England this is today's percentile, exactly (its own rule, pools of 2 or more).
- ``all``: every tier and age group of one gender (genders never mix: their physical scales differ by design). Levels
  differ, so a response in this scope warns.

FBref's percentile rule throughout (``fbref_percentile``, inverted where lower is better). A pool under ``MIN_POOL``
gives no percentile and says why; a pool under ``SMALL_POOL`` is flagged ``small``.

**Reliability.** ``noisy`` reads England's own table (``data/season/reliability.json``) for England in competition scope,
as the existing endpoints do, and the row's level table (``data/catalogue/reliability.json``, measured on full
regenerated seasons of the level) everywhere else. A row's own flag adjusts the level's split-half r (measured on
half-seasons of ``median_half_minutes``) to the row's minutes with Spearman-Brown, r_k = k r / (1 + (k - 1) r) with
k = minutes / median_half_minutes, and is noisy when r_k is below 0.3: a 60-minute upload is noisier than half a season.

**Ranking across levels.** A list that mixes levels (``order_rows``) ranks by each row's percentile within its own pool
by default, never by raw values from different levels, and keeps genders on separate boards; ranking by raw value
stays available (``rank_by="value"``).

**Never served:** the hidden ratings and the competition files' ``level`` block. Everything here reads the event
streams, the physical records and the public bio (``regista.season.league.people`` drops ``attributes``).
"""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path
from typing import Any

from regista.catalogue import store
from regista.catalogue.realism import WOMEN_ZONE_NOTE, ZONE_KEYS
from regista.catalogue.taxonomy import BY_ID, ENGLAND_ID
from regista.season.metrics import (CATALOGUE, DEFAULT_COLUMNS, SIMILAR_DEFAULT, SIMILARITY_TEMPLATE, TEAM_CATALOGUE,
                                    ClipIndex, PlayerSeason, SeasonMetrics, fbref_percentile, rank_value)
from regista.season.reliability import NOISE_R

Record = dict[str, Any]

MIN_POOL = 5          # fewer qualified peers than this: no percentile (England's own competition scope keeps its rule: 2)
SMALL_POOL = 15       # fewer than this: the pool is flagged small
FLOOR = 45.0          # qualifying minutes are at least this outside England (one and a half 30-minute matches)
SMALL_TEAM_SAMPLE = 3  # a club with fewer uploaded matches than this has a small team-style sample
SCOPES = ("level", "competition", "all")
LABEL_KEYS = ("competition_id", "name", "country", "region", "tier", "age_group", "gender", "format", "season", "coverage")

POOL_RULE = ("FBref's percentile rank (the mean of the share of the pool strictly below and the share at or below), "
             "inverted where lower is better, among qualified peers in the same position: scope level (default) pools "
             "the same tier, age group and gender; competition pools one competition; all pools every tier and age group "
             "of one gender. A row qualifies under its own competition's rule: a third of the minutes of the competition's "
             f"busiest club (FBref's 30 minutes per squad game), at least {FLOOR:g} outside England, and the ratio minimums scaled to the "
             f"competition's minutes. No percentile from fewer than {MIN_POOL} peers (England's own competition scope "
             f"keeps the Regista League's rule, 2); fewer than {SMALL_POOL} is flagged small.")
RELIABILITY_NOTE = ("noisy: split-half reliability below 0.3 within a role. England's competition scope reads the Regista "
                    "League's table; every other number reads its level's table, measured on full regenerated seasons of "
                    "the level, and adjusts its r to the row's own minutes (Spearman-Brown: r_k = k r / (1 + (k - 1) r), "
                    "k = the row's minutes / the level's median half-season minutes; r_at_minutes), so a short upload is "
                    "flagged where half a season would not be. A list of noisy metrics without a row reads the level's "
                    "table at half a season.")
ALL_WARNING = ("rows from different levels: read each percentile against its own pool. Raw event rates barely encode "
               "level (both sides of a synthetic match scale together, so pass completion, ball losses and goals come out "
               "similar at every level); compare players through their percentiles within their pools.")
RANK_BY = ("pool", "value")
RANK_RULE = ("rank_by pool (the default when rows come from more than one level): each row's percentile within its own "
             "pool, best first, then rows from pools that are not small, then more minutes, then the value; rows without "
             "a percentile are listed after, unranked. rank_by value: the raw value, best first (the default within one "
             "level). order (asc or desc) is the raw direction in both modes: desc lists the largest numbers first even "
             "where lower is better (in pool mode, the lowest percentiles of such a metric first); without order, best "
             "first. Genders are never ranked together: a list holding both has one board per gender (each row's board; "
             "boards gives each board's size, its offset in the list and its top rows, so no board hides behind another).")
GENDER_ORDER = ("men", "women")
BOARD_TOP = 5          # each gender board's top rows carried beside a page (boards[].top), so no board hides behind another
CAREER_NOTE = ("Counts and minutes are summed across competitions; per-90 rates and percentiles stay per competition, "
               "because rates from two levels would mix pools.")
SYNTHETIC_NOTE = ("Synthetic data: invented players, clubs and competition names, generated by Regista. Countries, regions "
                  "and levels are classification labels.")


class CatalogueMetrics:
    """Every competition's metrics and the pools across them. Build once (``load_catalogue_metrics``), then query."""

    MIN_POOL = MIN_POOL
    SMALL_POOL = SMALL_POOL

    def __init__(self, index: Record, comps: dict[str, Record], metrics: dict[str, SeasonMetrics], reliability: Record,
                 realism_checks: Record | None = None):
        from regista.season.league import people

        self.index = index
        self.realism_checks = realism_checks if realism_checks is not None else {"bands": [], "orders": [],
                                                                                  "stale": "no realism verdicts loaded"}
        self.order = [e["competition_id"] for e in index["competitions"] if e["competition_id"] in metrics]
        self.labels = {e["competition_id"]: {k: e.get(k) for k in LABEL_KEYS} for e in index["competitions"]}
        self.level = {cid: BY_ID[cid].level_key for cid in self.order}
        self.comps = comps
        self.metrics = metrics
        self.reliability = reliability
        self.careers = {c["global_id"]: c for c in index.get("careers", [])}
        self.people: dict[str, list[tuple[str, Record]]] = {}
        for cid in self.order:
            for gid, p in people(comps[cid]).items():
                self.people.setdefault(gid, []).append((cid, p))
        for gid, car in self.careers.items():   # a career reads in its own order: where the player came from first
            if gid in self.people:
                rank = {c: i for i, c in enumerate(car["competitions"])}
                self.people[gid].sort(key=lambda e: rank.get(e[0], len(rank)))
        england_uploads = next((e.get("uploads", {}) for e in index["competitions"] if e["competition_id"] == ENGLAND_ID), {})
        self.uploads: dict[str, Record] = {mid: dict(u) for mid, u in england_uploads.items()}
        for cid in self.order:
            for fx in comps[cid]["fixtures"]:
                if "camera" in fx:
                    self.uploads[fx["match_id"]] = {"uploader": fx["uploader"], "camera": fx["camera"]}
        self._pools: dict[tuple, list[float]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ scopes and pools
    def scope_competitions(self, cid: str, scope: str) -> list[str]:
        """The competitions a row of ``cid`` is compared with in ``scope``, in the index's order."""
        if scope == "competition":
            return [cid]
        if scope == "level":
            return [c for c in self.order if self.level[c] == self.level[cid]]
        if scope == "all":
            return [c for c in self.order if self.labels[c]["gender"] == self.labels[cid]["gender"]]
        raise ValueError(f"unknown scope {scope!r}: one of {', '.join(SCOPES)}")

    def _pool_id(self, cid: str, scope: str) -> tuple:
        lab = self.labels[cid]
        if scope == "competition":
            return ("competition", cid)
        if scope == "level":
            return ("level", lab["tier"], lab["age_group"], lab["gender"])
        if scope == "all":
            return ("all", lab["gender"])
        raise ValueError(f"unknown scope {scope!r}: one of {', '.join(SCOPES)}")

    def pool_values(self, cid: str, key: str, position: str, scope: str = "level") -> list[float]:
        """The sorted rank values of the qualified rows in this pool (a row qualifies under its own competition's rule)."""
        m = CATALOGUE[key]
        if scope == "competition":
            return self.metrics[cid].peer_pools.get((key, position), [])
        pid = (*self._pool_id(cid, scope), key, position)
        hit = self._pools.get(pid)
        if hit is None:
            vals: list[float] = []
            if position in m.positions and m.kind != "total":
                for c in self.scope_competitions(cid, scope):
                    sm = self.metrics[c]
                    vals += [rank_value(ps.values[key]) for ps in sm.players.values()
                             if ps.info["position"] == position and sm.qualified(ps, m)]
            hit = sorted(vals)
            with self._lock:
                self._pools[pid] = hit
        return hit

    def min_size(self, cid: str, scope: str) -> int:
        return self.metrics[cid].min_pool if scope == "competition" else MIN_POOL

    def pool(self, cid: str, key: str, position: str, scope: str = "level") -> Record:
        """What a number's percentile was drawn from: the scope, the level, the position, the size and its flags."""
        m = CATALOGUE[key]
        lab = self.labels[cid]
        size = len(self.pool_values(cid, key, position, scope))
        need = self.min_size(cid, scope)
        if m.kind == "total":
            reason = "a season total: not ranked"
        elif position not in m.positions:
            reason = "not ranked for this position"
        elif size < need:
            reason = f"fewer than {need} qualified peers"
        else:
            reason = None
        out: Record = {"scope": scope, "tier": lab["tier"] if scope != "all" else None,
                       "age_group": lab["age_group"] if scope != "all" else None, "gender": lab["gender"],
                       "position": position, "size": size, "small": size < SMALL_POOL, "min_size": need,
                       "competitions": self.scope_competitions(cid, scope), "reason": reason}
        if scope == "competition":
            out["competition_id"] = cid
        return out

    def percentile(self, cid: str, ps: PlayerSeason, key: str, scope: str = "level") -> float | None:
        """FBref's percentile of this row among its pool, or None (not qualified, not ranked, or too small a pool)."""
        if scope == "competition":
            return ps.percentiles.get(key)
        m = CATALOGUE[key]
        sm = self.metrics[cid]
        pos = ps.info["position"]
        if m.kind == "total" or pos not in m.positions or not sm.qualified(ps, m):
            return None
        vals = self.pool_values(cid, key, pos, scope)
        if len(vals) < MIN_POOL:
            return None
        pct = fbref_percentile(vals, rank_value(ps.values[key]))
        return round(100.0 - pct if m.higher_is_better is False else pct)

    def level_noisy(self, level: str, key: str) -> bool:
        return bool((((self.reliability.get("levels") or {}).get(level) or {}).get("metrics", {}).get(key) or {}).get("noisy"))

    def reliability_at(self, cid: str, key: str, minutes: float) -> float | None:
        """The level's split-half r adjusted to ``minutes`` with Spearman-Brown (None without a measured r)."""
        lv = (self.reliability.get("levels") or {}).get(self.level[cid]) or {}
        r = ((lv.get("metrics") or {}).get(key) or {}).get("r")
        half = lv.get("median_half_minutes")
        if r is None or not half or minutes <= 0:
            return None
        if r <= 0:
            return float(r)
        k = minutes / half
        return k * r / (1.0 + (k - 1.0) * r)

    def noisy(self, cid: str, key: str, scope: str = "level", minutes: float | None = None) -> bool:
        """England's own table in competition scope (as the existing endpoints read it). Elsewhere the row's level table:
        with ``minutes``, its r adjusted to them (``reliability_at``) and noisy below 0.3; without, the level's own flag
        (half a season)."""
        if scope == "competition" and cid == ENGLAND_ID:
            return self.metrics[cid].noisy(key)
        if minutes is not None:
            r_k = self.reliability_at(cid, key, minutes)
            if r_k is not None:
                return r_k < NOISE_R
        return self.level_noisy(self.level[cid], key)

    def reliability_entry(self, cid: str, key: str, scope: str = "level") -> Record | None:
        if scope == "competition" and cid == ENGLAND_ID:
            return self.metrics[cid].reliability.get("metrics", {}).get(key)
        lv = (self.reliability.get("levels") or {}).get(self.level[cid]) or {}
        return lv.get("metrics", {}).get(key)

    # ------------------------------------------------------------------ one number
    def row(self, cid: str, gid: str) -> PlayerSeason | None:
        sm = self.metrics.get(cid)
        return sm.players.get(gid) if sm else None

    def sample(self, cid: str, ps: PlayerSeason) -> Record:
        sm = self.metrics[cid]
        club = ps.info["club_id"]
        return {"competition_id": cid, "minutes": round(ps.minutes, 1), "appearances": ps.appearances,
                "qualifying_minutes": round(sm.min_minutes, 1), "competition_matches": len(sm.match_rows),
                "club_matches": sum(1 for r in sm.match_rows if club in (r["home"], r["away"]))}

    def cell(self, cid: str, gid: str, key: str, scope: str = "level") -> Record:
        """One metric for one player-competition row: the competition engine's cell (value, count, qualified), with the
        percentile, ``peers`` and ``noisy`` of the scope's pool, the moments behind it, the pool and the sample."""
        sm = self.metrics[cid]
        ps = sm.players[gid]
        pos = ps.info["position"]
        pool = self.pool(cid, key, pos, scope)
        out = sm.cell(ps, key)
        out["percentile"] = self.percentile(cid, ps, key, scope)
        out["peers"] = pool["size"]
        out["noisy"] = self.noisy(cid, key, scope, ps.minutes)
        r_k = None if (scope == "competition" and cid == ENGLAND_ID) else self.reliability_at(cid, key, ps.minutes)
        out["r_at_minutes"] = None if r_k is None else round(r_k, 3)
        out["evidence_total"] = sm.evidence_total(ps, key)
        out["pool"] = pool
        out["sample"] = self.sample(cid, ps)
        if self.labels[cid]["gender"] == "women" and key in ZONE_KEYS:
            out["threshold_note"] = WOMEN_ZONE_NOTE
        return out

    def evidence(self, cid: str, gid: str, key: str, limit: int | None = None, offset: int = 0) -> Record:
        """The events behind a number, from its competition's engine: each links its match in the Clip view."""
        sm = self.metrics[cid]
        return sm.evidence(sm.players[gid], key, limit, offset)

    def describe(self, key: str, cid: str, scope: str = "level") -> Record:
        """A metric's public description in one competition: its competition's ratio minimum, the reliability its numbers
        read in this scope, and how far it is checked for realism at this level (``regista.catalogue.realism``)."""
        from regista.catalogue.realism import realism

        out = self.metrics[cid].describe(key)
        out["reliability"] = self.reliability_entry(cid, key, scope)
        out["reliability_source"] = ("Regista League (England semi-pro men)" if scope == "competition" and cid == ENGLAND_ID
                                     else f"level {self.level[cid]}")
        out["realism"] = realism(key, cid, self.realism_checks)
        return out

    # ------------------------------------------------------------------ rows
    def labels_of(self, cid: str) -> Record:
        lab = self.labels[cid]
        return {"competition_id": cid, "competition": lab["name"], "country": lab["country"], "tier": lab["tier"],
                "age_group": lab["age_group"], "gender": lab["gender"]}

    def card(self, cid: str, ps: PlayerSeason) -> Record:
        """A row as a list shows it: who, where, how much, at which level, and whether the player has a career."""
        sm = self.metrics[cid]
        gid = ps.info["global_id"]
        out = {**sm.card(ps), **self.labels_of(cid), "career": len(self.people.get(gid, [])) > 1}
        if cid != ENGLAND_ID:
            out["profile_url"] = None   # the existing profile page serves England's players only (the UI round links these)
        return out

    def player_rows(self, gid: str) -> list[tuple[str, PlayerSeason]]:
        return [(cid, self.metrics[cid].players[gid]) for cid, _p in self.people.get(gid, [])
                if gid in self.metrics[cid].players]

    def select(self, *, tier: str | None = None, age_group: str | None = None, gender: str | None = None,
               country: str | None = None, competition: str | None = None, position: str | None = None,
               role: str | None = None, q: str | None = None, min_minutes: float | None = None, age_min: int | None = None,
               age_max: int | None = None, foot: str | None = None, camera: str | None = None,
               career: bool | None = None) -> list[tuple[str, PlayerSeason]]:
        """Player-competition rows across the catalogue, filtered. ``min_minutes`` None: each row's own competition's
        qualifying minutes; ``camera``: rows with an appearance in a match filmed on that camera type."""
        out = []
        for cid in self.order:
            lab = self.labels[cid]
            if (tier and lab["tier"] != tier) or (age_group and lab["age_group"] != age_group) or \
                    (gender and lab["gender"] != gender) or (competition and cid != competition) or \
                    (country and lab["country"].lower() != country.lower()):
                continue
            for ps in self.metrics[cid].rows(position=position, role=role, min_minutes=min_minutes, age_min=age_min,
                                             age_max=age_max, foot=foot, q=q):
                if camera and not any((self.uploads.get(r["match_id"]) or {}).get("camera") == camera for r in ps.matches):
                    continue
                if career is not None and (len(self.people.get(ps.info["global_id"], [])) > 1) != career:
                    continue
                out.append((cid, ps))
        return out

    def sort(self, rows: list[tuple[str, PlayerSeason]], key: str, order: str | None = None) -> list[tuple[str, PlayerSeason]]:
        """By a metric's value, best first (or ``order`` "asc" / "desc"); rows without a value last."""
        m = CATALOGUE[key]
        desc = (m.higher_is_better is not False) if order is None else order == "desc"
        have = [r for r in rows if r[1].values.get(key) is not None]
        none = [r for r in rows if r[1].values.get(key) is None]
        have.sort(key=lambda r: (-r[1].values[key] if desc else r[1].values[key], r[1].info["name"], r[0]))
        return have + sorted(none, key=lambda r: (r[1].info["name"], r[0]))

    def rank_mode(self, rows: list[tuple[str, PlayerSeason]], key: str, rank_by: str | None = None) -> str:
        """``rank_by``, else pool when the rows come from more than one level (value within one level, and always for a
        season total, which has no percentile)."""
        if rank_by:
            if rank_by not in RANK_BY:
                raise ValueError(f"unknown rank_by {rank_by!r}: one of {', '.join(RANK_BY)}")
            return "value" if CATALOGUE[key].kind == "total" else rank_by
        if CATALOGUE[key].kind == "total":
            return "value"
        return "pool" if len({self.level[c] for c, _ps in rows}) > 1 else "value"

    def order_rows(self, rows: list[tuple[str, PlayerSeason]], key: str, scope: str = "level", order: str | None = None,
                   rank_by: str | None = None) -> tuple[list[tuple[str, PlayerSeason]], str, list[str] | None, set]:
        """(rows in order, the rank mode, the gender boards or None, the (cid, gid) of rows ranked by percentile).

        ``pool``: by each row's percentile in ``scope``, then rows whose pool is not small, then more minutes, then the
        value; rows without a percentile follow, by value. ``value``: ``sort``. ``order`` means the same in both modes: the
        raw direction ("desc": the largest numbers first, even where lower is better, as ``sort`` does), so in pool mode a
        lower-is-better metric's "desc" lists the lowest (oriented) percentiles first; with no ``order``, best first.
        Rows of both genders are grouped into one board per gender (men, then women): genders are never ranked together."""
        mode = self.rank_mode(rows, key, rank_by)
        ranked: set = set()
        if mode == "value":
            ordered = self.sort(rows, key, order)
        else:
            m = CATALOGUE[key]
            best_high = m.higher_is_better is not False
            # the percentile is oriented (high = good); an explicit order is the raw direction, as in value mode
            worst_first = False if order is None else (order == "asc") == best_high
            pct: dict[tuple, float | None] = {}
            small: dict[tuple, bool] = {}
            for c, ps in rows:
                gid = ps.info["global_id"]
                pct[(c, gid)] = self.percentile(c, ps, key, scope)
                small[(c, gid)] = len(self.pool_values(c, key, ps.info["position"], scope)) < SMALL_POOL
            have = [r for r in rows if pct[(r[0], r[1].info["global_id"])] is not None]
            none = [r for r in rows if pct[(r[0], r[1].info["global_id"])] is None]

            def key_of(r: tuple[str, PlayerSeason]) -> tuple:
                c, ps = r
                k = (c, ps.info["global_id"])
                v = ps.values.get(key) or 0.0
                p = pct[k]
                return (p if worst_first else -p, small[k], -ps.minutes, -v if best_high != worst_first else v,
                        ps.info["name"], c)

            have.sort(key=key_of)
            ranked = {(c, ps.info["global_id"]) for c, ps in have}
            ordered = have + self.sort(none, key, order)
        genders = [g for g in GENDER_ORDER if any(self.labels[c]["gender"] == g for c, _ps in rows)]
        if len(genders) > 1:
            ordered.sort(key=lambda r: GENDER_ORDER.index(self.labels[r[0]]["gender"]))   # stable: each board keeps its order
            return ordered, mode, genders, ranked
        return ordered, mode, None, ranked

    # ------------------------------------------------------------------ a player across the catalogue
    def career(self, gid: str) -> list[Record]:
        """Every competition the person is in a squad of (season 2026/27), with the club, the shirt, and what they played:
        appearances, minutes, the first and last match, the matches."""
        out = []
        for cid, p in self.people.get(gid, []):
            ps = self.metrics[cid].players.get(gid)
            matches = ps.matches if ps else []
            dates = sorted(r["date"] for r in matches)
            out.append({**self.labels_of(cid), "region": self.labels[cid]["region"], "season": self.labels[cid]["season"],
                        "club_id": p["club_id"], "club": p["club"], "short_name": p["short_name"],
                        "kit_number": p["kit_number"], "position": p["position"], "role": p.get("role"),
                        "starter": p.get("starter"), "appearances": ps.appearances if ps else 0,
                        "minutes": round(ps.minutes, 1) if ps else 0.0,
                        "qualified": bool(ps) and ps.minutes >= self.metrics[cid].min_minutes,
                        "first_match": dates[0] if dates else None, "last_match": dates[-1] if dates else None,
                        "matches": [r["match_id"] for r in matches]})
        return out

    def overall(self, gid: str) -> Record:
        """What adds up across competitions: appearances, minutes and the counts behind every per-90 metric. No merged
        per-90 or percentile (``CAREER_NOTE``)."""
        rows = self.player_rows(gid)
        totals: dict[str, float] = {}
        for key, m in CATALOGUE.items():
            if m.kind == "per90":
                totals[key] = round(sum(ps.totals.get(key, 0.0) for _c, ps in rows), 3)
        return {"competitions": len(self.people.get(gid, [])), "competitions_played": len(rows),
                "appearances": sum(ps.appearances for _c, ps in rows), "minutes": round(sum(ps.minutes for _c, ps in rows), 1),
                "totals": totals, "note": CAREER_NOTE}

    def player(self, gid: str, scope: str = "level", metrics: list[str] | None = None) -> Record | None:
        """The player across the catalogue: bio, career, what adds up, and per competition the metrics (default: the
        position's default columns) with their pools. None for an unknown id."""
        entries = self.people.get(gid)
        if not entries:
            return None
        from regista.season.league import bio

        person = entries[0][1]
        b = {k: v for k, v in bio(person).items() if k != "date_of_birth"}
        rows = []
        for cid, ps in self.player_rows(gid):
            keys = metrics or list(DEFAULT_COLUMNS.get(ps.info["position"], DEFAULT_COLUMNS[None]))
            rows.append({**self.labels_of(cid), "club_id": ps.info["club_id"], "club": ps.info["club"],
                         "position": ps.info["position"], "role": ps.info.get("role"), "scope": scope,
                         "sample": self.sample(cid, ps), "metrics": {k: self.cell(cid, gid, k, scope) for k in keys}})
        return {"global_id": gid, "name": person["name"], "bio": b, "career": self.career(gid),
                "career_story": (self.careers.get(gid) or {}).get("story"), "overall": self.overall(gid), "rows": rows,
                "scope": scope, "warning": ALL_WARNING if scope == "all" else None, "pool_rule": POOL_RULE,
                "reliability_note": RELIABILITY_NOTE, "synthetic": True, "note": SYNTHETIC_NOTE}

    # ------------------------------------------------------------------ similar players
    def similar(self, cid: str, gid: str, scope: str = "level", n: int = SIMILAR_DEFAULT) -> Record:
        """Players with the most similar per-90 profile (FBref's summary template; the keeper template for keepers): the
        cosine of standardised vectors among qualified rows in the same position.

        ``competition``: the competition engine's own ``similar`` (England: exactly the existing endpoint's). ``level``:
        candidates from the whole level, standardised on the level's pool. ``all``: candidates from every level of the
        gender, each row standardised on its own level's pool, so similarity compares how a player stands out at his
        level, not raw volumes that differ between levels. The same person's other row is never his own match."""
        sm = self.metrics[cid]
        target = sm.players[gid]
        pos = target.info["position"]
        if scope == "competition":
            base = sm.similar(gid, n)
            for row in base["similar"]:
                row.update(self.labels_of(cid))
                if cid != ENGLAND_ID:
                    row["profile_url"] = None
            return {**base, "competition_id": cid, "scope": scope, "z_basis": "competition", "warning": None}
        keys = SIMILARITY_TEMPLATE["GK" if pos == "GK" else "outfield"]
        cands = [(c, ps) for c in self.scope_competitions(cid, scope) for ps in self.metrics[c].players.values()
                 if ps.info["position"] == pos and ps.minutes >= self.metrics[c].min_minutes and ps.info["global_id"] != gid]
        stats: dict[str, dict[str, tuple[float, float]]] = {}

        def level_stats(level: str) -> dict[str, tuple[float, float]]:
            if level not in stats:
                pool = [ps for c in self.order if self.level[c] == level for ps in self.metrics[c].players.values()
                        if ps.info["position"] == pos and ps.minutes >= self.metrics[c].min_minutes]
                if level == self.level[cid] and target not in pool:
                    pool.append(target)
                st = {}
                for k in keys:
                    vals = [ps.values[k] for ps in pool if ps.values.get(k) is not None]
                    mu = sum(vals) / len(vals) if vals else 0.0
                    sd = math.sqrt(sum((v - mu) * (v - mu) for v in vals) / len(vals)) if vals else 0.0
                    st[k] = (mu, sd)
                stats[level] = st
            return stats[level]

        def z(c: str, ps: PlayerSeason) -> list[float]:
            st = level_stats(self.level[c])
            return [0.0 if ps.values.get(k) is None or not st[k][1] else (ps.values[k] - st[k][0]) / st[k][1] for k in keys]

        tz = z(cid, target)
        norm_t = math.sqrt(sum(a * a for a in tz))
        scored = []
        for c, ps in cands:
            oz = z(c, ps)
            norm_o = math.sqrt(sum(b * b for b in oz))
            sim = sum(a * b for a, b in zip(tz, oz)) / (norm_t * norm_o) if norm_t and norm_o else 0.0
            shared = [k for k, a, b in zip(keys, tz, oz) if a > 0.5 and b > 0.5]
            scored.append((sim, c, ps, shared, oz))
        scored.sort(key=lambda s: (-s[0], s[2].info["name"], s[1]))
        return {"global_id": gid, "competition_id": cid, "position": pos, "scope": scope, "z_basis": "level",
                "template": list(keys), "pool": len(cands), "target_qualified": target.minutes >= sm.min_minutes,
                "z": {k: round(v, 2) for k, v in zip(keys, tz)},
                "similar": [{**self.card(c, ps), "similarity": round(sim, 3), "shared_strengths": shared,
                             "same_level": self.level[c] == self.level[cid],
                             "z": {k: round(v, 2) for k, v in zip(keys, oz)},
                             "values": {k: self.metrics[c].cell(ps, k)["value"] for k in keys}}
                            for sim, c, ps, shared, oz in scored[:n]],
                "warning": ALL_WARNING if scope == "all" else None}

    # ------------------------------------------------------------------ team style
    def team_style(self, cid: str, club_id: str) -> Record:
        """A club's style in its competition (the competition engine's: rank among its competition's clubs), plus its rank
        among every club of its level with uploaded matches, and how many matches it rests on."""
        sm = self.metrics[cid]
        out = sm.team_style(club_id)
        level_clubs = [(c, tid, t) for c in self.scope_competitions(cid, "level") for tid, t in self.metrics[c].teams.items()]
        for key, m in TEAM_CATALOGUE.items():
            vals = [(c, tid, t["values"].get(key)) for c, tid, t in level_clubs if t["values"].get(key) is not None]
            desc = m.higher_is_better is not False
            ranked = sorted(vals, key=lambda r: -r[2] if desc else r[2])
            rank = next((i for i, (c, tid, _v) in enumerate(ranked, start=1) if c == cid and tid == club_id), None)
            mean = sum(v for _c, _t, v in vals) / len(vals) if vals else None
            out["values"][key].update({"level_rank": rank, "level_of": len(vals),
                                       "level_mean": None if mean is None else round(mean, m.digits)})
        out.update({**self.labels_of(cid), "sample": {"matches": out["matches"], "small": out["matches"] < SMALL_TEAM_SAMPLE,
                                                      "competition_matches": len(sm.match_rows)},
                    "note": "rank and league_mean: among the competition's clubs with uploaded matches; level_rank and "
                            "level_mean: among every club of the level with uploaded matches. A sparse competition's "
                            "style rests on its uploads only."})
        return out

    # ------------------------------------------------------------------ the pools at a glance
    def pool_sizes(self, scope: str = "level") -> list[Record]:
        """Per pool and position: how many rows qualify on minutes (each under its own competition's rule). A metric's own
        pool can be smaller (ratio attempts)."""
        seen: dict[tuple, Record] = {}
        for cid in self.order:
            pid = self._pool_id(cid, scope)
            if pid in seen:
                continue
            comps = self.scope_competitions(cid, scope)
            lab = self.labels[cid]
            label = {"competition": lab["name"], "level": self.level[cid], "all": f"all levels / {lab['gender']}"}[scope]
            positions = {}
            for pos in ("GK", "DF", "MF", "FW"):
                size = sum(1 for c in comps for ps in self.metrics[c].players.values()
                           if ps.info["position"] == pos and ps.minutes >= self.metrics[c].min_minutes)
                positions[pos] = {"size": size, "small": size < SMALL_POOL, "under_min": size < self.min_size(cid, scope)}
            seen[pid] = {"scope": scope, "label": label, "competitions": comps,
                         "tier": lab["tier"] if scope != "all" else None,
                         "age_group": lab["age_group"] if scope != "all" else None, "gender": lab["gender"],
                         "positions": positions}
        return list(seen.values())


# ============================================================================ build once per process

def build_catalogue_metrics(index_path: Path | str | None = None, root: Path | str | None = None,
                            league_path: Path | str | None = None, season_root: Path | str | None = None,
                            england: SeasonMetrics | None = None, reliability: Record | None = None) -> CatalogueMetrics:
    """Build every competition's metrics: England from ``load_metrics`` (or ``england``), every other competition from
    its uploaded matches (built first, in one process pool: a calling script needs a ``__main__`` guard)."""
    from regista.catalogue import reliability as cat_rel
    from regista.catalogue.build import build_catalogue
    from regista.schema import iter_jsonl
    from regista.season.league import load_league
    from regista.season.metrics import load_metrics

    index_path = Path(index_path) if index_path else store.index_path()
    root = Path(root) if root else store.matches_root()
    index = store.load_index(index_path)
    league_path = Path(league_path) if league_path else store.competition_path(store.entry(ENGLAND_ID, index_path), index_path)
    season_root = Path(season_root or os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    eng = england if england is not None else load_metrics(league_path, season_root)
    league = load_league(league_path)
    comps = store.new_competitions(index_path)
    if reliability is None:
        reliability = cat_rel.load(league, comps, index_path.with_name(cat_rel.FILE_NAME))
    from regista.catalogue import realism as cat_realism

    checks = cat_realism.load(index_path.with_name(cat_realism.FILE_NAME), league, comps)
    paths = build_catalogue(comps, root)
    by_match = {p.name: p for p in paths}
    metrics: dict[str, SeasonMetrics] = {ENGLAND_ID: eng}
    comp_by_id: dict[str, Record] = {ENGLAND_ID: league}
    for comp in comps:
        cid = comp["competition"]["competition_id"]
        streams = []
        for fx in comp["fixtures"]:
            d = by_match[fx["match_id"]]
            streams.append((fx, list(iter_jsonl(d / "events.jsonl")), ClipIndex.load(d)))
        sm = SeasonMetrics.from_streams(comp, streams, xt=eng.xt, min_minutes_floor=FLOOR, min_pool=MIN_POOL)
        sm.reliability = cat_rel.level_table(reliability, BY_ID[cid].level_key)
        metrics[cid] = sm
        comp_by_id[cid] = comp
    return CatalogueMetrics(index, comp_by_id, metrics, reliability, checks)


_cache: dict[tuple, CatalogueMetrics] = {}
_cache_lock = threading.Lock()


def _mtime(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return 0


def load_catalogue_metrics(index_path: Path | str | None = None, root: Path | str | None = None,
                           league_path: Path | str | None = None, season_root: Path | str | None = None) -> CatalogueMetrics:
    """The catalogue's metrics, built once per process: rebuilt when the index, a competition file, the league file or a
    reliability table changes."""
    from regista.catalogue.reliability import FILE_NAME

    index_path = Path(index_path) if index_path else store.index_path()
    root = Path(root) if root else store.matches_root()
    league_path = Path(league_path) if league_path else store.competition_path(store.entry(ENGLAND_ID, index_path), index_path)
    season_root = Path(season_root or os.environ.get("REGISTA_SEASON_ROOT", "data/season/matches"))
    files = [index_path, league_path, index_path.with_name(FILE_NAME), league_path.with_name("reliability.json"),
             index_path.with_name("realism.json")]
    files += [store.competition_path(e, index_path) for e in store.entries(index_path) if e["source"] == "catalogue"]
    key = (str(index_path.resolve()), str(root.resolve()), str(league_path.resolve()), str(season_root.resolve()),
           tuple(_mtime(f) for f in files))
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            hit = build_catalogue_metrics(index_path, root, league_path, season_root)
            _cache.clear()
            _cache[key] = hit
        return hit


def invalidate() -> None:
    with _cache_lock:
        _cache.clear()
