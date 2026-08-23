from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.tool import ToolCall
from app.security.permission import PermissionAction, PermissionPolicy
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.write_file import WriteFileTool

WORKSPACE = str(PROJECT_ROOT / "workspace")


class TestPermissionPolicy:
    def test_permission_actions_enum(self):
        assert PermissionAction.READ == "READ"
        assert PermissionAction.WRITE == "WRITE"
        assert PermissionAction.EXECUTE == "EXECUTE"
        assert PermissionAction.NETWORK == "NETWORK"
        assert PermissionAction.GIT_MUTATE == "GIT_MUTATE"

    def test_read_only_policy(self):
        policy = PermissionPolicy.read_only()
        assert policy.is_action_allowed(PermissionAction.READ) is True
        assert policy.is_action_allowed(PermissionAction.WRITE) is False
        assert policy.is_action_allowed(PermissionAction.EXECUTE) is False

        ok, msg = policy.check_tool_permission("read_file", {"path": "hello.py"})
        assert ok is True

        ok_write, msg_write = policy.check_tool_permission("write_file", {"path": "hello.py", "content": "..."})
        assert ok_write is False
        assert "PERMISSION_DENIED" in msg_write

        ok_test, msg_test = policy.check_tool_permission("run_tests", {})
        assert ok_test is False
        assert "PERMISSION_DENIED" in msg_test

    def test_standard_coding_policy(self):
        policy = PermissionPolicy.standard_coding()
        assert policy.is_action_allowed(PermissionAction.READ) is True
        assert policy.is_action_allowed(PermissionAction.WRITE) is True
        assert policy.is_action_allowed(PermissionAction.EXECUTE) is True

        ok_write, _ = policy.check_tool_permission("write_file", {})
        assert ok_write is True

    def test_registry_enforcement_read_only_blocks_write_tool(self):
        """验证 ToolRegistry 在执行工具前执行 PermissionPolicy 强拦截。"""
        async def _run():
            reg = ToolRegistry()
            reg.register(ReadFileTool())
            reg.register(WriteFileTool())

            read_only_policy = PermissionPolicy.read_only()

            # 1. 读操作允许
            tc_read = ToolCall(name="read_file", arguments={"path": "conftest.py"})
            res_read = await reg.execute(tc_read, WORKSPACE, permission_policy=read_only_policy)
            assert res_read.success is True

            # 2. 写操作被 PermissionPolicy 强拦截
            tc_write = ToolCall(name="write_file", arguments={"path": "test_output.txt", "content": "hi"})
            res_write = await reg.execute(tc_write, WORKSPACE, permission_policy=read_only_policy)
            assert res_write.success is False
            assert "PERMISSION_DENIED" in res_write.output
            assert res_write.metadata.get("permission_blocked") is True

        asyncio.run(_run())
