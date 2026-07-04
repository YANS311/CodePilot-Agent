"""Tests for app/evaluation/reporting.py — benchmark report generation.

Covers:
- load_report_json: valid file, missing file
- extract_baseline_report: v2.0 compat, v2.1 fields, missing fields → not_available
- merge_baseline_reports: multiple baselines
- render_markdown_report: overall table, layer breakdown, agent metrics, CI disclaimer
- render_single_report: from single JSON
- write_report: JSON and Markdown output
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.reporting import (
    NOT_AVAILABLE,
    BaselineReport,
    BenchmarkReport,
    CI_DISCLAIMER,
    extract_baseline_report,
    load_report_json,
    merge_baseline_reports,
    render_markdown_report,
    render_single_report,
    write_report,
)


# ═══════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════

V21_REPORT = {
    "version": "2.1",
    "timestamp": "2026-07-04T00:00:00",
    "baseline": "react_full",
    "layer": "all",
    "tasks": [
        {"task_id": "t1", "success": True, "tool_calls_count": 3, "passed": 2, "failed": 0},
        {"task_id": "t2", "success": False, "tool_calls_count": 5, "passed": 0, "failed": 1},
        {"task_id": "t3", "success": True, "tool_calls_count": 2, "passed": 1, "failed": 0},
    ],
    "metrics": {
        "total_tasks": 3,
        "successful_tasks": 2,
        "task_success_rate": 0.667,
        "total_tests_passed": 3,
        "total_tests_failed": 1,
        "test_pass_rate": 0.75,
        "avg_tool_calls": 3.33,
        "avg_duration_ms": 15000.0,
        "pass_at_1": 0.667,
        "tool_efficiency": 0.3,
        "tool_calls_per_success": 2.5,
        "budget_efficiency": 0.6,
        "verification_pass_rate": 0.5,
        "edit_precision_rate": 0.75,
        "success_by_layer": {
            "unit": {"total": 2, "success": 2, "rate": 1.0},
            "integration": {"total": 1, "success": 0, "rate": 0.0},
        },
        "success_by_difficulty": {
            "easy": {"total": 2, "success": 2, "rate": 1.0},
            "medium": {"total": 1, "success": 0, "rate": 0.0},
        },
        "error_distribution": {"test_not_executed": 1},
    },
}

V20_REPORT = {
    "version": "2.0",
    "timestamp": "2026-06-19T00:00:00",
    "tasks": [{"task_id": "t1", "success": True}],
    "metrics": {
        "total_tasks": 1,
        "successful_tasks": 1,
        "task_success_rate": 1.0,
        "avg_tool_calls": 5.0,
    },
}


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def v21_json(tmp_dir):
    p = tmp_dir / "v21_report.json"
    p.write_text(json.dumps(V21_REPORT), encoding="utf-8")
    return str(p)


@pytest.fixture
def v20_json(tmp_dir):
    p = tmp_dir / "v20_report.json"
    p.write_text(json.dumps(V20_REPORT), encoding="utf-8")
    return str(p)


# ═══════════════════════════════════════════
# 1. load_report_json
# ═══════════════════════════════════════════


class TestLoadReportJson:
    def test_load_valid_json(self, v21_json):
        data = load_report_json(v21_json)
        assert data["version"] == "2.1"
        assert data["baseline"] == "react_full"

    def test_load_missing_file(self, tmp_dir):
        with pytest.raises(FileNotFoundError):
            load_report_json(str(tmp_dir / "nonexistent.json"))

    def test_load_invalid_json(self, tmp_dir):
        bad = tmp_dir / "bad.json"
        bad.write_text("not json {{{", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            load_report_json(str(bad))


# ═══════════════════════════════════════════
# 2. extract_baseline_report
# ═══════════════════════════════════════════


class TestExtractBaselineReport:
    def test_v21_full_fields(self):
        br = extract_baseline_report(V21_REPORT)
        assert br.baseline == "react_full"
        assert br.layer == "all"
        assert br.task_count == 3
        assert br.ci_mode is False
        assert br.metrics["verification_pass_rate"] == 0.5
        assert br.metrics["edit_precision_rate"] == 0.75
        assert br.metrics["success_by_layer"] != NOT_AVAILABLE

    def test_v20_missing_fields(self):
        br = extract_baseline_report(V20_REPORT)
        assert br.baseline == NOT_AVAILABLE
        assert br.layer == "all"
        assert br.task_count == 1
        assert br.metrics["verification_pass_rate"] == NOT_AVAILABLE
        assert br.metrics["edit_precision_rate"] == NOT_AVAILABLE
        assert br.metrics["success_by_layer"] == NOT_AVAILABLE

    def test_ci_mode_detected(self):
        data = dict(V21_REPORT)
        data["ci_mode"] = True
        br = extract_baseline_report(data)
        assert br.ci_mode is True

    def test_ci_mode_default_false(self):
        br = extract_baseline_report(V20_REPORT)
        assert br.ci_mode is False

    def test_source_path_stored(self):
        br = extract_baseline_report(V21_REPORT, source_path="/tmp/report.json")
        assert br.source_path == "/tmp/report.json"


# ═══════════════════════════════════════════
# 3. merge_baseline_reports
# ═══════════════════════════════════════════


class TestMergeBaselineReports:
    def test_merge_two_reports(self):
        r1 = BaselineReport(baseline="react_full", task_count=30)
        r2 = BaselineReport(baseline="bare_llm", task_count=30)
        merged = merge_baseline_reports([r1, r2])
        assert len(merged.reports) == 2
        assert merged.reports[0].baseline == "react_full"
        assert merged.reports[1].baseline == "bare_llm"
        assert merged.generated_at  # non-empty

    def test_merge_preserves_not_available(self):
        r1 = BaselineReport(
            baseline="react_full",
            metrics={"verification_pass_rate": NOT_AVAILABLE},
        )
        merged = merge_baseline_reports([r1])
        assert merged.reports[0].metrics["verification_pass_rate"] == NOT_AVAILABLE


# ═══════════════════════════════════════════
# 4. render_markdown_report
# ═══════════════════════════════════════════


class TestRenderMarkdownReport:
    def _render(self, reports, ci=False):
        for r in reports:
            if ci:
                r.ci_mode = True
        report = BenchmarkReport(reports=reports, generated_at="2026-07-04 12:00:00")
        return render_markdown_report(report)

    def test_contains_header(self):
        r = BaselineReport(baseline="react_full", metrics={"task_success_rate": 0.9})
        md = self._render([r])
        assert "# CodePilot Agent Benchmark Report" in md
        assert "2026-07-04 12:00:00" in md

    def test_contains_overall_table(self):
        r = BaselineReport(baseline="react_full", task_count=30, metrics={"task_success_rate": 0.9})
        md = self._render([r])
        assert "## Overall Comparison" in md
        assert "react_full" in md
        assert "90.0%" in md

    def test_contains_layer_breakdown(self):
        r = BaselineReport(
            baseline="react_full",
            metrics={
                "success_by_layer": {
                    "unit": {"total": 10, "success": 10, "rate": 1.0},
                    "integration": {"total": 12, "success": 10, "rate": 0.833},
                    "stress": {"total": 8, "success": 5, "rate": 0.625},
                }
            },
        )
        md = self._render([r])
        assert "## Layer Breakdown" in md
        assert "unit" in md
        assert "integration" in md
        assert "stress" in md

    def test_layer_breakdown_not_available(self):
        r = BaselineReport(baseline="bare_llm", metrics={})
        md = self._render([r])
        assert "## Layer Breakdown" in md
        assert NOT_AVAILABLE in md

    def test_contains_agent_metrics(self):
        r = BaselineReport(
            baseline="react_full",
            metrics={"verification_pass_rate": 0.8, "edit_precision_rate": 0.7},
        )
        md = self._render([r])
        assert "## Agent-Specific Metrics" in md
        assert "80.0%" in md

    def test_ci_disclaimer_present(self):
        r = BaselineReport(baseline="react_full", metrics={})
        md = self._render([r], ci=True)
        assert CI_DISCLAIMER in md

    def test_ci_disclaimer_absent(self):
        r = BaselineReport(baseline="react_full", metrics={})
        md = self._render([r], ci=False)
        assert "CI/mock mode" not in md

    def test_multi_baseline_rows(self):
        r1 = BaselineReport(baseline="react_full", task_count=30, metrics={"task_success_rate": 0.9})
        r2 = BaselineReport(baseline="bare_llm", task_count=30, metrics={"task_success_rate": 0.0})
        md = self._render([r1, r2])
        assert "react_full" in md
        assert "bare_llm" in md

    def test_missing_metrics_not_zero(self):
        r = BaselineReport(baseline="bare_llm", metrics={})
        md = self._render([r])
        # Should show not_available, not 0
        lines = md.split("\n")
        table_lines = [l for l in lines if l.startswith("| bare_llm")]
        assert len(table_lines) >= 1
        assert NOT_AVAILABLE in table_lines[0]

    def test_baseline_in_output(self):
        r = BaselineReport(baseline="my_custom_baseline", metrics={})
        md = self._render([r])
        assert "my_custom_baseline" in md

    def test_known_limitations(self):
        r = BaselineReport(baseline="react_full", metrics={})
        md = self._render([r])
        assert "## Known Limitations" in md
        assert "not_available" in md


# ═══════════════════════════════════════════
# 5. render_single_report
# ═══════════════════════════════════════════


class TestRenderSingleReport:
    def test_renders_v21(self):
        md = render_single_report(V21_REPORT)
        assert "react_full" in md
        assert "# CodePilot Agent Benchmark Report" in md

    def test_renders_v20(self):
        md = render_single_report(V20_REPORT)
        assert NOT_AVAILABLE in md
        assert "# CodePilot Agent Benchmark Report" in md


# ═══════════════════════════════════════════
# 6. write_report
# ═══════════════════════════════════════════


class TestWriteReport:
    def test_write_md(self, tmp_dir):
        r = BaselineReport(baseline="react_full", metrics={"task_success_rate": 0.9})
        report = BenchmarkReport(reports=[r], generated_at="2026-07-04")
        md_path = tmp_dir / "report.md"
        write_report(report, output_md=str(md_path))
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "CodePilot Agent Benchmark Report" in content

    def test_write_json(self, tmp_dir):
        r = BaselineReport(baseline="react_full", task_count=30, metrics={"task_success_rate": 0.9})
        report = BenchmarkReport(reports=[r], generated_at="2026-07-04")
        json_path = tmp_dir / "report.json"
        write_report(report, output_json=str(json_path))
        assert json_path.exists()
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["version"] == "3.0"
        assert data["baselines"][0]["baseline"] == "react_full"

    def test_write_creates_parent_dirs(self, tmp_dir):
        r = BaselineReport(baseline="react_full", metrics={})
        report = BenchmarkReport(reports=[r], generated_at="2026-07-04")
        md_path = tmp_dir / "sub" / "dir" / "report.md"
        write_report(report, output_md=str(md_path))
        assert md_path.exists()

    def test_write_both(self, tmp_dir):
        r = BaselineReport(baseline="react_full", metrics={})
        report = BenchmarkReport(reports=[r], generated_at="2026-07-04")
        md_path = tmp_dir / "report.md"
        json_path = tmp_dir / "report.json"
        write_report(report, output_json=str(json_path), output_md=str(md_path))
        assert md_path.exists()
        assert json_path.exists()
