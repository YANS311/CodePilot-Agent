"""app/mcp/client.py — 轻量级 Model Context Protocol (MCP) 客户端。

基于 JSON-RPC 2.0 规范，提供 stdio 与 SSE (Server-Sent Events) 双传输层支持，
具备异步非阻塞通信、协议握手与工具发现调用能力。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional, Union

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# MCP 协议版本
MCP_PROTOCOL_VERSION = "2024-11-05"


# ═════════════════════════════════════════════════════════════════════
# 1. JSON-RPC 2.0 协议模型 (Pydantic V2)
# ═════════════════════════════════════════════════════════════════════


class JSONRPCError(BaseModel):
    """JSON-RPC 错误对象。"""

    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCRequest(BaseModel):
    """JSON-RPC 请求对象。"""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Union[int, str]
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCNotification(BaseModel):
    """JSON-RPC 通知对象（无 id）。"""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None


class JSONRPCResponse(BaseModel):
    """JSON-RPC 响应对象。"""

    jsonrpc: Literal["2.0"] = "2.0"
    id: Optional[Union[int, str]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


class MCPToolDefinition(BaseModel):
    """MCP 工具定义元数据。"""

    name: str
    description: str = ""
    inputSchema: Dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})


# ═════════════════════════════════════════════════════════════════════
# 2. 传输层抽象 (Transport Layer)
# ═════════════════════════════════════════════════════════════════════


class BaseTransport(ABC):
    """MCP 传输层抽象基类。"""

    @abstractmethod
    async def start(self) -> None:
        """启动传输通道。"""
        ...

    @abstractmethod
    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        """发送 JSON-RPC 请求并等待返回 result，如果出错抛出异常。"""
        ...

    @abstractmethod
    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """发送 JSON-RPC 通知（无响应）。"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """关闭传输通道并释放资源。"""
        ...


class StdioTransport(BaseTransport):
    """基于子进程标准输入输出的 stdio 传输层。

    通过异步流 (asyncio.StreamReader / StreamWriter) 与外部 MCP 进程通信，
    使用换行符分隔的 JSON-RPC 消息。
    """

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd

        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_counter = 0
        self._pending_requests: Dict[Union[int, str], asyncio.Future[Any]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._is_closed = False

    async def start(self) -> None:
        """启动子进程并开启异步读取循环。"""
        if self._process is not None:
            return

        resolved_cmd = shutil.which(self.command) or self.command
        if sys.platform == "win32" and resolved_cmd.lower().endswith((".cmd", ".bat")):
            comspec = os.environ.get("COMSPEC", "cmd.exe")
            cmd_list = [comspec, "/c", resolved_cmd] + self.args
        else:
            cmd_list = [resolved_cmd] + self.args
        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        logger.info("Starting MCP stdio process: %s (cwd=%s)", " ".join(cmd_list), self.cwd)
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd_list,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=merged_env,
            )
        except Exception as exc:
            logger.error("Failed to spawn MCP stdio process: %s", exc)
            raise RuntimeError(f"无法启动 MCP 服务进程 '{self.command}': {exc}") from exc

        self._is_closed = False
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """异步逐行读取子进程标准输出并分发响应。"""
        assert self._process is not None and self._process.stdout is not None
        stdout = self._process.stdout

        while not self._is_closed and not stdout.at_eof():
            try:
                line = await stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                try:
                    data = json.loads(line_str)
                except json.JSONDecodeError:
                    logger.debug("Non-JSON stdout from MCP server: %s", line_str)
                    continue

                # 分发 JSON-RPC 响应
                req_id = data.get("id")
                if req_id is not None and req_id in self._pending_requests:
                    future = self._pending_requests.pop(req_id)
                    if not future.done():
                        if "error" in data and data["error"]:
                            err_dict = data["error"]
                            msg = err_dict.get("message", "Unknown JSON-RPC Error")
                            code = err_dict.get("code", -1)
                            future.set_exception(RuntimeError(f"MCP RPC Error [{code}]: {msg}"))
                        else:
                            future.set_result(data.get("result"))
                else:
                    # 通知或未知 ID
                    logger.debug("Received MCP notification / unhandled message: %s", data)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in MCP stdio read loop: %s", exc)
                break

        # 进程退出或异常，取消所有未决请求
        for fut in self._pending_requests.values():
            if not fut.done():
                fut.set_exception(RuntimeError("MCP stdio process closed unexpectedly"))
        self._pending_requests.clear()

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        """发送 JSON-RPC 请求。"""
        if self._is_closed or self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP StdioTransport 未启动或已关闭")

        self._request_counter += 1
        req_id = self._request_counter
        req = JSONRPCRequest(id=req_id, method=method, params=params)

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending_requests[req_id] = fut

        msg_bytes = req.model_dump_json().encode("utf-8") + b"\n"
        try:
            self._process.stdin.write(msg_bytes)
            await self._process.stdin.drain()
        except Exception as exc:
            self._pending_requests.pop(req_id, None)
            raise RuntimeError(f"向 MCP 服务写入数据失败: {exc}") from exc

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(req_id, None)
            raise asyncio.TimeoutError(f"MCP 请求 '{method}' 超时 (Timeout: {timeout}s)")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """发送通知。"""
        if self._is_closed or self._process is None or self._process.stdin is None:
            return
        notif = JSONRPCNotification(method=method, params=params)
        msg_bytes = notif.model_dump_json().encode("utf-8") + b"\n"
        try:
            self._process.stdin.write(msg_bytes)
            await self._process.stdin.drain()
        except Exception as exc:
            logger.warning("Failed to send MCP notification '%s': %s", method, exc)

    async def close(self) -> None:
        """关闭子进程与读取任务。"""
        self._is_closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()

        if self._process is not None:
            try:
                if self._process.stdin and not self._process.stdin.is_closing():
                    self._process.stdin.close()
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    self._process.kill()
                    await self._process.wait()
            except Exception as exc:
                logger.debug("Error closing MCP process: %s", exc)
            finally:
                self._process = None


class SSETransport(BaseTransport):
    """基于 Server-Sent Events (SSE) / HTTP 的 MCP 传输层。

    支持连接远程或本地 HTTP/SSE 服务的 MCP Server。
    """

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

        self._client: Optional[httpx.AsyncClient] = None
        self._post_endpoint: Optional[str] = None
        self._request_counter = 0
        self._pending_requests: Dict[Union[int, str], asyncio.Future[Any]] = {}
        self._is_closed = False

    async def start(self) -> None:
        """初始化 HTTP 客户端。"""
        if self._client is not None:
            return

        self._client = httpx.AsyncClient(
            headers=self.headers,
            timeout=httpx.Timeout(self.timeout, read=None),
        )
        self._is_closed = False
        self._post_endpoint = self.url

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 30.0) -> Any:
        """发送 JSON-RPC POST 请求。"""
        if self._client is None or self._is_closed:
            raise RuntimeError("MCP SSETransport 未启动或已关闭")

        self._request_counter += 1
        req_id = self._request_counter
        req = JSONRPCRequest(id=req_id, method=method, params=params)

        target_url = self._post_endpoint or self.url
        try:
            resp = await self._client.post(
                target_url,
                json=req.model_dump(exclude_none=True),
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            raise asyncio.TimeoutError(f"MCP SSE 请求 '{method}' 超时 (Timeout: {timeout}s)")
        except Exception as exc:
            raise RuntimeError(f"MCP HTTP POST 请求失败: {exc}") from exc

        if "error" in data and data["error"]:
            err_dict = data["error"]
            msg = err_dict.get("message", "Unknown JSON-RPC Error")
            code = err_dict.get("code", -1)
            raise RuntimeError(f"MCP RPC Error [{code}]: {msg}")

        return data.get("result")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """发送通知。"""
        if self._client is None or self._is_closed:
            return
        notif = JSONRPCNotification(method=method, params=params)
        target_url = self._post_endpoint or self.url
        try:
            await self._client.post(
                target_url,
                json=notif.model_dump(exclude_none=True),
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("Failed to send SSE notification '%s': %s", method, exc)

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        self._is_closed = True
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# ═════════════════════════════════════════════════════════════════════
# 3. 高层 MCP Client 封装
# ═════════════════════════════════════════════════════════════════════


class MCPClient:
    """轻量级 Model Context Protocol (MCP) 客户端。

    封装传输层连接、标准 MCP 协议握手（initialize / initialized）、
    工具发现（tools/list）与工具调用（tools/call）。
    """

    def __init__(self, transport: BaseTransport, client_name: str = "CodePilot-Agent", version: str = "0.1.0") -> None:
        self.transport = transport
        self.client_name = client_name
        self.version = version
        self.is_connected = False
        self.server_info: Dict[str, Any] = {}
        self.server_capabilities: Dict[str, Any] = {}

    async def connect(self) -> None:
        """建立连接并执行 MCP 协议初始化握手。"""
        if self.is_connected:
            return

        await self.transport.start()

        # 1. 发送 initialize 请求
        init_params = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": False},
                "sampling": {},
            },
            "clientInfo": {
                "name": self.client_name,
                "version": self.version,
            },
        }

        try:
            res = await self.transport.send_request("initialize", init_params)
            if isinstance(res, dict):
                self.server_info = res.get("serverInfo", {})
                self.server_capabilities = res.get("capabilities", {})
                logger.info(
                    "MCP connected to server '%s' (protocol %s)",
                    self.server_info.get("name", "unknown"),
                    res.get("protocolVersion", "unknown"),
                )
        except Exception as exc:
            await self.transport.close()
            raise RuntimeError(f"MCP 初始化握手失败: {exc}") from exc

        # 2. 发送 notifications/initialized 通知
        await self.transport.send_notification("notifications/initialized")
        self.is_connected = True

    async def list_tools(self) -> List[MCPToolDefinition]:
        """向 MCP Server 请求可用工具列表 (tools/list)。"""
        if not self.is_connected:
            raise RuntimeError("MCPClient 尚未连接，无法获取工具列表")

        res = await self.transport.send_request("tools/list", {})
        if not isinstance(res, dict) or "tools" not in res:
            return []

        tools_data = res.get("tools", [])
        tool_defs = []
        for t in tools_data:
            if isinstance(t, dict) and "name" in t:
                tool_defs.append(
                    MCPToolDefinition(
                        name=t["name"],
                        description=t.get("description", ""),
                        inputSchema=t.get("inputSchema", {"type": "object", "properties": {}}),
                    )
                )
        return tool_defs

    async def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """调用 MCP 工具 (tools/call)，并格式化返回结果文本。"""
        if not self.is_connected:
            raise RuntimeError("MCPClient 尚未连接，无法调用工具")

        params = {
            "name": name,
            "arguments": arguments or {},
        }
        res = await self.transport.send_request("tools/call", params)

        # 处理 MCP 标准返回结构: { content: [{ type: "text", text: "..." }], isError: bool }
        if isinstance(res, dict):
            is_error = res.get("isError", False)
            content_list = res.get("content", [])
            text_parts = []
            for item in content_list:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "image":
                        text_parts.append(f"[MCP Image: {item.get('mimeType', 'unknown')}]")
                    elif item.get("type") == "resource":
                        text_parts.append(f"[MCP Resource: {item.get('resource', {})}]")
                elif isinstance(item, str):
                    text_parts.append(item)

            output_text = "\n".join(text_parts) if text_parts else json.dumps(res, ensure_ascii=False)
            if is_error:
                return f"错误: {output_text}"
            return output_text

        return str(res)

    async def close(self) -> None:
        """关闭客户端连接。"""
        if self.is_connected or self.transport is not None:
            try:
                await self.transport.close()
            finally:
                self.is_connected = False

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
