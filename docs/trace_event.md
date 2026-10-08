# TraceEvent Contract Draft

Status: active compatibility contract (`schema_version = "0.1"`)

`TraceEvent` is the normalized event contract for Agent runtime, tool execution,
API output, and evaluation traces. `ExecutionTrace` retains its legacy step list
while publishing these events to an optional `TraceSink`.

## Fields

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Trace contract version |
| `task_id` | string | Stable ID shared by every event in one task |
| `step_id` | integer | Monotonic step number within the task |
| `timestamp` | string | ISO-8601 UTC event timestamp |
| `agent_action` | string | Planner or execution action, such as `tool_call` |
| `tool_name` | string or null | Invoked tool, when applicable |
| `tool_input` | object | Validated tool arguments |
| `tool_output` | JSON value | Sanitized tool result |
| `execution_result` | string | Domain outcome, such as `success` or `error` |
| `duration_ms` | number | Event execution latency |
| `metadata` | object | Versioned extension data |

## Semantics

- `execution_result` records the domain outcome. A subprocess or RPC returning
  successfully does not imply that tests passed or the requested operation did.
- Producers must assign one `task_id` before routing and retain it across
  planning, tool calls, verification retries, and final output.
- `step_id` is monotonic within a task. Parallel events may share a parent step
  later, but this draft does not define parent-child relationships yet.
- Tool output must be sanitized and size-limited before persistent storage.
- Skills remain procedural instructions and do not emit or execute tools by
  themselves. The runtime records the selection as a `skill_selection` event.
- Automatic verification tool calls carry `metadata.phase = "verification"`
  and a one-based `metadata.attempt`. Ordinary Agent-initiated test calls do
  not increment the automatic verification retry count.
- `context_build` records initial context assembly; `context_compaction` records
  each successful pre-call budget check, including checks with no changes.
  Metadata contains estimated tokens before/after, `tokens_saved`, retained
  `compression_ratio` (after/before), messages before/after, retained tool outputs
  compressed, dropped/truncated section names and `compaction_triggered`.
  Compaction phase is `react`, `final_summary`, or `repo_analysis`. Context events
  have no tool name/input/output, add no legacy tool step, and do not affect tool
  counts, verification attempts, changed files, or terminal task outcomes.
  No prompt, Memory text or observation contents are copied into these events.
  See [Context Management](context_management.md) for estimate limitations.
- `task_complete` records runtime termination (`completed`, `error`,
  `cancelled`, `budget_exhausted`, or `verification_failed`). `completed`
  alone does not establish benchmark task success; the evaluator runs its own tests.

## Trace Sinks

- `InMemoryTraceSink` collects events for API consumers and tests.
- `JsonlTraceSink` appends one event per line for durable replay and evaluation.
- Custom sinks implement `emit(event)` and can forward events to observability systems.
- Sink failures are logged and do not interrupt the Agent task; the in-result event list remains available.

## Migration Boundary

The runtime emits normalized routing, Skill selection, tool call, verification,
and completion events. `EvaluationRunner` passes its task ID into the Agent,
validates event ownership, and derives tool, verification, and changed-file metrics
from the event stream. Changed-file candidates must also differ from the seed
workspace on disk. Existing `ExecutionStepTrace`, API response schemas, and
whole-trace JSONL exports remain compatible.
