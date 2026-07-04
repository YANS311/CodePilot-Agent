from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agent.budget import ToolBudget
from app.agent.error_event import AgentErrorEvent
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.verification import VerificationPolicy
from app.memory.memory_manager import get_memory_manager
from app.router.intent_router import get_intent_router, INTENT_REPO, INTENT_SECURITY
from app.security.tool_guardrail import ToolGuardrail
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
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
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._workspace_root = workspace_root
        self._max_tool_calls = max_tool_calls
        self._has_drift_corrected = False
        self._has_completion_corrected = False
        self._budget = ToolBudget(max_calls=max_tool_calls)
        self._guardrail = ToolGuardrail()
        self._index: Optional[WorkspaceIndex] = None
        self._error_events: list[AgentErrorEvent] = []
        self._resolver: Optional[SmartFileResolver] = None
        self._verification = verification_policy or VerificationPolicy()

    async def run(self, task: str) -> AgentRunResult:
        """执行一个编码任务，返回最终结果。"""
        # Prompt Injection 检查
        prompt_result = self._guardrail.check_prompt(task)
        if not prompt_result.allow:
            return AgentRunResult(
                answer=f"安全拦截: {prompt_result.reason}",
                security_warnings=self._guardrail.warnings,
            )

        # D33: Hybrid intent routing (rule → embedding → LLM fallback)
        intent_result = get_intent_router().route(task)

        # SECURITY intent detected by router → block early
        if intent_result.intent == INTENT_SECURITY:
            self._guardrail.warnings.append({
                "type": "intent_security",
                "detail": f"Router detected security intent: {intent_result.details}",
            })
            return AgentRunResult(
                answer=f"安全拦截: 检测到可疑意图 ({intent_result.layer} layer)",
                security_warnings=self._guardrail.warnings,
            )

        # REPO intent → repo analysis mode
        if intent_result.intent == INTENT_REPO:
            return await self._run_repo_mode(task)

        # 构建 Workspace 索引并注入上下文
        index_context = self._build_index_context()
        mem_ctx = self._build_memory_context(task)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + index_context + mem_ctx},
            {"role": "user", "content": task},
        ]

        tools_schema = self._registry.get_schemas()
        result = await self._run_core(task, messages, tools_schema)

        # ── Self-Verification Loop ──
        if self._verification.enabled and result.wrote_file:
            result = await self._verify(task, result, messages, tools_schema)

        self._write_task_memory(task, result, result.steps)
        return result

    async def _run_core(
        self,
        task: str,
        messages: list[dict[str, Any]],
        tools_schema: list[dict],
    ) -> AgentRunResult:
        """Core agent loop — Think → Act → Observe.

        Reusable for verification retries: passes existing message history
        so the agent sees prior context plus the test failure.
        """
        tool_results: list[ToolResult] = []
        thoughts: list[str] = []
        steps: list[AgentStep] = []
        tool_calls_count = 0

        for iteration in range(self._max_tool_calls):
            budget_prompt = self._budget.get_budget_prompt()
            if budget_prompt:
                messages.append({"role": "system", "content": budget_prompt})

            response: ChatResponse = await self._llm.chat(
                messages, tools=tools_schema if tools_schema else None
            )

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

                return AgentRunResult(
                    answer=response.content or "",
                    tool_calls_count=tool_calls_count,
                    tool_results=tool_results,
                    messages=messages,
                    thoughts=thoughts,
                    steps=steps,
                    security_warnings=self._guardrail.warnings,
                    wrote_file=has_write,
                    no_code_change_reason=no_reason,
                    error_events=list(self._error_events),
                )

            thought = response.content or ""
            if thought:
                thoughts.append(thought)

            assistant_msg = self._build_assistant_message(response)
            messages.append(assistant_msg)

            for tc_info in response.tool_calls:
                if self._budget.should_stop():
                    logger.warning("Budget exhausted, stopping tool calls")
                    break

                tool_calls_count += 1
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

                tool_call = ToolCall(
                    id=tc_info.id, name=tc_info.name, arguments=tc_info.arguments
                )
                result = await self._registry.execute(
                    tool_call, self._workspace_root, guardrail=self._guardrail
                )
                tool_results.append(result)

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

            if tool_calls_count >= self._max_tool_calls:
                break

        # Budget exhausted: ask LLM to summarize
        final_response = await self._llm.chat(messages)
        has_write = self._has_write_file_in_trajectory(steps)
        is_code_mod = self._is_code_modification_task(task)
        no_reason = ""
        if is_code_mod and not has_write:
            no_reason = "Agent exhausted tool calls without write_file"
            logger.warning("Budget exhausted without write_file for code modification task")

        return AgentRunResult(
            answer=final_response.content or "[达到最大工具调用次数，未能生成回答]",
            tool_calls_count=tool_calls_count,
            tool_results=tool_results,
            messages=messages,
            thoughts=thoughts,
            steps=steps,
            security_warnings=self._guardrail.warnings,
            wrote_file=has_write,
            no_code_change_reason=no_reason,
            error_events=list(self._error_events),
        )

    async def _verify(
        self,
        task: str,
        result: AgentRunResult,
        messages: list[dict[str, Any]],
        tools_schema: list[dict],
    ) -> AgentRunResult:
        """Post-write verification loop: run tests, retry on failure.

        After the agent writes a file, automatically run run_tests.
        If tests pass → done. If fail → inject failure as Observation,
        let the agent continue fixing. Up to max_retries rounds.
        """
        target = self._verification.test_command or ""
        retries = 0

        while retries <= self._verification.max_retries:
            logger.info("Verification attempt %d/%d", retries + 1, self._verification.max_retries + 1)

            # Run tests via registry
            test_tc = ToolCall(
                id=f"verify_{retries}",
                name="run_tests",
                arguments={"target": target} if target else {},
            )
            test_result = await self._registry.execute(
                test_tc, self._workspace_root, guardrail=self._guardrail
            )
            tool_calls_count = result.tool_calls_count + 1

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

            # Parse test result
            test_passed = test_result.success
            test_output = test_result.output

            if test_passed:
                result.verification_passed = True
                result.verification_retries = retries
                result.test_result = test_output
                result.tool_calls_count = tool_calls_count
                logger.info("Verification passed on attempt %d", retries + 1)
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
                return result

            # Inject test failure as Observation for agent to continue
            logger.info("Tests failed, injecting failure and retrying")
            messages.append({
                "role": "system",
                "content": (
                    f"[自动验证] 测试未通过:\n{test_output}\n\n"
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
                return result

            # Let the agent continue fixing
            continuation = await self._run_core(task, messages, tools_schema)

            # Merge continuation into result
            result.answer = continuation.answer
            result.tool_calls_count = tool_calls_count + continuation.tool_calls_count
            result.tool_results.extend(continuation.tool_results)
            result.steps.extend(continuation.steps)
            result.thoughts.extend(continuation.thoughts)
            result.messages = continuation.messages
            result.error_events = list(self._error_events)

            retries += 1

        # Should not reach here, but safety fallback
        result.verification_passed = False
        result.verification_retries = retries
        return result

    async def _run_repo_mode(self, task: str) -> AgentRunResult:
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

        analyzer = RepoAnalyzer(llm=self._llm, index=self._index)
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
        """检查执行轨迹中是否调用过 write_file。"""
        return any(s.tool_name == "write_file" for s in steps)

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
            mgr = get_memory_manager()
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
            mgr = get_memory_manager()
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
            mgr = get_memory_manager()
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
