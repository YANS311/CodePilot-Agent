"""Real-world repo bug benchmark runner.

Runs the CodePilot agent on 15 seeded-bug tasks across 3 small repos,
measures fix success, and produces a JSON report.

Usage:
    py scripts/run_realworld_eval.py [--tasks todo-01,calc-01] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = ROOT / "benchmarks" / "real_world"
REPOS_DIR = BENCH_DIR / "repos"
REPORTS_DIR = BENCH_DIR / "reports"
TASKS_FILE = BENCH_DIR / "tasks.json"


def load_tasks() -> List[Dict[str, Any]]:
    with open(TASKS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data["tasks"]


def make_work_copy(repo_name: str, task_id: str) -> Path:
    """Create an isolated work copy of the repo for a task."""
    src = REPOS_DIR / repo_name
    dst = REPORTS_DIR / f"work_{task_id}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def run_tests(work_dir: Path, test_pattern: str) -> Dict[str, Any]:
    """Run pytest in the work directory and return structured results."""
    cmd = [sys.executable, "-m", "pytest", test_pattern, "-v", "--tb=short"]
    start = time.time()
    result = subprocess.run(
        cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = round(time.time() - start, 2)

    # Parse output for pass/fail counts
    passed = result.stdout.count(" PASSED")
    failed = result.stdout.count(" FAILED")
    errors = result.stdout.count(" ERROR")

    return {
        "returncode": result.returncode,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "elapsed_s": elapsed,
        "stdout": result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
        "stderr": result.stderr[-1000:] if len(result.stderr) > 1000 else result.stderr,
    }


def run_agent_on_task(task: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
    """Invoke the CodePilot agent to fix bugs in a task.

    This calls the existing benchmark runner or demo_runner infrastructure.
    For now, we do a simple prompt-based invocation.
    """
    # Build the agent prompt from the task description
    prompt = (
        f"Fix the bug in this repository.\n\n"
        f"Task: {task['title']}\n"
        f"Description: {task['description']}\n"
        f"Files to modify: {', '.join(task['files_to_modify'])}\n\n"
        f"Repository root: {work_dir}\n"
        f"Hint: {task.get('hints', [''])[0]}\n\n"
        f"After fixing, verify by running: {task['test_command']}"
    )

    # Try to import and use the existing agent
    try:
        sys.path.insert(0, str(ROOT))
        from app.agent.react_agent import ReactAgent
        from app.config import settings

        agent = ReactAgent(workspace_root=str(work_dir))
        result = agent.run(prompt)
        return {
            "agent_used": True,
            "answer": result.answer[:500] if result.answer else "",
            "tool_calls": len(result.tool_calls),
            "success": result.success,
        }
    except Exception as e:
        return {
            "agent_used": False,
            "error": str(e)[:500],
        }


def run_single_task(task: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """Run one benchmark task end-to-end."""
    task_id = task["id"]
    repo = task["repo"]

    print(f"\n{'='*60}")
    print(f"Task: {task_id} — {task['title']}")
    print(f"Repo: {repo} | Difficulty: {task['difficulty']}")
    print(f"{'='*60}")

    # Create isolated work copy
    work_dir = make_work_copy(repo, task_id)
    print(f"Work copy: {work_dir}")

    # Run baseline tests (should have failures)
    print("Running baseline tests...")
    baseline = run_tests(work_dir, task["expected_test"])
    print(f"  Baseline: {baseline['passed']} passed, {baseline['failed']} failed")

    if dry_run:
        print("  [DRY RUN] Skipping agent invocation")
        return {
            "task_id": task_id,
            "repo": repo,
            "difficulty": task["difficulty"],
            "title": task["title"],
            "files_to_modify": task["files_to_modify"],
            "baseline": baseline,
            "agent_result": {"dry_run": True},
            "final_tests": baseline,
            "fixed": False,
        }

    # Run agent to fix bugs
    print("Running agent...")
    agent_result = run_agent_on_task(task, work_dir)
    print(f"  Agent used: {agent_result.get('agent_used', False)}")

    # Run tests again after agent fix
    print("Running verification tests...")
    final = run_tests(work_dir, task["expected_test"])
    print(f"  Final: {final['passed']} passed, {final['failed']} failed")

    fixed = final["failed"] == 0 and final["passed"] > 0
    print(f"  Result: {'FIXED' if fixed else 'NOT FIXED'}")

    return {
        "task_id": task_id,
        "repo": repo,
        "difficulty": task["difficulty"],
        "title": task["title"],
        "files_to_modify": task["files_to_modify"],
        "baseline": {
            "passed": baseline["passed"],
            "failed": baseline["failed"],
            "elapsed_s": baseline["elapsed_s"],
        },
        "agent_result": {
            "agent_used": agent_result.get("agent_used", False),
            "answer_preview": agent_result.get("answer", "")[:300],
            "tool_calls": agent_result.get("tool_calls", 0),
            "error": agent_result.get("error"),
        },
        "final_tests": {
            "passed": final["passed"],
            "failed": final["failed"],
            "elapsed_s": final["elapsed_s"],
        },
        "fixed": fixed,
    }


def compute_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate benchmark metrics."""
    total = len(results)
    fixed = sum(1 for r in results if r["fixed"])

    # By difficulty
    by_diff = {}
    for diff in ["easy", "medium", "hard"]:
        subset = [r for r in results if r["difficulty"] == diff]
        if subset:
            by_diff[diff] = {
                "total": len(subset),
                "fixed": sum(1 for r in subset if r["fixed"]),
                "rate": round(sum(1 for r in subset if r["fixed"]) / len(subset), 3),
            }

    # By repo
    by_repo = {}
    for repo in ["todo_api", "calculator_pkg", "config_parser"]:
        subset = [r for r in results if r["repo"] == repo]
        if subset:
            by_repo[repo] = {
                "total": len(subset),
                "fixed": sum(1 for r in subset if r["fixed"]),
                "rate": round(sum(1 for r in subset if r["fixed"]) / len(subset), 3),
            }

    # Modified files accuracy (did the agent touch the right files?)
    files_accuracy = []
    for r in results:
        expected = set(r["files_to_modify"])
        # This would need file-change tracking in a real run
        files_accuracy.append({
            "task_id": r["task_id"],
            "expected_files": list(expected),
        })

    return {
        "total_tasks": total,
        "fixed": fixed,
        "fix_rate": round(fixed / total, 3) if total else 0,
        "by_difficulty": by_diff,
        "by_repo": by_repo,
        "files_accuracy": files_accuracy,
    }


def generate_report(results: List[Dict[str, Any]], metrics: Dict[str, Any]) -> str:
    """Generate a human-readable report."""
    lines = [
        "# Real-World Bug Benchmark Report",
        "",
        f"**Date**: {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Total Tasks**: {metrics['total_tasks']}",
        f"**Fixed**: {metrics['fixed']}/{metrics['total_tasks']} ({metrics['fix_rate']*100:.1f}%)",
        "",
        "## By Difficulty",
        "",
        "| Difficulty | Total | Fixed | Rate |",
        "|------------|-------|-------|------|",
    ]
    for diff, stats in metrics.get("by_difficulty", {}).items():
        lines.append(f"| {diff} | {stats['total']} | {stats['fixed']} | {stats['rate']*100:.1f}% |")

    lines.extend([
        "",
        "## By Repository",
        "",
        "| Repo | Total | Fixed | Rate |",
        "|------|-------|-------|------|",
    ])
    for repo, stats in metrics.get("by_repo", {}).items():
        lines.append(f"| {repo} | {stats['total']} | {stats['fixed']} | {stats['rate']*100:.1f}% |")

    lines.extend(["", "## Task Details", ""])
    for r in results:
        status = "PASS" if r["fixed"] else "FAIL"
        lines.append(f"- [{status}] **{r['task_id']}** ({r['difficulty']}) — {r['title']}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run real-world bug benchmark")
    parser.add_argument(
        "--tasks",
        type=str,
        default=None,
        help="Comma-separated task IDs to run (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run baseline tests only, skip agent invocation",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON report path (default: reports/eval_TIMESTAMP.json)",
    )
    args = parser.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    tasks = load_tasks()
    if args.tasks:
        task_ids = [t.strip() for t in args.tasks.split(",")]
        tasks = [t for t in tasks if t["id"] in task_ids]
        if not tasks:
            print(f"No tasks matched IDs: {args.tasks}")
            sys.exit(1)

    print(f"Running {len(tasks)} tasks (dry_run={args.dry_run})")

    results = []
    for task in tasks:
        result = run_single_task(task, dry_run=args.dry_run)
        results.append(result)

    metrics = compute_metrics(results)
    report_text = generate_report(results, metrics)

    # Save JSON report
    ts = time.strftime("%Y%m%d_%H%M%S")
    json_path = Path(args.output) if args.output else REPORTS_DIR / f"eval_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "metrics": metrics}, f, indent=2, ensure_ascii=False)
    print(f"\nJSON report: {json_path}")

    # Save markdown report
    md_path = json_path.with_suffix(".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Markdown report: {md_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(report_text)
    print(f"{'='*60}")

    # Cleanup work copies
    for r in results:
        work = REPORTS_DIR / f"work_{r['task_id']}"
        if work.exists():
            shutil.rmtree(work)
    print("Cleaned up work copies.")


if __name__ == "__main__":
    main()
