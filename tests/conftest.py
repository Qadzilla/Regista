"""Test-wide isolation.

- Every test gets its own empty feedback folder, so no test reads verdicts or a model another test (or a real
  person) produced. The folder is resolved per call (regista.feedback.feedback_dir), so this works per test.
- Tests never reach real Azure: the project's .env is not loaded and cloud variables are cleared, so every
  Foundry, Cosmos DB, and Search path in the tests runs against fakes or not at all.
"""

import os

import pytest

os.environ["REGISTA_DOTENV"] = ""
for _var in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL", "REGISTA_COSMOS_ENDPOINT", "REGISTA_COSMOS_KEY", "REGISTA_CLOUD",
             "REGISTA_SEARCH_ENDPOINT", "APPLICATIONINSIGHTS_CONNECTION_STRING", "REGISTA_ADMIN_TOKEN", "REGISTA_STUDIO_VIEW_TOKEN",
             "REGISTA_READONLY"):
    os.environ.pop(_var, None)


@pytest.fixture(autouse=True)
def _isolated_feedback(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("REGISTA_FEEDBACK_DIR", str(tmp_path_factory.mktemp("feedback")))
