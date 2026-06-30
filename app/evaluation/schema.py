"""EvalTask / EvalResult — 评测任务与结果的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvalLayer(str, Enum):
    """Evaluation layer — determines where and how an eval task runs."""

    UNIT = "unit"              # CI — deterministic, mock deps
    INTEGRATION = "integration"  # Local — real embedding, optional LLM
    STRESS = "stress"          # Manual — multi-file, retry, recovery


@dataclass
class EvalTask:
    """单个评测任务的定义。"""

    id: str
    name: str
    difficulty: str  # easy / medium / hard
    category: str  # bug-fix / enhancement
    task: str  # 给 Agent 的 prompt
    file: str = ""  # 目标文件路径（相对于 workspace）
    test_target: str = ""  # pytest 目标（如 tests/test_foo.py::TestClass::test_method）
    expected_behavior: str = ""
    success_criteria: list[str] = field(default_factory=list)
    reference_fix: str = ""
    layer: EvalLayer = EvalLayer.INTEGRATION

    @classmethod
    def from_dict(cls, d: dict) -> EvalTask:
        return cls(
            id=d["id"],
            name=d["name"],
            difficulty=d.get("difficulty", "unknown"),
            category=d.get("category", "unknown"),
            task=d["task"],
            file=d.get("file", ""),
            test_target=d.get("test_target", ""),
            expected_behavior=d.get("expected_behavior", ""),
            success_criteria=d.get("success_criteria", []),
            reference_fix=d.get("reference_fix", ""),
            layer=EvalLayer(d.get("layer", "integration")),
        )


@dataclass
class ToolCallRecord:
    """记录单次工具调用的结果。"""

    tool_name: str = ""
    success: bool = True
    output: str = ""
    observation: str = ""


@dataclass
class EvalResult:
    """单个任务的评测结果。"""

    task_id: str
    success: bool = False
    final_answer: str = ""
    tool_calls_count: int = 0
    duration_ms: int = 0
    error: str = ""
    # pytest 结果
    test_success: bool = False
    passed: int = 0
    failed: int = 0
    # 错误归因
    error_type: str = ""
    error_reason: str = ""
    # 工具调用详情（高级指标用）
    steps: list[ToolCallRecord] = field(default_factory=list)
    tool_results: list[ToolCallRecord] = field(default_factory=list)
    # Stress test tracking
    is_retry_result: bool = False  # 是否为重试后的结果
    retry_count: int = 0  # 重试次数
    files_modified: list[str] = field(default_factory=list)  # 实际修改的文件列表
    # D32: memory tracking
    memory_utilized: bool = False  # whether historical memory was injected

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "final_answer": self.final_answer,
            "tool_calls_count": self.tool_calls_count,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "test_success": self.test_success,
            "passed": self.passed,
            "failed": self.failed,
            "error_type": self.error_type,
            "error_reason": self.error_reason,
        }

    def to_unified(self) -> dict:
        """Convert to AgentFinalOutput-compatible dict (D23)."""
        tools_used = []
        seen: set = set()
        for s in self.steps:
            if s.tool_name and s.tool_name not in seen:
                seen.add(s.tool_name)
                tools_used.append(s.tool_name)

        execution_trace = []
        for s in self.steps:
            execution_trace.append({
                "step_id": len(execution_trace) + 1,
                "action": s.observation[:200] if s.observation else "",
                "tool": s.tool_name,
                "input": "",
                "output": s.observation[:500] if s.observation else "",
                "success": s.success,
                "duration_ms": 0,
            })

        return {
            "mode": "eval",
            "summary": self.final_answer,
            "execution_trace": execution_trace,
            "tools_used": tools_used,
            "metrics": {
                "task_success": self.success,
                "tool_calls": self.tool_calls_count,
                "duration_ms": self.duration_ms,
                "test_pass": self.test_success,
                "test_passed": self.passed,
                "test_failed": self.failed,
                "security_block": False,
                "evidence_count": 0,
            },
            "evidence": [],
            "confidence": 0.0,
            "security_warnings": [],
        }
