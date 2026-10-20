"""Test doubles for Azure clients. Nothing here touches the network."""

from __future__ import annotations

from typing import Any


class FakeContainer:
    """The slice of azure.cosmos ContainerProxy that ClipStore uses, interpreting its few query shapes."""

    def __init__(self, items: list[dict[str, Any]] | None = None):
        self.items: dict[str, dict[str, Any]] = {}
        self.queries: list[dict[str, Any]] = []
        for it in items or []:
            self.upsert_item(it)

    def upsert_item(self, body):
        assert "id" in body and "match_id" in body
        self.items[body["id"]] = body

    def query_items(self, query, parameters=None, enable_cross_partition_query=False, partition_key=None):
        want = {p["name"]: p["value"] for p in (parameters or [])}
        self.queries.append({"query": query, "params": want, "cross": enable_cross_partition_query, "partition_key": partition_key})
        if partition_key is None and not enable_cross_partition_query:
            raise AssertionError(f"query needs a partition key or cross-partition flag: {query}")
        for it in list(self.items.values()):
            if "@m" in want and it["match_id"] != want["@m"]:
                continue
            if partition_key is not None and it["match_id"] != partition_key:
                continue
            if "@p" in want and it.get("player_id") != want["@p"]:
                continue
            if "@id" in want and it.get("id") != want["@id"]:
                continue
            for t in ("match", "annotation"):
                if f"c.type = '{t}'" in query and it.get("type") != t:
                    break
            else:
                yield {**it, "_rid": "x", "_ts": 1}
