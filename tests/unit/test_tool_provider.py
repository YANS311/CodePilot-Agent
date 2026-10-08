from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.mcp.registry import MCPRegistry
from app.tools.base import BaseTool
from app.tools.provider import ExternalToolProvider
from app.tools.registry import ToolRegistry


class DummyTool(BaseTool):
    description = "A provider test tool"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, name: str, output: str = "ok") -> None:
        self.name = name
        self.output = output

    async def run(self, *, workspace_root: str, **kwargs: Any) -> str:
        return self.output


class FakeProvider:
    provider_id = "remote-api-test"

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools = tools
        self.connected = False

    async def connect(self) -> list[BaseTool]:
        self.connected = True
        return self.list_tools()

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools)

    async def close(self) -> None:
        self.connected = False


class TestExternalToolProvider:
    def test_protocol_is_structural(self):
        provider = FakeProvider([DummyTool("remote_search")])
        assert isinstance(provider, ExternalToolProvider)
        assert isinstance(MCPRegistry(), ExternalToolProvider)

    def test_provider_lifecycle_is_transport_agnostic(self):
        provider = FakeProvider([DummyTool("remote_search")])

        tools = asyncio.run(provider.connect())
        assert provider.connected is True
        assert [tool.name for tool in tools] == ["remote_search"]

        asyncio.run(provider.close())
        assert provider.connected is False

    def test_mount_provider_registers_tools(self):
        registry = ToolRegistry()
        provider = FakeProvider([DummyTool("remote_search"), DummyTool("remote_read")])

        mounted = registry.mount_provider(provider)

        assert mounted == 2
        assert registry.get("remote_search") is not None
        assert registry.get("remote_read") is not None

    def test_collision_is_rejected_before_any_provider_tool_is_mounted(self):
        registry = ToolRegistry()
        original = DummyTool("existing", output="native")
        registry.register(original)
        provider = FakeProvider([DummyTool("new_tool"), DummyTool("existing")])

        with pytest.raises(ValueError, match="conflicts with registered tools"):
            registry.mount_provider(provider)

        assert registry.get("existing") is original
        assert registry.get("new_tool") is None

    def test_explicit_replace_preserves_mcp_compatibility(self):
        registry = ToolRegistry()
        original = DummyTool("shared", output="native")
        replacement = DummyTool("shared", output="external")
        registry.register(original)

        mounted = registry.mount_provider(FakeProvider([replacement]), replace=True)

        assert mounted == 1
        assert registry.get("shared") is replacement

    def test_duplicate_provider_snapshot_is_rejected(self):
        registry = ToolRegistry()
        provider = FakeProvider([DummyTool("duplicate"), DummyTool("duplicate")])

        with pytest.raises(ValueError, match="returned duplicate tools"):
            registry.mount_provider(provider)

        assert registry.list_tools() == []
