from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.models.tool import ToolCall, ToolResult
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# write_file 允许的文件后缀
_ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json"}

# write_file 禁止的无意义文件名
_MEANINGLESS_NAMES = {"1cm.py", "tmp.py", "test.py", "a.py", "b.py", "c.py", "x.py"}


def _validate_tool_args(
    tool_name: str, args: dict[str, Any], workspace_root: str
) -> str | None:
    """校验工具参数，返回错误信息字符串或 None（通过）。"""
    if tool_name == "read_file":
        path = args.get("path", "")
        if not path or not path.strip():
            return "错误: path 参数不能为空"
        if path.strip() in (".", "/", "./"):
            return f"错误: path 不能是目录 — {path}，请传入具体文件路径"
        # 检查是否是目录
        ws = Path(workspace_root).resolve()
        target = (ws / path).resolve()
        if target.exists() and target.is_dir():
            return f"错误: {path} 是一个目录，不是文件。read_file 只能读取文件"

    elif tool_name == "write_file":
        path = args.get("path", "")
        if not path or not path.strip():
            return "错误: path 参数不能为空"
        from pathlib import PurePath
        suffix = PurePath(path).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            return f"错误: 文件后缀 '{suffix}' 不允许。只支持 {', '.join(sorted(_ALLOWED_SUFFIXES))}"
        from pathlib import PurePosixPath
        basename = PurePosixPath(path).name.lower()
        if basename in _MEANINGLESS_NAMES:
            return f"错误: 文件名 '{basename}' 无意义，请使用语义明确的文件名"

    elif tool_name == "search_code":
        query = args.get("query", "")
        if not query or not query.strip():
            return "错误: query 参数不能为空"
        if len(query.strip()) < 2:
            return "错误: query 长度必须 >= 2"

    return None


class ToolRegistry:
    """工具注册中心 — 体现多态。

    Registry 只持有 BaseTool 类型的引用，execute() 调用 tool.run() 时，
    实际执行的是具体子类（ReadFileTool / WriteFileTool / ...）的 run() 实现，
    这就是多态：同一接口，不同行为。
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"工具 '{tool.name}' 已注册")
        self._tools[tool.name] = tool
        logger.info("Tool registered: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        """导出所有工具的 OpenAI function calling schema。"""
        return [t.to_openai_schema() for t in self._tools.values()]

    async def execute(
        self, tool_call: ToolCall, workspace_root: str
    ) -> ToolResult:
        """按名称执行工具，返回结构化 ToolResult。

        工具不存在或执行异常时返回 success=False 的 ToolResult。
        """
        tool = self.get(tool_call.name)
        if tool is None:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                success=False,
                output=f"未知工具: {tool_call.name}",
            )

        # 参数校验
        error = _validate_tool_args(tool_call.name, tool_call.arguments, workspace_root)
        if error:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool.name,
                success=False,
                output=error,
            )

        try:
            output = await tool.run(
                workspace_root=workspace_root, **tool_call.arguments
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool.name,
                success=True,
                output=output,
            )
        except Exception as exc:
            logger.exception("Tool '%s' execution failed", tool.name)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool.name,
                success=False,
                output=f"{type(exc).__name__}: {exc}",
            )
