"""ErrorAnalyzer — 根据 EvalResult 自动判断 error_type。"""

from __future__ import annotations

import re

from app.evaluation.error_taxonomy import ErrorType
from app.evaluation.schema import EvalResult

# 检测文本中伪造的工具调用
_TOOL_CALL_PATTERNS = [
    re.compile(r"write_file\s*\(", re.IGNORECASE),
    re.compile(r"read_file\s*\(", re.IGNORECASE),
    re.compile(r"search_code\s*\(", re.IGNORECASE),
    re.compile(r"run_tests\s*\(", re.IGNORECASE),
    re.compile(r"Action:\s*write_file", re.IGNORECASE),
    re.compile(r"<｜｜DSML｜｜invoke\s+name=\"write_file\"", re.IGNORECASE),
]


def analyze_error(result: EvalResult, max_tool_calls: int = 20) -> EvalResult:
    """分析 EvalResult，填充 error_type 和 error_reason。

    规则按优先级从高到低匹配。
    """
    # 已成功则不分析
    if result.success:
        return result

    # 1. TOOL_CALL_FORMAT_DRIFT — 达到上限 + 文本中包含伪造工具调用
    if result.tool_calls_count >= max_tool_calls:
        for pattern in _TOOL_CALL_PATTERNS:
            if pattern.search(result.final_answer):
                result.error_type = ErrorType.TOOL_CALL_FORMAT_DRIFT.value
                result.error_reason = (
                    "达到工具调用上限后，模型将 write_file 调用写入文本而非真实执行"
                )
                return result
        result.error_type = ErrorType.MAX_TOOL_CALLS_EXCEEDED.value
        result.error_reason = f"达到最大工具调用次数 ({max_tool_calls})"
        return result

    # 2. NO_CODE_CHANGE — 没有调用过 write_file
    has_write = any(
        tr.name == "write_file" and tr.success
        for tr in []  # tool_results 不在 EvalResult 中，用 answer 判断
    )
    write_in_answer = bool(re.search(r"write_file", result.final_answer, re.IGNORECASE))
    if not write_in_answer and not has_write:
        # 检查 answer 是否声称修复了
        claim_words = ["修复", "修改", "fixed", "modified", "已修复", "完成"]
        claims_fix = any(w in result.final_answer for w in claim_words)
        if claims_fix:
            result.error_type = ErrorType.NO_CODE_CHANGE.value
            result.error_reason = "声称修复但未实际调用 write_file"
            return result

    # 3. TEST_NOT_EXECUTED — 没有调用 run_tests
    run_tests_in_answer = bool(
        re.search(r"run_tests", result.final_answer, re.IGNORECASE)
    )
    if not run_tests_in_answer and not result.test_success:
        result.error_type = ErrorType.TEST_NOT_EXECUTED.value
        result.error_reason = "修改后未执行 run_tests 验证"
        return result

    # 4. TEST_FAILED — 执行了测试但失败
    if not result.test_success and result.tool_calls_count > 0:
        result.error_type = ErrorType.TEST_FAILED.value
        result.error_reason = (
            f"测试执行失败: passed={result.passed}, failed={result.failed}"
        )
        return result

    # 5. 兜底
    result.error_type = ErrorType.UNKNOWN.value
    result.error_reason = "未能自动归因"
    return result
