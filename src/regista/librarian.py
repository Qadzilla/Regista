"""The Librarian: natural-language clip search over a match's labels. Local, no cloud, no model.

    python -m regista.librarian data/synthetic/sample/syn_0294 "find me Castellanos doing a nutmeg"

How it works: a query is parsed into a player (surname, first name, kit number, team,
position word), a set of tags (with synonyms: "meg" is a nutmeg, "strike" is a shot),
an optional minute window ("in the first 10 minutes", "second half"), an optional result
limit ("top 3"), and an optional segment kind ("replays of"). Matching labels are ranked by
watchability. If nothing matches every requested tag, the search relaxes to any tag and
says so, so a user never gets silence without an explanation.

Tool surface
------------
``search_clips(match_dir, query, limit=10) -> dict`` is deliberately a plain function with
JSON-serialisable input and output. ``regista.mcp_server`` exposes it as an MCP tool of the
same name, so any MCP host (Copilot Agent Mode, a Microsoft Agent Framework agent, Claude)
can call it. When a Foundry-hosted model fronts the Librarian, it calls this tool rather
than re-implementing the parsing: the model decides *what* to ask, this module answers
deterministically and explainably. The returned ``parsed`` block is what makes a result
defensible on air: it states exactly how the query was understood.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from regista.clips import derive_clips, match_minute
from regista.schema import iter_jsonl

Record = dict[str, Any]

# tag -> phrases that mean it. Longer phrases are matched first.
TAG_SYNONYMS: dict[str, list[str]] = {
    "nutmeg": ["through the legs", "nutmegging", "nutmegged", "nutmegs", "nutmeg", "panna", "megs", "meg"],
    "goal": ["scoring", "scores", "scored", "score", "goals", "goal", "finishes", "finish"],
    "assist": ["assisting", "assisted", "assists", "assist"],
    "shot": ["shooting", "shoots", "shots", "shot", "strikes", "strike", "efforts", "effort", "attempts", "attempt"],
    "skill_move": ["skill moves", "skill move", "stepovers", "stepover", "elastico", "roulette", "body feint", "drag back", "tricks", "trick", "skills", "skill"],
    "take_on": ["takes on", "take-ons", "take-on", "take on", "beating", "beats", "beat", "dribbles past", "goes past", "past a defender", "one on one", "1v1"],
    "dribble": ["dribbling", "dribbles", "dribble"],
    "carry": ["carrying", "carries", "carry", "runs with the ball", "run with the ball", "driving run"],
    "pass": ["passing", "passes", "pass", "through ball", "through balls", "key pass", "key passes"],
    "cross": ["crossing", "crosses", "cross"],
    "header": ["headers", "header", "headed"],
    "tackle": ["tackling", "tackles", "tackle"],
    "interception": ["interceptions", "interception", "intercepts", "intercept"],
    "block": ["blocks", "block", "blocked"],
    "save": ["saves", "save"],
    "foul": ["fouled", "fouls", "foul"],
    "foul_won": ["wins a foul", "won a foul", "free kick won", "fouls won"],
    "card_yellow": ["yellow card", "yellow cards", "booked", "booking", "yellow"],
    "card_red": ["red card", "red cards", "sent off", "sending off"],
    "pressure": ["pressing", "presses", "press", "pressure"],
    "recovery": ["recoveries", "recovery", "wins the ball back", "ball recovery"],
    "replay_appearance": ["replays", "replay", "slow motion", "slow-mo", "slomo"],
    "highlight_appearance": ["highlights", "highlight", "highlight reel", "package"],
    "closeup_appearance": ["closeups", "closeup", "close-ups", "close-up", "close ups", "close up"],
}
STOPWORDS = {"find", "me", "show", "all", "every", "the", "a", "an", "of", "by", "from", "for", "with", "doing", "do",
             "does", "did", "please", "clips", "clip", "moments", "moment", "video", "videos", "where", "when", "his",
             "her", "their", "and", "in", "on", "at", "to", "get", "give", "want", "i", "any", "some", "best", "top",
             "this", "that", "match", "game", "footage", "player", "players", "everything", "anything"}
# position word -> (position code, preferred kit numbers in order)
POSITION_WORDS: dict[str, tuple[str, list[int]]] = {
    "goalkeeper": ("GK", [1]), "keeper": ("GK", [1]), "goalie": ("GK", [1]),
    "striker": ("FW", [9]), "strikers": ("FW", [9]), "centre-forward": ("FW", [9]), "number nine": ("FW", [9]),
    "forward": ("FW", [9, 11, 7]), "forwards": ("FW", [9, 11, 7]), "attacker": ("FW", [9, 11, 7]),
    "winger": ("FW", [7, 11]), "wingers": ("FW", [7, 11]),
    "midfielder": ("MF", [10, 8, 6]), "midfielders": ("MF", [10, 8, 6]), "playmaker": ("MF", [10]), "number ten": ("MF", [10]),
    "defender": ("DF", [4, 5, 2, 3]), "defenders": ("DF", [4, 5, 2, 3]), "full-back": ("DF", [2, 3]), "fullback": ("DF", [2, 3]),
    "centre-back": ("DF", [4, 5]), "centerback": ("DF", [4, 5]),
}


# ---------------------------------------------------------------------------- loading

@lru_cache(maxsize=8)
def _load(match_dir: str) -> tuple[Record, list[Record], list[Record], dict[str, Record]]:
    """(match header, full stream, clips, labels by clip id) for a match directory."""
    stream = list(iter_jsonl(Path(match_dir) / "events.jsonl"))
    match = next(r for r in stream if r["type"] == "match")
    clips: list[Record] = []
    labels: dict[str, Record] = {}
    path = Path(match_dir) / "clips.jsonl"
    if path.exists():
        for r in iter_jsonl(path):
            if r["type"] == "clip":
                clips.append(r)
            elif r["type"] == "label":
                labels[r["clip_id"]] = r
    return match, stream, clips, labels


def _clips_for(match_dir: str, player_id: str) -> tuple[list[Record], dict[str, Record]]:
    match, stream, clips, labels = _load(match_dir)
    mine = [c for c in clips if c["player_id"] == player_id]
    if mine:
        return mine, labels
    derived, derived_labels = derive_clips(stream, player_id)
    return derived, {lb["clip_id"]: lb for lb in derived_labels}


# ---------------------------------------------------------------------------- parsing

def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"'s\b", " ", text)  # possessives: "the striker's goal"
    text = re.sub(r"[^a-z0-9#'\- ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _find_tags(text: str) -> tuple[list[str], str]:
    """Tags mentioned in the text, longest phrase first; returns the leftover text too."""
    found: list[str] = []
    phrases = sorted(((p, tag) for tag, ps in TAG_SYNONYMS.items() for p in ps), key=lambda x: -len(x[0]))
    for phrase, tag in phrases:
        pattern = r"\b" + re.escape(phrase) + r"\b"
        if re.search(pattern, text):
            if tag not in found:
                found.append(tag)
            text = re.sub(pattern, " ", text)
    return found, re.sub(r"\s+", " ", text).strip()


def _find_minutes(text: str, match: Record) -> tuple[tuple[int, int] | None, str]:
    """Minute window from phrases like 'first 10 minutes', 'after 60', 'between 10 and 20', 'second half'."""
    total = 0
    for per in match["periods"]:
        total = max(total, match_minute(match, per["t_end"] - 0.01))
    window: tuple[int, int] | None = None
    patterns = [
        (r"\bfirst (\d+) minutes?\b", lambda m: (1, int(m.group(1)))),
        (r"\blast (\d+) minutes?\b", lambda m: (max(1, total - int(m.group(1)) + 1), total)),
        (r"\bbetween (\d+)(?:'| ?min(?:ute)?s?)? and (\d+)", lambda m: (int(m.group(1)), int(m.group(2)))),
        (r"\b(?:after|from) (?:the )?(\d+)(?:th|st|nd|rd)?(?:'| ?min(?:ute)?s?)?\b", lambda m: (int(m.group(1)), total)),
        (r"\b(?:before|until|up to) (?:the )?(\d+)(?:th|st|nd|rd)?(?:'| ?min(?:ute)?s?)?\b", lambda m: (1, int(m.group(1)))),
        (r"\bfirst half\b", lambda m: (1, 45)),
        (r"\bsecond half\b", lambda m: (46, max(46, total))),
        (r"\bin (?:the )?(\d+)(?:th|st|nd|rd) minute\b", lambda m: (int(m.group(1)), int(m.group(1)))),
    ]
    for pat, fn in patterns:
        m = re.search(pat, text)
        if m:
            window = fn(m)
            text = text[: m.start()] + " " + text[m.end():]
            break
    return window, re.sub(r"\s+", " ", text).strip()


def _find_limit(text: str) -> tuple[int | None, str]:
    m = re.search(r"\b(?:top|best|first) (\d+)\b", text)
    if m:
        return int(m.group(1)), (text[: m.start()] + " " + text[m.end():]).strip()
    return None, text


def _find_player(text: str, match: Record) -> tuple[list[Record], str, str | None, str | None]:
    """Resolve players from kit number, team + position, or a (possibly misspelt) name.

    Returns (candidates, leftover text, how, team_id). More than one candidate means the query was
    ambiguous (a kit number with no team) and every candidate is searched."""
    roster = match["players"]
    teams = {t["team_id"]: t for t in match["teams"]}
    team_id: str | None = None
    # Team by name, short name, or home/away.
    for t in match["teams"]:
        for key in (t["name"].lower(), t["short_name"].lower(), t["name"].lower().split()[0]):
            if re.search(r"\b" + re.escape(key) + r"\b", text):
                team_id = t["team_id"]
                text = re.sub(r"\b" + re.escape(key) + r"\b", " ", text)
                break
    if team_id is None:
        if re.search(r"\bhome\b", text):
            team_id, text = match["home_team_id"], re.sub(r"\bhome\b", " ", text)
        elif re.search(r"\baway\b", text):
            team_id, text = match["away_team_id"], re.sub(r"\baway\b", " ", text)
    # Kit number: "number 9", "#9", "no 9", "no. 9", "the 9", or a bare number once a team is named ("the home 9",
    # "Southgate's 10"). Without a team both 9s are candidates.
    m = re.search(r"\b(?:number|no\.?|#|nr)\s?(\d{1,2})\b|#(\d{1,2})\b|\bthe (\d{1,2})\b", text)
    if m is None and team_id is not None:
        m = re.search(r"(?<![\d.])\b(\d{1,2})\b(?!\s*(?:min|minute|minutes|'|th|st|nd|rd))", text)
    if m:
        num = int(next(g for g in m.groups() if g))
        cands = [p for p in roster if p["kit_number"] == num and (team_id is None or p["team_id"] == team_id)]
        if cands:
            how = f"kit number {num}" + ("" if team_id or len(cands) == 1 else " (both teams)")
            return cands, (text[: m.start()] + " " + text[m.end():]).strip(), how, team_id
    # Position word + team ("the home striker"): prefer the conventional number for that role.
    for w, (pos, prefer) in sorted(POSITION_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(w) + r"\b", text):
            cands = [p for p in roster if p["position"] == pos and p["starter"] and (team_id is None or p["team_id"] == team_id)]
            if cands:
                def rank(p, prefer=prefer):
                    return p["team_id"] != match["home_team_id"], prefer.index(p["kit_number"]) if p["kit_number"] in prefer else 99, p["kit_number"]

                pick = sorted(cands, key=rank)[0]
                return [pick], re.sub(r"\b" + re.escape(w) + r"\b", " ", text).strip(), f"{w} of {teams[pick['team_id']]['name']}", team_id
    # Name tokens: exact surname/first name, then fuzzy.
    tokens = [tok.strip("'-") for tok in text.split() if tok not in STOPWORDS and not tok.isdigit()]
    names: dict[str, list[Record]] = {}
    for p in roster:
        for part in p["name"].lower().split():
            names.setdefault(part, []).append(p)
    for tok in tokens:
        if tok in names:
            cands = [p for p in names[tok] if team_id is None or p["team_id"] == team_id]
            if cands:
                return cands[:1], re.sub(r"\b" + re.escape(tok) + r"\b", " ", text).strip(), f"name '{tok}'", team_id
    for tok in tokens:
        if len(tok) < 4:
            continue
        close = difflib.get_close_matches(tok, list(names), n=1, cutoff=0.72)
        if close:
            cands = [p for p in names[close[0]] if team_id is None or p["team_id"] == team_id]
            if cands:
                return cands[:1], re.sub(r"\b" + re.escape(tok) + r"\b", " ", text).strip(), f"'{tok}' taken as '{close[0]}'", team_id
    return [], text, (f"team {teams[team_id]['name']}" if team_id else None), team_id


def parse_query(query: str, match: Record) -> dict[str, Any]:
    text = _normalise(query)
    tags, text = _find_tags(text)
    window, text = _find_minutes(text, match)
    limit, text = _find_limit(text)
    players, text, how, team_id = _find_player(text, match)
    reasons = [t for t in tags if t.endswith("_appearance")]
    event_tags = [t for t in tags if not t.endswith("_appearance")]
    return {
        "player_ids": [p["player_id"] for p in players],
        "player_id": players[0]["player_id"] if len(players) == 1 else None,
        "player": " / ".join(p["name"] for p in players) if players else None,
        "player_how": how,
        "team_id": team_id,
        "tags": event_tags,
        "reasons": reasons,
        "minutes": list(window) if window else None,
        "limit": limit,
        "unparsed": [tok for tok in text.split() if tok not in STOPWORDS],
    }


# ---------------------------------------------------------------------------- search

def search_clips(match_dir: str | Path, query: str, limit: int = 10) -> dict[str, Any]:
    """Search one match's clips with a natural-language query.

    Returns ``{"parsed": {...}, "results": [...], "relaxed": bool, "message": str}``. Each result has
    clip_id, title, t, t_end, minute, reason, tags, watchability, explanation, summary, player.
    """
    match_dir = str(match_dir)
    match, stream, _, _ = _load(match_dir)
    parsed = parse_query(query, match)
    if parsed["player_ids"]:
        player_ids = parsed["player_ids"]
    elif parsed["team_id"]:
        player_ids = [p["player_id"] for p in match["players"] if p["starter"] and p["team_id"] == parsed["team_id"]]
    else:
        # No player and no team: search the players who have clips on disk, else every starter.
        _, _, clips, _ = _load(match_dir)
        player_ids = sorted({c["player_id"] for c in clips}) or [p["player_id"] for p in match["players"] if p["starter"]]

    rows: list[Record] = []
    for pid in player_ids:
        clips, labels = _clips_for(match_dir, pid)
        name = next(p["name"] for p in match["players"] if p["player_id"] == pid)
        for c in clips:
            lb = labels.get(c["id"])
            if lb is None:
                continue
            rows.append({
                "clip_id": c["id"], "player_id": pid, "player": name, "title": lb["title"], "t": c["t"], "t_end": c["t_end"],
                "minute": match_minute(match, c["keyframe_t"]), "reason": c["reason"], "tags": lb["tags"],
                "watchability": lb["watchability"], "explanation": lb.get("explanation", ""), "summary": lb.get("summary", ""),
                "event_ids": c["event_ids"], "segment_ids": c["segment_ids"],
            })

    def in_window(r: Record) -> bool:
        return parsed["minutes"] is None or parsed["minutes"][0] <= r["minute"] <= parsed["minutes"][1]

    def reason_ok(r: Record) -> bool:
        return not parsed["reasons"] or r["reason"] in parsed["reasons"]

    want = set(parsed["tags"])
    pool = [r for r in rows if in_window(r) and reason_ok(r)]
    strict = [r for r in pool if want <= set(r["tags"])] if want else pool
    relaxed = False
    results = strict
    if want and not strict:
        results = [r for r in pool if want & set(r["tags"])]
        relaxed = bool(results)
    results.sort(key=lambda r: (-(len(want & set(r["tags"])) if want else 0), -r["watchability"], r["t"]))
    n = parsed["limit"] or limit
    results = results[:n]

    if results:
        message = f"{len(results)} clip(s)" + (" (relaxed: no clip has every requested tag, showing partial matches)" if relaxed else "")
    elif not parsed["player_ids"] and parsed["unparsed"]:
        message = f"No player recognised in {parsed['unparsed']!r} and no clips matched."
    else:
        message = "No clips match. " + (f"{parsed['player']} has clips tagged: " + ", ".join(sorted({t for r in rows for t in r['tags']})) if rows else "That player has no clips in this match.")
    return {"parsed": parsed, "results": results, "relaxed": relaxed, "message": message}


# ---------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search a match's clips in plain English.")
    parser.add_argument("match_dir", type=Path)
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--json", action="store_true", help="print the raw result as JSON")
    args = parser.parse_args(argv)
    out = search_clips(args.match_dir, args.query, args.limit)
    if args.json:
        print(json.dumps(out, indent=2))
        return 0 if out["results"] else 1
    p = out["parsed"]
    print(f"understood: player={p['player'] or '-'} ({p['player_how'] or 'none'})  tags={p['tags'] or '-'}  reasons={p['reasons'] or '-'}  "
          f"minutes={p['minutes'] or 'any'}  limit={p['limit'] or args.limit}" + (f"  unparsed={p['unparsed']}" if p["unparsed"] else ""))
    print(out["message"])
    for r in out["results"]:
        print(f"  {r['clip_id']}  {r['watchability']:.2f}  {r['minute']:>3}'  {r['t']:7.2f}-{r['t_end']:7.2f}s  {r['title']}")
        print(f"             {r['explanation']}")
    return 0 if out["results"] else 1


if __name__ == "__main__":
    sys.exit(main())
