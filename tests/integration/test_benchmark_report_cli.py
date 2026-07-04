"""Tests for scripts/generate_benchmark_report.py — CLI integration.

Covers:
- --from-json mode generates Markdown
- --baseline-files merges multiple JSONs
- --output-json produces valid JSON
- --ci-disclaimer forces disclaimer
- Missing file returns error
- --from-json does not run eval
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = str(PROJECT_ROOT / "scripts" / "generate_benchmark_report.py")
PYTHON = sys.executable

V21_REPORT = {
    "version": "2.1",
    "timestamp": "2026-07-04T00:00:00",
    "baseline": "react_full",
    "layer": "all",
    "tasks": [
        {"task_id": "t1", "success": True, "tool_calls_count": 3, "passed": 2, "failed": 0},
    ],
    "metrics": {
        "total_tasks": 1,
        "successful_tasks": 1,
        "task_success_rate": 1.0,
        "pass_at_1": 1.0,
        "avg_tool_calls": 3.0,
        "verification_pass_rate": 0.5,
        "edit_precision_rate": 0.75,
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
    },
}


@pytest.fixture
def v21_file(tmp_path):
    p = tmp_path / "v21.json"
    p.write_text(json.dumps(V21_REPORT), encoding="utf-8")
    return str(p)


@pytest.fixture
def v20_file(tmp_path):
    p = tmp_path / "v20.json"
    p.write_text(json.dumps(V20_REPORT), encoding="utf-8")
    return str(p)


@pytest.fixture
def v21_file_b(tmp_path):
    """Second baseline file for merge tests."""
    data = dict(V21_REPORT)
    data["baseline"] = "bare_llm"
    p = tmp_path / "v21_b.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, SCRIPT, *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


# ═══════════════════════════════════════════
# 1. --from-json mode
# ═══════════════════════════════════════════


class TestFromJsonMode:
    def test_generates_markdown(self, v21_file, tmp_path):
        md_path = str(tmp_path / "out.md")
        result = _run_cli("--from-json", v21_file, "--output-md", md_path)
        assert result.returncode == 0, result.stderr
        content = Path(md_path).read_text(encoding="utf-8")
        assert "CodePilot Agent Benchmark Report" in content
        assert "react_full" in content

    def test_stdout_when_no_output(self, v21_file):
        result = _run_cli("--from-json", v21_file)
        assert result.returncode == 0, result.stderr
        assert "CodePilot Agent Benchmark Report" in result.stdout

    def test_no_eval_runner_import(self, v21_file):
        """from-json mode should not import EvaluationRunner."""
        result = _run_cli("--from-json", v21_file)
        assert result.returncode == 0
        # The script should not mention running tasks
        assert "Running task:" not in result.stderr


# ═══════════════════════════════════════════
# 2. --baseline-files mode
# ═══════════════════════════════════════════


class TestBaselineFilesMode:
    def test_merges_two_files(self, v21_file, v21_file_b, tmp_path):
        md_path = str(tmp_path / "merged.md")
        result = _run_cli(
            "--baseline-files", v21_file, v21_file_b,
            "--output-md", md_path,
        )
        assert result.returncode == 0, result.stderr
        content = Path(md_path).read_text(encoding="utf-8")
        assert "react_full" in content
        assert "bare_llm" in content

    def test_generates_json(self, v21_file, v21_file_b, tmp_path):
        json_path = str(tmp_path / "out.json")
        result = _run_cli(
            "--baseline-files", v21_file, v21_file_b,
            "--output-json", json_path,
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert data["version"] == "3.0"
        assert len(data["baselines"]) == 2


# ═══════════════════════════════════════════
# 3. --output-json
# ═══════════════════════════════════════════


class TestOutputJson:
    def test_json_has_version_3(self, v21_file, tmp_path):
        json_path = str(tmp_path / "out.json")
        result = _run_cli("--from-json", v21_file, "--output-json", json_path)
        assert result.returncode == 0, result.stderr
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        assert data["version"] == "3.0"
        assert "generated_at" in data
        assert "baselines" in data


# ═══════════════════════════════════════════
# 4. --ci-disclaimer
# ═══════════════════════════════════════════


class TestCiDisclaimer:
    def test_forced_disclaimer(self, v21_file, tmp_path):
        md_path = str(tmp_path / "out.md")
        result = _run_cli(
            "--from-json", v21_file,
            "--output-md", md_path,
            "--ci-disclaimer",
        )
        assert result.returncode == 0, result.stderr
        content = Path(md_path).read_text(encoding="utf-8")
        assert "CI/mock mode" in content

    def test_no_disclaimer_by_default(self, v21_file, tmp_path):
        md_path = str(tmp_path / "out.md")
        result = _run_cli("--from-json", v21_file, "--output-md", md_path)
        assert result.returncode == 0, result.stderr
        content = Path(md_path).read_text(encoding="utf-8")
        assert "CI/mock mode" not in content


# ═══════════════════════════════════════════
# 5. Missing file error
# ═══════════════════════════════════════════


class TestMissingFile:
    def test_missing_from_json(self):
        result = _run_cli("--from-json", "/nonexistent/path.json")
        assert result.returncode != 0

    def test_missing_baseline_files(self, v21_file):
        result = _run_cli(
            "--baseline-files", v21_file, "/nonexistent/path.json",
        )
        assert result.returncode != 0


# ═══════════════════════════════════════════
# 6. V2.0 backward compatibility
# ═══════════════════════════════════════════


class TestV20Compat:
    def test_v20_from_json(self, v20_file, tmp_path):
        md_path = str(tmp_path / "out.md")
        result = _run_cli("--from-json", v20_file, "--output-md", md_path)
        assert result.returncode == 0, result.stderr
        content = Path(md_path).read_text(encoding="utf-8")
        assert "not_available" in content
