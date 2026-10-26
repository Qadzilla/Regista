"""The Scout agent on the catalogue (``POST /api/scout/ask`` with ``where: "catalogue"``): plain questions about the 14
synthetic competitions' players, answered with the catalogue MCP tools' own rows (``regista.catalogue.tools``).

- **rules** (``answer_catalogue``): the place words are read first (``regista.catalogue.place``: country, level, age
  group, gender, competition, "my level", "whole catalogue"), then the stat and the position from the league's own
  question parser (``regista.season.scout.parse``), mapped to the Scout terminal's metric; the tool
  ``search_catalogue_players`` (or ``get_catalogue_player`` for a named player) answers. Percentiles are within each
  row's level unless the question says otherwise; men and women never share a pool.
- **Foundry**: the agent calls the same tools through Regista's MCP server; ``cards_from_calls`` runs its last
  catalogue call again here for the cards, and ``regista.season.scout.from_foundry`` checks every number in its reply.

Cards are catalogue rows: who, club, competition, country, level, the number with its percentile and its pool (in plain
words, small and noisy marks, none yet), minutes and the profile link.
"""

from __future__ import annotations

import threading
from typing import Any

from regista.catalogue import tools
from regista.catalogue.metrics import CatalogueMetrics
from regista.catalogue.taxonomy import POSITION_WORDS, level_words
from regista.season.metrics import CATALOGUE, DEFAULT_COLUMNS

Record = dict[str, Any]

CATALOGUE_TOOLS = ("list_competitions", "search_catalogue_players", "get_catalogue_player")
# The league parser's profile stats, read as the Scout terminal's metrics (the catalogue tools' sort keys).
SORT_OF = {"forward_passes": "progressive_passes", "pass_accuracy": "pass_pct", "take_on_success": "take_on_pct",
           "shot_accuracy": "shot_on_target_pct", "aerial_win": "aerial_win_pct"}
EXAMPLES = ["Who are the best U19 dribblers up front?", "Find me women forwards who score",
            "Which amateur midfielders create the most chances?", "most interceptions at my level"]
_vocab: dict[str, Any] = {}
_vocab_lock = threading.Lock()


def place_vocab(cm: CatalogueMetrics) -> Record:
    from regista.catalogue.place import vocab

    with _vocab_lock:
        hit = _vocab.get("v")
        if hit is None or hit[0] is not cm:
            hit = (cm, vocab(cm.index, [cm.comps[c] for c in cm.order]))
            _vocab["v"] = hit
        return hit[1]


def named_player(cm: CatalogueMetrics, question: str) -> str | None:
    """The catalogue player a question names by full name (the longest name that fits), else None."""
    import re

    low = f" {question.lower()} "
    best = None
    for gid, entries in cm.people.items():
        name = entries[0][1]["name"].lower()
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", low) and (best is None or len(name) > len(best[1])):
            best = (gid, name)
    return best[0] if best else None


def metric_for(sort: str | None, position: str | None) -> str:
    """A league stat key as the catalogue tools' sort: the terminal's metric of the same meaning; none named: the
    position's first default column."""
    if sort in (None, "minutes"):
        return DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None])[0]
    key = SORT_OF.get(sort, sort)
    return key if key in CATALOGUE else DEFAULT_COLUMNS.get(position, DEFAULT_COLUMNS[None])[0]


def card(row: Record) -> Record:
    """A catalogue tool row as the Scout page shows it."""
    st = row.get("stat") or {}
    pool = st.get("pool") or {}
    return {"global_id": row["global_id"], "name": row["name"], "club": row["club"], "position": row["position"],
            "competition_id": row["competition_id"], "competition": row["competition"], "country": row["country"],
            "tier": row["tier"], "age_group": row["age_group"], "gender": row["gender"],
            "level_words": level_words(f"{row['tier']}/{row['age_group']}/{row['gender']}"),
            "minutes": row["minutes"], "appearances": row["appearances"], "qualified": row["qualified"],
            "career": row["career"], "board": row.get("board"),
            "stat": {"key": st.get("key"), "label": st.get("label"), "value": st.get("value"),
                     "percentile": st.get("percentile"), "noisy": st.get("noisy"), "none_yet": st.get("none_yet"),
                     "zeros": st.get("zeros"), "pool": pool} if st else None,
            "small": pool.get("small"), "profile_url": f"/players/{row['global_id']}",
            "api_url": f"/api/catalogue/players/{row['global_id']}"}


def player_card(cm: CatalogueMetrics, gid: str, sort: str | None = None, scope: str = "level") -> Record | None:
    """A named player's card: the row with the most minutes, and ``sort`` (or the position's first default column)."""
    rows = cm.player_rows(gid)
    if not rows:
        return None
    cid, ps = max(rows, key=lambda r: r[1].minutes)
    key = sort if sort in CATALOGUE else DEFAULT_COLUMNS.get(ps.info["position"], DEFAULT_COLUMNS[None])[0]
    c = cm.cell(cid, gid, key, scope)
    row = {"global_id": gid, "name": ps.info["name"], **cm.labels_of(cid), "club": ps.info["club"],
           "position": ps.info["position"], "minutes": round(ps.minutes, 1), "appearances": ps.appearances,
           "qualified": ps.minutes >= cm.metrics[cid].min_minutes, "career": len(cm.people.get(gid, [])) > 1,
           "stat": {"key": key, "label": CATALOGUE[key].label, "value": c["value"], "percentile": c["percentile"],
                    "noisy": c["noisy"], "none_yet": c["none_yet"], "zeros": c["zeros"],
                    "pool": {k: c["pool"][k] for k in ("scope", "tier", "age_group", "gender", "position", "size",
                                                       "small", "reason", "words")}}}
    return card(row)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _number(st: Record) -> str:
    m = CATALOGUE[st["key"]]
    if st.get("none_yet"):
        return "none yet"
    v = st["value"]
    if v is None:
        return "no value yet"
    if m.kind == "ratio":
        return f"{v:g}%" if m.unit == "%" else f"{v:g} {m.unit}"
    return f"{v:.2f} per 90" if m.kind in ("per90", "padj") else f"{v:g}"


def _pool_line(st: Record) -> str:
    pool = st["pool"]
    if st.get("percentile") is None:
        return f"no percentile ({pool.get('reason') or 'not enough minutes'})"
    small = ", a small pool" if pool.get("small") else ""
    noisy = "; ≈ noisy over a sample this size" if st.get("noisy") else ""
    return f"{_ordinal(round(st['percentile']))} percentile among {pool['size']} {pool['words']}{small}{noisy}"


def reply_for(result: Record, query: Record) -> str:
    rows = result.get("players") or []
    label = CATALOGUE[query["sort"]].label.lower()
    who = query["who"]
    if not rows:
        return f"No {who} in the catalogue match that yet."
    top = rows[0]
    st = top["stat"]
    head = (f"{top['name']} ({top['club']}, {top['competition']}, {top['country']}) leads {who} for {label}: "
            f"{_number(st)}, {_pool_line(st)}.")
    nxt = [f"{r['name']} {_number(r['stat'])}" for r in rows[1:3]]
    out = head + (f" Next: {' and '.join(nxt)}." if nxt else "")
    if result.get("with_any") is not None and result.get("none_yet"):
        out += f" {result['with_any']} of {result['with_any'] + result['none_yet']} have any so far."
    if result.get("warning"):
        out += " These rows come from more than one level: read each percentile against its own pool."
    return out


def answer_catalogue(season: Any, cm: CatalogueMetrics, question: str, trace: list[Record] | None = None) -> Record:
    """The rules engine on the catalogue: ``{reply, understood, query, players: [cards], trace, answered_by, tools_used,
    where, warning}``, the league answer's shape. ``players`` are the tool's rows as cards."""
    from regista.catalogue.place import parse as parse_place
    from regista.conversation import timed_step
    from regista.season.scout import parse as parse_question

    trace = trace if trace is not None else []
    v = place_vocab(cm)
    place = timed_step(trace, "scout.catalogue_place", parse_place, question, v)
    q = timed_step(trace, "scout.parse", parse_question, season, place["rest"] or question)
    named = named_player(cm, question)
    w = dict(place["where"])
    if named:
        result = timed_step(trace, "scout.get_catalogue_player", tools.get_player, cm, named)
        c = player_card(cm, named)
        reply = (f"{c['name']} ({c['club']}, {c['competition']}, {c['country']}): {c['stat']['label'].lower()} "
                 f"{_number(c['stat'])}, {_pool_line(c['stat'])}." if c else result.get("error", ""))
        query = {"mode": "player", "ids": [named], "where": w, "sort": c["stat"]["key"] if c else None,
                 "position": None, "order": "desc", "limit": 1}
        return {"reply": reply, "understood": _understood(place, q, query, named=True), "query": query,
                "players": [c] if c else [], "trace": trace, "answered_by": "rules", "tools_used": [], "where": "catalogue",
                "warning": None}
    sort = metric_for(q["sort"], q["position"])
    order = "asc" if q["order"] == "asc" else "desc"
    args = {**{k: w[k] for k in ("tier", "age_group", "gender", "country", "competition") if k in w},
            "position": q["position"], "sort": sort, "order": order, "limit": q["limit"]}
    result = timed_step(trace, "scout.search_catalogue_players", lambda: tools.search_players(cm, **args))
    pos = POSITION_WORDS.get(q["position"] or "", "players")
    level = level_words(f"{w['tier']}/{w['age_group']}/{w['gender']}") if {"tier", "age_group", "gender"} <= set(w) else \
        " ".join(x for x in (w.get("tier", "").replace("_", "-"), w.get("age_group", ""), w.get("gender", "")) if x)
    where_words = " ".join(x for x in (level, pos) if x) + (f" in {w['country']}" if w.get("country") else "") + \
        (f" in {v['comp_name'][w['competition']]}" if w.get("competition") else "")
    query = {"mode": "rank", "where": w, "position": q["position"], "sort": sort, "order": order, "limit": q["limit"],
             "who": f"the {where_words}".replace("  ", " "), "args": args}
    reply = reply_for(result, query) if "error" not in result else result["error"]
    return {"reply": reply, "understood": _understood(place, q, query), "query": {k: query[k] for k in query if k != "who"},
            "players": [card(r) for r in result.get("players", [])], "trace": trace, "answered_by": "rules",
            "tools_used": [], "where": "catalogue", "warning": result.get("warning"), "result_total": result.get("total"),
            "with_any": result.get("with_any"), "none_yet": result.get("none_yet")}


def _understood(place: Record, q: Record, query: Record, named: bool = False) -> str:
    parts = ["the catalogue"]
    if place["said"]:
        parts.append(", ".join(place["said"]))
    if place["unknown"]:
        parts.append(f"no {', '.join(place['unknown'])} level in the catalogue")
    if named:
        parts.append("one player")
    else:
        if q.get("position"):
            parts.append(POSITION_WORDS[q["position"]])
        m = CATALOGUE[query["sort"]]
        parts.append(f"{'fewest' if query['order'] == 'asc' else 'most'} {m.label.lower()}"
                     + (" per 90" if m.kind == "per90" else ""))
        parts.append(f"top {query['limit']}")
        parts.append("percentiles within each player's level")
    return " · ".join(parts) + (f" (heard {'; '.join(q['heard'])})" if q.get("heard") else "")


def run_tool(cm: CatalogueMetrics, name: str, args: Record) -> Record:
    """Run one of the catalogue tools in-process with the arguments a model gave the MCP server."""
    args = dict(args or {})
    if name == "list_competitions":
        allowed = {"country", "tier", "age_group", "gender"}
        return tools.list_competitions(None, **{k: v for k, v in args.items() if k in allowed and v is not None})
    if name == "search_catalogue_players":
        allowed = {"tier", "age_group", "gender", "country", "competition", "position", "sort", "order", "scope", "limit",
                   "min_minutes", "rank_by"}
        return tools.search_players(cm, **{k: v for k, v in args.items() if k in allowed and v is not None})
    if name == "get_catalogue_player":
        return tools.get_player(cm, str(args.get("player") or args.get("global_id") or ""), str(args.get("scope") or "level"))
    return {"error": f"unknown tool {name}"}


def cards_from_calls(cm: CatalogueMetrics, calls: list[tuple[str, Record]]) -> tuple[list[Record], list[Record]]:
    """(cards from the last catalogue player call, every catalogue call's result) for a Foundry answer."""
    results = [run_tool(cm, n, a) for n, a in calls]
    cards: list[Record] = []
    for (name, _args), res in zip(reversed(calls), reversed(results)):
        if name == "search_catalogue_players" and "players" in res:
            cards = [card(r) for r in res["players"]]
            break
        if name == "get_catalogue_player" and "global_id" in res:
            c = player_card(cm, res["global_id"])
            cards = [c] if c else []
            break
    return cards, results
