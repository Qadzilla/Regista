"""Levels that play like their level (docs/catalogue/build/levels.md): technical execution by level, inert for England.

Ratings scaled by level cancel in head-to-head outcomes (a weaker passer meets a weaker marker), so a level's execution
against absolute football is a separate, optional team-spec key (``execution``) that only catalogue competitions carry.
"""

from __future__ import annotations

from pathlib import Path

from regista.catalogue import store
from regista.catalogue.taxonomy import LEVELS
from regista.season.league import generate_kwargs, load_league
from regista.synth.generator import generate

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
LEAGUE = ROOT / "data" / "season" / "league.json"


def _comp(cid: str) -> dict:
    return next(c for c in store.new_competitions(INDEX) if c["competition"]["competition_id"] == cid)


def test_england_kwargs_never_carry_execution():
    league = load_league(LEAGUE)
    for fx in league["fixtures"]:
        for team in generate_kwargs(league, fx)["teams"]:
            assert "execution" not in team and "style_offset" not in team


def test_catalogue_kwargs_carry_their_levels_execution():
    for comp in store.new_competitions(INDEX):
        want = LEVELS[comp["level"]["key"]].execution
        assert comp["level"]["execution"] == want
        for team in generate_kwargs(comp, comp["fixtures"][0])["teams"]:
            assert team.get("execution", 0.0) == want, comp["competition"]["competition_id"]


def test_execution_orders_the_levels():
    ex = {k: lv.execution for k, lv in LEVELS.items()}
    assert ex["semi_pro/senior/men"] == 0.0
    youth = ["academy/U17/men", "academy/U18/men", "academy/U19/men", "academy/U20/men", "semi_pro/senior/men"]
    assert all(ex[a] > ex[b] for a, b in zip(youth, youth[1:]))
    assert ex["amateur/senior/men"] > ex["college/college/men"] > ex["semi_pro/senior/men"]
    assert ex["semi_pro/senior/women"] > ex["semi_pro/senior/men"]
    assert ex["college/college/women"] > ex["college/college/men"]


def _passes(stream: list[dict]) -> tuple[int, int, int]:
    passes = [r for r in stream if r.get("type") == "event" and r.get("event_type") in ("pass", "cross")]
    heavy = sum(1 for r in stream if r.get("type") == "event" and "heavy_touch" in (r.get("qualifiers") or []))
    return len(passes), sum(1 for r in passes if r.get("outcome") == "success"), heavy


def test_execution_lowers_pass_completion_and_adds_heavy_touches():
    comp = _comp("co_gha_u17")
    with_, without = [0, 0, 0], [0, 0, 0]
    for fx in comp["fixtures"][:2]:
        kw = generate_kwargs(comp, fx)
        for i, v in enumerate(_passes(generate(**kw).stream)):
            with_[i] += v
        for team in kw["teams"]:
            team.pop("execution")
        for i, v in enumerate(_passes(generate(**kw).stream)):
            without[i] += v
    assert with_[2] > 0 and without[2] == 0
    assert with_[1] / with_[0] < without[1] / without[0] - 0.04
