"""Where the Player view's uploads, jobs and results live: Azure Blob Storage + Queue Storage, or a local folder.

The contract shared by the API (it takes the upload), the worker (it runs the vision workflow) and the profiles (they
read the result):

    uploads/{upload_id}/video.mp4      the player's footage, as uploaded
    uploads/{upload_id}/record.json    the upload record (``UploadRecord``): who, which clubs, status, stages, result
    matches/{match_id}/...             the match folder the worker wrote (events.jsonl, tracks.jsonl, clips.jsonl,
                                       manifest.json, review/), exactly what regista.api serves
    models/vision/...                  the trained vision models the worker loads (private; never in the repository)
    queue "vision-jobs"                one JSON message per job: {"upload_id": ..., "kind": "vision"}

``store_from_env()`` picks the backend: ``REGISTA_STORAGE_ACCOUNT`` set means Azure (keyless, ``DefaultAzureCredential``:
the app's and the job's managed identities, or ``az login`` on a laptop); otherwise a folder (``REGISTA_PLAYER_DIR``,
default ``data/player``) with the same layout and a directory of JSON files for the queue. Tests and offline runs use
the folder; the worker runs the same code against either.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Iterator

Record = dict[str, Any]
QUEUE = "vision-jobs"
CONTAINERS = ("uploads", "matches", "models")
STATUSES = ("queued", "running", "needs_review", "done", "failed")
MAX_VIDEO_BYTES = 300 * 1024 * 1024


def new_upload_id() -> str:
    return "up_" + uuid.uuid4().hex[:10]


def match_id_for(upload_id: str) -> str:
    """The match an upload becomes (``up_ab12…`` -> ``pv_ab12…``): a Player-view match, never a league fixture id."""
    return "pv_" + upload_id.removeprefix("up_")


@dataclass
class UploadRecord:
    upload_id: str
    global_id: str                 # the (synthetic) player who uploaded: their profile gets the match
    club_id: str                   # the player's club in the footage
    opponent_club_id: str          # the other team in the footage
    side: str                      # "home" or "away": which team the player's club is in the roster
    kit_number: int
    status: str = "queued"         # one of STATUSES
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    filename: str = "video.mp4"
    size_bytes: int = 0
    stages: list[Record] = field(default_factory=list)   # [{role, status, ms, note}] as the vision workflow reports them
    match_id: str | None = None
    error: str | None = None
    source: str = "synthetic"      # footage rendered by Regista (``regista.player.film``), not a real camera
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> Record:
        return asdict(self)

    @classmethod
    def from_json(cls, d: Record) -> UploadRecord:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


class Store:
    """The operations the API, the worker and the profiles need; two backends below."""

    kind = "base"

    # uploads
    def put_video(self, upload_id: str, data: BinaryIO) -> int: raise NotImplementedError
    def get_video(self, upload_id: str, dest: Path) -> Path: raise NotImplementedError
    def put_record(self, rec: UploadRecord) -> None: raise NotImplementedError
    def get_record(self, upload_id: str) -> UploadRecord | None: raise NotImplementedError
    def list_records(self) -> list[UploadRecord]: raise NotImplementedError
    # the queue
    def enqueue(self, message: Record) -> None: raise NotImplementedError
    def receive(self, visibility_s: int = 1800) -> tuple[Record, Any] | None: raise NotImplementedError
    def done(self, receipt: Any) -> None: raise NotImplementedError
    # results and models
    def put_dir(self, container: str, prefix: str, src: Path) -> int: raise NotImplementedError
    def get_dir(self, container: str, prefix: str, dest: Path) -> int: raise NotImplementedError
    def list_prefixes(self, container: str, prefix: str = "") -> list[str]: raise NotImplementedError

    def put_match(self, match_id: str, src: Path) -> int:
        return self.put_dir("matches", match_id, src)

    def get_match(self, match_id: str, dest: Path) -> int:
        return self.get_dir("matches", match_id, dest)

    def list_matches(self) -> list[str]:
        return self.list_prefixes("matches")

    def update(self, upload_id: str, **changes: Any) -> UploadRecord:
        rec = self.get_record(upload_id)
        if rec is None:
            raise KeyError(upload_id)
        for k, v in changes.items():
            setattr(rec, k, v)
        rec.updated_at = time.time()
        self.put_record(rec)
        return rec


def _walk(src: Path) -> Iterator[tuple[Path, str]]:
    for p in sorted(src.rglob("*")):
        if p.is_file():
            yield p, p.relative_to(src).as_posix()


class LocalStore(Store):
    kind = "local"

    def __init__(self, root: Path | str):
        self.root = Path(root)
        for c in (*CONTAINERS, "queue"):
            (self.root / c).mkdir(parents=True, exist_ok=True)

    def _blob(self, container: str, name: str) -> Path:
        p = (self.root / container / name).resolve()
        if not str(p).startswith(str((self.root / container).resolve())):
            raise ValueError(f"bad blob name {name!r}")
        return p

    def put_video(self, upload_id: str, data: BinaryIO) -> int:
        dest = self._blob("uploads", f"{upload_id}/video.mp4")
        dest.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with dest.open("wb") as fh:
            while chunk := data.read(1 << 20):
                n += len(chunk)
                if n > MAX_VIDEO_BYTES:
                    fh.close()
                    dest.unlink(missing_ok=True)
                    raise ValueError(f"video larger than {MAX_VIDEO_BYTES // (1 << 20)} MB")
                fh.write(chunk)
        return n

    def get_video(self, upload_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self._blob("uploads", f"{upload_id}/video.mp4"), dest)
        return dest

    def put_record(self, rec: UploadRecord) -> None:
        p = self._blob("uploads", f"{rec.upload_id}/record.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec.to_json(), indent=1))
        os.replace(tmp, p)

    def get_record(self, upload_id: str) -> UploadRecord | None:
        p = self._blob("uploads", f"{upload_id}/record.json")
        return UploadRecord.from_json(json.loads(p.read_text())) if p.exists() else None

    def list_records(self) -> list[UploadRecord]:
        out = [UploadRecord.from_json(json.loads(p.read_text())) for p in (self.root / "uploads").glob("*/record.json")]
        return sorted(out, key=lambda r: -r.created_at)

    def enqueue(self, message: Record) -> None:
        name = f"{time.time_ns()}_{uuid.uuid4().hex[:6]}.json"
        tmp = self.root / "queue" / f".{name}"
        tmp.write_text(json.dumps(message))
        os.replace(tmp, self.root / "queue" / name)

    def receive(self, visibility_s: int = 1800) -> tuple[Record, Any] | None:
        for p in sorted((self.root / "queue").glob("*.json")):
            claimed = p.with_name(p.name + ".claimed")
            try:
                os.replace(p, claimed)  # atomic: one worker wins
            except FileNotFoundError:
                continue
            return json.loads(claimed.read_text()), claimed
        return None

    def done(self, receipt: Any) -> None:
        Path(receipt).unlink(missing_ok=True)

    def put_dir(self, container: str, prefix: str, src: Path) -> int:
        n = 0
        for p, rel in _walk(src):
            dest = self._blob(container, f"{prefix}/{rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            n += 1
        return n

    def get_dir(self, container: str, prefix: str, dest: Path) -> int:
        src = self._blob(container, prefix)
        if not src.exists():
            return 0
        n = 0
        for p, rel in _walk(src):
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, out)
            n += 1
        return n

    def list_prefixes(self, container: str, prefix: str = "") -> list[str]:
        base = self._blob(container, prefix) if prefix else self.root / container
        return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else []


class AzureStore(Store):
    """Blob containers and a Storage queue in one account, keyless (Entra ID roles: Storage Blob Data Contributor and
    Storage Queue Data Contributor for the app and the job)."""

    kind = "azure"

    def __init__(self, account: str, credential: Any = None):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient
        from azure.storage.queue import QueueClient

        cred = credential or DefaultAzureCredential()
        self.account = account
        self.blobs = BlobServiceClient(f"https://{account}.blob.core.windows.net", credential=cred)
        self.queue = QueueClient(f"https://{account}.queue.core.windows.net", QUEUE, credential=cred)

    def _c(self, container: str):
        return self.blobs.get_container_client(container)

    def put_video(self, upload_id: str, data: BinaryIO) -> int:
        class Counting:
            def __init__(self, f: BinaryIO):
                self.f, self.n = f, 0

            def read(self, size: int = -1) -> bytes:
                chunk = self.f.read(size)
                self.n += len(chunk)
                if self.n > MAX_VIDEO_BYTES:
                    raise ValueError(f"video larger than {MAX_VIDEO_BYTES // (1 << 20)} MB")
                return chunk

        src = Counting(data)
        self._c("uploads").upload_blob(f"{upload_id}/video.mp4", src, overwrite=True, max_concurrency=2)
        return src.n

    def get_video(self, upload_id: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as fh:
            self._c("uploads").download_blob(f"{upload_id}/video.mp4").readinto(fh)
        return dest

    def put_record(self, rec: UploadRecord) -> None:
        self._c("uploads").upload_blob(f"{rec.upload_id}/record.json", json.dumps(rec.to_json()), overwrite=True)

    def get_record(self, upload_id: str) -> UploadRecord | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            raw = self._c("uploads").download_blob(f"{upload_id}/record.json").readall()
        except ResourceNotFoundError:
            return None
        return UploadRecord.from_json(json.loads(raw))

    def list_records(self) -> list[UploadRecord]:
        out = []
        for b in self._c("uploads").list_blobs():
            if b.name.endswith("/record.json"):
                out.append(UploadRecord.from_json(json.loads(self._c("uploads").download_blob(b.name).readall())))
        return sorted(out, key=lambda r: -r.created_at)

    def enqueue(self, message: Record) -> None:
        self.queue.send_message(json.dumps(message))

    def receive(self, visibility_s: int = 1800) -> tuple[Record, Any] | None:
        for m in self.queue.receive_messages(messages_per_page=1, visibility_timeout=visibility_s):
            return json.loads(m.content), m
        return None

    def done(self, receipt: Any) -> None:
        self.queue.delete_message(receipt)

    def put_dir(self, container: str, prefix: str, src: Path) -> int:
        n = 0
        for p, rel in _walk(src):
            with p.open("rb") as fh:
                self._c(container).upload_blob(f"{prefix}/{rel}", fh, overwrite=True)
            n += 1
        return n

    def get_dir(self, container: str, prefix: str, dest: Path) -> int:
        n = 0
        for b in self._c(container).list_blobs(name_starts_with=f"{prefix}/"):
            out = dest / b.name[len(prefix) + 1:]
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("wb") as fh:
                self._c(container).download_blob(b.name).readinto(fh)
            n += 1
        return n

    def list_prefixes(self, container: str, prefix: str = "") -> list[str]:
        start = f"{prefix}/" if prefix else ""
        names = set()
        for item in self._c(container).walk_blobs(name_starts_with=start, delimiter="/"):
            if item.name.endswith("/"):
                names.add(item.name[len(start):].rstrip("/"))
        return sorted(names)


def store_from_env() -> Store:
    account = os.environ.get("REGISTA_STORAGE_ACCOUNT")
    if account:
        return AzureStore(account)
    return LocalStore(os.environ.get("REGISTA_PLAYER_DIR", "data/player"))
