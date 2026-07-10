"""Tool for running tests inside a workspace."""

from __future__ import annotations

import json
from typing import Any

from app.execution.factory import RunnerFactory
from app.language.detector import LanguageDetector
from app.tools.workspace_tool import WorkspaceTool

_MAX_TEXT_FIELD_BYTES = 45 * 1024


def _truncate_text(value: str, max_bytes: int = _MAX_TEXT_FIELD_BYTES) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker = "\n... [truncated]"
    marker_bytes = marker.encode("utf-8")
    keep = max(0, max_bytes - len(marker_bytes))
    return encoded[:keep].decode("utf-8", errors="ignore") + marker


class RunTestsTool(WorkspaceTool):
    """Run workspace tests and always return a JSON payload."""

    name = "run_tests"
    description = "Run tests inside the workspace. Optionally pass a test target file or node id."
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "Optional test target, for example 'tests/test_example.py'. Empty runs all tests.",
                "default": "",
            },
        },
    }

    def __init__(self, *, mode: str | None = None) -> None:
        self._mode = mode
        self._detector = LanguageDetector()

    def _json_result(
        self,
        *,
        success: bool,
        passed: int = 0,
        failed: int = 0,
        stdout: str = "",
        stderr: str = "",
        duration_ms: int = 0,
        error: str = "",
        **extra: Any,
    ) -> str:
        output = {
            "success": success,
            "passed": passed,
            "failed": failed,
            "stdout": _truncate_text(stdout),
            "stderr": _truncate_text(stderr),
            "duration_ms": duration_ms,
            "error": error,
        }
        output.update(extra)
        return json.dumps(output, ensure_ascii=False)

    async def run(self, *, workspace_root: str, target: str = "", **_) -> str:
        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self._json_result(
                success=False,
                error=f"workspace does not exist: {workspace_root}",
            )

        detection = self._detector.detect(str(ws))
        primary_lang = detection["primary_language"]

        if not primary_lang:
            return self._json_result(
                success=False,
                error="could not detect a programming language in workspace",
                detected_languages=detection["detected_languages"],
            )

        adapter = self._detector.get_adapter(primary_lang)
        if adapter is None:
            return self._json_result(
                success=False,
                error=f"unsupported language: {primary_lang}",
                language_detected=primary_lang,
                detected_languages=detection["detected_languages"],
            )

        if primary_lang == "python":
            return await self._run_python(ws, target)

        return self._json_result(
            success=False,
            language_detected=primary_lang,
            message=f"language {primary_lang} detected, but test execution is not supported",
            test_command=adapter.get_test_command(target or None),
            detected_languages=detection["detected_languages"],
        )

    async def _run_python(self, ws, target: str) -> str:
        from app.core.config import settings

        mode = self._mode or settings.execution_mode
        runner = RunnerFactory.create(mode)

        result = await runner.run_pytest(
            workspace_path=str(ws),
            target=target or None,
        )

        if result.error:
            return self._json_result(
                success=False,
                passed=result.passed,
                failed=result.failed,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=result.duration_ms,
                error=result.error,
            )

        return self._json_result(
            success=result.success,
            passed=result.passed,
            failed=result.failed,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
        )
