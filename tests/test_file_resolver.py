"""D16 Tests — SmartFileResolver 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.workspace.indexer import IndexBuilder, WorkspaceIndex, FileEntry
from app.workspace.resolver import SmartFileResolver, _normalize


# ═══════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════


def _make_index(files: list[tuple[str, str]]) -> WorkspaceIndex:
    """创建测试用 WorkspaceIndex。files = [(path, module_name), ...]"""
    entries = [
        FileEntry(path=p, module_name=m, size=100)
        for p, m in files
    ]
    return WorkspaceIndex(root="/workspace", files=entries)


# ═══════════════════════════════════════════
# 1. Normalize
# ═══════════════════════════════════════════


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("BuggyCalculator") == "buggycalculator"

    def test_spaces_to_underscore(self):
        assert _normalize("todo service") == "todo_service"

    def test_special_chars(self):
        assert _normalize("my-file.py") == "my_file.py"

    def test_strip_whitespace(self):
        assert _normalize("  calc  ") == "calc"


# ═══════════════════════════════════════════
# 2. Exact match
# ═══════════════════════════════════════════


class TestExactMatch:
    def test_exact_module_name(self):
        index = _make_index([
            ("examples/buggy_calculator.py", "buggy_calculator"),
            ("examples/todo_service.py", "todo_service"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("buggy_calculator") == "examples/buggy_calculator.py"

    def test_exact_case_insensitive(self):
        index = _make_index([
            ("examples/BuggyCalculator.py", "BuggyCalculator"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("buggycalculator") == "examples/BuggyCalculator.py"


# ═══════════════════════════════════════════
# 3. Fuzzy match (substring)
# ═══════════════════════════════════════════


class TestFuzzyMatch:
    def test_query_in_name(self):
        index = _make_index([
            ("examples/buggy_calculator.py", "buggy_calculator"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("calc") == "examples/buggy_calculator.py"

    def test_name_in_query(self):
        index = _make_index([
            ("examples/todo.py", "todo"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("todo_service") == "examples/todo.py"

    def test_closest_match(self):
        index = _make_index([
            ("examples/calc.py", "calc"),
            ("examples/buggy_calculator.py", "buggy_calculator"),
        ])
        resolver = SmartFileResolver(index)
        # "calc" 应该匹配 "calc"（更短更精确）
        assert resolver.resolve("calc") == "examples/calc.py"


# ═══════════════════════════════════════════
# 4. Token overlap match
# ═══════════════════════════════════════════


class TestTokenMatch:
    def test_token_overlap(self):
        index = _make_index([
            ("examples/todo_service.py", "todo_service"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("todo service") == "examples/todo_service.py"

    def test_partial_token(self):
        index = _make_index([
            ("examples/string_utils.py", "string_utils"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("string") == "examples/string_utils.py"


# ═══════════════════════════════════════════
# 5. Directory match
# ═══════════════════════════════════════════


class TestDirectoryMatch:
    def test_directory_name(self):
        index = _make_index([
            ("tests/test_main.py", "test_main"),
            ("tests/test_utils.py", "test_utils"),
            ("examples/app.py", "app"),
        ])
        resolver = SmartFileResolver(index)
        result = resolver.resolve("tests")
        assert result is not None
        assert result.startswith("tests/")

    def test_directory_fuzzy(self):
        index = _make_index([
            ("examples/buggy_calculator.py", "buggy_calculator"),
        ])
        resolver = SmartFileResolver(index)
        result = resolver.resolve("examples")
        assert result == "examples/buggy_calculator.py"


# ═══════════════════════════════════════════
# 6. No match
# ═══════════════════════════════════════════


class TestNoMatch:
    def test_empty_query(self):
        index = _make_index([("a.py", "a")])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("") is None

    def test_whitespace_query(self):
        index = _make_index([("a.py", "a")])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("   ") is None

    def test_unrelated_query(self):
        index = _make_index([
            ("examples/app.py", "app"),
        ])
        resolver = SmartFileResolver(index)
        assert resolver.resolve("nonexistent_module_xyz") is None


# ═══════════════════════════════════════════
# 7. Integration with real workspace
# ═══════════════════════════════════════════


class TestIntegration:
    def test_resolve_calculator(self, tmp_path):
        (tmp_path / "examples").mkdir()
        (tmp_path / "examples" / "buggy_calculator.py").write_text("class Calculator: pass")
        (tmp_path / "examples" / "todo_service.py").write_text("class TodoService: pass")

        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        resolver = SmartFileResolver(index)

        assert resolver.resolve("calculator") == "examples/buggy_calculator.py"
        assert resolver.resolve("todo") == "examples/todo_service.py"

    def test_resolve_with_real_files(self):
        """使用项目真实 workspace 测试。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))
        resolver = SmartFileResolver(index)

        result = resolver.resolve("calculator")
        assert result is not None
        assert "calculator" in result.lower()
