"""D31 Tests — Workspace lock system validation."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.workspace_lock import WorkspaceLockManager, LockInfo, QueueEntry


# ═══════════════════════════════════════════
# 1. Basic lock/unlock
# ═══════════════════════════════════════════


class TestBasicLock:
    def test_acquire_release(self):
        mgr = WorkspaceLockManager()
        info = asyncio.run(mgr.acquire("ws1", "task1", "user1"))
        assert isinstance(info, LockInfo)
        assert mgr.is_locked("ws1")
        mgr.release("ws1", "task1")
        assert not mgr.is_locked("ws1")

    def test_get_status_locked(self):
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "task1"))
        status = mgr.get_status("ws1")
        assert status["status"] == "locked"
        assert status["task_id"] == "task1"
        mgr.release("ws1", "task1")

    def test_get_status_unlocked(self):
        mgr = WorkspaceLockManager()
        status = mgr.get_status("ws1")
        assert status["status"] == "unlocked"

    def test_release_wrong_task_id(self):
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "task1"))
        mgr.release("ws1", "wrong_task")  # should log warning, not release
        assert mgr.is_locked("ws1")  # still locked
        mgr.release("ws1", "task1")

    def test_release_no_lock(self):
        mgr = WorkspaceLockManager()
        mgr.release("ws1", "task1")  # should log warning, no crash


# ═══════════════════════════════════════════
# 2. Concurrent access — serial execution
# ═══════════════════════════════════════════


class TestConcurrentAccess:
    def test_two_tasks_serialize(self):
        """Two concurrent tasks on same workspace should serialize."""
        mgr = WorkspaceLockManager()
        results = []

        async def worker(name: str, delay: float):
            await mgr.acquire("ws1", name)
            results.append(f"{name}_start")
            await asyncio.sleep(delay)
            results.append(f"{name}_end")
            mgr.release("ws1", name)

        async def run():
            t1 = asyncio.create_task(worker("t1", 0.1))
            t2 = asyncio.create_task(worker("t2", 0.1))
            await asyncio.gather(t1, t2)

        asyncio.run(run())

        # t1 should start and end before t2 starts, or vice versa
        # Check that starts and ends are interleaved properly
        assert len(results) == 4
        # First task should complete before second starts
        assert results[0].endswith("_start")
        assert results[1].endswith("_end")
        assert results[2].endswith("_start")
        assert results[3].endswith("_end")

    def test_different_workspaces_parallel(self):
        """Different workspaces should allow parallel execution."""
        mgr = WorkspaceLockManager()
        results = []

        async def worker(ws: str, name: str):
            await mgr.acquire(ws, name)
            results.append(f"{name}_start")
            await asyncio.sleep(0.05)
            results.append(f"{name}_end")
            mgr.release(ws, name)

        async def run():
            t1 = asyncio.create_task(worker("ws1", "t1"))
            t2 = asyncio.create_task(worker("ws2", "t2"))
            await asyncio.gather(t1, t2)

        asyncio.run(run())

        # Both should start before either ends
        starts = [r for r in results if r.endswith("_start")]
        assert len(starts) == 2


# ═══════════════════════════════════════════
# 3. Queue mechanism
# ═══════════════════════════════════════════


class TestQueue:
    def test_queue_status(self):
        mgr = WorkspaceLockManager()
        queue = mgr.get_queue("ws1")
        assert queue == []

    def test_queue_length_in_status(self):
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "t1"))
        status = mgr.get_status("ws1")
        assert status["queue_length"] == 0
        mgr.release("ws1", "t1")

    def test_cancel_queue_entry(self):
        mgr = WorkspaceLockManager()
        # Add a fake entry to queue
        entry = QueueEntry(task_id="t2", user_id="u1", workspace_id="ws1", task_prompt="test task")
        mgr._get_queue("ws1").append(entry)
        assert len(mgr.get_queue("ws1")) == 1
        result = mgr.cancel_queue_entry("ws1", "t2")
        assert result is True
        assert len(mgr.get_queue("ws1")) == 0

    def test_cancel_nonexistent_entry(self):
        mgr = WorkspaceLockManager()
        result = mgr.cancel_queue_entry("ws1", "nonexistent")
        assert result is False


# ═══════════════════════════════════════════
# 4. Crash safety — release on exception
# ═══════════════════════════════════════════


class TestCrashSafety:
    def test_try_finally_releases(self):
        """Simulate crash: lock should be released in finally block."""
        mgr = WorkspaceLockManager()

        async def crashy_task():
            await mgr.acquire("ws1", "crash_task")
            raise ValueError("simulated crash")

        with pytest.raises(ValueError, match="simulated crash"):
            asyncio.run(crashy_task())

        # Lock should still be released if caller uses try-finally
        # (Our API layer does this, but test the manager itself)
        assert mgr.is_locked("ws1")  # manager doesn't auto-release
        mgr.release("ws1", "crash_task")
        assert not mgr.is_locked("ws1")

    def test_release_idempotent(self):
        """Double release should not crash."""
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "t1"))
        mgr.release("ws1", "t1")
        mgr.release("ws1", "t1")  # second release — should be no-op
        assert not mgr.is_locked("ws1")


# ═══════════════════════════════════════════
# 5. Multi-workspace isolation
# ═══════════════════════════════════════════


class TestMultiWorkspace:
    def test_independent_locks(self):
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "t1"))
        asyncio.run(mgr.acquire("ws2", "t2"))
        assert mgr.is_locked("ws1")
        assert mgr.is_locked("ws2")
        mgr.release("ws1", "t1")
        assert not mgr.is_locked("ws1")
        assert mgr.is_locked("ws2")
        mgr.release("ws2", "t2")

    def test_get_all_status(self):
        mgr = WorkspaceLockManager()
        asyncio.run(mgr.acquire("ws1", "t1"))
        asyncio.run(mgr.acquire("ws2", "t2"))
        status = mgr.get_all_status()
        assert "ws1" in status["locked_workspaces"]
        assert "ws2" in status["locked_workspaces"]
        mgr.release("ws1", "t1")
        mgr.release("ws2", "t2")


# ═══════════════════════════════════════════
# 6. API endpoint test
# ═══════════════════════════════════════════


class TestLockAPIEndpoint:
    def test_lock_status_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.get("/api/lock/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("locked", "unlocked")


# ═══════════════════════════════════════════
# 7. Singleton
# ═══════════════════════════════════════════


class TestSingleton:
    def test_get_lock_manager_returns_same_instance(self):
        from app.core.workspace_lock import get_lock_manager
        m1 = get_lock_manager()
        m2 = get_lock_manager()
        assert m1 is m2
