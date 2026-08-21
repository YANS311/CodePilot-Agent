from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.kernel import AgentContext, BasePlugin, EventBus, KernelEvent, PluginManager


# ═════════════════════════════════════════════════════════════════════
# 1. 模拟测试插件
# ═════════════════════════════════════════════════════════════════════


class StoragePlugin(BasePlugin):
    name = "storage"
    dependencies = []

    async def activate(self, ctx: AgentContext) -> None:
        ctx.provide("db", {"status": "connected"})

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("db")


class ToolPlugin(BasePlugin):
    name = "tools"
    dependencies = ["storage"]

    async def activate(self, ctx: AgentContext) -> None:
        db = ctx.inject("db")
        ctx.provide("tools", [f"tool_with_{db['status']}"])

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("tools")


class CyclicPluginA(BasePlugin):
    name = "cyclic_a"
    dependencies = ["cyclic_b"]

    async def activate(self, ctx: AgentContext) -> None: ...
    async def deactivate(self, ctx: AgentContext) -> None: ...


class CyclicPluginB(BasePlugin):
    name = "cyclic_b"
    dependencies = ["cyclic_a"]

    async def activate(self, ctx: AgentContext) -> None: ...
    async def deactivate(self, ctx: AgentContext) -> None: ...


# ═════════════════════════════════════════════════════════════════════
# 2. 单元测试用例
# ═════════════════════════════════════════════════════════════════════


class TestEventBus:
    def test_event_bus_pub_sub_and_sourcing(self):
        async def _run():
            bus = EventBus()
            received = []

            async def on_event(e: KernelEvent):
                received.append(e.payload)

            bus.on("task:start", on_event)
            await bus.emit("task:start", {"task_id": "T01"})

            assert len(received) == 1
            assert received[0]["task_id"] == "T01"
            assert len(bus.get_events("task:start")) == 1

            # 测试注销监听
            bus.off("task:start", on_event)
            await bus.emit("task:start", {"task_id": "T02"})
            assert len(received) == 1  # 没有新触发
            assert len(bus.get_events("task:start")) == 2

        asyncio.run(_run())


class TestAgentContext:
    def test_context_dependency_injection_and_hierarchy(self):
        parent = AgentContext()
        parent.provide("global_config", {"timeout": 30})

        child = parent.create_child()
        child.provide("session_id", "sess-123")

        assert child.inject("global_config")["timeout"] == 30
        assert child.inject("session_id") == "sess-123"

        # 类型安全注入验证
        config = child.inject_typed("global_config", dict)
        assert config["timeout"] == 30

        with pytest.raises(TypeError):
            child.inject_typed("global_config", str)

        with pytest.raises(KeyError):
            parent.inject("session_id")


class TestPluginManager:
    def test_plugin_manager_lifecycle_and_reversibility(self):
        async def _run():
            ctx = AgentContext()
            mgr = PluginManager(ctx)

            mgr.register(ToolPlugin())
            mgr.register(StoragePlugin())

            # 激活：自动根据依赖拓扑排序调整顺序（storage -> tools）
            await mgr.activate_all()

            assert ctx.inject("db")["status"] == "connected"
            assert ctx.inject("tools") == ["tool_with_connected"]

            # 逆序安全卸载 (可逆副作用消除)
            await mgr.deactivate_all()
            with pytest.raises(KeyError):
                ctx.inject("tools")
            with pytest.raises(KeyError):
                ctx.inject("db")

        asyncio.run(_run())

    def test_plugin_manager_cyclic_dependency(self):
        async def _run():
            mgr = PluginManager()
            mgr.register(CyclicPluginA())
            mgr.register(CyclicPluginB())

            with pytest.raises(ValueError, match="Cyclic dependency detected"):
                await mgr.activate_all()

        asyncio.run(_run())

    def test_plugin_manager_missing_dependency(self):
        async def _run():
            mgr = PluginManager()
            mgr.register(ToolPlugin())  # 依赖 storage，但未注册 storage

            with pytest.raises(ValueError, match="Missing dependency"):
                await mgr.activate_all()

        asyncio.run(_run())
