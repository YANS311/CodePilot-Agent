"""Offline context/recovery/trace contract tests, with request snapshots."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.context import ContextBudget, ContextBudgetExceeded, ContextManager
from app.agent.context.compactor import group_messages
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.react_agent import ReActAgent
from app.agent.trace import InMemoryTraceSink
from app.agent.verification import VerificationPolicy
from app.core.llm_client import ChatResponse, ToolCallInfo
from app.models.tool import ToolResult
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.run_tests import RunTestsTool
from app.tools.write_file import WriteFileTool


@pytest.fixture
def harness(monkeypatch, tmp_path):
    router = MagicMock()
    router.route.return_value = SimpleNamespace(intent="coding", layer="rule")
    monkeypatch.setattr("app.agent.react_agent.get_intent_router", lambda: router)
    memory = MagicMock()
    memory.build_memory_context.return_value = "\nHistorical context: a retrieved solution"
    monkeypatch.setattr("app.agent.react_agent.get_memory_manager", lambda: memory)

    def create(responses, *, budget=None, execute=None, verification=None, max_calls=8, workspace="ws context"):
        registry = ToolRegistry()
        for tool in (ReadFileTool(), WriteFileTool(), RunTestsTool()):
            registry.register(tool)
        registry.execute = AsyncMock(side_effect=execute)
        manager = ContextManager(budget or ContextBudget(tool_observation_budget=200))
        requests = []
        iterator = iter(responses)

        async def chat(messages, *, tools=None, temperature=0.0):
            snapshot = deepcopy(messages)
            group_messages(snapshot)
            assert manager.estimator.estimate_messages(snapshot, tools) <= manager.budget.usable_input_tokens
            assert snapshot[1]["content"] == "Fix this exact bug"
            assert snapshot[0]["content"].startswith(SYSTEM_PROMPT)
            requests.append((snapshot, deepcopy(tools)))
            return next(iterator)

        llm = SimpleNamespace(chat=chat)
        skills = MagicMock()
        skills.match_and_load_for_task.return_value = None
        sink = InMemoryTraceSink()
        agent = ReActAgent(
            llm, registry, str(tmp_path), max_tool_calls=max_calls,
            verification_policy=verification or VerificationPolicy.disabled(),
            skill_manager_instance=skills, trace_sink=sink, context_manager=manager,
        )
        monkeypatch.setattr(agent, "_build_index_context", lambda: workspace)
        return agent, requests, sink, memory, registry

    return create


def call(call_id="read1", name="read_file", args=None):
    return ChatResponse(tool_calls=[ToolCallInfo(id=call_id, name=name, arguments=args or {"path": "bug.py"})])


def tool_result(tc, *, success=True, output="ok"):
    return ToolResult(tool_call_id=tc.id, name=tc.name, success=success, output=output)


def assert_context_trace(result, sink, task_id, requests):
    events = sink.snapshot()
    assert events == result.trace.events
    assert [event.step_id for event in events] == list(range(1, len(events) + 1))
    assert all(event.task_id == task_id for event in events)
    contexts = [event for event in events if event.agent_action == "context_compaction"]
    assert len(contexts) == len(requests)
    for event in contexts:
        assert event.tool_name is None
        assert event.tool_input == {}
        assert event.tool_output is None
        assert event.metadata["tokens_saved"] >= 0
        assert len(json.dumps(event.metadata)) < 1000
    assert events[-1].agent_action == "task_complete"


def test_large_observation_does_not_change_results_memory_or_tool_metrics(harness):
    output = json.dumps({"success": False, "stderr": "AssertionError HEAD " + "x" * 15000 + " TAIL"})
    agent, requests, sink, memory, registry = harness(
        [call(), ChatResponse(content="The evidence is in bug.py")],
        execute=lambda tc, *args, **kwargs: tool_result(tc, output=output),
    )
    result = asyncio.run(agent.run("Fix this exact bug", task_id="context-task"))
    assert len(result.tool_results[0].output) == len(output)
    assert result.steps[0].observation == output
    assert result.tool_calls_count == 1
    assert len(result.trace.steps) == 1
    assert result.wrote_file is False
    assert result.verification_retries == 0
    assert "[Tool Observation compacted]" in requests[1][0][-1]["content"]
    assert_context_trace(result, sink, "context-task", requests)
    assert sum(e.agent_action == "tool_call" for e in result.trace.events) == 1
    assert any(e.metadata.get("tool_outputs_compressed") == 1 for e in result.trace.events)
    memory.build_memory_context.assert_called_once_with("Fix this exact bug", workspace_id=agent._workspace_root)
    memory.add_task_memory.assert_called_once()
    assert memory.add_task_memory.call_args.kwargs["tool_trace"] == ["read_file"]
    assert "retrieved solution" in requests[0][0][0]["content"]


def test_verification_retry_compacts_failure_without_changing_attempts(harness):
    verifies = []

    def execute(tc, *args, **kwargs):
        if tc.name == "run_tests":
            verifies.append(tc.id)
            if len(verifies) == 1:
                return tool_result(tc, success=False, output=json.dumps({"success": False, "stderr": "AssertionError " + "x" * 25000}))
        return tool_result(tc)

    agent, requests, sink, memory, registry = harness(
        [call("write1", "write_file", {"path": "bug.py", "content": "first"}), ChatResponse(content="Attempt one"),
         call("write2", "write_file", {"path": "bug.py", "content": "fixed"}), ChatResponse(content="Attempt two")],
        execute=execute, verification=VerificationPolicy(enabled=True, max_retries=2),
    )
    result = asyncio.run(agent.run("Fix this exact bug", task_id="retry-task"))
    assert result.verification_passed
    assert result.verification_retries == 1
    assert result.tool_calls_count == 4
    assert result.wrote_file
    assert verifies == ["verify_0", "verify_1"]
    assert result.trace.status == "completed"
    verification_events = [e for e in result.trace.events if e.metadata.get("phase") == "verification"]
    assert [e.metadata["attempt"] for e in verification_events] == [1, 2]
    retry_request = requests[2][0]
    observation = next(m for m in retry_request if m.get("tool_call_id") == "verify_0")
    assert "status=failed" in observation["content"]
    assert "AssertionError" in observation["content"]
    assert len(observation["content"]) < 1000
    assert_context_trace(result, sink, "retry-task", requests)


def test_budget_exhaustion_completes_unexecuted_batch_before_final_summary(harness):
    response = call("a")
    response.tool_calls.append(ToolCallInfo(id="b", name="read_file", arguments={"path": "other.py"}))
    agent, requests, sink, _, registry = harness(
        [response, ChatResponse(content="Out of budget")], max_calls=1,
        execute=lambda tc, *args, **kwargs: tool_result(tc, output="x" * 10000),
    )
    result = asyncio.run(agent.run("Fix this exact bug", task_id="budget-task"))
    assert registry.execute.await_count == 1
    assert result.tool_calls_count == 1
    assert result.trace.status == "budget_exhausted"
    assert requests[-1][1] is None
    assert {m["tool_call_id"] for m in requests[-1][0] if m["role"] == "tool"} == {"a", "b"}
    assert any(m.get("content") == "Tool not executed: tool budget exhausted." for m in requests[-1][0])
    assert_context_trace(result, sink, "budget-task", requests)
    assert result.trace.events[-2].metadata["phase"] == "final_summary"


@pytest.mark.parametrize("answer", ["write_file('bug.py')", "测试通过，已修复"])
def test_drift_corrections_still_reach_budgeted_chat(harness, answer):
    agent, requests, sink, _, _ = harness(
        [ChatResponse(content=answer), call("write", "write_file", {"path": "bug.py", "content": "fixed"}), ChatResponse(content="done")],
        execute=lambda tc, *args, **kwargs: tool_result(tc),
    )
    result = asyncio.run(agent.run("Fix this exact bug", task_id="drift-task"))
    assert result.wrote_file
    assert result.tool_calls_count == 1
    assert len(requests) == 3
    assert any(m["role"] == "system" and m is not requests[1][0][0] for m in requests[1][0])
    assert_context_trace(result, sink, "drift-task", requests)


def test_initial_optional_sections_yield_to_recent_tool_observation(harness):
    agent, requests, sink, _, _ = harness(
        [call(), ChatResponse(content="evidence received")],
        budget=ContextBudget(max_input_tokens=5200, reserve_output_tokens=512, tool_observation_budget=500),
        workspace="Workspace listing " * 5000,
        execute=lambda tc, *args, **kwargs: tool_result(tc, output="recent evidence " * 100),
    )
    result = asyncio.run(agent.run("Fix this exact bug", task_id="optional-task"))
    assert len(requests) == 2
    assert_context_trace(result, sink, "optional-task", requests)
    assert any(
        "workspace" in e.metadata.get("context_sections_dropped", ()) + e.metadata.get("context_sections_truncated", ())
        for e in result.trace.events if e.agent_action == "context_compaction"
    )


def test_unfit_task_fails_before_llm_and_closes_trace(harness):
    agent, requests, sink, _, _ = harness([], budget=ContextBudget(max_input_tokens=300, reserve_output_tokens=100))
    with pytest.raises(ContextBudgetExceeded):
        asyncio.run(agent.run("Fix this exact bug", task_id="overflow-task"))
    assert not requests
    assert sink.snapshot()[-1].agent_action == "task_complete"
    assert sink.snapshot()[-1].execution_result == "error"
    assert sink.snapshot()[-1].metadata["error_type"] == "ContextBudgetExceeded"


def test_repo_analysis_mode_is_budgeted_and_traced(harness, monkeypatch, tmp_path):
    from app.router.intent_router import INTENT_REPO
    from app.workspace.indexer import FileEntry, WorkspaceIndex

    agent, _, sink, _, _ = harness([])
    router = MagicMock()
    router.route.return_value = SimpleNamespace(intent=INTENT_REPO, layer="rule")
    monkeypatch.setattr("app.agent.react_agent.get_intent_router", lambda: router)
    agent._index = WorkspaceIndex(root=str(tmp_path), files=[
        FileEntry(path="bug.py", module_name="bug", size=100, summary="def example(): pass\n" * 1000),
    ])
    captured = []

    async def chat(messages):
        captured.append(deepcopy(messages))
        assert agent._context_manager.estimator.estimate_messages(messages) <= agent._context_manager.budget.usable_input_tokens
        assert messages[1]["content"] == "Analyze this repository"
        return ChatResponse(content="## Project Overview\nUnknown repository")

    agent._llm.chat = chat
    result = asyncio.run(agent.run("Analyze this repository", task_id="repo-context"))
    assert len(captured) == 1
    events = sink.snapshot()
    assert all(e.task_id == "repo-context" for e in events)
    assert [e.step_id for e in events] == list(range(1, len(events) + 1))
    assert any(e.agent_action == "context_compaction" and e.metadata["phase"] == "repo_analysis" for e in events)
    assert result.trace.status == "completed"
    assert result.tool_calls_count == 0


def test_evaluation_metrics_ignore_context_events(harness, tmp_path, monkeypatch):
    from app.evaluation.runner import EvaluationRunner
    from app.evaluation.schema import EvalTask
    from app.execution.base import ExecutionResult

    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "bug.py").write_text("broken", encoding="utf-8")
    agent, requests, sink, _, _ = harness(
        [call("write", "write_file", {"path": "bug.py", "content": "fixed"}), ChatResponse(content="done")],
        verification=VerificationPolicy(enabled=True, max_retries=1),
    )

    def factory(workspace, *args):
        agent._workspace_root = workspace

        def execute(tc, *args, **kwargs):
            if tc.name == "write_file":
                from pathlib import Path
                (Path(workspace) / "bug.py").write_text("fixed", encoding="utf-8")
            return tool_result(tc)

        agent._registry.execute.side_effect = execute
        return agent

    runner = EvaluationRunner(workspace_seed=seed, workspace_eval=tmp_path / "eval")
    runner._runner.run_pytest = AsyncMock(return_value=ExecutionResult(success=True, passed=1))
    monkeypatch.setattr("app.evaluation.runner.get_memory_manager", lambda: MagicMock())
    task = EvalTask(id="context-eval", name="Context eval", task="Fix this exact bug", difficulty="easy", category="bug-fix")
    result = asyncio.run(runner.run_task(task, factory))
    assert result.success
    assert result.tool_calls_count == 2
    assert [s.tool_name for s in result.steps] == ["write_file", "run_tests"]
    assert result.files_modified == ["bug.py"]
    assert result.verification_passed
    assert result.verification_retries == 0
    assert any(e.agent_action == "context_compaction" for e in result.trace_events)
    assert [e.step_id for e in result.trace_events] == list(range(1, len(result.trace_events) + 1))
    assert all(e.task_id == "context-eval" for e in result.trace_events)
    unified = result.to_unified()
    assert unified["metrics"]["tool_calls"] == 2
    assert unified["tools_used"] == ["write_file", "run_tests"]
    assert any(e["action"] == "context_compaction" for e in unified["execution_trace"])
