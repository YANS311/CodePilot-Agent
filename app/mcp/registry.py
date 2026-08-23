"""app/mcp/registry.py — MCP 工具动态转换与注册中心。

将外部 MCP Server 列出的工具动态封装为 CodePilot Agent 兼容的 BaseTool 实例 (MCPTool)，
提供多 Server 生命周期治理、Workspace 路径穿越防御 (Path Traversal Guard) 以及异步执行超时控制。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.mcp.client import MCPClient, MCPToolDefinition, SSETransport, StdioTransport
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# 潜在包含文件/路径的参数名集合
_PATH_PARAM_KEYS = frozenset({
    "path", "paths", "file_path", "filepath", "file_paths", "filepaths",
    "dir", "directory", "dir_path", "directory_path",
    "target", "target_path", "source", "source_path", "destination",
    "dest", "file", "filename", "relative_path", "uri",
})

# 敏感文件/目录阻止匹配
_BLOCKED_NAMES = frozenset({".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"})


class MCPServerConfig(BaseModel):
    """MCP Server 注册配置模型。"""

    name: str = Field(..., description="Server 唯一标识名称")
    transport: Literal["stdio", "sse"] = Field("stdio", description="传输协议类型")
    # stdio 配置
    command: Optional[str] = Field(None, description="stdio 进程启动命令 (如 npx 或 python)")
    args: List[str] = Field(default_factory=list, description="命令行参数列表")
    env: Dict[str, str] = Field(default_factory=dict, description="子进程环境变量")
    cwd: Optional[str] = Field(None, description="子进程工作目录")
    # sse 配置
    url: Optional[str] = Field(None, description="SSE / HTTP 服务端点 URL")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    # 通用配置
    timeout: float = Field(30.0, description="默认调用超时时间 (秒)")
    auto_register: bool = Field(True, description="是否自动挂载到 ToolRegistry")
    namespace_tools: bool = Field(False, description="是否为工具名称添加 Server 前缀")


class MCPTool(BaseTool):
    """MCP 工具包装器 — 继承 CodePilot Agent 的 BaseTool。

    动态代理外部 MCP Server 的 tools/call 请求，并强制注入：
    1. Workspace 边界与 Path Traversal 安全拦截
    2. 异步非阻塞超时控制 (Timeout)
    3. 异常降级与结构化结果转换
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        client: MCPClient,
        server_name: str,
        original_name: Optional[str] = None,
        timeout: float = 30.0,
        enforce_path_guardrail: bool = True,
    ) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self.client = client
        self.server_name = server_name
        self.original_name = original_name or name
        self.timeout = timeout
        self.enforce_path_guardrail = enforce_path_guardrail

    def _check_path_security(self, args: Dict[str, Any], workspace_root: str) -> Optional[str]:
        """检查参数中是否存在路径穿越或敏感文件访问风险。

        Returns:
            若违规则返回错误提示字符串，否则返回 None。
        """
        if not workspace_root:
            return None

        ws_resolved = Path(workspace_root).resolve()

        def _validate_single_path(val: str) -> Optional[str]:
            raw_path = str(val).strip()
            if not raw_path:
                return None

            # 阻止绝对系统敏感路径或跨驱动器访问
            p = Path(raw_path)
            target = (ws_resolved / p).resolve() if not p.is_absolute() else p.resolve()

            # 路径穿越检查：必须位于 workspace_root 目录下
            try:
                target.relative_to(ws_resolved)
            except ValueError:
                return f"SECURITY_BLOCKED: 路径超出 workspace 范围 — {raw_path}"

            # 敏感文件检查
            name_lower = target.name.lower()
            if name_lower in _BLOCKED_NAMES:
                return f"SECURITY_BLOCKED: 禁止访问敏感配置文件 — {raw_path}"

            # 禁止修改 .git 内部
            if ".git" in target.parts:
                return f"SECURITY_BLOCKED: 禁止操作 .git 仓库核心目录 — {raw_path}"

            return None

        # 1. 优先扫描已知 path 键
        for k, v in args.items():
            k_lower = k.lower()
            if k_lower in _PATH_PARAM_KEYS:
                if isinstance(v, str):
                    err = _validate_single_path(v)
                    if err:
                        return err
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str):
                            err = _validate_single_path(item)
                            if err:
                                return err

        # 2. 检查任何包含明显穿越特征的字符串参数
        for v in args.values():
            if isinstance(v, str) and ("../" in v or "..\\" in v):
                err = _validate_single_path(v)
                if err:
                    return err

        return None

    async def run(self, *, workspace_root: str, **kwargs: Any) -> str:
        """执行 MCP 工具调用。

        执行安全校验 -> 异步调用 MCP Client -> 超时熔断保护 -> 结果格式化。
        """
        # 1. Workspace 安全拦截
        if self.enforce_path_guardrail:
            sec_err = self._check_path_security(kwargs, workspace_root)
            if sec_err:
                logger.warning("MCPTool '%s' security blocked: %s", self.name, sec_err)
                return sec_err

        # 2. 异步调用与超时保护
        try:
            output = await asyncio.wait_for(
                self.client.call_tool(self.original_name, kwargs),
                timeout=self.timeout,
            )
            return output
        except asyncio.TimeoutError:
            logger.error("MCPTool '%s' timed out after %ss", self.name, self.timeout)
            return f"错误: MCP 工具 '{self.name}' 执行超时 (Timeout: {self.timeout}s)"
        except Exception as exc:
            logger.exception("MCPTool '%s' execution failed: %s", self.name, exc)
            return f"错误: MCP 工具 '{self.name}' 执行失败 — {type(exc).__name__}: {exc}"

    def to_metadata(self) -> Dict[str, Any]:
        """导出统一元数据。"""
        return {
            "name": self.name,
            "description": self.description,
            "source": "mcp",
            "server": self.server_name,
            "original_name": self.original_name,
            "parameters": self.parameters,
            "timeout": self.timeout,
            "enabled": True,
        }


class MCPRegistry:
    """MCP 插件与服务器集中管理器。

    管理多个本地或远程 MCP Server 的配置、连接握手、工具发现与 BaseTool 挂载。
    """

    def __init__(self) -> None:
        self._configs: Dict[str, MCPServerConfig] = {}
        self._clients: Dict[str, MCPClient] = {}
        self._tools: Dict[str, MCPTool] = {}

    def register_server(self, config: MCPServerConfig) -> MCPClient:
        """注册并创建 MCPClient（未连接状态）。"""
        if config.name in self._configs:
            raise ValueError(f"MCP Server '{config.name}' 已存在")

        self._configs[config.name] = config

        if config.transport == "stdio":
            if not config.command:
                raise ValueError(f"Stdio MCP Server '{config.name}' 必须指定 command")
            transport = StdioTransport(
                command=config.command,
                args=config.args,
                env=config.env,
                cwd=config.cwd,
            )
        elif config.transport == "sse":
            if not config.url:
                raise ValueError(f"SSE MCP Server '{config.name}' 必须指定 url")
            transport = SSETransport(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
            )
        else:
            raise ValueError(f"不支持的传输协议: {config.transport}")

        client = MCPClient(transport=transport, client_name="CodePilot-Agent")
        self._clients[config.name] = client
        return client

    def register_client(self, name: str, client: MCPClient, config: Optional[MCPServerConfig] = None) -> None:
        """直接注册已构建的 MCPClient（便于自定义 Transport 或 Mock 测试）。"""
        if name in self._clients:
            raise ValueError(f"MCP Server '{name}' 已存在")
        self._clients[name] = client
        if config:
            self._configs[name] = config
        else:
            self._configs[name] = MCPServerConfig(name=name, transport="stdio", command="custom")

    def load_from_dict(self, data: Dict[str, Any]) -> List[str]:
        """从配置字典中批量加载 MCP Server 配置。
        
        支持标准格式:
        {"mcpServers": {"server_name": {"transport": "stdio", "command": "...", "args": []}}}
        """
        registered: List[str] = []
        servers = data.get("mcpServers", data)
        for srv_name, srv_conf in servers.items():
            if not isinstance(srv_conf, dict):
                continue
            conf_data = dict(srv_conf)
            conf_data.setdefault("name", srv_name)
            cfg = MCPServerConfig(**conf_data)
            self.register_server(cfg)
            registered.append(srv_name)
        return registered

    def load_from_json(self, json_path: str | Path) -> List[str]:
        """从 JSON 配置文件 (如 mcp.json) 批量加载并注册 MCP Server。"""
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"MCP 配置文件不存在: {json_path}")
        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self.load_from_dict(data)

    def unregister_server(self, name: str) -> None:
        """注销 MCP Server。"""
        self._configs.pop(name, None)
        self._clients.pop(name, None)
        # 移除该 server 关联的 tools
        self._tools = {k: t for k, t in self._tools.items() if t.server_name != name}

    def get_client(self, name: str) -> Optional[MCPClient]:
        """获取指定名称的 MCPClient。"""
        return self._clients.get(name)

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """获取已加载的 MCPTool。"""
        return self._tools.get(name)

    def list_servers(self) -> List[str]:
        """返回当前所有已注册的 MCP Server 名称。"""
        return list(self._clients.keys())

    def list_tools(self) -> List[MCPTool]:
        """返回当前所有已挂载的 MCPTool 实例。"""
        return list(self._tools.values())

    async def connect_server(self, name: str) -> List[MCPTool]:
        """连接单个 MCP Server，执行握手并拉取工具列表转化为 MCPTool。"""
        client = self._clients.get(name)
        if client is None:
            raise ValueError(f"未找到已注册的 MCP Server: '{name}'")

        cfg = self._configs.get(name)
        timeout = cfg.timeout if cfg else 30.0
        namespace_tools = cfg.namespace_tools if cfg else False

        await client.connect()
        tool_defs = await client.list_tools()

        created_tools: List[MCPTool] = []
        for t_def in tool_defs:
            tool_name = f"mcp_{name}_{t_def.name}" if namespace_tools else t_def.name
            mcp_tool = MCPTool(
                name=tool_name,
                description=t_def.description,
                parameters=t_def.inputSchema,
                client=client,
                server_name=name,
                original_name=t_def.name,
                timeout=timeout,
            )
            self._tools[tool_name] = mcp_tool
            created_tools.append(mcp_tool)
            logger.info("Loaded MCP tool: %s from server '%s'", tool_name, name)

        return created_tools

    async def connect_all(self) -> List[MCPTool]:
        """连接所有已注册的 MCP Server 并加载全部工具。"""
        all_tools: List[MCPTool] = []
        for name in list(self._clients.keys()):
            try:
                tools = await self.connect_server(name)
                all_tools.extend(tools)
            except Exception as exc:
                logger.error("Failed to connect to MCP server '%s': %s", name, exc)
        return all_tools

    def mount_to_tool_registry(self, tool_registry: Any) -> int:
        """将所有已加载的 MCPTool 动态注入到 CodePilot 的 ToolRegistry 中。

        Args:
            tool_registry: ToolRegistry 实例。

        Returns:
            成功注入的工具数量。
        """
        count = 0
        for tool in self._tools.values():
            try:
                # 若已存在同名工具则先卸载或覆盖
                if tool.name in tool_registry._tools:
                    logger.warning("Overriding existing tool '%s' with MCP tool", tool.name)
                    tool_registry._tools[tool.name] = tool
                else:
                    tool_registry.register(tool)
                count += 1
            except Exception as exc:
                logger.warning("Failed to mount MCP tool '%s' to ToolRegistry: %s", tool.name, exc)
        logger.info("Successfully mounted %d MCP tools to ToolRegistry", count)
        return count

    async def disconnect_server(self, name: str) -> None:
        """断开指定 MCP Server 连接并释放资源。"""
        client = self._clients.get(name)
        if client:
            await client.close()
        # 清除该 server 的 tools
        self._tools = {k: t for k, t in self._tools.items() if t.server_name != name}

    async def disconnect_all(self) -> None:
        """断开所有已连接的 MCP Server。"""
        for name, client in self._clients.items():
            try:
                await client.close()
            except Exception as exc:
                logger.debug("Error disconnecting MCP client '%s': %s", name, exc)
        self._tools.clear()

    def get_tools_metadata(self) -> List[Dict[str, Any]]:
        """导出所有 MCP 工具的元数据描述。"""
        return [t.to_metadata() for t in self._tools.values()]


# 全局单例 MCPRegistry
mcp_registry = MCPRegistry()
