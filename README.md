# CodePilot Agent

> **CodePilot is a Python-based AI Coding Agent system built with FastAPI and LLM tool-calling architecture.**

A full-stack Agent platform that autonomously fixes bugs, analyzes codebases, and provides evidence-backed explanations — built from scratch with ReAct loop, evaluation framework, security guardrails, and explainability layer.

## 1-Command Run

```bash
# Clone and start
git clone https://github.com/YANS311/CodePilot-Agent.git
cd CodePilot-Agent
cp .env.example .env    # Add your API key
docker-compose up
# Open http://localhost:8000
```

## Live Demo Flow

| Step | Action | Result |
|------|--------|--------|
| 1 | Click **Bug Fix** | Agent auto-locates → reads → fixes → tests → verifies |
| 2 | Click **Repo Analysis** | AST evidence extraction → structured report → confidence 85% |
| 3 | Click **Security** | Prompt injection detected → blocked by guardrails |

## Tech Stack

| Category | Technology |
|----------|-----------|
| **Language** | Python 3.9+ |
| **Backend** | FastAPI + Pydantic Settings |
| **LLM** | OpenAI / DeepSeek compatible API (Tool Calling / Function Calling) |
| **Execution** | Local subprocess / Docker sandbox (`--read-only --network none`) |
| **Repo Indexing** | RAG-like Workspace Intelligence (file tree + AST summaries) |
| **Eval** | Custom 30-task benchmark with 7 advanced metrics |
| **Security** | Prompt injection detection + tool guardrail |

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
   │30 tasks  │   │Guardrails│   │AST +     │
   │TSR 90%   │   │100% block│   │Confidence│
   └──────────┘   └──────────┘   └──────────┘
```

## Project Description

### Layer 1 — Resume Screening

> Python + FastAPI 后端服务 | 基于 LLM 的 Agent 系统 | 支持代码修复 / 文件操作 / 自动测试

- Python backend service built with FastAPI
- LLM-powered Agent system with Tool Calling architecture
- Automated code fix, file operations, and test execution

### Layer 2 — Technical Capability

> ReAct Agent Loop | Tool Registry | Evaluation System | Security Guardrails | Evidence-based Repo Analysis

- **ReAct Agent**: Think → Act → Observe loop with 6 tools and Mode Router
- **Evaluation**: 30-task benchmark, 7 advanced metrics, automatic error taxonomy. **TSR: 90%**
- **Security**: Prompt injection detection, tool guardrail, completion chain validation. **Block Rate: 100%**
- **Explainability**: AST-based evidence extraction with confidence scoring (0.0~1.0)

## Features

- **ReAct Agent** — Think → Act → Observe loop with 6 tools (search, read, write, test, diff, status). Mode Router auto-detects intent: code tasks vs project analysis.
- **Evaluation Framework** — 30-task benchmark (Easy/Medium/Hard), 7 advanced metrics, automatic error taxonomy. **TSR: 90%**.
- **Security Guardrails** — Prompt injection detection, tool execution guardrail, completion chain validation. **Block Rate: 100%**.
- **Explainability** — AST-based evidence extraction. Every conclusion backed by file → function → line number. **Confidence scoring (0.0~1.0)**.

## Demo

3 built-in demos — click a button to run:

| Demo | What it shows |
|------|---------------|
| **Bug Fix** | Auto-locate file → read code → fix bug → run tests → verify |
| **Repo Analysis** | Scan workspace → extract evidence → structured report with confidence |
| **Security** | Prompt injection detected → blocked by guardrails |

```bash
# Quick start
pip install -r requirements.txt
uvicorn app.main:app --reload
# Open http://localhost:8000
```

## Evaluation

30-task benchmark across three difficulty tiers:

| Difficulty | Tasks | Pass Rate |
|:-----------|------:|----------:|
| Easy       |    10 | **100%**  |
| Medium     |    12 | **92%**   |
| Hard       |     8 | **75%**   |
| **Total**  | **30**| **90%**   |

| Metric | Value |
|--------|------:|
| Task Success Rate | 90.0% |
| Test Pass Rate | 96.6% |
| Tool Call Validity | ~98% |
| Verification Completion | ~85% |
| Code Change Validity | 93.3% |
| Planning Efficiency | 6.9 |
| Security Block Rate | 100% |

## Security

3-layer defense:

1. **Prompt Injection Detection** — Blocks role-play, instruction override, jailbreak attempts
2. **Tool Guardrail** — Prevents dangerous operations (file deletion, network requests, path traversal)
3. **Completion Chain** — Validates that claimed fixes were actually executed via tool calls

## Explainability

Every analysis conclusion includes evidence:

```
Claim: Agent core loop implemented in react_agent.py
- File: app/agent/react_agent.py, Symbol: ReActAgent, Lines: 112-308
- File: app/agent/react_agent.py, Symbol: run, Lines: 140-308

Confidence: 85%
```

## Quick Start

```bash
# Option 1: Docker (recommended)
docker-compose up
# Open http://localhost:8000

# Option 2: Local
pip install -r requirements.txt
cp .env.example .env    # Add your API key
uvicorn app.main:app --reload

# Run all 3 demos from CLI
python scripts/demo_runner.py
```

## Run Tests

```bash
pytest tests/ -v    # 337 unit tests
```

## Keywords for Recruitment

> **Python / FastAPI / LLM / Agent / RAG / Docker / Tool Calling / Function Calling / Evaluation / Security / ReAct / Prompt Engineering**

## Docs

- [Architecture Overview](docs/architecture_overview.md) — Complete system diagram
- [3-Minute Interview Script](docs/interview_3min.md) — 面试讲解稿
- [Final Demo Script](docs/demo_script_final.md) — 可复现的演示流程
- [Demo Recording Guide](docs/demo_guide.md) — 录屏步骤和推荐工具
- [Demo Flows](docs/demo_flows.md) — Standardized demo scenarios
- [Evaluation](docs/evaluation.md) — Full metrics breakdown
- [Error Taxonomy](docs/error-taxonomy.md) — 7 error types

## License

MIT
