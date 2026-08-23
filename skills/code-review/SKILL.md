---
name: code-review
description: Perform comprehensive code quality, security, and regression review on git diffs or target files.
version: 1.0.0
tags: [review, diff, security, code-quality]
---

# Procedural Knowledge: Code Review Workflow

When performing a code review or auditing changes, execute the following structured analysis:

## Phase 1: Inspect Changes
1. Run `git_diff` or `read_file` to collect the exact changeset.
2. Identify the modified symbols, function signatures, and data flows.

## Phase 2: Correctness & Logic Flow
1. Check off-by-one errors, edge condition handling (None, empty lists, boundary values).
2. Verify exception handling robustness and error propagation paths.

## Phase 3: Security & Sandboxing Boundaries
1. Check for workspace path traversal vulnerabilities (e.g. unvalidated relative path resolution).
2. Check for unauthorized shell execution, dangerous eval/exec calls, or unsanitized user inputs.
3. Check for exposed secrets, API keys, or credentials.

## Phase 4: Maintainability & Architecture
1. Verify adherence to existing project patterns (e.g. BaseTool contracts, DI conventions).
2. Ensure documentation and type hints are accurate.

## Phase 5: Actionable Findings Output
Format review findings into:
* **Critical / Blockers**: Bugs, security issues, or regressions.
* **Suggestions / Improvements**: Performance or readability tips.
* **Positive Highlights**: Clean implementations.
