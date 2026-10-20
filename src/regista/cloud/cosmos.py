"""Azure Cosmos DB behind the Persist agent: match, clip, and label documents, partitioned by match_id.

Containers (created by infra/provision.sh): ``matches``, ``clips``, ``labels``, each with partition
key ``/match_id``. Documents are the stream records with an added ``id`` that Cosmos requires.
Keyless by default (``DefaultAzureCredential``, needs the "Cosmos DB Built-in Data Contributor"
role); ``REGISTA_COSMOS_KEY`` is honoured when set.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from regista.agents.base import AgentError, State
from regista.agents.roles import PersistAgent
from regista.cloud.config import CloudConfig

Record = dict[str, Any]


class ContainerLike(Protocol):  # the slice of azure.cosmos ContainerProxy we use; tests pass a fake
    def upsert_item(self, body: dict[str, Any]) -> Any: ...
    def query_items(self, query: str, parameters: list[dict[str, Any]] | None = None, enable_cross_partition_query: bool = False) -> Any: ...


class ClipStore:
    """Thin wrapper over the three containers."""

    def __init__(self, matches: ContainerLike, clips: ContainerLike, labels: ContainerLike, annotations: ContainerLike | None = None):
        self.matches, self.clips, self.labels, self.annotations = matches, clips, labels, annotations

    @classmethod
    def connect(cls, config: CloudConfig) -> ClipStore:
        from azure.cosmos import CosmosClient

        if not config.cosmos_enabled:
            raise AgentError("Cosmos DB is not configured (REGISTA_COSMOS_ENDPOINT)", retryable=False)
        if config.cosmos_key:
            client = CosmosClient(config.cosmos_endpoint, credential=config.cosmos_key)
        else:
            from azure.identity import DefaultAzureCredential

            client = CosmosClient(config.cosmos_endpoint, credential=DefaultAzureCredential())
        db = client.get_database_client(config.cosmos_database)
        return cls(db.get_container_client("matches"), db.get_container_client("clips"), db.get_container_client("labels"),
                   db.get_container_client("annotations"))

    @staticmethod
    def _doc(record: Record) -> Record:
        return {**record, "id": record["id"] if record["type"] != "match" else record["match_id"]}

    def write_match(self, match: Record) -> None:
        self.matches.upsert_item(self._doc(match))

    def write_clips(self, clips: list[Record], labels: list[Record]) -> int:
        n = 0
        for c in clips:
            self.clips.upsert_item(self._doc(c))
            n += 1
        for lb in labels:
            self.labels.upsert_item(self._doc(lb))
            n += 1
        return n

    # -- human feedback: verdicts and the learned model survive container restarts here
    MODEL_ID = "watchability-model"
    MODEL_PARTITION = "_feedback"

    def write_annotation(self, annotation: Record) -> None:
        if self.annotations is None:
            raise AgentError("no annotations container configured", retryable=False)
        # Annotation ids are unique (time + random suffix), so they double as the document id; upserts are idempotent.
        doc = {**annotation, "annotation_id": annotation["id"], "id": annotation["id"]}
        self.annotations.upsert_item(doc)

    def all_annotations(self) -> list[Record]:
        if self.annotations is None:
            return []
        rows = self.annotations.query_items("SELECT * FROM c WHERE c.type = 'annotation'", enable_cross_partition_query=True)
        out = []
        for r in rows:
            clean = {k: v for k, v in r.items() if not k.startswith("_")}
            clean["id"] = clean.pop("annotation_id", clean["id"])
            out.append(clean)
        return sorted(out, key=lambda a: a.get("annotated_at", ""))

    def save_model(self, model_json: Record) -> None:
        if self.annotations is not None:
            self.annotations.upsert_item({**model_json, "id": self.MODEL_ID, "match_id": self.MODEL_PARTITION, "type": "model"})

    def load_model(self) -> Record | None:
        if self.annotations is None:
            return None
        rows = list(self.annotations.query_items("SELECT * FROM c WHERE c.id = @id",
                                                 parameters=[{"name": "@id", "value": self.MODEL_ID}], enable_cross_partition_query=True))
        if not rows:
            return None
        return {k: v for k, v in rows[0].items() if not k.startswith("_") and k not in ("id", "match_id", "type")}

    def clips_for(self, match_id: str, player_id: str | None = None) -> tuple[list[Record], dict[str, Record]]:
        q = "SELECT * FROM c WHERE c.match_id = @m" + (" AND c.player_id = @p" if player_id else "")
        params = [{"name": "@m", "value": match_id}] + ([{"name": "@p", "value": player_id}] if player_id else [])
        clips = list(self.clips.query_items(q, parameters=params))
        labels = {lb["clip_id"]: lb for lb in self.labels.query_items(q, parameters=params)}
        return clips, labels


@dataclass
class CosmosPersistAgent(PersistAgent):
    """PersistAgent that writes clips.jsonl (as before) and upserts everything into Cosmos DB."""

    description: str = "Writes clips.jsonl and upserts match, clip, and label documents into Azure Cosmos DB (partition match_id)."
    config: dict[str, Any] = field(default_factory=dict)
    cloud: CloudConfig | None = None
    store: ClipStore | None = None  # injectable for tests
    outputs: tuple[str, ...] = ("clips_path", "cosmos")

    def handle(self, state: State) -> State:
        state = super().handle(state)
        store = self.store or ClipStore.connect(self.cloud or CloudConfig.from_env())
        store.write_match(state["match"])
        written = 1
        for pid, clips in state["clips"].items():
            written += store.write_clips(clips, state["labels"].get(pid, []))
        state["cosmos"] = {"documents": written, "match_id": state["match"]["match_id"]}
        return state
