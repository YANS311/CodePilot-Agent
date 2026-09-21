from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.mcp.client import BaseTransport, MCPClient
from app.mcp.registry import (
    MCPRegistry,
    MCPServerConfig,
    ServerRuntimeState,
    ServerStatus,
    mcp_registry,
)
from app.mcp.storage import MCPConfigStore, mcp_config_store


class FakeMCPTransport(BaseTransport):
    """纯内存 Mock 传输层。"""

    def __init__(self, tools_data: Optional[list[dict[str, Any]]] = None) -> None:
        self.is_started = False
        self.tools_data = tools_data or [
            {
                "name": "calc_sum",
                "description": "Calculate sum of numbers",
                "inputSchema": {
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                    "required": ["a", "b"],
                },
            }
        ]

    async def start(self) -> None:
        self.is_started = True

    async def send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0
    ) -> Any:
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "mock-server", "version": "1.0.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            return {"tools": self.tools_data}
        elif method == "tools/call":
            return {"content": [{"type": "text", "text": "OK"}], "isError": False}
        raise ValueError(f"Unsupported mock method: {method}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        pass

    async def close(self) -> None:
        self.is_started = False


class FailingMCPTransport(BaseTransport):
    """模拟连接必定失败的传输层。"""

    async def start(self) -> None:
        raise ConnectionRefusedError("Connection refused by remote host on 127.0.0.1:9999")

    async def send_request(
        self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0
    ) -> Any:
        raise ConnectionRefusedError("Connection refused by remote host on 127.0.0.1:9999")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        pass

    async def close(self) -> None:
        pass


class TestMCPLifecycle:
    """MCP Server 生命周期与持久化恢复集成测试。"""

    def test_case1_config_store_persistence(self, tmp_path):
        """Case 1: MCPConfigStore 保存、读取与删除，验证 JSON 文件格式正确。"""
        store_file = tmp_path / "mcp_servers.json"
        store = MCPConfigStore(storage_path=store_file)

        # 初始为空
        assert store.load_servers() == {}

        cfg1 = MCPServerConfig(
            name="demo_db",
            transport="stdio",
            command="python",
            args=["-m", "db_server"],
            env={"DB_PORT": "5432"},
        )
        cfg2 = MCPServerConfig(
            name="demo_web",
            transport="sse",
            url="http://localhost:8000/sse",
        )

        store.save_server(cfg1)
        store.save_server(cfg2)

        # 验证文件落盘与内容格式
        assert store_file.exists()
        with open(store_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)

        assert "mcpServers" in disk_data
        assert "demo_db" in disk_data["mcpServers"]
        assert disk_data["mcpServers"]["demo_db"]["command"] == "python"
        assert disk_data["mcpServers"]["demo_db"]["args"] == ["-m", "db_server"]
        assert "demo_web" in disk_data["mcpServers"]
        assert disk_data["mcpServers"]["demo_web"]["url"] == "http://localhost:8000/sse"

        # 验证 load_servers 与 get_server
        loaded = store.load_servers()
        assert len(loaded) == 2
        assert loaded["demo_db"].name == "demo_db"
        assert store.get_server("demo_db") is not None

        # 验证删除
        removed = store.remove_server("demo_db")
        assert removed is True
        assert store.get_server("demo_db") is None
        assert len(store.load_servers()) == 1

    def test_case2_restart_simulation_restore(self, tmp_path):
        """Case 2: 模拟系统重启，新实例从持久化配置中恢复 Server。"""
        async def _run():
            store_file = tmp_path / "mcp_servers.json"
            store1 = MCPConfigStore(storage_path=store_file)

            cfg = MCPServerConfig(
                name="restart_test_srv",
                transport="stdio",
                command="mock_cmd",
                args=["--flag"],
            )
            store1.save_server(cfg)

            # 模拟重启：实例化全新的 store 和 registry
            store2 = MCPConfigStore(storage_path=store_file)
            new_registry = MCPRegistry()
            assert new_registry.list_servers() == []

            with patch("app.mcp.registry.StdioTransport", return_value=FakeMCPTransport()):
                loaded_tools = await new_registry.startup_restore(config_store=store2)

            # 验证 Server 已恢复并处于连接状态
            assert "restart_test_srv" in new_registry.list_servers()
            state = new_registry.get_server_state("restart_test_srv")
            assert state is not None
            assert state.status == ServerStatus.CONNECTED
            assert len(loaded_tools) >= 1

            await new_registry.disconnect_all()

        asyncio.run(_run())

    def test_case3_startup_restore_populates_tools_and_runtime_states(self, tmp_path):
        """Case 3: startup_restore 自动连接并拉取 tools，填充运行时状态。"""
        async def _run():
            store_file = tmp_path / "mcp_servers.json"
            store = MCPConfigStore(storage_path=store_file)

            cfg = MCPServerConfig(
                name="calc_service",
                transport="stdio",
                command="python",
                args=["calc.py"],
                namespace_tools=True,
            )
            store.save_server(cfg)

            registry = MCPRegistry()
            fake_tools = [
                {
                    "name": "add",
                    "description": "Add two numbers",
                    "inputSchema": {"type": "object"},
                },
                {
                    "name": "sub",
                    "description": "Subtract two numbers",
                    "inputSchema": {"type": "object"},
                },
            ]

            with patch("app.mcp.registry.StdioTransport", return_value=FakeMCPTransport(tools_data=fake_tools)):
                await registry.startup_restore(config_store=store)

            # 验证工具被注册且命名空间生效
            tool_names = list(registry._tools.keys())
            assert "mcp_calc_service_add" in tool_names
            assert "mcp_calc_service_sub" in tool_names

            # 验证状态跟踪
            state = registry.get_server_state("calc_service")
            assert state.status == ServerStatus.CONNECTED
            assert state.tool_count == 2
            assert state.last_error is None
            assert state.last_connected_at is not None

            await registry.disconnect_all()

        asyncio.run(_run())

    def test_case4_failed_server_isolation(self, tmp_path):
        """Case 4: 单个 MCP Server 恢复失败时被标记为 FAILED，不影响其他正常 Server 连接。"""
        async def _run():
            store_file = tmp_path / "mcp_servers.json"
            store = MCPConfigStore(storage_path=store_file)

            cfg_bad = MCPServerConfig(
                name="bad_server",
                transport="stdio",
                command="non_existent_command",
            )
            cfg_good = MCPServerConfig(
                name="good_server",
                transport="stdio",
                command="good_command",
            )
            store.save_server(cfg_bad)
            store.save_server(cfg_good)

            registry = MCPRegistry()

            def _transport_factory(*args, **kwargs):
                cmd = kwargs.get("command") or (args[0] if args else "")
                if "non_existent_command" in cmd:
                    return FailingMCPTransport()
                return FakeMCPTransport()

            with patch("app.mcp.registry.StdioTransport", side_effect=_transport_factory):
                # startup_restore 不应抛出未捕获异常
                await registry.startup_restore(config_store=store)

            # 验证 bad_server 状态隔离与错误记录
            bad_state = registry.get_server_state("bad_server")
            assert bad_state is not None
            assert bad_state.status == ServerStatus.FAILED
            assert "Connection refused" in (bad_state.last_error or "")
            assert bad_state.tool_count == 0

            # 验证 good_server 正常启动与可用
            good_state = registry.get_server_state("good_server")
            assert good_state is not None
            assert good_state.status == ServerStatus.CONNECTED
            assert good_state.tool_count == 1
            assert good_state.last_error is None

            # 检查 tools 集合中只包含 good_server 的工具
            assert any(t.server_name == "good_server" for t in registry._tools.values())
            assert not any(t.server_name == "bad_server" for t in registry._tools.values())

            await registry.disconnect_all()

        asyncio.run(_run())

    def test_case5_delete_server_cleanup_api_and_store(self, tmp_path, monkeypatch):
        """Case 5: DELETE /api/mcp/servers/{name} 清理连接、内存注册表与持久化文件。"""
        store_file = tmp_path / "mcp_servers.json"
        monkeypatch.setattr(mcp_config_store, "storage_path", store_file)

        # 预置一个已注册 server
        cfg = MCPServerConfig(
            name="del_target_srv",
            transport="stdio",
            command="mock",
        )
        mcp_config_store.save_server(cfg)

        fake_transport = FakeMCPTransport()
        client_mock = MCPClient(transport=fake_transport)
        mcp_registry.register_client("del_target_srv", client_mock, config=cfg)

        async def _connect():
            await mcp_registry.connect_server("del_target_srv")

        asyncio.run(_connect())

        assert "del_target_srv" in mcp_registry.list_servers()
        assert mcp_config_store.get_server("del_target_srv") is not None

        client = TestClient(app)

        # 检查 GET /api/mcp/status 包含该 server
        resp_status = client.get("/api/mcp/status")
        assert resp_status.status_code == 200
        server_names = [s["name"] for s in resp_status.json()["servers"]]
        assert "del_target_srv" in server_names

        # 调用 DELETE 接口删除
        resp_del = client.delete("/api/mcp/servers/del_target_srv")
        assert resp_del.status_code == 200
        assert resp_del.json() == {"status": "unregistered", "server": "del_target_srv"}

        # 验证内存注销
        assert mcp_registry.get_client("del_target_srv") is None
        assert mcp_registry.get_server_state("del_target_srv") is None
        assert not any(t.server_name == "del_target_srv" for t in mcp_registry._tools.values())

        # 验证磁盘持久化删除
        assert mcp_config_store.get_server("del_target_srv") is None
        loaded_disk = mcp_config_store.load_servers()
        assert "del_target_srv" not in loaded_disk

        # 验证重复删除返回 404
        resp_del_again = client.delete("/api/mcp/servers/del_target_srv")
        assert resp_del_again.status_code == 404
