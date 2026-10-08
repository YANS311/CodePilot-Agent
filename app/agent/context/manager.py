"""Per-LLM-call selection and compaction; consumes but never owns Memory."""

from copy import deepcopy
import json
from typing import Any

from .budget import LightweightTokenEstimator, TokenEstimator
from .compactor import clip_text, group_messages
from .models import ContextBudget, ContextBudgetExceeded, ContextBuildResult, ContextStats


class ContextManager:
    def __init__(self, budget: ContextBudget | None = None, estimator: TokenEstimator | None = None):
        self.budget = budget or ContextBudget()
        self.estimator = estimator or LightweightTokenEstimator()

    def build_initial_context(
        self, *, system: str, task: str, workspace: str = "", memory: str = "",
        skill: str = "", tools: list[dict] | None = None,
    ) -> ContextBuildResult:
        sections = {"workspace": workspace, "memory": memory, "skill": skill}

        def assemble(parts: dict[str, str]) -> list[dict[str, Any]]:
            return [
                {"role": "system", "content": system + "\n\n" + parts.get("workspace", "")
                 + parts.get("memory", "") + parts.get("skill", "")},
                {"role": "user", "content": task},
            ]

        before = self.estimator.estimate_messages(assemble(sections), tools)
        chosen: dict[str, str] = {}
        if self.estimator.estimate_text(system) > self.budget.system_budget:
            raise ContextBudgetExceeded("Core system instructions exceed system_budget; increase it, do not truncate safety")
        if self.estimator.estimate_messages(assemble(chosen), tools) > self.budget.usable_input_tokens:
            raise ContextBudgetExceeded("Core system instructions, task and tool schemas exceed context budget")
        dropped, truncated = [], []
        # Allocation priority differs from serialization order for compatibility.
        for name in ("skill", "memory", "workspace"):
            text = sections[name]
            if not text:
                continue
            cap = getattr(self.budget, f"{name}_budget")
            candidate = clip_text(text, cap, self.estimator)
            chosen[name] = candidate
            if self.estimator.estimate_messages(assemble(chosen), tools) > self.budget.usable_input_tokens:
                low, high = 0, cap
                while low < high:
                    mid = (low + high + 1) // 2
                    chosen[name] = clip_text(text, mid, self.estimator)
                    if self.estimator.estimate_messages(assemble(chosen), tools) <= self.budget.usable_input_tokens:
                        low = mid
                    else:
                        high = mid - 1
                chosen[name] = clip_text(text, low, self.estimator)
            if not chosen[name]:
                dropped.append(name)
            elif chosen[name] != text:
                truncated.append(name)
        messages = assemble(chosen)
        return ContextBuildResult(messages, ContextStats(
            before, self.estimator.estimate_messages(messages, tools), 2, 2,
            context_sections_dropped=tuple(dropped), context_sections_truncated=tuple(truncated),
        ), core_system=system, optional_sections=chosen)

    def compact_messages(
        self, messages: list[dict[str, Any]], *, tools: list[dict] | None = None,
        initial_context: ContextBuildResult | None = None,
    ) -> ContextBuildResult:
        groups = group_messages(messages)
        working = deepcopy(messages)
        before = self.estimator.estimate_messages(messages, tools)
        first_system = next((i for i, m in enumerate(messages) if m.get("role") == "system"), None)
        users = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        systems = [i for i, m in enumerate(messages) if m.get("role") == "system"]
        protected = set(users[:1] + users[-1:] + systems[:1] + systems[-1:])
        if groups:
            protected.update(groups[-1].indices)
        latest_tool_group = next((group for group in reversed(groups) if group.tool_names), None)
        if latest_tool_group is not None:
            protected.update(latest_tool_group.indices)
        compressed: set[int] = set()
        truncated: set[str] = set()
        dropped: set[str] = set()
        sections = dict(initial_context.optional_sections) if initial_context else {}
        for group in groups:
            for i in group.indices:
                message = working[i]
                if message.get("role") == "tool" and isinstance(message.get("content"), str):
                    original = message["content"]
                    message["content"] = clip_text(
                        original, self.budget.tool_observation_budget, self.estimator,
                        tool_name=group.tool_names[message["tool_call_id"]],
                    )
                    if original != message["content"]:
                        compressed.add(i)

        retained = set(range(len(messages)))

        def current() -> list[dict[str, Any]]:
            return [working[i] for i in sorted(retained)]

        def fits() -> bool:
            transcript = current()
            history = [working[i] for i in sorted(retained) if i != first_system and i not in users[:1]]
            return (
                self.estimator.estimate_messages(transcript, tools) <= self.budget.usable_input_tokens
                and (not history or self.estimator.estimate_messages(history) <= self.budget.history_budget)
            )

        # Duplicate non-protocol history is the cheapest evidence to discard.
        seen: set[str] = set()
        for group in reversed(groups):
            if len(group.indices) != 1 or group.tool_names:
                continue
            i = group.indices[0]
            key = json.dumps(working[i], sort_keys=True, ensure_ascii=False)
            if key in seen and i not in protected and not fits():
                retained.remove(i)
            seen.add(key)

        recent_start = max(0, len(messages) - self.budget.recent_message_count)
        candidates = sorted(groups, key=lambda g: (max(g.indices) >= recent_start, min(g.indices)))
        for group in candidates:
            if fits():
                break
            if protected.intersection(group.indices) or max(group.indices) >= recent_start:
                continue
            retained.difference_update(group.indices)

        # Reclaim optional initial sections before evicting recent tool evidence.
        if initial_context is not None and initial_context.core_system is not None and first_system is not None:
            def update_system() -> None:
                working[first_system]["content"] = initial_context.core_system + "\n\n" + "".join(
                    sections.get(name, "") for name in ("workspace", "memory", "skill")
                )

            for name in ("workspace", "memory", "skill"):
                if fits():
                    break
                original = sections.get(name, "")
                if not original:
                    continue
                sections[name] = ""
                update_system()
                if fits():
                    low, high = 0, self.estimator.estimate_text(original)
                    while low < high:
                        mid = (low + high + 1) // 2
                        sections[name] = clip_text(original, mid, self.estimator)
                        update_system()
                        if fits():
                            low = mid
                        else:
                            high = mid - 1
                    sections[name] = clip_text(original, low, self.estimator)
                    update_system()
                if not sections[name]:
                    dropped.add(name)
                elif sections[name] != original:
                    truncated.add(name)

        for group in candidates:
            if fits():
                break
            if not protected.intersection(group.indices):
                retained.difference_update(group.indices)

        # If even the recent evidence is oversized, shrink contents, never IDs/arguments.
        cap = max(1, self.budget.tool_observation_budget)
        while not fits() and cap > 0:
            cap //= 2
            for group in groups:
                for i in group.indices:
                    if i not in retained or working[i].get("role") in {"system", "user"}:
                        continue
                    message = working[i]
                    if not isinstance(message.get("content"), str):
                        continue
                    name = group.tool_names.get(message.get("tool_call_id"))
                    original = messages[i].get("content", "")
                    clipped = clip_text(original, cap, self.estimator, tool_name=name)
                    if clipped != original:
                        message["content"] = clipped
                        if name:
                            compressed.add(i)
                        else:
                            truncated.add("history")
        if not fits():
            raise ContextBudgetExceeded("Protected task/system/tool exchange cannot fit context budget")
        compacted = current()
        group_messages(compacted)
        return ContextBuildResult(compacted, ContextStats(
            before, self.estimator.estimate_messages(compacted, tools), len(messages), len(compacted),
            tool_outputs_compressed=len(compressed.intersection(retained)),
            context_sections_dropped=tuple(sorted(dropped | ({"history"} if len(retained) != len(messages) else set()))),
            context_sections_truncated=tuple(sorted(truncated)),
        ), core_system=initial_context.core_system if initial_context else None, optional_sections=sections)
