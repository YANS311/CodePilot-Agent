"""D28 Tests — Stress test infrastructure validation."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.schema import EvalResult, EvalTask, ToolCallRecord
from app.evaluation.advanced_metrics import AdvancedMetrics, compute_advanced_metrics
from app.models.tool import AgentStep


# ═══════════════════════════════════════════
# 1. Stress tasks.json validation
# ═══════════════════════════════════════════


class TestStressTasksFile:
    def test_stress_tasks_file_exists(self):
        path = PROJECT_ROOT / "evaluation" / "stress_tasks.json"
        assert path.exists()

    def test_stress_tasks_loadable(self):
        path = PROJECT_ROOT / "evaluation" / "stress_tasks.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "tasks" in data
        assert len(data["tasks"]) >= 8

    def test_stress_tasks_have_required_fields(self):
        path = PROJECT_ROOT / "evaluation" / "stress_tasks.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for task in data["tasks"]:
            assert "id" in task
            assert "name" in task
            assert "difficulty" in task
            assert "category" in task
            assert "task" in task
            assert "test_target" in task

    def test_stress_task_categories(self):
        path = PROJECT_ROOT / "evaluation" / "stress_tasks.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        categories = {t["category"] for t in data["tasks"]}
        assert "multi-file-bug-fix" in categories
        assert "mixed-instruction" in categories
        assert "repo-understand-modify" in categories
        assert "partial-failure-recovery" in categories

    def test_stress_tasks_parseable(self):
        path = PROJECT_ROOT / "evaluation" / "stress_tasks.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tasks = [EvalTask.from_dict(t) for t in data["tasks"]]
        assert len(tasks) >= 8
        for t in tasks:
            assert t.id.startswith("stress-")


# ═══════════════════════════════════════════
# 2. AgentStep recovery fields
# ═══════════════════════════════════════════


class TestAgentStepRecoveryFields:
    def test_default_values(self):
        step = AgentStep(step_id=1)
        assert step.is_retry is False
        assert step.retry_of == 0

    def test_retry_fields(self):
        step = AgentStep(
            step_id=3,
            is_retry=True,
            retry_of=2,
            tool_name="write_file",
        )
        assert step.is_retry is True
        assert step.retry_of == 2


# ═══════════════════════════════════════════
# 3. EvalResult stress tracking fields
# ═══════════════════════════════════════════


class TestEvalResultStressFields:
    def test_default_values(self):
        r = EvalResult(task_id="test")
        assert r.is_retry_result is False
        assert r.retry_count == 0
        assert r.files_modified == []

    def test_retry_result(self):
        r = EvalResult(
            task_id="test",
            is_retry_result=True,
            retry_count=2,
            files_modified=["a.py", "b.py"],
        )
        assert r.is_retry_result is True
        assert r.retry_count == 2
        assert len(r.files_modified) == 2


# ═══════════════════════════════════════════
# 4. AdvancedMetrics stress fields
# ═══════════════════════════════════════════


class TestAdvancedMetricsStressFields:
    def test_default_stress_values(self):
        m = AdvancedMetrics()
        assert m.recovery_rate == 0.0
        assert m.multi_file_success_rate == 0.0
        assert m.first_pass_rate == 0.0
        assert m.retry_success_rate == 0.0
        assert m.tool_efficiency_under_stress == 0.0
        assert m.stress_total_tasks == 0
        assert m.stress_successful_tasks == 0

    def test_to_dict_includes_stress_fields(self):
        m = AdvancedMetrics()
        d = m.to_dict()
        assert "recovery_rate" in d
        assert "multi_file_success_rate" in d
        assert "first_pass_rate" in d
        assert "retry_success_rate" in d
        assert "tool_efficiency_under_stress" in d
        assert "stress_total_tasks" in d["details"]
        assert "stress_successful_tasks" in d["details"]


# ═══════════════════════════════════════════
# 5. Stress metrics computation
# ═══════════════════════════════════════════


class TestStressMetricsComputation:
    def test_empty_results(self):
        m = compute_advanced_metrics([], [])
        assert m.recovery_rate == 0.0
        assert m.multi_file_success_rate == 0.0

    def test_stress_tasks_identified(self):
        tasks = [
            EvalTask(id="s1", name="s1", difficulty="medium", category="multi-file-bug-fix", task="fix"),
            EvalTask(id="s2", name="s2", difficulty="hard", category="mixed-instruction", task="fix"),
            EvalTask(id="n1", name="n1", difficulty="easy", category="bug-fix", task="fix"),
        ]
        results = [
            EvalResult(task_id="s1", success=True, tool_calls_count=3),
            EvalResult(task_id="s2", success=False, tool_calls_count=5),
            EvalResult(task_id="n1", success=True, tool_calls_count=2),
        ]
        m = compute_advanced_metrics(results, tasks)
        assert m.stress_total_tasks == 2
        assert m.stress_successful_tasks == 1

    def test_multi_file_success_rate(self):
        tasks = [
            EvalTask(id="s1", name="s1", difficulty="medium", category="multi-file-bug-fix", task="fix"),
            EvalTask(id="s2", name="s2", difficulty="medium", category="multi-file-bug-fix", task="fix"),
        ]
        results = [
            EvalResult(task_id="s1", success=True, tool_calls_count=3),
            EvalResult(task_id="s2", success=False, tool_calls_count=5),
        ]
        m = compute_advanced_metrics(results, tasks)
        assert m.multi_file_tasks == 2
        assert m.multi_file_successful == 1
        assert abs(m.multi_file_success_rate - 0.5) < 0.01

    def test_recovery_rate(self):
        tasks = [
            EvalTask(id="s1", name="s1", difficulty="hard", category="partial-failure-recovery", task="fix"),
        ]
        results = [
            EvalResult(task_id="s1", success=True, tool_calls_count=5, is_retry_result=True),
        ]
        m = compute_advanced_metrics(results, tasks)
        assert m.retry_tasks == 1
        assert m.retry_successful == 1
        assert m.recovery_rate == 1.0

    def test_first_pass_rate(self):
        tasks = [
            EvalTask(id="s1", name="s1", difficulty="easy", category="bug-fix", task="fix"),
            EvalTask(id="s2", name="s2", difficulty="easy", category="bug-fix", task="fix"),
        ]
        results = [
            EvalResult(task_id="s1", success=True, tool_calls_count=2, is_retry_result=False),
            EvalResult(task_id="s2", success=True, tool_calls_count=3, is_retry_result=False),
        ]
        m = compute_advanced_metrics(results, tasks)
        assert m.first_pass_tasks == 2
        assert m.first_pass_successful == 2
        assert m.first_pass_rate == 1.0

    def test_tool_efficiency_under_stress(self):
        tasks = [
            EvalTask(id="s1", name="s1", difficulty="hard", category="multi-file-bug-fix", task="fix"),
            EvalTask(id="s2", name="s2", difficulty="hard", category="multi-file-bug-fix", task="fix"),
        ]
        results = [
            EvalResult(task_id="s1", success=True, tool_calls_count=4),
            EvalResult(task_id="s2", success=True, tool_calls_count=6),
        ]
        m = compute_advanced_metrics(results, tasks)
        assert abs(m.tool_efficiency_under_stress - 5.0) < 0.01


# ═══════════════════════════════════════════
# 6. Workspace stress test files exist
# ═══════════════════════════════════════════


class TestWorkspaceStressFiles:
    def test_stress_multi_file_test_exists(self):
        path = PROJECT_ROOT / "workspace" / "tests" / "test_stress_multi_file.py"
        assert path.exists()

    def test_stress_mixed_test_exists(self):
        path = PROJECT_ROOT / "workspace" / "tests" / "test_stress_mixed.py"
        assert path.exists()

    def test_stress_multi_file_test_has_failing_tests(self):
        """stress_multi_file tests should fail until bugs are fixed."""
        path = PROJECT_ROOT / "workspace" / "tests" / "test_stress_multi_file.py"
        content = path.read_text(encoding="utf-8")
        assert "TestTodoCompletePersistence" in content
        assert "TestTodoListPending" in content
        assert "TestUserToDict" in content
        assert "TestTaskToDict" in content
        assert "TestTaskManagerListByPriority" in content


# ═══════════════════════════════════════════
# 7. Stress runner script exists
# ═══════════════════════════════════════════


class TestStressRunnerScript:
    def test_runner_script_exists(self):
        path = PROJECT_ROOT / "scripts" / "run_stress_eval.py"
        assert path.exists()

    def test_runner_script_has_main(self):
        path = PROJECT_ROOT / "scripts" / "run_stress_eval.py"
        content = path.read_text(encoding="utf-8")
        assert "def main()" in content
        assert "stress_tasks" in content
        assert "_compute_stress_metrics" in content
