"""Audit existing datasets without changing their tasks, hints or difficulty."""

import ast
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    category: str
    difficulty: str
    source: str
    seed_workspace: str | None
    test_target: str | None
    criterion: str
    mode: str
    prompt: str
    target_exists: bool | None = None
    criterion_coverage: str = "targeted tests; not all prose criteria necessarily covered"


def contained(root, reference):
    path = (Path(root) / reference).resolve()
    path.relative_to(Path(root).resolve())
    return path


def target_exists(seed, target):
    parts = target.split("::")
    path = contained(seed, parts[0])
    if path.is_dir() and len(parts) == 1:
        return any(path.rglob("test_*.py"))
    if not path.is_file():
        return False
    nodes = ast.parse(path.read_text(encoding="utf-8")).body
    for name in parts[1:]:
        node = next((n for n in nodes if getattr(n, "name", None) == name), None)
        if node is None:
            return False
        nodes = getattr(node, "body", [])
    return True


def audit_datasets(root=ROOT, *, collect=False):
    root = Path(root).resolve()
    entries = []
    datasets = (
        ("evaluation/tasks.json", "synthetic", "workspace"),
        ("evaluation/stress_tasks.json", "stress", "workspace"),
        ("benchmarks/real_world/tasks.json", "repository_fixture", None),
        ("evaluation/security_tasks.json", "security", None),
    )
    for source, kind, default_seed in datasets:
        raw_tasks = json.loads(contained(root, source).read_text(encoding="utf-8"))["tasks"]
        for raw in raw_tasks:
            seed = default_seed or (f"benchmarks/real_world/repos/{raw['repo']}" if "repo" in raw else None)
            target = raw.get("test_target") or raw.get("expected_test")
            entries.append(BenchmarkTask(
                task_id=raw["id"], category=raw.get("category", kind), difficulty=raw.get("difficulty", "unspecified"),
                source=source, seed_workspace=seed, test_target=target,
                criterion=raw.get("expected_behavior") or (f"pytest target passes: {target}" if target else f"should_block={raw['should_block']}"),
                mode="live_llm_NOT_RUN" if target else "deterministic_security_contract",
                prompt=raw.get("task") or raw["description"],
                target_exists=target_exists(contained(root, seed), target) if seed and target else None,
            ).model_dump())
    if len({e["task_id"] for e in entries}) != len(entries):
        raise ValueError("Duplicate manifest task ID")
    collection = []
    if collect:
        seeds = sorted({e["seed_workspace"] for e in entries if e["test_target"]})
        for seed in seeds:
            targets = sorted({e["test_target"] for e in entries if e["seed_workspace"] == seed})
            completed = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", *targets],
                                       cwd=contained(root, seed), capture_output=True, timeout=60)
            collection.append({"seed_workspace": seed, "return_code": completed.returncode,
                               "target_count": len(targets), "collectable": completed.returncode == 0})
    return {"schema_version": "1.0", "tasks": entries,
            "counts_by_source": dict(Counter(e["source"] for e in entries)),
            "missing_test_targets": [e["task_id"] for e in entries if e["target_exists"] is False],
            "collection": collection,
            "limitations": ["repository_fixture sources are small authored seeded repositories, not external production projects",
                            "collection/AST checks validate executable targets, not complete prose criterion coverage",
                            "legacy real-world runner references nonexistent ReactAgent/app.config; use the new EvaluationRunner adapter"]}


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        raise ValueError("Unsupported benchmark manifest")
    entries = [BenchmarkTask.model_validate(item) for item in data["tasks"]]
    if len({entry.task_id for entry in entries}) != len(entries):
        raise ValueError("Duplicate benchmark task ID")
    return entries
