"""evidence_extractor.py — AST-based code evidence extraction.

从 WorkspaceIndex 中提取函数/类定义，构建 EvidenceItem 索引。
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.workspace.indexer import WorkspaceIndex

logger = logging.getLogger(__name__)

_DUNDER_PATTERN = "__"
_MAX_EXCERPT_LINES = 3


@dataclass
class EvidenceItem:
    """单条代码证据。"""

    claim_type: str  # "function" / "class"
    file: str  # "app/main.py"
    symbol: str  # "generate_video"
    line_start: int  # 15
    line_end: int  # 42
    excerpt: str = ""  # first 3 lines of body


class EvidenceExtractor:
    """从 WorkspaceIndex 提取代码级证据（AST 解析）。"""

    def __init__(self, index: WorkspaceIndex) -> None:
        self._index = index
        self._root = Path(index.root)

    def extract(self) -> list[EvidenceItem]:
        """提取所有 Python 文件的函数/类证据。"""
        items: list[EvidenceItem] = []
        for f in self._index.files:
            if not f.path.endswith(".py"):
                continue
            filepath = self._root / f.path
            if not filepath.exists():
                continue
            items.extend(self._parse_file(str(filepath), f.path))
        return items

    def build_index(self) -> dict[str, list[EvidenceItem]]:
        """返回 {file_path: [EvidenceItem, ...]} 的索引。"""
        index: dict[str, list[EvidenceItem]] = {}
        for item in self.extract():
            index.setdefault(item.file, []).append(item)
        return index

    def _parse_file(self, filepath: str, rel_path: str) -> list[EvidenceItem]:
        """解析单个 .py 文件，提取函数/类定义。"""
        try:
            source = Path(filepath).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return []

        lines = source.splitlines()
        items: list[EvidenceItem] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # 跳过 dunder 方法
                if node.name.startswith(_DUNDER_PATTERN) and node.name.endswith(_DUNDER_PATTERN):
                    continue
                items.append(self._make_item(node, rel_path, lines, "function"))

            elif isinstance(node, ast.ClassDef):
                items.append(self._make_item(node, rel_path, lines, "class"))
                # 提取类中的方法
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if child.name.startswith(_DUNDER_PATTERN) and child.name.endswith(_DUNDER_PATTERN):
                            continue
                        items.append(self._make_item(child, rel_path, lines, "function"))

        return items

    def _make_item(
        self,
        node: ast.AST,
        rel_path: str,
        lines: list[str],
        claim_type: str,
    ) -> EvidenceItem:
        """从 AST 节点构建 EvidenceItem。"""
        name = getattr(node, "name", "")
        line_start = getattr(node, "lineno", 1)
        line_end = getattr(node, "end_lineno", None) or self._estimate_end(node, lines)

        excerpt = self._extract_excerpt(lines, node, line_start)

        return EvidenceItem(
            claim_type=claim_type,
            file=rel_path,
            symbol=name,
            line_start=line_start,
            line_end=line_end,
            excerpt=excerpt,
        )

    @staticmethod
    def _estimate_end(node: ast.AST, lines: list[str]) -> int:
        """估算节点结束行号（fallback when end_lineno unavailable）。"""
        # Simple heuristic: scan forward from lineno for indent decrease
        start = getattr(node, "lineno", 1)
        if not lines:
            return start
        base_indent = None
        for i in range(start - 1, len(lines)):
            line = lines[i]
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(stripped)
            if base_indent is None:
                base_indent = indent
            elif indent <= base_indent and i > start - 1:
                return i
        return len(lines)

    @staticmethod
    def _extract_excerpt(lines: list[str], node: ast.AST, line_start: int) -> str:
        """提取函数体前 3 行非空行作为 excerpt。"""
        body = getattr(node, "body", [])
        if not body:
            return ""

        # 获取函数体起始行
        first_stmt = body[0]
        body_start = getattr(first_stmt, "lineno", line_start + 1)

        excerpt_lines: list[str] = []
        for i in range(body_start - 1, min(body_start + 10, len(lines))):
            line = lines[i].rstrip()
            if line.strip():
                excerpt_lines.append(line)
                if len(excerpt_lines) >= _MAX_EXCERPT_LINES:
                    break

        return "\n".join(excerpt_lines)
