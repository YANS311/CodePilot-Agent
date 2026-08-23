from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.trace import ExecutionStepTrace, ExecutionTrace


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
