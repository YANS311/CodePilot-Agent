from __future__ import annotations

from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin
from app.security.tool_guardrail import ToolGuardrail


class GuardrailPlugin(BasePlugin):
    """安全护栏插件：向内核注入工具执行过滤与权限拦截器。"""

    name = "guardrails"
    dependencies = []

    async def activate(self, ctx: AgentContext) -> None:
        guardrail = ToolGuardrail()
        ctx.provide("guardrail", guardrail)

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("guardrail")
