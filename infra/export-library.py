#!/usr/bin/env python3
"""Export library matches' clips and Foundry labels from Cosmos DB into their local clips.jsonl. Read-only.

The library matches (syn_0141, syn_0142) were uploaded through the live workflow, labelled by Microsoft Foundry and
stored in Cosmos DB; their event streams lived on a replica's disk and were lost. The generator is deterministic, so
regenerate the streams from their seeds first (as infra/restore-library.sh does), then run this to bring Foundry's
labels back next to them, so the image and Cosmos DB agree:

    for s in 141 142; do PYTHONPATH=src python3 -m regista.synth --seed $s --minutes 3 --track-hz 1 --out data/synthetic/sample; done
    PYTHONPATH=src python3 infra/export-library.py                      # syn_0141 syn_0142 into data/synthetic/sample
    PYTHONPATH=src python3 infra/export-library.py syn_0141 --check     # compare only, write nothing

For each match it:
  1. reads the match header, clips and labels from Cosmos DB (queries only: it never upserts, deletes or uploads);
  2. strips Cosmos system fields (_rid, _self, _etag, _attachments, _ts) and validates every record against the schema;
  3. checks the stream on disk against Cosmos DB: the header must match (except its id), and every clip's id,
     player_id, t and t_end must equal the clip rule (regista.clips.derive_clips) applied to events.jsonl, and every
     clip must carry exactly one Foundry label (model "foundry:...");
  4. only if every check passes, writes clips.jsonl (clips, then labels, as the committed sample does) and updates the
     clips.jsonl count in manifest.json. Any mismatch stops the run with a non-zero exit and writes nothing.

Auth is Entra ID (DefaultAzureCredential: `az login` locally), endpoints from .env (REGISTA_COSMOS_ENDPOINT,
REGISTA_COSMOS_DATABASE). It prints what it compared and wrote, never tokens or keys.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from regista.clips import derive_clips
from regista.cloud.config import CloudConfig
from regista.cloud.cosmos import ClipStore
from regista.schema import clips_validator, iter_jsonl, write_jsonl

CHECKED = ("id", "player_id", "t", "t_end")  # must equal the clip rule exactly
COMPARED = ("reason", "segment_ids", "event_ids", "possession_ids", "keyframe_t", "pre_roll_s", "post_roll_s")  # reported


def _clean(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if not k.startswith("_")}


def _query(container, match_id: str) -> list[dict]:
    rows = container.query_items("SELECT * FROM c WHERE c.match_id = @m", parameters=[{"name": "@m", "value": match_id}],
                                 partition_key=match_id)
    return [_clean(r) for r in rows]


def export_match(store: ClipStore, match_dir: Path, player: str) -> tuple[list[dict], list[str], list[str]]:
    """Return (records to write, problems, notes). Writes nothing."""
    match_id = match_dir.name
    problems: list[str] = []
    notes: list[str] = []
    events_path = match_dir / "events.jsonl"
    if not events_path.exists():
        return [], [f"{events_path} missing: regenerate the stream from its seed first"], notes
    stream = list(iter_jsonl(events_path))

    header = store.get_match(match_id)
    if header is None:
        return [], [f"{match_id}: no match header in Cosmos DB"], notes
    local_header = stream[0]
    diff = sorted(k for k in set(header) | set(local_header) if k != "id" and header.get(k) != local_header.get(k))
    if diff:
        problems.append(f"match header differs from Cosmos DB in: {', '.join(diff)}")

    clips = sorted((c for c in _query(store.clips, match_id) if c.get("player_id") == player), key=lambda c: c["id"])
    labels = [lb for lb in _query(store.labels, match_id) if lb.get("player_id") == player]
    stale = [c["id"] for c in clips if not c["id"].startswith(f"cl_{player}_")]
    if stale:
        problems.append(f"pre-0.1.1 clip ids in Cosmos DB: {stale}")

    expected, _ = derive_clips(stream, player)
    if len(expected) != len(clips):
        problems.append(f"clip count: Cosmos DB {len(clips)}, clip rule {len(expected)}")
    for exp, got in zip(expected, clips):
        for k in CHECKED:
            if exp[k] != got.get(k):  # numeric compare, so Cosmos's 0 equals the rule's 0.0
                problems.append(f"{exp['id']}: {k} clip rule {exp[k]!r} vs Cosmos DB {got.get(k)!r}")
        for k in COMPARED:
            if exp.get(k) != got.get(k):
                notes.append(f"{exp['id']}: {k} differs (clip rule {exp.get(k)!r}, Cosmos DB {got.get(k)!r})")

    by_clip: dict[str, list[dict]] = {}
    for lb in labels:
        by_clip.setdefault(lb["clip_id"], []).append(lb)
    ordered_labels = []
    for c in clips:
        found = by_clip.pop(c["id"], [])
        if len(found) != 1:
            problems.append(f"{c['id']}: {len(found)} labels in Cosmos DB, expected 1")
            continue
        if not str(found[0].get("model", "")).startswith("foundry:"):
            problems.append(f"{c['id']}: label model {found[0].get('model')!r} is not Foundry")
        ordered_labels.append(found[0])
    if by_clip:
        problems.append(f"labels without a clip: {sorted(by_clip)}")

    records = clips + ordered_labels
    validator = clips_validator()
    for r in records:
        for err in validator.errors(r):
            problems.append(f"{r.get('id')}: schema: {err}")
    return records, problems, notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("matches", nargs="*", default=["syn_0141", "syn_0142"])
    ap.add_argument("--root", default="data/synthetic/sample", help="folder holding the match directories")
    ap.add_argument("--player", default="t_home_09")
    ap.add_argument("--check", action="store_true", help="compare only; write nothing")
    ap.add_argument("--dotenv", default=None, help=".env to read endpoints from (default: $REGISTA_DOTENV, else .env)")
    args = ap.parse_args(argv)

    store = ClipStore.connect(CloudConfig.from_env(args.dotenv))
    failed = False
    for match_id in args.matches:
        match_dir = Path(args.root) / match_id
        records, problems, notes = export_match(store, match_dir, args.player)
        n_clips = sum(r["type"] == "clip" for r in records)
        models = sorted({r["model"] for r in records if r["type"] == "label"})
        for n in notes:
            print(f"  note {match_id}: {n}")
        if problems:
            failed = True
            print(f"FAIL {match_id}: {len(problems)} problem(s); nothing written")
            for p in problems:
                print(f"  {p}")
            continue
        print(f"ok   {match_id}: {n_clips} clips for {args.player} match the clip rule (id, player_id, t, t_end); labels {models}")
        for r in records:
            if r["type"] == "clip":
                print(f"     {r['id']}  {r['reason']:<22} t {r['t']:>7} .. {r['t_end']:<7}")
        if args.check:
            continue
        n = write_jsonl(match_dir / "clips.jsonl", records)
        manifest_path = match_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.setdefault("files", {})["clips.jsonl"] = n
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"     wrote {match_dir / 'clips.jsonl'} ({n} records)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
