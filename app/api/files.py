from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.api.upload import _resolve_workspace_id

router = APIRouter(prefix="/api/files", tags=["files"])

_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".idea"}
_MAX_FILES = 500
_MAX_PREVIEW = 100 * 1024  # 100KB
_BLOCKED_DOWNLOADS = {".env", ".env.local", ".env.production"}
_HIDDEN_PREFIXES = (".",)
_TEXT_SUFFIXES = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
    ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".sh",
    ".cfg", ".ini", ".xml", ".csv", ".sql", ".env",
}


def _safe_path(relative: str, ws_root: Optional[Path] = None) -> Path:
    """解析相对路径并校验是否在 workspace 内。"""
    ws = ws_root or Path(settings.workspace_root).resolve()
    target = (ws / relative).resolve()
    if not str(target).startswith(str(ws)):
        raise HTTPException(status_code=403, detail="路径超出 workspace 范围")
    return target


# ── Part 1: 文件列表 ──────────────────────────────────────


class FileInfo(BaseModel):
    path: str
    name: str
    type: str = "file"
    size: int


class FileListResponse(BaseModel):
    files: list[FileInfo]


@router.get("", response_model=FileListResponse)
async def list_files(workspace_id: Optional[str] = Query(None, description="Workspace ID")):
    """递归列出 workspace 下的文件。"""
    ws = _resolve_workspace_id(workspace_id)
    if not ws.exists():
        return FileListResponse(files=[])

    files: list[FileInfo] = []

    for root, dirs, filenames in os.walk(ws):
        # 原地修改 dirs 以跳过忽略目录
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

        for fname in filenames:
            if len(files) >= _MAX_FILES:
                break

            fpath = Path(root) / fname
            rel = fpath.relative_to(ws).as_posix()

            # 跳过隐藏文件
            if any(part.startswith(".") for part in Path(rel).parts):
                continue

            try:
                size = fpath.stat().st_size
            except OSError:
                continue

            files.append(FileInfo(
                path=rel,
                name=fname,
                type="file",
                size=size,
            ))

        if len(files) >= _MAX_FILES:
            break

    files.sort(key=lambda f: f.path)
    return FileListResponse(files=files)


# ── Part 2: 文件内容预览 ────────────────────────────────────


class FileContentResponse(BaseModel):
    path: str
    content: str
    truncated: bool


@router.get("/content", response_model=FileContentResponse)
async def read_file_content(
    path: str = Query(..., description="文件相对路径"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """读取文件内容用于预览。"""
    ws = _resolve_workspace_id(workspace_id)
    target = _safe_path(path, ws)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    if target.is_dir():
        raise HTTPException(status_code=400, detail=f"不能预览目录: {path}")

    # 检查是否是文本文件（按后缀判断）
    suffix = target.suffix.lower()
    if suffix and suffix not in _TEXT_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持预览 {suffix} 文件")

    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"读取失败: {exc}")

    truncated = len(raw) > _MAX_PREVIEW
    if truncated:
        raw = raw[:_MAX_PREVIEW]

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是 UTF-8 编码，无法预览")

    return FileContentResponse(path=path, content=content, truncated=truncated)


# ── Part 3: 文件下载 ────────────────────────────────────────


@router.get("/download")
async def download_file(
    path: str = Query(..., description="文件相对路径"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
):
    """下载 workspace 内文件。"""
    ws = _resolve_workspace_id(workspace_id)
    target = _safe_path(path, ws)

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {path}")

    if target.is_dir():
        raise HTTPException(status_code=400, detail="不能下载目录")

    fname = target.name

    # 禁止下载 .env 等敏感文件
    if fname in _BLOCKED_DOWNLOADS:
        raise HTTPException(status_code=403, detail=f"禁止下载敏感文件: {fname}")

    # 禁止下载隐藏文件（以 . 开头）
    if any(part.startswith(".") for part in Path(path).parts):
        raise HTTPException(status_code=403, detail="禁止下载隐藏文件")

    return FileResponse(
        path=str(target),
        filename=fname,
        media_type="application/octet-stream",
    )
