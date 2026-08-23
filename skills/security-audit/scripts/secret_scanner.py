#!/usr/bin/env python3
"""skills/security-audit/scripts/secret_scanner.py — 静态代码安全与敏感信息扫描工具。

用于扫描目标代码库或指定文件中的敏感凭证、硬编码密钥及常见高危代码模式。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# 常见安全漏洞与敏感凭据检测规则
_RULES = [
    {
        "id": "SEC001",
        "name": "Hardcoded Private Key",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "pattern": re.compile(r"-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PRIVATE)\s+KEY-----", re.IGNORECASE),
        "description": "Found unencrypted private key in source code.",
    },
    {
        "id": "SEC002",
        "name": "AWS Access Key ID",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "pattern": re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}", re.ASCII),
        "description": "Found potential AWS Access Key ID.",
    },
    {
        "id": "SEC003",
        "name": "Generic API Key or Secret Token",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "pattern": re.compile(r"""(?i)(?:api_key|apikey|secret_key|app_secret|client_secret)\s*[:=]\s*["']([A-Za-z0-9_\-]{20,})["']"""),
        "description": "Found hardcoded high-entropy secret or API token.",
    },
    {
        "id": "SEC004",
        "name": "Hardcoded Database Password",
        "severity": "HIGH",
        "cwe": "CWE-798",
        "pattern": re.compile(r"""(?i)(?:password|passwd|pwd|db_pass)\s*[:=]\s*["']([^"'\s]{6,})["']"""),
        "description": "Found hardcoded password in variable assignment.",
    },
    {
        "id": "SEC005",
        "name": "Unsafe Dynamic Code Execution",
        "severity": "HIGH",
        "cwe": "CWE-95",
        "pattern": re.compile(r"\b(?:eval|exec)\s*\(", re.IGNORECASE),
        "description": "Found dynamic eval/exec call susceptible to arbitrary code injection.",
    },
    {
        "id": "SEC006",
        "name": "Insecure Shell Subprocess Execution",
        "severity": "MEDIUM",
        "cwe": "CWE-78",
        "pattern": re.compile(r"subprocess\.(?:Popen|run|call|check_output)\s*\([^)]*shell\s*=\s*True", re.IGNORECASE),
        "description": "Found subprocess call with shell=True enabled, susceptible to command injection.",
    },
    {
        "id": "SEC007",
        "name": "Potential Path Traversal Pattern",
        "severity": "MEDIUM",
        "cwe": "CWE-22",
        "pattern": re.compile(r"""(?:\.\./\.\./|open\s*\(\s*f?["'][^"']*\.\./)"""),
        "description": "Found relative path traversal sequence without canonicalization.",
    },
]

# 忽略扫描的目录与文件后缀
_IGNORED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache", ".idea", ".vscode"}
_SCANNABLE_EXTS = {".py", ".json", ".yaml", ".yml", ".env", ".toml", ".ini", ".cfg", ".sh", ".js", ".ts", ".md"}


def scan_file(file_path: Path) -> List[Dict[str, Any]]:
    """扫描单个文件并返回检测到的安全问题。"""
    findings: List[Dict[str, Any]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    lines = content.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        # 忽略测试文件中的 mock 数据与测试用例
        if "test" in file_path.name.lower() and ("mock" in line.lower() or "assert" in line.lower()):
            continue

        for rule in _RULES:
            match = rule["pattern"].search(line)
            if match:
                snippet = line.strip()
                if len(snippet) > 120:
                    snippet = snippet[:117] + "..."
                findings.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "severity": rule["severity"],
                    "cwe": rule["cwe"],
                    "file": str(file_path.as_posix()),
                    "line": line_idx,
                    "snippet": snippet,
                    "description": rule["description"],
                })
    return findings


def scan_path(target_path: Path) -> List[Dict[str, Any]]:
    """递归扫描目标路径下的所有适宜文件。"""
    all_findings: List[Dict[str, Any]] = []
    if target_path.is_file():
        return scan_file(target_path)

    if not target_path.is_dir():
        return all_findings

    for root, dirs, files in os.walk(target_path):
        # 过滤忽略目录
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() in _SCANNABLE_EXTS:
                findings = scan_file(fpath)
                all_findings.extend(findings)

    return all_findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Static security and secret scanner for CodePilot Agent.")
    parser.add_argument("target", help="Target file or directory path to scan.")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format.")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Error: Target path '{target}' does not exist.", file=sys.stderr)
        return 1

    findings = scan_path(target)

    if args.json:
        result = {
            "target": str(target.as_posix()),
            "total_findings": len(findings),
            "findings": findings,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"=== Security & Secret Audit Report ===")
        print(f"Target: {target.as_posix()}")
        print(f"Total Findings: {len(findings)}\n")
        if not findings:
            print("✅ No security issues or hardcoded secrets detected.")
        else:
            for item in findings:
                print(f"[{item['severity']}] {item['rule_name']} ({item['cwe']})")
                print(f"  Location: {item['file']}:{item['line']}")
                print(f"  Snippet : {item['snippet']}")
                print(f"  Detail  : {item['description']}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
