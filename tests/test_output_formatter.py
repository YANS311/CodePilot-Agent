"""Tests for app.output.formatter — format_output() for all modes."""

from app.models.tool import AgentStep, ToolResult
from app.output.formatter import format_output


class TestFormatReact:
    def test_basic_react(self):
        steps = [
            AgentStep(step_id=1, thought="need to search", action="search_code({'query':'bug'})",
                      tool_name="search_code", observation="found bug at line 5"),
            AgentStep(step_id=2, thought="fix it", action="write_file({'path':'x.py','content':'...'})",
                      tool_name="write_file", observation="written"),
        ]
        tool_results = [
            ToolResult(tool_call_id="t1", name="search_code", success=True, output="found"),
            ToolResult(tool_call_id="t2", name="write_file", success=True, output="ok"),
        ]
        out = format_output(mode="react", answer="Fixed the bug", steps=steps, tool_results=tool_results)
        assert out.mode == "react"
        assert out.summary == "Fixed the bug"
        assert len(out.execution_trace) == 2
        assert out.execution_trace[0].tool == "search_code"
        assert out.execution_trace[1].tool == "write_file"
        assert out.tools_used == ["search_code", "write_file"]
        assert out.metrics.tool_calls == 2

    def test_react_empty_steps(self):
        out = format_output(mode="react", answer="No tools needed")
        assert out.execution_trace == []
        assert out.tools_used == []
        assert out.metrics.tool_calls == 0


class TestFormatRepo:
    def test_repo_with_evidence(self):
        evidence = [
            {"claim_text": "main function", "evidence": [{"file": "app/main.py", "symbol": "main"}]},
        ]
        out = format_output(mode="repo", answer="## Project Overview\n...", evidence=evidence, confidence=0.85)
        assert out.mode == "repo"
        assert out.confidence == 0.85
        assert len(out.evidence) == 1
        assert out.metrics.evidence_count == 1
        assert out.execution_trace == []
        assert out.tools_used == []


class TestFormatSecurity:
    def test_security_blocked(self):
        warnings = [{"risk_type": "prompt_injection", "reason": "ignore rules"}]
        out = format_output(mode="security", answer="安全拦截: ...", security_warnings=warnings)
        assert out.mode == "security"
        assert out.metrics.security_block is True
        assert len(out.security_warnings) == 1
        assert out.execution_trace == []


class TestFormatEval:
    def test_eval_with_metrics(self):
        out = format_output(
            mode="eval", answer="Fixed",
            duration_ms=5000, test_success=True, test_passed=5, test_failed=0,
        )
        assert out.mode == "eval"
        assert out.metrics.test_pass is True
        assert out.metrics.test_passed == 5
        assert out.metrics.duration_ms == 5000


class TestToolsDedup:
    def test_dedup_tools(self):
        steps = [
            AgentStep(step_id=1, tool_name="search_code", action="search"),
            AgentStep(step_id=2, tool_name="read_file", action="read"),
            AgentStep(step_id=3, tool_name="search_code", action="search2"),
        ]
        out = format_output(mode="react", answer="done", steps=steps)
        assert out.tools_used == ["search_code", "read_file"]
