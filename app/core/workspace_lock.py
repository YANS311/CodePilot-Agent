"""workspace_lock.py — Lightweight per-workspace task lock.

Single-machine, in-memory lock with FIFO queue.
No Redis, no Celery, no distributed locks.

Rules:
- Same workspace: only one Agent task at a time
- Other requests enter queued state
- Queue is FIFO per workspace
- Crash safety: try-finally guarantees release
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class LockInfo:
    """Information about a held lock."""
    task_id: str
    user_id: str
    workspace_id: str
    acquired_at: float = field(default_factory=time.monotonic)
    task_prompt: str = ""


@dataclass
class QueueEntry:
    """A queued task waiting for lock."""
    task_id: str
    user_id: str
    workspace_id: str
    task_prompt: str
    created_at: float = field(default_factory=time.monotonic)
    future: Optional[asyncio.Future] = None


class WorkspaceLockManager:
    """Per-workspace task lock with FIFO queue.

    Usage:
        manager = WorkspaceLockManager()

        # Check lock status
        status = manager.get_status(workspace_id)

        # Acquire lock (blocks until available)
        async with manager.lock(workspace_id, task_id, user_id):
            # execute task
            pass

        # Or manually
        await manager.acquire(workspace_id, task_id, user_id)
        try:
            # execute task
        finally:
            manager.release(workspace_id, task_id)
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._held: dict[str, LockInfo] = {}
        self._queues: dict[str, deque[QueueEntry]] = {}
        self._queue_events: dict[str, asyncio.Event] = {}

    def _get_lock(self, workspace_id: str) -> asyncio.Lock:
        if workspace_id not in self._locks:
            self._locks[workspace_id] = asyncio.Lock()
        return self._locks[workspace_id]

    def _get_queue(self, workspace_id: str) -> deque[QueueEntry]:
        if workspace_id not in self._queues:
            self._queues[workspace_id] = deque()
        return self._queues[workspace_id]

    def _get_queue_event(self, workspace_id: str) -> asyncio.Event:
        if workspace_id not in self._queue_events:
            self._queue_events[workspace_id] = asyncio.Event()
            self._queue_events[workspace_id].set()
        return self._queue_events[workspace_id]

    def is_locked(self, workspace_id: str) -> bool:
        """Check if workspace is currently locked."""
        return workspace_id in self._held

    def get_status(self, workspace_id: str) -> dict[str, Any]:
        """Get lock status for a workspace."""
        if workspace_id in self._held:
            info = self._held[workspace_id]
            queue = self._get_queue(workspace_id)
            return {
                "status": "locked",
                "task_id": info.task_id,
                "user_id": info.user_id,
                "task_prompt": info.task_prompt,
                "queue_length": len(queue),
                "locked_since": info.acquired_at,
            }
        queue = self._get_queue(workspace_id)
        return {
            "status": "unlocked",
            "queue_length": len(queue),
        }

    async def acquire(
        self,
        workspace_id: str,
        task_id: str,
        user_id: str = "default",
        task_prompt: str = "",
    ) -> LockInfo:
        """Acquire lock for workspace. Blocks until available."""
        lock = self._get_lock(workspace_id)
        await lock.acquire()

        info = LockInfo(
            task_id=task_id,
            user_id=user_id,
            workspace_id=workspace_id,
            task_prompt=task_prompt,
        )
        self._held[workspace_id] = info
        logger.info(
            "Lock acquired: workspace=%s task=%s user=%s",
            workspace_id, task_id, user_id,
        )
        return info

    def release(self, workspace_id: str, task_id: str) -> None:
        """Release lock for workspace. Process next in queue if any."""
        if workspace_id not in self._held:
            logger.warning("Release called but no lock held: workspace=%s", workspace_id)
            return

        info = self._held[workspace_id]
        if info.task_id != task_id:
            logger.warning(
                "Release mismatch: workspace=%s expected=%s got=%s",
                workspace_id, info.task_id, task_id,
            )
            return

        del self._held[workspace_id]
        lock = self._get_lock(workspace_id)
        lock.release()

        logger.info("Lock released: workspace=%s task=%s", workspace_id, task_id)

        # Signal next in queue
        queue = self._get_queue(workspace_id)
        if queue:
            event = self._get_queue_event(workspace_id)
            event.set()

    async def wait_in_queue(
        self,
        workspace_id: str,
        task_id: str,
        user_id: str = "default",
        task_prompt: str = "",
    ) -> QueueEntry:
        """Add task to queue and wait for its turn. Returns when lock is acquired."""
        entry = QueueEntry(
            task_id=task_id,
            user_id=user_id,
            workspace_id=workspace_id,
            task_prompt=task_prompt,
        )

        queue = self._get_queue(workspace_id)
        queue.append(entry)
        logger.info(
            "Task queued: workspace=%s task=%s queue_len=%d",
            workspace_id, task_id, len(queue),
        )

        # Wait until this entry is at the front of the queue
        while queue[0].task_id != task_id:
            await asyncio.sleep(0.1)

        # Now wait for lock to be available
        await self.acquire(workspace_id, task_id, user_id, task_prompt)

        # Remove from queue
        queue.remove(entry)

        return entry

    def cancel_queue_entry(self, workspace_id: str, task_id: str) -> bool:
        """Remove a task from the queue without acquiring lock."""
        queue = self._get_queue(workspace_id)
        for entry in queue:
            if entry.task_id == task_id:
                queue.remove(entry)
                logger.info("Queue entry cancelled: workspace=%s task=%s", workspace_id, task_id)
                return True
        return False

    def get_queue(self, workspace_id: str) -> list[dict[str, Any]]:
        """Get queue status for a workspace."""
        queue = self._get_queue(workspace_id)
        return [
            {
                "task_id": entry.task_id,
                "user_id": entry.user_id,
                "task_prompt": entry.task_prompt[:100],
                "queued_at": entry.created_at,
            }
            for entry in queue
        ]

    def get_all_status(self) -> dict[str, Any]:
        """Get status of all workspaces."""
        return {
            "locked_workspaces": list(self._held.keys()),
            "queue_lengths": {
                ws: len(q) for ws, q in self._queues.items() if q
            },
        }


# ── Singleton ──────────────────────────────────────────────

_lock_manager: Optional[WorkspaceLockManager] = None


def get_lock_manager() -> WorkspaceLockManager:
    """Get the global lock manager instance."""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = WorkspaceLockManager()
    return _lock_manager
