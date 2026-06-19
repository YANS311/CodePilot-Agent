"""Upload API — 用户上传代码项目到 workspace。

POST /api/upload
- 支持 .zip 项目包（自动解压）
- 支持单个 .py / .txt / .md / .json 文件
- 上传到 workspace/uploads/<timestamp>/
- 安全限制：Zip Slip、文件大小、文件类型
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])

# ── 安全常量 ──────────────────────────────────────────────

_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
_MAX_FILES = 500

_TEXT_SUFFIXES = {
    ".py", ".txt", ".md", ".json", ".yaml", ".yml", ".toml",
    ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".sh",
    ".cfg", ".ini", ".xml", ".csv", ".sql",
}

_SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".idea"}

_BLOCKED_NAMES = {".env", ".env.local", ".env.production", ".env.development"}


# ── 响应模型 ──────────────────────────────────────────────


class UploadResponse(BaseModel):
    workspace_id: str
    root_path: str
    file_count: int


# ── 工具函数 ──────────────────────────────────────────────


def _is_safe_zip_path(member_name: str, extract_dir: Path) -> bool:
    """校验 zip 成员路径不会穿越到 extract_dir 之外（Zip Slip 防护）。"""
    try:
        target = (extract_dir / member_name).resolve()
        return str(target).startswith(str(extract_dir.resolve()))
    except (ValueError, OSError):
        return False


def _is_allowed_file(filename: str) -> bool:
    """检查文件名是否允许上传。"""
    name = Path(filename).name
    # 禁止 .env 等敏感文件
    if name in _BLOCKED_NAMES:
        return False
    # 禁止隐藏文件（以 . 开头，但允许 .py 等后缀）
    parts = Path(filename).parts
    for part in parts[:-1]:  # 目录名不能以 . 开头
        if part.startswith("."):
            return False
    return True


def _is_text_file(filename: str) -> bool:
    """检查文件是否为文本/代码文件。"""
    suffix = Path(filename).suffix.lower()
    return suffix in _TEXT_SUFFIXES


def _should_skip_dir(dirname: str) -> bool:
    """检查目录是否应跳过。"""
    return dirname in _SKIP_DIRS


# ── 路由 ──────────────────────────────────────────────────


@router.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile) -> UploadResponse:
    """上传代码项目（zip 或单文件）到 workspace。"""
    filename = file.filename or "unnamed"
    ws_root = Path(settings.workspace_root).resolve()

    # 确保 uploads 目录存在
    uploads_dir = ws_root / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # 生成 workspace_id（时间戳）
    workspace_id = str(int(time.time()))
    extract_dir = uploads_dir / workspace_id
    extract_dir.mkdir(parents=True, exist_ok=True)

    try:
        content = await file.read()

        # 检查文件大小
        if len(content) > _MAX_FILE_SIZE:
            _cleanup(extract_dir)
            raise HTTPException(
                status_code=413,
                detail=f"文件过大，最大 {_MAX_FILE_SIZE // (1024*1024)}MB",
            )

        # 检查文件名
        if not _is_allowed_file(filename):
            _cleanup(extract_dir)
            raise HTTPException(
                status_code=400,
                detail=f"不允许上传此文件: {filename}",
            )

        if filename.lower().endswith(".zip"):
            file_count = _extract_zip(content, extract_dir)
        else:
            if not _is_text_file(filename):
                _cleanup(extract_dir)
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的文件类型: {Path(filename).suffix}",
                )
            # 单文件直接保存
            target = extract_dir / Path(filename).name
            target.write_bytes(content)
            file_count = 1

        logger.info("Upload complete: workspace_id=%s, files=%d", workspace_id, file_count)

        return UploadResponse(
            workspace_id=workspace_id,
            root_path=str(extract_dir),
            file_count=file_count,
        )

    except HTTPException:
        raise
    except Exception as exc:
        _cleanup(extract_dir)
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}")


def _extract_zip(content: bytes, extract_dir: Path) -> int:
    """解压 zip 文件，返回解压的文件数。"""
    file_count = 0

    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue

            name = member.filename
            # 跳过忽略目录中的文件
            parts = Path(name).parts
            if any(_should_skip_dir(p) for p in parts):
                continue

            # 跳过隐藏文件
            if any(p.startswith(".") for p in parts if p != parts[-1]):
                continue

            # 跳过不允许的文件名
            if not _is_allowed_file(name):
                continue

            # Zip Slip 防护
            if not _is_safe_zip_path(name, extract_dir):
                logger.warning("Zip Slip attempt blocked: %s", name)
                continue

            # 只允许文本文件
            if not _is_text_file(name):
                continue

            # 文件数限制
            if file_count >= _MAX_FILES:
                logger.warning("Max files reached, skipping remaining")
                break

            # 提取文件
            target = (extract_dir / name).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)

            with zf.open(member) as src:
                target.write_bytes(src.read())

            file_count += 1

    return file_count


def _cleanup(path: Path) -> None:
    """清理目录。"""
    import shutil
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def _resolve_workspace_id(workspace_id: Optional[str] = None) -> Path:
    """根据 workspace_id 解析 workspace 路径。"""
    ws_root = Path(settings.workspace_root).resolve()
    if workspace_id:
        target = (ws_root / "uploads" / workspace_id).resolve()
        if not str(target).startswith(str(ws_root)):
            raise HTTPException(status_code=403, detail="workspace_id 路径不合法")
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"workspace 不存在: {workspace_id}")
        return target
    return ws_root
