"""Crash-window demonstrations with NEW runtimes and offline fake model responses."""

import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.checkpoint import CheckpointManager, FileCheckpointStore, ResumeRejected
from app.agent.context import ContextBudget, ContextManager
from app.agent.context import ContextProtocolError
from app.agent.context.compactor import group_messages
from app.agent.react_agent import ReActAgent
from app.agent.trace import InMemoryTraceSink
from app.agent.verification import VerificationPolicy
from app.core.llm_client import ChatResponse, ToolCallInfo
from app.models.tool import ToolResult
from app.security.permission import PermissionPolicy
from app.tools.read_file import ReadFileTool
from app.tools.search_code import SearchCodeTool
from app.tools.run_tests import RunTestsTool
from app.tools.write_file import WriteFileTool
from app.tools.registry import ToolRegistry


class SimulatedCrash(BaseException):
    """Model process death, not an ordinary caught task failure/cancellation."""


class CrashAfterSave(FileCheckpointStore):
    def __init__(self, root, predicate):
        super().__init__(root)
        self.predicate = predicate

    def save(self, checkpoint):
        saved = super().save(checkpoint)
        if self.predicate(saved):
            raise SimulatedCrash("simulated process exit after durable save")
        return saved


def call(call_id, name="read_file", **arguments):
    return ChatResponse(tool_calls=[ToolCallInfo(id=call_id, name=name, arguments=arguments or {"path": "source.py"})])


@pytest.fixture
def factory(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "source.py").write_text("original content", encoding="utf-8")
    storage = tmp_path / "private-state"
    sink = InMemoryTraceSink()
    memory = MagicMock()
    memory.build_memory_context.return_value = "Retrieved historical evidence " * 400
    monkeypatch.setattr("app.agent.react_agent.get_memory_manager", lambda: memory)
    router = MagicMock()
    router.route.return_value = SimpleNamespace(intent="react", layer="rule")
    monkeypatch.setattr("app.agent.react_agent.get_intent_router", lambda: router)

    def create(responses, *, store=None, execute=None, verification=None, permission=None, max_calls=8):
        registry = ToolRegistry()
        for tool in (ReadFileTool(), WriteFileTool(), RunTestsTool(), SearchCodeTool()):
            registry.register(tool)
        calls = []

        async def default_execute(tc, root, guardrail=None):
            calls.append(tc.id)
            return ToolResult(tool_call_id=tc.id, name=tc.name, success=True, output="evidence HEAD " + "x" * 15000 + " TAIL")

        registry.execute = AsyncMock(side_effect=execute or default_execute)
        requests = []
        iterator = iter(responses)
        context = ContextManager(ContextBudget(tool_observation_budget=150))

        async def chat(messages, *, tools=None, temperature=0.0):
            group_messages(messages)
            requests.append(deepcopy(messages))
            return next(iterator)

        llm = SimpleNamespace(chat=chat)
        skills = MagicMock()
        skills.match_and_load_for_task.return_value = None
        agent = ReActAgent(
            llm, registry, str(workspace), max_tool_calls=max_calls,
            verification_policy=verification or VerificationPolicy.disabled(),
            permission_policy=permission, context_manager=context, skill_manager_instance=skills,
            trace_sink=sink, checkpoint_manager=CheckpointManager(store or FileCheckpointStore(storage)),
        )
        monkeypatch.setattr(agent, "_build_index_context", lambda: "Workspace evidence")
        return agent, requests, calls

    return create, workspace, storage, sink, memory, router


def assert_trace(sink, task_id):
    events = sink.snapshot()
    assert all(event.task_id == task_id for event in events)
    ids = [event.step_id for event in events]
    assert all(current > previous for previous, current in zip(ids, ids[1:]))
    for event in events:
        if event.agent_action in {"checkpoint_saved", "checkpoint_loaded", "task_resumed", "resume_rejected", "recovery_required"}:
            assert event.tool_name is None
            assert event.tool_input == {}
            assert event.tool_output is None
            assert len(json.dumps(event.metadata)) < 1000


def test_new_runtime_resumes_completed_read_without_reexecution(factory):
    create, workspace, storage, sink, memory, router = factory
    store = CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read-1"])
    first, _, first_calls = create([call("read-1")], store=store)
    first._skill_manager.match_and_load_for_task.return_value = SimpleNamespace(
        name="repo_bugfix", to_prompt_instruction=lambda: "Active repository bugfix instructions",
    )
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="read-demo"))
    saved = FileCheckpointStore(storage).load("read-demo")
    assert saved.budget.current_calls == 1
    assert saved.budget.remaining_calls == 7
    assert saved.runtime.iteration == 1
    assert saved.status == "checkpointed"
    assert "[Tool Observation compacted]" in saved.messages[-1]["content"]
    second, requests, second_calls = create([ChatResponse(content="Inspection complete")])
    result = asyncio.run(second.resume_task("read-demo"))
    assert first is not second
    assert first_calls == ["read-1"]
    assert second_calls == []
    assert result.answer == "Inspection complete"
    assert saved.active_skill == result.active_skill == "repo_bugfix"
    assert "Active repository bugfix instructions" in requests[0][0]["content"]
    second._skill_manager.match_and_load_for_task.assert_not_called()
    assert result.tool_calls_count == 1
    assert second._budget.current_calls == 1
    assert second._budget.remaining_calls == 7
    assert requests[0][:len(saved.messages)] == saved.messages
    assert memory.build_memory_context.call_count == 1
    assert router.route.call_count == 1
    assert memory.add_task_memory.call_count == 1
    assert result.trace.task_id == "read-demo"
    assert FileCheckpointStore(storage).load("read-demo").status == "completed"
    assert_trace(sink, "read-demo")
    print("read-demo: read-1 completed once -> NEW runtime -> 0 replayed tools -> completed; budget=1/8")


def test_completed_write_is_not_replayed_and_terminal_memory_is_not_duplicated(factory):
    create, workspace, storage, sink, memory, _ = factory
    executed = []

    def execute(tc, root, guardrail=None):
        executed.append(tc.id)
        (workspace / "source.py").write_text(tc.arguments["content"], encoding="utf-8")
        return ToolResult(tool_call_id=tc.id, name=tc.name, success=True, output="written")

    store = CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["write-1"])
    first, _, _ = create([call("write-1", "write_file", path="source.py", content="updated")], store=store, execute=execute)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Update source", task_id="write-demo"))
    second, _, calls = create([ChatResponse(content="Modification recorded")], execute=execute)
    result = asyncio.run(second.resume_task("write-demo"))
    assert executed == ["write-1"]
    assert (workspace / "source.py").read_text() == "updated"
    assert result.wrote_file
    assert memory.add_task_memory.call_count == 1
    for _ in range(2):
        third, _, _ = create([])
        with pytest.raises(ResumeRejected, match="terminal_checkpoint"):
            asyncio.run(third.resume_task("write-demo"))
    assert memory.add_task_memory.call_count == 1
    assert_trace(sink, "write-demo")


def test_indeterminate_write_after_real_effect_fails_closed(factory):
    create, workspace, storage, sink, memory, _ = factory
    executed = []

    def crash_after_write(tc, root, guardrail=None):
        executed.append(tc.id)
        (workspace / "source.py").write_text("possibly committed", encoding="utf-8")
        raise SimulatedCrash("write happened but outcome was not saved")

    first, _, _ = create([call("uncertain-write", "write_file", path="source.py", content="possibly committed")], execute=crash_after_write)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Update source", task_id="unsafe-demo"))
    state = FileCheckpointStore(storage).load("unsafe-demo")
    assert state.status == "indeterminate"
    assert state.in_flight[0].replay_class == "side_effecting"
    group_messages(state.messages)
    second, requests, calls = create([])
    with pytest.raises(ResumeRejected, match="indeterminate_tool_exchange"):
        asyncio.run(second.resume_task("unsafe-demo"))
    assert executed == ["uncertain-write"]
    assert requests == calls == []
    assert any(event.agent_action == "recovery_required" for event in sink.snapshot())
    assert memory.add_task_memory.call_count == 0
    assert_trace(sink, "unsafe-demo")
    print("unsafe-demo: write effect occurred -> indeterminate marker -> NEW runtime refuses replay -> recovery_required")


def test_partial_multi_tool_exchange_never_produces_resumable_partial_messages(factory):
    create, workspace, storage, sink, _, _ = factory
    executed = []

    def execute(tc, root, guardrail=None):
        executed.append(tc.id)
        if tc.id == "b":
            raise SimulatedCrash()
        return ToolResult(tool_call_id=tc.id, name=tc.name, success=True, output="ok")

    response = call("a")
    response.tool_calls.append(ToolCallInfo(id="b", name="write_file", arguments={"path": "source.py", "content": "new"}))
    first, _, _ = create([response], execute=execute)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="batch-demo"))
    saved = FileCheckpointStore(storage).load("batch-demo")
    assert [p.id for p in saved.in_flight] == ["a", "b"]
    assert not any(m.get("tool_call_id") == "a" for m in saved.messages)
    group_messages(saved.messages)
    second, _, _ = create([])
    with pytest.raises(ResumeRejected):
        asyncio.run(second.resume_task("batch-demo"))
    assert executed == ["a", "b"]
    assert_trace(sink, "batch-demo")


def test_verification_failure_resume_preserves_retry_position(factory):
    create, _, storage, sink, memory, _ = factory
    executions = []

    def execute(tc, root, guardrail=None):
        executions.append(tc.id)
        success = tc.id != "verify_0"
        return ToolResult(tool_call_id=tc.id, name=tc.name, success=success, output=json.dumps({"success": success, "stderr": "AssertionError " + "x" * 6000 if not success else ""}))

    policy = VerificationPolicy(enabled=True, max_retries=2)
    store = CrashAfterSave(storage, lambda cp: cp.next_step == "repair" and cp.status == "checkpointed")
    first, _, _ = create([call("write-1", "write_file", path="source.py", content="first"), ChatResponse(content="Attempt one")], store=store, execute=execute, verification=policy)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Fix source", task_id="verify-demo"))
    state = FileCheckpointStore(storage).load("verify-demo")
    assert state.verification_attempt == 1
    assert state.result.verification_retries == 0
    second, requests, _ = create([call("write-2", "write_file", path="source.py", content="fixed"), ChatResponse(content="Attempt two")], execute=execute, verification=policy)
    result = asyncio.run(second.resume_task("verify-demo"))
    assert executions == ["write-1", "verify_0", "write-2", "verify_1"]
    assert result.verification_passed
    assert result.verification_retries == 1
    assert result.tool_calls_count == 4
    verification = [e for e in result.trace.events if e.metadata.get("phase") == "verification"]
    assert [e.metadata["attempt"] for e in verification] == [1, 2]
    assert len([e for e in result.trace.events if e.agent_action == "tool_call"]) == 4
    assert memory.add_task_memory.call_count == 1
    assert_trace(sink, "verify-demo")


@pytest.mark.parametrize("error,status", [(RuntimeError("offline failure"), "failed"), (asyncio.CancelledError(), "cancelled")])
def test_failure_and_cancellation_remain_terminal(factory, error, status):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([])

    async def fail(*args, **kwargs):
        raise error

    first._llm.chat = fail
    with pytest.raises(type(error)):
        asyncio.run(first.run("Inspect source", task_id="failed-demo"))
    assert FileCheckpointStore(storage).load("failed-demo").status == status
    second, requests, _ = create([])
    with pytest.raises(ResumeRejected, match="terminal_checkpoint"):
        asyncio.run(second.resume_task("failed-demo"))
    assert requests == []
    assert_trace(sink, "failed-demo")


def test_external_workspace_change_rejects_resume(factory):
    create, workspace, storage, sink, _, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.completed_tool_ids == ["read-1"] and cp.status == "checkpointed"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="changed-demo"))
    (workspace / "source.py").write_text("operator edit", encoding="utf-8")
    second, requests, _ = create([])
    with pytest.raises(ResumeRejected, match="workspace_identity_mismatch"):
        asyncio.run(second.resume_task("changed-demo"))
    assert requests == []
    assert_trace(sink, "changed-demo")


def test_current_permission_policy_still_applies_after_resume(factory):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.completed_tool_ids == ["read-1"] and cp.status == "checkpointed"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="permission-demo"))
    second, _, executed = create([call("write-2", "write_file", path="source.py", content="blocked"), ChatResponse(content="Permission denied")], permission=PermissionPolicy.read_only())
    result = asyncio.run(second.resume_task("permission-demo"))
    assert executed == []
    assert result.tool_results[-1].metadata["permission_blocked"]
    assert_trace(sink, "permission-demo")


def test_complete_multi_tool_exchange_restores_anti_loop_and_guardrail(factory):
    create, _, storage, sink, _, _ = factory

    def execute(tc, root, guardrail=None):
        guardrail.restore_checkpoint_state(3, [1.0, 2.0, 3.0], [])
        return ToolResult(tool_call_id=tc.id, name=tc.name, success=True, output="source.py:1: evidence")

    response = call("search", "search_code", query="Evidence")
    response.tool_calls.append(ToolCallInfo(id="read", name="read_file", arguments={"path": "source.py"}))
    store = CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and len(cp.completed_tool_ids) == 2)
    first, _, _ = create([response], store=store, execute=execute)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="complete-batch"))
    saved = FileCheckpointStore(storage).load("complete-batch")
    group_messages(saved.messages)
    second, _, calls = create([ChatResponse(content="Inspection complete")])
    result = asyncio.run(second.resume_task("complete-batch"))
    assert calls == []
    assert result.tool_calls_count == 2
    assert second._budget.is_duplicate_search("evidence")
    assert second._budget.get_cached_path("evidence") == "source.py"
    assert second._budget.has_read("source.py")
    assert second._guardrail.checkpoint_state() == (3, [1.0, 2.0, 3.0])
    assert_trace(sink, "complete-batch")


def test_budget_summary_resume_does_not_reset_budget(factory):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([call("only-read")], max_calls=1, store=CrashAfterSave(storage, lambda cp: cp.next_step == "summary"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="budget-demo"))
    saved = FileCheckpointStore(storage).load("budget-demo")
    assert saved.runtime.iteration == 1
    second, requests, calls = create([ChatResponse(content="Budget summary")], max_calls=1)
    result = asyncio.run(second.resume_task("budget-demo"))
    assert second._budget.remaining_calls == 0
    assert len(requests) == 1 and calls == []
    assert result.trace.status == "budget_exhausted"
    assert FileCheckpointStore(storage).load("budget-demo").status == "budget_exhausted"
    assert_trace(sink, "budget-demo")


def test_correction_iteration_exhaustion_persists_summary_boundary(factory):
    create, _, storage, _, _, _ = factory
    first, _, _ = create([ChatResponse(content="read_file(source.py)")], max_calls=1, store=CrashAfterSave(storage, lambda cp: cp.next_step == "summary"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="correction-demo"))
    saved = FileCheckpointStore(storage).load("correction-demo")
    assert saved.drift_corrected and saved.runtime.iteration == 1
    second, requests, calls = create([ChatResponse(content="Summary")], max_calls=1)
    asyncio.run(second.resume_task("correction-demo"))
    assert second._has_drift_corrected
    assert len(requests) == 1 and not calls


def test_resume_before_llm_does_not_duplicate_prepared_budget_prompt(factory):
    create, _, storage, _, _, _ = factory
    store = CrashAfterSave(storage, lambda cp: cp.llm_request_prepared and cp.completed_tool_ids == ["read-1"])
    first, _, _ = create([call("read-1")], max_calls=3, store=store)
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="prepared-demo"))
    saved = FileCheckpointStore(storage).load("prepared-demo")
    second, requests, _ = create([ChatResponse(content="Inspection complete")], max_calls=3)
    asyncio.run(second.resume_task("prepared-demo"))
    assert requests[0] == saved.messages


def test_crash_during_resume_never_reuses_emitted_lifecycle_ids(factory, monkeypatch):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read-1"]))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="resume-crash"))
    second, _, _ = create([])

    def crash(task):
        raise SimulatedCrash("exit after checkpoint_loaded reached the sink")

    monkeypatch.setattr(second._guardrail, "check_prompt", crash)
    with pytest.raises(SimulatedCrash):
        asyncio.run(second.resume_task("resume-crash"))
    third, _, calls = create([ChatResponse(content="Inspection complete")])
    result = asyncio.run(third.resume_task("resume-crash"))
    assert not calls and result.trace.status == "completed"
    assert len([e for e in sink.snapshot() if e.agent_action == "checkpoint_loaded"]) == 2
    assert_trace(sink, "resume-crash")


def test_run_existing_task_id_cannot_overwrite_or_restart_trace(factory):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([ChatResponse(content="Inspection complete")])
    asyncio.run(first.run("Inspect source", task_id="unique-task"))
    saved = FileCheckpointStore(storage).load("unique-task")
    before = sink.snapshot()
    second, requests, calls = create([])
    with pytest.raises(ResumeRejected, match="task_id_already_exists"):
        asyncio.run(second.run("Different task", task_id="unique-task"))
    assert requests == calls == []
    assert sink.snapshot() == before
    assert FileCheckpointStore(storage).load("unique-task") == saved


def test_duplicate_batch_ids_rejected_before_any_effect(factory):
    create, _, storage, _, _, _ = factory
    response = call("duplicate", "write_file", path="source.py", content="new")
    response.tool_calls.append(response.tool_calls[0])
    first, _, calls = create([response])
    with pytest.raises(ContextProtocolError):
        asyncio.run(first.run("Update source", task_id="duplicate-demo"))
    assert calls == []
    assert FileCheckpointStore(storage).load("duplicate-demo").status == "failed"


def test_completed_call_id_reuse_rejected_after_resume(factory):
    create, _, storage, _, _, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read-1"]))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="reuse-demo"))
    second, _, calls = create([call("read-1")])
    with pytest.raises((ResumeRejected, ContextProtocolError)):
        asyncio.run(second.resume_task("reuse-demo"))
    assert calls == []


@pytest.mark.parametrize("change,reason", [
    ("budget", "tool_budget_policy_changed"),
    ("verification", "verification_policy_changed"),
    ("context", "context_policy_changed"),
    ("tools", "tool_registry_changed"),
    ("workspace", "workspace_validation_failed"),
])
def test_runtime_policy_or_unavailable_workspace_rejects_resume(factory, change, reason):
    create, _, storage, sink, _, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read-1"]))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="policy-demo"))
    second, requests, calls = create([])
    if change == "budget":
        second._max_tool_calls = 20
    elif change == "verification":
        second._verification = VerificationPolicy(enabled=True)
    elif change == "context":
        second._context_manager = ContextManager(ContextBudget(tool_observation_budget=200))
    elif change == "tools":
        second._registry.register(SimpleNamespace(to_openai_schema=lambda: {"changed": True}, name="new-tool"))
    else:
        second._workspace_root = str(storage / "nonexistent-workspace")
    with pytest.raises(ResumeRejected, match=reason):
        asyncio.run(second.resume_task("policy-demo"))
    assert requests == calls == []
    assert_trace(sink, "policy-demo")


@pytest.mark.parametrize("passed", [True, False])
def test_completed_verification_resume_does_not_rerun_tests(factory, passed):
    create, _, storage, sink, _, _ = factory
    executions = []

    def execute(tc, root, guardrail=None):
        executions.append(tc.id)
        return ToolResult(tool_call_id=tc.id, name=tc.name, success=passed if tc.name == "run_tests" else True, output="test evidence")

    policy = VerificationPolicy(enabled=True, max_retries=0)
    first, _, _ = create([call("write-1", "write_file", path="source.py", content="new"), ChatResponse(content="Attempt")], verification=policy, execute=execute, store=CrashAfterSave(storage, lambda cp: cp.next_step == "finish"))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Fix source", task_id="verify-finish"))
    second, requests, calls = create([], verification=policy)
    result = asyncio.run(second.resume_task("verify-finish"))
    assert requests == calls == []
    assert executions == ["write-1", "verify_0"]
    assert result.verification_passed == passed
    assert result.verification_retries == 0
    assert result.trace.status == ("completed" if passed else "verification_failed")
    assert_trace(sink, "verify-finish")


def test_evaluation_counts_only_actual_tool_events_across_resume(factory, tmp_path, monkeypatch):
    from app.evaluation.runner import EvaluationRunner
    from app.evaluation.schema import EvalTask

    create, workspace, storage, sink, memory, _ = factory
    first, _, _ = create([call("read-1")], store=CrashAfterSave(storage, lambda cp: cp.status == "checkpointed" and cp.completed_tool_ids == ["read-1"]))
    with pytest.raises(SimulatedCrash):
        asyncio.run(first.run("Inspect source", task_id="eval-resume"))
    second, _, _ = create([ChatResponse(content="Inspection complete")])
    runner = EvaluationRunner(workspace_seed=workspace, workspace_eval=tmp_path / "eval")
    monkeypatch.setattr(runner, "_prepare_workspace", lambda task_id: workspace)
    runner._runner.run_pytest = AsyncMock(return_value=SimpleNamespace(success=True, passed=1, failed=0))
    monkeypatch.setattr("app.evaluation.runner.get_memory_manager", lambda: memory)
    adapter = SimpleNamespace(run=lambda task, task_id: second.resume_task(task_id))
    task = EvalTask(id="eval-resume", name="resume", difficulty="easy", category="review", task="Inspect source")
    result = asyncio.run(runner.run_task(task, lambda *args: adapter))
    assert result.success and not result.error
    assert result.tool_calls_count == len(result.steps) == len(result.tool_results) == 1
    assert result.verification_retries == 0 and result.files_modified == []
    assert any(e.agent_action == "task_resumed" for e in result.trace_events)
    assert any(e.agent_action == "context_compaction" and e.metadata.get("phase") == "checkpoint" for e in result.trace_events)
    assert_trace(sink, "eval-resume")
