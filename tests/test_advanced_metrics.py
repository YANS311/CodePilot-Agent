"""D15 Tests — Advanced Metrics 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.advanced_metrics import AdvancedMetrics, compute_advanced_metrics
from app.evaluation.schema import EvalResult, EvalTask, ToolCallRecord


# ═══════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════


def _make_task(task_id: str = "t1", difficulty: str = "easy") -> EvalTask:
    return EvalTask(
        id=task_id,
        name=task_id,
        difficulty=difficulty,
        category="bug-fix",
        task=f"Fix {task_id}",
    )


def _make_result(
    task_id: str = "t1",
    success: bool = True,
    passed: int = 1,
    failed: int = 0,
    tool_calls_count: int = 7,
    steps: list[ToolCallRecord] | None = None,
    tool_results: list[ToolCallRecord] | None = None,
) -> EvalResult:
    return EvalResult(
        task_id=task_id,
        success=success,
        passed=passed,
        failed=failed,
        tool_calls_count=tool_calls_count,
        steps=steps or [],
        tool_results=tool_results or [],
    )


# ═══════════════════════════════════════════
# 1. Empty input
# ═══════════════════════════════════════════


class TestEmptyInput:
    def test_empty_results(self):
        m = compute_advanced_metrics([], [])
        assert m.task_success_rate == 0.0
        assert m.total_tasks == 0


# ═══════════════════════════════════════════
# 2. Task Success Rate
# ═══════════════════════════════════════════


class TestTaskSuccessRate:
    def test_all_pass(self):
        results = [_make_result(success=True) for _ in range(5)]
        tasks = [_make_task(f"t{i}") for i in range(5)]
        m = compute_advanced_metrics(results, tasks)
        assert m.task_success_rate == 1.0

    def test_all_fail(self):
        results = [_make_result(success=False) for _ in range(5)]
        tasks = [_make_task(f"t{i}") for i in range(5)]
        m = compute_advanced_metrics(results, tasks)
        assert m.task_success_rate == 0.0

    def test_mixed(self):
        results = [
            _make_result(success=True),
            _make_result(success=True),
            _make_result(success=False),
        ]
        tasks = [_make_task(f"t{i}") for i in range(3)]
        m = compute_advanced_metrics(results, tasks)
        assert abs(m.task_success_rate - 2 / 3) < 0.01


# ═══════════════════════════════════════════
# 3. Test Pass Rate
# ═══════════════════════════════════════════


class TestTestPassRate:
    def test_all_tests_pass(self):
        results = [_make_result(passed=10, failed=0)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.test_pass_rate == 1.0

    def test_all_tests_fail(self):
        results = [_make_result(passed=0, failed=10)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.test_pass_rate == 0.0

    def test_mixed_tests(self):
        results = [_make_result(passed=8, failed=2)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert abs(m.test_pass_rate - 0.8) < 0.01


# ═══════════════════════════════════════════
# 4. Tool Call Validity
# ═══════════════════════════════════════════


class TestToolCallValidity:
    def test_all_valid(self):
        results = [_make_result(tool_calls_count=5)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.tool_call_validity == 1.0

    def test_with_blocked_tool(self):
        blocked = ToolCallRecord(
            tool_name="read_file",
            success=False,
            output="SECURITY_BLOCKED: .env access denied",
        )
        results = [_make_result(tool_calls_count=3, tool_results=[blocked])]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.tool_call_validity < 1.0

    def test_with_fake_tool(self):
        fake_step = ToolCallRecord(
            tool_name="unknown",
            observation="fake_tool_call detected",
        )
        results = [_make_result(tool_calls_count=4, steps=[fake_step])]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.tool_call_validity < 1.0


# ═══════════════════════════════════════════
# 5. Verification Completion Rate
# ═══════════════════════════════════════════


class TestVerificationRate:
    def test_write_then_test(self):
        steps = [
            ToolCallRecord(tool_name="read_file"),
            ToolCallRecord(tool_name="write_file"),
            ToolCallRecord(tool_name="run_tests"),
        ]
        results = [_make_result(steps=steps)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.verification_completion_rate == 1.0

    def test_write_no_test(self):
        steps = [
            ToolCallRecord(tool_name="read_file"),
            ToolCallRecord(tool_name="write_file"),
        ]
        results = [_make_result(steps=steps)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.verification_completion_rate == 0.0

    def test_no_write_skipped(self):
        steps = [ToolCallRecord(tool_name="search_code")]
        results = [_make_result(steps=steps)]
        m = compute_advanced_metrics(results, [_make_task()])
        # No write_file tasks → rate defaults to 1.0
        assert m.verification_completion_rate == 1.0


# ═══════════════════════════════════════════
# 6. Code Change Validity
# ═══════════════════════════════════════════


class TestCodeChangeValidity:
    def test_has_write(self):
        steps = [ToolCallRecord(tool_name="write_file")]
        results = [_make_result(steps=steps)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.code_change_validity == 1.0

    def test_no_write(self):
        steps = [ToolCallRecord(tool_name="search_code")]
        results = [_make_result(steps=steps)]
        m = compute_advanced_metrics(results, [_make_task()])
        assert m.code_change_validity == 0.0


# ═══════════════════════════════════════════
# 7. Planning Efficiency
# ═══════════════════════════════════════════


class TestPlanningEfficiency:
    def test_success_avg(self):
        results = [
            _make_result(success=True, tool_calls_count=7),
            _make_result(success=True, tool_calls_count=9),
        ]
        tasks = [_make_task(f"t{i}") for i in range(2)]
        m = compute_advanced_metrics(results, tasks)
        assert m.planning_efficiency == 8.0

    def test_only_successful_counted(self):
        results = [
            _make_result(success=True, tool_calls_count=7),
            _make_result(success=False, tool_calls_count=20),
        ]
        tasks = [_make_task(f"t{i}") for i in range(2)]
        m = compute_advanced_metrics(results, tasks)
        assert m.planning_efficiency == 7.0


# ═══════════════════════════════════════════
# 8. Security Block Rate
# ═══════════════════════════════════════════


class TestSecurityBlockRate:
    def test_all_blocked(self):
        security = [{"blocked": True}, {"blocked": True}, {"blocked": True}]
        m = compute_advanced_metrics([], [], security_results=security)
        assert m.security_block_rate == 1.0

    def test_none_blocked(self):
        security = [{"blocked": False}, {"blocked": False}]
        m = compute_advanced_metrics([], [], security_results=security)
        assert m.security_block_rate == 0.0

    def test_mixed_blocked(self):
        security = [{"blocked": True}, {"blocked": False}]
        m = compute_advanced_metrics([], [], security_results=security)
        assert m.security_block_rate == 0.5

    def test_no_security_tasks(self):
        m = compute_advanced_metrics([], [], security_results=None)
        assert m.security_block_rate == 0.0


# ═══════════════════════════════════════════
# 9. to_dict
# ═══════════════════════════════════════════


class TestToDict:
    def test_to_dict_keys(self):
        m = AdvancedMetrics(task_success_rate=0.9)
        d = m.to_dict()
        assert "task_success_rate" in d
        assert "test_pass_rate" in d
        assert "tool_call_validity" in d
        assert "verification_completion_rate" in d
        assert "code_change_validity" in d
        assert "planning_efficiency" in d
        assert "security_block_rate" in d
        assert "details" in d
        assert d["task_success_rate"] == 0.9


# ═══════════════════════════════════════════
# 10. Integration — full scenario
# ═══════════════════════════════════════════


class TestFullScenario:
    def test_mixed_success_and_failure(self):
        """模拟 3 个任务：2 成功 1 失败。"""
        results = [
            _make_result(
                task_id="t1",
                success=True,
                passed=5,
                failed=0,
                tool_calls_count=7,
                steps=[
                    ToolCallRecord(tool_name="read_file"),
                    ToolCallRecord(tool_name="write_file"),
                    ToolCallRecord(tool_name="run_tests"),
                ],
            ),
            _make_result(
                task_id="t2",
                success=True,
                passed=3,
                failed=0,
                tool_calls_count=9,
                steps=[
                    ToolCallRecord(tool_name="search_code"),
                    ToolCallRecord(tool_name="read_file"),
                    ToolCallRecord(tool_name="write_file"),
                    ToolCallRecord(tool_name="run_tests"),
                ],
            ),
            _make_result(
                task_id="t3",
                success=False,
                passed=1,
                failed=4,
                tool_calls_count=12,
                steps=[
                    ToolCallRecord(tool_name="read_file"),
                    ToolCallRecord(tool_name="write_file"),
                ],
            ),
        ]
        tasks = [_make_task(f"t{i}") for i in range(1, 4)]
        security = [{"blocked": True}, {"blocked": True}]

        m = compute_advanced_metrics(results, tasks, security_results=security)

        assert abs(m.task_success_rate - 2 / 3) < 0.01
        assert abs(m.test_pass_rate - 9 / 13) < 0.01
        assert m.tool_call_validity == 1.0  # no blocked/fake tools in steps
        assert abs(m.verification_completion_rate - 2 / 3) < 0.01
        assert m.code_change_validity == 1.0  # all 3 tasks called write_file
        assert m.planning_efficiency == 8.0  # (7+9)/2
        assert m.security_block_rate == 1.0
