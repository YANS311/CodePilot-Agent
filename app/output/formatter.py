"""Output formatter — converts any Agent mode result to AgentFinalOutput.

All Agent outputs pass through format_output() before reaching the API,
frontend, or eval system. This guarantees structural consistency.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.tool import AgentStep, ToolResult
from app.output.metrics import compute_react_metrics, compute_security_metrics
from app.output.schema import AgentFinalOutput, OutputMetrics, StepTrace


def _truncate(text: str, max_len: int = 500) -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _steps_to_trace(steps: List[AgentStep]) -> List[StepTrace]:
    """Convert internal AgentStep list to universal StepTrace list."""
    trace: List[StepTrace] = []
    for s in steps:
        trace.append(StepTrace(
            step_id=s.step_id,
            action=s.action,
            tool=s.tool_name,
            input=_truncate(str(s.tool_args), 200),
            output=_truncate(s.observation, 500),
            success=s.success,
        ))
    return trace


def _dedup_tools(steps: List[AgentStep]) -> List[str]:
    """Extract deduplicated tool names from steps."""
    seen: set = set()
    result: List[str] = []
    for s in steps:
        if s.tool_name and s.tool_name not in seen:
            seen.add(s.tool_name)
            result.append(s.tool_name)
    return result


def format_output(
    *,
    mode: str,
    answer: str,
    steps: Optional[List[AgentStep]] = None,
    tool_results: Optional[List[ToolResult]] = None,
    evidence: Optional[List[dict]] = None,
    confidence: float = 0.0,
    security_warnings: Optional[List[dict]] = None,
    thoughts: Optional[List[str]] = None,
    duration_ms: int = 0,
    test_success: bool = False,
    test_passed: int = 0,
    test_failed: int = 0,
) -> AgentFinalOutput:
    """Format any Agent mode result into the unified AgentFinalOutput.

    Args:
        mode: "react" / "repo" / "security" / "eval"
        answer: primary answer text
        steps: internal AgentStep list (REACT mode)
        tool_results: ToolResult list (REACT mode)
        evidence: evidence dicts (REPO mode)
        confidence: analysis confidence (REPO mode)
        security_warnings: security warning dicts (SECURITY mode)
        thoughts: agent thoughts list
        duration_ms: execution time
        test_success: whether tests passed
        test_passed: number of passed tests
        test_failed: number of failed tests

    Returns:
        AgentFinalOutput with all fields populated
    """
    steps = steps or []
    tool_results = tool_results or []
    evidence = evidence or []
    security_warnings = security_warnings or []
    thoughts = thoughts or []

    # Build execution trace
    execution_trace = _steps_to_trace(steps) if steps else []

    # Deduplicate tools used
    tools_used = _dedup_tools(steps) if steps else []

    # Compute metrics based on mode
    if mode == "react":
        metrics = compute_react_metrics(steps, tool_results, duration_ms)
    elif mode == "security":
        metrics = compute_security_metrics(bool(security_warnings), security_warnings)
    else:
        # repo / eval — use defaults + evidence count
        metrics = OutputMetrics(
            tool_calls=len(steps),
            duration_ms=duration_ms,
            evidence_count=len(evidence),
            test_pass=test_success,
            test_passed=test_passed,
            test_failed=test_failed,
        )

    return AgentFinalOutput(
        mode=mode,
        summary=answer,
        actions=execution_trace,
        tools_used=tools_used,
        evidence=evidence,
        metrics=metrics,
        confidence=confidence,
        execution_trace=execution_trace,
        security_warnings=security_warnings,
        thoughts=thoughts,
        raw_answer=answer,
    )
