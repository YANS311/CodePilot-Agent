from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.chat import _build_registry
from app.mcp.client import BaseTransport, MCPClient
from app.mcp.registry import MCPRegistry, MCPServerConfig, MCPTool, mcp_registry
from app.models.tool import ToolCall
from app.security.permission import PermissionAction, PermissionPolicy
from app.tools.registry import ToolRegistry


class FakeMCPTransport(BaseTransport):
    """纯内存 Mock 传输层，零网络/子进程开销。"""

    def __init__(self, tools_data: Optional[list[dict[str, Any]]] = None) -> None:
        self.is_started = False
        self.tools_data = tools_data or [
            {
                "name": "query_database",
                "description": "Execute read-only query on remote database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "SQL query statement"}
                    },
                    "required": ["sql"],
                },
            },
            {
                "name": "write_report",
                "description": "Write a report file to workspace",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Destination file path"},
                        "content": {"type": "string", "description": "Content of the report"},
                    },
                    "required": ["path", "content"],
                },
            },
        ]

    async def start(self) -> None:
        self.is_started = True

    async def send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0
    ) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "fake-data-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            return {"tools": self.tools_data}
        elif method == "tools/call":
            tool_name = (params or {}).get("name", "")
            args = (params or {}).get("arguments", {})
            if tool_name == "query_database":
                return {
                    "content": [{"type": "text", "text": f"Result for query '{args.get('sql', '')}': 42 rows."}],
                    "isError": False,
                }
            elif tool_name == "write_report":
                return {
                    "content": [{"type": "text", "text": f"Successfully wrote report to {args.get('path', '')}"}],
                    "isError": False,
                }
            return {
                "content": [{"type": "text", "text": f"Executed tool '{tool_name}'"}],
                "isError": False,
            }
        raise ValueError(f"Unsupported mock method: {method}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        pass

    async def close(self) -> None:
        self.is_started = False


class TestMCPRuntimeAgentFlow:
    """验证 MCP Runtime 到 Agent Execution 的完整连接闭环。"""

    def test_case1_and_case2_connect_and_generate_mcptools(self):
        """Case 1 & Case 2: MCPRegistry 可以连接 fake server，并自动将 tools/list 生成 MCPTool。"""
        async def _run():
            transport = FakeMCPTransport()
            client = MCPClient(transport=transport, client_name="test-agent")
            registry = MCPRegistry()

            cfg = MCPServerConfig(
                name="fake_db",
                transport="stdio",
                command="custom",
                namespace_tools=True,
            )
            registry.register_client("fake_db", client, config=cfg)

            # 执行握手与工具发现
            tools = await registry.connect_server("fake_db")

            assert len(tools) == 2
            tool_names = [t.name for t in tools]
            assert "mcp_fake_db_query_database" in tool_names
            assert "mcp_fake_db_write_report" in tool_names

            for t in tools:
                assert isinstance(t, MCPTool)
                assert t.server_name == "fake_db"

            # 清理连接
            await registry.disconnect_all()

        asyncio.run(_run())

    def test_case3_and_case4_mount_and_openai_schema(self):
        """Case 3 & Case 4: mount_mcp_registry 后，ToolRegistry.get_schemas() 包含 MCP tool，且符合 OpenAI 规范。"""
        async def _run():
            transport = FakeMCPTransport()
            client = MCPClient(transport=transport)
            custom_mcp_reg = MCPRegistry()

            cfg = MCPServerConfig(
                name="analytics",
                transport="stdio",
                command="custom",
                namespace_tools=False,
            )
            custom_mcp_reg.register_client("analytics", client, config=cfg)
            await custom_mcp_reg.connect_server("analytics")

            # 挂载到全新的 ToolRegistry
            tool_reg = ToolRegistry()
            tool_reg.mount_mcp_registry(custom_mcp_reg)

            schemas = tool_reg.get_schemas()
            schema_map = {s["function"]["name"]: s for s in schemas}

            # 确认包含 MCP tool
            assert "query_database" in schema_map
            assert "write_report" in schema_map

            # Case 4: 校验 OpenAI Function Calling 规范结构
            query_schema = schema_map["query_database"]
            assert query_schema["type"] == "function"
            assert "function" in query_schema
            assert query_schema["function"]["name"] == "query_database"
            assert query_schema["function"]["description"] == "Execute read-only query on remote database"
            assert query_schema["function"]["parameters"]["type"] == "object"
            assert "sql" in query_schema["function"]["parameters"]["properties"]
            assert query_schema["function"]["parameters"]["required"] == ["sql"]

            await custom_mcp_reg.disconnect_all()

        asyncio.run(_run())

    def test_chat_build_registry_includes_mcp_tools(self):
        """验证 app/api/chat.py 中 _build_registry() 真正完成闭环挂载。"""
        async def _run():
            transport = FakeMCPTransport()
            client = MCPClient(transport=transport)

            # 注册并连接至全局 mcp_registry 单例
            cfg = MCPServerConfig(
                name="global_fake",
                transport="stdio",
                command="custom",
                namespace_tools=True,
            )
            try:
                mcp_registry.register_client("global_fake", client, config=cfg)
                await mcp_registry.connect_server("global_fake")

                # 调用 chat 模块的 _build_registry()
                agent_registry = _build_registry()
                schemas = agent_registry.get_schemas()
                schema_names = [s["function"]["name"] for s in schemas]

                # 验证 Native tools 完好无损
                assert "read_file" in schema_names
                assert "search_code" in schema_names
                assert "write_file" in schema_names
                assert "git_diff" in schema_names
                assert "git_status" in schema_names
                assert "run_tests" in schema_names

                # 验证 MCP tools 已成功挂载入 Agent registry
                assert "mcp_global_fake_query_database" in schema_names
                assert "mcp_global_fake_write_report" in schema_names
            finally:
                await mcp_registry.disconnect_server("global_fake")
                mcp_registry.unregister_server("global_fake")

        asyncio.run(_run())

    def test_security_guardrail_and_permission_policy_on_mcp_tool(self, tmp_path: Path):
        """Step 4: 安全回归 — 验证 MCP Tool 执行仍然受到权限策略与安全沙箱的严格拦截。"""
        async def _run():
            transport = FakeMCPTransport()
            client = MCPClient(transport=transport)
            custom_mcp_reg = MCPRegistry()

            cfg = MCPServerConfig(
                name="sec_test",
                transport="stdio",
                command="custom",
                namespace_tools=True,
            )
            custom_mcp_reg.register_client("sec_test", client, config=cfg)
            await custom_mcp_reg.connect_server("sec_test")

            tool_reg = ToolRegistry()
            tool_reg.mount_mcp_registry(custom_mcp_reg)

            workspace_root = str(tmp_path)

            # 1. 验证 PermissionPolicy 只读策略能够拦截写操作 MCP Tool
            read_only_policy = PermissionPolicy.read_only()
            write_call = ToolCall(
                name="mcp_sec_test_write_report",
                arguments={"path": "report.txt", "content": "secret data"},
            )
            perm_res = await tool_reg.execute(
                write_call, workspace_root=workspace_root, permission_policy=read_only_policy
            )
            assert perm_res.success is False
            assert perm_res.metadata.get("permission_blocked") is True
            assert "PERMISSION_DENIED" in perm_res.output

            # 2. 验证路径穿越攻击被安全拦截 (即使权限通过)
            standard_policy = PermissionPolicy.standard_coding()
            traversal_call = ToolCall(
                name="mcp_sec_test_write_report",
                arguments={"path": "../../etc/shadow", "content": "malicious content"},
            )
            traversal_res = await tool_reg.execute(
                traversal_call, workspace_root=workspace_root, permission_policy=standard_policy
            )
            assert "SECURITY_BLOCKED" in traversal_res.output

            # 3. 验证合规调用正常通过
            valid_query = ToolCall(
                name="mcp_sec_test_query_database",
                arguments={"sql": "SELECT COUNT(*) FROM users;"},
            )
            valid_res = await tool_reg.execute(
                valid_query, workspace_root=workspace_root, permission_policy=standard_policy
            )
            assert valid_res.success is True
            assert "42 rows" in valid_res.output

            await custom_mcp_reg.disconnect_all()

        asyncio.run(_run())
