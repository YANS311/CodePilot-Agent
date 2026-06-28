"""memory_manager.py — Hybrid Memory Manager for CodePilot Agent.

Combines structured memory (keyword matching) with vector memory (FAISS semantic search).
1. Structured memory: exact/keyword match for task, error, repo records
2. Vector memory: semantic similarity for past solutions, errors, repo summaries
3. Merged context injection for the agent's system prompt
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
from app.memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)


def _extract_keywords(prompt: str) -> list[str]:
    """Extract meaningful keywords from a task prompt for matching."""
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
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "们", "那", "被", "从", "把", "能", "让", "还", "可以", "吗",
        "请", "帮", "帮忙", "一下", "下", "修改", "修复", "添加", "创建",
    }
    tokens = re.split(r"[\s\W_]+", prompt.lower())
    keywords = [t for t in tokens if len(t) >= 2 and t not in stop_words]
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique[:10]


class HybridMemoryManager:
    """Hybrid memory — structured (keyword) + vector (semantic) retrieval.

    Singleton via get_memory_manager().
    """

    def __init__(self, persist_path: Optional[str] = None) -> None:
        self._store = InMemoryStore(persist_path=persist_path)
        self._vector = VectorMemoryStore()

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
        """Record a completed task to both structured and vector stores."""
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

        # Write summary to vector store
        status = "success" if success else "failed"
        tools_str = ", ".join(tool_trace[:5]) if tool_trace else "no tools"
        vec_text = f"[{status}] Task: {prompt[:200]}. Result: {result[:200]}. Tools: {tools_str}"
        self._vector.add_memory(
            text=vec_text,
            metadata={"task_id": mem.task_id, "success": success, "workspace_id": workspace_id},
            memory_type="task",
        )

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
        """Record an error pattern to both structured and vector stores."""
        mem = ErrorMemory(
            error_type=error_type,
            context=context,
            fix_strategy=fix_strategy,
            tool_trace=tool_trace or [],
            workspace_id=workspace_id,
        )
        self._store.add_error(mem)

        # Write to vector store for semantic retrieval
        fix_str = f". Fix: {fix_strategy[:200]}" if fix_strategy else ""
        vec_text = f"[error:{error_type}] {context[:300]}{fix_str}"
        self._vector.add_memory(
            text=vec_text,
            metadata={"error_id": mem.error_id, "error_type": error_type},
            memory_type="error",
        )

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
        """Record a workspace analysis to both structured and vector stores."""
        mem = RepoMemory(
            workspace_id=workspace_id,
            file_summary=file_summary,
            module_map=module_map or {},
            analysis_result=analysis_result,
            confidence=confidence,
        )
        self._store.add_repo(mem)

        # Write to vector store
        modules_str = ", ".join(list(module_map.keys())[:10]) if module_map else "unknown"
        vec_text = f"[repo:{workspace_id}] Modules: {modules_str}. Summary: {file_summary[:300]}"
        self._vector.add_memory(
            text=vec_text,
            metadata={"repo_id": mem.repo_id, "workspace_id": workspace_id, "confidence": confidence},
            memory_type="repo",
        )

        logger.info("Repo memory added: %s (ws=%s)", mem.repo_id, workspace_id)
        return mem

    def query_repo_memory(self, workspace_id: str) -> Optional[RepoMemory]:
        """Find the latest repo memory for a workspace."""
        return self._store.query_repos(workspace_id)

    def get_repo_memory(self, limit: int = 20) -> list[RepoMemory]:
        return self._store.get_repos(limit)

    # ── Vector Search ────────────────────────────────────

    def search_vector_memory(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
    ) -> list[dict]:
        """Semantic search across all vector memories.

        Returns list of dicts with text, score, metadata, memory_type.
        """
        results = self._vector.search_memory(query, top_k=top_k, memory_type=memory_type)
        return [
            {
                "text": entry.text[:300],
                "score": round(score, 4),
                "memory_type": entry.memory_type,
                "metadata": entry.metadata,
            }
            for entry, score in results
        ]

    # ── Hybrid Prompt Injection ──────────────────────────

    def build_memory_context(self, task: str, workspace_id: str = "") -> str:
        """Build a merged memory context block for the agent's system prompt.

        Combines structured (keyword) and vector (semantic) results:
        1. Structured: exact/keyword match from task/error/repo stores
        2. Vector: semantic similarity from FAISS index
        """
        sections: list[str] = []

        # ── Structured Memory (keyword match) ────────────

        # 1a. Similar past tasks (structured)
        similar_tasks = self.query_task_memory(task, limit=3)
        if similar_tasks:
            lines = []
            for t in similar_tasks:
                status = "success" if t.success else "failed"
                prompt_short = t.prompt[:80]
                result_short = t.result[:100]
                tools = ", ".join(t.tool_trace[:5]) if t.tool_trace else "none"
                lines.append(
                    f"- [{status}] \"{prompt_short}\" → "
                    f"tools: {tools}, result: {result_short}"
                )
            sections.append("### Similar past tasks (keyword match):\n" + "\n".join(lines))

        # 1b. Previous failures (structured)
        keywords = _extract_keywords(task)
        past_errors = self.query_error_memory(keywords=keywords, limit=3)
        if past_errors:
            lines = []
            for e in past_errors:
                fix = f" → fix: {e.fix_strategy[:80]}" if e.fix_strategy else ""
                lines.append(f"- [{e.error_type}] {e.context[:100]}{fix}")
            sections.append("### Previous failures (keyword match):\n" + "\n".join(lines))

        # 1c. Repo context (structured)
        if workspace_id:
            repo_mem = self.query_repo_memory(workspace_id)
            if repo_mem:
                sections.append(
                    f"### Repo context:\n"
                    f"- Last analysis: confidence={repo_mem.confidence}, "
                    f"{len(repo_mem.module_map)} modules\n"
                    f"- Files: {repo_mem.file_summary[:150]}"
                )

        # ── Vector Memory (semantic match) ───────────────

        # 2a. Similar past solutions (vector)
        similar_vec = self._vector.search_memory(task, top_k=3, memory_type="task")
        if similar_vec:
            lines = []
            for entry, score in similar_vec:
                if score > 0.3:  # relevance threshold
                    lines.append(f"- (sim={score:.2f}) {entry.text[:150]}")
            if lines:
                sections.append("### Similar past solutions (semantic match):\n" + "\n".join(lines))

        # 2b. Similar errors (vector)
        error_vec = self._vector.search_memory(task, top_k=2, memory_type="error")
        if error_vec:
            lines = []
            for entry, score in error_vec:
                if score > 0.3:
                    lines.append(f"- (sim={score:.2f}) {entry.text[:150]}")
            if lines:
                sections.append("### Related errors (semantic match):\n" + "\n".join(lines))

        if not sections:
            return ""

        return "## Historical Context\n" + "\n\n".join(sections)

    # ── Stats ────────────────────────────────────────────

    def stats(self) -> dict:
        """Memory statistics including vector store."""
        structured = self._store.stats()
        return {
            **structured,
            "vector_count": self._vector.count(),
        }


# ── Singleton ──────────────────────────────────────────

_memory_manager: Optional[HybridMemoryManager] = None


def get_memory_manager() -> HybridMemoryManager:
    """Get the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        from pathlib import Path
        persist_dir = Path(__file__).resolve().parent.parent.parent / "data" / "memory"
        persist_path = str(persist_dir / "memory_store.json")
        _memory_manager = HybridMemoryManager(persist_path=persist_path)
    return _memory_manager


# Backward compat alias
MemoryManager = HybridMemoryManager
