"""node_adapter.py — Node.js 语言适配器 (Stub)。

仅实现 detect，不实现完整测试执行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.language.base import BaseLanguageAdapter


class NodeAdapter(BaseLanguageAdapter):
    """Node.js 项目适配器 — 仅检测，测试执行未实现。"""

    language = "node"
    file_extensions = [".js", ".ts", ".jsx", ".tsx", ".mjs"]
    test_commands = ["npm test", "yarn test", "npx jest"]
    dependency_files = ["package.json", "yarn.lock", "pnpm-lock.yaml"]

    def detect(self, workspace_path: str) -> bool:
        """检测 workspace 是否为 Node.js 项目。"""
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return False

        # 检查 package.json
        if (ws / "package.json").exists():
            return True

        # 检查是否有 JS/TS 文件
        js_files = []
        for ext in self.file_extensions:
            js_files.extend(ws.rglob(f"*{ext}"))
        js_files = [
            f for f in js_files
            if not any(p.startswith(".") or p in ("node_modules",) for p in f.relative_to(ws).parts)
        ]
        return len(js_files) > 0

    def get_test_command(self, target: Optional[str] = None) -> str:
        """获取测试命令（未实现）。"""
        if (Path(".") / "yarn.lock").exists():
            return "yarn test"
        return "npm test"
