from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """LLM 发出的工具调用请求。

    对齐 OpenAI Function Calling 的 tool_call 结构。
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    def to_openai(self) -> dict:
        """转换为 OpenAI API 格式。"""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


class ToolResult(BaseModel):
    """工具执行后的结果。

    由 Tool.execute() 返回，追加到对话历史中供 LLM 参考。
    """

    tool_call_id: str
    name: str
    success: bool
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStep(BaseModel):
    """Agent 单步执行记录：Thought → Action → Observation。"""

    step_id: int
    thought: str = ""
    action: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    observation: str = ""
    success: bool = True
    # Stress test tracking fields
    is_retry: bool = False  # 是否为重试步骤（前一次失败后）
    retry_of: int = 0  # 重试的是哪个 step_id（0 表示不是重试）
