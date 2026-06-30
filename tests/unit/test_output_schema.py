"""Tests for app.output.schema — AgentFinalOutput, StepTrace, OutputMetrics."""

import json

from app.output.schema import AgentFinalOutput, OutputMetrics, StepTrace


class TestStepTrace:
    def test_defaults(self):
        s = StepTrace(step_id=1)
        assert s.step_id == 1
        assert s.action == ""
        assert s.tool == ""
        assert s.input == ""
        assert s.output == ""
        assert s.success is True
        assert s.duration_ms == 0

    def test_to_dict(self):
        s = StepTrace(step_id=1, action="search", tool="search_code", success=True)
        d = s.to_dict()
        assert d["step_id"] == 1
        assert d["tool"] == "search_code"
        assert d["success"] is True


class TestOutputMetrics:
    def test_defaults(self):
        m = OutputMetrics()
        assert m.task_success is False
        assert m.tool_calls == 0
        assert m.duration_ms == 0
        assert m.test_pass is False
        assert m.security_block is False
        assert m.evidence_count == 0

    def test_to_dict(self):
        m = OutputMetrics(task_success=True, tool_calls=3, duration_ms=1500)
        d = m.to_dict()
        assert d["task_success"] is True
        assert d["tool_calls"] == 3
        assert d["duration_ms"] == 1500


class TestAgentFinalOutput:
    def test_defaults(self):
        out = AgentFinalOutput(mode="react", summary="test")
        assert out.mode == "react"
        assert out.summary == "test"
        assert out.actions == []
        assert out.tools_used == []
        assert out.evidence == []
        assert isinstance(out.metrics, OutputMetrics)
        assert out.confidence == 0.0
        assert out.execution_trace == []
        assert out.security_warnings == []
        assert out.thoughts == []
        assert out.raw_answer == ""

    def test_to_dict(self):
        out = AgentFinalOutput(
            mode="repo",
            summary="analysis",
            confidence=0.85,
            evidence=[{"claim_text": "test", "evidence": []}],
            tools_used=["search_code"],
        )
        d = out.to_dict()
        assert d["mode"] == "repo"
        assert d["summary"] == "analysis"
        assert d["confidence"] == 0.85
        assert len(d["evidence"]) == 1
        assert d["tools_used"] == ["search_code"]
        assert "metrics" in d
        assert "execution_trace" in d

    def test_json_roundtrip(self):
        out = AgentFinalOutput(mode="react", summary="fixed")
        out.execution_trace = [StepTrace(step_id=1, tool="write_file")]
        out.metrics = OutputMetrics(tool_calls=1, task_success=True)

        serialized = json.dumps(out.to_dict(), ensure_ascii=False)
        loaded = json.loads(serialized)

        assert loaded["mode"] == "react"
        assert loaded["metrics"]["tool_calls"] == 1
        assert loaded["metrics"]["task_success"] is True
        assert len(loaded["execution_trace"]) == 1
        assert loaded["execution_trace"][0]["tool"] == "write_file"
