"""In-memory todo storage."""

from __future__ import annotations

from typing import Optional
from app.models import Todo


class TodoStorage:
    def __init__(self) -> None:
        self._todos: dict[int, Todo] = {}
        self._next_id = 1

    def add(self, title: str) -> Todo:
        todo = Todo(id=self._next_id, title=title)
        self._todos[todo.id] = todo
        self._next_id += 1
        return todo

    def get(self, todo_id: int) -> Optional[Todo]:
        return self._todos.get(todo_id)

    def list_all(self) -> list[Todo]:
        return list(self._todos.values())

    def list_pending(self) -> list[Todo]:
        return [t for t in self._todos.values() if not t.done]

    def list_completed(self) -> list[Todo]:
        return [t for t in self._todos.values() if t.done]

    def delete(self, todo_id: int) -> bool:
        if todo_id in self._todos:
            del self._todos[todo_id]
            return True
        return False

    def save(self, todo: Todo) -> None:
        """Persist a todo back to storage."""
        self._todos[todo.id] = todo
