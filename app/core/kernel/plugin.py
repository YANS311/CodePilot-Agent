from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.kernel.context import AgentContext


class BasePlugin(ABC):
    """DeepSeek-Harness 风格的插件抽象基类。

    所有功能（模型、工具、MCP、护栏、编排器）均通过实现此基类接入微内核。
    """

    name: str
    dependencies: List[str] = []

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.is_active: bool = False

    @abstractmethod
    async def activate(self, ctx: AgentContext) -> None:
        """插件激活：注册服务、挂载工具、订阅事件。"""
        ...

    @abstractmethod
    async def deactivate(self, ctx: AgentContext) -> None:
        """插件卸载：撤销工具、释放连接、清理临时资源（严格可逆，无泄漏）。"""
        ...
