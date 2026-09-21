from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.llm_client import ChatResponse, LLMClient
from app.mcp.client import BaseTransport, MCPClient
from app.mcp.registry import MCPTool
from app.tools.base import BaseTool
from app.tools.discovery import ToolDiscovery, default_tool_discovery
from app.tools.registry import ToolRegistry


class DummyTool(BaseTool):
    """测试用虚拟工具。"""

    def __init__(self, name: str, description: str, parameters: Optional[Dict[str, Any]] = None) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters or {"type": "object", "properties": {}}

    async def run(self, *, workspace_root: str, **kwargs: Any) -> str:
        return f"result of {self.name}"


class TestToolDiscovery:
    """ToolDiscovery 核心算法与选择策略测试。"""

    def test_keyword_matching_name_and_description(self):
        """测试根据任务关键词、同义词和工具描述匹配最适工具。"""
        async def _run():
            discovery = ToolDiscovery(default_top_k=3)
            tools = [
                DummyTool("read_file", "Read file contents from local filesystem"),
                DummyTool("write_file", "Write content to a file on local filesystem"),
                DummyTool("mcp_postgres_query_database", "Execute read-only SQL queries on remote Postgres DB"),
                DummyTool("git_commit", "Commit changes to local git repository"),
                DummyTool("audio_transcribe", "Convert spoken audio file to text transcript"),
            ]

            # 任务 1: 数据库查询
            selected1, meta1 = await discovery.select_tools_detailed(
                task="请查询数据库中的 users 表并获取统计数据",
                tools=tools,
                top_k=2,
            )
            assert len(selected1) == 2
            selected_names1 = [t.name for t in selected1]
            assert "mcp_postgres_query_database" in selected_names1
            assert meta1["scores"]["mcp_postgres_query_database"] > 0

            # 任务 2: 文件读取
            selected2, _ = await discovery.select_tools_detailed(
                task="查看并读取 main.py 的实现",
                tools=tools,
                top_k=2,
            )
            selected_names2 = [t.name for t in selected2]
            assert "read_file" in selected_names2

        asyncio.run(_run())

    def test_top_k_truncation(self):
        """测试候选工具数量超过 Top-K 时正确截断。"""
        async def _run():
            discovery = ToolDiscovery(default_top_k=4)
            tools = [DummyTool(f"custom_tool_{i}", f"General tool description for number {i}") for i in range(15)]

            selected, meta = await discovery.select_tools_detailed(
                task="any general task",
                tools=tools,
                top_k=4,
            )
            assert len(selected) == 4
            assert meta["candidate_count"] == 15
            assert len(meta["selected_tools"]) == 4

            # 当 tools 数量少于或等于 top_k 时全量保留
            selected_all, meta_all = await discovery.select_tools_detailed(
                task="any task",
                tools=tools[:3],
                top_k=5,
            )
            assert len(selected_all) == 3
            assert meta_all["candidate_count"] == 3

        asyncio.run(_run())

    def test_no_match_fallback(self):
        """测试在毫无关键词匹配的情况下平滑降级保底。"""
        async def _run():
            discovery = ToolDiscovery(default_top_k=3)
            tools = [
                DummyTool("misc_alpha", "Something completely unrelated to anything"),
                DummyTool("misc_beta", "Another completely arbitrary tool description"),
                DummyTool("read_file", "Read file from filesystem"),
                DummyTool("misc_gamma", "Third unrelated item"),
            ]

            # 完全不相关的随机字符（确保与任何工具名及描述均无重合）
            selected, meta = await discovery.select_tools_detailed(
                task="xyz123 foo999 bar777",
                tools=tools,
                top_k=2,
            )
            assert len(selected) == 2
            # 基础核心工具 read_file 拥有 baseline preference，应在无明确匹配时被优先召回
            assert any(t.name == "read_file" for t in selected)
            assert "Fallback" in meta["reason"] or "top-2" in meta["reason"]

        asyncio.run(_run())

    def test_native_and_mcp_heterogeneous_selection(self):
        """测试原生工具与动态 MCP 工具异构场景下的协同检索。"""
        async def _run():
            discovery = ToolDiscovery(default_top_k=3)

            class FakeTransport(BaseTransport):
                async def start(self): pass
                async def send_request(self, *args, **kwargs): return {}
                async def send_notification(self, *args, **kwargs): pass
                async def close(self): pass

            client = MCPClient(transport=FakeTransport())
            mcp_tool = MCPTool(
                name="mcp_github_create_pull_request",
                description="Create a pull request on GitHub repository with title and branch",
                parameters={"type": "object", "properties": {"title": {"type": "string"}}},
                client=client,
                server_name="github",
            )

            tools: List[BaseTool] = [
                DummyTool("read_file", "Read local file"),
                DummyTool("write_file", "Write local file"),
                DummyTool("code_edit", "Edit lines in source code"),
                mcp_tool,
                DummyTool("audio_play", "Play audio file"),
            ]

            # 任务命中 MCP 工具
            selected, meta = await discovery.select_tools_detailed(
                task="在 GitHub 仓库中创建 Pull Request 提交本次代码变更",
                tools=tools,
                top_k=3,
            )
            names = [t.name for t in selected]
            assert "mcp_github_create_pull_request" in names
            assert meta["scores"]["mcp_github_create_pull_request"] >= 3.0

        asyncio.run(_run())

    def test_active_skill_tag_boost(self):
        """测试当前激活 Skill 对特定领域工具的加成。"""
        async def _run():
            discovery = ToolDiscovery(default_top_k=2)
            tools = [
                DummyTool("general_helper", "General helper utility"),
                DummyTool("search_code", "Search code patterns in repository workspace"),
                DummyTool("sound_generator", "Generate sound effects"),
            ]

            # 激活 repository-explorer Skill 时，代码探索/搜索工具获得加成
            selected, meta = await discovery.select_tools_detailed(
                task="分析代码架构",
                tools=tools,
                top_k=2,
                active_skill="repository-explorer",
                skill_tags=["repo-exploration", "architecture-analysis"],
            )
            assert selected[0].name == "search_code"
            assert "skill_boost" in meta["reason"] or meta["scores"]["search_code"] > 4.0

        asyncio.run(_run())

    def test_react_agent_injects_top_k_tools_and_records_trace(self, tmp_path):
        """测试 ReActAgent 在运行前仅向 LLM 注入 Top-K 工具，并在 Trace 中记录检索决策。"""
        async def _run():
            registry = ToolRegistry()
            # 注册 12 个工具（超过默认 top_k 10）
            for i in range(10):
                registry.register(DummyTool(f"mcp_extra_tool_{i}", f"Unrelated auxiliary tool {i}"))
            registry.register(DummyTool("read_file", "Read file contents from filesystem"))
            registry.register(DummyTool("search_code", "Search for code patterns in repository"))

            assert len(registry.list_tools()) == 12

            # Mock LLM 客户端
            llm_mock = MagicMock(spec=LLMClient)
            captured_tools_schema: List[dict] = []

            async def mock_chat(messages, tools=None):
                if tools is not None:
                    captured_tools_schema.extend(tools)
                return ChatResponse(content="I have analyzed the repository.", tool_calls=[])

            llm_mock.chat = AsyncMock(side_effect=mock_chat)

            discovery = ToolDiscovery(default_top_k=5)
            agent = ReActAgent(
                llm=llm_mock,
                registry=registry,
                workspace_root=str(tmp_path),
                tool_discovery=discovery,
            )

            result = await agent.run("请在项目中检索 search_code 函数定义")

            # 验证仅向 LLM 注入了 top-k (5 个) 工具，而不是全部 12 个
            assert len(captured_tools_schema) == 5
            injected_names = [t["function"]["name"] for t in captured_tools_schema]
            assert "search_code" in injected_names

            # 验证 ExecutionTrace 正确记录了 tool_selection
            assert result.trace is not None
            assert result.trace.tool_selection is not None
            ts = result.trace.tool_selection
            assert ts["candidate_count"] == 12
            assert len(ts["selected_tools"]) == 5
            assert "search_code" in ts["selected_tools"]
            assert "scores" in ts
            assert "reason" in ts

        asyncio.run(_run())
