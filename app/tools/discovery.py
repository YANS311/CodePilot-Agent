"""app/tools/discovery.py — MCP Tool Progressive Loading & Discovery Routing.

根据任务意图与上下文动态过滤与召回最适用的 Top-K 工具，
避免全量工具 Schema 无差别注入导致 Token 膨胀与 LLM 注意力稀释。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# 基础原生核心工具集合（在无特定强匹配时提供保底能力）
DEFAULT_CORE_TOOLS = {
    "read_file",
    "search_code",
    "code_edit",
    "write_file",
}

# 意图同义词规则表，对齐中英文常见开发任务
_SYNONYM_CLUSTERS: Dict[str, Set[str]] = {
    "read": {"read", "view", "cat", "open", "load", "inspect", "show", "读", "读取", "查看", "打开", "展示"},
    "write": {"write", "save", "create", "dump", "output", "写", "写入", "创建", "保存", "生成"},
    "edit": {"edit", "replace", "modify", "patch", "change", "update", "fix", "修改", "编辑", "替换", "变更", "修复"},
    "search": {"search", "find", "grep", "lookup", "locate", "query", "scan", "搜索", "查找", "寻找", "定位", "检索"},
    "run": {"run", "execute", "exec", "test", "pytest", "eval", "start", "运行", "执行", "测试"},
    "database": {"db", "database", "sql", "table", "postgres", "sqlite", "query", "数据库", "查询", "表", "数据"},
    "git": {"git", "commit", "branch", "diff", "conflict", "merge", "status", "版本", "提交", "分支", "冲突", "合并"},
    "repo": {"repo", "repository", "structure", "architecture", "explore", "tree", "仓库", "架构", "结构", "分析", "探索"},
    "web": {"web", "http", "api", "fetch", "url", "curl", "request", "网络", "接口", "请求"},
    "security": {"security", "audit", "vuln", "vulnerability", "secret", "leak", "安全", "审计", "漏洞", "泄露"},
}

# Skill 到工具关键词的加成规则
_SKILL_TOOL_BOOSTS: Dict[str, Set[str]] = {
    "repository-explorer": {"search", "read", "repo", "git", "tree", "structure"},
    "bug-fix": {"read", "edit", "search", "run", "test"},
    "code-review": {"read", "diff", "git", "search", "security"},
    "test-debugging": {"run", "test", "read", "edit", "pytest"},
    "security-audit": {"security", "read", "search", "scan", "audit"},
    "git-workflow": {"git", "diff", "branch", "commit", "conflict"},
    "api-spec-validator": {"web", "api", "read", "test"},
}


def _tokenize_text(text: str) -> Set[str]:
    """提取文本中的英文单词、数字和中文 2~4 字词元。"""
    if not text:
        return set()
    text_lower = text.lower()
    tokens: Set[str] = set()

    # 1. 英文与数字 token
    for word in re.findall(r"[a-z0-9_\-]+", text_lower):
        parts = re.split(r"[_\-]+", word)
        for p in parts:
            if len(p) >= 2:
                tokens.add(p)
        if len(word) >= 2:
            tokens.add(word)

    # 2. 中文词元（提取 2-4 字符组合）
    chinese_chars = re.findall(r"[\u4e00-\u9fff]+", text_lower)
    for c_str in chinese_chars:
        if len(c_str) <= 4:
            tokens.add(c_str)
        else:
            for i in range(len(c_str) - 1):
                tokens.add(c_str[i : i + 2])
                if i + 3 <= len(c_str):
                    tokens.add(c_str[i : i + 3])

    return tokens


def _expand_synonyms(tokens: Set[str]) -> Set[str]:
    """将 tokens 扩充对应的意图同义词概念。"""
    expanded = set(tokens)
    for concept, words in _SYNONYM_CLUSTERS.items():
        if tokens & words:
            expanded.add(concept)
            expanded.update(words)
    return expanded


class ToolDiscovery:
    """工具检索与路由分发器。

    支持轻量 Hybrid Scoring：
    1. Tool Name Matching (精确名称与分词重合)
    2. Description Keyword Matching (描述关键词覆盖)
    3. Active Skill Tag Boost (根据当前激活 Skill 加成匹配度)
    4. Core Baseline Fallback (保底原生基础工具可用性)
    """

    def __init__(
        self,
        core_tools: Optional[Set[str]] = None,
        default_top_k: int = 10,
    ) -> None:
        self.core_tools = core_tools or DEFAULT_CORE_TOOLS
        self.default_top_k = default_top_k

    def calculate_score(
        self,
        tool: BaseTool,
        task_tokens: Set[str],
        task_expanded: Set[str],
        task_raw_lower: str,
        active_skill: Optional[str] = None,
        skill_tags: Optional[List[str]] = None,
    ) -> Tuple[float, List[str]]:
        """计算单个工具对任务的匹配得分与原因说明。"""
        score = 0.0
        reasons: List[str] = []

        tool_name_lower = tool.name.lower()
        tool_desc_lower = (tool.description or "").lower()

        tool_name_tokens = _tokenize_text(tool_name_lower)
        tool_desc_tokens = _tokenize_text(tool_desc_lower)

        # 1. Tool Name Matching
        if tool_name_lower in task_raw_lower:
            score += 10.0
            reasons.append("exact_name_match(+10.0)")
        else:
            # 分词精确命中
            name_hits = tool_name_tokens & task_tokens
            if name_hits:
                pts = min(len(name_hits) * 3.0, 9.0)
                score += pts
                reasons.append(f"name_tokens({','.join(sorted(name_hits))}:+{pts:.1f})")

            # 分词同义词命中
            name_syn_hits = tool_name_tokens & task_expanded
            if name_syn_hits and not name_hits:
                pts = min(len(name_syn_hits) * 2.0, 6.0)
                score += pts
                reasons.append(f"name_synonyms(+{pts:.1f})")

        # 2. Description Keyword Matching
        desc_hits = tool_desc_tokens & task_tokens
        if desc_hits:
            pts = min(len(desc_hits) * 1.0, 5.0)
            score += pts
            reasons.append(f"desc_keywords({len(desc_hits)}hits:+{pts:.1f})")

        desc_syn_hits = tool_desc_tokens & task_expanded
        if desc_syn_hits and not desc_hits:
            pts = min(len(desc_syn_hits) * 0.8, 3.0)
            score += pts
            reasons.append(f"desc_synonyms(+{pts:.1f})")

        # 3. Active Skill Tag Boost
        if active_skill:
            boost_concepts = _SKILL_TOOL_BOOSTS.get(active_skill, set())
            # 检查工具名称或描述是否包含加成概念
            matched_boosts = boost_concepts & (tool_name_tokens | tool_desc_tokens)
            if matched_boosts:
                score += 4.0
                reasons.append(f"skill_boost({active_skill}:+4.0)")

        if skill_tags:
            tag_tokens = set()
            for t in skill_tags:
                tag_tokens.update(_tokenize_text(t))
            matched_tags = tag_tokens & (tool_name_tokens | tool_desc_tokens)
            if matched_tags:
                score += 2.0
                reasons.append("skill_tag_boost(+2.0)")

        # 4. Core Baseline Preference
        # 原生基础工具赋予微小保底分（0.5），在无明显外部命中时优先保证基础能力可用
        if tool.name in self.core_tools:
            score += 0.5
            reasons.append("core_baseline(+0.5)")

        return score, reasons

    async def select_tools_detailed(
        self,
        task: str,
        tools: List[BaseTool],
        top_k: Optional[int] = None,
        active_skill: Optional[str] = None,
        skill_tags: Optional[List[str]] = None,
    ) -> Tuple[List[BaseTool], Dict[str, Any]]:
        """执行工具检索与排序，并返回选中的工具及其详细决策信息。"""
        if top_k is None:
            top_k = self.default_top_k

        if not tools:
            return [], {
                "candidate_count": 0,
                "selected_tools": [],
                "scores": {},
                "reason": "No candidate tools available",
            }

        # 若候选工具数未超过 top_k，直接全量返回
        if len(tools) <= top_k:
            return list(tools), {
                "candidate_count": len(tools),
                "selected_tools": [t.name for t in tools],
                "scores": {t.name: 1.0 for t in tools},
                "reason": f"Candidate tool count ({len(tools)}) <= top_k ({top_k}), retained all",
            }

        task_raw_lower = task.lower()
        task_tokens = _tokenize_text(task_raw_lower)
        task_expanded = _expand_synonyms(task_tokens)

        scored_tools: List[Tuple[BaseTool, float, List[str]]] = []
        scores_map: Dict[str, float] = {}

        for tool in tools:
            score, reasons = self.calculate_score(
                tool=tool,
                task_tokens=task_tokens,
                task_expanded=task_expanded,
                task_raw_lower=task_raw_lower,
                active_skill=active_skill,
                skill_tags=skill_tags,
            )
            scored_tools.append((tool, score, reasons))
            scores_map[tool.name] = round(score, 2)

        # 排序策略：得分高优先；同分时优先核心基础工具，其次按工具名稳定排序
        scored_tools.sort(
            key=lambda item: (
                item[1],
                1 if item[0].name in self.core_tools else 0,
                -len(item[0].name),
            ),
            reverse=True,
        )

        # 截取 Top-K
        selected_pairs = scored_tools[:top_k]
        selected_tools = [p[0] for p in selected_pairs]
        selected_names = [t.name for t in selected_tools]

        has_relevant_hits = any(p[1] > 0.5 for p in selected_pairs)
        if has_relevant_hits:
            top_reasons = [f"{p[0].name}({p[1]:.1f})" for p in selected_pairs[:3]]
            reason_str = f"Selected top-{len(selected_tools)} tools via hybrid scoring: {', '.join(top_reasons)}"
        else:
            reason_str = f"Fallback default selection of top-{len(selected_tools)} tools (no high-confidence query matches)"

        metadata = {
            "candidate_count": len(tools),
            "selected_tools": selected_names,
            "scores": {name: scores_map[name] for name in selected_names},
            "reason": reason_str,
        }

        logger.info(
            "ToolDiscovery selected %d/%d tools for task '%s...': %s",
            len(selected_tools),
            len(tools),
            task[:40],
            selected_names,
        )

        return selected_tools, metadata

    async def select_tools(
        self,
        task: str,
        tools: List[BaseTool],
        top_k: Optional[int] = None,
        active_skill: Optional[str] = None,
        skill_tags: Optional[List[str]] = None,
    ) -> List[BaseTool]:
        """按任务意图检索最适用的 Top-K 工具。"""
        selected_tools, _ = await self.select_tools_detailed(
            task=task,
            tools=tools,
            top_k=top_k,
            active_skill=active_skill,
            skill_tags=skill_tags,
        )
        return selected_tools


# 全局默认 ToolDiscovery 实例
default_tool_discovery = ToolDiscovery()
