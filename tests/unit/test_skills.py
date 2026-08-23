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
        assert len(skills) >= 6
        assert "bug-fix" in skills
        assert "code-review" in skills
        assert "test-debugging" in skills
        assert "security-audit" in skills
        assert "api-spec-validator" in skills
        assert "git-workflow" in skills

        bug_fix = skills["bug-fix"]
        assert bug_fix.name == "bug-fix"
        assert "defect" in bug_fix.description.lower() or "fix" in bug_fix.description.lower()

    def test_load_level3_resources(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 验证 security-audit 的 scripts 与 references
        sec_skill = mgr.get_skill("security-audit")
        assert sec_skill is not None
        assert "secret_scanner.py" in sec_skill.scripts
        assert "owasp_cwe_cheatsheet.md" in sec_skill.references

        prompt_str = sec_skill.to_prompt_instruction()
        assert "Available Helper Scripts" in prompt_str
        assert "secret_scanner.py" in prompt_str
        assert "Available Domain References" in prompt_str
        assert "owasp_cwe_cheatsheet.md" in prompt_str


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
        skill = mgr.match_and_load_for_task("Review the git diff for code quality")
        assert skill is not None
        assert skill.name == "code-review"

    def test_skill_selection_security_audit(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 security audit 任务
        skill = mgr.match_and_load_for_task("Perform a security audit for SQL injection and hardcoded secret keys")
        assert skill is not None
        assert skill.name == "security-audit"
        assert "secret_scanner.py" in skill.scripts

    def test_skill_selection_api_spec_validator(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 API 路由与契约校验任务
        skill = mgr.match_and_load_for_task("Validate FastAPI route contracts and OpenAPI schema status codes")
        assert skill is not None
        assert skill.name == "api-spec-validator"
        assert "route_linter.py" in skill.scripts

    def test_skill_selection_git_workflow(self):
        skills_dir = PROJECT_ROOT / "skills"
        mgr = SkillManager(skills_dir=skills_dir)

        # 匹配 Git 冲突与提交规范任务
        skill = mgr.match_and_load_for_task("Check git rebase conflict markers and format conventional commit")
        assert skill is not None
        assert skill.name == "git-workflow"
        assert "conflict_detector.py" in skill.scripts

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
        assert "security-audit" in summary
        assert "api-spec-validator" in summary
        assert "git-workflow" in summary


class TestSkillHelperScriptsExecution:
    @staticmethod
    def _import_script(script_rel_path: str):
        import importlib.util
        script_full_path = PROJECT_ROOT / script_rel_path
        spec = importlib.util.spec_from_file_location("skill_helper", str(script_full_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_secret_scanner_execution(self, tmp_path):
        sec_mod = self._import_script("skills/security-audit/scripts/secret_scanner.py")

        # 创建一个测试文件包含假密钥与高危动态执行
        vuln_file = tmp_path / "vulnerable_sample.py"
        vuln_file.write_text(
            'API_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
            'result = eval("2 + 2")\n',
            encoding="utf-8"
        )

        findings = sec_mod.scan_path(tmp_path)
        assert len(findings) >= 2
        rule_ids = [f["rule_id"] for f in findings]
        assert "SEC002" in rule_ids or "SEC003" in rule_ids  # AWS or API Key
        assert "SEC005" in rule_ids  # eval/exec

    def test_route_linter_execution(self, tmp_path):
        route_mod = self._import_script("skills/api-spec-validator/scripts/route_linter.py")

        api_file = tmp_path / "mock_routes.py"
        api_file.write_text(
            'from fastapi import FastAPI\n'
            'app = FastAPI()\n'
            '@app.get("/items")\n'
            'def list_items():\n'
            '    return [{"id": 1}]\n',
            encoding="utf-8"
        )

        routes, issues = route_mod.lint_file(api_file)
        assert len(routes) == 1
        assert routes[0]["method"] == "GET"
        assert routes[0]["path"] == "/items"
        assert len(issues) >= 1
        assert issues[0]["code"] == "API001"

    def test_conflict_detector_execution(self, tmp_path):
        conflict_mod = self._import_script("skills/git-workflow/scripts/conflict_detector.py")

        conflict_file = tmp_path / "merge_conflict.py"
        conflict_file.write_text(
            '<<<<<<< HEAD\n'
            'def add(a, b):\n'
            '    return a + b\n'
            '=======\n'
            'def add(x, y):\n'
            '    return x + y\n'
            '>>>>>>> feature-branch\n',
            encoding="utf-8"
        )

        conflicts = conflict_mod.scan_file_conflicts(conflict_file)
        assert len(conflicts) == 1
        assert conflicts[0]["our_branch"] == "HEAD"
        assert conflicts[0]["their_branch"] == "feature-branch"

