"""The image smoke test's file checks: the dashboards' static files and the four sample matches must be packaged."""

from __future__ import annotations

import shutil
from pathlib import Path

from regista.cloud.smoke import SAMPLE_MATCHES, STATIC_FILES, file_checks

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "sample"


def test_the_checkout_passes_the_file_checks():
    results = file_checks(data_root=SAMPLE)
    assert [r["check"] for r in results] == ["static-files", "sample-matches"]
    assert all(r["ok"] and not r["missing"] for r in results), results


def test_a_missing_page_or_match_fails_by_name(tmp_path):
    static, data = tmp_path / "static", tmp_path / "data"
    for f in STATIC_FILES[1:]:
        (static / f).parent.mkdir(parents=True, exist_ok=True)
        (static / f).write_text("x")
    for m in SAMPLE_MATCHES[:-1]:
        shutil.copytree(SAMPLE / m, data / m, ignore=shutil.ignore_patterns("tracks.jsonl", "review"))
    files, matches = file_checks(static, data)
    assert not files["ok"] and files["missing"] == [STATIC_FILES[0]]
    assert not matches["ok"] and all(p.startswith(f"{SAMPLE_MATCHES[-1]}/") for p in matches["missing"])


def test_the_season_check_passes_on_the_committed_season_and_names_a_match_that_differs(tmp_path):

    from regista.cloud.smoke import season_checks
    from regista.season.build import build_all
    from regista.season.league import load_league

    root = Path(__file__).resolve().parents[1] / "data" / "season"
    build_all(load_league(root / "league.json"), root / "matches")
    [ok] = season_checks(root / "league.json", root / "matches")
    assert ok["ok"] and ok["differs"] == {}
    shutil.copytree(root / "matches" / "rl_r01_ash_fai", tmp_path / "rl_r01_ash_fai")
    with open(tmp_path / "rl_r01_ash_fai" / "events.jsonl", "a") as f:
        f.write("\n")
    [bad] = season_checks(root / "league.json", tmp_path)
    assert not bad["ok"] and bad["differs"]["rl_r01_ash_fai"] != "missing" and bad["differs"]["rl_r01_eas_bro"] == "missing"
