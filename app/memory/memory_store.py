"""memory_store.py — Three memory types for CodePilot Agent.

1. TaskMemory: history of executed tasks (prompt, result, success, tool_trace)
2. ErrorMemory: error patterns and fix strategies
3. RepoMemory: workspace/file summaries for cross-session reuse

All stored in-memory. No vector DB, no embedding, no external storage.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TaskMemory:
    """Record of a previously executed task."""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    prompt: str = ""
    result: str = ""
    success: bool = False
    tool_calls_count: int = 0
    tool_trace: list[str] = field(default_factory=list)  # tool names in order
    workspace_id: str = ""
    duration_ms: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "result": self.result[:200],
            "success": self.success,
            "tool_calls_count": self.tool_calls_count,
            "tool_trace": self.tool_trace,
            "workspace_id": self.workspace_id,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
        }


@dataclass
class ErrorMemory:
    """Record of an error pattern and its fix strategy."""
    error_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    error_type: str = ""  # no_code_change, test_failed, budget_exhausted, etc.
    context: str = ""  # what task was being attempted
    fix_strategy: str = ""  # what fixed it (or empty if unknown)
    tool_trace: list[str] = field(default_factory=list)
    workspace_id: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "context": self.context[:200],
            "fix_strategy": self.fix_strategy[:200],
            "tool_trace": self.tool_trace,
            "workspace_id": self.workspace_id,
            "created_at": self.created_at,
        }


@dataclass
class RepoMemory:
    """Record of a workspace analysis result."""
    repo_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    workspace_id: str = ""
    file_summary: str = ""  # compressed file list
    module_map: dict[str, str] = field(default_factory=dict)  # module → role
    analysis_result: str = ""  # full analysis text
    confidence: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "repo_id": self.repo_id,
            "workspace_id": self.workspace_id,
            "file_summary": self.file_summary[:200],
            "module_count": len(self.module_map),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


class InMemoryStore:
    """In-memory storage for all three memory types.

    Thread-safe for single-machine use.
    """

    def __init__(self) -> None:
        self._tasks: list[TaskMemory] = []
        self._errors: list[ErrorMemory] = []
        self._repos: list[RepoMemory] = []
        self._max_tasks: int = 200
        self._max_errors: int = 100
        self._max_repos: int = 50

    # ── Task Memory ──────────────────────────────────────────

    def add_task(self, memory: TaskMemory) -> None:
        self._tasks.append(memory)
        if len(self._tasks) > self._max_tasks:
            self._tasks = self._tasks[-self._max_tasks:]

    def get_tasks(self, limit: int = 50) -> list[TaskMemory]:
        return list(reversed(self._tasks[-limit:]))

    def query_tasks(self, keywords: list[str], limit: int = 10) -> list[TaskMemory]:
        """Simple keyword matching against task prompts."""
        results = []
        for mem in reversed(self._tasks):
            prompt_lower = mem.prompt.lower()
            if any(kw.lower() in prompt_lower for kw in keywords):
                results.append(mem)
                if len(results) >= limit:
                    break
        return results

    # ── Error Memory ─────────────────────────────────────────

    def add_error(self, memory: ErrorMemory) -> None:
        self._errors.append(memory)
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

    def get_errors(self, limit: int = 50) -> list[ErrorMemory]:
        return list(reversed(self._errors[-limit:]))

    def query_errors(self, error_type: str = "", keywords: list[str] | None = None, limit: int = 10) -> list[ErrorMemory]:
        """Query errors by type and/or keywords."""
        results = []
        for mem in reversed(self._errors):
            if error_type and mem.error_type != error_type:
                continue
            if keywords:
                ctx = (mem.context + " " + mem.fix_strategy).lower()
                if not any(kw.lower() in ctx for kw in keywords):
                    continue
            results.append(mem)
            if len(results) >= limit:
                break
        return results

    # ── Repo Memory ──────────────────────────────────────────

    def add_repo(self, memory: RepoMemory) -> None:
        self._repos.append(memory)
        if len(self._repos) > self._max_repos:
            self._repos = self._repos[-self._max_repos:]

    def get_repos(self, limit: int = 20) -> list[RepoMemory]:
        return list(reversed(self._repos[-limit:]))

    def query_repos(self, workspace_id: str) -> Optional[RepoMemory]:
        """Find the latest repo memory for a workspace."""
        for mem in reversed(self._repos):
            if mem.workspace_id == workspace_id:
                return mem
        return None

    # ── Stats ────────────────────────────────────────────────

    def stats(self) -> dict:
        return {
            "task_count": len(self._tasks),
            "error_count": len(self._errors),
            "repo_count": len(self._repos),
        }
