# CodePilot Agent

> A mini coding agent that thinks, acts, and verifies — built from scratch in Python.

CodePilot is a lightweight **ReAct Agent** with **Tool Calling**, designed to autonomously fix bugs in Python codebases. It follows a structured reasoning loop: search the code, read the relevant files, write fixes, run tests, and report diffs.

```
User: "Fix the subtract bug in calculator.py"
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              ReAct Agent Loop                       │
│                                                     │
│  Think: "subtract returns a + b, should be a - b"  │
│    Act: write_file("a - b")                        │
│  Observe: file updated                             │
│    Act: run_tests("test_buggy_calculator")          │
│  Observe: 1 passed, 0 failed                       │
│    Act: git_diff                                   │
│  Observe: +1 -1                                    │
│  Answer: "Fixed. subtract now returns a - b"       │
└─────────────────────────────────────────────────────┘
```

## Eval Results

30-task benchmark across three difficulty tiers:

| Difficulty | Tasks | Pass Rate | Description |
|:-----------|------:|----------:|-------------|
| Easy       |    10 | **100%**  | Single-line fixes, off-by-one, import errors |
| Medium     |    12 | **92%**   | Multi-function bugs, missing fields, URL encoding |
| Hard       |     8 | **75%**   | Cross-file fixes, multiple bugs in one file |
| **Total**  | **30**| **90%**   | |

### Advanced Metrics (D15+)

| Metric | Value | Description |
|--------|------:|-------------|
| Task Success Rate | 90.0% | 任务是否最终通过 |
| Test Pass Rate | 96.6% | 测试是否通过 |
| Tool Call Validity | ~98% | 工具调用是否合法 |
| Verification Completion | ~85% | 修改后是否执行 run_tests |
| Code Change Validity | 93.3% | 是否实际调用 write_file |
| Planning Efficiency | 6.9 | 成功任务平均工具调用次数 |
| Security Block Rate | 100% | 攻击样例被正确拦截的比例 |

See [docs/evaluation.md](docs/evaluation.md) for full breakdown.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        FastAPI Server                         │
│                         (app/main.py)                        │
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
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │ Execution Runner │    │     Language Detector         │   │
│  │ (Local / Docker) │◀───│  PythonAdapter (full)        │   │
│  └──────────────────┘    │  JavaAdapter / NodeAdapter    │   │
│                          └──────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

**Core loop**: Think -> Act -> Observe, repeated until the task is resolved or the tool call limit is reached.

## Features

| Feature | Description |
|---------|-------------|
| **ReAct Agent** | Think-Act-Observe loop with OpenAI Function Calling |
| **6 Tools** | `search_code` `read_file` `write_file` `run_tests` `git_diff` `git_status` |
| **Language Adapter** | BaseLanguageAdapter ABC + PythonAdapter (full) / Java / Node (stubs), auto-detection |
| **Advanced Metrics** | 7 metrics: TSR, Test Pass Rate, Tool Validity, Verification Rate, Code Change, Planning Efficiency, Security Block Rate |
| **Prompt Guardrail** | Detects and corrects fake tool calls in model text output |
| **Execution Sandbox** | Local subprocess or Docker `--read-only --network none` |
| **Evaluation Framework** | 30 tasks, auto metrics, error taxonomy, markdown reports |
| **Error Taxonomy** | 7 error types with automatic root-cause classification |

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API key

# Run server
uvicorn app.main:app --reload

# Verify
curl http://localhost:8000/health
# {"status":"ok"}
```

## Demo

> TODO: Add screenshot or GIF of the agent fixing a bug end-to-end

```
$ python scripts/run_eval.py --tasks fix-subtract
Loaded 30 tasks
  [1] fix-subtract: PASS (test=PASS, tools=7, 26s)
Task Success Rate: 100.0% (1/1)
```

## Run Tests

```bash
pytest tests/ -v          # 147 unit tests
```

## Run Full Evaluation

```bash
python scripts/run_eval.py                    # All 30 tasks
python scripts/run_eval.py --tasks fix-subtract  # Single task
# Output: reports/eval_report.md
```

## Project Structure

```
app/
├── main.py                  # FastAPI entry
├── core/config.py           # Pydantic Settings
├── agent/
│   ├── react_agent.py       # ReAct loop + guardrail
│   └── prompts.py           # System prompt
├── language/                # Language Adapter (ABC + Python/Java/Node)
├── tools/                   # 6 tools + registry
├── execution/               # Local / Docker runners
└── evaluation/              # Metrics (7 advanced), analyzer, taxonomy

workspace/                   # Bug seed files + tests
evaluation/tasks.json        # 30 eval tasks
scripts/run_eval.py          # Eval CLI
tests/                       # 192+ unit tests
docs/                        # Architecture & eval docs
```

## Tech Stack

Python 3.11+ | FastAPI | Pydantic Settings | OpenAI Compatible API | Docker (optional)

## License

MIT

---
Built with Claude Code
