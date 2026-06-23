"""Unified output schema — AgentFinalOutput, StepTrace, OutputMetrics.

All Agent modes (REACT / REPO / SECURITY / EVAL) produce AgentFinalOutput.
This ensures every response is structured, displayable, and evaluable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepTrace:
    """Single execution step — universal across all modes.

    Replaces the mode-specific step formats with one common structure.
    """

    step_id: int
    action: str = ""
    tool: str = ""
    input: str = ""
    output: str = ""
    success: bool = True
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }


@dataclass
class OutputMetrics:
    """Unified metrics — always present, mode-specific fields optional.

    Every AgentFinalOutput includes a metrics block so consumers
    can read structured performance data without parsing text.
    """

    task_success: bool = False
    tool_calls: int = 0
    duration_ms: int = 0
    test_pass: bool = False
    test_passed: int = 0
    test_failed: int = 0
    security_block: bool = False
    evidence_count: int = 0

    def to_dict(self) -> dict:
        return {
            "task_success": self.task_success,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
            "test_pass": self.test_pass,
            "test_passed": self.test_passed,
            "test_failed": self.test_failed,
            "security_block": self.security_block,
            "evidence_count": self.evidence_count,
        }


@dataclass
class AgentFinalOutput:
    """Unified output from all Agent modes.

    Every mode produces this structure. Consumers (API, frontend, eval)
    read the same fields regardless of which mode ran.
    """

    mode: str  # "react" / "repo" / "security" / "eval"
    summary: str  # primary answer / analysis text

    actions: list[StepTrace] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    metrics: OutputMetrics = field(default_factory=OutputMetrics)
    confidence: float = 0.0
    execution_trace: list[StepTrace] = field(default_factory=list)

    # Mode-specific extras (preserved for backwards compat)
    security_warnings: list[dict] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    raw_answer: str = ""  # original unformatted answer

    def to_dict(self) -> dict:
        """JSON-serializable dict for API responses."""
        return {
            "mode": self.mode,
            "summary": self.summary,
            "actions": [s.to_dict() for s in self.actions],
            "tools_used": self.tools_used,
            "evidence": self.evidence,
            "metrics": self.metrics.to_dict(),
            "confidence": self.confidence,
            "execution_trace": [s.to_dict() for s in self.execution_trace],
            "security_warnings": self.security_warnings,
            "thoughts": self.thoughts,
            "raw_answer": self.raw_answer,
        }
