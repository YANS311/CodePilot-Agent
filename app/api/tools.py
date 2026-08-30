"""app/api/tools.py — 工具与 MCP 插件统一元数据接口。

提供 GET /api/tools 与 GET /api/skills，展示所有原生工具与当前已挂载 MCP 工具的统一番号、参数模式与状态。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.chat import _build_registry
from app.mcp.registry import MCPServerConfig, mcp_registry
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tools"])


class ToolMetadataItem(BaseModel):
    """单个工具的元数据定义。"""

    name: str = Field(..., description="工具唯一标识名称")
    description: str = Field(..., description="工具功能描述")
    source: str = Field(..., description="来源: 'native' 或 'mcp'")
    server: str = Field(..., description="所属 Server 标识: 'builtin' 或 MCP Server 标识")
    original_name: Optional[str] = Field(None, description="原始工具名称")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema 参数描述")
    timeout: Optional[float] = Field(None, description="超时限制 (秒)")
    enabled: bool = Field(True, description="是否启用")


class ToolsListResponse(BaseModel):
    """GET /api/tools 响应模型。"""

    total: int
    native_count: int
    mcp_count: int
    tools: List[ToolMetadataItem]


class SkillsTierResponse(BaseModel):
    """GET /api/skills 分层技能响应模型。"""

    tier1_core_tools: List[ToolMetadataItem]
    tier2_mcp_skills: List[ToolMetadataItem]
    total_skills: int


def _get_unified_registry() -> ToolRegistry:
    """构建包含原生工具与已加载 MCP 工具的注册中心。"""
    reg = _build_registry()
    reg.mount_mcp_registry(mcp_registry)
    return reg


@router.get("/api/tools", response_model=ToolsListResponse)
async def list_all_tools() -> ToolsListResponse:
    """获取当前所有已挂载的原生与 MCP 工具的统一元数据。"""
    reg = _get_unified_registry()
    metadata_list = reg.get_tools_metadata()

    items = [ToolMetadataItem(**m) for m in metadata_list]
    native_count = sum(1 for item in items if item.source == "native")
    mcp_count = sum(1 for item in items if item.source == "mcp")

    return ToolsListResponse(
        total=len(items),
        native_count=native_count,
        mcp_count=mcp_count,
        tools=items,
    )


@router.get("/api/skills", response_model=SkillsTierResponse)
async def list_skills() -> SkillsTierResponse:
    """获取分层技能视图 (Tier 1 Core System Tools vs Tier 2 MCP Skills)。"""
    reg = _get_unified_registry()
    metadata_list = reg.get_tools_metadata()

    tier1 = [ToolMetadataItem(**m) for m in metadata_list if m.get("source") == "native"]
    tier2 = [ToolMetadataItem(**m) for m in metadata_list if m.get("source") == "mcp"]

    return SkillsTierResponse(
        tier1_core_tools=tier1,
        tier2_mcp_skills=tier2,
        total_skills=len(metadata_list),
    )


@router.get("/api/mcp/servers")
async def list_mcp_servers() -> Dict[str, Any]:
    """获取当前已注册的 MCP Server 及其连接状态。"""
    mcp_path = Path(__file__).resolve().parent.parent.parent / "mcp.json"
    if not mcp_registry._configs and mcp_path.exists():
        try:
            mcp_registry.load_from_json(mcp_path)
        except Exception as exc:
            logger.debug("Auto loading mcp.json fallback: %s", exc)

    servers_info = []
    for name, cfg in mcp_registry._configs.items():
        client = mcp_registry.get_client(name)
        servers_info.append({
            "name": name,
            "transport": cfg.transport,
            "command": cfg.command,
            "url": cfg.url,
            "is_connected": client.is_connected if client else False,
            "server_info": client.server_info if client else {},
            "tools_count": sum(1 for t in mcp_registry._tools.values() if t.server_name == name),
        })

    return {
        "count": len(servers_info),
        "servers": servers_info,
    }


@router.post("/api/mcp/connect")
async def connect_mcp_server(config: MCPServerConfig) -> Dict[str, Any]:
    """动态注册并连接 MCP Server，拉取工具挂载至系统。"""
    try:
        if config.name in mcp_registry._configs:
            mcp_registry.unregister_server(config.name)

        mcp_registry.register_server(config)
        tools = await mcp_registry.connect_server(config.name)
        return {
            "status": "connected",
            "server": config.name,
            "tools_loaded": [t.name for t in tools],
        }
    except Exception as exc:
        logger.exception("Failed to connect MCP server '%s'", config.name)
        raise HTTPException(status_code=400, detail=f"连接 MCP Server 失败: {exc}")


@router.delete("/api/mcp/servers/{name}")
async def disconnect_mcp_server(name: str) -> Dict[str, Any]:
    """断开并注销指定的 MCP Server。"""
    if name not in mcp_registry._configs:
        raise HTTPException(status_code=404, detail=f"MCP Server '{name}' not found")
    mcp_registry.unregister_server(name)
    return {"status": "unregistered", "server": name}


# ── Agent Skills (3-Level Progressive Disclosure) ──
import dataclasses
from app.skills.manager import skill_manager


@router.get("/api/agent-skills")
async def list_agent_skills() -> Dict[str, Any]:
    """获取所有 Agent Skills 元数据 (Level 1 Progressive Disclosure)。"""
    metas = skill_manager.list_metadata()
    return {
        "count": len(metas),
        "skills": [dataclasses.asdict(m) for m in metas],
    }


@router.get("/api/agent-skills/{name}")
async def get_agent_skill_detail(name: str) -> Dict[str, Any]:
    """获取单个 Agent Skill 的 Level 2 SOP 指令与 Level 3 辅助资源。"""
    skill = skill_manager.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return {
        "name": skill.name,
        "metadata": dataclasses.asdict(skill.metadata),
        "instruction_markdown": skill.instructions,
        "scripts": {k: str(v) for k, v in skill.scripts.items()},
        "references": {k: str(v) for k, v in skill.references.items()},
    }


@router.post("/api/agent-skills/match")
async def match_agent_skill(payload: Dict[str, str]) -> Dict[str, Any]:
    """根据任务意图匹配最适用的 Agent Skill。"""
    task = payload.get("task", "")
    matched = skill_manager.match_and_load_for_task(task)
    if matched:
        return {
            "matched": True,
            "skill_name": matched.name,
            "metadata": dataclasses.asdict(matched.metadata),
            "instruction_snippet": (
                matched.instructions[:300] + "..."
                if len(matched.instructions) > 300
                else matched.instructions
            ),
        }
    return {"matched": False, "skill_name": None}


