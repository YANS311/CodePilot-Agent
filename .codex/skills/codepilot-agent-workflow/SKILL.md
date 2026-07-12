---
name: codepilot-agent-workflow
description: "Use for CodePilot Agent repository work: planning and shipping changes, running conda-based pytest checks, replaying evaluation failures, triaging CI failures, maintaining generated artifact hygiene, and preparing PR-ready verification notes for this repo."
---

# CodePilot Agent Workflow

## Overview

Use this skill to move CodePilot Agent changes from local diagnosis to verified PRs without rediscovering the repo workflow each time.

## Core Workflow

1. Inspect `git status --short --branch` and avoid touching unrelated user changes.
2. Read the smallest relevant code and docs before editing.
3. Use the `mini_coding_agent` conda Python for local checks.
4. Match validation depth to risk: targeted tests for narrow changes, CI-equivalent unit plus integration checks for shared behavior.
5. For eval or agent behavior changes, replay the affected task and preserve curated replay artifacts only when they document an intentional recovery.
6. Keep generated timestamped benchmark reports ignored.
7. Before PR, summarize changed files, commands run, and any skipped or unavailable checks.

## When To Read References

- Read `references/commands.md` when you need exact test, replay, CI, Docker, or artifact commands.
- Read repository docs such as `docs/ci_notes.md`, `docs/evaluation.md`, or `docs/architecture.md` only when the task touches those domains.

## Repo-Specific Defaults

- Prefer `C:\Users\A\anaconda3\envs\mini_coding_agent\python.exe` over bare `python`.
- CI mode is `CODEPILOT_CI_MODE=true`; GitHub Actions runs `pytest tests/unit -q --tb=short` and `pytest tests/integration -q --tb=short`.
- Docker is optional and may be unavailable locally; verify Docker before using docker-mode tests.
- Curated replay traces live under `reports/replays/`.
- Generated benchmark reports matching `benchmarks/real_world/reports/eval_*.json` and `eval_*.md` should remain untracked.

## PR Readiness

Before opening or updating a PR, ensure:

- `git status --short` contains only intended tracked changes or expected ignored runtime outputs.
- Relevant tests or replay commands have been run.
- The PR body states verification commands and notes any environment limitations.
