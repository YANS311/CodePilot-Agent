import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.api.chat import router as chat_router
from app.api.files import router as files_router
from app.api.memory import router as memory_router
from app.api.upload import router as upload_router
from app.core.config import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CodePilot Agent",
    description="轻量级 Python Coding Agent",
    version="0.1.0",
)


@app.on_event("startup")
async def _log_config():
    logger.info("LLM base_url: %s", settings.llm_base_url)
    logger.info("LLM model:    %s", settings.llm_model)
    logger.info("LLM api_key:  %s...", settings.llm_api_key[:8] if settings.llm_api_key else "(empty)")

# ── 路由 ──
app.include_router(chat_router)
app.include_router(files_router)
app.include_router(memory_router)
app.include_router(upload_router)


@app.get("/health")
async def health():
    """健康检查 — 用于 Docker 启动验证和监控。"""
    ws = settings.workspace_root
    workspace_mounted = ws.exists() and ws.is_dir()
    return {
        "status": "ok",
        "agent": "ready",
        "workspace": "mounted" if workspace_mounted else "not_found",
        "llm_model": settings.llm_model,
    }


@app.get("/health/deep")
async def health_deep():
    """深度健康检查 — 验证各组件可用性。"""
    checks = {}
    overall = "ok"

    # 1. Workspace
    ws = settings.workspace_root
    checks["workspace"] = "ok" if ws.exists() and ws.is_dir() else "not_found"
    if checks["workspace"] == "not_found":
        overall = "degraded"

    # 2. Memory manager
    try:
        from app.memory.memory_manager import get_memory_manager
        mgr = get_memory_manager()
        checks["memory"] = "ok"
    except Exception as exc:
        checks["memory"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    # 3. Tool registry
    try:
        from app.tools.registry import ToolRegistry
        from app.tools.read_file import ReadFileTool
        from app.tools.search_code import SearchCodeTool
        from app.tools.write_file import WriteFileTool
        from app.tools.git_diff import GitDiffTool
        from app.tools.git_status import GitStatusTool
        from app.tools.run_tests import RunTestsTool
        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(SearchCodeTool())
        reg.register(WriteFileTool())
        reg.register(GitDiffTool())
        reg.register(GitStatusTool())
        reg.register(RunTestsTool())
        checks["tool_registry"] = f"ok ({len(reg._tools)} tools)"
    except Exception as exc:
        checks["tool_registry"] = f"error: {type(exc).__name__}"
        overall = "degraded"

    # 4. LLM config
    if settings.llm_api_key:
        checks["llm_config"] = "ok"
    else:
        checks["llm_config"] = "missing_api_key"
        overall = "degraded"

    return {
        "status": overall,
        "checks": checks,
    }


# ── 静态文件 (放在最后，避免覆盖 API 路由) ──
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    from starlette.responses import FileResponse
    return FileResponse(str(_STATIC_DIR / "index.html"))

