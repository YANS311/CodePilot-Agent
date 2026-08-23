"""app/skills/manager.py — Skills 统一运行时生命周期管理器。

统一协调 Level 1 元数据缓存、Level 2 渐进式注入与 Level 3 资源读取。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.skills.loader import SkillLoader
from app.skills.models import Skill, SkillMetadata
from app.skills.selector import SkillSelector

logger = logging.getLogger(__name__)


class SkillManager:
    """Skill 运行时统一治理中心。"""

    def __init__(self, skills_dir: Optional[str | Path] = None) -> None:
        self.skills_dir = Path(skills_dir or "skills")
        self._metadata_cache: Dict[str, SkillMetadata] = {}
        self._loaded_skills: Dict[str, Skill] = {}
        self.refresh_skills()

    def refresh_skills(self) -> int:
        """扫描技能目录并刷新 Level 1 元数据缓存。"""
        self._metadata_cache = SkillLoader.scan_skills(self.skills_dir)
        self._loaded_skills.clear()
        logger.info("SkillManager indexed %d skills from '%s'", len(self._metadata_cache), self.skills_dir)
        return len(self._metadata_cache)

    def list_metadata(self) -> List[SkillMetadata]:
        """获取所有可用技能的 Level 1 元数据。"""
        return list(self._metadata_cache.values())

    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """获取指定技能的元数据。"""
        return self._metadata_cache.get(name)

    def get_skill(self, name: str) -> Optional[Skill]:
        """获取并按需加载指定技能的 Level 2/3 完整实例。"""
        if name in self._loaded_skills:
            return self._loaded_skills[name]

        meta = self._metadata_cache.get(name)
        if not meta:
            return None

        skill = SkillLoader.load_skill_body(meta)
        if skill:
            self._loaded_skills[name] = skill
        return skill

    def match_and_load_for_task(self, task: str) -> Optional[Skill]:
        """核心渐进式揭示接口：根据任务选择最匹配的 Skill 并加载其 Instructions。"""
        selected_meta = SkillSelector.select_skill(task, self._metadata_cache)
        if not selected_meta:
            return None
        return self.get_skill(selected_meta.name)

    def build_system_prompt_skills_summary(self) -> str:
        """生成供 Agent 初始感知使用的轻量级 Level 1 技能清单 (仅含名字与简述)。"""
        if not self._metadata_cache:
            return ""

        summaries = [meta.to_summary() for meta in self._metadata_cache.values()]
        return (
            "\n\n### Available Procedural Skills (Loaded On-Demand):\n"
            + "\n".join(summaries)
            + "\n(The Harness will automatically inject detailed workflows when relevant to your task.)\n"
        )


# 全局单例
skill_manager = SkillManager()
