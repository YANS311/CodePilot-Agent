# Interview Project Brief

## 30-second introduction

CodePilot Agent is a Python/FastAPI coding-agent prototype. I built a Harness
around a ReAct loop to make tool execution bounded, observable and independently
verifiable: unified tools and MCP providers, permissions, context compaction,
Memory, procedural Skills, verification retries and conservative checkpoint recovery.
The release includes reproducible offline experiments; real-model effectiveness
has not been measured in this release.

## Two-minute architecture

Intent routing selects the runtime. Skills provide task procedures, not executable
capabilities. Context assembly combines core instructions, workspace information,
retrieved Memory and selected Skills. The ReAct runtime prepares protocol-valid
messages within a configured estimated-token ceiling, then delegates validated
calls to the ToolRegistry. Permissions and workspace boundaries remain enabled.
Local or Docker runners execute tests. Automatic verification can repair a failing
patch within an explicit retry budget.

TraceEvents retain task identity, ordering, tool outcomes and lifecycle metadata.
EvaluationRunner derives execution metrics from those events and checks final
correctness with independent pytest runs. Checkpoints persist durable execution
state; a new runtime can resume safe completed exchanges. Uncertain writes fail
closed instead of being silently repeated. These are separate responsibilities,
not an assertion of production isolation or exactly-once execution.

## Five technical questions

1. **Why a Harness instead of a simple ReAct loop?** A loop chooses actions;
   the Harness controls budgets, permissions, verification, context and evidence.
   Agent claims are not evaluation criteria.
2. **Memory vs Context vs Checkpoint vs Trace?** Memory retrieves prior experience;
   Context bounds the next model input; Checkpoint stores resumable state;
   Trace records what happened. None substitutes for another.
3. **How is tool-call protocol integrity preserved?** Assistant calls and matching
   observations form complete groups. Compaction and resume validate those groups;
   evaluation rejects mismatched task ownership and non-increasing step IDs.
4. **How do you recover after a write?** Persist an in-flight marker before execution.
   If an operation may have occurred without a durable outcome, reject automatic
   replay and emit recovery-required evidence. External workspace or policy changes
   also invalidate resume. This does not guarantee exactly-once effects.
5. **How do you evaluate Context?** Hold tasks, model settings, tools, budgets,
   permissions and final pytest criteria constant across cumulative profiles.
   Measure per-call and total estimated input tokens, tool calls, latency and success.
   Synthetic compaction proves deterministic behavior, not model effectiveness.

## Three trade-offs

- Deterministic compaction is explainable and inexpensive, but can lose semantic
  evidence. UTF-8 bytes/3 is an estimate, not a provider tokenizer or invoice.
- Verification catches controlled bad patches but adds subprocess latency and
  tool calls; bounded retries cannot guarantee repair.
- Conservative checkpoint rejection prevents uncertain replay but sacrifices
  automatic recovery when effects or workspace identity cannot be established.

## Key reproducible experiment

```powershell
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts/run_harness_benchmark.py --offline --audit-collect --repetitions 2
```

Inspect [the generated report](harness_benchmark_report.md), JSON/CSV provenance
and the verification OFF/ON comparison. Scripted responses deliberately include
correct-first, recoverable and unrepairable patches; independent pytest decides
correctness. This demonstrates control-flow contracts, not general coding ability.

## Limitations and future improvements

The datasets are authored fixtures, not hidden production-repository benchmarks;
some legacy prompts expose hints and some tests cover only part of the prose.
The offline Memory embedding is deterministic hash-based, not semantic retrieval
evidence. Real-model repeated trials require separate cost approval. Local processes
are not a tenant security sandbox. Recovery is single-host and bounded, with no
distributed guarantees. Prompt-injection resistance is not complete. Existing
startup logs expose a key prefix and need hardening before public deployment.
Future work should validate semantic evidence retention and harden deployment
boundaries after freezing this interview release, not expand the framework now.

## Resume-ready summary

Implemented a Python/FastAPI Coding Agent Harness with unified local/MCP tools,
permission checks, deterministic context budgeting, procedural Skills, Memory,
trace-driven evaluation, bounded test verification and fail-closed checkpoint
recovery. Built cumulative ablation tooling, isolated workspace/Memory trials,
independent pytest criteria and reproducible JSON/CSV reports with source provenance;
validated offline control-flow and recovery behavior without claiming unmeasured
real-model gains.
