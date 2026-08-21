from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.config import Settings
from app.core.kernel import AgentContext, PluginManager
from app.core.llm_client import LLMClient
from app.mcp.client import BaseTransport, MCPClient
from app.mcp.registry import MCPRegistry
from app.plugins import (
    GuardrailPlugin,
    MCPPlugin,
    ModelAdapterPlugin,
    NativeToolsPlugin,
    ReActOrchestratorPlugin,
)
from app.security.tool_guardrail import ToolGuardrail
from app.tools.registry import ToolRegistry

WORKSPACE = str(PROJECT_ROOT / "workspace")


class MockMCPTransport(BaseTransport):
    def __init__(self) -> None:
        self.is_closed = False

    async def start(self) -> None:
        pass

    async def send_request(self, method: str, params: Any = None, timeout: float = 30.0) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "test-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "plugin_mcp_echo",
                        "description": "Echo back args",
                        "inputSchema": {"type": "object", "properties": {"msg": {"type": "string"}}},
                    }
                ]
            }
        elif method == "tools/call":
            return {
                "content": [{"type": "text", "text": f"Echo: {params.get('arguments', {}).get('msg')}"}],
                "isError": False,
            }
        return {}

    async def send_notification(self, method: str, params: Any = None) -> None:
        pass

    async def close(self) -> None:
        self.is_closed = True


class TestPluginMatrix:
    def test_full_plugin_lifecycle_and_agent_assembly(self):
        async def _run():
            ctx = AgentContext()
            mgr = PluginManager(ctx)

            # 1. 构造 Mock MCP Registry
            mock_mcp_reg = MCPRegistry()
            mock_transport = MockMCPTransport()
            mock_client = MCPClient(transport=mock_transport)
            mock_mcp_reg.register_client("mock_srv", mock_client)
            await mock_mcp_reg.connect_server("mock_srv")

            # 2. 乱序注册所有 Phase 2 核心插件
            mgr.register(
                ReActOrchestratorPlugin(
                    config={"workspace_root": WORKSPACE, "max_tool_calls": 10}
                )
            )
            mgr.register(MCPPlugin(config={"registry": mock_mcp_reg}))
            mgr.register(
                ModelAdapterPlugin(
                    config={"client": LLMClient(settings=Settings(ci_mode=True))}
                )
            )
            mgr.register(NativeToolsPlugin())
            mgr.register(GuardrailPlugin())

            # 3. 激活所有插件（按依赖拓扑序自动激活）
            await mgr.activate_all()

            # 验证服务注入完整性
            llm = ctx.inject("llm_client")
            assert llm is not None

            tool_reg = ctx.inject_typed("tool_registry", ToolRegistry)
            assert tool_reg.get("read_file") is not None
            assert tool_reg.get("write_file") is not None
            assert tool_reg.get("code_edit") is not None
            assert tool_reg.get("plugin_mcp_echo") is not None  # MCP 工具已成功挂载

            guardrail = ctx.inject_typed("guardrail", ToolGuardrail)
            assert guardrail is not None

            agent = ctx.inject_typed("agent", ReActAgent)
            assert isinstance(agent, ReActAgent)
            assert agent._workspace_root == WORKSPACE
            assert agent._max_tool_calls == 10

            # 4. 验证事件溯源日志
            events = ctx.events.get_events()
            event_types = [e.type for e in events]
            assert "model:ready" in event_types
            assert "tools:registered" in event_types
            assert "mcp:ready" in event_types
            assert "orchestrator:ready" in event_types

            # 5. 可逆卸载验证 (deactivate_all)
            await mgr.deactivate_all()

            # 验证所有服务已干净移除
            for srv_name in ["llm_client", "tool_registry", "mcp_registry", "guardrail", "agent"]:
                with pytest.raises(KeyError):
                    ctx.inject(srv_name)

            assert mock_transport.is_closed is True

        asyncio.run(_run())

    def test_mcp_plugin_session_end_event_cleanup(self):
        async def _run():
            ctx = AgentContext()
            mgr = PluginManager(ctx)

            mock_mcp_reg = MCPRegistry()
            mock_transport = MockMCPTransport()
            mock_client = MCPClient(transport=mock_transport)
            mock_mcp_reg.register_client("srv_session", mock_client)
            await mock_mcp_reg.connect_server("srv_session")

            mgr.register(NativeToolsPlugin())
            mgr.register(MCPPlugin(config={"registry": mock_mcp_reg}))
            await mgr.activate_all()

            # 触发 session:end 事件
            await ctx.events.emit("session:end", {"session_id": "sess_001"})
            assert mock_transport.is_closed is True

            await mgr.deactivate_all()

        asyncio.run(_run())

    def test_model_adapter_plugin_config_instantiation(self):
        async def _run():
            ctx = AgentContext()
            plugin = ModelAdapterPlugin(
                config={
                    "api_key": "test-key-123",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-coder",
                    "ci_mode": True,
                }
            )
            await plugin.activate(ctx)

            client = ctx.inject_typed("llm_client", LLMClient)
            assert client is not None

            await plugin.deactivate(ctx)
            with pytest.raises(KeyError):
                ctx.inject("llm_client")

        asyncio.run(_run())
