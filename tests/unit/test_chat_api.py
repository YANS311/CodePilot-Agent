from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.main import app
from app.agent.react_agent import AgentRunResult
from app.models.tool import ToolResult
from app.core.config import settings
from app.core.workspace_lock import WorkspaceLockManager

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
        data = resp.json()
        assert data["status"] == "ok"
        assert "agent" in data


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
        assert data["task_id"] == mock_agent.run.await_args.kwargs["task_id"]
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


@pytest.mark.parametrize(
    ("first_route", "second_route"),
    [("/api/chat", "/api/chat/stream"), ("/api/chat/stream", "/api/chat")],
)
def test_chat_routes_share_workspace_lock(monkeypatch, tmp_path, first_route, second_route):
    async def exercise():
        manager = WorkspaceLockManager()
        entered = asyncio.Event()
        release = asyncio.Event()
        seen_ids = {}
        monkeypatch.setattr(settings, "workspace_root", tmp_path)
        other_workspace = tmp_path / "uploads" / "other"
        other_workspace.mkdir(parents=True)

        async def run(task, *, task_id):
            seen_ids[task] = task_id
            if task == "first":
                entered.set()
                await release.wait()
            return AgentRunResult(answer=task)

        agent = AsyncMock()
        agent.run.side_effect = run
        monkeypatch.setattr("app.api.chat.get_lock_manager", lambda: manager)
        monkeypatch.setattr("app.api.chat._build_agent", lambda workspace_root: agent)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            first = asyncio.create_task(api.post(first_route, json={"task": "first"}))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                status = (await api.get("/api/lock/status")).json()
                assert status["task_id"] == seen_ids["first"]
                conflict = await api.post(second_route, json={"task": "second"})
                assert conflict.status_code == 409
                assert set(conflict.json()) == {"detail"}
                assert "second" not in seen_ids

                parallel = await api.post("/api/chat", json={"task": "parallel", "workspace_id": "other"})
                assert parallel.status_code == 200
                assert parallel.json()["task_id"] == seen_ids["parallel"]
            finally:
                release.set()
                response = await asyncio.wait_for(first, timeout=5)
            assert response.status_code == 200
            assert seen_ids["first"] in response.text
            retry = await api.post(second_route, json={"task": "retry"})
            assert retry.status_code == 200
            assert seen_ids["retry"] in retry.text
            assert (await api.get("/api/lock/status")).json()["status"] == "unlocked"

    asyncio.run(exercise())


@pytest.mark.parametrize("route", ["/api/chat", "/api/chat/stream"])
def test_cancelling_chat_releases_workspace(monkeypatch, tmp_path, route):
    async def exercise():
        manager = WorkspaceLockManager()
        entered = asyncio.Event()
        monkeypatch.setattr(settings, "workspace_root", tmp_path)

        async def run(task, *, task_id):
            entered.set()
            await asyncio.Future()

        agent = AsyncMock()
        agent.run.side_effect = run
        monkeypatch.setattr("app.api.chat.get_lock_manager", lambda: manager)
        monkeypatch.setattr("app.api.chat._build_agent", lambda workspace_root: agent)

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as api:
            request = asyncio.create_task(api.post(route, json={"task": "cancelled"}))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
            finally:
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
            assert (await api.get("/api/lock/status")).json()["status"] == "unlocked"

    asyncio.run(exercise())


@patch("app.api.chat._build_agent")
def test_chat_error_matches_public_response_contract(mock_build):
    agent = AsyncMock()
    agent.run.side_effect = RuntimeError("internal detail")
    mock_build.return_value = agent

    response = client.post("/api/chat", json={"task": "test error response"})
    assert response.status_code == 500
    assert response.json() == {"detail": "任务执行失败。"}
    assert client.get("/api/lock/status").json()["status"] == "unlocked"
