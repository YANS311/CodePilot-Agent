"""Tests for CodeEditTool — surgical code editing.

Covers:
- Unique match replacement
- old not found → EDIT_TARGET_NOT_FOUND
- Multiple matches without occurrence → EDIT_TARGET_AMBIGUOUS
- occurrence specified → replace only that match
- occurrence out of range → EDIT_OCCURRENCE_OUT_OF_RANGE
- Workspace path traversal blocked
- Binary file blocked
- Newline preservation
- before_hash / after_hash in response
- Integration with verification loop (code_edit triggers run_tests)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.code_edit import (
    CodeEditTool,
    EDIT_TARGET_NOT_FOUND,
    EDIT_TARGET_AMBIGUOUS,
    EDIT_OCCURRENCE_OUT_OF_RANGE,
    EDIT_BINARY_FILE,
)
from app.tools.registry import ToolRegistry
from app.tools.write_file import WriteFileTool
from app.tools.run_tests import RunTestsTool
from app.tools.read_file import ReadFileTool
from app.models.tool import ToolCall
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.agent.react_agent import ReActAgent
from app.agent.verification import VerificationPolicy


@pytest.fixture
def tmp_ws(tmp_path):
    """Create a temp workspace with a test file."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def _write_file(ws: Path, rel_path: str, content: str) -> Path:
    """Helper to write a file in the workspace."""
    target = ws / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


# ═══════════════════════════════════════════
# 1. Unique match — success
# ═══════════════════════════════════════════


class TestUniqueMatch:
    def test_replace_unique_match(self, tmp_ws):
        _write_file(tmp_ws, "calc.py", "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a + b\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="def subtract(a, b):\n    return a + b",
            new="def subtract(a, b):\n    return a - b",
        ))
        data = json.loads(result)
        assert data["success"] is True
        assert data["changed"] is True
        assert data["replacement_count"] == 1
        assert "before_hash" in data
        assert "after_hash" in data
        assert data["before_hash"] != data["after_hash"]

        # Verify file content
        content = (tmp_ws / "calc.py").read_text()
        assert "return a - b" in content
        assert "return a + b" in content  # add() unchanged

    def test_replace_preserves_surrounding_code(self, tmp_ws):
        original = "line 1\nline 2\nline 3\nline 4\nline 5\n"
        _write_file(tmp_ws, "file.py", original)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="file.py",
            old="line 3",
            new="LINE THREE",
        ))
        data = json.loads(result)
        assert data["success"] is True
        content = (tmp_ws / "file.py").read_text()
        assert content == "line 1\nline 2\nLINE THREE\nline 4\nline 5\n"


# ═══════════════════════════════════════════
# 2. old not found
# ═══════════════════════════════════════════


class TestNotFound:
    def test_old_not_found(self, tmp_ws):
        _write_file(tmp_ws, "calc.py", "def add(a, b):\n    return a + b\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="def nonexistent():\n    pass",
            new="def fixed():\n    pass",
        ))
        data = json.loads(result)
        assert data["error_code"] == EDIT_TARGET_NOT_FOUND
        assert "未找到" in data["message"]

    def test_file_not_exist(self, tmp_ws):
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="nonexistent.py",
            old="old",
            new="new",
        ))
        assert "不存在" in result


# ═══════════════════════════════════════════
# 3. Multiple matches without occurrence
# ═══════════════════════════════════════════


class TestAmbiguousMatch:
    def test_multiple_matches_no_occurrence(self, tmp_ws):
        content = "return a + b\n\ndef add2(a, b):\n    return a + b\n"
        _write_file(tmp_ws, "calc.py", content)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
        ))
        data = json.loads(result)
        assert data["error_code"] == EDIT_TARGET_AMBIGUOUS
        assert data["match_count"] == 2
        assert "occurrence" in data["message"]


# ═══════════════════════════════════════════
# 4. Occurrence specified
# ═══════════════════════════════════════════


class TestOccurrenceSpecified:
    def test_replace_second_occurrence(self, tmp_ws):
        content = "return a + b\n\ndef add2(a, b):\n    return a + b\n"
        _write_file(tmp_ws, "calc.py", content)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
            occurrence=2,
        ))
        data = json.loads(result)
        assert data["success"] is True
        assert data["occurrence_used"] == 2

        file_content = (tmp_ws / "calc.py").read_text()
        # First occurrence unchanged
        assert file_content.startswith("return a + b")
        # Second occurrence changed
        assert "return a - b" in file_content

    def test_replace_first_occurrence(self, tmp_ws):
        content = "return a + b\n\ndef add2(a, b):\n    return a + b\n"
        _write_file(tmp_ws, "calc.py", content)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
            occurrence=1,
        ))
        data = json.loads(result)
        assert data["success"] is True

        file_content = (tmp_ws / "calc.py").read_text()
        lines = file_content.split("\n")
        assert lines[0] == "return a - b"  # first changed
        assert lines[3] == "    return a + b"  # second unchanged


# ═══════════════════════════════════════════
# 5. Occurrence out of range
# ═══════════════════════════════════════════


class TestOccurrenceOutOfRange:
    def test_occurrence_zero(self, tmp_ws):
        _write_file(tmp_ws, "calc.py", "return a + b\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
            occurrence=0,
        ))
        data = json.loads(result)
        assert data["error_code"] == EDIT_OCCURRENCE_OUT_OF_RANGE

    def test_occurrence_too_large(self, tmp_ws):
        content = "return a + b\nreturn a + b\n"
        _write_file(tmp_ws, "calc.py", content)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
            occurrence=5,
        ))
        data = json.loads(result)
        assert data["error_code"] == EDIT_OCCURRENCE_OUT_OF_RANGE
        assert data["match_count"] == 2


# ═══════════════════════════════════════════
# 6. Workspace path traversal blocked
# ═══════════════════════════════════════════


class TestPathTraversal:
    def test_traversal_blocked(self, tmp_ws):
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="../../../etc/passwd",
            old="root",
            new="hacked",
        ))
        assert "超出 workspace" in result

    def test_dotgit_blocked(self, tmp_ws):
        ws = tmp_ws
        (ws / ".git").mkdir()
        _write_file(ws, ".git/config", "[core]\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(ws),
            path=".git/config",
            old="[core]",
            new="[hacked]",
        ))
        assert "禁止编辑 .git" in result


# ═══════════════════════════════════════════
# 7. Binary file blocked
# ═══════════════════════════════════════════


class TestBinaryFile:
    def test_binary_extension_blocked(self, tmp_ws):
        _write_file(tmp_ws, "image.png", b"\x89PNG\r\n\x1a\n".decode("latin-1"))
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="image.png",
            old="PNG",
            new="JPG",
        ))
        data = json.loads(result)
        assert data["error_code"] == EDIT_BINARY_FILE


# ═══════════════════════════════════════════
# 8. Newline preservation
# ═══════════════════════════════════════════


class TestNewlinePreservation:
    def test_lf_preserved(self, tmp_ws):
        content = "line1\nline2\nline3\n"
        _write_file(tmp_ws, "unix.py", content)
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="unix.py",
            old="line2",
            new="LINE2",
        ))
        data = json.loads(result)
        assert data["success"] is True
        file_content = (tmp_ws / "unix.py").read_text()
        assert "\r\n" not in file_content
        assert "LINE2" in file_content


# ═══════════════════════════════════════════
# 9. Hash verification
# ═══════════════════════════════════════════


class TestHashVerification:
    def test_hashes_different_after_edit(self, tmp_ws):
        _write_file(tmp_ws, "calc.py", "def add(a, b):\n    return a + b\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a - b",
        ))
        data = json.loads(result)
        assert data["before_hash"] != data["after_hash"]
        assert len(data["before_hash"]) == 16
        assert len(data["after_hash"]) == 16

    def test_same_content_same_hash(self, tmp_ws):
        """Replacing old with identical new should produce same hash."""
        _write_file(tmp_ws, "calc.py", "def add(a, b):\n    return a + b\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="return a + b",
            new="return a + b",
        ))
        data = json.loads(result)
        assert data["before_hash"] == data["after_hash"]
        assert data["changed"] is True  # replacement happened, even if content same


# ═══════════════════════════════════════════
# 10. Empty old / new edge cases
# ═══════════════════════════════════════════


class TestEdgeCases:
    def test_delete_by_empty_new(self, tmp_ws):
        """old replaced with empty string = deletion."""
        _write_file(tmp_ws, "calc.py", "line1\nline2\nline3\n")
        tool = CodeEditTool()
        result = asyncio.run(tool.run(
            workspace_root=str(tmp_ws),
            path="calc.py",
            old="line2\n",
            new="",
        ))
        data = json.loads(result)
        assert data["success"] is True
        content = (tmp_ws / "calc.py").read_text()
        assert "line2" not in content
        assert "line1" in content
        assert "line3" in content


# ═══════════════════════════════════════════
# 11. code_edit triggers verification run_tests
# ═══════════════════════════════════════════


class TestCodeEditVerification:
    def test_code_edit_triggers_verification(self, tmp_ws):
        """After code_edit, verification should trigger run_tests."""
        _write_file(tmp_ws, "calc.py", "def add(a, b):\n    return a + b\n")

        llm = AsyncMock(spec=LLMClient)
        llm.chat = AsyncMock(side_effect=[
            ChatResponse(tool_calls=[
                ToolCallInfo(id="tc1", name="code_edit", arguments={
                    "path": "calc.py",
                    "old": "return a + b",
                    "new": "return a - b",
                }),
            ]),
            ChatResponse(content="Fixed."),
        ])

        registry = ToolRegistry()
        registry.register(CodeEditTool())
        registry.register(ReadFileTool())
        registry.register(RunTestsTool())
        registry.register(WriteFileTool())

        run_tests_called = []

        original_execute = registry.execute

        async def tracking_execute(tool_call, workspace_root, guardrail=None):
            if tool_call.name == "run_tests":
                run_tests_called.append(True)
                from app.models.tool import ToolResult
                return ToolResult(
                    tool_call_id=tool_call.id, name="run_tests",
                    success=True,
                    output=json.dumps({"success": True, "passed": 1, "failed": 0}),
                )
            return await original_execute(tool_call, workspace_root, guardrail=guardrail)

        registry.execute = tracking_execute

        policy = VerificationPolicy(enabled=True, max_retries=1)
        agent = ReActAgent(llm, registry, str(tmp_ws), verification_policy=policy)
        result = asyncio.run(agent.run("fix the add function"))

        assert len(run_tests_called) >= 1, "code_edit should trigger verification"
        assert result.verification_passed is True
        assert result.wrote_file is True


# ═══════════════════════════════════════════
# 12. Registry integration
# ═══════════════════════════════════════════


class TestRegistryIntegration:
    def test_code_edit_registered(self):
        registry = ToolRegistry()
        registry.register(CodeEditTool())
        assert registry.get("code_edit") is not None
        schemas = registry.get_schemas()
        names = [s["function"]["name"] for s in schemas]
        assert "code_edit" in names
