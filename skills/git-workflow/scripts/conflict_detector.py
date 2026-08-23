#!/usr/bin/env python3
"""skills/git-workflow/scripts/conflict_detector.py — Git 冲突标记扫描与分支卫生检查工具。

扫描工作区文件中的未解决 Git 冲突标记 (<<<<<<<, =======, >>>>>>>)。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

_CONFLICT_START = re.compile(r"^<{7}\s*(.*)$")
_CONFLICT_MID = re.compile(r"^={7}$")
_CONFLICT_END = re.compile(r"^>{7}\s*(.*)$")

_IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}


def scan_file_conflicts(file_path: Path) -> List[Dict[str, Any]]:
    """检测单文件中的未解决冲突块。"""
    conflicts: List[Dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return conflicts

    lines = content.splitlines()
    in_conflict = False
    start_line = 0
    branch_a = ""

    for idx, line in enumerate(lines, start=1):
        m_start = _CONFLICT_START.match(line)
        if m_start:
            in_conflict = True
            start_line = idx
            branch_a = m_start.group(1).strip()
            continue

        m_end = _CONFLICT_END.match(line)
        if m_end and in_conflict:
            branch_b = m_end.group(1).strip()
            conflicts.append({
                "file": str(file_path.as_posix()),
                "start_line": start_line,
                "end_line": idx,
                "our_branch": branch_a or "HEAD",
                "their_branch": branch_b or "Incoming",
            })
            in_conflict = False

    return conflicts


def scan_workspace_conflicts(target_path: Path) -> List[Dict[str, Any]]:
    """扫描目标路径下的所有冲突。"""
    all_conflicts: List[Dict[str, Any]] = []
    if target_path.is_file():
        return scan_file_conflicts(target_path)

    if not target_path.is_dir():
        return []

    for root, dirs, files in os.walk(target_path):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.is_file():
                conflicts = scan_file_conflicts(fpath)
                all_conflicts.extend(conflicts)

    return all_conflicts


def main() -> int:
    parser = argparse.ArgumentParser(description="Git Conflict Marker Detector for CodePilot Agent.")
    parser.add_argument("target", help="Target file or workspace directory.")
    parser.add_argument("--json", action="store_true", help="Output in JSON format.")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Error: Target '{target}' does not exist.", file=sys.stderr)
        return 1

    conflicts = scan_workspace_conflicts(target)

    if args.json:
        result = {
            "target": str(target.as_posix()),
            "has_conflicts": len(conflicts) > 0,
            "total_conflicts": len(conflicts),
            "conflicts": conflicts,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"=== Git Conflict Detection Report ===")
        print(f"Target: {target.as_posix()}")
        print(f"Total Conflicts: {len(conflicts)}\n")

        if not conflicts:
            print("✅ Clean: No unresolved merge/rebase conflict markers found.")
        else:
            print("❌ Unresolved Git conflict markers detected:")
            for c in conflicts:
                print(f"  File: {c['file']} (Lines {c['start_line']}-{c['end_line']})")
                print(f"  Branches: {c['our_branch']} vs {c['their_branch']}\n")

    return 0 if not conflicts else 1


if __name__ == "__main__":
    sys.exit(main())
