"""resolver.py — SmartFileResolver，基于 WorkspaceIndex 的智能文件定位。"""

from __future__ import annotations

import re
from typing import Optional

from app.workspace.indexer import WorkspaceIndex


def _normalize(query: str) -> str:
    """标准化查询：小写，替换特殊字符为下划线。"""
    q = query.strip().lower()
    q = re.sub(r"[\s\-]+", "_", q)
    q = re.sub(r"[^a-z0-9_.]", "", q)
    return q


class SmartFileResolver:
    """基于 WorkspaceIndex 的智能文件定位器。

    匹配策略（按优先级）：
    1. 精确模块名匹配
    2. 模糊子串匹配
    3. Token 重叠匹配
    4. 目录匹配
    """

    def __init__(self, index: WorkspaceIndex) -> None:
        self._index = index
        # module_name (lower) → path
        self._name_map: dict[str, str] = {}
        # path (lower) → path
        self._path_map: dict[str, str] = {}
        for f in index.files:
            self._name_map[f.module_name.lower()] = f.path
            self._path_map[f.path.lower()] = f.path

    def resolve(self, query: str) -> Optional[str]:
        """根据查询智能定位文件，返回相对路径或 None。"""
        if not query or not query.strip():
            return None

        normalized = _normalize(query)

        # 1. 精确模块名匹配
        if normalized in self._name_map:
            return self._name_map[normalized]

        # 2. 模糊子串匹配（query in name 或 name in query）
        candidates = []
        for name, path in self._name_map.items():
            if normalized in name or name in normalized:
                candidates.append((path, len(name)))
        if candidates:
            # 选择最短名称的（最精确匹配）
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]

        # 3. Token 重叠匹配
        tokens = set(normalized.split("_"))
        tokens.discard("")
        if tokens:
            best_path = None
            best_score = 0
            for name, path in self._name_map.items():
                name_tokens = set(name.split("_"))
                overlap = len(tokens & name_tokens)
                if overlap > best_score:
                    best_score = overlap
                    best_path = path
            if best_score > 0:
                return best_path

        # 4. 目录匹配
        query_lower = query.strip().lower()
        dir_matches = []
        for f in self._index.files:
            parts = f.path.split("/")
            if len(parts) > 1:
                dir_name = parts[0].lower()
                if query_lower in dir_name or dir_name in query_lower:
                    dir_matches.append(f.path)
        if dir_matches:
            return dir_matches[0]

        return None
