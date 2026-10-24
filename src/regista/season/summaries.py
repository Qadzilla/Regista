"""The Profile agent's summaries: two or three plain sentences per player, every claim citing where it came from.

A summary is ``{text, sentences: [{text, sources: [id]}], sources: [...], model, basis}``. Sources are structured:
``S…`` a stat (key, label, per 90, count, minutes, rank among the position), ``M…`` a moment (match, round, opponent,
clip, video), ``P1`` the player's season (appearances, minutes). Each sentence lists the ids it rests on, so the
profile page can link every claim to the numbers and clips behind it.

- **rules** (``rules_summary``): what kind of player (the archetype of the position whose stats rank best), what else
  stands out (the next best ranks), and the best moment.
- **Foundry** (``foundry_summaries``): a Foundry model writes the sentences from the same numbered facts and must cite
  them; an answer that cites nothing, names a fact that does not exist, or uses a number no cited fact holds is refused
  (one retry with the reason), and that player keeps the rules summary, which says so in ``model``.

``python -m regista.season summarise [--cloud]`` writes ``data/season/summaries.json`` (committed). ``basis`` is a
fingerprint of the numbers a summary was written from: ``summary_for`` serves the stored summary only while the
profile still has those numbers (a match added since makes it stale) and otherwise writes the rules one on the spot.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from regista.season.profiles import Season
from regista.season.scout import POSITIONS, RATIO_MIN, held_numbers, rank_in_position, stat_of, unheld

Record = dict[str, Any]
Runner = Callable[[str, str], Awaitable[str]]  # (instructions, prompt) -> model text

RULES_MODEL = "rules-v0"
# Stats a summary may talk about (the rest are parts of these, or too routine to say).
CANDIDATES = ["goals", "assists", "shots", "shots_on_target", "key_passes", "forward_passes", "crosses", "take_ons_won", "nutmegs",
              "carries", "tackles_won", "interceptions", "recoveries", "clearances", "pressures", "saves", "fouls_won",
              "pass_accuracy", "take_on_success"]
# Per position: (archetype, the stats that make it). The archetype whose stats rank best describes the player.
ARCHETYPES: dict[str, list[tuple[str, list[str]]]] = {
    "FW": [("goalscoring forward", ["goals", "shots_on_target"]), ("dribbling forward", ["take_ons_won", "nutmegs"]),
           ("creative forward", ["key_passes", "assists"]), ("pressing forward", ["pressures", "recoveries", "tackles_won"])],
    "MF": [("creative midfielder", ["key_passes", "assists"]), ("ball-winning midfielder", ["recoveries", "tackles_won", "interceptions"]),
           ("progressive passer in midfield", ["forward_passes", "pass_accuracy"]), ("ball-carrying midfielder", ["take_ons_won", "carries"]),
           ("goal threat from midfield", ["shots", "goals"])],
    "DF": [("ball-playing defender", ["forward_passes", "pass_accuracy"]), ("stopper", ["clearances", "interceptions", "tackles_won"]),
           ("attacking defender", ["crosses", "key_passes"]), ("ball-winning defender", ["recoveries", "tackles_won"])],
    "GK": [("shot-stopper", ["saves"]), ("goalkeeper who builds play", ["forward_passes", "pass_accuracy"])],
}
MIN_COUNT = 3  # a stat counted fewer times than this is not a claim worth making
GENDERED = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)


def basis(season: Season, p: Record, fs: list[Record] | None = None) -> str:
    """Fingerprint of what a summary is written from: its facts (minutes, every candidate stat with its rank among the
    position, the best moments). The ranks are in it because they move when *other* players' numbers move: a player
    whose own counts are unchanged can still have dropped from 3rd to 5th, and a summary saying "3rd" is then stale."""
    data = {"facts": fs if fs is not None else facts(season, p), "counts": p["counts"]}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------- facts

def facts(season: Season, p: Record) -> list[Record]:
    """The numbered facts a summary may cite: P1 the season, S… every candidate stat with its rank, M… best moments."""
    group = POSITIONS[p["position"]][1]
    out: list[Record] = [{"id": "P1", "type": "season", "name": p["name"], "club": p["club"], "position": p["position"],
                          "kit_number": p["kit_number"], "appearances": p["appearances"], "minutes": p["minutes"]}]
    for i, key in enumerate(CANDIDATES, start=1):
        s = stat_of(p, key, rank_in_position(season, p, key))
        if s["kind"] == "ratio" and (s["value"] is None or s["of"] < _ratio_min(key)):
            continue
        out.append({"id": f"S{i}", "type": "stat", "group": group, **s})
    opponents = {m["match_id"]: m["opponent"] for m in p["matches"]}
    for i, m in enumerate(p["moments"][:3], start=1):
        out.append({"id": f"M{i}", "type": "moment", "match_id": m["match_id"], "round": m["round"], "opponent": opponents.get(m["match_id"]),
                    "player_id": m["player_id"], "clip_id": m["clip_id"], "title": m["title"], "tags": m["tags"],
                    "video_url": m["video_url"]})
    return out


def _ratio_min(key: str) -> int:
    return RATIO_MIN.get(key, 0)


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _stat_phrase(s: Record) -> str:
    if s["kind"] == "ratio":
        return f"{s['label'].lower()} of {s['display']} ({s['count']} of {s['of']})"
    return f"{s['value']:g} {s['label'].lower()} per 90"


def _place(s: Record) -> str:
    return f"{'joint ' if s['tied_with'] else ''}{_ordinal(s['rank'])}"


def _rank_phrase(s: Record) -> str:
    if s["rank"] == 1 and not s["tied_with"]:
        return f"the best of the league's {s['of_players']} {s['group']}"
    return f"{_place(s)} of the league's {s['of_players']} {s['group']}"


def _a(word: str) -> str:
    return f"{'an' if word[0].lower() in 'aeiou' else 'a'} {word}"


def _summary(sentences: list[tuple[str, list[str]]], fs: list[Record], model: str, b: str) -> Record:
    used = {i for _t, ids in sentences for i in ids}
    return {"text": " ".join(t for t, _ids in sentences), "sentences": [{"text": t, "sources": ids} for t, ids in sentences],
            "sources": [f for f in fs if f["id"] in used], "model": model, "basis": b}


# ---------------------------------------------------------------------------- rules

def rules_summary(season: Season, p: Record, model: str = RULES_MODEL) -> Record:
    """Three sentences from the numbers: the kind of player, what else stands out, the best moment."""
    fs = facts(season, p)
    stats = {f["key"]: f for f in fs if f["type"] == "stat"}
    season_fact = fs[0]
    surname = p["name"].split()[-1]

    def share(st: Record) -> float:  # rank as a share of the group: 0 the best, 1 the last
        return (st["rank"] - 1) / max(1, st["of_players"] - 1)

    def strength(keys: list[str]) -> tuple[float, float]:  # best and mean share over the stats worth a claim
        have = [share(stats[k]) for k in keys if k in stats and stats[k]["count"] >= MIN_COUNT]
        return (min(have), sum(have) / len(have)) if have else (2.0, 2.0)

    kind, keys = min(ARCHETYPES[p["position"]], key=lambda a: strength(a[1]))
    lead = min((stats[k] for k in keys if k in stats and stats[k]["count"] >= MIN_COUNT), key=lambda s: s["rank"], default=None)
    if lead is not None and share(lead) > 0.5:  # nothing in the archetype ranks in the top half: no label
        lead = None
    sentences: list[tuple[str, list[str]]] = []
    if lead is not None:
        sentences.append((f"{p['name']} is {_a(kind)} for {p['club']}: {_stat_phrase(lead)}, {_rank_phrase(lead)}.", [lead["id"]]))
    else:
        sentences.append((f"{p['name']} plays as {_a(_group_word(p))} for {p['club']}, with {p['appearances']} appearances and "
                          f"{p['minutes']:g} minutes.", ["P1"]))
    others = sorted((s for s in stats.values() if s["count"] >= MIN_COUNT and (lead is None or s["key"] != lead["key"]) and
                     s["key"] not in _overlaps(lead["key"] if lead else "")), key=lambda s: (s["rank"] / s["of_players"], CANDIDATES.index(s["key"])))
    good = [s for s in others if s["rank"] <= max(3, s["of_players"] // 4)][:2]
    if good:
        parts = [f"{_place(s)} for {s['label'].lower()} ({_stat_value(s)})" for s in good]
        sentences.append((f"{surname} also ranks {' and '.join(parts)} among the {good[0]['group']}.", [s["id"] for s in good]))
    else:
        g, a = stats.get("goals"), stats.get("assists")
        bits = [] if lead is None else [f"{season_fact['appearances']} appearances and {season_fact['minutes']:g} minutes"]
        ids = [] if lead is None else ["P1"]
        if g and g["count"]:
            bits.append(f"{g['count']} goal{'s' if g['count'] != 1 else ''}")
            ids.append(g["id"])
        if a and a["count"]:
            bits.append(f"{a['count']} assist{'s' if a['count'] != 1 else ''}")
            ids.append(a["id"])
        if bits:
            sentences.append((f"Across the season: {' and '.join(bits)}.", ids))
    best = next((f for f in fs if f["id"] == "M1"), None)
    if best:
        against = f" against {best['opponent']}" if best.get("opponent") else ""
        sentences.append((f"Best moment: {_moment_words(best['title'])} in round {best['round']}{against}.", [best["id"]]))
    if len(sentences) < 2:  # a substitute with a few minutes and nothing to rank: say so rather than overclaim
        sentences.append((f"{surname} has played too little so far for rates to mean much.", ["P1"]))
    return _summary(sentences, fs, model, basis(season, p, fs))


def _group_word(p: Record) -> str:
    return POSITIONS[p["position"]][0]


def _overlaps(key: str) -> set[str]:
    """Stats that would only repeat the lead (shots on target after goals, take-on success after take-ons won)."""
    pairs = [{"goals", "shots_on_target", "shots"}, {"take_ons_won", "take_on_success"}, {"key_passes", "assists"}]
    return set().union(*(s for s in pairs if key in s)) - {key} if key else set()


def _stat_value(s: Record) -> str:
    return s["display"] if s["kind"] == "ratio" else f"{s['value']:g} per 90"


def _moment_words(title: str) -> str:
    """The moment part of a clip title, quoted: "Amari Ustinov (9): assist at 13'" gives “assist at 13'”."""
    what = title.split(": ", 1)[-1]
    return f"“{what}”"


# ---------------------------------------------------------------------------- Foundry

SUMMARY_INSTRUCTIONS = """You are Regista's Profile agent, writing for football scouts. You get one player of the
synthetic Regista League and a list of numbered facts about their season (P1 the season, S… stats with their rank among
the league's players in the same position, M… their best moments). Return JSON only:
  {"sentences": [{"text": "...", "sources": ["S3", "M1"]}, ...]}
Write two or three plain sentences, each under 35 words: first what kind of player this is and for which club, with the
stat that shows it; then what else stands out; then the best moment (its round and opponent). Every sentence lists in
"sources" the ids of the facts it uses, and uses only numbers those facts hold (per 90 values, counts, ranks,
percentages, minutes, rounds). Say "per 90" for per-90 values. Write ranks as ordinals among the position ("2nd of 18
midfielders"), and "joint" when the fact's tied_with is above 0. Prefer stats with a count of 3 or more. Use the
player's full name once, then the surname; never he, she, his, her or any other gendered pronoun. No jargon such as xG,
no hype, nothing a fact does not say. Never mention facts, ids or that you are a model in the text."""


def summary_prompt(p: Record, fs: list[Record]) -> str:
    return json.dumps({"player": {"name": p["name"], "club": p["club"], "position": p["position"], "kit_number": p["kit_number"]},
                       "facts": fs}, ensure_ascii=False) + "\n\nRespond with JSON only."


def check_sentences(obj: Any, fs: list[Record]) -> list[tuple[str, list[str]]]:
    """The model's sentences if they hold up, else ValueError saying why: 2-3 sentences, each citing known facts,
    every number held by a cited fact, no gendered pronouns."""
    by_id = {f["id"]: f for f in fs}
    sents = obj.get("sentences") if isinstance(obj, dict) else None
    if not isinstance(sents, list) or not 2 <= len(sents) <= 3:
        raise ValueError("write two or three sentences")
    out = []
    for s in sents:
        text = str(s.get("text", "")).strip() if isinstance(s, dict) else ""
        ids = [str(i) for i in (s.get("sources") or [])] if isinstance(s, dict) else []
        if not text or len(text) > 320:
            raise ValueError("each sentence needs text, at most 320 characters")
        unknown = [i for i in ids if i not in by_id]
        if not ids or unknown:
            raise ValueError(f"every sentence must cite facts that exist (unknown: {unknown})" if unknown else
                             f"cite the facts behind: {text[:60]}")
        if GENDERED.search(text):
            raise ValueError("no gendered pronouns; use the surname")
        wrong = unheld(text, held_numbers([by_id[i] for i in ids] + [by_id["P1"]]))
        if wrong:
            raise ValueError(f"the number {wrong[0]} is not in the facts that sentence cites")
        out.append((text, ids))
    return out


RATE_LIMIT_WAITS = 5
RATE_LIMIT_WAIT_S = 15.0


def _rate_limited(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return "429" in text or "rate_limit" in text.lower() or "RateLimit" in text


async def foundry_summary(season: Season, p: Record, runner: Runner, model: str) -> tuple[Record, str | None]:
    """One player's Foundry summary, checked; on a second bad answer, the rules summary. Returns (summary, note)."""
    from regista.cloud.foundry import _extract_json

    fs = facts(season, p)
    prompt = summary_prompt(p, fs)
    why = None
    attempts, waits = 0, 0
    while attempts < 2:
        try:
            text = await runner(SUMMARY_INSTRUCTIONS, prompt if why is None else f"{prompt}\n\nYour last answer was refused: {why}. "
                                f"Answer again, JSON only.")
            return _summary(check_sentences(_extract_json(text), fs), fs, model, basis(season, p, fs)), None
        except Exception as exc:  # noqa: BLE001 - a bad answer gets one retry, then the rules summary
            if _rate_limited(exc) and waits < RATE_LIMIT_WAITS:  # the deployment's quota, not the answer: wait, ask again
                waits += 1
                await asyncio.sleep(RATE_LIMIT_WAIT_S * waits)
                continue
            attempts += 1
            why = f"{type(exc).__name__}: {str(exc)[:160]}"
    return rules_summary(season, p, model=f"{RULES_MODEL} (foundry fallback)"), why


async def foundry_summaries(season: Season, players: list[Record], runner: Runner, model: str, concurrency: int = 4,
                            progress: Callable[[str], None] | None = None) -> tuple[dict[str, Record], dict[str, str]]:
    sem = asyncio.Semaphore(concurrency)
    notes: dict[str, str] = {}

    async def one(p: Record) -> tuple[str, Record]:
        async with sem:
            s, note = await foundry_summary(season, p, runner, model)
            if note:
                notes[p["global_id"]] = note
            if progress:
                progress(f"{p['global_id']} {s['model']}")
            return p["global_id"], s

    pairs = await asyncio.gather(*(one(p) for p in players))
    return dict(pairs), notes


# ---------------------------------------------------------------------------- the file

def players_with_minutes(season: Season) -> list[Record]:
    return sorted((p for p in season.profiles.values() if p["appearances"] and p["minutes"] > 0), key=lambda p: p["global_id"])


def summarise(season: Season, *, runner: Runner | None = None, model: str | None = None, concurrency: int = 4,
              progress: Callable[[str], None] | None = None, keep: dict[str, Record] | None = None) -> Record:
    """Every player's summary: from ``runner`` (a Foundry model) when given, else the rules. ``keep`` holds summaries
    to reuse as they are (those of ``model`` still current), so a second run only redoes the rest."""
    from regista.aio import run_sync

    players = players_with_minutes(season)
    kept = {p["global_id"]: keep[p["global_id"]] for p in players
            if keep and p["global_id"] in keep and keep[p["global_id"]].get("model") == (model or RULES_MODEL)
            and keep[p["global_id"]].get("basis") == basis(season, p)}
    todo = [p for p in players if p["global_id"] not in kept]
    notes: dict[str, str] = {}
    if runner is None:
        out = {p["global_id"]: rules_summary(season, p) for p in todo}
    else:
        out, notes = run_sync(foundry_summaries(season, todo, runner, model or "foundry", concurrency, progress))
    out = dict(sorted({**kept, **out}.items()))
    return {"league": season.league["league"], "season": season.league["season"],
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": model or RULES_MODEL,
            "note": "Written by Regista's Profile agent from the league's profiles; every sentence cites its sources.",
            "fallbacks": notes, "players": out}


def write_summaries(doc: Record, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


_cache: dict[str, tuple[int, Record]] = {}
_lock = threading.Lock()


def load_summaries(path: Path | str) -> Record:
    """The summaries file (re-read when it changes); empty when there is none."""
    path = Path(path)
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return {"players": {}}
    with _lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == mtime:
            return hit[1]
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            doc = {"players": {}}
        _cache[str(path)] = (mtime, doc)
        return doc


def summaries_path() -> Path:
    """Beside the league file (REGISTA_SEASON), or REGISTA_SEASON_SUMMARIES."""
    import os

    override = os.environ.get("REGISTA_SEASON_SUMMARIES")
    return Path(override) if override else Path(os.environ.get("REGISTA_SEASON", "data/season/league.json")).with_name("summaries.json")


def summary_for(season: Season, p: Record, path: Path | str | None = None) -> Record | None:
    """The player's summary: the stored one while its numbers are current, else the rules summary written now
    (``model`` says "rules-v0 (live)"). None for players without minutes."""
    if not p["appearances"] or not p["minutes"]:
        return None
    stored = load_summaries(path or summaries_path()).get("players", {}).get(p["global_id"])
    if stored and stored.get("basis") == basis(season, p):
        return stored
    return rules_summary(season, p, model=f"{RULES_MODEL} (live)")
