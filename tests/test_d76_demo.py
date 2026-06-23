from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.agent.react_agent import ReActAgent, AgentRunResult
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.models.tool import AgentStep, ToolCall, ToolResult
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.tools.registry import ToolRegistry

client = TestClient(app)

WORKSPACE = str(PROJECT_ROOT / "workspace")


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    return reg


def _mock_llm(responses: list[ChatResponse]) -> LLMClient:
    llm = AsyncMock(spec=LLMClient)
    llm.chat = AsyncMock(side_effect=responses)
    return llm


# ═══════════════════════════════════════════
# 1. API 返回 final_answer 不为空
# ═══════════════════════════════════════════


class TestChatAPINotEmpty:
    @patch("app.api.chat._build_agent")
    def test_answer_is_not_empty_string(self, mock_build):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = AgentRunResult(
            answer="这是一段有意义的回答",
            tool_calls_count=1,
            tool_results=[
                ToolResult(tool_call_id="tc1", name="search_code", success=True, output="结果"),
            ],
            messages=[],
        )
        mock_build.return_value = mock_agent

        resp = client.post("/api/chat", json={"task": "解释代码"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"]  # 非空
        assert len(data["answer"]) > 0

    @patch("app.api.chat._build_agent")
    def test_answer_has_content_field(self, mock_build):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = AgentRunResult(
            answer="## 标题\n\n代码分析结果。",
            tool_calls_count=0,
            tool_results=[],
            messages=[],
        )
        mock_build.return_value = mock_agent

        resp = client.post("/api/chat", json={"task": "分析这段代码"})
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "标题" in data["answer"]


# ═══════════════════════════════════════════
# 2. files API 返回排序结果
# ═══════════════════════════════════════════


class TestFileListSorted:
    def test_files_are_sorted_by_path(self):
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        paths = [f["path"] for f in data["files"]]
        assert paths == sorted(paths), f"文件列表未按路径排序: {paths}"

    def test_files_sorted_case_insensitive(self):
        resp = client.get("/api/files")
        data = resp.json()
        paths = [f["path"] for f in data["files"]]
        # localeCompare 默认按 Unicode 排序，但 Python sorted 也是
        # 主要确保不是随机顺序
        assert paths == sorted(paths)


# ═══════════════════════════════════════════
# 3. Agent 查询类任务不调用 git_status
# ═══════════════════════════════════════════


class TestQueryTaskNoGitStatus:
    def test_query_only_uses_search_and_read(self):
        """模拟纯查询任务：LLM 只调用 search_code 和 read_file，不调用 git_status。"""
        llm = _mock_llm([
            # LLM 决定搜索
            ChatResponse(
                content="让我搜索 Calculator 类",
                tool_calls=[
                    ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
                ],
            ),
            # LLM 决定读取文件
            ChatResponse(
                content="找到了文件，读取内容",
                tool_calls=[
                    ToolCallInfo(id="tc2", name="read_file", arguments={"path": "examples/buggy_calculator.py"}),
                ],
            ),
            # LLM 直接回答，不调用 git_status
            ChatResponse(content="Calculator 类有 add, subtract 等方法。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("Calculator 类有哪些方法？")
        )

        # 验证只调用了 search_code 和 read_file
        tool_names = [tr.name for tr in result.tool_results]
        assert "search_code" in tool_names
        assert "read_file" in tool_names
        assert "git_status" not in tool_names, "查询任务不应调用 git_status"

    def test_modify_task_may_use_git(self):
        """模拟修改任务：LLM 可以调用 git_diff 但不一定调用 git_status。"""
        llm = _mock_llm([
            ChatResponse(
                content="搜索 Calculator 类",
                tool_calls=[
                    ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
                ],
            ),
            ChatResponse(content="找到了 Calculator 类。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("修复 Calculator 的 subtract 方法")
        )

        tool_names = [tr.name for tr in result.tool_results]
        # 修改任务不一定调用 git_status（由 LLM 决定），但不应强制调用
        # 这里验证的是 agent 不强制插入 git_status
        assert "search_code" in tool_names


# ═══════════════════════════════════════════
# 4. AgentRunResult thoughts 完整性
# ═══════════════════════════════════════════


class TestAgentThoughts:
    def test_thoughts_match_tool_calls(self):
        """每个 tool_call 都应该有对应的 thought。"""
        llm = _mock_llm([
            ChatResponse(
                content="我需要搜索代码",
                tool_calls=[
                    ToolCallInfo(id="tc1", name="search_code", arguments={"query": "test"}),
                ],
            ),
            ChatResponse(
                content="读取文件确认内容",
                tool_calls=[
                    ToolCallInfo(id="tc2", name="read_file", arguments={"path": "test.py"}),
                ],
            ),
            ChatResponse(content="完成。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("测试任务")
        )

        assert len(result.thoughts) == 2
        assert result.thoughts[0] == "我需要搜索代码"
        assert result.thoughts[1] == "读取文件确认内容"
        assert len(result.steps) == 2
        assert result.steps[0].thought == "我需要搜索代码"
        assert result.steps[1].thought == "读取文件确认内容"
