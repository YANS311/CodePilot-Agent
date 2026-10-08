"""app/skills/selector.py — 基于任务意图与关键词的 Skill 选择器。

确保只在任务与 Skill 强相关时才激活并加载该 Skill，
防止所有 Skill 无差别注入导致 Context 膨胀与 Attention 稀释。
"""

from __future__ import annotations

import re
from typing import Dict, Optional

from app.skills.models import SkillMetadata


def _contains_keyword(text: str, kw: str) -> bool:
    """检查文本中是否包含关键词。对纯英文单词采用词边界匹配，避免如 capital 误匹配 api。"""
    kw = kw.strip().lower()
    if not kw:
        return False

    # 若关键词为纯英文/数字/下划线/连字符单词，使用词边界匹配
    if re.match(r"^[a-zA-Z0-9_\-]+$", kw):
        # 兼容连字符与下划线作为分隔符
        pattern = rf"(?:\b|_){re.escape(kw)}(?:\b|_)"
        return bool(re.search(pattern, text))

    # 多词短语或中文直接使用子串匹配
    return kw in text


class SkillSelector:
    """任务与 Skill 匹配选择器。"""

    @classmethod
    def select_skill(
        cls,
        task: str,
        available_skills: Dict[str, SkillMetadata],
    ) -> Optional[SkillMetadata]:
        """根据用户任务描述，选取最契合的一个 Skill（若无明确匹配则返回 None）。"""
        if not available_skills or not task:
            return None

        task_lower = task.lower()
        best_skill: Optional[SkillMetadata] = None
        highest_score = 0

        for skill_name, meta in available_skills.items():
            score = 0
            # 1. 显式技能名提及
            if _contains_keyword(task_lower, skill_name) or _contains_keyword(task_lower, skill_name.replace("-", " ")):
                score += 10

            # 2. Skill 自声明触发词匹配
            for kw in meta.trigger_keywords:
                if _contains_keyword(task_lower, kw):
                    score += 2

            # 3. 标签匹配
            for tag in meta.tags:
                if _contains_keyword(task_lower, tag):
                    score += 3

            if score > highest_score:
                highest_score = score
                best_skill = meta

        # 阈值控制：至少得分 >= 2 才视为命中
        if highest_score >= 2:
            return best_skill

        return None
