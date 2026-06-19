"""RunTestsTool — 执行 workspace 内的测试。

通过 LanguageAdapter 获取测试命令，
通过 RunnerFactory 获取 ExecutionRunner 执行。
当前只有 Python Adapter 完整支持测试执行。
"""

from __future__ import annotations

import json

from app.execution.factory import RunnerFactory
from app.language.detector import LanguageDetector
from app.tools.workspace_tool import WorkspaceTool


class RunTestsTool(WorkspaceTool):
    """执行 workspace 内的测试 — 继承 WorkspaceTool，支持多语言适配。"""

    name = "run_tests"
    description = "执行 workspace 内的测试。可选指定测试目标文件。支持自动语言检测。"
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
        self._mode = mode
        self._detector = LanguageDetector()

    async def run(self, *, workspace_root: str, target: str = "", **_) -> str:
        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self.error(f"workspace 不存在 — {workspace_root}")

        # 检测语言
        detection = self._detector.detect(str(ws))
        primary_lang = detection["primary_language"]

        if not primary_lang:
            return self.error("无法检测 workspace 中的编程语言")

        adapter = self._detector.get_adapter(primary_lang)
        if adapter is None:
            return self.error(f"不支持的语言: {primary_lang}")

        # Python — 完整支持
        if primary_lang == "python":
            return await self._run_python(ws, target)

        # 其他语言 — 返回提示
        return json.dumps({
            "success": False,
            "language_detected": primary_lang,
            "message": f"语言 {primary_lang} 已检测到，但测试执行暂不支持",
            "test_command": adapter.get_test_command(target or None),
            "detected_languages": detection["detected_languages"],
        }, ensure_ascii=False)

    async def _run_python(self, ws, target: str) -> str:
        """Python 测试执行 — 完整支持。"""
        from app.core.config import settings

        mode = self._mode or settings.execution_mode
        runner = RunnerFactory.create(mode)

        result = await runner.run_pytest(
            workspace_path=str(ws),
            target=target or None,
        )

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
