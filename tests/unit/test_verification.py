"""Tests for Self-Verifying Agent (v0.4.3).

Covers:
- VerificationPolicy defaults and disabled()
- Agent triggers run_tests after write_file
- Agent retries on test failure and succeeds
- max_retries prevents infinite loop
- Verification disabled = old behavior
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.react_agent import ReActAgent, AgentRunResult
from app.agent.verification import VerificationPolicy
from app.agent.error_event import AgentErrorEvent
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.tools.read_file import ReadFileTool
from app.tools.write_file import WriteFileTool
from app.tools.run_tests import RunTestsTool
from app.tools.registry import ToolRegistry
from app.models.tool import ToolCall

import tempfile

WORKSPACE = str(PROJECT_ROOT / "workspace")


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(ReadFileTool())
    reg.register(WriteFileTool())
    reg.register(RunTestsTool())
    return reg


def _mock_llm(responses: list) -> LLMClient:
    """Create a mock LLMClient that returns responses in sequence."""
    llm = AsyncMock(spec=LLMClient)
    llm.chat = AsyncMock(side_effect=responses)
    return llm


# ═══════════════════════════════════════════
# 1. VerificationPolicy defaults
# ═══════════════════════════════════════════


class TestVerificationPolicyDefaults:
    def test_default_values(self):
        policy = VerificationPolicy()
        assert policy.enabled is False  # opt-in, not opt-out
        assert policy.max_retries == 2
        assert policy.test_command is None
        assert policy.stop_on_pass is True

    def test_enabled_explicitly(self):
        policy = VerificationPolicy(enabled=True)
        assert policy.enabled is True

    def test_disabled_factory(self):
        policy = VerificationPolicy.disabled()
        assert policy.enabled is False
        assert policy.max_retries == 2  # other fields keep defaults

    def test_custom_values(self):
        policy = VerificationPolicy(
            enabled=True, max_retries=5, test_command="tests/test_foo.py", stop_on_pass=False
        )
        assert policy.max_retries == 5
        assert policy.test_command == "tests/test_foo.py"
        assert policy.stop_on_pass is False


# ═══════════════════════════════════════════
# 2. Agent triggers run_tests after write_file
# ═══════════════════════════════════════════


class TestVerificationTrigger:
    def test_run_tests_triggered_after_write(self):
        """When agent writes a file and verification is enabled,
        run_tests is automatically called."""
        llm = _mock_llm([
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="write_file", arguments={
                    "path": "examples/buggy_calculator.py",
                    "content": "# fixed code\n",
                }),
            ]),
            ChatResponse(content="Fixed the code."),
        ])

        registry = _make_registry()
        run_tests_called = []

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "run_tests":
                run_tests_called.append(True)
                return ToolResult(
                    tool_call_id=tool_call.id, name="run_tests",
                    success=True,
                    output=json.dumps({"success": True, "passed": 1, "failed": 0}),
                )
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry.execute = mock_execute

        policy = VerificationPolicy(enabled=True, max_retries=2)
        agent = ReActAgent(llm, registry, WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("fix the calculator bug"))

        assert len(run_tests_called) >= 1, "run_tests should be called after write_file"
        assert result.verification_passed is True

    def test_no_verification_when_disabled(self):
        """When verification is disabled, no run_tests is called after write."""
        llm = _mock_llm([
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="write_file", arguments={
                    "path": "examples/buggy_calculator.py",
                    "content": "# fixed code\n",
                }),
            ]),
            ChatResponse(content="Fixed the code."),
        ])

        registry = _make_registry()
        run_tests_called = []

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "run_tests":
                run_tests_called.append(True)
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry.execute = mock_execute

        policy = VerificationPolicy.disabled()
        agent = ReActAgent(llm, registry, WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("fix the calculator bug"))

        assert len(run_tests_called) == 0, "run_tests should NOT be called when disabled"
        assert result.verification_passed is False
        assert result.verification_retries == 0

    def test_no_verification_when_no_write(self):
        """When agent doesn't write any file, verification is skipped."""
        llm = _mock_llm([
            ChatResponse(content="No changes needed, code is fine."),
        ])

        registry = _make_registry()
        run_tests_called = []

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "run_tests":
                run_tests_called.append(True)
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry.execute = mock_execute

        policy = VerificationPolicy(enabled=True)
        agent = ReActAgent(llm, registry, WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("what does this code do?"))

        assert len(run_tests_called) == 0
        assert result.wrote_file is False


# ═══════════════════════════════════════════
# 3. First test fails → agent retries → passes
# ═══════════════════════════════════════════


class TestVerificationRetry:
    def test_retry_on_failure_then_pass(self):
        """Agent writes file, tests fail, agent fixes, tests pass."""
        call_count = [0]

        async def mock_chat(messages, *, tools=None, temperature=0.0):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: write file
                return ChatResponse(tool_calls=[
                    ToolCallInfo(id="tc1", name="write_file", arguments={
                        "path": "examples/buggy_calculator.py",
                        "content": "# attempt 1\n",
                    }),
                ])
            elif call_count[0] == 2:
                # After test failure injection, agent writes again
                return ChatResponse(tool_calls=[
                    ToolCallInfo(id="tc2", name="write_file", arguments={
                        "path": "examples/buggy_calculator.py",
                        "content": "# attempt 2 - fixed\n",
                    }),
                ])
            else:
                # Done
                return ChatResponse(content="Fixed after test failure.")

        llm = AsyncMock(spec=LLMClient)
        llm.chat = mock_chat

        test_call_count = [0]

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "write_file":
                # Write to a temp location so it doesn't affect real files
                return ToolResult(
                    tool_call_id=tool_call.id, name="write_file",
                    success=True, output="written",
                )
            if tool_call.name == "run_tests":
                test_call_count[0] += 1
                if test_call_count[0] == 1:
                    # First test run fails
                    return ToolResult(
                        tool_call_id=tool_call.id, name="run_tests",
                        success=False,
                        output=json.dumps({"success": False, "passed": 0, "failed": 1, "stderr": "AssertionError"}),
                    )
                else:
                    # Second test run passes
                    return ToolResult(
                        tool_call_id=tool_call.id, name="run_tests",
                        success=True,
                        output=json.dumps({"success": True, "passed": 1, "failed": 0}),
                    )
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry = _make_registry()
        registry.execute = mock_execute

        policy = VerificationPolicy(enabled=True, max_retries=2)
        agent = ReActAgent(llm, registry, WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("fix the bug"))

        assert result.verification_passed is True
        assert result.verification_retries == 1  # failed once, passed on retry
        assert test_call_count[0] == 2  # tests ran twice


# ═══════════════════════════════════════════
# 4. max_retries prevents infinite loop
# ═══════════════════════════════════════════


class TestMaxRetries:
    def test_max_retries_enforced(self):
        """Agent should stop after max_retries even if tests keep failing."""
        # Use a pattern: odd calls → write_file, even calls → text (done)
        # This lets the main loop end after 1 tool call, then verification
        # injects failure, continuation writes again, etc.
        call_count = [0]

        async def mock_chat(messages, *, tools=None, temperature=0.0):
            call_count[0] += 1
            c = call_count[0]
            if c % 2 == 1:
                # Odd call: write file
                return ChatResponse(tool_calls=[
                    ToolCallInfo(id=f"tc{c}", name="write_file", arguments={
                        "path": "examples/buggy_calculator.py",
                        "content": f"# fix attempt {c}\n",
                    }),
                ])
            else:
                # Even call: text response (end loop)
                return ChatResponse(content=f"Attempt {c - 1} done.")

        llm = AsyncMock(spec=LLMClient)
        llm.chat = mock_chat

        test_call_count = [0]

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "write_file":
                return ToolResult(
                    tool_call_id=tool_call.id, name="write_file",
                    success=True, output="written",
                )
            if tool_call.name == "run_tests":
                test_call_count[0] += 1
                # Always fail
                return ToolResult(
                    tool_call_id=tool_call.id, name="run_tests",
                    success=False,
                    output=json.dumps({"success": False, "passed": 0, "failed": 1}),
                )
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry = _make_registry()
        registry.execute = mock_execute

        max_retries = 2
        policy = VerificationPolicy(enabled=True, max_retries=max_retries)
        agent = ReActAgent(
            llm, registry, WORKSPACE,
            max_tool_calls=20,
            verification_policy=policy,
        )
        result = asyncio.run(agent.run("fix the bug"))

        assert result.verification_passed is False
        assert result.verification_retries == max_retries
        # Should have run tests max_retries + 1 times (initial + retries)
        assert test_call_count[0] == max_retries + 1

        # Check error events recorded
        verify_events = [e for e in result.error_events if e.module == "verification"]
        assert len(verify_events) >= 1
        last_event = verify_events[-1]
        assert last_event.recovery_action == "max_retries_exhausted"


# ═══════════════════════════════════════════
# 5. Verification disabled = old behavior
# ═══════════════════════════════════════════


class TestVerificationDisabled:
    def test_disabled_no_verification_fields(self):
        """With verification disabled, result has default verification fields."""
        llm = _mock_llm([
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="write_file", arguments={
                    "path": "examples/buggy_calculator.py",
                    "content": "# code\n",
                }),
            ]),
            ChatResponse(content="Done."),
        ])

        policy = VerificationPolicy.disabled()
        agent = ReActAgent(llm, _make_registry(), WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("fix the bug"))

        assert result.verification_passed is False
        assert result.verification_retries == 0
        assert result.test_result == ""
        assert result.wrote_file is True  # still tracked


# ═══════════════════════════════════════════
# 6. Error events recorded during verification
# ═══════════════════════════════════════════


class TestVerificationObservability:
    def test_error_events_on_test_failure(self):
        """Test failures are recorded as AgentErrorEvent."""
        call_count = [0]

        async def mock_chat(messages, *, tools=None, temperature=0.0):
            call_count[0] += 1
            if call_count[0] == 1:
                return ChatResponse(tool_calls=[
                    ToolCallInfo(id="tc1", name="write_file", arguments={
                        "path": "examples/buggy_calculator.py",
                        "content": "# code\n",
                    }),
                ])
            return ChatResponse(content="Gave up.")

        llm = AsyncMock(spec=LLMClient)
        llm.chat = mock_chat

        async def mock_execute(tool_call, workspace_root, guardrail=None):
            from app.models.tool import ToolResult
            if tool_call.name == "write_file":
                return ToolResult(
                    tool_call_id=tool_call.id, name="write_file",
                    success=True, output="written",
                )
            if tool_call.name == "run_tests":
                return ToolResult(
                    tool_call_id=tool_call.id, name="run_tests",
                    success=False,
                    output=json.dumps({"success": False, "failed": 2}),
                )
            return ToolResult(
                tool_call_id=tool_call.id, name=tool_call.name,
                success=True, output="ok",
            )

        registry = _make_registry()
        registry.execute = mock_execute

        policy = VerificationPolicy(enabled=True, max_retries=1)
        agent = ReActAgent(llm, registry, WORKSPACE, verification_policy=policy)
        result = asyncio.run(agent.run("fix the bug"))

        verify_events = [e for e in result.error_events if e.module == "verification"]
        assert len(verify_events) >= 1

        first_event = verify_events[0]
        assert first_event.error_type == "TestFailure"
        assert first_event.tool_name == "run_tests"
        assert "attempt" in first_event.context
