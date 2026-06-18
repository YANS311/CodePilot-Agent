"""TodoService 测试 — 用于验证 Agent 修复结果。"""

import json
import tempfile
from pathlib import Path

import pytest
from examples.todo_service import TodoService


@pytest.fixture
def service(tmp_path):
    path = tmp_path / "todos.json"
    return TodoService(storage_path=str(path))


class TestTodoService:
    def test_add(self, service):
        todo = service.add("Buy milk")
        assert todo.title == "Buy milk"
        assert todo.done is False
        assert todo.id == 1

    def test_complete(self, service):
        todo = service.add("Buy milk")
        result = service.complete(todo.id)
        assert result is not None
        assert result.done is True
        # 验证持久化：重新加载后 done 状态应保持
        service2 = TodoService(storage_path=service._path)
        todos = service2.list_all()
        assert any(t.done for t in todos)

    def test_list_pending(self, service):
        service.add("Task 1")
        t2 = service.add("Task 2")
        service.complete(t2.id)
        pending = service.list_pending()
        assert len(pending) == 1
        assert pending[0].title == "Task 1"

    def test_list_done(self, service):
        service.add("Task 1")
        t2 = service.add("Task 2")
        service.complete(t2.id)
        done = service.list_done()
        assert len(done) == 1
        assert done[0].title == "Task 2"

    def test_remove(self, service):
        todo = service.add("Buy milk")
        assert service.remove(todo.id) is True
        assert service.list_all() == []

    def test_stats(self, service):
        service.add("Task 1")
        t2 = service.add("Task 2")
        service.complete(t2.id)
        stats = service.stats()
        assert stats["total"] == 2
        assert stats["done"] == 1
        assert stats["pending"] == 1
