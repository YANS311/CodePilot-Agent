# Failure Patterns

Use this catalog to accelerate hypothesis formation. A pattern is a search guide, not proof. Confirm it against the actual traceback, inputs, contracts, and tests before editing.

## FastAPI request and response failures

### 422 validation errors

Likely causes:

- path, query, or body fields do not match the declared Pydantic model;
- aliases or nested payload shapes differ between client and schema;
- a dependency expects a required header or parameter;
- a validator rejects a value before route logic executes.

Inspect the response `detail`, route signature, request model, aliases, validators, and test payload. Fix the incorrect contract owner; do not weaken validation simply to accept one failing example.

### Unexpected 500 responses

Likely causes:

- an internal exception crosses the route boundary untranslated;
- sync code blocks or fails inside an async path;
- a dependency, database session, or resource is not cleaned up;
- code assumes optional configuration is present;
- response serialization fails after route logic succeeds.

Trace the first internal exception. Check exception chaining and logging, then verify the intended mapping to an HTTP status and safe response body. Do not expose secrets or raw internal errors to clients.

### Response validation errors

Likely causes:

- returned data omits a required response-model field;
- an ORM object is used without compatible model configuration;
- runtime types do not match unions, enums, or nested schemas;
- an error branch returns a shape different from the successful branch.

Compare every return path with the declared response model and its serialization configuration.

## Async and resource lifecycle failures

### Coroutine or event-loop errors

Typical signals include an un-awaited coroutine warning, `asyncio.run()` inside a running loop, or a resource bound to another loop.

Inspect async boundaries, fixtures, client usage, and lifecycle hooks. Await async work at the owning boundary and avoid converting async behavior to sync as a shortcut.

### Leaked or closed resources

Typical signals include unclosed client/session warnings, use-after-close errors, exhausted pools, or failures only after several tests.

Inspect dependency generators, context managers, shutdown hooks, and failure-path cleanup. Verify cleanup with a test that exercises the exceptional path when practical.

## Dependency injection and configuration

### Dependency override leaks

Symptoms include tests that pass alone but fail in a suite, unexpected authentication state, or stale mocked services.

Inspect `dependency_overrides`, fixture scopes, teardown behavior, and mutable globals. Ensure overrides are removed even when a test fails.

### Missing or mismatched settings

Symptoms include import-time crashes, missing keys, wrong environment-dependent behavior, or CI-only failures.

Inspect settings defaults, environment variable names, `.env` loading boundaries, and CI flags. Do not commit real secrets. Distinguish required production configuration from optional local integrations.

## Test failures

### Passes locally, fails in CI

Compare Python versions, `CODEPILOT_CI_MODE`, dependency locks, path separators, filesystem case sensitivity, locale, time zone, and test order. Remove hidden environmental assumptions rather than special-casing CI without evidence.

### Flaky or order-dependent tests

Look for shared globals, non-unique temporary paths, dependency overrides, cached settings, nondeterministic ordering, time dependence, random seeds, ports, and background tasks. Re-run the exact node repeatedly and in both relevant orders before calling it flaky.

### Mock assertion mismatch

Determine whether the production contract changed, the mock is at the wrong import boundary, or the assertion over-specifies implementation details. Prefer assertions on observable behavior while retaining precise contract checks where interaction itself is the behavior.

### Snapshot or serialization differences

Check stable ordering, timezone and datetime formatting, enum conversion, excluded `None` values, and Pydantic-version behavior. Normalize only fields that are contractually nondeterministic.

## Agent and tool execution failures

### ReAct loop stops or retries incorrectly

Inspect termination conditions, attempt counters, tool-result classification, verification transitions, and exception propagation in `app/agent/`. Replay a known task when the failure matches a curated evaluation scenario.

### Tool registry or dispatch errors

Inspect tool name normalization, registration timing, schema generation, argument validation, and `BaseTool` contracts in `app/tools/`. Search all callers before changing a tool signature.

### Workspace access failures

Inspect path resolution, traversal guards, allowed roots, encoding, and cleanup. Do not weaken guarded workspace protections to make a failing path work. Add cases for absolute paths, `..`, symlinks or junctions when relevant, and Windows separators.

### Evaluation mismatch

Inspect evaluator inputs, normalization, expected artifacts, and replay output under `app/evaluation/` and `reports/replays/`. Separate a real agent regression from a stale expectation or generated benchmark noise.

## Data and state failures

### Transaction or persistence errors

Look for missing commits or rollbacks, session scope errors, uniqueness races, stale objects, and partial writes. Verify both successful persistence and rollback after the failing operation.

### Cache or stale-state errors

Look for missing invalidation, keys that omit tenant or version dimensions, mutable cached values, and tests that reuse process state. Confirm the cache key and ownership before adding broad cache clearing.

## When no pattern fits

Return to the smallest reproducible input and trace the first divergence from expected behavior. Add instrumentation only when existing logs and tests cannot reveal the boundary, keep it free of sensitive data, and remove temporary diagnostics before completing the fix unless they provide lasting operational value.
