from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Type
import yaml

from app.core.kernel.context import AgentContext
from app.core.kernel.manager import PluginManager
from app.core.kernel.plugin import BasePlugin
from app.plugins.guardrail_plugin import GuardrailPlugin
from app.plugins.mcp_plugin import MCPPlugin
from app.plugins.model_plugin import ModelAdapterPlugin
from app.plugins.orchestrator_plugin import ReActOrchestratorPlugin
from app.plugins.tools_plugin import NativeToolsPlugin

# 内置插件注册表
PLUGIN_REGISTRY: Dict[str, Type[BasePlugin]] = {
    "model_adapter": ModelAdapterPlugin,
    "native_tools": NativeToolsPlugin,
    "mcp": MCPPlugin,
    "guardrails": GuardrailPlugin,
    "react_orchestrator": ReActOrchestratorPlugin,
}


@dataclass
class PluginConfig:
    name: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProfileSpec:
    name: str
    version: str
    description: str = ""
    plugins: List[PluginConfig] = field(default_factory=list)


class ProfileLoader:
    """声明式 Profile 加载器，负责将 YAML 配置装配为完整的微内核运行时。"""

    @classmethod
    def load_from_yaml(cls, yaml_path: str | Path) -> ProfileSpec:
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Profile 文件不存在: {yaml_path}")

        raw_content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_content)

        profile_data = data.get("profile", {})
        plugins_data = data.get("plugins", [])

        plugins = [
            PluginConfig(name=p["name"], config=p.get("config", {}))
            for p in plugins_data
        ]

        return ProfileSpec(
            name=profile_data.get("name", "anonymous"),
            version=profile_data.get("version", "1.0.0"),
            description=profile_data.get("description", ""),
            plugins=plugins,
        )

    @classmethod
    async def bootstrap(
        cls,
        spec_or_path: ProfileSpec | str | Path,
        context: AgentContext | None = None,
        custom_registry: Dict[str, Type[BasePlugin]] | None = None,
    ) -> PluginManager:
        """根据 Profile 规范一键初始化并激活微内核环境。"""
        if isinstance(spec_or_path, (str, Path)):
            spec = cls.load_from_yaml(spec_or_path)
        else:
            spec = spec_or_path

        registry = dict(PLUGIN_REGISTRY)
        if custom_registry:
            registry.update(custom_registry)

        ctx = context or AgentContext()
        manager = PluginManager(ctx)

        for p_cfg in spec.plugins:
            plugin_cls = registry.get(p_cfg.name)
            if not plugin_cls:
                raise ValueError(f"未知的插件类型: '{p_cfg.name}'")
            plugin_instance = plugin_cls(config=p_cfg.config)
            manager.register(plugin_instance)

        await manager.activate_all()
        await ctx.events.emit("profile:bootstrapped", {"name": spec.name, "version": spec.version})
        return manager
