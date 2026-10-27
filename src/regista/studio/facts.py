"""Read-only facts about this replica for the Studio: pipeline runs, the to-do list, the render cache, and document counts.

Nothing here writes or raises for a missing or malformed file: a match with no run says so, a bad line in a trace is
skipped, and a Cosmos DB or Search failure comes back as an error string. ``regista.api`` is imported inside functions
because it imports this package's router at the end of its own import.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COSMOS_CONTAINERS = ("matches", "clips", "labels", "annotations")
DATA_TTL_S = 60.0


def _iso(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if t else None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    """Rows of a JSONL file; a missing file is empty and a line that does not parse is skipped."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _n(n: int, word: str) -> str:
    """``1 clip``, ``3 clips``."""
    return f"{n} {word}{'' if n == 1 else 's'}"


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except ValueError:
        return default


def local_matches() -> list[Path]:
    from regista import api

    root = api.DATA_ROOT
    return [d for d in sorted(root.iterdir()) if (d / "events.jsonl").exists()] if root.exists() else []


# ---------------------------------------------------------------------------- pipeline runs

def run_of(d: Path, match_id: str | None = None, *, rows: bool = True) -> dict[str, Any]:
    """The last pipeline run recorded in ``d/agents`` (the intelligence workflow, or the vision workflow for a vision
    match). ``status`` is none, ok, paused (waiting for a human), or failed (an agent failed or dead-lettered; this wins
    over paused, since a failed resume gives its review back)."""
    sd = d / "agents"
    trace = [r for r in _jsonl(sd / "trace.jsonl") if r.get("agent") and r.get("status")]
    dead = _jsonl(sd / "dead_letter.jsonl")
    pending = _json(sd / "pending_review.json", [])
    pending = pending if isinstance(pending, list) else []
    state = _json(sd / "state.json", {})
    agents: dict[str, dict[str, Any]] = {}
    for r in trace:
        name = str(r["agent"])
        a = agents.setdefault(name, {"agent": name, "status": None, "attempts": 0, "elapsed_ms": 0.0, "error": None})
        a["status"] = r.get("status")
        a["attempts"] = max(a["attempts"], int(r.get("attempt") or 0))
        a["elapsed_ms"] = round(a["elapsed_ms"] + float(r.get("elapsed_ms") or 0.0), 1)
        if r.get("error"):
            a["error"] = r["error"]
        if r.get("note"):
            a["note"] = r["note"]
    failed = bool(dead) or any(a["status"] == "failed" for a in agents.values())
    status = "none" if not (trace or dead or pending) else "failed" if failed else "paused" if pending else "ok"
    label_models: dict[str, int] = {}
    for r in _jsonl(d / "clips.jsonl"):
        if r.get("type") == "label":
            label_models[str(r.get("model") or "unknown")] = label_models.get(str(r.get("model") or "unknown"), 0) + 1
    vision = (d / ".vision_work").exists() or (d / "review").exists()
    out = {"match_id": match_id or d.name, "has_run": status != "none", "status": status,
           "kind": "vision" if vision else "intelligence",
           # Who's who answers rewrite the vision layer's identity result; a copy without it (the live app) is read-only
           "identity_result": (d / ".vision_work" / "identity.joblib").exists() if vision else None,
           "clips": sum(1 for r in _jsonl(d / "clips.jsonl") if r.get("type") == "clip"),
           "finished_at": trace[-1].get("at") if trace else None, "agents": list(agents.values()),
           "dead_letters": [{"agent": x.get("agent"), "error": x.get("error"), "attempts": x.get("attempts"), "at": x.get("at")} for x in dead],
           "label_models": label_models,
           "review": {"pending_requests": len(pending), "pending_items": sum(len((p.get("request") or {}).get("items") or []) for p in pending),
                      "log": state.get("review_log") if isinstance(state, dict) else None}}
    if rows:
        out["rows"] = [{k: r.get(k) for k in ("at", "agent", "attempt", "status", "elapsed_ms", "error", "note")} for r in trace]
    return out


def empty_run(match_id: str, source: str) -> dict[str, Any]:
    return {"match_id": match_id, "has_run": False, "status": "none", "kind": None, "identity_result": None, "clips": None,
            "finished_at": None, "agents": [], "dead_letters": [],
            "label_models": {}, "review": {"pending_requests": 0, "pending_items": 0, "log": None}, "rows": [], "source": source}


def runs() -> list[dict[str, Any]]:
    """Every match this replica knows: local ones with their last run, then Cosmos-only ones (no run here)."""
    from regista import api

    out = [{**run_of(d, rows=False), "source": "local"} for d in local_matches()]
    local = {r["match_id"] for r in out}
    for mid in sorted(api._library()):
        if mid not in local:
            row = empty_run(mid, "cosmos")
            row.pop("rows")
            out.append(row)
    return out


# ---------------------------------------------------------------------------- the to-do list

def _todo(kind: str, match_id: str | None, count: int, detail: str, link: str, api_path: str) -> dict[str, Any]:
    return {"kind": kind, "match_id": match_id, "count": count, "detail": detail, "link": link, "api": api_path}


def todo() -> list[dict[str, Any]]:
    """What is waiting on Zaid, most urgent first: failed runs, paused reviews, who's who, unsure clips, a stale model."""
    from regista import api
    from regista.feedback import needs_review

    api._sync_feedback()
    failed, reviews, whos, unsure = [], [], [], []
    for d in local_matches():
        mid = d.name
        run = run_of(d, rows=False)
        if run["status"] == "failed":
            bad = [a for a in run["agents"] if a["status"] == "failed"] or [{"agent": x["agent"], "error": x["error"]} for x in run["dead_letters"]]
            first = bad[0] if bad else {"agent": "?", "error": None}
            failed.append(_todo("failed_run", mid, max(1, len(run["dead_letters"])), f"{first['agent']} failed: {first.get('error') or 'see the trace'}",
                                f"/studio#runs/{mid}", f"/api/studio/runs/{mid}"))
        if run["review"]["pending_items"] or run["review"]["pending_requests"]:
            n = run["review"]["pending_items"]
            reviews.append(_todo("workflow_review", mid, n, f"the workflow paused for a verdict on {_n(n, 'clip')}",
                                 f"/studio#review/{mid}", f"/api/matches/{mid}/review"))
        queue = _json(d / "review" / "identity_review.json", {})
        items = queue.get("items", []) if isinstance(queue, dict) else []
        if items:
            whos.append(_todo("whos_who", mid, len(items), f"{_n(len(items), 'identity call')} the vision layer is unsure of",
                              f"/studio#whos-who/{mid}", f"/api/matches/{mid}/identity-review"))
        try:
            clips, labels = api._clips(d)
        except Exception:  # noqa: BLE001 - a broken clips file must not hide the rest of the list
            continue
        verdicts = api._verdicts_for(mid)
        n = 0
        for c in clips:
            lb = labels.get(c["id"])
            if lb is None or c["id"] in verdicts:
                continue
            if lb.get("review") or needs_review(float(lb.get("watchability", 0.0)), lb.get("prior_watchability")):
                n += 1
        if n:
            unsure.append(_todo("unsure_clips", mid, n, f"{_n(n, 'clip')} flagged unsure {'has' if n == 1 else 'have'} no verdict yet", f"/studio#review/{mid}",
                                f"/api/matches/{mid}/clips"))
    return failed + reviews + whos + claims_todo() + unsure + model_todo()


def claims_todo() -> list[dict[str, Any]]:
    """"That's me" claims waiting for the operator, one row per match (regista.season.claims)."""
    from regista.season.claims import all_claims

    per: dict[str, int] = {}
    for c in all_claims():
        if c["status"] == "pending":
            per[c["match_id"]] = per.get(c["match_id"], 0) + 1
    return [_todo("pending_claims", mid, n, f"{_n(n, 'claim')} (\"that's me\") waiting for a decision", f"/studio#claims/{mid}",
                  f"/api/claims?match_id={mid}") for mid, n in sorted(per.items())]


def model_todo() -> list[dict[str, Any]]:
    """The watchability model is stale when people gave verdicts after it was trained (or it was never trained and there
    are enough verdicts to train it)."""
    from regista.feedback import MIN_SAMPLES, WatchabilityModel, latest_per_label, load_annotations, usable

    anns = load_annotations()
    if not anns:
        return []
    model = WatchabilityModel.load()
    if model is None or not model.trained_at:
        ready = len(latest_per_label(a for a in anns if usable(a)))
        if ready < MIN_SAMPLES:
            return []
        return [_todo("stale_model", None, ready, f"no model trained yet; {ready} verdicts are ready to train on", "/studio#training", "/api/feedback")]
    newer = [a for a in anns if a.get("annotated_at", "") > model.trained_at]
    if not newer:
        return []
    return [_todo("stale_model", None, len(newer), f"{_n(len(newer), 'verdict')} since {model.name} was trained at {model.trained_at}",
                  "/studio#training", "/api/feedback")]


# ---------------------------------------------------------------------------- the render cache

def cache() -> dict[str, Any]:
    from regista import api

    root = api.CACHE_ROOT
    matches = []
    for d in sorted(root.iterdir()) if root.exists() else []:
        if not d.is_dir():
            continue
        files = [f for f in d.iterdir() if f.is_file()]
        partial = [f for f in files if f.name.startswith(".") and ".part" in f.name]
        done = [f for f in files if f not in partial]
        matches.append({"match_id": d.name, "files": len(done), "bytes": sum(f.stat().st_size for f in done), "partial": len(partial)})
    p = dict(api.PRERENDER_PROGRESS)
    prerender = {"enabled": os.environ.get("REGISTA_PRERENDER") == "1", "running": p["running"], "total": p["total"],
                 "rendered": p["rendered"], "failed": p["failed"], "started_at": _iso(p["started_at"]), "finished_at": _iso(p["finished_at"]),
                 "tour": dict(p["tour"]) if p.get("tour") else None}   # the guided tour's part of the totals (regista.warm)
    from regista.render.video import usable_cpus

    return {"cache_root": str(root), "files": sum(m["files"] for m in matches), "bytes": sum(m["bytes"] for m in matches),
            "matches": matches, "prerender": prerender, "render_concurrency": api.RENDER_CONCURRENCY,
            "usable_cpus": usable_cpus()}   # what one render's processes are sized from (the container's quota)


# ---------------------------------------------------------------------------- Cosmos DB and Azure AI Search

_data_lock = threading.Lock()
_data_cache: dict[str, Any] = {"t": None, "value": None}


def _search_count() -> int:
    """Documents in the Azure AI Search index (tests replace this)."""
    from regista.cloud.search import ClipIndex

    return int(ClipIndex().search_client.get_document_count())


def _cosmos_counts() -> dict[str, Any]:
    from regista import api
    from regista.cloud import CloudConfig

    cfg = CloudConfig.from_env()
    if not cfg.cosmos_enabled:
        return {"configured": False}
    out: dict[str, Any] = {"configured": True, "database": cfg.cosmos_database, "containers": {}, "error": None}
    store = api._feedback_store()
    if store is None:
        out["error"] = "Cosmos DB is configured but could not be reached"
        return out
    for name in COSMOS_CONTAINERS:
        container = getattr(store, name, None)
        if container is None:
            continue
        try:
            rows = list(container.query_items("SELECT VALUE COUNT(1) FROM c", enable_cross_partition_query=True))
            out["containers"][name] = int(rows[0]) if rows else 0
        except Exception as exc:  # noqa: BLE001 - reported, never raised
            out["containers"][name] = None
            out["error"] = f"{name}: {type(exc).__name__}: {str(exc)[:200]}"
    return out


def _search_counts() -> dict[str, Any]:
    from regista.cloud import CloudConfig
    from regista.cloud.search import INDEX_NAME

    if not CloudConfig.from_env().search_enabled:
        return {"configured": False}
    try:
        return {"configured": True, "index": INDEX_NAME, "documents": _search_count(), "error": None}
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return {"configured": True, "index": INDEX_NAME, "documents": None, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def data(max_age_s: float = DATA_TTL_S) -> dict[str, Any]:
    """Documents per Cosmos DB container (read-only COUNT queries) and in the Search index, cached for a minute."""
    with _data_lock:
        now = time.monotonic()
        if _data_cache["t"] is None or now - _data_cache["t"] >= max_age_s:
            _data_cache["value"] = {"cosmos": _cosmos_counts(), "search": _search_counts(), "checked_at": _iso(time.time())}
            _data_cache["t"] = now
        return {**_data_cache["value"], "age_s": round(now - _data_cache["t"], 1)}
