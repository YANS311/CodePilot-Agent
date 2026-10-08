"""app/agent/trace.py — 结构化可观察 Execution Trace 记录器。

记录 Agent 执行过程中的每一步决策、工具调用、耗时、状态与错误，
为评估指标计算与事后调试提供统一、客观的 Trace 轨迹。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


TRACE_EVENT_SCHEMA_VERSION = "0.1"
logger = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp suitable for JSON traces."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    """Versioned event contract for the converged harness trace stream."""

    task_id: str
    step_id: int
    agent_action: str
    timestamp: str = field(default_factory=_utc_timestamp)
    tool_name: Optional[str] = None
    tool_input: Dict[str, Any] = field(default_factory=dict)
    tool_output: Any = None
    execution_result: str = "unknown"
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = TRACE_EVENT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Export the versioned event as a JSON-serializable dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Export the versioned event as UTF-8 friendly JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class TraceSink(Protocol):
    """Destination for normalized trace events."""

    def emit(self, event: TraceEvent) -> None:
        """Persist or forward one trace event."""


class InMemoryTraceSink:
    """Thread-safe sink useful for APIs, tests, and in-process evaluation."""

    def __init__(self) -> None:
        self._events: List[TraceEvent] = []
        self._lock = threading.Lock()

    def emit(self, event: TraceEvent) -> None:
        with self._lock:
            self._events.append(event)

    def snapshot(self) -> List[TraceEvent]:
        with self._lock:
            return list(self._events)


class JsonlTraceSink:
    """Append one versioned TraceEvent per line for durable replay."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def emit(self, event: TraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(event.to_json() + "\n")


@dataclass
class ExecutionStepTrace:
    """单个执行步骤的结构化记录。"""

    step: int
    tool_name: str
    arguments: Dict[str, Any]
    status: str  # "success" | "error" | "permission_blocked"
    latency_ms: float
    decision: str = ""
    error: Optional[str] = None
    output_snippet: str = ""


@dataclass
class ExecutionTrace:
    """单次任务完整的可观察执行轨迹。"""

    task: str
    steps: List[ExecutionStepTrace] = field(default_factory=list)
    total_latency_ms: float = 0.0
    status: str = "running"  # "completed" | "budget_exhausted" | "error"
    active_skill: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    events: List[TraceEvent] = field(default_factory=list)
    sink: Optional[TraceSink] = field(default=None, repr=False, compare=False)
    _next_event_id: int = field(default=1, init=False, repr=False, compare=False)

    def record_event(
        self,
        agent_action: str,
        *,
        tool_name: Optional[str] = None,
        tool_input: Optional[Dict[str, Any]] = None,
        tool_output: Any = None,
        execution_result: str = "unknown",
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TraceEvent:
        """Create and publish the next monotonic event for this task."""
        event = TraceEvent(
            task_id=self.task_id,
            step_id=self._next_event_id,
            agent_action=agent_action,
            tool_name=tool_name,
            tool_input=dict(tool_input or {}),
            tool_output=tool_output,
            execution_result=execution_result,
            duration_ms=duration_ms,
            metadata=dict(metadata or {}),
        )
        self._next_event_id += 1
        self.events.append(event)
        if self.sink is not None:
            try:
                self.sink.emit(event)
            except Exception as exc:
                logger.warning("Trace sink failed for task %s: %s", self.task_id, exc)
        return event

    def add_step(
        self,
        step: int,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        latency_ms: float,
        decision: str = "",
        error: Optional[str] = None,
        output: str = "",
    ) -> None:
        """追加单步记录。"""
        snippet = output[:200] if output else ""
        step_trace = ExecutionStepTrace(
            step=step,
            tool_name=tool_name,
            arguments=arguments,
            status=status,
            latency_ms=latency_ms,
            decision=decision,
            error=error,
            output_snippet=snippet,
        )
        self.steps.append(step_trace)
        self.total_latency_ms += latency_ms
        self.record_event(
            "tool_call",
            tool_name=tool_name,
            tool_input=arguments,
            tool_output=snippet,
            execution_result=status,
            duration_ms=latency_ms,
            metadata={
                "decision": decision,
                "error": error[:200] if error else None,
                "legacy_step": step,
            },
        )

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return {
            "task": self.task,
            "steps": [asdict(step) for step in self.steps],
            "total_latency_ms": self.total_latency_ms,
            "status": self.status,
            "active_skill": self.active_skill,
            "created_at": self.created_at,
            "task_id": self.task_id,
            "events": [event.to_dict() for event in self.events],
        }

    def export_jsonl(self, path: str | Path) -> None:
        """将轨迹导出为 JSONL 文件。"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
