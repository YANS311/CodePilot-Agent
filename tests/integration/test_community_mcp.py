from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.chat import _build_registry
from app.main import app
from app.mcp.registry import mcp_registry
from app.models.tool import ToolCall

WORKSPACE = str(PROJECT_ROOT / "workspace")
HAS_NPX = shutil.which("npx") is not None


@pytest.mark.skipif(not HAS_NPX, reason="npx is required for community MCP integration tests")
class TestCommunityMCPEndToEnd:
    def test_connect_filesystem_and_memory_servers(self):
        async def _run():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. 动态连接官方 Filesystem MCP Server
                resp_fs = await client.post(
                    "/api/mcp/connect",
                    json={
                        "name": "e2e_filesystem",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-filesystem", WORKSPACE],
                        "namespace_tools": True,
                    },
                )
                if resp_fs.status_code == 400:
                    pytest.skip(f"npx community MCP server unavailable in environment: {resp_fs.text}")
                assert resp_fs.status_code == 200
                fs_data = resp_fs.json()
                assert len(fs_data["tools_loaded"]) >= 10
                assert "mcp_e2e_filesystem_list_directory" in fs_data["tools_loaded"]

                # 2. 动态连接官方 Memory Graph MCP Server
                resp_mem = await client.post(
                    "/api/mcp/connect",
                    json={
                        "name": "e2e_memory",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "@modelcontextprotocol/server-memory"],
                        "namespace_tools": True,
                    },
                )
                assert resp_mem.status_code == 200
                mem_data = resp_mem.json()
                assert "mcp_e2e_memory_create_entities" in mem_data["tools_loaded"]

                # 3. 验证 /api/skills
                resp_skills = await client.get("/api/skills")
                assert resp_skills.status_code == 200
                skills_data = resp_skills.json()
                assert len(skills_data["tier1_core_tools"]) >= 6
                assert len(skills_data["tier2_mcp_skills"]) >= 15

                # 4. 执行真实工具调用
                tool_reg = _build_registry()
                tool_reg.mount_mcp_registry(mcp_registry)

                # 正常调用
                tc = ToolCall(name="mcp_e2e_filesystem_list_directory", arguments={"path": WORKSPACE})
                res = await tool_reg.execute(tc, WORKSPACE)
                assert res.success is True
                assert "examples" in res.output or "tests" in res.output

                # 恶意越界安全拦截
                tc_bad = ToolCall(name="mcp_e2e_filesystem_read_file", arguments={"path": "../../secret.txt"})
                res_bad = await tool_reg.execute(tc_bad, WORKSPACE)
                assert "SECURITY_BLOCKED" in res_bad.output

                # 清理连接
                await mcp_registry.disconnect_all()

        asyncio.run(_run())
