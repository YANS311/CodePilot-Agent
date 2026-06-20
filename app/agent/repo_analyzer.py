"""repo_analyzer.py — RepoAnalyzer，基于 WorkspaceIndex 的多文件项目分析。

D18: 支持 Evidence-based 分析 — 每个结论附带代码证据 + 置信度。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.agent.evidence_extractor import EvidenceExtractor, EvidenceItem
from app.core.llm_client import LLMClient
from app.workspace.indexer import WorkspaceIndex

logger = logging.getLogger(__name__)

_REPO_ANALYSIS_PROMPT = """你是一个高级代码分析师。请分析以下 Python 项目的结构和架构。

项目文件列表:
{file_summaries}

可用的代码证据索引 (函数/类定义及其行号):
{evidence_index}

请严格按以下格式输出分析结果（使用 Markdown）:

## Project Overview
(项目类型: AI System / Web App / Library / CLI Tool / Data Pipeline，然后一句话概述项目功能)

## Architecture Flow
(执行流程，用数字编号，描述请求/数据如何在模块间流动)

## Core Modules
| Module | Path | Role |
|--------|------|------|
(列出每个核心模块: 名称 + 路径 + 一句话职责)

## Evidence
(为每个核心结论列出证据。使用以下格式，每个 Claim 独占一段:)
Claim: [结论描述]
- File: [文件路径], Symbol: [函数/类名], Lines: [行号范围]
- File: [文件路径], Symbol: [函数/类名], Lines: [行号范围]

(如果证据索引中有对应的函数/类，请引用实际的文件路径、符号名和行号)

## Potential Issues
(列出潜在问题/风险点，用 bullet list)

## Suggested Improvements
(列出改进建议，用 bullet list)
"""


@dataclass
class ClaimEvidence:
    """单个结论 + 支撑证据。"""

    claim_text: str
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass
class RepoAnalysis:
    """项目分析结果。"""

    project_type: str = ""
    architecture_summary: str = ""
    core_modules: list[dict] = field(default_factory=list)
    execution_flow: list[str] = field(default_factory=list)
    key_entry_points: list[str] = field(default_factory=list)
    potential_bottlenecks: list[str] = field(default_factory=list)
    suggested_improvements: list[str] = field(default_factory=list)
    raw_output: str = ""
    # D18: evidence-based fields
    confidence: float = 0.0
    claims: list[ClaimEvidence] = field(default_factory=list)


def _format_evidence_index(evidence_index: dict[str, list[EvidenceItem]]) -> str:
    """将 evidence index 格式化为 prompt 中的可读文本。"""
    if not evidence_index:
        return "(无代码证据)"

    lines: list[str] = []
    for file_path, items in evidence_index.items():
        lines.append(f"{file_path}:")
        for item in items:
            lines.append(
                f"  - {item.claim_type}: {item.symbol} (L{item.line_start}-L{item.line_end})"
            )
    return "\n".join(lines)


class RepoAnalyzer:
    """基于 WorkspaceIndex 的多文件项目分析器。"""

    def __init__(self, llm: LLMClient, index: WorkspaceIndex) -> None:
        self._llm = llm
        self._index = index
        self._evidence_extractor = EvidenceExtractor(index)
        self._evidence_index: dict[str, list[EvidenceItem]] = {}

    async def analyze(self) -> RepoAnalysis:
        """分析整个项目，返回结构化结果。"""
        # 1. 构建 evidence index
        self._evidence_index = self._evidence_extractor.build_index()

        # 2. 构建文件摘要输入
        file_summaries = self._build_file_summaries()
        evidence_index_text = _format_evidence_index(self._evidence_index)

        # 3. 调用 LLM 分析
        prompt = _REPO_ANALYSIS_PROMPT.format(
            file_summaries=file_summaries,
            evidence_index=evidence_index_text,
        )
        messages = [{"role": "user", "content": prompt}]

        try:
            response = await self._llm.chat(messages)
            raw_output = response.content or ""
        except Exception as exc:
            logger.exception("Repo analysis LLM call failed")
            return RepoAnalysis(
                project_type="Unknown",
                architecture_summary=f"分析失败: {exc}",
                raw_output=str(exc),
            )

        # 4. 解析结构化输出
        analysis = self._parse_analysis(raw_output)
        analysis.raw_output = raw_output

        # 5. 验证 evidence — 匹配 LLM 引用的符号到实际 evidence index
        self._validate_evidence(analysis)

        # 6. 计算置信度
        analysis.confidence = self._compute_confidence(
            analysis.claims, self._evidence_index
        )

        return analysis

    def _build_file_summaries(self) -> str:
        """从 WorkspaceIndex 构建文件摘要列表。"""
        lines = []
        for f in self._index.files:
            if not f.path.endswith(".py"):
                continue
            lines.append(f"### {f.path} ({f.size} bytes)")
            if f.summary:
                # 只取前 50 行用于 prompt（节省 token）
                summary_lines = f.summary.split("\n")[:50]
                lines.append("\n".join(summary_lines))
            lines.append("")

        if not lines:
            return "(无 Python 文件)"

        return "\n".join(lines)

    def _parse_analysis(self, raw: str) -> RepoAnalysis:
        """解析 LLM 输出为 RepoAnalysis。"""
        analysis = RepoAnalysis()

        # 提取 Project Overview
        overview_match = re.search(
            r"## Project Overview\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if overview_match:
            overview_text = overview_match.group(1).strip()
            first_line = overview_text.split("\n")[0].strip()
            if ":" in first_line:
                analysis.project_type = first_line.split(":")[0].strip()
                analysis.architecture_summary = ":".join(first_line.split(":")[1:]).strip()
            else:
                analysis.project_type = first_line
                analysis.architecture_summary = overview_text

        # 提取 Architecture Flow
        flow_match = re.search(
            r"## Architecture Flow\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if flow_match:
            flow_text = flow_match.group(1).strip()
            analysis.execution_flow = [
                line.strip() for line in flow_text.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]

        # 提取 Core Modules
        modules_match = re.search(
            r"## Core Modules\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if modules_match:
            modules_text = modules_match.group(1).strip()
            for line in modules_text.split("\n"):
                line = line.strip()
                if line.startswith("|") and not line.startswith("|--") and "Module" not in line:
                    parts = [p.strip() for p in line.split("|") if p.strip()]
                    if len(parts) >= 3:
                        analysis.core_modules.append({
                            "name": parts[0],
                            "path": parts[1],
                            "role": parts[2],
                        })

        # 提取 Evidence (D18)
        analysis.claims = self._parse_evidence_section(raw)

        # 提取 Potential Issues
        issues_match = re.search(
            r"## Potential Issues\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if issues_match:
            issues_text = issues_match.group(1).strip()
            analysis.potential_bottlenecks = [
                line.strip().lstrip("- ").lstrip("* ")
                for line in issues_text.split("\n")
                if line.strip() and line.strip().startswith(("- ", "* "))
            ]

        # 提取 Suggested Improvements
        improvements_match = re.search(
            r"## Suggested Improvements\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if improvements_match:
            improvements_text = improvements_match.group(1).strip()
            analysis.suggested_improvements = [
                line.strip().lstrip("- ").lstrip("* ")
                for line in improvements_text.split("\n")
                if line.strip() and line.strip().startswith(("- ", "* "))
            ]

        return analysis

    def _parse_evidence_section(self, raw: str) -> list[ClaimEvidence]:
        """解析 ## Evidence 部分为 ClaimEvidence 列表。"""
        evidence_match = re.search(
            r"## Evidence\s*\n(.+?)(?=\n##|\Z)", raw, re.DOTALL
        )
        if not evidence_match:
            return []

        evidence_text = evidence_match.group(1).strip()
        claims: list[ClaimEvidence] = []

        # 按 "Claim:" 分割
        claim_blocks = re.split(r"(?=^Claim:)", evidence_text, flags=re.MULTILINE)

        for block in claim_blocks:
            block = block.strip()
            if not block.startswith("Claim:"):
                continue

            # 提取 claim 文本
            claim_match = re.match(r"Claim:\s*(.+?)(?=\n-|\n\n|\Z)", block, re.DOTALL)
            if not claim_match:
                continue
            claim_text = claim_match.group(1).strip()

            # 提取 evidence items
            evidence_items: list[EvidenceItem] = []
            ev_pattern = re.compile(
                r"File:\s*(\S+),\s*Symbol:\s*(\S+),\s*Lines:\s*(\d+)-(\d+)"
            )
            for ev_match in ev_pattern.finditer(block):
                evidence_items.append(EvidenceItem(
                    claim_type="reference",
                    file=ev_match.group(1),
                    symbol=ev_match.group(2),
                    line_start=int(ev_match.group(3)),
                    line_end=int(ev_match.group(4)),
                ))

            claims.append(ClaimEvidence(
                claim_text=claim_text,
                evidence=evidence_items,
            ))

        return claims

    def _validate_evidence(self, analysis: RepoAnalysis) -> None:
        """验证 LLM 引用的 evidence 是否在实际 evidence index 中存在。"""
        if not self._evidence_index:
            return

        # 构建 (file, symbol) → EvidenceItem 的查找表
        lookup: dict[tuple[str, str], EvidenceItem] = {}
        for file_path, items in self._evidence_index.items():
            for item in items:
                lookup[(file_path, item.symbol)] = item

        for claim in analysis.claims:
            validated: list[EvidenceItem] = []
            for ev in claim.evidence:
                key = (ev.file, ev.symbol)
                if key in lookup:
                    # 用实际 evidence 替换（包含准确的行号和 excerpt）
                    validated.append(lookup[key])
                else:
                    # LLM 引用的符号不在索引中，保留原始引用
                    validated.append(ev)
            claim.evidence = validated

    @staticmethod
    def _compute_confidence(
        claims: list[ClaimEvidence],
        evidence_index: dict[str, list[EvidenceItem]],
    ) -> float:
        """计算分析置信度 (0.0 ~ 1.0)。"""
        if not claims:
            return 0.0

        # Factor 1: evidence coverage — % of claims with >=1 evidence item
        claims_with_evidence = sum(1 for c in claims if c.evidence)
        evidence_coverage = claims_with_evidence / len(claims)

        # Factor 2: file coverage — % of project files referenced
        total_files = len(evidence_index)
        referenced_files = len({e.file for c in claims for e in c.evidence})
        file_coverage = referenced_files / total_files if total_files else 0.0

        # Factor 3: evidence density — avg evidence items per claim (normalize to 1.0 at 3)
        total_evidence = sum(len(c.evidence) for c in claims)
        density = min(total_evidence / len(claims) / 3.0, 1.0)

        return round(
            0.4 * evidence_coverage + 0.3 * file_coverage + 0.3 * density, 2
        )
