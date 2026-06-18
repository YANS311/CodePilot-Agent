"""EvaluationRunner — 逐个执行评测任务，每个任务使用独立 workspace。

流程：
1. 读取 evaluation/tasks.json
2. 对每个任务：
   a. 从 workspace_seed/ 复制到 workspace_eval/<task_id>/
   b. 创建 Agent，指向独立 workspace
   c. 执行 task prompt
   d. 用 LocalRunner 运行 pytest 验证
   e. 记录 EvalResult
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from app.evaluation.analyzer import analyze_error
from app.evaluation.schema import EvalResult, EvalTask
from app.execution.local_runner import LocalExecutionRunner

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class EvaluationRunner:
    """评测执行器 — 管理任务执行和 workspace 隔离。"""

    def __init__(
        self,
        tasks_file: str | Path | None = None,
        workspace_seed: str | Path | None = None,
        workspace_eval: str | Path | None = None,
    ) -> None:
        self._tasks_file = Path(tasks_file) if tasks_file else (
            _PROJECT_ROOT / "evaluation" / "tasks.json"
        )
        self._seed = Path(workspace_seed) if workspace_seed else (
            _PROJECT_ROOT / "workspace"
        )
        self._eval_dir = Path(workspace_eval) if workspace_eval else (
            _PROJECT_ROOT / "workspace_eval"
        )
        self._runner = LocalExecutionRunner()

    def load_tasks(self) -> list[EvalTask]:
        """从 tasks.json 加载评测任务列表。"""
        with open(self._tasks_file, encoding="utf-8") as f:
            data = json.load(f)
        return [EvalTask.from_dict(t) for t in data.get("tasks", [])]

    def _prepare_workspace(self, task_id: str) -> Path:
        """为单个任务准备独立 workspace：从 seed 复制到 eval 目录。"""
        task_ws = self._eval_dir / task_id
        # 清理旧的 workspace
        if task_ws.exists():
            shutil.rmtree(task_ws)
        # 复制 seed
        shutil.copytree(self._seed, task_ws)
        return task_ws

    def _cleanup_workspace(self, task_id: str) -> None:
        """清理任务的独立 workspace。"""
        task_ws = self._eval_dir / task_id
        if task_ws.exists():
            shutil.rmtree(task_ws)

    async def run_task(
        self,
        task: EvalTask,
        agent_factory,
    ) -> EvalResult:
        """执行单个评测任务。

        Args:
            task: 评测任务定义。
            agent_factory: 可调用对象，接受 workspace_root 参数返回 ReActAgent。
        """
        task_ws = self._prepare_workspace(task.id)
        t0 = time.monotonic()

        try:
            # 创建指向独立 workspace 的 Agent
            agent = agent_factory(str(task_ws))

            # 执行 Agent
            agent_result = await agent.run(task.task)
            duration = int((time.monotonic() - t0) * 1000)

            # 用 Runner 验证：只运行任务相关的测试
            test_result = await self._runner.run_pytest(
                str(task_ws), target=task.test_target or None
            )

            eval_result = EvalResult(
                task_id=task.id,
                success=agent_result.tool_calls_count > 0 and test_result.success,
                final_answer=agent_result.answer,
                tool_calls_count=agent_result.tool_calls_count,
                duration_ms=duration,
                test_success=test_result.success,
                passed=test_result.passed,
                failed=test_result.failed,
            )
            # 错误归因
            if not eval_result.success:
                analyze_error(eval_result)
            return eval_result

        except Exception as exc:
            duration = int((time.monotonic() - t0) * 1000)
            logger.exception("Task %s failed", task.id)
            return EvalResult(
                task_id=task.id,
                success=False,
                duration_ms=duration,
                error=str(exc),
            )
        finally:
            self._cleanup_workspace(task.id)

    async def run_all(
        self,
        agent_factory,
        task_ids: list[str] | None = None,
    ) -> list[EvalResult]:
        """执行所有（或指定的）评测任务。

        Args:
            agent_factory: 可调用对象，接受 workspace_root 参数返回 ReActAgent。
            task_ids: 可选的任务 ID 列表。为 None 时执行全部。
        """
        tasks = self.load_tasks()
        if task_ids:
            tasks = [t for t in tasks if t.id in task_ids]

        results = []
        for task in tasks:
            logger.info("Running task: %s (%s)", task.id, task.name)
            result = await self.run_task(task, agent_factory)
            results.append(result)
            logger.info(
                "  → success=%s, tests=%s, tools=%d, %dms",
                result.success, result.test_success,
                result.tool_calls_count, result.duration_ms,
            )

        return results
