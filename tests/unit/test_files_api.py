from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ═══════════════════════════════════════════
# 1. GET /api/files 返回文件列表
# ═══════════════════════════════════════════


class TestFileList:
    def test_returns_file_list(self):
        resp = client.get("/api/files")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data
        assert isinstance(data["files"], list)
        assert len(data["files"]) > 0

    def test_files_have_correct_fields(self):
        resp = client.get("/api/files")
        data = resp.json()
        f = data["files"][0]
        assert "path" in f
        assert "name" in f
        assert "type" in f
        assert "size" in f
        assert f["type"] == "file"

    def test_paths_are_relative(self):
        resp = client.get("/api/files")
        data = resp.json()
        for f in data["files"]:
            assert not f["path"].startswith("/"), f"路径不应是绝对路径: {f['path']}"

    def test_ignores_pycache(self):
        resp = client.get("/api/files")
        data = resp.json()
        for f in data["files"]:
            assert "__pycache__" not in f["path"]

    def test_ignores_git_dir(self):
        resp = client.get("/api/files")
        data = resp.json()
        for f in data["files"]:
            parts = Path(f["path"]).parts
            assert ".git" not in parts

    def test_includes_workspace_examples(self):
        resp = client.get("/api/files")
        data = resp.json()
        paths = [f["path"] for f in data["files"]]
        assert any("buggy_calculator.py" in p for p in paths)


# ═══════════════════════════════════════════
# 2. GET /api/files/content 正常读取
# ═══════════════════════════════════════════


class TestFileContent:
    def test_read_existing_file(self):
        resp = client.get("/api/files/content", params={"path": "examples/buggy_calculator.py"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["path"] == "examples/buggy_calculator.py"
        assert "Calculator" in data["content"]
        assert data["truncated"] is False

    def test_read_nonexistent_file(self):
        resp = client.get("/api/files/content", params={"path": "no_such_file.py"})
        assert resp.status_code == 404

    def test_read_directory_returns_error(self):
        resp = client.get("/api/files/content", params={"path": "examples"})
        assert resp.status_code == 400


# ═══════════════════════════════════════════
# 3. content 路径穿越被拒绝
# ═══════════════════════════════════════════


class TestFileContentSecurity:
    def test_path_traversal_blocked(self):
        resp = client.get("/api/files/content", params={"path": "../../etc/passwd"})
        assert resp.status_code == 403

    def test_dot_dot_slash_blocked(self):
        resp = client.get("/api/files/content", params={"path": "../.env"})
        assert resp.status_code == 403


# ═══════════════════════════════════════════
# 4. download 正常
# ═══════════════════════════════════════════


class TestFileDownload:
    def test_download_existing_file(self):
        resp = client.get("/api/files/download", params={"path": "examples/buggy_calculator.py"})
        assert resp.status_code == 200
        assert "content-disposition" in resp.headers

    def test_download_nonexistent_file(self):
        resp = client.get("/api/files/download", params={"path": "no_such.py"})
        assert resp.status_code == 404


# ═══════════════════════════════════════════
# 5. download .env 被拒绝
# ═══════════════════════════════════════════


class TestFileDownloadSecurity:
    def test_download_env_blocked(self):
        # 先创建一个 .env 文件在 workspace 里来测试
        import tempfile, shutil
        from app.core.config import settings
        ws = Path(settings.workspace_root)
        env_file = ws / ".env"
        existed = env_file.exists()
        if not existed:
            env_file.write_text("SECRET=test", encoding="utf-8")
        try:
            resp = client.get("/api/files/download", params={"path": ".env"})
            assert resp.status_code == 403
        finally:
            if not existed and env_file.exists():
                env_file.unlink()

    def test_download_hidden_file_blocked(self):
        resp = client.get("/api/files/download", params={"path": ".hidden_file"})
        # 可能 403 (blocked) 或 404 (不存在)，但不能 200
        assert resp.status_code != 200

    def test_path_traversal_download_blocked(self):
        resp = client.get("/api/files/download", params={"path": "../../.env"})
        assert resp.status_code == 403
