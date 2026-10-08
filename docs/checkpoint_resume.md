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
