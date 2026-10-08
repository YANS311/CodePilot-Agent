from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.trace import (
    TRACE_EVENT_SCHEMA_VERSION,
    ExecutionStepTrace,
    ExecutionTrace,
    InMemoryTraceSink,
    JsonlTraceSink,
    TraceEvent,
)


class TestTraceEventContract:
    def test_serializes_required_harness_fields(self):
        event = TraceEvent(
            task_id="task-123",
            step_id=3,
            agent_action="tool_call",
            tool_name="search_code",
            tool_input={"query": "jwt"},
            tool_output={"matches": 2},
            execution_result="success",
            duration_ms=12.5,
        )

        data = json.loads(event.to_json())

        assert data["schema_version"] == TRACE_EVENT_SCHEMA_VERSION
        assert data["task_id"] == "task-123"
        assert data["step_id"] == 3
        assert data["agent_action"] == "tool_call"
        assert data["tool_name"] == "search_code"
        assert data["tool_input"] == {"query": "jwt"}
        assert data["tool_output"] == {"matches": 2}
        assert data["execution_result"] == "success"
        assert data["duration_ms"] == 12.5
        assert datetime.fromisoformat(data["timestamp"]).utcoffset() is not None

    def test_mutable_fields_are_isolated_per_event(self):
        first = TraceEvent(task_id="task-1", step_id=1, agent_action="plan")
        second = TraceEvent(task_id="task-2", step_id=1, agent_action="plan")

        first.tool_input["query"] = "first"
        first.metadata["source"] = "agent"

        assert second.tool_input == {}
        assert second.metadata == {}


class TestExecutionTrace:
    def test_trace_step_addition_and_latency(self, tmp_path: Path):
        trace = ExecutionTrace(task="Fix calculator subtract bug", active_skill="bug-fix")
        assert trace.active_skill == "bug-fix"
        assert len(trace.steps) == 0

        # 添加第一步
        trace.add_step(
            step=1,
            tool_name="search_code",
            arguments={"query": "def subtract"},
            status="success",
            latency_ms=45.2,
            decision="Locate subtract definition",
            output="examples/buggy_calculator.py:5: def subtract",
        )

        # 添加第二步
        trace.add_step(
            step=2,
            tool_name="code_edit",
            arguments={"path": "examples/buggy_calculator.py", "old": "a + b", "new": "a - b"},
            status="success",
            latency_ms=12.8,
            decision="Apply minimal fix",
            output="Successfully edited file",
        )

        assert len(trace.steps) == 2
        assert len(trace.events) == 2
        assert [event.step_id for event in trace.events] == [1, 2]
        assert all(event.task_id == trace.task_id for event in trace.events)
        assert trace.events[0].agent_action == "tool_call"
        assert trace.events[0].tool_output == "examples/buggy_calculator.py:5: def subtract"
        assert trace.total_latency_ms == pytest.approx(58.0, rel=1e-2)

        # 导出为 JSONL
        out_file = tmp_path / "test_trace.jsonl"
        trace.export_jsonl(out_file)

        assert out_file.exists()
        line = out_file.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["task"] == "Fix calculator subtract bug"
        assert data["active_skill"] == "bug-fix"
        assert len(data["steps"]) == 2
        assert data["steps"][0]["tool_name"] == "search_code"
        assert len(data["events"]) == 2


class TestTraceSinks:
    def test_in_memory_sink_receives_execution_events(self):
        sink = InMemoryTraceSink()
        trace = ExecutionTrace(task="Inspect code", task_id="task-fixed", sink=sink)

        trace.record_event(
            "tool_call",
            tool_name="read_file",
            tool_input={"path": "app/main.py"},
            execution_result="success",
        )

        events = sink.snapshot()
        assert len(events) == 1
        assert events[0].task_id == "task-fixed"
        assert events[0].step_id == 1

    def test_jsonl_sink_writes_one_event_per_line(self, tmp_path: Path):
        output = tmp_path / "events.jsonl"
        sink = JsonlTraceSink(output)
        sink.emit(TraceEvent(task_id="task-1", step_id=1, agent_action="plan"))
        sink.emit(TraceEvent(task_id="task-1", step_id=2, agent_action="tool_call"))

        lines = output.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert [json.loads(line)["step_id"] for line in lines] == [1, 2]

    def test_sink_failure_does_not_break_agent_trace(self):
        class FailingSink:
            def emit(self, event: TraceEvent) -> None:
                raise OSError("storage unavailable")

        trace = ExecutionTrace(task="Keep running", sink=FailingSink())
        event = trace.record_event("task_start", execution_result="started")

        assert event in trace.events
