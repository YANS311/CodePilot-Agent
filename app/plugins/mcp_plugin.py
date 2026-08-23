from __future__ import annotations

from typing import Any, Optional
from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin
from app.mcp.registry import MCPRegistry, mcp_registry
from app.tools.registry import ToolRegistry


class MCPPlugin(BasePlugin):
    """MCP 插件：管理 MCP 客户端连接并将远端工具无缝接入 ToolRegistry。"""

    name = "mcp"
    dependencies = ["native_tools"]

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._registry_instance: Optional[MCPRegistry] = None

    async def activate(self, ctx: AgentContext) -> None:
        self._registry_instance = self.config.get("registry", mcp_registry)
        ctx.provide("mcp_registry", self._registry_instance)

        tool_registry: ToolRegistry = ctx.inject("tool_registry")
        self._registry_instance.mount_to_tool_registry(tool_registry)

        # 订阅会话结束事件，做可逆断开
        ctx.events.on("session:end", self._on_session_end)
        await ctx.events.emit(
            "mcp:ready",
            {"connected_servers": len(self._registry_instance.list_servers())},
        )

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.events.off("session:end", self._on_session_end)
        if self._registry_instance:
            await self._registry_instance.disconnect_all()
        ctx.unprovide("mcp_registry")
        self._registry_instance = None

    async def _on_session_end(self, event: Any) -> None:
        if self._registry_instance:
            await self._registry_instance.disconnect_all()
