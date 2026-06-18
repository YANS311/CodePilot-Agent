"""RunTestsTool — 执行 workspace 内的 pytest 测试。

通过 RunnerFactory 获取 ExecutionRunner，
Tool 只负责业务逻辑（参数校验、结果格式化），
Runner 负责执行环境（本地进程 / Docker 容器）。
"""

from __future__ import annotations

import json

from app.execution.factory import RunnerFactory
from app.tools.workspace_tool import WorkspaceTool


class RunTestsTool(WorkspaceTool):
    """执行 workspace 内的 pytest 测试 — 继承 WorkspaceTool。"""

    name = "run_tests"
    description = "执行 workspace 内的 pytest 测试。可选指定测试目标文件。"
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "可选的测试目标，如 'tests/test_example.py'。留空则运行所有测试。",
                "default": "",
            },
        },
    }

    def __init__(self, *, mode: str | None = None) -> None:
        """初始化 RunTestsTool。

        Args:
            mode: 执行模式。为 None 时使用配置中的 EXECUTION_MODE。
        """
        self._mode = mode

    async def run(self, *, workspace_root: str, target: str = "", **_) -> str:
        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self.error(f"workspace 不存在 — {workspace_root}")

        # 通过 Factory 获取 Runner — 体现工厂模式
        from app.core.config import settings

        mode = self._mode or settings.execution_mode
        runner = RunnerFactory.create(mode)

        # Runner 负责执行，Tool 只负责结果格式化
        result = await runner.run_pytest(
            workspace_path=str(ws),
            target=target or None,
        )

        # 如果 Runner 返回错误（非执行结果），直接返回错误字符串
        if result.error:
            return self.error(result.error)

        output = {
            "success": result.success,
            "passed": result.passed,
            "failed": result.failed,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
        }

        return json.dumps(output, ensure_ascii=False)
