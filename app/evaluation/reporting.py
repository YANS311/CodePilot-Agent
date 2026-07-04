"""reporting — Benchmark report generation: load, merge, render.

Pure functions for generating multi-baseline comparison reports.
No eval execution, no external dependencies beyond stdlib.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# Sentinel for missing fields
NOT_AVAILABLE = "not_available"

# CI disclaimer text
CI_DISCLAIMER = (
    "> **Note**: This report was generated in CI/mock mode and should "
    "not be interpreted as real model performance."
)


@dataclass
class BaselineReport:
    """Single baseline's evaluation report."""

    baseline: str = "unknown"
    layer: str = "all"
    timestamp: str = ""
    metrics: dict = field(default_factory=dict)
    task_count: int = 0
    ci_mode: bool = False
    source_path: str = ""


@dataclass
class BenchmarkReport:
    """Multi-baseline comparison report."""

    reports: list[BaselineReport] = field(default_factory=list)
    generated_at: str = ""


def load_report_json(path: str | Path) -> dict:
    """Load a v2.0/v2.1 eval report JSON.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Report file not found: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _safe_get(data: dict, *keys: str, default: Any = None) -> Any:
    """Safely get a nested dict value."""
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
    return current


def extract_baseline_report(
    data: dict, source_path: str | None = None
) -> BaselineReport:
    """Extract BaselineReport from loaded eval report JSON.

    Compatible with v2.0 (no baseline/layer fields) and v2.1.
    Missing fields are set to NOT_AVAILABLE where appropriate.
    """
    # Baseline: try top-level, then metadata
    baseline = (
        data.get("baseline")
        or _safe_get(data, "metadata", "baseline")
        or NOT_AVAILABLE
    )

    # Layer: try top-level, then metadata
    layer = (
        data.get("layer")
        or _safe_get(data, "metadata", "layer")
        or "all"
    )

    # Timestamp
    timestamp = data.get("timestamp", "")

    # ci_mode: check multiple sources
    ci_mode = bool(
        data.get("ci_mode")
        or _safe_get(data, "metadata", "ci_mode")
        or _safe_get(data, "metadata", "mock_mode")
    )

    # Metrics: extract from report
    raw_metrics = data.get("metrics", {})

    # Build sanitized metrics dict — replace missing with NOT_AVAILABLE
    metrics = _sanitize_metrics(raw_metrics)

    # Task count: from metrics or count tasks list
    task_count = raw_metrics.get("total_tasks", 0)
    if task_count == 0 and "tasks" in data:
        task_count = len(data["tasks"])

    return BaselineReport(
        baseline=str(baseline),
        layer=str(layer),
        timestamp=str(timestamp),
        metrics=metrics,
        task_count=task_count,
        ci_mode=ci_mode,
        source_path=str(source_path) if source_path else "",
    )


def _sanitize_metrics(raw: dict) -> dict:
    """Ensure all known metric keys are present; use NOT_AVAILABLE for missing."""
    known_keys = [
        "total_tasks",
        "successful_tasks",
        "task_success_rate",
        "total_tests_passed",
        "total_tests_failed",
        "test_pass_rate",
        "avg_tool_calls",
        "avg_duration_ms",
        "pass_at_1",
        "tool_efficiency",
        "tool_calls_per_success",
        "budget_efficiency",
        "verification_pass_rate",
        "edit_precision_rate",
        "success_by_layer",
        "error_distribution",
        "success_by_difficulty",
        "success_by_category",
    ]
    result = {}
    for key in known_keys:
        if key in raw:
            result[key] = raw[key]
        else:
            result[key] = NOT_AVAILABLE
    return result


def merge_baseline_reports(
    reports: list[BaselineReport],
) -> BenchmarkReport:
    """Combine multiple BaselineReport into a BenchmarkReport."""
    return BenchmarkReport(
        reports=list(reports),
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _fmt_metric(value: Any, fmt: str = "") -> str:
    """Format a metric value for display in Markdown tables."""
    if value == NOT_AVAILABLE or value is None:
        return NOT_AVAILABLE
    if isinstance(value, float):
        if fmt == "pct":
            return f"{value:.1%}"
        if fmt == "rate":
            return f"{value:.4f}"
        return f"{value:.1f}"
    return str(value)


def _get_metric(metrics: dict, key: str, default: Any = NOT_AVAILABLE) -> Any:
    """Get a metric value, returning default if missing or NOT_AVAILABLE."""
    val = metrics.get(key, default)
    if val is None:
        return NOT_AVAILABLE
    return val


def _build_overall_table(reports: list[BaselineReport]) -> list[str]:
    """Build the Overall Comparison markdown table."""
    lines = [
        "## Overall Comparison",
        "",
        "| Baseline | Layer | Tasks | Passed | Failed | TSR | Pass@1 | Avg Tools | Verification Rate | Edit Precision |",
        "|----------|-------|------:|-------:|-------:|----:|-------:|----------:|------------------:|---------------:|",
    ]
    for r in reports:
        m = r.metrics
        passed = _get_metric(m, "successful_tasks")
        failed = _get_metric(m, "total_tests_failed")
        if passed != NOT_AVAILABLE and r.task_count > 0:
            failed_val = r.task_count - passed if isinstance(passed, int) else NOT_AVAILABLE
        else:
            failed_val = failed
        lines.append(
            f"| {r.baseline} | {r.layer} | {r.task_count} "
            f"| {_fmt_metric(passed)} | {_fmt_metric(failed_val)} "
            f"| {_fmt_metric(_get_metric(m, 'task_success_rate'), 'pct')} "
            f"| {_fmt_metric(_get_metric(m, 'pass_at_1'), 'pct')} "
            f"| {_fmt_metric(_get_metric(m, 'avg_tool_calls'))} "
            f"| {_fmt_metric(_get_metric(m, 'verification_pass_rate'), 'pct')} "
            f"| {_fmt_metric(_get_metric(m, 'edit_precision_rate'), 'pct')} |"
        )
    lines.append("")
    return lines


def _build_layer_breakdown(reports: list[BaselineReport]) -> list[str]:
    """Build Layer Breakdown section — one table per baseline."""
    lines = ["## Layer Breakdown", ""]

    for r in reports:
        layer_data = r.metrics.get("success_by_layer", NOT_AVAILABLE)
        lines.append(f"### {r.baseline}")
        lines.append("")

        if layer_data == NOT_AVAILABLE or not isinstance(layer_data, dict):
            lines.append(f"{NOT_AVAILABLE}")
            lines.append("")
            continue

        lines.append("| Layer | Total | Passed | Failed | Pass Rate |")
        lines.append("|-------|------:|-------:|-------:|----------:|")
        for layer_name in ("unit", "integration", "stress"):
            if layer_name in layer_data:
                stats = layer_data[layer_name]
                total = stats.get("total", 0)
                success = stats.get("success", 0)
                rate = stats.get("rate", 0.0)
                lines.append(
                    f"| {layer_name} | {total} | {success} "
                    f"| {total - success} | {rate:.1%} |"
                )
            else:
                lines.append(f"| {layer_name} | {NOT_AVAILABLE} | {NOT_AVAILABLE} | {NOT_AVAILABLE} | {NOT_AVAILABLE} |")
        lines.append("")

    return lines


def _build_agent_metrics_table(reports: list[BaselineReport]) -> list[str]:
    """Build Agent-Specific Metrics section."""
    lines = [
        "## Agent-Specific Metrics",
        "",
        "| Baseline | Verification Rate | Edit Precision | Avg Tool Calls | Tool Calls/Success |",
        "|----------|------------------:|---------------:|---------------:|-------------------:|",
    ]
    for r in reports:
        m = r.metrics
        lines.append(
            f"| {r.baseline} "
            f"| {_fmt_metric(_get_metric(m, 'verification_pass_rate'), 'pct')} "
            f"| {_fmt_metric(_get_metric(m, 'edit_precision_rate'), 'pct')} "
            f"| {_fmt_metric(_get_metric(m, 'avg_tool_calls'))} "
            f"| {_fmt_metric(_get_metric(m, 'tool_calls_per_success'))} |"
        )
    lines.append("")
    return lines


def _build_difficulty_breakdown(reports: list[BaselineReport]) -> list[str]:
    """Build difficulty breakdown section."""
    lines = ["## Difficulty Breakdown", ""]

    for r in reports:
        diff_data = r.metrics.get("success_by_difficulty", NOT_AVAILABLE)
        lines.append(f"### {r.baseline}")
        lines.append("")

        if diff_data == NOT_AVAILABLE or not isinstance(diff_data, dict):
            lines.append(NOT_AVAILABLE)
            lines.append("")
            continue

        lines.append("| Difficulty | Total | Passed | Pass Rate |")
        lines.append("|------------|------:|-------:|----------:|")
        for diff in ("easy", "medium", "hard"):
            if diff in diff_data:
                stats = diff_data[diff]
                lines.append(
                    f"| {diff} | {stats.get('total', 0)} "
                    f"| {stats.get('success', 0)} "
                    f"| {stats.get('rate', 0.0):.1%} |"
                )
        lines.append("")

    return lines


def render_markdown_report(report: BenchmarkReport) -> str:
    """Render BenchmarkReport as Markdown string.

    Sections: Header, CI disclaimer, Overall Comparison, Layer Breakdown,
    Agent Metrics, Difficulty Breakdown, Reproducing, Known Limitations.
    """
    sections: list[str] = []

    # Header
    baselines_str = ", ".join(r.baseline for r in report.reports)
    sections.append("# CodePilot Agent Benchmark Report")
    sections.append("")
    sections.append(f"**Generated**: {report.generated_at}")
    sections.append(f"**Baselines**: {baselines_str}")
    sections.append("")

    # CI disclaimer — show if any report is ci_mode
    if any(r.ci_mode for r in report.reports):
        sections.append(CI_DISCLAIMER)
        sections.append("")

    # Overall Comparison
    sections.extend(_build_overall_table(report.reports))

    # Layer Breakdown
    sections.extend(_build_layer_breakdown(report.reports))

    # Agent-Specific Metrics
    sections.extend(_build_agent_metrics_table(report.reports))

    # Difficulty Breakdown
    sections.extend(_build_difficulty_breakdown(report.reports))

    # Reproducing
    sections.extend([
        "## Reproducing",
        "",
        "```bash",
        "# From existing JSON reports (no eval run needed)",
        "python scripts/generate_benchmark_report.py \\",
        "  --baseline-files reports/react_full.json reports/bare_llm.json \\",
        "  --output-md docs/benchmark_report.md",
        "",
        "# From single report",
        "python scripts/generate_benchmark_report.py \\",
        "  --from-json reports/eval_report.json \\",
        "  --output-md docs/benchmark_report.md",
        "```",
        "",
    ])

    # Known Limitations
    sections.extend([
        "## Known Limitations",
        "",
        "- Missing fields are reported as `not_available` rather than fabricated.",
        "- CI/mock reports are not real model performance.",
        "- `bare_llm` is a conservative text-only baseline (no tools, no agent loop).",
        "- Metrics depend on trace availability from the evaluation runner.",
        "- `retry_recovery_rate` is not yet tracked and shows `not_available`.",
        "",
    ])

    return "\n".join(sections)


def render_single_report(data: dict) -> str:
    """Render a single-baseline JSON report as Markdown.

    Internally uses extract_baseline_report + render_markdown_report.
    """
    br = extract_baseline_report(data)
    report = BenchmarkReport(
        reports=[br],
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )
    return render_markdown_report(report)


def write_report(
    report: BenchmarkReport,
    output_json: str | Path | None = None,
    output_md: str | Path | None = None,
) -> None:
    """Write BenchmarkReport to JSON and/or Markdown files.

    Creates parent directories if they don't exist.
    """
    if output_md:
        md_path = Path(output_md)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_content = render_markdown_report(report)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    if output_json:
        json_path = Path(output_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_data = {
            "version": "3.0",
            "generated_at": report.generated_at,
            "baselines": [
                {
                    "baseline": r.baseline,
                    "layer": r.layer,
                    "timestamp": r.timestamp,
                    "task_count": r.task_count,
                    "ci_mode": r.ci_mode,
                    "source_path": r.source_path,
                    "metrics": r.metrics,
                }
                for r in report.reports
            ],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
