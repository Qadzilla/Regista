"""Claims: "that's me". A person links a player in an uploaded match to one of the league's synthetic players.

An uploaded match (the vision layer's output, through the token-gated upload) has its usual per-match ids
(``t_home_09``) and no global ids. A claim says "in match M, player ``t_home_09`` is ``pl_bro_09``"; the operator
confirms or rejects it in the Studio, and a confirmed claim adds that match to the player's profile
(``regista.season.profiles``), with the match's ``player_id`` mapped to the claimed global id.

Both the claim and each decision are human ``annotation`` records (``source: human``), appended to
``claims.jsonl`` in the feedback folder (``$REGISTA_FEEDBACK_DIR``) and never edited, so the history stays:

- the claim: ``target_type: track``, ``target_id`` the match's player id (the identity the vision layer's tracks were
  named as), ``verdict: correct``, ``correction: {global_id}``, ``context.kind: identity_claim`` with a snapshot of the
  roster entry and the league player, so the Studio can show a kit-number mismatch without reopening the match;
- a decision: the same target, ``verdict: confirm`` or ``reject``, ``context: {kind: identity_claim_decision, claim_id}``.

A claim's status is its newest decision (``confirmed``, ``rejected``), else ``pending``; the operator may change their
mind. Only synthetic league players can be claimed: there are no real players' profiles.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from regista.feedback import ANNOTATOR_RE, feedback_dir, new_annotation_id
from regista.schema import SCHEMA_VERSION, events_validator, iter_jsonl

Record = dict[str, Any]

CLAIMS_FILE = "claims.jsonl"
CLAIM, DECISION = "identity_claim", "identity_claim_decision"
KINDS = (CLAIM, DECISION)
STATUS = {"confirm": "confirmed", "reject": "rejected"}
CLAIM_ID_RE = re.compile(r"^an_[0-9]{20}_[0-9a-f]{6}$")
MAX_NOTE = 300
_write_lock = threading.Lock()


class ClaimError(ValueError):
    """A claim or decision that cannot be recorded; ``status`` is the HTTP status the API answers with."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def claims_path() -> Path:
    return feedback_dir() / CLAIMS_FILE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _check(rec: Record) -> Record:
    problems = events_validator().errors(rec)
    if problems:
        raise ClaimError(f"invalid annotation: {problems[0]}")
    return rec


def _append(rec: Record, path: Path | None) -> Record:
    path = Path(path) if path else claims_path()
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _clean(text: str, name: str) -> str:
    if not isinstance(text, str) or len(text) > MAX_NOTE:
        raise ClaimError(f"{name} must be text of at most {MAX_NOTE} characters")
    return text.strip()


def records(path: Path | str | None = None) -> list[Record]:
    """Every claim and decision record, oldest first."""
    path = Path(path) if path else claims_path()
    if not path.exists():
        return []
    rows = [r for r in iter_jsonl(path) if r.get("type") == "annotation" and (r.get("context") or {}).get("kind") in KINDS]
    return sorted(rows, key=lambda r: (r.get("annotated_at", ""), r["id"]))


def merge(local: list[Record], remote: list[Record], path: Path | str | None = None) -> list[Record]:
    """Union local and remote (Cosmos DB) records by id and write the result; returns the local rows remote lacks."""
    remote = [r for r in remote if (r.get("context") or {}).get("kind") in KINDS]
    have = {r["id"] for r in remote}
    local_only = [r for r in local if r["id"] not in have]
    merged = {r["id"]: r for r in remote} | {r["id"]: r for r in local_only}
    rows = sorted(merged.values(), key=lambda r: (r.get("annotated_at", ""), r["id"]))
    path = Path(path) if path else claims_path()
    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(path)
    return local_only


def fold(rows: list[Record]) -> list[Record]:
    """The claims as people read them, newest first: who claimed which player, its status, and the last decision."""
    out: dict[str, Record] = {}
    for r in rows:
        ctx = r["context"]
        if ctx["kind"] == CLAIM:
            out[r["id"]] = {"claim_id": r["id"], "match_id": r["match_id"], "player_id": r["target_id"],
                            "global_id": r["correction"]["global_id"], "status": "pending", "claimant": r["annotator"],
                            "claimed_at": r["annotated_at"], "note": r.get("note", ""), "player": ctx.get("player", {}),
                            "person": ctx.get("person", {}), "kit_matches": ctx.get("kit_matches"), "decision": None,
                            "history": []}
    for r in rows:
        ctx = r["context"]
        c = out.get(ctx.get("claim_id", "")) if ctx["kind"] == DECISION else None
        if c is None:
            continue
        if r.get("verdict") not in STATUS:
            continue
        d = {"decision": STATUS[r["verdict"]], "by": r["annotator"],
             "at": r["annotated_at"], "note": r.get("note", ""), "annotation_id": r["id"]}
        c["history"].append(d)
        c["decision"], c["status"] = d, d["decision"]
    return sorted(out.values(), key=lambda c: (c["claimed_at"], c["claim_id"]), reverse=True)


def all_claims(path: Path | str | None = None) -> list[Record]:
    return fold(records(path))


def get(claim_id: str, path: Path | str | None = None) -> Record | None:
    return next((c for c in all_claims(path) if c["claim_id"] == claim_id), None)


def confirmed(path: Path | str | None = None, match_id: str | None = None) -> list[Record]:
    return [c for c in all_claims(path) if c["status"] == "confirmed" and (match_id is None or c["match_id"] == match_id)]


def _conflict(claims: list[Record], match_id: str, player_id: str, global_id: str, *, statuses: tuple[str, ...],
              skip: str | None = None) -> Record | None:
    for c in claims:
        if c["claim_id"] == skip or c["match_id"] != match_id or c["status"] not in statuses:
            continue
        if c["player_id"] == player_id or c["global_id"] == global_id:
            return c
    return None


def new_claim(header: Record, player_id: str, person: Record, *, claimant: str = "claimant", note: str = "",
              path: Path | str | None = None) -> Record:
    """Record a pending claim that ``player_id`` in the match ``header`` describes is the league player ``person``
    (``regista.season.league.people`` entry). Refuses a second open or confirmed claim on the same player or for the
    same person in one match (409)."""
    if not isinstance(claimant, str) or not ANNOTATOR_RE.match(claimant):
        raise ClaimError("claimant must be 1-40 letters, digits, spaces, dots, dashes or underscores")
    note = _clean(note, "note")
    roster = {p["player_id"]: p for p in header.get("players", [])}
    p = roster.get(player_id)
    if p is None:
        raise ClaimError(f"{player_id} is not on match {header['match_id']}'s team sheet")
    if any(x.get("global_player_id") for x in roster.values()):
        raise ClaimError("this match's team sheet already carries global player ids: it needs no claims")
    clash = _conflict(all_claims(path), header["match_id"], player_id, person["global_id"], statuses=("pending", "confirmed"))
    if clash:
        raise ClaimError(f"claim {clash['claim_id']} ({clash['status']}) already links {clash['player_id']} or {clash['global_id']} "
                         f"in match {header['match_id']}", status=409)
    team = next((t for t in header.get("teams", []) if t["team_id"] == p["team_id"]), {})
    rec: Record = {
        "type": "annotation", "id": new_annotation_id(), "match_id": header["match_id"], "schema_version": SCHEMA_VERSION,
        "source": "human", "confidence": 1, "t": 0.0, "target_id": player_id, "target_type": "track", "verdict": "correct",
        "correction": {"global_id": person["global_id"]}, "annotator": claimant, "annotated_at": _now(),
        "context": {"kind": CLAIM,
                    "player": {"player_id": player_id, "name": p.get("name"), "kit_number": p.get("kit_number"),
                               "team_id": p["team_id"], "team": team.get("name"), "team_short": team.get("short_name")},
                    "person": {"global_id": person["global_id"], "name": person["name"], "kit_number": person["kit_number"],
                               "club_id": person["club_id"], "club": person["club"], "position": person["position"]},
                    "kit_matches": p.get("kit_number") == person["kit_number"]},
    }
    if note:
        rec["note"] = note
    return _append(_check(rec), path)


def decide(claim_id: str, decision: str, *, annotator: str = "zaid", note: str = "", path: Path | str | None = None) -> Record:
    """Confirm or reject a claim (the newest decision wins). A confirm that would give one match's player two people,
    or one person two players in a match, is refused (409)."""
    if decision not in STATUS:
        raise ClaimError("decision must be confirm or reject")
    if not isinstance(annotator, str) or not ANNOTATOR_RE.match(annotator):
        raise ClaimError("annotator must be 1-40 letters, digits, spaces, dots, dashes or underscores")
    note = _clean(note, "note")
    claims = all_claims(path)
    c = next((x for x in claims if x["claim_id"] == claim_id), None)
    if c is None:
        raise ClaimError(f"no claim {claim_id}", status=404)
    if decision == "confirm":
        clash = _conflict(claims, c["match_id"], c["player_id"], c["global_id"], statuses=("confirmed",), skip=claim_id)
        if clash:
            raise ClaimError(f"claim {clash['claim_id']} is already confirmed for {clash['player_id']} / {clash['global_id']} "
                             f"in match {c['match_id']}: reject it first", status=409)
    rec: Record = {
        "type": "annotation", "id": new_annotation_id(), "match_id": c["match_id"], "schema_version": SCHEMA_VERSION,
        "source": "human", "confidence": 1, "t": 0.0, "target_id": c["player_id"], "target_type": "track", "verdict": decision,
        "correction": {"global_id": c["global_id"]}, "annotator": annotator, "annotated_at": _now(),
        "context": {"kind": DECISION, "claim_id": claim_id},
    }
    if note:
        rec["note"] = note
    return _append(_check(rec), path)


# ---------------------------------------------------------------------------- what profiles read

def claimed_matches(data_root: Path | str, path: Path | str | None = None) -> list[Record]:
    """Confirmed claims whose match is on this replica: {match_id, match_dir, player_id, global_id, claim_id}, one per
    (match, player). A match only Cosmos DB still holds has no event stream here, so it cannot count yet."""
    out, seen = [], set()
    for c in sorted(confirmed(path), key=lambda c: (c["match_id"], c["claimed_at"])):
        d = Path(data_root) / c["match_id"]
        key = (c["match_id"], c["player_id"])
        if key in seen or not (d / "events.jsonl").exists():
            continue
        seen.add(key)
        out.append({"match_id": c["match_id"], "match_dir": str(d), "player_id": c["player_id"], "global_id": c["global_id"],
                    "claim_id": c["claim_id"]})
    return out


def fingerprint(extra: list[Record]) -> str:
    """Changes when a confirmed claim is added or withdrawn, or a claimed match's event stream changes."""
    parts = []
    for e in extra:
        ev = Path(e["match_dir"]) / "events.jsonl"
        parts.append([e["match_id"], e["player_id"], e["global_id"], ev.stat().st_mtime_ns if ev.exists() else 0])
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:16]
