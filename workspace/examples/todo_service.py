"""一个故意包含 Bug 的 Todo Service，用于测试 Agent 的代码理解能力。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Todo:
    id: int
    title: str
    done: bool = False


class TodoService:
    def __init__(self, storage_path: str = "todos.json"):
        self._path = Path(storage_path)
        self._next_id = 1
        self._todos: list[Todo] = []
        self._load()

    def _load(self):
        if self._path.exists():
            data = json.loads(self._path.read_text())
            for item in data:
                self._todos.append(
                    Todo(id=item["id"], title=item["title"], done=item["done"])
                )
                self._next_id = max(self._next_id, item["id"] + 1)

    def _save(self):
        data = [{"id": t.id, "title": t.title, "done": t.done} for t in self._todos]
        self._path.write_text(json.dumps(data, indent=2))

    def add(self, title: str) -> Todo:
        todo = Todo(id=self._next_id, title=title)
        self._next_id += 1
        self._todos.append(todo)
        self._save()
        return todo

    def complete(self, todo_id: int) -> Optional[Todo]:
        for todo in self._todos:
            if todo.id == todo_id:
                todo.done = True  # BUG: 没有调用 _save()
                return todo
        return None

    def remove(self, todo_id: int) -> bool:
        for i, todo in enumerate(self._todos):
            if todo.id == todo_id:
                del self._todos[i]
                self._save()
                return True
        return False

    def list_all(self) -> list[Todo]:
        return self._todos.copy()

    def list_pending(self) -> list[Todo]:
        # BUG: 条件反了，返回的是已完成的
        return [t for t in self._todos if t.done]

    def list_done(self) -> list[Todo]:
        return [t for t in self._todos if t.done]

    def search(self, keyword: str) -> list[Todo]:
        return [t for t in self._todos if keyword.lower() in t.title.lower()]

    def stats(self) -> dict:
        total = len(self._todos)
        done = sum(1 for t in self._todos if t.done)
        return {
            "total": total,
            "done": done,
            "pending": total - done,
            "completion_rate": done / total if total > 0 else 0,
        }


def main():
    service = TodoService("/tmp/demo_todos.json")
    service.add("学习 FastAPI")
    service.add("实现 Agent Loop")
    service.add("编写单元测试")

    todo = service.add("部署上线")
    service.complete(todo.id)

    print("=== All Todos ===")
    for t in service.list_all():
        status = "done" if t.done else "pending"
        print(f"  [{status}] #{t.id} {t.title}")

    print(f"\nStats: {service.stats()}")
    print(f"Pending: {[t.title for t in service.list_pending()]}")
    print(f"Search 'agent': {[t.title for t in service.search('agent')]}")


if __name__ == "__main__":
    main()
