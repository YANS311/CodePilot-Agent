"""Todo business logic service.

BUG 1: complete() does not persist the change (missing storage.save)
BUG 2: list_pending() condition is inverted (returns completed instead of pending)
BUG 3: delete() returns False on success instead of True
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models import Todo
from app.storage import TodoStorage


class TodoService:
    def __init__(self, storage: TodoStorage) -> None:
        self._storage = storage

    def create(self, title: str) -> Todo:
        return self._storage.add(title)

    def get(self, todo_id: int) -> Optional[Todo]:
        return self._storage.get(todo_id)

    def complete(self, todo_id: int) -> Optional[Todo]:
        """Mark a todo as completed.

        BUG: Does not persist the change back to storage.
        """
        todo = self._storage.get(todo_id)
        if todo is None:
            return None
        todo.done = True
        todo.completed_at = datetime.now().isoformat()
        # BUG: Missing self._storage.save(todo)
        return todo

    def list_pending(self) -> list[Todo]:
        """List all pending (not completed) todos.

        BUG: Condition is inverted — returns completed instead of pending.
        """
        # BUG: Should be "not t.done" but uses "t.done"
        return [t for t in self._storage.list_all() if t.done]

    def delete(self, todo_id: int) -> bool:
        """Delete a todo by ID.

        BUG: Returns False on success instead of True.
        """
        result = self._storage.delete(todo_id)
        # BUG: Should return result, but returns inverted value
        return not result
