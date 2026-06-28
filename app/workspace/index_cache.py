"""index_cache.py — TTL-based cache for WorkspaceIndex.

Avoids rebuilding the index on every /api/chat request.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from app.workspace.indexer import IndexBuilder, WorkspaceIndex

logger = logging.getLogger(__name__)


class WorkspaceIndexCache:
    """TTL cache for WorkspaceIndex objects.

    Keyed by workspace root path. Entries expire after ttl_seconds.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, WorkspaceIndex]] = {}

    def get(self, workspace_root: str) -> Optional[WorkspaceIndex]:
        """Return cached index if valid, else None."""
        entry = self._cache.get(workspace_root)
        if entry is None:
            return None
        ts, index = entry
        if time.monotonic() - ts > self._ttl:
            del self._cache[workspace_root]
            logger.debug("Index cache expired for %s", workspace_root)
            return None
        logger.debug("Index cache hit for %s", workspace_root)
        return index

    def get_or_build(self, workspace_root: str) -> WorkspaceIndex:
        """Return cached index or build a new one."""
        cached = self.get(workspace_root)
        if cached is not None:
            return cached
        index = IndexBuilder().build(workspace_root)
        self._cache[workspace_root] = (time.monotonic(), index)
        logger.info("Index built and cached for %s (%d files)", workspace_root, len(index.files))
        return index

    def invalidate(self, workspace_root: str) -> None:
        """Manually invalidate cache for a workspace."""
        self._cache.pop(workspace_root, None)
        logger.debug("Index cache invalidated for %s", workspace_root)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


# Module-level singleton
_index_cache: Optional[WorkspaceIndexCache] = None


def get_index_cache() -> WorkspaceIndexCache:
    """Get the global index cache instance."""
    global _index_cache
    if _index_cache is None:
        from app.core.config import settings
        ttl = getattr(settings, "workspace_index_cache_ttl", 300)
        _index_cache = WorkspaceIndexCache(ttl_seconds=ttl)
    return _index_cache
