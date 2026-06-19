# Architecture

## System Overview

CodePilot is a single-agent coding assistant built on the ReAct (Reasoning + Acting) pattern. The agent receives a natural language task, reasons about it step-by-step, invokes tools to inspect and modify code, and verifies its changes by running tests.

```
┌──────────────────────────────────────────────────────────────┐
│                        FastAPI Server                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │  ReAct Agent │───▶│  LLM Client  │───▶│  OpenAI API    │  │
│  │  (Loop)      │◀───│  (httpx)     │◀───│  (GPT-4o)      │  │
│  └──────┬──────┘    └──────────────┘    └────────────────┘  │
│         │                                                     │
│         │  tool_calls                                         │
│         ▼                                                     │
│  ┌──────────────────────────────────────────────────────┐    │
│  │                  Tool Registry                        │    │
│  ├──────────┬──────────┬──────────┬──────────┬─────────┤    │
│  │search_code│read_file│write_file│run_tests │git_diff │    │
│  └──────────┴──────────┴──────────┴────┬─────┴─────────┘    │
│                                        │                     │
│                                        ▼                     │
│                              ┌──────────────────┐            │
│                              │ Execution Runner │            │
│                              │ (Local / Docker) │            │
│                              └──────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

## ReAct Agent Loop

The agent follows the standard ReAct pattern:

1. **Think** — The LLM analyzes the task and decides the next action
2. **Act** — The agent calls a tool (e.g., `search_code`, `write_file`)
3. **Observe** — The tool result is fed back to the LLM
4. **Repeat** — Until the task is resolved or the tool call limit is reached

```python
# Simplified loop
while tool_calls_count < max_tool_calls:
    response = llm.chat(messages)          # Think
    if response.has_tool_calls:            # Act
        for call in response.tool_calls:
            result = registry.execute(call) # Observe
            messages.append(tool_result)
    else:
        return response.text               # Done
```

### Guardrail: Fake Tool Call Detection

Some LLMs write tool calls as text (e.g., `write_file("path", "content")`) instead of using the Function Calling protocol. The agent detects this with regex patterns and injects a correction message:

```python
_TOOL_DRIFT_PATTERNS = [
    re.compile(r"write_file\s*\(", re.IGNORECASE),
    re.compile(r"read_file\s*\(", re.IGNORECASE),
    re.compile(r"Action:\s*write_file", re.IGNORECASE),
]
```

## Tool Registry

All tools inherit from `BaseTool` and are registered in `ToolRegistry`:

| Tool | Purpose | Returns |
|------|---------|---------|
| `search_code` | Regex search across workspace files | Matching lines with context |
| `read_file` | Read file contents | File content string |
| `write_file` | Write content to a file | Byte count written |
| `run_tests` | Execute pytest on target | JSON with pass/fail counts |
| `git_diff` | Show staged/unstaged changes | Diff output |
| `git_status` | Show working tree status | Status output |

Each tool validates inputs, enforces path safety (no traversal outside workspace), and returns structured results.

## Execution Environment

Tests are executed via `ExecutionRunner`, with two implementations:

### Local Runner (`LocalExecutionRunner`)
- Uses `subprocess.run` + `asyncio.run_in_executor` (Windows-compatible)
- 30s timeout, 50KB max output
- Runs `pytest <target> -v --tb=short --no-header -q`

### Docker Runner (`DockerExecutionRunner`)
- `docker run --rm --read-only --network none python:3.12-slim`
- Full filesystem and network isolation
- Falls back to local if Docker is unavailable

The runner is selected via `EXECUTION_MODE` env var (`local` or `docker`).

## Evaluation Framework

```
evaluation/tasks.json ──▶ EvaluationRunner ──▶ EvalResult ──▶ Metrics
                              │                                   │
                              ├── workspace_seed/ (copy)          │
                              │   └── workspace_eval/<task_id>/   │
                              │                                   │
                              └── run_task()                      │
                                  ├── agent.run()                 │
                                  ├── run_tests(test_target)      │
                                  └── analyze_error()             │
```

- **Workspace isolation**: Each task gets a fresh copy of `workspace_seed/`
- **Task-specific tests**: Only the relevant test file is executed
- **Error taxonomy**: Failed tasks are automatically classified into 7 error types

See [evaluation.md](evaluation.md) for results and [error-taxonomy.md](error-taxonomy.md) for error types.
