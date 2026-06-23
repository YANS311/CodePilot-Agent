# Release v0.4.0 — Memory & Routing Enhanced Coding Agent

**Date:** 2026-06-23
**Tag:** v0.4.0

## What's New

### D32 — Agent Memory Layer

- **Short-term memory**: ReAct execution trace, tool history, and current task context
- **Structured long-term memory**: Task memory (what was done), error memory (what failed), repo knowledge (codebase facts)
- Memory context injection: prior task/error memories are injected into agent prompts
- Memory API endpoints: `GET /api/memory`, `GET /api/memory/query`, `GET /api/memory/search`

### D33 — Hybrid Memory & Intent Router

**Hybrid Memory System:**
- Vector memory store using FAISS IndexFlatIP with brute-force cosine fallback
- Sentence-transformers (all-MiniLM-L6-v2) for 384-dim embeddings
- Dual-write: every memory add writes to both structured (keyword) and vector stores
- Merged context retrieval combining keyword matching + semantic similarity

**3-Layer Intent Router:**
- Layer 1: Rule-based (keyword + regex) — fast path, ~0ms
- Layer 2: Embedding-based (cosine similarity to intent centroids) — ~50ms
- Layer 3: LLM fallback heuristic — for ambiguous inputs
- Security intent is rule-only (excluded from embedding classification)
- Intent prototypes built from representative Chinese + English phrases
- Routing statistics tracking (layer distribution, intent counts)

**Workspace Lock:**
- Per-workspace asyncio.Lock with FIFO queue
- Concurrent request queuing for same-workspace tasks
- Prevents write conflicts during parallel agent execution

### Evaluation Updates

- 12 advanced metrics including routing metrics (accuracy, fallback rate, layer distribution)
- Memory metrics: memory_hit_rate, memory_utilization_effect, similar_task_recall
- Real-world benchmark repos: calculator_pkg, config_parser, todo_api
- Stress evaluation tasks and runners

### Output Unification (D23)

- `AgentFinalOutput` schema: unified output from all agent modes
- `StepTrace` and `OutputMetrics` dataclasses
- `format_output()` formatter converts any mode result to unified format
- API response now includes `mode`, `metrics`, `execution_trace`, `tools_used`

## Test Status

```
516 passed, 2 skipped
```

## Upgrade Notes

- No breaking API changes — existing endpoints continue to work
- New fields added to `ChatResponse`: `mode`, `metrics`, `execution_trace`, `tools_used`
- Memory API is new (`/api/memory/*`)
- Intent router replaces old `_detect_mode()` keyword matching

## Commits Included

- `6ad076b` feat: D33 — Hybrid Memory & Intent Router
- `aa5fe63` feat: D32 — Agent Memory Layer
- Plus D23 output unification and evaluation enhancements
