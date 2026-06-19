"""workspace_guardrail.py — Workspace 文件访问安全检查。

阻止读取/写入敏感文件（.env、密钥等），阻止访问系统目录。
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.security.taxonomy import (
    BLOCKED_FILE_NAMES,
    BLOCKED_FILE_PATTERNS,
    BLOCKED_SYSTEM_PATHS,
    DESTRUCTIVE_PATTERNS,
    GuardrailResult,
    RiskType,
)

logger = logging.getLogger(__name__)

# 允许的隐藏文件前缀（不阻止）
_ALLOWED_HIDDEN_PREFIXES = (".pytest_cache",)


def check_file_access(
    tool_name: str,
    args: dict,
    workspace_root: str,
) -> GuardrailResult:
    """检查工具调用的文件访问安全性。"""
    if tool_name == "read_file":
        return _check_read(args, workspace_root)
    elif tool_name == "write_file":
        return _check_write(args, workspace_root)
    elif tool_name == "search_code":
        return _check_search(args)
    elif tool_name == "run_tests":
        return _check_run_tests(args)
    return GuardrailResult(allow=True)


def _check_read(args: dict, workspace_root: str) -> GuardrailResult:
    """检查 read_file 的安全性。"""
    path = args.get("path", "")
    if not path:
        return GuardrailResult(allow=True)

    # 检查是否访问敏感文件
    result = _check_sensitive_file(path)
    if not result.allow:
        return result

    # 检查是否访问隐藏文件
    parts = Path(path).parts
    for part in parts:
        if part.startswith(".") and part not in _ALLOWED_HIDDEN_PREFIXES:
            # 检查是否是允许的隐藏文件
            if not any(part.startswith(p) for p in _ALLOWED_HIDDEN_PREFIXES):
                return GuardrailResult(
                    allow=False,
                    risk_type=RiskType.SECRET_ACCESS,
                    reason=f"禁止读取隐藏文件: {path}",
                )

    # 检查系统路径
    result = _check_system_path(path)
    if not result.allow:
        return result

    return GuardrailResult(allow=True)


def _check_write(args: dict, workspace_root: str) -> GuardrailResult:
    """检查 write_file 的安全性。"""
    path = args.get("path", "")
    if not path:
        return GuardrailResult(allow=True)

    # 检查是否写入敏感文件
    result = _check_sensitive_file(path)
    if not result.allow:
        return result

    # 检查是否写入 .git 目录
    if ".git" in Path(path).parts:
        return GuardrailResult(
            allow=False,
            risk_type=RiskType.DESTRUCTIVE_ACTION,
            reason=f"禁止写入 .git 目录: {path}",
        )

    return GuardrailResult(allow=True)


def _check_search(args: dict) -> GuardrailResult:
    """检查 search_code 的安全性。"""
    query = args.get("query", "")
    if not query:
        return GuardrailResult(allow=True)

    # 检查搜索查询是否包含敏感关键词
    sensitive_queries = [
        "password", "secret", "token", "api_key", "private_key",
        "credentials", "aws_access", "ssh_key",
    ]
    query_lower = query.lower()
    for sq in sensitive_queries:
        if sq in query_lower:
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.DATA_EXFILTRATION,
                reason=f"搜索查询包含敏感关键词: {sq}",
            )

    return GuardrailResult(allow=True)


def _check_run_tests(args: dict) -> GuardrailResult:
    """检查 run_tests 的安全性。"""
    target = args.get("target", "")
    # run_tests 的 target 是 pytest node ID，不做过多限制
    return GuardrailResult(allow=True)


def _check_sensitive_file(path: str) -> GuardrailResult:
    """检查文件名是否为敏感文件。"""
    name = Path(path).name.lower()

    # 精确匹配
    if name in BLOCKED_FILE_NAMES:
        return GuardrailResult(
            allow=False,
            risk_type=RiskType.SECRET_ACCESS,
            reason=f"禁止访问敏感文件: {name}",
        )

    # 模式匹配
    for pattern in BLOCKED_FILE_PATTERNS:
        if pattern in name:
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.SECRET_ACCESS,
                reason=f"禁止访问敏感文件: {name} (匹配模式: {pattern})",
            )

    return GuardrailResult(allow=True)


def _check_system_path(path: str) -> GuardrailResult:
    """检查是否访问系统目录。"""
    path_lower = path.lower().replace("\\", "/")
    for sys_path in BLOCKED_SYSTEM_PATHS:
        if path_lower.startswith(sys_path.lower().replace("\\", "/")):
            return GuardrailResult(
                allow=False,
                risk_type=RiskType.SYSTEM_ACCESS,
                reason=f"禁止访问系统目录: {path}",
            )
    return GuardrailResult(allow=True)
