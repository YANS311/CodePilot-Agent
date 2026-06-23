# CodePilot Agent

> **Evidence-grounded AI Coding Agent System**

## System Overview

CodePilot is an evidence-grounded coding agent built from scratch with FastAPI + LLM tool-calling. It searches code, locates bugs, fixes issues, runs tests, and explains every decision with code-level evidence.

| Layer | What it does |
|-------|-------------|
| **Agent** | ReAct loop (Think → Act → Observe) + Mode Router for intent detection |
| **Tool** | 6 tools: search, read, write, run_tests, git_diff, git_status |
| **Evaluation** | 30-task benchmark + 15 real-world + 10 stress test tasks |
| **Explainability** | AST evidence extraction with confidence scoring |

## Architecture

```
                        User
                         │
                  ┌──────▼──────┐
                  │  FastAPI    │
                  └──────┬──────┘
                         │
              ┌──────────▼──────────┐
              │  Agent Orchestrator │
              │  Mode Router        │
              │  ReAct / Repo Mode  │
              └──────────┬──────────┘
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
      ┌──────────┐ ┌──────────┐ ┌──────────┐
      │  Tools   │ │Execution │ │Workspace │
      │ 6 tools  │ │Local/    │ │Index +   │
      │ + guard  │ │Docker    │ │Resolver  │
      └──────────┘ └──────────┘ └──────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │Evaluation│   │ Security │   │Evidence  │
   │30+15 tasks│  │Guardrails│   │AST +     │
   │TSR 90%   │   │100% block│   │Confidence│
   └──────────┘   └──────────┘   └──────────┘
```

## Demo

One unified flow: **Upload → Index → Agent → Tool → Execute → Evidence → Result**

| Step | What happens |
|------|-------------|
| 1 | Upload a buggy Python project |
| 2 | Agent auto-builds WorkspaceIndex (file tree + AST summaries) |
| 3 | Click **Bug Fix** — Agent locates, reads, fixes, tests, verifies |
| 4 | Unified output: Summary + Trace + Tools + Metrics + Evidence + Confidence |

```bash
# Quick start
git clone https://github.com/YANS311/CodePilot-Agent.git
cd CodePilot-Agent
cp .env.example .env    # Add your API key
docker-compose up       # Open http://localhost:8000
```

## Metrics

| Metric | Value | What It Proves |
|--------|------:|----------------|
| Task Success Rate (Normal) | **90%** | Core capability on controlled tasks |
| Task Success Rate (Stress) | Measured | Real-world boundary under complexity |
| Recovery Rate | Measured | Ability to recover from failures |
| Security Block Rate | **100%** | Attack inputs never reach LLM |
| Tool Efficiency | Measured | Tool calls per successful task |

> All metrics are based on controlled evaluation + real-world benchmark.

| Benchmark | Tasks | Scope |
|-----------|------:|-------|
| Synthetic (Easy/Medium/Hard) | 30 | Bug fix / enhancement |
| Real-World (3 repos, seeded bugs) | 15 | Cross-file, hidden bugs |
| Stress Test (multi-file, recovery) | 10 | Complexity boundary |

## Security

3-layer defense:

1. **Prompt Injection Detection** — blocks role-play, instruction override, jailbreak
2. **Tool Guardrail** — prevents dangerous operations (file deletion, path traversal)
3. **Completion Chain** — validates claimed fixes were actually executed via tool calls

## Explainability

Every analysis conclusion backed by code evidence:

```
Claim: Bug in subtract function
- File: app/calc.py, Symbol: subtract, Lines: 15-20

Confidence: 85%
```

## Tech Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.9+ |
| Backend | FastAPI + Pydantic |
| LLM | OpenAI / DeepSeek compatible API |
| Execution | Local subprocess / Docker sandbox |
| Indexing | Workspace Intelligence (file tree + AST) |
| Eval | Custom benchmark with 7 advanced metrics |
| Security | Prompt injection + tool guardrail |

## Run Tests

```bash
pytest tests/ -v    # 416 unit tests
```

## Keywords

> **Python / FastAPI / LLM / Agent / RAG / Docker / Tool Calling / Evaluation / Security / ReAct / Explainability**

## License

MIT
