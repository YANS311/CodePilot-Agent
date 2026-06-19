"""indexer.py — WorkspaceIndex Builder，扫描 workspace 构建文件结构索引。"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea", ".pytest_cache", "uploads"})
_SUMMARY_LINES = 200


@dataclass
class FileEntry:
    """单个文件的信息。"""

    path: str  # 相对路径: "examples/buggy_calculator.py"
    module_name: str  # 模块名: "buggy_calculator"
    size: int = 0
    summary: str = ""  # 前 200 行摘要


@dataclass
class WorkspaceIndex:
    """Workspace 结构索引。"""

    root: str
    files: list[FileEntry] = field(default_factory=list)
    tree: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


class IndexBuilder:
    """扫描 workspace 目录，构建文件树和索引。"""

    def build(self, workspace_root: str) -> WorkspaceIndex:
        ws = Path(workspace_root).resolve()
        if not ws.exists():
            return WorkspaceIndex(root=str(ws))

        files: list[FileEntry] = []
        tree: dict = {"files": [], "dirs": {}}

        for root, dirs, filenames in os.walk(ws):
            # 跳过忽略目录
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

            rel_dir = Path(root).relative_to(ws)
            node = tree
            for part in rel_dir.parts:
                if part not in node.get("dirs", {}):
                    node.setdefault("dirs", {})[part] = {"files": [], "dirs": {}}
                node = node["dirs"][part]

            for fname in sorted(filenames):
                fpath = Path(root) / fname
                rel_path = fpath.relative_to(ws).as_posix()

                try:
                    size = fpath.stat().st_size
                except OSError:
                    continue

                module_name = fpath.stem

                summary = ""
                if fpath.suffix == ".py":
                    summary = _read_summary(fpath)

                entry = FileEntry(
                    path=rel_path,
                    module_name=module_name,
                    size=size,
                    summary=summary,
                )
                files.append(entry)
                node["files"].append(fname)

        # 统计
        python_files = sum(1 for f in files if f.path.endswith(".py"))
        largest = sorted(files, key=lambda f: f.size, reverse=True)[:10]

        return WorkspaceIndex(
            root=str(ws),
            files=files,
            tree=tree,
            summary={
                "total_files": len(files),
                "python_files": python_files,
                "largest_files": [
                    {"path": f.path, "size": f.size} for f in largest
                ],
            },
        )


def _read_summary(file_path: Path) -> str:
    """读取文件前 N 行作为摘要。"""
    try:
        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[:_SUMMARY_LINES])
    except OSError:
        return ""
