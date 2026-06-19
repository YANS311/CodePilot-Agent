from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.agent.budget import ToolBudget
from app.agent.prompts import SYSTEM_PROMPT
from app.security.tool_guardrail import ToolGuardrail
from app.core.llm_client import ChatResponse, LLMClient, ToolCallInfo
from app.models.tool import AgentStep, ToolCall, ToolResult
from app.tools.registry import ToolRegistry
from app.workspace.indexer import IndexBuilder, WorkspaceIndex
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
        self._resolver: Optional[SmartFileResolver] = None

    async def run(self, task: str) -> AgentRunResult:
        """执行一个编码任务，返回最终结果。"""
        # Prompt Injection 检查
        prompt_result = self._guardrail.check_prompt(task)
        if not prompt_result.allow:
            return AgentRunResult(
                answer=f"安全拦截: {prompt_result.reason}",
                security_warnings=self._guardrail.warnings,
            )

        # 构建 Workspace 索引并注入上下文
        index_context = self._build_index_context()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + index_context},
            {"role": "user", "content": task},
        ]

        tools_schema = self._registry.get_schemas()
        tool_results: list[ToolResult] = []
        thoughts: list[str] = []
        steps: list[AgentStep] = []
        tool_calls_count = 0

        for iteration in range(self._max_tool_calls):
            # 注入预算提示
            budget_prompt = self._budget.get_budget_prompt()
            if budget_prompt:
                messages.append({"role": "system", "content": budget_prompt})

            response: ChatResponse = await self._llm.chat(
                messages, tools=tools_schema if tools_schema else None
            )

            # 如果 LLM 给出了纯文本回答（无 tool_calls），检查是否有伪造工具调用
            if not response.has_tool_calls:
                answer = response.content or ""

                # Guardrail: 检测文本中伪造的工具调用
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

                # Guardrail: Completion Chain — 声称完成但未执行 write_file
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
                return AgentRunResult(
                    answer=response.content or "",
                    tool_calls_count=tool_calls_count,
                    tool_results=tool_results,
                    messages=messages,
                    thoughts=thoughts,
                    steps=steps,
                    security_warnings=self._guardrail.warnings,
                )

            # 有 tool_calls：提取 thought 并构建 assistant 消息
            thought = response.content or ""
            if thought:
                thoughts.append(thought)

            assistant_msg = self._build_assistant_message(response)
            messages.append(assistant_msg)

            # 逐个执行 tool_call
            for tc_info in response.tool_calls:
                # 检查预算
                if self._budget.should_stop():
                    logger.warning("Budget exhausted, stopping tool calls")
                    break

                tool_calls_count += 1
                self._budget.consume()

                # 重复搜索检查
                if tc_info.name == "search_code":
                    query = tc_info.arguments.get("query", "")
                    if self._budget.is_duplicate_search(query):
                        # 注入警告但不阻止执行
                        logger.info("Duplicate search detected: %s", query)
                    self._budget.record_search(query)

                # 记录已读取的文件
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

                # 从 search_code 结果中缓存文件路径
                if tc_info.name == "search_code" and result.success:
                    self._extract_and_cache_paths(tc_info.arguments.get("query", ""), result.output)

                # 构建 AgentStep
                steps.append(AgentStep(
                    step_id=tool_calls_count,
                    thought=thought,
                    action=f"{tc_info.name}({tc_info.arguments})",
                    tool_name=tc_info.name,
                    tool_args=tc_info.arguments,
                    observation=result.output,
                    success=result.success,
                ))

                # 构造 tool role 消息追加到对话
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_info.id,
                    "content": result.output,
                })

            if tool_calls_count >= self._max_tool_calls:
                break

        # 达到上限：发一次不含 tools 的请求，让 LLM 基于已有信息总结
        final_response = await self._llm.chat(messages)
        return AgentRunResult(
            answer=final_response.content or "[达到最大工具调用次数，未能生成回答]",
            tool_calls_count=tool_calls_count,
            tool_results=tool_results,
            messages=messages,
            thoughts=thoughts,
            steps=steps,
            security_warnings=self._guardrail.warnings,
        )

    def _build_index_context(self) -> str:
        """构建 Workspace 索引上下文，注入到系统提示中。"""
        try:
            builder = IndexBuilder()
            self._index = builder.build(self._workspace_root)
            self._resolver = SmartFileResolver(self._index)
        except Exception:
            logger.warning("Failed to build workspace index")
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
