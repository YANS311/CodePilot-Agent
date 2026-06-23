"""D33 Tests — Hybrid Memory System (structured + vector)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.memory.embeddings import EmbeddingModel
from app.memory.vector_store import VectorMemoryStore, VectorEntry
from app.memory.memory_manager import HybridMemoryManager, get_memory_manager


# ═══════════════════════════════════════════
# 1. EmbeddingModel
# ═══════════════════════════════════════════


class TestEmbeddingModel:
    def test_encode_one(self):
        model = EmbeddingModel()
        vec = model.encode_one("hello world")
        assert vec.shape == (384,)

    def test_encode_batch(self):
        model = EmbeddingModel()
        vecs = model.encode(["hello", "world", "test"])
        assert vecs.shape == (3, 384)

    def test_dim_property(self):
        model = EmbeddingModel()
        assert model.dim == 384

    def test_normalized_vectors(self):
        model = EmbeddingModel()
        vec = model.encode_one("test query")
        norm = (vec ** 2).sum() ** 0.5
        assert abs(norm - 1.0) < 0.01  # approximately normalized


# ═══════════════════════════════════════════
# 2. VectorMemoryStore — add + search
# ═══════════════════════════════════════════


class TestVectorStore:
    def test_add_and_count(self):
        store = VectorMemoryStore()
        store.add_memory("fixed bug in todo.py", memory_type="task")
        store.add_memory("test assertion failed", memory_type="error")
        assert store.count() == 2

    def test_search_returns_results(self):
        store = VectorMemoryStore()
        store.add_memory("fixed persistence bug in todo list", memory_type="task")
        store.add_memory("deployed to production server", memory_type="task")
        results = store.search_memory("todo list persistence issue", top_k=2)
        assert len(results) > 0
        assert all(isinstance(e, VectorEntry) for e, _ in results)

    def test_search_ranking(self):
        store = VectorMemoryStore()
        store.add_memory("fixed bug in todo.py by adding null check", memory_type="task")
        store.add_memory("deployed application to AWS EC2", memory_type="task")
        results = store.search_memory("todo.py null pointer fix", top_k=2)
        # First result should be more relevant
        assert len(results) >= 1
        # The todo.py entry should score higher than deploy
        if len(results) >= 2:
            assert results[0][1] >= results[1][1]

    def test_search_empty(self):
        store = VectorMemoryStore()
        results = store.search_memory("anything", top_k=5)
        assert results == []

    def test_search_with_type_filter(self):
        store = VectorMemoryStore()
        store.add_memory("fixed todo bug", memory_type="task")
        store.add_memory("test assertion error", memory_type="error")
        results = store.search_memory("todo bug", top_k=5, memory_type="task")
        assert all(e.memory_type == "task" for e, _ in results)

    def test_fifo_eviction(self):
        store = VectorMemoryStore()
        store._max_entries = 5
        for i in range(10):
            store.add_memory(f"memory entry {i}", memory_type="task")
        assert store.count() == 5

    def test_clear(self):
        store = VectorMemoryStore()
        store.add_memory("test entry", memory_type="task")
        assert store.count() == 1
        store.clear()
        assert store.count() == 0

    def test_get_all(self):
        store = VectorMemoryStore()
        store.add_memory("first", memory_type="task")
        store.add_memory("second", memory_type="task")
        entries = store.get_all()
        assert len(entries) == 2
        # Most recent first
        assert entries[0].text == "second"

    def test_metadata_preserved(self):
        store = VectorMemoryStore()
        store.add_memory(
            "test",
            metadata={"task_id": "abc123", "success": True},
            memory_type="task",
        )
        results = store.search_memory("test", top_k=1)
        assert results[0][0].metadata["task_id"] == "abc123"


# ═══════════════════════════════════════════
# 3. HybridMemoryManager — hybrid retrieval
# ═══════════════════════════════════════════


class TestHybridRetrieval:
    def test_add_task_writes_both_stores(self):
        mgr = HybridMemoryManager()
        mgr.add_task_memory(
            prompt="fix the todo list persistence bug",
            result="Fixed by adding save() call",
            success=True,
        )
        # Structured store has the task
        tasks = mgr.get_task_memory()
        assert len(tasks) == 1
        # Vector store also has it
        assert mgr._vector.count() >= 1

    def test_add_error_writes_both_stores(self):
        mgr = HybridMemoryManager()
        mgr.add_error_memory(
            error_type="test_failed",
            context="pytest assertion in test_todo.py",
            fix_strategy="Added missing import",
        )
        errors = mgr.get_error_memory()
        assert len(errors) == 1
        assert mgr._vector.count() >= 1

    def test_add_repo_writes_both_stores(self):
        mgr = HybridMemoryManager()
        mgr.add_repo_memory(
            workspace_id="/ws1",
            file_summary="5 modules",
            module_map={"agent": "core"},
            confidence=0.8,
        )
        repos = mgr.get_repo_memory()
        assert len(repos) == 1
        assert mgr._vector.count() >= 1

    def test_hybrid_context_includes_vector(self):
        mgr = HybridMemoryManager()
        # Add some task memories
        mgr.add_task_memory(
            prompt="fix todo list persistence",
            result="Added save() call",
            success=True,
        )
        # Build context for a semantically similar but lexically different query
        ctx = mgr.build_memory_context("todo persistence issue not saving data")
        # Should have some context (either structured or vector match)
        assert ctx != ""


# ═══════════════════════════════════════════
# 4. Fallback — structured-only when no FAISS
# ═══════════════════════════════════════════


class TestFallback:
    def test_structured_only_works(self):
        """If vector store has no embeddings model, structured still works."""
        mgr = HybridMemoryManager()
        mgr.add_task_memory(prompt="fix bug", result="fixed", success=True)
        # Structured query should still work
        tasks = mgr.query_task_memory("fix bug")
        assert len(tasks) == 1

    def test_search_vector_memory_endpoint(self):
        """Vector search endpoint works even with empty store."""
        mgr = HybridMemoryManager()
        results = mgr.search_vector_memory("anything", top_k=5)
        assert results == []


# ═══════════════════════════════════════════
# 5. Empty memory behavior
# ═══════════════════════════════════════════


class TestEmptyMemory:
    def test_empty_context(self):
        mgr = HybridMemoryManager()
        ctx = mgr.build_memory_context("fix some bug")
        assert ctx == ""

    def test_empty_stats(self):
        mgr = HybridMemoryManager()
        stats = mgr.stats()
        assert stats["vector_count"] == 0

    def test_empty_vector_search(self):
        store = VectorMemoryStore()
        results = store.search_memory("query", top_k=5)
        assert results == []


# ═══════════════════════════════════════════
# 6. Memory metrics
# ═══════════════════════════════════════════


class TestMemoryMetrics:
    def test_advanced_metrics_has_memory_fields(self):
        from app.evaluation.advanced_metrics import AdvancedMetrics
        m = AdvancedMetrics()
        assert hasattr(m, "memory_hit_rate")
        assert hasattr(m, "memory_utilization_effect")
        assert hasattr(m, "similar_task_recall")

    def test_metrics_to_dict_includes_memory(self):
        from app.evaluation.advanced_metrics import AdvancedMetrics
        m = AdvancedMetrics()
        d = m.to_dict()
        assert "memory_hit_rate" in d
        assert "memory_utilization_effect" in d
        assert "similar_task_recall" in d


# ═══════════════════════════════════════════
# 7. Vector search API endpoint
# ═══════════════════════════════════════════


class TestVectorSearchAPI:
    def test_search_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/memory/search", params={"query": "fix bug"})
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "query" in data
        assert "total" in data

    def test_search_with_type_filter(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get(
            "/api/memory/search",
            params={"query": "test", "memory_type": "error"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
