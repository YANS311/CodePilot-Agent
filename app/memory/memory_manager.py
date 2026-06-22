"""memory_manager.py — High-level memory operations for CodePilot Agent.

Provides CRUD + query for TaskMemory, ErrorMemory, RepoMemory.
Integrates with the Agent loop to inject historical context.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.memory.memory_store import (
    ErrorMemory,
    InMemoryStore,
    RepoMemory,
    TaskMemory,
)

logger = logging.getLogger(__name__)


def _extract_keywords(prompt: str) -> list[str]:
    """Extract meaningful keywords from a task prompt for matching.

    Strips common stop words and short tokens, keeps nouns/verbs.
    """
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "under", "again",
        "over", "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "both", "each", "few", "more", "most", "other", "some",
        "such", "no", "nor", "not", "only", "own", "same", "so", "than",
        "too", "very", "just", "don", "now", "and", "but", "or", "if",
        "what", "which", "who", "whom", "this", "that", "these", "those",
        # Chinese stop words
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "们", "那", "被", "从", "把", "能", "让", "还", "可以", "吗",
        "请", "帮", "帮忙", "一下", "下", "修改", "修复", "添加", "创建",
    }

    # Split on whitespace and non-alphanumeric chars
    tokens = re.split(r"[\s\W_]+", prompt.lower())
    # Keep tokens >= 2 chars and not in stop words
    keywords = [t for t in tokens if len(t) >= 2 and t not in stop_words]
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:10]  # max 10 keywords


class MemoryManager:
    """High-level memory operations — CRUD + query + prompt injection.

    Singleton via get_memory_manager().
    """

    def __init__(self) -> None:
        self._store = InMemoryStore()

    # ── Task Memory ──────────────────────────────────────

    def add_task_memory(
        self,
        prompt: str,
        result: str,
        success: bool,
        tool_calls_count: int = 0,
        tool_trace: list[str] | None = None,
        workspace_id: str = "",
        duration_ms: int = 0,
    ) -> TaskMemory:
        """Record a completed task."""
        mem = TaskMemory(
            prompt=prompt,
            result=result,
            success=success,
            tool_calls_count=tool_calls_count,
            tool_trace=tool_trace or [],
            workspace_id=workspace_id,
            duration_ms=duration_ms,
        )
        self._store.add_task(mem)
        logger.info("Task memory added: %s (success=%s)", mem.task_id, success)
        return mem

    def query_task_memory(self, task_prompt: str, limit: int = 5) -> list[TaskMemory]:
        """Find similar past tasks by keyword matching."""
        keywords = _extract_keywords(task_prompt)
        if not keywords:
            return []
        return self._store.query_tasks(keywords, limit=limit)

    def get_task_memory(self, limit: int = 20) -> list[TaskMemory]:
        return self._store.get_tasks(limit)

    # ── Error Memory ─────────────────────────────────────

    def add_error_memory(
        self,
        error_type: str,
        context: str,
        fix_strategy: str = "",
        tool_trace: list[str] | None = None,
        workspace_id: str = "",
    ) -> ErrorMemory:
        """Record an error pattern and its fix strategy."""
        mem = ErrorMemory(
            error_type=error_type,
            context=context,
            fix_strategy=fix_strategy,
            tool_trace=tool_trace or [],
            workspace_id=workspace_id,
        )
        self._store.add_error(mem)
        logger.info("Error memory added: %s (type=%s)", mem.error_id, error_type)
        return mem

    def query_error_memory(
        self,
        error_type: str = "",
        keywords: list[str] | None = None,
        limit: int = 5,
    ) -> list[ErrorMemory]:
        """Find past errors by type and/or keywords."""
        return self._store.query_errors(error_type=error_type, keywords=keywords, limit=limit)

    def get_error_memory(self, limit: int = 20) -> list[ErrorMemory]:
        return self._store.get_errors(limit)

    # ── Repo Memory ──────────────────────────────────────

    def add_repo_memory(
        self,
        workspace_id: str,
        file_summary: str,
        module_map: dict[str, str] | None = None,
        analysis_result: str = "",
        confidence: float = 0.0,
    ) -> RepoMemory:
        """Record a workspace analysis result."""
        mem = RepoMemory(
            workspace_id=workspace_id,
            file_summary=file_summary,
            module_map=module_map or {},
            analysis_result=analysis_result,
            confidence=confidence,
        )
        self._store.add_repo(mem)
        logger.info("Repo memory added: %s (ws=%s)", mem.repo_id, workspace_id)
        return mem

    def query_repo_memory(self, workspace_id: str) -> Optional[RepoMemory]:
        """Find the latest repo memory for a workspace."""
        return self._store.query_repos(workspace_id)

    def get_repo_memory(self, limit: int = 20) -> list[RepoMemory]:
        return self._store.get_repos(limit)

    # ── Prompt Injection ─────────────────────────────────

    def build_memory_context(self, task: str, workspace_id: str = "") -> str:
        """Build a memory context block to inject into the agent's system prompt.

        Returns a string like:
            ## Historical Context
            ### Similar past tasks:
            - [success] Fixed bug in todo.py by...
            ### Previous failures to avoid:
            - test_failed: pytest assertion in line 42...
            ### Repo context:
            - Last analysis: AI System with 12 modules...

        Returns empty string if no relevant memories found.
        """
        sections: list[str] = []

        # 1. Similar past tasks
        similar_tasks = self.query_task_memory(task, limit=3)
        if similar_tasks:
            lines = []
            for t in similar_tasks:
                status = "success" if t.success else "failed"
                # Truncate prompt and result for context
                prompt_short = t.prompt[:80]
                result_short = t.result[:100]
                tools = ", ".join(t.tool_trace[:5]) if t.tool_trace else "none"
                lines.append(
                    f"- [{status}] \"{prompt_short}\" → "
                    f"tools: {tools}, result: {result_short}"
                )
            sections.append("### Similar past tasks:\n" + "\n".join(lines))

        # 2. Previous failures (only if task looks like it might hit similar errors)
        keywords = _extract_keywords(task)
        past_errors = self.query_error_memory(keywords=keywords, limit=3)
        if past_errors:
            lines = []
            for e in past_errors:
                fix = f" → fix: {e.fix_strategy[:80]}" if e.fix_strategy else ""
                lines.append(f"- [{e.error_type}] {e.context[:100]}{fix}")
            sections.append("### Previous failures to avoid:\n" + "\n".join(lines))

        # 3. Repo context
        if workspace_id:
            repo_mem = self.query_repo_memory(workspace_id)
            if repo_mem:
                sections.append(
                    f"### Repo context:\n"
                    f"- Last analysis: confidence={repo_mem.confidence}, "
                    f"{len(repo_mem.module_map)} modules\n"
                    f"- Files: {repo_mem.file_summary[:150]}"
                )

        if not sections:
            return ""

        return "## Historical Context\n" + "\n\n".join(sections)

    # ── Stats ────────────────────────────────────────────

    def stats(self) -> dict:
        return self._store.stats()


# ── Singleton ──────────────────────────────────────────

_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
