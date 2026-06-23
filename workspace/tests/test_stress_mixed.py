"""Stress test: mixed instruction + partial failure recovery."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from examples.todo_service import TodoService
from examples.data_models import TaskManager


# ═══════════════════════════════════════════
# Mixed 1: TodoService — 多个 bug 需要同时修复
# ═══════════════════════════════════════════


class TestTodoServiceAllBugs:
    """验证 TodoService 的 3 个 bug 全部修复。"""

    def test_complete_persists(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            svc = TodoService(path)
            todo = svc.add("test")
            svc.complete(todo.id)
            svc2 = TodoService(path)
            assert svc2.get(todo.id).done is True
        finally:
            Path(path).unlink(missing_ok=True)

    def test_list_pending_correct(self):
        svc = TodoService("/tmp/stress_mixed.json")
        svc._todos.clear()
        t1 = svc.add("pending")
        t2 = svc.add("done")
        svc.complete(t2.id)
        pending = svc.list_pending()
        assert t1.id in [t.id for t in pending]
        assert t2.id not in [t.id for t in pending]

    def test_list_done_correct(self):
        svc = TodoService("/tmp/stress_mixed2.json")
        svc._todos.clear()
        t1 = svc.add("pending")
        t2 = svc.add("done")
        svc.complete(t2.id)
        done = svc.list_done()
        assert t2.id in [t.id for t in done]
        assert t1.id not in [t.id for t in done]


# ═══════════════════════════════════════════
# Mixed 2: TaskManager — list_by_priority 返回 None
# ═══════════════════════════════════════════


class TestTaskManagerAllBugs:
    """验证 TaskManager 的 bug 全部修复。"""

    def test_list_by_priority_returns_sorted_list(self):
        tm = TaskManager()
        tm.add("a", owner_id=1, priority=5)
        tm.add("b", owner_id=1, priority=1)
        result = tm.list_by_priority(min_priority=0)
        assert result is not None
        assert isinstance(result, list)
        priorities = [t.priority for t in result]
        assert priorities == sorted(priorities)

    def test_list_by_priority_filters(self):
        tm = TaskManager()
        tm.add("low", owner_id=1, priority=1)
        tm.add("high", owner_id=1, priority=5)
        result = tm.list_by_priority(min_priority=3)
        assert len(result) == 1
        assert result[0].priority == 5
