# Context Management

`app/agent/context/` manages what a model sees in one call. It does not store
cross-task knowledge and does not replace `app/core/kernel/context.py` (kernel DI).
`HybridMemoryManager` still selects and persists Task, Error and Repository Memory;
the Context Manager consumes its retrieved text without modifying the Memory store.

## Budget And Estimation

`ContextBudget.usable_input_tokens = max_input_tokens - reserve_output_tokens`.
Defaults are a 32,768-token total envelope and 4,096 reserved output tokens.
Optional section caps are Skill 4,096, Memory 3,072 and Workspace 3,072;
history is capped at 16,384 and each tool observation at 2,048 estimated tokens.
Caps are independent ceilings, not quotas that must sum to the total envelope.
The mandatory core system text has a 4,096-token ceiling: exceeding it raises
`ContextBudgetExceeded`, never truncates safety. The current task has no separate cap.

`TokenEstimator` is replaceable. The default uses UTF-8 bytes / 3, rounded up,
on deterministic JSON serialization, plus four tokens per message and two for
framing. It includes message IDs, tool-call arguments and available tool schemas.
This is an approximation, not a model-specific tokenizer or a billing metric;
an estimated bound does not guarantee a provider's real token count.

## Assembly And Compaction

1. Preserve the complete core system contract and current task. Reject a mandatory
   payload (including tool schemas) that cannot fit the usable budget.
2. Allocate optional text in order: active Skill, retrieved Memory, Workspace.
   Keep legacy serialization order when everything fits. Clip lower-priority
   text to its cap and remaining envelope with deterministic head/tail evidence.
3. Before a model call, validate the transcript and clip oversized tool outputs.
4. When over budget, remove duplicate non-protocol history, then oldest groups
   outside the recent-message window. Reclaim initial optional text in order:
   Workspace, Memory, Skill. Only then evict older groups inside the window.
5. Preserve the first and latest user message, first and latest system message,
   latest logical group, and latest tool exchange (even after a budget reminder).
   Shrink remaining recent non-system/non-user contents
   if necessary. Never rewrite tool arguments or IDs to make a call fit.
6. If protected instructions or the latest tool exchange still cannot fit, raise
   an explicit error rather than send invalid or silently altered instructions.

The recent window (six messages by default) is a preference, not an unlimited
retention guarantee. Tool results are kept with the assistant that requested
them; a multi-tool assistant and all of its results form one eviction group.
Malformed/incomplete input raises `ContextProtocolError`. Text compaction records
the tool name, JSON `success` status when available, original/retained characters,
and head/tail evidence. At very small caps only a marker or empty text can fit.
Clipping includes marker JSON-escaping overhead so the marker itself does not
inflate an otherwise smaller serialized observation.

The API returns a copied transcript plus `ContextStats`; caller-owned messages,
tool results and Memory are not changed by the Context Manager itself.
The assembly result carries core-system/optional-section boundaries. The Harness
keeps that state local to one task and advances it after compaction; dropped
sections are not reintroduced on later calls or verification retries.

## Runtime Configuration

The existing Settings accepts `CODEPILOT_CONTEXT_MAX_INPUT_TOKENS`,
`CODEPILOT_CONTEXT_RESERVE_OUTPUT_TOKENS`, `CODEPILOT_CONTEXT_TOOL_OUTPUT_LIMIT`,
and `CODEPILOT_CONTEXT_RECENT_MESSAGE_COUNT`. Negative limits and an output
reservation smaller than `llm_max_tokens` are invalid. Other section caps are
configurable through an injected `ContextManager(ContextBudget(...))`.

ReAct checks context before ordinary calls, correction/verification continuations
and final budget-exhaustion summaries. Repository analysis invoked by the Harness
uses the same manager; standalone `RepoAnalyzer` preserves its legacy behavior
unless a manager is injected. Verification failures are represented by complete
assistant/tool pairs plus a short recovery instruction, not giant system logs.
Requested batch calls beyond the tool budget receive explicit non-executed tool
results for protocol integrity, without execution or increments to tool metrics.

## Metrics

`ContextStats` measures each operation's estimated tokens before/after, messages
before/after, retained tool outputs compressed, and dropped/truncated section
names. `tokens_saved = max(0, before - after)`; `compression_ratio = after / before`
is the retained fraction (1.0 for an empty estimate), not the savings fraction.
These are per-operation estimates, not end-to-end cost or quality claims.
The Harness emits `context_build` and `context_compaction` through the existing
`ExecutionTrace.record_event`; step ordering and task ownership are unchanged.

No LLM summarization, checkpoints, persistence, or secondary Memory/Trace system
is introduced here.
