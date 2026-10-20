"""Cloud configuration from the environment (and a local ``.env`` if present).

Variables
---------
FOUNDRY_PROJECT_ENDPOINT   https://<resource>.services.ai.azure.com/api/projects/<project>   (Agent Framework's own name)
FOUNDRY_MODEL              the model deployment name, e.g. gpt-5-mini
REGISTA_COSMOS_ENDPOINT    https://<account>.documents.azure.com:443/
REGISTA_COSMOS_DATABASE    database name (default: regista)
REGISTA_COSMOS_KEY         optional account key; without it DefaultAzureCredential (az login, managed identity) is used

Authentication is keyless by default: ``DefaultAzureCredential`` picks up ``az login`` on a laptop
and the managed identity inside Azure Container Apps.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path | str = ".env") -> dict[str, str]:
    """Minimal .env loader: KEY=VALUE lines, '#' comments, optional quotes. Never overrides real env vars."""
    path = Path(path)
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


@dataclass(frozen=True)
class CloudConfig:
    foundry_project_endpoint: str | None = None
    foundry_model: str | None = None
    cosmos_endpoint: str | None = None
    cosmos_database: str = "regista"
    cosmos_key: str | None = None
    search_endpoint: str | None = None

    @classmethod
    def from_env(cls, dotenv: Path | str | None = None) -> CloudConfig:
        """Read the environment, after loading ``dotenv`` (default: $REGISTA_DOTENV, else ``.env``; empty disables it)."""
        if dotenv is None:
            dotenv = os.environ.get("REGISTA_DOTENV", ".env")
        if dotenv:
            load_dotenv(dotenv)
        return cls(
            foundry_project_endpoint=os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or None,
            foundry_model=os.environ.get("FOUNDRY_MODEL") or None,
            cosmos_endpoint=os.environ.get("REGISTA_COSMOS_ENDPOINT") or None,
            cosmos_database=os.environ.get("REGISTA_COSMOS_DATABASE") or "regista",
            cosmos_key=os.environ.get("REGISTA_COSMOS_KEY") or None,
            search_endpoint=os.environ.get("REGISTA_SEARCH_ENDPOINT") or None,
        )

    @property
    def foundry_enabled(self) -> bool:
        return bool(self.foundry_project_endpoint and self.foundry_model)

    @property
    def cosmos_enabled(self) -> bool:
        return bool(self.cosmos_endpoint)

    @property
    def search_enabled(self) -> bool:
        return bool(self.search_endpoint)

    def describe(self) -> str:
        parts = [
            f"Foundry: {'on (' + str(self.foundry_model) + ')' if self.foundry_enabled else 'off'}",
            f"Cosmos DB: {'on (' + self.cosmos_database + ')' if self.cosmos_enabled else 'off'}",
            f"AI Search: {'on' if self.search_enabled else 'off'}",
        ]
        return "; ".join(parts)
