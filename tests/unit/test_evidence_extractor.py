"""D18 Tests — EvidenceExtractor 测试。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.evidence_extractor import EvidenceExtractor, EvidenceItem
from app.workspace.indexer import WorkspaceIndex, FileEntry


# ═══════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════


def _make_index(files: list[tuple[str, str, str]]) -> WorkspaceIndex:
    """创建测试用 WorkspaceIndex。files = [(path, module_name, summary), ...]"""
    entries = [
        FileEntry(path=p, module_name=m, size=100, summary=s)
        for p, m, s in files
    ]
    return WorkspaceIndex(root="/workspace", files=entries)


def _make_index_with_root(root: str, files: list[tuple[str, str, str]]) -> WorkspaceIndex:
    """创建带指定 root 的 WorkspaceIndex。"""
    entries = [
        FileEntry(path=p, module_name=m, size=100, summary=s)
        for p, m, s in files
    ]
    return WorkspaceIndex(root=root, files=entries)


# ═══════════════════════════════════════════
# 1. EvidenceItem dataclass
# ═══════════════════════════════════════════


class TestEvidenceItem:
    def test_default_values(self):
        item = EvidenceItem(
            claim_type="function",
            file="app/main.py",
            symbol="foo",
            line_start=1,
            line_end=10,
        )
        assert item.claim_type == "function"
        assert item.file == "app/main.py"
        assert item.symbol == "foo"
        assert item.line_start == 1
        assert item.line_end == 10
        assert item.excerpt == ""

    def test_with_excerpt(self):
        item = EvidenceItem(
            claim_type="class",
            file="app/utils.py",
            symbol="Helper",
            line_start=5,
            line_end=20,
            excerpt="class Helper:\n    def __init__(self):",
        )
        assert "class Helper:" in item.excerpt


# ═══════════════════════════════════════════
# 2. AST extraction — functions
# ═══════════════════════════════════════════


class TestExtractFunctions:
    def test_extract_simple_function(self, tmp_path: Path):
        """AST 解析提取简单函数定义。"""
        code = 'def hello():\n    print("hello")\n'
        f = tmp_path / "test.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("test.py", "test", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        assert len(items) == 1
        assert items[0].claim_type == "function"
        assert items[0].symbol == "hello"
        assert items[0].file == "test.py"
        assert items[0].line_start == 1
        assert "print" in items[0].excerpt

    def test_extract_multiple_functions(self, tmp_path: Path):
        """提取多个函数。"""
        code = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "def subtract(a, b):\n"
            "    return a - b\n"
        )
        f = tmp_path / "calc.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("calc.py", "calc", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        assert len(items) == 2
        symbols = {i.symbol for i in items}
        assert "add" in symbols
        assert "subtract" in symbols

    def test_extract_async_function(self, tmp_path: Path):
        """提取 async 函数。"""
        code = (
            "async def fetch_data():\n"
            "    return await something()\n"
        )
        f = tmp_path / "async_mod.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("async_mod.py", "async_mod", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        assert len(items) == 1
        assert items[0].symbol == "fetch_data"


# ═══════════════════════════════════════════
# 3. AST extraction — classes
# ═══════════════════════════════════════════


class TestExtractClasses:
    def test_extract_class(self, tmp_path: Path):
        """AST 解析提取类定义。"""
        code = (
            "class VideoProcessor:\n"
            "    def process(self):\n"
            "        pass\n"
        )
        f = tmp_path / "video.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("video.py", "video", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        # Class + method inside it
        assert len(items) == 2
        assert items[0].claim_type == "class"
        assert items[0].symbol == "VideoProcessor"
        assert items[1].claim_type == "function"
        assert items[1].symbol == "process"

    def test_extract_class_with_methods(self, tmp_path: Path):
        """提取类及其方法。"""
        code = (
            "class Agent:\n"
            "    def run(self):\n"
            "        pass\n"
            "    def stop(self):\n"
            "        pass\n"
        )
        f = tmp_path / "agent.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("agent.py", "agent", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        # Should have class + 2 methods
        assert len(items) == 3
        symbols = {i.symbol for i in items}
        assert "Agent" in symbols
        assert "run" in symbols
        assert "stop" in symbols


# ═══════════════════════════════════════════
# 4. Skip dunder methods
# ═══════════════════════════════════════════


class TestSkipDunder:
    def test_skip_init(self, tmp_path: Path):
        """跳过 __init__ 方法。"""
        code = (
            "class Foo:\n"
            "    def __init__(self):\n"
            "        self.x = 1\n"
            "    def bar(self):\n"
            "        pass\n"
        )
        f = tmp_path / "foo.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("foo.py", "foo", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        symbols = {i.symbol for i in items}
        assert "__init__" not in symbols
        assert "bar" in symbols

    def test_skip_str(self, tmp_path: Path):
        """跳过 __str__ 方法。"""
        code = (
            "class Bar:\n"
            "    def __str__(self):\n"
            "        return 'Bar'\n"
            "    def process(self):\n"
            "        pass\n"
        )
        f = tmp_path / "bar.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("bar.py", "bar", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        symbols = {i.symbol for i in items}
        assert "__str__" not in symbols
        assert "process" in symbols


# ═══════════════════════════════════════════
# 5. build_index
# ═══════════════════════════════════════════


class TestBuildIndex:
    def test_build_index_format(self, tmp_path: Path):
        """build_index 返回 {file: [EvidenceItem]} 格式。"""
        code = "def foo():\n    pass\n"
        f = tmp_path / "mod.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("mod.py", "mod", code)])
        extractor = EvidenceExtractor(index)
        idx = extractor.build_index()

        assert "mod.py" in idx
        assert len(idx["mod.py"]) == 1
        assert idx["mod.py"][0].symbol == "foo"

    def test_build_index_multiple_files(self, tmp_path: Path):
        """多文件索引。"""
        code1 = "def alpha():\n    pass\n"
        code2 = "class Beta:\n    pass\n"
        (tmp_path / "a.py").write_text(code1, encoding="utf-8")
        (tmp_path / "b.py").write_text(code2, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [
            ("a.py", "a", code1),
            ("b.py", "b", code2),
        ])
        extractor = EvidenceExtractor(index)
        idx = extractor.build_index()

        assert len(idx) == 2
        assert "a.py" in idx
        assert "b.py" in idx


# ═══════════════════════════════════════════
# 6. Edge cases
# ═══════════════════════════════════════════


class TestEdgeCases:
    def test_empty_workspace(self):
        """空 workspace 返回空索引。"""
        index = WorkspaceIndex(root="/workspace")
        extractor = EvidenceExtractor(index)
        items = extractor.extract()
        assert items == []

    def test_non_python_files_skipped(self, tmp_path: Path):
        """跳过非 .py 文件。"""
        (tmp_path / "readme.md").write_text("# Hello", encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("readme.md", "readme", "# Hello")])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()
        assert items == []

    def test_syntax_error_handling(self, tmp_path: Path):
        """语法错误的文件不崩溃。"""
        code = "def broken(\n    invalid syntax"
        f = tmp_path / "broken.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("broken.py", "broken", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()
        # Should not crash, returns empty
        assert items == []

    def test_file_not_found(self):
        """文件不存在时不崩溃。"""
        index = _make_index([("nonexistent.py", "non", "code")])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()
        assert items == []


# ═══════════════════════════════════════════
# 7. Excerpt extraction
# ═══════════════════════════════════════════


class TestExcerpt:
    def test_excerpt_first_lines(self, tmp_path: Path):
        """excerpt 包含函数体前几行。"""
        code = (
            "def process():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    z = 3\n"
            "    return x + y + z\n"
        )
        f = tmp_path / "proc.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("proc.py", "proc", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        assert len(items) == 1
        excerpt = items[0].excerpt
        assert "x = 1" in excerpt
        assert "y = 2" in excerpt

    def test_excerpt_max_3_lines(self, tmp_path: Path):
        """excerpt 最多 3 行。"""
        code = (
            "def many_lines():\n"
            "    line1 = 1\n"
            "    line2 = 2\n"
            "    line3 = 3\n"
            "    line4 = 4\n"
            "    line5 = 5\n"
        )
        f = tmp_path / "many.py"
        f.write_text(code, encoding="utf-8")

        index = _make_index_with_root(str(tmp_path), [("many.py", "many", code)])
        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        assert len(items) == 1
        lines = items[0].excerpt.strip().split("\n")
        assert len(lines) <= 3


# ═══════════════════════════════════════════
# 8. Integration with real workspace
# ═══════════════════════════════════════════


class TestIntegration:
    def test_extract_real_workspace(self):
        """测试真实 workspace 的 evidence 提取。"""
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        from app.workspace.indexer import IndexBuilder
        builder = IndexBuilder()
        index = builder.build(str(ws))

        extractor = EvidenceExtractor(index)
        items = extractor.extract()

        # 应该提取到一些函数/类
        assert len(items) > 0

        # 验证每个 item 有合理的字段
        for item in items[:5]:
            assert item.claim_type in ("function", "class")
            assert item.file.endswith(".py")
            assert item.symbol
            assert item.line_start > 0
            assert item.line_end >= item.line_start
