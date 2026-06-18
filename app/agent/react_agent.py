from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.prompts import SYSTEM_PROMPT
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.models.tool import AgentStep, ToolCall, ToolResult
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 检测文本中伪造的工具调用
_TOOL_DRIFT_PATTERNS = [
    re.compile(r"write_file\s*\(", re.IGNORECASE),
    re.compile(r"read_file\s*\(", re.IGNORECASE),
    re.compile(r"Action:\s*write_file", re.IGNORECASE),
    re.compile(r"<｜｜DSML｜｜invoke\s+name=\"write_file\"", re.IGNORECASE),
]

MAX_TOOL_CALLS = 5


@dataclass
class AgentRunResult:
    """Agent 单次任务的执行结果。"""

    answer: str
    tool_calls_count: int = 0
    tool_results: list[ToolResult] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)


class ReActAgent:
    """最小可运行的 ReAct Agent。

    循环流程：
    1. 将用户任务 + 对话历史发送给 LLM
    2. LLM 返回 content → 直接作为最终回答
    3. LLM 返回 tool_calls → 执行工具 → 结果追加到对话 → 回到步骤 1
    4. 达到 MAX_TOOL_CALLS 上限时强制停止
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        workspace_root: str,
        max_tool_calls: int = MAX_TOOL_CALLS,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._workspace_root = workspace_root
        self._max_tool_calls = max_tool_calls
        self._has_drift_corrected = False

    async def run(self, task: str) -> AgentRunResult:
        """执行一个编码任务，返回最终结果。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        tools_schema = self._registry.get_schemas()
        tool_results: list[ToolResult] = []
        thoughts: list[str] = []
        steps: list[AgentStep] = []
        tool_calls_count = 0

        for iteration in range(self._max_tool_calls):
            response: ChatResponse = await self._llm.chat(
                messages, tools=tools_schema if tools_schema else None
            )

            # 如果 LLM 给出了纯文本回答（无 tool_calls），检查是否有伪造工具调用
            if not response.has_tool_calls:
                answer = response.content or ""

                # Guardrail: 检测文本中伪造的工具调用
                if self._has_fake_tool_calls(answer) and not self._has_drift_corrected:
                    self._has_drift_corrected = True
                    logger.warning("Detected fake tool calls in answer, injecting correction")
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({
                        "role": "system",
                        "content": (
                            "你刚才把工具调用写进了文本，这是禁止的行为。"
                            "你必须使用真实 tool_call 调用 write_file，不允许在文本中伪造工具调用。"
                            "请立即使用 write_file tool_call 完成修改。"
                        ),
                    })
                    continue

                messages.append({"role": "assistant", "content": answer})
                return AgentRunResult(
                    answer=response.content or "",
                    tool_calls_count=tool_calls_count,
                    tool_results=tool_results,
                    messages=messages,
                    thoughts=thoughts,
                    steps=steps,
                )

            # 有 tool_calls：提取 thought 并构建 assistant 消息
            thought = response.content or ""
            if thought:
                thoughts.append(thought)

            assistant_msg = self._build_assistant_message(response)
            messages.append(assistant_msg)

            # 逐个执行 tool_call
            for tc_info in response.tool_calls:
                tool_calls_count += 1
                if tool_calls_count > self._max_tool_calls:
                    break

                logger.info(
                    "Tool call #%d: %s(%s)",
                    tool_calls_count, tc_info.name, tc_info.arguments,
                )

                tool_call = ToolCall(
                    id=tc_info.id, name=tc_info.name, arguments=tc_info.arguments
                )
                result = await self._registry.execute(
                    tool_call, self._workspace_root
                )
                tool_results.append(result)

                # 构建 AgentStep
                steps.append(AgentStep(
                    step_id=tool_calls_count,
                    thought=thought,
                    action=f"{tc_info.name}({tc_info.arguments})",
                    tool_name=tc_info.name,
                    tool_args=tc_info.arguments,
                    observation=result.output,
                    success=result.success,
                ))

                # 构造 tool role 消息追加到对话
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_info.id,
                    "content": result.output,
                })

            if tool_calls_count >= self._max_tool_calls:
                break

        # 达到上限：发一次不含 tools 的请求，让 LLM 基于已有信息总结
        final_response = await self._llm.chat(messages)
        return AgentRunResult(
            answer=final_response.content or "[达到最大工具调用次数，未能生成回答]",
            tool_calls_count=tool_calls_count,
            tool_results=tool_results,
            messages=messages,
            thoughts=thoughts,
            steps=steps,
        )

    @staticmethod
    def _has_fake_tool_calls(text: str) -> bool:
        """检测文本中是否包含伪造的工具调用。"""
        return any(p.search(text) for p in _TOOL_DRIFT_PATTERNS)

    @staticmethod
    def _build_assistant_message(response: ChatResponse) -> dict[str, Any]:
        """将 ChatResponse 转为 OpenAI 格式的 assistant 消息。"""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for tc in response.tool_calls
            ]
        return msg
