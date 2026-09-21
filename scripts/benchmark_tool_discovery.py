#!/usr/bin/env python3
"""scripts/benchmark_tool_discovery.py — Tool Discovery Progressive Loading Benchmark.

评估全量工具暴露 vs Top-K 动态检索在 Schema 数量与 Token 消耗上的优化收益。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.tools.base import BaseTool
from app.tools.discovery import ToolDiscovery


class BenchmarkDummyTool(BaseTool):
    """基准测试虚拟工具。"""

    def __init__(self, name: str, description: str, parameters: Dict[str, Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters

    async def run(self, *, workspace_root: str, **kwargs: Any) -> str:
        return f"executed {self.name}"


def _estimate_tokens(schemas: List[dict]) -> int:
    """估算工具 Schema 占用的 Token 数量。"""
    raw_json = json.dumps(schemas, ensure_ascii=False)
    # 按通用 LLM 经验：中文/英文混排时平均约 3.5 字符 / token
    return max(1, int(len(raw_json) / 3.5))


def get_benchmark_tools() -> List[BaseTool]:
    """构建 10 个具有代表性的异构工具库（5 原生 + 5 MCP）。"""
    return [
        # Native Tools
        BenchmarkDummyTool(
            name="read_file",
            description="Read file contents from local filesystem with line offset support",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path in workspace"},
                    "offset": {"type": "integer", "description": "Line offset to start reading from"},
                    "limit": {"type": "integer", "description": "Max lines to read"},
                },
                "required": ["path"],
            },
        ),
        BenchmarkDummyTool(
            name="write_file",
            description="Write new text content to target file path on local filesystem",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination file path"},
                    "content": {"type": "string", "description": "File body content to write"},
                },
                "required": ["path", "content"],
            },
        ),
        BenchmarkDummyTool(
            name="code_edit",
            description="Perform surgical line-based text replacement in existing source code file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file to edit"},
                    "old": {"type": "string", "description": "Target string chunk to be replaced"},
                    "new": {"type": "string", "description": "Replacement string chunk"},
                },
                "required": ["path", "old", "new"],
            },
        ),
        BenchmarkDummyTool(
            name="search_code",
            description="Fast regex or literal code pattern search across workspace directory tree",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keyword or regex pattern to search"},
                    "file_pattern": {"type": "string", "description": "Glob filter for target filenames"},
                },
                "required": ["query"],
            },
        ),
        BenchmarkDummyTool(
            name="run_tests",
            description="Execute pytest automated test suite in workspace and return stdout/stderr",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Target test file or test node id"},
                    "flags": {"type": "string", "description": "Optional flags e.g. -k or -q"},
                },
            },
        ),
        # MCP Tools
        BenchmarkDummyTool(
            name="mcp_db_query_database",
            description="Execute read-only SQL queries against relational database tables (PostgreSQL / MySQL)",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL select statement to execute"},
                    "database": {"type": "string", "description": "Target database schema name"},
                    "timeout_seconds": {"type": "number", "description": "Query execution timeout"},
                },
                "required": ["sql"],
            },
        ),
        BenchmarkDummyTool(
            name="mcp_github_create_pull_request",
            description="Create a new Pull Request on remote GitHub repository with title, branch, and description",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "PR title"},
                    "head": {"type": "string", "description": "Head branch containing commits"},
                    "base": {"type": "string", "description": "Target merge branch, default main"},
                    "body": {"type": "string", "description": "Markdown formatted description"},
                },
                "required": ["title", "head"],
            },
        ),
        BenchmarkDummyTool(
            name="mcp_slack_send_notification",
            description="Post real-time alerts, error notifications, or task status updates to Slack channel",
            parameters={
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Slack channel name or ID"},
                    "message": {"type": "string", "description": "Text or BlockKit message content"},
                    "mention_users": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["channel", "message"],
            },
        ),
        BenchmarkDummyTool(
            name="mcp_k8s_list_pods",
            description="List Kubernetes cluster pods, container statuses, restarts, and health readiness",
            parameters={
                "type": "object",
                "properties": {
                    "namespace": {"type": "string", "description": "Kubernetes namespace filter"},
                    "label_selector": {"type": "string", "description": "Label selector query string"},
                },
            },
        ),
        BenchmarkDummyTool(
            name="mcp_s3_upload_artifact",
            description="Upload build binary, report artifact or logs archive to Amazon S3 bucket",
            parameters={
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "description": "S3 bucket name"},
                    "key": {"type": "string", "description": "Destination S3 object key path"},
                    "local_file": {"type": "string", "description": "Path of local file to upload"},
                },
                "required": ["bucket", "key", "local_file"],
            },
        ),
    ]


BENCHMARK_TASKS = [
    {
        "id": "task_1",
        "task": "查找代码中包含 parse_config 函数的实现文件并检查逻辑",
        "active_skill": "repository-explorer",
    },
    {
        "id": "task_2",
        "task": "查询用户数据库中活跃账号数量并统计注册趋势",
        "active_skill": None,
    },
    {
        "id": "task_3",
        "task": "在 GitHub 上为当前 feature 分支创建 Pull Request 并附上修改说明",
        "active_skill": "git-workflow",
    },
    {
        "id": "task_4",
        "task": "修复 payment.py 中的空指针异常错误，并运行单元测试验证结果",
        "active_skill": "bug-fix",
    },
    {
        "id": "task_5",
        "task": "向 Slack 团队运维频道发送服务健康检查告警通知",
        "active_skill": None,
    },
]


async def run_benchmark(top_k: int = 3) -> Dict[str, Any]:
    """运行对比基准测试。"""
    tools = get_benchmark_tools()
    all_schemas = [t.to_openai_schema() for t in tools]
    before_schema_count = len(all_schemas)
    before_tokens = _estimate_tokens(all_schemas)

    discovery = ToolDiscovery(default_top_k=top_k)
    results = []

    total_after_tokens = 0

    print("=" * 80)
    print(f"Tool Progressive Loading Benchmark (10 Tools, 5 Tasks, Top-K={top_k})")
    print("=" * 80)
    print(f"Baseline (Before): {before_schema_count} tools, ~{before_tokens} tokens per prompt\n")

    for item in BENCHMARK_TASKS:
        task_text = item["task"]
        skill = item["active_skill"]

        selected, meta = await discovery.select_tools_detailed(
            task=task_text,
            tools=tools,
            top_k=top_k,
            active_skill=skill,
        )

        after_schemas = [t.to_openai_schema() for t in selected]
        after_tokens = _estimate_tokens(after_schemas)
        total_after_tokens += after_tokens

        token_reduction = (before_tokens - after_tokens) / before_tokens * 100.0

        results.append({
            "task_id": item["id"],
            "task": task_text,
            "skill": skill or "None",
            "selected_tools": [t.name for t in selected],
            "before_count": before_schema_count,
            "after_count": len(selected),
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
            "reduction_pct": round(token_reduction, 1),
        })

    avg_after_tokens = int(total_after_tokens / len(BENCHMARK_TASKS))
    avg_reduction_pct = round((before_tokens - avg_after_tokens) / before_tokens * 100.0, 1)

    # 打印 Markdown 表格
    print("| Task ID | Active Skill | Selected Tools (Top-K) | Tools (Before/After) | Tokens (Before/After) | Reduction (%) |")
    print("|---|---|---|---|---|---|")
    for r in results:
        tools_str = ", ".join(f"`{t}`" for t in r["selected_tools"])
        print(
            f"| {r['task_id']} | `{r['skill']}` | {tools_str} | "
            f"{r['before_count']} &rarr; **{r['after_count']}** | "
            f"{r['before_tokens']} &rarr; **{r['after_tokens']}** | "
            f"**-{r['reduction_pct']}%** |"
        )

    print("\n" + "-" * 80)
    print(f"Average Token Reduction Ratio: -{avg_reduction_pct}% (from ~{before_tokens} to ~{avg_after_tokens} tokens)")
    print("-" * 80 + "\n")

    return {
        "before_tools": before_schema_count,
        "before_tokens": before_tokens,
        "top_k": top_k,
        "avg_after_tokens": avg_after_tokens,
        "avg_reduction_pct": avg_reduction_pct,
        "tasks": results,
    }


if __name__ == "__main__":
    asyncio.run(run_benchmark(top_k=3))
