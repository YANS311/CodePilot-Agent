# CodePilot Agent

[![CI](https://github.com/YANS311/CodePilot-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/YANS311/CodePilot-Agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python/FastAPI Coding Agent Harness prototype: bounded ReAct execution,
unified tools, context engineering, verification and conservative recovery.
The Harness makes agent execution inspectable and reproducible; MCP connects
capabilities but does not replace orchestration.

**Evidence:** [release benchmark report](docs/harness_benchmark_report.md),
[machine-readable results](benchmarks/results/),
[evaluation protocol](docs/harness_evaluation.md),
[interview brief](docs/interview_project_brief.md).
Real-model effectiveness is **NOT RUN** in this release. Offline simulated
results validate runtime contracts, not general coding performance.

## Architecture

```text
User Task / FastAPI
        |
Coding Agent Harness
|-- Intent Routing
|-- ReAct Orchestration
|-- Context Engineering
|-- Hybrid Memory
|-- Skills / Progressive Disclosure
|-- Tool Budget / Loop Control
|-- Verification / Recovery
|-- Checkpoint / Resume (opt-in)
|-- Permission Policy
|-- Unified Trace / Evaluation
`-- Tool Runtime (ToolRegistry)
    |-- Built-in Tools
    |-- MCP Providers
    `-- Local / Docker Execution
```

## Core Engineering

- **Unified execution:** built-in and external tools share validation, outcomes,
  budgets and permission enforcement. Workspace file tools are guarded.
- **Context and Memory:** task context combines workspace, retrieved experience
  and Skills; deterministic compaction preserves complete tool-call groups.
- **Skills:** metadata routing and progressive disclosure add procedures without
  replacing executable tools.
- **Verification:** explicit post-write test phases and bounded repair retries;
  final benchmark success uses independent pytest, not the agent's claim.
- **Recovery and evidence:** ordered task-owned TraceEvents, checkpoint policy
  checks and rejection of indeterminate side effects rather than silent replay.

Details: [architecture](docs/architecture.md),
[context management](docs/context_management.md),
[TraceEvent contract](docs/trace_event.md).

## Benchmark Evidence

The audited legacy datasets contain **75 tasks**: 30 synthetic coding tasks,
15 authored small repository tasks, 10 stress tasks and 20 security tasks.
[The manifest](benchmarks/manifest.json) records source, seed, target and criterion;
collection results establish target executability, not complete requirement coverage.
The "real_world" fixtures are not external production repositories. Some task
descriptions contain hints; these are not a clean hidden-test benchmark.

The release separates four kinds of evidence:

| Experiment | Interpretation |
|---|---|
| Real-model cumulative ablation | NOT RUN; paid calls need explicit approval |
| Scripted coding controls | Three scenarios, independent pytest, repeated isolated trials |
| Six synthetic context scenarios | Compaction, evidence sentinels and protocol validity only |
| Six checkpoint fault cases | Safe resume and fail-closed rejection, separate from TSR |

The report includes measured overhead and failure cases. Estimated input tokens
use UTF-8 bytes/3, not provider-billed tokens; Pass@1 is not reported without a
valid single-candidate sampling protocol. No real-model benefit is inferred from
scripted responses or compression ratios.

## Quick Start

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Configure provider settings using the existing `.env.example`. Keep credentials
and logs private: current startup logging includes an API-key prefix and requires
hardening before public deployment. CI mode uses deterministic mocks, not a real
model benchmark. Docker and community MCP checks have optional external dependencies.

## Reproducible Evaluation

Use the repository's configured conda environment on this workstation:

```powershell
$env:CODEPILOT_CI_MODE = 'true'
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts/run_harness_benchmark.py --offline --audit-collect --repetitions 2
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts/run_harness_benchmark.py --dry-run --tasks fix-subtract --repetitions 2
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest tests/unit tests/integration -q --tb=short
```

The CLI defaults to offline. Live mode requires explicit task selection and
`--approve-paid`, a configured key and non-CI mode. Dry-run shows call-volume
upper bounds and pricing uncertainty without constructing a model client.
See [the protocol](docs/harness_evaluation.md) for safe setup and interpretation.

Four **cumulative**, not independent, profiles share tools, schemas, seeds,
permissions, budgets and final test criteria:

| Profile | Memory retrieval | Context compaction | Automatic verification |
|---|---|---|---|
| A: ReAct | Off | Guarded pass-through | Off |
| B: +Memory | On | Guarded pass-through | Off |
| C: +Context | On | Existing ContextManager | Off |
| D: Full Harness | On | Existing ContextManager | On |

Each trial has a fresh temporary workspace, model conversation, Memory and trace
sink. Seeded Memory contains a documented general debugging procedure, not test
solutions; cold-start is separately configurable. Normal ablations do not enable
checkpoints. Recorded provenance includes source SHA, model category, configuration,
tool-schema hash, seeds, repetitions and estimated-token semantics.

## Reliability And Safety Boundaries

Memory retrieves experience; Context bounds the next request; Checkpoint stores
resumable state; Trace records execution. They are not interchangeable.
Recovery validates task, workspace and policy and rejects uncertain side effects.
It is single-host, bounded checkpoint recovery, **not exactly-once execution**.

Permission checks remain enabled in all profiles. Local subprocess execution is
not a multi-tenant security sandbox. Docker isolation is optional, not proof of
production security. Prompt-injection protection is incomplete, and approximate
token accounting cannot reproduce provider billing.

## Repository Structure

```text
app/agent/           ReAct, context, verification, checkpoint
app/tools/           Registry, built-in tools, providers
app/memory/          Hybrid Memory
app/evaluation/      Existing evaluator and cumulative benchmark adapter
skills/              Procedural agent Skills
evaluation/          Legacy coding, stress and security tasks
benchmarks/          Audited manifest, repository fixtures, curated release results
tests/               Unit, integration and optional e2e coverage
docs/                Architecture, protocol, measured report, interview brief
workspace/           Reusable workspace seeds
scripts/             Evaluation and development commands
```

## Release Scope

This is an interview-ready engineering prototype, not a production deployment
claim. Real-model efficacy, semantic Memory benefit, broader hidden datasets and
deployment hardening remain unmeasured or incomplete. The offline Memory backend
uses deterministic hash embeddings for reproducibility, not semantic retrieval
validation. Legacy scripts and optional integrations may need separate maintenance.

After this milestone, freeze the job-application release and use the reproducible
report to discuss implementation, trade-offs and limits. Do not automatically add
another framework or feature milestone.

## License

MIT, as declared by the project. A standalone license file is not yet included.
