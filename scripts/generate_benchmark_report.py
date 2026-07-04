#!/usr/bin/env python3
"""generate_benchmark_report.py — Generate multi-baseline benchmark reports.

Three modes:
  1. --from-json: Read single JSON, generate Markdown (no eval run)
  2. --baseline-files: Merge multiple JSON reports into comparison
  3. --baselines: Run eval for each baseline, then generate report

Usage:
  # Mode 1: from single JSON
  python scripts/generate_benchmark_report.py \\
    --from-json reports/eval_report.json \\
    --output-md docs/benchmark_report.md

  # Mode 2: merge multiple baseline JSONs
  python scripts/generate_benchmark_report.py \\
    --baseline-files reports/react_full.json reports/bare_llm.json \\
    --output-md docs/benchmark_report.md \\
    --output-json reports/benchmark_report.json

  # Mode 3: run eval then report
  python scripts/generate_benchmark_report.py \\
    --baselines react_full,bare_llm \\
    --layer all \\
    --output-md docs/benchmark_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.evaluation.reporting import (
    BaselineReport,
    BenchmarkReport,
    extract_baseline_report,
    load_report_json,
    merge_baseline_reports,
    render_markdown_report,
    render_single_report,
    write_report,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CodePilot Agent Benchmark Report Generator"
    )

    # Mode 1: from single JSON
    parser.add_argument(
        "--from-json",
        default=None,
        help="Path to a single eval report JSON (read-only, no eval run)",
    )

    # Mode 2: multiple baseline JSON files
    parser.add_argument(
        "--baseline-files",
        nargs="+",
        default=None,
        help="Paths to multiple baseline report JSON files",
    )

    # Mode 3: run eval for each baseline
    parser.add_argument(
        "--baselines",
        default=None,
        help="Comma-separated baseline modes to run (e.g. react_full,bare_llm)",
    )

    parser.add_argument(
        "--layer",
        default="all",
        choices=["all", "unit", "integration", "stress"],
        help="Layer filter for eval run mode (default: all)",
    )

    parser.add_argument(
        "--output-md",
        default=None,
        help="Output Markdown file path",
    )

    parser.add_argument(
        "--output-json",
        default=None,
        help="Output JSON file path",
    )

    parser.add_argument(
        "--ci-disclaimer",
        action="store_true",
        help="Force CI/mock disclaimer in Markdown output",
    )

    args = parser.parse_args(argv)

    # Validate mutual exclusivity
    modes = [
        args.from_json is not None,
        args.baseline_files is not None,
        args.baselines is not None,
    ]
    if sum(modes) == 0:
        parser.error("Specify one of: --from-json, --baseline-files, --baselines")
    if sum(modes) > 1:
        parser.error("--from-json, --baseline-files, and --baselines are mutually exclusive")

    return args


def _run_from_json(args: argparse.Namespace) -> BenchmarkReport:
    """Mode 1: Load single JSON, extract BaselineReport, wrap in BenchmarkReport."""
    data = load_report_json(args.from_json)
    br = extract_baseline_report(data, source_path=args.from_json)
    if args.ci_disclaimer:
        br.ci_mode = True
    return BenchmarkReport(
        reports=[br],
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _run_baseline_files(args: argparse.Namespace) -> BenchmarkReport:
    """Mode 2: Load multiple JSON files, merge into comparison."""
    reports = []
    for path in args.baseline_files:
        data = load_report_json(path)
        br = extract_baseline_report(data, source_path=path)
        if args.ci_disclaimer:
            br.ci_mode = True
        reports.append(br)
    return merge_baseline_reports(reports)


def _run_eval_baselines(args: argparse.Namespace) -> BenchmarkReport:
    """Mode 3: Run eval for each baseline, collect results.

    This mode requires real LLM API (or CI mock). If the runner
    is not available or fails, the baseline is marked as failed.
    """
    from app.evaluation.metrics import compute_metrics
    from app.evaluation.runner import EvaluationRunner
    from app.evaluation.schema import BaselineMode, EvalLayer

    baseline_names = [b.strip() for b in args.baselines.split(",")]
    layer = EvalLayer(args.layer) if args.layer != "all" else None
    runner = EvaluationRunner()
    tasks = runner.load_tasks()

    reports = []
    for name in baseline_names:
        try:
            baseline = BaselineMode(name)
        except ValueError:
            print(f"Warning: unknown baseline '{name}', skipping", file=sys.stderr)
            continue

        print(f"Running baseline: {name} (layer={args.layer})...")
        try:
            results = asyncio.get_event_loop().run_until_complete(
                runner.run_all(
                    _agent_factory,
                    layer=layer,
                    baseline=baseline,
                )
            )
            filtered_tasks = tasks
            if layer:
                filtered_tasks = [t for t in tasks if t.layer == layer]
            metrics = compute_metrics(results, filtered_tasks)

            br = BaselineReport(
                baseline=name,
                layer=args.layer,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                metrics=metrics.to_dict(),
                task_count=len(results),
                ci_mode=args.ci_disclaimer,
            )
        except Exception as exc:
            print(f"Warning: baseline '{name}' failed: {exc}", file=sys.stderr)
            br = BaselineReport(
                baseline=name,
                layer=args.layer,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                metrics={},
                task_count=0,
                ci_mode=args.ci_disclaimer,
            )
        reports.append(br)

    return BenchmarkReport(
        reports=reports,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _agent_factory(
    workspace_root: str,
    max_tool_calls: int | None = None,
    baseline=None,
):
    """Create an agent for eval run mode. Reuses run_eval.py logic."""
    from app.agent.react_agent import ReActAgent
    from app.core.config import settings
    from app.core.llm_client import LLMClient
    from app.evaluation.schema import BaselineMode
    from app.tools.code_edit import CodeEditTool
    from app.tools.git_diff import GitDiffTool
    from app.tools.git_status import GitStatusTool
    from app.tools.read_file import ReadFileTool
    from app.tools.registry import ToolRegistry
    from app.tools.run_tests import RunTestsTool
    from app.tools.search_code import SearchCodeTool
    from app.tools.write_file import WriteFileTool

    llm = LLMClient(settings)
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(SearchCodeTool())
    registry.register(WriteFileTool())
    registry.register(CodeEditTool())
    registry.register(GitDiffTool())
    registry.register(GitStatusTool())
    registry.register(RunTestsTool())

    agent = ReActAgent(
        llm=llm,
        registry=registry,
        workspace_root=workspace_root,
        max_tool_calls=max_tool_calls or settings.max_tool_calls,
    )
    if baseline == BaselineMode.REACT_NO_MEMORY:
        agent._build_memory_context = lambda task: ""
    return agent


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # Route to the correct mode
    if args.from_json:
        report = _run_from_json(args)
    elif args.baseline_files:
        report = _run_baseline_files(args)
    elif args.baselines:
        report = _run_eval_baselines(args)
    else:
        print("Error: no mode specified", file=sys.stderr)
        sys.exit(1)

    # Write output
    if args.output_md or args.output_json:
        write_report(report, output_json=args.output_json, output_md=args.output_md)
        if args.output_md:
            print(f"Markdown report: {args.output_md}")
        if args.output_json:
            print(f"JSON report: {args.output_json}")
    else:
        # No output file specified — print Markdown to stdout
        print(render_markdown_report(report))


if __name__ == "__main__":
    main()
