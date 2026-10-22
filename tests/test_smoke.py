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
