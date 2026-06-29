from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent, AgentRunResult
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.tools.registry import ToolRegistry
from app.memory.embeddings import EmbeddingModel

WORKSPACE = str(PROJECT_ROOT / "workspace")
_HAS_EMBEDDING_MODEL = EmbeddingModel().is_available()


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    return reg


def _mock_llm(responses: list[ChatResponse]) -> LLMClient:
    """创建一个按顺序返回预设响应的 mock LLMClient。"""
    llm = AsyncMock(spec=LLMClient)
    llm.chat = AsyncMock(side_effect=responses)
    return llm


# ═══════════════════════════════════════════
# 1. 直接回答 — 不需要工具
# ═══════════════════════════════════════════


class TestAgentDirectAnswer:
    def test_direct_answer(self):
        """LLM 不调用工具，直接给出回答。"""
        llm = _mock_llm([
            ChatResponse(content="FastAPI 是一个现代 Python Web 框架。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("FastAPI 是什么？")
        )
        assert "FastAPI" in result.answer
        assert result.tool_calls_count == 0


# ═══════════════════════════════════════════
# 2. 单次工具调用
# ═══════════════════════════════════════════


@pytest.mark.skipif(not _HAS_EMBEDDING_MODEL, reason="Intent router needs embedding model for correct routing")
class TestAgentSingleToolCall:
    def test_single_search(self):
        """LLM 调用一次 search_code，然后给出回答。"""
        llm = _mock_llm([
            # 第一次：LLM 决定搜索
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
            ]),
            # 第二次：基于搜索结果回答
            ChatResponse(content="Calculator 类定义在 workspace/examples/buggy_calculator.py 中。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("项目里有 Calculator 类吗？")
        )
        assert "Calculator" in result.answer
        assert result.tool_calls_count == 1
        assert len(result.tool_results) == 1
        assert result.tool_results[0].success is True


# ═══════════════════════════════════════════
# 3. 多步工具调用 — 搜索 → 读取
# ═══════════════════════════════════════════


class TestAgentMultiStep:
    def test_search_then_read(self):
        """LLM 先 search_code，再 read_file，最后回答。"""
        llm = _mock_llm([
            # 第一次：搜索
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
            ]),
            # 第二次：读取文件
            ChatResponse(tool_calls=[
                ToolCallInfo(
                    id="tc2",
                    name="read_file",
                    arguments={"path": "examples/buggy_calculator.py"},
                ),
            ]),
            # 第三次：基于文件内容回答
            ChatResponse(content="Calculator 类有 add, subtract, multiply, divide 等方法。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("项目里有没有 ToolRegistry 类？")
        )
        assert result.tool_calls_count == 2
        assert len(result.tool_results) == 2
        assert "Calculator" in result.answer

        # 验证消息历史包含关键消息（预算提示可能插入额外 system 消息）
        msgs = result.messages
        roles = [m["role"] for m in msgs]
        assert "system" in roles
        assert "user" in roles
        assert "assistant" in roles
        assert "tool" in roles
        # 至少有 2 个 tool 消息（search_code + read_file）
        assert roles.count("tool") >= 2
        # 最后一条是 assistant（最终回答）
        assert roles[-1] == "assistant"


# ═══════════════════════════════════════════
# 4. 工具调用上限
# ═══════════════════════════════════════════


@pytest.mark.skipif(not _HAS_EMBEDDING_MODEL, reason="Intent router needs embedding model for correct routing")
class TestAgentMaxToolCalls:
    def test_stops_at_limit(self):
        """超过 max_tool_calls 后强制停止。"""
        # 构造 5 个 tool_call 响应 + 1 个最终回答（max=5）
        tool_call_responses = [
            ChatResponse(tool_calls=[
                ToolCallInfo(id=f"tc{i}", name="search_code", arguments={"query": f"q{i}"}),
            ])
            for i in range(5)
        ]
        final = ChatResponse(content="最终总结。")
        llm = _mock_llm(tool_call_responses + [final])

        agent = ReActAgent(llm, _make_registry(), WORKSPACE, max_tool_calls=5)
        result = asyncio.run(
            agent.run("无限搜索任务")
        )
        assert result.tool_calls_count == 5
        assert "最终总结" in result.answer


# ═══════════════════════════════════════════
# 5. 工具执行失败
# ═══════════════════════════════════════════


class TestAgentToolFailure:
    def test_tool_error_reported(self):
        """工具返回错误信息时，Agent 将其传回 LLM。"""
        llm = _mock_llm([
            # LLM 读一个不存在的文件
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="read_file", arguments={"path": "nonexistent.py"}),
            ]),
            # LLM 基于工具返回的错误信息回答
            ChatResponse(content="文件 nonexistent.py 不存在。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("读取 nonexistent.py")
        )
        assert result.tool_calls_count == 1
        # ReadFileTool 不抛异常，返回错误字符串；Registry 标记 success=True
        assert result.tool_results[0].success is True
        assert "不存在" in result.tool_results[0].output


# ═══════════════════════════════════════════
# 6. AgentRunResult 数据完整性
# ═══════════════════════════════════════════


class TestAgentRunResult:
    def test_result_fields(self):
        """验证 AgentRunResult 所有字段正确填充。"""
        llm = _mock_llm([
            ChatResponse(content="简单回答。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("测试任务")
        )
        assert isinstance(result, AgentRunResult)
        assert result.answer == "简单回答。"
        assert result.tool_calls_count == 0
        assert result.tool_results == []
        assert len(result.messages) == 3  # system + user + assistant
