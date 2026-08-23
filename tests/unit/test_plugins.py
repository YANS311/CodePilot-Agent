from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.config import Settings
from app.core.kernel import AgentContext, PluginManager
from app.core.llm_client import LLMClient
from app.mcp.client import MCPClient, StdioTransport
from app.mcp.registry import MCPServerConfig, MCPRegistry
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
PYTHON_EXE = sys.executable


class TestRealPluginMatrix:
    def test_full_real_plugin_lifecycle_and_agent_assembly(self):
        """测试使用真实组件（真实 Stdio MCP 子进程、原生工具集、Guardrail、ReAct 编排器）完成全流程组装与可逆卸载。"""
        async def _run():
            ctx = AgentContext()
            mgr = PluginManager(ctx)

            # 1. 构造真实 MCP Registry (连接真实的 Python stdio MCP Server)
            real_mcp_reg = MCPRegistry()
            cfg = MCPServerConfig(
                name="stdio_runtime_srv",
                transport="stdio",
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            real_mcp_reg.register_server(cfg)
            await real_mcp_reg.connect_server("stdio_runtime_srv")

            # 2. 乱序注册所有 Phase 2 核心插件
            mgr.register(
                ReActOrchestratorPlugin(
                    config={"workspace_root": WORKSPACE, "max_tool_calls": 15}
                )
            )
            mgr.register(MCPPlugin(config={"registry": real_mcp_reg}))
            mgr.register(
                ModelAdapterPlugin(
                    config={"client": LLMClient(settings=Settings(ci_mode=True))}
                )
            )
            mgr.register(NativeToolsPlugin())
            mgr.register(GuardrailPlugin())

            # 3. 激活所有插件（按依赖拓扑序自动激活）
            await mgr.activate_all()

            # 验证依赖注入完整性
            llm = ctx.inject("llm_client")
            assert llm is not None

            tool_reg = ctx.inject_typed("tool_registry", ToolRegistry)
            assert tool_reg.get("read_file") is not None
            assert tool_reg.get("write_file") is not None
            assert tool_reg.get("code_edit") is not None
            assert tool_reg.get("calculate") is not None  # 真实 MCP calculate 工具成功挂载
            assert tool_reg.get("echo") is not None       # 真实 MCP echo 工具成功挂载

            guardrail = ctx.inject_typed("guardrail", ToolGuardrail)
            assert guardrail is not None

            agent = ctx.inject_typed("agent", ReActAgent)
            assert isinstance(agent, ReActAgent)
            assert agent._workspace_root == WORKSPACE
            assert agent._max_tool_calls == 15

            # 验证事件溯源日志
            events = ctx.events.get_events()
            event_types = [e.type for e in events]
            assert "model:ready" in event_types
            assert "tools:registered" in event_types
            assert "mcp:ready" in event_types
            assert "orchestrator:ready" in event_types

            # 4. 可逆安全卸载
            await mgr.deactivate_all()

            # 验证所有服务已被全部注销
            for srv_name in ["llm_client", "tool_registry", "mcp_registry", "guardrail", "agent"]:
                with pytest.raises(KeyError):
                    ctx.inject(srv_name)

        asyncio.run(_run())

    def test_real_mcp_plugin_session_end_cleanup(self):
        """测试 session:end 事件触发真实子进程安全清理与断开。"""
        async def _run():
            ctx = AgentContext()
            mgr = PluginManager(ctx)

            real_mcp_reg = MCPRegistry()
            cfg = MCPServerConfig(
                name="stdio_cleanup_srv",
                transport="stdio",
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            real_mcp_reg.register_server(cfg)
            await real_mcp_reg.connect_server("stdio_cleanup_srv")

            mgr.register(NativeToolsPlugin())
            mgr.register(MCPPlugin(config={"registry": real_mcp_reg}))
            await mgr.activate_all()

            client = real_mcp_reg.get_client("stdio_cleanup_srv")
            assert client is not None and client.is_connected is True

            # 触发 session:end 事件
            await ctx.events.emit("session:end", {"session_id": "sess_real_001"})
            assert client.is_connected is False

            await mgr.deactivate_all()

        asyncio.run(_run())

    def test_model_adapter_plugin_config_instantiation(self):
        """测试 ModelAdapterPlugin 根据实际配置参数构建客户端。"""
        async def _run():
            ctx = AgentContext()
            plugin = ModelAdapterPlugin(
                config={
                    "api_key": "sk-real-config-key",
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
