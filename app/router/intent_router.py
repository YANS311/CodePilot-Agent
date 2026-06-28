"""intent_router.py — 3-layer hybrid intent router.

Layer 1: Rule-based (keyword + regex) — fast path
Layer 2: Embedding-based (cosine similarity) — semantic layer
Layer 3: LLM fallback — for ambiguous inputs

Decision: rule > embedding (if confident) > LLM fallback
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from app.router.embedding_router import EmbeddingRouter, EmbeddingResult

logger = logging.getLogger(__name__)


# ── Intent Constants ─────────────────────────────────────

INTENT_REACT = "react"
INTENT_REPO = "repo"
INTENT_SECURITY = "security"
INTENT_UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: str  # "react" | "repo" | "security" | "unknown"
    confidence: float  # 0.0 ~ 1.0
    layer: str  # "rule" | "embedding" | "llm" | "default"
    details: str = ""  # explanation of why this intent was chosen
    latency_ms: int = 0


# ── Layer 1: Rule-based Router ──────────────────────────

# REACT mode keywords (code fix / tool execution)
_REACT_KEYWORDS = [
    "fix", "修复", "debug", "调试", "write", "编写", "create", "创建",
    "add", "添加", "modify", "修改", "refactor", "重构", "implement", "实现",
    "update", "更新", "remove", "删除", "optimize", "优化",
    "test", "测试", "execute", "执行",
    "bug", "error", "crash", "exception", "failed", "failing",
    "null pointer", "type error", "import error", "syntax error",
]

# REPO mode keywords (migrated from react_agent.py)
_REPO_KEYWORDS = [
    "项目做什么", "做什么的", "整体架构", "系统架构",
    "系统流程", "执行流程", "怎么运行", "如何运行",
    "项目结构", "代码结构", "模块职责", "分析项目",
    "项目概览", "代码分析", "架构分析",
    "repo", "architecture", "overview", "analyze project",
    "explain the codebase", "what does this project",
    "describe the architecture",
]

# SECURITY mode keywords (attack / injection patterns)
_SECURITY_KEYWORDS = [
    "ignore previous", "忽略之前", "ignore all previous",
    "you are now", "你现在是", "pretend you",
    "reveal your system", "系统提示词", "system prompt",
    "bypass", "绕过", "no restrictions", "没有限制",
    "inject", "注入", "malicious", "恶意",
    "unauthorized", "未授权", "arbitrary command", "任意命令",
    "jailbreak", "越狱", "override safety",
    "disregard", "forget your instructions",
]

# Regex patterns for security detection
_SECURITY_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+)?(have|are|do)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"bypass\s+(safety|security|filter)", re.IGNORECASE),
    re.compile(r"<\|.*?\|>", re.IGNORECASE),  # special token injection
    re.compile(r"<[a-z]{2,}:[a-z]+", re.IGNORECASE),  # DSML-style injection
]


def _rule_based_route(task: str) -> Optional[IntentResult]:
    """Layer 1: Rule-based routing via keywords and regex.

    Returns IntentResult if a rule matches, None otherwise.
    """
    task_lower = task.lower().strip()

    # Check security first (highest priority)
    for pattern in _SECURITY_PATTERNS:
        if pattern.search(task):
            return IntentResult(
                intent=INTENT_SECURITY,
                confidence=1.0,
                layer="rule",
                details=f"regex: {pattern.pattern}",
            )

    for kw in _SECURITY_KEYWORDS:
        if kw.lower() in task_lower:
            return IntentResult(
                intent=INTENT_SECURITY,
                confidence=0.95,
                layer="rule",
                details=f"keyword: {kw}",
            )

    # Check react mode (code fix / tool execution) — higher priority than repo
    for kw in _REACT_KEYWORDS:
        if kw.lower() in task_lower:
            return IntentResult(
                intent=INTENT_REACT,
                confidence=0.85,
                layer="rule",
                details=f"keyword: {kw}",
            )

    # Check repo mode
    for kw in _REPO_KEYWORDS:
        if kw.lower() in task_lower:
            return IntentResult(
                intent=INTENT_REPO,
                confidence=0.9,
                layer="rule",
                details=f"keyword: {kw}",
            )

    return None  # No rule matched → fall through to next layer


# ── Layer 2: Embedding Router (lazy init) ───────────────

_embedding_router: Optional[EmbeddingRouter] = None


def _get_embedding_router() -> EmbeddingRouter:
    """Lazy-init the embedding router singleton."""
    global _embedding_router
    if _embedding_router is None:
        from app.core.config import settings
        threshold = getattr(settings, "intent_embedding_threshold", 0.55)
        _embedding_router = EmbeddingRouter(threshold=threshold)
    return _embedding_router


def _embedding_route(task: str) -> Optional[IntentResult]:
    """Layer 2: Embedding-based routing via cosine similarity.

    Returns IntentResult if confidence exceeds threshold, None otherwise.
    """
    try:
        router = _get_embedding_router()
        result = router.classify(task)

        # Require high confidence for embedding-based classification
        # to avoid false positives on ambiguous inputs
        if result.score >= router.threshold:
            return IntentResult(
                intent=result.intent,
                confidence=min(result.score, 1.0),
                layer="embedding",
                details=f"scores: {result.all_scores}",
            )
    except Exception as e:
        logger.debug("Embedding router failed: %s", e)

    return None  # Below threshold or error → fall through


# ── Layer 3: LLM Fallback ──────────────────────────────

def _llm_route(task: str) -> IntentResult:
    """Layer 3: LLM-based routing for ambiguous inputs.

    Uses a simple heuristic when LLM is not available.
    In production, this would call the LLM with a classification prompt.
    """
    # Simple heuristic fallback: check for question patterns
    task_lower = task.lower()

    # Questions about code → likely repo analysis
    question_patterns = [
        r"^(what|how|why|explain|describe|tell me about)",
        r"^(什么|怎么|为什么|解释|描述|告诉我)",
    ]
    for pat in question_patterns:
        if re.match(pat, task_lower):
            return IntentResult(
                intent=INTENT_REPO,
                confidence=0.6,
                layer="llm",
                details="heuristic: question pattern",
            )

    # Default to react for imperative commands
    return IntentResult(
        intent=INTENT_REACT,
        confidence=0.5,
        layer="default",
        details="default: react mode",
    )


# ── Main Router ─────────────────────────────────────────

class IntentRouter:
    """3-layer hybrid intent router.

    Decision flow:
        1. Rule-based (keyword/regex) → high confidence, fast
        2. Embedding-based (cosine similarity) → semantic match
        3. LLM fallback → for ambiguous inputs

    Usage:
        router = IntentRouter()
        result = router.route("fix the bug in todo.py")
        assert result.intent == "react"
    """

    def __init__(self) -> None:
        self._route_count = 0
        self._layer_counts = {"rule": 0, "embedding": 0, "llm": 0, "default": 0}
        self._intent_counts: dict[str, int] = {}

    def route(self, task: str) -> IntentResult:
        """Route a task to the appropriate intent.

        Tries each layer in order. Returns the first confident match.
        """
        t0 = time.monotonic()
        self._route_count += 1

        # Layer 1: Rule-based (fast path)
        result = _rule_based_route(task)
        if result is not None:
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            self._record(result)
            return result

        # Layer 2: Embedding-based (semantic)
        result = _embedding_route(task)
        if result is not None:
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            self._record(result)
            return result

        # Layer 3: LLM fallback
        result = _llm_route(task)
        result.latency_ms = int((time.monotonic() - t0) * 1000)
        self._record(result)
        return result

    def _record(self, result: IntentResult) -> None:
        """Record routing statistics."""
        self._layer_counts[result.layer] = self._layer_counts.get(result.layer, 0) + 1
        self._intent_counts[result.intent] = self._intent_counts.get(result.intent, 0) + 1

    def stats(self) -> dict:
        """Return routing statistics."""
        return {
            "total_routes": self._route_count,
            "layer_counts": dict(self._layer_counts),
            "intent_counts": dict(self._intent_counts),
        }

    def reset_stats(self) -> None:
        """Reset routing statistics."""
        self._route_count = 0
        self._layer_counts = {"rule": 0, "embedding": 0, "llm": 0, "default": 0}
        self._intent_counts = {}


# ── Singleton ──────────────────────────────────────────

_intent_router: Optional[IntentRouter] = None


def get_intent_router() -> IntentRouter:
    """Get the global intent router instance."""
    global _intent_router
    if _intent_router is None:
        _intent_router = IntentRouter()
    return _intent_router
