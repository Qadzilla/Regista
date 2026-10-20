"""The six roles from CLAUDE.md §3.1 as they exist today (rule-based v0).

Ingest reads the stream and indexes it. Validator checks it against the schema. Possession
finds the on-ball windows per player. Clip applies the clip rule. Label tags, titles, scores
and explains. Librarian answers questions over the labels. Identity (the vision-layer role
that tracks a player through the footage) is not here: it lives in the private vision layer,
and the synthetic generator plays its part for the demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from regista.agents.base import Agent, AgentError, State
from regista.clips import StreamIndex, cut_clips, label_clips
from regista.librarian import search_clips
from regista.schema import iter_jsonl, validate_match_dir, write_jsonl


@dataclass
class IngestAgent(Agent):
    role: str = "ingest"
    inputs: tuple[str, ...] = ("match_dir",)
    outputs: tuple[str, ...] = ("stream", "index", "match", "record_counts")
    description: str = "Reads events.jsonl, keeps the match header, indexes segments, possessions, events, appearances."

    def handle(self, state: State) -> State:
        path = Path(state["match_dir"]) / "events.jsonl"
        if not path.exists():
            raise AgentError(f"{path} does not exist", retryable=False)
        stream = list(iter_jsonl(path))
        index = StreamIndex.build(stream)
        counts: dict[str, int] = {}
        for r in stream:
            counts[r["type"]] = counts.get(r["type"], 0) + 1
        state.update(stream=stream, index=index, match=index.match, record_counts=counts)
        return state


@dataclass
class ValidatorAgent(Agent):
    role: str = "validator"
    inputs: tuple[str, ...] = ("match_dir",)
    outputs: tuple[str, ...] = ("validation",)
    description: str = "Validates every JSONL file in the match directory against the schemas; blocks on invalid events."

    def handle(self, state: State) -> State:
        problems = validate_match_dir(Path(state["match_dir"]))
        state["validation"] = {k: len(v) for k, v in problems.items()}
        if problems.get("events.jsonl"):
            raise AgentError(f"events.jsonl has {len(problems['events.jsonl'])} schema problem(s): {problems['events.jsonl'][0]}", retryable=False)
        return state


@dataclass
class PossessionAgent(Agent):
    role: str = "possession"
    inputs: tuple[str, ...] = ("index", "player_ids")
    outputs: tuple[str, ...] = ("on_ball",)
    description: str = "For each requested player, the windows in which they had the ball, with the camera segment each falls in."

    def handle(self, state: State) -> State:
        index: StreamIndex = state["index"]
        on_ball: dict[str, list[dict[str, Any]]] = {}
        for pid in state["player_ids"]:
            if pid not in index.roster:
                raise AgentError(f"{pid} is not in the roster", retryable=False)
            rows = []
            for pos in index.possessions:
                if pos["player_id"] != pid:
                    continue
                seg = index.segment_at(pos["t"])
                rows.append({"possession_id": pos["id"], "t": pos["t"], "t_end": pos["t_end"], "segment_id": seg["id"] if seg else None,
                             "segment_kind": seg["kind"] if seg else None, "touches": pos["touches"], "under_pressure": pos.get("under_pressure", False)})
            on_ball[pid] = rows
        state["on_ball"] = on_ball
        return state


@dataclass
class ClipAgent(Agent):
    role: str = "clip"
    inputs: tuple[str, ...] = ("index", "player_ids", "on_ball")
    outputs: tuple[str, ...] = ("clips",)
    description: str = "Applies the clip rule: on-ball main-view windows plus every replay, highlight, and closeup appearance."

    def handle(self, state: State) -> State:
        index: StreamIndex = state["index"]
        clips: dict[str, list[dict[str, Any]]] = {}
        for pid in state["player_ids"]:
            clips[pid] = cut_clips(index, pid, pre_roll_s=self.config.get("pre_roll_s", 2.0), post_roll_s=self.config.get("post_roll_s", 2.0))
        state["clips"] = clips
        return state


@dataclass
class LabelAgent(Agent):
    role: str = "label"
    inputs: tuple[str, ...] = ("index", "clips")
    outputs: tuple[str, ...] = ("labels",)
    description: str = "Tags, titles, scores (watchability) and explains each clip. rules-v0 today; Foundry model later."

    def handle(self, state: State) -> State:
        index: StreamIndex = state["index"]
        labels: dict[str, list[dict[str, Any]]] = {}
        for pid, clips in state["clips"].items():
            labels[pid] = label_clips(index, clips, model=self.config.get("model", "rules-v0"))
        state["labels"] = labels
        return state


@dataclass
class PersistAgent(Agent):
    role: str = "persist"
    inputs: tuple[str, ...] = ("match_dir", "clips", "labels")
    outputs: tuple[str, ...] = ("clips_path",)
    description: str = "Writes clips.jsonl next to the match so the Librarian and the renderer can read it."

    def handle(self, state: State) -> State:
        rows: list[dict[str, Any]] = []
        for pid in state["clips"]:
            rows += state["clips"][pid] + state["labels"].get(pid, [])
        path = Path(state["match_dir"]) / self.config.get("filename", "clips.jsonl")
        write_jsonl(path, rows)
        state["clips_path"] = str(path)
        return state


@dataclass
class LibrarianAgent(Agent):
    role: str = "librarian"
    inputs: tuple[str, ...] = ("clips_path", "queries")
    outputs: tuple[str, ...] = ("answers",)
    description: str = "Answers plain-English questions over the labelled clips, with how each query was understood."

    def handle(self, state: State) -> State:
        from regista import librarian as lib

        lib._load.cache_clear()  # clips.jsonl may have just been rewritten by the Persist agent
        answers = [search_clips(state["match_dir"], q, self.config.get("limit", 10)) for q in state["queries"]]
        state["answers"] = answers
        return state


def default_agents() -> list[Agent]:
    return [IngestAgent(), ValidatorAgent(), PossessionAgent(), ClipAgent(), LabelAgent(), PersistAgent(), LibrarianAgent()]
