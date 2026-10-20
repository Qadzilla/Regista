"""Microsoft Foundry behind the Label and Librarian agents, through the Microsoft Agent Framework.

Both agents keep the exact role, inputs, outputs, and state keys of their rule-based versions
(``regista.agents.roles``), so the orchestrator, the trace, and the tests do not change.

- ``FoundryLabelAgent`` asks a Foundry model deployment to title, tag, score, and explain each
  clip, given the clip's events and the rules-v0 label as a prior. Output is structured JSON
  (``response_format``) and validated against the tag vocabulary; any clip the model cannot
  label falls back to rules-v0 and says so in ``model``.
- ``FoundryLibrarianAgent`` is an Agent Framework agent with Regista's own MCP server attached
  as a stdio tool. It calls ``search_clips`` itself and writes a short broadcast-ready answer;
  the deterministic results are kept alongside so the UI can still show clips.

Credentials: ``DefaultAzureCredential`` (az login locally, managed identity in Container Apps).
Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL; see ``regista.cloud.config``.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from regista.agents.base import AgentError, State
from regista.aio import run_sync
from regista.agents.roles import LabelAgent, LibrarianAgent, flag_for_review, learned_model
from regista.clips import REASON_TAGS, TAG_WEIGHTS, StreamIndex, label_clips, match_minute
from regista.cloud.config import CloudConfig
from regista.librarian import search_clips

Record = dict[str, Any]
Runner = Callable[[str, str], Awaitable[str]]  # (instructions, prompt) -> model text

ALLOWED_TAGS = set(TAG_WEIGHTS) | REASON_TAGS | {f"{t}_against" for t in ("goal", "nutmeg", "take_on", "foul")}

LABEL_INSTRUCTIONS = """You are Regista's Label Agent, writing for a football broadcast studio.
For ONE clip you get: the player, why the clip was cut, the match minute, the events the player
was involved in, and a rule-based prior label. Return JSON only, with keys:
  title        short on-screen title, at most 70 characters, name and kit number first
  tags         list drawn ONLY from the allowed vocabulary given to you; keep the reason tag
  watchability number 0 to 1: would a highlights editor keep this clip? goals and nutmegs ~1.0,
               routine passes ~0.2; use the prior as a guide but judge the events
  summary      one sentence a commentator could read
  explanation  one sentence starting with "Scored" that states why the watchability is what it is
Never invent events that are not listed. Never mention that you are a model."""

LIBRARIAN_INSTRUCTIONS = """You are Regista's Librarian for a football broadcast desk. The user asks for clips of a player
in plain English. Tools:
- search_clips (Regista MCP): one match's clips; always call it first with the match_dir and the user's exact query.
- search_library (Regista MCP): every indexed match at once, when the user asks beyond this match.
- Azure MCP Server, when attached: cosmos_database_container_item_query runs a read-only SELECT on the Cosmos DB library
  (account, database "regista", containers matches / clips / labels / annotations, partition key match_id) for counts and
  history; search_index_query queries the Azure AI Search index "regista-clips".
Answer in at most two sentences: say how many clips matched and name the best one or two by title and minute. If nothing
matched, say what the tool reported and suggest the nearest thing it offered. Never invent clips a tool did not return."""


_CHILD_ENV_PREFIXES = ("REGISTA_", "FOUNDRY_", "AZURE_", "IDENTITY_", "MSI_")
_CHILD_ENV_NAMES = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "TMPDIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
_CHILD_ENV_SECRETS = ("REGISTA_COSMOS_KEY", "APPLICATIONINSIGHTS_CONNECTION_STRING")


def child_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """An allowlisted environment for MCP child processes: configuration and Azure identity, never stored secrets."""
    import os

    env = {k: v for k, v in os.environ.items()
           if (k in _CHILD_ENV_NAMES or k.startswith(_CHILD_ENV_PREFIXES)) and k not in _CHILD_ENV_SECRETS}
    env.update(extra or {})
    return env


AZURE_MCP_TOOLS = {"cosmos": ["cosmos_database_container_item_query", "cosmos_list"], "search": ["search_index_query"]}


def azure_mcp_args(cloud: CloudConfig, namespaces: tuple[str, ...] | None = None) -> tuple[list[str], list[str]]:
    """Command-line arguments and allowed tools for the Azure MCP Server: read-only, only the namespaces asked for
    (default: Cosmos DB, plus AI Search when configured), and only those a configured service backs."""
    wanted = namespaces if namespaces is not None else ("cosmos", "search")
    have = {"cosmos": cloud.cosmos_enabled, "search": cloud.search_enabled}
    use = [ns for ns in wanted if have.get(ns)]
    args = ["server", "start", "--mode", "all", "--read-only"]
    allowed: list[str] = []
    for ns in use:
        args += ["--namespace", ns]
        allowed += AZURE_MCP_TOOLS[ns]
    return args, allowed


def azure_mcp_env() -> dict[str, str]:
    """Environment for the azmcp child: configuration and Azure identity only (see ``child_env``).

    azmcp is a .NET binary that loads ICU for culture data unless told not to; the slim container image has no ICU,
    so it runs in invariant-globalization mode (its queries and answers do not depend on culture)."""
    import os

    managed = bool(os.environ.get("IDENTITY_ENDPOINT") or os.environ.get("MSI_ENDPOINT"))
    return child_env({"AZURE_TOKEN_CREDENTIALS": "prod" if managed else "AzureCliCredential", "AZURE_MCP_COLLECT_TELEMETRY": "false",
                      "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"})


def azure_mcp_tool(cloud: CloudConfig, namespaces: tuple[str, ...] | None = None):
    """Microsoft's Azure MCP Server (pip package msmcp-azure), read-only, limited to Cosmos DB and AI Search queries.

    Locally it signs in with the Azure CLI; in Container Apps with the app's managed identity. None when the binary is
    missing or no requested namespace is backed by a configured service."""
    import shutil

    from agent_framework import MCPStdioTool

    exe = shutil.which("azmcp")
    args, allowed = azure_mcp_args(cloud, namespaces)
    if exe is None or not allowed:
        return None
    return MCPStdioTool(name="azure", command=exe, args=args, env=azure_mcp_env(), allowed_tools=allowed, load_prompts=False,
                        approval_mode="never_require")


def tools_used(result: Any) -> list[str]:
    """Names of the tools the agent called during a run, in order (for the trace and for transparency)."""
    names = []
    for msg in getattr(result, "messages", []) or []:
        for c in getattr(msg, "contents", []) or []:
            if getattr(c, "type", None) == "function_call" and getattr(c, "name", None):
                names.append(c.name)
    return names


def cosmos_account_name(cloud: CloudConfig) -> str | None:
    import re

    m = re.match(r"https://([^.]+)\.", cloud.cosmos_endpoint or "")
    return m.group(1) if m else None


def search_service_name(cloud: CloudConfig) -> str | None:
    import re

    m = re.match(r"https://([^.]+)\.", cloud.search_endpoint or "")
    return m.group(1) if m else None


@dataclass
class LabelOut:
    """What the model must return per clip (validated by hand; no pydantic dependency in core)."""

    title: str
    tags: list[str]
    watchability: float
    summary: str
    explanation: str

    @classmethod
    def parse(cls, text: str) -> LabelOut:
        obj = _extract_json(text)
        tags = [str(t).strip().lower().replace(" ", "_") for t in obj.get("tags", [])]
        return cls(title=str(obj["title"]).strip()[:120], tags=tags, watchability=float(obj["watchability"]),
                   summary=str(obj.get("summary", "")).strip(), explanation=str(obj.get("explanation", "")).strip())


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def clip_prompt(index: StreamIndex, clip: Record, prior: Record) -> str:
    player = index.roster[clip["player_id"]]
    team = next(t["name"] for t in index.match["teams"] if t["team_id"] == player["team_id"])
    events = []
    for eid in clip["event_ids"]:
        e = index.events_by_id.get(eid)
        if not e:
            continue
        who = "player" if e.get("player_id") == clip["player_id"] else "opponent/teammate"
        related = index.roster.get(e.get("related_player_id") or "", {}).get("name")
        events.append({"minute": match_minute(index.match, e["t"]), "type": e["event_type"], "by": who, "outcome": e.get("outcome"),
                       "related": related, "qualifiers": e.get("qualifiers", []), "metrics": e.get("metrics", {})})
    seg = index.seg_by_id[clip["segment_ids"][0]]
    return json.dumps({
        "player": {"name": player["name"], "kit_number": player["kit_number"], "position": player["position"], "team": team},
        "reason_for_cut": clip["reason"],
        "camera": {"kind": seg["kind"], "playback_speed": seg.get("playback_speed", 1.0), "angle": seg.get("angle")},
        "minute": match_minute(index.match, clip["keyframe_t"]),
        "duration_s": round(clip["t_end"] - clip["t"], 1),
        "events": events,
        "prior_label": {"title": prior["title"], "tags": prior["tags"], "watchability": prior["watchability"]},
        "allowed_tags": sorted(ALLOWED_TAGS),
    }, ensure_ascii=False) + "\n\nRespond with JSON only."  # JSON mode requires the word 'json' in the input, not only the instructions


def validate_label(out: LabelOut, prior: Record) -> tuple[LabelOut, list[str]]:
    """Keep the model honest: known tags only, the reason tag kept, watchability clamped."""
    notes = []
    tags = [t for t in out.tags if t in ALLOWED_TAGS]
    dropped = [t for t in out.tags if t not in ALLOWED_TAGS]
    if dropped:
        notes.append(f"dropped unknown tags {dropped}")
    reason = next(t for t in prior["tags"] if t in REASON_TAGS)
    if reason not in tags:
        tags.append(reason)
    if not tags:
        tags = list(prior["tags"])
    w = min(1.0, max(0.0, out.watchability))
    if w != out.watchability:
        notes.append("clamped watchability")
    return LabelOut(title=out.title or prior["title"], tags=list(dict.fromkeys(tags)), watchability=round(w, 3),
                    summary=out.summary or prior["summary"], explanation=out.explanation or prior["explanation"]), notes


async def foundry_runner(config: CloudConfig, *, response_json: bool = False) -> Runner:
    """A (instructions, prompt) -> text coroutine backed by Agent Framework + Foundry. Built once, reused."""
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential()
    client = FoundryChatClient(project_endpoint=config.foundry_project_endpoint, model=config.foundry_model, credential=credential)

    async def run(instructions: str, prompt: str) -> str:
        options = {"response_format": {"type": "json_object"}} if response_json else None
        agent = Agent(client=client, name="regista", instructions=instructions, default_options=options)
        result = await agent.run(prompt)
        return getattr(result, "text", None) or str(result)

    return run


@dataclass
class FoundryLabelAgent(LabelAgent):
    """LabelAgent whose labels come from a Foundry model, validated and with rules-v0 as the fallback."""

    description: str = "Titles, tags, scores and explains each clip with a Microsoft Foundry model (Agent Framework); rules-v0 prior and fallback."
    config: dict[str, Any] = field(default_factory=dict)
    cloud: CloudConfig | None = None
    runner: Runner | None = None  # injectable for tests
    concurrency: int = 4

    def handle(self, state: State) -> State:
        cloud = self.cloud or CloudConfig.from_env()
        if self.runner is None and not cloud.foundry_enabled:
            raise AgentError("Foundry is not configured (FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL)", retryable=False)
        index: StreamIndex = state["index"]
        labels: dict[str, list[Record]] = {}
        notes: dict[str, list[str]] = {}
        for pid, clips in state["clips"].items():
            priors = label_clips(index, clips, model="rules-v0", scorer=learned_model(self.config))
            labels[pid], notes[pid] = run_sync(self._label_all(cloud, index, clips, priors))
        state["labels"] = labels
        state["label_notes"] = notes
        return state

    async def _label_all(self, cloud: CloudConfig, index: StreamIndex, clips: list[Record], priors: list[Record]) -> tuple[list[Record], list[str]]:
        runner = self.runner or await foundry_runner(cloud, response_json=True)
        model_name = f"foundry:{cloud.foundry_model}" if self.runner is None else "foundry:test"
        sem = asyncio.Semaphore(self.concurrency)
        notes: list[str] = []

        async def one(clip: Record, prior: Record) -> Record:
            async with sem:
                try:
                    text = await runner(LABEL_INSTRUCTIONS, clip_prompt(index, clip, prior))
                    out, why = validate_label(LabelOut.parse(text), prior)
                    notes.extend(f"{clip['id']}: {w}" for w in why)
                    # prior_watchability stays the rules score (the learned model's training input); the score Foundry revised
                    # (rules or learned) is what needs_review compares against.
                    revised = {**prior, "title": out.title, "tags": out.tags, "watchability": out.watchability, "summary": out.summary,
                               "explanation": out.explanation, "model": model_name,
                               "prior_watchability": prior.get("prior_watchability", prior["watchability"])}
                    flagged = flag_for_review([{**revised, "prior_watchability": prior["watchability"]}])[0]
                    if flagged.get("review"):
                        revised["review"] = flagged["review"]
                    return revised
                except Exception as exc:  # noqa: BLE001 - a bad model answer must not lose the clip
                    notes.append(f"{clip['id']}: fell back to {prior.get('model', 'rules-v0')} ({type(exc).__name__}: {str(exc)[:120]})")
                    return flag_for_review([{**prior, "model": f"{prior.get('model', 'rules-v0')} (foundry fallback)"}])[0]

        results = await asyncio.gather(*(one(c, p) for c, p in zip(clips, priors)))
        return list(results), notes


@dataclass
class FoundryLibrarianAgent(LibrarianAgent):
    """LibrarianAgent that answers through a Foundry model using Regista's MCP server as its tool."""

    description: str = "Answers questions with a Microsoft Foundry model that calls Regista's MCP search_clips tool (Agent Framework)."
    config: dict[str, Any] = field(default_factory=dict)
    cloud: CloudConfig | None = None
    # (match_dir, query) -> text, or (text, tools used); injectable for tests
    answerer: Callable[[str, str], Awaitable[str | tuple[str, list[str]]]] | None = None
    last_tools_used: list[str] = field(default_factory=list)

    def handle(self, state: State) -> State:
        cloud = self.cloud or CloudConfig.from_env()
        if self.answerer is None and not cloud.foundry_enabled:
            raise AgentError("Foundry is not configured (FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL)", retryable=False)
        from regista import librarian as lib

        lib._load.cache_clear()
        answers = []
        for q in state["queries"]:
            structured = search_clips(state["match_dir"], q, self.config.get("limit", 10))
            try:
                self.last_tools_used = []
                text = run_sync(self._answer(cloud, state["match_dir"], q))
                structured["answer"] = text
                structured["answered_by"] = f"foundry:{cloud.foundry_model}" if self.answerer is None else "foundry:test"
                structured["tools_used"] = list(self.last_tools_used)
            except Exception as exc:  # noqa: BLE001
                structured["answer"] = structured["message"]
                structured["answered_by"] = f"rules (foundry fallback: {type(exc).__name__})"
            answers.append(structured)
        state["answers"] = answers
        return state

    async def _answer(self, cloud: CloudConfig, match_dir: str, query: str) -> str:
        if self.answerer is not None:
            out = await self.answerer(match_dir, query)
            if isinstance(out, tuple):
                out, self.last_tools_used = out[0], list(out[1])
            return out
        from agent_framework import Agent, MCPStdioTool
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        from contextlib import AsyncExitStack

        async with DefaultAzureCredential() as credential, AsyncExitStack() as stack:
            client = FoundryChatClient(project_endpoint=cloud.foundry_project_endpoint, model=cloud.foundry_model, credential=credential)
            # config["regista_tools"] / config["azure_namespaces"] narrow the tools for public use (see regista.api /ask).
            regista_mcp = MCPStdioTool(name="regista", command=sys.executable, args=["-m", "regista.mcp_server"], env=child_env(),
                                       allowed_tools=self.config.get("regista_tools"))
            tools = [await stack.enter_async_context(regista_mcp)]
            azure = (azure_mcp_tool(cloud, self.config.get("azure_namespaces"))
                     if (cloud.cosmos_enabled or cloud.search_enabled) and self.config.get("azure_mcp", True) else None)
            context = [f"match_dir: {match_dir}"]
            if azure is not None:
                try:
                    tools.append(await stack.enter_async_context(azure))
                except Exception:  # noqa: BLE001 - the Librarian still answers with Regista's own tools
                    azure = None
            if azure is not None:
                _args, allowed = azure_mcp_args(cloud, self.config.get("azure_namespaces"))
                if cloud.cosmos_enabled and "cosmos_list" in allowed:
                    context.append(f"cosmos account: {cosmos_account_name(cloud)}, database: {cloud.cosmos_database}")
                if cloud.search_enabled and "search_index_query" in allowed:
                    context.append(f"search service: {search_service_name(cloud)}, index: regista-clips")
            # Name the tools it actually holds, so it never offers one this deployment withheld (the public endpoint has no Cosmos DB tool).
            held = list(self.config.get("regista_tools") or ["search_clips", "search_library", "derive_clips", "validate_stream",
                                                               "render_clip", "list_matches"])
            if azure is not None:
                held += azure_mcp_args(cloud, self.config.get("azure_namespaces"))[1]
            context.append("tools you hold (offer nothing else): " + ", ".join(held))
            agent = await stack.enter_async_context(Agent(client=client, name="regista-librarian", instructions=LIBRARIAN_INSTRUCTIONS))
            result = await agent.run("\n".join(context) + f"\nquery: {query}", tools=tools)
            self.last_tools_used = tools_used(result)
            return getattr(result, "text", None) or str(result)
