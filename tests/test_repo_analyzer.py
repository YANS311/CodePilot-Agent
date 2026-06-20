"""D17+D18 Tests — RepoAnalyzer 测试。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.repo_analyzer import RepoAnalyzer, RepoAnalysis, ClaimEvidence, _format_evidence_index
from app.agent.evidence_extractor import EvidenceItem
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

    def test_default_evidence_fields(self):
        """D18: evidence 和 confidence 字段默认值。"""
        analysis = RepoAnalysis()
        assert analysis.confidence == 0.0
        assert analysis.claims == []


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

    def test_parse_evidence_section(self):
        """D18: 解析 Evidence 部分。"""
        raw = """## Project Overview
AI System: 视频分析平台

## Evidence
Claim: 视频处理由 process_video() 完成
- File: app/main.py, Symbol: process_video, Lines: 10-25
- File: app/processor.py, Symbol: Processor, Lines: 5-40

Claim: 配置管理通过 config 模块处理
- File: app/config.py, Symbol: load_config, Lines: 1-15

## Potential Issues
- 缺少错误处理
"""
        index = _make_index([("app/main.py", "main", "")])
        llm = _mock_llm(raw)
        analyzer = RepoAnalyzer(llm=llm, index=index)

        import asyncio
        analysis = asyncio.run(analyzer.analyze())

        assert len(analysis.claims) == 2
        assert analysis.claims[0].claim_text == "视频处理由 process_video() 完成"
        assert len(analysis.claims[0].evidence) == 2
        assert analysis.claims[0].evidence[0].file == "app/main.py"
        assert analysis.claims[0].evidence[0].symbol == "process_video"
        assert analysis.claims[0].evidence[0].line_start == 10
        assert analysis.claims[0].evidence[0].line_end == 25
        assert analysis.claims[1].claim_text == "配置管理通过 config 模块处理"
        assert len(analysis.claims[1].evidence) == 1


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


# ═══════════════════════════════════════════
# 6. ClaimEvidence dataclass (D18)
# ═══════════════════════════════════════════


class TestClaimEvidence:
    def test_claim_with_evidence(self):
        """ClaimEvidence 链接 claim 和 evidence items。"""
        ev = EvidenceItem(
            claim_type="function",
            file="app/main.py",
            symbol="process",
            line_start=10,
            line_end=25,
        )
        claim = ClaimEvidence(
            claim_text="视频处理由 process() 完成",
            evidence=[ev],
        )
        assert claim.claim_text == "视频处理由 process() 完成"
        assert len(claim.evidence) == 1
        assert claim.evidence[0].symbol == "process"

    def test_claim_without_evidence(self):
        """无证据的 claim 仍然有效。"""
        claim = ClaimEvidence(claim_text="这是一个结论")
        assert claim.claim_text == "这是一个结论"
        assert claim.evidence == []


# ═══════════════════════════════════════════
# 7. Confidence calculation (D18)
# ═══════════════════════════════════════════


class TestConfidence:
    def test_high_confidence(self):
        """多证据 + 多文件 → 高置信度。"""
        claims = [
            ClaimEvidence(
                claim_text="claim1",
                evidence=[
                    EvidenceItem("function", "a.py", "foo", 1, 10),
                    EvidenceItem("function", "b.py", "bar", 1, 10),
                ],
            ),
            ClaimEvidence(
                claim_text="claim2",
                evidence=[
                    EvidenceItem("class", "c.py", "Baz", 1, 20),
                ],
            ),
        ]
        evidence_index = {
            "a.py": [EvidenceItem("function", "a.py", "foo", 1, 10)],
            "b.py": [EvidenceItem("function", "b.py", "bar", 1, 10)],
            "c.py": [EvidenceItem("class", "c.py", "Baz", 1, 20)],
        }
        confidence = RepoAnalyzer._compute_confidence(claims, evidence_index)
        assert confidence >= 0.7

    def test_low_confidence_no_evidence(self):
        """无证据 → 低置信度。"""
        claims = [
            ClaimEvidence(claim_text="unsupported claim"),
        ]
        confidence = RepoAnalyzer._compute_confidence(claims, {})
        assert confidence == 0.0

    def test_medium_confidence(self):
        """部分有证据 → 中等置信度。"""
        claims = [
            ClaimEvidence(
                claim_text="supported",
                evidence=[EvidenceItem("function", "a.py", "foo", 1, 10)],
            ),
            ClaimEvidence(claim_text="unsupported"),
        ]
        evidence_index = {
            "a.py": [EvidenceItem("function", "a.py", "foo", 1, 10)],
            "b.py": [EvidenceItem("function", "b.py", "bar", 1, 10)],
        }
        confidence = RepoAnalyzer._compute_confidence(claims, evidence_index)
        assert 0.2 <= confidence <= 0.8

    def test_empty_claims(self):
        """空 claims → 0.0。"""
        confidence = RepoAnalyzer._compute_confidence([], {})
        assert confidence == 0.0


# ═══════════════════════════════════════════
# 8. Evidence index formatting (D18)
# ═══════════════════════════════════════════


class TestEvidenceIndexFormat:
    def test_format_empty(self):
        """空索引输出占位文本。"""
        result = _format_evidence_index({})
        assert "无代码证据" in result

    def test_format_with_items(self):
        """有数据时格式化为可读文本。"""
        index = {
            "app/main.py": [
                EvidenceItem("function", "app/main.py", "run", 10, 30),
                EvidenceItem("class", "app/main.py", "Agent", 50, 100),
            ],
        }
        result = _format_evidence_index(index)
        assert "app/main.py:" in result
        assert "function: run (L10-L30)" in result
        assert "class: Agent (L50-L100)" in result
