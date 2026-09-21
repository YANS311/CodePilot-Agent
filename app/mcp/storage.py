"""app/mcp/storage.py — 动态 MCP Server 运行时配置持久化存储。

职责：
将通过 GUI / API 动态注册的 MCP Server 配置持久化至 data/mcp_servers.json，
实现服务重启后的自动恢复。

原则：
1. 不污染根目录 mcp.json (mcp.json 保留为开发期静态配置)
2. 异常安全降级，文件损坏不阻断系统启动
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from app.mcp.registry import MCPServerConfig

logger = logging.getLogger(__name__)

_DEFAULT_STORAGE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mcp_servers.json"


class MCPConfigStore:
    """动态 MCP Server 配置文件持久化管理器。"""

    def __init__(self, storage_path: Optional[str | Path] = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else _DEFAULT_STORAGE_PATH

    def load_servers(self) -> Dict[str, MCPServerConfig]:
        """从持久化文件加载已保存的 MCP Server 配置字典。"""
        if not self.storage_path.exists():
            return {}

        try:
            content = self.storage_path.read_text(encoding="utf-8").strip()
            if not content:
                return {}

            data = json.loads(content)
            servers_dict: Dict[str, Any] = data.get("mcpServers", data)
            if not isinstance(servers_dict, dict):
                logger.warning("mcp_servers.json format invalid: root is not a dict")
                return {}

            loaded: Dict[str, MCPServerConfig] = {}
            for name, srv_conf in servers_dict.items():
                if not isinstance(srv_conf, dict):
                    continue
                conf = dict(srv_conf)
                conf.setdefault("name", name)
                try:
                    loaded[name] = MCPServerConfig(**conf)
                except Exception as exc:
                    logger.warning("Failed to parse MCPServerConfig for '%s': %s", name, exc)

            logger.info("Loaded %d dynamic MCP server(s) from %s", len(loaded), self.storage_path)
            return loaded
        except Exception as exc:
            logger.warning("Failed to load mcp_servers.json: %s", exc)
            return {}

    def save_server(self, config: MCPServerConfig) -> None:
        """保存或更新单个 MCP Server 配置至持久化文件。"""
        servers = self.load_servers()
        servers[config.name] = config
        self._write_servers(servers)
        logger.info("Persisted MCP server '%s' to %s", config.name, self.storage_path)

    def remove_server(self, name: str) -> bool:
        """从持久化文件中删除指定 MCP Server 配置。"""
        servers = self.load_servers()
        if name not in servers:
            return False

        servers.pop(name, None)
        self._write_servers(servers)
        logger.info("Removed MCP server '%s' from %s", name, self.storage_path)
        return True

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """获取单个已持久化的 MCP Server 配置。"""
        servers = self.load_servers()
        return servers.get(name)

    def _write_servers(self, servers: Dict[str, MCPServerConfig]) -> None:
        """安全写回 JSON 文件。"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "mcpServers": {name: cfg.model_dump() for name, cfg in servers.items()}
            }
            self.storage_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.error("Failed to write to %s: %s", self.storage_path, exc)
            raise


# 全局单例
mcp_config_store = MCPConfigStore()
