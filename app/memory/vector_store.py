"""vector_store.py — FAISS-based vector memory store.

Stores text + metadata, supports semantic search via embeddings.
Falls back to brute-force cosine similarity if FAISS is unavailable.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from app.memory.embeddings import EmbeddingModel

logger = logging.getLogger(__name__)


@dataclass
class VectorEntry:
    """A single entry in the vector store."""
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # memory_type: "task" | "error" | "repo"
    memory_type: str = ""
    created_at: float = field(default_factory=time.time)


class VectorMemoryStore:
    """FAISS-backed vector memory store.

    - add_memory(text, metadata) → stores text + embedding
    - search_memory(query, top_k) → returns top-k similar entries
    - Graceful fallback: if FAISS unavailable, uses brute-force cosine

    Usage:
        store = VectorMemoryStore()
        store.add_memory("fixed bug in todo.py", {"type": "task", "success": True})
        results = store.search_memory("todo list persistence issue", top_k=3)
    """

    def __init__(self, embedding_model: Optional[EmbeddingModel] = None) -> None:
        self._embedder = embedding_model or EmbeddingModel()
        self._entries: list[VectorEntry] = []
        self._vectors: Optional[np.ndarray] = None  # (N, dim) matrix
        self._index = None  # FAISS index
        self._use_faiss = False
        self._max_entries: int = 500

        # Try to init FAISS
        try:
            import faiss
            self._use_faiss = True
            logger.info("FAISS available, using FAISS index")
        except ImportError:
            logger.info("FAISS not available, using brute-force cosine similarity")

    def _rebuild_index(self) -> None:
        """Rebuild the FAISS index from all entries."""
        if not self._entries:
            self._vectors = None
            self._index = None
            return

        texts = [e.text for e in self._entries]
        self._vectors = self._embedder.encode(texts)

        if self._use_faiss:
            try:
                import faiss
                dim = self._vectors.shape[1]
                self._index = faiss.IndexFlatIP(dim)  # Inner product (cosine for normalized)
                self._index.add(self._vectors)
            except Exception as e:
                logger.warning("FAISS index build failed: %s, falling back to brute-force", e)
                self._use_faiss = False

    def add_memory(
        self,
        text: str,
        metadata: Optional[dict[str, Any]] = None,
        memory_type: str = "",
    ) -> VectorEntry:
        """Add a memory entry to the vector store.

        Args:
            text: The text content to embed and store.
            metadata: Optional metadata dict (e.g., task_id, error_type).
            memory_type: Category — "task", "error", or "repo".

        Returns:
            The created VectorEntry.
        """
        entry = VectorEntry(
            text=text,
            metadata=metadata or {},
            memory_type=memory_type,
        )
        self._entries.append(entry)

        # Evict oldest if over limit
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        # Rebuild index (incremental not worth the complexity for <500 entries)
        self._rebuild_index()

        logger.debug("Vector memory added: %s (type=%s)", entry.entry_id, memory_type)
        return entry

    def search_memory(
        self,
        query: str,
        top_k: int = 5,
        memory_type: Optional[str] = None,
    ) -> list[tuple[VectorEntry, float]]:
        """Search for similar memories by semantic similarity.

        Args:
            query: The search query text.
            top_k: Number of results to return.
            memory_type: Optional filter — "task", "error", or "repo".

        Returns:
            List of (VectorEntry, score) tuples, sorted by similarity descending.
        """
        if not self._entries or self._vectors is None:
            return []

        query_vec = self._embedder.encode_one(query)

        if self._use_faiss and self._index is not None:
            results = self._search_faiss(query_vec, top_k * 2)  # over-fetch for filtering
        else:
            results = self._search_bruteforce(query_vec, top_k * 2)

        # Apply memory_type filter
        if memory_type:
            results = [(e, s) for e, s in results if e.memory_type == memory_type]

        return results[:top_k]

    def _search_faiss(
        self, query_vec: np.ndarray, k: int
    ) -> list[tuple[VectorEntry, float]]:
        """Search using FAISS index."""
        try:
            k = min(k, len(self._entries))
            query_vec = query_vec.reshape(1, -1).astype(np.float32)
            scores, indices = self._index.search(query_vec, k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._entries):
                    continue
                results.append((self._entries[idx], float(score)))
            return results
        except Exception as e:
            logger.warning("FAISS search failed: %s, falling back", e)
            return self._search_bruteforce(query_vec, k)

    def _search_bruteforce(
        self, query_vec: np.ndarray, k: int
    ) -> list[tuple[VectorEntry, float]]:
        """Brute-force cosine similarity search."""
        if self._vectors is None or len(self._vectors) == 0:
            return []

        # Cosine similarity (vectors are normalized)
        sims = np.dot(self._vectors, query_vec)
        k = min(k, len(sims))
        top_indices = np.argsort(sims)[::-1][:k]

        results = []
        for idx in top_indices:
            results.append((self._entries[int(idx)], float(sims[idx])))
        return results

    def count(self) -> int:
        """Number of entries in the store."""
        return len(self._entries)

    def get_all(self, limit: int = 100) -> list[VectorEntry]:
        """Get all entries (most recent first)."""
        return list(reversed(self._entries[-limit:]))

    def clear(self) -> None:
        """Clear all entries and rebuild empty index."""
        self._entries.clear()
        self._vectors = None
        self._index = None
