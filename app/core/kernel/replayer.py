from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List
from app.core.kernel.context import AgentContext
from app.core.kernel.events import EventBus, KernelEvent


class EventStreamReplayer:
    """事件流回放引擎，支持断点调试、状态重放与轨迹分叉。"""

    def __init__(self, events: List[KernelEvent] | None = None) -> None:
        self._events: List[KernelEvent] = list(events or [])

    @classmethod
    def from_jsonl(cls, jsonl_path: str | Path) -> EventStreamReplayer:
        """从 JSONL 日志中还原事件流。"""
        path = Path(jsonl_path)
        events = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    events.append(KernelEvent(
                        type=item["type"],
                        payload=item.get("payload"),
                        timestamp=item.get("timestamp", 0.0),
                    ))
        return cls(events)

    def export_jsonl(self, output_path: str | Path) -> None:
        """导出当前事件流到 JSONL 文件。"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for event in self._events:
                line = json.dumps(asdict(event), ensure_ascii=False)
                f.write(line + "\n")

    async def replay_to_bus(
        self,
        event_bus: EventBus,
        up_to_step: int | None = None,
        filter_fn: Callable[[KernelEvent], bool] | None = None,
    ) -> int:
        """将历史事件流重放到目标 EventBus，支持限制步数。"""
        replayed_count = 0
        events_to_replay = self._events[:up_to_step] if up_to_step is not None else self._events

        for event in events_to_replay:
            if filter_fn and not filter_fn(event):
                continue
            await event_bus.emit(event.type, event.payload)
            replayed_count += 1

        return replayed_count

    def fork_at(self, step_index: int, new_context: AgentContext | None = None) -> AgentContext:
        """在指定事件索引处进行轨迹分叉 (Fork)，创建独立的派生上下文。"""
        if step_index < 0 or step_index > len(self._events):
            raise IndexError(f"分叉索引越界: {step_index} (总事件数: {len(self._events)})")

        forked_events = self._events[:step_index]
        parent_ctx = new_context or AgentContext()
        child_ctx = parent_ctx.create_child()

        # 将分叉前的历史事件载入子上下文的 EventBus
        for e in forked_events:
            child_ctx.events._event_log.append(e)

        return child_ctx
