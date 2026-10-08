"""Synthetic compression/evidence experiments, explicitly not model performance."""

from dataclasses import asdict
import json
import time

from app.agent.context import ContextBudget, ContextBudgetExceeded, ContextManager
from app.agent.context.compactor import group_messages
from app.evaluation.profiles import PassThroughContextManager


def exchange(index, name, output):
    return [{"role": "assistant", "content": "", "tool_calls": [{"id": str(index), "type": "function", "function": {"name": name, "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": str(index), "content": output}]


def run_context_stress():
    budget = ContextBudget(max_input_tokens=12000, reserve_output_tokens=1000, tool_observation_budget=200, history_budget=9000)
    base = [{"role": "system", "content": "Mandatory safety policy"}, {"role": "user", "content": "Inspect failing arithmetic test"}]
    payload = "EVIDENCE_HEAD arithmetic.py:2\n" + "noise " * 4000 + "\nEVIDENCE_TAIL AssertionError"
    cases = {
        "long_read": base + exchange(1, "read_file", payload),
        "pytest_failure": base + exchange(1, "run_tests", json.dumps({"success": False, "stderr": payload})),
        "repeated_search": base + sum((exchange(i, "search_code", payload) for i in range(3)), []),
        "old_observations": base + sum((exchange(i, "read_file", payload) for i in range(7)), []),
        "multi_tool": base + [
            {"role": "assistant", "tool_calls": [exchange(i, "read_file", payload)[0]["tool_calls"][0] for i in range(2)]},
            *[exchange(i, "read_file", payload)[1] for i in range(2)],
        ],
        "near_limit": base + exchange(1, "read_file", "EVIDENCE_HEAD " + "x" * 32500 + " EVIDENCE_TAIL"),
    }
    rows = []
    for scenario, messages in cases.items():
        for enabled in (False, True):
            manager = ContextManager(budget) if enabled else PassThroughContextManager(budget)
            before = manager.estimator.estimate_messages(messages)
            started = time.perf_counter()
            try:
                result = manager.compact_messages(messages)
                group_messages(result.messages)
                output = " ".join(m.get("content", "") or "" for m in result.messages)
                rows.append({"scenario": scenario, "compaction": enabled, "status": "MEASURED",
                             "before_estimated_input_tokens": before, "after_estimated_input_tokens": result.stats.estimated_tokens_after,
                             "local_tokens_saved": result.stats.tokens_saved, "retained_ratio": result.stats.compression_ratio,
                             "compacted_observations": result.stats.tool_outputs_compressed,
                             "protocol_valid": True, "evidence_head_retained": "EVIDENCE_HEAD" in output,
                             "evidence_tail_retained": "EVIDENCE_TAIL" in output,
                             "duration_ms": (time.perf_counter() - started) * 1000})
            except ContextBudgetExceeded:
                rows.append({"scenario": scenario, "compaction": enabled, "status": "CONTEXT_BUDGET_FAILURE",
                             "before_estimated_input_tokens": before, "after_estimated_input_tokens": None,
                             "local_tokens_saved": None, "retained_ratio": None,
                             "protocol_valid": True, "evidence_head_retained": None, "evidence_tail_retained": None,
                             "duration_ms": (time.perf_counter() - started) * 1000})
    return {"label": "SYNTHETIC deterministic compression, not LLM task success", "estimator": "UTF-8 bytes / 3 rounded up",
            "budget": asdict(budget), "rows": rows}
