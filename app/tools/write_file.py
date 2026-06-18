from __future__ import annotations

from app.tools.workspace_tool import WorkspaceTool

_MAX_FILE_SIZE = 100 * 1024  # 100KB


class WriteFileTool(WorkspaceTool):
    """写入 workspace 内的文件 — 继承 WorkspaceTool，复用路径解析与穿越防护。"""

    name = "write_file"
    description = "写入文件到 workspace。支持创建新文件和覆盖已有文件。"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于 workspace 的文件路径，如 'src/main.py'",
            },
            "content": {
                "type": "string",
                "description": "要写入的文件内容",
            },
        },
        "required": ["path", "content"],
    }

    async def run(self, *, workspace_root: str, path: str, content: str, **_) -> str:
        try:
            target = self.safe_resolve(workspace_root, path)
        except ValueError as exc:
            return self.error(str(exc))

        if ".git" in target.parts:
            return self.error(f"禁止写入 .git 目录 — {path}")

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > _MAX_FILE_SIZE:
            return self.error(f"内容超过 100KB 限制 ({len(content_bytes)} bytes)")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

        return f"已写入 {path} ({len(content_bytes)} bytes)"
