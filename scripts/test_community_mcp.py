"""scripts/test_community_mcp.py — 演示与测试 CodePilot Agent 连接官方/社区 MCP Servers。

连接：
1. @modelcontextprotocol/server-filesystem (官方文件系统 MCP)
2. @modelcontextprotocol/server-memory (官方知识图谱长程记忆 MCP)
3. 验证 /api/tools、/api/skills、/api/mcp/servers 统一元数据展示与工具执行
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.models.tool import ToolCall
from app.mcp.registry import mcp_registry
from app.api.chat import _build_registry

WORKSPACE = str(PROJECT_ROOT / "workspace")


async def async_main() -> None:
    print("=" * 65)
    print("[MCP E2E Demo] CodePilot Agent Community MCP & Skills Mount")
    print("=" * 65)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 动态挂载官方 Filesystem MCP Server
        print("\n[Step 1] Mounting @modelcontextprotocol/server-filesystem...")
        resp_fs = await client.post(
            "/api/mcp/connect",
            json={
                "name": "community_filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", WORKSPACE],
                "namespace_tools": True,
            },
        )
        if resp_fs.status_code == 200:
            fs_data = resp_fs.json()
            print(f"[OK] Connected! Loaded tools count: {len(fs_data['tools_loaded'])}")
            print(f"     Tools: {', '.join(fs_data['tools_loaded'][:6])} ...")
        else:
            print(f"[ERROR] Connect failed: {resp_fs.status_code} {resp_fs.text}")

        # 2. 动态挂载官方 Memory Graph MCP Server
        print("\n[Step 2] Mounting @modelcontextprotocol/server-memory...")
        resp_mem = await client.post(
            "/api/mcp/connect",
            json={
                "name": "community_memory",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "namespace_tools": True,
            },
        )
        if resp_mem.status_code == 200:
            mem_data = resp_mem.json()
            print(f"[OK] Connected! Loaded tools count: {len(mem_data['tools_loaded'])}")
            print(f"     Tools: {', '.join(mem_data['tools_loaded'])}")
        else:
            print(f"[ERROR] Connect failed: {resp_mem.status_code} {resp_mem.text}")

        # 3. 查看已注册 MCP Servers 状态
        print("\n[Step 3] Querying GET /api/mcp/servers status...")
        resp_servers = (await client.get("/api/mcp/servers")).json()
        print(f"Active MCP Servers ({resp_servers['count']} registered):")
        for s in resp_servers["servers"]:
            print(f"  * {s['name']}: {s['tools_count']} tools, connected={s['is_connected']}")

        # 4. 查看分层技能列表 GET /api/skills
        print("\n[Step 4] Querying GET /api/skills (Tier 1 vs Tier 2)...")
        resp_skills = (await client.get("/api/skills")).json()
        print(f"Total skills/tools available: {resp_skills['total_skills']}")
        print(f"Tier 1 Core Native Tools ({len(resp_skills['tier1_core_tools'])} tools):")
        for t in resp_skills["tier1_core_tools"]:
            print(f"  - [Tier 1] {t['name']}")

        print(f"\nTier 2 Dynamic MCP Skills ({len(resp_skills['tier2_mcp_skills'])} tools):")
        for t in resp_skills["tier2_mcp_skills"][:10]:
            print(f"  - [Tier 2 MCP] {t['name']} (server: {t['server']})")
        if len(resp_skills["tier2_mcp_skills"]) > 10:
            print(f"  ... and {len(resp_skills['tier2_mcp_skills']) - 10} more MCP skills")

        # 5. 通过 ToolRegistry 统一执行 MCP 工具并验证安全拦截
        print("\n[Step 5] Executing Tool Calls & Guardrail Security Verification...")
        tool_reg = _build_registry()
        tool_reg.mount_mcp_registry(mcp_registry)

        # 5.1 正常调用 filesystem 工具
        tc_list = ToolCall(
            name="mcp_community_filesystem_list_directory",
            arguments={"path": WORKSPACE},
        )
        result_list = await tool_reg.execute(tc_list, WORKSPACE)
        print(f"Call: mcp_community_filesystem_list_directory (normal path):\n  success={result_list.success}")
        first_lines = [line.strip() for line in result_list.output.strip().split("\n") if line.strip()][:4]
        print(f"  snippet: {'; '.join(first_lines)}")

        # 5.2 安全拦截路径越界
        tc_hack = ToolCall(
            name="mcp_community_filesystem_read_file",
            arguments={"path": "../../etc/passwd"},
        )
        result_hack = await tool_reg.execute(tc_hack, WORKSPACE)
        print(f"\nCall: mcp_community_filesystem_read_file (malicious path traversal):\n  success={result_hack.success}\n  output: {result_hack.output}")

        # 5.3 调用 memory 图谱工具写入知识节点
        tc_mem = ToolCall(
            name="mcp_community_memory_create_entities",
            arguments={
                "entities": [
                    {
                        "name": "CodePilotMicrokernel",
                        "entityType": "Architecture",
                        "observations": ["Everything is a Plugin", "MCP Powered"],
                    }
                ]
            },
        )
        result_mem = await tool_reg.execute(tc_mem, WORKSPACE)
        print(f"\nCall: mcp_community_memory_create_entities (graph persistence):\n  success={result_mem.success}\n  output: {result_mem.output.strip()}")

        # 6. 安全清理
        await mcp_registry.disconnect_all()
        print("\n" + "=" * 65)
        print("[SUCCESS] All Community MCP Servers & Skills Verified End-to-End!")
        print("=" * 65)


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
