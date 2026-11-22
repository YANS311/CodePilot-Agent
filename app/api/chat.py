from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.react_agent import AgentRunResult, ReActAgent
from app.core.config import settings
from app.api.upload import _resolve_workspace_id
from app.core.llm_client import LLMClient
from app.core.workspace_lock import get_lock_manager
from app.output.formatter import format_output
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.run_tests import RunTestsTool
from app.tools.registry import ToolRegistry
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool
from app.workspace.indexer import IndexBuilder
from app.demo.scenarios import get_demo, list_demos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])
_WORKSPACE_BUSY = "该工作区已有任务正在运行，请稍后重试。"
_CHAT_FAILED = "任务执行失败。"


# ── 请求/响应模型 ──────────────────────────────────────


class ChatRequest(BaseModel):
    task: str = Field(..., min_length=1, description="用户任务描述")
    workspace_id: Optional[str] = Field(None, description="指定 workspace ID")


class ToolResultItem(BaseModel):
    tool_call_id: str
    name: str
    success: bool
    output: str


class AgentStepItem(BaseModel):
    step_id: int
    thought: str = ""
    action: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    observation: str = ""
    success: bool = True


class ChatResponse(BaseModel):
    task_id: str
    answer: str
    tool_calls_count: int
    tool_results: list[ToolResultItem]
    messages: list[dict[str, Any]]
    thoughts: list[str] = Field(default_factory=list)
    steps: list[AgentStepItem] = Field(default_factory=list)
    security_warnings: list[dict[str, Any]] = Field(default_factory=list)
    # D18: evidence-based fields
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    # D23: unified output fields
    mode: str = "react"
    metrics: dict[str, Any] = Field(default_factory=dict)
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str


class DemoRequest(BaseModel):
    demo_id: str = Field(..., description="Demo 场景 ID")
    workspace_id: Optional[str] = Field(None, description="Workspace ID")


class DemoResponse(BaseModel):
    id: str
    name: str
    category: str
    task: str
    description: str


class DemoListResponse(BaseModel):
    demos: list[DemoResponse]


# ── 工具构建 (每次请求新建，避免状态污染) ────────────────


def _build_registry(index=None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool(index=index))
    registry.register(SearchCodeTool(index=index))
    registry.register(WriteFileTool())
    registry.register(GitDiffTool())
    registry.register(GitStatusTool())
    registry.register(RunTestsTool())
    return registry


def _build_agent(workspace_root: Optional[str] = None) -> ReActAgent:
    llm = LLMClient(settings)
    ws = workspace_root or str(settings.workspace_root)
    # 构建 workspace 索引
    try:
        index = IndexBuilder().build(ws)
    except Exception as exc:
        logger.warning("Failed to build workspace index: [%s] %s", type(exc).__name__, exc)
        index = None
    registry = _build_registry(index=index)
    return ReActAgent(
        llm=llm,
        registry=registry,
        workspace_root=ws,
        max_tool_calls=settings.max_tool_calls,
    )


# ── 路由 ──────────────────────────────────────────────


@router.get("/workspace/index")
async def get_workspace_index(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """返回 workspace 文件结构索引。"""
    ws = _resolve_workspace_id(workspace_id)
    builder = IndexBuilder()
    index = builder.build(str(ws))
    return {
        "root": index.root,
        "tree": index.tree,
        "summary": index.summary,
        "files": [
            {"path": f.path, "module_name": f.module_name, "size": f.size}
            for f in index.files
        ],
    }


@router.get("/demos", response_model=DemoListResponse)
async def get_demos():
    """列出所有 Demo 场景。"""
    demos = list_demos()
    return DemoListResponse(
        demos=[
            DemoResponse(
                id=d.id, name=d.name, category=d.category,
                task=d.task, description=d.description,
            )
            for d in demos
        ]
    )


@router.get("/lock/status")
async def get_lock_status(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """获取 workspace 锁状态。"""
    ws = str(_resolve_workspace_id(workspace_id))
    lock_mgr = get_lock_manager()
    return lock_mgr.get_status(ws)


@router.post("/demo", response_model=DemoResponse)
async def run_demo(req: DemoRequest):
    """获取 Demo 场景信息（前端用 task 填充输入框）。"""
    scenario = get_demo(req.demo_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Demo not found: {req.demo_id}")
    return DemoResponse(
        id=scenario.id,
        name=scenario.name,
        category=scenario.category,
        task=scenario.task,
        description=scenario.description,
    )


def _check_workspace_available(ws: str) -> None:
    if get_lock_manager().is_locked(ws):
        raise HTTPException(status_code=409, detail=_WORKSPACE_BUSY)


async def _run_workspace_task(ws: str, task: str, task_id: str) -> AgentRunResult:
    lock_mgr = get_lock_manager()
    # Both HTTP entry points use this admission check and take the same lock.
    _check_workspace_available(ws)
    await lock_mgr.acquire(ws, task_id, task_prompt=task)
    try:
        agent = _build_agent(workspace_root=ws)
        return await agent.run(task, task_id=task_id)
    finally:
        lock_mgr.release(ws, task_id)


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def chat(req: ChatRequest) -> ChatResponse:
    """执行编码任务，返回完整结果。"""
    ws = str(_resolve_workspace_id(req.workspace_id))
    task_id = uuid4().hex
    try:
        result = await _run_workspace_task(ws, req.task, task_id)

        # D23: format through unified output layer
        from app.router.intent_router import get_intent_router
        intent = get_intent_router().route(req.task)
        mode = intent.intent
        if result.security_warnings:
            mode = "security"

        unified = format_output(
            mode=mode,
            answer=result.answer,
            steps=result.steps,
            tool_results=result.tool_results,
            evidence=result.evidence,
            confidence=result.confidence,
            security_warnings=result.security_warnings,
            thoughts=result.thoughts,
        )

        return ChatResponse(
            task_id=task_id,
            answer=result.answer,
            tool_calls_count=result.tool_calls_count,
            tool_results=[
                ToolResultItem(
                    tool_call_id=tr.tool_call_id,
                    name=tr.name,
                    success=tr.success,
                    output=tr.output,
                )
                for tr in result.tool_results
            ],
            messages=result.messages,
            thoughts=result.thoughts,
            steps=[
                AgentStepItem(
                    step_id=s.step_id,
                    thought=s.thought,
                    action=s.action,
                    tool_name=s.tool_name,
                    tool_args=s.tool_args,
                    observation=s.observation,
                    success=s.success,
                )
                for s in result.steps
            ],
            security_warnings=result.security_warnings,
            evidence=result.evidence,
            confidence=result.confidence,
            # D23: unified fields
            mode=unified.mode,
            metrics=unified.metrics.to_dict(),
            execution_trace=[s.to_dict() for s in unified.execution_trace],
            tools_used=unified.tools_used,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chat request %s failed", task_id)
        raise HTTPException(status_code=500, detail=_CHAT_FAILED) from exc


@router.post("/chat/stream", responses={409: {"model": ErrorResponse}})
async def chat_stream(req: ChatRequest):
    """用 SSE 返回任务完成后的工具结果。"""
    from starlette.responses import StreamingResponse

    ws = str(_resolve_workspace_id(req.workspace_id))
    _check_workspace_available(ws)
    task_id = uuid4().hex

    async def event_generator():
        yield _sse_event("start", {"task": req.task, "task_id": task_id})

        try:
            # Admission is checked again once the stream starts consuming its body.
            result = await _run_workspace_task(ws, req.task, task_id)

            # 逐个发送 tool_results
            for tr in result.tool_results:
                yield _sse_event("tool_result", {
                    "name": tr.name,
                    "success": tr.success,
                    "output": tr.output,
                })

            # event: final
            yield _sse_event("final", {
                "task_id": task_id,
                "answer": result.answer,
                "tool_calls_count": result.tool_calls_count,
            })

        except HTTPException as exc:
            yield _sse_event("error", {"task_id": task_id, "error": exc.detail})
        except Exception:
            logger.exception("Stream chat request %s failed", task_id)
            yield _sse_event("error", {"task_id": task_id, "error": _CHAT_FAILED})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event: str, data: dict) -> str:
    """构造 SSE 事件字符串。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
