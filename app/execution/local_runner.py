"""LocalExecutionRunner — 本地执行环境。

当前默认 Runner，在本地进程中执行 pytest。
使用同步 subprocess + run_in_executor 避免 Windows event loop 兼容问题。
"""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
import time
from pathlib import Path

from app.execution.base import BaseExecutionRunner, ExecutionResult

_MAX_OUTPUT = 50 * 1024  # 50KB
_TIMEOUT = 30  # seconds


class LocalExecutionRunner(BaseExecutionRunner):
    """本地执行环境 — 在本地进程中运行 pytest。

    体现多态：与 BaseExecutionRunner 接口一致，
    但具体执行逻辑是本地 subprocess。
    """

    async def run_pytest(
        self,
        workspace_path: str,
        target: str | None = None,
    ) -> ExecutionResult:
        ws = Path(workspace_path).resolve()
        if not ws.exists():
            return ExecutionResult(error=f"workspace 不存在 — {workspace_path}")

        # 构建 pytest 命令
        cmd = [sys.executable, "-m", "pytest"]

        if target:
            target_path = (ws / target).resolve()
            if not str(target_path).startswith(str(ws)):
                return ExecutionResult(error=f"target 路径超出范围 — {target}")
            cmd.append(str(target_path))

        cmd.extend(["-v", "--tb=short", "--no-header"])

        t0 = time.monotonic()
        try:
            # 使用同步 subprocess + run_in_executor 避免 Windows ProactorEventLoop 问题
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    cwd=str(ws),
                    capture_output=True,
                    timeout=_TIMEOUT,
                ),
            )
        except subprocess.TimeoutExpired:
            duration = int((time.monotonic() - t0) * 1000)
            return ExecutionResult(
                error=f"pytest 执行超时 ({_TIMEOUT}s)",
                duration_ms=duration,
            )

        duration = int((time.monotonic() - t0) * 1000)
        stdout_str = result.stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
        stderr_str = result.stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT]

        passed, failed = _parse_summary(stdout_str)

        return ExecutionResult(
            success=result.returncode == 0,
            return_code=result.returncode,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration,
            passed=passed,
            failed=failed,
        )


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
