"""Bounded atomic JSON snapshots and single-host OS locks."""

from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Protocol

from .models import AgentCheckpoint, CheckpointBusy, CheckpointError, timestamp, validate_task_id

_CREDENTIAL_KEYS = {"api_key", "apikey", "password", "secret", "access_token", "authorization", "proxy-authorization"}
_CREDENTIAL_TEXT = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|(?:authorization[\"']?\s*[:=]\s*[\"']?(?:Bearer|Basic)\s+\S+)"
    r"|(?:api[_-]?key|password|access[_-]?token|secret)\s*[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{8,})",
    re.IGNORECASE,
)


def reject_credentials(value, forbidden_values=()) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in _CREDENTIAL_KEYS and item:
                raise CheckpointError("Checkpoint contains credential fields")
            reject_credentials(item, forbidden_values)
    elif isinstance(value, list):
        for item in value:
            reject_credentials(item, forbidden_values)
    elif isinstance(value, str):
        if _CREDENTIAL_TEXT.search(value) or any(secret and secret in value for secret in forbidden_values):
            raise CheckpointError("Checkpoint contains sensitive credential text")


class CheckpointStore(Protocol):
    root: Path

    def save(self, checkpoint: AgentCheckpoint) -> AgentCheckpoint: ...
    def load(self, task_id: str) -> AgentCheckpoint: ...
    def lease(self, task_id: str): ...


class FileCheckpointStore:
    def __init__(self, root: str | Path | None = None, *, max_size_bytes: int = 2 * 1024 * 1024, forbidden_values=()):
        self.root = Path(root or Path(__file__).resolve().parents[3] / "data" / "checkpoints").resolve()
        if max_size_bytes < 1:
            raise ValueError("Checkpoint size limit must be positive")
        self.max_size_bytes = max_size_bytes
        self.forbidden_values = tuple(forbidden_values)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _path(self, task_id: str, suffix: str = ".json") -> Path:
        validate_task_id(task_id)
        if self.root.resolve() != self.root:
            raise CheckpointError("Checkpoint root was redirected")
        path = self.root / f"cp-{task_id}{suffix}"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CheckpointError("Checkpoint path is not an application-owned regular file")
        if path.resolve().parent != self.root:
            raise CheckpointError("Checkpoint path escaped storage root")
        return path

    @contextmanager
    def _lock(self, task_id: str, suffix: str):
        path = self._path(task_id, suffix)
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        acquired = False
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise CheckpointError("Invalid lock file")
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise CheckpointBusy("Task checkpoint is locked") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise CheckpointBusy("Task checkpoint is locked") from exc
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == "nt":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def lease(self, task_id: str):
        """Hold for the entire run/resume, not just an individual save."""
        return self._lock(task_id, ".lease")

    def load(self, task_id: str) -> AgentCheckpoint:
        path = self._path(task_id)
        if path.stat().st_size > self.max_size_bytes:
            raise CheckpointError("Checkpoint exceeds size limit")
        try:
            with path.open("rb") as stream:
                raw = stream.read(self.max_size_bytes + 1)
            if len(raw) > self.max_size_bytes:
                raise CheckpointError("Checkpoint exceeds size limit")
            data = json.loads(raw)
            reject_credentials(data, self.forbidden_values)
            checkpoint = AgentCheckpoint.model_validate(data)
        except (ValueError, TypeError) as exc:
            raise CheckpointError("Corrupt or unsupported checkpoint") from exc
        if checkpoint.task_id != task_id:
            raise CheckpointError("Checkpoint filename/task identity mismatch")
        return checkpoint

    def save(self, checkpoint: AgentCheckpoint) -> AgentCheckpoint:
        # Validate a fresh JSON-compatible projection, even after model_copy updates.
        data = checkpoint.model_dump(mode="json")
        reject_credentials(data, self.forbidden_values)
        with self._lock(checkpoint.task_id, ".lock"):
            path = self._path(checkpoint.task_id)
            previous = self.load(checkpoint.task_id) if path.exists() else None
            revision = previous.revision if previous else 0
            if checkpoint.revision != revision:
                raise CheckpointError("Stale checkpoint revision")
            if previous and previous.status in {"completed", "failed", "cancelled", "budget_exhausted", "verification_failed"}:
                old_data = previous.model_dump(mode="json")
                frozen = set(AgentCheckpoint.model_fields) - {"trace", "revision", "updated_at"}
                if any(data[name] != old_data[name] for name in frozen):
                    raise CheckpointError("Terminal checkpoint cannot be overwritten")
                frozen_trace = set(data["trace"]) - {"events", "next_event_id"}
                if any(data["trace"][name] != old_data["trace"][name] for name in frozen_trace):
                    raise CheckpointError("Terminal trace facts cannot be overwritten")
                if checkpoint.trace.next_event_id < previous.trace.next_event_id:
                    raise CheckpointError("Terminal trace cursor cannot regress")
                prior_events = previous.trace.events
                if checkpoint.trace.events[:len(prior_events)] != prior_events or any(
                    event.agent_action not in {"checkpoint_loaded", "resume_rejected", "recovery_required"}
                    for event in checkpoint.trace.events[len(prior_events):]
                ):
                    raise CheckpointError("Terminal trace can only append resume rejection events")
            data.update(revision=revision + 1, updated_at=timestamp())
            saved = AgentCheckpoint.model_validate(data)
            encoded = json.dumps(saved.model_dump(mode="json"), ensure_ascii=False, allow_nan=False).encode("utf-8")
            if len(encoded) > self.max_size_bytes:
                raise CheckpointError("Checkpoint exceeds size limit")
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.root, prefix=f".cp-{checkpoint.task_id}-", suffix=".tmp", delete=False) as stream:
                    temp_path = Path(stream.name)
                    os.chmod(temp_path, 0o600)
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, path)
                self._sync_directory()
            finally:
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()
            return saved

    def _sync_directory(self) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            return
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                os.fsync(fd)
            except OSError as exc:
                if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                    raise
        finally:
            os.close(fd)

    def list_tasks(self) -> list[str]:
        return sorted(self.load(path.name[3:-5]).task_id for path in self.root.glob("cp-*.json"))

    def delete(self, task_id: str) -> None:
        with self.lease(task_id), self._lock(task_id, ".lock"):
            self._path(task_id).unlink(missing_ok=True)
            self._sync_directory()
