"""D10 Tests — Evaluation Runner 测试。"""

from __future__ import annotations

import ast
import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.schema import BaselineMode, EvalLayer, EvalResult, EvalTask
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


    def test_task_test_targets_exist_in_workspace_seed(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        missing = []

        for task in tasks:
            if not task.test_target:
                continue
            parts = task.test_target.split("::")
            test_file = PROJECT_ROOT / "workspace" / parts[0]
            if not test_file.exists():
                missing.append(f"{task.id}: missing file {parts[0]}")
                continue

            tree = ast.parse(test_file.read_text(encoding="utf-8"))
            classes = {
                node.name: node
                for node in tree.body
                if isinstance(node, ast.ClassDef)
            }
            functions = {
                node.name
                for node in tree.body
                if isinstance(node, ast.FunctionDef)
            }

            if len(parts) >= 2:
                target = parts[1]
                if target.startswith("Test"):
                    if target not in classes:
                        missing.append(f"{task.id}: missing class {target}")
                        continue
                    if len(parts) >= 3:
                        methods = {
                            node.name
                            for node in classes[target].body
                            if isinstance(node, ast.FunctionDef)
                        }
                        if parts[2] not in methods:
                            missing.append(
                                f"{task.id}: missing method {target}::{parts[2]}"
                            )
                elif target not in functions:
                    missing.append(f"{task.id}: missing function {target}")

        assert missing == []

# ═══════════════════════════════════════════


class TestEvalPromptContext:
    def test_build_agent_prompt_includes_eval_context(self):
        runner = EvaluationRunner()
        task = EvalTask(
            id="ctx-test",
            name="Context Test",
            task="Fix the bug",
            difficulty="hard",
            category="bug-fix",
            file="examples/file_processor.py",
            test_target="tests/test_file_processor.py",
            expected_behavior="handles edge cases",
            success_criteria=["replace returns 0", "append avoids blank lines"],
            reference_fix="secret solution",
        )

        prompt = runner._build_agent_prompt(task)

        assert prompt.startswith("Fix the bug")
        assert "Evaluation context:" in prompt
        assert "examples/file_processor.py" in prompt
        assert "tests/test_file_processor.py" in prompt
        assert "handles edge cases" in prompt
        assert "replace returns 0" in prompt
        assert "append avoids blank lines" in prompt
        assert "workspace/examples" not in prompt
        assert "secret solution" not in prompt

    def test_build_agent_prompt_without_metadata_returns_task(self):
        runner = EvaluationRunner()
        task = EvalTask(
            id="plain",
            name="Plain",
            task="Just answer",
            difficulty="easy",
            category="analysis",
        )

        assert runner._build_agent_prompt(task) == "Just answer"

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

        def factory(ws_root, max_calls=None, baseline=BaselineMode.REACT_FULL):
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
            runner.run_task(task, lambda ws, max_calls=None, baseline=BaselineMode.REACT_FULL: mock_agent)
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


# ═══════════════════════════════════════════
# 8. v0.4.5: EvalLayer enum
# ═══════════════════════════════════════════


class TestEvalLayer:
    def test_layer_values(self):
        assert EvalLayer.UNIT.value == "unit"
        assert EvalLayer.INTEGRATION.value == "integration"
        assert EvalLayer.STRESS.value == "stress"

    def test_task_from_dict_with_layer(self):
        d = {
            "id": "t1",
            "name": "T1",
            "task": "fix",
            "layer": "unit",
        }
        task = EvalTask.from_dict(d)
        assert task.layer == EvalLayer.UNIT

    def test_task_from_dict_default_layer(self):
        d = {"id": "t1", "name": "T1", "task": "fix"}
        task = EvalTask.from_dict(d)
        assert task.layer == EvalLayer.INTEGRATION

    def test_all_tasks_have_layer(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        for t in tasks:
            assert isinstance(t.layer, EvalLayer)


# ═══════════════════════════════════════════
# 9. v0.4.5: BaselineMode enum
# ═══════════════════════════════════════════


class TestBaselineMode:
    def test_baseline_values(self):
        assert BaselineMode.BARE_LLM.value == "bare_llm"
        assert BaselineMode.REACT_NO_MEMORY.value == "react_no_memory"
        assert BaselineMode.REACT_FULL.value == "react_full"

    def test_baseline_from_string(self):
        assert BaselineMode("bare_llm") == BaselineMode.BARE_LLM
        assert BaselineMode("react_full") == BaselineMode.REACT_FULL


# ═══════════════════════════════════════════
# 10. v0.4.5: Layer filtering
# ═══════════════════════════════════════════


class TestLayerFiltering:
    def test_filter_by_unit_layer(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        unit_tasks = [t for t in tasks if t.layer == EvalLayer.UNIT]
        assert len(unit_tasks) > 0
        for t in unit_tasks:
            assert t.layer == EvalLayer.UNIT

    def test_filter_by_integration_layer(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        int_tasks = [t for t in tasks if t.layer == EvalLayer.INTEGRATION]
        assert len(int_tasks) > 0

    def test_filter_by_stress_layer(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        stress_tasks = [t for t in tasks if t.layer == EvalLayer.STRESS]
        assert len(stress_tasks) > 0

    def test_all_layers_cover_all_tasks(self):
        runner = EvaluationRunner()
        tasks = runner.load_tasks()
        by_layer = {EvalLayer.UNIT: 0, EvalLayer.INTEGRATION: 0, EvalLayer.STRESS: 0}
        for t in tasks:
            by_layer[t.layer] += 1
        assert sum(by_layer.values()) == 30
        assert all(v > 0 for v in by_layer.values())


# ═══════════════════════════════════════════
# 11. v0.4.5: Bare LLM baseline
# ═══════════════════════════════════════════


class TestBareLLMBaseline:
    def test_bare_llm_returns_result(self):
        """Bare LLM baseline should return AgentRunResult with tool_calls_count=0."""
        from unittest.mock import AsyncMock, MagicMock
        from app.core.llm_client import ChatResponse

        runner = EvaluationRunner()

        mock_agent = MagicMock()
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content="This is a bug in subtract. Change a+b to a-b.",
            tool_calls=[],
        ))
        mock_agent._llm = mock_llm

        def factory(ws_root, max_calls=None, baseline=BaselineMode.REACT_FULL):
            return mock_agent

        task = EvalTask(
            id="bare-test",
            name="Bare LLM Test",
            task="Fix subtract function",
            difficulty="easy",
            category="bug-fix",
        )

        result = asyncio.run(
            runner.run_task(task, factory, baseline=BaselineMode.BARE_LLM)
        )

        assert result.task_id == "bare-test"
        assert result.tool_calls_count == 0
        assert "bug" in result.final_answer.lower() or "subtract" in result.final_answer.lower()

    def test_bare_llm_no_tools_used(self):
        """Bare LLM should not invoke any tools."""
        from unittest.mock import AsyncMock, MagicMock
        from app.core.llm_client import ChatResponse

        runner = EvaluationRunner()

        mock_agent = MagicMock()
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=ChatResponse(
            content="Analysis complete.",
            tool_calls=[],
        ))
        mock_agent._llm = mock_llm

        task = EvalTask(
            id="bare-test-2",
            name="Bare LLM Test 2",
            task="Fix something",
            difficulty="easy",
            category="bug-fix",
        )

        result = asyncio.run(
            runner.run_task(task, lambda ws, mc=None, bl=BaselineMode.REACT_FULL: mock_agent,
                           baseline=BaselineMode.BARE_LLM)
        )

        assert result.tool_calls_count == 0
        mock_llm.chat.assert_called_once()


# ═══════════════════════════════════════════
# 12. v0.4.5: Agent-specific metrics
# ═══════════════════════════════════════════


class TestAgentMetrics:
    def test_verification_pass_rate(self):
        results = [
            EvalResult(task_id="t1", success=True, verification_passed=True, verification_retries=1),
            EvalResult(task_id="t2", success=False, verification_passed=False, verification_retries=2),
            EvalResult(task_id="t3", success=True, verification_passed=True, verification_retries=0),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t2", name="T2", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t3", name="T3", task="fix", difficulty="easy", category="bug-fix"),
        ]
        m = compute_metrics(results, tasks)
        # t1 and t3 ran verification (retries>0 or passed=True), t2 also ran
        # 2 out of 3 passed verification
        assert m.verification_pass_rate == pytest.approx(2 / 3)

    def test_edit_precision_rate(self):
        results = [
            EvalResult(task_id="t1", success=True, code_edit_used=True, write_file_used=False),
            EvalResult(task_id="t2", success=True, code_edit_used=False, write_file_used=True),
            EvalResult(task_id="t3", success=True, code_edit_used=True, write_file_used=True),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t2", name="T2", task="fix", difficulty="easy", category="bug-fix"),
            EvalTask(id="t3", name="T3", task="fix", difficulty="easy", category="bug-fix"),
        ]
        m = compute_metrics(results, tasks)
        # code_edit: t1, t3 = 2; write_file: t2, t3 = 2; total = 4
        assert m.edit_precision_rate == pytest.approx(2 / 4)

    def test_success_by_layer(self):
        results = [
            EvalResult(task_id="t1", success=True),
            EvalResult(task_id="t2", success=False),
            EvalResult(task_id="t3", success=True),
        ]
        tasks = [
            EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix", layer=EvalLayer.UNIT),
            EvalTask(id="t2", name="T2", task="fix", difficulty="easy", category="bug-fix", layer=EvalLayer.INTEGRATION),
            EvalTask(id="t3", name="T3", task="fix", difficulty="easy", category="bug-fix", layer=EvalLayer.UNIT),
        ]
        m = compute_metrics(results, tasks)
        assert m.success_by_layer["unit"]["success"] == 2
        assert m.success_by_layer["unit"]["total"] == 2
        assert m.success_by_layer["integration"]["success"] == 0
        assert m.success_by_layer["integration"]["total"] == 1

    def test_metrics_to_dict_includes_new_fields(self):
        results = [EvalResult(task_id="t1", success=True, verification_passed=True, code_edit_used=True)]
        tasks = [EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix", layer=EvalLayer.UNIT)]
        m = compute_metrics(results, tasks)
        d = m.to_dict()
        assert "success_by_layer" in d
        assert "verification_pass_rate" in d
        assert "edit_precision_rate" in d


# ═══════════════════════════════════════════
# 13. v0.4.5: Report with baseline and layer
# ═══════════════════════════════════════════


class TestReportV21:
    def test_report_includes_baseline_and_layer(self):
        results = [EvalResult(task_id="t1", success=True, passed=2, tool_calls_count=1, duration_ms=50)]
        tasks = [EvalTask(id="t1", name="T1", task="fix", difficulty="easy", category="bug-fix", layer=EvalLayer.UNIT)]
        metrics = compute_metrics(results, tasks)

        report = {
            "version": "2.1",
            "timestamp": "2026-07-04T00:00:00",
            "baseline": "react_full",
            "layer": "unit",
            "tasks": [r.to_dict() for r in results],
            "metrics": metrics.to_dict(),
        }

        assert report["version"] == "2.1"
        assert report["baseline"] == "react_full"
        assert report["layer"] == "unit"
        assert "success_by_layer" in report["metrics"]

    def test_eval_result_agent_fields(self):
        r = EvalResult(
            task_id="t1",
            success=True,
            verification_passed=True,
            verification_retries=1,
            code_edit_used=True,
            write_file_used=False,
        )
        assert r.verification_passed is True
        assert r.verification_retries == 1
        assert r.code_edit_used is True
        assert r.write_file_used is False
