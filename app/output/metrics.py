"""Unified metrics computation and merging.

Provides helpers to compute OutputMetrics from different mode results
and merge partial metrics into a single OutputMetrics.
"""

from __future__ import annotations

from typing import List

from app.models.tool import AgentStep, ToolResult
from app.output.schema import OutputMetrics


def merge_metrics(*partials: OutputMetrics) -> OutputMetrics:
    """Merge multiple partial metrics into one.

    For scalar fields, the last non-default value wins.
    For counts, values are summed.
    """
    result = OutputMetrics()
    for p in partials:
        if p.task_success:
            result.task_success = True
        result.tool_calls += p.tool_calls
        result.duration_ms += p.duration_ms
        if p.test_pass:
            result.test_pass = True
        result.test_passed += p.test_passed
        result.test_failed += p.test_failed
        if p.security_block:
            result.security_block = True
        result.evidence_count += p.evidence_count
    return result


def compute_react_metrics(
    steps: List[AgentStep],
    tool_results: List[ToolResult],
    duration_ms: int = 0,
) -> OutputMetrics:
    """Compute metrics from REACT mode execution.

    Checks if write_file was called and if run_tests passed.
    """
    tool_calls = len(steps)
    has_write = any(s.tool_name == "write_file" for s in steps)

    test_pass = False
    test_passed = 0
    test_failed = 0
    for tr in tool_results:
        if tr.name == "run_tests" and tr.success:
            import json
            try:
                data = json.loads(tr.output)
                test_pass = data.get("success", False)
                test_passed = data.get("passed", 0)
                test_failed = data.get("failed", 0)
            except (json.JSONDecodeError, AttributeError):
                pass

    return OutputMetrics(
        task_success=has_write and test_pass,
        tool_calls=tool_calls,
        duration_ms=duration_ms,
        test_pass=test_pass,
        test_passed=test_passed,
        test_failed=test_failed,
    )


def compute_security_metrics(
    blocked: bool,
    warnings: List[dict],
) -> OutputMetrics:
    """Compute metrics from SECURITY mode."""
    return OutputMetrics(
        task_success=False,
        security_block=blocked,
    )
