from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agent.react_agent import ReActAgent
from app.core.config import settings
from app.api.upload import _resolve_workspace_id
from app.core.llm_client import LLMClient
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


class ErrorResponse(BaseModel):
    error: str


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
    except Exception:
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


@router.post("/chat", response_model=ChatResponse, responses={500: {"model": ErrorResponse}})
async def chat(req: ChatRequest) -> ChatResponse:
    """执行编码任务，返回完整结果。"""
    try:
        ws = str(_resolve_workspace_id(req.workspace_id))
        agent = _build_agent(workspace_root=ws)
        result = await agent.run(req.task)
        return ChatResponse(
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
        )
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式接口 — 当前为模拟流式，预留真实流式扩展点。"""
    from starlette.responses import StreamingResponse

    async def event_generator():
        # event: start
        yield _sse_event("start", {"task": req.task})

        try:
            ws = str(_resolve_workspace_id(req.workspace_id))
            agent = _build_agent(workspace_root=ws)
            result = await agent.run(req.task)

            # 逐个发送 tool_results
            for tr in result.tool_results:
                yield _sse_event("tool_result", {
                    "name": tr.name,
                    "success": tr.success,
                    "output": tr.output,
                })

            # event: final
            yield _sse_event("final", {
                "answer": result.answer,
                "tool_calls_count": result.tool_calls_count,
            })

        except Exception as exc:
            logger.exception("Stream chat failed")
            yield _sse_event("error", {"error": str(exc)})

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
