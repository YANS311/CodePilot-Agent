"""D15 Tests — Language Adapter 测试。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.language.python_adapter import PythonAdapter
from app.language.java_adapter import JavaAdapter
from app.language.node_adapter import NodeAdapter
from app.language.detector import LanguageDetector


# ═══════════════════════════════════════════
# 1. Python Adapter
# ═══════════════════════════════════════════


class TestPythonAdapter:
    def test_detect_with_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\n")
        adapter = PythonAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_with_py_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')\n")
        adapter = PythonAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_empty_workspace(self, tmp_path):
        adapter = PythonAdapter()
        assert adapter.detect(str(tmp_path)) is False

    def test_get_test_command(self):
        adapter = PythonAdapter()
        assert adapter.get_test_command() == "pytest"

    def test_get_test_command_with_target(self):
        adapter = PythonAdapter()
        assert adapter.get_test_command("tests/test_main.py") == "pytest tests/test_main.py"

    def test_get_source_files(self, tmp_path):
        (tmp_path / "main.py").write_text("")
        (tmp_path / "utils.py").write_text("")
        (tmp_path / "README.md").write_text("")
        adapter = PythonAdapter()
        files = adapter.get_source_files(str(tmp_path))
        assert "main.py" in files
        assert "utils.py" in files
        assert len(files) == 2

    def test_get_dependency_files(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\n")
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        adapter = PythonAdapter()
        deps = adapter.get_dependency_files(str(tmp_path))
        assert "requirements.txt" in deps
        assert "pyproject.toml" in deps


# ═══════════════════════════════════════════
# 2. Java Adapter (Stub)
# ═══════════════════════════════════════════


class TestJavaAdapter:
    def test_detect_with_pom(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        adapter = JavaAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_with_java_files(self, tmp_path):
        (tmp_path / "Main.java").write_text("class Main {}")
        adapter = JavaAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_empty_workspace(self, tmp_path):
        adapter = JavaAdapter()
        assert adapter.detect(str(tmp_path)) is False

    def test_get_test_command(self):
        adapter = JavaAdapter()
        cmd = adapter.get_test_command()
        assert "mvn" in cmd or "gradle" in cmd


# ═══════════════════════════════════════════
# 3. Node Adapter (Stub)
# ═══════════════════════════════════════════


class TestNodeAdapter:
    def test_detect_with_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        adapter = NodeAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_with_js_files(self, tmp_path):
        (tmp_path / "index.js").write_text("console.log('hello')")
        adapter = NodeAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_with_ts_files(self, tmp_path):
        (tmp_path / "app.ts").write_text("console.log('hello')")
        adapter = NodeAdapter()
        assert adapter.detect(str(tmp_path)) is True

    def test_detect_empty_workspace(self, tmp_path):
        adapter = NodeAdapter()
        assert adapter.detect(str(tmp_path)) is False


# ═══════════════════════════════════════════
# 4. Language Detector
# ═══════════════════════════════════════════


class TestLanguageDetector:
    def test_detect_python_workspace(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "requirements.txt").write_text("pytest\n")
        detector = LanguageDetector()
        result = detector.detect(str(tmp_path))
        assert result["primary_language"] == "python"
        assert "python" in result["detected_languages"]
        assert result["confidence"] > 0.5

    def test_detect_java_workspace(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        (tmp_path / "Main.java").write_text("class Main {}")
        detector = LanguageDetector()
        result = detector.detect(str(tmp_path))
        assert result["primary_language"] == "java"
        assert "java" in result["detected_languages"]

    def test_detect_node_workspace(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "index.js").write_text("console.log('hello')")
        detector = LanguageDetector()
        result = detector.detect(str(tmp_path))
        assert result["primary_language"] == "node"
        assert "node" in result["detected_languages"]

    def test_detect_mixed_workspace(self, tmp_path):
        # Python + Node 混合
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "index.js").write_text("console.log('hello')")
        detector = LanguageDetector()
        result = detector.detect(str(tmp_path))
        assert "python" in result["detected_languages"]
        assert "node" in result["detected_languages"]
        # Python 文件更多，应为主语言
        assert result["primary_language"] == "python"

    def test_detect_empty_workspace(self, tmp_path):
        detector = LanguageDetector()
        result = detector.detect(str(tmp_path))
        assert result["primary_language"] == ""
        assert result["detected_languages"] == []
        assert result["confidence"] == 0.0

    def test_get_adapter(self):
        detector = LanguageDetector()
        adapter = detector.get_adapter("python")
        assert adapter is not None
        assert adapter.language == "python"

    def test_list_adapters(self):
        detector = LanguageDetector()
        adapters = detector.list_adapters()
        assert len(adapters) == 3
        languages = [a["language"] for a in adapters]
        assert "python" in languages
        assert "java" in languages
        assert "node" in languages
