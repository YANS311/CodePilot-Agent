import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent.context import ContextBudget, ContextBudgetExceeded
from app.agent.react_agent import ReActAgent
from app.agent.trace import TraceEvent
from app.core.llm_client import ChatResponse
from app.evaluation.context_stress import run_context_stress
from app.evaluation.harness_metrics import aggregate, task_metrics
from app.evaluation.harness_runner import HarnessConfig, copy_seed, registry, run_ablations
from app.evaluation.manifest import audit_datasets, load_manifest
from app.evaluation.profiles import PROFILES, BenchmarkMemory, PassThroughContextManager
from app.evaluation.schema import EvalResult
from app.tools.registry import ToolRegistry
from app.models.tool import ToolCall
from app.security.tool_guardrail import ToolGuardrail


def test_profiles_cumulative_and_security_identical():
    assert [(p.memory, p.context, p.verification) for p in PROFILES] == [
        (False, False, False), (True, False, False), (True, True, False), (True, True, True)]
    for profile in PROFILES:
        policy = profile.permission()
        assert policy.enforce_workspace_boundary and not policy.allow_network
        assert policy.check_tool_permission("run_tests")[0]
        assert not policy.check_tool_permission("http_fetch")[0]
        assert profile.verification_policy("tests/test_a.py").test_command == "tests/test_a.py"


def test_memory_isolation_and_seeded_vs_cold():
    one = BenchmarkMemory(retrieval=True)
    two = BenchmarkMemory(retrieval=True, state="cold")
    disabled = BenchmarkMemory(retrieval=False)
    assert one.build_memory_context("arithmetic regression")
    assert not two.build_memory_context("arithmetic regression")
    assert not disabled.build_memory_context("arithmetic regression")
    one.add_task_memory("unrelated new data", "trial result", True)
    assert len(two.get_task_memory()) == 0
    assert len(disabled.get_task_memory()) == 1
    assert disabled.retrieval_calls == 0


def test_pass_through_preserves_messages_and_refuses_overflow():
    manager = PassThroughContextManager(ContextBudget(max_input_tokens=1000, reserve_output_tokens=100, system_budget=200))
    initial = manager.build_initial_context(system="Mandatory safety", task="Fix arithmetic", memory="Prior knowledge")
    saved = deepcopy(initial.messages)
    result = manager.compact_messages(initial.messages, initial_context=initial)
    assert result.messages == saved and initial.messages == saved
    assert result.stats.tokens_saved == 0
    with pytest.raises(ContextBudgetExceeded):
        manager.compact_messages(saved + [{"role": "assistant", "content": "x" * 10000}])


def test_manifest_actual_counts_and_targets(tmp_path):
    manifest = audit_datasets()
    assert manifest["counts_by_source"] == {
        "evaluation/tasks.json": 30, "evaluation/stress_tasks.json": 10,
        "benchmarks/real_world/tasks.json": 15, "evaluation/security_tasks.json": 20}
    assert manifest["missing_test_targets"] == []
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert len(load_manifest(path)) == 75
    assert [t.task_id for t in load_manifest(path)] == [t["task_id"] for t in manifest["tasks"]]
    manifest["tasks"].append(manifest["tasks"][0])
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_manifest(path)


def test_trace_measurements_exclude_lifecycle_and_keep_null_usage():
    events = [
        TraceEvent("t", 1, "checkpoint_saved", metadata={"path": "file.py"}),
        TraceEvent("t", 2, "task_resumed"),
        TraceEvent("t", 3, "context_compaction", metadata={"tokens_saved": 90, "compression_ratio": .1, "tool_outputs_compressed": 1}),
        TraceEvent("t", 4, "llm_request", metadata={"estimated_input_tokens": 120}),
        TraceEvent("t", 5, "llm_response", metadata={"provider_usage": {}}),
        TraceEvent("t", 6, "tool_call", tool_name="run_tests", execution_result="error", metadata={"phase": "verification"}),
        TraceEvent("t", 7, "tool_call", tool_name="run_tests", execution_result="success", metadata={"phase": "verification"}),
        TraceEvent("t", 8, "task_complete", execution_result="completed"),
    ]
    result = EvalResult(task_id="t", success=True, trace_events=events)
    measured = task_metrics(result)
    assert measured["executed_tool_calls"] == 2
    assert measured["verification_attempts"] == 2 and measured["verification_retries"] == 1
    assert measured["total_estimated_input_tokens"] == 120
    assert measured["local_compaction_tokens_saved"] == 90
    assert measured["provider_input_tokens"] is None and measured["files_modified"] == []
    summary = aggregate([result], [], [measured], simulated=True)
    assert summary["status"] == "SIMULATED" and summary["pass_at_1"] is None
    assert summary["verification_pass_rate"] == 1


@pytest.mark.parametrize("change", ["ownership", "ordering"])
def test_metrics_reject_malformed_trace(change):
    events = [TraceEvent("t", 1, "task_start"), TraceEvent("other" if change == "ownership" else "t", 1 if change == "ordering" else 2, "task_complete")]
    with pytest.raises(ValueError):
        task_metrics(EvalResult(task_id="t", trace_events=events))


def test_zero_results_are_not_fabricated_performance():
    summary = aggregate([], [], [], simulated=False)
    assert summary == {"status": "NOT RUN", "trial_count": 0, "task_success_rate": None, "pass_at_1": None}


def test_empty_live_selection_never_constructs_model():
    result = asyncio.run(run_ablations(HarnessConfig(), entries=[],
                                      llm_factory=lambda: pytest.fail("no task, no model")))
    assert result["trials"] == [] and result["selected_tasks"] == []
    assert all(s["status"] == "NOT RUN" for s in result["summary"].values())


def test_partial_provider_usage_is_not_reported_as_complete():
    events = [TraceEvent("t", 1, "llm_request", metadata={"estimated_input_tokens": 10}),
              TraceEvent("t", 2, "llm_response", metadata={"provider_usage": {"prompt_tokens": 10, "completion_tokens": 2}}),
              TraceEvent("t", 3, "llm_request", metadata={"estimated_input_tokens": 20}),
              TraceEvent("t", 4, "task_complete", execution_result="error")]
    result = task_metrics(EvalResult(task_id="t", trace_events=events))
    assert result["llm_requests"] == 2 and result["total_estimated_input_tokens"] == 30
    assert result["provider_input_tokens"] is None and result["provider_output_tokens"] is None


def test_live_seed_excludes_untracked_artifacts(tmp_path, monkeypatch):
    from app.evaluation import harness_runner
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "source.py").write_text("versioned source", encoding="utf-8")
    (seed / "uploaded_answer.py").write_text("untracked answer", encoding="utf-8")
    monkeypatch.setattr(harness_runner, "ROOT", tmp_path)
    monkeypatch.setattr(harness_runner.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="seed/source.py\n"))
    destination = tmp_path / "destination"
    copy_seed(seed, destination, simulated=False)
    assert sorted(p.name for p in destination.iterdir()) == ["source.py"]


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.id)
@pytest.mark.parametrize("tool_name", ["write_file", "code_edit"])
@pytest.mark.parametrize("absolute", [False, True])
def test_all_profiles_refuse_workspace_escape(profile, tool_name, absolute, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = asyncio.run(registry().execute(
        ToolCall(id="escape", name=tool_name, arguments={
            "path": str(tmp_path / "outside.py") if absolute else "../outside.py", "content": "unsafe",
            "old": "before", "new": "after"}),
        str(workspace), guardrail=ToolGuardrail(), permission_policy=profile.permission()))
    assert not result.success and not (tmp_path / "outside.py").exists()


def test_context_synthetic_evidence_and_protocol():
    experiment = run_context_stress()
    assert len(experiment["rows"]) == 12
    assert "not LLM task success" in experiment["label"]
    compacted = [r for r in experiment["rows"] if r["compaction"]]
    assert all(r["protocol_valid"] and r["status"] == "MEASURED" for r in compacted)
    assert all(r["evidence_head_retained"] and r["evidence_tail_retained"] for r in compacted)
    assert all(r["after_estimated_input_tokens"] < r["before_estimated_input_tokens"] for r in compacted)


def test_llm_requests_trace_estimates_usage_and_injected_memory(tmp_path):
    memory = BenchmarkMemory(retrieval=False, state="cold")
    llm = SimpleNamespace(chat=AsyncMock(return_value=ChatResponse(content="Inspection ended", raw={"usage": {"prompt_tokens": 42, "completion_tokens": 7, "authorization": "never saved"}})))
    agent = ReActAgent(llm, ToolRegistry(), str(tmp_path), memory_manager=memory)
    result = asyncio.run(agent.run("Fix arithmetic regression", task_id="measure"))
    request = next(e for e in result.trace.events if e.agent_action == "llm_request")
    assert request.metadata["estimated_input_tokens"] > 0
    response = next(e for e in result.trace.events if e.agent_action == "llm_response")
    assert response.metadata["provider_usage"] == {"prompt_tokens": 42, "completion_tokens": 7}
    assert len(memory.get_task_memory()) == 1
