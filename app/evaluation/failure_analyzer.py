"""FailureAnalyzer — 对失败任务进行深层归因分析。

不同于 analyzer.py 的快速错误分类（基于 EvalResult 元数据），
failure_analyzer.py 分析 replay 中的完整执行轨迹，将失败归入 5 类：

1. Planning Error      — Agent 选错了工具或执行顺序不当
2. Tool Selection Error — Agent 调用了错误的工具或传了错误参数
3. Verification Error  — Agent 修改了代码但未运行测试，或测试失败后未修复
4. File Modification Error — Agent 调用了 write_file 但内容不正确
5. Path Resolution Error   — Agent 引用了错误的文件路径
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FailureCluster:
    """单个失败任务的归因结果。"""

    task_id: str
    cluster: str  # planning / tool_selection / verification / file_modification / path_resolution / unknown
    confidence: float  # 0-1
    evidence: list[str] = field(default_factory=list)
    suggestion: str = ""


def analyze_replay(replay: dict) -> FailureCluster:
    """分析单个 replay 轨迹，返回失败归因。"""
    task_id = replay["task_id"]
    result = replay["result"]
    steps = replay.get("steps", [])

    if result["success"]:
        return FailureCluster(task_id=task_id, cluster="unknown", confidence=0.0)

    # 收集证据
    tool_names = [s["tool_name"] for s in steps]
    tool_args_list = [s.get("tool_args", {}) for s in steps]
    has_write = "write_file" in tool_names
    has_run_tests = "run_tests" in tool_names
    has_search = "search_code" in tool_names
    has_read = "read_file" in tool_names
    write_successes = sum(
        1 for s in steps if s["tool_name"] == "write_file" and s["success"]
    )
    test_ran = any(
        s["tool_name"] == "run_tests" and "passed" in s.get("observation", "")
        for s in steps
    )
    test_passed = any(
        s["tool_name"] == "run_tests" and '"failed": 0' in s.get("observation", "")
        for s in steps
    )

    # 检查 write_file 的目标路径
    write_paths = [
        s.get("tool_args", {}).get("path", "")
        for s in steps
        if s["tool_name"] == "write_file"
    ]
    target_file = replay.get("file", "")
    wrote_to_target = any(target_file in p for p in write_paths) if target_file else False

    # 检查 final_answer 中是否有伪造工具调用
    final_answer = replay.get("final_answer", "")
    has_fake_calls = bool(re.search(r"write_file\s*\(", final_answer))

    # 检查 tool_args 中的路径是否包含 .. 或绝对路径
    suspicious_paths = []
    for args in tool_args_list:
        path = args.get("path", args.get("file_path", ""))
        if ".." in path or (path.startswith("/") and not path.startswith("/tmp")):
            suspicious_paths.append(path)

    # === 分析逻辑 ===

    # 1. Verification Error — 最常见的失败模式
    #    特征：有 write_file 但没有 run_tests，或者 run_tests 失败后没有再次修改
    if has_write and not has_run_tests:
        return FailureCluster(
            task_id=task_id,
            cluster="verification",
            confidence=0.85,
            evidence=[
                f"调用了 write_file {write_successes} 次",
                "但从未调用 run_tests 验证",
            ],
            suggestion="Agent 应在修改后立即运行 run_tests 验证结果",
        )

    if has_write and has_run_tests and not test_passed:
        # 测试失败后没有再次修改
        last_write_idx = max(
            i for i, s in enumerate(steps) if s["tool_name"] == "write_file"
        )
        last_test_idx = max(
            i for i, s in enumerate(steps) if s["tool_name"] == "run_tests"
        )
        writes_after_test = any(
            steps[i]["tool_name"] == "write_file"
            for i in range(last_test_idx + 1, len(steps))
        )
        if not writes_after_test:
            return FailureCluster(
                task_id=task_id,
                cluster="verification",
                confidence=0.80,
                evidence=[
                    f"测试失败: {result.get('passed', 0)} passed, {result.get('failed', 0)} failed",
                    "测试失败后没有再次修改代码",
                ],
                suggestion="Agent 应在测试失败后分析失败原因并重新修改",
            )

    # 2. File Modification Error
    #    特征：write_file 成功但测试仍然失败，说明写入内容不正确
    if has_write and write_successes > 0 and has_run_tests and not test_passed:
        return FailureCluster(
            task_id=task_id,
            cluster="file_modification",
            confidence=0.75,
            evidence=[
                f"write_file 成功 {write_successes} 次",
                f"但测试仍然失败: {result.get('passed', 0)} passed, {result.get('failed', 0)} failed",
            ],
            suggestion="Agent 的修复内容不正确，需要更精确地理解 bug 的根因",
        )

    # 3. Tool Selection Error
    #    特征：没有调用 write_file，或者调用了完全不相关的工具
    if not has_write and not has_fake_calls:
        if has_search or has_read:
            return FailureCluster(
                task_id=task_id,
                cluster="tool_selection",
                confidence=0.70,
                evidence=[
                    f"调用了: {', '.join(tool_names)}",
                    "但未调用 write_file 进行修改",
                ],
                suggestion="Agent 需要在搜索/阅读后调用 write_file 完成修改",
            )
        else:
            return FailureCluster(
                task_id=task_id,
                cluster="planning",
                confidence=0.65,
                evidence=[
                    f"调用了: {', '.join(tool_names) or '(无)'}",
                    "未执行有效的代码修改流程",
                ],
                suggestion="Agent 需要制定更清晰的执行计划",
            )

    # 4. Path Resolution Error
    if suspicious_paths:
        return FailureCluster(
            task_id=task_id,
            cluster="path_resolution",
            confidence=0.70,
            evidence=[f"可疑路径: {p}" for p in suspicious_paths],
            suggestion="Agent 引用了错误的文件路径",
        )

    # 5. Planning Error — 兜底
    #    特征：工具调用次数异常（过多或过少），执行顺序混乱
    tool_calls_count = result.get("tool_calls_count", 0)
    if tool_calls_count >= 14:
        return FailureCluster(
            task_id=task_id,
            cluster="planning",
            confidence=0.60,
            evidence=[
                f"工具调用 {tool_calls_count} 次（偏多）",
                f"工具序列: {tool_names}",
            ],
            suggestion="Agent 执行效率低，可能在重复无效操作",
        )

    # 默认归类
    return FailureCluster(
        task_id=task_id,
        cluster="unknown",
        confidence=0.3,
        evidence=[f"工具序列: {tool_names}"],
        suggestion="需要人工分析执行轨迹",
    )


def load_replay(path: Path) -> dict:
    """加载 replay JSON 文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def analyze_all_replays(replay_dir: Path) -> list[FailureCluster]:
    """分析目录下所有 replay 文件。"""
    clusters = []
    for p in sorted(replay_dir.glob("*.json")):
        replay = load_replay(p)
        if not replay.get("result", {}).get("success", True):
            cluster = analyze_replay(replay)
            clusters.append(cluster)
    return clusters


def compute_failure_distribution(clusters: list[FailureCluster]) -> dict[str, dict]:
    """计算失败分布统计。"""
    total = len(clusters)
    if total == 0:
        return {}

    dist: dict[str, dict] = {}
    for c in clusters:
        if c.cluster not in dist:
            dist[c.cluster] = {"count": 0, "tasks": [], "avg_confidence": 0.0}
        dist[c.cluster]["count"] += 1
        dist[c.cluster]["tasks"].append(c.task_id)
        dist[c.cluster]["avg_confidence"] += c.confidence

    for v in dist.values():
        v["avg_confidence"] /= v["count"]
        v["percentage"] = v["count"] / total

    return dist
