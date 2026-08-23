"""app/mcp — Model Context Protocol (MCP) 插件适配层。

提供轻量级 stdio / SSE MCP 客户端、安全拦截校验、动态 BaseTool 转换及统一注册管理。
"""

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

__all__ = [
    "BaseTransport",
    "JSONRPCError",
    "JSONRPCNotification",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "MCPClient",
    "MCPToolDefinition",
    "SSETransport",
    "StdioTransport",
    "MCPServerConfig",
    "MCPRegistry",
    "MCPTool",
    "mcp_registry",
]
