"""Evaluation-only cumulative switches; runtime safety is never an ablation."""

from copy import deepcopy
from dataclasses import dataclass
import time

from app.agent.context import ContextBudgetExceeded, ContextBuildResult, ContextManager, ContextStats
from app.agent.context.compactor import group_messages
from app.agent.verification import VerificationPolicy
from app.memory.fixed_embedding import FixedEmbeddingModel
from app.memory.memory_manager import HybridMemoryManager
from app.memory.vector_store import VectorMemoryStore
from app.security.permission import PermissionPolicy


@dataclass(frozen=True)
class AblationProfile:
    id: str
    name: str
    memory: bool
    context: bool
    verification: bool

    def permission(self):
        return PermissionPolicy.standard_coding()

    def verification_policy(self, target):
        return VerificationPolicy(enabled=self.verification, max_retries=1, test_command=target)


PROFILES = (
    AblationProfile("A", "ReAct baseline", False, False, False),
    AblationProfile("B", "ReAct + Memory", True, False, False),
    AblationProfile("C", "ReAct + Memory + Context", True, True, False),
    AblationProfile("D", "Full Harness", True, True, True),
)


class PassThroughContextManager(ContextManager):
    """No clipping/eviction, but preserve protocol and the same input ceiling."""

    def build_initial_context(self, *, system, task, workspace="", memory="", skill="", tools=None):
        sections = {"workspace": workspace, "memory": memory, "skill": skill}
        messages = [{"role": "system", "content": system + "\n\n" + workspace + memory + skill},
                    {"role": "user", "content": task}]
        if self.estimator.estimate_text(system) > self.budget.system_budget:
            raise ContextBudgetExceeded("Mandatory system exceeds baseline safeguard")
        prepared = self.compact_messages(messages, tools=tools)
        return ContextBuildResult(prepared.messages, prepared.stats, system, sections)

    def compact_messages(self, messages, *, tools=None, initial_context=None):
        group_messages(messages)
        count = self.estimator.estimate_messages(messages, tools)
        if count > self.budget.usable_input_tokens:
            raise ContextBudgetExceeded("Pass-through context exceeds input safeguard")
        return ContextBuildResult(deepcopy(messages), ContextStats(count, count, len(messages), len(messages)),
                                  initial_context.core_system if initial_context else None,
                                  dict(initial_context.optional_sections) if initial_context else {})


class BenchmarkMemory(HybridMemoryManager):
    """Fresh existing stores per trial; hash embeddings are not semantic evidence."""

    def __init__(self, *, retrieval, state="seeded"):
        if state not in {"cold", "seeded"}:
            raise ValueError("Unknown Memory setup")
        super().__init__(persist_path=None)
        self._vector = VectorMemoryStore(FixedEmbeddingModel())
        self.retrieval = retrieval
        self.state = state
        self.retrieval_calls = 0
        self.context_hits = 0
        self.retrieval_latency_ms = 0.0
        if state == "seeded":
            self.add_task_memory(
                prompt="Prior arithmetic regression debugging and test workflow",
                result="Inspect operator and boundary behavior, reproduce failures, change source only, then run the requested tests.",
                success=True, tool_trace=["read_file", "run_tests"],
            )

    def build_memory_context(self, task, workspace_id=""):
        if not self.retrieval:
            return ""
        self.retrieval_calls += 1
        started = time.perf_counter()
        text = super().build_memory_context(task, workspace_id)
        self.retrieval_latency_ms += (time.perf_counter() - started) * 1000
        self.context_hits += bool(text)
        return text
