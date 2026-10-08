# Debugging Workflow

Use this reference as the detailed operating procedure for bug fixes and fault diagnosis in CodePilot Agent, a FastAPI-based ReAct coding-agent prototype.

## Phase 1: Understand the problem

### Capture the evidence

Collect the most precise evidence available:

- full exception type, message, traceback, HTTP status, and response body;
- failing test node ID and assertion output;
- request method, route, headers, parameters, and sanitized body;
- relevant logs and the first meaningful failure rather than only the final wrapper error;
- runtime conditions such as Python version, CI mode, Docker availability, or optional dependencies.

Never invent missing error text. When reproduction is possible, reproduce the issue with the smallest relevant command or request. When reproduction is not possible, state which evidence supports the diagnosis and what remains assumed.

### Define expected behavior

Turn the report into an observable comparison:

- actual behavior;
- expected behavior;
- smallest input or state that triggers the difference;
- whether the behavior is a regression;
- explicit acceptance criteria for the fix.

Check nearby tests, route schemas, tool contracts, and documentation for the strongest available definition of expected behavior. Resolve contradictions before editing when they materially change the fix.

## Phase 2: Analyze the code

### Search before reading broadly

Use `rg` or `rg --files` to search for:

- exception text and log fragments;
- route names, status codes, schema fields, function names, and test names;
- call sites of the suspected function;
- fixtures, mocks, dependency overrides, and configuration variables.

Start at the failure boundary and trace both directions: backward to the input or state that caused it, and forward to callers or consumers affected by a change.

### Read complete local context

Read the whole function or class, its direct callers, relevant tests, and shared contracts. For this repository, preserve these architectural boundaries unless evidence proves they are the defect:

- the ReAct loop under `app/agent/`;
- `BaseTool`, `ToolRegistry`, and guarded workspace tools under `app/tools/`;
- evaluation behavior under `app/evaluation/`;
- reusable seed content under `workspace/`.

Do not patch only the line named in a traceback without understanding validation, cleanup, retries, error translation, and async boundaries around it.

### Form and test a hypothesis

Write a short internal hypothesis that connects cause to symptom. Prefer evidence that can disprove it: a focused test, a minimal reproduction, a call-site search, or a comparison with the expected contract.

Map the likely impact scope:

- direct code path;
- public API or tool contract;
- persistence or filesystem side effects;
- callers and downstream consumers;
- unit, integration, replay, or end-to-end tests that cover the behavior.

If the hypothesis fails, return to the evidence rather than accumulating speculative edits.

## Phase 3: Fix

Choose the smallest change that corrects the cause rather than concealing the symptom.

- Preserve public behavior outside the acceptance criteria.
- Avoid unrelated renaming, formatting, dependency upgrades, and architecture changes.
- Add or update a small behavior-focused test when practical, especially for regressions.
- Keep exception handling narrow. Do not catch broad exceptions merely to make a test pass.
- Preserve guarded workspace access and the existing ReAct verification flow.
- Handle async resources, temporary state, and cleanup on both success and failure paths.

Before editing, check `git status --short`. Treat existing modifications as user-owned and avoid overlapping them. If overlap is unavoidable and the intended result is ambiguous, stop and ask for direction.

## Phase 4: Verify

### Run the narrowest relevant check

Use the repository conda interpreter:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest -p no:cacheprovider tests\unit\test_name.py -q
```

Replace the example path with the affected test file or node ID. After editing Python under `workspace/examples` or `workspace/tests`, run its specific test or `py_compile` on each changed Python file.

For known evaluation failures, replay the applicable task:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe scripts\replay_task.py <task-id>
```

Common replay IDs include `fix-retry-request`, `fix-append-line`, and `fix-file-processor-all`.

### Widen according to risk

When the focused check passes and the change can affect shared behavior, run the CI-equivalent suite:

```powershell
C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest tests\unit tests\integration -q --tb=short
```

CI uses Python 3.11 with `CODEPILOT_CI_MODE=true`. Use that mode when reproducing a CI-only difference.

### Analyze failures

For every failure, identify whether it is:

1. caused by the proposed change;
2. evidence that the hypothesis or impact analysis was incomplete;
3. pre-existing and reproducible without the change;
4. an environment limitation, such as a missing optional LLM key, embedding model, Docker daemon, or local-only documentation.

Fix categories 1 and 2 within scope, then rerun the narrowest failing check. Report categories 3 and 4 with evidence; do not relabel them as passing.

### Inspect the final change

Run:

```powershell
git diff --check
git diff
git status --short
```

Confirm that the diff contains only intended changes, no secrets or generated noise, and no accidental edits to unrelated user files. Timestamped benchmark reports under `benchmarks/real_world/reports/eval_*.json` and `eval_*.md` are runtime artifacts and should remain ignored. Curated replay artifacts under `reports/replays/` may be kept only when they intentionally document the recovery path.

## Phase 5: Summarize

Report results in this order:

1. **Root cause**: connect the defect to the observed behavior.
2. **Changed files**: list each file and the behavioral purpose of its change.
3. **Tests**: list exact commands and results, including failure or skip counts and environment limitations.
4. **Follow-up**: note remaining risk, broader verification, or operational action; write `None` if there is nothing actionable.

Keep the summary proportional to the change. Include enough evidence for another engineer to reproduce the diagnosis and verification without narrating every exploratory step.
