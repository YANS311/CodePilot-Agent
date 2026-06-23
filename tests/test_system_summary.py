"""D29 Tests — System compression & interview readiness validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════
# 1. system_summary.md exists and is valid
# ═══════════════════════════════════════════


class TestSystemSummary:
    def test_file_exists(self):
        path = PROJECT_ROOT / "docs" / "system_summary.md"
        assert path.exists()

    def test_has_one_line_definition(self):
        path = PROJECT_ROOT / "docs" / "system_summary.md"
        content = path.read_text(encoding="utf-8")
        assert "Evidence-grounded" in content

    def test_has_4_layer_architecture(self):
        path = PROJECT_ROOT / "docs" / "system_summary.md"
        content = path.read_text(encoding="utf-8")
        assert "Agent Layer" in content
        assert "Execution Layer" in content
        assert "Intelligence Layer" in content
        assert "Evaluation & Safety Layer" in content

    def test_has_key_numbers(self):
        path = PROJECT_ROOT / "docs" / "system_summary.md"
        content = path.read_text(encoding="utf-8")
        assert "396" in content or "374" in content  # unit tests
        assert "30" in content  # eval tasks
        assert "6" in content  # tools


# ═══════════════════════════════════════════
# 2. interview_onepager.md exists and is valid
# ═══════════════════════════════════════════


class TestInterviewOnePager:
    def test_file_exists(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        assert path.exists()

    def test_has_5_sections(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8")
        assert "What I Built" in content
        assert "Why This System" in content
        assert "Architecture" in content
        assert "Demo Flow" in content
        assert "Three Core Highlights" in content

    def test_has_unified_demo_flow(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8")
        assert "Upload → Index → Agent → Tool → Execute → Evidence → Result" in content

    def test_has_three_highlights(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8")
        assert "Evaluation System" in content
        assert "Evidence Grounding" in content
        assert "Security Guardrails" in content

    def test_no_complex_expressions(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8").lower()
        assert "mcp" not in content
        assert "multi-agent" not in content
        assert "plugin system" not in content
        assert "memory system" not in content


# ═══════════════════════════════════════════
# 3. Demo runner convergence
# ═══════════════════════════════════════════


class TestDemoRunnerConvergence:
    def test_demo_runner_exists(self):
        path = PROJECT_ROOT / "scripts" / "demo_runner.py"
        assert path.exists()

    def test_exactly_3_demos(self):
        path = PROJECT_ROOT / "scripts" / "demo_runner.py"
        content = path.read_text(encoding="utf-8")
        # Count demo definitions in DEMOS list
        assert '"bug-fix"' in content
        assert '"repo-analysis"' in content
        assert '"security-test"' in content

    def test_no_new_demo_types(self):
        path = PROJECT_ROOT / "scripts" / "demo_runner.py"
        content = path.read_text(encoding="utf-8")
        # Should not have more than 3 demo IDs
        demo_count = content.count('"id":')
        assert demo_count == 3


# ═══════════════════════════════════════════
# 4. Metrics explanation completeness
# ═══════════════════════════════════════════


class TestMetricsExplanation:
    def test_interview_onepager_explains_metrics(self):
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8")
        # Must explain why each metric exists
        assert "What it proves" in content

    def test_metrics_are_measurable(self):
        """All metrics mentioned must have concrete values or be computable."""
        path = PROJECT_ROOT / "docs" / "interview_onepager.md"
        content = path.read_text(encoding="utf-8")
        # TSR should have a value
        assert "90%" in content
        # Security should have a value
        assert "100%" in content


# ═══════════════════════════════════════════
# 5. Architecture consistency
# ═══════════════════════════════════════════


class TestArchitectureConsistency:
    def test_system_summary_matches_onepager(self):
        s1 = (PROJECT_ROOT / "docs" / "system_summary.md").read_text(encoding="utf-8")
        s2 = (PROJECT_ROOT / "docs" / "interview_onepager.md").read_text(encoding="utf-8")
        # Both should mention the same 4 layers
        for layer in ["Agent Layer", "Execution Layer", "Intelligence Layer", "Evaluation"]:
            assert layer in s1, f"system_summary.md missing {layer}"
            assert layer in s2, f"interview_onepager.md missing {layer}"

    def test_demo_flow_consistent(self):
        s1 = (PROJECT_ROOT / "docs" / "system_summary.md").read_text(encoding="utf-8")
        s2 = (PROJECT_ROOT / "docs" / "interview_onepager.md").read_text(encoding="utf-8")
        flow = "Upload → Index → Agent → Tool → Execute → Evidence → Result"
        # At least one of them should have the full flow
        assert flow in s1 or flow in s2


# ═══════════════════════════════════════════
# 6. No complex expressions in对外文档
# ═══════════════════════════════════════════


class TestNoComplexExpressions:
    def _check_file(self, rel_path: str):
        path = PROJECT_ROOT / rel_path
        if not path.exists():
            return  # skip non-existent files
        content = path.read_text(encoding="utf-8").lower()
        assert "mcp" not in content, f"{rel_path} contains 'mcp'"
        assert "multi-agent" not in content, f"{rel_path} contains 'multi-agent'"
        assert "plugin system" not in content, f"{rel_path} contains 'plugin system'"
        assert "memory system" not in content, f"{rel_path} contains 'memory system'"

    def test_readme_clean(self):
        self._check_file("README.md")

    def test_system_summary_clean(self):
        self._check_file("docs/system_summary.md")

    def test_onepager_clean(self):
        self._check_file("docs/interview_onepager.md")


# ═══════════════════════════════════════════
# 7. Gitignore includes new docs
# ═══════════════════════════════════════════


class TestGitignore:
    def test_new_docs_gitignored(self):
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "interview_deep_dive.md" in gitignore
        assert "interview_questions.md" in gitignore
        assert "interview_final.md" in gitignore
        assert "interview_defense.md" in gitignore
