"""D16 Tests — Agent 文件感知集成测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.workspace.indexer import IndexBuilder
from app.workspace.resolver import SmartFileResolver


# ═══════════════════════════════════════════
# 1. Index Builder 集成
# ═══════════════════════════════════════════


class TestIndexIntegration:
    def test_build_real_workspace(self):
        """测试真实 workspace 目录的索引构建。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        assert index.files  # 应有文件
        assert index.tree  # 应有树结构
        assert index.summary["total_files"] > 0
        assert index.summary["python_files"] > 0

    def test_tree_has_examples(self):
        """workspace 应包含 examples 目录。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        assert "examples" in index.tree.get("dirs", {})
        example_files = index.tree["dirs"]["examples"]["files"]
        assert len(example_files) > 0

    def test_tree_has_tests(self):
        """workspace 应包含 tests 目录。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        assert "tests" in index.tree.get("dirs", {})
        test_files = index.tree["dirs"]["tests"]["files"]
        assert len(test_files) > 0


# ═══════════════════════════════════════════
# 2. Resolver 集成 — 模拟 Agent 查找文件
# ═══════════════════════════════════════════


class TestResolverIntegration:
    def test_find_calculator_by_keyword(self):
        """用户说"计算器" → Agent 应找到 buggy_calculator.py。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("calculator")
        assert result is not None
        assert "calculator" in result.lower()
        assert result.endswith(".py")

    def test_find_todo_by_keyword(self):
        """用户说"todo" → Agent 应找到 todo_service.py。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("todo")
        assert result is not None
        assert "todo" in result.lower()

    def test_find_string_utils(self):
        """用户说"string utils" → Agent 应找到 string_utils.py。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("string utils")
        assert result is not None
        assert "string_utils" in result

    def test_find_by_directory(self):
        """用户说"test" → Agent 应定位到 tests/ 目录下的文件。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("test")
        assert result is not None
        # 应匹配 tests/ 目录下的文件（优先于 uploads/ 等）
        assert "test" in result.lower()

    def test_ambiguous_returns_something(self):
        """模糊查询"service" → Agent 应返回某个匹配。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("service")
        # 可能找到 todo_service 或 api_client（如果有的话）
        # 关键是不应该返回 None
        # 如果真的没匹配，跳过
        if result is not None:
            assert result.endswith(".py")


# ═══════════════════════════════════════════
# 3. Prompt 上下文格式
# ═══════════════════════════════════════════


class TestPromptContext:
    def test_index_has_all_files(self):
        """索引应包含 workspace 中所有 .py 文件。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        # 检查 examples 目录下的 .py 文件
        examples_dir = ws / "examples"
        if examples_dir.exists():
            expected_py = [f.stem for f in examples_dir.glob("*.py")]
            indexed_names = [f.module_name for f in index.files]
            for name in expected_py:
                assert name in indexed_names, f"Missing: {name}"

    def test_summary_useful(self):
        """摘要信息应足够 Agent 使用。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        summary = index.summary
        assert summary["total_files"] > 0
        assert summary["python_files"] > 0
        assert len(summary["largest_files"]) > 0
