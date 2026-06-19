"""D17 Tests — RepoAnalyzer 测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.repo_analyzer import RepoAnalyzer, RepoAnalysis
from app.agent.react_agent import _detect_mode
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


def _mock_llm(response_text: str) -> AsyncMock:
    """创建 mock LLM client。"""
    llm = AsyncMock()
    response = MagicMock()
    response.content = response_text
    llm.chat = AsyncMock(return_value=response)
    return llm


# ═══════════════════════════════════════════
# 1. Mode Detection
# ═══════════════════════════════════════════


class TestModeDetection:
    def test_react_mode_default(self):
        assert _detect_mode("修复 calculator 的 bug") == "react"

    def test_react_mode_fix(self):
        assert _detect_mode("fix the subtract function") == "react"

    def test_repo_mode_chinese(self):
        assert _detect_mode("这个项目做什么") == "repo"

    def test_repo_mode_architecture(self):
        assert _detect_mode("整体架构是什么") == "repo"

    def test_repo_mode_flow(self):
        assert _detect_mode("系统流程是怎样的") == "repo"

    def test_repo_mode_run(self):
        assert _detect_mode("怎么运行这个项目") == "repo"

    def test_repo_mode_structure(self):
        assert _detect_mode("项目结构分析") == "repo"

    def test_repo_mode_english(self):
        assert _detect_mode("show me the architecture") == "repo"

    def test_repo_mode_overview(self):
        assert _detect_mode("give me an overview") == "repo"


# ═══════════════════════════════════════════
# 2. RepoAnalysis dataclass
# ═══════════════════════════════════════════


class TestRepoAnalysis:
    def test_default_values(self):
        analysis = RepoAnalysis()
        assert analysis.project_type == ""
        assert analysis.core_modules == []
        assert analysis.execution_flow == []
        assert analysis.potential_bottlenecks == []
        assert analysis.suggested_improvements == []


# ═══════════════════════════════════════════
# 3. File summaries builder
# ═══════════════════════════════════════════


class TestFileSummaries:
    def test_build_summaries(self):
        index = _make_index([
            ("app/main.py", "main", "print('hello')"),
            ("utils.py", "utils", "def foo(): pass"),
        ])
        llm = _mock_llm("")
        analyzer = RepoAnalyzer(llm=llm, index=index)
        summaries = analyzer._build_file_summaries()
        assert "app/main.py" in summaries
        assert "utils.py" in summaries
        assert "print('hello')" in summaries

    def test_skip_non_py(self):
        index = _make_index([
            ("README.md", "README", "# Project"),
            ("app.py", "app", "print('hi')"),
        ])
        llm = _mock_llm("")
        analyzer = RepoAnalyzer(llm=llm, index=index)
        summaries = analyzer._build_file_summaries()
        assert "README.md" not in summaries
        assert "app.py" in summaries

    def test_empty_index(self):
        index = WorkspaceIndex(root="/workspace")
        llm = _mock_llm("")
        analyzer = RepoAnalyzer(llm=llm, index=index)
        summaries = analyzer._build_file_summaries()
        assert "无 Python 文件" in summaries


# ═══════════════════════════════════════════
# 4. Analysis parsing
# ═══════════════════════════════════════════


class TestAnalysisParsing:
    def test_parse_full_output(self):
        raw = """## Project Overview
AI System: 一个智能视频分析平台

## Architecture Flow
1. main.py → 加载配置
2. processor.py → 处理视频
3. output.py → 输出结果

## Core Modules
| Module | Path | Role |
|--------|------|------|
| main | app/main.py | 入口文件 |
| processor | app/processor.py | 视频处理 |

## Potential Issues
- 缺少错误处理
- 没有日志记录

## Suggested Improvements
- 添加异常处理
- 增加单元测试
"""
        index = _make_index([("app/main.py", "main", "")])
        llm = _mock_llm(raw)
        analyzer = RepoAnalyzer(llm=llm, index=index)

        import asyncio
        analysis = asyncio.run(analyzer.analyze())

        assert analysis.project_type == "AI System"
        assert "智能视频分析平台" in analysis.architecture_summary
        assert len(analysis.execution_flow) == 3
        assert len(analysis.core_modules) == 2
        assert analysis.core_modules[0]["name"] == "main"
        assert len(analysis.potential_bottlenecks) == 2
        assert len(analysis.suggested_improvements) == 2

    def test_parse_minimal_output(self):
        raw = "这是一个简单的项目。"
        index = _make_index([("app.py", "app", "")])
        llm = _mock_llm(raw)
        analyzer = RepoAnalyzer(llm=llm, index=index)

        import asyncio
        analysis = asyncio.run(analyzer.analyze())

        # 即使输出不规范，也不应崩溃
        assert analysis.raw_output == raw


# ═══════════════════════════════════════════
# 5. Integration with real workspace
# ═══════════════════════════════════════════


class TestIntegration:
    def test_analyze_real_workspace(self):
        """测试真实 workspace 的索引构建（不调用 LLM）。"""
        from app.workspace.indexer import IndexBuilder
        ws = PROJECT_ROOT / "workspace"
        if not ws.exists():
            pytest.skip("workspace 目录不存在")

        builder = IndexBuilder()
        index = builder.build(str(ws))

        assert index.files
        py_files = [f for f in index.files if f.path.endswith(".py")]
        assert len(py_files) > 0

        # 验证每个 .py 文件都有 summary
        for f in py_files[:5]:
            assert f.summary != "" or f.size == 0
