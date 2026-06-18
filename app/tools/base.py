from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """工具抽象基类 — 体现封装。

    定义所有工具的公共接口：name / description / parameters / run()。
    子类只需关注 run() 的业务逻辑，Registry 通过统一接口调用，实现多态。
    """

    name: str
    description: str
    # JSON Schema，描述参数结构，对齐 OpenAI function calling parameters 字段
    parameters: dict[str, Any]

    @abstractmethod
    async def run(self, *, workspace_root: str, **kwargs: Any) -> str:
        """执行工具逻辑。

        Args:
            workspace_root: 工作区绝对路径，由 Registry 在调用时注入。
            **kwargs: 工具特定参数。

        Returns:
            工具执行结果的文本输出。
        """
        ...

    def to_openai_schema(self) -> dict:
        """导出为 OpenAI function calling 格式的工具描述。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
