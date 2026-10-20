"""Azure wiring for Regista: Microsoft Foundry behind the Label and Librarian agents, Cosmos DB behind Persist.

Nothing here is required to run Regista locally. Each piece reads its configuration from the
environment (see ``regista.cloud.config`` and ``.env.example``) and is only selected when it is
configured, so the rule-based agents remain the default and the fallback.
"""

from regista.cloud.config import CloudConfig


def agents_for(config: CloudConfig | None = None, *, require: bool = False):
    """The default pipeline with Foundry and Cosmos agents swapped in wherever they are configured.

    ``require=True`` raises if nothing cloud-side is configured (for ``--cloud`` on the CLI)."""
    from regista.agents.roles import default_agents

    config = config or CloudConfig.from_env()
    if require and not (config.foundry_enabled or config.cosmos_enabled):
        raise RuntimeError("no cloud configuration found; set FOUNDRY_PROJECT_ENDPOINT/FOUNDRY_MODEL and/or REGISTA_COSMOS_ENDPOINT (see .env.example)")
    agents = default_agents()
    if config.foundry_enabled:
        from regista.cloud.foundry import FoundryLabelAgent, FoundryLibrarianAgent

        agents = [FoundryLabelAgent(cloud=config) if a.role == "label" else FoundryLibrarianAgent(cloud=config) if a.role == "librarian" else a for a in agents]
    if config.cosmos_enabled:
        from regista.cloud.cosmos import CosmosPersistAgent

        agents = [CosmosPersistAgent(cloud=config) if a.role == "persist" else a for a in agents]
    return agents


__all__ = ["CloudConfig", "agents_for"]
