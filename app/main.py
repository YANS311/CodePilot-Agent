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


# ── 静态文件 (放在最后，避免覆盖 API 路由) ──
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def index():
    from starlette.responses import FileResponse
    return FileResponse(str(_STATIC_DIR / "index.html"))

