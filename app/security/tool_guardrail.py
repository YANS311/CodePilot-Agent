"""tool_guardrail.py — 安全 Guardrail 编排器。

组合 input_guardrail 和 workspace_guardrail，
在 ToolRegistry.execute() 前执行安全检查。
"""

from __future__ import annotations

import logging
import time

from app.security.input_guardrail import analyze_prompt
from app.security.stats import security_stats
from app.security.taxonomy import GuardrailResult, RiskType
from app.security.workspace_guardrail import check_file_access

logger = logging.getLogger(__name__)

# 过量文件访问阈值
_EXCESSIVE_READ_THRESHOLD = 20
_EXCESSIVE_READ_WINDOW = 60  # 60 秒窗口


class ToolGuardrail:
    """安全 Guardrail 编排器 — 每个 Agent 会话一个实例。"""

    def __init__(self) -> None:
        self._read_count = 0
        self._read_timestamps: list[float] = []
        self._warnings: list[dict] = []

    @property
    def warnings(self) -> list[dict]:
        return list(self._warnings)

    def check_prompt(self, task: str) -> GuardrailResult:
        """检查用户提示词是否包含注入攻击。"""
        result = analyze_prompt(task)
        security_stats.record_check(
            blocked=not result.allow,
            risk_type=result.risk_type,
        )
        if not result.allow:
            self._warnings.append(result.to_dict())
            logger.warning("Input guardrail blocked: %s", result.reason)
        return result

    def check_tool_call(
        self,
        name: str,
        args: dict,
        workspace_root: str,
    ) -> GuardrailResult:
        """检查工具调用是否安全。"""
        # 1. 文件访问安全检查
        result = check_file_access(name, args, workspace_root)
        if not result.allow:
            security_stats.record_check(
                blocked=True,
                risk_type=result.risk_type,
            )
            self._warnings.append(result.to_dict())
            logger.warning("Tool guardrail blocked: %s — %s", name, result.reason)
            return result

        # 2. 过量文件访问检查
        if name == "read_file":
            self._record_read()
            excess_result = self._check_excessive_access()
            if not excess_result.allow:
                security_stats.record_check(
                    blocked=True,
                    risk_type=excess_result.risk_type,
                )
                self._warnings.append(excess_result.to_dict())
                return excess_result

        # 通过
        security_stats.record_check(blocked=False)
        return GuardrailResult(allow=True)

    def _record_read(self) -> None:
        """记录一次 read_file 调用。"""
        now = time.time()
        self._read_timestamps.append(now)
        self._read_count += 1
        # 清理过期时间戳
        cutoff = now - _EXCESSIVE_READ_WINDOW
        self._read_timestamps = [t for t in self._read_timestamps if t > cutoff]

    def _check_excessive_access(self) -> GuardrailResult:
        """检查是否过量访问文件。"""
        if len(self._read_timestamps) >= _EXCESSIVE_READ_THRESHOLD:
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.EXCESSIVE_FILE_ACCESS,
                reason=f"过量文件访问: {_EXCESSIVE_READ_WINDOW}秒内读取了{len(self._read_timestamps)}个文件",
            )
        return GuardrailResult(allow=True)
