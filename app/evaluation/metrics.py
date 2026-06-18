"""metrics — 评测指标统计。"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evaluation.schema import EvalResult, EvalTask


@dataclass
class EvalMetrics:
    """评测汇总指标。"""

    total_tasks: int = 0
    successful_tasks: int = 0
    task_success_rate: float = 0.0

    total_tests_passed: int = 0
    total_tests_failed: int = 0
    test_pass_rate: float = 0.0

    avg_tool_calls: float = 0.0
    avg_duration_ms: float = 0.0

    # 新增指标
    pass_at_1: float = 0.0  # Pass@1: 单次尝试成功率
    tool_efficiency: float = 0.0  # Tool Efficiency: 成功任务的工具调用效率
    tool_calls_per_success: float = 0.0  # 每个成功任务的平均工具调用次数

    # 错误分布
    error_distribution: dict[str, int] = field(default_factory=dict)

    # 按难度分组
    success_by_difficulty: dict[str, dict] = field(default_factory=dict)
    # 按类别分组
    success_by_category: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_tasks": self.total_tasks,
            "successful_tasks": self.successful_tasks,
            "task_success_rate": self.task_success_rate,
            "total_tests_passed": self.total_tests_passed,
            "total_tests_failed": self.total_tests_failed,
            "test_pass_rate": self.test_pass_rate,
            "avg_tool_calls": self.avg_tool_calls,
            "avg_duration_ms": self.avg_duration_ms,
            "pass_at_1": self.pass_at_1,
            "tool_efficiency": self.tool_efficiency,
            "tool_calls_per_success": self.tool_calls_per_success,
            "error_distribution": self.error_distribution,
            "success_by_difficulty": self.success_by_difficulty,
            "success_by_category": self.success_by_category,
        }


def compute_metrics(
    results: list[EvalResult],
    tasks: list[EvalTask],
) -> EvalMetrics:
    """根据评测结果和任务定义计算汇总指标。"""
    if not results:
        return EvalMetrics()

    task_map = {t.id: t for t in tasks}
    total = len(results)
    successful = sum(1 for r in results if r.success)

    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_tests = total_passed + total_failed

    total_tools = sum(r.tool_calls_count for r in results)
    total_duration = sum(r.duration_ms for r in results)

    # Pass@1: 单次尝试成功率 (成功率)
    pass_at_1 = successful / total if total else 0.0

    # Tool Efficiency: 成功任务的工具调用效率 (成功任务数 / 总工具调用数)
    successful_tools = sum(r.tool_calls_count for r in results if r.success)
    tool_efficiency = successful / successful_tools if successful_tools > 0 else 0.0

    # Tool Calls per Success: 每个成功任务的平均工具调用次数
    tool_calls_per_success = successful_tools / successful if successful > 0 else 0.0

    # 错误分布统计
    error_distribution: dict[str, int] = {}
    for r in results:
        if not r.success and r.error_type:
            error_distribution[r.error_type] = error_distribution.get(r.error_type, 0) + 1

    # 按难度分组
    by_difficulty: dict[str, dict] = {}
    for r in results:
        t = task_map.get(r.task_id)
        diff = t.difficulty if t else "unknown"
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "success": 0}
        by_difficulty[diff]["total"] += 1
        if r.success:
            by_difficulty[diff]["success"] += 1

    for d in by_difficulty.values():
        d["rate"] = d["success"] / d["total"] if d["total"] else 0.0

    # 按类别分组
    by_category: dict[str, dict] = {}
    for r in results:
        t = task_map.get(r.task_id)
        cat = t.category if t else "unknown"
        if cat not in by_category:
            by_category[cat] = {"total": 0, "success": 0}
        by_category[cat]["total"] += 1
        if r.success:
            by_category[cat]["success"] += 1

    for c in by_category.values():
        c["rate"] = c["success"] / c["total"] if c["total"] else 0.0

    return EvalMetrics(
        total_tasks=total,
        successful_tasks=successful,
        task_success_rate=successful / total if total else 0.0,
        total_tests_passed=total_passed,
        total_tests_failed=total_failed,
        test_pass_rate=total_passed / total_tests if total_tests else 0.0,
        avg_tool_calls=total_tools / total if total else 0.0,
        avg_duration_ms=total_duration / total if total else 0.0,
        pass_at_1=pass_at_1,
        tool_efficiency=tool_efficiency,
        tool_calls_per_success=tool_calls_per_success,
        error_distribution=error_distribution,
        success_by_difficulty=by_difficulty,
        success_by_category=by_category,
    )
