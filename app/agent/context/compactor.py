"""Deterministic evidence clipping and atomic tool-exchange grouping."""

import json
from dataclasses import dataclass
from typing import Any

from .budget import TokenEstimator
from .models import ContextProtocolError


@dataclass
class MessageGroup:
    indices: tuple[int, ...]
    tool_names: dict[str, str]


def group_messages(messages: list[dict[str, Any]]) -> list[MessageGroup]:
    """Reject malformed transcripts; never manufacture or silently drop results."""
    groups: list[MessageGroup] = []
    seen_ids: set[str] = set()
    index = 0
    while index < len(messages):
        message = messages[index]
        calls = message.get("tool_calls") or []
        if message.get("role") == "tool":
            raise ContextProtocolError("Orphan tool result")
        if not calls:
            groups.append(MessageGroup((index,), {}))
            index += 1
            continue
        if message.get("role") != "assistant":
            raise ContextProtocolError("tool_calls must belong to an assistant")
        names: dict[str, str] = {}
        for call in calls:
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id or call_id in names or call_id in seen_ids:
                raise ContextProtocolError("Tool call IDs must be nonempty and unique")
            names[call_id] = str(call.get("function", {}).get("name", "unknown"))[:64]
        seen_ids.update(names)
        pending = set(names)
        end = index + 1
        while pending and end < len(messages):
            result = messages[end]
            call_id = result.get("tool_call_id")
            if result.get("role") != "tool" or call_id not in pending:
                raise ContextProtocolError("Tool exchange is incomplete or has duplicate results")
            pending.remove(call_id)
            end += 1
        if pending:
            raise ContextProtocolError("Missing tool results")
        groups.append(MessageGroup(tuple(range(index, end)), names))
        index = end
    return groups


def clip_text(text: str, limit: int, estimator: TokenEstimator, *, tool_name: str | None = None) -> str:
    """Keep deterministic head/tail evidence; measure the marker within the cap."""
    if estimator.estimate_text(text) <= limit:
        return text
    status = "unknown"
    if tool_name:
        try:
            output = json.loads(text)
        except (ValueError, TypeError):
            output = None
        if isinstance(output, dict) and isinstance(output.get("success"), bool):
            status = "success" if output["success"] else "failed"

    def render(kept: int) -> str:
        head_size = (kept + 1) // 2
        tail_size = kept // 2
        head = text[:head_size]
        tail = text[-tail_size:] if tail_size else ""
        label = "Tool Observation" if tool_name else "Context"
        tool = f"\ntool={tool_name}\nstatus={status}" if tool_name else ""
        return (
            f"[{label} compacted]{tool}\noriginal_chars={len(text)}\nkept_chars={kept}"
            f"\nhead:\n{head}\ntail:\n{tail}"
        )

    if estimator.estimate_text(render(0)) > limit:
        return "[compacted]" if estimator.estimate_text("[compacted]") <= limit else ""
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if estimator.estimate_text(render(mid)) <= limit:
            low = mid
        else:
            high = mid - 1
    return render(low)
