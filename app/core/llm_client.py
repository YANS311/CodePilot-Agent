from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """LLM 调用异常的统一类型。"""


@dataclass
class ToolCallInfo:
    """从 LLM 响应中解析出的单个 tool_call。"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """LLM 单次调用的完整响应。"""

    content: str | None = None
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class LLMClient:
    """OpenAI 兼容的异步 LLM 客户端。

    支持所有兼容 /chat/completions 端点的服务：
    - OpenAI / OpenRouter
    - DeepSeek
    - Qwen (通义千问)
    - 任何自部署 OpenAI 兼容 API

    特性：
    - 超时控制
    - 自动重试 (指数退避)
    - 统一异常处理
    """

    def __init__(self, settings: Settings) -> None:
        self._ci_mode = getattr(settings, "ci_mode", False)
        if self._ci_mode:
            from app.core.mock_llm import MockLLMProvider
            self._mock = MockLLMProvider()
            return
        self._mock = None
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._max_tokens = settings.llm_max_tokens
        self._timeout = getattr(settings, "llm_timeout_seconds", 30)
        self._max_retries = getattr(settings, "llm_max_retries", 2)
        self._retry_backoff = getattr(settings, "llm_retry_backoff_seconds", 1.0)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        """发送 Chat Completion 请求，返回完整 ChatResponse。

        Args:
            messages: OpenAI 格式的消息列表。
            tools: 可选的 function calling 工具描述列表。
            temperature: 生成温度，默认 0 以保证确定性。

        Returns:
            ChatResponse，包含 content 和 tool_calls。

        Raises:
            LLMClientError: 所有重试用尽后的统一异常。
        """
        # CI mode: use deterministic mock
        if self._ci_mode and self._mock is not None:
            return await self._mock.chat(messages, tools=tools, temperature=temperature)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        data = await self._send_request(payload)

        message = data.get("choices", [{}])[0].get("message", {})
        content = message.get("content") or None

        # 解析 tool_calls
        tool_calls: list[ToolCallInfo] = []
        for tc in message.get("tool_calls", []):
            func = tc.get("function", {})
            args_raw = func.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                ToolCallInfo(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=args,
                )
            )

        return ChatResponse(content=content, tool_calls=tool_calls, raw=data)

    async def _send_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 HTTP 请求并处理重试逻辑，返回原始 JSON。"""
        if not self._api_key:
            raise LLMClientError(
                "LLM_API_KEY 未配置。请在 .env 中设置 CODEPILOT_LLM_API_KEY"
            )

        url = f"{self._base_url}/chat/completions"
        logger.info(
            "LLM request: model=%s, tools=%d, msgs=%d",
            payload.get("model"),
            len(payload.get("tools", [])),
            len(payload.get("messages", [])),
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self._timeout, connect=10.0)
                ) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                    if resp.status_code == 429:
                        retry_after = int(resp.headers.get("Retry-After", 2))
                        logger.warning(
                            "Rate limited (429), retrying in %ds (attempt %d/%d)",
                            retry_after, attempt, self._max_retries,
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if resp.status_code >= 500:
                        logger.warning(
                            "Server error %d (attempt %d/%d)",
                            resp.status_code, attempt, self._max_retries,
                        )
                        await asyncio.sleep(self._retry_backoff * attempt)
                        continue

                    if resp.status_code >= 400:
                        body = resp.text
                        logger.error(
                            "LLM API error %d: %s", resp.status_code, body
                        )

                    resp.raise_for_status()
                    return resp.json()

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                logger.warning(
                    "Request failed: %s (attempt %d/%d)",
                    exc, attempt, self._max_retries,
                )
                if attempt < self._max_retries:
                    await asyncio.sleep(self._retry_backoff * attempt)

        raise LLMClientError(
            f"LLM 调用失败，已重试 {self._max_retries} 次: {last_exc}"
        )
