"""数据模型模块 — 包含多个 Bug 用于评测。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool = True
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def deactivate(self) -> None:
        """停用用户。"""
        self.active = False  # BUG: 没有记录停用时间

    def to_dict(self) -> dict:
        """转换为字典。"""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "active": self.active,
        }  # BUG: 缺少 created_at 字段


@dataclass
class Task:
    id: int
    title: str
    owner_id: int
    done: bool = False
    priority: int = 0

    def mark_done(self) -> None:
        """标记为完成。"""
        self.done = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "owner_id": self.owner_id,
            "done": self.done,
        }  # BUG: 缺少 priority 字段


class TaskManager:
    """任务管理器。"""

    def __init__(self):
        self._tasks: list[Task] = []
        self._next_id = 1

    def add(self, title: str, owner_id: int, priority: int = 0) -> Task:
        """添加新任务。"""
        task = Task(
            id=self._next_id,
            title=title,
            owner_id=owner_id,
            priority=priority,
        )
        self._next_id += 1
        self._tasks.append(task)
        return task

    def get(self, task_id: int) -> Optional[Task]:
        """获取任务。"""
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def list_by_owner(self, owner_id: int) -> list[Task]:
        """列出某用户的所有任务。"""
        return [t for t in self._tasks if t.owner_id == owner_id]

    def list_pending(self) -> list[Task]:
        """列出所有未完成任务。"""
        return [t for t in self._tasks if not t.done]

    def list_by_priority(self, min_priority: int = 0) -> list[Task]:
        """列出优先级 >= min_priority 的任务。"""
        result = [t for t in self._tasks if t.priority >= min_priority]
        return result.sort(key=lambda t: t.priority)  # BUG: sort() 返回 None，应该用 sorted()

    def delete(self, task_id: int) -> bool:
        """删除任务。"""
        for i, task in enumerate(self._tasks):
            if task.id == task_id:
                del self._tasks[i]
                return True
        return False

    def count(self) -> dict[str, int]:
        """统计任务数量。"""
        total = len(self._tasks)
        done = sum(1 for t in self._tasks if t.done)
        return {
            "total": total,
            "done": done,
            "pending": total - done,
        }
