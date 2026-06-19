"""D17 Tests — Demo Scenarios 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.demo.scenarios import DemoScenario, get_demo, list_demos, DEMO_SCENARIOS


# ═══════════════════════════════════════════
# 1. Demo list
# ═══════════════════════════════════════════


class TestDemoList:
    def test_list_returns_three(self):
        demos = list_demos()
        assert len(demos) == 3

    def test_all_have_ids(self):
        demos = list_demos()
        for d in demos:
            assert d.id
            assert d.id.startswith("demo-")

    def test_all_have_names(self):
        demos = list_demos()
        for d in demos:
            assert d.name

    def test_all_have_tasks(self):
        demos = list_demos()
        for d in demos:
            assert d.task
            assert len(d.task) > 10

    def test_all_have_descriptions(self):
        demos = list_demos()
        for d in demos:
            assert d.description


# ═══════════════════════════════════════════
# 2. Get demo
# ═══════════════════════════════════════════


class TestGetDemo:
    def test_get_valid(self):
        demo = get_demo("demo-bug-fix")
        assert demo is not None
        assert demo.category == "bug_fix"

    def test_get_repo_analysis(self):
        demo = get_demo("demo-repo-analysis")
        assert demo is not None
        assert demo.category == "repo_analysis"

    def test_get_security(self):
        demo = get_demo("demo-security")
        assert demo is not None
        assert demo.category == "security"

    def test_get_invalid(self):
        demo = get_demo("nonexistent")
        assert demo is None


# ═══════════════════════════════════════════
# 3. Categories
# ═══════════════════════════════════════════


class TestCategories:
    def test_valid_categories(self):
        valid = {"bug_fix", "repo_analysis", "security"}
        demos = list_demos()
        for d in demos:
            assert d.category in valid, f"Invalid category: {d.category}"

    def test_unique_ids(self):
        demos = list_demos()
        ids = [d.id for d in demos]
        assert len(ids) == len(set(ids))

    def test_unique_categories(self):
        demos = list_demos()
        cats = [d.category for d in demos]
        assert len(cats) == len(set(cats))


# ═══════════════════════════════════════════
# 4. Scenario content
# ═══════════════════════════════════════════


class TestScenarioContent:
    def test_bug_fix_mentions_calculator(self):
        demo = get_demo("demo-bug-fix")
        assert "calculator" in demo.task.lower() or "buggy" in demo.task.lower()

    def test_repo_analysis_mentions_architecture(self):
        demo = get_demo("demo-repo-analysis")
        assert "架构" in demo.task or "architecture" in demo.task.lower()

    def test_security_mentions_injection(self):
        demo = get_demo("demo-security")
        assert "规则" in demo.task or "admin" in demo.task.lower()

    def test_expected_behaviors_present(self):
        demos = list_demos()
        for d in demos:
            assert d.expected_behavior
            assert len(d.expected_behavior) > 5
