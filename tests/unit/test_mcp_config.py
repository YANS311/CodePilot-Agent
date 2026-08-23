from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.mcp.registry import MCPServerConfig, MCPRegistry


class TestMCPConfigLoading:
    def test_load_from_dict(self):
        reg = MCPRegistry()
        config_data = {
            "mcpServers": {
                "server_a": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "app.mcp.server"],
                    "timeout": 15.0,
                },
                "server_b": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "app.mcp.server"],
                    "timeout": 20.0,
                },
            }
        }
        loaded = reg.load_from_dict(config_data)
        assert len(loaded) == 2
        assert "server_a" in loaded
        assert "server_b" in loaded

        client_a = reg.get_client("server_a")
        assert client_a is not None

    def test_load_from_json_file(self):
        reg = MCPRegistry()
        mcp_json_path = PROJECT_ROOT / "mcp.json"
        assert mcp_json_path.exists()

        loaded = reg.load_from_json(mcp_json_path)
        assert len(loaded) >= 1
        assert "local_helper" in loaded

    def test_duplicate_server_registration_raises(self):
        reg = MCPRegistry()
        cfg = MCPServerConfig(name="srv1", transport="stdio", command="python")
        reg.register_server(cfg)
        with pytest.raises(ValueError):
            reg.register_server(cfg)
