"""RunnerFactory — 根据配置选择执行环境。

体现工厂模式：调用方无需知道具体 Runner 类型，
只需通过 Factory 获取合适的 Runner 实例。
"""

from __future__ import annotations

from app.execution.base import BaseExecutionRunner

# 注册表：mode → Runner 类
_RUNNERS: dict[str, type[BaseExecutionRunner]] = {}


def _register_runners() -> None:
    """延迟注册，避免循环导入。"""
    if _RUNNERS:
        return
    from app.execution.local_runner import LocalExecutionRunner

    _RUNNERS["local"] = LocalExecutionRunner

    # Docker Runner 延迟注册（可能不可用）
    try:
        from app.execution.docker_runner import DockerExecutionRunner

        _RUNNERS["docker"] = DockerExecutionRunner
    except ImportError:
        pass


class RunnerFactory:
    """执行环境工厂 — 根据 EXECUTION_MODE 选择 Runner。

    体现工厂模式：隐藏具体实例化逻辑，
    调用方只需 `RunnerFactory.create()` 即可获得合适的 Runner。
    """

    @staticmethod
    def create(mode: str = "local") -> BaseExecutionRunner:
        """根据 mode 创建对应的 ExecutionRunner。

        Args:
            mode: 执行模式，支持 "local" 和 "docker"。

        Returns:
            对应的 ExecutionRunner 实例。

        Raises:
            ValueError: 未知的执行模式。
        """
        _register_runners()

        runner_cls = _RUNNERS.get(mode)
        if runner_cls is None:
            available = ", ".join(_RUNNERS.keys()) or "无"
            raise ValueError(
                f"未知的执行模式: {mode}。可用模式: {available}"
            )

        return runner_cls()

    @staticmethod
    def available_modes() -> list[str]:
        """返回所有可用的执行模式。"""
        _register_runners()
        return list(_RUNNERS.keys())
