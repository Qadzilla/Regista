"""Vision jobs started from the Studio: local only, one at a time, from an allow-list.

Each job is ``python3 -m regista.vision <kind> …`` as a subprocess, with no shell and no free-form arguments: the Studio
sends a kind and a few typed fields, and ``build_argv`` turns them into an argument list or refuses. Paths are resolved
here (match ids under REGISTA_DATA, the models directory from REGISTA_MODELS), so nothing the caller sends can become
an option. Each job keeps ``job.json`` and ``log.txt`` in its own folder under REGISTA_STUDIO_JOBS (default
``data/studio/jobs``, git-ignored); ``evaluate`` also keeps its JSON report there as ``result.json``.

Kinds and their fields
----------------------
vision-run          video (path to a video file), roster (match id: the team sheet), out (new match id), workflow (bool, default true)
evaluate            set ("dev" or "fresh", default "dev"), e2e_seed (int, optional)
train-events        (none)
learn-from-reviews  match_ids (1-20 match ids with answered who's who reviews)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$")  # starts alphanumeric: never ".", ".hidden" or "-x"
JOB_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z\-]{1,24}-[0-9a-f]{6}$")
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
LOG_CHUNK = 64 * 1024
SECRET_ENV = ("REGISTA_ADMIN_TOKEN", "REGISTA_STUDIO_VIEW_TOKEN", "APPLICATIONINSIGHTS_CONNECTION_STRING")

KINDS: dict[str, dict[str, Any]] = {
    "vision-run": {"help": "run the vision layer on a video and write a new match directory",
                   "args": {"video": "path to a video file on this machine", "roster": "match id whose team sheet to use",
                            "out": "new match id to write", "workflow": "bool, default true: run as the Agent Framework workflow"}},
    "evaluate": {"help": "score the frozen vision models on the development set or the fresh matches",
                 "args": {"set": "dev or fresh (default dev)", "e2e_seed": "int, optional: match for the end-to-end clip comparison"}},
    "train-events": {"help": "render event-spotting data and train the event spotter", "args": {}},
    "learn-from-reviews": {"help": "fine-tune the kit-number reader on answered who's who reviews",
                           "args": {"match_ids": "list of 1-20 match ids with answered reviews"}},
}


class JobError(ValueError):
    """The request does not fit the allow-list (an HTTP 422)."""


class JobBusy(RuntimeError):
    """Another job is running (an HTTP 409)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _match_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.match(value) or ".." in value or value.startswith("-"):
        raise JobError(f"{field} must be a match id (letters, digits, _ . -)")
    return value


def _existing_match(data_root: Path, value: Any, field: str) -> Path:
    d = data_root / _match_id(value, field)
    if not (d / "events.jsonl").exists():
        raise JobError(f"{field}: no match {value!r} under {data_root}")
    return d.resolve()


def build_argv(kind: str, args: dict[str, Any] | None, *, data_root: Path, models_dir: Path, job_dir: Path) -> list[str]:
    """The ``regista.vision`` argument list for this job, or JobError. Unknown kinds and unknown fields are refused."""
    if kind not in KINDS:
        raise JobError(f"unknown job kind {kind!r}; one of {sorted(KINDS)}")
    args = dict(args or {})
    unknown = sorted(set(args) - set(KINDS[kind]["args"]))
    if unknown:
        raise JobError(f"{kind} does not take {unknown}; it takes {sorted(KINDS[kind]['args']) or 'no arguments'}")
    models = ["--models", str(Path(models_dir).resolve())]
    if kind == "vision-run":
        for field in ("video", "roster", "out"):
            if field not in args:
                raise JobError(f"vision-run needs {field}")
        if not isinstance(args["video"], str) or not args["video"] or "\x00" in args["video"]:
            raise JobError("video must be a path")
        video = Path(args["video"]).expanduser().resolve()  # absolute, so it can never read as an option
        if not video.is_file() or video.suffix.lower() not in VIDEO_SUFFIXES:
            raise JobError(f"video must be an existing {'/'.join(sorted(VIDEO_SUFFIXES))} file")
        roster = _existing_match(data_root, args["roster"], "roster")
        out_id = _match_id(args["out"], "out")
        out = data_root / out_id
        if out.exists():
            raise JobError(f"out: match {out_id!r} already exists")
        workflow = args.get("workflow", True)
        if not isinstance(workflow, bool):
            raise JobError("workflow must be true or false")
        return ["run", str(video), "--roster", str(roster), "--out", str(out.resolve()), *models, "--match-id", out_id] + (["--workflow"] if workflow else [])
    if kind == "evaluate":
        match_set = args.get("set", "dev")
        if match_set not in ("dev", "fresh"):
            raise JobError("set must be dev or fresh")
        argv = ["evaluate", "--set", match_set, *models, "--out", str((job_dir / "result.json").resolve())]
        if args.get("e2e_seed") is not None:
            seed = args["e2e_seed"]
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 < seed < 100000:
                raise JobError("e2e_seed must be an integer between 1 and 99999")
            argv += ["--e2e-seed", str(seed)]
        return argv
    if kind == "train-events":
        return ["train-events", *models]
    ids = args.get("match_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
        raise JobError("match_ids must be a list of 1 to 20 match ids")
    dirs = []
    for mid in ids:
        d = _existing_match(data_root, mid, "match_ids")
        if not (d / "review").is_dir():
            raise JobError(f"match_ids: {mid!r} has no who's who reviews")
        dirs.append(str(d))
    return ["learn-from-reviews", *dirs, *models]


class JobRunner:
    """One job at a time. ``prefix`` is the command before the job's arguments (tests swap in a harmless script)."""

    def __init__(self, root: Path | str, prefix: list[str] | None = None):
        self.root = Path(root)
        self.prefix = prefix or [sys.executable, "-m", "regista.vision"]
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._current: str | None = None
        self._threads: dict[str, threading.Thread] = {}

    # -- reading
    def _read(self, job_dir: Path) -> dict[str, Any] | None:
        try:
            job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if job.get("status") == "running" and job.get("id") != self._current:
            job["status"] = "lost"  # this process did not start it, or it ended without being recorded (a restart)
        job["log_bytes"] = (job_dir / "log.txt").stat().st_size if (job_dir / "log.txt").exists() else 0
        return job

    def list(self) -> list[dict[str, Any]]:
        jobs = [j for d in self.root.iterdir() if d.is_dir() and JOB_ID_RE.match(d.name) and (j := self._read(d))] if self.root.exists() else []
        return sorted(jobs, key=lambda j: j.get("id", ""), reverse=True)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self._read(self.root / job_id) if JOB_ID_RE.match(job_id) else None

    def running(self) -> dict[str, Any] | None:
        with self._lock:
            current = self._current if self._proc is not None and self._proc.poll() is None else None
        return self.get(current) if current else None

    def log(self, job_id: str, offset: int = 0, limit: int = LOG_CHUNK) -> dict[str, Any] | None:
        job = self.get(job_id)
        if job is None:
            return None
        path = self.root / job_id / "log.txt"
        size = path.stat().st_size if path.exists() else 0
        offset = max(0, min(offset, size))
        with (path.open("rb") if path.exists() else open(os.devnull, "rb")) as fh:
            fh.seek(offset)
            chunk = fh.read(max(1, min(limit, LOG_CHUNK)))
        return {"job_id": job_id, "status": job["status"], "offset": offset, "next_offset": offset + len(chunk), "size": size,
                "text": chunk.decode("utf-8", errors="replace")}

    # -- starting
    def start(self, kind: str, args: dict[str, Any] | None, *, data_root: Path, models_dir: Path) -> dict[str, Any]:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                raise JobBusy(f"job {self._current} is still running; one job at a time")
            job_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}-{uuid.uuid4().hex[:6]}"
            job_dir = self.root / job_id
            argv = build_argv(kind, args, data_root=Path(data_root), models_dir=Path(models_dir), job_dir=job_dir)
            job_dir.mkdir(parents=True)
            env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
            src = str(Path(__file__).resolve().parents[2])  # the folder holding the regista package
            env["PYTHONPATH"] = os.pathsep.join(p for p in (src, env.get("PYTHONPATH", "")) if p)
            env["PYTHONUNBUFFERED"] = "1"
            job = {"id": job_id, "kind": kind, "args": args or {}, "argv": ["python3", "-m", "regista.vision", *argv], "status": "running",
                   "started_at": _now(), "ended_at": None, "returncode": None, "result": None}
            self._current = job_id  # before job.json says running, so a reader never sees it as lost
            (job_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
            log = (job_dir / "log.txt").open("wb")
            try:
                proc = subprocess.Popen([*self.prefix, *argv], stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                                        start_new_session=True)
            except OSError as exc:
                log.close()
                self._current = None
                job.update(status="failed", ended_at=_now(), error=f"{type(exc).__name__}: {exc}")
                (job_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
                return job
            self._proc = proc
            t = threading.Thread(target=self._watch, args=(proc, log, job_dir, job), name=f"studio-job-{job_id}", daemon=True)
            self._threads[job_id] = t
            t.start()
            return job

    def _watch(self, proc: subprocess.Popen, log, job_dir: Path, job: dict[str, Any]) -> None:
        rc = proc.wait()
        log.close()
        result = None
        if (job_dir / "result.json").exists() and (job_dir / "result.json").stat().st_size < 2 * 1024 * 1024:
            try:
                result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
            except ValueError:
                result = None
        job.update(status="ok" if rc == 0 else "failed", returncode=rc, ended_at=_now(), result=result)
        (job_dir / "job.json").write_text(json.dumps(job, indent=2), encoding="utf-8")
        with self._lock:
            if self._proc is proc:
                self._proc, self._current = None, None

    def wait(self, job_id: str, timeout: float = 30.0) -> dict[str, Any] | None:
        t = self._threads.get(job_id)
        if t is not None:
            t.join(timeout)
        return self.get(job_id)
