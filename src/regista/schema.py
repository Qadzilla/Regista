"""Load the Regista JSON Schemas and validate JSON Lines streams against them.

Records are validated one line at a time by their ``type`` field, which keeps
validation of large ``tracks.jsonl`` files linear and gives line-numbered errors.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

Record = dict[str, Any]

SCHEMA_VERSION = "0.2.0"  # 0.2.0 (2026-10-23): the Regista League's events. New event type ``aerial_duel``; the generator
# now emits ``substitution``, ``penalty``, ``card_red`` and ``offside`` (already in the enum) in league mode; possession
# ``lost_by`` gains ``offside``; record type ``physical`` (one per player who played: his 10 Hz motion summarised,
# regista.synth.physical). Additive only: every 0.1.x record stays valid.
LEGACY_SCHEMA_VERSION = "0.1.1"  # the stamp of a stream that uses nothing added in 0.2.0. The generator without league
# attributes keeps writing it, so the committed samples and the vision layer's seeds stay byte-identical.
# 0.1.1: annotation.context (additive). Since 2026-10-22 the match record also accepts the optional season fields
# teams[].club_id and players[].global_player_id (regista.season); optional and additive, so the version was not bumped.
# The schemas ship inside the package so validation works from any install, not only a repo checkout.
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
EVENTS_SCHEMA = SCHEMA_DIR / "regista-events.schema.json"
CLIPS_SCHEMA = SCHEMA_DIR / "regista-clips.schema.json"

# Which schema validates which record type.
EVENT_TYPES = ("match", "camera_segment", "track", "appearance", "possession", "event", "annotation", "physical")
CLIP_TYPES = ("clip", "label")


@lru_cache(maxsize=None)
def load_schema(path: Path | str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class RecordValidator:
    """Validates records by dispatching on ``type`` to the matching ``$defs`` entry."""

    def __init__(self, schema_path: Path | str):
        self.schema_path = Path(schema_path)
        self.schema = load_schema(self.schema_path)
        self._by_type: dict[str, Draft202012Validator] = {}
        for name, sub in self.schema["$defs"].items():
            const = sub.get("properties", {}).get("type", {}).get("const")
            if const is None:
                continue
            wrapped = {
                "$schema": self.schema["$schema"],
                "$defs": self.schema["$defs"],
                "$ref": f"#/$defs/{name}",
            }
            self._by_type[const] = Draft202012Validator(wrapped, format_checker=FormatChecker())

    @property
    def types(self) -> tuple[str, ...]:
        return tuple(self._by_type)

    def errors(self, record: Record) -> list[str]:
        rtype = record.get("type")
        validator = self._by_type.get(rtype)
        if validator is None:
            return [f"unknown record type {rtype!r} (expected one of {', '.join(self.types)})"]
        out = []
        for err in validator.iter_errors(record):
            where = "/".join(str(p) for p in err.absolute_path) or "<root>"
            out.append(f"{where}: {err.message}")
        return out

    def is_valid(self, record: Record) -> bool:
        return not self.errors(record)


@lru_cache(maxsize=None)
def events_validator() -> RecordValidator:
    return RecordValidator(EVENTS_SCHEMA)


@lru_cache(maxsize=None)
def clips_validator() -> RecordValidator:
    return RecordValidator(CLIPS_SCHEMA)


def validator_for(record: Record) -> RecordValidator:
    return clips_validator() if record.get("type") in CLIP_TYPES else events_validator()


def iter_jsonl(path: Path | str) -> Iterator[Record]:
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: Path | str, records: Iterable[Record]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":"), ensure_ascii=False))
            fh.write("\n")
            n += 1
    return n


def validate_jsonl(path: Path | str, validator: RecordValidator | None = None) -> list[str]:
    """Return a list of ``line N: message`` strings. Empty means the file is valid."""
    problems: list[str] = []
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(f"line {lineno}: invalid JSON ({exc.msg})")
                continue
            v = validator or validator_for(record)
            for msg in v.errors(record):
                problems.append(f"line {lineno}: {msg}")
    return problems


def validate_match_dir(match_dir: Path | str) -> dict[str, list[str]]:
    """Validate every known JSONL file in a sample match directory."""
    match_dir = Path(match_dir)
    results: dict[str, list[str]] = {}
    for name, validator in (
        ("events.jsonl", events_validator()),
        ("tracks.jsonl", events_validator()),
        ("clips.jsonl", clips_validator()),
    ):
        path = match_dir / name
        if path.exists():
            results[name] = validate_jsonl(path, validator)
    if not results:
        raise FileNotFoundError(f"no events.jsonl, tracks.jsonl or clips.jsonl under {match_dir}")
    return results
