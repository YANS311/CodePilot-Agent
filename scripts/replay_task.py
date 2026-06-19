#!/usr/bin/env python3
"""replay_task.py — 单独重放评测任务并保存完整执行轨迹。

用法:
    python scripts/replay_task.py fix-append-line
    python scripts/replay_task.py fix-retry-request fix-file-processor-all
    python scripts/replay_task.py --all-failed
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.config import settings
from app.core.llm_client import LLMClient
from app.evaluation.analyzer import analyze_error
from app.evaluation.runner import EvaluationRunner
from app.evaluation.schema import EvalResult, EvalTask
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.run_tests import RunTestsTool
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool

REPLAY_DIR = _PROJECT_ROOT / "reports" / "replays"


def _build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(WriteFileTool())
    registry.register(GitDiffTool())
    registry.register(GitStatusTool())
    registry.register(RunTestsTool())
    return registry


def _agent_factory(workspace_root: str, max_tool_calls: int | None = None) -> ReActAgent:
    llm = LLMClient(settings)
    registry = _build_registry()
    return ReActAgent(
        llm=llm,
        registry=registry,
        workspace_root=workspace_root,
        max_tool_calls=max_tool_calls or settings.max_tool_calls,
    )


def _save_replay(task_id: str, result: EvalResult, agent_result, task: EvalTask) -> Path:
    """保存完整执行轨迹到 JSON。"""
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    # 构建步骤轨迹
    steps = []
    for step in agent_result.steps:
        steps.append({
            "step_id": step.step_id,
            "thought": step.thought,
            "action": step.action,
            "tool_name": step.tool_name,
            "tool_args": step.tool_args,
            "observation": step.observation[:2000],  # 截断过长输出
            "success": step.success,
        })

    replay = {
        "task_id": task_id,
        "task_name": task.name,
        "difficulty": task.difficulty,
        "category": task.category,
        "task_prompt": task.task,
        "file": task.file,
        "test_target": task.test_target,
        "expected_behavior": task.expected_behavior,
        "success_criteria": task.success_criteria,
        "reference_fix": task.reference_fix,
        "result": {
            "success": result.success,
            "test_success": result.test_success,
            "passed": result.passed,
            "failed": result.failed,
            "tool_calls_count": result.tool_calls_count,
            "duration_ms": result.duration_ms,
            "error_type": result.error_type,
            "error_reason": result.error_reason,
        },
        "thoughts": agent_result.thoughts,
        "final_answer": agent_result.answer,
        "steps": steps,
        "messages_count": len(agent_result.messages),
    }

    out_path = REPLAY_DIR / f"{task_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(replay, f, ensure_ascii=False, indent=2)

    return out_path


def _save_trace_md(task_id: str, result: EvalResult, agent_result, task: EvalTask) -> Path:
    """保存 Thought-Action-Observation 链路为 Markdown。"""
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Trace: {task_id}",
        "",
        f"**Task**: {task.name}",
        f"**Difficulty**: {task.difficulty}",
        f"**Result**: {'PASS' if result.success else 'FAIL'}",
        f"**Tool Calls**: {result.tool_calls_count}",
        f"**Duration**: {result.duration_ms}ms",
        "",
    ]

    if result.error_type:
        lines.extend([
            f"**Error Type**: {result.error_type}",
            f"**Error Reason**: {result.error_reason}",
            "",
        ])

    lines.extend([
        "## Task Prompt",
        "",
        f"> {task.task}",
        "",
        "## Execution Trace",
        "",
    ])

    for step in agent_result.steps:
        status = "+" if step.success else "-"
        lines.extend([
            f"### Step {step.step_id} [{status}]",
            "",
            f"**Thought**: {step.thought[:500] or '(none)'}",
            "",
            f"**Action**: `{step.action}`",
            "",
            f"**Observation**:",
            "```",
            step.observation[:1000] or "(empty)",
            "```",
            "",
        ])

    lines.extend([
        "## Final Answer",
        "",
        agent_result.answer[:2000] or "(empty)",
        "",
    ])

    out_path = REPLAY_DIR / f"{task_id}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return out_path


async def replay_task(task_id: str) -> EvalResult:
    """重放单个任务，保存轨迹，返回结果。"""
    runner = EvaluationRunner()
    tasks = runner.load_tasks()
    task = next((t for t in tasks if t.id == task_id), None)
    if not task:
        print(f"Task not found: {task_id}")
        sys.exit(1)

    print(f"Replaying: {task_id} ({task.name})")

    # 准备 workspace
    task_ws = runner._prepare_workspace(task.id)
    t0 = time.monotonic()

    try:
        # 根据难度设置工具调用预算
        from app.evaluation.runner import DIFFICULTY_BUDGET
        max_calls = DIFFICULTY_BUDGET.get(task.difficulty, 20)
        agent = _agent_factory(str(task_ws), max_calls)
        agent_result = await agent.run(task.task)
        duration = int((time.monotonic() - t0) * 1000)

        # 运行测试
        test_result = await runner._runner.run_pytest(
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
        if not eval_result.success:
            analyze_error(eval_result)

        # 保存轨迹
        json_path = _save_replay(task_id, eval_result, agent_result, task)
        md_path = _save_trace_md(task_id, eval_result, agent_result, task)

        status = "PASS" if eval_result.success else "FAIL"
        print(f"  Result: {status} (tools={eval_result.tool_calls_count}, {duration}ms)")
        if eval_result.error_type:
            print(f"  Error:  {eval_result.error_type} — {eval_result.error_reason}")
        print(f"  JSON:   {json_path}")
        print(f"  Trace:  {md_path}")

        return eval_result

    finally:
        runner._cleanup_workspace(task.id)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Replay evaluation tasks")
    parser.add_argument("tasks", nargs="*", help="Task IDs to replay")
    parser.add_argument("--all-failed", action="store_true", help="Replay all failed tasks from last eval")
    args = parser.parse_args()

    task_ids = args.tasks

    if args.all_failed:
        # 从上一次 eval 报告中读取失败任务
        report_path = _PROJECT_ROOT / "reports" / "eval_report.json"
        if not report_path.exists():
            print("No eval report found. Run eval first.")
            sys.exit(1)
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
        task_ids = [t["task_id"] for t in report["tasks"] if not t["success"]]
        print(f"Found {len(task_ids)} failed tasks: {task_ids}")

    if not task_ids:
        print("No tasks specified. Use: replay_task.py <task_id> [...] or --all-failed")
        sys.exit(1)

    results = []
    for tid in task_ids:
        result = await replay_task(tid)
        results.append(result)
        print()

    # 汇总
    passed = sum(1 for r in results if r.success)
    print(f"=== Summary: {passed}/{len(results)} passed ===")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
