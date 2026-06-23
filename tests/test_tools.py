from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# ── 确保项目根目录在 sys.path ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.base import BaseTool
from app.tools.registry import ToolRegistry
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.models.tool import ToolCall

# workspace 指向项目内的示例目录
WORKSPACE = str(PROJECT_ROOT / "workspace")


# ═══════════════════════════════════════════
# 1. ToolRegistry 注册
# ═══════════════════════════════════════════


class TestRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = ReadFileTool()
        reg.register(tool)
        assert reg.get("read_file") is tool

    def test_list_tools(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())
        names = [t.name for t in reg.list_tools()]
        assert "read_file" in names
        assert "search_code" in names

    def test_duplicate_register_raises(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        with pytest.raises(ValueError, match="已注册"):
            reg.register(ReadFileTool())

    def test_get_unknown_returns_none(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_get_schemas_format(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        schemas = reg.get_schemas()
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "read_file"
        assert "parameters" in schema["function"]

    def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        tc = ToolCall(name="no_such_tool", arguments={})
        result = asyncio.run(reg.execute(tc, WORKSPACE))
        assert result.success is False
        assert "未知工具" in result.output


# ═══════════════════════════════════════════
# 2. ReadFileTool
# ═══════════════════════════════════════════


class TestReadFile:
    def setup_method(self):
        self.tool = ReadFileTool()

    def test_read_existing_file(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, path="examples/buggy_calculator.py")
        )
        assert "Calculator" in result
        assert "class" in result

    def test_read_nonexistent_file(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, path="no_such_file.py")
        )
        assert "错误" in result
        assert "不存在" in result

    def test_path_traversal_blocked(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, path="../../etc/passwd")
        )
        assert "错误" in result
        assert "超出" in result

    def test_read_directory_returns_error(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, path="examples")
        )
        assert "错误" in result
        assert "目录" in result


# ═══════════════════════════════════════════
# 3. SearchCodeTool
# ═══════════════════════════════════════════


class TestSearchCode:
    def setup_method(self):
        self.tool = SearchCodeTool()

    def test_search_finds_match(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, query="Calculator")
        )
        assert "buggy_calculator.py" in result
        assert "匹配" in result

    def test_search_no_match(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, query="xyzzy_not_exist_999")
        )
        assert "未找到" in result

    def test_search_with_file_pattern(self):
        result = asyncio.run(
            self.tool.run(
                workspace_root=WORKSPACE,
                query="Todo",
                file_pattern="*.py",
            )
        )
        assert "todo_service.py" in result

    def test_search_skips_git_dir(self):
        """搜索结果不应包含 .git 目录下的文件。"""
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, query="HEAD")
        )
        assert ".git" not in result

    def test_search_with_invalid_regex(self):
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE, query="[invalid")
        )
        assert "错误" in result
        assert "正则" in result

    def test_search_nonexistent_workspace(self):
        result = asyncio.run(
            self.tool.run(workspace_root="/nonexistent/path", query="test")
        )
        assert "错误" in result
        assert "不存在" in result
