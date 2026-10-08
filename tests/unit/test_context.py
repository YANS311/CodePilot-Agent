from dataclasses import replace
import json

import pytest

from app.agent.context import (
    ContextBudget, ContextBudgetExceeded, ContextManager, ContextProtocolError,
    ContextStats, LightweightTokenEstimator,
)
from app.agent.context.compactor import group_messages


def exchange(ids=("tc1",), output="ok", name="run_tests"):
    return [
        {"role": "assistant", "content": "Inspect evidence", "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}
            for call_id in ids
        ]},
        *[{"role": "tool", "tool_call_id": call_id, "content": output} for call_id in ids],
    ]


def base():
    return [{"role": "system", "content": "SAFETY: only edit workspace"},
            {"role": "user", "content": "Fix the current task exactly"}]


class TestBudgetAndEstimation:
    @pytest.mark.parametrize("kwargs", [
        {"max_input_tokens": 100, "reserve_output_tokens": 100},
        {"memory_budget": -1}, {"skill_budget": True}, {"history_budget": 1.2},
    ])
    def test_invalid_budget(self, kwargs):
        with pytest.raises(ValueError):
            ContextBudget(**kwargs)

    def test_usable_budget(self):
        assert ContextBudget(max_input_tokens=1000, reserve_output_tokens=100).usable_input_tokens == 900

    def test_estimates_deterministically_include_wire_fields_and_schemas(self):
        estimator = LightweightTokenEstimator()
        assert estimator.estimate_text("") == 0
        assert estimator.estimate_text("abcd") == 2
        assert estimator.estimate_text("修复") == 2
        messages = base() + exchange()
        tools = [{"type": "function", "function": {"name": "read_file", "description": "x" * 1000}}]
        assert estimator.estimate_messages(messages, tools) > estimator.estimate_messages(messages)
        assert estimator.estimate_messages(messages) == estimator.estimate_messages(messages)

    def test_statistics(self):
        stats = ContextStats(100, 25, 10, 4, tool_outputs_compressed=2)
        assert stats.tokens_saved == 75
        assert stats.compression_ratio == .25
        assert stats.to_metadata()["compaction_triggered"] is True
        assert ContextStats(0, 0, 0, 0).compression_ratio == 1
        assert ContextStats(1, 2, 1, 1).tokens_saved == 0


class TestInitialContext:
    def test_under_budget_preserves_legacy_assembly(self):
        manager = ContextManager()
        result = manager.build_initial_context(system="safe", task="task", workspace="ws", memory="mem", skill="skill")
        assert result.messages == [{"role": "system", "content": "safe\n\nwsmemskill"}, {"role": "user", "content": "task"}]
        assert result.stats.tokens_saved == 0

    def test_section_priority_and_total_budget(self):
        budget = ContextBudget(max_input_tokens=550, reserve_output_tokens=50, skill_budget=300, memory_budget=300, workspace_budget=300)
        manager = ContextManager(budget)
        result = manager.build_initial_context(system="SAFETY", task="CURRENT", skill="s" * 600, memory="m" * 600, workspace="w" * 600)
        assert result.messages[1]["content"] == "CURRENT"
        assert result.messages[0]["content"].startswith("SAFETY")
        assert "s" * 600 in result.messages[0]["content"]
        assert "workspace" in result.stats.context_sections_dropped + result.stats.context_sections_truncated
        assert result.stats.estimated_tokens_after <= budget.usable_input_tokens
        assert result.stats.tokens_saved > 0

    def test_optional_sections_zero_caps(self):
        result = ContextManager(ContextBudget(skill_budget=0, memory_budget=0, workspace_budget=0)).build_initial_context(
            system="safe", task="task", skill="skill", memory="memory", workspace="workspace",
        )
        assert result.stats.context_sections_dropped == ("skill", "memory", "workspace")

    @pytest.mark.parametrize("field", ["task", "system", "tools"])
    def test_oversized_mandatory_payload_fails_explicitly(self, field):
        manager = ContextManager(ContextBudget(max_input_tokens=100, reserve_output_tokens=10))
        kwargs = {"system": "safe", "task": "task"}
        kwargs[field] = [{"description": "x" * 2000}] if field == "tools" else "x" * 2000
        with pytest.raises(ContextBudgetExceeded):
            manager.build_initial_context(**kwargs)

    def test_system_cap_does_not_truncate_safety(self):
        with pytest.raises(ContextBudgetExceeded, match="system_budget"):
            ContextManager(ContextBudget(system_budget=1)).build_initial_context(system="SAFETY CONTRACT", task="task")

    def test_optional_sections_can_release_space_for_later_tool_results(self):
        manager = ContextManager(ContextBudget(max_input_tokens=600, reserve_output_tokens=100))
        initial = manager.build_initial_context(system="SAFETY", task="CURRENT", workspace="w" * 900, skill="s" * 150)
        messages = initial.messages + exchange(output="Recent AssertionError evidence " * 15)
        result = manager.compact_messages(messages, initial_context=initial)
        assert result.messages[0]["content"].startswith("SAFETY")
        assert result.messages[1]["content"] == "CURRENT"
        assert "s" * 150 in result.messages[0]["content"]
        assert result.stats.estimated_tokens_after <= 500
        assert "workspace" in result.stats.context_sections_dropped + result.stats.context_sections_truncated
        assert result.messages[-1]["content"] == messages[-1]["content"]
        assert initial.optional_sections["workspace"] == "w" * 900


class TestSettings:
    def test_default_context_settings(self):
        from app.core.config import Settings
        settings = Settings(_env_file=None)
        assert settings.context_max_input_tokens > settings.context_reserve_output_tokens
        assert settings.context_reserve_output_tokens >= settings.llm_max_tokens

    @pytest.mark.parametrize("kwargs", [
        {"context_max_input_tokens": 4096},
        {"context_reserve_output_tokens": 100},
        {"context_tool_output_limit": -1},
    ])
    def test_invalid_settings_fail_fast(self, kwargs):
        from app.core.config import Settings
        with pytest.raises(ValueError):
            Settings(_env_file=None, **kwargs)


class TestCompaction:
    def test_under_budget_is_unchanged_and_not_mutated(self):
        messages = base() + exchange() + [{"role": "assistant", "content": "done"}]
        original = json.dumps(messages)
        result = ContextManager().compact_messages(messages)
        assert result.messages == messages
        assert json.dumps(messages) == original
        assert result.messages is not messages
        assert result.stats.tokens_saved == 0
        assert not result.stats.compaction_triggered

    def test_large_tool_output_keeps_failure_and_head_tail(self):
        output = json.dumps({"success": False, "stderr": "HEAD AssertionError " + "x" * 9000 + " TAIL evidence"})
        messages = base() + exchange(output=output)
        manager = ContextManager(ContextBudget(tool_observation_budget=600))
        result = manager.compact_messages(messages)
        observation = result.messages[-1]["content"]
        assert "[Tool Observation compacted]" in observation
        assert "tool=run_tests" in observation
        assert "status=failed" in observation
        assert "HEAD AssertionError" in observation
        assert "TAIL evidence" in observation
        assert result.stats.tool_outputs_compressed == 1
        assert result.stats.tokens_saved > 0
        assert result.stats.compression_ratio == result.stats.estimated_tokens_after / result.stats.estimated_tokens_before
        assert len(json.dumps(result.stats.to_metadata())) < 1000
        group_messages(result.messages)

    def test_recent_evidence_preferred_and_old_groups_evicted_atomically(self):
        messages = base() + exchange(("old1", "old2"), "old " * 600) + [
            {"role": "assistant", "content": "old low-value " * 300},
        ] + exchange(("new1", "new2"), "recent evidence")
        manager = ContextManager(ContextBudget(max_input_tokens=650, reserve_output_tokens=100, recent_message_count=3))
        result = manager.compact_messages(messages)
        assert result.messages[:2] == base()
        assert result.messages[-3:] == messages[-3:]
        assert not any(m.get("tool_call_id", "").startswith("old") for m in result.messages)
        assert result.stats.messages_after < result.stats.messages_before
        assert result.stats.estimated_tokens_after <= 550
        group_messages(result.messages)

    def test_duplicate_and_history_budget(self):
        messages = base() + [{"role": "assistant", "content": "redundant " * 100}] * 8
        result = ContextManager(ContextBudget(history_budget=400)).compact_messages(messages)
        assert result.messages[:2] == base()
        assert result.stats.messages_after < len(messages)

    def test_latest_system_correction_is_preserved(self):
        correction = {"role": "system", "content": "Use real tool calls, do not pretend work is done"}
        result = ContextManager(ContextBudget(max_input_tokens=400, reserve_output_tokens=50)).compact_messages(
            base() + [{"role": "assistant", "content": "noise" * 1000}, correction],
        )
        assert result.messages == base() + [correction]

    def test_multiple_tool_calls_remain_valid_after_clipping(self):
        result = ContextManager(ContextBudget(tool_observation_budget=100)).compact_messages(base() + exchange(("a", "b", "c"), "log" * 9000))
        assert len(result.messages[-4]["tool_calls"]) == 3
        assert {m["tool_call_id"] for m in result.messages[-3:]} == {"a", "b", "c"}
        assert result.stats.tool_outputs_compressed == 3
        group_messages(result.messages)

    def test_latest_tool_evidence_survives_a_following_budget_reminder(self):
        messages = base() + [{"role": "assistant", "content": "old noise" * 1000}] + exchange(output="critical evidence") + [
            {"role": "system", "content": "Two tool calls remain"},
        ]
        manager = ContextManager(ContextBudget(max_input_tokens=400, reserve_output_tokens=50, recent_message_count=0))
        result = manager.compact_messages(messages)
        assert any(m.get("tool_call_id") == "tc1" and m["content"] == "critical evidence" for m in result.messages)
        assert result.messages[-1] == messages[-1]
        group_messages(result.messages)

    def test_zero_tool_cap_still_allows_plain_history_to_shrink(self):
        manager = ContextManager(ContextBudget(max_input_tokens=300, reserve_output_tokens=50, tool_observation_budget=0))
        result = manager.compact_messages(base() + [{"role": "assistant", "content": "x" * 10000}])
        assert result.messages[:2] == base()
        assert result.stats.estimated_tokens_after <= 250

    def test_first_task_and_latest_user_request_are_both_preserved(self):
        latest = {"role": "user", "content": "Keep the API backwards compatible"}
        manager = ContextManager(ContextBudget(max_input_tokens=300, reserve_output_tokens=50))
        result = manager.compact_messages(base() + [{"role": "assistant", "content": "noise" * 1000}, latest])
        assert result.messages == base() + [latest]

    def test_reclaimed_sections_do_not_reappear_on_repeated_calls(self):
        manager = ContextManager(ContextBudget(max_input_tokens=600, reserve_output_tokens=100))
        initial = manager.build_initial_context(system="SAFETY", task="CURRENT", workspace="w" * 900)
        first = manager.compact_messages(initial.messages + exchange(output="evidence " * 60), initial_context=initial)
        second = manager.compact_messages(first.messages, initial_context=first)
        assert second.messages == first.messages
        assert second.optional_sections == first.optional_sections
        assert second.stats.tokens_saved == 0

    def test_huge_latest_arguments_fail_without_protocol_corruption(self):
        messages = base() + exchange()
        messages[-2]["tool_calls"][0]["function"]["arguments"] = json.dumps({"content": "x" * 9000})
        with pytest.raises(ContextBudgetExceeded):
            ContextManager(ContextBudget(max_input_tokens=400, reserve_output_tokens=50)).compact_messages(messages)
        assert len(messages[-2]["tool_calls"][0]["function"]["arguments"]) > 9000

    @pytest.mark.parametrize("messages", [
        base() + [{"role": "tool", "tool_call_id": "orphan", "content": "ok"}],
        base() + exchange()[:-1],
        base() + exchange(("a", "b"))[:-1],
        base() + exchange(("a", "a")),
        base() + exchange() + exchange(),
        base() + [exchange()[0], {"role": "system", "content": "interrupt"}, exchange()[1]],
    ])
    def test_invalid_tool_protocol_is_rejected(self, messages):
        with pytest.raises(ContextProtocolError):
            ContextManager().compact_messages(messages)

    @pytest.mark.parametrize("cap", [0, 1, 10, 100, 800])
    def test_tool_limits_are_deterministic(self, cap):
        manager = ContextManager(replace(ContextBudget(), tool_observation_budget=cap))
        messages = base() + exchange(output="修复\n" * 5000)
        first = manager.compact_messages(messages)
        assert first == manager.compact_messages(messages)
        assert manager.estimator.estimate_text(first.messages[-1]["content"]) <= cap
        assert first.stats.tokens_saved >= 0

    @pytest.mark.parametrize("output", ["a" * 301, "\\" * 301, "\n" * 301, "修复" * 101])
    def test_compaction_marker_never_increases_serialized_estimate(self, output):
        manager = ContextManager(ContextBudget(tool_observation_budget=100))
        result = manager.compact_messages(base() + exchange(output=output))
        assert result.stats.estimated_tokens_after <= result.stats.estimated_tokens_before
        assert result.stats.compression_ratio <= 1.0
        assert result.stats.tokens_saved == result.stats.estimated_tokens_before - result.stats.estimated_tokens_after
