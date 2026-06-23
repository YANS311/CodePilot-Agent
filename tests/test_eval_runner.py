"""D10 Tests — Evaluation Runner 测试。"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.schema import EvalResult, EvalTask
from app.evaluation.runner import EvaluationRunner
from app.evaluation.metrics import compute_metrics, EvalMetrics

WORKSPACE_SEED = str(PROJECT_ROOT / "workspace")


# ═══════════════════════════════════════════
# 1. EvalTask schema
# ═══════════════════════════════════════════


class TestEvalTask:
    def test_from_dict(self):
        d = {
            "id": "fix-subtract",
            "name": "修复 subtract bug",
            "difficulty": "easy",
            "category": "bug-fix",
            "task": "修复 subtract 函数",
            "file": "examples/buggy_calculator.py",
            "expected_behavior": "返回 a - b",
            "success_criteria": ["subtract(5,3)==2"],
            "reference_fix": "改 a+b 为 a-b",
        }
        task = EvalTask.from_dict(d)
        assert task.id == "fix-subtract"
        assert task.difficulty == "easy"
        assert task.category == "bug-fix"
        assert len(task.success_criteria) == 1

    def test_from_dict_defaults(self):
        task = EvalTask.from_dict({"id": "x", "name": "X", "task": "do stuff"})
        assert task.difficulty == "unknown"
        assert task.category == "unknown"
        assert task.success_criteria == []


# ═══════════════════════════════════════════
# 2. EvalResult schema
# ═══════════════════════════════════════════


class TestEvalResult:
    def test_to_dict(self):
        r = EvalResult(
            task_id="t1",
            success=True,
            tool_calls_count=3,
            passed=5,
            failed=0,
        )
        d = r.to_dict()
        assert d["task_id"] == "t1"
        assert d["success"] is True
        assert d["passed"] == 5

    def test_defaults(self):
        r = EvalResult(task_id="t1")
        assert r.success is False
        assert r.tool_calls_count == 0
        assert r.test_success is False


# ═══════════════════════════════════════════
# 3. tasks.json loading
# ═══════════════════════════════════════════


class TestTasksLoading:
    def test_load_tasks(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        assert len(tasks) == 30
        assert tasks[0].id == "fix-subtract"

    def test_all_tasks_have_required_fields(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        for t in tasks:
            assert t.id
            assert t.name
            assert t.task
            assert t.difficulty in ("easy", "medium", "hard")


# ═══════════════════════════════════════════
# 4. workspace isolation
# ═══════════════════════════════════════════


class TestWorkspaceIsolation:
    def test_prepare_creates_independent_workspace(self):
        runner = EvaluationRunner()
        task_ws = runner._prepare_workspace("test-isolation")
        try:
            assert task_ws.exists()
            assert task_ws.name == "test-isolation"
            # 应包含 seed 中的文件
            assert (task_ws / "examples").exists()
            assert (task_ws / "valid_module.py").exists()
        finally:
            runner._cleanup_workspace("test-isolation")

    def test_cleanup_removes_workspace(self):
        runner = EvaluationRunner()
        task_ws = runner._prepare_workspace("test-cleanup")
        assert task_ws.exists()
        runner._cleanup_workspace("test-cleanup")
        assert not task_ws.exists()

    def test_independent_workspaces_are_copies(self):
        runner = EvaluationRunner()
        ws1 = runner._prepare_workspace("ws-a")
        ws2 = runner._prepare_workspace("ws-b")
        try:
            # 修改 ws1 不应影响 ws2
            (ws1 / "marker.txt").write_text("from-a", encoding="utf-8")
            assert not (ws2 / "marker.txt").exists()
        finally:
            runner._cleanup_workspace("ws-a")
            runner._cleanup_workspace("ws-b")


# ═══════════════════════════════════════════
# 5. Metrics
# ═══════════════════════════════════════════


class TestMetrics:
    def test_empty_results(self):
        metrics = compute_metrics([], [])
        assert metrics.total_tasks == 0
        assert metrics.task_success_rate == 0.0

    def test_all_success(self):
        results = [
            EvalResult(task_id="t1", success=True, passed=5, tool_calls_count=3, duration_ms=100),
            EvalResult(task_id="t2", success=True, passed=3, tool_calls_count=2, duration_ms=200),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t2", name="T2", task="fix", difficulty="medium", category="bug-fix"),
        ]
        m = compute_metrics(results, tasks)
        assert m.task_success_rate == 1.0
        assert m.successful_tasks == 2
        assert m.avg_tool_calls == 2.5
        assert m.avg_duration_ms == 150.0
        assert m.total_tests_passed == 8

    def test_partial_success(self):
        results = [
            EvalResult(task_id="t1", success=True, passed=2, tool_calls_count=1),
            EvalResult(task_id="t2", success=False, failed=1, tool_calls_count=4),
            EvalResult(task_id="t3", success=True, passed=3, tool_calls_count=2),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t2", name="T2", task="fix", difficulty="hard", category="enhancement"),
            EvalTask(id="t3", name="T3", task="fix", difficulty="easy", category="bug-fix"),
        ]
        m = compute_metrics(results, tasks)
        assert m.task_success_rate == pytest.approx(2 / 3)
        assert m.test_pass_rate == pytest.approx(5 / 6)
        # 按难度
        assert m.success_by_difficulty["easy"]["success"] == 2
        assert m.success_by_difficulty["easy"]["total"] == 2
        assert m.success_by_difficulty["hard"]["success"] == 0
        # 按类别
        assert m.success_by_category["bug-fix"]["success"] == 2
        assert m.success_by_category["enhancement"]["success"] == 0

    def test_to_dict(self):
        m = compute_metrics(
            [EvalResult(task_id="t1", success=True)],
            [EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix")],
        )
        d = m.to_dict()
        assert "task_success_rate" in d
        assert "success_by_difficulty" in d


# ═══════════════════════════════════════════
# 6. EvaluationRunner.run_task (mock agent)
# ═══════════════════════════════════════════


class TestRunnerRunTask:
    def test_run_task_with_mock_agent(self):
        """用 mock agent 验证 run_task 的 workspace 隔离和结果收集。"""
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.react_agent import AgentRunResult

        runner = EvaluationRunner()

        # Mock agent：模拟成功执行
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=AgentRunResult(
            answer="fixed",
            tool_calls_count=3,
        ))

        def factory(ws_root, max_calls=None):
            mock_agent._workspace_root = ws_root
            return mock_agent

        task = EvalTask(
            id="mock-test",
            name="Mock Test",
            task="fix something",
            difficulty="easy",
            category="bug-fix",
        )

        result = asyncio.run(
            runner.run_task(task, factory)
        )

        assert result.task_id == "mock-test"
        assert result.tool_calls_count == 3
        assert result.duration_ms >= 0
        # workspace 应已清理
        assert not (runner._eval_dir / "mock-test").exists()

    def test_run_task_with_error(self):
        """验证 agent 异常时返回错误结果。"""
        from unittest.mock import AsyncMock, MagicMock

        runner = EvaluationRunner()

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("LLM failed"))

        task = EvalTask(
            id="error-test",
            name="Error Test",
            task="fix something",
            difficulty="easy",
            category="bug-fix",
        )

        result = asyncio.run(
            runner.run_task(task, lambda ws, max_calls=None: mock_agent)
        )

        assert result.success is False
        assert "LLM failed" in result.error
        # workspace 应已清理
        assert not (runner._eval_dir / "error-test").exists()


# ═══════════════════════════════════════════
# 7. report generation
# ═══════════════════════════════════════════


class TestReportGeneration:
    def test_report_json_structure(self):
        """验证生成的 report JSON 包含正确结构。"""
        from app.evaluation.metrics import compute_metrics

        results = [
            EvalResult(task_id="t1", success=True, passed=2, tool_calls_count=1, duration_ms=50),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix"),
        ]
        metrics = compute_metrics(results, tasks)

        report = {
            "version": "2.0",
            "tasks": [r.to_dict() for r in results],
            "metrics": metrics.to_dict(),
        }

        # 验证结构
        assert report["version"] == "2.0"
        assert len(report["tasks"]) == 1
        assert report["tasks"][0]["task_id"] == "t1"
        assert "task_success_rate" in report["metrics"]

        # 验证可序列化
        json_str = json.dumps(report, ensure_ascii=False, indent=2)
        parsed = json.loads(json_str)
        assert parsed["metrics"]["total_tasks"] == 1
