"""D32 Tests — Agent memory layer validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.memory.memory_store import (
    ErrorMemory,
    InMemoryStore,
    RepoMemory,
    TaskMemory,
)
from app.memory.memory_manager import MemoryManager, get_memory_manager, _extract_keywords


# ═══════════════════════════════════════════
# 1. Task Memory — add + query by keywords
# ═══════════════════════════════════════════


class TestTaskMemory:
    def test_add_and_query(self):
        mgr = MemoryManager()
        mgr.add_task_memory(
            prompt="fix the bug in todo.py line 42",
            result="Fixed by adding null check",
            success=True,
            tool_calls_count=3,
            tool_trace=["read_file", "search_code", "write_file"],
            workspace_id="/ws1",
            duration_ms=1500,
        )
        results = mgr.query_task_memory("fix bug in todo.py")
        assert len(results) >= 1
        assert results[0].success is True
        assert "fix" in results[0].prompt.lower()

    def test_query_no_match(self):
        mgr = MemoryManager()
        mgr.add_task_memory(
            prompt="fix the bug in todo.py",
            result="Fixed",
            success=True,
        )
        results = mgr.query_task_memory("deploy to production server")
        assert len(results) == 0

    def test_multiple_tasks_ordering(self):
        mgr = MemoryManager()
        mgr.add_task_memory(prompt="task one", result="r1", success=True)
        mgr.add_task_memory(prompt="task two", result="r2", success=False)
        mgr.add_task_memory(prompt="task three", result="r3", success=True)
        tasks = mgr.get_task_memory(limit=10)
        assert len(tasks) == 3
        # Most recent first
        assert tasks[0].prompt == "task three"


# ═══════════════════════════════════════════
# 2. Error Memory — add + query by type
# ═══════════════════════════════════════════


class TestErrorMemory:
    def test_add_and_query_by_type(self):
        mgr = MemoryManager()
        mgr.add_error_memory(
            error_type="test_failed",
            context="pytest assertion error in test_todo.py",
            fix_strategy="Fixed missing return statement",
            workspace_id="/ws1",
        )
        results = mgr.query_error_memory(error_type="test_failed")
        assert len(results) == 1
        assert results[0].error_type == "test_failed"

    def test_query_by_keywords(self):
        mgr = MemoryManager()
        mgr.add_error_memory(
            error_type="no_code_change",
            context="Agent claimed fix but did not modify files",
            fix_strategy="Inject completion chain correction",
        )
        results = mgr.query_error_memory(keywords=["completion", "files"])
        assert len(results) >= 1

    def test_query_no_match(self):
        mgr = MemoryManager()
        mgr.add_error_memory(error_type="test_failed", context="assertion error")
        results = mgr.query_error_memory(error_type="budget_exhausted")
        assert len(results) == 0


# ═══════════════════════════════════════════
# 3. Repo Memory — add + query by workspace_id
# ═══════════════════════════════════════════


class TestRepoMemory:
    def test_add_and_query(self):
        mgr = MemoryManager()
        mgr.add_repo_memory(
            workspace_id="/ws1",
            file_summary="5 modules, 3 flow steps",
            module_map={"react_agent": "core agent loop", "tools": "tool implementations"},
            analysis_result="AI coding agent with ReAct pattern",
            confidence=0.85,
        )
        repo = mgr.query_repo_memory("/ws1")
        assert repo is not None
        assert repo.confidence == 0.85
        assert "react_agent" in repo.module_map

    def test_query_nonexistent(self):
        mgr = MemoryManager()
        repo = mgr.query_repo_memory("/nonexistent")
        assert repo is None

    def test_latest_repo_memory(self):
        mgr = MemoryManager()
        mgr.add_repo_memory(workspace_id="/ws1", file_summary="v1", confidence=0.5)
        mgr.add_repo_memory(workspace_id="/ws1", file_summary="v2", confidence=0.9)
        repo = mgr.query_repo_memory("/ws1")
        assert repo is not None
        assert repo.confidence == 0.9  # latest wins


# ═══════════════════════════════════════════
# 4. build_memory_context — with history
# ═══════════════════════════════════════════


class TestBuildMemoryContext:
    def test_with_history(self):
        mgr = MemoryManager()
        mgr.add_task_memory(
            prompt="fix the todo list persistence bug",
            result="Fixed by adding save call",
            success=True,
            tool_trace=["read_file", "write_file"],
        )
        mgr.add_error_memory(
            error_type="test_failed",
            context="test_todo_save failed",
            fix_strategy="Added missing import",
        )
        ctx = mgr.build_memory_context("fix todo list persistence issue")
        assert "Historical Context" in ctx
        assert "Similar past tasks" in ctx

    def test_empty_history(self):
        mgr = MemoryManager()
        ctx = mgr.build_memory_context("fix some bug")
        assert ctx == ""

    def test_with_repo_memory(self):
        mgr = MemoryManager()
        mgr.add_repo_memory(
            workspace_id="/ws1",
            file_summary="3 modules",
            module_map={"agent": "core"},
            confidence=0.7,
        )
        ctx = mgr.build_memory_context("analyze project", workspace_id="/ws1")
        assert "Repo context" in ctx


# ═══════════════════════════════════════════
# 5. InMemoryStore — FIFO eviction
# ═══════════════════════════════════════════


class TestFIFOEviction:
    def test_task_eviction(self):
        store = InMemoryStore()
        store._max_tasks = 5
        for i in range(10):
            store.add_task(TaskMemory(prompt=f"task_{i}"))
        tasks = store.get_tasks(limit=100)
        assert len(tasks) == 5
        # Oldest evicted — most recent kept
        prompts = [t.prompt for t in tasks]
        assert "task_9" in prompts
        assert "task_0" not in prompts

    def test_error_eviction(self):
        store = InMemoryStore()
        store._max_errors = 3
        for i in range(5):
            store.add_error(ErrorMemory(error_type=f"type_{i}"))
        errors = store.get_errors(limit=100)
        assert len(errors) == 3

    def test_repo_eviction(self):
        store = InMemoryStore()
        store._max_repos = 2
        for i in range(4):
            store.add_repo(RepoMemory(workspace_id=f"/ws{i}"))
        repos = store.get_repos(limit=100)
        assert len(repos) == 2


# ═══════════════════════════════════════════
# 6. MemoryManager singleton
# ═══════════════════════════════════════════


class TestSingleton:
    def test_get_memory_manager_returns_same_instance(self):
        m1 = get_memory_manager()
        m2 = get_memory_manager()
        assert m1 is m2


# ═══════════════════════════════════════════
# 7. Keyword extraction
# ═══════════════════════════════════════════


class TestKeywordExtraction:
    def test_basic_keywords(self):
        kws = _extract_keywords("fix the bug in todo.py line 42")
        assert "fix" in kws
        assert "bug" in kws
        assert "todo" in kws  # todo.py splits on non-alphanumeric

    def test_stop_words_removed(self):
        kws = _extract_keywords("the quick brown fox jumps over the lazy dog")
        assert "the" not in kws
        assert "over" not in kws
        assert "quick" in kws
        assert "brown" in kws

    def test_chinese_stop_words(self):
        kws = _extract_keywords("请帮我修复 todo.py 的 bug")
        assert "请" not in kws
        assert "帮" not in kws
        assert "bug" in kws or "todo.py" in kws

    def test_max_keywords(self):
        long_prompt = " ".join([f"word{i}" for i in range(20)])
        kws = _extract_keywords(long_prompt)
        assert len(kws) <= 10


# ═══════════════════════════════════════════
# 8. Stats
# ═══════════════════════════════════════════


class TestStats:
    def test_empty_stats(self):
        mgr = MemoryManager()
        stats = mgr.stats()
        assert stats["task_count"] == 0
        assert stats["error_count"] == 0
        assert stats["repo_count"] == 0

    def test_populated_stats(self):
        mgr = MemoryManager()
        mgr.add_task_memory(prompt="t1", result="r1", success=True)
        mgr.add_error_memory(error_type="e1", context="c1")
        mgr.add_repo_memory(workspace_id="/ws1", file_summary="f1")
        stats = mgr.stats()
        assert stats["task_count"] == 1
        assert stats["error_count"] == 1
        assert stats["repo_count"] == 1


# ═══════════════════════════════════════════
# 9. Memory API endpoint
# ═══════════════════════════════════════════


class TestMemoryAPI:
    def test_get_memory_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        data = resp.json()
        assert "stats" in data
        assert "tasks" in data
        assert "errors" in data
        assert "repos" in data

    def test_query_memory_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/memory/query", params={"task_prompt": "fix bug"})
        assert resp.status_code == 200
        data = resp.json()
        assert "similar_tasks" in data
        assert "similar_errors" in data
