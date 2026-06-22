"""Memory API — GET /api/memory for viewing agent memory state."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.memory.memory_manager import get_memory_manager

router = APIRouter(prefix="/api", tags=["memory"])


@router.get("/memory")
async def get_memory(
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    limit: int = Query(20, ge=1, le=100, description="Max items per category"),
):
    """Return current agent memory state."""
    mgr = get_memory_manager()

    tasks = mgr.get_task_memory(limit=limit)
    errors = mgr.get_error_memory(limit=limit)
    repos = mgr.get_repo_memory(limit=limit)

    return {
        "stats": mgr.stats(),
        "tasks": [t.to_dict() for t in tasks],
        "errors": [e.to_dict() for e in errors],
        "repos": [r.to_dict() for r in repos],
    }


@router.get("/memory/query")
async def query_memory(
    task_prompt: str = Query(..., min_length=1, description="Task prompt to match"),
    limit: int = Query(5, ge=1, le=20, description="Max results"),
):
    """Query memory by task prompt (keyword matching)."""
    mgr = get_memory_manager()

    similar_tasks = mgr.query_task_memory(task_prompt, limit=limit)
    keywords = task_prompt.split()[:5]
    similar_errors = mgr.query_error_memory(keywords=keywords, limit=limit)

    return {
        "query": task_prompt,
        "similar_tasks": [t.to_dict() for t in similar_tasks],
        "similar_errors": [e.to_dict() for e in similar_errors],
    }
