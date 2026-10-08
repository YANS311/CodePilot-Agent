# Checkpoint / Resume

Checkpoint is execution-state persistence. Memory is cross-task knowledge;
Context selects the model-visible prompt; Trace records execution facts. This
package reuses existing AgentState, ToolBudget, VerificationPolicy, ContextBudget,
ToolResult/AgentStep and normalized TraceEvent instead of another workflow engine.

## State Contract

`AgentCheckpoint` schema `1.0` captures request/task identity, canonical workspace
and content fingerprint, lifecycle/next safe phase, AgentState iteration,
protocol-valid messages, active Skill, consumed ToolBudget and anti-loop caches,
drift flags, completed call IDs/outcomes, verification policy/attempt, compacted
context section boundaries/budget, result projection, trace history/cursor,
guardrail read state, resume count, revision and timestamps. Live clients, tool
registries, transports, settings/credentials and Python object graphs are excluded.
The `llm_request_prepared` flag prevents reinserting a budget prompt when resuming
an already prepared model call. Result and trace projections retain completed
outcomes even when old conversation groups have been compacted away.

The trace cursor can reserve IDs beyond recorded events so uncertain execution
does not reuse IDs already emitted to a durable sink. Gaps are allowed; strictly
increasing ownership-consistent event IDs remain required.

## Storage

`FileCheckpointStore` defaults to application-owned `data/checkpoints/`, outside
the Agent workspace. Enable only with a disjoint storage/workspace pair; a store
inside a tool-accessible workspace is rejected. Validated task IDs are 1-64 ASCII
letters/digits/underscore/hyphen and produce prefixed filenames, never user paths.
Storage rejects redirected roots and non-regular snapshot/lock files.

Save validates a fresh JSON projection and compares the existing revision under
a local OS lock. It writes a same-directory temporary file, flushes/fsyncs it,
then uses `os.replace`. Directory fsync is used where supported; Windows and
filesystems without directory fsync have a weaker power-loss durability boundary.
Failed replacement leaves the previous complete snapshot. A separate OS lease
is held for the whole run/resume; another instance cannot run/delete the same task
while that lease is held. Locks are single-machine, not distributed.

Snapshots are capped at 2 MiB. Workspace fingerprints cover regular file contents
and root identity, capped at 10,000 files/256 MiB, excluding `.git`, `__pycache__`
and `.pytest_cache`; linked entries are not supported. This is not a Git history
or external-service snapshot. There is no automatic retention scheduler: trusted
application code can `list_tasks()` and `delete(task_id)`; lock files are retained
to avoid inode races. Never commit runtime snapshots (`data/` is already ignored).

Only trusted application code should configure/access the store. POSIX files
use mode 0600 and new directories 0700; on Windows protect the directory with
account ACLs. Workspace confinement protects normal file-tool paths, not arbitrary
code running with the application's OS permissions. Untrusted pytest/MCP/executors
need OS/container isolation and must not be granted access to this directory.

Credential-key/text detection and caller-supplied forbidden values reject saves,
without redacting the execution state. Arbitrarily unlabeled secrets cannot be
recognized perfectly: use trusted workspaces and provide known secret values.
No LLM/API settings, transport headers or environment credential dictionaries are
part of the schema. Rejection messages never include the secret value.

## Recovery Policy

Durable snapshots must contain complete assistant/tool groups. Before executing
a group, an indeterminate marker is written over the last safe transcript, with
pending call IDs/names/replay classification. After the entire group finishes a
new safe checkpoint can replace it. A crash between execution and safe save leaves
the marker: automatic replay is refused, including read-only calls in this MVP.
No idempotency guarantees are assumed for custom/MCP calls or test execution.
There is no exactly-once claim and no operator bypass API in this milestone;
reconcile effects externally, inspect the snapshot, and deliberately start a new
task if necessary. Never silently clear an indeterminate marker and retry writes.

## Runtime API

Checkpointing is disabled by default. Existing `run(...)` callers need no changes;
this milestone adds an explicit Python API, not an automatic startup scanner or a
new HTTP recovery endpoint. Supply the same registry schemas, workspace, budget,
verification policy and context policy when constructing a replacement runtime:

```python
from app.agent.checkpoint import CheckpointManager, FileCheckpointStore
from app.agent.react_agent import ReActAgent

def new_runtime():
    store = FileCheckpointStore("/private/codepilot-checkpoints")
    return ReActAgent(
        llm, registry, workspace_root,
        max_tool_calls=8,
        verification_policy=verification_policy,
        context_manager=context_manager,
        permission_policy=current_permission_policy,
        trace_sink=trace_sink,
        checkpoint_manager=CheckpointManager(store),
    )

result = await new_runtime().run("Inspect source", task_id="inspect-42")
# After an interruption at a durable safe boundary, in a NEW runtime:
result = await new_runtime().resume_task("inspect-42")
```

The second call is an alternative recovery path after interruption, not a replay
of the completed first call. Terminal checkpoints are rejected, including failed
and cancelled tasks. `run` also refuses to overwrite an existing task ID; select
a new ID for a genuinely new task. `ResumeRejected` exposes the safe reason and, when a valid
snapshot was loaded, the rejection trace. Corrupt snapshots fail schema validation
before their task ID or trace contents are trusted.

Resume does not route the task, load Skills again, retrieve Memory again or build
a new workspace index. It restores the saved active Skill and model-visible
sections, anti-loop caches, correction flags, guardrail counters and result history.
Current prompt checks and tool PermissionPolicy still apply. Changed content/root
identity, tool schemas, budget ceiling, context budget/estimator type or verification
policy reject resume. Caller-defined tool implementations and estimator behavior
must also remain compatible: schema/type equality cannot detect code changes.

## Boundaries And Lifecycle

- Initial context assembly and each prepared LLM request are safe checkpoints.
- Whole assistant/tool exchanges replace the pre-execution indeterminate marker.
- Verification outcomes persist before either finishing or entering repair.
- `core`, `repair`, `verify`, `summary` and `finish` identify the next safe phase.
- Terminal state is saved before task Memory publication; it cannot restart work.

The persisted lifecycle uses `created`, `checkpointed`, `resumed`, `indeterminate`
and the existing terminal outcomes (`completed`, `failed`, `cancelled`,
`budget_exhausted`, `verification_failed`). Trace retains the existing runtime
terminal semantics. A resumable snapshot does not imply successful completion.

Verification resumes from its stored zero-based attempt, without rerunning a
completed attempt or counting recovery as a retry. The existing ToolBudget covers
ReAct tool calls; verification has its existing independent retry policy and is
included in cumulative result/trace tool counts, not retroactively charged to that
budget. A model reusing a completed call ID is rejected before execution. A new
call ID is a new model request, not an idempotency guarantee for equal arguments.

Task Memory is attempted only after a durable terminal checkpoint. Terminal resume
is rejected, preventing duplicate task Memory publication. This is an at-most-once
attempt, not a transactional outbox: a crash after terminal save but before Memory
write can omit the Memory entry. Existing Error/Repository Memory behavior is not
transactionally checkpointed. Repository analysis has no mid-analysis recovery;
the durable resumable workflow in this MVP is the ReAct execution path.

## Trace And Evaluation

The existing TraceSink receives `checkpoint_saved`, `checkpoint_loaded`,
`task_resumed`, `resume_rejected` and `recovery_required`. Metadata contains bounded
version/step/count/size/duration/budget/reason values, not messages, credentials or
tool contents. Checkpoint-triggered compaction uses the existing
`context_compaction` action with `phase=checkpoint` and measured estimates.

Loaded historical events are not re-emitted to the sink. Their snapshots remain
in the result trace for EvaluationRunner; new events advance the persisted cursor.
Resume claims a bounded lifecycle ID range durably before publishing its first
event, so a second crash during loading cannot cause event-ID reuse.
The event announcing a successful save is emitted after that save and is included
in a later snapshot if one occurs. A crash may therefore leave cursor gaps or
events present only in the sink. Checkpoints are not a transactional event log.
Evaluation still counts only actual `tool_call` events, identifies verification
attempts by existing metadata, and verifies edits against final file contents.

## Offline Recovery Demonstrations

These tests use mocked LLM/Memory and temporary, disjoint workspace/storage roots;
no network, external model, Docker or API keys are required:

```powershell
& C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe -m pytest -p no:cacheprovider -s -q tests/integration/test_checkpoint_resume.py::test_new_runtime_resumes_completed_read_without_reexecution tests/integration/test_checkpoint_resume.py::test_indeterminate_write_after_real_effect_fails_closed
```

The first test saves a completed `read-1`, simulates process exit, creates a new
runtime, restores budget `1/8`, executes zero replayed tools and completes. The
second performs a real temporary-file write and exits before outcome persistence;
the new runtime refuses replay and emits `recovery_required`. Simulated process
exit uses a `BaseException` so ordinary failure/cancellation handling is not
mistaken for a process crash.

## Operational Limitations

This is single-host, local-filesystem recovery, not distributed scheduling,
cross-machine migration, a backup, tool idempotency or exactly-once execution.
Use one task per runtime instance and serialize access to a workspace using the
existing application workspace ownership/lock mechanism. The task lease protects
the same task ID, not different task IDs sharing a workspace or external editors.
Fingerprint validation is not an OS filesystem transaction: concurrent edits after
validation or adversarial filesystem changes require external isolation/ownership.
A side effect followed by storage failure remains indeterminate; safe progress
may be refused rather than guessed. Keep retention bounded and protect checkpoint
ACLs, storage capacity and trusted executor permissions operationally.
