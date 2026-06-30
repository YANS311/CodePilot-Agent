from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.write_file import WriteFileTool
from app.tools.git_diff import GitDiffTool
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.tools.registry import ToolRegistry
from app.models.tool import ToolCall
from app.agent.react_agent import ReActAgent, AgentRunResult
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from unittest.mock import AsyncMock

WORKSPACE = str(PROJECT_ROOT / "workspace")


# ═══════════════════════════════════════════
# WriteFileTool 测试
# ═══════════════════════════════════════════


class TestWriteFile:
    def setup_method(self):
        self.tool = WriteFileTool()

    def test_write_new_file(self):
        target = Path(WORKSPACE) / "_test_new_file.txt"
        try:
            result = asyncio.run(
                self.tool.run(
                    workspace_root=WORKSPACE,
                    path="_test_new_file.txt",
                    content="hello world",
                )
            )
            assert "已写入" in result
            assert "_test_new_file.txt" in result
            assert target.read_text(encoding="utf-8") == "hello world"
        finally:
            if target.exists():
                target.unlink()

    def test_overwrite_existing_file(self):
        target = Path(WORKSPACE) / "_test_overwrite.txt"
        try:
            target.write_text("old content", encoding="utf-8")
            result = asyncio.run(
                self.tool.run(
                    workspace_root=WORKSPACE,
                    path="_test_overwrite.txt",
                    content="new content",
                )
            )
            assert "已写入" in result
            assert target.read_text(encoding="utf-8") == "new content"
        finally:
            if target.exists():
                target.unlink()

    def test_auto_create_parent_dirs(self):
        target = Path(WORKSPACE) / "_test_nested" / "deep" / "file.txt"
        try:
            result = asyncio.run(
                self.tool.run(
                    workspace_root=WORKSPACE,
                    path="_test_nested/deep/file.txt",
                    content="nested content",
                )
            )
            assert "已写入" in result
            assert target.read_text(encoding="utf-8") == "nested content"
        finally:
            import shutil
            nested = Path(WORKSPACE) / "_test_nested"
            if nested.exists():
                shutil.rmtree(nested)

    def test_path_traversal_blocked(self):
        result = asyncio.run(
            self.tool.run(
                workspace_root=WORKSPACE,
                path="../../etc/passwd",
                content="evil",
            )
        )
        assert "错误" in result
        assert "超出" in result

    def test_write_to_git_blocked(self):
        result = asyncio.run(
            self.tool.run(
                workspace_root=WORKSPACE,
                path=".git/config",
                content="evil",
            )
        )
        assert "错误" in result
        assert ".git" in result

    def test_content_too_large(self):
        huge = "x" * (100 * 1024 + 1)  # 100KB + 1 byte
        result = asyncio.run(
            self.tool.run(
                workspace_root=WORKSPACE,
                path="_test_huge.txt",
                content=huge,
            )
        )
        assert "错误" in result
        assert "100KB" in result

    def test_returns_byte_count(self):
        target = Path(WORKSPACE) / "_test_bytes.txt"
        try:
            result = asyncio.run(
                self.tool.run(
                    workspace_root=WORKSPACE,
                    path="_test_bytes.txt",
                    content="abc",
                )
            )
            assert "3 bytes" in result
        finally:
            if target.exists():
                target.unlink()


# ═══════════════════════════════════════════
# GitDiffTool 测试
# ═══════════════════════════════════════════


class TestGitDiff:
    def setup_method(self):
        self.tool = GitDiffTool()

    def test_non_git_repo_returns_error(self):
        """临时目录不是 git repo，应返回错误。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = asyncio.run(
                self.tool.run(workspace_root=tmp)
            )
            assert "错误" in result
            assert "git 仓库" in result

    def test_git_repo_returns_diff(self):
        """当前项目是 git repo，应能返回 diff 或 clean。"""
        result = asyncio.run(
            self.tool.run(workspace_root=WORKSPACE)
        )
        # 当前 workspace/examples 下的文件可能已 commit，也可能有未暂存变更
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nonexistent_workspace(self):
        result = asyncio.run(
            self.tool.run(workspace_root="/nonexistent/path")
        )
        assert "错误" in result
        assert "不存在" in result


# ═══════════════════════════════════════════
# Registry 注册 4 个工具
# ═══════════════════════════════════════════


class TestRegistryAllTools:
    def test_register_all_four(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())
        reg.register(WriteFileTool())
        reg.register(GitDiffTool())
        names = {t.name for t in reg.list_tools()}
        assert names == {"read_file", "search_code", "write_file", "git_diff"}

    def test_schemas_count(self):
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())
        reg.register(WriteFileTool())
        reg.register(GitDiffTool())
        assert len(reg.get_schemas()) == 4


# ═══════════════════════════════════════════
# Agent 修复 buggy_calculator 的 mock 测试
# ═══════════════════════════════════════════


def _make_full_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    reg.register(WriteFileTool())
    reg.register(GitDiffTool())
    return reg


class TestAgentFixCode:
    def test_fix_buggy_calculator(self):
        """Agent 执行 search → read → write → diff → answer 完整流程。"""
        llm = AsyncMock(spec=LLMClient)
        llm.chat = AsyncMock(side_effect=[
            # 1. search_code: 搜索 Calculator
            ChatResponse(tool_calls=[
                ToolCallInfo(
                    id="tc1", name="search_code",
                    arguments={"query": "Calculator"},
                ),
            ]),
            # 2. read_file: 读取文件内容
            ChatResponse(tool_calls=[
                ToolCallInfo(
                    id="tc2", name="read_file",
                    arguments={"path": "examples/buggy_calculator.py"},
                ),
            ]),
            # 3. write_file: 修复 subtract 方法 (a+b → a-b)
            ChatResponse(tool_calls=[
                ToolCallInfo(
                    id="tc3", name="write_file",
                    arguments={
                        "path": "_test_fixed_calculator.py",
                        "content": FIXED_CALCULATOR,
                    },
                ),
            ]),
            # 4. git_diff: 验证变更
            ChatResponse(tool_calls=[
                ToolCallInfo(
                    id="tc4", name="git_diff",
                    arguments={},
                ),
            ]),
            # 5. 最终回答
            ChatResponse(content="已修复 subtract 方法：将 a + b 改为 a - b。可通过 git_diff 确认变更。"),
        ])

        agent = ReActAgent(llm, _make_full_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("把 buggy_calculator.py 里的 subtract 函数改正确"
                       "，它错误地用了加法而不是减法。"
                       "只修复 subtract，其他方法不动。"
                       "用 _test_ 前缀写入测试文件，不要覆盖原文件。"
                       "文件路径: _test_fixed_calculator.py")
        )

        # 验证调用了 4 个工具
        assert result.tool_calls_count == 4
        tool_names = [tr.name for tr in result.tool_results]
        assert tool_names == ["search_code", "read_file", "write_file", "git_diff"]

        # 验证 write_file 写入的文件确实存在
        written = Path(WORKSPACE) / "_test_fixed_calculator.py"
        try:
            assert written.exists()
            content = written.read_text(encoding="utf-8")
            assert "a - b" in content  # 修复后应有减法

            # 验证最终回答不声称测试通过
            assert "测试通过" not in result.answer
            assert "运行正确" not in result.answer
            assert "已修复" in result.answer
        finally:
            if written.exists():
                written.unlink()


# 修复后的 calculator 内容（只改 subtract）
FIXED_CALCULATOR = '''\
"""一个故意包含 Bug 的计算器模块，用于测试 Agent 的搜索和修复能力。"""


class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def subtract(self, a: int, b: int) -> int:
        return a - b

    def multiply(self, a: int, b: int) -> int:
        return a * b

    def divide(self, a: int, b: int) -> float:
        return a / b

    def power(self, base: int, exp: int) -> int:
        result = 1
        for _ in range(exp):
            result *= base
        return result

    def factorial(self, n: int) -> int:
        if n < 0:
            raise ValueError("负数没有阶乘")
        result = 1
        for i in range(1, n):
            result *= i
        return result


def main():
    calc = Calculator()
    print(f"2 + 3 = {calc.add(2, 3)}")
    print(f"5 - 3 = {calc.subtract(5, 3)}")
    print(f"4 * 3 = {calc.multiply(4, 3)}")
    print(f"10 / 3 = {calc.divide(10, 3)}")
    print(f"2^8 = {calc.power(2, 8)}")
    print(f"5! = {calc.factorial(5)}")


if __name__ == "__main__":
    main()
'''
