from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.mcp.client import (
    BaseTransport,
    JSONRPCError,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
    MCPClient,
    MCPToolDefinition,
    SSETransport,
    StdioTransport,
)
from app.mcp.registry import (
    MCPServerConfig,
    MCPRegistry,
    MCPTool,
    mcp_registry,
)
from app.models.tool import ToolCall
from app.tools.base import BaseTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry

WORKSPACE = str(PROJECT_ROOT / "workspace")


# ═════════════════════════════════════════════════════════════════════
# 1. 模拟 Transport 辅助类
# ═════════════════════════════════════════════════════════════════════


class MockTransport(BaseTransport):
    """用于单元测试的模拟 MCP Transport。"""

    def __init__(self, tools_data: Optional[List[Dict[str, Any]]] = None) -> None:
        self.is_started = False
        self.is_closed = False
        self.sent_notifications: List[str] = []
        self.requests_received: List[tuple[str, Optional[Dict[str, Any]]]] = []
        self.tools_data = tools_data or [
            {
                "name": "list_files",
                "description": "List files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "calc_add",
                "description": "Add two numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            },
        ]

    async def start(self) -> None:
        self.is_started = True

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        self.requests_received.append((method, params))

        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            return {"tools": self.tools_data}
        elif method == "tools/call":
            name = params.get("name") if params else ""
            args = params.get("arguments", {}) if params else {}

            if name == "list_files":
                return {
                    "content": [{"type": "text", "text": f"file1.py\nfile2.py in {args.get('path')}"}],
                    "isError": False,
                }
            elif name == "calc_add":
                val = args.get("a", 0) + args.get("b", 0)
                return {
                    "content": [{"type": "text", "text": f"Result: {val}"}],
                    "isError": False,
                }
            elif name == "error_tool":
                return {
                    "content": [{"type": "text", "text": "Tool simulated error"}],
                    "isError": True,
                }
            elif name == "slow_tool":
                await asyncio.sleep(timeout + 0.5)
                return {"content": [{"type": "text", "text": "done"}]}
            else:
                raise RuntimeError(f"Unknown tool: {name}")

        raise RuntimeError(f"Unhandled method: {method}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        self.sent_notifications.append(method)

    async def close(self) -> None:
        self.is_closed = True


# ═════════════════════════════════════════════════════════════════════
# 2. 协议模型与消息序列化测试
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
# 3. MCPClient 生命周期与工具调用测试
# ═════════════════════════════════════════════════════════════════════


class TestMCPClient:
    def test_connect_handshake(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            assert client.is_connected is True
            assert client.server_info.get("name") == "mock-mcp-server"
            assert "notifications/initialized" in transport.sent_notifications
            await client.close()
            assert transport.is_closed is True

        asyncio.run(_run())

    def test_list_tools(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            tools = await client.list_tools()
            assert len(tools) == 2
            names = [t.name for t in tools]
            assert "list_files" in names
            assert "calc_add" in names
            await client.close()

        asyncio.run(_run())

    def test_call_tool_success(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            output = await client.call_tool("calc_add", {"a": 10, "b": 20})
            assert "Result: 30" in output
            await client.close()

        asyncio.run(_run())

    def test_call_tool_error(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            output = await client.call_tool("error_tool", {})
            assert output.startswith("错误:")
            assert "Tool simulated error" in output
            await client.close()

        asyncio.run(_run())

    def test_async_context_manager(self):
        async def _run():
            transport = MockTransport()
            async with MCPClient(transport=transport) as client:
                assert client.is_connected is True
                tools = await client.list_tools()
                assert len(tools) == 2
            assert transport.is_closed is True

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 4. MCPTool 动态包装与安全/超时测试
# ═════════════════════════════════════════════════════════════════════


class TestMCPTool:
    def test_mcp_tool_execution(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            tool = MCPTool(
                name="calc_add",
                description="Add numbers",
                parameters={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
                client=client,
                server_name="math_server",
            )

            # 验证 BaseTool 接口
            assert tool.name == "calc_add"
            schema = tool.to_openai_schema()
            assert schema["type"] == "function"
            assert schema["function"]["name"] == "calc_add"

            result = await tool.run(workspace_root=WORKSPACE, a=5, b=7)
            assert "Result: 12" in result
            await client.close()

        asyncio.run(_run())

    def test_path_traversal_blocked_relative(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            tool = MCPTool(
                name="list_files",
                description="List files",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                client=client,
                server_name="fs_server",
            )

            # 恶意路径穿越
            result = await tool.run(workspace_root=WORKSPACE, path="../../etc/passwd")
            assert "SECURITY_BLOCKED" in result
            assert "路径超出 workspace 范围" in result
            await client.close()

        asyncio.run(_run())

    def test_path_traversal_blocked_sensitive_file(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            tool = MCPTool(
                name="list_files",
                description="List files",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}},
                client=client,
                server_name="fs_server",
            )

            result = await tool.run(workspace_root=WORKSPACE, path=".env")
            assert "SECURITY_BLOCKED" in result
            assert "禁止访问敏感配置文件" in result
            await client.close()

        asyncio.run(_run())

    def test_timeout_interception(self):
        async def _run():
            transport = MockTransport()
            client = MCPClient(transport=transport)
            await client.connect()

            tool = MCPTool(
                name="slow_tool",
                description="A slow tool",
                parameters={"type": "object"},
                client=client,
                server_name="slow_server",
                timeout=0.1,  # 100ms 超时
            )

            result = await tool.run(workspace_root=WORKSPACE)
            assert "错误" in result
            assert "超时" in result
            await client.close()

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 5. MCPRegistry 多 Server 与 ToolRegistry 挂载测试
# ═════════════════════════════════════════════════════════════════════


class TestMCPRegistryIntegration:
    def test_registry_lifecycle_and_mounting(self):
        async def _run():
            reg = MCPRegistry()
            mock_transport = MockTransport()
            mock_client = MCPClient(transport=mock_transport)

            reg.register_client("mock_server", mock_client)
            tools = await reg.connect_server("mock_server")

            assert len(tools) == 2
            assert reg.get_tool("list_files") is not None

            # 挂载到 CodePilot 原生 ToolRegistry
            tool_reg = ToolRegistry()
            tool_reg.register(ReadFileTool())
            assert len(tool_reg.list_tools()) == 1

            count = reg.mount_to_tool_registry(tool_reg)
            assert count == 2
            assert len(tool_reg.list_tools()) == 3

            # 验证原生 execute() 多态调用 MCP 工具
            tc = ToolCall(name="calc_add", arguments={"a": 100, "b": 200})
            res = await tool_reg.execute(tc, WORKSPACE)
            assert res.success is True
            assert "Result: 300" in res.output

            # 验证统一元数据导出
            meta = tool_reg.get_tools_metadata()
            assert len(meta) == 3
            sources = {m["source"] for m in meta}
            assert "native" in sources
            assert "mcp" in sources

            await reg.disconnect_all()
            assert mock_transport.is_closed is True

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 6. Transport 层直接测试 (SSE & Stdio 模拟)
# ═════════════════════════════════════════════════════════════════════


class TestTransports:
    def test_sse_transport_post_success(self):
        async def _run():
            transport = SSETransport(url="http://mock-mcp-server/sse")
            await transport.start()

            # Mock httpx client post
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"protocolVersion": "2024-11-05"},
            }
            mock_resp.raise_for_status = MagicMock()

            with patch.object(transport._client, "post", new_callable=AsyncMock) as mock_post:
                mock_post.return_value = mock_resp
                result = await transport.send_request("initialize", {})
                assert result == {"protocolVersion": "2024-11-05"}

            await transport.close()

        asyncio.run(_run())

    def test_stdio_transport_closed_guard(self):
        async def _run():
            transport = StdioTransport(command="nonexistent_cmd_xyz")
            with pytest.raises(RuntimeError, match="未启动或已关闭"):
                await transport.send_request("ping", {})

        asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════
# 7. FastAPI API 端点测试 (GET /api/tools & GET /api/skills)
# ═════════════════════════════════════════════════════════════════════


class TestToolsAPI:
    def setup_method(self):
        self.client = TestClient(app)

    def test_get_api_tools(self):
        resp = self.client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "native_count" in data
        assert "mcp_count" in data
        assert "tools" in data
        assert data["native_count"] >= 6  # 默认包含 read_file, search_code 等

        # 检查工具属性结构
        first_tool = data["tools"][0]
        assert "name" in first_tool
        assert "description" in first_tool
        assert "source" in first_tool
        assert "parameters" in first_tool

    def test_get_api_skills(self):
        resp = self.client.get("/api/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert "tier1_core_tools" in data
        assert "tier2_mcp_skills" in data
        assert "total_skills" in data
        assert len(data["tier1_core_tools"]) >= 6

    def test_get_mcp_servers(self):
        resp = self.client.get("/api/mcp/servers")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "servers" in data
