"""error_event.py — Structured error event for agent failure observability.

Every exception in the agent pipeline is recorded as an AgentErrorEvent,
making failures visible to the eval system and debug tooling.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AgentErrorEvent:
    """Structured error record for agent execution failures.

    Attributes:
        module: Where the error occurred (e.g., "react_agent", "llm_client", "tool").
        error_type: Exception class name (e.g., "LLMClientError", "TimeoutError").
        context: Human-readable description of what was happening.
        tool_name: Which tool was involved (if applicable).
        recovery_action: What recovery was attempted (e.g., "retry", "fallback", "skip").
        timestamp: When the error occurred.
    """

    module: str
    error_type: str
    context: str
    tool_name: str = ""
    recovery_action: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "module": self.module,
            "error_type": self.error_type,
            "context": self.context,
            "tool_name": self.tool_name,
            "recovery_action": self.recovery_action,
            "timestamp": self.timestamp,
        }
