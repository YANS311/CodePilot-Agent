#!/usr/bin/env python3
"""skills/api-spec-validator/scripts/route_linter.py — FastAPI 路由与契约静态检查工具。

通过 AST 分析 FastAPI 路由定义，检查 response_model 声明、状态码规范及路径参数契约。
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


class RouteVisitor(ast.NodeVisitor):
    """AST 访问器，提取并校验 FastAPI 路由装饰器及参数。"""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self.routes: List[Dict[str, Any]] = []
        self.issues: List[Dict[str, Any]] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_node(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_node(node)
        self.generic_visit(node)

    def _check_function_node(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            func = decorator.func
            method_name = ""
            if isinstance(func, ast.Attribute) and func.attr.lower() in _HTTP_METHODS:
                method_name = func.attr.upper()
            elif isinstance(func, ast.Name) and func.id.lower() in _HTTP_METHODS:
                method_name = func.id.upper()

            if not method_name:
                continue

            # 提取路径参数
            path = "/"
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path = str(decorator.args[0].value)

            # 提取关键字参数 (response_model, status_code, tags 等)
            kwargs = {kw.arg: kw.value for kw in decorator.keywords if kw.arg}
            has_response_model = "response_model" in kwargs or node.returns is not None
            status_code = None
            if "status_code" in kwargs and isinstance(kwargs["status_code"], ast.Constant):
                status_code = kwargs["status_code"].value

            route_info = {
                "file": self.file_path,
                "line": node.lineno,
                "function": node.name,
                "method": method_name,
                "path": path,
                "has_response_model": bool(has_response_model),
                "status_code": status_code,
            }
            self.routes.append(route_info)

            # 规则检查 1: 缺少 response_model 或类型标注
            if not has_response_model:
                self.issues.append({
                    "severity": "MEDIUM",
                    "code": "API001",
                    "file": self.file_path,
                    "line": node.lineno,
                    "endpoint": f"{method_name} {path}",
                    "message": f"Endpoint '{node.name}' is missing explicit response_model or return type annotation.",
                })

            # 规则检查 2: POST 请求推荐返回 201 或显式指定 status_code
            if method_name == "POST" and status_code is None:
                self.issues.append({
                    "severity": "LOW",
                    "code": "API002",
                    "file": self.file_path,
                    "line": node.lineno,
                    "endpoint": f"{method_name} {path}",
                    "message": f"POST endpoint '{node.name}' uses default 200 status code. Consider status_code=201 (Created) if resource is created.",
                })


def lint_file(file_path: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """静态检查单个 Python 文件中的 FastAPI 路由。"""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(file_path))
    except Exception:
        return [], []

    visitor = RouteVisitor(str(file_path.as_posix()))
    visitor.visit(tree)
    return visitor.routes, visitor.issues


def lint_path(target_path: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """递归检查指定路径下的所有 Python 文件。"""
    all_routes: List[Dict[str, Any]] = []
    all_issues: List[Dict[str, Any]] = []

    if target_path.is_file() and target_path.suffix == ".py":
        return lint_file(target_path)

    if not target_path.is_dir():
        return [], []

    for root, _, files in os.walk(target_path):
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("test_"):
                fpath = Path(root) / fname
                routes, issues = lint_file(fpath)
                all_routes.extend(routes)
                all_issues.extend(issues)

    return all_routes, all_issues


def main() -> int:
    parser = argparse.ArgumentParser(description="FastAPI Route & Contract Linter for CodePilot Agent.")
    parser.add_argument("target", help="Target Python file or directory.")
    parser.add_argument("--json", action="store_true", help="Output in JSON format.")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"Error: Target '{target}' does not exist.", file=sys.stderr)
        return 1

    routes, issues = lint_path(target)

    if args.json:
        result = {
            "target": str(target.as_posix()),
            "total_routes": len(routes),
            "total_issues": len(issues),
            "routes": routes,
            "issues": issues,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"=== FastAPI Route & Contract Lint Report ===")
        print(f"Target: {target.as_posix()}")
        print(f"Discovered Routes: {len(routes)}")
        print(f"Total Issues: {len(issues)}\n")

        for r in routes:
            status_desc = f"[status_code={r['status_code']}]" if r["status_code"] else "[default status]"
            model_desc = "✅ Model" if r["has_response_model"] else "⚠️ No Model"
            print(f"  {r['method']:<6} {r['path']:<30} -> {r['function']} ({model_desc}, {status_desc})")

        if issues:
            print("\n--- Identified Issues ---")
            for iss in issues:
                print(f"[{iss['severity']}] {iss['code']} {iss['endpoint']}")
                print(f"  Location: {iss['file']}:{iss['line']}")
                print(f"  Message : {iss['message']}\n")
        else:
            print("\n✅ All routes adhere to schema & contract guidelines.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
