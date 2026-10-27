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
- ``foundry_scout_answer`` is the Scout agent (Scout view): an Agent Framework agent with Regista's MCP server
  limited to the read-only player tools (``search_players``, ``get_profile``, ``compare_players``).
- ``foundry_recap_text`` is the Recap agent: it writes a match recap from the facts ``regista.recap`` reads, every
  sentence citing them; ``regista.recap.check_written`` keeps only what holds. ``FoundryRecapAgent`` is its workflow role.

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
from regista.conversation import pick, timed_step
from regista.librarian import search_clips
from regista.recap import RecapAgent

Record = dict[str, Any]
Runner = Callable[[str, str], Awaitable[str]]  # (instructions, prompt) -> model text

ALLOWED_TAGS = set(TAG_WEIGHTS) | REASON_TAGS | {f"{t}_against" for t in ("goal", "nutmeg", "take_on", "foul")}

LABEL_INSTRUCTIONS = """You are Regista's Label Agent, writing for a football broadcast studio.
For ONE clip you get: the player, why the clip was cut, the match minute, the events the player
was involved in, and a rule-based prior label. Return JSON only, with keys:
  title        short on-screen title, at most 70 characters, in the prior title's shape: name and kit number,
               then the moment in plain words and its minute ("Sami Castellanos (9): goal at 1'")
  tags         list drawn ONLY from the allowed vocabulary given to you; keep the reason tag
  watchability number 0 to 1: would a highlights editor keep this clip? goals and nutmegs ~1.0,
               routine passes ~0.2; use the prior as a guide but judge the events
  summary      one sentence a commentator could read
  explanation  one or two plain football sentences a fan would understand: what happens in the clip and why it is
               worth watching (or not), using the player's name
The title, summary and explanation are read by fans: no numbers other than the minute (never the watchability, which
is shown beside them, and no distances, speeds or probabilities), and no jargon such as xG.
Never invent events that are not listed. Never mention that you are a model."""

LIBRARIAN_INSTRUCTIONS = """You are Regista's Librarian for a football broadcast desk. The user asks for clips of a player
in plain English. Tools:
- search_clips (Regista MCP): one match's clips; always call it first with the match_dir and the user's exact query.
- search_library (Regista MCP): every indexed match at once, when the user asks beyond this match.
- Azure MCP Server, when attached: cosmos_database_container_item_query runs a read-only SELECT on the Cosmos DB library
  (account, database "regista", containers matches / clips / labels / annotations, partition key match_id) for counts and
  history; search_index_query queries the Azure AI Search index "regista-clips".
Answer in at most two sentences: say how many moments matched and name the best one or two by title and minute. If nothing
matched, say what the tool reported and suggest the nearest thing it offered. Never invent clips a tool did not return."""


_CHILD_ENV_PREFIXES = ("REGISTA_", "FOUNDRY_", "AZURE_", "IDENTITY_", "MSI_")
_CHILD_ENV_NAMES = ("PATH", "PYTHONPATH", "HOME", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "TMPDIR", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
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


REGISTA_MCP_TOOLS = ("search_clips", "search_library", "list_matches", "derive_clips", "validate_stream", "render_clip",
                     "search_players", "get_profile", "compare_players", "match_recap", "list_competitions",
                     "search_catalogue_players", "get_catalogue_player")


def tool_server(name: str) -> str | None:
    """Which MCP server a tool the Librarian called lives on: Regista's own, or Microsoft's Azure MCP Server."""
    if name in REGISTA_MCP_TOOLS:
        return "regista-mcp"
    if name.startswith(("cosmos_", "search_index_")) or any(name in tools for tools in AZURE_MCP_TOOLS.values()):
        return "azure-mcp"
    return None


TRACE_FALLBACK_NOTE = ("No spans were recorded for this run, so the trace lists the tools the model called, in order, "
                       "without timings.")


def foundry_trace(spans: list[Any], tools: list[str]) -> tuple[list[Record], str | None]:
    """The answer trace of one Foundry run: its Agent Framework spans (agent, model calls, tool calls, with durations),
    or, when none were recorded, the tools it called in order without timings and a note saying so."""
    from regista.cloud.telemetry import spans_to_trace

    steps = spans_to_trace(spans, tool_server)
    if steps:
        return steps, None
    return [{"name": t, "kind": "tool", "server": tool_server(t), "ms": None} for t in tools], TRACE_FALLBACK_NOTE


def tools_used(result: Any) -> list[str]:
    """Names of the tools the agent called during a run, in order (for the trace and for transparency)."""
    names = []
    for msg in getattr(result, "messages", []) or []:
        for c in getattr(msg, "contents", []) or []:
            if getattr(c, "type", None) == "function_call" and getattr(c, "name", None):
                names.append(c.name)
    return names


def tool_calls(result: Any) -> list[tuple[str, dict[str, Any]]]:
    """The tools the agent called during a run with their arguments, in order (arguments parsed from JSON text)."""
    calls = []
    for msg in getattr(result, "messages", []) or []:
        for c in getattr(msg, "contents", []) or []:
            if getattr(c, "type", None) == "function_call" and getattr(c, "name", None):
                args = getattr(c, "arguments", None)
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                calls.append((c.name, dict(args) if isinstance(args, dict) else {}))
    return calls


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
        from regista.cloud.telemetry import capture_spans

        lib._load.cache_clear()
        answers = []
        for q in state["queries"]:
            trace: list[Record] = []
            structured = timed_step(trace, "librarian.search_clips", search_clips, state["match_dir"], q, self.config.get("limit", 10))
            try:
                self.last_tools_used = []
                with capture_spans("regista.librarian.answer") as cap:  # the Agent Framework spans of this answer, for its trace
                    text = run_sync(self._answer(cloud, state["match_dir"], q))
                structured["answer"] = text
                structured["answered_by"] = f"foundry:{cloud.foundry_model}" if self.answerer is None else "foundry:test"
                structured["tools_used"] = list(self.last_tools_used)
                steps, note = foundry_trace(cap.spans, self.last_tools_used)
                trace += steps
                if note:
                    structured["trace_note"] = note
            except Exception as exc:  # noqa: BLE001
                structured["answer"] = structured["message"]
                structured["answered_by"] = f"rules (foundry fallback: {type(exc).__name__})"
            structured["trace"] = trace
            answers.append(structured)
        state["answers"] = answers
        return state

    async def _answer(self, cloud: CloudConfig, match_dir: str, query: str) -> str:
        if self.answerer is not None:
            out = await self.answerer(match_dir, query)
            if isinstance(out, tuple):
                out, self.last_tools_used = out[0], list(out[1])
            return out
        from contextlib import AsyncExitStack

        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        async with DefaultAzureCredential() as credential, AsyncExitStack() as stack:
            client = FoundryChatClient(project_endpoint=cloud.foundry_project_endpoint, model=cloud.foundry_model, credential=credential)
            tools, context = await open_librarian_tools(stack, cloud, self.config)
            context.insert(0, f"match_dir: {match_dir}")
            agent = await stack.enter_async_context(Agent(client=client, name="regista-librarian", instructions=LIBRARIAN_INSTRUCTIONS))
            result = await agent.run("\n".join(context) + f"\nquery: {query}", tools=tools)
            self.last_tools_used = tools_used(result)
            return getattr(result, "text", None) or str(result)


async def open_librarian_tools(stack: Any, cloud: CloudConfig, config: dict[str, Any]) -> tuple[list[Any], list[str]]:
    """Regista's MCP server and, when configured, Microsoft's Azure MCP Server, entered on ``stack``. ``config`` may
    narrow them (``regista_tools``, ``azure_namespaces``; the public endpoints do). Returns the tools and the context
    lines that tell the model what it holds, so it never offers a tool this deployment withheld."""
    from agent_framework import MCPStdioTool

    regista_mcp = MCPStdioTool(name="regista", command=sys.executable, args=["-m", "regista.mcp_server"], env=child_env(),
                               allowed_tools=config.get("regista_tools"))
    tools = [await stack.enter_async_context(regista_mcp)]
    azure = (azure_mcp_tool(cloud, config.get("azure_namespaces"))
             if (cloud.cosmos_enabled or cloud.search_enabled) and config.get("azure_mcp", True) else None)
    context: list[str] = []
    if azure is not None:
        try:
            tools.append(await stack.enter_async_context(azure))
        except Exception:  # noqa: BLE001 - the Librarian still answers with Regista's own tools
            azure = None
    if azure is not None:
        _args, allowed = azure_mcp_args(cloud, config.get("azure_namespaces"))
        if cloud.cosmos_enabled and "cosmos_list" in allowed:
            context.append(f"cosmos account: {cosmos_account_name(cloud)}, database: {cloud.cosmos_database}")
        if cloud.search_enabled and "search_index_query" in allowed:
            context.append(f"search service: {search_service_name(cloud)}, index: regista-clips")
    held = list(config.get("regista_tools") or ["search_clips", "search_library", "derive_clips", "validate_stream", "render_clip", "list_matches"])
    if azure is not None:
        held += azure_mcp_args(cloud, config.get("azure_namespaces"))[1]
    context.append("tools you hold (offer nothing else): " + ", ".join(held))
    return tools, context


CHAT_INSTRUCTIONS = """You are Regista's Librarian in a conversation with a football producer who is building clips and reels.
Each user turn arrives with two notes from Regista: how it understood the whole conversation so far (player, moments,
angles, minutes), and the clips its search found for that, best first, with titles and minutes. Reply in at most two
sentences: say how many moments there are and name the best one or two by title and minute (once each); if the search
found nothing, say what is available instead (the note lists it). Say "moments", never "clips" or "clip(s)". Follow the conversation: "he", "his", "those" refer to what was
discussed. When the user asks beyond this match (other matches, every match, the library), search before you reply:
search_index_query on the Azure AI Search index regista-clips if you hold it, else search_library; then say what it found
there. Otherwise you may call your tools for detail the note lacks. Never invent clips,
players or moments that the notes or your tools did not give you. Never mention the notes themselves."""


async def foundry_chat_reply(cloud: CloudConfig, match_dir: str, history: list[dict[str, str]], message: str, understood: str,
                             results: list[Record], fallback: str, config: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """The conversational Librarian's reply from a Foundry model (Agent Framework), given the conversation so far,
    Regista's understanding of it, and the clips its search found. Returns (reply, tools called)."""
    from contextlib import AsyncExitStack

    from agent_framework import Agent, Message
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    found = "; ".join(pick(r) for r in results[:6]) or "none"
    note = (f"[Regista understood the conversation as: {understood}. Search results ({len(results)} shown): {found}. "
            f"If none: {fallback}. match_dir: {match_dir}]")
    async with DefaultAzureCredential() as credential, AsyncExitStack() as stack:
        client = FoundryChatClient(project_endpoint=cloud.foundry_project_endpoint, model=cloud.foundry_model, credential=credential)
        tools, context = await open_librarian_tools(stack, cloud, config or {})
        agent = await stack.enter_async_context(Agent(client=client, name="regista-librarian-chat", instructions=CHAT_INSTRUCTIONS))
        turns = [Message(t["role"], [t["text"]]) for t in history[-6:] if t.get("role") in ("user", "assistant") and t.get("text")]
        turns.append(Message("user", [f"{message}\n\n{note}\n" + "\n".join(context)]))
        result = await agent.run(turns, tools=tools)
        return getattr(result, "text", None) or str(result), tools_used(result)


# ---------------------------------------------------------------------------- the Scout agent (Scout view)

# read-only, public data: synthetic players only (never the Cosmos DB annotations, never render_clip)
SCOUT_TOOLS = ["search_players", "get_profile", "compare_players",
               "list_competitions", "search_catalogue_players", "get_catalogue_player"]

SCOUT_INSTRUCTIONS = """You are Regista's Scout agent. A football scout asks about players in the Regista League, a
synthetic league of 6 clubs and 10 rounds. Your tools (Regista MCP) read the season's profiles:
- search_players: filter (position GK/DF/MF/FW, club, name words) and rank by a stat per 90 or a ratio. Wingers and
  strikers are FW. "Finisher" means goals; "wins the ball back" means recoveries; "take-ons" means take_ons_won.
- get_profile: one player by global id or full name.
- compare_players: two or three players.
Always call a tool before answering. Answer in one to three plain sentences a scout would say, not a list of fields:
name the best one to three players with their club and the numbers exactly as the tools returned them, for example
"Haruki Fontaine (Eastwick United) wins the most take-ons among forwards, 2.5 per 90 (8 in 288 minutes), ahead of …".
Say "per 90" for per-90 values. Never invent players, stats or numbers. Use full names or surnames, never gendered pronouns. Each question comes with a note on how Regista's rules read
it: use it as a hint; if it reads the question wrongly, call the tools the way the question needs.
The catalogue: 14 synthetic competitions in 10 countries below the professional line (invented names; countries and
levels are labels). For a question about other countries, levels, age groups, women's football or "the catalogue" use
list_competitions, search_catalogue_players (filters tier, age_group, gender, country, competition, position; sort by a
Scout terminal metric key such as np_goals, take_ons_won, key_passes, interceptions) and get_catalogue_player. Its rules:
percentiles are within the player's own level by default; say the pool and its size as the tool gives it ("98th
percentile among 33 semi-pro men forwards"); when rows come from more than one level, say that each percentile is read
against its own pool; never put men and women in one pool or one ranking; a count of 0 is "none yet", never a rank;
a row with ranked false (below its minimum attempts, or none yet) is listed after the ranked rows and never leads: when
no row is ranked, say that no one is ranked (or has any) yet; a number marked noisy is a small sample. Quote only
numbers the tools returned."""


async def foundry_scout_answer(cloud: CloudConfig, question: str, understood: str, season_env: dict[str, str],
                               tools: list[str] | None = None) -> tuple[str, list[tuple[str, dict[str, Any]]]]:
    """The Scout agent's answer from a Foundry model (Agent Framework) with Regista's MCP server limited to the player
    tools. ``season_env`` points the server at the league (REGISTA_SEASON, REGISTA_SEASON_ROOT). Returns (answer, the
    tool calls it made with their arguments)."""
    from contextlib import AsyncExitStack

    from agent_framework import Agent, MCPStdioTool
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    allowed = list(tools or SCOUT_TOOLS)
    async with DefaultAzureCredential() as credential, AsyncExitStack() as stack:
        client = FoundryChatClient(project_endpoint=cloud.foundry_project_endpoint, model=cloud.foundry_model, credential=credential)
        regista_mcp = MCPStdioTool(name="regista", command=sys.executable, args=["-m", "regista.mcp_server"],
                                   env=child_env(season_env), allowed_tools=allowed)
        mcp = await stack.enter_async_context(regista_mcp)
        agent = await stack.enter_async_context(Agent(client=client, name="regista-scout", instructions=SCOUT_INSTRUCTIONS))
        prompt = (f"{question}\n\n[Regista's rules read this as: {understood}]\n"
                  f"tools you hold (offer nothing else): {', '.join(allowed)}")
        result = await agent.run(prompt, tools=[mcp])
        return getattr(result, "text", None) or str(result), tool_calls(result)


# ---------------------------------------------------------------------------- the Recap agent (match recaps)

async def foundry_recap_text(cloud: CloudConfig, prompt: str) -> str:
    """The Recap agent's recap as JSON text from a Foundry model (Agent Framework), written from the facts in ``prompt``
    (``regista.recap.model_prompt``). No tools: everything it may say is in the facts, and every sentence cites them."""
    from agent_framework import Agent
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    from regista.recap import RECAP_INSTRUCTIONS

    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(project_endpoint=cloud.foundry_project_endpoint, model=cloud.foundry_model, credential=credential)
        agent = Agent(client=client, name="regista-recap", instructions=RECAP_INSTRUCTIONS,
                      default_options={"response_format": {"type": "json_object"}})
        result = await agent.run(prompt)
        return getattr(result, "text", None) or str(result)


@dataclass
class FoundryRecapAgent(RecapAgent):
    """RecapAgent whose recap a Foundry model writes (``foundry_recap_text``), checked sentence by sentence; the rules
    recap is the fallback, and ``answered_by`` in recap.json says which wrote it."""

    description: str = ("Writes the match recap with a Microsoft Foundry model (Agent Framework) from the facts of the stream; every "
                        "sentence must cite a clip or an event and use only the facts' numbers; rules recap as the fallback.")
    engine: str = "foundry"
    cloud: CloudConfig | None = None

    def handle(self, state: State) -> State:
        if self.writer is None:
            cloud = self.cloud or CloudConfig.from_env()
            if cloud.foundry_enabled:
                def write(prompt: str) -> str:
                    return run_sync(foundry_recap_text(cloud, prompt))

                write.answered_by = f"foundry:{cloud.foundry_model}"  # type: ignore[attr-defined]
                self.writer = write
        return super().handle(state)
