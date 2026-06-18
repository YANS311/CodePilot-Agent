from __future__ import annotations

import asyncio

from app.tools.workspace_tool import WorkspaceTool

_MAX_DIFF_SIZE = 50 * 1024  # 50KB


class GitDiffTool(WorkspaceTool):
    """查看 workspace 的 git diff — 继承 WorkspaceTool，复用 git 仓库判断。"""

    name = "git_diff"
    description = "查看 workspace 当前的 git diff，展示未暂存的变更。"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def run(self, *, workspace_root: str, **_) -> str:
        ws = self.resolve_workspace(workspace_root)
        if not ws.exists():
            return self.error(f"workspace 不存在 — {workspace_root}")

        if not self.is_workspace_git_repo(workspace_root):
            return self.error(f"{workspace_root} 不是一个 git 仓库")

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff",
                cwd=str(ws),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30
            )
        except asyncio.TimeoutError:
            return self.error("git diff 执行超时 (30s)")

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return self.error(f"git diff 失败 — {err}")

        diff = stdout.decode("utf-8", errors="replace")

        if not diff.strip():
            return "无变更 (working tree clean)"

        if len(diff.encode("utf-8")) > _MAX_DIFF_SIZE:
            diff = diff[:_MAX_DIFF_SIZE] + "\n... [diff 过长，已截断至 50KB]"

        return diff
