from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.mcp.client import (
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPClient,
    MCPToolDefinition,
    StdioTransport,
)
from app.mcp.registry import (
    MCPServerConfig,
    MCPRegistry,
    MCPTool,
)
from app.models.tool import ToolCall
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry

WORKSPACE = str(PROJECT_ROOT / "workspace")
PYTHON_EXE = sys.executable


# ═════════════════════════════════════════════════════════════════════
# 1. 协议模型与消息序列化测试 (真实数据模型)
# ═════════════════════════════════════════════════════════════════════


class TestMCPProtocolModels:
    def test_jsonrpc_request_serialization(self):
        req = JSONRPCRequest(id=1, method="tools/list", params={})
        data = req.model_dump()
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == 1
        assert data["method"] == "tools/list"

    def test_jsonrpc_response_success(self):
        res = JSONRPCResponse(id=1, result={"tools": []})
        assert res.result == {"tools": []}
        assert res.error is None

    def test_jsonrpc_response_error(self):
        err = JSONRPCError(code=-32601, message="Method not found")
        res = JSONRPCResponse(id=2, error=err)
        assert res.error.code == -32601
        assert res.error.message == "Method not found"

    def test_mcp_tool_definition(self):
        t = MCPToolDefinition(name="test_tool", description="A test tool")
        assert t.name == "test_tool"
        assert t.inputSchema["type"] == "object"


# ═════════════════════════════════════════════════════════════════════
# 2. 真实 Stdio 进程与 MCPClient 交互测试 (真实 OS 子进程与管道)
# ═════════════════════════════════════════════════════════════════════


class TestRealStdioMCPClient:
    def test_real_stdio_connect_and_handshake(self):
        """测试启动真实的 Python MCP Server 子进程并执行 JSON-RPC 握手。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            client = MCPClient(transport=transport)
            await client.connect()

            assert client.is_connected is True
            assert client.server_info.get("name") == "codepilot-mcp-server"

            # 关闭并验证真实子进程被安全终止
            await client.close()
            assert client.is_connected is False

        asyncio.run(_run())

    def test_real_stdio_list_tools(self):
        """测试从真实的 MCP Server 子进程拉取可用工具列表。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            async with MCPClient(transport=transport) as client:
                tools = await client.list_tools()
                assert len(tools) >= 4
                names = [t.name for t in tools]
                assert "echo" in names
                assert "calculate" in names
                assert "get_system_info" in names
                assert "list_dir" in names

        asyncio.run(_run())

    def test_real_stdio_call_tool(self):
        """测试向真实的 MCP Server 子进程发起 tools/call 调用并获取真实计算结果。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            async with MCPClient(transport=transport) as client:
                # 1. 调用 echo 工具
                echo_out = await client.call_tool("echo", {"message": "Hello CodePilot Real MCP"})
                assert "Echo: Hello CodePilot Real MCP" in echo_out

                # 2. 调用 calculate 工具
                calc_out = await client.call_tool("calculate", {"op": "multiply", "a": 7, "b": 8})
                assert "56" in calc_out

                # 3. 调用 get_system_info 工具
                sys_out = await client.call_tool("get_system_info", {})
                assert "python" in sys_out.lower() or "pid" in sys_out

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 3. 动态 MCPTool 包装与真实安全防御/超时测试
# ═════════════════════════════════════════════════════════════════════


class TestRealMCPToolSecurity:
    def test_real_mcp_tool_execution(self):
        """验证动态生成的 MCPTool 实例与 BaseTool 的完全兼容性及真实执行。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            async with MCPClient(transport=transport) as client:
                tool = MCPTool(
                    name="calculate",
                    description="Perform calculation",
                    parameters={"type": "object", "properties": {"op": {"type": "string"}, "a": {"type": "number"}, "b": {"type": "number"}}},
                    client=client,
                    server_name="math_service",
                )

                # 验证 OpenAI Function Calling Schema 导出
                schema = tool.to_openai_schema()
                assert schema["type"] == "function"
                assert schema["function"]["name"] == "calculate"

                # 真实执行计算
                res = await tool.run(workspace_root=WORKSPACE, op="add", a=25, b=75)
                assert "100" in res

        asyncio.run(_run())

    def test_real_path_traversal_blocking(self):
        """测试对真实文件列表 MCP 工具实施 Workspace 路径穿越拦截。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            async with MCPClient(transport=transport) as client:
                tool = MCPTool(
                    name="list_dir",
                    description="List directory",
                    parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                    client=client,
                    server_name="fs_service",
                )

                # 1. 拦截相对越界路径
                res1 = await tool.run(workspace_root=WORKSPACE, path="../../etc/passwd")
                assert "SECURITY_BLOCKED" in res1
                assert "路径超出 workspace 范围" in res1

                # 2. 拦截敏感文件
                res2 = await tool.run(workspace_root=WORKSPACE, path=".env")
                assert "SECURITY_BLOCKED" in res2
                assert "禁止访问敏感配置文件" in res2

                # 3. 正常 workspace 路径允许放行并执行
                res3 = await tool.run(workspace_root=WORKSPACE, path="examples")
                assert "SECURITY_BLOCKED" not in res3

        asyncio.run(_run())

    def test_real_timeout_interception(self):
        """测试超时熔断保护。"""
        async def _run():
            transport = StdioTransport(
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            async with MCPClient(transport=transport) as client:
                tool = MCPTool(
                    name="echo",
                    description="Echo",
                    parameters={"type": "object"},
                    client=client,
                    server_name="echo_service",
                    timeout=0.000001,  # 极短超时强制触发
                )
                res = await tool.run(workspace_root=WORKSPACE, message="slow")
                assert "超时" in res or "Timeout" in res

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 4. MCPRegistry 与 ToolRegistry 真实多 Server 挂载与调用
# ═════════════════════════════════════════════════════════════════════


class TestRealMCPRegistryIntegration:
    def test_real_registry_multi_server_mounting_and_execution(self):
        """测试使用真实配置注册两个真实的 stdio MCP 子进程并挂载至 ToolRegistry。"""
        async def _run():
            reg = MCPRegistry()

            # 注册第一个真实 MCP Server
            cfg1 = MCPServerConfig(
                name="server_primary",
                transport="stdio",
                command=PYTHON_EXE,
                args=["-m", "app.mcp.server"],
                cwd=str(PROJECT_ROOT),
            )
            reg.register_server(cfg1)

            # 连接并拉取真实工具
            tools = await reg.connect_server("server_primary")
            assert len(tools) >= 4

            # 挂载到原生 ToolRegistry
            tool_reg = ToolRegistry()
            tool_reg.register(ReadFileTool())
            assert len(tool_reg.list_tools()) == 1

            count = reg.mount_to_tool_registry(tool_reg)
            assert count >= 4
            assert len(tool_reg.list_tools()) >= 5

            # 验证多态调用真实 MCP 工具
            tc = ToolCall(name="calculate", arguments={"op": "add", "a": 123, "b": 456})
            res = await tool_reg.execute(tc, WORKSPACE)
            assert res.success is True
            assert "579" in res.output

            # 验证统一元数据导出
            meta = tool_reg.get_tools_metadata()
            assert len(meta) >= 5
            sources = {m["source"] for m in meta}
            assert "native" in sources
            assert "mcp" in sources

            # 逆序干净释放所有子进程
            await reg.disconnect_all()

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 5. FastAPI 接口真实调用测试
# ═════════════════════════════════════════════════════════════════════


class TestRealToolsAPI:
    def setup_method(self):
        self.client = TestClient(app)

    def test_get_api_tools(self):
        resp = self.client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 6
        assert data["native_count"] >= 6
        assert len(data["tools"]) >= 6

    def test_get_api_skills(self):
        resp = self.client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "tier1_core_tools" in data
        assert len(data["tier1_core_tools"]) >= 6

    def test_get_mcp_servers(self):
        resp = self.client.get("/api/mcp/servers")
        assert resp.status_code == 200
        data = resp.json()
        assert "servers" in data
