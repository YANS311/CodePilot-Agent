# CodePilot Agent

> **Lightweight AI Coding Agent Prototype**

## System Overview

CodePilot is an interview-ready engineering prototype that demonstrates a ReAct-based coding agent with tool-calling, evidence-grounded analysis, and controlled evaluation benchmarks.

| Layer | What it does |
|-------|-------------|
| **Agent** | ReAct loop (Think -> Act -> Observe) with hybrid intent routing |
| **Tool** | 6 tools: search, read, write, run_tests, git_diff, git_status |
| **Memory** | Lightweight hybrid memory: structured (keyword) + vector (FAISS) |
| **Routing** | 3-layer intent router: rule -> embedding -> LLM fallback |
| **Concurrency** | Workspace-level lock with FIFO queue |
| **Evaluation** | 30 synthetic + 15 real-world + 10 stress test tasks |
| **Explainability** | AST evidence extraction with confidence scoring |

## Architecture

```
                        User
                         |
                  +------v------+
                  |  FastAPI    |
                  +------+------+
                         |
              +----------v----------+
              |  Agent Orchestrator |
              |  Intent Router      |
              |  ReAct / Repo Mode  |
              +----------+----------+
                         |
            +------------+------------+
            v            v            v
      +----------+ +----------+ +----------+
      |  Tools   | | Execution| |Workspace |
      | 6 tools  | | Local/   | |Index +   |
      | + guard  | | Docker   | |Lock      |
      +----------+ +----------+ +----------+
                         |
         +---------------+---------------+
         v               v               v
   +----------+   +----------+   +----------+
   |Evaluation|   | Security |   |Evidence  |
   |30+15+10  |   |Guardrails|   |AST +     |
   |tasks     |   |3-layer   |   |Confidence|
   +----------+   +----------+   +----------+
         |
   +-----v-----+
   |  Memory   |
   |Structured |
   |+ Vector   |
   +-----------+
```

## Features

### Agent Memory Layer

Three tiers of memory for context persistence:

| Tier | Type | What it stores |
|------|------|---------------|
| **Short-term** | In-memory | ReAct execution trace, tool history, current task context |
| **Structured long-term** | Keyword-indexed | Task history (what was done), error patterns (what failed), repo knowledge |
| **Vector memory** | FAISS + sentence-transformers | Semantic similarity search across all memory entries |

Memory is injected into the agent prompt as context on each task, enabling the agent to recall prior errors and similar tasks.

### Hybrid Intent Router

3-layer routing to determine agent mode (ReAct / Repo Analysis / Security Block):

| Layer | Method | Latency |
|-------|--------|---------|
| **Rule-based** | Keyword + regex patterns | ~0ms |
| **Embedding** | Cosine similarity to intent centroids (sentence-transformers) | ~50ms |
| **LLM fallback** | Heuristic question-pattern detection | ~100ms |

Security intent is rule-only (never routed via embedding). Intent prototypes are built from representative Chinese + English phrases.

### Workspace Lock

Per-workspace concurrency control:

- Acquire/release lock per agent task
- FIFO queue for concurrent requests on the same workspace
- Prevents write conflicts when multiple tasks target the same codebase

### Security

3-layer defense:

1. **Prompt Injection Detection** -- blocks role-play, instruction override, jailbreak patterns
2. **Tool Guardrail** -- prevents dangerous operations (file deletion, path traversal)
3. **Completion Chain** -- validates claimed fixes were actually executed via tool calls

### Explainability

Every analysis conclusion backed by code evidence:

```
Claim: Bug in subtract function
- File: app/calc.py, Symbol: subtract, Lines: 15-20

Confidence: 85%
```

## Demo

One unified flow: **Upload -> Index -> Agent -> Tool -> Execute -> Evidence -> Result**

| Step | What happens |
|------|-------------|
| 1 | Upload a buggy Python project |
| 2 | Agent auto-builds WorkspaceIndex (file tree + AST summaries) |
| 3 | Click **Bug Fix** -- Agent locates, reads, fixes, tests, verifies |
| 4 | Unified output: Summary + Trace + Tools + Metrics + Evidence + Confidence |

```bash
# Quick start
git clone https://github.com/YANS311/CodePilot-Agent.git
cd CodePilot-Agent
cp .env.example .env    # Add your API key
docker-compose up       # Open http://localhost:8000
```

## Evaluation

Controlled benchmark results on internal test suites:

| Benchmark | Tasks | Scope |
|-----------|------:|-------|
| Synthetic (Easy/Medium/Hard) | 30 | Bug fix / enhancement |
| Real-World (3 repos, seeded bugs) | 15 | Cross-file, hidden bugs |
| Stress Test (multi-file, recovery) | 10 | Complexity boundary |

| Metric | Value | Notes |
|--------|------:|-------|
| Task Success Rate (Synthetic) | 90% | 30 controlled tasks |
| Security Block Rate | 100% | Attack inputs in controlled test set |
| Recovery Rate | Measured | Ability to recover from tool failures |
| Tool Efficiency | Measured | Tool calls per successful task |

> All metrics are controlled evaluation results, not production claims.

## Real Usage Case Studies

Self-tested execution traces documenting how the agent handles real coding tasks — including failures and recovery.

| Case | Task Type | Tool Calls | Key Finding |
|------|-----------|-----------|-------------|
| [Bug Fix (Todo Service)](docs/real_usage_cases.md#case-1-python-bug-fix--todo-service-persistence-bug) | 3-bug fix | 10 | Guardrail caught no-write, forced re-execution |
| [Repo Analysis](docs/real_usage_cases.md#case-2-repository-architecture-analysis) | Architecture | 0 | WorkspaceIndex sufficient, no file reads needed |
| [Wrong File Recovery](docs/real_usage_cases.md#case-3-wrong-file-recovery--fibonacci-error-handling) | Error handling | 9 | SmartFileResolver disambiguated similar files |
| [No-Code-Change Failure](docs/real_usage_cases.md#case-4-agent-no-code-change-failure) | Bug fix (failed) | 7 | Agent analyzed but didn't write; tracked via `wrote_file` |
| [Security Guardrail](docs/real_usage_cases.md#case-5-security-guardrail--prompt-injection) | Injection attack | 0 | Blocked before LLM call, zero tool usage |

> See [docs/real_usage_cases.md](docs/real_usage_cases.md) for full execution traces and system lessons.

## Engineering Notes for Interview

Detailed engineering docs covering Docker operations, failure modes, and operational knowledge grounded in actual code:

| Doc | Focus | Key Topics |
|-----|-------|------------|
| [Engineering Interview Audit](docs/engineering_interview_audit.md) | Docker, Memory/Cache, LLM failures | compose lifecycle, degradation modes, retry logic |
| [Git Interview Notes](docs/git_interview_notes.md) | Git workflow Q&As | merge vs rebase, cherry-pick, revert vs reset |
| [Agent Failure Playbook](docs/agent_failure_playbook.md) | Failure diagnosis steps | no-write detection, wrong file, test failures, timeouts |

## Tech Stack

| Category | Technology |
|----------|-----------|
| Language | Python 3.9+ |
| Backend | FastAPI + Pydantic |
| LLM | OpenAI / DeepSeek compatible API |
| Execution | Local subprocess / Docker sandbox |
| Indexing | Workspace Intelligence (file tree + AST) |
| Memory | sentence-transformers + FAISS (lightweight hybrid) |
| Routing | 3-layer intent classifier (rule + embedding + fallback) |
| Eval | Custom benchmark with 12 advanced metrics |
| Security | Prompt injection + tool guardrail |

## Run Tests

```bash
pytest tests/ -v    # 516 passed, 2 skipped
```

## Keywords

> **Python / FastAPI / LLM / Agent / Tool Calling / Evaluation / Security / ReAct / Memory / Intent Routing / Explainability**

## License

MIT
