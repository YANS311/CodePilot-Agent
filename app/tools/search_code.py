from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Optional

from app.tools.workspace_tool import WorkspaceTool


class SearchCodeTool(WorkspaceTool):
    """在 workspace 中搜索代码 — 继承 WorkspaceTool，复用路径解析与目录跳过。"""

    name = "search_code"
    description = "在 workspace 中递归搜索代码，返回包含匹配内容的文件、行号和内容。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要搜索的关键词或简单正则表达式",
            },
            "file_pattern": {
                "type": "string",
                "description": "文件名 glob 过滤，如 '*.py'。留空则搜索所有文件。",
                "default": "",
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, index=None) -> None:
        self._index = index

    async def run(
        self, *, workspace_root: str, query: str, file_pattern: str = "", **_
    ) -> str:
        # 优先使用索引定位文件
        if self._index:
            from app.workspace.resolver import SmartFileResolver
            resolver = SmartFileResolver(self._index)
            match = resolver.resolve(query)
            if match:
                # 返回文件信息而非正则搜索
                file_info = next(
                    (f for f in self._index.files if f.path == match), None
                )
                if file_info:
                    return (
                        f"基于 Workspace 索引找到匹配文件:\n"
                        f"  路径: {file_info.path}\n"
                        f"  模块: {file_info.module_name}\n"
                        f"  大小: {file_info.size} bytes\n"
                        f"请使用 read_file 读取该文件。"
                    )

        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self.error(f"workspace 不存在 — {workspace_root}")

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as exc:
            return self.error(f"无效的正则表达式 — {exc}")

        matches: list[str] = []
        file_count = 0

        for file_path in self._iter_files(ws, file_pattern):
            file_count += 1
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    rel = file_path.relative_to(ws).as_posix()
                    matches.append(f"{rel}:{lineno}: {line.rstrip()}")

            if len(matches) >= 200:
                matches.append("... 结果过多，已截断 (>= 200 行)")
                break

        if not matches:
            return f"未找到匹配 '{query}' 的内容 (扫描了 {file_count} 个文件)"

        header = f"找到 {len(matches)} 处匹配 (扫描了 {file_count} 个文件):\n"
        return header + "\n".join(matches)

    def _iter_files(self, root: Path, file_pattern: str):
        """递归遍历目录，跳过忽略目录，可选 glob 过滤。"""
        pattern = file_pattern or "*"

        def _walk(directory: Path):
            for entry in sorted(directory.iterdir()):
                if entry.is_dir():
                    if self.should_skip_dir(entry.name):
                        continue
                    yield from _walk(entry)
                elif entry.is_file():
                    if fnmatch.fnmatch(entry.name, pattern):
                        yield entry

        yield from _walk(root)
