from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentTask(BaseModel):
    """用户提交的编码任务。"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    prompt: str
    workspace_path: str
    model: str = "gpt-4o"
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    answer: Optional[str] = None


class TaskRequest(BaseModel):
    """API 请求体。"""

    prompt: str
    workspace_path: str
    model: str = "gpt-4o"


class TaskResponse(BaseModel):
    """API 响应体。"""

    task_id: str
    status: TaskStatus
    answer: Optional[str] = None
