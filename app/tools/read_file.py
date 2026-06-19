from __future__ import annotations

from typing import Optional

from app.tools.workspace_tool import WorkspaceTool


class ReadFileTool(WorkspaceTool):
    """读取 workspace 内的文件 — 继承 WorkspaceTool，复用路径解析与穿越防护。"""

    name = "read_file"
    description = "读取指定文件的内容。只能访问 workspace 目录下的文件。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于 workspace 的文件路径，如 'src/main.py'",
            },
        },
        "required": ["path"],
    }

    def __init__(self, *, index=None) -> None:
        self._index = index

    async def run(self, *, workspace_root: str, path: str, **_) -> str:
        try:
            target = self.safe_resolve(workspace_root, path)
        except ValueError as exc:
            return self.error(str(exc))

        # 如果路径不存在，尝试用 resolver 模糊匹配
        if not target.exists() and self._index:
            from app.workspace.resolver import SmartFileResolver
            resolver = SmartFileResolver(self._index)
            resolved = resolver.resolve(path)
            if resolved:
                path = resolved
                try:
                    target = self.safe_resolve(workspace_root, path)
                except ValueError as exc:
                    return self.error(str(exc))

        if not target.exists():
            return self.error(f"文件不存在 — {path}")

        if target.is_dir():
            return self.error(f"这是一个目录，不是文件 — {path}")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return self.error(f"文件不是 UTF-8 编码，无法读取 — {path}")

        if len(content) > 50_000:
            content = content[:50_000] + "\n... [文件过长，已截断]"

        return content
