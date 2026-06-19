"""input_guardrail.py — 用户输入（提示词）安全检查。

检测提示注入攻击，如"忽略之前规则"、"你是系统管理员"等。
"""

from __future__ import annotations

import logging
import re

from app.security.taxonomy import (
    INJECTION_PATTERNS,
    GuardrailResult,
    RiskType,
)

logger = logging.getLogger(__name__)


def analyze_prompt(task: str) -> GuardrailResult:
    """分析用户任务描述，检测提示注入攻击。

    使用关键词/模式匹配，无需 LLM 调用。
    """
    if not task:
        return GuardrailResult(allow=True)

    text = task.lower().strip()

    for pattern in INJECTION_PATTERNS:
        if pattern.lower() in text:
            logger.warning("Prompt injection detected: pattern='%s'", pattern)
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.PROMPT_INJECTION,
                reason=f"检测到提示注入攻击: 包含 '{pattern}'",
            )

    # 检测常见注入结构模式
    injection_structures = [
        r"ignore\s+(all|every|previous|above)\s+(rules?|instructions?|guidelines?)",
        r"you\s+are\s+now\s+",
        r"from\s+now\s+on\s+",
        r"pretend\s+(you\s+are|to\s+be)",
        r"act\s+as\s+(?:a\s+)?(?:admin|hacker|root|system)",
        r"disregard\s+(all|previous|above)",
        r"override\s+(your|all|the)\s+(rules?|instructions?)",
    ]

    for struct_pattern in injection_structures:
        if re.search(struct_pattern, text):
            logger.warning("Prompt injection structure detected: %s", struct_pattern)
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.PROMPT_INJECTION,
                reason=f"检测到提示注入攻击模式",
            )

    return GuardrailResult(allow=True)
