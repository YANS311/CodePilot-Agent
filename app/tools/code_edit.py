"""CodeEditTool — Surgical code editing via old/new text replacement.

Instead of overwriting entire files, this tool performs targeted replacements
of specific text blocks. Safer than write_file for targeted repairs:
- Preserves untouched code
- Produces minimal diffs
- Supports occurrence disambiguation for repeated patterns
"""

from __future__ import annotations

import hashlib
import json

from app.tools.workspace_tool import WorkspaceTool

# Binary file extensions — refuse to edit
_BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".mp3", ".mp4", ".avi", ".mov", ".wav",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".woff", ".woff2", ".ttf", ".eot",
    ".db", ".sqlite", ".sqlite3",
})

# Error codes
EDIT_TARGET_NOT_FOUND = "EDIT_TARGET_NOT_FOUND"
EDIT_TARGET_AMBIGUOUS = "EDIT_TARGET_AMBIGUOUS"
EDIT_OCCURRENCE_OUT_OF_RANGE = "EDIT_OCCURRENCE_OUT_OF_RANGE"
EDIT_BINARY_FILE = "EDIT_BINARY_FILE"


def _content_hash(content: str) -> str:
    """SHA-256 hash of content, truncated to 16 hex chars."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _detect_newline(content: str) -> str:
    """Detect the dominant newline style in content."""
    crlf = content.count("\r\n")
    lf = content.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


class CodeEditTool(WorkspaceTool):
    """Surgical code editing — replace specific text blocks within a file.

    Safer than write_file for targeted repairs:
    - Only replaces the matched text, preserving everything else
    - Supports occurrence disambiguation for repeated patterns
    - Returns before/after hashes for auditability
    """

    name = "code_edit"
    description = (
        "精确替换文件中的指定代码块。"
        "通过 old 文本定位目标，替换为 new 文本。"
        "比 write_file 更安全，只修改命中的部分。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "相对于 workspace 的文件路径",
            },
            "old": {
                "type": "string",
                "description": "要替换的原始代码（必须与文件中的内容完全匹配）",
            },
            "new": {
                "type": "string",
                "description": "替换后的新代码",
            },
            "occurrence": {
                "type": "integer",
                "description": "当 old 匹配多处时，指定替换第几处（从 1 开始）。不指定则要求唯一匹配。",
            },
        },
        "required": ["path", "old", "new"],
    }

    async def run(
        self,
        *,
        workspace_root: str,
        path: str,
        old: str,
        new: str,
        occurrence: int | None = None,
        **_,
    ) -> str:
        # ── Path validation ──
        try:
            target = self.safe_resolve(workspace_root, path)
        except ValueError as exc:
            return self.error(str(exc))

        if ".git" in target.parts:
            return self.error(f"禁止编辑 .git 目录 — {path}")

        # ── Binary check ──
        suffix = target.suffix.lower()
        if suffix in _BINARY_EXTENSIONS:
            return json.dumps({
                "error_code": EDIT_BINARY_FILE,
                "message": f"不允许编辑二进制文件 ({suffix})",
            }, ensure_ascii=False)

        # ── File existence ──
        if not target.exists():
            return self.error(f"文件不存在 — {path}")

        if not target.is_file():
            return self.error(f"不是文件 — {path}")

        # ── Read and match ──
        try:
            original = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return json.dumps({
                "error_code": EDIT_BINARY_FILE,
                "message": f"文件包含非 UTF-8 内容，无法编辑 — {path}",
            }, ensure_ascii=False)

        # Count occurrences
        count = original.count(old)
        if count == 0:
            return json.dumps({
                "error_code": EDIT_TARGET_NOT_FOUND,
                "message": f"在文件中未找到匹配的代码块 — {path}",
                "old_preview": old[:200],
            }, ensure_ascii=False)

        # ── Occurrence resolution ──
        if count > 1 and occurrence is None:
            return json.dumps({
                "error_code": EDIT_TARGET_AMBIGUOUS,
                "message": f"匹配到 {count} 处，需要指定 occurrence 参数（从 1 开始）",
                "match_count": count,
            }, ensure_ascii=False)

        if occurrence is not None:
            if occurrence < 1 or occurrence > count:
                return json.dumps({
                    "error_code": EDIT_OCCURRENCE_OUT_OF_RANGE,
                    "message": f"occurrence={occurrence} 超出范围（共 {count} 处匹配）",
                    "match_count": count,
                }, ensure_ascii=False)
            target_index = occurrence - 1  # convert to 0-based
        else:
            target_index = 0  # unique match

        # ── Perform replacement ──
        before_hash = _content_hash(original)

        # Find the Nth occurrence and replace only that one
        idx = -1
        for _ in range(target_index + 1):
            idx = original.index(old, idx + 1)
        result_content = original[:idx] + new + original[idx + len(old):]

        after_hash = _content_hash(result_content)

        # Preserve original newline style
        newline = _detect_newline(original)
        if newline == "\r\n":
            result_content = result_content.replace("\r\n", "\n").replace("\n", "\r\n")

        # ── Write back ──
        target.write_text(result_content, encoding="utf-8")

        return json.dumps({
            "success": True,
            "path": path,
            "replacement_count": 1,
            "occurrence_used": occurrence if occurrence is not None else 1,
            "match_count": count,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "changed": True,
        }, ensure_ascii=False)
