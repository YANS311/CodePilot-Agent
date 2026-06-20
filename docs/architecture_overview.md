# CodePilot Architecture Overview

> 一张图讲清整个系统，面向面试讲解。

## System Architecture

```
                            ┌─────────────────────┐
                            │       User          │
                            │  "Fix the bug in    │
                            │   calculator.py"    │
                            └──────────┬──────────┘
                                       │
                            ┌──────────▼──────────┐
                            │    FastAPI Layer     │
                            │   POST /api/chat     │
                            │   POST /api/demo     │
                            └──────────┬──────────┘
                                       │
                 ┌─────────────────────┴─────────────────────┐
                 │          Agent Orchestrator                │
                 │                                           │
                 │   ┌─────────────┐    ┌────────────────┐  │
                 │   │ Mode Router │───▶│  ReAct Agent   │  │
                 │   │ (intent)    │    │  Think → Act   │  │
                 │   └──────┬──────┘    │  → Observe     │  │
                 │          │           └───────┬────────┘  │
                 │          ▼                   │           │
                 │   ┌─────────────┐            │           │
                 │   │ Repo        │            │           │
                 │   │ Analyzer    │            │           │
                 │   │ (LLM+AST)  │            │           │
                 │   └─────────────┘            │           │
                 └─────────────────────────────┼───────────┘
                                               │
                 ┌─────────────────────────────┼───────────┐
                 │          Tool Layer          │           │
                 │                             ▼           │
                 │  ┌──────────┬──────────┬──────────┐    │
                 │  │search_   │read_     │write_    │    │
                 │  │code      │file      │file      │    │
                 │  ├──────────┼──────────┼──────────┤    │
                 │  │run_      │git_      │git_      │    │
                 │  │tests     │diff      │status    │    │
                 │  └──────────┴──────────┴──────────┘    │
                 │         ToolRegistry + Guardrail        │
                 └─────────────────────────┬───────────────┘
                                           │
                 ┌─────────────────────────┼───────────────┐
                 │     Execution Layer     │               │
                 │                         ▼               │
                 │  ┌──────────────┐  ┌───────────────┐  │
                 │  │Local Runner  │  │Docker Runner  │  │
                 │  │(subprocess)  │  │(--read-only)  │  │
                 │  └──────────────┘  └───────────────┘  │
                 └─────────────────────────┬───────────────┘
                                           │
                 ┌─────────────────────────┼───────────────┐
                 │    Evaluation Layer     │               │
                 │                         ▼               │
                 │  ┌──────────────────────────────────┐  │
                 │  │  30-task Benchmark               │  │
                 │  │  TSR: 90% | 7 Advanced Metrics   │  │
                 │  │  Error Taxonomy: 7 error types   │  │
                 │  └──────────────────────────────────┘  │
                 └─────────────────────────┬───────────────┘
                                           │
                 ┌─────────────────────────┼───────────────┐
                 │    Security Layer       │               │
                 │                         ▼               │
                 │  ┌──────────────────────────────────┐  │
                 │  │  Prompt Injection Detection      │  │
                 │  │  Tool Guardrail (6 risk types)   │  │
                 │  │  Completion Chain Validation     │  │
                 │  │  Security Block Rate: 100%       │  │
                 │  └──────────────────────────────────┘  │
                 └─────────────────────────┬───────────────┘
                                           │
                 ┌─────────────────────────┼───────────────┐
                 │  Explainability Layer   │               │
                 │                         ▼               │
                 │  ┌──────────────────────────────────┐  │
                 │  │  Evidence Extractor (AST)        │  │
                 │  │  Claim → File → Symbol → Lines   │  │
                 │  │  Confidence Score (0.0~1.0)      │  │
                 │  │  Clickable file references       │  │
                 │  └──────────────────────────────────┘  │
                 └───────────────────────────────────────┘
```

## Layer Responsibilities

| Layer | What it does | Key Components |
|-------|-------------|----------------|
| **FastAPI** | HTTP API + SSE streaming | POST /api/chat, POST /api/demo |
| **Agent Orchestrator** | Intent detection + task execution | Mode Router, ReAct Agent, Repo Analyzer |
| **Tool Layer** | Code operations | 6 tools + ToolRegistry + Guardrail |
| **Execution Layer** | Sandboxed code execution | Local subprocess, Docker --read-only |
| **Evaluation Layer** | Automated benchmarking | 30 tasks, 7 metrics, error taxonomy |
| **Security Layer** | Attack prevention | Prompt injection, tool guardrail, completion chain |
| **Explainability Layer** | Evidence-backed output | EvidenceExtractor, confidence scoring |

## Data Flow

```
User Task
  → Mode Router (intent detection)
    → REACT_MODE: ReAct Agent → Tool Calls → Execution → Verify
    → REPO_MODE: RepoAnalyzer → EvidenceExtractor → LLM Analysis
  → Output: answer + evidence + confidence
```

## Key Design Decisions

1. **Mode Router**: Keyword-based intent detection splits code tasks from project analysis
2. **ReAct Loop**: Think → Act → Observe, bounded by ToolBudget (max 5 calls)
3. **Workspace Intelligence**: File tree + summaries injected into agent context
4. **Evidence Extraction**: AST parsing provides ground-truth code locations
5. **Confidence Scoring**: Evidence coverage + file coverage + density → 0.0~1.0
6. **Security Guardrails**: 6 risk types detected before tool execution
