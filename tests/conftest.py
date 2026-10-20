"""Test-wide isolation.

- Tests never read or write the real human feedback in data/feedback.
- Tests never reach real Azure: the project's .env is not loaded and cloud variables are cleared, so every
  Foundry and Cosmos DB path in the tests runs against fakes or not at all.
"""

import os
import tempfile

os.environ["REGISTA_FEEDBACK_DIR"] = tempfile.mkdtemp(prefix="regista_test_feedback_")
os.environ["REGISTA_DOTENV"] = ""
for _var in ("FOUNDRY_PROJECT_ENDPOINT", "FOUNDRY_MODEL", "REGISTA_COSMOS_ENDPOINT", "REGISTA_COSMOS_KEY", "REGISTA_CLOUD",
             "REGISTA_SEARCH_ENDPOINT", "APPLICATIONINSIGHTS_CONNECTION_STRING"):
    os.environ.pop(_var, None)
