"""Place words for the Scout agent on the catalogue (``POST /api/scout/ask`` with ``where: catalogue``): country, level,
age group, gender and competition words, plus "my level" and "whole catalogue". A Python port of the Scout terminal's
``static/scout/terminal-place.js`` (the sandbox's), so the agent's rules engine reads a question's place the way the
Terminal's search box does. Pure: the vocabulary is built once from the catalogue index and the squads.

    v = vocab(index, comps)
    parse("U19 midfielders in Spain", v)
      -> {"found": True, "where": {"country": "Spain", "age_group": "U19"}, "reset": None, "rest": "midfielders",
          "said": ["in Spain", "U19"], "unknown": [], "young": None}

Everything here is synthetic: invented competitions; countries and levels are labels.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

Record = dict[str, Any]

# Words of competition names too common to name one competition alone.
GENERIC = {"league", "liga", "ligue", "conference", "academy", "amateur", "collegiate", "university", "women", "womens",
           "juniors", "junior", "campeonato", "regional", "interior", "centre", "center", "coast", "valley", "colts", "atlas",
           "riverside", "juvenil", "preferente", "serrano", "state", "soccer", "football", "premier", "division", "national",
           "sub-20", "sub20"}
TIER_WORDS = [(re.compile(r"^(semi-?pro|semipro|semi-?professional|semi professional|semi pro)$"), "semi_pro"),
              (re.compile(r"^(amateur|amateurs|grassroots)$"), "amateur"),
              (re.compile(r"^(college|colleges|collegiate|university|universities|uni|varsity)$"), "college"),
              (re.compile(r"^(academy|academies|youth|juniors?)$"), "academy")]
GENDER_WORDS = [(re.compile(r"^(women|woman|womens|female|females|ladies|lady|girls|girl)$"), "women"),
                (re.compile(r"^(men|mens|male|males|boys)$"), "men")]
RESET_ALL = ["the whole catalogue", "the whole catalog", "whole catalogue", "whole catalog", "the catalogue", "the catalog",
             "across the catalogue", "in the catalogue", "everywhere", "anywhere", "all levels", "every level", "any level",
             "all countries", "every country", "any country", "all competitions", "every competition", "any competition",
             "worldwide"]
RESET_MINE = ["at my level", "at our level", "my level", "our level", "my own level"]
COUNTRY_ALIAS = {"united states": "USA", "united states of america": "USA", "america": "USA", "usa": "USA", "u.s.a": "USA"}
PREP = {"in", "from", "at", "the", "of", "across", "for", "within", "playing", "based"}
AFTER = {"level", "levels", "football", "soccer", "only"}
# The scout's own level (Maya Lindqvist, Fairhaven FC: a synthetic persona; static/shared/demo.js)
MY_LEVEL = {"tier": "semi_pro", "age_group": "senior", "gender": "men"}


def norm(s: Any) -> str:
    t = unicodedata.normalize("NFD", str(s or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"['’]", "", t)
    t = re.sub(r"[?!.,;:]+(\s|$)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def vocab(index: Record, comps: list[Record], mine: Record | None = None) -> Record:
    """The vocabulary, built once: countries, competitions (full names and the words that name one competition alone),
    the levels and age groups that exist, the scout's level. ``comps``: every competition, league-shaped (squads and
    clubs: a competition word that is also a surname or a club word is never used alone)."""
    from regista.catalogue.taxonomy import AGE_GROUPS, TIERS

    entries = index["competitions"]
    countries = {norm(e["country"]): e["country"] for e in entries}
    for k, v in COUNTRY_ALIAS.items():
        if v in countries.values():
            countries[k] = v
    cs = [{"id": e["competition_id"], "name": e["name"], "n": norm(e["name"]), "alt": norm(e["name"]).replace("-", " ")}
          for e in entries]
    taken: set[str] = set()
    names: set[str] = set()
    for comp in comps:
        for club in comp["clubs"]:
            taken.update(w for w in re.split(r"[\s-]+", norm(club["name"])) if w)
            for p in club.get("squad", []):
                taken.update(norm(p["name"]).split(" "))
                names.add(norm(p["name"]))
    count: dict[str, int] = {}
    for c in cs:
        for w in set(c["alt"].split(" ")):
            count[w] = count.get(w, 0) + 1
    words = {}
    for c in cs:
        for w in set(c["alt"].split(" ")):
            if len(w) >= 5 and count[w] == 1 and w not in GENERIC and w not in taken and w not in countries \
                    and not re.search(r"\d", w):
                words[w] = c["id"]
    return {"countries": countries, "comps": cs, "words": words, "ages": {k for k, _v in AGE_GROUPS},
            "tiers": {k for k, _v in TIERS}, "mine": dict(mine or MY_LEVEL), "names": names,
            "comp_name": {c["id"]: c["name"] for c in cs}}


def _cut(toks: list[str], i: int, n: int) -> list[str]:
    a, b = i, i + n
    while b < len(toks) and toks[b] in AFTER:
        b += 1
    while a > 0 and toks[a - 1] in PREP:
        a -= 1
    return toks[:a] + toks[b:]


def parse(text: str, v: Record) -> Record:
    """A question's place (see the module doc): ``where`` holds only the fields the words named, ``reset`` is "all"
    ("whole catalogue") or "mine" ("my level"), ``rest`` what is left for the ordinary question, ``said`` what was read,
    ``unknown`` age groups the catalogue does not have ("U21"), ``young`` "academy" or "dropped"."""
    toks = [t for t in norm(text).split(" ") if t]
    where: Record = {}
    said: list[str] = []
    unknown: list[str] = []
    reset = None

    def phrase(options: list[str]) -> tuple[int, int] | None:
        for p in options:
            pw = p.split(" ")
            for i in range(len(toks) - len(pw) + 1):
                if toks[i:i + len(pw)] == pw:
                    return i, len(pw)
        return None

    hit = phrase(RESET_MINE)
    if hit and v["mine"]:
        reset = "mine"
        where.update(v["mine"])
        said.append("my level")
        toks = _cut(toks, *hit)
    hit = phrase(RESET_ALL)
    if hit:
        reset = reset or "all"
        said.append("the whole catalogue")
        toks = _cut(toks, *hit)
    for c in sorted(v["comps"], key=lambda c: -len(c["alt"])):   # full names, longest first
        for form in dict.fromkeys([c["n"], c["alt"]]):
            fw = form.split(" ")
            for i in range(len(toks) - len(fw) + 1):
                if all(toks[i + j] == w or toks[i + j].replace("-", " ") == w for j, w in enumerate(fw)):
                    where["competition"] = c["id"]
                    said.append(c["name"])
                    toks = _cut(toks, i, len(fw))
                    break
            if "competition" in where:
                break
        if "competition" in where:
            break
    for n in (2, 1):   # countries, two-word aliases first
        if "country" in where:
            break
        for i in range(len(toks) - n + 1):
            k = " ".join(toks[i:i + n])
            if k in v["countries"]:
                where["country"] = v["countries"][k]
                said.append(f"in {where['country']}")
                toks = _cut(toks, i, n)
                break
    if "competition" not in where:   # a competition named by one word only it has
        for i, t in enumerate(toks):
            if t in v["words"]:
                where["competition"] = v["words"][t]
                said.append(v["comp_name"][where["competition"]])
                toks = _cut(toks, i, 1)
                break
    for i in range(len(toks)):   # age groups: U19, u-19, U19s, "under 19", "under-19"; seniors
        m = re.match(r"^u-?(\d{2})s?$", toks[i])
        n = 1
        if not m and toks[i] == "under" and i + 1 < len(toks) and re.match(r"^\d{2}s?$", toks[i + 1]):
            m, n = re.match(r"^(\d{2})", toks[i + 1]), 2
        if not m:
            m = re.match(r"^under-(\d{2})s?$", toks[i])
        if m:
            key = f"U{m.group(1)}"
            if key in v["ages"]:
                where["age_group"] = key
                said.append(key)
            else:
                unknown.append(key)
            toks = _cut(toks, i, n)
            break
        if re.match(r"^(senior|seniors|adult|adults)$", toks[i]):
            where["age_group"] = "senior"
            said.append("senior")
            toks = _cut(toks, i, 1)
            break
    for i in range(len(toks)):   # levels: two-word "semi pro" first, then one word
        two = toks[i] + " " + (toks[i + 1] if i + 1 < len(toks) else "")
        one = toks[i]
        t, n = None, 1
        for rx, k in TIER_WORDS:
            if rx.match(two):
                t, n = k, 2
                break
        if t is None:
            for rx, k in TIER_WORDS:
                if rx.match(one):
                    t = k
                    break
        if t and t in v["tiers"]:
            where["tier"] = t
            said.append(two if n == 2 else one)
            toks = _cut(toks, i, n)
            break
    young = None
    for i, w in enumerate(toks):   # "young": the catalogue's youth levels are its academies
        hit_y = bool(re.match(r"^(youngsters|youngest|younger|teenagers|teens|teenage)$", w)) or (
            w == "young" and i + 1 < len(toks) and not (i > 0 and f"{toks[i - 1]} young" in v["names"]))
        if not hit_y:
            continue
        if "tier" not in where and "age_group" not in where and "academy" in v["tiers"]:
            where["tier"] = "academy"
            said.append('academy (for "young")')
            young = "academy"
        else:
            young = "dropped"
        toks = _cut(toks, i, 1)
        break
    for i, w in enumerate(toks):   # gender
        g = next((k for rx, k in GENDER_WORDS if rx.match(w)), None)
        if g:
            where["gender"] = g
            said.append(g)
            toks = _cut(toks, i, 1)
            break
    if where.get("tier") == "college" and "age_group" not in where:   # college competitions are college / college
        where["age_group"] = "college"
    found = bool(reset or where or unknown or young)
    return {"found": found, "where": where, "reset": reset, "rest": " ".join(toks), "said": said, "unknown": unknown,
            "young": young}
