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

**Ranking across levels** (``order_rows``, ``RANK_RULE``). Percentiles are compared only within one position and raw
numbers only within one level. A list from more than one level that holds one position ranks by each row's percentile
within its own pool, one board per gender; a list from more than one level and more than one position ranks by value
within each level, one board per level (a one-goal defender at the 99th percentile of defenders never tops a list of
goals above the top scorer); one level ranks by value. ``rank_by`` forces a mode.

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
from regista.catalogue.realism import zone_note_for
from bisect import bisect_left, bisect_right

from regista.catalogue.taxonomy import BY_ID, ENGLAND_ID, POSITION_WORDS, level_words
from regista.season.metrics import (CATALOGUE, COUNT_METRICS, DEFAULT_COLUMNS, SIMILAR_DEFAULT, SIMILARITY_TEMPLATE,
                                    TEAM_CATALOGUE, ClipIndex, PlayerSeason, SeasonMetrics, fbref_percentile, rank_value)
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
ALL_WARNING = ("rows from different levels: read each percentile against its own pool. Raw numbers carry each level's "
               "own football (lower levels and younger ages complete fewer passes and lose the ball more, women's pools "
               "run on lower speeds), so a raw number from one level is not a better or worse player than the same "
               "number from another; compare players through their percentiles within their pools.")
RANK_BY = ("pool", "value")
RANK_RULE = ("Percentiles are compared only within one position, raw numbers only within one level. One level: by the "
             "raw value. More than one level and one position (a position filter, or a list that holds one): rank_by "
             "pool, each row's percentile within its own pool, then rows from pools that are not small, then more "
             "minutes, then the value; rows without a percentile follow, unranked; one board per gender. More than one "
             "level and more than one position: rank_by value within each level, one board per level, so a defender's "
             "percentile never outranks a forward's goals. rank_by forces a mode: value always ranks within each level "
             "(one board per level); pool with more than one position gives one board per gender and position. order: "
             "in value mode desc lists the largest numbers first, even where lower is better. In pool mode desc lists "
             "the rows highest in their own pool in the raw direction first: the largest numbers relative to each row's "
             "pool, not the largest numbers (for a lower-is-better metric, the lowest oriented percentiles). Without "
             "order, best first. boards gives each board's key, label, size, its offset in the list and its top rows, so "
             "no board hides behind another; each row's board names the board it is ranked on.")
GENDER_ORDER = ("men", "women")
POSITION_ORDER = ("GK", "DF", "MF", "FW")
BOARD_TOP = 5          # each board's top rows carried beside a page (boards[].top), so no board hides behind another
BOARD_BY = ("level", "gender", "gender_position")
CAREER_NOTE = ("Counts and minutes are summed across competitions; per-90 rates and percentiles stay per competition, "
               "because rates from two levels would mix pools.")
SYNTHETIC_NOTE = ("Synthetic data: invented players, clubs and competition names, generated by Regista. Countries, regions "
                  "and levels are classification labels.")
NONE_YET_RULE = ("None yet: a count where more is better (goals, assists, take-ons won...; count_metrics) at exactly 0 gets "
                 "no percentile and no place: it is listed after the ranked rows, and the cell says how many of its pool "
                 "have none (zeros). Measures (xG, xA, metres, speeds, percentages) and differences keep their percentile "
                 "at 0; a count where fewer is better (fouls, offsides) is never none yet.")
NOISY_WORDS = ("≈ marks a number that is mostly noise over a sample this size: it cannot yet tell players in the same role "
               "apart. Read it with care.")


# Similar players' shared strengths in plain words (the Terminal's metric names are "non-penalty xG", "shot-creating
# actions"); any other metric reads as its label, lower case.
PLAIN = {"npxg": "getting good scoring chances", "np_goals": "goals other than penalties",
         "sca": "actions that lead to a shot", "xa": "passes that set up good chances",
         "progressive_passes": "passes that move the ball forward", "progressive_passes_received": "getting forward passes",
         "progressive_carries": "carrying the ball forward", "aerial_duels_won": "winning headers",
         "pass_pct": "pass completion", "touches_in_box": "touches in the box", "clean_sheet_pct": "clean sheets",
         "gk_pass_pct": "passing (keeper)", "gk_passes": "passing a lot (keeper)",
         "gk_avg_pass_length": "long passing (keeper)", "gk_launch_pct": "long kicks (keeper)",
         "save_pct": "saving shots", "sot_faced": "shots on target faced", "goals_conceded": "conceding few goals"}


def strength_words(key: str) -> str:
    if key in PLAIN:
        return PLAIN[key]
    label = CATALOGUE[key].label if key in CATALOGUE else key.replace("_", " ")
    return label[:1].lower() + label[1:]


def pool_words(scope: str, position: str, *, tier: str | None, age_group: str | None, gender: str,
               competition: str | None = None) -> str:
    """Who a percentile is among, in plain words: "semi-pro men forwards" (level), "forwards in Regista League"
    (competition), "men forwards at every level" (all)."""
    pos = POSITION_WORDS.get(position, "players")
    if scope == "competition":
        return f"{pos} in {competition}"
    if scope == "all":
        return f"{gender} {pos} at every level"
    return f"{level_words(f'{tier}/{age_group}/{gender}')} {pos}"


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
                       "competitions": self.scope_competitions(cid, scope), "reason": reason,
                       "words": pool_words(scope, position, tier=lab["tier"], age_group=lab["age_group"],
                                           gender=lab["gender"], competition=lab["name"])}
        if scope == "competition":
            out["competition_id"] = cid
        return out

    @staticmethod
    def none_yet(ps: PlayerSeason, key: str) -> bool:
        """A count where more is better (``COUNT_METRICS``) at exactly 0: no percentile, no place (``NONE_YET_RULE``),
        whatever the position (a keeper with no goals has none yet; his pool's ``reason`` still says the metric is not
        ranked for keepers)."""
        return key in COUNT_METRICS and ps.values.get(key) is not None and ps.values[key] == 0

    def zeros(self, cid: str, key: str, position: str, scope: str = "level") -> Record:
        """How many of this pool's rows have none of a count: ``{none, of}`` (the pool's size)."""
        vals = self.pool_values(cid, key, position, scope)
        z = rank_value(0.0)
        return {"none": bisect_right(vals, z) - bisect_left(vals, z), "of": len(vals)}

    def percentile(self, cid: str, ps: PlayerSeason, key: str, scope: str = "level") -> float | None:
        """FBref's percentile of this row among its pool, or None (not qualified, not ranked, too small a pool, or none
        yet: a count at 0)."""
        if self.none_yet(ps, key):
            return None
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

    def sample_words(self, cid: str) -> str:
        """What a competition's per-90s rest on, in plain words (the sample, without code names)."""
        sm = self.metrics[cid]
        smp = sm.sample()
        n = len(sm.match_rows)
        per_club = sorted(sum(1 for r in sm.match_rows if club in (r["home"], r["away"])) for club in sm.clubs)
        per_club = [x for x in per_club if x] or [0]
        mm = round(smp["match_minutes"]) if smp["match_minutes"] else 0
        median = round(smp["median_qualified_minutes"])
        need = round(sm.min_minutes)
        if self.labels[cid]["coverage"] == "full":
            return (f"Every league match is uploaded: {n} matches, {smp['matches_per_club']} for each club, of about {mm} "
                    f"minutes. A regular's season here is about {median} minutes ({smp['median_full_matches']:g} full "
                    f"matches); a percentile needs {need} minutes. Per 90s rest on the {n} league matches.")
        clubs = f"{per_club[0]} for each club" if per_club[0] == per_club[-1] else \
            f"{per_club[0]} to {per_club[-1]} for each club"
        return (f"Only uploaded matches count here: {n} so far, {clubs}, of about {mm} minutes. A regular's season here is "
                f"about {median} minutes; a percentile needs {need} minutes. Per 90s rest on the {n} uploaded matches.")

    def cell(self, cid: str, gid: str, key: str, scope: str = "level") -> Record:
        """One metric for one player-competition row: the competition engine's cell (value, count, qualified), with the
        percentile, ``peers`` and ``noisy`` of the scope's pool, the moments behind it, the pool and the sample."""
        sm = self.metrics[cid]
        ps = sm.players[gid]
        pos = ps.info["position"]
        pool = self.pool(cid, key, pos, scope)
        out = sm.cell(ps, key)
        out["percentile"] = self.percentile(cid, ps, key, scope)
        out["none_yet"] = self.none_yet(ps, key)
        out["zeros"] = self.zeros(cid, key, pos, scope) if out["none_yet"] else None
        out["peers"] = pool["size"]
        out["noisy"] = self.noisy(cid, key, scope, ps.minutes)
        r_k = None if (scope == "competition" and cid == ENGLAND_ID) else self.reliability_at(cid, key, ps.minutes)
        out["r_at_minutes"] = None if r_k is None else round(r_k, 3)
        out["evidence_total"] = sm.evidence_total(ps, key)
        out["pool"] = pool
        out["sample"] = self.sample(cid, ps)
        zone_note = zone_note_for(BY_ID[cid].level_key, key)
        if zone_note:   # women's and youth pools read the men's senior zones
            out["threshold_note"] = zone_note
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
        others = [c for c, _p in self.people.get(gid, []) if c != cid]
        # the profile page (/players/{gid}) serves every catalogue player; also_in: the player's other competitions
        return {**sm.card(ps), **self.labels_of(cid), "career": len(self.people.get(gid, [])) > 1, "also_in": others,
                "profile_url": f"/players/{gid}"}

    def player_rows(self, gid: str) -> list[tuple[str, PlayerSeason]]:
        return [(cid, self.metrics[cid].players[gid]) for cid, _p in self.people.get(gid, [])
                if gid in self.metrics[cid].players]

    def select(self, *, tier: str | None = None, age_group: str | None = None, gender: str | None = None,
               country: str | None = None, competition: str | None = None, position: str | None = None,
               role: str | None = None, q: str | None = None, min_minutes: float | None = None, age_min: int | None = None,
               age_max: int | None = None, foot: str | None = None, camera: str | None = None,
               career: bool | None = None) -> list[tuple[str, PlayerSeason]]:
        """Player-competition rows across the catalogue, filtered. ``tier``: one tier or a comma list; ``min_minutes``
        None: each row's own competition's qualifying minutes; ``camera``: rows with an appearance in a match filmed on
        that camera type."""
        out = []
        for cid in self.order:
            lab = self.labels[cid]
            if (tier and lab["tier"] not in tier.split(",")) or (age_group and lab["age_group"] != age_group) or \
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
        """By a metric's value, best first (or ``order`` "asc" / "desc"); then the rows with none yet (a count at 0, by
        name), then rows without a value."""
        m = CATALOGUE[key]
        desc = (m.higher_is_better is not False) if order is None else order == "desc"
        have = [r for r in rows if r[1].values.get(key) is not None and not self.none_yet(r[1], key)]
        zero = [r for r in rows if self.none_yet(r[1], key)]   # none yet: after the ranked rows, in any order
        none = [r for r in rows if r[1].values.get(key) is None]
        have.sort(key=lambda r: (-r[1].values[key] if desc else r[1].values[key], r[1].info["name"], r[0]))
        return have + sorted(zero, key=lambda r: (r[1].info["name"], r[0])) + sorted(none, key=lambda r: (r[1].info["name"], r[0]))

    def rank_mode(self, rows: list[tuple[str, PlayerSeason]], key: str, rank_by: str | None = None) -> str:
        """``choose_mode`` for terminal rows ranked by a metric (a season total has no percentile)."""
        return self.choose_mode([(c, ps.info["position"]) for c, ps in rows], CATALOGUE[key].kind != "total", rank_by)

    @staticmethod
    def check_rank_by(rank_by: str | None) -> None:
        if rank_by is not None and rank_by not in RANK_BY:
            raise ValueError(f"unknown rank_by {rank_by!r}: one of {', '.join(RANK_BY)}")

    def choose_mode(self, items: list[tuple[str, str]], rateable: bool, rank_by: str | None = None) -> str:
        """``RANK_RULE``'s mode for rows given as (competition id, position): ``rank_by`` when given (value for what has no
        percentile); else pool when the rows come from more than one level and hold one position, otherwise value."""
        self.check_rank_by(rank_by)
        if not rateable:
            return "value"
        if rank_by:
            return rank_by
        levels = {self.level[c] for c, _p in items}
        positions = {p for _c, p in items}
        return "pool" if len(levels) > 1 and len(positions) == 1 else "value"

    def board_by(self, items: list[tuple[str, str]], mode: str) -> str | None:
        """How a list is split into boards (``RANK_RULE``): value mode, one board per level when there is more than one;
        pool mode, one board per gender and position when there is more than one position, else one per gender when
        both are there. None: one board."""
        levels = {self.level[c] for c, _p in items}
        if mode == "value":
            return "level" if len(levels) > 1 else None
        if len({p for _c, p in items}) > 1:
            return "gender_position"
        return "gender" if len({self.labels[c]["gender"] for c, _p in items}) > 1 else None

    def board_key(self, by: str | None, cid: str, position: str) -> str:
        """The board a row is ranked on: its level, its gender and position, or its gender (one board: the gender)."""
        gender = self.labels[cid]["gender"]
        if by == "level":
            return self.level[cid]
        if by == "gender_position":
            return f"{gender}/{position}"
        return gender

    def _board_rank(self, by: str | None, cid: str, position: str) -> tuple:
        """Board order: men before women; levels in the catalogue's order of their first competition; positions GK, DF,
        MF, FW."""
        gender = GENDER_ORDER.index(self.labels[cid]["gender"])
        if by == "level":
            level = self.level[cid]
            return gender, min(i for i, c in enumerate(self.order) if self.level[c] == level)
        if by == "gender_position":
            return gender, POSITION_ORDER.index(position) if position in POSITION_ORDER else len(POSITION_ORDER)
        return (gender,)

    def group_boards(self, rows: list, by: str | None, where: Any) -> list:
        """``rows`` grouped by board, in board order, each board keeping its order (a stable sort). ``where(row)`` gives
        the row's (competition id, position)."""
        if by is None:
            return list(rows)
        return sorted(rows, key=lambda r: self._board_rank(by, *where(r)))

    def boards(self, by: str | None, rows: list, where: Any, row_of: Any, limit: int,
               any_of: Any = None) -> list[Record] | None:
        """One shape for every surface: each board's ``board`` key, ``by``, ``label``, ``gender``, ``level``, ``position``,
        ``size``, ``offset`` (where it starts in ``rows``, which are grouped by board), ``top`` (its first rows,
        ``row_of(index)``, at most ``BOARD_TOP`` and ``limit``), and ``with_any`` / ``none_yet``: how many of its rows have
        any of the sorted count and how many have none yet (``any_of(row)``: True, False, or None for neither; both None
        when the sort is not a count). None when the list is one board."""
        if by is None:
            return None
        from regista.catalogue.taxonomy import AGE_GROUPS, GENDERS, TIERS

        names = dict(TIERS) | dict(AGE_GROUPS) | dict(GENDERS)
        out: list[Record] = []
        index: dict[str, Record] = {}
        for i, r in enumerate(rows):
            cid, position = where(r)
            key = self.board_key(by, cid, position)
            b = index.get(key)
            if b is None:
                lab = self.labels[cid]
                if by == "level":
                    label = f"{names[lab['tier']]}, {names[lab['age_group']].lower()}, {names[lab['gender']].lower()}"
                elif by == "gender_position":
                    label = f"{names[lab['gender']]}, {position}"
                else:
                    label = names[lab["gender"]]
                b = index[key] = {"board": key, "by": by, "label": label, "gender": lab["gender"],
                                  "level": self.level[cid] if by == "level" else None,
                                  "position": position if by == "gender_position" else None,
                                  "size": 0, "offset": i, "_idx": [],
                                  "with_any": 0 if any_of else None, "none_yet": 0 if any_of else None}
                out.append(b)
            b["size"] += 1
            b["_idx"].append(i)
            if any_of:
                has = any_of(r)
                if has is True:
                    b["with_any"] += 1
                elif has is False:
                    b["none_yet"] += 1
        for b in out:
            b["top"] = [row_of(i) for i in b.pop("_idx")[:min(BOARD_TOP, limit)]]
        return out

    def order_rows(self, rows: list[tuple[str, PlayerSeason]], key: str, scope: str = "level", order: str | None = None,
                   rank_by: str | None = None) -> tuple[list[tuple[str, PlayerSeason]], str, str | None, set]:
        """(rows in order, the rank mode, how the rows are split into boards or None, the (cid, gid) of rows ranked by
        percentile), as ``RANK_RULE`` says.

        ``pool``: by each row's percentile in ``scope``, then rows whose pool is not small, then more minutes, then the
        value; rows without a percentile follow, by value. ``value``: ``sort``. In value mode "desc" lists the largest
        numbers first (even where lower is better); in pool mode it lists the rows highest in their own pool in the raw
        direction first, which are the largest numbers relative to each row's pool, not the largest numbers (a
        lower-is-better metric's "desc" lists its lowest oriented percentiles first). With no ``order``, best first.
        Rows are then grouped by board (``board_by``): one per level in value mode, one per gender (and position, when
        there is more than one) in pool mode."""
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
        where = self.where_of
        by = self.board_by([where(r) for r in rows], mode)
        return self.group_boards(ordered, by, where), mode, by, ranked

    def placed(self, rows: list[tuple[str, PlayerSeason]], key: str, mode: str, by_pct: set) -> list[tuple[str, PlayerSeason]]:
        """The rows that get a place, in order (``RANK_RULE``): pool mode, the rows ranked by percentile; value mode, the rows
        with their competition's minimum minutes (and attempts), never none yet (a count at 0). ``by_pct``: the fourth
        value of ``order_rows``."""
        m = CATALOGUE[key]
        if mode == "pool":
            return [(cid, ps) for cid, ps in rows if (cid, ps.info["global_id"]) in by_pct]
        return [(cid, ps) for cid, ps in rows
                if (self.metrics[cid].qualified(ps, m) or (m.kind == "total" and ps.values.get(key) is not None))
                and not self.none_yet(ps, key)]

    def ranked_first(self, rows: list[tuple[str, PlayerSeason]], key: str, mode: str, by_pct: set,
                     by: str | None) -> tuple[list[tuple[str, PlayerSeason]], set]:
        """(``order_rows``' rows with, on each board, the rows that get a place first and the rest after in their order, as
        ``/api/catalogue/rank`` lists them; the (cid, gid) of the placed rows). A ratio below its minimum attempts never
        leads a list."""
        placed = {(cid, ps.info["global_id"]) for cid, ps in self.placed(rows, key, mode, by_pct)}
        first = [r for r in rows if (r[0], r[1].info["global_id"]) in placed]
        rest = [r for r in rows if (r[0], r[1].info["global_id"]) not in placed]
        return self.group_boards(first + rest, by, self.where_of), placed

    @staticmethod
    def where_of(row: tuple[str, PlayerSeason]) -> tuple[str, str]:
        return row[0], row[1].info["position"]

    @staticmethod
    def any_of(key: str) -> Any:
        """For ``boards``: a row's "has any" (True), "none yet" (False) or neither (None) on a count; None when ``key``
        is not a count."""
        if key not in COUNT_METRICS:
            return None

        def has(row: tuple[str, PlayerSeason]) -> bool | None:
            v = row[1].values.get(key)
            return None if v is None else v != 0
        return has

    @classmethod
    def count_split(cls, rows: list[tuple[str, PlayerSeason]], key: str) -> Record:
        """``{with_any, none_yet}`` over ``rows`` on a count (both None when ``key`` is not one)."""
        has = cls.any_of(key)
        if has is None:
            return {"with_any": None, "none_yet": None}
        flags = [has(r) for r in rows]
        return {"with_any": sum(1 for f in flags if f is True), "none_yet": sum(1 for f in flags if f is False)}

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
                row["profile_url"] = f"/players/{row['global_id']}"
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
