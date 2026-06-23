"""Stress test: multi-file bug fix — tests spanning todo_service + data_models."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from examples.todo_service import TodoService, Todo
from examples.data_models import User, Task, TaskManager


# ═══════════════════════════════════════════
# Multi-file Bug 1: TodoService.complete() 不保存
# ═══════════════════════════════════════════


class TestTodoCompletePersistence:
    def test_complete_persists(self):
        """complete() 应该持久化变更。"""
        import tempfile, json
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            svc = TodoService(path)
            todo = svc.add("test")
            svc.complete(todo.id)
            # 重新加载验证持久化
            svc2 = TodoService(path)
            loaded = svc2.get(todo.id)
            assert loaded is not None
            assert loaded.done is True
        finally:
            Path(path).unlink(missing_ok=True)


# ═══════════════════════════════════════════
# Multi-file Bug 2: TodoService.list_pending() 条件反了
# ═══════════════════════════════════════════


class TestTodoListPending:
    def test_list_pending_excludes_completed(self):
        """list_pending() 应该只返回未完成的。"""
        svc = TodoService("/tmp/stress_todos.json")
        svc._todos.clear()
        t1 = svc.add("pending task")
        t2 = svc.add("done task")
        svc.complete(t2.id)
        pending = svc.list_pending()
        ids = [t.id for t in pending]
        assert t1.id in ids
        assert t2.id not in ids


# ═══════════════════════════════════════════
# Multi-file Bug 3: User.to_dict() 缺少 created_at
# ═══════════════════════════════════════════


class TestUserToDict:
    def test_to_dict_includes_created_at(self):
        """User.to_dict() 应包含 created_at。"""
        user = User(id=1, name="Alice", email="a@b.com")
        d = user.to_dict()
        assert "created_at" in d
        assert d["created_at"] != ""


# ═══════════════════════════════════════════
# Multi-file Bug 4: Task.to_dict() 缺少 priority
# ═══════════════════════════════════════════


class TestTaskToDict:
    def test_to_dict_includes_priority(self):
        """Task.to_dict() 应包含 priority。"""
        task = Task(id=1, title="t", owner_id=1, priority=5)
        d = task.to_dict()
        assert "priority" in d
        assert d["priority"] == 5


# ═══════════════════════════════════════════
# Multi-file Bug 5: TaskManager.list_by_priority() 返回 None
# ═══════════════════════════════════════════


class TestTaskManagerListByPriority:
    def test_list_by_priority_returns_list(self):
        """list_by_priority() 应返回排序后的列表，不是 None。"""
        tm = TaskManager()
        tm.add("low", owner_id=1, priority=1)
        tm.add("high", owner_id=1, priority=5)
        tm.add("med", owner_id=1, priority=3)
        result = tm.list_by_priority(min_priority=0)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 3
        # 应按优先级升序排列
        priorities = [t.priority for t in result]
        assert priorities == sorted(priorities)
