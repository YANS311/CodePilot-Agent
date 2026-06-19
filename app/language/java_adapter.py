"""java_adapter.py — Java 语言适配器 (Stub)。

仅实现 detect，不实现完整测试执行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.language.base import BaseLanguageAdapter


class JavaAdapter(BaseLanguageAdapter):
    """Java 项目适配器 — 仅检测，测试执行未实现。"""

    language = "java"
    file_extensions = [".java"]
    test_commands = ["mvn test", "gradle test"]
    dependency_files = ["pom.xml", "build.gradle", "build.gradle.kts"]

    def detect(self, workspace_path: str) -> bool:
        """检测 workspace 是否为 Java 项目。"""
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return False

        # 检查构建文件
        for dep_file in self.dependency_files:
            if (ws / dep_file).exists():
                return True

        # 检查是否有 .java 文件
        java_files = list(ws.rglob("*.java"))
        java_files = [
            f for f in java_files
            if not any(p.startswith(".") for p in f.relative_to(ws).parts)
        ]
        return len(java_files) > 0

    def get_test_command(self, target: Optional[str] = None) -> str:
        """获取测试命令（未实现）。"""
        if (Path(".") / "pom.xml").exists():
            return "mvn test"
        return "gradle test"
