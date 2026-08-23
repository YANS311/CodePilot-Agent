"""app/mcp/server.py — 标准轻量级 Python MCP (Model Context Protocol) Server。

支持基于 stdio (stdin/stdout) 的标准 JSON-RPC 2.0 协议交互，
可作为独立子进程供 MCPClient (StdioTransport) 直连调用，无需任何外部 Mock。
"""

from __future__ import annotations

import json
import os
import platform
import sys
from typing import Any, Dict, List


class StandardMCPServer:
    """标准轻量级 MCP 服务端实现 (stdio 传输)。"""

    def __init__(self, server_name: str = "codepilot-mcp-server", version: str = "0.1.0") -> None:
        self.server_name = server_name
        self.version = version
        self.tools: Dict[str, Dict[str, Any]] = {
            "echo": {
                "name": "echo",
                "description": "Echo back input text message",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Text to echo back"}
                    },
                    "required": ["message"],
                },
            },
            "get_system_info": {
                "name": "get_system_info",
                "description": "Get current operating system and Python runtime info",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
            "calculate": {
                "name": "calculate",
                "description": "Perform basic arithmetic addition or multiplication",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "op": {"type": "string", "enum": ["add", "multiply", "subtract"]},
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["op", "a", "b"],
                },
            },
            "list_dir": {
                "name": "list_dir",
                "description": "List files in the target directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Target relative directory path"}
                    },
                    "required": ["path"],
                },
            },
        }

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any] | None:
        """处理单条 JSON-RPC 请求。"""
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {}) or {}

        # 1. 协议初始化握手
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": self.server_name,
                        "version": self.version,
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }

        # 2. 初始化通知 (无返回值)
        elif method == "notifications/initialized":
            return None

        # 3. 获取工具列表
        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": list(self.tools.values()),
                },
            }

        # 4. 执行工具调用
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            res_content, is_error = self._execute_tool(tool_name, args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": res_content}],
                    "isError": is_error,
                },
            }

        # 未知方法
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method '{method}' not found",
            },
        }

    def _execute_tool(self, name: str, args: Dict[str, Any]) -> tuple[str, bool]:
        """执行具体工具逻辑。"""
        if name == "echo":
            msg = str(args.get("message", ""))
            return f"Echo: {msg}", False

        elif name == "get_system_info":
            info = {
                "os": platform.system(),
                "release": platform.release(),
                "python": platform.python_version(),
                "pid": os.getpid(),
            }
            return json.dumps(info, ensure_ascii=False), False

        elif name == "calculate":
            op = args.get("op", "add")
            a = float(args.get("a", 0))
            b = float(args.get("b", 0))
            if op == "add":
                return str(a + b), False
            elif op == "multiply":
                return str(a * b), False
            elif op == "subtract":
                return str(a - b), False
            return f"Unknown operation: {op}", True

        elif name == "list_dir":
            path = args.get("path", ".")
            try:
                if os.path.exists(path) and os.path.isdir(path):
                    items = os.listdir(path)
                    return "\n".join(items[:50]), False
                return f"Directory not found: {path}", True
            except Exception as exc:
                return f"Error listing dir: {exc}", True

        return f"Tool '{name}' not found", True

    def run_stdio_loop(self) -> None:
        """从标准输入逐行读取请求，处理并将响应写入标准输出。"""
        for line in sys.stdin:
            line_str = line.strip()
            if not line_str:
                continue

            try:
                req = json.loads(line_str)
                resp = self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
            except Exception as exc:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32700,
                        "message": f"Parse error or exception: {exc}",
                    },
                }
                sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def main() -> None:
    server = StandardMCPServer()
    server.run_stdio_loop()


if __name__ == "__main__":
    main()
