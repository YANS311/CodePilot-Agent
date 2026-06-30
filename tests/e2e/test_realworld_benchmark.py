"""Tests for the real-world bug benchmark infrastructure.

Validates that:
1. tasks.json is well-formed with 15 tasks
2. All 3 repos have expected file structure
3. All seeded bugs produce test failures
4. The benchmark runner works in dry-run mode
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BENCH_DIR = ROOT / "benchmarks" / "real_world"
REPOS_DIR = BENCH_DIR / "repos"
TASKS_FILE = BENCH_DIR / "tasks.json"


# ── tasks.json validation ──


class TestTasksJson:
    def test_exists(self):
        assert TASKS_FILE.exists(), "tasks.json not found"

    def test_has_15_tasks(self):
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        assert len(data["tasks"]) == 15

    def test_difficulty_distribution(self):
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        by_diff = {}
        for t in data["tasks"]:
            by_diff.setdefault(t["difficulty"], []).append(t["id"])
        assert len(by_diff.get("easy", [])) == 6
        assert len(by_diff.get("medium", [])) == 6
        assert len(by_diff.get("hard", [])) == 3

    def test_all_repos_covered(self):
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        repos = {t["repo"] for t in data["tasks"]}
        assert repos == {"todo_api", "calculator_pkg", "config_parser"}

    def test_each_task_has_required_fields(self):
        data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
        required = {"id", "repo", "difficulty", "title", "description",
                     "files_to_modify", "test_command", "expected_test"}
        for t in data["tasks"]:
            missing = required - set(t.keys())
            assert not missing, f"Task {t.get('id')}: missing {missing}"


# ── Repo structure validation ──


class TestRepoStructure:
    def test_todo_api_files(self):
        base = REPOS_DIR / "todo_api"
        assert (base / "app" / "service.py").exists()
        assert (base / "app" / "models.py").exists()
        assert (base / "app" / "storage.py").exists()
        assert (base / "app" / "main.py").exists()
        assert (base / "tests" / "test_todo_api.py").exists()

    def test_calculator_pkg_files(self):
        base = REPOS_DIR / "calculator_pkg"
        assert (base / "calculator" / "__init__.py").exists()
        assert (base / "calculator" / "core.py").exists()
        assert (base / "calculator" / "advanced.py").exists()
        assert (base / "tests" / "test_core.py").exists()
        assert (base / "tests" / "test_advanced.py").exists()

    def test_config_parser_files(self):
        base = REPOS_DIR / "config_parser"
        assert (base / "cfgparser" / "__init__.py").exists()
        assert (base / "cfgparser" / "loader.py").exists()
        assert (base / "cfgparser" / "validator.py").exists()
        assert (base / "cfgparser" / "env.py").exists()
        assert (base / "tests" / "test_loader.py").exists()
        assert (base / "tests" / "test_validator.py").exists()
        assert (base / "tests" / "test_env.py").exists()


# ── Seeded bug verification ──


class TestSeededBugs:
    """Each repo should have tests that fail due to seeded bugs."""

    def test_todo_api_has_failures(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=no", "-q"],
            cwd=str(REPOS_DIR / "todo_api"),
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0, "Expected test failures in todo_api"
        assert "failed" in result.stdout.lower()

    def test_calculator_pkg_has_failures(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=no", "-q"],
            cwd=str(REPOS_DIR / "calculator_pkg"),
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0, "Expected test failures in calculator_pkg"
        assert "failed" in result.stdout.lower()

    def test_config_parser_has_failures(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=no", "-q"],
            cwd=str(REPOS_DIR / "config_parser"),
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode != 0, "Expected test failures in config_parser"
        assert "failed" in result.stdout.lower()


# ── Benchmark runner ──


class TestBenchmarkRunner:
    def test_dry_run(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_realworld_eval.py",
             "--dry-run", "--tasks", "todo-01"],
            cwd=str(ROOT),
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout

    def test_runner_script_exists(self):
        assert (ROOT / "scripts" / "run_realworld_eval.py").exists()
