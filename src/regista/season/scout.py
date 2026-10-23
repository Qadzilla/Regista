"""The Scout agent: plain questions about the Regista League's players, answered with names and numbers from the profiles.

Three player tools, the same everywhere: the MCP server exposes them (``regista.mcp_server``), the rules engine calls
them, and the Foundry engine's own tool calls are run again here so the cards a scout sees are what the model read.

- ``search_players``   filters (position, club, name) and a sort (any stat per 90, or a ratio), highest first
- ``get_profile``      one player without the bulky evidence: rates, percentiles, ranks, best moments, summary
- ``compare_players``  two or three players side by side, every rate

Two engines give one shape of answer, ``{reply, understood, query, players, trace, answered_by}``:

- **rules** (``answer_rules``): ``parse`` reads the question into filters and a sort ("a winger with the most
  take-ons" is forwards by take-ons won per 90; winger and striker are FW), runs the tool, and writes the reply from
  its numbers. ``understood`` always says how the question was read.
- **Foundry** (``regista.cloud.foundry.foundry_scout_answer``): a Microsoft Agent Framework agent on a Foundry model
  that calls these tools through Regista's MCP server and answers with what they returned. ``from_foundry`` re-runs
  its last player call for the cards and checks every number in the reply against the tools' results.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from regista.season.profiles import HEADLINE, RATIOS, STATS, Season, card

Record = dict[str, Any]

POSITIONS = {"GK": ("goalkeeper", "goalkeepers"), "DF": ("defender", "defenders"), "MF": ("midfielder", "midfielders"),
             "FW": ("forward", "forwards")}
MIN_SHARE = 0.4  # rankings count players with at least this share of the most minutes (the percentiles' rule too)
RATIO_MIN = {"pass_accuracy": 50, "take_on_success": 5, "shot_accuracy": 5}  # attempts a ratio needs before it ranks
MAX_LIMIT = 20
DEFAULT_LIMIT = 5
GID = re.compile(r"^pl_[a-z0-9_]{1,40}$")


# ---------------------------------------------------------------------------- the tools

def sort_keys() -> list[str]:
    return [*STATS, *RATIOS, "minutes", "name"]


def stat_label(key: str) -> str:
    if key in STATS:
        return STATS[key][0]
    if key in RATIOS:
        return RATIOS[key][0]
    return {"minutes": "Minutes", "name": "Name"}.get(key, key)


def _eligible(season: Season) -> list[Record]:
    return [p for p in season.profiles.values() if p["appearances"] > 0]


def default_min_minutes(season: Season) -> float:
    most = max((p["minutes"] for p in _eligible(season)), default=0.0)
    return round(MIN_SHARE * most, 1)


def stat_of(p: Record, key: str, rank: tuple[int, int, int] | None = None) -> Record:
    """One stat of one player as the tools report it: per 90 and the count it came from, or a ratio and its parts."""
    if key in RATIOS:
        _label, num, den = RATIOS[key]
        v = p["ratios"][key]
        out = {"key": key, "label": RATIOS[key][0], "kind": "ratio", "value": v,
               "display": f"{round(100 * v)}%" if v is not None else "n/a", "count": p["counts"][num], "of": p["counts"][den]}
    elif key in STATS:
        out = {"key": key, "label": STATS[key][0], "kind": "per90", "value": p["per90"][key], "display": f"{p['per90'][key]:g} per 90",
               "count": p["counts"][key], "minutes": p["minutes"], "percentile": p["percentiles"].get(key)}
    else:
        out = {"key": "minutes", "label": "Minutes", "kind": "total", "value": p["minutes"], "display": f"{p['minutes']:g} minutes",
               "count": p["appearances"]}
    if rank:
        out["rank"], out["of_players"], out["tied_with"] = rank
    return out


def _value(p: Record, key: str) -> float:
    if key in RATIOS:
        return p["ratios"][key] if p["ratios"][key] is not None else -1.0
    if key in STATS:
        return p["per90"][key]
    return p["minutes"]


def rank_in_position(season: Season, p: Record, key: str) -> tuple[int, int, int]:
    """(rank, players, others tied) for ``key`` among players in the same position who qualify (minutes, and attempts
    for ratios); ties share the better rank."""
    group = [q for q in _qualified(season, key, default_min_minutes(season)) if q["position"] == p["position"]]
    if p not in group:
        group.append(p)
    v = _value(p, key)
    return 1 + sum(1 for q in group if _value(q, key) > v), len(group), sum(1 for q in group if q is not p and _value(q, key) == v)


def _qualified(season: Season, key: str, min_minutes: float) -> list[Record]:
    rows = [p for p in _eligible(season) if p["minutes"] >= min_minutes]
    if key in RATIO_MIN:
        den = RATIOS[key][2]
        rows = [p for p in rows if p["counts"][den] >= RATIO_MIN[key]]
    return rows


def search_players(season: Season, *, position: str | None = None, club: str | None = None, q: str | None = None,
                   min_minutes: float | None = None, sort: str = "minutes", order: str = "desc", limit: int = 10,
                   ids: list[str] | None = None) -> Record:
    """Players filtered and sorted. ``sort`` is a stat key (per 90), a ratio key, "minutes" or "name"; ``order`` desc
    (most first) or asc; ``ids`` keeps only those global ids. ``min_minutes`` None means the default for rankings (40% of the most minutes; 0 for sorts by
    minutes or name). Ratios also need a few attempts (``RATIO_MIN``). Unknown values come back as ``error``."""
    if sort not in sort_keys():
        return {"error": f"unknown sort {sort!r}", "sort_keys": sort_keys()}
    if position and position.upper() not in POSITIONS:
        return {"error": f"unknown position {position!r}", "positions": list(POSITIONS)}
    if order not in ("desc", "asc"):
        return {"error": f"unknown order {order!r}", "orders": ["desc", "asc"]}
    limit = max(1, min(MAX_LIMIT, int(limit)))
    ranking = sort not in ("minutes", "name")
    floor = (default_min_minutes(season) if ranking else 0.0) if min_minutes is None else float(min_minutes)
    rows = _qualified(season, sort, floor)
    if position:
        rows = [p for p in rows if p["position"] == position.upper()]
    if club:
        c = club.lower().strip()
        rows = [p for p in rows if c in (p["club_id"].lower(), p["club"].lower(), p["short_name"].lower()) or c in p["club"].lower()]
    if ids:
        keep = set(ids)
        rows = [p for p in rows if p["global_id"] in keep]
    if q:
        words = q.lower().split()
        rows = [p for p in rows if all(w in p["name"].lower() or w in p["club"].lower() for w in words)]
    if sort == "name":
        rows.sort(key=lambda p: p["name"], reverse=order == "asc")
    else:
        rows.sort(key=lambda p: (-_value(p, sort) if order == "desc" else _value(p, sort), p["name"]))
    out = []
    for p in rows[:limit]:
        out.append({"global_id": p["global_id"], "name": p["name"], "club": p["club"], "position": p["position"],
                    "kit_number": p["kit_number"], "appearances": p["appearances"], "minutes": p["minutes"],
                    "stat": stat_of(p, sort, rank_in_position(season, p, sort) if ranking else None),
                    "headline_per90": {k: p["per90"][k] for k in HEADLINE if p["counts"][k]}})
    note = []
    if floor:
        note.append(f"players with at least {floor:g} minutes")
    if sort in RATIO_MIN:
        note.append(f"at least {RATIO_MIN[sort]} {STATS[RATIOS[sort][2]][0].lower()}")
    return {"players": out, "matched": len(rows), "sort": sort, "sort_label": stat_label(sort), "order": order,
            "min_minutes": floor, "note": "; ".join(note) or None}


def resolve(season: Season, who: str) -> tuple[Record | None, list[Record]]:
    """A player by global id or by name: (the player, other candidates when the name fits several)."""
    who = who.strip()
    if GID.match(who):
        p = season.player(who)
        return (p if p and p["appearances"] else None), []
    words = who.lower().split()
    hits = [p for p in _eligible(season) if all(w in p["name"].lower().split() for w in words)] if words else []
    exact = [p for p in hits if p["name"].lower() == who.lower()]
    if exact:
        return exact[0], []
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def get_profile(season: Season, who: str, *, moments: int = 5) -> Record:
    """One player's profile for a reader (a model or a scout): no evidence lists, no touch map, the best few moments,
    every rate with its percentile and its rank among the same position, and the summary when there is one."""
    p, candidates = resolve(season, who)
    if p is None:
        if candidates:
            return {"error": f"{who!r} fits {len(candidates)} players; ask by global id",
                    "candidates": [{"global_id": c["global_id"], "name": c["name"], "club": c["club"], "position": c["position"]}
                                   for c in candidates]}
        return {"error": f"no player {who!r} in the league"}
    from regista.season.summaries import summary_for

    stats = {k: stat_of(p, k, rank_in_position(season, p, k)) for k in [*STATS, *RATIOS]}
    summary = summary_for(season, p)
    return {"global_id": p["global_id"], "name": p["name"], "club": p["club"], "position": p["position"], "kit_number": p["kit_number"],
            "appearances": p["appearances"], "minutes": p["minutes"], "stats": stats,
            "best_moments": [{k: m[k] for k in ("match_id", "round", "clip_id", "title", "tags", "watchability", "video_url")}
                             for m in p["moments"][:moments]],
            "matches": [{k: m[k] for k in ("round", "opponent", "home", "score")} for m in p["matches"]],
            "summary": summary["text"] if summary else None}


def compare_players(season: Season, ids: list[str]) -> Record:
    """Two or three players (global ids or names) side by side: every per-90 rate and ratio, percentiles, ranks."""
    chosen: list[Record] = []
    for who in dict.fromkeys(ids):
        p, candidates = resolve(season, who)
        if p is None:
            return get_profile(season, who)  # the same error, with candidates when the name fits several
        if p not in chosen:
            chosen.append(p)
    if not 2 <= len(chosen) <= 3:
        return {"error": "compare needs two or three different players"}
    return {"players": [{"global_id": p["global_id"], "name": p["name"], "club": p["club"], "position": p["position"],
                         "appearances": p["appearances"], "minutes": p["minutes"],
                         "stats": {k: stat_of(p, k, rank_in_position(season, p, k)) for k in [*STATS, *RATIOS]}} for p in chosen]}


# ---------------------------------------------------------------------------- the rules engine: question -> query

# Stat phrases, most specific first. Each is (pattern, stat key, position it implies or None). Matched spans are cut
# out before roles are read, so "forward passes" never reads as forwards.
STAT_PHRASES: list[tuple[str, str, str | None]] = [
    (r"shots? on target|on target", "shots_on_target", None),
    (r"shot accuracy|shooting accuracy|accurate shoot\w*|clinical", "shot_accuracy", None),
    (r"forward pass\w*|pass\w* forward|play\w* (?:the ball |it )?forward|progressive pass\w*|progressive|line[- ]breaking|vertical pass\w*",
     "forward_passes", None),
    (r"key pass\w*|chances? created|creat\w* chances|chance creat\w*|creative|creators?|unlock\w*", "key_passes", None),
    (r"playmak\w*", "key_passes", "MF"),
    (r"pass(?:ing)? accuracy|accurate pass\w*|keeps? the ball|tidy|retain\w* possession|pass completion", "pass_accuracy", None),
    (r"take[- ]?on success|dribbl\w* success|success\w* (?:dribbl\w*|take[- ]?ons?)", "take_on_success", None),
    (r"take[- ]?ons?|dribbl\w*|beat\w* (?:his |her |their |a |the )?(?:man|player|defenders?|opponents?)|1v1|one[- ]on[- ]one|skilful|skillful",
     "take_ons_won", None),
    (r"nutmeg\w*|megs", "nutmegs", None),
    (r"assists?|provider|set\w* up goals", "assists", None),
    (r"cross(?:es|er|ers|ing)?\b", "crosses", None),
    (r"goal ?scor\w*|\bgoals?\b|\bscor(?:e|es|ed|er|ers|ing)\b|finish(?:er|ers|ing)|prolific|in front of goal", "goals", None),
    (r"shoot\w*|\bshots?\b|shooters?", "shots", None),
    (r"win\w* (?:the )?ball back|ball[- ]?win\w*|recover\w*|regain\w*|win\w* (?:back )?possession", "recoveries", None),
    (r"tackl\w*", "tackles_won", None),
    (r"intercept\w*|read\w* the game|cut\w* out passes", "interceptions", None),
    (r"\bpress\w*|harass\w*", "pressures", None),
    (r"clear(?:s|ances?|ing)\b", "clearances", None),
    (r"shot[- ]stop\w*", "saves", "GK"),
    (r"\bsaves?\b", "saves", None),
    (r"fouls? won|win\w* fouls|draw\w* fouls|fouled", "fouls_won", None),
    (r"carr(?:y|ies|ying)|runs? with the ball|ball[- ]carr\w*", "carries", None),
    (r"touches|most involved|on the ball the most|busiest", "touches", None),
    (r"\bpass(?:es|er|ers|ing)?\b", "passes_completed", None),
    (r"most minutes|played the most|ever[- ]?present|minutes", "minutes", None),
]
ROLE_PHRASES: list[tuple[str, str]] = [
    (r"goal ?keepers?|keepers?|\bgks?\b|goalies?", "GK"),
    (r"defenders?|cent(?:re|er)[- ]?backs?|full[- ]?backs?|wing[- ]?backs?|\bcbs?\b|defen[cs]e|back (?:four|line)", "DF"),
    (r"midfielders?|midfield|anchors?|holding|box[- ]to[- ]box|number (?:6|8|10)|no\.? ?(?:6|8|10)\b|regista", "MF"),
    (r"wingers?|strikers?|forwards?|attackers?|cent(?:re|er)[- ]forwards?|number 9|no\.? ?9\b|front (?:three|line)", "FW"),
]
FEWEST = r"\b(fewest|least|lowest|worst|fewer|bottom)\b"
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COMPARE = r"\b(compare|comparison|vs\.?|versus|against each other|or)\b"


def _names(season: Season, text: str) -> tuple[list[Record], list[str]]:
    """Players the question names: full names first, then single first or last names (a shared surname names
    every player who has it). Returns (players, the words that named them)."""
    low = text.lower()
    found: list[Record] = []
    words: list[str] = []
    players = _eligible(season)
    for p in sorted(players, key=lambda p: -len(p["name"])):
        if re.search(rf"\b{re.escape(p['name'].lower())}\b", low) and p not in found:
            found.append(p)
            words.append(p["name"])
            low = low.replace(p["name"].lower(), " ")
    taken = {w for p in players for w in p["name"].lower().split()}
    for w in re.findall(r"[a-zà-ÿ'-]{3,}", low):
        if w in taken and w not in words:
            hits = [p for p in players if w in p["name"].lower().split()]
            for p in hits:
                if p not in found:
                    found.append(p)
            words.append(w)
    return found, words


def _club(season: Season, text: str) -> Record | None:
    low = text.lower()
    for c in season.league["clubs"]:
        first = c["name"].split()[0].lower()
        if c["name"].lower() in low or re.search(rf"\b{re.escape(first)}\b", low) or re.search(rf"\b{c['short_name']}\b", text):
            return c
    return None


def parse(season: Season, question: str) -> Record:
    """Read a question into a query: {mode: rank|player|compare|none, position, club, ids, sort, order, limit, heard}.
    ``heard`` lists each phrase that set something, for ``understood``."""
    text = " " + question.strip() + " "
    low = text.lower()
    heard: list[str] = []
    sorts: list[str] = []
    implied = None
    rest = low
    for pat, key, pos in STAT_PHRASES:
        m = re.search(pat, rest)
        if m:
            if key == "passes_completed" and {"forward_passes", "key_passes", "pass_accuracy"} & set(sorts):
                rest = rest[:m.start()] + " " + rest[m.end():]
                continue
            if key not in sorts:
                sorts.append(key)
                heard.append(f"“{m.group(0).strip()}” → {stat_label(key).lower()}")
            implied = implied or pos
            rest = rest[:m.start()] + " " + rest[m.end():]
    position = None
    for pat, pos in ROLE_PHRASES:
        m = re.search(pat, rest)
        if m:
            position = pos
            heard.append(f"“{m.group(0).strip()}” → {POSITIONS[pos][1]} ({pos})")
            break
    if position is None and implied:
        position = implied
        heard.append(f"{stat_label(sorts[0]).lower()} → {POSITIONS[implied][1]} ({implied})")
    club = _club(season, text)
    if club:
        heard.append(f"club: {club['name']}")
    named, name_words = _names(season, text)
    order = "asc" if re.search(FEWEST, low) else "desc"
    m = re.search(r"\b(?:top|best|first)\s+(\d{1,2}|" + "|".join(NUMBERS) + r")\b", low) or \
        re.search(r"\b(\d{1,2}|" + "|".join(NUMBERS) + r")\s+(?:players|wingers|strikers|forwards|midfielders|defenders|keepers|goalkeepers|names|options)\b", low)
    limit = DEFAULT_LIMIT
    if m:
        limit = max(1, min(MAX_LIMIT, int(NUMBERS.get(m.group(1), m.group(1)))))
    if named and club and len({p["club_id"] for p in named}) > 1:
        named = [p for p in named if p["club_id"] == club["club_id"]] or named
    if len(named) >= 2 and (re.search(COMPARE, low) or len(name_words) >= 2) and len(named) <= 3:
        mode = "compare"
    elif named and len(name_words) == 1 and len(named) > 1 and not (sorts or position):
        mode = "ambiguous"
    elif named and len(named) == 1:
        mode = "player"
    elif named and (sorts or position):
        mode = "rank"  # a shared surname plus a stat: rank those players
    elif named:
        mode = "ambiguous"
    elif sorts or position or club:
        mode = "rank"
    else:
        mode = "none"
    if named:
        heard.append("named: " + ", ".join(p["name"] for p in named))
    return {"mode": mode, "position": position, "club": club["club_id"] if club else None, "club_name": club["name"] if club else None,
            "name_words": name_words,
            "ids": [p["global_id"] for p in named], "sort": sorts[0] if sorts else ("minutes" if mode == "rank" else None),
            "also": sorts[1:3], "order": order, "limit": limit, "heard": heard}


def understood_text(query: Record, result: Record | None = None) -> str:
    """How the question was read, in one line: "forwards (“winger”) · most take-ons won per 90 · top 5"."""
    parts: list[str] = []
    if query["mode"] in ("player", "compare", "ambiguous"):
        parts.append({"player": "one player", "compare": "compare", "ambiguous": "a name several players share"}[query["mode"]])
    if query.get("club_name"):
        parts.append(query["club_name"])
    if query.get("position"):
        parts.append(POSITIONS[query["position"]][1])
    if query["mode"] == "rank" and query.get("sort"):
        label = stat_label(query["sort"]).lower()
        most = "fewest" if query["order"] == "asc" else "most"
        if query["sort"] in RATIOS:
            parts.append(f"{'lowest' if query['order'] == 'asc' else 'highest'} {label}")
        elif query["sort"] == "minutes":
            parts.append(f"{most} minutes")
        else:
            parts.append(f"{most} {label} per 90")
        parts.append(f"top {query['limit']}")
    elif query.get("sort") and query["mode"] in ("player", "compare"):
        parts.append(stat_label(query["sort"]).lower())
    if result and result.get("note"):
        parts.append(result["note"])
    read = " · ".join(parts) or "nothing I recognise"
    return read + (f" (heard {'; '.join(query['heard'])})" if query["heard"] else "")


# ---------------------------------------------------------------------------- the rules engine: query -> answer

EXAMPLES = ["a winger with the most take-ons", "midfielders who win the ball back", "the best finisher",
            "defenders who play forward passes", "compare Amari Ustinov and Hugo Fontaine"]


def api_card(season: Season, gid: str, sort: str | None) -> Record | None:
    """The card the Scout page shows (``profiles.card``), plus the stat the answer is about with its rank."""
    p = season.player(gid)
    if p is None:
        return None
    c = card(p)
    if sort:
        c["stat"] = stat_of(p, sort, rank_in_position(season, p, sort) if sort not in ("minutes", "name") else None)
    c["profile_url"] = f"/players/{gid}"
    return c


def _group(query: Record) -> str:
    pos = POSITIONS[query["position"]][1] if query.get("position") else "players"
    if query.get("name_words") and query["mode"] == "rank":
        return f"the {pos} named {' or '.join(w.title() for w in query['name_words'])}"
    if query.get("club_name"):
        club = query["club_name"]
        return f"{club}{chr(39) if club.endswith('s') else chr(39) + 's'} {pos}"
    return f"the league's {pos}"


def _fmt(s: Record) -> str:
    if s["kind"] == "ratio":
        return f"{s['display']} ({s['count']} of {s['of']})"
    if s["kind"] == "total":
        return s["display"]
    return f"{s['value']:g} per 90 ({s['count']} in {s['minutes']:g} minutes)"


def _surname(name: str) -> str:
    return name.split()[-1]


def answer_rules(season: Season, question: str, trace: list[Record] | None = None) -> Record:
    """The rules engine's whole answer: the query it read, the tool it ran, the reply and the cards."""
    from regista.conversation import timed_step

    trace = trace if trace is not None else []
    query = timed_step(trace, "scout.parse", parse, season, question)
    mode = query["mode"]
    result: Record | None = None
    if mode == "rank":
        result = timed_step(trace, "scout.search_players", lambda: search_players(  # a shared surname: rank only those
            season, position=query["position"], club=query["club"], sort=query["sort"], order=query["order"],
            limit=query["limit"], ids=query["ids"] or None, min_minutes=0 if query["ids"] else None))
        ids = [r["global_id"] for r in result["players"]]
        reply = _rank_reply(query, result)
        sort = query["sort"]
    elif mode == "player":
        result = timed_step(trace, "scout.get_profile", get_profile, season, query["ids"][0])
        ids, sort = query["ids"], query["sort"]
        reply = _player_reply(season, query, result)
    elif mode == "compare":
        result = timed_step(trace, "scout.compare_players", compare_players, season, query["ids"])
        ids, sort = query["ids"], query["sort"]
        reply = _compare_reply(query, result)
    elif mode == "ambiguous":
        ids, sort = query["ids"], None
        reply = (("That name fits" if len(query["name_words"]) <= 1 else "Those names fit") + f" {len(ids)} players: " + "; ".join(f"{p['name']} ({p['club']}, {p['position']})" for p in
                 (season.player(g) for g in ids)) + ". Use the full name.")
    else:
        ids, sort = [], None
        reply = ("I could not tell which players or which stat you mean. Try: " + "; ".join(f"“{e}”" for e in EXAMPLES[:4]) + ".")
    return {"reply": reply, "understood": understood_text(query, result if mode == "rank" else None),
            "query": {k: query[k] for k in ("mode", "position", "club", "ids", "sort", "also", "order", "limit")},
            "players": [c for c in (api_card(season, g, sort) for g in ids) if c], "trace": trace,
            "answered_by": "rules", "tools_used": []}


def _rank_reply(query: Record, result: Record) -> str:
    rows = result["players"]
    if not rows:
        return f"No {_group(query).replace('the league', 'league')} qualify for that ({result.get('note') or 'no matches'})."
    s = rows[0]["stat"]
    if query["sort"] == "minutes":
        head = f"{rows[0]['name']} ({rows[0]['club']}) has played the most minutes among {_group(query)}: {_fmt(s)}."
    else:
        most = ("the lowest" if query["order"] == "asc" else "the highest") if s["kind"] == "ratio" else \
            ("the fewest" if query["order"] == "asc" else "the most")
        head = f"{rows[0]['name']} ({rows[0]['club']}) has {most} {s['label'].lower()}" + \
            ("" if s["kind"] == "ratio" else " per 90") + f" among {_group(query)}: {_fmt(s)}."
    nxt = [f"{r['name']} {r['stat']['display'].replace(' per 90', '')}" for r in rows[1:3]]
    return head + (f" Next: {' and '.join(nxt)}." if nxt else "")


def _player_reply(season: Season, query: Record, prof: Record) -> str:
    if "error" in prof:
        return prof["error"]
    if query["sort"] and query["sort"] != "minutes":
        s = prof["stats"][query["sort"]]
        return (f"{prof['name']} ({prof['club']}): {s['label'].lower()} {_fmt(s)}, {'joint ' if s['tied_with'] else ''}"
                f"{_ordinal(s['rank'])} of {s['of_players']} "
                f"{POSITIONS[prof['position']][1]}.")
    if prof.get("summary"):
        return prof["summary"]
    return f"{prof['name']} ({prof['club']}, {prof['position']}): {prof['appearances']} appearances, {prof['minutes']:g} minutes."


def _compare_reply(query: Record, cmp: Record) -> str:
    if "error" in cmp:
        return cmp["error"]
    ps = cmp["players"]
    keys = [query["sort"]] if query["sort"] and query["sort"] != "minutes" else []
    keys += [k for k in query.get("also", []) if k not in keys]
    if not keys:  # the headline rates where they differ most, relative to the larger
        def spread(k: str) -> float:
            vs = [p["stats"][k]["value"] or 0 for p in ps]
            return (max(vs) - min(vs)) / max(vs) if max(vs) else 0.0
        keys = sorted((k for k in HEADLINE if any(p["stats"][k]["value"] for p in ps)), key=lambda k: (-spread(k), HEADLINE.index(k)))[:3]
    names = " vs ".join(_surname(p["name"]) if len({_surname(q["name"]) for q in ps}) == len(ps) else p["name"] for p in ps)
    bits = []
    for k in keys:
        vals = " vs ".join(p["stats"][k]["display"].replace(" per 90", "") for p in ps)
        bits.append(f"{stat_label(k).lower()} {vals}" + ("" if k in RATIOS else " per 90"))
    return f"{names}: " + "; ".join(bits) + "."


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


# ---------------------------------------------------------------------------- the Foundry engine's answer, checked

PLAYER_TOOLS = ("search_players", "get_profile", "compare_players")


def run_tool(season: Season, name: str, args: Record) -> Record:
    """Run one of the player tools in-process with the arguments a model gave the MCP server."""
    args = dict(args or {})
    if name == "search_players":
        allowed = {"position", "club", "q", "min_minutes", "sort", "order", "limit"}
        return search_players(season, **{k: v for k, v in args.items() if k in allowed and v is not None})
    if name == "get_profile":
        return get_profile(season, str(args.get("player") or args.get("global_id") or ""))
    if name == "compare_players":
        ids = args.get("players") or args.get("global_ids") or []
        return compare_players(season, [str(i) for i in (ids if isinstance(ids, list) else str(ids).split(","))])
    return {"error": f"unknown tool {name}"}


def _call_text(name: str, args: Record) -> str:
    shown = ", ".join(f"{k}={v}" for k, v in (args or {}).items() if v not in (None, "", []))
    return f"{name}({shown})"


def _numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text)]


def held_numbers(data: Any) -> list[float]:
    """Every number in ``data`` (tool results or facts), plus each ratio as a percentage."""
    known = _numbers(json.dumps(data, ensure_ascii=False))

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if x.get("kind") == "ratio" and isinstance(x.get("value"), (int, float)):
                known.append(100 * x["value"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(data)
    return known


def _holds(n: float, k: float) -> bool:
    """``n`` is ``k`` as written: to two decimals, or a whole number rounding a larger value (81% for 81.1)."""
    return abs(n - k) < 0.051 or (n == round(n) and k > 1.5 and abs(n - k) < 0.51)


def unheld(text: str, known: list[float]) -> list[str]:
    """Numbers in ``text`` that ``known`` does not hold."""
    return [raw for raw in re.findall(r"(?<![\w.])\d+(?:\.\d+)?", text) if not any(_holds(float(raw), k) for k in known)]


def unverified_numbers(reply: str, results: list[Record]) -> list[str]:
    """Numbers in the reply that no tool result holds (allowing rounding, and ratios as percentages)."""
    return unheld(reply, held_numbers(results))


def from_foundry(season: Season, rules: Record, text: str, calls: list[tuple[str, Record]], answered_by: str) -> Record:
    """The Foundry answer in the Scout shape: the model's reply; cards and ``understood`` from its last player tool
    call, run again here (so the cards are what it read); every number in the reply checked against its tool results."""
    player_calls = [(n, a) for n, a in calls if n in PLAYER_TOOLS]
    results = [run_tool(season, n, a) for n, a in player_calls]
    out = {**rules, "reply": text.strip(), "answered_by": answered_by, "tools_used": [n for n, _a in calls]}
    if player_calls:
        name, args = player_calls[-1]
        last = results[-1]
        if name == "search_players" and "players" in last:
            ids, sort = [r["global_id"] for r in last["players"]], last["sort"]
        elif name == "compare_players" and "players" in last:
            ids, sort = [r["global_id"] for r in last["players"]], rules["query"].get("sort")
        elif name == "get_profile" and "global_id" in last:
            ids, sort = [last["global_id"]], rules["query"].get("sort")
        else:
            ids, sort = [], None
        out["players"] = [c for c in (api_card(season, g, sort) for g in ids) if c]
        out["understood"] = "Foundry called " + ", then ".join(_call_text(n, a) for n, a in player_calls) + \
            f". Regista's rules read it as: {rules['understood']}"
    else:
        out["understood"] = f"Foundry answered without a player tool; the cards are Regista's rules reading: {rules['understood']}"
    out["checked"] = {"tool_calls": len(player_calls), "numbers_not_in_tool_results": unverified_numbers(out["reply"], results)}
    return out


ScoutAnswerer = Callable[[Season, str, Record], tuple[str, list[tuple[str, Record]], str]]
