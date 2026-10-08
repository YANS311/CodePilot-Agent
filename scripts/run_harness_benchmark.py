"""Offline by default; live model calls require a separate explicit cost gate."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.context_stress import run_context_stress
from app.evaluation.harness_reporting import write_reports
from app.evaluation.harness_runner import HarnessConfig, provenance, run_ablations
from app.evaluation.manifest import audit_datasets, load_manifest
from app.evaluation.profiles import PROFILES
from app.evaluation.recovery_matrix import run_recovery_matrix


def dry_run_plan(entries, config, settings):
    count = len(entries) * len(PROFILES) * config.repetitions
    logical_ceiling = count * (config.max_tool_calls + 1) * 2
    return {"status": "DRY RUN", "model": settings.llm_model, "configured_api_key": bool(settings.llm_api_key),
            "provider_category": "configured OpenAI-compatible endpoint", "task_count": len(entries),
            "profiles": [p.id for p in PROFILES], "repetitions": config.repetitions, "trials": count,
            "logical_llm_request_upper_estimate": logical_ceiling,
            "http_attempt_upper_estimate": logical_ceiling * max(1, settings.llm_max_retries),
            "estimated_cost": None, "cost_uncertainty": "Price/usage unavailable; ceilings are not expected billable volume. No calls made.",
            "approval_required": "--live --approve-paid; requires non-CI provider configuration"}


async def execute(args):
    from app.core.config import settings
    from app.core.llm_client import LLMClient
    config = HarnessConfig(args.repetitions, args.order_seed, args.max_tool_calls, args.timeout, args.memory_state)
    manifest = audit_datasets(collect=args.audit_collect)
    manifest_path = ROOT / "benchmarks/manifest.json"
    if args.audit_collect:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    entries = []
    if args.live or args.dry_run:
        if not args.tasks:
            raise ValueError("Choose explicit --tasks before planning or running live trials")
        candidates = {entry.task_id: entry for entry in load_manifest(manifest_path)}
        for task_id in args.tasks:
            if task_id not in candidates or not candidates[task_id].test_target or not candidates[task_id].target_exists:
                raise ValueError(f"Task has no audited executable criterion: {task_id}")
            entries.append(candidates[task_id])
        plan = dry_run_plan(entries, config, settings)
        print(json.dumps(plan, indent=2))
        if args.dry_run:
            return
        if not args.approve_paid:
            raise ValueError("Live benchmarking refused: inspect --dry-run then explicitly approve paid execution")
        if settings.ci_mode or not settings.llm_api_key:
            raise ValueError("Real-model execution needs a configured API key and CODEPILOT_CI_MODE=false")
    simulated = await run_ablations(config)
    real = await run_ablations(config, entries=entries, llm_factory=lambda: LLMClient(settings)) if args.live else {
        "label": "NOT RUN: no paid model experiment authorized", "selected_tasks": [], "trials": [],
        "summary": {p.id: {"status": "NOT RUN", "trial_count": None, "task_success_rate": None, "pass_at_1": None} for p in PROFILES}}
    report = {"schema_version": "1.0", "provenance": provenance(config, model=settings.llm_model if args.live else "ScriptedLLM-v1", mode="live" if args.live else "offline"),
              "simulated": simulated, "real_model": real}
    context = run_context_stress()
    recovery = await run_recovery_matrix()
    for experiment in (context, recovery):
        experiment["provenance"] = report["provenance"]
    write_reports(args.output, report, context, recovery, manifest, args.report)
    print(json.dumps({"simulated": simulated["summary"], "real_model": real["label"], "recovery": [r["status"] for r in recovery["rows"]]}, indent=2))
    if any(row["status"] != "PASS" for row in recovery["rows"]):
        raise ValueError("Recovery correctness experiment failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true")
    modes.add_argument("--live", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    parser.add_argument("--approve-paid", action="store_true")
    parser.add_argument("--tasks", nargs="+")
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--order-seed", type=int, default=17)
    parser.add_argument("--max-tool-calls", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--memory-state", choices=["cold", "seeded"], default="seeded")
    parser.add_argument("--audit-collect", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/results")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/harness_benchmark_report.md")
    args = parser.parse_args(argv)
    try:
        asyncio.run(execute(args))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
