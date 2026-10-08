"""External tool provider contract for pluggable tool sources."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.tools.base import BaseTool


@runtime_checkable
class ExternalToolProvider(Protocol):
    """Lifecycle and discovery boundary for non-native tool sources.

    MCP servers implement this contract today. Future remote API adapters can
    implement the same boundary without adding provider-specific logic to the
    Agent or ToolRegistry.
    """

    provider_id: str

    async def connect(self) -> Sequence[BaseTool]:
        """Initialize the provider and return its currently available tools."""

    def list_tools(self) -> Sequence[BaseTool]:
        """Return tools already discovered by this provider."""

    async def close(self) -> None:
        """Release provider resources."""
