"""embeddings.py — Local embedding model for vector memory.

Uses sentence-transformers by default (no API key needed).
Falls back gracefully if the library is not available.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Lazy-loaded model singleton
_model = None
_model_name: Optional[str] = None
_model_failed = False  # Cache failure to avoid repeated retries


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load sentence-transformers model (lazy, singleton).

    Caches failure — if the model can't be loaded (no network, missing deps),
    subsequent calls return None immediately without retrying.
    """
    global _model, _model_name, _model_failed
    if _model is not None and _model_name == model_name:
        return _model
    if _model_failed:
        return None
    try:
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Loaded embedding model: %s", model_name)
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed, vector memory disabled")
        _model_failed = True
        return None
    except Exception as e:
        logger.warning("Failed to load embedding model %s: %s", model_name, e)
        _model_failed = True
        return None


class EmbeddingModel:
    """Thin wrapper around sentence-transformers for memory embeddings.

    Usage:
        model = EmbeddingModel()
        vecs = model.encode(["text1", "text2"])
        query_vec = model.encode_one("query text")
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._dim: Optional[int] = None

    @property
    def dim(self) -> int:
        """Embedding dimension (lazy — computed on first encode)."""
        if self._dim is not None:
            return self._dim
        model = _get_model(self._model_name)
        if model is None:
            return 384  # default for all-MiniLM-L6-v2
        # Encode a dummy sentence to get dimension
        test = model.encode(["test"], show_progress_bar=False)
        self._dim = test.shape[1]
        return self._dim

    def encode(self, texts: list[str], show_progress_bar: bool = False) -> np.ndarray:
        """Encode a list of texts into vectors.

        Returns:
            np.ndarray of shape (len(texts), dim)
        """
        model = _get_model(self._model_name)
        if model is None:
            # Fallback: random vectors (for testing without model)
            return np.random.randn(len(texts), self.dim).astype(np.float32)
        return model.encode(
            texts,
            show_progress_bar=show_progress_bar,
            normalize_embeddings=True,
        ).astype(np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text into a vector."""
        return self.encode([text])[0]

    def is_available(self) -> bool:
        """Check if the embedding model is available."""
        return _get_model(self._model_name) is not None
