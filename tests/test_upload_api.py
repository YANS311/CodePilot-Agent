"""D13 Tests — Upload API + workspace switching."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from httpx import AsyncClient, ASGITransport
from app.main import app

transport = ASGITransport(app=app)


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════


def _make_zip(files: dict[str, bytes]) -> bytes:
    """创建内存中的 zip 文件。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ═══════════════════════════════════════════
# 1. Upload single file
# ═══════════════════════════════════════════


class TestUploadSingleFile:
    @pytest.mark.asyncio
    async def test_upload_py_file(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("hello.py", b"print('hello')", "text/plain")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "workspace_id" in data
            assert data["file_count"] == 1
            assert Path(data["root_path"]).exists()

    @pytest.mark.asyncio
    async def test_upload_txt_file(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("readme.txt", b"hello world", "text/plain")},
            )
            assert resp.status_code == 200
            assert resp.json()["file_count"] == 1


# ═══════════════════════════════════════════
# 2. Upload zip
# ═══════════════════════════════════════════


class TestUploadZip:
    @pytest.mark.asyncio
    async def test_upload_zip(self):
        zip_content = _make_zip({
            "src/main.py": b"print('main')",
            "tests/test_main.py": b"def test_ok(): pass",
            "README.md": b"# Project",
        })
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("project.zip", zip_content, "application/zip")},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["file_count"] == 3
            # 验证解压后的文件存在
            root = Path(data["root_path"])
            assert (root / "src" / "main.py").exists()
            assert (root / "tests" / "test_main.py").exists()
            assert (root / "README.md").exists()

    @pytest.mark.asyncio
    async def test_upload_zip_skips_pycache(self):
        zip_content = _make_zip({
            "src/main.py": b"print('main')",
            "src/__pycache__/main.cpython-312.pyc": b"bytecode",
            ".git/config": b"[core]",
            "node_modules/pkg/index.js": b"module.exports",
        })
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("project.zip", zip_content, "application/zip")},
            )
            assert resp.status_code == 200
            data = resp.json()
            # 只有 src/main.py 应被解压
            assert data["file_count"] == 1


# ═══════════════════════════════════════════
# 3. Zip Slip rejected
# ═══════════════════════════════════════════


class TestZipSlip:
    @pytest.mark.asyncio
    async def test_zip_slip_rejected(self):
        zip_content = _make_zip({
            "../../etc/passwd": b"root:x:0:0",
            "safe.py": b"print('safe')",
        })
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("evil.zip", zip_content, "application/zip")},
            )
            assert resp.status_code == 200
            data = resp.json()
            # Zip Slip 文件应被跳过
            assert data["file_count"] == 1
            root = Path(data["root_path"])
            assert not (root / ".." / ".." / "etc" / "passwd").exists()


# ═══════════════════════════════════════════
# 4. Oversized file rejected
# ═══════════════════════════════════════════


class TestOversizedFile:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self):
        # 21MB file
        big_content = b"x" * (21 * 1024 * 1024)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("big.py", big_content, "text/plain")},
            )
            assert resp.status_code == 413


# ═══════════════════════════════════════════
# 5. workspace_id for /api/files
# ═══════════════════════════════════════════


class TestFilesWorkspaceId:
    @pytest.mark.asyncio
    async def test_files_with_workspace_id(self):
        # 上传文件
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            upload_resp = await client.post(
                "/api/upload",
                files={"file": ("test.py", b"print('test')", "text/plain")},
            )
            ws_id = upload_resp.json()["workspace_id"]

            # 用 workspace_id 列出文件
            files_resp = await client.get(f"/api/files?workspace_id={ws_id}")
            assert files_resp.status_code == 200
            files = files_resp.json()["files"]
            assert any(f["name"] == "test.py" for f in files)

    @pytest.mark.asyncio
    async def test_files_content_with_workspace_id(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            upload_resp = await client.post(
                "/api/upload",
                files={"file": ("hello.py", b"print('hello')", "text/plain")},
            )
            ws_id = upload_resp.json()["workspace_id"]

            content_resp = await client.get(
                f"/api/files/content?path=hello.py&workspace_id={ws_id}"
            )
            assert content_resp.status_code == 200
            assert content_resp.json()["content"] == "print('hello')"

    @pytest.mark.asyncio
    async def test_invalid_workspace_id(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/files?workspace_id=nonexistent")
            assert resp.status_code == 404


# ═══════════════════════════════════════════
# 6. /api/chat with workspace_id
# ═══════════════════════════════════════════


class TestChatWorkspaceId:
    @pytest.mark.asyncio
    async def test_chat_with_workspace_id(self):
        # 上传文件
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            upload_resp = await client.post(
                "/api/upload",
                files={"file": ("buggy.py", b"def add(a, b): return a - b", "text/plain")},
            )
            ws_id = upload_resp.json()["workspace_id"]

            # 用 workspace_id 发送 chat 请求
            chat_resp = await client.post(
                "/api/chat",
                json={"task": "read buggy.py", "workspace_id": ws_id},
            )
            # 不验证完整结果（需要 LLM），只验证 200
            assert chat_resp.status_code == 200


# ═══════════════════════════════════════════
# 7. Blocked files
# ═══════════════════════════════════════════


class TestBlockedFiles:
    @pytest.mark.asyncio
    async def test_env_file_rejected(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": (".env", b"SECRET=abc", "text/plain")},
            )
            assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_binary_file_rejected(self):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/upload",
                files={"file": ("image.png", b"\x89PNG", "image/png")},
            )
            assert resp.status_code == 400
