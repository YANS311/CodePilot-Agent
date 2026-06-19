"""detector.py — Language Detector，自动识别 workspace 中的编程语言。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.language.base import BaseLanguageAdapter
from app.language.python_adapter import PythonAdapter
from app.language.java_adapter import JavaAdapter
from app.language.node_adapter import NodeAdapter

logger = logging.getLogger(__name__)

# 所有已注册的适配器
_ADAPTERS: list[BaseLanguageAdapter] = [
    PythonAdapter(),
    JavaAdapter(),
    NodeAdapter(),
]


class LanguageDetector:
    """语言检测器 — 扫描 workspace 自动识别编程语言。"""

    def __init__(self, adapters: Optional[list[BaseLanguageAdapter]] = None) -> None:
        self._adapters = adapters or _ADAPTERS

    def detect(self, workspace_path: str) -> dict:
        """检测 workspace 中的编程语言。

        Returns:
            {
                "primary_language": "python",
                "detected_languages": ["python", "node"],
                "confidence": 0.85,
                "details": {...}
            }
        """
        detected = []
        details = {}

        for adapter in self._adapters:
            if adapter.detect(workspace_path):
                detected.append(adapter.language)
                # 获取详细信息
                source_files = adapter.get_source_files(workspace_path)
                dep_files = adapter.get_dependency_files(workspace_path)
                details[adapter.language] = {
                    "source_files_count": len(source_files),
                    "dependency_files": dep_files,
                    "test_command": adapter.get_test_command(),
                }

        # 确定主语言（按文件数排序）
        primary = ""
        if detected:
            # 按 source_files_count 排序
            ranked = sorted(
                detected,
                key=lambda lang: details[lang]["source_files_count"],
                reverse=True,
            )
            primary = ranked[0]

        # 计算置信度
        confidence = self._compute_confidence(detected, details)

        return {
            "primary_language": primary,
            "detected_languages": detected,
            "confidence": confidence,
            "details": details,
        }

    def _compute_confidence(self, detected: list[str], details: dict) -> float:
        """计算检测置信度。"""
        if not detected:
            return 0.0

        # 基础置信度：检测到语言数量
        base = min(len(detected) * 0.3, 0.6)

        # 有依赖文件加分
        has_deps = any(
            details[lang]["dependency_files"]
            for lang in detected
        )
        if has_deps:
            base += 0.2

        # 有测试命令加分
        has_tests = any(
            details[lang]["test_command"]
            for lang in detected
        )
        if has_tests:
            base += 0.1

        # 主语言文件数多加分
        if detected:
            main_count = details[detected[0]]["source_files_count"]
            if main_count > 10:
                base += 0.1
            elif main_count > 5:
                base += 0.05

        return min(base, 1.0)

    def get_adapter(self, language: str) -> Optional[BaseLanguageAdapter]:
        """获取指定语言的适配器。"""
        for adapter in self._adapters:
            if adapter.language == language:
                return adapter
        return None

    def list_adapters(self) -> list[dict]:
        """列出所有已注册的适配器。"""
        return [a.get_info() for a in self._adapters]
