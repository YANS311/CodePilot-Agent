from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """OpenAI 兼容的聊天消息格式。

    对齐 OpenAI Chat Completion Message 结构：
    - role: system / user / assistant / tool
    - content: 文本内容（assistant 消息可能为 None，当存在 tool_calls 时）
    - tool_calls: assistant 发出的工具调用列表
    - tool_call_id: role=tool 时必填，关联对应的 tool_call
    - name: 可选的名称标识
    """

    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[list[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    def to_openai(self) -> dict:
        """转换为 OpenAI API 格式的 dict。"""
        msg: dict = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls is not None:
            msg["tool_calls"] = [tc.to_openai() for tc in self.tool_calls]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


# ChatMessage 内部引用 ToolCall，延迟导入在 model_rebuild 中处理
from app.models.tool import ToolCall  # noqa: E402

ChatMessage.model_rebuild()
