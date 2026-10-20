"""The infra scripts read .env without executing it: values with ';' survive whole, and nothing in a value runs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _load(tmp_path: Path, text: str, preset: dict[str, str] | None = None) -> dict[str, str]:
    env_file = tmp_path / ".env"
    env_file.write_text(text)
    script = f'. "{ROOT}/infra/lib/dotenv.sh"; load_dotenv "{env_file}"; env -0'
    base = {"PATH": "/usr/bin:/bin", **(preset or {})}
    out = subprocess.run(["bash", "-c", script], capture_output=True, check=True, cwd=tmp_path, env=base).stdout.decode()
    return dict(kv.split("=", 1) for kv in out.split("\0") if "=" in kv)


def test_connection_string_with_semicolons_survives_whole(tmp_path):
    conn = "InstrumentationKey=abc;IngestionEndpoint=https://eastus-8.in.applicationinsights.azure.com/;LiveEndpoint=https://x/;ApplicationId=y"
    env = _load(tmp_path, f"# comment\n\nAPPLICATIONINSIGHTS_CONNECTION_STRING={conn}\nFOUNDRY_MODEL = gpt-5-mini \n")
    assert env["APPLICATIONINSIGHTS_CONNECTION_STRING"] == conn
    assert env["FOUNDRY_MODEL"] == "gpt-5-mini"
    assert "IngestionEndpoint" not in env  # the tail was not run as a separate assignment


def test_quotes_are_stripped_and_existing_variables_win(tmp_path):
    env = _load(tmp_path, 'A="quoted value"\nB=\'single\'\nC=from-file\n', preset={"C": "from-env"})
    assert env["A"] == "quoted value" and env["B"] == "single" and env["C"] == "from-env"


def test_nothing_in_a_value_is_executed(tmp_path):
    env = _load(tmp_path, "X=$(touch pwned)\nY=`touch pwned2`;touch pwned3\nnot a line\n1BAD=no\n")
    assert env["X"] == "$(touch pwned)" and env["Y"] == "`touch pwned2`;touch pwned3" and "1BAD" not in env
    assert not any((tmp_path / f).exists() for f in ("pwned", "pwned2", "pwned3"))


def test_deploy_script_uses_the_safe_reader():
    text = (ROOT / "infra/deploy-app.sh").read_text()
    assert "load_dotenv .env" in text and "source .env" not in text
    assert "--revision-suffix" in text  # every deploy starts a revision that reads current secrets
