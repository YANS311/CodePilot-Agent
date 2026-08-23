"""app/security/permission.py — 运行时最小权限模型与沙箱安全边界。

明确原则：
Prompt Guardrail != Security Boundary
Prompt Guardrail 仅用于引导与修正模型行为；
真实的系统安全边界由 PermissionPolicy 与执行沙箱 (Local / Docker) 在运行时强制拦截 (Deterministic Enforcement)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PermissionAction(str, Enum):
    """运行时操作权限分类。"""

    READ = "READ"              # 读取文件、检索代码、查看 Git 状态
    WRITE = "WRITE"            # 写入、修改、删除工作区文件
    EXECUTE = "EXECUTE"        # 启动测试子进程、执行本地二进制命令
    NETWORK = "NETWORK"        # 发起外部网络请求 / HTTP 访问
    GIT_MUTATE = "GIT_MUTATE"  # 执行 git commit / push / branch 等写入变更


# 默认内置工具的权限映射
TOOL_PERMISSION_MAP: Dict[str, PermissionAction] = {
    "read_file": PermissionAction.READ,
    "search_code": PermissionAction.READ,
    "git_diff": PermissionAction.READ,
    "git_status": PermissionAction.READ,
    "write_file": PermissionAction.WRITE,
    "code_edit": PermissionAction.WRITE,
    "run_tests": PermissionAction.EXECUTE,
}


@dataclass
class PermissionPolicy:
    """运行时安全策略，负责在工具执行前执行强拦截。"""

    allowed_actions: Set[PermissionAction] = field(
        default_factory=lambda: {
            PermissionAction.READ,
            PermissionAction.WRITE,
            PermissionAction.EXECUTE,
        }
    )
    enforce_workspace_boundary: bool = True
    allow_network: bool = False

    def is_action_allowed(self, action: PermissionAction) -> bool:
        """检查指定权限是否被允许。"""
        return action in self.allowed_actions

    def check_tool_permission(self, tool_name: str, arguments: Optional[dict] = None) -> tuple[bool, str]:
        """检查工具调用是否符合当前权限策略。"""
        # 1. 查询工具所需权限
        action = TOOL_PERMISSION_MAP.get(tool_name)
        if action is None:
            # MCP 工具或自定义插件：根据命名或默认规则推断
            if any(k in tool_name.lower() for k in ["read", "get", "list", "search", "query"]):
                action = PermissionAction.READ
            elif any(k in tool_name.lower() for k in ["write", "edit", "create", "delete", "update", "modify"]):
                action = PermissionAction.WRITE
            elif any(k in tool_name.lower() for k in ["run", "exec", "eval", "test", "cmd"]):
                action = PermissionAction.EXECUTE
            elif any(k in tool_name.lower() for k in ["http", "fetch", "web", "download", "url"]):
                action = PermissionAction.NETWORK
            else:
                action = PermissionAction.READ

        # 2. 策略权限判断
        if action not in self.allowed_actions:
            err_msg = f"PERMISSION_DENIED: Action '{action.value}' for tool '{tool_name}' is blocked by PermissionPolicy."
            logger.warning(err_msg)
            return False, err_msg

        return True, "ALLOWED"

    @classmethod
    def read_only(cls) -> PermissionPolicy:
        """只读策略：禁止写入与执行。"""
        return cls(allowed_actions={PermissionAction.READ})

    @classmethod
    def standard_coding(cls) -> PermissionPolicy:
        """标准编码策略：允许 READ, WRITE, EXECUTE。"""
        return cls(allowed_actions={PermissionAction.READ, PermissionAction.WRITE, PermissionAction.EXECUTE})
