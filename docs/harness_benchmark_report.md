# Harness Benchmark Release Report

Generated from committed machine-readable artifacts. Scripted-model results are **SIMULATED**, not real Agent/model task performance.

## Provenance

```json
{
  "executed_at_utc": "2026-10-08T10:26:15.948875+00:00",
  "git_sha": "eeb99a8c47990f204cd3ad21eb7059f5893d96be",
  "tracked_worktree_dirty": false,
  "benchmark_source_sha256": "ca27ab743bd3fb0985f850536a56394f969363bdd52bd770c65d292c88edab0a",
  "python": "3.11.15",
  "platform": "Windows",
  "mode": "offline",
  "model": "ScriptedLLM-v1",
  "provider_category": "offline scripted",
  "temperature": 0.0,
  "config": {
    "repetitions": 2,
    "order_seed": 17,
    "max_tool_calls": 8,
    "task_timeout_seconds": 120,
    "memory_state": "seeded"
  },
  "estimated_tokens": "UTF-8 bytes / 3 rounded up; not billed tokens",
  "context_budget": {
    "max_input_tokens": 32768,
    "reserve_output_tokens": 4096,
    "system_budget": 4096,
    "workspace_budget": 3072,
    "memory_budget": 3072,
    "skill_budget": 4096,
    "history_budget": 16384,
    "tool_observation_budget": 250,
    "recent_message_count": 6
  },
  "generation_max_output_tokens": null,
  "verification_max_retries": 1,
  "independent_pytest_runner": "LocalExecutionRunner (30s subprocess ceiling)",
  "checkpoint_in_normal_ablations": false,
  "memory_backend": "isolated HybridMemoryManager structured + deterministic hash vectors",
  "profiles": [
    {
      "id": "A",
      "name": "ReAct baseline",
      "memory": false,
      "context": false,
      "verification": false
    },
    {
      "id": "B",
      "name": "ReAct + Memory",
      "memory": true,
      "context": false,
      "verification": false
    },
    {
      "id": "C",
      "name": "ReAct + Memory + Context",
      "memory": true,
      "context": true,
      "verification": false
    },
    {
      "id": "D",
      "name": "Full Harness",
      "memory": true,
      "context": true,
      "verification": true
    }
  ],
  "tools_sha256": "925a9d4f4f41ca8bc289c3f06e85e02b67155263ca8886b3bd714730c10bf412"
}
```

Latency includes the Agent, independent final pytest and workspace cleanup; excludes seed preparation and Memory seeding. It is environment-dependent wall time, not an isolated causal overhead estimate.

## Dataset Audit

| Source | Tasks |
|---|---:|
| evaluation/tasks.json | 30 |
| evaluation/stress_tasks.json | 10 |
| benchmarks/real_world/tasks.json | 15 |
| evaluation/security_tasks.json | 20 |

Missing structural test targets: none.
Collection outcomes are in `benchmarks/manifest.json`; collection checks executability, not full prose-criterion coverage.
The 15 repository tasks are authored seeded fixtures across three small repositories, not external production repositories. Existing task descriptions/hints are not a clean hidden-test benchmark; difficulty is unchanged.

## Profiles

Cumulative profiles, not independent factorial effects. Skills, core tools, schemas, runtime guardrails, permissions, generation settings, tasks and budgets are held constant.

| Profile | Historical Memory | Context | Automatic Verification |
|---|---|---|---|
| A: ReAct baseline | False | pass-through with same hard ceiling | False |
| B: ReAct + Memory | True | pass-through with same hard ceiling | False |
| C: ReAct + Memory + Context | True | budgeted compaction | False |
| D: Full Harness | True | budgeted compaction | True |

Memory is cold or seeded explicitly per trial. The permitted seed is general arithmetic debugging procedure, not a held-out patch or test solution. Retrieval uses existing structured Memory plus fixed hash vectors, not learned semantic embeddings. No global task Memory is used.
Checkpoint is off in these profiles and only enabled in separate recovery trials. No paid benchmarking was started automatically.

## Real Model Task Performance

| Profile | Status | Trials | Fixture success / TSR | Tools mean | LLM requests mean | Total estimated input tokens mean | Latency ms mean |
|---|---|---:|---:|---:|---:|---:|---:|
| A | NOT RUN | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A |
| B | NOT RUN | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A |
| C | NOT RUN | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A |
| D | NOT RUN | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A | NOT RUN / N/A |

## Simulated Runtime Regression

| Profile | Status | Trials | Fixture success / TSR | Tools mean | LLM requests mean | Total estimated input tokens mean | Latency ms mean |
|---|---|---:|---:|---:|---:|---:|---:|
| A | SIMULATED | 6 | 0.333 | 2 | 3 | 38510.667 | 884.839 |
| B | SIMULATED | 6 | 0.333 | 2 | 3 | 38791.667 | 886.644 |
| C | SIMULATED | 6 | 0.333 | 2 | 3 | 13263.667 | 890.876 |
| D | SIMULATED | 6 | 0.667 | 4.333 | 4.333 | 20036.667 | 2240.132 |

Real-model Memory/context/verification effectiveness is **NOT RUN** unless the real-model section contains authorized measured trials. Simulated fixtures do not establish model improvement. Pass@1 is N/A: this protocol has iterative edits/recovery, not independent one-candidate sampling.

## Verification Comparison (SIMULATED)

Independent identical pytest is the success criterion for every profile. The scripted client deliberately exercises correct-first-edit, failed-then-repair, and unrecoverable branches.

| Profile | Task | Independent success | Automatic test attempts | Recovered failure | Verification tool latency ms |
|---|---|---|---:|---|---:|
| D | recoverable (rep 1) | True | 2 | True | 1687.495 |
| C | unrecoverable (rep 1) | False | 0 | False | 0.000 |
| C | first-pass (rep 0) | True | 0 | False | 0.000 |
| C | unrecoverable (rep 0) | False | 0 | False | 0.000 |
| D | recoverable (rep 0) | True | 2 | True | 1669.160 |
| C | recoverable (rep 1) | False | 0 | False | 0.000 |
| D | unrecoverable (rep 1) | False | 2 | False | 1700.925 |
| C | recoverable (rep 0) | False | 0 | False | 0.000 |
| D | first-pass (rep 1) | True | 1 | False | 784.753 |
| C | first-pass (rep 1) | True | 0 | False | 0.000 |
| D | first-pass (rep 0) | True | 1 | False | 781.141 |
| D | unrecoverable (rep 0) | False | 2 | False | 1751.625 |

Verification adds tool/model calls and wall time. The first-pass fixture needs no repair; the unrecoverable fixture remains incorrect despite extra verification. Recovery of the scripted repair fixture is contract evidence, not a measured LLM success gain.

## Deterministic Context Stress

| Scenario | Compaction | Status | Before estimates | After estimates | Retained ratio | Head / tail evidence | Protocol |
|---|---|---|---:|---:|---:|---|---|
| long_read | False | MEASURED | 8140 | 8140 | 1.000 | True / True | True |
| long_read | True | MEASURED | 8140 | 319 | 0.039 | True / True | True |
| pytest_failure | False | MEASURED | 8153 | 8153 | 1.000 | True / True | True |
| pytest_failure | True | MEASURED | 8153 | 319 | 0.039 | True / True | True |
| repeated_search | False | CONTEXT_BUDGET_FAILURE | 24315 | NOT RUN / N/A | NOT RUN / N/A | None / None | True |
| repeated_search | True | MEASURED | 24315 | 852 | 0.035 | True / True | True |
| old_observations | False | CONTEXT_BUDGET_FAILURE | 56660 | NOT RUN / N/A | NOT RUN / N/A | None / None | True |
| old_observations | True | MEASURED | 56660 | 1913 | 0.034 | True / True | True |
| multi_tool | False | CONTEXT_BUDGET_FAILURE | 16202 | NOT RUN / N/A | NOT RUN / N/A | None / None | True |
| multi_tool | True | MEASURED | 16202 | 560 | 0.035 | True / True | True |
| near_limit | False | MEASURED | 10962 | 10962 | 1.000 | True / True | True |
| near_limit | True | MEASURED | 10962 | 319 | 0.029 | True / True | True |

These are UTF-8 bytes/3 input estimates, not provider billing tokens. Local tokens saved by compaction are not summed hypothetical billing savings; total task estimates sum actual logical LLM invocations. A shorter prompt can lead to more requests. Provider usage, when supplied, is separate in trial JSON; client HTTP retries are not counted as new logical requests. Head/tail sentinels measure specific retained evidence, not semantic sufficiency for a model.

## Checkpoint Fault Injection

| Scenario | Outcome | Assertions |
|---|---|---|
| safe_read | PASS | {"budget_preserved": true, "completed": true, "context_preserved": true, "new_runtime": true, "no_replay": true, "trace_integrity": true} |
| indeterminate_write | PASS | {"indeterminate": true, "new_runtime": true, "no_new_effect": true, "recovery_event": true, "rejected": true, "trace_integrity": true} |
| verification_progress | PASS | {"completed": true, "correct_retry": true, "new_runtime": true, "no_duplicate_attempt": true, "trace_integrity": true} |
| workspace_changed | PASS | {"new_runtime": true, "no_new_effect": true, "rejected": true, "trace_integrity": true} |
| corrupt_snapshot | PASS | {"new_runtime": true, "no_new_effect": true, "rejected": true, "trace_integrity": true} |
| policy_changed | PASS | {"new_runtime": true, "no_new_effect": true, "rejected": true, "trace_integrity": true} |

Real file/test tools with scripted LLMs and new runtime objects; safe resumes preserve budget/context, uncertain writes refuse replay, completed verification is not repeated, changed workspaces/corrupt state/policy mismatch reject. Reliability is separate from normal TSR. No exactly-once guarantee.

## Reproduce

```bash
python scripts/run_harness_benchmark.py --offline --repetitions 2
python scripts/run_harness_benchmark.py --dry-run --tasks fix-subtract --repetitions 2
```

Live execution requires explicit `--live --approve-paid` after inspecting the dry-run plan and provider configuration. This release has not authorized or run it.

## Release Decision And Limits

Freeze the job-application release after this PR. No next feature milestone is scheduled.
Single-host recovery, heuristic injection checks, bounded deterministic context, trusted test/MCP executors and non-transactional Memory publication remain limitations. Local subprocesses are not a multi-tenant security sandbox; arbitrary executors need OS/container isolation. No production rollout, business impact, billing reduction or general model improvement is claimed.
