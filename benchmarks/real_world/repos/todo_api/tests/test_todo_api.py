"""Tests for Todo API service layer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.storage import TodoStorage
from app.service import TodoService


def _make_service():
    return TodoService(TodoStorage())


# ── Create ──


class TestCreate:
    def test_create_todo(self):
        svc = _make_service()
        todo = svc.create("Buy milk")
        assert todo.title == "Buy milk"
        assert todo.done is False
        assert todo.id == 1

    def test_create_multiple(self):
        svc = _make_service()
        t1 = svc.create("Task 1")
        t2 = svc.create("Task 2")
        assert t1.id != t2.id


# ── Complete ──


class TestComplete:
    def test_complete_persists(self):
        """BUG: complete() does not persist the change."""
        svc = _make_service()
        todo = svc.create("Buy milk")
        svc.complete(todo.id)
        # After complete, listing pending should NOT include this todo
        pending = svc.list_pending()
        assert todo.id not in [t.id for t in pending]

    def test_complete_not_found(self):
        svc = _make_service()
        result = svc.complete(999)
        assert result is None


# ── List Pending ──


class TestListPending:
    def test_list_pending_excludes_completed(self):
        """BUG: list_pending() condition is inverted."""
        svc = _make_service()
        svc.create("Task 1")
        t2 = svc.create("Task 2")
        svc.complete(t2.id)
        pending = svc.list_pending()
        assert len(pending) == 1
        assert pending[0].title == "Task 1"

    def test_list_pending_empty(self):
        svc = _make_service()
        assert svc.list_pending() == []


# ── Delete ──


class TestDelete:
    def test_delete_returns_true(self):
        """BUG: delete() returns False on success."""
        svc = _make_service()
        todo = svc.create("Delete me")
        result = svc.delete(todo.id)
        assert result is True

    def test_delete_not_found(self):
        svc = _make_service()
        result = svc.delete(999)
        assert result is False

    def test_delete_removes_todo(self):
        svc = _make_service()
        todo = svc.create("Delete me")
        svc.delete(todo.id)
        assert svc.get(todo.id) is None
