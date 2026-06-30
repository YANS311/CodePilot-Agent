"""Tests for cross-mode output consistency.

Verifies that all 4 modes produce AgentFinalOutput with identical structure.
"""

from app.models.tool import AgentStep, ToolResult
from app.output.formatter import format_output
from app.output.schema import AgentFinalOutput, OutputMetrics, StepTrace


REQUIRED_FIELDS = [
    "mode", "summary", "actions", "tools_used", "evidence",
    "metrics", "confidence", "execution_trace",
    "security_warnings", "thoughts", "raw_answer",
]

METRICS_FIELDS = [
    "task_success", "tool_calls", "duration_ms",
    "test_pass", "test_passed", "test_failed",
    "security_block", "evidence_count",
]


class TestConsistentStructure:
    """All modes must produce the same AgentFinalOutput structure."""

    def _make_react(self):
        steps = [AgentStep(step_id=1, tool_name="search_code", action="s")]
        return format_output(mode="react", answer="fixed", steps=steps)

    def _make_repo(self):
        return format_output(
            mode="repo", answer="analysis",
            evidence=[{"claim_text": "x"}], confidence=0.9,
        )

    def _make_security(self):
        return format_output(
            mode="security", answer="blocked",
            security_warnings=[{"risk_type": "injection"}],
        )

    def _make_eval(self):
        return format_output(mode="eval", answer="done", test_success=True)

    def test_all_modes_have_required_fields(self):
        for maker in [self._make_react, self._make_repo, self._make_security, self._make_eval]:
            out = maker()
            assert isinstance(out, AgentFinalOutput)
            for field in REQUIRED_FIELDS:
                assert hasattr(out, field), f"Missing field: {field}"

    def test_all_modes_have_metrics(self):
        for maker in [self._make_react, self._make_repo, self._make_security, self._make_eval]:
            out = maker()
            assert isinstance(out.metrics, OutputMetrics)
            for field in METRICS_FIELDS:
                assert hasattr(out.metrics, field), f"Missing metrics field: {field}"

    def test_all_modes_execution_trace_is_list(self):
        for maker in [self._make_react, self._make_repo, self._make_security, self._make_eval]:
            out = maker()
            assert isinstance(out.execution_trace, list)

    def test_all_modes_evidence_is_list(self):
        for maker in [self._make_react, self._make_repo, self._make_security, self._make_eval]:
            out = maker()
            assert isinstance(out.evidence, list)

    def test_all_modes_mode_field_matches(self):
        modes = ["react", "repo", "security", "eval"]
        makers = [self._make_react, self._make_repo, self._make_security, self._make_eval]
        for mode, maker in zip(modes, makers):
            out = maker()
            assert out.mode == mode

    def test_all_modes_to_dict_roundtrip(self):
        for maker in [self._make_react, self._make_repo, self._make_security, self._make_eval]:
            out = maker()
            d = out.to_dict()
            assert isinstance(d, dict)
            assert "mode" in d
            assert "metrics" in d
            assert "execution_trace" in d
            assert isinstance(d["execution_trace"], list)


class TestMetricsConsistency:
    """Metrics block is always fully populated."""

    def test_react_metrics(self):
        out = format_output(mode="react", answer="x",
                            steps=[AgentStep(step_id=1, tool_name="write_file", action="w")])
        m = out.metrics
        assert m.tool_calls == 1
        assert isinstance(m.task_success, bool)
        assert isinstance(m.duration_ms, int)

    def test_security_metrics(self):
        out = format_output(mode="security", answer="x",
                            security_warnings=[{"risk_type": "injection"}])
        assert out.metrics.security_block is True

    def test_repo_metrics(self):
        out = format_output(mode="repo", answer="x",
                            evidence=[{"claim_text": "a"}, {"claim_text": "b"}])
        assert out.metrics.evidence_count == 2

    def test_eval_metrics(self):
        out = format_output(mode="eval", answer="x",
                            test_success=True, test_passed=5, test_failed=0)
        assert out.metrics.test_pass is True
        assert out.metrics.test_passed == 5


class TestEvalSchemaUnified:
    """EvalResult.to_unified() produces AgentFinalOutput-compatible dict."""

    def test_to_unified_structure(self):
        from app.evaluation.schema import EvalResult, ToolCallRecord
        result = EvalResult(
            task_id="fix-01",
            success=True,
            final_answer="Fixed",
            tool_calls_count=3,
            duration_ms=5000,
            test_success=True,
            passed=5,
            failed=0,
            steps=[
                ToolCallRecord(tool_name="search_code", success=True),
                ToolCallRecord(tool_name="write_file", success=True),
            ],
        )
        unified = result.to_unified()
        assert unified["mode"] == "eval"
        assert unified["summary"] == "Fixed"
        assert unified["metrics"]["task_success"] is True
        assert unified["metrics"]["tool_calls"] == 3
        assert unified["metrics"]["test_pass"] is True
        assert unified["tools_used"] == ["search_code", "write_file"]
        assert len(unified["execution_trace"]) == 2
