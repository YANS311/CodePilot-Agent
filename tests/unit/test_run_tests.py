"""D8 Tests — RunTestsTool 测试。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.run_tests import RunTestsTool
from app.tools.registry import ToolRegistry
from app.models.tool import ToolCall

WORKSPACE = str(PROJECT_ROOT / "workspace")


def _make_tool() -> RunTestsTool:
    return RunTestsTool()


# ═══════════════════════════════════════════
# 1. pytest success
# ═══════════════════════════════════════════


class TestRunTestsSuccess:
    def test_run_all_tests(self):
        """运行 workspace 内所有测试 — 验证 runner 正常工作。"""
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root=WORKSPACE)
        )
        data = json.loads(result)
        # workspace 可能有预置的失败测试，只要求发现并执行了测试
        assert data["passed"] + data["failed"] > 0
        assert "stdout" in data

    def test_run_specific_test_file(self):
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root=WORKSPACE, target="tests/test_health.py")
        )
        data = json.loads(result)
        assert data["success"] is True
        assert data["passed"] >= 1


# ═══════════════════════════════════════════
# 2. pytest failure
# ═══════════════════════════════════════════


class TestRunTestsFailure:
    def test_run_failing_test(self):
        """创建一个必定失败的测试文件并执行。"""
        ws = Path(WORKSPACE)
        test_file = ws / "test_must_fail.py"
        test_file.write_text(
            "def test_fail():\n    assert False, 'intentional failure'\n",
            encoding="utf-8",
        )
        try:
            tool = _make_tool()
            result = asyncio.run(
                tool.run(workspace_root=WORKSPACE, target="test_must_fail.py")
            )
            data = json.loads(result)
            assert data["success"] is False
            assert data["failed"] >= 1
        finally:
            test_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════
# 3. timeout
# ═══════════════════════════════════════════


class TestRunTestsTimeout:
    def test_timeout_message(self):
        """验证超时返回正确的错误信息。"""
        tool = _make_tool()
        # 超时测试：创建一个无限循环的测试
        ws = Path(WORKSPACE)
        test_file = ws / "test_infinite.py"
        test_file.write_text(
            "import time\ndef test_infinite():\n    time.sleep(60)\n",
            encoding="utf-8",
        )
        try:
            result = asyncio.run(
                tool.run(workspace_root=WORKSPACE, target="test_infinite.py")
            )
            # timeout returns a plain error string, not JSON
            assert "超时" in result or "Timeout" in result or "错误" in result
        finally:
            test_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════
# 4. invalid target
# ═══════════════════════════════════════════


class TestRunTestsInvalid:
    def test_traversal_blocked(self):
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root=WORKSPACE, target="../../etc/passwd")
        )
        assert "错误" in result
        assert "超出" in result

    def test_nonexistent_workspace(self):
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root="/nonexistent/path")
        )
        assert "错误" in result
        assert "不存在" in result


# ═══════════════════════════════════════════
# 5. output truncation
# ═══════════════════════════════════════════


class TestRunTestsOutput:
    def test_output_is_json(self):
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root=WORKSPACE, target="tests/test_health.py")
        )
        data = json.loads(result)
        assert "success" in data
        assert "passed" in data
        assert "failed" in data
        assert "stdout" in data
        assert "stderr" in data

    def test_output_max_size(self):
        """验证 stdout 不超过 50KB。"""
        tool = _make_tool()
        result = asyncio.run(
            tool.run(workspace_root=WORKSPACE)
        )
        assert len(result.encode("utf-8")) <= 50 * 1024 + 1024  # 允许 JSON 包装开销


# ═══════════════════════════════════════════
# 6. ToolRegistry integration
# ═══════════════════════════════════════════


class TestRunTestsRegistry:
    def test_registry_can_execute_run_tests(self):
        reg = ToolRegistry()
        reg.register(RunTestsTool())
        tc = ToolCall(name="run_tests", arguments={"target": "tests/test_health.py"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is True
        data = json.loads(result.output)
        assert data["passed"] >= 1

    def test_run_tests_is_base_tool(self):
        from app.tools.base import BaseTool
        from app.tools.workspace_tool import WorkspaceTool
        tool = RunTestsTool()
        assert isinstance(tool, BaseTool)
        assert isinstance(tool, WorkspaceTool)
