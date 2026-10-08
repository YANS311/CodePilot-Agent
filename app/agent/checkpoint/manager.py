"""Workspace identity and conservative recovery policy over existing runtime state."""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from app.agent.budget import ToolBudget
from app.agent.trace import ExecutionTrace
from app.models.state import AgentState

from .models import AgentCheckpoint, CheckpointError, PendingCall, TraceSnapshot, digest
from .store import CheckpointStore


def workspace_fingerprint(root: str | Path) -> str:
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise CheckpointError("Workspace must be a directory")
    info = root.stat()
    result = hashlib.sha256(f"{root}|{info.st_dev}|{info.st_ino}".encode())
    count, size = 0, 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(name for name in dirs if name not in {".git", "__pycache__", ".pytest_cache"})
        for name in dirs + sorted(files):
            path = Path(current) / name
            if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
                raise CheckpointError("Linked workspace entries are unsupported for checkpointing")
        for name in sorted(files):
            path = Path(current) / name
            count += 1
            size += path.stat().st_size
            if count > 10000 or size > 256 * 1024 * 1024:
                raise CheckpointError("Workspace fingerprint limit exceeded")
            result.update(path.relative_to(root).as_posix().encode())
            result.update(b"\0")
            with path.open("rb") as stream:
                file_hash = hashlib.file_digest(stream, "sha256").digest()
            result.update(file_hash)
    return result.hexdigest()


def tools_fingerprint(schemas) -> str:
    return digest(json.dumps(schemas, sort_keys=True, ensure_ascii=False))


def estimator_identity(manager) -> str:
    cls = type(manager.estimator)
    return f"{cls.__module__}.{cls.__qualname__}"


class CheckpointManager:
    def __init__(self, store: CheckpointStore):
        self.store = store

    def validate_storage_boundary(self, workspace: str) -> str:
        root = Path(workspace).resolve(strict=True)
        storage = self.store.root.resolve(strict=True)
        if root == storage or root in storage.parents or storage in root.parents:
            raise CheckpointError("Checkpoint storage must be disjoint from the Agent workspace")
        return str(root)

    def create(self, task_id, task, workspace, max_calls, verification, context_manager, schemas, trace):
        root = self.validate_storage_boundary(workspace)
        return AgentCheckpoint(
            task_id=task_id, task=task, task_digest=digest(task), workspace_root=root,
            workspace_digest=workspace_fingerprint(root),
            runtime=AgentState(task_id=task_id, workspace_path=root, max_iterations=max_calls),
            budget=ToolBudget(max_calls=max_calls), verification=verification,
            context_budget=context_manager.budget, estimator_name=estimator_identity(context_manager),
            tools_digest=tools_fingerprint(schemas), trace=self.capture_trace(trace),
        )

    @staticmethod
    def capture_trace(trace: ExecutionTrace, reserve: int = 1) -> TraceSnapshot:
        return TraceSnapshot(
            events=list(trace.events), steps=list(trace.steps),
            next_event_id=trace.next_event_id + reserve,
            total_latency_ms=trace.total_latency_ms, status=trace.status, created_at=trace.created_at,
        )

    def validate_resume(self, checkpoint, workspace, max_calls, verification, context_manager, schemas):
        root = self.validate_storage_boundary(workspace)
        if checkpoint.in_flight:
            return "indeterminate_tool_exchange"
        if checkpoint.workspace_root != root or checkpoint.workspace_digest != workspace_fingerprint(root):
            return "workspace_identity_mismatch"
        if checkpoint.budget.max_calls != max_calls:
            return "tool_budget_policy_changed"
        if asdict(checkpoint.verification) != asdict(verification):
            return "verification_policy_changed"
        if checkpoint.context_budget != context_manager.budget or checkpoint.estimator_name != estimator_identity(context_manager):
            return "context_policy_changed"
        if checkpoint.tools_digest != tools_fingerprint(schemas):
            return "tool_registry_changed"
        if checkpoint.next_step == "initializing":
            return "initial_context_unavailable"
        return None

    @staticmethod
    def pending_calls(calls) -> list[PendingCall]:
        # No plugin name heuristic grants replay permission. All uncertain calls fail closed.
        read_only = {"read_file", "search_code", "git_diff", "git_status"}
        return [PendingCall(id=call.id, name=call.name, replay_class="read_only" if call.name in read_only else "side_effecting") for call in calls]
