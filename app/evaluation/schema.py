"""EvalTask / EvalResult — 评测任务与结果的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field


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
        )


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
