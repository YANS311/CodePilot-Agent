"""WorkspaceTool — 所有 workspace 工具的公共基类。

封装：
- workspace 路径解析
- 路径穿越防护
- 忽略目录判断
- 统一错误格式

子类只需实现 run() 中的业务逻辑，复用本类的安全工具方法。
"""

from __future__ import annotations

from pathlib import Path

from app.tools.base import BaseTool

# 递归搜索时跳过的目录
SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules", ".idea"})


class WorkspaceTool(BaseTool):
    """所有需要访问 workspace 的工具的公共基类。

    体现继承：子类继承本类，获得路径解析、安全校验等通用能力，
    同时各自实现不同的 run() 业务逻辑。
    """

    def resolve_workspace(self, workspace_root: str) -> Path:
        """解析 workspace 根目录为绝对路径。"""
        return Path(workspace_root).resolve()

    def safe_resolve(self, workspace_root: str, relative_path: str) -> Path:
        """解析相对路径并校验是否在 workspace 内。

        路径穿越时抛出 ValueError，由 run() 捕获并返回错误字符串。
        """
        ws = self.resolve_workspace(workspace_root)
        target = (ws / relative_path).resolve()
        if not str(target).startswith(str(ws)):
            raise ValueError(f"路径超出 workspace 范围 — {relative_path}")
        return target

    def is_workspace_git_repo(self, workspace_root: str) -> bool:
        """判断 workspace 是否为 git 仓库。"""
        ws = self.resolve_workspace(workspace_root)
        return (ws / ".git").exists()

    @staticmethod
    def should_skip_dir(dirname: str) -> bool:
        """判断目录名是否应被递归搜索跳过。"""
        return dirname in SKIP_DIRS

    @staticmethod
    def error(message: str) -> str:
        """统一的工具错误返回格式。"""
        return f"错误: {message}"
