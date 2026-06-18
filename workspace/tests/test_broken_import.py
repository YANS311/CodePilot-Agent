"""broken_import 模块测试 — 验证 import 可以正常工作。"""


def test_broken_import_can_import():
    """验证 broken_import 模块可以被正常导入。"""
    from examples.broken_import import hello
    assert hello() == "hello"
