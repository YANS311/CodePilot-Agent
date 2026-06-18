from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING_TOOL = "executing_tool"
    RESPONDING = "responding"
    ERROR = "error"
    DONE = "done"


class AgentState(BaseModel):
    """Agent 运行时状态。

    每次 LLM 调用前由 AgentLoop 读取，执行过程中更新。
    序列化后可用于 SSE 推送或持久化。
    """

    task_id: str
    status: AgentStatus = AgentStatus.IDLE
    iteration: int = 0
    max_iterations: int = 20
    workspace_path: str
    accumulated_cost: float = 0.0
