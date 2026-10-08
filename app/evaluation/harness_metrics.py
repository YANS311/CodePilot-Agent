"""Trace-authoritative measurements; null means missing, never fabricated zero."""

from collections import Counter
import json
from statistics import mean, pstdev
from types import SimpleNamespace

from app.evaluation.metrics import compute_metrics
from app.evaluation.runner import EvaluationRunner


def task_metrics(result):
    events = EvaluationRunner._trace_events(SimpleNamespace(trace=SimpleNamespace(events=result.trace_events)), result.task_id)
    tools = [e for e in events if e.agent_action == "tool_call" and e.tool_name]
    requests = [e for e in events if e.agent_action == "llm_request"]
    context = [e for e in events if e.agent_action in {"context_build", "context_compaction"}]
    verify = [e for e in tools if e.tool_name == "run_tests" and e.metadata.get("phase") == "verification"]
    counts = Counter((e.tool_name, json.dumps(e.tool_input, sort_keys=True)) for e in tools if e.tool_name in {"read_file", "search_code"})
    terminal = next((e.execution_result for e in reversed(events) if e.agent_action == "task_complete"), "unknown")
    failures = [e.metadata.get("error_type") for e in events if e.agent_action == "task_complete"]
    usage = [e.metadata.get("provider_usage", {}) for e in events if e.agent_action == "llm_response"]
    usage_present = bool(usage) and len(usage) == len(requests) and all(
        "prompt_tokens" in item and "completion_tokens" in item for item in usage)
    ratios = [e.metadata["compression_ratio"] for e in context if "compression_ratio" in e.metadata]
    return {
        "success": result.success, "terminal_status": terminal,
        "executed_tool_calls": len(tools),
        "duplicate_read_search_calls": sum(n - 1 for n in counts.values()),
        "task_latency_ms": result.duration_ms,
        "llm_requests": len(requests),
        "estimated_input_tokens_per_call": [e.metadata["estimated_input_tokens"] for e in requests],
        "total_estimated_input_tokens": sum(e.metadata["estimated_input_tokens"] for e in requests),
        "local_compaction_tokens_saved": sum(e.metadata.get("tokens_saved", 0) for e in context),
        "retained_context_ratio_mean": mean(ratios) if ratios else None,
        "compacted_observations": sum(e.metadata.get("tool_outputs_compressed", 0) for e in context),
        "context_budget_failure": "ContextBudgetExceeded" in failures,
        "verification_attempts": len(verify), "verification_retries": max(0, len(verify) - 1),
        "verification_failures": sum(e.execution_result != "success" for e in verify),
        "verification_passed": verify[-1].execution_result == "success" if verify else None,
        "recovered_test_failure": bool(verify and verify[0].execution_result != "success" and verify[-1].execution_result == "success"),
        "verification_latency_ms": sum(e.duration_ms for e in verify),
        "provider_input_tokens": sum(u["prompt_tokens"] for u in usage) if usage_present else None,
        "provider_output_tokens": sum(u["completion_tokens"] for u in usage) if usage_present else None,
        "files_modified": result.files_modified,
    }


def aggregate(results, tasks, measurements, *, simulated):
    if not results:
        return {"status": "NOT RUN", "trial_count": 0, "task_success_rate": None, "pass_at_1": None}
    existing = compute_metrics(results, tasks)
    latencies = [m["task_latency_ms"] for m in measurements]
    verified = [m for m in measurements if m["verification_attempts"]]
    return {
        "status": "SIMULATED" if simulated else "MEASURED", "trial_count": len(results),
        "task_success_rate": existing.task_success_rate,
        "task_failure_rate": 1 - existing.task_success_rate,
        # Iterative Harness runs are not independent one-candidate samples.
        "pass_at_1": None,
        "verification_pass_rate": sum(m["verification_passed"] for m in verified) / len(verified) if verified else None,
        "avg_executed_tool_calls": mean(m["executed_tool_calls"] for m in measurements),
        "avg_llm_requests": mean(m["llm_requests"] for m in measurements),
        "avg_total_estimated_input_tokens": mean(m["total_estimated_input_tokens"] for m in measurements),
        "avg_task_latency_ms": mean(latencies), "latency_population_stddev_ms": pstdev(latencies),
        "terminal_status_counts": dict(Counter(m["terminal_status"] for m in measurements)),
        "completed_tasks": sum(m["terminal_status"] == "completed" for m in measurements),
        "budget_exhaustions": sum(m["terminal_status"] == "budget_exhausted" for m in measurements),
        "cancelled_tasks": sum(m["terminal_status"] == "cancelled" for m in measurements),
        "runtime_errors": sum(m["terminal_status"] == "error" for m in measurements),
        "evaluation_errors": sum(m.get("evaluation_error", False) for m in measurements),
        "task_timeouts": sum(m.get("evaluation_timeout", False) for m in measurements),
        "verification_failures": sum(m["verification_failures"] for m in measurements),
        "context_budget_failures": sum(m["context_budget_failure"] for m in measurements),
        "recovered_test_failures": sum(m["recovered_test_failure"] for m in measurements),
    }
