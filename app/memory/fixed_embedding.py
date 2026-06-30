"""fixed_embedding.py — Deterministic embedding model for CI.

Uses SHA-256 hashing to produce repeatable vectors without
any external dependency (no sentence-transformers, no network).
"""

from __future__ import annotations

import hashlib
import numpy as np


class FixedEmbeddingModel:
    """Deterministic hash-based embedding for CI environments.

    Produces the same vector for the same input text every time.
    No model download, no GPU, no network required.
    """

    def __init__(self, dim: int = 384) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str], **kwargs) -> np.ndarray:
        """Encode texts into deterministic vectors via SHA-256 hashing."""
        vecs = [self._text_to_vec(t) for t in texts]
        return np.array(vecs, dtype=np.float32)

    def encode_one(self, text: str) -> np.ndarray:
        """Encode a single text into a vector."""
        return self._text_to_vec(text)

    def is_available(self) -> bool:
        return True

    def _text_to_vec(self, text: str) -> np.ndarray:
        """Convert text to a deterministic unit vector."""
        vec = np.zeros(self._dim, dtype=np.float32)
        # Fill dim floats by hashing text + index
        for i in range(self._dim):
            h = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
            # Use first 4 bytes as float seed, normalize to [-1, 1]
            val = int.from_bytes(h[:4], "little") / (2**32) * 2 - 1
            vec[i] = val
        # L2 normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec
