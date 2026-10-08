# Reproducible Harness Evaluation

This is an evaluation/release adapter around `ReActAgent`, `EvaluationRunner`,
`compute_metrics`, normalized TraceEvent, existing ContextManager and CheckpointManager.
It is not a new orchestration or Memory framework.

## Comparable Profiles

| Profile | Historical retrieval | Context policy | Automatic verification |
|---|---|---|---|
| A | off | pass-through, hard input ceiling | off |
| B | on | pass-through, hard input ceiling | off |
| C | on | existing budgeted deterministic compaction | off |
| D | on | existing budgeted deterministic compaction | on, at most one repair retry |

These profiles are cumulative, not a factorial study. Intent routing, Skills,
mandatory safety prompts, workspace guards, standard coding permissions, seven
built-in tools/schemas, temperature 0, max tool calls and task timeout are constant.
Checkpoint is off outside dedicated fault-injection experiments. Pass-through does
not disable protocol checking or input safeguards; it refuses oversized prompts.

Each task/profile/repetition receives a fresh temporary workspace, registry, model
client and HybridMemoryManager. Live seeds contain only versioned files, excluding
untracked uploads/cached results. No singleton task Memory is read/written. Fixed
hash vector embeddings keep the Memory contract experiment deterministic; these
are not learned semantic retrieval effectiveness results. Skills may cache fixed
instructions, but no model answers are cached. Order is shuffled using the recorded
seed, not inference determinism. Provider version/temperature can still introduce
stochasticity; use repeated trials and inspect variation.

## Memory Setup

`--memory-state cold` starts with zero records. `--memory-state seeded` starts with
one permitted general prior procedure: inspect arithmetic operators/boundaries,
reproduce failures, edit source rather than tests, and run the requested target.
It contains no patch, function solution, held-out assertions or copied current-task
answer. Every variant receives an independently created store; A never retrieves
the prior. Trial fields record actual retrieval calls/context hits, not the legacy
post-task `memory_utilized` heuristic. Current-run publications cannot leak into
the next trial. General arithmetic prior knowledge may be irrelevant to other
categories; interpret Memory results by task relevance, not global improvement.

## Dataset Audit

The manifest is generated from current JSON sources and validated via AST target
checks and optional actual pytest collection. Difficulty is preserved. Collections
check importability/node selection, not complete prose success criteria. Some stress
tasks describe multiple defects while their target checks a subset; report this
criterion-coverage limitation. The `real_world` folder holds three authored small
seed repositories, not external production projects. Existing descriptions/hints
sometimes expose the intended repair; this is not a clean held-out capability test.

The older `run_realworld_eval.py` references nonexistent `ReactAgent` and `app.config`.
Do not use its invocation path as release evidence. The new adapter turns audited
entries into EvalTask and uses the current EvaluationRunner without those imports.
Historical reports remain historical, not refreshed model-performance claims.

## Commands

```powershell
$env:PYTHONUTF8='1'
$env:CODEPILOT_CI_MODE='true'
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts/run_harness_benchmark.py --offline --audit-collect --repetitions 2
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts/run_harness_benchmark.py --dry-run --tasks fix-subtract --repetitions 2
```

Offline is the default even without `--offline`; it constructs no LLM API client.
The report separates scripted-model fixtures, synthetic compression, recovery
correctness and real-model performance. Real-model rows are NOT RUN with null
measurements when unexecuted, not zero-valued synthetic performance. Generated
release artifacts are deliberately curated under `benchmarks/results/`; ephemeral
workspaces/checkpoints are temporary and never committed.

The dry run prints task/profile/repetition counts, model identifier, credential
presence (never the key), an upper estimate of logical requests/HTTP attempts and
unknown cost. It does not call an API. An upper estimate is not an expected bill.
Only after separately approving a paid experiment:

```bash
CODEPILOT_CI_MODE=false python scripts/run_harness_benchmark.py --live --approve-paid --tasks fix-subtract --repetitions 2
```

API key/model/base URL use existing `CODEPILOT_LLM_*` settings. Live mode rejects
missing keys and CI mock mode. Endpoint URLs/headers/keys are not persisted. This
release did not authorize paid execution. The CLI approval gate is a human workflow
boundary, not an authorization mechanism for arbitrary hostile callers.

## Metrics And Interpretations

The final identical independent pytest target determines correctness, never the
Agent answer or the presence of verification. Tool counts use only `tool_call`
events. Verification events require explicit phase metadata; resume is not a retry.
Successful edit events plus a net seed/disk difference identify modified files.
Ownership/order violations reject metric extraction. `compute_metrics` supplies
task success/failure aggregation; new trace-derived fields record logical model
invocations, read/search exact-argument duplicates, verification attempts/recovery,
terminal status counts, context-budget failures and input estimates.

`llm_request` is a logical client invocation, not a count of HTTP retries or proof
of provider billing. `llm_response` includes only allowlisted nonnegative integer
usage fields and duration, not responses or credentials. Estimates use the existing
UTF-8 bytes/3 estimator, including message/tool-schema wire fields. Per-call values
and total actual-call estimates are separate from local compaction savings and
retained ratios. Retained sentinels do not prove semantic adequacy for a model.
Available provider usage is reported separately; incomplete usage remains null.

Pass@1 is N/A: iterative edit/recovery runs are not independent single-candidate
sampling. Repetitions support task-level variation; JSON includes wall-time mean
and population standard deviation. Current small samples do not establish statistical
significance or generalization. No price lookup or billing reduction is inferred.

End-to-end task latency includes Agent execution, independent pytest and workspace
cleanup, but excludes seed preparation and initial Memory seeding. Agent latency,
verification tool latency, Memory retrieval latency and request counts are separate.
Context stress records transformation wall time. These are observed costs, not a
controlled estimate of each component's causal overhead; subprocess startup and
host load can dominate.

## Fault Injection And Safety

Six separate scenarios cover safe-read resume, indeterminate write refusal,
verification progress, workspace edits, corrupt JSON and changed budget policy.
They use scripted models, real file/test tools, fresh stores and new runtime objects.
They are reliability experiments, not normal TSR and not exactly-once guarantees.
Existing checkpoint tests additionally cover cancelled/failed tasks, storage locks,
atomic-save failure, terminal replay and trace cursor crash windows.

Benchmarks run trusted authored code locally. Local subprocess execution is not an
arbitrary-code sandbox; production/untrusted pytest or MCP tools require OS/container
isolation and protected checkpoint ACLs. Existing optional community MCP integration
tests may need cached npx packages/network; the new benchmark/tests never connect to
MCP servers or model APIs. Run full repository CI-equivalent checks with the project's
conda environment and interpret optional-dependency skips explicitly.
