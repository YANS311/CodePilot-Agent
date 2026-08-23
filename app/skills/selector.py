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
    "security-audit": [
        "security audit", "vulnerability", "secret", "hardcoded", "sql injection",
        "cwe", "owasp", "leak", "api key", "credentials", "xss", "csrf",
        "安全审计", "漏洞", "敏感信息", "注入", "泄露", "弱点",
    ],
    "api-spec-validator": [
        "api spec", "openapi", "rest api", "fastapi route", "route validation",
        "schema validation", "endpoint contract", "status code", "pydantic model",
        "接口规范", "路由校验", "契约", "接口文档",
    ],
    "git-workflow": [
        "git workflow", "merge conflict", "rebase conflict", "conventional commit",
        "git conflict", "branch hygiene", "changelog", "commit message",
        "代码冲突", "合并冲突", "提交规范", "分支管理",
    ],
}


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

            # 2. 规则关键词匹配
            rules = _SKILL_KEYWORD_RULES.get(skill_name, [])
            for kw in rules:
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
