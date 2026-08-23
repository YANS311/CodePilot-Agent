from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager
from app.skills.models import Skill, SkillMetadata
from app.skills.selector import SkillSelector


class TestSkillLoader:
    def test_parse_valid_frontmatter(self):
        content = """---
name: sample-skill
description: A sample procedural skill
version: 1.2.0
tags: [demo, test]
---
# Step 1: Do something
Execute carefully.
"""
        meta, body = SkillLoader.parse_frontmatter(content)
        assert meta["name"] == "sample-skill"
        assert meta["description"] == "A sample procedural skill"
        assert meta["version"] == "1.2.0"
        assert "Step 1: Do something" in body

    def test_parse_malformed_frontmatter_fallback(self):
        content = """No frontmatter here, just markdown body.
# Header
"""
        meta, body = SkillLoader.parse_frontmatter(content)
        assert meta == {}
        assert "No frontmatter here" in body

    def test_scan_built_in_skills(self):
        skills_dir = PROJECT_ROOT / "skills"
        skills = SkillLoader.scan_skills(skills_dir)
        assert len(skills) >= 3
        assert "bug-fix" in skills
        assert "code-review" in skills
        assert "test-debugging" in skills

        bug_fix = skills["bug-fix"]
        assert bug_fix.name == "bug-fix"
        assert "defect" in bug_fix.description.lower() or "fix" in bug_fix.description.lower()


class TestSkillSelectorAndProgressiveDisclosure:
    def test_skill_selection_bug_fix(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 bug 修复类任务
        skill = mgr.match_and_load_for_task("Fix the failing test in calculator add method")
        assert skill is not None
        assert skill.name == "bug-fix"
        assert "Procedural Knowledge: Bug Fixing Workflow" in skill.instructions

    def test_skill_selection_code_review(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 review 类任务
        skill = mgr.match_and_load_for_task("Review the git diff for security vulnerabilities")
        assert skill is not None
        assert skill.name == "code-review"

    def test_skill_selection_test_debugging(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 test debugging 任务
        skill = mgr.match_and_load_for_task("Debug the failing test assertion in test_api")
        assert skill is not None
        assert skill.name in ["test-debugging", "bug-fix"]

    def test_unrelated_task_no_skill_injected(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 无关闲聊任务不应触发任何 Skill 注入 (Progressive Disclosure)
        skill = mgr.match_and_load_for_task("What is the capital of France?")
        assert skill is None

    def test_system_prompt_skills_summary_level1(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        summary = mgr.build_system_prompt_skills_summary()
        assert "Available Procedural Skills" in summary
        assert "bug-fix" in summary
        assert "code-review" in summary
