"""API 客户端模块 — 包含多个 Bug 用于评测。"""

from __future__ import annotations

import json
from typing import Any
from urllib.request import urlopen, Request
from urllib.error import HTTPError


class APIClient:
    """简单的 HTTP API 客户端。"""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers: dict[str, str] = {}

    def set_header(self, key: str, value: str) -> None:
        """设置请求头。"""
        self.headers[key] = value

    def get(self, path: str) -> dict[str, Any]:
        """发送 GET 请求。"""
        url = f"{self.base_url}{path}"
        req = Request(url, headers=self.headers)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            return {"error": str(e), "status": e.code}  # BUG: 应该返回 e.code 但用的是 str(e)

    def post(self, path: str, data: dict) -> dict[str, Any]:
        """发送 POST 请求。"""
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers=self.headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            return {"error": str(e)}

    def build_url(self, path: str, params: dict[str, str] | None = None) -> str:
        """构建完整 URL。"""
        url = f"{self.base_url}{path}"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url += f"?{query}"  # BUG: 没有对参数值进行 URL encode
        return url

    def parse_response(self, raw: str) -> dict[str, Any]:
        """解析 JSON 响应。"""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"error": "Invalid JSON", "raw": raw}  # BUG: 缺少 status 字段

    def retry_request(self, path: str, max_retries: int = 3) -> dict[str, Any]:
        """带重试的 GET 请求。"""
        last_error = None
        for attempt in range(max_retries):
            try:
                return self.get(path)
            except Exception as e:
                last_error = e  # BUG: 没有 sleep，会立即重试
        return {"error": f"Failed after {max_retries} retries: {last_error}"}
