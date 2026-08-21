from __future__ import annotations

from typing import Any, Dict
from app.core.config import Settings
from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin
from app.core.llm_client import LLMClient


class ModelAdapterPlugin(BasePlugin):
    """模型提供方适配插件：向上下文注入 llm_client 实例。"""

    name = "model_adapter"
    dependencies = []

    async def activate(self, ctx: AgentContext) -> None:
        custom_client = self.config.get("client")
        if custom_client:
            client = custom_client
        else:
            api_key = self.config.get("api_key", "")
            base_url = self.config.get("base_url", "https://api.openai.com/v1")
            model = self.config.get("model", "gpt-4o")
            ci_mode = self.config.get("ci_mode", False)
            settings_obj = Settings(
                llm_api_key=api_key,
                llm_base_url=base_url,
                llm_model=model,
                ci_mode=ci_mode,
            )
            client = LLMClient(settings=settings_obj)

        ctx.provide("llm_client", client)
        await ctx.events.emit("model:ready", {"model": getattr(client, "model", "custom")})

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("llm_client")
