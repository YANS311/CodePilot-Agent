"""Error Taxonomy — 评测错误类型分类。"""

from __future__ import annotations

from enum import Enum


class ErrorType(str, Enum):
    """Agent 执行错误类型。"""

    # 模型把工具调用写在文本里，而不是调用真实 tool_call
    TOOL_CALL_FORMAT_DRIFT = "tool_call_format_drift"

    # 路径选择错误
    PATH_RESOLUTION_ERROR = "path_resolution_error"

    # 修改后未执行 run_tests
    TEST_NOT_EXECUTED = "test_not_executed"

    # 执行了测试但测试失败
    TEST_FAILED = "test_failed"

    # 达到最大工具调用次数
    MAX_TOOL_CALLS_EXCEEDED = "max_tool_calls_exceeded"

    # 未实际修改文件
    NO_CODE_CHANGE = "no_code_change"

    # git diff 不可用或 workspace 不是 git repo
    DIFF_UNAVAILABLE = "diff_unavailable"

    # 未知错误
    UNKNOWN = "unknown"


# 错误类型 → 中文描述
ERROR_DESCRIPTIONS: dict[ErrorType, str] = {
    ErrorType.TOOL_CALL_FORMAT_DRIFT: "模型将工具调用写入文本而非真实执行",
    ErrorType.PATH_RESOLUTION_ERROR: "文件路径解析错误",
    ErrorType.TEST_NOT_EXECUTED: "修改后未执行测试验证",
    ErrorType.TEST_FAILED: "执行了测试但测试失败",
    ErrorType.MAX_TOOL_CALLS_EXCEEDED: "达到最大工具调用次数上限",
    ErrorType.NO_CODE_CHANGE: "未实际修改任何文件",
    ErrorType.DIFF_UNAVAILABLE: "git diff 不可用",
    ErrorType.UNKNOWN: "未知错误",
}
