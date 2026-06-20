# CodePilot Agent

> A Python Coding Agent that thinks, acts, verifies, and explains — built from scratch.

CodePilot autonomously fixes bugs in Python codebases. It searches code, reads files, writes fixes, runs tests, and outputs evidence-backed analysis reports.

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
pip install -r requirements.txt
cp .env.example .env    # Add your API key
uvicorn app.main:app --reload
curl http://localhost:8000/health  # {"status":"ok"}
```

## Run Tests

```bash
pytest tests/ -v    # 337 unit tests
```

## Docs

- [Architecture Overview](docs/architecture_overview.md) — Complete system diagram
- [3-Minute Interview Script](docs/interview_3min.md) — 面试讲解稿
- [Demo Flows](docs/demo_flows.md) — Standardized demo scenarios
- [Evaluation](docs/evaluation.md) — Full metrics breakdown
- [Error Taxonomy](docs/error-taxonomy.md) — 7 error types

## Tech Stack

Python 3.9+ | FastAPI | Pydantic | OpenAI Compatible API | Docker (optional)

## License

MIT
