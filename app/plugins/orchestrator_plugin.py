from __future__ import annotations

from app.agent.react_agent import ReActAgent
from app.agent.verification import VerificationPolicy
from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin


class ReActOrchestratorPlugin(BasePlugin):
    """ReAct 任务编排插件：依赖 Model、Tools 与 Guardrail 组装 Agent 运行器。"""

    name = "react_orchestrator"
    dependencies = ["model_adapter", "native_tools", "guardrails"]

    async def activate(self, ctx: AgentContext) -> None:
        llm = ctx.inject("llm_client")
        tool_registry = ctx.inject("tool_registry")
        guardrail = ctx.inject("guardrail")

        workspace_root = self.config.get("workspace_root", "./workspace")
        max_tool_calls = self.config.get("max_tool_calls", 20)

        enable_verification = self.config.get("enable_verification", True)
        policy = VerificationPolicy(enabled=enable_verification)

        agent = ReActAgent(
            llm=llm,
            registry=tool_registry,
            workspace_root=workspace_root,
            max_tool_calls=max_tool_calls,
            verification_policy=policy,
        )
        if guardrail:
            agent._guardrail = guardrail

        ctx.provide("agent", agent)
        await ctx.events.emit("orchestrator:ready", {"type": "ReActAgent"})

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("agent")
