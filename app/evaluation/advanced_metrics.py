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

    # 8. Stress-specific metrics
    recovery_rate: float = 0.0  # 重试后成功的比例
    multi_file_success_rate: float = 0.0  # 多文件任务成功率
    first_pass_rate: float = 0.0  # 首次尝试即成功的比例
    retry_success_rate: float = 0.0  # 重试后成功的比例（与 recovery_rate 区分）
    tool_efficiency_under_stress: float = 0.0  # 压力下工具效率

    # 9. Memory-specific metrics
    memory_hit_rate: float = 0.0  # 有多少比例的任务命中了历史 memory
    memory_utilization_effect: float = 0.0  # memory-utilized 任务的成功率 vs 未利用的成功率
    similar_task_recall: float = 0.0  # 相似任务的历史方案召回率

    # 10. Routing-specific metrics
    routing_accuracy: float = 0.0  # 路由正确率（intent 匹配任务类别）
    routing_fallback_rate: float = 0.0  # LLM/default 层的使用比例
    rule_layer_rate: float = 0.0  # Rule 层命中比例
    embedding_layer_rate: float = 0.0  # Embedding 层命中比例

    # 详细统计
    total_tasks: int = 0
    successful_tasks: int = 0
    total_tool_calls: int = 0
    valid_tool_calls: int = 0
    tasks_with_verification: int = 0
    tasks_with_code_change: int = 0
    security_tasks_total: int = 0
    security_tasks_blocked: int = 0
    # Stress details
    stress_total_tasks: int = 0
    stress_successful_tasks: int = 0
    multi_file_tasks: int = 0
    multi_file_successful: int = 0
    first_pass_tasks: int = 0
    first_pass_successful: int = 0
    retry_tasks: int = 0
    retry_successful: int = 0

    def to_dict(self) -> dict:
        return {
            "task_success_rate": round(self.task_success_rate, 4),
            "test_pass_rate": round(self.test_pass_rate, 4),
            "tool_call_validity": round(self.tool_call_validity, 4),
            "verification_completion_rate": round(self.verification_completion_rate, 4),
            "code_change_validity": round(self.code_change_validity, 4),
            "planning_efficiency": round(self.planning_efficiency, 4),
            "security_block_rate": round(self.security_block_rate, 4),
            "recovery_rate": round(self.recovery_rate, 4),
            "multi_file_success_rate": round(self.multi_file_success_rate, 4),
            "first_pass_rate": round(self.first_pass_rate, 4),
            "retry_success_rate": round(self.retry_success_rate, 4),
            "tool_efficiency_under_stress": round(self.tool_efficiency_under_stress, 4),
            "memory_hit_rate": round(self.memory_hit_rate, 4),
            "memory_utilization_effect": round(self.memory_utilization_effect, 4),
            "similar_task_recall": round(self.similar_task_recall, 4),
            "routing_accuracy": round(self.routing_accuracy, 4),
            "routing_fallback_rate": round(self.routing_fallback_rate, 4),
            "rule_layer_rate": round(self.rule_layer_rate, 4),
            "embedding_layer_rate": round(self.embedding_layer_rate, 4),
            "details": {
                "total_tasks": self.total_tasks,
                "successful_tasks": self.successful_tasks,
                "total_tool_calls": self.total_tool_calls,
                "valid_tool_calls": self.valid_tool_calls,
                "tasks_with_verification": self.tasks_with_verification,
                "tasks_with_code_change": self.tasks_with_code_change,
                "security_tasks_total": self.security_tasks_total,
                "security_tasks_blocked": self.security_tasks_blocked,
                "stress_total_tasks": self.stress_total_tasks,
                "stress_successful_tasks": self.stress_successful_tasks,
                "multi_file_tasks": self.multi_file_tasks,
                "multi_file_successful": self.multi_file_successful,
                "first_pass_tasks": self.first_pass_tasks,
                "first_pass_successful": self.first_pass_successful,
                "retry_tasks": self.retry_tasks,
                "retry_successful": self.retry_successful,
            },
        }


def compute_advanced_metrics(
    results: list[EvalResult],
    tasks: list[EvalTask],
    security_results: Optional[list[dict]] = None,
    routing_stats: Optional[dict] = None,
) -> AdvancedMetrics:
    """根据评测结果计算高级指标。

    Args:
        routing_stats: Optional dict from IntentRouter.stats() with
            layer_counts and intent_counts.
    """
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

    # 8. Stress-specific metrics
    # Build task_id → EvalTask lookup for category info
    task_lookup = {t.id: t for t in tasks} if tasks else {}

    STRESS_CATEGORIES = {"multi-file-bug-fix", "mixed-instruction", "repo-understand-modify", "partial-failure-recovery"}
    stress_results = [r for r in results if task_lookup.get(r.task_id, EvalTask(id="", name="", difficulty="", category="", task="")).category in STRESS_CATEGORIES]
    multi_file_results = [r for r in stress_results if task_lookup.get(r.task_id, EvalTask(id="", name="", difficulty="", category="", task="")).category == "multi-file-bug-fix"]

    # First-pass vs retry
    first_pass_results = [r for r in results if not r.is_retry_result]
    retry_results = [r for r in results if r.is_retry_result]

    # Compute rates
    m.stress_total_tasks = len(stress_results)
    m.stress_successful_tasks = sum(1 for r in stress_results if r.success)
    m.multi_file_tasks = len(multi_file_results)
    m.multi_file_successful = sum(1 for r in multi_file_results if r.success)
    m.first_pass_tasks = len(first_pass_results)
    m.first_pass_successful = sum(1 for r in first_pass_results if r.success)
    m.retry_tasks = len(retry_results)
    m.retry_successful = sum(1 for r in retry_results if r.success)

    m.recovery_rate = (
        m.retry_successful / m.retry_tasks if m.retry_tasks else 0.0
    )
    m.multi_file_success_rate = (
        m.multi_file_successful / m.multi_file_tasks if m.multi_file_tasks else 0.0
    )
    m.first_pass_rate = (
        m.first_pass_successful / m.first_pass_tasks if m.first_pass_tasks else 0.0
    )
    m.retry_success_rate = m.recovery_rate  # alias

    # Tool efficiency under stress: successful stress tasks avg tool calls
    stress_successful_tools = sum(
        r.tool_calls_count for r in stress_results if r.success
    )
    stress_successful_count = sum(1 for r in stress_results if r.success)
    m.tool_efficiency_under_stress = (
        stress_successful_tools / stress_successful_count
        if stress_successful_count else 0.0
    )

    # 9. Memory-specific metrics
    memory_utilized = [r for r in results if r.memory_utilized]
    memory_not_utilized = [r for r in results if not r.memory_utilized]

    # Memory Hit Rate: % of tasks that had memory context injected
    m.memory_hit_rate = len(memory_utilized) / total if total else 0.0

    # Memory Utilization Effect: success rate with memory vs without
    mem_success = sum(1 for r in memory_utilized if r.success)
    no_mem_success = sum(1 for r in memory_not_utilized if r.success)
    mem_rate = mem_success / len(memory_utilized) if memory_utilized else 0.0
    no_mem_rate = no_mem_success / len(memory_not_utilized) if memory_not_utilized else 0.0
    m.memory_utilization_effect = mem_rate - no_mem_rate  # positive = memory helps

    # Similar Task Recall: of tasks with memory, how many matched similar past tasks
    # (simplified: memory_utilized means at least one similar task was found)
    m.similar_task_recall = m.memory_hit_rate  # same as hit rate in this impl

    # 10. Routing-specific metrics
    if routing_stats:
        layer_counts = routing_stats.get("layer_counts", {})
        total_routes = routing_stats.get("total_routes", 0)
        if total_routes > 0:
            m.rule_layer_rate = layer_counts.get("rule", 0) / total_routes
            m.embedding_layer_rate = layer_counts.get("embedding", 0) / total_routes
            m.routing_fallback_rate = (
                layer_counts.get("llm", 0) + layer_counts.get("default", 0)
            ) / total_routes
            # Accuracy: rule + embedding layers are "confident", llm/default are fallback
            m.routing_accuracy = m.rule_layer_rate + m.embedding_layer_rate

    return m
