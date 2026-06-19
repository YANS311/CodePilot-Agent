"""python_adapter.py — Python 语言适配器。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.language.base import BaseLanguageAdapter


class PythonAdapter(BaseLanguageAdapter):
    """Python 项目适配器 — 完整支持检测、测试执行。"""

    language = "python"
    file_extensions = [".py"]
    test_commands = ["pytest"]
    dependency_files = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]

    def detect(self, workspace_path: str) -> bool:
        """检测 workspace 是否为 Python 项目。"""
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return False

        # 检查依赖文件
        for dep_file in self.dependency_files:
            if (ws / dep_file).exists():
                return True

        # 检查是否有 .py 文件
        py_files = list(ws.rglob("*.py"))
        # 过滤掉隐藏目录和缓存目录
        py_files = [
            f for f in py_files
            if not any(p.startswith(".") or p in ("__pycache__", "venv", ".venv")
                       for p in f.relative_to(ws).parts)
        ]
        return len(py_files) > 0

    def get_test_command(self, target: Optional[str] = None) -> str:
        """获取 pytest 命令。"""
        if target:
            return f"pytest {target}"
        return "pytest"
