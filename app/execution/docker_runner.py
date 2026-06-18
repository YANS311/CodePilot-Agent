"""DockerExecutionRunner — Docker 隔离执行环境。

最小版本：仅支持 pytest，不支持 pip/apt/联网。
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

from app.execution.base import BaseExecutionRunner, ExecutionResult

_MAX_OUTPUT = 50 * 1024  # 50KB
_TIMEOUT = 30  # seconds
_DOCKER_IMAGE = "python:3.12-slim"


class DockerExecutionRunner(BaseExecutionRunner):
    """Docker 执行环境 — 在隔离容器中运行 pytest。

    体现多态：与 BaseExecutionRunner 接口一致，
    但具体执行逻辑是 docker run。

    安全限制：
    - 只读挂载 workspace
    - 不支持 pip install / apt install
    - 网络隔离
    """

    async def run_pytest(
        self,
        workspace_path: str,
        target: str | None = None,
    ) -> ExecutionResult:
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return ExecutionResult(error=f"workspace 不存在 — {workspace_path}")

        # 先检查 Docker 是否可用
        if not await self._docker_available():
            return ExecutionResult(error="Docker 不可用，请确认 Docker 已安装并运行")

        # 检查镜像是否存在
        if not await self._image_exists():
            return ExecutionResult(
                error=f"Docker 镜像 {_DOCKER_IMAGE} 不存在，请先拉取"
            )

        # 构建 pytest 命令
        pytest_cmd = "python -m pytest -v --tb=short --no-header"
        if target:
            # 校验 target 路径安全性
            target_path = (ws / target).resolve()
            if not str(target_path).startswith(str(ws)):
                return ExecutionResult(error=f"target 路径超出范围 — {target}")
            pytest_cmd += f" /workspace/{target}"

        # docker run 命令
        cmd = [
            "docker", "run", "--rm",
            "--read-only",  # 只读文件系统
            "--network", "none",  # 无网络
            "-v", f"{ws}:/workspace:ro",  # 只读挂载
            "-w", "/workspace",
            _DOCKER_IMAGE,
            "sh", "-c", pytest_cmd,
        ]

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=_TIMEOUT
            )
        except asyncio.TimeoutError:
            duration = int((time.monotonic() - t0) * 1000)
            # 超时时尝试杀掉容器
            if proc and proc.returncode is None:
                proc.kill()
            return ExecutionResult(
                error=f"pytest 执行超时 ({_TIMEOUT}s)",
                duration_ms=duration,
            )

        duration = int((time.monotonic() - t0) * 1000)
        stdout_str = stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
        stderr_str = stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT]

        passed, failed = _parse_summary(stdout_str)

        return ExecutionResult(
            success=proc.returncode == 0,
            return_code=proc.returncode or 0,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration,
            passed=passed,
            failed=failed,
        )

    @staticmethod
    async def _docker_available() -> bool:
        """检查 Docker 是否可用。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    async def _image_exists() -> bool:
        """检查 Docker 镜像是否已拉取。"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "image", "inspect", _DOCKER_IMAGE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False


def _parse_summary(output: str) -> tuple[int, int]:
    """从 pytest 输出中解析 passed/failed 数量。"""
    passed = 0
    failed = 0

    m_passed = re.search(r"(\d+) passed", output)
    m_failed = re.search(r"(\d+) failed", output)

    if m_passed:
        passed = int(m_passed.group(1))
    if m_failed:
        failed = int(m_failed.group(1))

    return passed, failed
