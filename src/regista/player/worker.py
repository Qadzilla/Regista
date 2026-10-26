"""The Player view's worker: one uploaded video in, one match folder out. What the Azure Container Apps Job runs.

    python -m regista.player.worker --once          # the job: handle at most one queued upload, then exit
    python -m regista.player.worker --poll 10       # a laptop: keep taking uploads, checking every 10 seconds

For each message on the ``vision-jobs`` queue (``regista.player.store``, Azure or the local folder, the same code):

1. load the ``UploadRecord`` and set it to ``running``;
2. download the video, and the trained models from the store's ``models/vision/`` (unless ``--models DIR``);
3. build the team sheet with ``roster_for`` (both clubs' league squads, global player ids);
4. run the vision workflow (the Microsoft Agent Framework one, ``regista.vision.agents``), writing each role's result
   into ``record.stages`` as the workflow reports it, so the page shows progress live;
5. cut every starter's clips (``regista.clips.derive_clips``, as ``regista.season.build`` does) into ``clips.jsonl``;
6. write ``manifest.json`` and upload the folder, ``review/`` and ``.vision_work/`` included (the Who's who answers are
   applied to them later), to ``matches/{match_id}``;
7. set the status: ``needs_review`` when Who's who has open questions about the player's own track (their kit number
   on their team), otherwise ``done``; then delete the message.

Any error sets ``failed`` with a plain-English reason and deletes the message: a bad video fails the same way twice,
so there is no retry loop. A message whose upload is already ``running`` means an earlier attempt died (out of memory,
or past the queue's visibility timeout); it is marked failed rather than run again.

Who's who during the job: nobody is there to answer, so the workflow does not pause (``review`` off); the vision
writer saves the questions and crops (``review_min_doubt`` 0.15 and 12 questions, as the CLI) for the player to answer
on the page.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import sys
import tempfile
import time
import traceback
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from regista.player.store import Store, UploadRecord, match_id_for, store_from_env

Record = dict[str, Any]
MAX_FOOTAGE_S = 330.0          # "about 5 minutes": five and a half, so a clip that runs a few seconds over still goes in
VIDEO_SIZE = (640, 360)        # what the vision models were trained on (CLAUDE.md §3.1: the shot model fails at 720p)
VIDEO_FPS = (9.5, 10.5)        # 10 fps; the shot model degrades at 25
VISIBILITY_S = 1800            # the queue hides a taken message this long; a job that runs past it is marked failed
REVIEW_MIN_DOUBT = 0.15        # as ``python -m regista.vision run --workflow --review``
REVIEW_QUESTIONS = 12
WORKER_STAGES_BEFORE = ["download"]
WORKER_STAGES_AFTER = ["clips", "publish"]
STAGE_NOTES = {
    "download": "fetching the video and the vision models",
    "shots": "cutting the footage into camera shots",
    "identity": "finding the players and the ball, reading kit numbers",
    "identity_review": "deciding what to ask you",
    "possession_vision": "working out who is on the ball",
    "events_vision": "spotting passes, shots, tackles, take-ons",
    "vision_writer": "writing and validating the match",
    "clips": "cutting every starter's moments",
    "publish": "saving the match",
}


class JobError(Exception):
    """A reason the job cannot finish, worded for the player (it is what the page shows)."""


def log(msg: str, upload_id: str | None = None) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"{stamp} [worker]{f' {upload_id}' if upload_id else ''} {msg}", flush=True)


def peak_rss_mb() -> float:
    """This process's peak resident memory (ru_maxrss is bytes on macOS, kilobytes on Linux)."""
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(rss / (1 << 20) if sys.platform == "darwin" else rss / 1024, 1)


# ---------------------------------------------------------------------------- stages: what the page shows

class Stages:
    """``record.stages`` kept in step with the workflow: every role listed up front as pending, then running, then its
    result (``ok``, ``failed``, ``skipped``) with milliseconds and a note. Each change is written to the store."""

    def __init__(self, store: Store, upload_id: str, roles: list[str]):
        self.store = store
        self.upload_id = upload_id
        self.rows: list[Record] = [{"role": r, "status": "pending", "ms": None, "note": STAGE_NOTES.get(r, "")} for r in roles]
        self.started: dict[str, float] = {}
        self.save()

    def _row(self, role: str) -> Record:
        for row in self.rows:
            if row["role"] == role:
                return row
        row = {"role": role, "status": "pending", "ms": None, "note": STAGE_NOTES.get(role, "")}
        self.rows.append(row)
        return row

    def save(self) -> None:
        self.store.update(self.upload_id, stages=[dict(r) for r in self.rows])

    def running(self, role: str) -> None:
        self.started[role] = time.perf_counter()
        self._row(role).update(status="running", ms=None)
        self.save()

    def finish(self, role: str, status: str, ms: float | None = None, note: str | None = None) -> None:
        row = self._row(role)
        if ms is None and role in self.started:
            ms = (time.perf_counter() - self.started[role]) * 1000
        row.update(status=status, ms=None if ms is None else int(round(ms)))
        if note is not None:
            row["note"] = note
        self.save()

    def note(self, role: str, note: str) -> None:
        self._row(role)["note"] = note

    def stop(self, why: str) -> None:
        """The job ended early: the step in progress failed, the ones after it never ran."""
        for row in self.rows:
            if row["status"] == "running":
                ms = (time.perf_counter() - self.started[row["role"]]) * 1000 if row["role"] in self.started else None
                row.update(status="failed", ms=None if ms is None else int(round(ms)))
            elif row["status"] == "pending":
                row.update(status="skipped", note=why)
        self.save()


def _trace_note(row: Record) -> str | None:
    """A first note from the workflow's trace row (counts only); ``_final_notes`` replaces it with the full picture."""
    if row.get("status") == "failed":
        return row.get("error") or "failed"
    if row.get("status") == "skipped":
        return row.get("error") or "skipped"
    if row.get("note"):
        return str(row["note"])
    out = row.get("records_out") or {}
    words = {"camera_segments": "camera shots", "possessions": "possessions", "vision_events": "events"}
    parts = [f"{n} {words[k]}" for k, n in out.items() if k in words and n is not None]
    return ", ".join(parts) or None


# ---------------------------------------------------------------------------- the vision workflow, streamed

def vision_agents_for(models_dir: Path) -> list[Any]:
    """The five vision roles, loading the models from ``models_dir``. Tests swap this for stand-in roles."""
    from regista.vision.agents import vision_agents

    return vision_agents({"models_dir": str(models_dir)})


def run_vision_streamed(video: Path, roster: Record, out_dir: Path, match_id: str, models_dir: Path, stages: Stages) -> Any:
    """Run the vision workflow, writing each role's progress into ``stages`` as the workflow emits it
    (``executor_invoked`` = running, Regista's trace row = its result). Returns a ``VisionRun``."""
    from regista.agents.workflow import DEAD_EVENT, TRACE_EVENT, PipelineOutput
    from regista.aio import run_sync
    from regista.vision.agents import VisionRequest, VisionRun, build_vision_workflow

    config = {"models_dir": str(models_dir), "review_min_doubt": REVIEW_MIN_DOUBT, "review_questions": REVIEW_QUESTIONS}
    workflow, _keys = build_vision_workflow(vision_agents_for(models_dir), config=config)
    request = VisionRequest(video_path=str(video), roster=roster, out_dir=str(out_dir), match_id=match_id, review=False,
                            annotator="player")
    roles = {row["role"] for row in stages.rows}
    trace: list[Record] = []
    dead: list[Record] = []
    outputs: list[Any] = []

    async def go() -> None:
        async for ev in workflow.run(request, stream=True):
            if ev.type == "executor_invoked" and getattr(ev, "executor_id", None) in roles:
                stages.running(ev.executor_id)
            elif ev.type == TRACE_EVENT:
                row = ev.data
                trace.append(row)
                if row.get("status") in ("ok", "failed", "skipped"):
                    note = _trace_note(row)
                    if row["agent"] == "identity_review" and row.get("note") == "review off":
                        note = "nobody to ask during the job: the questions are saved for you to answer"
                    stages.finish(row["agent"], row["status"], row.get("elapsed_ms"), note)
                    log(f"{row['agent']:<18} {row['status']:<7} {row.get('elapsed_ms') or 0:>9.0f} ms  {note or ''}")
            elif ev.type == DEAD_EVENT:
                dead.append(ev.data)
            elif ev.type == "output" and isinstance(ev.data, PipelineOutput):
                outputs.append(ev.data)

    run_sync(go())
    out = outputs[-1] if outputs else None
    run = VisionRun(ok=bool(out and out.ok), state=dict(out.state) if out else {}, trace=trace, dead_letters=dead,
                    failed_role=out.failed_role if out else None)
    agents_dir = out_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / "trace.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in trace), encoding="utf-8")
    (agents_dir / "dead_letter.jsonl").write_text("".join(json.dumps(r, default=str) + "\n" for r in dead), encoding="utf-8")
    return run


def _final_notes(stages: Stages, state: Record, review: Record) -> None:
    """Once the workflow is done, the notes say what each role found (the final state holds it)."""
    segs = state.get("camera_segments") or []
    if segs:
        kinds = Counter(s["kind"] for s in segs)
        stages.note("shots", f"{len(segs)} camera shots: " + ", ".join(f"{n} {k}" for k, n in kinds.most_common()))
    ident = state.get("identity_summary") or {}
    if ident:
        stages.note("identity", f"{ident.get('named_tracks', 0)} of {ident.get('tracks', 0)} player tracks named from kit numbers, "
                                f"{ident.get('cutaway_segments', 0)} replays and close-ups checked")
    if "possessions" in state:
        stages.note("possession_vision", f"{len(state['possessions'])} spells on the ball")
    if "vision_events" in state:
        kinds = Counter(e.get("event_type") for e in state["vision_events"])
        stages.note("events_vision", f"{len(state['vision_events'])} events" +
                    (": " + ", ".join(f"{n} {k}" for k, n in kinds.most_common(5)) if kinds else ""))
    q = review.get("questions", 0)
    stages.note("vision_writer", f"match written and validated; {q} Who's who question{'s' if q != 1 else ''}"
                                 f" ({len(review.get('about_player', []))} about you)")
    stages.save()


# ---------------------------------------------------------------------------- models

_PULLED: dict[str, Path] = {}


def models_cache_dir() -> Path:
    """Where pulled models go: ``REGISTA_MODELS_CACHE``, or a folder of this process's own (two workers on one laptop
    never pull over each other)."""
    if os.environ.get("REGISTA_MODELS_CACHE"):
        return Path(os.environ["REGISTA_MODELS_CACHE"])
    return Path(tempfile.gettempdir()) / f"regista-models-{os.getpid()}" / "vision"


def ensure_models(store: Store, models_dir: Path | None) -> Path:
    """``models_dir`` when given; otherwise the store's ``models/vision/``, downloaded once per process."""
    if models_dir is not None:
        if not any(Path(models_dir).glob("*")):
            raise JobError(f"No vision models in {models_dir}.")
        return Path(models_dir)
    key = f"{store.kind}:{id(store)}"
    if key not in _PULLED:
        from regista.player.models import pull

        dest = models_cache_dir()
        shutil.rmtree(dest, ignore_errors=True)
        n = pull(store, dest)
        if n == 0:
            raise JobError("The vision models are not in storage yet (models/vision/); the operator pushes them with "
                           "python -m regista.player.models push.")
        log(f"pulled {n} model files into {dest}")
        _PULLED[key] = dest
    return _PULLED[key]


# ---------------------------------------------------------------------------- one job

def check_footage(video: Path) -> Any:
    from regista.vision.frames import probe

    try:
        info = probe(video)
    except Exception as exc:  # noqa: BLE001 - any decode failure means the same thing to the player
        raise JobError(f"The video could not be read ({type(exc).__name__}). Upload an MP4 file.") from exc
    if info.duration_s <= 0:
        raise JobError("The video has no frames.")
    if (info.width, info.height) != VIDEO_SIZE or not VIDEO_FPS[0] <= info.fps <= VIDEO_FPS[1]:
        raise JobError(f"Regista's vision models read {VIDEO_SIZE[0]}x{VIDEO_SIZE[1]} video at 10 frames a second (the format "
                       f"python -m regista.player.film renders); this video is {info.width}x{info.height} at {info.fps:g} fps.")
    if info.duration_s > MAX_FOOTAGE_S:
        raise JobError(f"The footage is {info.duration_s / 60:.1f} minutes long; Regista takes up to 5 minutes per upload. "
                       "Trim it and upload again.")
    return info


def the_player(roster: Record, rec: UploadRecord) -> Record:
    """The uploader's line on the team sheet: their global id, on their club's side."""
    team_id = roster["home_team_id"] if rec.side == "home" else roster["away_team_id"]
    for p in roster["players"]:
        if p.get("global_player_id") == rec.global_id:
            if p["team_id"] != team_id:
                raise JobError(f"Player {rec.global_id} plays for the other team in this footage; check the club and side.")
            return p
    raise JobError(f"Player {rec.global_id} is not in the squad of {rec.club_id}.")


def questions_about(review_dir: Path, player: Record) -> tuple[list[Record], list[str]]:
    """Open Who's who questions, and the ids of those about the player's own track: a track on their team that the
    identity agent named them, or with them among its candidates."""
    from regista.vision.review import QUEUE_FILE

    q = review_dir / QUEUE_FILE
    items = json.loads(q.read_text())["items"] if q.exists() else []
    mine = [it["item_id"] for it in items
            if it.get("kind") == "track" and it.get("team_id") == player["team_id"]
            and (it.get("current") == player["player_id"] or any(c.get("player_id") == player["player_id"] for c in it.get("candidates", [])))]
    return items, mine


def cut_clips(match_dir: Path, player_id: str) -> tuple[list[Record], list[Record], list[str]]:
    """Every starter's clips (and the uploader's, starter or not), as ``regista.season.build`` cuts a league match."""
    from regista.clips import derive_clips
    from regista.schema import iter_jsonl

    stream = list(iter_jsonl(match_dir / "events.jsonl"))
    header = stream[0]
    who = [p["player_id"] for p in header["players"] if p.get("starter")]
    if player_id not in who:
        who.append(player_id)
    clips: list[Record] = []
    labels: list[Record] = []
    for pid in who:
        c, lb = derive_clips(stream, pid)
        clips += c
        labels += lb
    return clips, labels, who


def _add_score(match_dir: Path) -> dict[str, int]:
    """Goals the vision layer spotted, on the match header (where the app reads the score), as the vision packager does."""
    from regista.schema import iter_jsonl, write_jsonl
    from regista.vision.package import _score

    stream = list(iter_jsonl(match_dir / "events.jsonl"))
    score = _score(stream[0], stream[1:])
    stream[0] = {**stream[0], "score": score}
    write_jsonl(match_dir / "events.jsonl", stream)
    return score


def process(store: Store, upload_id: str, *, models_dir: Path | None = None, work_root: Path | None = None) -> UploadRecord:
    """Run one upload end to end. Raises ``JobError`` (or anything unexpected) for the caller to record."""
    t_job = time.perf_counter()
    rec = store.get_record(upload_id)
    if rec is None:
        raise JobError(f"No upload record for {upload_id}.")
    match_id = match_id_for(upload_id)
    store.update(upload_id, status="running", error=None, match_id=None)
    from regista.vision.agents import VISION_ROLE_ORDER

    roles = list(VISION_ROLE_ORDER)
    roles.insert(roles.index("identity") + 1, "identity_review")
    stages = Stages(store, upload_id, WORKER_STAGES_BEFORE + roles + WORKER_STAGES_AFTER)
    try:
        with tempfile.TemporaryDirectory(prefix=f"regista-{upload_id}-", dir=work_root) as tmp:
            tmp = Path(tmp)
            stages.running("download")
            video = store.get_video(upload_id, tmp / "video.mp4")
            info = check_footage(video)
            from regista.player.film import roster_for

            try:
                roster = roster_for(rec.club_id, rec.opponent_club_id, rec.side, competition_id=rec.competition_id,
                                    date=rec.date_played)
            except ValueError as exc:
                raise JobError(f"Cannot build the team sheet: {exc}.") from exc
            player = the_player(roster, rec)
            if player["kit_number"] != rec.kit_number:
                rec_note = (f"you said kit number {rec.kit_number}; the team sheet has {player['name']} as number "
                            f"{player['kit_number']}, which is what the vision layer looks for")
                store.update(upload_id, notes=[*rec.notes, rec_note])
            models = ensure_models(store, models_dir)
            stages.finish("download", "ok", note=f"{info.duration_s / 60:.1f} minutes of {info.width}x{info.height} footage, "
                                                 f"{info.fps:g} fps")
            log(f"footage {info.duration_s:.1f}s {info.width}x{info.height} {info.fps:g} fps; player {player['player_id']} "
                f"({player['name']}, #{player['kit_number']}); models {models}", upload_id)

            out = tmp / match_id
            run = run_vision_streamed(video, roster, out, match_id, models, stages)
            if not run.ok:
                letter = run.dead_letters[0] if run.dead_letters else {}
                role = run.failed_role or letter.get("agent") or "vision"
                stages.stop(f"not run: {role} failed")
                raise JobError(f"The vision workflow stopped at its {role} step: {letter.get('error') or 'no reason given'}.")

            stages.running("clips")
            score = _add_score(out)
            clips, labels, who = cut_clips(out, player["player_id"])
            from regista.schema import write_jsonl

            write_jsonl(out / "clips.jsonl", clips + labels)
            mine = sum(1 for c in clips if c.get("player_id") == player["player_id"])
            stages.finish("clips", "ok", note=f"{len(clips)} clips for {len(who)} players, {mine} of them yours")

            items, about = questions_about(out / "review", player)
            _final_notes(stages, run.state, {"questions": len(items), "about_player": about})
            manifest = build_manifest(out, rec, roster, player, run.state, info, score, clips, who, items, about,
                                      seconds=time.perf_counter() - t_job)
            (out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n", encoding="utf-8")
            _portable_run_json(out)

            stages.running("publish")
            n = store.put_match(match_id, out)
            stages.finish("publish", "ok", note=f"{n} files saved as match {match_id}")
            status = "needs_review" if about else "done"
            rec = store.update(upload_id, status=status, match_id=match_id, error=None)
            log(f"{status}: {len(clips)} clips ({mine} the player's), {len(items)} questions ({len(about)} about the player), "
                f"{time.perf_counter() - t_job:.1f}s, peak memory {peak_rss_mb()} MB", upload_id)
            return rec
    except BaseException:
        stages.stop("not run: an earlier step failed")
        raise


def build_manifest(out: Path, rec: UploadRecord, roster: Record, player: Record, state: Record, info: Any, score: dict[str, int],
                   clips: list[Record], who: list[str], items: list[Record], about: list[str], *, seconds: float) -> Record:
    """The match folder's manifest: what the Product and the profiles read, with no machine paths."""
    teams = {t["team_id"]: t for t in roster["teams"]}
    home, away = teams[roster["home_team_id"]], teams[roster["away_team_id"]]
    vision = json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else {}
    events = state.get("vision_events") or []
    return {
        "match_id": match_id_for(rec.upload_id),
        "title": f"{player['name']}'s match: {home['name']} v {away['name']}",
        "subtitle": f"Uploaded by {player['name']} (#{player['kit_number']}, {teams[player['team_id']]['name']}). "
                    "Regista's vision workflow found the players, the ball and the moments in the footage.",
        "collection": "player", "source": "vision", "footage": rec.source,
        "uploaded_by": rec.global_id, "upload_id": rec.upload_id,
        "player": {"global_id": rec.global_id, "player_id": player["player_id"], "name": player["name"],
                   "kit_number": player["kit_number"], "team_id": player["team_id"], "club_id": rec.club_id},
        "home": home.get("club_id"), "away": away.get("club_id"),
        "competition": roster.get("competition"), "date": rec.date_played or roster.get("date"), "venue": roster.get("venue"),
        **catalogue_labels(rec),
        "score": score,
        "video": {"fps": info.fps, "width": info.width, "height": info.height, "duration_s": info.duration_s,
                  "blob": f"uploads/{rec.upload_id}/video.mp4"},
        "video_duration_s": info.duration_s,
        "files": {"events.jsonl": sum(1 for _ in (out / "events.jsonl").open()), "tracks.jsonl": sum(1 for _ in (out / "tracks.jsonl").open()),
                  "clips.jsonl": len(clips)},
        "record_counts": vision.get("record_counts", {}),
        "segments": vision.get("segments", {}),
        "event_type_counts": dict(Counter(e.get("event_type") for e in events)),
        "validation": vision.get("validation", {}),
        "identity": {k: v for k, v in (state.get("identity_summary") or {}).items() if k != "video"},
        "clip_count": len(clips), "clips_for": who,
        "player_clip_count": sum(1 for c in clips if c.get("player_id") == player["player_id"]),
        "review": {"questions": len(items), "kinds": dict(Counter(it.get("kind") for it in items)), "about_player": about},
        "pipeline": vision.get("pipeline", "regista.vision"),
        "worker": {"seconds": round(seconds, 1), "peak_rss_mb": peak_rss_mb(), "models": "models/vision (from storage)",
                   "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
    }


def catalogue_labels(rec: UploadRecord) -> Record:
    """A catalogue club's upload names its competition (labels only), the camera and the uploader in its manifest; the
    Regista League's friendly form (no competition) adds nothing, so its manifests are what they were."""
    if not rec.competition_id:
        return {}
    from regista.catalogue.taxonomy import BY_ID

    lab = BY_ID.get(rec.competition_id)
    labels = {k: getattr(lab, k) for k in ("country", "region", "tier", "age_group", "gender")} if lab else {}
    return {"competition_id": rec.competition_id, **labels, "camera": rec.camera,
            "uploader": {"type": rec.uploader_type, "global_id": rec.global_id, "club_id": rec.club_id},
            "counted": False}


def _portable_run_json(out: Path) -> None:
    """``.vision_work/run.json`` names the models the match was made with; the worker's cache path means nothing
    elsewhere, so it names the store's copy (the app falls back to its own models when the path is not there)."""
    run = out / ".vision_work" / "run.json"
    if run.exists():
        run.write_text(json.dumps({"models_dir": "models/vision", "store": "models/vision"}) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------- the queue

def handle_one(store: Store, *, models_dir: Path | None = None, work_root: Path | None = None) -> str | None:
    """Take at most one message and finish it (done, needs_review or failed). Returns its upload id, or None when the
    queue was empty."""
    got = store.receive(visibility_s=VISIBILITY_S)
    if got is None:
        return None
    message, receipt = got
    upload_id = str(message.get("upload_id") or "")
    try:
        if message.get("kind", "vision") != "vision" or not upload_id:
            log(f"ignoring a message this worker does not handle: {json.dumps(message)[:200]}")
            return upload_id or None
        rec = store.get_record(upload_id)
        if rec is None:
            log("no upload record; dropping the message", upload_id)
            return upload_id
        if rec.status in ("done", "needs_review", "failed"):
            log(f"already {rec.status}; dropping the repeated message", upload_id)
            return upload_id
        if rec.status == "running":
            _fail(store, upload_id, "An earlier attempt at this video stopped without finishing (it ran out of memory or time). "
                                    "Try a shorter clip.")
            return upload_id
        log(f"start: {rec.global_id}, {rec.club_id} v {rec.opponent_club_id} ({rec.side})", upload_id)
        try:
            process(store, upload_id, models_dir=models_dir, work_root=work_root)
        except JobError as exc:
            _fail(store, upload_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - recorded for the player, logged in full for the operator
            traceback.print_exc()
            _fail(store, upload_id, f"Something went wrong while processing the video ({type(exc).__name__}: {exc}).")
        return upload_id
    finally:
        try:
            store.done(receipt)
        except Exception as exc:  # noqa: BLE001 - e.g. the message became visible again and another job took it
            log(f"could not delete the message: {type(exc).__name__}: {exc}", upload_id or None)


def _fail(store: Store, upload_id: str, error: str) -> None:
    log(f"failed: {error}", upload_id)
    try:
        store.update(upload_id, status="failed", error=error)
    except Exception as exc:  # noqa: BLE001 - the record itself is unreachable; the log keeps the reason
        log(f"could not record the failure: {type(exc).__name__}: {exc}", upload_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m regista.player.worker", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="handle at most one queued upload, then exit (the Container Apps Job)")
    mode.add_argument("--poll", type=float, metavar="SECONDS", help="keep taking uploads, checking the queue every SECONDS")
    ap.add_argument("--models", type=Path, default=None, help="use these models instead of the store's models/vision/")
    ap.add_argument("--work", type=Path, default=None, help="scratch folder for the video and the match (default: the system temp)")
    args = ap.parse_args(argv)
    if args.work is not None:
        args.work.mkdir(parents=True, exist_ok=True)   # a new scratch folder is fine (it failed every upload before)
    store = store_from_env()
    log(f"store {store.kind}; {'once' if args.once else f'polling every {args.poll:g}s'}")
    if args.once:
        upload_id = handle_one(store, models_dir=args.models, work_root=args.work)
        log("queue empty, nothing to do" if upload_id is None else f"handled {upload_id}")
        return 0
    try:
        while True:
            if handle_one(store, models_dir=args.models, work_root=args.work) is None:
                time.sleep(max(0.5, args.poll))
    except KeyboardInterrupt:
        log("stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
