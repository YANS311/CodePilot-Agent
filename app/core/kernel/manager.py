from __future__ import annotations

from typing import Dict, List
from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin


class PluginManager:
    """插件管理器：负责依赖解析、拓扑排序激活与逆序可逆卸载。"""

    def __init__(self, context: AgentContext | None = None) -> None:
        self.context = context or AgentContext()
        self._plugins: Dict[str, BasePlugin] = {}
        self._active_order: List[str] = []

    def register(self, plugin: BasePlugin) -> None:
        """注册插件实例。"""
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' is already registered.")
        self._plugins[plugin.name] = plugin

    def get_plugin(self, name: str) -> BasePlugin | None:
        return self._plugins.get(name)

    def _resolve_dependency_order(self) -> List[str]:
        """Kahn 算法拓扑排序，检测循环依赖并确定加载顺序。"""
        in_degree: Dict[str, int] = {name: 0 for name in self._plugins}
        graph: Dict[str, List[str]] = {name: [] for name in self._plugins}

        for name, plugin in self._plugins.items():
            for dep in plugin.dependencies:
                if dep not in self._plugins:
                    raise ValueError(f"Missing dependency: Plugin '{name}' requires '{dep}'")
                graph[dep].append(name)
                in_degree[name] += 1

        queue = [name for name, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self._plugins):
            raise ValueError("Cyclic dependency detected among registered plugins.")
        return order

    async def activate_all(self) -> None:
        """按拓扑序依次激活插件。"""
        order = self._resolve_dependency_order()
        for name in order:
            plugin = self._plugins[name]
            if not plugin.is_active:
                await self.context.events.emit("plugin:before_activate", {"plugin": name})
                await plugin.activate(self.context)
                plugin.is_active = True
                self._active_order.append(name)
                await self.context.events.emit("plugin:after_activate", {"plugin": name})

    async def deactivate_all(self) -> None:
        """按激活顺序的严格逆序卸载插件（可逆副作用消除）。"""
        for name in reversed(self._active_order):
            plugin = self._plugins[name]
            if plugin.is_active:
                await self.context.events.emit("plugin:before_deactivate", {"plugin": name})
                await plugin.deactivate(self.context)
                plugin.is_active = False
                await self.context.events.emit("plugin:after_deactivate", {"plugin": name})
        self._active_order.clear()
