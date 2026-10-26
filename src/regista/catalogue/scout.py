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
from regista.catalogue.taxonomy import POSITION_WORDS, TIER_WORDS, level_words
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
            "career": row["career"], "board": row.get("board"), "ranked": row.get("ranked"),
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


def whole(x: float) -> int:
    """Whole minutes as the pages show them (JavaScript's Math.round: 90.5 is 91), not Python's round half to even."""
    import math

    return math.floor(x + 0.5)


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


def _pool_line(st: Record, row: Record | None = None, short: bool = False) -> str:
    """The pool line as the pages word it: "98th percentile among 33 semi-pro men forwards", "none yet · 25 of the 33
    semi-pro men forwards have none", or the engine's reason for no percentile (never a guessed one)."""
    pool = st["pool"]
    if st.get("none_yet"):
        z = st.get("zeros") or {}
        if not z.get("of"):
            return "none yet"
        who = pool.get("words") or "players"
        share = f"all {z['of']}" if z["none"] == z["of"] else f"{z['none']} of the {z['of']}"
        return f"none yet · {share} {who} have none"
    if st.get("percentile") is None:
        m = CATALOGUE.get(st.get("key") or "")
        if pool.get("reason"):
            why = pool["reason"]
        elif m is not None and m.kind == "total":
            why = "a season total, ranked by value only"
        elif row is not None and row.get("qualified") is False:
            why = f"{whole(row.get('minutes') or 0)} minutes, under the minutes a regular needs in {row.get('competition')}"
        elif m is not None and m.kind == "ratio":
            why = "too few attempts"
        else:
            why = None
        return f"no percentile ({why})" if why else "no percentile"
    small = ", a small pool" if pool.get("small") else ""
    noisy = ("; noisy" if short else "; ≈ noisy over a sample this size") if st.get("noisy") else ""
    return f"{_ordinal(round(st['percentile']))} percentile among {pool['size']} {pool['words']}{small}{noisy}"


def _stat_words(st: Record, row: Record | None = None, short: bool = False) -> str:
    """A number with its pool line: "1.64 per 90, 98th percentile among 33 semi-pro men forwards", or "none yet · 25 of
    the 33 … have none". ``short``: a noisy number says "noisy" only (a list's next rows)."""
    return _pool_line(st, row, short) if st.get("none_yet") else f"{_number(st)}, {_pool_line(st, row, short)}"


def lower_label(key: str) -> str:
    """A metric's label inside a sentence: lower case but for its abbreviations ("non-penalty xG", "npxG + xA")."""
    import re

    return re.sub(r"\b(?!xG\b|xA\b|xT\b|npxG\b)([A-Z])", lambda m: m.group(1).lower(), CATALOGUE[key].label)


def _fewest_word(key: str) -> str:
    """"fewest" for a count, "lowest" for a measure (a percentage, a distance, a speed)."""
    return "fewest" if CATALOGUE[key].kind in ("per90", "padj", "total") else "lowest"


def default_note(query: Record, position: str | None) -> str:
    """Said when the question named no stat Regista knows: which one the answer ranks by instead."""
    if not query.get("defaulted"):
        return ""
    whose = f"the {POSITION_WORDS[position][:-1]}s' first column" if position else "the default column"
    return (f" I did not find a stat I know in the question, so this ranks by {CATALOGUE[query['sort']].label} "
            f"({whose}); the Terminal's search knows every metric by name.")


def _place(r: Record) -> str:
    return f"{r['name']} ({r['club']}, {r['competition']}, {r['country']})"


def _minutes(r: Record) -> str:
    n = whole(r['minutes'])
    return f"{n:,} minute{'' if n == 1 else 's'}"


def _apps(n: int) -> str:
    return f"{n} appearance{'' if n == 1 else 's'}"


def _boards_of(result: Record, rows: list[Record]) -> list[tuple[Record | None, list[Record]]]:
    """(board or None, its rows in order) for the rows a tool returned: one entry when the list is one board."""
    boards = result.get("boards") or []
    if not boards:
        return [(None, rows)]
    out = []
    for b in boards:
        mine = [r for r in rows if r.get("board") == b["board"]]
        if mine:
            out.append((b, mine))
    return out


def _board_name(b: Record) -> str:
    """A board in words: its level ("semi-pro men"), or its gender and position ("Men, DF")."""
    if b.get("level"):
        return level_words(b["level"])
    return b["label"]


def _none_yet_line(who: str, lab: str, b: Record | None, result: Record, rows: list[Record]) -> str:
    """No one on a list has any of a count yet: "No one among the players in Ghana has any nutmegs yet (0 of 21)"."""
    n = (b or {}).get("none_yet") if b else result.get("none_yet")
    n = n if n is not None else len(rows)
    return f"No one among the {who} has any {lab} yet (0 of {n})."


def _ranked_rows(rows: list[Record]) -> list[Record]:
    return [r for r in rows if r.get("ranked") is not False]


def _minutes_top(rs: list[Record]) -> str:
    """The top of a minutes list, ties named: "Andres Vidal (…), 90 minutes, shared with at least 4 others"."""
    top = rs[0]
    tied = [r for r in rs[1:] if whole(r["minutes"]) == whole(top["minutes"])]
    share = ""
    if tied:
        n = len(tied)
        share = f", shared with {'at least ' if n == len(rs) - 1 else ''}{n} {'other' if n == 1 else 'others'}"
    return f"{_place(top)}, {_minutes(top)}{share}"


def _minutes_reply(result: Record, query: Record) -> str:
    """Minutes played: a total, by value within each level (one list per level when the rows hold more than one)."""
    rows = result.get("players") or []
    who = query["who"]
    most = "fewest" if query.get("order") == "asc" else "most"
    groups = _boards_of(result, rows)
    if len(groups) == 1:
        rs = _ranked_rows(rows) or rows
        top = rs[0]
        tied = [r for r in rs[1:] if whole(r["minutes"]) == whole(top["minutes"])]
        if tied:
            return f"The {most} minutes among the {who}: {_minutes_top(rs)}."
        out = f"{_place(top)} has played the {most} minutes among the {who}: {_minutes(top)} in " \
              f"{_apps(top['appearances'])}."
        nxt = [f"{r['name']} ({_minutes(r)})" for r in rs[1:3]]
        return out + (f" Next: {' and '.join(nxt)}." if nxt else "")
    parts = [f"{_cap(_board_name(b))}: {_minutes_top(_ranked_rows(rs) or rs)}." for b, rs in groups[:3]]
    more = len(groups) - 3
    return (f"One list per level for the {who}, {most} minutes played first within the level. " + " ".join(parts)
            + (f" {more} more {'level is' if more == 1 else 'levels are'} in the list." if more > 0 else ""))


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def reply_for(result: Record, query: Record) -> str:
    """The rules reply, in the shape of the ranking rule the tool used (``RANK_RULE``): one level, "<name> leads …";
    more than one level and one position (``rank_by`` pool), the rule first and each row with its own pool line; more
    than one level and more than one position, one list per level. A row the rule does not rank (below its minimum
    attempts, none yet) never leads; a list where no one has any of a count says so."""
    rows = result.get("players") or []
    who = query["who"]
    if query["sort"] == "minutes":
        return _minutes_reply(result, query) if rows else f"No {who} in the catalogue match that yet."
    lab = lower_label(query["sort"])
    note = default_note(query, query.get("position"))
    if not rows:
        return f"No {who} in the catalogue match that yet.{note}"
    asc = query.get("order") == "asc"
    groups = _boards_of(result, rows)
    counted = result.get("with_any") is not None
    if result.get("rank_by") == "pool":
        head = (f"{result.get('total', len(rows))} {who} from several levels, ranked by each player's percentile for {lab} "
                f"in their own pool{', lowest first' if asc else ''}{', one list per gender' if len(groups) > 1 else ''}.")
        parts = []
        for b, rs in groups:
            ranked = _ranked_rows(rs)
            lead = f"{b['label']}, first" if b is not None and len(groups) > 1 else "First"
            if not ranked:
                if counted and all((r.get("stat") or {}).get("none_yet") for r in rs):
                    parts.append(_none_yet_line(f"{b['label'].lower()} {who}" if b and len(groups) > 1 else who, lab, b,
                                                result, rs))
                else:
                    parts.append(f"{b['label']}: no one has a percentile for {lab} yet." if b is not None and len(groups) > 1
                                 else f"No one has a percentile for {lab} yet.")
                continue
            top = ranked[0]
            line = f"{lead}: {_place(top)}, {_stat_words(top['stat'], top)}."
            nxt = [f"{r['name']} ({_stat_words(r['stat'], r, short=True)})" for r in ranked[1:3]]
            parts.append(line + (f" Next: {' and '.join(nxt)}." if nxt else ""))
        out = head + " " + " ".join(parts)
    elif len(groups) > 1:   # value mode, one list per level
        head = (f"One list per level for the {who}, ranked by {lab} within the level{' (lowest first)' if asc else ''}: "
                "a raw number is only compared with players at the same level.")
        parts = []
        for b, rs in groups[:3]:
            ranked = _ranked_rows(rs)
            if not ranked:
                none = counted and all((r.get("stat") or {}).get("none_yet") for r in rs)
                parts.append(f"{_cap(_board_name(b))}: {'no one has any yet' if none else 'no one ranked yet'}.")
                continue
            parts.append(f"{_cap(_board_name(b))}: {_place(ranked[0])}, {_stat_words(ranked[0]['stat'], ranked[0])}.")
        more = len(groups) - 3
        out = head + " " + " ".join(parts) + \
            (f" {more} more {'level is' if more == 1 else 'levels are'} in the list." if more > 0 else "")
    else:
        ranked = _ranked_rows(rows)
        if not ranked:
            if counted and all((r.get("stat") or {}).get("none_yet") for r in rows):
                return _none_yet_line(who, lab, None, result, rows) + note
            top = rows[0]
            return (f"No one among the {who} has enough attempts to be ranked for {lab} yet. Listed first: {_place(top)}, "
                    f"{_stat_words(top['stat'], top)}.{note}")
        top = ranked[0]
        st = top["stat"]
        if asc:
            head = f"{_place(top)} has the {_fewest_word(query['sort'])} {lab} among the {who}: {_stat_words(st, top)}."
        else:
            head = f"{_place(top)} leads the {who} for {lab}: {_stat_words(st, top)}."
        nxt = [f"{r['name']} {_number(r['stat'])}" for r in ranked[1:3]]
        out = head + (f" Next: {' and '.join(nxt)}." if nxt else "")
    if counted and result.get("none_yet"):
        out += f" {result['with_any']} of {result['with_any'] + result['none_yet']} have any so far."
    return out + note


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
    asked = resolve_stat(q, place["rest"] or question)
    if named:
        result = timed_step(trace, "scout.get_catalogue_player", tools.get_player, cm, named)
        c = player_card(cm, named, sort=asked if asked != "minutes" else None)
        if c and asked == "minutes":
            reply = f"{_place(c)}: {_minutes(c)} in {_apps(c['appearances'])}."
        elif c:
            reply = f"{_place(c)}: {lower_label(c['stat']['key'])} {_stat_words(c['stat'], c)}."
        else:
            reply = result.get("error", "")
        query = {"mode": "player", "ids": [named], "where": w, "sort": c["stat"]["key"] if c else None,
                 "position": None, "order": "desc", "limit": 1}
        return {"reply": reply, "understood": _understood(place, q, query, named=True), "query": query,
                "players": [c] if c else [], "trace": trace, "answered_by": "rules", "tools_used": [], "where": "catalogue",
                "warning": None}
    sort = asked or metric_for(None, q["position"])
    order = "asc" if q["order"] == "asc" else "desc"
    args = {**{k: w[k] for k in ("tier", "age_group", "gender", "country", "competition") if k in w},
            "position": q["position"], "sort": sort, "order": order, "limit": q["limit"]}
    if sort == "minutes":   # a total with no percentile: every player counts, not only those with enough minutes for one
        args["min_minutes"] = 0
    result = timed_step(trace, "scout.search_catalogue_players", lambda: tools.search_players(cm, **args))
    pos = POSITION_WORDS.get(q["position"] or "", "players")
    where_words = " ".join(x for x in (level_phrase(w), pos) if x) + (f" in {w['country']}" if w.get("country") else "") + \
        (f" in {v['comp_name'][w['competition']]}" if w.get("competition") else "")
    query = {"mode": "rank", "where": w, "position": q["position"], "sort": sort, "order": order, "limit": q["limit"],
             "who": where_words, "args": args, "defaulted": asked is None}
    reply = reply_for(result, query) if "error" not in result else result["error"]
    return {"reply": reply, "understood": _understood(place, q, query),
            "query": {k: query[k] for k in query if k not in ("who", "defaulted")},
            "players": [card(r) for r in result.get("players", [])], "trace": trace, "answered_by": "rules",
            "tools_used": [], "where": "catalogue",
            # minutes have no percentile: the reply says they rank within each level, so no percentile warning
            "warning": None if sort == "minutes" else result.get("warning"), "result_total": result.get("total"),
            "with_any": result.get("with_any"), "none_yet": result.get("none_yet")}


def level_phrase(w: Record) -> str:
    """The level words of a place filter, each word once: "semi-pro men", "college women", "U19", "college" (the age
    group only where it is not the tier's own, as ``level_words`` says it)."""
    if {"tier", "age_group", "gender"} <= set(w):
        return level_words(f"{w['tier']}/{w['age_group']}/{w['gender']}")
    tier = TIER_WORDS.get(w.get("tier", ""), w.get("tier", "").replace("_", "-"))
    age = w.get("age_group", "")
    age = "" if age == "senior" or (age == "college" and tier == "college") else age
    return " ".join(x for x in (tier, age, w.get("gender", "")) if x)


def _phrases() -> list[tuple[str, str]]:
    """(phrase, metric key) for every catalogue metric: its label and its key in words, longest first."""
    out: dict[str, str] = {}
    for k, m in CATALOGUE.items():
        for ph in (m.label.lower(), k.replace("_", " ")):
            ph = ph.split(" (")[0].strip()
            if len(ph) >= 3:
                out.setdefault(ph, k)
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


PHRASES = _phrases()


# "win the most aerial duels" names "aerial duels won": every metric whose label ends in "won", by the verb
WON = sorted(((ph[:-4], k) for ph, k in PHRASES if ph.endswith(" won")), key=lambda kv: -len(kv[0]))


def catalogue_stat(text: str) -> tuple[str, str] | None:
    """(metric key, the words that named it) for a stat by any Terminal metric's label or key, singular or plural ("yellow
    cards", "fouls", "sprint distance", "touches in the box"), or a "won" metric by its verb ("wins the most aerial
    duels"); the longest name wins."""
    import re

    low = f" {text.lower()} "
    best: tuple[str, str] | None = None
    for stem, k in WON:
        st = stem[:-1] if stem.endswith("s") else stem
        m = re.search(rf"(?<![\w])w(?:in|ins|inning|on)(?:\s+the)?(?:\s+(?:most|more|fewest|least))?\s+{re.escape(st)}s?(?![\w])", low)
        if m:
            best = (k, m.group(0).strip())
            break
    for ph, k in PHRASES:
        stem = ph[:-1] if ph.endswith("s") else ph
        m = re.search(rf"(?<![\w]){re.escape(stem)}s?(?![\w])", low)
        if m:
            if best is None or len(ph) > len(CATALOGUE[best[0]].label):
                best = (k, m.group(0).strip())
            break
    return best


def stat_asked(q: Record) -> str | None:
    """The stat the question named (the league parser's key), else None. A rank with no stat reads "minutes" in the
    league parser, so minutes count as asked only when the parser heard them ("most minutes", "played the most")."""
    if q.get("sort") == "minutes":
        return "minutes" if any(h.endswith("→ minutes") for h in q.get("heard") or []) else None
    return q.get("sort")


def _parser_words(q: Record) -> str | None:
    """The words the league parser read as its first stat ("aerial duels" in "“aerial duels” → aerial duels")."""
    import re

    from regista.season.scout import stat_label

    if q.get("sort") in (None, "minutes"):
        return None
    tail = f"→ {stat_label(q['sort']).lower()}"
    for h in q.get("heard") or []:
        m = re.match(r"“(.+)” → ", h)
        if m and h.endswith(tail):
            return m.group(1).lower()
    return None


def resolve_stat(q: Record, text: str) -> str | None:
    """The catalogue metric key a question asks for, "minutes", or None (no stat: the position's first column).

    The league parser's stat first, mapped to the Terminal's metric; a catalogue metric named by longer words that hold
    the parser's ("touches in the box" over "touches", "win the most aerial duels" over "aerial duels") wins, and so does
    any catalogue metric when the parser found none it maps. ``q["heard"]`` then names the catalogue's metric."""
    asked = stat_asked(q)
    words = _parser_words(q)
    _catalogue_heard(q)
    known = asked == "minutes" or (asked is not None and SORT_OF.get(asked, asked) in CATALOGUE)
    hit = catalogue_stat(text)
    if hit and (not known or (words and words in hit[1].lower() and len(hit[1]) > len(words)
                              and SORT_OF.get(asked, asked) != hit[0])):
        heard = q.get("heard") or []
        if words:   # the parser's line gives way to the catalogue's
            heard = [h for h in heard if not h.startswith(f"“{words}” → ")]
        q["heard"] = [*heard, f"“{hit[1]}” → {CATALOGUE[hit[0]].label.lower()}"]
        return hit[0]
    if asked is None or asked == "minutes":
        return asked
    return SORT_OF.get(asked, asked) if known else None


def _catalogue_heard(q: Record) -> None:
    """The parser's "heard" lines name the catalogue's metric, not the league profile's stat: "“shots” → shots" (the
    Terminal's shots leave penalties out), "“forward passes” → progressive passes"."""
    from regista.season.scout import stat_label

    keys = [k for k in [q.get("sort"), *(q.get("also") or [])] if k not in (None, "minutes")]
    for k in keys:
        mk = SORT_OF.get(k, k)
        if mk not in CATALOGUE:
            continue
        old, new = f"→ {stat_label(k).lower()}", f"→ {CATALOGUE[mk].label.lower()}"
        q["heard"] = [h.replace(old, new) if h.endswith(old) else h for h in q.get("heard") or []]


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
        if query["sort"] == "minutes":
            parts.append(f"{'fewest' if query['order'] == 'asc' else 'most'} minutes played")
            parts.append(f"top {query['limit']}")
            parts.append("within each player's level")
        else:
            m = CATALOGUE[query["sort"]]
            parts.append(f"{_fewest_word(query['sort']) if query['order'] == 'asc' else 'most'} {m.label.lower()}"
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
