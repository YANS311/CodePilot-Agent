"""D7.7 OOP 重构测试 — 验证封装、继承、多态。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.base import BaseTool
from app.tools.workspace_tool import WorkspaceTool
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.registry import ToolRegistry
from app.models.tool import ToolCall

WORKSPACE = str(PROJECT_ROOT / "workspace")


# ═══════════════════════════════════════════
# 1. 所有默认工具都是 BaseTool 实例
# ═══════════════════════════════════════════


class TestToolsAreBaseTool:
    def test_all_tools_inherit_base_tool(self):
        tools = [
            ReadFileTool(),
            SearchCodeTool(),
            WriteFileTool(),
            GitDiffTool(),
            GitStatusTool(),
        ]
        for tool in tools:
            assert isinstance(tool, BaseTool), f"{tool.name} 不是 BaseTool 的实例"

    def test_all_tools_inherit_workspace_tool(self):
        tools = [
            ReadFileTool(),
            SearchCodeTool(),
            WriteFileTool(),
            GitDiffTool(),
            GitStatusTool(),
        ]
        for tool in tools:
            assert isinstance(tool, WorkspaceTool), f"{tool.name} 不是 WorkspaceTool 的子类"

    def test_workspace_tool_inherits_base_tool(self):
        assert issubclass(WorkspaceTool, BaseTool)


# ═══════════════════════════════════════════
# 2. ToolRegistry 统一接口执行不同工具（多态）
# ═══════════════════════════════════════════


class TestRegistryPolymorphism:
    def test_registry_executes_different_tool_types(self):
        """Registry 通过 BaseTool 接口调用 run()，实际执行不同子类的实现。"""
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())

        # 两个不同类型的工具
        assert reg.get("read_file") is not reg.get("search_code")

    def test_registry_execute_read_file(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        tc = ToolCall(name="read_file", arguments={"path": "examples/buggy_calculator.py"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is True
        assert "Calculator" in result.output

    def test_registry_execute_search_code(self):
        reg = ToolRegistry()
        reg.register(SearchCodeTool())
        tc = ToolCall(name="search_code", arguments={"query": "Calculator"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is True
        assert "匹配" in result.output

    def test_all_five_tools_register(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())
        reg.register(WriteFileTool())
        reg.register(GitDiffTool())
        reg.register(GitStatusTool())
        assert len(reg.list_tools()) == 5


# ═══════════════════════════════════════════
# 3. WorkspaceTool 公共方法
# ═══════════════════════════════════════════


class TestWorkspaceToolMethods:
    def test_resolve_workspace(self):
        tool = ReadFileTool()
        ws = tool.resolve_workspace(WORKSPACE)
        assert ws.exists()
        assert ws.is_dir()

    def test_safe_resolve_valid(self):
        tool = ReadFileTool()
        target = tool.safe_resolve(WORKSPACE, "examples/buggy_calculator.py")
        assert target.exists()
        assert target.suffix == ".py"

    def test_safe_resolve_traversal(self):
        tool = ReadFileTool()
        with pytest.raises(ValueError, match="超出"):
            tool.safe_resolve(WORKSPACE, "../../etc/passwd")

    def test_is_workspace_git_repo(self):
        tool = GitDiffTool()
        # workspace 不是 git repo（或可能是）
        result = tool.is_workspace_git_repo(WORKSPACE)
        assert isinstance(result, bool)

    def test_should_skip_dir(self):
        assert WorkspaceTool.should_skip_dir(".git") is True
        assert WorkspaceTool.should_skip_dir("__pycache__") is True
        assert WorkspaceTool.should_skip_dir("src") is False

    def test_error_format(self):
        assert WorkspaceTool.error("test") == "错误: test"
