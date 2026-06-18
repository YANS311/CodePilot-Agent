"""Tests for data_models module."""

from examples.data_models import User, Task, TaskManager


class TestUser:
    def test_deactivate(self):
        user = User(id=1, name="test", email="test@example.com")
        user.deactivate()
        assert user.active is False

    def test_to_dict(self):
        user = User(id=1, name="test", email="test@example.com")
        d = user.to_dict()
        assert d["id"] == 1
        assert d["name"] == "test"
        assert d["email"] == "test@example.com"
        assert d["active"] is True
        assert "created_at" in d


class TestTask:
    def test_mark_done(self):
        task = Task(id=1, title="test", owner_id=1)
        task.mark_done()
        assert task.done is True

    def test_to_dict(self):
        task = Task(id=1, title="test", owner_id=1, priority=3)
        d = task.to_dict()
        assert d["id"] == 1
        assert d["title"] == "test"
        assert d["priority"] == 3


class TestTaskManager:
    def test_add_and_get(self):
        tm = TaskManager()
        t = tm.add("task1", 1)
        assert tm.get(t.id) is t

    def test_list_by_priority(self):
        tm = TaskManager()
        tm.add("low", 1, priority=1)
        tm.add("high", 1, priority=5)
        tm.add("med", 1, priority=3)
        result = tm.list_by_priority(min_priority=3)
        assert len(result) == 2
        assert all(t.priority >= 3 for t in result)
        priorities = [t.priority for t in result]
        assert priorities == sorted(priorities, reverse=True)

    def test_delete(self):
        tm = TaskManager()
        t = tm.add("task1", 1)
        assert tm.delete(t.id) is True
        assert tm.get(t.id) is None
