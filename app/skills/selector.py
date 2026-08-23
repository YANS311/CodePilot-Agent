"""app/skills/selector.py — 基于任务意图与关键词的 Skill 选择器。

确保只在任务与 Skill 强相关时才激活并加载该 Skill，
防止所有 Skill 无差别注入导致 Context 膨胀与 Attention 稀释。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from app.skills.models import SkillMetadata


# 内置意图关键词规则表
_SKILL_KEYWORD_RULES: Dict[str, List[str]] = {
    "bug-fix": [
        "bug", "fix", "repair", "defect", "failing", "fails", "failed",
        "error", "exception", "broken", "issue", "crash", "wrong result",
        "修复", "报错", "异常", "排查", "缺陷",
    ],
    "code-review": [
        "review", "diff", "inspect", "audit", "security review", "pr",
        "pull request", "refactor check", "code quality", "审查", "评审", "评估",
    ],
    "test-debugging": [
        "test debug", "failing test", "flaky", "pytest", "unit test",
        "test failure", "assert", "assertion", "traceback", "调试测试", "用例失败",
    ],
}


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
            if skill_name.lower() in task_lower or skill_name.replace("-", " ") in task_lower:
                score += 10

            # 2. 规则关键词匹配
            rules = _SKILL_KEYWORD_RULES.get(skill_name, [])
            for kw in rules:
                if kw in task_lower:
                    score += 2

            # 3. 标签匹配
            for tag in meta.tags:
                if tag.lower() in task_lower:
                    score += 3

            if score > highest_score:
                highest_score = score
                best_skill = meta

        # 阈值控制：至少得分 >= 2 才视为命中
        if highest_score >= 2:
            return best_skill

        return None
