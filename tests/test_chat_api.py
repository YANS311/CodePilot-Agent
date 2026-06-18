from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.agent.react_agent import AgentRunResult
from app.models.tool import ToolResult
from app.core.llm_client import ChatResponse

client = TestClient(app)


# ═══════════════════════════════════════════
# 1. GET / 返回 HTML
# ═══════════════════════════════════════════


class TestIndexPage:
    def test_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "CodePilot Agent" in resp.text


# ═══════════════════════════════════════════
# 2. GET /health 仍然正常
# ═══════════════════════════════════════════


class TestHealthStillWorks:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ═══════════════════════════════════════════
# 3. POST /api/chat 正常返回
# ═══════════════════════════════════════════


class TestChatAPI:
    @patch("app.api.chat._build_agent")
    def test_chat_returns_answer(self, mock_build):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = AgentRunResult(
            answer="测试回答",
            tool_calls_count=2,
            tool_results=[
                ToolResult(tool_call_id="tc1", name="search_code", success=True, output="搜索结果"),
                ToolResult(tool_call_id="tc2", name="read_file", success=True, output="文件内容"),
            ],
            messages=[{"role": "system", "content": "..."}],
        )
        mock_build.return_value = mock_agent

        resp = client.post("/api/chat", json={"task": "测试任务"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "测试回答"
        assert data["tool_calls_count"] == 2
        assert len(data["tool_results"]) == 2
        assert data["tool_results"][0]["name"] == "search_code"

    def test_chat_empty_task_returns_error(self):
        resp = client.post("/api/chat", json={"task": ""})
        assert resp.status_code == 422  # Pydantic validation

    def test_chat_missing_task_returns_error(self):
        resp = client.post("/api/chat", json={})
        assert resp.status_code == 422


# ═══════════════════════════════════════════
# 4. POST /api/chat/stream 返回 SSE
# ═══════════════════════════════════════════


class TestChatStream:
    @patch("app.api.chat._build_agent")
    def test_stream_returns_sse(self, mock_build):
        mock_agent = AsyncMock()
        mock_agent.run.return_value = AgentRunResult(
            answer="流式回答",
            tool_calls_count=1,
            tool_results=[
                ToolResult(tool_call_id="tc1", name="read_file", success=True, output="文件内容"),
            ],
            messages=[],
        )
        mock_build.return_value = mock_agent

        resp = client.post("/api/chat/stream", json={"task": "流式测试"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        body = resp.text
        assert "event: start" in body
        assert "event: tool_result" in body
        assert "event: final" in body
        assert "流式回答" in body
