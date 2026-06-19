#!/usr/bin/env python3
"""run_eval.py — 运行 CodePilot Agent 评测。

用法:
    python scripts/run_eval.py                    # 运行全部任务
    python scripts/run_eval.py --tasks fix-subtract fix-divide-zero  # 运行指定任务
    python scripts/run_eval.py --output reports/eval_report.json     # 指定输出路径
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.agent.react_agent import ReActAgent
from app.core.config import settings
from app.core.llm_client import LLMClient
from app.evaluation.metrics import compute_metrics
from app.evaluation.runner import EvaluationRunner
from app.evaluation.schema import EvalResult
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


def _print_result(result: EvalResult, index: int) -> None:
    status = "PASS" if result.success else "FAIL"
    test_status = "PASS" if result.test_success else "FAIL"
    print(
        f"  [{index}] {result.task_id}: "
        f"{status} (test={test_status}, "
        f"tools={result.tool_calls_count}, "
        f"{result.duration_ms}ms)"
    )
    if result.error:
        print(f"       error: {result.error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="CodePilot Agent 评测")
    parser.add_argument(
        "--tasks", nargs="*", default=None,
        help="指定要运行的任务 ID（留空运行全部）",
    )
    parser.add_argument(
        "--output", default=str(_PROJECT_ROOT / "reports" / "eval_report.json"),
        help="输出报告路径",
    )
    args = parser.parse_args()

    runner = EvaluationRunner()

    print("=" * 60)
    print("CodePilot Agent Evaluation")
    print("=" * 60)

    # 加载任务
    tasks = runner.load_tasks()
    print(f"\nLoaded {len(tasks)} tasks")

    # 运行
    t0 = time.monotonic()
    results = asyncio.get_event_loop().run_until_complete(
        runner.run_all(_agent_factory, task_ids=args.tasks)
    )
    total_duration = int((time.monotonic() - t0) * 1000)

    # 打印每个任务结果
    print("\n--- Results ---")
    for i, r in enumerate(results, 1):
        _print_result(r, i)

    # 计算指标
    metrics = compute_metrics(results, tasks)

    # 打印汇总
    print("\n--- Metrics ---")
    print(f"  Task Success Rate: {metrics.task_success_rate:.1%} "
          f"({metrics.successful_tasks}/{metrics.total_tasks})")
    print(f"  Test Pass Rate:    {metrics.test_pass_rate:.1%} "
          f"({metrics.total_tests_passed}/{metrics.total_tests_passed + metrics.total_tests_failed})")
    print(f"  Pass@1:            {metrics.pass_at_1:.1%}")
    print(f"  Tool Efficiency:   {metrics.tool_efficiency:.3f}")
    print(f"  Tool Calls/Success:{metrics.tool_calls_per_success:.1f}")
    print(f"  Avg Tool Calls:    {metrics.avg_tool_calls:.1f}")
    print(f"  Avg Duration:      {metrics.avg_duration_ms:.0f}ms")
    print(f"  Total Duration:    {total_duration}ms")

    if metrics.error_distribution:
        print("\n  Error Distribution:")
        for error_type, count in sorted(metrics.error_distribution.items(), key=lambda x: -x[1]):
            print(f"    {error_type}: {count}")

    if metrics.success_by_difficulty:
        print("\n  By Difficulty:")
        for diff, stats in metrics.success_by_difficulty.items():
            print(f"    {diff}: {stats['rate']:.0%} ({stats['success']}/{stats['total']})")

    if metrics.success_by_category:
        print("\n  By Category:")
        for cat, stats in metrics.success_by_category.items():
            print(f"    {cat}: {stats['rate']:.0%} ({stats['success']}/{stats['total']})")

    # 保存 JSON 报告
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "version": "2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tasks": [r.to_dict() for r in results],
        "metrics": metrics.to_dict(),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 生成 Markdown 报告
    md_path = output_path.with_suffix(".md")
    _generate_markdown_report(md_path, metrics, results, tasks, total_duration)

    print(f"\nJSON Report saved to: {output_path}")
    print(f"Markdown Report saved to: {md_path}")
    print("=" * 60)


def _generate_markdown_report(
    path: Path,
    metrics: 'EvalMetrics',
    results: list[EvalResult],
    tasks: list[EvalTask],
    total_duration: int,
) -> None:
    """生成 Markdown 格式的评测报告。"""
    task_map = {t.id: t for t in tasks}

    lines = [
        "# CodePilot Agent 评测报告",
        "",
        f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 核心指标",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 任务成功率 (TSR) | {metrics.task_success_rate:.1%} ({metrics.successful_tasks}/{metrics.total_tasks}) |",
        f"| Pass@1 | {metrics.pass_at_1:.1%} |",
        f"| 测试通过率 | {metrics.test_pass_rate:.1%} ({metrics.total_tests_passed}/{metrics.total_tests_passed + metrics.total_tests_failed}) |",
        f"| 工具效率 | {metrics.tool_efficiency:.3f} |",
        f"| 成功任务平均工具调用 | {metrics.tool_calls_per_success:.1f} |",
        f"| 平均工具调用 | {metrics.avg_tool_calls:.1f} |",
        f"| 平均耗时 | {metrics.avg_duration_ms:.0f}ms |",
        f"| 总耗时 | {total_duration}ms |",
        "",
    ]

    # 错误分布
    if metrics.error_distribution:
        lines.extend([
            "## 错误分布",
            "",
            "| 错误类型 | 数量 |",
            "|----------|------|",
        ])
        for error_type, count in sorted(metrics.error_distribution.items(), key=lambda x: -x[1]):
            lines.append(f"| {error_type} | {count} |")
        lines.append("")

    # 按难度分组
    if metrics.success_by_difficulty:
        lines.extend([
            "## 按难度分组",
            "",
            "| 难度 | 成功/总数 | 成功率 |",
            "|------|-----------|--------|",
        ])
        for diff, stats in metrics.success_by_difficulty.items():
            lines.append(f"| {diff} | {stats['success']}/{stats['total']} | {stats['rate']:.0%} |")
        lines.append("")

    # 按类别分组
    if metrics.success_by_category:
        lines.extend([
            "## 按类别分组",
            "",
            "| 类别 | 成功/总数 | 成功率 |",
            "|------|-----------|--------|",
        ])
        for cat, stats in metrics.success_by_category.items():
            lines.append(f"| {cat} | {stats['success']}/{stats['total']} | {stats['rate']:.0%} |")
        lines.append("")

    # 失败任务详情
    failed_results = [r for r in results if not r.success]
    if failed_results:
        lines.extend([
            "## 失败任务详情",
            "",
        ])
        for r in failed_results:
            task = task_map.get(r.task_id)
            task_name = task.name if task else r.task_id
            lines.extend([
                f"### {r.task_id}: {task_name}",
                "",
                f"- **难度**: {task.difficulty if task else 'unknown'}",
                f"- **错误类型**: {r.error_type or 'N/A'}",
                f"- **错误原因**: {r.error_reason or 'N/A'}",
                f"- **工具调用**: {r.tool_calls_count}",
                "",
            ])

    # 成功任务列表
    succeeded_results = [r for r in results if r.success]
    if succeeded_results:
        lines.extend([
            "## 成功任务",
            "",
            "| 任务 ID | 任务名称 | 工具调用 | 耗时 |",
            "|---------|----------|----------|------|",
        ])
        for r in succeeded_results:
            task = task_map.get(r.task_id)
            task_name = task.name if task else r.task_id
            lines.append(f"| {r.task_id} | {task_name} | {r.tool_calls_count} | {r.duration_ms}ms |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
