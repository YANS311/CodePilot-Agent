"""Isolated cumulative ablations using the existing Agent and EvaluationRunner."""

import asyncio
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time

from app.agent.context import ContextBudget, ContextManager
from app.agent.context.compactor import group_messages
from app.agent.react_agent import ReActAgent
from app.agent.trace import InMemoryTraceSink
from app.core.llm_client import ChatResponse, ToolCallInfo
from app.evaluation.harness_metrics import aggregate, task_metrics
from app.evaluation.manifest import ROOT, contained
from app.evaluation.profiles import PROFILES, BenchmarkMemory, PassThroughContextManager
from app.evaluation.runner import EvaluationRunner
from app.evaluation.schema import EvalResult, EvalTask
from app.tools.code_edit import CodeEditTool
from app.tools.git_diff import GitDiffTool
from app.tools.git_status import GitStatusTool
from app.tools.read_file import ReadFileTool
from app.tools.registry import ToolRegistry
from app.tools.run_tests import RunTestsTool
from app.tools.search_code import SearchCodeTool
from app.tools.write_file import WriteFileTool


@dataclass(frozen=True)
class HarnessConfig:
    repetitions: int = 1
    order_seed: int = 17
    max_tool_calls: int = 8
    task_timeout_seconds: int = 120
    memory_state: str = "seeded"

    def __post_init__(self):
        if self.repetitions < 1 or self.max_tool_calls < 1 or self.task_timeout_seconds < 1:
            raise ValueError("Benchmark counts and timeout must be positive")
        if self.memory_state not in {"cold", "seeded"}:
            raise ValueError("Unknown Memory setup")


def registry():
    tools = ToolRegistry()
    for tool in (ReadFileTool(), SearchCodeTool(), WriteFileTool(), CodeEditTool(),
                 GitDiffTool(), GitStatusTool(), RunTestsTool(mode="local")):
        tools.register(tool)
    return tools


def tool_response(call_id, name, **arguments):
    return ChatResponse(tool_calls=[ToolCallInfo(call_id, name, arguments)])


def copy_seed(source, destination, *, simulated):
    if simulated:
        files = [source / "arithmetic.py", source / "tests/test_arithmetic.py"]
    else:
        # Never feed local uploads, cached answers or other untracked data to a model.
        tracked = subprocess.run(["git", "ls-files", "--", source.relative_to(ROOT).as_posix()],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        files = [ROOT / name for name in tracked]
    if not files:
        raise ValueError("No versioned seed files")
    for path in files:
        if path.is_symlink():
            raise ValueError("Linked seed files are unsupported")
        relative = path.resolve().relative_to(source.resolve())
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


class ScriptedLLM:
    """Hand-authored actions measure Harness contracts, NOT agent capability."""

    def __init__(self, scenario):
        self.scenario = scenario
        self.requests = 0
        self.writes = 0

    async def chat(self, messages, *, tools=None, temperature=0.0):
        group_messages(messages)
        self.requests += 1
        if self.requests == 1:
            return tool_response("read", "read_file", path="arithmetic.py")
        if self.requests == 2 or (messages[-1]["role"] == "system" and any(
            m.get("tool_call_id", "").startswith("verify_") for m in messages
        )):
            self.writes += 1
            correct = self.scenario == "first-pass" or (self.scenario == "recoverable" and self.writes > 1)
            content = "def subtract(a, b):\n    return a - b\n" if correct else "def subtract(a, b):\n    return a + b + 1\n"
            return tool_response(f"write-{self.writes}", "write_file", path="arithmetic.py", content=content)
        return ChatResponse(content="Source edit recorded.")


class SequenceLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = 0

    async def chat(self, messages, *, tools=None, temperature=0.0):
        group_messages(messages)
        self.requests += 1
        return next(self.responses)


def provenance(config, *, model, mode):
    from app.core.config import settings
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "diff", "--quiet", "HEAD"], cwd=ROOT).returncode != 0
    sources = sorted((ROOT / "app" / "evaluation").glob("*.py")) + [ROOT / "app/agent/react_agent.py"]
    fingerprint = hashlib.sha256(b"".join(path.name.encode() + path.read_bytes() for path in sources)).hexdigest()
    return {"executed_at_utc": datetime.now(timezone.utc).isoformat(), "git_sha": sha,
            "tracked_worktree_dirty": dirty, "benchmark_source_sha256": fingerprint,
            "python": platform.python_version(), "platform": platform.system(), "mode": mode,
            "model": model, "provider_category": "offline scripted" if mode == "offline" else "configured OpenAI-compatible endpoint",
            "temperature": 0.0, "config": asdict(config), "estimated_tokens": "UTF-8 bytes / 3 rounded up; not billed tokens",
            "context_budget": asdict(ContextBudget(tool_observation_budget=250)),
            "generation_max_output_tokens": settings.llm_max_tokens if mode == "live" else None,
            "verification_max_retries": 1, "independent_pytest_runner": "LocalExecutionRunner (30s subprocess ceiling)",
            "checkpoint_in_normal_ablations": False, "memory_backend": "isolated HybridMemoryManager structured + deterministic hash vectors",
            "profiles": [asdict(profile) for profile in PROFILES],
            "tools_sha256": hashlib.sha256(json.dumps(registry().get_schemas(), sort_keys=True).encode()).hexdigest()}


async def run_ablations(config=None, *, entries=None, llm_factory=None):
    config = config or HarnessConfig()
    simulated = llm_factory is None
    smoke = json.loads((ROOT / "benchmarks/harness/smoke_tasks.json").read_text(encoding="utf-8"))["tasks"]
    selected = smoke if simulated else entries
    if selected is None:
        raise ValueError("Live benchmarks require explicit manifest tasks")
    trials = []
    results_by_profile = {p.id: [] for p in PROFILES}
    tasks_by_profile = {p.id: [] for p in PROFILES}
    measurements_by_profile = {p.id: [] for p in PROFILES}
    schedule = [(p, item, repetition) for repetition in range(config.repetitions) for item in selected for p in PROFILES]
    random.Random(config.order_seed).shuffle(schedule)
    for profile, item, repetition in schedule:
        task = EvalTask.from_dict(item) if simulated else EvalTask(
            item.task_id, item.task_id, item.difficulty, item.category, item.prompt, test_target=item.test_target or "")
        original_id = task.id
        task = replace(task, id=f"{profile.id}-{original_id}-{repetition}")
        with TemporaryDirectory(prefix="codepilot-ablation-") as temp:
            temp = Path(temp)
            seed = temp / "seed"
            source = ROOT / "benchmarks/harness/seed" if simulated else contained(ROOT, item.seed_workspace)
            copy_seed(source, seed, simulated=simulated)
            if simulated:
                path = seed / "arithmetic.py"
                path.write_text(path.read_text(encoding="utf-8") + "# observational padding, not evidence\n" * 1000, encoding="utf-8")
            memory = BenchmarkMemory(retrieval=profile.memory, state=config.memory_state)
            sink = InMemoryTraceSink()
            budget = ContextBudget(tool_observation_budget=250)
            context = ContextManager(budget) if profile.context else PassThroughContextManager(budget)
            llm = ScriptedLLM(original_id) if simulated else llm_factory()
            def factory(workspace, max_calls, baseline):
                return ReActAgent(llm, registry(), workspace, max_tool_calls=config.max_tool_calls,
                                  verification_policy=profile.verification_policy(task.test_target),
                                  permission_policy=profile.permission(), context_manager=context,
                                  memory_manager=memory, trace_sink=sink)
            runner = EvaluationRunner(workspace_seed=seed, workspace_eval=temp / "eval", memory_manager=memory)
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(runner.run_task(task, factory), config.task_timeout_seconds)
            except asyncio.TimeoutError:
                result = EvalResult(task_id=task.id, error="Task timeout", duration_ms=config.task_timeout_seconds * 1000)
            if not result.trace_events:
                result.trace_events = sink.snapshot()
            measured = task_metrics(result)
            measured["agent_latency_ms"] = result.duration_ms
            measured["task_latency_ms"] = (time.perf_counter() - started) * 1000
            measured.update(profile=profile.id, task_id=original_id, trace_task_id=task.id, repetition=repetition,
                            mode="SIMULATED" if simulated else "REAL_MODEL", memory_state=config.memory_state,
                            memory_retrieval_calls=memory.retrieval_calls, memory_context_hits=memory.context_hits,
                            memory_retrieval_latency_ms=memory.retrieval_latency_ms,
                            workspace_instance_id=hashlib.sha256(str(temp.resolve()).encode()).hexdigest(),
                            evaluation_error=bool(result.error), evaluation_timeout=result.error == "Task timeout",
                            seed_digest=hashlib.sha256(b"".join(p.read_bytes() for p in sorted(seed.rglob("*.py")))).hexdigest())
            trials.append(measured)
            results_by_profile[profile.id].append(result)
            tasks_by_profile[profile.id].append(task)
            measurements_by_profile[profile.id].append(measured)
    return {"label": "SIMULATED runtime regression, not model effectiveness" if simulated else "REAL_MODEL",
            "selected_tasks": [t["id"] for t in selected] if simulated else [t.task_id for t in selected],
            "trials": trials, "summary": {p.id: aggregate(results_by_profile[p.id], tasks_by_profile[p.id],
                                                        measurements_by_profile[p.id], simulated=simulated) for p in PROFILES}}
