"""app/agent/trace.py — 结构化可观察 Execution Trace 记录器。

记录 Agent 执行过程中的每一步决策、工具调用、耗时、状态与错误，
为评估指标计算与事后调试提供统一、客观的 Trace 轨迹。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


TRACE_EVENT_SCHEMA_VERSION = "0.1"


def _utc_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp suitable for JSON traces."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TraceEvent:
    """Draft event contract for the converged harness trace stream.

    This model is additive in PR0. Existing ExecutionTrace and API output
    remain unchanged until producers and consumers migrate in later PRs.
    """

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
        return json.dumps(self.to_dict(), ensure_ascii=False)


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
    tool_selection: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def record_tool_selection(
        self,
        candidate_count: int,
        selected_tools: List[str],
        reason: str = "",
        scores: Optional[Dict[str, float]] = None,
    ) -> None:
        """记录动态工具检索与过滤决策信息。"""
        self.tool_selection = {
            "candidate_count": candidate_count,
            "selected_tools": selected_tools,
            "scores": scores or {},
            "reason": reason,
        }

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

    def to_dict(self) -> Dict[str, Any]:
        """导出为字典。"""
        return asdict(self)

    def export_jsonl(self, path: str | Path) -> None:
        """将轨迹导出为 JSONL 文件。"""
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
