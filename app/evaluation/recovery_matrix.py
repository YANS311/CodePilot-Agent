"""Separate real-tool, scripted-model crash consistency experiments."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agent.checkpoint import CheckpointError, CheckpointManager, FileCheckpointStore, ResumeRejected
from app.agent.context import ContextBudget, ContextManager
from app.agent.context.compactor import group_messages
from app.agent.react_agent import ReActAgent
from app.agent.trace import InMemoryTraceSink
from app.agent.verification import VerificationPolicy
from app.core.llm_client import ChatResponse
from app.evaluation.harness_runner import ROOT, SequenceLLM, copy_seed, registry, tool_response
from app.evaluation.profiles import BenchmarkMemory


class ProcessExit(BaseException):
    """Bypass normal caught task-error handling, as actual process death does."""


class InterruptingStore(FileCheckpointStore):
    def __init__(self, root, predicate):
        super().__init__(root)
        self.predicate = predicate

    def save(self, checkpoint):
        saved = super().save(checkpoint)
        if self.predicate(saved):
            raise ProcessExit()
        return saved


async def run_recovery_matrix():
    rows = []
    scenarios = ("safe_read", "indeterminate_write", "verification_progress", "workspace_changed", "corrupt_snapshot", "policy_changed")
    for scenario in scenarios:
        with TemporaryDirectory(prefix="codepilot-recovery-") as temp:
            root = Path(temp)
            workspace = root / "workspace"
            copy_seed(ROOT / "benchmarks/harness/seed", workspace, simulated=True)
            storage = root / "private-state"
            sink = InMemoryTraceSink()
            executions = []
            policy = VerificationPolicy(enabled=scenario == "verification_progress", max_retries=1,
                                        test_command="tests/test_arithmetic.py::test_difference")
            stop = lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read"]
            if scenario == "verification_progress":
                stop = lambda cp: cp.status == "checkpointed" and cp.next_step == "repair"
            store = FileCheckpointStore(storage) if scenario == "indeterminate_write" else InterruptingStore(storage, stop)

            def runtime(responses, current_store, max_calls=8):
                tools = registry()
                execute = tools.execute
                async def monitored(call, path, guardrail=None):
                    executions.append(call.id)
                    result = await execute(call, path, guardrail=guardrail)
                    if scenario == "indeterminate_write" and call.name == "write_file":
                        raise ProcessExit()
                    return result
                tools.execute = monitored
                return ReActAgent(SequenceLLM(responses), tools, str(workspace), max_tool_calls=max_calls,
                                  verification_policy=policy, context_manager=ContextManager(ContextBudget(tool_observation_budget=250)),
                                  memory_manager=BenchmarkMemory(retrieval=False, state="cold"), trace_sink=sink,
                                  checkpoint_manager=CheckpointManager(current_store))

            responses = [tool_response("read", "read_file", path="arithmetic.py")]
            if scenario in {"indeterminate_write", "verification_progress"}:
                responses = [tool_response("write-1", "write_file", path="arithmetic.py", content="def subtract(a,b):\n    return a+b+1\n"), ChatResponse(content="Edit recorded.")]
            first = runtime(responses, store)
            try:
                await first.run("Fix arithmetic regression", task_id=scenario)
                raise AssertionError("Failure injection did not interrupt")
            except ProcessExit:
                pass
            saved = FileCheckpointStore(storage).load(scenario)
            group_messages(saved.messages)
            before = list(executions)
            if scenario == "workspace_changed":
                (workspace / "arithmetic.py").write_text("operator edit\n", encoding="utf-8")
            if scenario == "corrupt_snapshot":
                (storage / f"cp-{scenario}.json").write_text("{broken", encoding="utf-8")
            remaining_responses = [ChatResponse(content="Inspection completed.")]
            if scenario == "verification_progress":
                remaining_responses = [tool_response("write-2", "write_file", path="arithmetic.py", content="def subtract(a,b):\n    return a-b\n"), ChatResponse(content="Edit recorded.")]
            second = runtime(remaining_responses, FileCheckpointStore(storage), max_calls=9 if scenario == "policy_changed" else 8)
            rejected = None
            result = None
            try:
                result = await second.resume_task(scenario)
            except ResumeRejected as error:
                rejected = str(error)
            except CheckpointError:
                rejected = "corrupt_snapshot"
            events = sink.snapshot()
            ids = [e.step_id for e in events]
            integrity = all(e.task_id == scenario for e in events) and all(b > a for a, b in zip(ids, ids[1:]))
            assertions = {"new_runtime": first is not second, "trace_integrity": integrity}
            if scenario == "safe_read":
                assertions.update(completed=result is not None and result.trace.status == "completed",
                                  no_replay=executions == before, budget_preserved=second._budget.current_calls == saved.budget.current_calls,
                                  context_preserved=bool(result and result.messages[:len(saved.messages)] == saved.messages))
            elif scenario == "verification_progress":
                assertions.update(completed=result is not None and result.verification_passed,
                                  correct_retry=bool(result and result.verification_retries == 1),
                                  no_duplicate_attempt=executions.count("verify_0") == executions.count("verify_1") == 1)
            else:
                expected = {"indeterminate_write": "indeterminate_tool_exchange", "workspace_changed": "workspace_identity_mismatch",
                            "corrupt_snapshot": "corrupt_snapshot", "policy_changed": "tool_budget_policy_changed"}[scenario]
                assertions.update(rejected=rejected == expected, no_new_effect=executions == before)
                if scenario == "indeterminate_write":
                    assertions.update(indeterminate=saved.status == "indeterminate", recovery_event=any(e.agent_action == "recovery_required" for e in events))
            rows.append({"scenario": scenario, "status": "PASS" if all(assertions.values()) else "FAIL",
                         "assertions": assertions, "executed_call_ids": executions, "rejection_reason": rejected})
    return {"label": "OFFLINE scripted model + real file/test tools; reliability, not TSR or exactly-once", "rows": rows}
