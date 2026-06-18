"""一个有 import 错误的模块，用于测试 Agent 的修复能力。"""

from nonexistent_module import something  # This import will fail


def hello():
    return "hello"
