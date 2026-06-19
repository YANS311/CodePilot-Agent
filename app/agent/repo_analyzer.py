"""repo_analyzer.py — RepoAnalyzer，基于 WorkspaceIndex 的多文件项目分析。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from app.core.llm_client import LLMClient
from app.workspace.indexer import WorkspaceIndex

logger = logging.getLogger(__name__)

_REPO_ANALYSIS_PROMPT = """你是一个高级代码分析师。请分析以下 Python 项目的结构和架构。

项目文件列表:
{file_summaries}

请严格按以下格式输出分析结果（使用 Markdown）:

## Project Overview
(项目类型: AI System / Web App / Library / CLI Tool / Data Pipeline，然后一句话概述项目功能)

## Architecture Flow
(执行流程，用数字编号，描述请求/数据如何在模块间流动)

## Core Modules
| Module | Path | Role |
|--------|------|------|
(列出每个核心模块: 名称 + 路径 + 一句话职责)

## Potential Issues
(列出潜在问题/风险点，用 bullet list)

## Suggested Improvements
(列出改进建议，用 bullet list)
"""


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


class RepoAnalyzer:
    """基于 WorkspaceIndex 的多文件项目分析器。"""

    def __init__(self, llm: LLMClient, index: WorkspaceIndex) -> None:
        self._llm = llm
        self._index = index

    async def analyze(self) -> RepoAnalysis:
        """分析整个项目，返回结构化结果。"""
        # 1. 构建文件摘要输入
        file_summaries = self._build_file_summaries()

        # 2. 调用 LLM 分析
        prompt = _REPO_ANALYSIS_PROMPT.format(file_summaries=file_summaries)
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

        # 3. 解析结构化输出
        analysis = self._parse_analysis(raw_output)
        analysis.raw_output = raw_output
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
            # 第一行通常是项目类型
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
