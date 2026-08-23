from __future__ import annotations

from typing import Any, Dict, Type, TypeVar
from app.core.kernel.events import EventBus

T = TypeVar("T")


class AgentContext:
    """运行时上下文：承载依赖注入（DI）、跨插件通信与分层状态。"""

    def __init__(self, parent: AgentContext | None = None, event_bus: EventBus | None = None) -> None:
        self.parent = parent
        self._services: Dict[str, Any] = {}
        self.events: EventBus = event_bus or (parent.events if parent else EventBus())

    def provide(self, name: str, service: Any) -> None:
        """向当前上下文注入服务。"""
        self._services[name] = service

    def unprovide(self, name: str) -> None:
        """从当前上下文撤销服务。"""
        self._services.pop(name, None)

    def inject(self, name: str) -> Any:
        """解析并注入服务（向上递归寻址）。"""
        if name in self._services:
            return self._services[name]
        if self.parent:
            return self.parent.inject(name)
        raise KeyError(f"Kernel Service '{name}' is not provided in current context.")

    def inject_typed(self, name: str, expected_type: Type[T]) -> T:
        """类型安全注入。"""
        service = self.inject(name)
        if not isinstance(service, expected_type):
            raise TypeError(f"Service '{name}' is of type {type(service)}, expected {expected_type}")
        return service

    def create_child(self) -> AgentContext:
        """创建派生子上下文（常用于单次 ReAct 循环或单个 Task 会话隔离）。"""
        return AgentContext(parent=self, event_bus=self.events)
