"""mock_llm.py — Deterministic mock LLM for CI.

Returns fixed responses based on message content.
No API calls, no network, no secrets required.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.core.llm_client import ChatResponse, ToolCallInfo

logger = logging.getLogger(__name__)


class MockLLMProvider:
    """Deterministic mock LLM for CI environments.

    Returns predictable responses without calling any external API.
    Used when CODEPILOT_CI_MODE=true.
    """

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        temperature: float = 0.0,
    ) -> ChatResponse:
        """Return a deterministic response.

        If tools are provided, returns a tool_call for the first tool.
        Otherwise returns a generic text response.
        """
        if tools and len(tools) > 0:
            return self._tool_call_response(messages, tools)
        return self._text_response(messages)

    def _tool_call_response(
        self, messages: list[dict[str, Any]], tools: list[dict]
    ) -> ChatResponse:
        """Generate a deterministic tool call."""
        tool = tools[0]
        func = tool.get("function", {})
        tool_name = func.get("name", "read_file")

        # Build deterministic arguments based on tool name
        args = self._default_args(tool_name, messages)
        tc_id = f"mock_{hashlib.md5(tool_name.encode()).hexdigest()[:8]}"

        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCallInfo(id=tc_id, name=tool_name, arguments=args)
            ],
            raw={"mock": True},
        )

    def _text_response(self, messages: list[dict[str, Any]]) -> ChatResponse:
        """Generate a deterministic text response."""
        # Use last user message to produce a stable response
        last_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_msg = m.get("content", "")
                break

        response = f"Analysis complete. Based on the code review, I have identified the relevant changes. [mock response for: {last_msg[:50]}]"
        return ChatResponse(content=response, tool_calls=[], raw={"mock": True})

    def _default_args(self, tool_name: str, messages: list[dict[str, Any]]) -> dict:
        """Generate deterministic tool arguments."""
        if tool_name == "read_file":
            return {"path": "examples/buggy_calculator.py"}
        if tool_name == "search_code":
            return {"query": "def"}
        if tool_name == "write_file":
            return {"path": "examples/buggy_calculator.py", "content": "# fixed"}
        if tool_name == "run_tests":
            return {"target": "tests/"}
        if tool_name == "git_diff":
            return {}
        if tool_name == "git_status":
            return {}
        return {}
