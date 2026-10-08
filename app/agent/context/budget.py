"""Replaceable deterministic token estimates including wire-message fields."""

import json
from typing import Any, Protocol


class TokenEstimator(Protocol):
    def estimate_text(self, text: str) -> int: ...

    def estimate_messages(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> int: ...


class LightweightTokenEstimator:
    """UTF-8 bytes / 3, rounded up. Estimates are not model billing tokens."""

    def estimate_text(self, text: str) -> int:
        return (len(text.encode("utf-8")) + 2) // 3

    def estimate_messages(
        self, messages: list[dict[str, Any]], tools: list[dict] | None = None
    ) -> int:
        payload: dict[str, Any] = {"messages": messages}
        if tools:
            payload["tools"] = tools
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.estimate_text(serialized) + 4 * len(messages) + 2
