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
   outside the recent-message window, then older groups inside that window.
5. Preserve the first and latest user message, first and latest system message,
   and latest logical group. Shrink remaining recent non-system/non-user contents
   if necessary. Never rewrite tool arguments or IDs to make a call fit.
6. If protected instructions or the latest tool exchange still cannot fit, raise
   an explicit error rather than send invalid or silently altered instructions.

The recent window (six messages by default) is a preference, not an unlimited
retention guarantee. Tool results are kept with the assistant that requested
them; a multi-tool assistant and all of its results form one eviction group.
Malformed/incomplete input raises `ContextProtocolError`. Text compaction records
the tool name, JSON `success` status when available, original/retained characters,
and head/tail evidence. At very small caps only a marker or empty text can fit.

The API returns a copied transcript plus `ContextStats`; caller-owned messages,
tool results and Memory are not changed by the Context Manager itself.

## Metrics

`ContextStats` measures each operation's estimated tokens before/after, messages
before/after, retained tool outputs compressed, and dropped/truncated section
names. `tokens_saved = max(0, before - after)`; `compression_ratio = after / before`
is the retained fraction (1.0 for an empty estimate), not the savings fraction.
These are per-operation estimates, not end-to-end cost or quality claims.

No LLM summarization, checkpoints, persistence, or secondary Memory/Trace system
is introduced here.
