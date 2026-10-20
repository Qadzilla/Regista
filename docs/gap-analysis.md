# Gap analysis: Regista against the hackathon's intentions (2026-10-20)

## Progress (updated the same day)

| Fix | Status |
|---|---|
| 1. Pipeline as an Agent Framework workflow | **Done.** `regista.agents.workflow`; diagram in `docs/workflow.md`; 10 tests |
| 2. Human in the loop and learning from Zaid | **Done.** Review pause (`request_info`), viewer Keep/Drop, `--review` prompt, review API; verdicts in `data/feedback` and Cosmos DB; model retrains from them. Waiting on Zaid's real verdicts |
| 3. Azure AI Search behind the Librarian | **Done.** Free service in South Central US, `indexer` role, `search_library` MCP tool |
| 4. Azure MCP Server | **Done.** Attached to the Foundry Librarian (read-only Cosmos DB and Search tools); seen calling `cosmos_database_container_item_query` |
| 5. Foundry tracing | **Done.** Application Insights connected to the project; full workflow, agent, model, and tool spans verified |
| 6. Vision agents | **v0 done on rendered footage.** Shot, identity, possession agents as an Agent Framework workflow; reproduced end to end on held-out matches (clip recall 0.80 and 1.00, precision 1.00). Real broadcast footage, event spotting, and the Azure AI Vision OCR backend are next |


Scored against the five equally weighted criteria in CLAUDE.md §1.1, the target category (Best Multi-Agent System), and the product plan in CLAUDE.md §2.3. Each gap names the fix and the hero technology it uses. "Running" means code calls it today.

## Where we stand

| Area | Today | Gap |
|---|---|---|
| Orchestration | Seven roles hand off through a hand-written Python orchestrator with retries, a trace, and dead letters | The category asks for Agent Framework / A2A orchestration. Ours is custom. |
| Model-backed agents | Label and Librarian run on Microsoft Foundry (gpt-5-mini) through Agent Framework | Five of seven roles are deterministic; the pipeline never asks a human anything |
| Human in the loop (plan step 3) | Annotation record type exists; only synthetic placeholders | No review surface, no real verdicts, nothing learns from them |
| Learning (plan steps 5, 6) | Watchability is a hand-set weight table plus a prompted model | Nothing is trained on feedback |
| Retrieval | The Librarian parses queries and ranks labels in memory | No search service; does not scale past one match |
| MCP | Regista's own MCP server, used by the Foundry Librarian | Azure MCP Server (a named hero technology) unused |
| Observability | trace.jsonl per run | Foundry tracing not wired; judges cannot see agent spans in the Foundry portal |
| Vision layer (plan steps 1, 2) | Designed; the generator stands in for it | No Shot, Identity, or Possession agent reads video |
| Microsoft Fabric | Not used | Fabric needs a work or school account; the trial runs on a personal Microsoft account. Stays planned unless that changes. |
| GitHub Copilot Agent Mode | Not used; we build with Claude Code | Not claimed, by decision |

## Fixes, in build order

1. **Pipeline as a Microsoft Agent Framework workflow.** Every role becomes a workflow executor with typed handoffs, shared state, retries, dead letters, and checkpointing, using Agent Framework's own primitives. The graph renders to a diagram for the README and the demo. Criterion 2 and the category.
2. **Human in the loop and learning from Zaid.** The Label agent pauses the workflow when it is unsure (the rule-based prior and the Foundry model disagree, or the model's own score is borderline) and asks for a verdict through Agent Framework's request-and-response mechanism. Verdicts are stored as real `annotation` records. A watchability model is retrained from those verdicts and becomes the Label agent's prior, and the Foundry labeller is scored against Zaid. Plan steps 3, 5, and 6; criteria 2 and 3.
3. **Azure AI Search behind the Librarian.** Labels are indexed per match and player; the Librarian's MCP tool queries the index with filters, so search works across every match ever processed. Criterion 1 (Azure AI Services).
4. **Azure MCP Server.** A Producer agent, Agent Framework on Foundry, answers questions about the stored library (counts, best clips per player, what was labelled when) by calling the official Azure MCP Server's Cosmos DB tools. Criterion 1 (Azure MCP) and criterion 2 (a second MCP integration).
5. **Foundry tracing.** Agent Framework's OpenTelemetry spans export to Application Insights connected to the Foundry project, so every agent call, tool call, and token count is visible in the Foundry portal. Best Use of Foundry and Best Enterprise Solution.
6. **Vision agents.** Shot, Identity, and Possession executors read a broadcast video and emit the event stream. They are built and tested on Regista's own rendered broadcast first, where the generator provides exact ground truth for accuracy numbers, and then on the real footage Zaid provides. Identity reads kit numbers with Azure AI Vision. Plan steps 1 and 2; criteria 1 and 3.

## Not doing, and why

- **GitHub Copilot Agent Mode:** the project is built with Claude Code; claiming Copilot would be untrue.
- **Fabric:** needs an organisational tenant. Revisit only if a work or school account becomes available.
