"""base.py — BaseLanguageAdapter 抽象基类。

定义语言适配器的统一接口，子类实现具体语言的检测与测试命令生成。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseLanguageAdapter(ABC):
    """语言适配器抽象基类。"""

    language: str = ""
    file_extensions: list[str] = []
    test_commands: list[str] = []
    dependency_files: list[str] = []

    @abstractmethod
    def detect(self, workspace_path: str) -> bool:
        """检测 workspace 是否包含该语言的项目。"""
        ...

    @abstractmethod
    def get_test_command(self, target: Optional[str] = None) -> str:
        """获取测试执行命令。"""
        ...

    def get_source_files(self, workspace_path: str) -> list[str]:
        """获取 workspace 中的源代码文件列表。"""
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return []

        files = []
        for ext in self.file_extensions:
            for f in ws.rglob(f"*{ext}"):
                # 跳过隐藏目录和常见忽略目录
                parts = f.relative_to(ws).parts
                if any(p.startswith(".") or p in ("__pycache__", "node_modules", "venv", ".venv") for p in parts):
                    continue
                files.append(str(f.relative_to(ws)))
        return sorted(files)

    def get_dependency_files(self, workspace_path: str) -> list[str]:
        """获取 workspace 中的依赖文件列表。"""
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return []

        found = []
        for dep_file in self.dependency_files:
            if (ws / dep_file).exists():
                found.append(dep_file)
        return found

    def get_info(self) -> dict:
        """返回适配器的基本信息。"""
        return {
            "language": self.language,
            "file_extensions": self.file_extensions,
            "test_commands": self.test_commands,
            "dependency_files": self.dependency_files,
        }
