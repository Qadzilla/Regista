"""The catalogue realism report (design.md §10 and §11, item 14): ``python -m regista.synth.report --catalogue``.

It reads the committed measurement (data/catalogue/realism.json) and re-runs the checks on its stored aggregates, so the
quick tests never regenerate a season (a guard makes any generation fail). docs/catalogue/realism.md must be exactly what
the report writes. The slow test regenerates one level and checks it equals the committed measurement. Nothing here
writes to data/ or reaches Azure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from regista.catalogue import realism as rea
from regista.catalogue.taxonomy import LEVELS
from regista.season.league import ATTRIBUTE_KEYS
from regista.synth import report

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "catalogue" / "catalogue.json"
COMMITTED = INDEX.with_name(rea.FILE_NAME)
DOC = ROOT / "docs" / "catalogue" / "realism.md"
HIDDEN = set(ATTRIBUTE_KEYS) | {"attributes", "skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift",
                                "execution", "style_offset", "level_scale"}


@pytest.fixture
def no_generation(monkeypatch):
    """Any regeneration fails the test: the default report reads the committed measurement only."""
    import regista.catalogue.measure as measure
    import regista.synth.generator as generator

    def refuse(*_a, **_k):
        raise AssertionError("the default catalogue report must not regenerate a season")

    monkeypatch.setattr(measure, "measure", refuse)
    monkeypatch.setattr(measure, "measure_season", refuse)
    monkeypatch.setattr(generator, "generate", refuse)


@pytest.fixture
def committed_report(no_generation):
    return report.report_catalogue(INDEX)


def test_the_default_report_reads_the_committed_measurement(committed_report):
    data, md, ok = committed_report
    assert ok and data["stale"] is None and data["drift"] == []
    assert "the committed file `data/catalogue/realism.json`" in md
    assert "6 regenerated seasons of every competition's full double round robin (1,524 matches)" in md


def test_the_verdicts_at_a_glance():
    data = json.loads(COMMITTED.read_text())
    s = report.catalogue_summary(data)
    # closing review B round 1: the amateur sprint order is assumed (S-1); the passes split into calibrated and scaled (S-2)
    assert s["sourced"] == {"total": 10, "pass": 10, "fail": 0, "not separated": 0, "not measured": 0, "bands": 1,
                            "calibrated": 3, "scaled": 7, "extended": 8}
    assert s["assumed"] == {"total": 7, "pass": 6, "fail": 1, "not separated": 0, "not measured": 0}
    [failing] = [o["id"] for o in data["orders"] if o["verdict"] != "pass"]
    assert failing == "youth_distance_extension"


def test_every_level_and_check_is_reported_with_its_kind_and_verdict(committed_report):
    data, md, _ok = committed_report
    for key in LEVELS:
        assert f"| {report.CATALOGUE_LEVEL_LABELS[key]} |" in md
    for b in rea.BANDS:
        assert b["label"] in md
    assert "| **pass** | S5 |" in md     # the U17 band
    for o in rea.ORDERS:
        row = next(line for line in md.splitlines() if line.startswith(f"| {o['label']} ("))
        verdict = next(c for c in data["orders"] if c["id"] == o["id"])["verdict"]
        assert f"**{verdict}**" in row
    sourced = md.split("## Orders between levels (sourced)")[1].split("## Assumed orders")[0]
    assumed = md.split("## Assumed orders (no published band)")[1].split("## References")[0]
    for o in rea.ORDERS:
        assert (o["label"] in assumed) == rea.assumed(o) and (o["label"] in sourced) == (not rea.assumed(o))
    assert "youth_distance_extension (assumed order): Academy U18 to Academy U19 -76.70" in md
    # "no published band": event rates at every level but the two the Premier League bands stand beside as a reference
    kinds = {line.split(" | ")[0][2:]: line.split(" | ")[2] for line in md.splitlines()
             if line.startswith("| ") and line.split(" | ")[0][2:] in report.CATALOGUE_LEVEL_LABELS.values()
             and len(line.split(" | ")) == 6}
    assert kinds["Semi-pro men"] == kinds["College men"] == "reference"
    assert all(v == "none" for k, v in kinds.items() if k not in ("Semi-pro men", "College men"))
    for sid in rea.SOURCES:
        assert f"- [{sid}] " in md
    assert "no verdict" in md and "never counted" in md


def test_references_carry_no_verdict(committed_report):
    _data, md, _ok = committed_report
    refs = md.split("## References (no verdict)")[1].split("## Speed zones")[0]
    assert "**pass**" not in refs and "**fail**" not in refs and "in band" not in refs
    assert "not comparable (a team's total per match)" in refs     # S11 is per team, never set against a per-90 number


def test_the_committed_verdicts_are_what_the_checks_compute():
    committed = json.loads(COMMITTED.read_text())
    assert report.catalogue_drift(committed, rea.recheck(committed)) == []


def test_docs_realism_md_is_what_the_report_writes(committed_report):
    _data, md, _ok = committed_report
    assert DOC.read_text(encoding="utf-8") == md, \
        "regenerate it: python -m regista.synth.report --catalogue --out docs/catalogue/realism.md"


def test_the_report_never_shows_a_hidden_rating_or_scale(committed_report, capsys):
    data, md, _ok = committed_report
    assert report.main(["--catalogue", "--json"]) == 0
    out = capsys.readouterr().out
    keys: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            keys.update(v)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(json.loads(out))
    assert not keys & HIDDEN
    # the scale keys never appear in the Markdown either (rating keys are ordinary words: "passing", "vision")
    for k in ("skill_offset", "stamina_offset", "speed_mult", "accel_mult", "height_shift", "style_offset", "level_scale"):
        assert k not in md


def test_matches_measured():
    assert report.catalogue_matches_measured(6) == 1524
    assert report.catalogue_matches_measured(6, ["academy/U17/men"]) == 72


def test_a_missing_measurement_is_said_and_fails(no_generation, monkeypatch):
    monkeypatch.setattr(rea, "FILE_NAME", "realism-missing.json")
    data, md, ok = report.report_catalogue(INDEX)
    assert not ok and "no realism-missing.json" in md and "python -m regista.catalogue reliability" in md


def test_a_stale_measurement_is_said_and_fails(no_generation, monkeypatch):
    import regista.synth.generator as generator

    monkeypatch.setattr(generator, "LEAGUE_GENERATOR_VERSION", "9.9.9")
    data, md, ok = report.report_catalogue(INDEX)
    assert not ok and data["stale"] == "realism.json was measured for generator 0.7.1"
    assert "**Stale:** realism.json was measured for generator 0.7.1" in md


def test_verdicts_out_of_step_with_the_checks_are_said_and_fail(no_generation, monkeypatch):
    monkeypatch.setattr(rea, "SEPARATION_SE", 40.0)    # a stricter check than the committed one
    data, md, ok = report.report_catalogue(INDEX)
    assert not ok and "youth_distance" in data["drift"]
    assert "The committed verdicts differ from the checks' code" in md and "not separated" in md


def test_the_command_line(no_generation, tmp_path, capsys):
    out = tmp_path / "realism.md"
    assert report.main(["--catalogue", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == DOC.read_text(encoding="utf-8")
    assert capsys.readouterr().out.startswith("# Catalogue realism report")
    assert report.main(["--catalogue", str(INDEX), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["sourced"]["pass"] == 10
    for bad in (["--catalogue", "--level", "academy/U17/men"], ["--catalogue", "--repeat", "3"],
                ["--catalogue", "--regenerate", "--level", "academy/U16/men"], ["--catalogue", "--profile", "league"]):
        with pytest.raises(SystemExit) as e:
            report.main(bad)
        assert e.value.code == 2


def test_the_league_report_keeps_one_season_by_default(monkeypatch):
    seen = []
    monkeypatch.setattr(report, "report_league", lambda path, repeat: seen.append(repeat) or ({}, ""))
    monkeypatch.setattr(report, "verdicts", lambda m, n=None: {})
    assert report.main(["--league"]) == 0 and report.main(["--league", "--repeat", "6"]) == 0
    assert seen == [1, 6]


def test_regenerating_nothing_claims_no_agreement(monkeypatch):
    monkeypatch.setattr(report, "regenerate_catalogue",
                        lambda repeats, workers, levels, index: rea.compute(*report._catalogue_league(index), repeats, []))
    data, md, ok = report.report_catalogue(INDEX, regenerate=True, levels=["academy/U17/men"])
    assert not ok and data["comparison"] == {"text": "nothing was measured.", "same": False}


@pytest.mark.slow
def test_regenerating_a_level_reproduces_the_committed_measurement():
    """``--regenerate --level academy/U17/men``: Ghana's six full seasons again (about 15 s on ten cores), equal to the
    committed aggregates season by season, the U17 band passing, and the committed file untouched."""
    before = COMMITTED.read_bytes()
    data, md, ok = report.report_catalogue(INDEX, regenerate=True, levels=["academy/U17/men"])
    assert ok and data["comparison"]["same"]
    assert "equal the committed file's aggregates, season by season" in md
    assert "--regenerate --level academy/U17/men" in md
    assert data["bands"][0]["verdict"] == "pass" and set(data["levels"]) == {"academy/U17/men"}
    assert all(o["verdict"] is None for o in data["orders"])      # every order needs another level: not measured
    assert COMMITTED.read_bytes() == before
