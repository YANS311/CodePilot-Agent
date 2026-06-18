"""ExecutionRunner 抽象基类 — 定义执行环境的统一接口。

Tool 负责业务逻辑，Runner 负责执行环境。
未来可扩展 Docker、Podman 甚至远程执行器。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """执行结果 — 统一的数据结构。"""

    success: bool = False
    return_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    # pytest 专用字段
    passed: int = 0
    failed: int = 0
    error: str = ""


class BaseExecutionRunner(ABC):
    """执行环境抽象基类 — 体现封装。

    定义所有 Runner 的公共接口。
    子类只需实现 run_pytest() 的具体执行逻辑，
    Tool 通过统一接口调用，实现多态。
    """

    @abstractmethod
    async def run_pytest(
        self,
        workspace_path: str,
        target: str | None = None,
    ) -> ExecutionResult:
        """在指定 workspace 中执行 pytest。

        Args:
            workspace_path: workspace 绝对路径。
            target: 可选的测试目标文件。留空则运行所有测试。

        Returns:
            ExecutionResult 包含执行结果、输出和耗时。
        """
        ...
