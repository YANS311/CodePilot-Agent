#!/usr/bin/env python3
"""run_stress_eval.py — CodePilot Agent 压力测试评测。

用法:
    python scripts/run_stress_eval.py                    # 运行全部压力测试任务
    python scripts/run_stress_eval.py --tasks stress-multifile-01  # 运行指定任务
    python scripts/run_stress_eval.py --output reports/stress_report.json  # 指定输出路径
    python scripts/run_stress_eval.py --include-normal   # 同时运行正常评测任务
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
from app.evaluation.advanced_metrics import AdvancedMetrics, compute_advanced_metrics
from app.evaluation.runner import EvaluationRunner
from app.evaluation.schema import EvalResult, EvalTask
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.run_tests import RunTestsTool
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool


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


def _load_stress_tasks(tasks_file: Path | None = None) -> list[EvalTask]:
    """加载压力测试任务。"""
    path = tasks_file or (_PROJECT_ROOT / "evaluation" / "stress_tasks.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [EvalTask.from_dict(t) for t in data.get("tasks", [])]


def _print_result(result: EvalResult, index: int, task_name: str = "") -> None:
    status = "PASS" if result.success else "FAIL"
    test_status = "PASS" if result.test_success else "FAIL"
    retry标记 = " [RETRY]" if result.is_retry_result else ""
    name_display = f" ({task_name})" if task_name else ""
    print(
        f"  [{index}] {result.task_id}{name_display}: "
        f"{status}{retry标记} (test={test_status}, "
        f"tools={result.tool_calls_count}, "
        f"{result.duration_ms}ms)"
    )
    if result.error:
        print(f"       error: {result.error}")


def _compute_stress_metrics(
    stress_results: list[EvalResult],
    stress_tasks: list[EvalTask],
    normal_results: list[EvalResult] | None = None,
    normal_tasks: list[EvalTask] | None = None,
) -> dict:
    """计算综合指标（正常 + 压力）。"""
    # 压力任务指标
    stress_metrics = compute_advanced_metrics(stress_results, stress_tasks)

    # 正常任务指标（如果有）
    normal_metrics = None
    if normal_results and normal_tasks:
        normal_metrics = compute_advanced_metrics(normal_results, normal_tasks)

    # 综合指标
    all_results = (normal_results or []) + stress_results
    all_tasks = (normal_tasks or []) + stress_tasks
    combined_metrics = compute_advanced_metrics(all_results, all_tasks)

    # Failure breakdown by category
    failure_breakdown = {}
    for r in stress_results:
        if not r.success:
            task = next((t for t in stress_tasks if t.id == r.task_id), None)
            category = task.category if task else "unknown"
            failure_breakdown[category] = failure_breakdown.get(category, 0) + 1

    return {
        "normal_tsr": round(normal_metrics.task_success_rate, 4) if normal_metrics else None,
        "normal_tasks": normal_metrics.total_tasks if normal_metrics else 0,
        "normal_successful": normal_metrics.successful_tasks if normal_metrics else 0,
        "stress_tsr": round(stress_metrics.task_success_rate, 4),
        "stress_tasks": stress_metrics.total_tasks,
        "stress_successful": stress_metrics.successful_tasks,
        "combined_tsr": round(combined_metrics.task_success_rate, 4),
        "combined_tasks": combined_metrics.total_tasks,
        "combined_successful": combined_metrics.successful_tasks,
        "recovery_rate": round(stress_metrics.recovery_rate, 4),
        "multi_file_success_rate": round(stress_metrics.multi_file_success_rate, 4),
        "first_pass_rate": round(stress_metrics.first_pass_rate, 4),
        "retry_success_rate": round(stress_metrics.retry_success_rate, 4),
        "tool_efficiency_under_stress": round(stress_metrics.tool_efficiency_under_stress, 4),
        "failure_breakdown": failure_breakdown,
        "stress_metrics": stress_metrics.to_dict(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="CodePilot Agent 压力测试")
    parser.add_argument(
        "--tasks", nargs="*", default=None,
        help="指定要运行的压力测试任务 ID",
    )
    parser.add_argument(
        "--output", default=str(_PROJECT_ROOT / "reports" / "stress_report.json"),
        help="输出报告路径",
    )
    parser.add_argument(
        "--include-normal", action="store_true",
        help="同时运行正常评测任务",
    )
    parser.add_argument(
        "--stress-tasks-file", default=None,
        help="压力测试任务文件路径",
    )
    args = parser.parse_args()

    runner = EvaluationRunner()

    print("=" * 60)
    print("CodePilot Agent Stress Test")
    print("=" * 60)

    # 加载压力测试任务
    stress_tasks = _load_stress_tasks(
        Path(args.stress_tasks_file) if args.stress_tasks_file else None
    )
    print(f"\nLoaded {len(stress_tasks)} stress tasks")

    if args.tasks:
        stress_tasks = [t for t in stress_tasks if t.id in args.tasks]
        print(f"Filtered to {len(stress_tasks)} tasks")

    # 运行压力测试
    t0 = time.monotonic()
    stress_results = asyncio.run(
        runner.run_all(_agent_factory, task_ids=[t.id for t in stress_tasks])
    )
    stress_duration = int((time.monotonic() - t0) * 1000)

    # 运行正常评测（可选）
    normal_results = None
    normal_tasks = None
    normal_duration = 0
    if args.include_normal:
        print("\n--- Running Normal Evaluation ---")
        normal_tasks = runner.load_tasks()
        print(f"Loaded {len(normal_tasks)} normal tasks")
        t1 = time.monotonic()
        normal_results = asyncio.run(
            runner.run_all(_agent_factory)
        )
        normal_duration = int((time.monotonic() - t1) * 1000)

    # 打印压力测试结果
    print("\n--- Stress Test Results ---")
    task_name_map = {t.id: t.name for t in stress_tasks}
    for i, r in enumerate(stress_results, 1):
        _print_result(r, i, task_name_map.get(r.task_id, ""))

    # 计算综合指标
    metrics = _compute_stress_metrics(
        stress_results, stress_tasks, normal_results, normal_tasks
    )

    # 打印汇总
    print("\n--- Summary ---")
    if metrics["normal_tsr"] is not None:
        print(f"  Normal TSR:     {metrics['normal_tsr']:.1%} "
              f"({metrics['normal_successful']}/{metrics['normal_tasks']})")
    print(f"  Stress TSR:     {metrics['stress_tsr']:.1%} "
          f"({metrics['stress_successful']}/{metrics['stress_tasks']})")
    print(f"  Combined TSR:   {metrics['combined_tsr']:.1%} "
          f"({metrics['combined_successful']}/{metrics['combined_tasks']})")
    print(f"  Recovery Rate:  {metrics['recovery_rate']:.1%}")
    print(f"  Multi-file:     {metrics['multi_file_success_rate']:.1%}")
    print(f"  First-pass:     {metrics['first_pass_rate']:.1%}")
    print(f"  Tool Efficiency: {metrics['tool_efficiency_under_stress']:.2f}")
    print(f"  Stress Duration: {stress_duration}ms")

    if metrics["failure_breakdown"]:
        print("\n--- Failure Breakdown ---")
        for category, count in sorted(metrics["failure_breakdown"].items(), key=lambda x: -x[1]):
            print(f"  {category}: {count}")

    # 保存 JSON 报告
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "version": "1.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stress_tasks_count": len(stress_tasks),
        "stress_results": [r.to_dict() for r in stress_results],
        "metrics": metrics,
    }
    if normal_results:
        report["normal_tasks_count"] = len(normal_tasks) if normal_tasks else 0
        report["normal_results"] = [r.to_dict() for r in normal_results]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 生成 Markdown 报告
    md_path = output_path.with_suffix(".md")
    _generate_stress_report(md_path, metrics, stress_results, stress_tasks, stress_duration)

    print(f"\nJSON Report: {output_path}")
    print(f"Markdown Report: {md_path}")
    print("=" * 60)


def _generate_stress_report(
    path: Path,
    metrics: dict,
    results: list[EvalResult],
    tasks: list[EvalTask],
    duration: int,
) -> None:
    """生成压力测试 Markdown 报告。"""
    task_map = {t.id: t for t in tasks}

    lines = [
        "# CodePilot Agent Stress Test Report",
        "",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
    ]

    if metrics["normal_tsr"] is not None:
        lines.append(f"| Normal TSR | {metrics['normal_tsr']:.1%} ({metrics['normal_successful']}/{metrics['normal_tasks']}) |")
    lines.extend([
        f"| Stress TSR | {metrics['stress_tsr']:.1%} ({metrics['stress_successful']}/{metrics['stress_tasks']}) |",
        f"| Combined TSR | {metrics['combined_tsr']:.1%} ({metrics['combined_successful']}/{metrics['combined_tasks']}) |",
        f"| Recovery Rate | {metrics['recovery_rate']:.1%} |",
        f"| Multi-file Success Rate | {metrics['multi_file_success_rate']:.1%} |",
        f"| First-pass Rate | {metrics['first_pass_rate']:.1%} |",
        f"| Tool Efficiency (Stress) | {metrics['tool_efficiency_under_stress']:.2f} |",
        f"| Duration | {duration}ms |",
        "",
    ])

    # Failure breakdown
    if metrics["failure_breakdown"]:
        lines.extend([
            "## Failure Breakdown",
            "",
            "| Category | Count |",
            "|----------|-------|",
        ])
        for category, count in sorted(metrics["failure_breakdown"].items(), key=lambda x: -x[1]):
            lines.append(f"| {category} | {count} |")
        lines.append("")

    # Task details
    lines.extend([
        "## Task Details",
        "",
        "| Task ID | Name | Difficulty | Category | Status | Tests | Tools | Duration |",
        "|---------|------|------------|----------|--------|-------|-------|----------|",
    ])
    for r in results:
        task = task_map.get(r.task_id)
        status = "PASS" if r.success else "FAIL"
        test_str = f"{r.passed}/{r.passed + r.failed}" if r.passed + r.failed > 0 else "N/A"
        retry标记 = " [R]" if r.is_retry_result else ""
        lines.append(
            f"| {r.task_id}{retry标记} | {task.name if task else ''} | "
            f"{task.difficulty if task else 'N/A'} | {task.category if task else 'N/A'} | "
            f"{status} | {test_str} | {r.tool_calls_count} | {r.duration_ms}ms |"
        )
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
