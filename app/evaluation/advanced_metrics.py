"""advanced_metrics.py — Coding Agent 高级评测指标。

参考 RAGAS 分层评估思想，定义适合 Coding Agent 的 7 项指标。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.evaluation.schema import EvalResult, EvalTask


@dataclass
class AdvancedMetrics:
    """高级评测指标汇总。"""

    # 1. Task Success Rate — 任务是否最终通过
    task_success_rate: float = 0.0

    # 2. Test Pass Rate — 测试是否通过
    test_pass_rate: float = 0.0

    # 3. Tool Call Validity — 工具调用是否合法
    tool_call_validity: float = 0.0

    # 4. Verification Completion Rate — 修改后是否执行 run_tests
    verification_completion_rate: float = 0.0

    # 5. Code Change Validity — 是否实际调用 write_file 并产生有效修改
    code_change_validity: float = 0.0

    # 6. Planning Efficiency — 成功任务平均工具调用次数
    planning_efficiency: float = 0.0

    # 7. Security Block Rate — 攻击样例中被正确拦截的比例
    security_block_rate: float = 0.0

    # 详细统计
    total_tasks: int = 0
    successful_tasks: int = 0
    total_tool_calls: int = 0
    valid_tool_calls: int = 0
    tasks_with_verification: int = 0
    tasks_with_code_change: int = 0
    security_tasks_total: int = 0
    security_tasks_blocked: int = 0

    def to_dict(self) -> dict:
        return {
            "task_success_rate": round(self.task_success_rate, 4),
            "test_pass_rate": round(self.test_pass_rate, 4),
            "tool_call_validity": round(self.tool_call_validity, 4),
            "verification_completion_rate": round(self.verification_completion_rate, 4),
            "code_change_validity": round(self.code_change_validity, 4),
            "planning_efficiency": round(self.planning_efficiency, 4),
            "security_block_rate": round(self.security_block_rate, 4),
            "details": {
                "total_tasks": self.total_tasks,
                "successful_tasks": self.successful_tasks,
                "total_tool_calls": self.total_tool_calls,
                "valid_tool_calls": self.valid_tool_calls,
                "tasks_with_verification": self.tasks_with_verification,
                "tasks_with_code_change": self.tasks_with_code_change,
                "security_tasks_total": self.security_tasks_total,
                "security_tasks_blocked": self.security_tasks_blocked,
            },
        }


def compute_advanced_metrics(
    results: list[EvalResult],
    tasks: list[EvalTask],
    security_results: Optional[list[dict]] = None,
) -> AdvancedMetrics:
    """根据评测结果计算高级指标。"""
    m = AdvancedMetrics()

    # 处理 security 结果（即使没有 eval results）
    security_total = 0
    security_blocked = 0
    if security_results:
        security_total = len(security_results)
        security_blocked = sum(
            1 for sr in security_results if sr.get("blocked", False)
        )
    m.security_tasks_total = security_total
    m.security_tasks_blocked = security_blocked
    m.security_block_rate = (
        security_blocked / security_total if security_total else 0.0
    )

    if not results:
        return m

    total = len(results)
    successful = sum(1 for r in results if r.success)

    # 1. Task Success Rate
    task_success_rate = successful / total if total else 0.0

    # 2. Test Pass Rate
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_tests = total_passed + total_failed
    test_pass_rate = total_passed / total_tests if total_tests else 0.0

    # 3. Tool Call Validity
    # 合法调用 = 总调用 - 安全拦截 - 伪造工具调用 - 参数错误
    total_tools = sum(r.tool_calls_count for r in results)
    blocked_tools = sum(
        1 for r in results
        for tr in r.tool_results
        if not tr.success and "SECURITY_BLOCKED" in tr.output
    )
    fake_tools = sum(
        1 for r in results
        for s in r.steps
        if "fake_tool_call" in s.observation.lower()
    )
    valid_tools = total_tools - blocked_tools - fake_tools
    tool_call_validity = valid_tools / total_tools if total_tools else 1.0

    # 4. Verification Completion Rate
    # 修改代码后执行了 run_tests 的比例
    tasks_with_verification = 0
    for r in results:
        has_write = any(s.tool_name == "write_file" for s in r.steps)
        has_test = any(s.tool_name == "run_tests" for s in r.steps)
        if has_write and has_test:
            tasks_with_verification += 1

    # 只统计有 write_file 的任务
    tasks_with_write = sum(
        1 for r in results
        if any(s.tool_name == "write_file" for s in r.steps)
    )
    verification_rate = (
        tasks_with_verification / tasks_with_write if tasks_with_write else 1.0
    )

    # 5. Code Change Validity
    # 调用了 write_file 且最终成功的比例
    tasks_with_code_change = 0
    for r in results:
        has_write = any(s.tool_name == "write_file" for s in r.steps)
        if has_write:
            tasks_with_code_change += 1
    code_change_validity = tasks_with_code_change / total if total else 0.0

    # 6. Planning Efficiency
    # 成功任务的平均工具调用次数
    successful_tools = sum(r.tool_calls_count for r in results if r.success)
    planning_efficiency = successful_tools / successful if successful else 0.0

    # Update m with computed values
    m.task_success_rate = task_success_rate
    m.test_pass_rate = test_pass_rate
    m.tool_call_validity = tool_call_validity
    m.verification_completion_rate = verification_rate
    m.code_change_validity = code_change_validity
    m.planning_efficiency = planning_efficiency
    m.total_tasks = total
    m.successful_tasks = successful
    m.total_tool_calls = total_tools
    m.valid_tool_calls = valid_tools
    m.tasks_with_verification = tasks_with_verification
    m.tasks_with_code_change = tasks_with_code_change

    return m
