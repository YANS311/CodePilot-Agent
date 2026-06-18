"""D9 Tests — ExecutionRunner 测试。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.execution.base import BaseExecutionRunner, ExecutionResult
from app.execution.local_runner import LocalExecutionRunner
from app.execution.factory import RunnerFactory
from app.tools.run_tests import RunTestsTool

WORKSPACE = str(PROJECT_ROOT / "workspace")


# ═══════════════════════════════════════════
# 1. ExecutionResult dataclass
# ═══════════════════════════════════════════


class TestExecutionResult:
    def test_default_values(self):
        r = ExecutionResult()
        assert r.success is False
        assert r.return_code == -1
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.duration_ms == 0
        assert r.passed == 0
        assert r.failed == 0
        assert r.error == ""

    def test_custom_values(self):
        r = ExecutionResult(
            success=True,
            return_code=0,
            stdout="ok",
            passed=5,
            duration_ms=123,
        )
        assert r.success is True
        assert r.passed == 5
        assert r.duration_ms == 123


# ═══════════════════════════════════════════
# 2. BaseExecutionRunner ABC
# ═══════════════════════════════════════════


class TestBaseExecutionRunner:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseExecutionRunner()

    def test_local_runner_is_subclass(self):
        assert issubclass(LocalExecutionRunner, BaseExecutionRunner)


# ═══════════════════════════════════════════
# 3. LocalRunner success
# ═══════════════════════════════════════════


class TestLocalRunnerSuccess:
    def test_run_all_tests(self):
        """运行 workspace 内所有测试 — 验证 runner 正常工作。"""
        runner = LocalExecutionRunner()
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_pytest(WORKSPACE)
        )
        # workspace 可能有预置的失败测试，只要求发现并执行了测试
        assert result.passed + result.failed > 0
        assert result.duration_ms > 0

    def test_run_specific_file(self):
        runner = LocalExecutionRunner()
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_pytest(WORKSPACE, target="tests/test_health.py")
        )
        assert result.success is True
        assert result.passed >= 1
        assert result.duration_ms > 0

    def test_stdout_not_empty(self):
        runner = LocalExecutionRunner()
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_pytest(WORKSPACE, target="tests/test_health.py")
        )
        assert "PASSED" in result.stdout or "passed" in result.stdout


# ═══════════════════════════════════════════
# 4. LocalRunner failure
# ═══════════════════════════════════════════


class TestLocalRunnerFailure:
    def test_failing_test(self):
        ws = Path(WORKSPACE)
        test_file = ws / "test_must_fail.py"
        test_file.write_text(
            "def test_fail():\n    assert False, 'intentional failure'\n",
            encoding="utf-8",
        )
        try:
            runner = LocalExecutionRunner()
            result = asyncio.get_event_loop().run_until_complete(
                runner.run_pytest(WORKSPACE, target="test_must_fail.py")
            )
            assert result.success is False
            assert result.failed >= 1
            assert result.return_code != 0
        finally:
            test_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════
# 5. LocalRunner timeout
# ═══════════════════════════════════════════


class TestLocalRunnerTimeout:
    def test_timeout_returns_error(self):
        ws = Path(WORKSPACE)
        test_file = ws / "test_infinite.py"
        test_file.write_text(
            "import time\ndef test_infinite():\n    time.sleep(60)\n",
            encoding="utf-8",
        )
        try:
            runner = LocalExecutionRunner()
            result = asyncio.get_event_loop().run_until_complete(
                runner.run_pytest(WORKSPACE, target="test_infinite.py")
            )
            assert result.success is False
            assert "超时" in result.error or "Timeout" in result.error
            assert result.duration_ms > 0
        finally:
            test_file.unlink(missing_ok=True)


# ═══════════════════════════════════════════
# 6. LocalRunner invalid input
# ═══════════════════════════════════════════


class TestLocalRunnerInvalid:
    def test_traversal_blocked(self):
        runner = LocalExecutionRunner()
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_pytest(WORKSPACE, target="../../etc/passwd")
        )
        assert result.success is False
        assert "超出" in result.error

    def test_nonexistent_workspace(self):
        runner = LocalExecutionRunner()
        result = asyncio.get_event_loop().run_until_complete(
            runner.run_pytest("/nonexistent/path")
        )
        assert result.success is False
        assert "不存在" in result.error


# ═══════════════════════════════════════════
# 7. RunnerFactory
# ═══════════════════════════════════════════


class TestRunnerFactory:
    def test_create_local(self):
        runner = RunnerFactory.create("local")
        assert isinstance(runner, LocalExecutionRunner)

    def test_create_unknown_raises(self):
        with pytest.raises(ValueError, match="未知的执行模式"):
            RunnerFactory.create("nonexistent")

    def test_available_modes_includes_local(self):
        modes = RunnerFactory.available_modes()
        assert "local" in modes

    def test_factory_returns_different_instances(self):
        r1 = RunnerFactory.create("local")
        r2 = RunnerFactory.create("local")
        assert r1 is not r2


# ═══════════════════════════════════════════
# 8. RunTestsTool refactored
# ═══════════════════════════════════════════


class TestRunTestsToolRefactored:
    def test_returns_json(self):
        tool = RunTestsTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.run(workspace_root=WORKSPACE, target="tests/test_health.py")
        )
        data = json.loads(result)
        assert "success" in data
        assert "passed" in data
        assert "failed" in data
        assert "duration_ms" in data

    def test_success_case(self):
        tool = RunTestsTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.run(workspace_root=WORKSPACE, target="tests/test_health.py")
        )
        data = json.loads(result)
        assert data["success"] is True
        assert data["passed"] >= 1

    def test_failure_case(self):
        ws = Path(WORKSPACE)
        test_file = ws / "test_fail_refactor.py"
        test_file.write_text(
            "def test_fail():\n    assert False\n",
            encoding="utf-8",
        )
        try:
            tool = RunTestsTool()
            result = asyncio.get_event_loop().run_until_complete(
                tool.run(workspace_root=WORKSPACE, target="test_fail_refactor.py")
            )
            data = json.loads(result)
            assert data["success"] is False
            assert data["failed"] >= 1
        finally:
            test_file.unlink(missing_ok=True)

    def test_explicit_mode(self):
        tool = RunTestsTool(mode="local")
        result = asyncio.get_event_loop().run_until_complete(
            tool.run(workspace_root=WORKSPACE, target="tests/test_health.py")
        )
        data = json.loads(result)
        assert data["success"] is True

    def test_nonexistent_workspace(self):
        tool = RunTestsTool()
        result = asyncio.get_event_loop().run_until_complete(
            tool.run(workspace_root="/nonexistent/path")
        )
        assert "错误" in result


# ═══════════════════════════════════════════
# 9. DockerRunner (auto-skip if no Docker)
# ═══════════════════════════════════════════


def _docker_available() -> bool:
    """检查本机是否有 Docker。"""
    import subprocess

    try:
        r = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


HAS_DOCKER = _docker_available()


@pytest.mark.skipif(not HAS_DOCKER, reason="本机无 Docker，跳过 DockerRunner 测试")
class TestDockerRunner:
    def test_import(self):
        from app.execution.docker_runner import DockerExecutionRunner

        assert issubclass(DockerExecutionRunner, BaseExecutionRunner)

    def test_create_via_factory(self):
        runner = RunnerFactory.create("docker")
        assert type(runner).__name__ == "DockerExecutionRunner"
