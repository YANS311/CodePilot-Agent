from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


@dataclass(frozen=True)
class KernelEvent:
    """不可变内核事件，支持审计与重放。"""

    type: str
    payload: Any
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """异步事件总线，支持事件流记录 (Event Sourcing)。"""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[KernelEvent], Any]]] = {}
        self._event_log: List[KernelEvent] = []

    def on(self, event_type: str, handler: Callable[[KernelEvent], Any]) -> None:
        """注册事件监听器。"""
        self._handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable[[KernelEvent], Any]) -> None:
        """注销事件监听器（支持可逆清理）。"""
        if event_type in self._handlers and handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def emit(self, event_type: str, payload: Any = None) -> KernelEvent:
        """发布事件并广播给所有监听器。"""
        event = KernelEvent(type=event_type, payload=payload)
        self._event_log.append(event)

        handlers = list(self._handlers.get(event_type, []))
        # 通配符监听
        wildcard_handlers = list(self._handlers.get("*", []))
        all_handlers = handlers + wildcard_handlers

        for h in all_handlers:
            if inspect.iscoroutinefunction(h):
                await h(event)
            else:
                h(event)
        return event

    def get_events(self, event_type: str | None = None) -> List[KernelEvent]:
        """获取历史事件日志。"""
        if event_type is None:
            return list(self._event_log)
        return [e for e in self._event_log if e.type == event_type]

    def clear(self) -> None:
        """清空日志与监听器。"""
        self._handlers.clear()
        self._event_log.clear()
