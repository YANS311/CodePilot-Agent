from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.skills.loader import SkillLoader
from app.skills.manager import SkillManager
from app.skills.models import Skill, SkillMetadata
from app.skills.selector import SkillSelector


class TestRepositoryExplorerSkill:
    """RepositoryExplorerSkill 规范与加载测试。"""

    @pytest.fixture
    def skill_path(self) -> Path:
        return PROJECT_ROOT / "skills" / "repository-explorer" / "SKILL.md"

    @pytest.fixture
    def skills_dir(self) -> Path:
        return PROJECT_ROOT / "skills"

    def test_skill_file_exists(self, skill_path: Path):
        """1. 验证 Skill 文件真实存在且非空。"""
        assert skill_path.exists(), f"Skill file does not exist: {skill_path}"
        assert skill_path.is_file(), f"Skill path is not a file: {skill_path}"
        assert skill_path.stat().st_size > 0, "Skill file is empty"

    def test_frontmatter_parsed_by_skill_loader(self, skill_path: Path):
        """2. 验证 Frontmatter 可以被 SkillLoader 成功解析。"""
        content = skill_path.read_text(encoding="utf-8")
        meta, body = SkillLoader.parse_frontmatter(content)

        assert bool(meta), "Failed to parse frontmatter from SKILL.md"
        assert meta.get("name") == "repository-explorer"
        assert meta.get("description") == (
            "Analyze unfamiliar software repositories by identifying architecture, "
            "technology stack, entry points and execution call chains."
        )

        tags = meta.get("tags", [])
        assert "repo-exploration" in tags
        assert "architecture-analysis" in tags
        assert "entrypoint-discovery" in tags
        assert "call-chain" in tags
        assert "codebase-understanding" in tags
        assert "understand codebase" in meta.get("trigger_keywords", [])

        # 验证 SOP 关键章节存在
        assert "Purpose" in body
        assert "When to activate" in body
        assert "Workflow" in body
        assert "Phase 1: Technology Stack Discovery" in body
        assert "Phase 2: Architecture Discovery" in body
        assert "Phase 3: Entry Point Discovery" in body
        assert "Phase 4: Execution Flow Analysis" in body

        # 验证输出模板要素存在
        assert "# Project Overview" in body
        assert "# Technology Stack" in body
        assert "# Directory Architecture" in body
        assert "# Entry Points" in body
        assert "# Execution Flow" in body
        assert "# Extension Points" in body
        assert "# Risks" in body

    def test_skill_manager_scan_and_discovery(self, skills_dir: Path):
        """3 & 4. 验证 SkillManager 在真实目录下可以扫描发现该 Skill。"""
        manager = SkillManager(skills_dir=skills_dir)
        meta = manager.get_metadata("repository-explorer")

        assert meta is not None, "SkillManager failed to discover 'repository-explorer'"
        assert meta.name == "repository-explorer"
        assert "repo-exploration" in meta.tags
        assert "梳理项目架构" in meta.trigger_keywords
        assert meta.version == "1.0.0"

        # 验证按需加载 Skill 正文
        skill = manager.get_skill("repository-explorer")
        assert skill is not None, "SkillManager failed to load 'repository-explorer' body"
        assert isinstance(skill, Skill)
        assert skill.name == "repository-explorer"
        assert "read_file" in skill.instructions

        # 验证注入 prompt 内容格式有效
        prompt_instruction = skill.to_prompt_instruction()
        assert "[Active Skill: repository-explorer]" in prompt_instruction
        assert "Phase 1: Technology Stack Discovery" in prompt_instruction

    def test_skill_activation_matching(self, skills_dir: Path):
        """5. 验证基于任务描述和技能标签能够准确匹配并激活该 Skill。"""
        manager = SkillManager(skills_dir=skills_dir)

        # 显式技能名称触发
        matched_by_name = manager.match_and_load_for_task("Please use repository-explorer to analyze this codebase")
        assert matched_by_name is not None
        assert matched_by_name.name == "repository-explorer"

        # 连字符替换为空格名称触发
        matched_by_space_name = manager.match_and_load_for_task("Perform repository explorer on the project")
        assert matched_by_space_name is not None
        assert matched_by_space_name.name == "repository-explorer"

        # 核心标签触发
        matched_by_tag = manager.match_and_load_for_task("Perform repo-exploration and call-chain mapping")
        assert matched_by_tag is not None
        assert matched_by_tag.name == "repository-explorer"

        matched_by_trigger = manager.match_and_load_for_task("Help me understand codebase structure")
        assert matched_by_trigger is not None
        assert matched_by_trigger.name == "repository-explorer"
