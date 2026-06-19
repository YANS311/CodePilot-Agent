#!/usr/bin/env python3
"""analyze_failures.py — 分析失败任务，生成 failure_summary.md。

用法:
    python scripts/analyze_failures.py

前提: 先运行 python scripts/replay_task.py --all-failed 生成轨迹
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.evaluation.failure_analyzer import (
    FailureCluster,
    analyze_all_replays,
    compute_failure_distribution,
)

REPLAY_DIR = _PROJECT_ROOT / "reports" / "replays"
OUTPUT_PATH = _PROJECT_ROOT / "reports" / "failure_summary.md"


def _generate_summary(
    clusters: list[FailureCluster],
    distribution: dict[str, dict],
) -> str:
    """生成 failure_summary.md 内容。"""
    lines = [
        "# Failure Analysis Report",
        "",
        f"**Total failed tasks**: {len(clusters)}",
        "",
    ]

    # 分布概览
    lines.extend([
        "## Failure Distribution",
        "",
        "| Category | Count | % | Avg Confidence | Tasks |",
        "|:---------|------:|--:|---------------:|:------|",
    ])
    for cat, info in sorted(distribution.items(), key=lambda x: -x[1]["count"]):
        tasks_str = ", ".join(info["tasks"])
        lines.append(
            f"| {cat} | {info['count']} | {info['percentage']:.0%} | "
            f"{info['avg_confidence']:.0%} | {tasks_str} |"
        )
    lines.append("")

    # 每个失败任务的详细分析
    lines.extend([
        "## Detailed Analysis",
        "",
    ])

    for c in clusters:
        emoji = {"verification": "VERIFY", "planning": "PLAN", "tool_selection": "TOOL", "file_modification": "FILE", "path_resolution": "PATH"}.get(c.cluster, "?")
        lines.extend([
            f"### {c.task_id} [{emoji}]",
            "",
            f"- **Cluster**: {c.cluster}",
            f"- **Confidence**: {c.confidence:.0%}",
            "",
            "**Evidence**:",
        ])
        for e in c.evidence:
            lines.append(f"- {e}")
        lines.extend([
            "",
            f"**Suggestion**: {c.suggestion}",
            "",
        ])

    # 共性分析
    lines.extend([
        "## Common Patterns",
        "",
    ])

    if distribution:
        top_cluster = max(distribution.items(), key=lambda x: x[1]["count"])
        lines.append(f"Most common failure: **{top_cluster[0]}** ({top_cluster[1]['count']} tasks)")
        lines.append("")

        # 检查是否都是同一类问题
        unique_clusters = set(c.cluster for c in clusters)
        if len(unique_clusters) == 1:
            lines.append("All failures belong to the **same category** — fixing this one issue could resolve all failures.")
        elif len(unique_clusters) == 2:
            lines.append(f"Failures split into **2 categories** — likely share a root cause.")
        else:
            lines.append(f"Failures span **{len(unique_clusters)} categories** — mixed root causes.")

    lines.append("")

    # 改进建议
    lines.extend([
        "## Improvement Suggestions",
        "",
    ])

    cluster_suggestions = {}
    for c in clusters:
        if c.cluster not in cluster_suggestions:
            cluster_suggestions[c.cluster] = {
                "suggestion": c.suggestion,
                "count": 0,
                "tasks": [],
            }
        cluster_suggestions[c.cluster]["count"] += 1
        cluster_suggestions[c.cluster]["tasks"].append(c.task_id)

    for cat, info in sorted(cluster_suggestions.items(), key=lambda x: -x[1]["count"]):
        lines.extend([
            f"### {cat} ({info['count']} tasks: {', '.join(info['tasks'])})",
            "",
            f"> {info['suggestion']}",
            "",
        ])

    return "\n".join(lines)


def main() -> None:
    if not REPLAY_DIR.exists():
        print(f"Replay directory not found: {REPLAY_DIR}")
        print("Run: python scripts/replay_task.py --all-failed")
        sys.exit(1)

    replay_files = list(REPLAY_DIR.glob("*.json"))
    if not replay_files:
        print("No replay files found.")
        sys.exit(1)

    print(f"Analyzing {len(replay_files)} replays...")

    clusters = analyze_all_replays(REPLAY_DIR)
    distribution = compute_failure_distribution(clusters)

    # 打印摘要
    print(f"\nFailed tasks: {len(clusters)}")
    for cat, info in sorted(distribution.items(), key=lambda x: -x[1]["count"]):
        print(f"  {cat}: {info['count']} ({info['percentage']:.0%}) — {', '.join(info['tasks'])}")

    # 生成报告
    summary = _generate_summary(clusters, distribution)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(summary)

    print(f"\nReport saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
