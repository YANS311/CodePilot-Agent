# Trace metrics (Go learning exercise)

A stateless, read-only HTTP service using only Go's standard library. The schema
is a projection of `app/agent/trace.py:TraceEvent` (version 0.1), and aggregation
matches six fields from `app/evaluation/harness_metrics.py:task_metrics`.
FastAPI, ReActAgent, Memory, ContextManager, Checkpoint, EvaluationRunner and
evaluation correctness criteria remain in Python. The service never runs tools
or commands, writes traces, or logs request content.

## Run locally

Requires Go 1.22 or newer; tested with portable Go 1.27.1. No external Go modules.
From the repository root:

```sh
cd services/trace-metrics-go
go test ./...
go vet ./...
go run .
```

Default address: `127.0.0.1:8091`. An explicit `-addr 127.0.0.1:8092` overrides
it. The optional Python adapter uses the default port.

PowerShell commands for the portable toolchain used during implementation:

```powershell
Set-Location D:\Users\A\PycharmProjects\FastAPIProject2\services\trace-metrics-go
$goExe = Join-Path $env:TEMP 'codepilot-trace-metrics-go/go/bin/go.exe'
$env:GOTOOLCHAIN = 'local'
& $goExe test ./...
& $goExe vet ./...
& $goExe run .
```

## HTTP contract and curl example

`GET /health` returns `200 {"status":"ok"}`.

`POST /v1/trace/summary` accepts one JSON object with a nonblank `task_id` and an
`events` array of normalized TraceEvent objects. Every event must have matching
`task_id`, integer `step_id`, nonempty `agent_action`, string `execution_result`,
and object `metadata`. `tool_name` may be null or absent. Other normalized fields
such as timestamps and tool inputs/outputs are accepted but ignored.

Step IDs must be strictly increasing, with gaps allowed. Like the existing
Python ownership/order validator, the service does not impose an initial step
value. Ownership here means consistency with the request, not authentication.

```sh
curl -sS http://127.0.0.1:8091/v1/trace/summary \
  -H 'Content-Type: application/json' \
  --data '{"task_id":"demo","events":[{"task_id":"demo","step_id":1,"agent_action":"llm_request","execution_result":"started","metadata":{"estimated_input_tokens":120}},{"task_id":"demo","step_id":2,"agent_action":"tool_call","tool_name":"run_tests","execution_result":"success","metadata":{"phase":"verification"}},{"task_id":"demo","step_id":3,"agent_action":"task_complete","execution_result":"completed","metadata":{}}]}'
```

On Windows use `curl.exe` (PowerShell's `curl` may be an alias). To avoid shell
quoting differences, save the JSON as `request.json` and use
`curl.exe -sS http://127.0.0.1:8091/v1/trace/summary -H "Content-Type: application/json" --data-binary "@request.json"`.

Response:

```json
{"task_id":"demo","executed_tool_calls":1,"llm_requests":1,"verification_attempts":1,"total_estimated_input_tokens":120,"terminal_status":"completed"}
```

Rules:

- Count only `tool_call` events with nonempty `tool_name`, including failed calls,
  exactly as Python does. Checkpoint/context/lifecycle events never count.
- Verification attempts are the subset of those calls where `tool_name` is
  `run_tests` and `metadata.phase` is `verification`; standalone verification
  events and development test runs do not count as verification attempts.
- Sum `metadata.estimated_input_tokens` only on `llm_request` events. Missing,
  null, negative, noninteger, or overflowing estimates return 400. Provider usage
  and context estimates are not substituted. No requests means an observed zero.
- Use the last `task_complete.execution_result`, or `unknown` if no terminal
  event exists. Do not infer completion or success from other events.
- Empty event arrays produce zero counters and `unknown` terminal status.

Successful responses are deterministic. Malformed/incomplete input returns 400,
bodies over 1 MiB return 413 (including oversized invalid JSON), internal failures
return 500, unsupported methods return 405. Errors contain fixed messages without
trace data. The server uses 5s header, 10s read/write, and 30s idle timeouts, plus a
16 KiB header limit. Do not expose this unauthenticated learning service publicly.

## Optional Python integration

Default is the unchanged Python metric calculation. Enable the adapter in the
Python evaluator's environment while Go is running on the default address:

```powershell
$env:CODEPILOT_TRACE_METRICS_BACKEND = 'go'
```

Set it to `python` or remove it to disable. The adapter has a 0.5s HTTP timeout,
bypasses environment proxies, enforces request/response size limits, and sends
only aggregation fields and the `phase`/`estimated_input_tokens` metadata keys.
It omits prompts, tool arguments, outputs, checkpoint paths and other metadata.

This deliberately cautious first integration still calculates the Python
reference and accepts Go's five metric fields only if their types and values
match it exactly (plus the task ID). Unavailable Go, HTTP failures, malformed
responses, or mismatches retain Python results. All remaining metrics and
correctness checks stay in Python. No speedup is claimed.

## Parity and Python checks

`testdata/parity.json` contains normalized TraceEvent exports and expected values
from the existing Python calculation, including lifecycle exclusion, verification,
empty traces, absent/last terminal events, step gaps and integers above 2^53.
Go unit tests and Python integration tests use these same fixtures. The live
integration test builds and starts a temporary Go binary, checks health, compares
actual HTTP responses directly with Python, and stops the process afterward.

From the repository root, using the local conda environment:

```powershell
$env:CODEPILOT_GO_EXECUTABLE = Join-Path $env:TEMP 'codepilot-trace-metrics-go/go/bin/go.exe'
$env:GOTOOLCHAIN = 'local'
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest -p no:cacheprovider tests/unit/test_trace_metrics_backend.py tests/unit/test_harness_benchmark.py tests/unit/test_trace.py tests/integration/test_go_trace_metrics.py tests/integration/test_harness_benchmark.py -q --tb=short
```

The live parity test skips when Go is absent from both `CODEPILOT_GO_EXECUTABLE`
and PATH; shared Python reference tests still run. CI provisions Go so direct
parity is exercised there.

## Limits

No persistence, batching across tasks, authentication, provider-usage aggregation,
schema migration, or measured performance results. JSON token estimates and step
IDs use signed 64-bit integers; normalized Python runtime estimates are integers.
Incomplete/noninteger token estimates are rejected more strictly than Python's
unchecked sum. The adapter's reference calculation is intentionally redundant
and may add up to 0.5s waiting on an unavailable service. Full TraceEvent exports
are accepted for manual callers, who should prefer the adapter's small projection
when trace content is sensitive. No changes to agent execution or tool behavior.
