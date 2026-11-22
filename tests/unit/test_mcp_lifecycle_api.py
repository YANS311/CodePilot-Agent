import asyncio
from unittest.mock import AsyncMock

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.mcp.client import MCPToolDefinition
from app.mcp.registry import MCPRegistry


def test_mcp_reconnect_and_delete_close_owned_clients(monkeypatch):
    async def exercise():
        registry = MCPRegistry()
        created = []

        def register_server(config):
            client = AsyncMock()
            client.list_tools.return_value = [
                MCPToolDefinition(name="example", description="A test tool", inputSchema={})
            ]
            registry.register_client(config.name, client, config)
            created.append(client)

        monkeypatch.setattr("app.api.tools.mcp_registry", registry)
        monkeypatch.setattr(registry, "register_server", register_server)
        config = {"name": "demo", "transport": "stdio", "command": "python", "namespace_tools": True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            initial = await api.post("/api/mcp/connect", json=config)
            assert initial.status_code == 200
            assert initial.json()["tools_loaded"] == ["mcp_demo_example"]
            listed = (await api.get("/api/tools")).json()
            discovered = [tool for tool in listed["tools"] if tool["source"] == "mcp"]
            assert len(discovered) == 1
            assert discovered[0]["enabled"] is False

            replacement = await api.post("/api/mcp/connect", json=config)
            assert replacement.status_code == 200
            created[0].close.assert_awaited_once()
            created[1].close.assert_not_awaited()

            removed = await api.delete("/api/mcp/servers/demo")
            assert removed.status_code == 200
            created[1].close.assert_awaited_once()
            assert (await api.get("/api/tools")).json()["mcp_count"] == 0
            assert (await api.delete("/api/mcp/servers/demo")).status_code == 404

    asyncio.run(exercise())


def test_failed_mcp_tool_discovery_cleans_up_client(monkeypatch):
    async def exercise():
        registry = MCPRegistry()
        client = AsyncMock()
        client.list_tools.side_effect = ValueError("internal transport detail")

        def register_server(config):
            registry.register_client(config.name, client, config)

        monkeypatch.setattr("app.api.tools.mcp_registry", registry)
        monkeypatch.setattr(registry, "register_server", register_server)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            response = await api.post("/api/mcp/connect", json={"name": "demo", "command": "python"})
            assert response.status_code == 400
            assert "internal transport detail" not in response.text
            assert (await api.get("/api/mcp/servers")).json()["servers"] == []
        client.close.assert_awaited_once()

    asyncio.run(exercise())


def test_lifespan_closes_registered_mcp_client(monkeypatch):
    registry = MCPRegistry()
    client = AsyncMock()
    registry.register_client("demo", client)
    monkeypatch.setattr("app.main.mcp_registry", registry)

    with TestClient(app) as api:
        assert api.get("/health").status_code == 200
        client.close.assert_not_awaited()

    client.close.assert_awaited_once()
