"""A catalogue player's profile in the profile page's shape (``include=profile`` on ``/api/catalogue/players/{id}``): one
renderer for every competition, England's included, on the catalogue's basis (each competition's own uploaded matches;
England the Regista League's fixtures only, ``FIXTURES_BASIS``).

Per player-competition row, in one scope (level by default):

- ``stats[key]``: the profile's counts and per-90s (``regista.season.profiles.STATS``), each with its percentile in the
  scope's pool and the pool's plain words. **One ranking rule:** a stat gets a percentile for a position only when its
  Scout terminal metric is scored for that position (``CATALOGUE[key].positions``); otherwise none, with the reason ("not
  ranked for goalkeepers"). A stat with no terminal metric (forward passes) keeps the profile engine's percentile for
  outfield players and none for goalkeepers. Passes and passes completed are the metrics engine's own cells (crosses
  included), so the profile and the Terminal say one number.
- **None yet:** a count where more is better at exactly 0 has no percentile, and says how many of its pool have none
  (``none_yet: {none, of}``). A count where fewer is better (offsides, aerial duels lost) is never none yet: at 0 it
  keeps the engine's percentile or reason.
- ``ratios[key]``: the metrics engine's ratio for each profile ratio (``METRIC_OF``: pass completion, take-on success,
  shots on target %, aerial duels won %), so a ratio here equals the Terminal's, value and denominator.
- ``evidence[stat]``: up to 10 events behind each count (match, clip, time, the engine's minute, video) and the true
  total; ``matches`` with uploader (named), camera and Clip view link; ``grid``; ``moments``; ``summary`` worded for the
  competition (``regista.season.summaries.Wording``).

Never a hidden rating or a level scale: everything here reads the event streams and the public bio.
"""

from __future__ import annotations

from typing import Any

from regista.catalogue.metrics import NONE_YET_RULE, CatalogueMetrics
from regista.catalogue.taxonomy import ENGLAND_ID, POSITION_WORDS
from regista.season.metrics import CATALOGUE, COUNT_METRICS, rank_value

Record = dict[str, Any]

EVIDENCE_KEPT = 10
FROM_METRICS = {"passes": "passes", "passes_completed": "passes_completed"}   # profile stat -> the metrics engine's cell
LOWER_IS_BETTER = {"aerial_duels_lost", "offsides"}                             # never "none yet"
PASSES_NOTE = "Passes and pass completion count crosses too, as the Scout terminal does."


def _is_count(stat: str) -> bool:
    """A profile count where more is better (none yet at 0): its terminal metric's count flag, or, for a stat with no
    terminal metric (forward passes), any count not in ``LOWER_IS_BETTER``."""
    if stat in LOWER_IS_BETTER:
        return False
    return stat in COUNT_METRICS if stat in CATALOGUE else True


def _ranked_for(stat: str, position: str) -> tuple[bool, str | None]:
    """Whether a profile stat gets a percentile for this position (the metrics engine decides), and why not."""
    m = CATALOGUE.get(stat)
    if m is not None:
        return (True, None) if position in m.positions else (False, f"not ranked for {POSITION_WORDS[position]}")
    return (False, "not ranked for goalkeepers") if position == "GK" else (True, None)


def _zeros(pool_vals: list[float]) -> Record:
    z = rank_value(0.0)
    return {"none": sum(1 for v in pool_vals if v == z), "of": len(pool_vals)}


def minute_of(cm: CatalogueMetrics, cid: str) -> Any:
    """match_id, t -> the engine's football minute (``SeasonMetrics.minute``)."""
    sm = cm.metrics[cid]
    index = {r["match_id"]: i for i, r in enumerate(sm.match_rows)}

    def minute(match_id: str, t: float | None) -> int | None:
        mi = index.get(match_id)
        return None if mi is None else sm.minute(mi, t)
    return minute


def wording_for(cm: CatalogueMetrics, cp: Any, cid: str, gid: str) -> Any:
    """The summary's wording for this row: the competition's name, full or sparse coverage, two-decimal rates and
    one-decimal percentages, whether the row has the minutes for a rank, and the pass sentence from the metrics engine's
    pass completion (crosses included), ranked among the competition's players in the same position who qualify."""
    from regista.season.summaries import Wording

    s = cp.seasons[cid]
    p = s.profiles[gid]
    sm = cm.metrics[cid]
    ps = sm.players.get(gid)
    overrides: Record = {}
    if ps is not None and ps.values.get("pass_pct") is not None:
        m = CATALOGUE["pass_pct"]
        pos = ps.info["position"]
        group = [q for q in sm.players.values() if q.info["position"] == pos and sm.qualified(q, m)]
        if ps not in group:
            group.append(ps)
        v = ps.values["pass_pct"]
        overrides["pass_accuracy"] = {
            "label": "Pass completion (crosses included)", "value": v / 100.0,
            "display": f"{v:.1f}%", "count": round(ps.totals.get("passes_completed", 0.0)),
            "of": round(ps.totals.get("passes", 0.0)),
            "rank": 1 + sum(1 for q in group if q.values["pass_pct"] > v), "of_players": len(group),
            "tied_with": sum(1 for q in group if q is not ps and q.values["pass_pct"] == v)}
    minutes = cp._minutes(cid, p)
    return Wording(competition=cm.labels[cid]["name"], sparse=cm.labels[cid]["coverage"] != "full",
                   qualified=bool(p["appearances"]) and minutes >= s.min_minutes, minutes=round(p["minutes"], 1),
                   needed=round(s.min_minutes), overrides=overrides)


def summary_row(cm: CatalogueMetrics, cp: Any, cid: str, gid: str) -> Record | None:
    """The row's summary: England's stored Foundry summary while it holds on the fixtures (``summary_for``), else the
    rules summary in the competition's wording; ``engine`` says which."""
    from regista.season.summaries import summary_for

    s = cp.seasons[cid]
    p = s.profiles.get(gid)
    if p is None:
        return None
    out = summary_for(s, p, wording=wording_for(cm, cp, cid, gid), stored=cid == ENGLAND_ID)
    if out is not None:
        out = {**out, "engine": "foundry" if str(out.get("model", "")).startswith("foundry") else "rules"}
    return out


def profile_row(cm: CatalogueMetrics, cp: Any, cid: str, gid: str, scope: str = "level", *, moments: int = 40,
                matches: list[Record] | None = None, uploader: Any = None) -> Record | None:
    """One row's profile (see the module doc). ``matches``: the competition's uploaded matches (``cp.matches``), for the
    uploader and camera of each of the player's matches; ``uploader(up)`` names an uploader."""
    s = cp.seasons[cid]
    p = s.profiles.get(gid)
    if p is None:
        return None
    sm = cm.metrics[cid]
    ps = sm.players.get(gid)
    pos = p["position"]
    minute = minute_of(cm, cid)
    counts, per90 = dict(p["counts"]), dict(p["per90"])
    stats: Record = {}
    evidence: Record = {}
    from regista.season.profiles import RATIOS, STATS

    for k, (label, _test) in STATS.items():
        ranked, why = _ranked_for(k, pos)
        mk = FROM_METRICS.get(k)
        if mk and ps is not None:
            cell = cm.cell(cid, gid, mk, scope)
            count = round(cell.get("total") or 0.0)
            rate = cell["value"]
            pct, pool, reason = cell["percentile"], cell["pool"], cell["pool"]["reason"]
            noisy, ev_total = cell["noisy"], cell["evidence_total"]
            zeros = cell["zeros"]
            label = CATALOGUE[mk].label + " (crosses included)"
            counts[k], per90[k] = count, rate
            ev = cm.evidence(cid, gid, mk, EVIDENCE_KEPT)
            items = [{"match_id": i["match_id"], "clip_id": i.get("clip_id"), "t": i.get("t"), "minute": i.get("minute"),
                      "video_url": i.get("video_url")} for i in ev["items"]]
            evidence[k] = {"total": ev["moments"], "items": items}
        else:
            sc = cp.stat_cell(cid, gid, k, scope)
            pool = sc["pool"]
            count, rate = p["counts"][k], p["per90"][k]
            pct = sc["percentile"] if ranked else None
            reason = pool["reason"] if ranked else why
            mk2 = k if k in CATALOGUE else None
            noisy = bool(mk2) and cm.noisy(cid, mk2, scope, ps.minutes if ps is not None else None)
            ev_total = count
            zeros = None
            if ranked and _is_count(k) and count == 0:
                pct = None
                zeros = _zeros(cp.stat_pool(cid, k, pos, scope))
            evidence[k] = {"total": count, "items": [
                {"match_id": e["match_id"], "clip_id": e.get("clip_id"), "t": e.get("t"),
                 "minute": minute(e["match_id"], e.get("t")),
                 "video_url": f"/api/matches/{e['match_id']}/clips/{e['clip_id']}.mp4" if e.get("clip_id") else None}
                for e in p["evidence"][k][:EVIDENCE_KEPT]]}
        none_yet = zeros if ranked and _is_count(k) and count == 0 else None   # not ranked: the reason says why
        stats[k] = {"label": label, "count": count, "per90": rate, "percentile": None if none_yet else pct,
                    "pool": pool, "reason": reason, "noisy": noisy, "none_yet": none_yet, "evidence_total": ev_total}
    ratios: Record = {}
    from regista.season.profiles import METRIC_OF

    for r, (_label, _num, _den) in RATIOS.items():
        mk = METRIC_OF[r]
        if ps is None:
            continue
        cell = cm.cell(cid, gid, mk, scope)
        ratios[r] = {"metric": mk, "label": CATALOGUE[mk].label, "unit": CATALOGUE[mk].unit, "value": cell["value"],
                     "num": cell.get("num"), "den": cell.get("den"), "percentile": cell["percentile"], "pool": cell["pool"],
                     "reason": cell["pool"]["reason"] or (None if cell["percentile"] is not None
                                                          else "not enough minutes or attempts for a percentile"),
                     "noisy": cell["noisy"], "evidence_total": cell["evidence_total"]}
    up_of = {m["match_id"]: m for m in (matches if matches is not None else cp.matches(cid))}
    rows = []
    for m in p["matches"]:
        u = up_of.get(m["match_id"]) or {}
        up = u.get("uploader")
        rows.append({"match_id": m["match_id"], "round": m.get("round"), "date": m.get("date"), "opponent": m.get("opponent"),
                     "home": m.get("home"), "score": m.get("score"), "source": m.get("source"),
                     "uploader": uploader(up) if uploader and up else up, "camera": u.get("camera"),
                     "clip_view": f"/?match={m['match_id']}&player={m['player_id']}" if m.get("player_id")
                     else f"/?match={m['match_id']}"})
    rows.sort(key=lambda r: (r["date"] or "", r["match_id"]), reverse=True)   # newest first
    return {"scope": scope, "appearances": p["appearances"], "minutes": p["minutes"],
            "qualifying_minutes": round(s.min_minutes, 1),
            "qualified": bool(p["appearances"]) and cp._minutes(cid, p) >= s.min_minutes,
            "counts": counts, "per90": per90, "stats": stats, "ratios": ratios, "evidence": evidence, "matches": rows,
            "grid": p["grid"], "moments": [{**mm, "competition_id": cid} for mm in p["moments"][:moments]],
            "summary": summary_row(cm, cp, cid, gid), "passes_note": PASSES_NOTE, "none_yet_rule": NONE_YET_RULE}
