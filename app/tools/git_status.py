from __future__ import annotations

import asyncio

from app.tools.workspace_tool import WorkspaceTool


class GitStatusTool(WorkspaceTool):
    """检查 workspace 的 git 状态 — 继承 WorkspaceTool，复用 git 仓库判断。"""

    name = "git_status"
    description = "检查 workspace 的 git 状态：是否为 git 仓库、当前分支、文件状态。"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def run(self, *, workspace_root: str, **_) -> str:
        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self.error(f"workspace 不存在 — {workspace_root}")

        if not self.is_workspace_git_repo(workspace_root):
            return f"当前 workspace ({workspace_root}) 不是一个 git 仓库。建议执行: git init && git add . && git commit -m \"init\""

        try:
            proc_branch = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--abbrev-ref", "HEAD",
                cwd=str(ws),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc_branch.communicate(), timeout=10)
            branch = stdout.decode("utf-8", errors="replace").strip()

            proc_status = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                cwd=str(ws),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc_status.communicate(), timeout=10)
            status_output = stdout.decode("utf-8", errors="replace").strip()

        except asyncio.TimeoutError:
            return self.error("git 命令执行超时")

        if not status_output:
            return f"分支: {branch}\n工作区干净，无变更。"

        lines = status_output.splitlines()
        summary = f"分支: {branch}\n共 {len(lines)} 个变更:\n" + "\n".join(lines[:30])
        if len(lines) > 30:
            summary += f"\n... 还有 {len(lines) - 30} 个变更未显示"

        return summary
