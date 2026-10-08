from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from app.agent.budget import ToolBudget
from app.agent.checkpoint import CheckpointError, CheckpointManager, ResumeRejected
from app.agent.checkpoint.models import ResultSnapshot, TERMINAL_STATUSES
from app.agent.checkpoint.manager import workspace_fingerprint
from app.agent.checkpoint.store import reject_credentials
from app.agent.context import ContextBudget, ContextBuildResult, ContextManager, ContextStats
from app.agent.context.compactor import group_messages
from app.agent.error_event import AgentErrorEvent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.trace import ExecutionStepTrace, ExecutionTrace, TraceSink
from app.agent.verification import VerificationPolicy
from app.memory.memory_manager import get_memory_manager
from app.router.intent_router import get_intent_router, INTENT_REPO, INTENT_SECURITY
from app.security.permission import PermissionPolicy
from app.security.tool_guardrail import ToolGuardrail
from app.skills.manager import SkillManager, skill_manager
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.core.config import settings
from app.models.tool import AgentStep, ToolCall, ToolResult
from app.tools.registry import ToolRegistry
from app.workspace.indexer import IndexBuilder, WorkspaceIndex
from app.workspace.index_cache import get_index_cache
from app.workspace.resolver import SmartFileResolver

logger = logging.getLogger(__name__)


# 检测文本中伪造的工具调用
_TOOL_DRIFT_PATTERNS = [
    re.compile(r"write_file\s*\(", re.IGNORECASE),
    re.compile(r"read_file\s*\(", re.IGNORECASE),
    re.compile(r"Action:\s*write_file", re.IGNORECASE),
    re.compile(r"<｜｜DSML｜｜invoke\s+name=\"write_file\"", re.IGNORECASE),
]

# 检测完成声明
_COMPLETION_PATTERNS = [
    re.compile(r"已修复", re.IGNORECASE),
    re.compile(r"已(成功)?修改", re.IGNORECASE),
    re.compile(r"(bug|问题).*已(被)?修复", re.IGNORECASE),
    re.compile(r"修复(完成|成功|完毕)", re.IGNORECASE),
    re.compile(r"修改(完成|成功|完毕)", re.IGNORECASE),
    re.compile(r"已.*添加.*验证", re.IGNORECASE),
    re.compile(r"(问题|bug)不存在", re.IGNORECASE),
    re.compile(r"代码.*正确", re.IGNORECASE),
    re.compile(r"(测试|test).*通过", re.IGNORECASE),
    re.compile(r"所有.*修复", re.IGNORECASE),
]

MAX_TOOL_CALLS = 5

# Patterns that indicate a code modification task
_CODE_MODIFICATION_PATTERNS = [
    re.compile(r"(fix|修复|debug|调试)", re.IGNORECASE),
    re.compile(r"(write|编写|create|创建|add|添加)", re.IGNORECASE),
    re.compile(r"(modify|修改|update|更新|refactor|重构)", re.IGNORECASE),
    re.compile(r"(implement|实现|optimize|优化)", re.IGNORECASE),
]


def _format_tree(tree: dict, prefix: str = "") -> str:
    """将 tree dict 格式化为可读的树形结构。

    Tree 格式: {"files": [...], "dirs": {name: {"files": [...], "dirs": {...}}}}
    """
    lines = []

    # 先列当前目录的文件
    files = tree.get("files", [])
    dirs = tree.get("dirs", {})
    dir_items = list(dirs.items())

    for j, fname in enumerate(files):
        is_last = j == len(files) - 1 and not dir_items
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{fname}")

    # 再列子目录
    for k, (dir_name, sub_node) in enumerate(dir_items):
        is_last = k == len(dir_items) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "

        sub_files = sub_node.get("files", [])
        sub_dirs = sub_node.get("dirs", {})

        lines.append(f"{prefix}{connector}{dir_name}/")
        # 递归渲染子目录内容
        sub_lines = _format_tree(sub_node, prefix + child_prefix)
        if sub_lines:
            lines.append(sub_lines)

    return "\n".join(lines)


@dataclass
class AgentRunResult:
    """Agent 单次任务的执行结果。"""

    answer: str
    tool_calls_count: int = 0
    tool_results: list[ToolResult] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    security_warnings: list[dict] = field(default_factory=list)
    # D18: evidence-based fields
    evidence: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    # D34: write_file tracking
    wrote_file: bool = False
    no_code_change_reason: str = ""
    # D36: error event tracking
    error_events: list[AgentErrorEvent] = field(default_factory=list)
    # v0.4.3: self-verification tracking
    verification_passed: bool = False
    verification_retries: int = 0
    test_result: str = ""
    # v2.0: skills & trace
    active_skill: Optional[str] = None
    trace: Optional[ExecutionTrace] = None


class ReActAgent:
    """最小可运行的 ReAct Agent。

    循环流程：
    1. 将用户任务 + 对话历史发送给 LLM
    2. LLM 返回 content → 直接作为最终回答
    3. LLM 返回 tool_calls → 执行工具 → 结果追加到对话 → 回到步骤 1
    4. 达到 MAX_TOOL_CALLS 上限时强制停止
    """

    def __init__(
        self,
        llm: LLMClient,
        registry: ToolRegistry,
        workspace_root: str,
        max_tool_calls: int = MAX_TOOL_CALLS,
        verification_policy: VerificationPolicy | None = None,
        permission_policy: PermissionPolicy | None = None,
        skill_manager_instance: SkillManager | None = None,
        trace_sink: TraceSink | None = None,
        context_manager: ContextManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        memory_manager=None,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._workspace_root = workspace_root
        self._max_tool_calls = max_tool_calls
        self._has_drift_corrected = False
        self._has_completion_corrected = False
        self._budget = ToolBudget(max_calls=max_tool_calls)
        self._guardrail = ToolGuardrail()
        self._permission_policy = permission_policy or PermissionPolicy.standard_coding()
        self._skill_manager = skill_manager_instance or skill_manager
        self._trace_sink = trace_sink
        self._context_manager = context_manager or ContextManager(ContextBudget(
            max_input_tokens=settings.context_max_input_tokens,
            reserve_output_tokens=settings.context_reserve_output_tokens,
            tool_observation_budget=settings.context_tool_output_limit,
            recent_message_count=settings.context_recent_message_count,
        ))
        self._index: Optional[WorkspaceIndex] = None
        self._error_events: list[AgentErrorEvent] = []
        self._resolver: Optional[SmartFileResolver] = None
        self._verification = verification_policy or VerificationPolicy()
        self._checkpoint_manager = checkpoint_manager
        self._checkpoint_state = None
        self._checkpoint_result = None
        self._checkpoint_context = None
        self._memory_manager = memory_manager

    async def run(self, task: str, *, task_id: str | None = None) -> AgentRunResult:
        """执行一个编码任务，返回最终结果。"""
        trace = ExecutionTrace(task=task, task_id=task_id or uuid.uuid4().hex, sink=self._trace_sink)
        lease = self._checkpoint_manager.store.lease(trace.task_id) if self._checkpoint_manager else nullcontext()
        with lease:
            if self._checkpoint_manager:
                try:
                    self._checkpoint_manager.store.load(trace.task_id)
                except FileNotFoundError:
                    pass
                else:
                    raise ResumeRejected("task_id_already_exists")
            trace.record_event("task_start", execution_result="started")
            if self._checkpoint_manager:
                self._budget = ToolBudget(max_calls=self._max_tool_calls)
                self._has_drift_corrected = self._has_completion_corrected = False
                self._guardrail = ToolGuardrail()
                self._error_events = []
                self._checkpoint_context = None
                self._checkpoint_result = AgentRunResult(answer="", trace=trace)
                self._checkpoint_state = self._checkpoint_manager.create(
                    trace.task_id, task, self._workspace_root, self._max_tool_calls,
                    self._verification, self._context_manager, self._registry.get_schemas(), trace,
                )
            try:
                result = await self._run_task(task, trace)
                if self._checkpoint_state and self._checkpoint_state.next_step != "terminal":
                    self._save_checkpoint(result, result.messages, trace, next_step="terminal", terminal=True)
                return result
            except (Exception, asyncio.CancelledError) as exc:
                self._record_failure(trace, exc)
                raise

    def _record_failure(self, trace, exc) -> None:
        trace.status = "error"
        trace.record_event(
            "task_complete", execution_result="cancelled" if isinstance(exc, asyncio.CancelledError) else "error",
            metadata={"error_type": type(exc).__name__},
        )
        if self._checkpoint_state is not None:
            state = self._checkpoint_state
            if state.in_flight:
                trace.record_event("recovery_required", execution_result="indeterminate", metadata={"recovery_reason": "indeterminate_tool_exchange"})
                status = "indeterminate"
            else:
                status = "cancelled" if isinstance(exc, asyncio.CancelledError) else "failed"
            updated = state.model_copy(update={
                "status": status, "next_step": state.next_step if state.in_flight else "terminal",
                "trace": self._checkpoint_manager.capture_trace(trace, reserve=0),
            })
            updated.trace.next_event_id = max(updated.trace.next_event_id, state.trace.next_event_id)
            try:
                self._checkpoint_state = self._checkpoint_manager.store.save(updated)
            except Exception as storage_error:
                # Keep the prior durable marker; never mask the original runtime error.
                logger.error("Failed to persist task failure: %s", type(storage_error).__name__)

    async def resume_task(self, task_id: str) -> AgentRunResult:
        """Explicit opt-in resumption of a safe local checkpoint, never tool replay."""
        if self._checkpoint_manager is None:
            raise ResumeRejected("checkpointing_not_enabled")
        with self._checkpoint_manager.store.lease(task_id):
            state = self._checkpoint_manager.store.load(task_id)
            event_cursor = state.trace.next_event_id
            # Claim lifecycle IDs durably before emitting anything to an external sink.
            state = self._checkpoint_manager.store.save(state.model_copy(update={
                "trace": state.trace.model_copy(update={"next_event_id": event_cursor + 8}),
            }))
            trace = ExecutionTrace(
                task=state.task, task_id=state.task_id, sink=self._trace_sink,
                events=deepcopy(state.trace.events), steps=deepcopy(state.trace.steps),
                status=state.trace.status, active_skill=state.active_skill,
                total_latency_ms=state.trace.total_latency_ms, created_at=state.trace.created_at,
            )
            trace.restore_cursor(event_cursor)
            trace.record_event("checkpoint_loaded", execution_result="success", metadata={"checkpoint_version": state.schema_version, "checkpoint_step": state.runtime.iteration})
            try:
                reason = "terminal_checkpoint" if state.status in TERMINAL_STATUSES else self._checkpoint_manager.validate_resume(
                    state, self._workspace_root, self._max_tool_calls, self._verification,
                    self._context_manager, self._registry.get_schemas(),
                )
            except (OSError, CheckpointError):
                reason = "workspace_validation_failed"
            if reason is None and not self._guardrail.check_prompt(state.task).allow:
                reason = "current_prompt_policy_rejected"
            if reason:
                action = "recovery_required" if state.in_flight else "resume_rejected"
                trace.record_event(action, execution_result="rejected", metadata={"recovery_reason": reason})
                snapshot = self._checkpoint_manager.capture_trace(trace, reserve=0)
                snapshot.next_event_id = max(snapshot.next_event_id, state.trace.next_event_id)
                self._checkpoint_manager.store.save(state.model_copy(update={"trace": snapshot}))
                raise ResumeRejected(reason, trace)
            self._checkpoint_state = state.model_copy(update={"resume_count": state.resume_count + 1})
            self._budget = ToolBudget(**asdict(state.budget))
            self._has_drift_corrected = state.drift_corrected
            self._has_completion_corrected = state.completion_corrected
            self._error_events = deepcopy(state.result.error_events)
            self._guardrail.restore_checkpoint_state(state.guardrail_read_count, state.guardrail_read_timestamps, state.result.security_warnings)
            messages = deepcopy(state.messages)
            estimated = self._context_manager.estimator.estimate_messages(messages, self._registry.get_schemas())
            self._checkpoint_context = ContextBuildResult(
                messages, ContextStats(estimated, estimated, len(messages), len(messages)),
                core_system=state.core_system, optional_sections=dict(state.optional_sections),
            )
            result = AgentRunResult(
                **{name: deepcopy(getattr(state.result, name)) for name in ResultSnapshot.model_fields},
                messages=messages, active_skill=state.active_skill, trace=trace,
            )
            self._checkpoint_result = result
            trace.record_event("task_resumed", execution_result="success", metadata={"resume_count": state.resume_count + 1, "restored_tool_budget": self._budget.remaining_calls})
            try:
                self._save_checkpoint(result, messages, trace, status="resumed", llm_request_prepared=state.llm_request_prepared)
                schemas = self._registry.get_schemas()
                if state.next_step in {"core", "repair", "summary"}:
                    result = await self._run_core(
                        state.task, messages, schemas, trace=trace, active_skill=state.active_skill,
                        initial_context=self._checkpoint_context, prior_result=result,
                        start_iteration=state.runtime.iteration,
                    )
                if self._checkpoint_state.next_step == "verify":
                    result = await self._verify(
                        state.task, result, messages, schemas, initial_context=self._checkpoint_context,
                        start_retries=self._checkpoint_state.verification_attempt,
                    )
                return self._finish_task(state.task, result, trace)
            except (Exception, asyncio.CancelledError) as exc:
                self._record_failure(trace, exc)
                raise

    def _save_checkpoint(self, result, messages, trace, *, next_step=None, iteration=None, in_flight=None, status=None, terminal=False, llm_request_prepared=False) -> None:
        if self._checkpoint_state is None:
            return
        state = self._checkpoint_state
        started = time.perf_counter()
        if messages and self._checkpoint_context is not None:
            prepared = self._context_manager.compact_messages(messages, tools=self._registry.get_schemas(), initial_context=self._checkpoint_context)
            messages[:] = prepared.messages
            self._checkpoint_context.optional_sections = prepared.optional_sections
            if prepared.stats.compaction_triggered:
                trace.record_event("context_compaction", execution_result="success", metadata={
                    "phase": "checkpoint", **prepared.stats.to_metadata(),
                })
        pending = in_flight or []
        runtime = state.runtime.model_copy(update={"iteration": state.runtime.iteration if iteration is None else iteration})
        read_count, read_times = self._guardrail.checkpoint_state()
        captured_trace = self._checkpoint_manager.capture_trace(trace, reserve=8 if llm_request_prepared else 1 + 2 * len(pending) + (8 if pending else 0))
        captured_trace.next_event_id = max(captured_trace.next_event_id, state.trace.next_event_id)
        if terminal:
            status = trace.status if trace.status in TERMINAL_STATUSES else "failed"
        updated = state.model_copy(update={
            "status": status or ("indeterminate" if pending else "checkpointed"),
            "next_step": next_step or state.next_step, "runtime": runtime,
            "messages": deepcopy(messages), "active_skill": result.active_skill,
            "budget": deepcopy(self._budget), "drift_corrected": self._has_drift_corrected,
            "completion_corrected": self._has_completion_corrected,
            "llm_request_prepared": llm_request_prepared,
            "completed_tool_ids": [item.tool_call_id for item in result.tool_results],
            "last_completed_outcome": result.tool_results[-1] if result.tool_results else None,
            "in_flight": pending, "result": ResultSnapshot.capture(result), "trace": captured_trace,
            "core_system": self._checkpoint_context.core_system if self._checkpoint_context else None,
            "optional_sections": dict(self._checkpoint_context.optional_sections) if self._checkpoint_context else {},
            "workspace_digest": workspace_fingerprint(self._workspace_root),
            "guardrail_read_count": read_count, "guardrail_read_timestamps": read_times,
            "memory_attempted": terminal or state.memory_attempted,
        })
        reject_credentials(updated.model_dump(mode="json"), (settings.llm_api_key,))
        self._checkpoint_state = self._checkpoint_manager.store.save(updated)
        size = len(json.dumps(self._checkpoint_state.model_dump(mode="json"), ensure_ascii=False).encode("utf-8"))
        trace.record_event("checkpoint_saved", execution_result="success", metadata={
            "checkpoint_version": state.schema_version, "checkpoint_step": runtime.iteration,
            "checkpoint_size_bytes": size, "checkpoint_duration_ms": (time.perf_counter() - started) * 1000,
        })

    def _finish_task(self, task, result, trace):
        if self._verification.enabled and result.wrote_file and not result.verification_passed:
            trace.status = "verification_failed"
        if trace.status == "running":
            trace.status = "completed"
        trace.record_event("task_complete", execution_result=trace.status)
        result.trace = trace
        self._save_checkpoint(result, result.messages, trace, next_step="terminal", terminal=True)
        self._write_task_memory(task, result, result.steps)
        return result

    async def _run_task(self, task: str, trace: ExecutionTrace) -> AgentRunResult:

        # Prompt Injection 检查
        prompt_result = self._guardrail.check_prompt(task)
        if not prompt_result.allow:
            trace.status = "error"
            trace.record_event(
                "security_check",
                execution_result="permission_blocked",
                metadata={"reason": prompt_result.reason},
            )
            trace.record_event("task_complete", execution_result="permission_blocked")
            return AgentRunResult(
                answer=f"安全拦截: {prompt_result.reason}",
                security_warnings=self._guardrail.warnings,
                trace=trace,
            )

        # D33: Hybrid intent routing (rule → embedding → LLM fallback)
        intent_result = get_intent_router().route(task)
        trace.record_event(
            "intent_routing",
            execution_result="success",
            metadata={"intent": intent_result.intent, "layer": intent_result.layer},
        )

        # SECURITY intent detected by router → block early
        if intent_result.intent == INTENT_SECURITY:
            self._guardrail.warnings.append({
                "type": "intent_security",
                "detail": f"Router detected security intent: {intent_result.details}",
            })
            trace.status = "error"
            trace.record_event(
                "security_check",
                execution_result="permission_blocked",
                metadata={"reason": intent_result.details},
            )
            trace.record_event("task_complete", execution_result="permission_blocked")
            return AgentRunResult(
                answer=f"安全拦截: 检测到可疑意图 ({intent_result.layer} layer)",
                security_warnings=self._guardrail.warnings,
                trace=trace,
            )

        # REPO intent → repo analysis mode
        if intent_result.intent == INTENT_REPO:
            result = await self._run_repo_mode(task, trace=trace)
            trace.status = "completed"
            trace.record_event("task_complete", execution_result="success")
            result.trace = trace
            return result

        # Progressive Disclosure: 针对任务意图按需检索并加载匹配的 Skill
        matched_skill = self._skill_manager.match_and_load_for_task(task)
        active_skill_name = matched_skill.name if matched_skill else None
        skill_prompt_section = matched_skill.to_prompt_instruction() if matched_skill else ""

        trace.active_skill = active_skill_name
        trace.record_event(
            "skill_selection",
            execution_result="success" if matched_skill else "no_match",
            metadata={"skill_name": active_skill_name},
        )

        # 构建 Workspace 索引与记忆上下文并注入
        index_context = self._build_index_context()
        mem_ctx = self._build_memory_context(task)

        tools_schema = self._registry.get_schemas()
        initial = self._context_manager.build_initial_context(
            system=SYSTEM_PROMPT, task=task, workspace=index_context,
            memory=mem_ctx, skill=skill_prompt_section, tools=tools_schema,
        )
        messages = initial.messages
        self._checkpoint_context = initial
        trace.record_event("context_build", execution_result="success", metadata=initial.stats.to_metadata())
        self._save_checkpoint(AgentRunResult(answer="", messages=messages, active_skill=active_skill_name, trace=trace), messages, trace, next_step="core", iteration=0)
        result = await self._run_core(
            task, messages, tools_schema, trace=trace, active_skill=active_skill_name, initial_context=initial,
        )

        # ── Self-Verification Loop ──
        if self._verification.enabled and result.wrote_file:
            result = await self._verify(task, result, messages, tools_schema, initial_context=initial)
        return self._finish_task(task, result, trace)

    async def _run_core(
        self,
        task: str,
        messages: list[dict[str, Any]],
        tools_schema: list[dict],
        trace: Optional[ExecutionTrace] = None,
        active_skill: Optional[str] = None,
        initial_context: ContextBuildResult | None = None,
        prior_result: AgentRunResult | None = None,
        start_iteration: int = 0,
    ) -> AgentRunResult:
        """Core agent loop — Think → Act → Observe.

        Reusable for verification retries: passes existing message history
        so the agent sees prior context plus the test failure.
        """
        working = prior_result or AgentRunResult(answer="", messages=messages, active_skill=active_skill, trace=trace)
        tool_results, thoughts, steps = working.tool_results, working.thoughts, working.steps
        tool_calls_count = working.tool_calls_count
        self._checkpoint_result = working

        for iteration in range(start_iteration, self._max_tool_calls):
            if self._checkpoint_state is not None:
                self._checkpoint_state = self._checkpoint_state.model_copy(update={"runtime": self._checkpoint_state.runtime.model_copy(update={"iteration": iteration})})
            budget_prompt = "" if self._checkpoint_state and self._checkpoint_state.llm_request_prepared else self._budget.get_budget_prompt()
            if budget_prompt:
                messages.append({"role": "system", "content": budget_prompt})

            response = await self._chat_with_context(messages, tools_schema, trace, initial_context=initial_context)

            if not response.has_tool_calls:
                answer = response.content or ""

                if self._has_fake_tool_calls(answer) and not self._has_drift_corrected:
                    self._has_drift_corrected = True
                    logger.warning("Detected fake tool calls in answer, injecting correction")
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({
                        "role": "system",
                        "content": (
                            "你刚才把工具调用写进了文本，这是禁止的行为。"
                            "你必须使用真实 tool_call 调用 write_file，不允许在文本中伪造工具调用。"
                            "请立即使用 write_file tool_call 完成修改。"
                        ),
                    })
                    continue

                if (
                    not self._has_completion_corrected
                    and self._has_completion_claim(answer)
                    and not self._has_write_file_in_trajectory(steps)
                ):
                    self._has_completion_corrected = True
                    logger.warning("Completion claimed without write_file, injecting correction")
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({
                        "role": "system",
                        "content": (
                            "你声称已修复问题，但未执行 write_file。"
                            "你必须使用 write_file tool_call 实际修改文件，然后用 run_tests 验证。"
                            "不要在文本中描述修改，必须通过工具执行。"
                        ),
                    })
                    continue

                messages.append({"role": "assistant", "content": answer})

                has_write = self._has_write_file_in_trajectory(steps)
                is_code_mod = self._is_code_modification_task(task)
                no_reason = ""
                if is_code_mod and not has_write:
                    no_reason = "Agent did not call write_file for code modification task"
                    logger.warning("Code modification task without write_file: %s", task[:80])

                working.answer = answer
                working.wrote_file = has_write
                working.no_code_change_reason = no_reason
                working.error_events = list(self._error_events)
                working.security_warnings = self._guardrail.warnings
                next_step = "verify" if self._verification.enabled and has_write else "finish"
                self._save_checkpoint(working, messages, trace, next_step=next_step, iteration=0)
                return working

            thought = response.content or ""
            if thought:
                thoughts.append(thought)

            assistant_msg = self._build_assistant_message(response)
            if self._checkpoint_state is not None:
                # Validate the whole proposed exchange before any external effect.
                group_messages(messages + [assistant_msg] + [
                    {"role": "tool", "tool_call_id": call.id, "content": ""}
                    for call in response.tool_calls
                ])
                completed = set(self._checkpoint_state.completed_tool_ids)
                if any(call.id in completed for call in response.tool_calls):
                    raise ResumeRejected("completed_tool_call_id_reused", trace)
                self._save_checkpoint(working, messages, trace, in_flight=self._checkpoint_manager.pending_calls(response.tool_calls), iteration=iteration)
            messages.append(assistant_msg)

            for tc_info in response.tool_calls:
                if self._budget.should_stop():
                    logger.warning("Budget exhausted, stopping tool calls")
                    # Every requested call needs a result, even when not executed.
                    messages.append({
                        "role": "tool", "tool_call_id": tc_info.id,
                        "content": "Tool not executed: tool budget exhausted.",
                    })
                    continue

                tool_calls_count += 1
                working.tool_calls_count = tool_calls_count
                self._budget.consume()

                if tc_info.name == "search_code":
                    query = tc_info.arguments.get("query", "")
                    if self._budget.is_duplicate_search(query):
                        logger.info("Duplicate search detected: %s", query)
                    self._budget.record_search(query)

                if tc_info.name == "read_file":
                    path = tc_info.arguments.get("path", "")
                    self._budget.record_read(path)

                logger.info(
                    "Tool call #%d: %s(%s) [remaining=%d]",
                    tool_calls_count, tc_info.name, tc_info.arguments,
                    self._budget.remaining_calls,
                )

                t_start = time.perf_counter()
                tool_call = ToolCall(
                    id=tc_info.id, name=tc_info.name, arguments=tc_info.arguments
                )

                if self._permission_policy is not None:
                    allowed, perm_msg = self._permission_policy.check_tool_permission(
                        tc_info.name, tc_info.arguments
                    )
                    if not allowed:
                        result = ToolResult(
                            tool_call_id=tc_info.id,
                            name=tc_info.name,
                            success=False,
                            output=perm_msg,
                            metadata={"permission_blocked": True},
                        )
                    else:
                        result = await self._registry.execute(
                            tool_call, self._workspace_root, guardrail=self._guardrail
                        )
                else:
                    result = await self._registry.execute(
                        tool_call, self._workspace_root, guardrail=self._guardrail
                    )

                t_latency = (time.perf_counter() - t_start) * 1000.0
                tool_results.append(result)

                if trace:
                    step_status = "success" if result.success else (
                        "permission_blocked" if result.metadata.get("permission_blocked") else "error"
                    )
                    trace.add_step(
                        step=tool_calls_count,
                        tool_name=tc_info.name,
                        arguments=tc_info.arguments,
                        status=step_status,
                        latency_ms=t_latency,
                        decision=thought,
                        error=result.output if not result.success else None,
                        output=result.output,
                    )

                if tc_info.name == "search_code" and result.success:
                    self._extract_and_cache_paths(tc_info.arguments.get("query", ""), result.output)

                steps.append(AgentStep(
                    step_id=tool_calls_count,
                    thought=thought,
                    action=f"{tc_info.name}({tc_info.arguments})",
                    tool_name=tc_info.name,
                    tool_args=tc_info.arguments,
                    observation=result.output,
                    success=result.success,
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_info.id,
                    "content": result.output,
                })

            working.wrote_file = self._has_write_file_in_trajectory(steps)
            working.security_warnings = self._guardrail.warnings
            if tool_calls_count >= self._max_tool_calls:
                break
            self._save_checkpoint(working, messages, trace, iteration=iteration + 1)

        # Budget exhausted: ask LLM to summarize
        self._save_checkpoint(working, messages, trace, next_step="summary", iteration=self._max_tool_calls)
        final_response = await self._chat_with_context(
            messages, None, trace, phase="final_summary", initial_context=initial_context,
        )
        has_write = self._has_write_file_in_trajectory(steps)
        is_code_mod = self._is_code_modification_task(task)
        no_reason = ""
        if is_code_mod and not has_write:
            no_reason = "Agent exhausted tool calls without write_file"
            logger.warning("Budget exhausted without write_file for code modification task")

        if trace:
            trace.status = "budget_exhausted"

        working.answer = final_response.content or "[达到最大工具调用次数，未能生成回答]"
        working.wrote_file = has_write
        working.no_code_change_reason = no_reason
        working.error_events = list(self._error_events)
        working.security_warnings = self._guardrail.warnings
        self._save_checkpoint(working, messages, trace, next_step="verify" if self._verification.enabled and has_write else "finish")
        return working

    async def _chat_with_context(
        self, messages: list[dict[str, Any]], tools: list[dict] | None,
        trace: ExecutionTrace | None, *, phase: str = "react",
        initial_context: ContextBuildResult | None = None,
    ) -> ChatResponse:
        prepared = self._context_manager.compact_messages(messages, tools=tools, initial_context=initial_context)
        messages[:] = prepared.messages
        if initial_context is not None:
            initial_context.optional_sections = prepared.optional_sections
        if trace is not None:
            trace.record_event(
                "context_compaction", execution_result="success",
                metadata={"phase": phase, **prepared.stats.to_metadata()},
            )
        if self._checkpoint_state is not None:
            self._save_checkpoint(self._checkpoint_result, messages, trace, llm_request_prepared=True)
        if trace is not None:
            trace.record_event("llm_request", execution_result="started", metadata={
                "phase": phase, "estimated_input_tokens": self._context_manager.estimator.estimate_messages(messages, tools),
                "estimator": type(self._context_manager.estimator).__name__, "temperature": 0.0,
            })
        started = time.perf_counter()
        response = await self._llm.chat(messages, tools=tools or None)
        if trace is not None:
            usage = response.raw.get("usage", {}) if isinstance(response.raw, dict) else {}
            safe_usage = {key: value for key, value in usage.items() if key in {
                "prompt_tokens", "completion_tokens", "total_tokens",
            } and isinstance(value, int) and not isinstance(value, bool) and value >= 0} if isinstance(usage, dict) else {}
            trace.record_event("llm_response", execution_result="success", duration_ms=(time.perf_counter() - started) * 1000,
                               metadata={"phase": phase, "provider_usage": safe_usage})
        return response

    async def _verify(
        self,
        task: str,
        result: AgentRunResult,
        messages: list[dict[str, Any]],
        tools_schema: list[dict],
        *, initial_context: ContextBuildResult | None = None,
        start_retries: int = 0,
    ) -> AgentRunResult:
        """Post-write verification loop: run tests, retry on failure.

        After the agent writes a file, automatically run run_tests.
        If tests pass → done. If fail → inject failure as Observation,
        let the agent continue fixing. Up to max_retries rounds.
        """
        target = self._verification.test_command or ""
        retries = start_retries

        while retries <= self._verification.max_retries:
            logger.info("Verification attempt %d/%d", retries + 1, self._verification.max_retries + 1)

            # Run tests via registry
            test_tc = ToolCall(
                id=f"verify_{retries}",
                name="run_tests",
                arguments={"target": target} if target else {},
            )
            if self._checkpoint_state is not None:
                self._checkpoint_result = result
                self._checkpoint_state = self._checkpoint_state.model_copy(update={"verification_attempt": retries})
                self._save_checkpoint(result, messages, result.trace, next_step="verify", in_flight=self._checkpoint_manager.pending_calls([test_tc]))
            verify_started = time.perf_counter()
            allowed, reason = self._permission_policy.check_tool_permission(test_tc.name, test_tc.arguments)
            if allowed:
                test_result = await self._registry.execute(test_tc, self._workspace_root, guardrail=self._guardrail)
            else:
                test_result = ToolResult(tool_call_id=test_tc.id, name=test_tc.name, success=False, output=reason, metadata={"permission_blocked": True})
            verify_latency = (time.perf_counter() - verify_started) * 1000.0
            tool_calls_count = result.tool_calls_count + 1
            messages.append(self._build_assistant_message(ChatResponse(tool_calls=[
                ToolCallInfo(id=test_tc.id, name=test_tc.name, arguments=test_tc.arguments),
            ])))
            messages.append({
                "role": "tool", "tool_call_id": test_tc.id, "content": test_result.output,
            })

            # Record verification step
            verify_step = AgentStep(
                step_id=tool_calls_count,
                thought="[verification] Running tests after write_file",
                action=f"run_tests(target={target!r})",
                tool_name="run_tests",
                tool_args={"target": target} if target else {},
                observation=test_result.output,
                success=test_result.success,
            )
            result.steps.append(verify_step)
            result.tool_results.append(test_result)
            result.tool_calls_count = tool_calls_count
            result.verification_retries = retries
            result.test_result = test_result.output
            if result.trace:
                result.trace.add_step(
                    step=tool_calls_count,
                    tool_name="run_tests",
                    arguments={"target": target} if target else {},
                    status="success" if test_result.success else "error",
                    latency_ms=verify_latency,
                    decision="[verification] Running tests after write_file",
                    error=test_result.output if not test_result.success else None,
                    output=test_result.output,
                    metadata={"phase": "verification", "attempt": retries + 1},
                )

            # Parse test result
            test_passed = test_result.success
            test_output = test_result.output

            if test_passed:
                result.verification_passed = True
                result.verification_retries = retries
                result.test_result = test_output
                result.tool_calls_count = tool_calls_count
                logger.info("Verification passed on attempt %d", retries + 1)
                self._save_checkpoint(result, messages, result.trace, next_step="finish")
                return result

            # Tests failed — record error event
            self._error_events.append(AgentErrorEvent(
                module="verification",
                error_type="TestFailure",
                context=f"Verification attempt {retries + 1} failed",
                tool_name="run_tests",
                recovery_action="retry" if retries < self._verification.max_retries else "max_retries_exhausted",
            ))

            if retries >= self._verification.max_retries:
                # Max retries exhausted
                result.verification_passed = False
                result.verification_retries = retries
                result.test_result = test_output
                result.tool_calls_count = tool_calls_count
                result.error_events = list(self._error_events)
                logger.warning(
                    "Verification failed after %d retries", self._verification.max_retries
                )
                self._save_checkpoint(result, messages, result.trace, next_step="finish")
                return result

            # Inject test failure as Observation for agent to continue
            logger.info("Tests failed, injecting failure and retrying")
            messages.append({
                "role": "system",
                "content": (
                    "[自动验证] 测试未通过，失败信息见上面的 run_tests 结果。\n"
                    "请根据测试失败信息继续修复代码。"
                ),
            })

            # Continue the agent loop with remaining budget
            remaining = self._max_tool_calls - tool_calls_count
            if remaining <= 0:
                result.verification_passed = False
                result.verification_retries = retries
                result.test_result = test_output
                result.tool_calls_count = tool_calls_count
                result.error_events = list(self._error_events)
                logger.warning("Budget exhausted during verification")
                self._save_checkpoint(result, messages, result.trace, next_step="finish")
                return result

            if self._checkpoint_state is not None:
                self._checkpoint_state = self._checkpoint_state.model_copy(update={"verification_attempt": retries + 1})
            self._save_checkpoint(result, messages, result.trace, next_step="repair", iteration=0)

            # Let the agent continue fixing
            continuation = await self._run_core(
                task,
                messages,
                tools_schema,
                trace=result.trace,
                active_skill=result.active_skill,
                initial_context=initial_context,
                prior_result=result,
            )

            result = continuation
            result.error_events = list(self._error_events)

            retries += 1

        # Should not reach here, but safety fallback
        result.verification_passed = False
        result.verification_retries = retries
        return result

    async def _run_repo_mode(self, task: str, trace: ExecutionTrace | None = None) -> AgentRunResult:
        """REPO_MODE：分析整个项目结构。"""
        from app.agent.repo_analyzer import RepoAnalyzer

        # 确保 index 已构建
        if not self._index:
            self._build_index_context()

        if not self._index or not self._index.files:
            return AgentRunResult(
                answer="当前 workspace 为空，无法进行项目分析。请先上传代码项目。",
                thoughts=["REPO_MODE: workspace 为空"],
            )

        analyzer = RepoAnalyzer(
            llm=self._llm, index=self._index, context_manager=self._context_manager,
            trace=trace, task=task,
        )
        analysis = await analyzer.analyze()

        # 格式化输出
        answer = self._format_analysis(analysis, task)

        # 构建 evidence 列表（转为 dict 以便 JSON 序列化）
        evidence_data = []
        for claim in analysis.claims:
            evidence_data.append({
                "claim_text": claim.claim_text,
                "evidence": [
                    {
                        "claim_type": ev.claim_type,
                        "file": ev.file,
                        "symbol": ev.symbol,
                        "line_start": ev.line_start,
                        "line_end": ev.line_end,
                        "excerpt": ev.excerpt,
                    }
                    for ev in claim.evidence
                ],
            })

        result = AgentRunResult(
            answer=answer,
            tool_calls_count=0,
            tool_results=[],
            messages=[],
            thoughts=[f"REPO_MODE: 分析项目结构 ({len(self._index.files)} files)"],
            steps=[],
            evidence=evidence_data,
            confidence=analysis.confidence,
            error_events=list(self._error_events),
        )
        # D32: Write repo memory
        self._write_repo_memory(analysis, task)
        return result

    def _format_analysis(self, analysis, task: str) -> str:
        """格式化 RepoAnalysis 为用户可读的 Markdown。"""
        parts = []

        if analysis.project_type:
            parts.append(f"## Project Overview\n**{analysis.project_type}**: {analysis.architecture_summary}")
        elif analysis.architecture_summary:
            parts.append(f"## Project Overview\n{analysis.architecture_summary}")

        if analysis.execution_flow:
            parts.append("## Architecture Flow")
            for line in analysis.execution_flow:
                parts.append(line)

        if analysis.core_modules:
            parts.append("## Core Modules")
            parts.append("| Module | Path | Role |")
            parts.append("|--------|------|------|")
            for m in analysis.core_modules:
                parts.append(f"| {m.get('name', '')} | {m.get('path', '')} | {m.get('role', '')} |")

        if analysis.potential_bottlenecks:
            parts.append("## Potential Issues")
            for issue in analysis.potential_bottlenecks:
                parts.append(f"- {issue}")

        if analysis.suggested_improvements:
            parts.append("## Suggested Improvements")
            for imp in analysis.suggested_improvements:
                parts.append(f"- {imp}")

        if not parts:
            return analysis.raw_output or "无法生成项目分析报告。"

        return "\n\n".join(parts)

    def _build_index_context(self) -> str:
        """构建 Workspace 索引上下文，注入到系统提示中。"""
        try:
            cache = get_index_cache()
            self._index = cache.get_or_build(self._workspace_root)
            self._resolver = SmartFileResolver(self._index)
        except Exception as exc:
            logger.warning(
                "Failed to build workspace index: [%s] %s",
                type(exc).__name__, exc,
            )
            self._error_events.append(AgentErrorEvent(
                module="react_agent",
                error_type=type(exc).__name__,
                context="Building workspace index",
                recovery_action="fallback to empty context",
            ))
            return ""

        if not self._index.files:
            return ""

        lines = ["当前 Workspace 结构:"]
        lines.append(_format_tree(self._index.tree, prefix=""))

        # 关键文件分组
        py_files = [f.path for f in self._index.files if f.path.endswith(".py")]
        other_files = [f.path for f in self._index.files if not f.path.endswith(".py")]

        if py_files:
            lines.append(f"\nPython 文件 ({len(py_files)}):")
            for f in py_files[:20]:
                lines.append(f"  - {f}")

        if other_files:
            lines.append(f"\n其他文件 ({len(other_files)}):")
            for f in other_files[:10]:
                lines.append(f"  - {f}")

        # 模块索引
        if self._index.files:
            lines.append("\n模块索引:")
            for f in self._index.files[:30]:
                lines.append(f"  - {f.module_name}: {f.path}")

        return "\n".join(lines)

    @staticmethod
    def _has_fake_tool_calls(text: str) -> bool:
        """检测文本中是否包含伪造的工具调用。"""
        return any(p.search(text) for p in _TOOL_DRIFT_PATTERNS)

    @staticmethod
    def _has_completion_claim(text: str) -> bool:
        """检测文本中是否声称任务已完成。"""
        return any(p.search(text) for p in _COMPLETION_PATTERNS)

    @staticmethod
    def _has_write_file_in_trajectory(steps: list[AgentStep]) -> bool:
        """检查执行轨迹中是否调用过 write_file 或 code_edit。"""
        return any(s.tool_name in ("write_file", "code_edit") for s in steps)

    @staticmethod
    def _is_code_modification_task(task: str) -> bool:
        """判断任务是否属于代码修改类。"""
        return any(p.search(task) for p in _CODE_MODIFICATION_PATTERNS)

    def _extract_and_cache_paths(self, query: str, search_output: str) -> None:
        """从 search_code 输出中提取文件路径并缓存。"""
        import re
        # 匹配 "文件路径:行号" 格式
        path_pattern = re.compile(r"^([a-zA-Z_][\w./]*\.py):\d+", re.MULTILINE)
        matches = path_pattern.findall(search_output)
        if matches:
            # 缓存第一个找到的路径
            self._budget.cache_path(query, matches[0])

    @staticmethod
    def _build_assistant_message(response: ChatResponse) -> dict[str, Any]:
        """将 ChatResponse 转为 OpenAI 格式的 assistant 消息。"""
        msg: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                    },
                }
                for tc in response.tool_calls
            ]
        return msg

    # ── D32: Memory Integration ──────────────────────────

    def _build_memory_context(self, task: str) -> str:
        """Build memory context block for system prompt injection."""
        try:
            mgr = self._memory_manager if self._memory_manager is not None else get_memory_manager()
            ws_id = self._workspace_root or ""
            ctx = mgr.build_memory_context(task, workspace_id=ws_id)
            if ctx:
                return "\n\n" + ctx
        except Exception as exc:
            logger.debug("Failed to build memory context: [%s] %s", type(exc).__name__, exc)
            self._error_events.append(AgentErrorEvent(
                module="react_agent",
                error_type=type(exc).__name__,
                context="Building memory context",
                recovery_action="fallback to empty context",
            ))
        return ""

    def _write_task_memory(
        self, task: str, result: AgentRunResult, steps: list[AgentStep]
    ) -> None:
        """Write task result to memory after completion."""
        try:
            mgr = self._memory_manager if self._memory_manager is not None else get_memory_manager()
            tool_trace = [s.tool_name for s in steps if s.tool_name]
            success = result.tool_calls_count > 0 and not result.security_warnings
            mgr.add_task_memory(
                prompt=task,
                result=result.answer,
                success=success,
                tool_calls_count=result.tool_calls_count,
                tool_trace=tool_trace,
                workspace_id=self._workspace_root or "",
            )
            # Also record error memory on failure
            if not success and result.answer:
                mgr.add_error_memory(
                    error_type="task_failed",
                    context=task,
                    fix_strategy="",
                    tool_trace=tool_trace,
                    workspace_id=self._workspace_root or "",
                )
        except Exception as exc:
            logger.debug("Failed to write task memory: [%s] %s", type(exc).__name__, exc)
            self._error_events.append(AgentErrorEvent(
                module="react_agent",
                error_type=type(exc).__name__,
                context="Writing task memory",
                recovery_action="skip memory write",
            ))

    def _write_repo_memory(self, analysis, task: str) -> None:
        """Write repo analysis result to memory."""
        try:
            mgr = self._memory_manager if self._memory_manager is not None else get_memory_manager()
            module_map = {
                m.get("name", ""): m.get("role", "")
                for m in analysis.core_modules
                if m.get("name")
            }
            file_summary = f"{len(analysis.core_modules)} modules, {len(analysis.execution_flow)} flow steps"
            mgr.add_repo_memory(
                workspace_id=self._workspace_root or "",
                file_summary=file_summary,
                module_map=module_map,
                analysis_result=analysis.raw_output[:500],
                confidence=analysis.confidence,
            )
        except Exception as exc:
            logger.debug("Failed to write repo memory: [%s] %s", type(exc).__name__, exc)
            self._error_events.append(AgentErrorEvent(
                module="react_agent",
                error_type=type(exc).__name__,
                context="Writing repo memory",
                recovery_action="skip memory write",
            ))
