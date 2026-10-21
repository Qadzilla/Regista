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


# ---------------------------------------------------------------------------- provisioning and deploys (no Azure: what the scripts must and must never do)

def _text(rel):
    return (ROOT / rel).read_text()


def test_provision_checks_sign_in_and_quota_before_creating_anything():
    s = _text("infra/provision.sh")
    first_create = s.index("az group create")
    for check in ('*"#EXT#"*)', "az account get-access-token --scope", "az cognitiveservices usage list"):
        assert s.index(check) < first_create, check
    assert "--disable-local-auth" in s and "--admin-enabled false" in s and "--admin-enabled true" not in s
    # Everything once done by hand is scripted: tracing connected to Foundry, the log cap, the CI identity, a budget.
    for step in ("az monitor app-insights component create", "project connection create", "workspace update", "--quota",
                 "federated-credential create", "Microsoft.Consumption/budgets", "gh variable set"):
        assert step in s, step
    assert "source .env" not in s and "Convert to internal" not in s


def test_deploys_never_use_a_registry_password():
    for rel in ("infra/deploy-app.sh", "infra/ci-deploy.sh", ".github/workflows/build-image.yml"):
        s = _text(rel)
        assert "acr credential" not in s and "ACR_PASSWORD" not in s and "ACR_USERNAME" not in s, rel
    assert "--identity system" in _text("infra/deploy-app.sh")
    assert "secret set" not in _text("infra/ci-deploy.sh")  # CI changes the image only


def test_the_workflow_deploys_only_from_main_with_a_federated_identity():
    import yaml

    wf = yaml.safe_load(_text(".github/workflows/build-image.yml"))
    assert wf["permissions"]["id-token"] == "write"
    deploy = wf["jobs"]["deploy"]
    assert deploy["needs"] == "build" and "pull_request" in deploy["if"] and "vars.AZURE_CLIENT_ID" in deploy["if"]
    assert wf["jobs"]["build"]["needs"] == "test"
    assert "secrets." not in _text(".github/workflows/build-image.yml")


def _fake_az(tmp_path, latest, ready, state):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    script = bin_dir / "az"
    script.write_text(f"""#!/bin/sh
case "$*" in
  *latestRevisionName*) echo {latest} ;;
  *latestReadyRevisionName*) echo {ready} ;;
  *runningState*) echo {state} ;;
  *logs*) echo "fake log line" ;;
esac
""")
    script.chmod(0o755)
    return str(bin_dir)


@pytest.mark.parametrize("latest,ready,state,ok", [("app--d2", "app--d2", "Running", True), ("app--d2", "app--d1", "Failed", False)])
def test_wait_ready_needs_the_newest_revision_to_be_the_ready_one(tmp_path, latest, ready, state, ok):
    env = {"PATH": _fake_az(tmp_path, latest, ready, state) + ":/usr/bin:/bin"}
    run = subprocess.run(["bash", "-c", f'. "{ROOT}/infra/lib/aca.sh"; wait_ready app rg'], capture_output=True, text=True, env=env)
    assert (run.returncode == 0) == ok, run
    if not ok:
        assert "did not become ready" in run.stderr and "traffic stays on app--d1" in run.stderr and "fake log line" in run.stderr


def test_provision_is_safe_in_a_shared_directory():
    s = _text("infra/provision.sh")
    first_create = s.index("az group create")
    # The subscription is named, never the CLI's default, and every resource command carries it.
    assert s.index('"${SUBSCRIPTION:-}"') < s.index("SUB_ID=$(az account show") < first_create
    assert 'command az "$@" --subscription "$SUB_ID"' in s
    # The deploy identity is looked up, reused and deleted only among apps the signed-in person owns.
    assert "--show-mine" in s and 'ad app list --display-name' not in s
    # A .env from another environment (its token and app URL) is never carried over.
    assert s.index('for subscription $SUB_ID') < first_create and "REGISTA_SUBSCRIPTION_ID=$SUB_ID" in s
    # Offers without budgets (Azure for Students) do not stop the run.
    assert 'budget not created' in s
    assert 'REGISTA_SUBSCRIPTION_ID' in _text("infra/deploy-app.sh")
