"""app/agent/trace.py — 结构化可观察 Execution Trace 记录器。

记录 Agent 执行过程中的每一步决策、工具调用、耗时、状态与错误，
为评估指标计算与事后调试提供统一、客观的 Trace 轨迹。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


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
