from __future__ import annotations

from app.core.kernel.context import AgentContext
from app.core.kernel.plugin import BasePlugin
from app.tools.code_edit import CodeEditTool
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.run_tests import RunTestsTool
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool


class NativeToolsPlugin(BasePlugin):
    """原生工具集插件：初始化 ToolRegistry 并按配置挂载基础工具。"""

    name = "native_tools"
    dependencies = []

    async def activate(self, ctx: AgentContext) -> None:
        registry = ToolRegistry()

        # 挂载核心开发工具
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(SearchCodeTool())
        registry.register(CodeEditTool())
        registry.register(RunTestsTool())
        registry.register(GitDiffTool())
        registry.register(GitStatusTool())

        ctx.provide("tool_registry", registry)
        await ctx.events.emit("tools:registered", {"tools_count": len(registry.list_tools())})

    async def deactivate(self, ctx: AgentContext) -> None:
        ctx.unprovide("tool_registry")
