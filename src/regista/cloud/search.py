"""Azure AI Search behind the Librarian: one index of every labelled clip, across every match.

The local Librarian (``regista.librarian``) answers questions about one match from its files. The
index answers the questions a studio actually asks, across the whole library: "every nutmeg by
the home 9 this season", "the most watchable replays from the last three matches". The Index agent
writes to it after Persist; the Regista MCP server exposes it as ``search_library``; the Foundry
Librarian can also reach it through the Azure MCP Server's ``search_index_query`` tool.

Keyless: DefaultAzureCredential with "Search Service Contributor" (create the index) and
"Search Index Data Contributor" (write and query). Configure with REGISTA_SEARCH_ENDPOINT.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from regista.agents.base import Agent, AgentError, State
from regista.clips import match_minute

Record = dict[str, Any]
INDEX_NAME = "regista-clips"


def search_endpoint() -> str | None:
    from regista.cloud.config import load_dotenv

    dotenv = os.environ.get("REGISTA_DOTENV", ".env")
    if dotenv:
        load_dotenv(dotenv)
    return os.environ.get("REGISTA_SEARCH_ENDPOINT") or None


def doc_key(match_id: str, clip_id: str) -> str:
    """Search keys allow letters, digits, _, - and = only."""
    return re.sub(r"[^A-Za-z0-9_\-=]", "-", f"{match_id}--{clip_id}")


def to_document(match: Record, clip: Record, label: Record) -> Record:
    player = next((p for p in match["players"] if p["player_id"] == clip["player_id"]), {})
    team = next((t for t in match["teams"] if t["team_id"] == player.get("team_id")), {})
    return {
        "id": doc_key(match["match_id"], clip["id"]),
        "match_id": match["match_id"], "clip_id": clip["id"], "player_id": clip["player_id"],
        "player_name": player.get("name", ""), "kit_number": int(player.get("kit_number", 0)), "team": team.get("name", ""),
        "team_id": team.get("team_id", ""), "team_short": team.get("short_name", ""), "position": player.get("position", ""),
        "home": team.get("team_id") == match.get("home_team_id"),
        "title": label.get("title", ""), "summary": label.get("summary", ""), "explanation": label.get("explanation", ""),
        "tags": list(label.get("tags", [])), "reason": clip["reason"], "watchability": float(label.get("watchability", 0.0)),
        "minute": match_minute(match, clip.get("keyframe_t", clip["t"])), "t": float(clip["t"]), "t_end": float(clip["t_end"]),
        "model": label.get("model", ""),
    }


def index_definition():
    from azure.search.documents.indexes.models import SearchableField, SearchFieldDataType as T, SearchIndex, SimpleField

    return SearchIndex(name=INDEX_NAME, fields=[
        SimpleField(name="id", type=T.STRING, key=True),
        SimpleField(name="match_id", type=T.STRING, filterable=True, facetable=True),
        SimpleField(name="clip_id", type=T.STRING, filterable=True),
        SimpleField(name="player_id", type=T.STRING, filterable=True, facetable=True),
        SearchableField(name="player_name", filterable=True),
        SimpleField(name="kit_number", type=T.INT32, filterable=True),
        SearchableField(name="team", filterable=True, facetable=True),
        SimpleField(name="team_id", type=T.STRING, filterable=True), SimpleField(name="team_short", type=T.STRING, filterable=True),
        SimpleField(name="position", type=T.STRING, filterable=True), SimpleField(name="home", type=T.BOOLEAN, filterable=True),
        SearchableField(name="title"), SearchableField(name="summary"), SearchableField(name="explanation"),
        SearchableField(name="tags", collection=True, filterable=True, facetable=True),
        SimpleField(name="reason", type=T.STRING, filterable=True, facetable=True),
        SimpleField(name="watchability", type=T.DOUBLE, filterable=True, sortable=True),
        SimpleField(name="minute", type=T.INT32, filterable=True, sortable=True),
        SimpleField(name="t", type=T.DOUBLE), SimpleField(name="t_end", type=T.DOUBLE),
        SimpleField(name="model", type=T.STRING, filterable=True, facetable=True),
    ])


class ClipIndex:
    """The clip index. ``index_client``/``search_client`` are injectable so tests run without Azure."""

    def __init__(self, endpoint: str | None = None, *, index_client: Any = None, search_client: Any = None):
        self.endpoint = endpoint or search_endpoint()
        if index_client is None or search_client is None:
            if not self.endpoint:
                raise AgentError("Azure AI Search is not configured (REGISTA_SEARCH_ENDPOINT)", retryable=False)
            from azure.identity import DefaultAzureCredential
            from azure.search.documents import SearchClient
            from azure.search.documents.indexes import SearchIndexClient

            cred = DefaultAzureCredential()
            index_client = index_client or SearchIndexClient(self.endpoint, cred)
            search_client = search_client or SearchClient(self.endpoint, INDEX_NAME, cred)
        self.index_client, self.search_client = index_client, search_client

    def ensure_index(self) -> None:
        self.index_client.create_or_update_index(index_definition())

    def upload(self, documents: list[Record]) -> int:
        ok = 0
        for i in range(0, len(documents), 1000):
            results = self.search_client.merge_or_upload_documents(documents[i:i + 1000])
            ok += sum(1 for r in results if getattr(r, "succeeded", True))
        return ok

    def search(self, text: str = "*", *, player_id: str | None = None, tags: list[str] | None = None, match_id: str | None = None,
               reason: str | None = None, min_watchability: float | None = None, minutes: tuple[int, int] | None = None,
               top: int = 10) -> list[Record]:
        filters = []
        if player_id:
            filters.append(f"player_id eq '{_quote(player_id)}'")
        if match_id:
            filters.append(f"match_id eq '{_quote(match_id)}'")
        if reason:
            filters.append(f"reason eq '{_quote(reason)}'")
        for t in tags or []:
            filters.append(f"tags/any(x: x eq '{_quote(t)}')")
        if min_watchability is not None:
            filters.append(f"watchability ge {float(min_watchability)}")
        if minutes:
            filters.append(f"minute ge {int(minutes[0])} and minute le {int(minutes[1])}")
        results = self.search_client.search(search_text=text or "*", filter=" and ".join(filters) or None,
                                            order_by=["watchability desc", "minute asc"], top=top)
        return [{k: v for k, v in dict(r).items() if not k.startswith("@")} for r in results]


def _quote(value: str) -> str:
    return str(value).replace("'", "''")


def search_library(query: str, *, top: int = 10, index: ClipIndex | None = None, match: Record | None = None) -> dict[str, Any]:
    """Plain-English search across every indexed match: the Librarian's parser turns the query into filters."""
    from regista.librarian import parse_query

    index = index or ClipIndex()
    roster_match = match or _any_indexed_roster(index)
    parsed = parse_query(query, roster_match) if roster_match else {"player_ids": [], "tags": [], "reasons": [], "minutes": None, "limit": None}
    player = parsed["player_ids"][0] if len(parsed.get("player_ids", [])) == 1 else None
    reason = parsed["reasons"][0] if parsed.get("reasons") else None
    rows = index.search("*", player_id=player, tags=parsed.get("tags") or None, reason=reason,
                        minutes=tuple(parsed["minutes"]) if parsed.get("minutes") else None, top=parsed.get("limit") or top)
    if not rows and parsed.get("tags"):
        rows = index.search(" ".join(parsed["tags"]), player_id=player, top=parsed.get("limit") or top)  # relax to text match
    return {"parsed": parsed, "results": rows, "backend": "azure-ai-search", "index": INDEX_NAME}


def _any_indexed_roster(index: ClipIndex) -> Record | None:
    """The parser needs a roster to resolve names; build one from the players present in the index."""
    rows = index.search("*", top=1000)
    if not rows:
        return None
    players, teams, home, away = {}, {}, None, None
    for r in rows:
        players[r["player_id"]] = {"player_id": r["player_id"], "name": r["player_name"], "kit_number": r["kit_number"],
                                   "team_id": r["team_id"], "position": r.get("position") or "MF", "starter": True}
        teams[r["team_id"]] = {"team_id": r["team_id"], "name": r["team"], "short_name": r.get("team_short") or r["team"][:3].upper()}
        if r.get("home"):
            home = r["team_id"]
        else:
            away = r["team_id"]
    ids = list(teams)
    home = home or ids[0]
    away = away or ids[-1]
    return {"players": list(players.values()), "teams": list(teams.values()), "home_team_id": home, "away_team_id": away,
            "periods": [{"period": 1, "t": 0.0, "t_end": 5400.0, "left_to_right_team_id": home}]}


@dataclass
class SearchIndexAgent(Agent):
    """After Persist: writes every clip and label into the Azure AI Search index, so the library is searchable across matches."""

    role: str = "indexer"
    inputs: tuple[str, ...] = ("match", "clips", "labels")
    outputs: tuple[str, ...] = ("search_index",)
    description: str = "Indexes every labelled clip in Azure AI Search (index regista-clips) for cross-match search."
    config: dict[str, Any] = field(default_factory=dict)
    clip_index: ClipIndex | None = None  # injectable for tests

    def handle(self, state: State) -> State:
        index = self.clip_index or ClipIndex()
        index.ensure_index()
        docs = []
        for pid, clips in state["clips"].items():
            labels = {lb["clip_id"]: lb for lb in state["labels"].get(pid, [])}
            docs += [to_document(state["match"], c, labels[c["id"]]) for c in clips if c["id"] in labels]
        state["search_index"] = {"index": INDEX_NAME, "documents": index.upload(docs), "match_id": state["match"]["match_id"]}
        return state
