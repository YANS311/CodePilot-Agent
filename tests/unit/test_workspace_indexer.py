"""D16 Tests — WorkspaceIndex Builder 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.workspace.indexer import IndexBuilder, WorkspaceIndex, FileEntry


# ═══════════════════════════════════════════
# 1. Empty workspace
# ═══════════════════════════════════════════


class TestEmptyWorkspace:
    def test_build_empty(self, tmp_path):
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.files == []
        assert index.tree == {"files": [], "dirs": {}}
        assert index.summary["total_files"] == 0

    def test_build_nonexistent(self, tmp_path):
        builder = IndexBuilder()
        index = builder.build(str(tmp_path / "nonexistent"))
        assert index.files == []


# ═══════════════════════════════════════════
# 2. File detection
# ═══════════════════════════════════════════


class TestFileDetection:
    def test_detect_py_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "utils.py").write_text("def foo(): pass")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert len(index.files) == 2
        paths = [f.path for f in index.files]
        assert "main.py" in paths
        assert "utils.py" in paths

    def test_module_name(self, tmp_path):
        (tmp_path / "buggy_calculator.py").write_text("class Calculator: pass")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.files[0].module_name == "buggy_calculator"

    def test_file_size(self, tmp_path):
        content = "x = 1\n" * 100
        (tmp_path / "data.py").write_text(content)
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.files[0].size > 0

    def test_mixed_files(self, tmp_path):
        (tmp_path / "app.py").write_text("print('app')")
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "config.json").write_text('{"key": "value"}')
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert len(index.files) == 3
        py_count = sum(1 for f in index.files if f.path.endswith(".py"))
        assert py_count == 1


# ═══════════════════════════════════════════
# 3. Tree structure
# ═══════════════════════════════════════════


class TestTreeStructure:
    def test_flat_tree(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert "a.py" in index.tree["files"]
        assert "b.py" in index.tree["files"]

    def test_nested_tree(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_main.py").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert "src" in index.tree["dirs"]
        assert "tests" in index.tree["dirs"]
        assert "main.py" in index.tree["dirs"]["src"]["files"]
        assert "test_main.py" in index.tree["dirs"]["tests"]["files"]

    def test_deeply_nested(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert "a" in index.tree["dirs"]
        assert "b" in index.tree["dirs"]["a"]["dirs"]
        assert "c" in index.tree["dirs"]["a"]["dirs"]["b"]["dirs"]
        assert "deep.py" in index.tree["dirs"]["a"]["dirs"]["b"]["dirs"]["c"]["files"]


# ═══════════════════════════════════════════
# 4. Skip dirs
# ═══════════════════════════════════════════


class TestSkipDirs:
    def test_skip_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("")
        (tmp_path / "app.py").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert len(index.files) == 1
        assert index.files[0].path == "app.py"

    def test_skip_pycache(self, tmp_path):
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-311.pyc").write_bytes(b"")
        (tmp_path / "module.py").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert len(index.files) == 1

    def test_skip_node_modules(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg").mkdir()
        (tmp_path / "node_modules" / "pkg" / "index.js").write_text("")
        (tmp_path / "index.js").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert len(index.files) == 1


# ═══════════════════════════════════════════
# 5. Summary stats
# ═══════════════════════════════════════════


class TestSummary:
    def test_total_files(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text("")
        (tmp_path / "readme.md").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.summary["total_files"] == 6
        assert index.summary["python_files"] == 5

    def test_largest_files(self, tmp_path):
        (tmp_path / "small.py").write_text("x = 1")
        (tmp_path / "large.py").write_text("x = 1\n" * 1000)
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        largest = index.summary["largest_files"]
        assert len(largest) > 0
        assert largest[0]["path"] == "large.py"

    def test_python_files_stat(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "c.txt").write_text("")
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.summary["python_files"] == 2


# ═══════════════════════════════════════════
# 6. File summary (first 200 lines)
# ═══════════════════════════════════════════


class TestFileSummary:
    def test_py_summary_extracted(self, tmp_path):
        content = "\n".join([f"line_{i}" for i in range(10)])
        (tmp_path / "code.py").write_text(content)
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.files[0].summary != ""
        assert "line_0" in index.files[0].summary

    def test_non_py_no_summary(self, tmp_path):
        (tmp_path / "data.json").write_text('{"key": "value"}')
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        assert index.files[0].summary == ""

    def test_long_file_truncated(self, tmp_path):
        content = "\n".join([f"line_{i}" for i in range(300)])
        (tmp_path / "long.py").write_text(content)
        builder = IndexBuilder()
        index = builder.build(str(tmp_path))
        summary_lines = index.files[0].summary.split("\n")
        assert len(summary_lines) == 200
