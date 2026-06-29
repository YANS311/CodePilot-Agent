from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent, AgentRunResult
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.models.tool import AgentStep, ToolCall
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool
from app.memory.embeddings import EmbeddingModel

WORKSPACE = str(PROJECT_ROOT / "workspace")
_HAS_EMBEDDING_MODEL = EmbeddingModel().is_available()


def _make_registry(**extra_tools) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    reg.register(WriteFileTool())
    for tool in extra_tools.values():
        reg.register(tool)
    return reg


def _mock_llm(responses: list[ChatResponse]) -> LLMClient:
    llm = AsyncMock(spec=LLMClient)
    llm.chat = AsyncMock(side_effect=responses)
    return llm


# ═══════════════════════════════════════════
# 1. read_file 目录路径被拦截
# ═══════════════════════════════════════════


class TestReadFileDirectoryBlocked:
    def test_dot_path_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="read_file", arguments={"path": "."})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "目录" in result.output

    def test_slash_path_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="read_file", arguments={"path": "/"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False

    def test_dot_slash_path_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="read_file", arguments={"path": "./"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False

    def test_empty_path_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="read_file", arguments={"path": ""})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "不能为空" in result.output

    def test_real_directory_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="read_file", arguments={"path": "examples"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "目录" in result.output


# ═══════════════════════════════════════════
# 2. write_file 无意义文件名被拦截
# ═══════════════════════════════════════════


class TestWriteFileGuardrails:
    def test_empty_path_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="write_file", arguments={"path": "", "content": "x"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "不能为空" in result.output

    def test_bad_suffix_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="write_file", arguments={"path": "test.exe", "content": "x"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "不允许" in result.output

    def test_meaningless_name_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="write_file", arguments={"path": "1cm.py", "content": "x"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "无意义" in result.output

    def test_tmp_py_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="write_file", arguments={"path": "tmp.py", "content": "x"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False

    def test_valid_py_allowed(self):
        reg = _make_registry()
        tc = ToolCall(name="write_file", arguments={"path": "valid_module.py", "content": "# ok"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is True


# ═══════════════════════════════════════════
# 3. search_code 空 query 被拦截
# ═══════════════════════════════════════════


class TestSearchCodeGuardrails:
    def test_empty_query_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="search_code", arguments={"query": ""})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert "不能为空" in result.output

    def test_short_query_blocked(self):
        reg = _make_registry()
        tc = ToolCall(name="search_code", arguments={"query": "a"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is False
        assert ">= 2" in result.output

    def test_valid_query_allowed(self):
        reg = _make_registry()
        tc = ToolCall(name="search_code", arguments={"query": "Calculator"})
        result = asyncio.run(
            reg.execute(tc, WORKSPACE)
        )
        assert result.success is True


# ═══════════════════════════════════════════
# 4. AgentRunResult 包含 steps
# ═══════════════════════════════════════════


class TestAgentRunResultSteps:
    def test_direct_answer_has_empty_steps(self):
        llm = _mock_llm([
            ChatResponse(content="直接回答。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("测试任务")
        )
        assert isinstance(result, AgentRunResult)
        assert result.steps == []
        assert result.thoughts == []

    @pytest.mark.skipif(not _HAS_EMBEDDING_MODEL, reason="Intent router needs embedding model for correct routing")
    def test_tool_call_creates_step(self):
        llm = _mock_llm([
            ChatResponse(
                content="我需要搜索 Calculator 类",
                tool_calls=[
                    ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
                ],
            ),
            ChatResponse(content="Calculator 类在 examples/buggy_calculator.py 中。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("找 Calculator 类"
        ))
        assert len(result.steps) == 1
        step = result.steps[0]
        assert step.step_id == 1
        assert step.thought == "我需要搜索 Calculator 类"
        assert step.tool_name == "search_code"
        assert step.tool_args == {"query": "Calculator"}
        assert step.success is True
        assert len(result.thoughts) == 1
        assert result.thoughts[0] == "我需要搜索 Calculator 类"

    @pytest.mark.skipif(not _HAS_EMBEDDING_MODEL, reason="Intent router needs embedding model for correct routing")
    def test_multi_step_records_all(self):
        llm = _mock_llm([
            ChatResponse(
                content="先搜索位置",
                tool_calls=[
                    ToolCallInfo(id="tc1", name="search_code", arguments={"query": "Calculator"}),
                ],
            ),
            ChatResponse(
                content="再读取文件内容",
                tool_calls=[
                    ToolCallInfo(id="tc2", name="read_file", arguments={"path": "examples/buggy_calculator.py"}),
                ],
            ),
            ChatResponse(content="找到了。"),
        ])
        agent = ReActAgent(llm, _make_registry(), WORKSPACE)
        result = asyncio.run(
            agent.run("多步任务")
        )
        assert len(result.steps) == 2
        assert result.steps[0].tool_name == "search_code"
        assert result.steps[1].tool_name == "read_file"
        assert len(result.thoughts) == 2


# ═══════════════════════════════════════════
# 5. AgentStep 数据结构
# ═══════════════════════════════════════════


class TestAgentStepModel:
    def test_agent_step_fields(self):
        step = AgentStep(
            step_id=1,
            thought="test thought",
            action="search_code({'query': 'test'})",
            tool_name="search_code",
            tool_args={"query": "test"},
            observation="found 3 matches",
            success=True,
        )
        assert step.step_id == 1
        assert step.thought == "test thought"
        assert step.tool_name == "search_code"
        assert step.success is True

    def test_agent_step_defaults(self):
        step = AgentStep(step_id=1)
        assert step.thought == ""
        assert step.tool_name == ""
        assert step.success is True
        assert step.tool_args == {}


# ═══════════════════════════════════════════
# 6. git_status 在非 git repo 下返回提示
# ═══════════════════════════════════════════


class TestGitStatus:
    def test_non_git_repo_returns_hint(self):
        """在非 git 目录下运行 git_status 应返回提示信息。"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tool = GitStatusTool()
            result = asyncio.run(
                tool.run(workspace_root=tmpdir)
            )
            assert "不是" in result or "git" in result.lower()

    def test_nonexistent_workspace(self):
        tool = GitStatusTool()
        result = asyncio.run(
            tool.run(workspace_root="/nonexistent/path/xyz")
        )
        assert "错误" in result
        assert "不存在" in result


# ═══════════════════════════════════════════
# 7. 前端 API 返回 steps 字段
# ═══════════════════════════════════════════


class TestAPIReturnsSteps:
    def test_chat_api_includes_steps(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        with patch("app.api.chat._build_agent") as mock_build:
            mock_agent = AsyncMock()
            mock_agent.run.return_value = AgentRunResult(
                answer="测试回答",
                tool_calls_count=1,
                tool_results=[],
                messages=[],
                thoughts=["我的思考"],
                steps=[
                    AgentStep(
                        step_id=1,
                        thought="我的思考",
                        action="search_code({'query': 'test'})",
                        tool_name="search_code",
                        tool_args={"query": "test"},
                        observation="found results",
                        success=True,
                    ),
                ],
            )
            mock_build.return_value = mock_agent

            resp = client.post("/api/chat", json={"task": "测试"})
            assert resp.status_code == 200
            data = resp.json()
            assert "steps" in data
            assert "thoughts" in data
            assert len(data["steps"]) == 1
            assert data["steps"][0]["tool_name"] == "search_code"
            assert data["steps"][0]["thought"] == "我的思考"
            assert data["thoughts"] == ["我的思考"]
